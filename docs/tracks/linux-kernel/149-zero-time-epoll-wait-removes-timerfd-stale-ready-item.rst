第一百四十九章：零超时epoll_wait() 怎样清理timerfd的stale-ready item？
================================================================================

上一章结束时，parent已经读取一次性timerfd的expiration count：

::

   epoll_wait(7, events, 1, -1) = 1
   read(6, &expirations, 8)     = 8
   expirations                  = 1

读取完成后，timerfd私有对象 ``T`` 的状态已经变成：

::

   T->ticks   = 0
   T->expired = 0
   T->tintv   = 0
   T->t.tmr   = inactive

然而level-triggered交付曾把epitem ``I`` 重新放回 ``EP->rdllist``。因此当前存在一个明确的不一致：

::

   ready-list membership = true
   actual timerfd EPOLLIN readiness = false

parent现在执行：

.. code-block:: c

   struct epoll_event events2[1];
   int n = epoll_wait(7, events2, 1, 0);

本章固定条件：

* CPU0是唯一online CPU；
* parent是当前执行者，处于x86-64 CPL 3；
* fd 6仍是blocking、close-on-exec timerfd；
* fd 7仍是close-on-exec eventpoll file；
* ``EP->rbr`` 包含唯一epitem ``I``；
* ``EP->rdllist`` 包含stale-ready ``I``；
* ``I`` 监听 ``EPOLLIN``，event data为 ``0x71FD6``；
* callback ``P`` 仍以non-exclusive entry挂在 ``T->wqh``；
* ``T->ticks=0``，没有新的timer expiration；
* 没有并发 ``timerfd_settime``、read、epoll_ctl、close或callback；
* 没有signal、copy fault、scheduler migration或内存错误。

本章结束在 ``epoll_wait`` 返回0： ``I`` 仍是有效registration并继续位于 ``EP->rbr``，但已经不在ready list中。

零超时怎样进入epoll内核路径
----------------------------

native x86-64入口为：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_epoll_wait
   → do_epoll_wait
   → ep_poll

``epoll_wait`` 参数为：

::

   epfd      = 7
   maxevents = 1
   timeout   = 0 ms

内核先验证：

* fd 7存在且是eventpoll file；
* ``events2`` 能写入一个 ``struct epoll_event``；
* ``maxevents=1`` 合法。

0毫秒timeout经 ``ep_timeout_to_timespec`` 变成零timespec。 ``ep_poll`` 因此设置：

::

   timed_out = 1
   to        = NULL

这里不会建立hrtimer，也不会把parent挂到 ``EP->wq``。

为什么零超时仍然进入ready scan
-------------------------------

``ep_poll`` 首先执行：

::

   eavail = ep_events_available(EP)

``EP->rdllist`` 当前仍包含 ``I``，所以初始 ``eavail=true``。即使timeout为0，已有ready candidate仍必须先被重新检查：

::

   ep_try_send_events
   → ep_send_events

zero timeout只禁止等待未来事件，不会跳过当前ready list。

这一区别必须明确：

::

   timeout = 0
   means
   do not sleep for a new event

并不意味着：

::

   trust every existing ready-list entry without re-polling

scan怎样暂时搬走I
-----------------

``ep_send_events`` 获取：

::

   mutex_lock(&EP->mtx)

然后调用 ``ep_start_scan``。在 ``EP->lock`` 下：

::

   splice EP->rdllist into local scan_batch
   EP->rdllist becomes empty
   EP->ovflist enters scan-active state

此刻 ``I`` 位于当前parent内核栈上的局部 ``scan_batch``，不再位于共享ready list。

``EP->mtx`` 保证本次delivery期间，用户线程不能通过 ``epoll_ctl`` 修改或删除 ``I``。 ``EP->lock`` 则保护ready-list和overflow-list状态切换。

ep_deliver_event为什么重新调用timerfd_poll
-----------------------------------------

``ep_deliver_event`` 首先执行：

::

   list_del_init(&I->rdllink)

然后调用：

::

   ep_item_poll(I, &pt, 1)
   → timerfd_poll(F6, &pt)

这不是直接读取旧callback结果。epoll把ready-list entry只视为“需要重新确认的候选”。

本次 ``poll_table`` 的queue callback为NULL，因此 ``timerfd_poll`` 内的：

.. code-block:: c

   poll_wait(file, &T->wqh, wait);

不会新增第二个callback entry。原来的 ``P`` 继续存在，registration结构不改变。

timerfd_poll怎样判定当前不再ready
---------------------------------

``timerfd_poll`` 获取：

::

   spin_lock_irqsave(&T->wqh.lock)

然后只检查：

