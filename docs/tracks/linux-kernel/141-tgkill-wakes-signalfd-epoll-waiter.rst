第一百四十一章：tgkill() 怎样让blocked SIGUSR1经signalfd callback唤醒epoll_wait？
================================================================================

上一章结束时：

::

   fd 6 → signalfd file F6 → signalfd_ctx S
   fd 7 → eventpoll file F7 → eventpoll EP
   EP->rbr contains epitem I
   EP->rdllist empty
   callback P is linked on sighand->signalfd_wqh
   parent private pending has no SIGUSR1

本章固定调度顺序：

#. parent在CPU0执行 ``epoll_wait(7, events, 1, -1)``；
#. parent阻塞后helper成为current；
#. helper执行 ``tgkill(tgid, parent_tid, SIGUSR1)``；
#. helper的tgkill返回0，然后阻塞在signal/epoll对象之外；
#. scheduler恢复parent原来的 ``epoll_wait`` kernel stack。

本章结束在parent已经被放回runqueue， ``SIGUSR1`` 已进入parent private pending，epitem ``I`` 已进入ready list；parent尚未重新poll signalfd，也尚未把event复制到用户态。

parent怎样进入epoll_wait
-----------------------

parent调用：

.. code-block:: c

   epoll_wait(7, events, 1, -1);

native x86-64路径：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_epoll_wait
   → do_epoll_wait
   → ep_poll

参数固定为：

::

   epfd      = 7
   events    = valid writable one-event array
   maxevents = 1
   timeout   = -1

``ep_timeout_to_timespec`` 对负timeout返回 ``NULL``。这表示无限等待，不创建超时deadline。

``do_epoll_wait`` 解析fd 7，确认 ``F7->f_op`` 是 ``eventpoll_fops``，取得：

::

   EP = F7->private_data

初始 ``EP->rdllist`` 为空，所以第一次 ``ep_events_available`` 返回false。

parent睡在哪条wait queue
-----------------------

``ep_poll`` 在kernel stack上建立：

::

   wait_queue_entry_t W

然后设置：

::

   W->private = parent
   W->func    = ep_autoremove_wake_function

在 ``EP->lock`` 内：

#. parent状态设为 ``TASK_INTERRUPTIBLE``；
#. 再次检查ready list；
#. 确认仍无ready item；
#. 通过 ``__add_wait_queue_exclusive`` 把 ``W`` 加入 ``EP->wq``。

因此存在两条完全不同的wait queue：

::

   sighand->signalfd_wqh
       contains callback P

   EP->wq
       contains sleeping-task entry W

``P`` 把signalfd readiness传播到epoll； ``W`` 才负责阻塞和唤醒parent。

释放 ``EP->lock`` 后，parent调用：

::

   schedule_hrtimeout_range(NULL, 0, HRTIMER_MODE_ABS)

没有deadline，所以最终进入scheduler。parent离开CPU0：

::

   parent state = TASK_INTERRUPTIBLE
   parent on_rq = 0
   parent on_cpu= 0

helper成为CPU0 current。

helper的tgkill怎样定位parent
--------------------------

helper执行：

.. code-block:: c

   tgkill(tgid, parent_tid, SIGUSR1);

路径为：

::

   __x64_sys_tgkill
   → do_tkill
   → prepare_kill_siginfo
   → do_send_specific

``tgkill`` 同时检查TGID和TID，避免旧TID退出并被其他process复用后误发信号。

``prepare_kill_siginfo`` 为thread-directed signal建立：

::

   si_signo = SIGUSR1
   si_errno = 0
   si_code  = SI_TKILL
   si_pid   = helper所在thread group的TGID
   si_uid   = helper当前UID

注意 ``si_pid`` 使用 ``task_tgid_vnr(current)``，不是helper的thread ID。helper与parent属于同一thread group，因此稍后signalfd记录中的 ``ssi_pid`` 是共同TGID。

``do_send_specific`` 在RCU read-side找到 ``parent_tid`` 对应task，并验证：

::

   task_tgid_vnr(parent) == tgid

权限检查成功后调用：

::

   do_send_sig_info(SIGUSR1, info, parent, PIDTYPE_PID)

``PIDTYPE_PID`` 表示信号进入目标thread自己的private pending queue，而不是process-wide shared pending。

