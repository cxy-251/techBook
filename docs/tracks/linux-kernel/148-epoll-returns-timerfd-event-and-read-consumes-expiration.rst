第一百四十八章：parent怎样从epoll event进入timerfd read并取出expiration count？
================================================================================

上一章结束时，timerfd callback已经完成：

::

   T.ticks = 1
   T.expired = 1
   T.t.tmr inactive
   I on EP.rdllist
   parent TASK_RUNNING on CPU0 runqueue

CPU0从idle interrupt返回路径选择parent。parent恢复的不是一个新syscall，而是原先阻塞的 ``epoll_wait`` kernel stack。

本章固定条件：

* parent恢复前没有第二次timer expiration；
* ``T.tintv=0``，底层hrtimer保持inactive；
* fd 6/7与registration都没有并发修改；
* ``T.ticks`` 在epoll delivery与read之间保持1；
* 用户event buffer与8字节expiration buffer均可写；
* 没有signal、timeout、copy fault、close或scheduler race。

本章结束在parent从timerfd读出 ``u64 expirations=1``，read返回8。fd 6/7与epoll registration继续存在；level-triggered epitem暂时作为stale-ready candidate留在ready list。

parent怎样恢复epoll_wait循环
---------------------------

scheduler恢复parent时：

::

   parent on_cpu = 1
   parent resumes after schedule_hrtimeout_range

``ep_poll`` 把task state恢复为 ``TASK_RUNNING``。wait entry ``W`` 已经由wake function自动移除，所以不需要再次从 ``EP.wq`` 摘除。

循环把 ``eavail`` 视为true，进入：

::

   ep_try_send_events
   → ep_send_events

``ep_send_events`` 锁住 ``EP.mtx``， ``ep_start_scan`` 在 ``EP.lock`` 下把：

::

   EP.rdllist → local scan_batch

``I`` 现在位于当前parent私有的scan batch中。registration仍受 ``EP.mtx`` 保护，其他 ``epoll_ctl`` 无法同时改变它。

为什么必须重新调用timerfd_poll
-----------------------------

ready list只说明callback曾报告“可能ready”。交付前 ``ep_deliver_event`` 先从scan batch摘下 ``I``，再调用：

::

   ep_item_poll(I)
   → vfs_poll(F6)
   → timerfd_poll(F6)

``timerfd_poll`` 先执行 ``poll_wait``。这次poll table没有queue callback，所以不会增加第二个 ``eppoll_entry``；原有 ``P`` 仍挂在 ``T.wqh``。

然后在 ``T.wqh.lock`` 下检查：

::

   T.ticks = 1

因此返回：

::

   EPOLLIN

与 ``I.event.events`` 相交后仍为 ``EPOLLIN``。这一刻才确认event可交付。

epoll怎样复制一个用户event
--------------------------

``epoll_put_uevent`` 向用户 ``events[0]`` 写入：

::

   events[0].events   = EPOLLIN
   events[0].data.u64 = 0x71FD6

固定copy成功，delivery count增加为1。

由于 ``I`` 是level-triggered，既没有 ``EPOLLONESHOT`` 也没有 ``EPOLLET``， ``ep_deliver_event`` 把它重新加入：

::

   EP.rdllist tail

requeue不是因为内核已经知道未来仍ready，而是让下一次 ``epoll_wait`` 再次验证当前level状态。此时 ``T.ticks`` 仍为1，所以requeue与真实readiness一致。

``ep_done_scan`` 完成scan，释放 ``EP.mtx``。 ``epoll_wait`` 返回：

::

   RAX = 1

parent回到CPL 3，用户程序看到一个timerfd ``EPOLLIN`` event。

epoll交付为什么不消费ticks
--------------------------

``timerfd_poll`` 只读取 ``T.ticks``，不会把它清零。epoll也不知道event payload是timer expiration count。

因此在 ``epoll_wait`` 返回后：

::

   T.ticks   = 1
   T.expired = 1

真正消费发生在后续read。

read怎样进入timerfd_read_iter
-----------------------------

parent执行：

.. code-block:: c

   uint64_t expirations;
   read(6, &expirations, sizeof(expirations));

native x86-64路径：

::

   __x64_sys_read
   → ksys_read
   → fdget_pos(6)
   → vfs_read
   → new_sync_read
   → timerfd_read_iter

``timerfd_read_iter`` 首先要求用户buffer至少容纳一个 ``u64``。固定长度为8，因此通过检查。

随后锁住：

::

   T.wqh.lock with IRQ disabled

fd 6不是nonblocking，代码进入：

::

   wait_event_interruptible_locked_irq(T.wqh, T.ticks)

条件 ``T.ticks==1`` 已经成立，所以不会创建wait entry、不会改变task state，也不会调用scheduler。

one-shot read怎样消费状态
-------------------------

本场景不使用realtime cancel-on-set，因此 ``timerfd_canceled(T)`` 返回false。

读路径看到 ``T.ticks`` 非零，保存：

::

   local ticks   = 1
   local expired = 1

随后在锁内清理：

::

   T.expired: 1 → 0
   T.ticks:   1 → 0

代码还检查：

::

   if (expired && T.tintv)
       ticks += timerfd_restart(T)

固定 ``T.tintv=0``，因此不会调用 ``hrtimer_forward_now``，不会重新arm底层timer。用户得到的expiration count保持1。

释放 ``T.wqh.lock`` 后， ``copy_to_iter`` 把8字节值写入用户buffer：

