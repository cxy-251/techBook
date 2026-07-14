第一百三十五章：epoll_wait() 怎样把parent挂到eventpoll自己的wait queue？
================================================================================

上一章结束时，eventfd fd 6已经被epoll fd 7监视：

::

   eventfd E->wqh
   → callback entry P
   → ep_poll_callback
   → epitem I
   → eventpoll EP

但 ``E->count=0``，所以 ``I`` 只存在于interest rbtree，不在ready list：

::

   EP->rbr     = { I }
   EP->rdllist = empty

parent现在调用：

.. code-block:: c

   struct epoll_event events[1];
   epoll_wait(7, events, 1, -1);

固定条件继续保持：

* CPU0是唯一online CPU；
* parent与helper共享fd 6、fd 7以及同一 ``files_struct``；
* parent与helper均为 ``SCHED_NORMAL``；
* timeout为-1，表示无限等待；
* ``events`` 是可写的单元素用户数组；
* 没有pending signal、ptrace、seccomp、freezer或spurious wake；
* eventfd不是socket，不进行NAPI busy poll；
* helper当前可运行，并将在parent真正阻塞后得到CPU0；
* eventfd counter在整个本章保持0；
* 没有其他epoll waiter或ready item。

本章结束时parent已经作为exclusive waiter加入 ``EP->wq`` 并从CPU0调度出去。eventfd上的callback entry ``P`` 仍然存在，但它与parent的wait entry不是同一个对象。

epoll_wait怎样解析epoll fd
-------------------------

native x86-64 syscall进入：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_epoll_wait(7, events, 1, -1)

``epoll_wait`` 把毫秒timeout转换为内部timespec指针。 ``timeout=-1`` 时：

::

   ep_timeout_to_timespec(...) → NULL

传给 ``ep_poll`` 的 ``timeout`` 指针为NULL，表示没有截止时间，不建立一次性timeout hrtimer。

``do_epoll_wait`` 取得fd 7对应的eventpoll file ``F7``，并检查：

* ``maxevents=1`` 大于0且未超过上限；
* 用户数组覆盖一个 ``struct epoll_event``；
* ``F7->f_op`` 确实是 ``eventpoll_fops``。

然后得到：

::

   EP = F7->private_data

并调用：

::

   ep_poll(EP, events, 1, NULL)

第一次ready检查为什么是空
-------------------------

``ep_poll`` 先无锁调用：

.. code-block:: c

   eavail = ep_events_available(EP);

``ep_events_available`` 通过seqcount与careful list检查判断：

::

   EP->rdllist empty
   EP not scanning
   sequence stable
   → eavail = false

这个第一次检查允许与callback并发，源码明确承认它是racy的。安全性不依赖这次结果绝对准确；如果要睡眠，parent还会在 ``EP->lock`` 下做最后一次检查并同时入队。

由于没有ready event， ``ep_try_send_events`` 不执行。timeout不是0，所以也不能直接返回0。

为什么不进入busy poll
---------------------

``ep_poll`` 随后调用：

::

   ep_busy_loop(EP)

当前watched file是eventfd，不是带NAPI id的socket；固定场景也没有配置per-epoll busy-poll参数。因此：

::

   ep_busy_loop → false

parent不会在用户期望的无限等待之前先自旋消费网络budget。

栈上wait entry怎样初始化
-----------------------

确认没有pending signal后， ``ep_poll`` 在parent当前kernel stack上建立：

::

   wait_queue_entry_t W

先通过 ``init_wait(&W)`` 初始化，再把默认callback替换为：

::

   W.func = ep_autoremove_wake_function

该callback内部调用 ``default_wake_function``，无论实际wake是否成功，都会执行：

::

   list_del_init_careful(&W.entry)

因此正常唤醒时，waker负责把parent的栈上entry从 ``EP->wq`` 自动移除。parent恢复后通常不需要再获取 ``EP->lock`` 删除同一个entry。

最终检查与入队必须在同一把锁下
------------------------------

parent获取：

::

   spin_lock_irq(EP->lock)

本地IRQ在临界区内关闭。锁内首先设置：

.. code-block:: c

   __set_current_state(TASK_INTERRUPTIBLE);

随后再次调用：

::

   ep_events_available(EP)

固定此时callback尚未发生， ``EP->rdllist`` 仍为空，因此：

::

   eavail = false

parent立即执行：

.. code-block:: c

   __add_wait_queue_exclusive(&EP->wq, &W);

``W`` 带有 ``WQ_FLAG_EXCLUSIVE``，被加到 ``EP->wq`` 尾部。

把最终ready检查、task state发布和wait queue入队放在 ``EP->lock`` 下，封闭了典型lost-wakeup窗口：

::

   callback cannot both
   - observe no waiter
   - and publish readiness
   between parent's final check and queue insertion

callback侧在修改 ``EP->rdllist`` 与检查 ``EP->wq`` 时也持有同一把 ``EP->lock``。

两条wait queue为什么完全不同
----------------------------

此时系统里同时存在两条等待边：

第一条属于watched eventfd：

::

   E->wqh
   → eppoll_entry P
   → P.wait.func = ep_poll_callback

