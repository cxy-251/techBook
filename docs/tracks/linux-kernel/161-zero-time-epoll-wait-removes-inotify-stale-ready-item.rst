第一百六十一章：零超时epoll_wait怎样清除inotify的stale-ready item？
================================================================================

上一章结束时，parent已经从inotify fd 6读取并释放两条event：

::

   read(6, buf, 4096) = 64
   G.q_len             = 0
   G.notification_list = empty

但第一次 ``epoll_wait`` 交付event时，queue仍然非空，所以level-triggered epitem ``I`` 被重新放回：

::

   EP.rdllist = { I }

此后 ``read`` 清空了queue，却不会主动修改eventpoll的ready list。因此 ``I`` 现在只是一个stale-ready候选。parent执行：

.. code-block:: c

   int n = epoll_wait(7, events2, 1, 0);

本章固定条件：

* CPU0是唯一online CPU；
* parent与helper属于同一进程并共享 ``files_struct``；
* helper阻塞在inotify之外，不再产生filesystem event；
* fd 6是blocking、close-on-exec inotify file ``F6``；
* fsnotify group ``G`` 的notification queue为空；
* watch descriptor 1与inode mark ``M`` 仍然active；
* epoll fd 7与eventpoll ``EP`` 仍然active；
* ``I`` 是level-triggered ``EPOLLIN`` registration，data为 ``0x494E4F36``；
* callback ``P`` 仍挂在 ``G.notification_waitq``；
* ``EP.rdllist`` 开始时只包含 ``I``；
* timeout为0，不发生signal、copy fault、并发ctl、close或新event。

本章结束在 ``epoll_wait`` 返回0， ``I`` 已从ready list清除；registration、callback、watch、inotify group和fd 6/7仍然存在。

零超时为什么仍然要扫描ready list
--------------------------------

parent从CPL 3进入：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_epoll_wait
   → do_epoll_wait
   → ep_poll

``timeout=0`` 的含义是：若没有可交付event，不进入睡眠。它不表示“完全不检查ready list”。由于：

::

   EP.rdllist = { I }

``ep_poll`` 立即进入event delivery scan。

本次不会建立parent sleeping waiter ``W``：

::

   EP.wq remains empty

因为系统已经有一个candidate-ready item可以检查，而且timeout禁止在检查失败后等待。

ready membership为什么不是最终readiness
--------------------------------------

``ep_send_events`` 在 ``EP.mtx`` 下把ready item移入本地scan batch。 ``I`` 从全局ready list暂时摘下后，eventpoll重新调用目标file：

::

   ep_item_poll(I)
   → vfs_poll(F6)
   → inotify_poll(F6, no-new-registration poll table)

ADD阶段已经把callback ``P`` 挂到 ``G.notification_waitq``，因此本次re-poll不会再创建第二个callback entry。

ready-list membership只表示：

::

   target may have become ready

用户event是否真正可交付，必须以这次 ``inotify_poll`` 的结果为准。

inotify_poll怎样确认queue已经为空
---------------------------------

``inotify_poll`` 先经过：

.. code-block:: c

   poll_wait(F6, &G->notification_waitq, wait);

本次delivery poll table不安装新entry。随后获取：

::

   G.notification_lock

并检查：

::

   fsnotify_notify_queue_is_empty(G) == true
   G.q_len == 0

因此返回mask：

::

   0

锁释放后，eventpoll得到：

::

   revents = 0 & I.interest = 0

没有 ``EPOLLIN``、 ``EPOLLERR`` 或 ``EPOLLHUP`` 可以复制给用户。

为什么I不会重新进入ready list
-----------------------------

level-triggered item只有在re-poll结果仍包含感兴趣的event时，才在本次交付后重新放回 ``EP.rdllist``。

本次结果为0，所以：

::

   I not requeued
   EP.rdllist = empty

注意这一步只删除ready membership。它不会删除registration本身：

::

   EP.rbr still contains I
   P still attached to G.notification_waitq
   EP.refcount remains 2

未来只要新的inotify record进入queue， ``fsnotify_add_event`` 再次wake ``G.notification_waitq``，callback ``P`` 仍能把同一个 ``I`` 加回ready list。

epoll_wait为什么返回0而不是EAGAIN
--------------------------------

``epoll_wait`` 的API用返回值0表示：

::

   no event became deliverable before timeout

这里timeout本来就是0，所以scan结束后立即返回：

::

   RAX = 0

``-EAGAIN`` 是某些nonblocking read/write接口的约定，不是 ``epoll_wait`` 的零超时结果。

本次没有向 ``events2[0]`` 写入有效event。用户程序不应读取或解释数组中的旧内容。

watch对象为什么完全不变
-----------------------

本次控制流只访问：

* eventpoll ready list；
* inotify file的 ``poll`` callback；
* group queue lock和empty状态。

它不会调用：

* ``inotify_rm_watch``；
* ``fsnotify_destroy_mark``；
* ``inotify_ignored_and_remove_idr``；
* ``fsnotify_destroy_group``。

所以：

::

   wd 1 remains valid
   M remains attached to /work inode
   M remains in G.inotify_data.idr
   /work inode remains pinned by fsnotify connector

``/work/new.txt`` 也继续存在。本章没有执行unlink或close任何与该文件相关的新fd。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：inotify stale-ready cleanup complete；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、 ``on_cpu=1``；
* latest syscall：``epoll_wait(7, events2, 1, 0)``；
* latest result/RAX：0；
* fd 6：open inotify file ``F6``；
* fsnotify group ``G``：active；
* ``G.q_len``：0；
* ``G.notification_list``：empty；
* overflow event：allocated、not queued；
* wd 1 / mark ``M``：active on ``/work`` inode；
* ``G.notification_waitq``：contains callback ``P`` only；
* fd 7：open eventpoll file ``F7``；
* eventpoll ``EP``：active， ``refcount=2``；
* ``EP.rbr``：contains epitem ``I``；
* ``EP.rdllist``：empty；
* ``EP.wq``：empty；
* helper：blocked outside inotify；
* ``/work/new.txt``：exists；
* next control entry：``inotify_rm_watch(6, 1)``。

关键边界
--------

#. ready-list membership是候选状态，真正交付前必须重新poll目标file。
#. 零超时不会跳过ready scan，只禁止在无event时睡眠。
#. inotify queue是否可读由 ``G.notification_lock`` 下的queue empty检查决定。
#. queue为空时 ``inotify_poll`` 返回0。
#. re-poll返回0会删除level-triggered item的ready membership。
#. 清除ready membership不会删除epoll registration或waitqueue callback。
#. ``epoll_wait(..., timeout=0)`` 无event时返回0，不返回 ``-EAGAIN``。
#. 本章不改变wd、mark、IDR、inode connector或group lifetime。

下一任务
--------

下一章执行：

::

   inotify_rm_watch(6, 1)
   → find mark M in group IDR
   → detach M from group
   → queue wd1 IN_IGNORED record before invalidating wd
   → remove wd1 from IDR
   → detach M from /work inode connector
   → queue mark and connector storage for SRCU-safe destruction
   → callback P places I back on EP.rdllist

资料
----

* `Linux 7.2-rc1 fs/eventpoll.c：ready scan与level-triggered requeue <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
* `Linux 7.2-rc1 fs/notify/inotify/inotify_user.c：inotify_poll <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/notify/inotify/inotify_user.c>`_
