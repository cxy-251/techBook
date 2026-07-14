第一百三十六章：eventfd write怎样触发epoll callback并让epoll_wait返回1？
================================================================================

上一章结束时，parent已经阻塞在eventpoll自己的wait queue上：

::

   eventfd E->wqh
   → callback entry P
   → ep_poll_callback
   → epitem I
   → eventpoll EP
   → EP->wq
   → parent wait entry W

固定状态：

::

   E->count       = 0
   I in EP->rbr   = yes
   I in rdllist   = no
   parent state   = TASK_INTERRUPTIBLE
   helper current = CPU0 / CPL3

helper现在执行：

.. code-block:: c

   uint64_t five = 5;
   write(6, &five, 8);

本章固定条件继续保持：

* level-triggered ``EPOLLIN``；
* 不启用 ``EPOLLET``、 ``EPOLLONESHOT`` 或 ``EPOLLEXCLUSIVE``；
* event data为 ``0xEFD6``；
* 没有其他eventfd waiter、epoll waiter或ready item；
* helper写入后主动阻塞在eventfd之外，使scheduler选择parent；
* parent用户event数组有效；
* 没有signal、copy fault、counter overflow、spurious wake或并发 ``epoll_ctl``；
* parent在本章不读取eventfd counter。

本章结束时 ``epoll_wait`` 返回1，用户得到 ``EPOLLIN`` 与data ``0xEFD6``。eventfd counter仍为5；由于采用level-triggered模式，epitem ``I`` 会重新留在ready list中。

helper怎样把counter从0改成5
--------------------------

``write(6, &five, 8)`` 沿VFS进入：

::

   __x64_sys_write
   → ksys_write
   → vfs_write
   → eventfd_write(F6, &five, 8, ...)

``eventfd_write`` 先从用户态复制8字节：

::

   ucnt = 5

它拒绝 ``ULLONG_MAX``，并检查counter是否有足够空间。当前：

::

   ULLONG_MAX - E->count > 5

条件成立，helper获取：

::

   spin_lock_irq(E->wqh.lock)

锁内执行：

::

   E->count: 0 → 5

counter修改发生在wake之前，因此callback即使立即运行，也能在后续poll中看到新值。

eventfd wake首先调用谁
---------------------

``E->wqh`` 不是空队列：里面有第一百三十四章安装的 ``P.wait``。所以eventfd执行：

.. code-block:: c

   wake_up_locked_poll(&E->wqh, EPOLLIN);

调用发生时 ``E->wqh.lock`` 已由helper持有，本地IRQ关闭。wait queue遍历到 ``P.wait``，调用：

::

   P.wait.func(P.wait, mode, sync, poll_to_key(EPOLLIN))
   → ep_poll_callback

此处没有直接唤醒parent。 ``P`` 指向epitem ``I``，callback先把watched-file readiness翻译成eventpoll ready-list状态。

ep_poll_callback怎样过滤event mask
----------------------------------

callback取得：

::

   I  = P->base
   EP = I->ep
   pollflags = EPOLLIN

然后获取IRQ-safe：

::

   spin_lock_irqsave(EP->lock)

当前 ``I->event.events`` 为：

::

   EPOLLIN | EPOLLERR | EPOLLHUP

它包含普通poll bit，不是被 ``EPOLLONESHOT`` 禁用的item。incoming key为 ``EPOLLIN``，与interest mask相交，因此callback继续。

如果key与interest不相交，例如只有 ``EPOLLOUT``，callback会在此处退出，不把item加入ready list，也不会唤醒 ``epoll_wait``。

I怎样进入ready list
-------------------

当前没有event delivery scan：

::

   EP->ovflist = EP_UNACTIVE_PTR

所以 ``ep_is_scanning(EP)`` 为false。 ``I`` 也尚未链接到 ``EP->rdllist``，callback执行：

.. code-block:: c

   list_add_tail(&I->rdllink, &EP->rdllist);

状态变成：

::

   EP->rbr     = { I }
   EP->rdllist = { I }

interest rbtree中的成员关系没有变化。ready list只是给同一个epitem增加另一条链。

callback怎样唤醒parent
---------------------

callback仍持有 ``EP->lock``，检查：

::

   waitqueue_active(&EP->wq) = true

由于 ``I`` 没有 ``EPOLLEXCLUSIVE``，它调用普通：

::

   wake_up(&EP->wq)

``EP->wq`` 中唯一entry是parent的exclusive ``W``。通用wake路径调用：

::

   W.func
   → ep_autoremove_wake_function
   → default_wake_function
   → try_to_wake_up(parent)

parent从：