第二条属于eventpoll实例：

::

   EP->wq
   → parent stack entry W
   → W.func = ep_autoremove_wake_function

它们的用途不同：

* ``E->wqh`` 接收eventfd readiness变化；
* ``P`` 把这种变化翻译成epitem ready状态；
* ``EP->wq`` 保存真正阻塞在 ``epoll_wait`` 中的task；
* ``W`` 最终把parent从 ``TASK_INTERRUPTIBLE`` 变回runnable。

所以eventfd write不会直接通过 ``P`` 把用户event复制到parent。它先运行epoll callback更新ready list，然后epoll callback再唤醒 ``EP->wq`` 上的parent。

parent怎样真正离开CPU0
---------------------

parent释放：

::

   spin_unlock_irq(EP->lock)

此时本地IRQ重新打开，但parent状态仍是：

::

   TASK_INTERRUPTIBLE

因为 ``eavail=false``，它执行：

::

   schedule_hrtimeout_range(NULL, 0, HRTIMER_MODE_ABS)

NULL deadline表示无限等待。该函数最终进入scheduler：

::

   schedule
   → __schedule

scheduler观察到parent不是 ``TASK_RUNNING``，将它从CPU0当前执行位置切出。固定场景没有其他runnable task，只有helper可运行，因此发生：

::

   context switch: parent → helper

parent原kernel stack停在 ``schedule_hrtimeout_range`` 内。它还没有返回 ``epoll_wait``，用户态 ``events[0]`` 尚未被写入。

阻塞完成后的对象状态
--------------------

helper成为CPU0当前执行者时：

::

   parent state      = TASK_INTERRUPTIBLE
   parent on_rq      = 0
   parent on_cpu     = 0
   W linked in EP->wq
   I remains in EP->rbr
   I not in EP->rdllist
   P remains linked in E->wqh
   E->count          = 0

``EP->mtx`` 没有被parent持有。阻塞等待只需要 ``EP->lock`` 完成最后检查与入队，释放后才调用scheduler。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：helper；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3，helper已从scheduler返回用户态；
* helper scheduling class：``SCHED_NORMAL``；
* parent syscall：``epoll_wait(7, events, 1, -1)`` 尚未返回；
* parent state：``TASK_INTERRUPTIBLE``；
* parent ``on_rq=0``、 ``on_cpu=0``；
* parent kernel stack：停在 ``schedule_hrtimeout_range`` / scheduler返回点；
* parent wait entry ``W``：挂在 ``EP->wq``， ``WQ_FLAG_EXCLUSIVE``；
* ``W.func``：``ep_autoremove_wake_function``；
* ``EP->wq``：包含parent ``W``；
* ``EP->lock``：unlocked；
* ``EP->mtx``：unlocked；
* ``EP->rbr``：包含 ``I``；
* ``EP->rdllist``：empty；
* ``EP->ovflist``：``EP_UNACTIVE_PTR``；
* eventfd ``E->count``：0；
* ``E->wqh``：仍包含epoll callback entry ``P``；
* ``P``：non-exclusive；
* 用户态 ``events[0]``：尚未由kernel写入；
* timeout hrtimer：none；
* pending signal：none；
* next control entry：helper调用 ``write(6, &five, 8)``，其中 ``five=5``。

关键边界
--------

#. ``timeout=-1`` 转换为NULL deadline，不建立timeout hrtimer。
#. 第一次ready检查可以racy；睡眠前会在 ``EP->lock`` 下再次检查。
#. parent的wait entry存在于 ``EP->wq``，不在eventfd ``E->wqh``。
#. eventfd上的 ``P`` 是callback entry，eventpoll上的 ``W`` 才指向parent task。
#. ``P`` 是non-exclusive， ``W`` 是exclusive。
#. task state、最后ready检查与wait queue入队由 ``EP->lock`` 串联，防止lost wakeup。
#. parent在释放 ``EP->lock`` 后才调用scheduler。
#. 阻塞时不持有 ``EP->mtx``，否则ctl与event delivery将无法继续。
#. 用户event buffer只有在parent恢复并执行event delivery时才会被写入。
#. 当前没有ready item；wake的前提是helper先改变eventfd readiness。

下一任务
--------

下一章追踪完整wake与delivery闭环：

::

   helper write(6, u64 5)
   → E->count 0 → 5
   → wake_up_locked_poll(E->wqh, EPOLLIN)
   → ep_poll_callback(P)
   → I enters EP->rdllist
   → wake parent W on EP->wq
   → parent resumes ep_poll
   → copy { EPOLLIN, data=0xEFD6 } to userspace
   → level-triggered I remains ready
   → epoll_wait returns 1

资料
----

* `Linux 7.2-rc1 fs/eventpoll.c：ep_poll、exclusive wait entry与scheduler入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
* `Linux 7.2-rc1 kernel/sched/wait.c：wait entry、exclusive queue与default wake <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/wait.c>`_
* `Linux 7.2-rc1 kernel/sched/core.c：schedule与__schedule <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/core.c>`_
* `Linux 7.2-rc1 kernel/time/hrtimer.c：schedule_hrtimeout_range的无限等待路径 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/hrtimer.c>`_
