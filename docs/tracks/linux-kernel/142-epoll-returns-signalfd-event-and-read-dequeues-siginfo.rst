第一百四十二章：parent怎样从epoll event进入signalfd read并取出128字节siginfo？
================================================================================

上一章结束时，helper已经完成 ``tgkill`` 并阻塞在对象之外：

::

   parent private pending contains SIGUSR1
   sigqueue Q contains SI_TKILL info
   epitem I is linked on EP->rdllist
   parent is runnable but not yet on CPU0
   parent epoll_wait kernel stack remains suspended

本章固定顺序：

#. scheduler恢复parent原来的 ``epoll_wait`` stack；
#. parent重新poll signalfd并取得一个 ``EPOLLIN`` event；
#. ``epoll_wait`` 返回1；
#. parent立即执行 ``read(6, &ssi, sizeof(ssi))``；
#. signalfd从parent private pending中移除 ``SIGUSR1``；
#. kernel复制一条128-byte ``signalfd_siginfo``；
#. read返回128。

本章结束时fd 6与fd 7仍open，registration仍存在。由于level-triggered epitem在epoll交付时被重新加入ready list，而随后signalfd read不会主动清理epoll ready list，所以 ``I`` 最终是一个stale-ready candidate。

scheduler怎样恢复原epoll_wait stack
----------------------------------

helper阻塞后，CPU0调度parent。context switch恢复的是parent之前保存在kernel stack中的完整调用链：

::

   epoll_wait
   → do_epoll_wait
   → ep_poll
   → schedule_hrtimeout_range

``schedule_hrtimeout_range(NULL, ...)`` 返回后， ``ep_poll`` 把parent状态恢复为：

::

   TASK_RUNNING

上一章中 ``W`` 已由 ``ep_autoremove_wake_function`` 从 ``EP->wq`` 删除，因此：

::

   list_empty_careful(&W->entry) == true

parent不需要再次获取 ``EP->lock`` 去移除wait entry。

``ep_poll`` 把：

::

   eavail = true

然后回到循环顶部，尝试真正采集event。

ready list为什么还要重新poll
---------------------------

``EP->rdllist`` 中已有 ``I``，但ready list只表示callback观察到“可能有事件”。特别是本场景的signalfd wake使用NULL key，而且发生在pending bit写入之前。

所以 ``ep_try_send_events`` 进入：

::

   ep_send_events
   → mutex_lock(EP->mtx)
   → ep_start_scan

``ep_start_scan`` 在 ``EP->lock`` 下把 ``EP->rdllist`` 移入parent私有 ``scan_batch``，并把：

::

   EP->ovflist = NULL

表示scan正在进行。callback若在此期间再次触发，会把item放进 ``ovflist``，避免与无spinlock的用户复制阶段冲突。

``ep_deliver_event`` 先把 ``I`` 从scan batch摘下，然后调用：

::

   ep_item_poll(I)
   → vfs_poll(F6)
   → signalfd_poll(F6)

signalfd_poll怎样确认SIGUSR1
---------------------------

执行 ``signalfd_poll`` 的 ``current`` 现在是parent。它先调用 ``poll_wait``，但本次传入的poll table没有queue callback，所以不会重复安装新的 ``eppoll_entry``。原callback ``P`` 仍然存在。

随后获取：

::

   parent->sighand->siglock

并检查：

::

   next_signal(&parent->pending, &S->sigmask)
   next_signal(&parent->signal->shared_pending, &S->sigmask)

``S->sigmask`` 是用户集合 ``{SIGUSR1}`` 的内部反转表示。parent private pending已经包含 ``SIGUSR1``，所以第一个 ``next_signal`` 返回该信号编号。

``signalfd_poll`` 设置：

::

   events |= EPOLLIN

并返回 ``EPOLLIN``。

stored interest为：

::

   EPOLLIN | EPOLLERR | EPOLLHUP

mask后仍是：

::

   revents = EPOLLIN

这个重新poll步骤才是本次readiness的最终确认。

epoll event怎样复制到用户态
----------------------------

``epoll_put_uevent`` 向用户buffer写入：

::

   events[0].events   = EPOLLIN
   events[0].data.u64 = 0x51FD6

``data.u64`` 来自 ``EPOLL_CTL_ADD`` 时用户保存的opaque data，不是：

* signalfd fd数字；
* signal number；
* sender PID；
* pending queue地址。

本场景恰好用 ``0x51FD6`` 表示该registration，kernel不解释其含义。

为什么I又回到ready list
----------------------

``I`` 没有 ``EPOLLONESHOT``，也没有 ``EPOLLET``。因此它是level-triggered registration。

