第一百五十五章：reap之后的pidfd为什么让epoll_wait返回EPOLLIN|EPOLLHUP？
====================================================================================

上一章结束时，parent已经通过 ``waitid(P_PIDFD)`` 回收child：

::

   child task_struct        = reaped
   numeric PID C            = reusable
   pid_task(P, PIDTYPE_PID) = NULL
   pidfd fd 6               = open
   epoll fd 7               = open
   EP.rbr                   = [I]
   EP.rdllist               = [I]

这里最重要的对象关系是：

::

   fd 6 → pidfd file F6
        → pidfs dentry D
        → pidfs inode N
        → N->i_private = old struct pid P

child task已经消失， ``P`` 仍被pidfs inode保持。 ``P`` 不再连接任何task，因此pidfd从“目标已经退出但仍是zombie”的状态进入“目标已经被彻底reap”的状态。

parent现在执行：

.. code-block:: c

   struct epoll_event events2[1] = {};
   int n = epoll_wait(7, events2, 1, 0);

本章固定条件：

* CPU0是唯一online CPU；
* parent是当前执行者，运行于CPL 3；
* fd 6是blocking、close-on-exec pidfd；
* fd 7是close-on-exec eventpoll；
* registration是level-triggered ``EPOLLIN``；
* registration data是 ``0x50494436``；
* epitem ``I`` 已经位于 ``EP.rdllist``；
* child没有task linkage，数字PID ``C`` 在本章不会被新进程复用；
* 不发生signal、copy fault、fd close、ctl race或allocator failure；
* 本章不执行 ``EPOLL_CTL_DEL``。

本章结束时， ``epoll_wait`` 返回1，用户得到 ``EPOLLIN|EPOLLHUP``。因为pidfd在post-reap状态下永久ready，level-triggered ``I`` 会再次进入ready list。

为什么零超时仍会处理已有ready item
-----------------------------------

``timeout=0`` 的含义是：

::

   do not wait for a future event

它不是：

::

   ignore events that are already ready

进入 ``epoll_wait`` 后，内核解析fd 7并取得eventpoll ``EP``。 ``EP.rdllist`` 已经包含 ``I``，所以ready检查立即成功，不会把parent挂入 ``EP.wq``，也不会调用 ``schedule()``。

控制流直接进入：

::

   epoll_wait
   → ep_poll
   → ep_send_events

parent从始至终都是CPU0上的当前task。

为什么I在waitid之后仍留在ready list
---------------------------------

上一章第一次交付pidfd event时，registration是level-triggered。 ``ep_deliver_event`` 在成功复制event之后执行：

.. code-block:: c

   if (!(epi->event.events & EPOLLET))
       list_add_tail(&epi->rdllink, &ep->rdllist);

``waitid(P_PIDFD)`` 操作child状态与 ``struct pid`` linkage，不会操作eventpoll的ready list，也不会删除registration。

因此waitid返回后：

::

   child readiness state changed
   EP.rdllist membership unchanged

``I`` 是一个待重新验证的ready candidate。

本次scan怎样取走I
----------------

``ep_send_events`` 获取 ``EP.mtx``，然后：

::

   ep_start_scan(EP, scan_batch)
   → splice EP.rdllist into local scan_batch
   → EP.rdllist becomes temporarily empty
   → I is owned by the current scan

在 ``EP.mtx`` 持有期间：

* ``EPOLL_CTL_DEL`` 不能并发删除 ``I``；
* eventpoll close不能并发销毁 ``EP``；
* ``I`` 在本地scan batch中保持有效。

接着进入：

::

   ep_deliver_event
   → list_del_init(I.rdllink)
   → ep_item_poll(I)

为什么epoll必须再次调用pidfd_poll
--------------------------------

ready-list membership只说明某个callback或上一次level delivery认为目标可能ready。真正复制给用户之前，epoll必须重新调用目标file的 ``poll`` 方法。

``ep_item_poll`` 临时增加 ``F6`` 的file reference，然后设置poll key：

::

   I.event.events = EPOLLIN | EPOLLERR | EPOLLHUP

用户在ADD时只提交 ``EPOLLIN``，但 ``do_epoll_ctl_file`` 会自动加入 ``EPOLLERR|EPOLLHUP``。这是为什么HUP即使不显式写进interest mask也会被报告。

随后：

::

   vfs_poll(F6)
   → pidfd_poll(F6, NULL-like poll table)

本次poll table没有queue callback，因此不会重复向 ``P->wait_pidfd`` 添加新的wait entry。原来的callback ``CB`` 仍由registration持有。

pidfd_poll怎样识别post-reap状态
-------------------------------

``pidfd_poll`` 先取得：

.. code-block:: c

   struct pid *P = pidfd_pid(F6);

然后在RCU read-side临界区执行：

.. code-block:: c

   task = pid_task(P, PIDTYPE_PID);

上一章的 ``release_task`` 已经解除所有task linkage，所以：

::

   task = NULL

fixed source直接返回：

.. code-block:: c

   EPOLLIN | EPOLLRDNORM | EPOLLHUP

三个bit表达不同含义：

* ``EPOLLIN``：pidfd存在可观察的终止状态；
* ``EPOLLRDNORM``：普通poll read-normal别名；
* ``EPOLLHUP``：pidfd对应的task linkage已经完全消失。

zombie阶段为什么没有EPOLLHUP
----------------------------

child刚退出但还没有被wait回收时：

::

   pid_task(P, PIDTYPE_PID) = child task
   child->exit_state        = EXIT_ZOMBIE

该分支只返回：

::

   EPOLLIN | EPOLLRDNORM

回收之后task pointer变为NULL，才进入包含 ``EPOLLHUP`` 的分支。