SIGUSR1为什么不会被普通handler处理
---------------------------------

发送路径取得parent共享 ``sighand->siglock``，进入：

::

   send_signal_locked
   → __send_signal_locked

parent blocked mask包含 ``SIGUSR1``。 ``sig_ignored`` 明确规定blocked signal不能被当作ignored signal丢弃，因为用户之后可能解除block或通过同步接口消费它。

固定没有已有legacy ``SIGUSR1`` pending，因此kernel分配一个 ``sigqueue`` 节点 ``Q``，填写 ``SI_TKILL`` siginfo，并把它加入：

::

   parent->pending.list

信号位稍后加入：

::

   parent->pending.signal

由于 ``SIGUSR1`` 被parent阻塞，它不会在syscall return-to-user路径建立signal frame，也不会调用用户signal handler。

signalfd_notify为什么先于pending bit写入
---------------------------------------

固定源码中的顺序是：

::

   signalfd_notify(parent, SIGUSR1)
   sigaddset(&parent->pending.signal, SIGUSR1)
   complete_signal(SIGUSR1, parent, PIDTYPE_PID)

这看起来反直觉：signalfd wait queue先被wake，pending bit后设置。

``signalfd_notify`` 本身不检查signalfd mask，也不读取pending queue。它只执行：

.. code-block:: c

   if (waitqueue_active(&parent->sighand->signalfd_wqh))
       wake_up(&parent->sighand->signalfd_wqh);

上一章已经把callback ``P`` 挂在这条queue上，所以 ``waitqueue_active`` 为true。

wake key为什么为空
------------------

``signalfd_notify`` 使用普通 ``wake_up``，没有像eventfd那样传入 ``EPOLLIN`` poll key。因此 ``ep_poll_callback`` 收到：

::

   key       = NULL
   pollflags = 0

callback中的mask过滤逻辑是：

::

   if (pollflags && !(pollflags & I->event.events))
       ignore

``pollflags=0`` 时不会执行过滤。epoll把这次wake视为“目标file可能ready”，而不是已经获得确定的event mask。

这符合epoll的candidate模型：callback负责避免漏事件；最终readiness必须由 ``signalfd_poll`` 重新确认。

ep_poll_callback怎样把I放进ready list
-------------------------------------

``P->wait.func`` 调用：

::

   ep_poll_callback(P, mode, sync, NULL)

callback取得 ``EP->lock``。固定条件：

* ``I`` 没有被 ``EPOLLONESHOT`` disable；
* ``EP`` 不在scan状态；
* ``I`` 当前不在 ``EP->rdllist``；
* ``I`` 不是 ``EPOLLEXCLUSIVE`` registration。

所以执行：

::

   list_add_tail(&I->rdllink, &EP->rdllist)

此时需要准确理解状态：

::

   I is a ready candidate
   ≠
   signalfd_poll has already observed pending SIGUSR1

signal bit尚未由后续 ``sigaddset`` 写入。 ``I`` 进入ready list的依据只是signalfd wait queue产生了wake。

parent怎样从EP->wq被唤醒
------------------------

callback仍持有 ``EP->lock`` 时发现：

::

   waitqueue_active(&EP->wq) == true

于是执行 ``wake_up`` 或 ``wake_up_sync``，具体取决于上游wake的sync参数。固定普通 ``wake_up`` 路径不要求立即切换current。

``EP->wq`` 上的exclusive entry ``W`` 调用：

::

   ep_autoremove_wake_function
   → default_wake_function
   → try_to_wake_up(parent)

parent状态变化：

::

   TASK_INTERRUPTIBLE → TASK_RUNNING
   on_rq: 0 → 1

随后 ``ep_autoremove_wake_function`` 无条件执行：

::

   list_del_init_careful(&W->entry)

因此parent被唤醒后， ``W`` 已从 ``EP->wq`` 自动移除。

callback释放 ``EP->lock`` 并返回到signal发送路径。

pending signal何时真正可见
-------------------------

``signalfd_notify`` 完成后，helper仍在持有parent ``sighand->siglock`` 的signal生成路径中。随后执行：

::

   sigaddset(&parent->pending.signal, SIGUSR1)

此时 ``Q`` 与signal bit共同表示一条private pending ``SIGUSR1``。

