第一百四十三章：零超时epoll_wait() 怎样清理signalfd的stale-ready item？
================================================================================

上一章结束时，parent已经通过signalfd读走唯一一条 ``SIGUSR1``：

::

   epoll_wait(7, events, 1, -1) = 1
   read(6, &ssi, 128)           = 128
   ssi.ssi_signo                = SIGUSR1
   ssi.ssi_code                 = SI_TKILL

signal已经从parent的thread-private pending queue中dequeue。因为上一轮是level-triggered交付，epitem ``I`` 在事件复制后又被放回 ``EP->rdllist``；随后执行的signalfd read只消费signal，不会主动修改epoll ready list。

因此当前存在一个典型的stale-ready candidate：

::

   actual signalfd EPOLLIN readiness = false
   I membership in EP.rdllist        = true

parent现在执行：

.. code-block:: c

   int n = epoll_wait(7, events2, 1, 0);

本章固定条件：

* CPU0是唯一online CPU；
* parent与helper属于同一TGID，共享 ``mm_struct``、 ``files_struct``、 ``signal_struct`` 与 ``sighand_struct``；
* parent与helper仍然在各自blocked mask中阻塞 ``SIGUSR1``；
* parent private pending与shared pending均不含 ``SIGUSR1``；
* fd 6指向blocking signalfd file ``F6``，ctx为 ``S``；
* fd 7指向eventpoll file ``F7``，ctx为 ``EP``；
* ``EP->rbr`` 包含一个监控 ``F6`` 的epitem ``I``；
* ``I`` 的interest为 ``EPOLLIN|EPOLLERR|EPOLLHUP``，data为 ``0x51FD6``；
* ``I`` 当前位于 ``EP->rdllist``；
* callback entry ``P`` 仍以non-exclusive方式挂在 ``sighand->signalfd_wqh``；
* ``EP->wq`` 没有parent waiter；
* 没有新signal、并发 ``epoll_ctl``、close、fork、exec或sighand teardown；
* 没有copy fault、signal、scheduler或allocation failure。

本章结束在zero-time ``epoll_wait`` 返回0， ``I`` 已从ready list移除；registration、callback和两个fd仍保持active。

零timeout怎样进入ep_poll
-----------------------

native x86-64进入：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_epoll_wait
   → do_epoll_wait
   → ep_poll(EP, events2, 1, timeout={0,0})

``ep_timeout_to_timespec`` 对 ``timeout=0`` 建立零timespec。 ``ep_poll`` 看到timeout pointer非NULL且秒、纳秒均为0，于是：

::

   timed_out = 1
   to        = NULL

这里的 ``timed_out=1`` 表示“不允许睡眠”，不是说内核已经先等待了一段时间再超时。

为什么初始ready检查仍然为true
----------------------------

``ep_poll`` 首先无锁读取：

.. code-block:: c

   eavail = ep_events_available(EP);

``EP->rdllist`` 当前包含 ``I``，所以固定结果：

::

   eavail = true

这一步只能证明ready list中存在candidate。它没有调用signalfd的 ``poll`` callback，也没有检查signal pending queue。

因此epoll ready list的语义是：

::

   candidate requiring revalidation

而不是：

::

   permanently true readiness fact

只要candidate还在list中， ``ep_poll`` 就必须尝试一次 ``ep_try_send_events``，即使用户timeout为0。

ep_send_events怎样取走candidate
------------------------------

``ep_try_send_events`` 进入 ``ep_send_events``：

::

   mutex_lock(EP->mtx)
   → ep_start_scan(EP, scan_batch)

``ep_start_scan`` 在 ``EP->lock`` 下把主ready list整体搬到task-private local list：

::

   EP->rdllist  : [ I ] → empty
   scan_batch   : empty → [ I ]
   EP->ovflist  : EP_UNACTIVE_PTR → scan mode

``I`` 没有被删除；它只是暂时从主ready list迁移到当前syscall的scan batch。

为什么必须重新调用signalfd_poll
-------------------------------

``ep_deliver_event`` 首先：

::

   list_del_init(&I->rdllink)

随后调用：

::

   ep_item_poll(I, pt, 1)
   → epi_fget(I)
   → temporary file reference on F6
   → vfs_poll(F6, pt)
   → signalfd_poll(F6, pt)

本次 ``pt`` 的queue callback为NULL。 ``signalfd_poll`` 仍会执行：

.. code-block:: c

   poll_wait(F6, &current->sighand->signalfd_wqh, pt);

但由于 ``pt->_qproc == NULL``，不会新分配第二个 ``eppoll_entry``，也不会向共享wait queue重复加入callback。原有 ``P`` 仍来自 ``epoll_ctl(ADD)`` 时的registration。

真正readiness检查发生在：

::

   spin_lock_irq(parent->sighand->siglock)
   → next_signal(parent->pending, S->sigmask)
   → next_signal(shared_pending, S->sigmask)
   → spin_unlock_irq

上一章已经dequeue唯一的 ``SIGUSR1``，因此两次 ``next_signal`` 都返回0：

::

   signalfd_poll result = 0
   ep_item_poll result  = 0

临时file reference随后由 ``fput(F6)`` 归还。

为什么没有event复制到events2
---------------------------

``ep_deliver_event`` 看到：

