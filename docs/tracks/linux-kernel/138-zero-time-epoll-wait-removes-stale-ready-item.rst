第一百三十八章：零超时epoll_wait() 怎样重新poll并清理stale-ready item？
================================================================================

上一章结束时，eventfd counter已经清零，但level-triggered epitem ``I`` 仍位于eventpoll ready list：

::

   E->count              = 0
   EP->rdllist           = contains I
   EP->rbr               = contains I
   E->wqh                = contains callback P
   I interest            = EPOLLIN | EPOLLERR | EPOLLHUP
   target current poll   = EPOLLOUT only

parent现在执行：

.. code-block:: c

   struct epoll_event events2[1];
   epoll_wait(7, events2, 1, 0);

本章固定条件：

* CPU0是唯一online CPU；
* timeout严格为0；
* ``events2`` 是有效可写用户buffer；
* ``maxevents=1``；
* 没有signal、copy fault或并发 ``epoll_ctl``；
* helper继续阻塞，不再写eventfd；
* callback ``P`` 在本章期间不会触发；
* ``E->count`` 始终保持0；
* ``I`` 是ready list中的唯一item；
* ``EP->ovflist`` 初始为 ``EP_UNACTIVE_PTR``；
* 不启用busy poll、NAPI、EPOLLET、EPOLLONESHOT或EPOLLWAKEUP。

本章结束在 ``epoll_wait`` 返回0， ``I`` 已从 ``EP->rdllist`` 移除，但registration本身仍存在： ``I`` 仍在RB tree中， ``P`` 仍挂在eventfd wait queue上。

零timeout怎样变成nonblocking poll
--------------------------------

x86-64进入：

::

   __x64_sys_epoll_wait
   → ep_timeout_to_timespec(&to, 0)
   → do_epoll_wait(7, events2, 1, &to)
   → ep_poll(EP, events2, 1, &to)

``ep_timeout_to_timespec`` 把timespec设为：

::

   tv_sec  = 0
   tv_nsec = 0

进入 ``ep_poll`` 后，代码识别到非NULL timeout且值为0，直接设置：

::

   timed_out = 1

它不会建立hrtimer，也不会调用 ``schedule_hrtimeout_range``。零超时的含义是：允许检查现有ready candidates，但没有事件可交付时立即返回。

为什么第一次检查认为有事件
--------------------------

``ep_poll`` 首先调用：

.. code-block:: c

   eavail = ep_events_available(EP);

这个helper检查的是epoll内部ready state：

* ``EP->rdllist`` 是否非空；
* 是否正在scan；
* seqcount读取期间是否发生变化。

由于 ``I`` 仍在 ``rdllist``：

::

   eavail = true

这里没有直接调用eventfd的 ``poll``。所以初始判断只说明“存在需要重新检查的candidate”，并不保证最终一定向用户复制一个event。

ep_send_events怎样开始scan
--------------------------

``eavail`` 为true，进入：

::

   ep_try_send_events
   → ep_send_events

固定没有fatal signal。 ``ep_send_events`` 初始化一个本地：

::

   LIST_HEAD(scan_batch)

然后获取：

::

   mutex_lock(&EP->mtx)

``ep_start_scan`` 再取得 ``EP->lock``，执行：

::

   list_splice_init(&EP->rdllist, &scan_batch)
   EP->ovflist = NULL

状态变成：

::

   EP->rdllist = empty
   scan_batch  = contains I
   EP scanning = true

将ready list整体移到task-private batch后，event delivery可以在不持续持有 ``EP->lock`` 的情况下执行 ``copy_to_user`` 与目标file ``poll``。若并发callback出现，它会改投 ``ovflist``；本章固定没有并发event。

ep_deliver_event为什么先摘掉I
-----------------------------

遍历 ``scan_batch`` 时调用：

::

   ep_deliver_event(EP, I, ...)

函数首先：

.. code-block:: c

   list_del_init(&I->rdllink);

此时 ``I`` 已不属于 ``scan_batch`` 或 ``EP->rdllist``。随后必须重新检查目标file当前状态：

::

   ep_item_poll(I)
   → epi_fget(I)
   → vfs_poll(F6, pt)
   → eventfd_poll(F6, pt)

这里的poll table没有queue callback，因为registration早在 ``epoll_ctl(ADD)`` 时已经完成。此次re-poll只读取当前readiness，不会再向 ``E->wqh`` 增加第二个callback entry。

eventfd_poll当前返回什么
------------------------

``eventfd_poll`` 执行 ``poll_wait``，但当前poll table的qproc为NULL，所以不会修改wait queue。随后读取：

::

   count = READ_ONCE(E->count) = 0

条件结果：

* ``count > 0`` 为false，不报告 ``EPOLLIN``；
* ``count == ULLONG_MAX`` 为false，不报告 ``EPOLLERR``；
* ``ULLONG_MAX - 1 > count`` 为true，报告 ``EPOLLOUT``。

原始结果是：

::

   eventfd_poll result = EPOLLOUT

``ep_item_poll`` 最后与interest mask相交：

::

   EPOLLOUT & (EPOLLIN | EPOLLERR | EPOLLHUP) = 0