交付一个event后， ``ep_deliver_event`` 执行：

::

   list_add_tail(&I->rdllink, &EP->rdllist)

原因是此刻signalfd仍然ready： ``SIGUSR1`` 尚未被read消费。level-triggered语义要求下次 ``epoll_wait`` 再次检查它。

``ep_done_scan`` 把scan状态恢复为：

::

   EP->ovflist = EP_UNACTIVE_PTR

``EP->rdllist`` 仍含 ``I``。释放 ``EP->mtx`` 后：

::

   ep_send_events returns 1
   → ep_poll returns 1
   → epoll_wait returns 1 to parent CPL3

用户态此时观察到：

::

   epoll_wait result = 1
   events[0]         = { EPOLLIN, data=0x51FD6 }

signal仍然pending，epoll只报告readiness，没有消费它。

parent怎样进入signalfd read
---------------------------

parent紧接着执行：

.. code-block:: c

   struct signalfd_siginfo ssi;
   read(6, &ssi, sizeof(ssi));

``sizeof(struct signalfd_siginfo)`` 固定为128。native syscall路径：

::

   __x64_sys_read
   → ksys_read
   → vfs_read
   → new_sync_read
   → signalfd_read_iter

``iov_iter_count`` 为128，因此：

::

   count = 128 / 128 = 1 record

fd 6没有 ``O_NONBLOCK``，但signal已经pending，所以不会睡眠。

signalfd_dequeue怎样取走private pending
--------------------------------------

``signalfd_read_iter`` 调用：

::

   signalfd_dequeue(S, &info, nonblock=false)

``signalfd_dequeue`` 在kernel stack上声明一个wait entry，不过先获取：

::

   parent->sighand->siglock

然后立即执行：

::

   dequeue_signal(&S->sigmask, &info, &type)

由于匹配signal已经存在，第一次dequeue就成功，不会把read task加入 ``signalfd_wqh``。

固定结果：

* 从 ``parent->pending.signal`` 清除 ``SIGUSR1`` bit；
* 从 ``parent->pending.list`` 摘除sigqueue ``Q``；
* 把 ``Q->info`` 复制到kernel ``info``；
* 重新计算pending状态；
* 返回 ``SIGUSR1`` signal number。

shared pending没有变化。普通signal handler没有运行，也没有建立signal frame。

为什么shared signalfd fd只能由parent取到这条signal
-----------------------------------------------

``dequeue_signal`` 操作的是执行read的 ``current``：

::

   current == parent

所以它先检查parent private pending，再检查shared pending。helper即使共享同一个fd 6，也不能通过自己的 ``read(6)`` 取走parent private pending中的 ``SIGUSR1``。

本场景由parent读取，因此准确命中 ``tgkill`` 定向给parent的signal。

signalfd_siginfo怎样由kernel siginfo转换
---------------------------------------

``signalfd_copyinfo`` 先把整个128-byte用户结构清零，再填写通用字段：

::

   ssi_signo = SIGUSR1
   ssi_errno = 0
   ssi_code  = SI_TKILL

``SI_TKILL`` 使用kill-style siginfo layout，因此继续填写：

::

   ssi_pid = helper所在thread group的TGID
   ssi_uid = helper的UID

其余未使用字段保持0，包括：

::

   ssi_tid = 0
   ssi_fd  = 0
   ssi_int = 0
   ssi_ptr = 0

``ssi_pid`` 不是helper TID。 ``prepare_kill_siginfo`` 在发送时使用 ``task_tgid_vnr(current)``，所以同一process内sender和receiver看到共同TGID。

``copy_to_iter_full`` 成功复制全部128 bytes， ``signalfd_copyinfo`` 返回128。

read为什么只返回一条记录
------------------------

用户buffer恰好容纳一个 ``signalfd_siginfo``：

::

   record capacity = 1

``signalfd_read_iter`` 在成功复制后：

::

   total = 128

并结束循环。最终：

::

   read result/RAX = 128

signalfd支持一次read返回多条128-byte记录，但本场景的buffer和pending queue都只对应一条。

read之后epitem为什么仍在ready list
--------------------------------

关键顺序是：

::

   epoll_wait delivery
   → level-triggered I requeued
   → return to userspace
   → signalfd read consumes SIGUSR1

``signalfd_read_iter`` 在成功dequeue后不会wake ``signalfd_wqh``，也不会调用epoll内部API去删除 ``I`` 的ready membership。

所以read完成后：

::

   parent pending SIGUSR1 = absent
   signalfd actual EPOLLIN readiness = false
   I still linked on EP->rdllist