::

   TASK_INTERRUPTIBLE

转换为：

::

   TASK_WAKING
   → acquire CPU0 rq lock
   → enqueue parent
   → TASK_RUNNING

同时 ``ep_autoremove_wake_function`` 无条件执行：

::

   list_del_init_careful(&W.entry)

所以parent已经从 ``EP->wq`` 移除。

callback只让parent变成runnable。parent尚未运行，用户event数组也尚未写入。

helper怎样结束write
-------------------

callback释放 ``EP->lock`` 并返回wait queue遍历。由于 ``P`` 不是exclusive callback entry，返回值不会消费eventfd wait queue的exclusive quota；本场景没有其他entry。

控制回到 ``eventfd_write``：

::

   spin_unlock_irq(E->wqh.lock)
   → return 8

helper回到CPL 3时：

::

   write result = 8
   E->count     = 5
   parent       = TASK_RUNNING, on_rq=1, on_cpu=0
   I            = linked in EP->rdllist

固定用户程序随后让helper阻塞在eventfd之外。scheduler选择已经runnable的parent。

parent从原schedule点恢复
-----------------------

context switch恢复parent停在 ``schedule_hrtimeout_range`` 内的原kernel stack。无限等待因wake而结束，parent执行：

::

   __set_current_state(TASK_RUNNING)
   eavail = true

它检查 ``W.entry``，发现callback已经执行autoremove，所以list为空，不需要再次获取 ``EP->lock`` 删除wait entry。

``ep_poll`` 回到循环顶部。由于 ``eavail=true``，调用：

::

   ep_try_send_events
   → ep_send_events

ready scan怎样取得I
-------------------

``ep_send_events`` 获取：

::

   mutex_lock(EP->mtx)

然后 ``ep_start_scan`` 短暂获取 ``EP->lock``：

::

   move EP->rdllist → local scan_batch
   set EP->ovflist = NULL

状态变为scan active：

::

   EP->rdllist = empty
   scan_batch  = { I }
   EP->ovflist = NULL

如果此时发生新的callback，它不会直接修改正在遍历的 ``scan_batch``，而会把epitem放入 ``ovflist``。固定场景没有第二次write，因此 ``ovflist`` 保持NULL。

epoll_wait为什么必须重新poll eventfd
------------------------------------

``ep_deliver_event`` 先把 ``I`` 从 ``scan_batch`` 链中移除，再调用：

::

   ep_item_poll(I, poll_table-without-qproc, 1)
   → eventfd_poll(F6, pt)

这次poll table没有queue callback，所以 ``poll_wait`` 不会再次安装wait entry。原来的 ``P`` 仍在 ``E->wqh`` 上。

``eventfd_poll`` 读取：

::

   E->count = 5

返回：

::

   EPOLLIN | EPOLLOUT

``ep_item_poll`` 与interest mask相交后得到：

::

   revents = EPOLLIN

``EPOLLOUT`` 不会交给用户，因为用户没有为这个epitem注册它。 ``EPOLLERR|EPOLLHUP`` 虽在interest mask中，但当前eventfd没有报告这些bit。

用户event怎样被写入
-------------------

``epoll_put_uevent`` 将一个 ``struct epoll_event`` 写入用户数组：

::

   events[0].events   = EPOLLIN
   events[0].data.u64 = 0xEFD6

这里返回的data完全来自 ``epoll_ctl`` 时保存在 ``I->event.data`` 的值。它不是内核自动填入的fd 6，也不是eventfd counter 5。

用户程序若希望通过data找到业务对象，必须自己在注册时编码指针、索引或tag。

level-triggered为什么把I重新排入ready list
------------------------------------------

交付成功后， ``I`` 没有 ``EPOLLONESHOT``，也没有 ``EPOLLET``。所以 ``ep_deliver_event`` 执行：

.. code-block:: c

   list_add_tail(&I->rdllink, &EP->rdllist);

原因是epoll只报告readiness，没有消费eventfd数据。当前：

::

   E->count = 5

eventfd仍然可读。level-triggered语义要求下一次 ``epoll_wait`` 再次检查并继续报告 ``EPOLLIN``。

``ep_done_scan`` 随后：

::

   drain empty ovflist
   EP->ovflist = EP_UNACTIVE_PTR
   merge remaining scan_batch

``scan_batch`` 已空，而 ``I`` 已直接在 ``EP->rdllist``，所以最终：

::

   EP->rdllist = { I }

这不是重复插入。 ``I`` 在开始delivery时已从旧ready链摘除，只在level-triggered分支重新加入一次。

epoll_wait怎样返回1
-------------------