::

   revents == 0

于是直接返回0：

* 不调用 ``epoll_put_uevent``；
* 不向 ``events2[0]`` 写入任何event；
* 不增加delivered count；
* 不重新把 ``I`` 放回 ``EP->rdllist``；
* 不删除 ``I`` 的registration。

level-triggered重新排队只发生在本次re-poll仍有匹配event，并且成功复制给用户之后。当前没有 ``EPOLLIN``，所以没有requeue。

ep_done_scan怎样留下空ready list
-------------------------------

``ep_send_events`` 完成本地scan后调用：

::

   ep_done_scan(EP, scan_batch)

固定场景没有并发callback，因此：

* ``EP->ovflist`` 没有新item；
* ``scan_batch`` 已为空；
* ``EP`` 退出scan mode；
* ``EP->rdllist`` 保持empty；
* 没有 ``EP->wq`` waiter需要唤醒。

随后：

::

   mutex_unlock(EP->mtx)
   ep_send_events returns 0
   ep_try_send_events returns 0

为什么epoll_wait立即返回0
-------------------------

控制回到 ``ep_poll``：

::

   eavail was true
   ep_try_send_events returned 0
   timed_out is already 1

因此命中：

.. code-block:: c

   if (timed_out)
       return 0;

本次调用不会：

* 初始化task wait entry；
* 把parent加入 ``EP->wq``；
* 修改parent task state；
* 调用 ``schedule_hrtimeout_range``；
* 发生context switch。

从syscall入口到返回，parent始终是CPU0上的current task。

清理ready membership不等于删除registration
----------------------------------------

调用返回后，对象关系是：

::

   EP->rbr      contains I
   EP->rdllist  empty
   I->pwqlist   contains P
   P            still attached to sighand->signalfd_wqh
   EP refcount  remains 2

这里仅消除了“当前ready candidate”关系。未来若新的匹配signal进入pending queue， ``signalfd_notify`` 仍可通过 ``P`` 调用 ``ep_poll_callback``，把同一个 ``I`` 再次加入 ``EP->rdllist``。

因此：

::

   remove from ready list ≠ EPOLL_CTL_DEL

前者是动态readiness状态；后者才删除长期registration。

blocked mask与pending queue有没有变化
-----------------------------------

本章只调用 ``epoll_wait`` 和target ``poll``：

* parent blocked mask仍包含 ``SIGUSR1``；
* helper blocked mask仍包含 ``SIGUSR1``；
* parent private pending仍不含 ``SIGUSR1``；
* shared pending仍不含 ``SIGUSR1``；
* 不建立signal frame；
* 不调用signal handler；
* 不修改 ``signalfd_ctx`` mask。

``signalfd_poll`` 在siglock下读取pending状态，不消费signal。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* latest syscall：``epoll_wait(7, events2, 1, 0)``；
* return/RAX：0；
* parent state：``TASK_RUNNING``；
* context switch during syscall：none；
* fd 6：open blocking signalfd file ``F6``，close-on-exec；
* signalfd ctx ``S``：active；
* fd 7：open eventpoll file ``F7``，close-on-exec；
* eventpoll ``EP``：active；
* ``EP->refcount``：2；
* ``EP->rbr``：包含 ``I``；
* ``EP->rdllist``：empty；
* ``EP->ovflist``：``EP_UNACTIVE_PTR``；
* ``EP->wq``：empty；
* epitem ``I``：registered、not ready；
* callback ``P``：仍挂在 ``sighand->signalfd_wqh``；
* actual signalfd ``EPOLLIN`` readiness：false；
* parent/helper blocked mask：仍包含 ``SIGUSR1``；
* parent private pending：无 ``SIGUSR1``；
* shared pending：无 ``SIGUSR1``；
* filesystem/block I/O：none；
* next control entry：``epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)``。

关键边界
--------

#. zero-time epoll仍会重新验证已在ready list中的candidate。
#. ``timed_out=1`` 表示禁止睡眠，不表示跳过现有ready scan。
#. ``EP->rdllist`` membership不是永久readiness事实。
#. re-poll signalfd时，siglock保护private与shared pending检查。
#. scan时的poll table没有queue callback，不会重复安装 ``P``。
#. ``revents=0`` 时不复制用户event，也不重新排入level-triggered ready list。
#. stale-ready清理只移除ready membership，不删除rbtree registration。
#. ``I`` 与 ``P`` 仍active，未来signal仍可重新触发callback。
#. 本次调用不加入 ``EP->wq``、不调度、不发生context switch。
#. signalfd poll只检查pending，不消费signal或修改blocked mask。

下一任务
--------

下一章执行：

::

   epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)
   → find I in EP.rbr
   → remove P from shared sighand->signalfd_wqh
   → free P synchronously
   → clear F6->f_ep reverse watcher state
   → erase I from EP.rbr
   → kfree_rcu(I)
   → EP refcount 2 → 1

资料
----

* `Linux 7.2-rc1 fs/eventpoll.c：zero-time ep_poll、candidate scan与re-poll <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
* `Linux 7.2-rc1 fs/signalfd.c：signalfd_poll检查private/shared pending <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/signalfd.c>`_
* `Linux 7.2-rc1 kernel/signal.c：next_signal与pending queue语义 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/signal.c>`_