这不是错误。epoll ready list保存需要在下次采集时重新验证的candidate。下一次 ``epoll_wait`` 会调用 ``signalfd_poll``，发现没有匹配pending signal，再把 ``I`` 从ready list移除。

registration本身仍然存在：

::

   I remains in EP->rbr
   P remains on sighand->signalfd_wqh

stale-ready只影响ready-list membership，不等于registration被删除。

blocked mask为什么仍包含SIGUSR1
------------------------------

signalfd读取只消费pending instance，不修改：

::

   parent->blocked
   helper->blocked
   S->sigmask

所以后续新的 ``SIGUSR1`` 仍会保持blocked，并可再次通过同一个signalfd/epoll registration观察。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：blocked ``SIGUSR1`` signalfd+epoll delivery complete；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* scheduling class：``SCHED_NORMAL``；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、 ``on_cpu=1``；
* helper：阻塞在signalfd/epoll之外；
* helper ``tgkill`` result：0；
* parent epoll result/RAX：1；
* ``events[0].events``：``EPOLLIN``；
* ``events[0].data.u64``：``0x51FD6``；
* parent signalfd read result/RAX：128；
* ``ssi_signo``：``SIGUSR1``；
* ``ssi_code``：``SI_TKILL``；
* ``ssi_pid``：shared TGID；
* ``ssi_uid``：sender UID；
* ``ssi_tid``：0；
* parent blocked mask：仍包含 ``SIGUSR1``；
* helper blocked mask：仍包含 ``SIGUSR1``；
* parent private pending：不含 ``SIGUSR1``；
* shared pending：不含 ``SIGUSR1``；
* pending sigqueue ``Q``：已dequeue并释放/回收；
* shared fd 6：open signalfd file ``F6``；
* signalfd ctx ``S``：active；
* callback ``P``：仍挂在 ``sighand->signalfd_wqh``；
* shared fd 7：open eventpoll file ``F7``；
* eventpoll ``EP``：active， ``refcount=2``；
* ``EP->rbr``：包含 ``I``；
* ``EP->rdllist``：仍包含stale-ready ``I``；
* ``EP->ovflist``：``EP_UNACTIVE_PTR``；
* ``EP->wq``：没有parent waiter；
* ``I`` registration：level-triggered，stored mask为 ``EPOLLIN|EPOLLERR|EPOLLHUP``；
* actual signalfd readiness：当前无 ``EPOLLIN``；
* filesystem/block I/O：none；
* next runtime scenario：unselected。

关键边界
--------

#. epoll callback只建立ready candidate，交付前必须重新调用target ``poll``。
#. signalfd poll检查执行者current的private pending与shared pending。
#. ``epoll_wait`` 返回1表示一个event，不表示signal number或字节数。
#. event data来自注册时的opaque ``data.u64``。
#. level-triggered交付发生时signal仍pending，因此 ``I`` 被重新加入ready list。
#. epoll event交付不消费signal。
#. signalfd read的最小记录大小固定为128 bytes。
#. pending signal已存在时，blocking signalfd read不会真正进入wait queue。
#. ``dequeue_signal`` 从parent private pending移除tgkill signal。
#. shared fd不允许helper读取parent的thread-private pending signal。
#. ``SI_TKILL`` 记录中的 ``ssi_pid`` 是sender TGID， ``ssi_tid`` 保持0。
#. signalfd read不修改blocked mask或ctx mask。
#. signalfd read不会主动清理epoll ready list。
#. read后 ``I`` 是stale-ready candidate，registration ``I/P`` 仍然存在。

下一任务
--------

优先接续是清理stale-ready并结束对象生命周期：

::

   parent epoll_wait(7, events, 1, 0)
   → re-poll signalfd
   → no pending SIGUSR1
   → remove I from EP->rdllist
   → return 0

   epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)
   → unregister P from sighand->signalfd_wqh
   → erase I from EP->rbr

   close(6)
   → signalfd_release frees S

   close(7)
   → eventpoll release frees EP after RCU grace period

资料
----

* `Linux 7.2-rc1 fs/signalfd.c：poll、dequeue、copyinfo与read_iter <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/signalfd.c>`_
* `Linux 7.2-rc1 include/uapi/linux/signalfd.h：128-byte signalfd_siginfo布局 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/uapi/linux/signalfd.h>`_
* `Linux 7.2-rc1 fs/eventpoll.c：ready scan、re-poll、level-triggered requeue <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
* `Linux 7.2-rc1 kernel/signal.c：dequeue_signal与pending状态更新 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/signal.c>`_