因此返回0。

为什么不向用户复制旧事件
------------------------

``ep_deliver_event`` 发现re-poll结果为0，立即返回0：

* 不调用 ``epoll_put_uevent``；
* 不写入 ``events2[0]``；
* 不增加delivered count；
* 不执行level-triggered requeue；
* 不把 ``I`` 放回scan batch。

level-triggered requeue只发生在“本次re-poll仍匹配且已经成功向用户复制event”之后。 ``I`` 曾经ready这一历史事实不够，当前目标状态必须仍满足interest。

ep_done_scan怎样完成stale-ready清理
----------------------------------

本地 ``scan_batch`` 已为空，固定 ``EP->ovflist`` 也没有并发spill。 ``ep_done_scan`` 获取 ``EP->lock`` 后：

::

   no ovflist item to merge
   EP->ovflist = EP_UNACTIVE_PTR
   splice empty scan_batch back to EP->rdllist

最终：

::

   EP->rdllist = empty
   I linked on ready list = false

``I`` 没有被释放。它仍位于 ``EP->rbr``，仍通过 ``I->pwqlist`` 指向callback ``P``。未来helper再次把counter从0写成正数时， ``P`` 仍会调用 ``ep_poll_callback``，重新把 ``I`` 加入ready list。

为什么epoll_wait最后返回0
-------------------------

``ep_send_events`` 返回delivered count 0， ``ep_try_send_events`` 也返回0。控制回到 ``ep_poll``：

::

   res = 0
   timed_out = 1

于是立即执行：

.. code-block:: c

   if (timed_out)
       return 0;

parent不会加入 ``EP->wq``，不会改变task state，也不会调度出去。syscall返回CPL 3：

::

   RAX = 0

``events2[0]`` 未由内核写入。用户程序不能把其旧内存内容解释为本次有效event；只有返回值范围内的数组元素有效。

stale-ready具体是什么意思
-------------------------

这里的“stale”不是悬空pointer，也不是损坏的epitem。它只表示：

::

   item is queued as a candidate
   but target no longer matches current interest

候选入队和实际交付之间允许目标状态变化。epoll通过交付前re-poll解决这一竞态：

* callback负责快速标记“可能ready”；
* ready list避免每次从整个interest tree扫描；
* delivery path负责确认“现在仍ready”；
* re-poll失败时只移除ready membership，不删除registration。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* scheduling class：``SCHED_NORMAL``；
* parent latest syscall：``epoll_wait(7, events2, 1, 0)``；
* parent return/RAX：0；
* ``events2`` valid event count：0；
* parent scheduling：未阻塞、未切换；
* helper：阻塞在eventfd之外；
* fd 6/eventfd file ``F6``：open；
* eventfd ctx ``E``：active；
* ``E->count``：0；
* ``E->wqh``：仍含callback ``P``；
* fd 7/eventpoll file ``F7``：open；
* eventpoll ``EP``：active；
* ``EP->refcount``：2；
* ``EP->rbr``：仍含epitem ``I``；
* ``EP->rdllist``：empty；
* ``EP->ovflist``：``EP_UNACTIVE_PTR``；
* ``EP->wq``：empty；
* ``I->rdllink``：unlinked/initialized；
* ``I->pwqlist``：仍含 ``P``；
* ``I->event.data``：仍为 ``0xEFD6``；
* eventfd current matching readiness：none for ``I`` interest；
* filesystem/block I/O：none；
* next control entry：``epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)``。

关键边界
--------

#. 零超时epoll_wait仍会处理现有ready candidates，只是不等待新事件。
#. ``ep_events_available`` 检查epoll内部队列，不直接保证目标file当前ready。
#. ``ep_start_scan`` 把ready list移到task-private scan batch并进入scanning状态。
#. event delivery前必须重新调用目标file的 ``poll``。
#. counter为0时eventfd只报告 ``EPOLLOUT``，与当前 ``EPOLLIN`` interest不匹配。
#. re-poll不匹配时，不复制用户event，也不执行level-triggered requeue。
#. stale-ready清理只移除 ``rdllist`` membership，不删除RB-tree registration。
#. callback ``P`` 继续存在，未来新的 ``EPOLLIN`` 可重新排入 ``I``。
#. ``epoll_wait`` 返回0时，用户buffer中没有任何有效event元素。
#. 本次调用不建立wait entry、不设置 ``TASK_INTERRUPTIBLE``、不进入scheduler。

下一任务
--------

下一章执行完整拆除：

::

   epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)
   → remove P from E.wqh
   → remove I from F6->f_ep and EP.rbr
   → EP refcount 2 → 1
   → kfree_rcu(I)
   → close(6), free eventfd ctx/file
   → close(7), ep_eventpoll_release
   → empty-tree ep_put 1 → 0
   → kfree_rcu(EP)

资料
----

* `Linux 7.2-rc1 fs/eventpoll.c：ep_poll、ep_send_events、ep_deliver_event与scan状态机 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
* `Linux 7.2-rc1 fs/eventfd.c：eventfd_poll的counter readiness规则 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventfd.c>`_