之后 ``complete_signal`` 检查目标thread是否需要按普通signal语义唤醒。 ``wants_signal`` 因parent blocked mask包含 ``SIGUSR1`` 返回false；又因为发送类型是 ``PIDTYPE_PID``， ``complete_signal`` 直接返回，不调用：

::

   signal_wake_up(parent, ...)

所以本场景parent被唤醒的直接原因不是普通signal delivery，而是：

::

   signalfd_notify
   → P ep_poll_callback
   → EP->wq wake

这一区分非常重要。

单CPU为什么保证parent重查时看到pending bit
----------------------------------------

CPU0当前仍在helper的tgkill syscall中。parent虽然已经变为runnable，但不会在helper尚未离开CPU前并行执行。

helper完成：

::

   sigaddset pending bit
   → release sighand->siglock
   → tgkill returns 0 to helper CPL3

固定helper随后阻塞在对象之外，scheduler才选择parent。parent恢复时，pending bit和sigqueue节点都已经建立完成。

在SMP系统中， ``signalfd_poll`` 会获取同一个 ``sighand->siglock``，也会与发送路径同步；本实验用单CPU进一步固定调度顺序。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：helper即将阻塞，下一current为parent；
* CPU：CPU0；
* CPU mode：helper已从tgkill返回CPL 3；
* helper ``tgkill`` result：0；
* helper：随后阻塞在signalfd/epoll之外；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、 ``on_cpu=0``；
* parent kernel stack：仍停在原 ``epoll_wait`` 的schedule调用之后；
* parent blocked mask：包含 ``SIGUSR1``；
* parent private pending：包含一条 ``SIGUSR1``；
* pending sigqueue ``Q``：包含 ``SI_TKILL`` info；
* shared pending：不含 ``SIGUSR1``；
* ordinary signal-handler wake：未发生；
* signalfd notify wake：已发生；
* shared fd 6/7：仍open；
* callback ``P``：仍挂在 ``sighand->signalfd_wqh``；
* epitem ``I``：仍在 ``EP->rbr``，并已加入 ``EP->rdllist``；
* ``EP->wq``：不再包含 ``W``；
* parent stack entry ``W``：已auto-remove，stack storage仍随epoll_wait frame存在；
* event copy to userspace：尚未发生；
* signalfd dequeue：尚未发生；
* next entry：scheduler恢复parent， ``ep_poll`` 重新检查ready list。

关键边界
--------

#. ``tgkill`` 把信号定向放进parent private pending，而不是shared pending。
#. ``SI_TKILL`` 的 ``si_pid`` 是sender TGID，不是sender TID。
#. blocked ``SIGUSR1`` 不会被ignored，也不会建立普通用户signal frame。
#. ``signalfd_notify`` 在pending bit写入之前执行。
#. signalfd notify使用普通 ``wake_up``，epoll callback收到NULL key。
#. NULL key不会经过event-mask过滤，只表示目标file可能ready。
#. callback把 ``I`` 加入ready list时，signalfd尚未重新确认pending signal。
#. ``P`` 挂在signalfd wait queue， ``W`` 挂在eventpoll wait queue。
#. parent由epoll wait queue唤醒，不是由 ``signal_wake_up`` 唤醒。
#. ``W`` 在wake callback中自动从 ``EP->wq`` 移除。
#. blocked thread-directed signal使 ``complete_signal`` 不再额外唤醒parent。
#. 单CPU顺序保证parent恢复前，pending bit与sigqueue info已经建立。

下一任务
--------

下一章从parent恢复开始：

::

   parent resumes epoll_wait
   → signalfd_poll confirms private pending SIGUSR1
   → events[0] = { EPOLLIN, data=0x51FD6 }
   → epoll_wait returns 1
   → parent read(6, &ssi, 128)
   → dequeue private pending SIGUSR1
   → copy signalfd_siginfo
   → read returns 128

资料
----

* `Linux 7.2-rc1 kernel/signal.c：tgkill、private pending与signalfd_notify顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/signal.c>`_
* `Linux 7.2-rc1 include/linux/signalfd.h：signalfd_notify wait queue wake <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/signalfd.h>`_
* `Linux 7.2-rc1 fs/eventpoll.c：ep_poll、ep_poll_callback与autoremove waiter <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