所以pidfd poll可以区分：

::

   exited but still waitable  → EPOLLIN
   fully reaped               → EPOLLIN | EPOLLHUP

这不等于读取接口
----------------

普通pidfd file没有 ``read`` file operation。 ``EPOLLIN`` 在这里不是“可以read若干字节”，而是统一poll API中的“退出状态可观察”标志。

用户获取退出信息的接口仍然是：

* ``waitid(P_PIDFD)``：自然parent/ptracer消费child状态；
* ``PIDFD_GET_INFO``：在支持的flags和权限语义下读取pidfs保存的信息。

poll readiness本身不消费 ``P->attr``，也不会改变 ``P`` reference count。

ep_item_poll为什么最终留下IN与HUP
--------------------------------

``ep_item_poll`` 对目标返回值执行interest mask过滤：

.. code-block:: c

   return res & I.event.events;

本场景：

::

   pidfd_poll result = EPOLLIN | EPOLLRDNORM | EPOLLHUP
   I.event.events    = EPOLLIN | EPOLLERR | EPOLLHUP

交集是：

::

   EPOLLIN | EPOLLHUP

``EPOLLRDNORM`` 没有出现在用户event中，因为registration没有请求该bit。

epoll怎样复制第二个event
-----------------------

``epoll_put_uevent`` 写入：

::

   events2[0].events   = EPOLLIN | EPOLLHUP
   events2[0].data.u64 = 0x50494436

固定用户buffer可写，所以复制成功。 ``ep_deliver_event`` 返回1， ``ep_send_events`` 的result变为1。

为什么I又被放回ready list
------------------------

该registration：

* 没有 ``EPOLLONESHOT``；
* 没有 ``EPOLLET``；
* 是普通level-triggered模式。

成功交付后， ``ep_deliver_event`` 再次执行：

.. code-block:: c

   list_add_tail(&I->rdllink, &EP->rdllist);

这一次不是stale requeue。重新poll已经确认pidfd仍真实ready。

``ep_done_scan`` 完成scan状态收尾。由于 ``EP.rdllist`` 仍非空，后续另一个 ``epoll_wait`` 也会立即看到event；不需要新的child exit wake，因为child不可能再次退出。

post-reap readiness为什么是永久的
--------------------------------

只要pidfd保持open：

::

   N->i_private = P
   pid_task(P, PIDTYPE_PID) = NULL

这两个条件不会恢复：

* 旧 ``P`` 不会重新连接到未来复用数字PID ``C`` 的task；
* pidfd不会重新指向另一个 ``struct pid``；
* waitid不能把已reap的task重新创建出来。

因此每次 ``pidfd_poll`` 都会返回包含HUP的mask，直到fd 6关闭。

第二次epoll_wait怎样返回
-----------------------

``ep_send_events`` 完成， ``ep_poll`` 不进入等待路径，syscall返回：

::

   epoll_wait(7, events2, 1, 0) = 1

回到CPL 3时：

::

   RAX                 = 1
   events2[0].events   = EPOLLIN | EPOLLHUP
   events2[0].data.u64 = 0x50494436

没有task切换，没有timer，也没有新的wake callback。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：post-reap pidfd readiness delivered；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* parent：``TASK_RUNNING``， ``on_rq=1``、 ``on_cpu=1``；
* last syscall：``epoll_wait(7, events2, 1, 0)``；
* last result/RAX：1；
* ``events2[0].events``：``EPOLLIN|EPOLLHUP``；
* ``events2[0].data.u64``：``0x50494436``；
* child task：不存在；
* numeric PID ``C``：可复用，但本章没有被重新分配；
* pidfd file ``F6``：active；
* pidfs dentry/inode ``D/N``：active；
* old ``struct pid P``：active，无task linkage；
* ``P->attr``：保留exit metadata；
* ``P->wait_pidfd``：仍包含callback ``CB``；
* eventpoll ``EP``：active， ``refcount=2``；
* ``EP.rbr``：包含 ``I``；
* ``EP.rdllist``：再次包含 ``I``；
* ``EP.wq``：empty；
* fd 6/7：open；
* filesystem/block I/O：none；
* next entry：``epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)``。

关键边界
--------

#. 零超时epoll仍处理已经ready的item，只是不等待未来event。
#. ready list中的item必须在交付前重新调用目标 ``poll``。
#. pidfd的zombie readiness与post-reap readiness不同，后者增加 ``EPOLLHUP``。
#. ``EPOLLERR|EPOLLHUP`` 在ADD时被内核自动加入registration mask。
#. 用户只请求 ``EPOLLIN`` 仍会收到 ``EPOLLHUP``。
#. ``EPOLLRDNORM`` 没有被请求，因此不会出现在本次用户event中。
#. pidfd的 ``EPOLLIN`` 不代表普通字节read接口可用。
#. epoll event不会改变pidfs exit metadata或pid reference。
#. level-triggered item在永久ready时会在每次成功交付后重新入ready list。
#. 未来复用数字PID ``C`` 的task不会改变旧pidfd的poll结果。
#. 本章没有scheduler sleep、signal delivery或磁盘I/O。

固定源码依据
------------

* `fs/pidfs.c：pidfd_poll <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/pidfs.c#L307-L327>`_
* `fs/eventpoll.c：ADD自动加入ERR/HUP与DEL入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c#L2665-L2690>`_
* `fs/eventpoll.c：ep_item_poll <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c#L1315-L1335>`_
* `fs/eventpoll.c：ep_deliver_event与level requeue <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c#L2035-L2112>`_
* `fs/eventpoll.c：ep_send_events <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c#L2114-L2158>`_