``ep_send_events`` 已成功交付一个event：

::

   res = 1

它释放 ``EP->mtx``，逐层返回：

::

   ep_send_events
   → ep_try_send_events
   → ep_poll
   → do_epoll_wait
   → __x64_sys_epoll_wait
   → syscall exit

固定没有signal或reschedule work，parent回到CPL 3：

::

   RAX = 1
   RIP = instruction after epoll_wait syscall

返回值1表示写入了一个 ``struct epoll_event``，不是字节数。eventfd write返回8，epoll_wait返回1，两者单位不同。

本章没有读取counter
------------------

``epoll_wait`` 的职责只有报告ready。它没有调用 ``eventfd_read``，所以：

::

   E->count remains 5

用户随后必须显式：

.. code-block:: c

   read(6, &value, 8);

才能消费counter。若立即再次调用 ``epoll_wait``，level-triggered ``I`` 仍在ready list，通常会再次返回 ``EPOLLIN``。

这也是epoll使用中的核心边界：

::

   readiness notification
   ≠
   data consumption

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：eventfd EPOLLIN callback与epoll_wait delivery complete；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* scheduling class：``SCHED_NORMAL``；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、 ``on_cpu=1``；
* parent latest syscall：``epoll_wait(7, events, 1, -1)``；
* parent return/RAX：1；
* ``events[0].events``：``EPOLLIN``；
* ``events[0].data.u64``：``0xEFD6``；
* helper write result：8；
* helper：阻塞在eventfd之外；
* fd 6：eventfd file ``F6``，open；
* eventfd ctx ``E``：active；
* ``E->count``：5；
* ``E->wqh``：仍包含callback entry ``P``；
* fd 7：eventpoll file ``F7``，open；
* eventpoll ``EP``：active；
* ``EP->rbr``：包含epitem ``I``；
* ``EP->rdllist``：包含 ``I``；
* ``EP->ovflist``：``EP_UNACTIVE_PTR``；
* ``EP->wq``：不再包含parent ``W``；
* parent stack wait entry ``W``：生命周期结束；
* epoll callback entry ``P``：仍active；
* ``I`` trigger mode：level-triggered；
* ``I->event.events``：``EPOLLIN|EPOLLERR|EPOLLHUP``；
* ``I->event.data``：``0xEFD6``；
* eventfd counter consumption：none；
* filesystem/block I/O：none；
* next runtime scenario：unselected。

关键边界
--------

#. eventfd先修改counter，再发出 ``EPOLLIN`` wake。
#. ``ep_poll_callback`` 先更新ready list，再唤醒 ``EP->wq`` 上的task。
#. callback entry ``P`` 不是parent；它是readiness翻译器。
#. wake只让parent runnable，不执行用户event copy。
#. parent恢复原 ``epoll_wait`` kernel stack后才扫描ready list。
#. event delivery前必须重新调用watched file的 ``poll`` 验证当前readiness。
#. 用户只注册 ``EPOLLIN``，所以eventfd同时报告的 ``EPOLLOUT`` 被mask掉。
#. returned data来自注册时的 ``event.data``，不是fd或counter。
#. ``epoll_wait`` 返回值1是event数量；eventfd write返回值8是字节数。
#. level-triggered delivery后，仍ready的epitem重新加入 ``rdllist``。
#. ``epoll_wait`` 不消费eventfd counter； ``E->count`` 仍为5。
#. callback entry继续挂在eventfd wait queue上，供后续readiness变化使用。

下一任务
--------

当前没有已选定场景。优先候选是继续处理level-triggered残留ready状态：

::

   parent read(6, &value, 8)
   → consume eventfd count 5 → 0
   → callback receives EPOLLOUT but interest does not match
   → I may still remain on EP->rdllist from prior level-triggered delivery
   parent epoll_wait(7, events, 1, 0)
   → take I from rdllist
   → re-poll eventfd and find no EPOLLIN
   → drop I from ready list
   → return 0

之后可以继续 ``EPOLL_CTL_DEL`` 与fd 6/7的final close，完整释放 ``P``、 ``I`` 与 ``EP``。

资料
----

* `Linux 7.2-rc1 fs/eventfd.c：write修改counter并发出EPOLLIN wake <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventfd.c>`_
* `Linux 7.2-rc1 fs/eventpoll.c：ep_poll_callback、ready list、delivery与level-triggered requeue <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
* `Linux 7.2-rc1 kernel/sched/wait.c：wait callback与task wakeup <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/wait.c>`_
* `Linux 7.2-rc1 kernel/sched/core.c：try_to_wake_up与scheduler恢复 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/core.c>`_
