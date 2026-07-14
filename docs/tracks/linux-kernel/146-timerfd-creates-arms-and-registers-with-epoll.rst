第一百四十六章：timerfd怎样建立一次性hrtimer并让parent阻塞在epoll_wait？
================================================================================

上一批已经释放signalfd与eventpoll对象。现在开始一个独立运行期实验。

固定用户程序顺序：

.. code-block:: c

   int tfd = timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC);   /* fd 6 */

   struct itimerspec its = {
       .it_value    = { .tv_sec = 0, .tv_nsec = 20 * 1000 * 1000 },
       .it_interval = { .tv_sec = 0, .tv_nsec = 0 },
   };
   timerfd_settime(tfd, 0, &its, NULL);

   int epfd = epoll_create1(EPOLL_CLOEXEC);                  /* fd 7 */
   struct epoll_event ev = {
       .events   = EPOLLIN,
       .data.u64 = 0x71FD6,
   };
   epoll_ctl(epfd, EPOLL_CTL_ADD, tfd, &ev);
   epoll_wait(epfd, events, 1, -1);

固定条件：

* CPU0是唯一online CPU；
* parent与helper属于同一TGID，共享 ``mm_struct``、``files_struct``、``signal_struct`` 与 ``sighand_struct``；
* 两个线程均为 ``SCHED_NORMAL``；
* helper阻塞在timerfd/epoll之外；
* fd 0..5已经占用，fd 6/7可分配；
* ``CONFIG_HIGH_RES_TIMERS=y``，非PREEMPT_RT；
* CPU0的local APIC clock-event工作在high-resolution one-shot模式；
* ``CLOCK_MONOTONIC`` 不发生clock set、suspend或time namespace变化；
* timer为相对20ms、一次性、无slack、无 ``TFD_TIMER_ABSTIME``、无 ``TFD_TIMER_CANCEL_ON_SET``；
* 所有create、settime、epoll registration与进入wait均在20ms到期前完成；
* epoll使用level-triggered ``EPOLLIN``，不使用 ``EPOLLET``、``EPOLLONESHOT``、``EPOLLEXCLUSIVE`` 或 ``EPOLLWAKEUP``；
* 没有fd、copy、allocation、signal、scheduler或security failure。

本章结束在parent作为exclusive waiter进入eventpoll自己的wait queue并调度出去。timerfd callback尚未执行。

timerfd_create怎样建立ctx与fd 6
-------------------------------

native x86-64进入：

::

   __x64_sys_timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC)
   → timerfd_create

系统调用先验证：

* flags只包含 ``TFD_CLOEXEC``；
* clockid是允许的 ``CLOCK_MONOTONIC``；
* monotonic timer不需要 ``CAP_WAKE_ALARM``。

随后分配 ``struct timerfd_ctx T``。关键字段初始状态来自zeroed allocation与显式初始化：

::

   T.clockid       = CLOCK_MONOTONIC
   T.ticks         = 0
   T.expired       = 0
   T.tintv         = 0
   T.might_cancel  = false
   T.wqh           = initialized, empty
   T.cancel_lock   = initialized

``hrtimer_setup`` 把内嵌 ``T.t.tmr`` 初始化为monotonic hrtimer，callback固定为：

::

   timerfd_tmrproc

create阶段只初始化timer，没有把它排入CPU0的hrtimer tree。

接着：

::

   anon_inode_getfile_fmode("[timerfd]", &timerfd_fops, T,
                            O_RDWR | O_CLOEXEC, FMODE_NOWAIT)
   → FD_ADD
   → fd 6 published

最终file ``F6`` 的重要关系：

::

   fdtable[6]      → F6
   F6->f_op        = timerfd_fops
   F6->private_data= T
   F6 flags        = O_RDWR | O_CLOEXEC

``TFD_CLOEXEC`` 只设置fdtable中的close-on-exec bit。它不让timerfd变成nonblocking，也不改变timer状态。

timerfd_settime怎样把20ms变成绝对expiry
-------------------------------------