::

   expirations = 1

成功copy返回8，所以整个read返回：

::

   RAX = 8

read之后epitem为什么还在ready list
---------------------------------

``timerfd_read_iter`` 不向 ``T.wqh`` 发送“not ready”通知，也不直接访问任何eventpoll对象。它只把timerfd ctx中的counter清零。

上一阶段level-triggered ``I`` 已经被重新加入 ``EP.rdllist``，所以read后形成：

::

   EP.rdllist contains I
   T.ticks = 0
   actual timerfd EPOLLIN readiness = false

这不是event丢失，而是stale-ready candidate。下一次 ``epoll_wait`` 会再次调用 ``timerfd_poll``，发现 ``ticks=0``，然后把 ``I`` 从ready list移除并返回0；registration仍继续存在。

为什么timerfd read不发送EPOLLOUT wake
-----------------------------------

与eventfd不同，timerfd没有一个可能因counter过大而阻塞的writer。用户不能通过write给timerfd增加ticks。因此read把ticks清零后，不需要用 ``EPOLLOUT`` 唤醒writer。

新的expiration只能来自：

* hrtimer/alarm callback；
* checkpoint/restore ioctl显式设置ticks；
* realtime cancel-on-set路径。

本场景只有第一次hrtimer callback，且one-shot已经inactive。

完整控制流
----------

::

   scheduler selects parent
   → resume original epoll_wait stack
   → ep_send_events scans I
   → timerfd_poll locks T.wqh
   → T.ticks=1 reports EPOLLIN
   → copy events[0]={EPOLLIN,data=0x71FD6}
   → level-triggered I requeued to EP.rdllist
   → epoll_wait returns 1

   parent read(6, &expirations, 8)
   → timerfd_read_iter
   → lock T.wqh
   → wait condition already true
   → local ticks=1
   → T.expired 1→0
   → T.ticks 1→0
   → no periodic restart because T.tintv=0
   → unlock T.wqh
   → copy u64 1 to userspace
   → read returns 8

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：one-shot monotonic timerfd + epoll delivery complete；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* scheduling class：``SCHED_NORMAL``；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、 ``on_cpu=1``；
* helper：阻塞在timerfd/epoll之外；
* timerfd create result：fd 6；
* timerfd_settime result：0；
* epoll create result：fd 7；
* epoll ADD result：0；
* parent ``epoll_wait`` result：1；
* ``events[0].events``：``EPOLLIN``；
* ``events[0].data.u64``：``0x71FD6``；
* timerfd ``read`` result：8；
* userspace ``expirations``：1；
* fd 6：open blocking timerfd ``F6``，close-on-exec；
* timerfd ctx ``T``：active；
* ``T.t.tmr``：inactive、not queued；
* ``T.tintv``：0；
* ``T.expired``：0；
* ``T.ticks``：0；
* ``T.wqh``：仍包含callback ``P``；
* fd 7：open eventpoll ``F7``，close-on-exec；
* eventpoll ``EP``：active， ``refcount=2``；
* callback ``P``：仍挂在 ``T.wqh``；
* ``EP.rbr``：包含epitem ``I``；
* ``EP.rdllist``：包含stale-ready ``I``；
* ``EP.ovflist``：``EP_UNACTIVE_PTR``；
* ``EP.wq``：无parent waiter；
* actual timerfd ``EPOLLIN`` readiness：false；
* parent/helper blocked mask：仍包含上一实验留下的 ``SIGUSR1``；
* private/shared pending ``SIGUSR1``：none；
* filesystem/block I/O：none；
* next runtime scenario：unselected。

关键边界
--------

#. scheduler恢复的是原 ``epoll_wait`` kernel stack，不是重新发起syscall。
#. ready-list item在交付前必须重新调用target ``poll``。
#. timerfd poll只观察ticks，不消费expiration count。
#. level-triggered成功交付后，epitem重新进入ready list。
#. epoll event只携带mask与用户data，不携带expiration count。
#. timerfd read要求至少8字节buffer。
#. ticks已经非零时，blocking read不会真正睡眠。
#. read在 ``T.wqh.lock`` 下把ticks与expired清零。
#. one-shot ``tintv=0`` 使read不执行periodic restart。
#. 用户buffer得到 ``u64 1``，read返回字节数8。
#. timerfd read不发送EPOLLOUT wake，也不直接修改epoll ready list。
#. read后 ``I`` 成为stale-ready candidate，等待下一次epoll scan清理。
#. fd 6/7与registration仍active，本章不执行DEL或close。

下一任务
--------

优先接续是完成timerfd/epoll teardown：

::

   epoll_wait(7, events2, 1, 0)
   → timerfd_poll sees T.ticks=0
   → remove stale-ready I
   → return 0

   epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)
   → remove P from T.wqh
   → erase I and kfree_rcu

   close(6)
   → hrtimer_cancel finds inactive timer
   → timerfd_release kfree_rcu(T)

   close(7)
   → empty eventpoll drain
   → kfree_rcu(EP)

资料
----

* `Linux 7.2-rc1 fs/timerfd.c：timerfd poll、read、ticks消费与periodic restart <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/timerfd.c>`_
* `Linux 7.2-rc1 fs/eventpoll.c：ready scan、re-poll与level-triggered requeue <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
* `Linux 7.2-rc1 fs/read_write.c：read到read_iter的VFS路径 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/read_write.c>`_