.. code-block:: c

   if (T->ticks)
       events |= EPOLLIN;

上一章的 ``timerfd_read_iter`` 已经在同一waitqueue lock下完成：

::

   T->ticks:   1 → 0
   T->expired: 1 → 0

固定期间没有新expiration，所以本次观察为：

::

   T->ticks = 0
   revents  = 0

释放 ``T->wqh.lock`` 后， ``ep_item_poll`` 还会与 ``I->event.events`` 做mask运算。结果仍然是0。

为什么I不会重新进入ready list
-----------------------------

``ep_deliver_event`` 对 ``revents=0`` 直接返回0：

* 不调用 ``epoll_put_uevent``；
* 不向 ``events2[0]`` copy任何event；
* 不执行level-triggered requeue；
* 不把 ``I`` 放回局部 ``scan_batch``；
* 不删除 ``I`` 的registration。

因此本次scan结束时：

::

   delivered events = 0
   I in EP->rdllist = false
   I in EP->rbr     = true
   P on T->wqh      = true

``ep_done_scan`` 将overflow状态恢复为 ``EP_UNACTIVE_PTR``。没有并发callback， ``EP->ovflist`` 没有spill entry，局部 ``scan_batch`` 也为空。

epoll_wait为什么直接返回0
-------------------------

``ep_send_events`` 返回0， ``ep_poll`` 随后检查：

::

   if (timed_out)
       return 0;

因为这是zero-time operation，它不会继续进入：

* ``init_wait``；
* ``__add_wait_queue_exclusive(&EP->wq, ...)``；
* ``TASK_INTERRUPTIBLE``；
* ``schedule_hrtimeout_range``；
* scheduler context switch。

syscall返回路径把：

::

   RAX = 0

带回CPL 3。 ``events2`` 没有被内核写入有效event，用户程序不能把其中旧字节当成返回结果。

清理ready状态是否会丢失未来expiration
-----------------------------------

不会。 ``I`` 虽然离开 ``EP->rdllist``，callback ``P`` 仍挂在 ``T->wqh``。

若在未来重新arm timerfd并再次到期：

::

   timerfd callback
   → T->ticks becomes nonzero
   → wake_up_locked_poll(T->wqh, EPOLLIN)
   → P / ep_poll_callback
   → I appended to EP->rdllist again

因此ready-list移除是对当前readiness的校正，不是取消监听。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* last syscall：``epoll_wait(7, events2, 1, 0)``；
* last result/RAX：0；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、 ``on_cpu=1``；
* fd 6：open timerfd file ``F6``；
* timerfd ctx ``T``：active；
* embedded hrtimer：inactive、not queued；
* ``T->ticks``：0；
* ``T->expired``：0；
* ``T->tintv``：0；
* callback ``P``：仍挂在 ``T->wqh``；
* fd 7：open eventpoll file ``F7``；
* eventpoll ``EP``：active， ``refcount=2``；
* ``EP->rbr``：仍包含 ``I``；
* ``EP->rdllist``：empty；
* ``EP->ovflist``：``EP_UNACTIVE_PTR``；
* ``EP->wq``：empty；
* ``I`` registration：active、not ready；
* ``events2``：没有本次有效event；
* helper：阻塞在timerfd/epoll之外；
* filesystem/block I/O：none；
* next control entry：``epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)``。

关键边界
--------

#. zero-time epoll会处理已有ready candidate，但不会等待未来事件。
#. ready-list membership只表示需要重新检查，不保证目标当前仍ready。
#. ``ep_deliver_event`` 在交付前重新调用target ``poll``。
#. re-poll使用NULL queue callback，不会重复安装 ``P``。
#. ``timerfd_poll`` 在 ``T->wqh.lock`` 下以 ``ticks != 0`` 判断 ``EPOLLIN``。
#. ``revents=0`` 时不复制event，也不执行level-triggered requeue。
#. 从ready list移除不等于删除 ``EP->rbr`` registration。
#. callback ``P`` 仍能在未来expiration时重新排入 ``I``。
#. zero-time返回路径不建立waiter、hrtimer或scheduler sleep。
#. 用户只能在return count大于0时读取对应的events数组元素。

下一任务
--------

下一章执行：

::

   epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)
   → remove P from T->wqh
   → clear F6->f_ep last-watcher state
   → erase I from EP->rbr
   → kfree_rcu(I)
   → EP refcount 2 → 1

资料
----

* `Linux 7.2-rc1 fs/eventpoll.c：zero-time ep_poll与event delivery re-poll <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
* `Linux 7.2-rc1 fs/timerfd.c：timerfd_poll的ticks readiness条件 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/timerfd.c>`_