parent随后进入：

::

   __x64_sys_timerfd_settime(6, 0, &its, NULL)
   → do_timerfd_settime

内核通过临时fd reference确认fd 6确实使用 ``timerfd_fops``，取得 ``T``。

``timerfd_setup_cancel`` 看到clock是monotonic且flags为0，因此 ``T`` 不加入全局cancel list。

接着在 ``T.wqh.lock`` 下停止旧timer。固定timer从未armed：

::

   hrtimer_try_to_cancel(T.t.tmr) = 0

旧状态写入内核临时 ``old``：remaining=0、interval=0。用户传入 ``otmr=NULL``，所以不会copy回用户空间。

``timerfd_setup`` 重置：

::

   T.expired = 0
   T.ticks   = 0
   T.tintv   = 0

20ms的 ``it_value`` 转为 ``ktime_t``，mode是 ``HRTIMER_MODE_REL``。``hrtimer_setup`` 重新初始化内嵌timer后，调用：

::

   hrtimer_start_range_ns_user(T.t.tmr,
                               20ms,
                               0,
                               HRTIMER_MODE_REL)

hrtimer core在CPU0的monotonic clock base上计算：

::

   absolute expiry = current CLOCK_MONOTONIC time + 20ms

然后把timer插入对应active RB tree。如果它成为最早到期timer，core重新编程CPU0的local APIC clock-event deadline。

固定20ms仍在未来，因此该调用返回“timer已queued”，不会同步执行callback。

settime完成时：

::

   T.t.tmr     = queued on CPU0 monotonic hrtimer base
   T.tintv     = 0
   T.ticks     = 0
   T.expired   = 0
   settime_flags = 0

parent返回CPL 3， ``timerfd_settime`` result为0。

epoll_create1怎样建立fd 7
-------------------------

parent执行：

::

   epoll_create1(EPOLL_CLOEXEC)

内核分配eventpoll对象 ``EP``，初始化：

::

   EP.mtx
   EP.lock
   EP.wq
   EP.poll_wait
   EP.rbr       = empty
   EP.rdllist   = empty
   EP.ovflist   = EP_UNACTIVE_PTR
   EP.refcount  = 1

``[eventpoll]`` anon-inode file ``F7`` 发布为shared fd 7，close-on-exec bit为1。

epoll_ctl怎样在timerfd wait queue上挂callback
--------------------------------------------

``epoll_ctl(7, EPOLL_CTL_ADD, 6, &ev)`` 解析 ``F7`` 与 ``F6``，锁住 ``EP.mtx``，为key：

::

   (target file F6, userspace fd number 6)

分配epitem ``I``。用户只提交 ``EPOLLIN``，内核存储mask包含：

::

   EPOLLIN | EPOLLERR | EPOLLHUP

并保存：

::

   I.event.data.u64 = 0x71FD6

``I`` 加入 ``EP.rbr``，并通过reverse link加入 ``F6->f_ep``。epitem持有一个eventpoll reference：

::

   EP.refcount: 1 → 2

首次 ``ep_item_poll`` 调用 ``timerfd_poll(F6, epq.pt)``。timerfd poll先执行：

::

   poll_wait(F6, &T.wqh, epq.pt)

这让epoll分配 ``eppoll_entry P``：

::

   P.wait.func = ep_poll_callback
   P.whead     = &T.wqh
   P.epi       = I

``P`` 以non-exclusive entry挂入 ``T.wqh``。

随后 ``timerfd_poll`` 在 ``T.wqh.lock`` 下检查 ``T.ticks``。此时timer尚未到期：

::

   T.ticks = 0
   → no EPOLLIN

因此registration完成时：

::

   EP.rbr      contains I
   EP.rdllist  empty
   T.wqh       contains callback P

parent怎样阻塞在另一条wait queue
-------------------------------

parent执行：

::

   epoll_wait(7, events, 1, -1)

initial ready check发现 ``EP.rdllist`` 为空。``ep_poll`` 在parent kernel stack上建立wait entry ``W``：

::

   W.func = ep_autoremove_wake_function

在 ``EP.lock`` 下：

::

   parent state = TASK_INTERRUPTIBLE
   add W exclusively to EP.wq

这里存在两条完全不同的wait queue：

::

   T.wqh  : contains non-exclusive epoll callback P
   EP.wq  : contains exclusive sleeping task entry W

``P`` 用于把目标timerfd readiness传递给eventpoll；``W`` 用于让eventpoll唤醒parent task。

parent调用scheduler后从CPU0移出：

::

   parent TASK_INTERRUPTIBLE
   parent on_rq = 0
   parent on_cpu = 0

helper已经阻塞，所以CPU0进入idle task，等待local APIC timer deadline。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：CPU0 idle task；
* CPU mode：x86-64 CPL 0 idle path；
* parent：``TASK_INTERRUPTIBLE``，阻塞在 ``EP.wq``；
* helper：阻塞在timerfd/epoll之外；
* fd 6：open blocking timerfd ``F6``，close-on-exec；
* timerfd ctx ``T``：active；
* ``T.t.tmr``：queued on CPU0 monotonic hard-hrtimer base；
* expiry：arm时monotonic time + 20ms；
* ``T.tintv``：0；
* ``T.ticks``：0；
* ``T.expired``：0；
* ``T.wqh``：包含non-exclusive callback ``P``；
* fd 7：open eventpoll ``F7``，close-on-exec；
* eventpoll ``EP``：active， ``refcount=2``；
* ``EP.rbr``：包含epitem ``I``；
* ``EP.rdllist``：empty；
* ``EP.wq``：包含parent exclusive waiter ``W``；
* stored event：``EPOLLIN|EPOLLERR|EPOLLHUP``，data ``0x71FD6``；
* filesystem/block I/O：none；
* next control entry：CPU0的 ``sysvec_apic_timer_interrupt``。

关键边界
--------

#. timerfd ctx内嵌hrtimer、expiration counter和自己的wait queue。
#. create初始化hrtimer，但不arm它； ``timerfd_settime`` 才把timer放入CPU base。
#. relative 20ms在hrtimer core中转换为monotonic absolute expiry。
#. one-shot由 ``it_interval=0`` 表示，不会自动周期重启。
#. ``TFD_CLOEXEC`` 只影响fdtable close-on-exec bookkeeping。
#. timerfd file使用 ``O_RDWR``，但用户主要通过read取得expiration count。
#. epoll registration把callback ``P`` 挂到 ``T.wqh``。
#. sleeping parent的waiter ``W`` 挂到 ``EP.wq``，不是 ``T.wqh``。
#. ``P`` non-exclusive， ``W`` exclusive。
#. timerfd尚未到期时，初始poll不产生ready-list membership。
#. epitem持有eventpoll reference，使 ``EP.refcount`` 从1变为2。
#. parent阻塞后CPU0进入idle，timer仍由local APIC clock-event驱动。

下一任务
--------

下一章从CPU0收到local APIC timer vector开始：

::

   sysvec_apic_timer_interrupt
   → local_apic_timer_interrupt
   → clock-event handler hrtimer_interrupt
   → run expired T.t.tmr
   → timerfd_tmrproc
   → T.ticks 0 → 1
   → wake_up_locked_poll(T.wqh, EPOLLIN)
   → epoll callback queues I
   → wake parent W

资料
----

* `Linux 7.2-rc1 fs/timerfd.c：timerfd create、settime、poll与ctx <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/timerfd.c>`_
* `Linux 7.2-rc1 kernel/time/hrtimer.c：relative timer enqueue与clock-event reprogram <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/hrtimer.c>`_
* `Linux 7.2-rc1 fs/eventpoll.c：epoll registration与wait queues <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
* `Linux 7.2-rc1 fs/anon_inodes.c：timerfd与eventpoll pseudo files <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/anon_inodes.c>`_
