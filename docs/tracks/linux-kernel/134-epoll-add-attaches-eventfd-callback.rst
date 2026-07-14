第一百三十四章：epoll_ctl(ADD) 怎样把eventfd callback挂进wait queue？
================================================================================

上一批已经完成旧eventfd对象的final close。本章开始一个独立运行期场景，重新创建eventfd与epoll实例，并建立它们之间的监视关系。

用户态固定执行：

.. code-block:: c

   int efd = eventfd2(0, EFD_CLOEXEC);          /* 返回 6 */
   int epfd = epoll_create1(EPOLL_CLOEXEC);     /* 返回 7 */

   struct epoll_event ev = {
       .events = EPOLLIN,
       .data.u64 = 0xEFD6,
   };

   epoll_ctl(epfd, EPOLL_CTL_ADD, efd, &ev);

固定条件：

* CPU0是唯一online CPU；
* parent与helper是同一进程内两个 ``SCHED_NORMAL`` 线程；
* 两线程通过 ``CLONE_FILES`` 共享同一个 ``files_struct``；
* fd 0..5已占用，因此eventfd与epoll依次得到fd 6、fd 7；
* eventfd初始counter为0，不启用 ``EFD_NONBLOCK`` 或 ``EFD_SEMAPHORE``；
* epoll采用level-triggered模式；
* 不设置 ``EPOLLET``、 ``EPOLLONESHOT``、 ``EPOLLEXCLUSIVE`` 或 ``EPOLLWAKEUP``；
* 用户event data固定为 ``0xEFD6``；
* eventfd与epoll均设置close-on-exec；
* 没有其他epoll instance、poll waiter、io_uring poll或额外file reference；
* 为固定 ``ep_ctl_lock`` 路径，进入本场景时全局 ``loop_check_gen`` 非0，新分配 ``eventpoll->gen`` 为0，因此非嵌套eventfd add走fast path，只获取 ``ep->mtx``；
* 所有fd、slab、quota与用户内存操作成功。

本章结束时，eventfd还没有ready：counter仍为0，epoll ready list为空；真正建立的是一条从eventfd wait queue指向 ``ep_poll_callback`` 的回调边。

eventfd2先建立fd 6
------------------

``eventfd2(0, EFD_CLOEXEC)`` 沿已经讲过的路径创建：

::

   __x64_sys_eventfd2
   → do_eventfd
   → allocate eventfd_ctx E
   → kref_init(E->kref)
   → init_waitqueue_head(E->wqh)
   → E->count = 0
   → anon_inode_getfile_fmode("[eventfd]", eventfd_fops, E, ...)
   → reserve and publish fd 6

结果对象：

::

   fd 6
   → eventfd file F6
   → F6->private_data = E
   → E->count = 0
   → E->wqh = empty

``EFD_CLOEXEC`` 只设置fdtable中的close-on-exec bit。 ``F6`` 仍是blocking、 ``O_RDWR`` 的anonymous file。

epoll_create1怎样建立fd 7
-------------------------

parent随后执行：

.. code-block:: c

   epoll_create1(EPOLL_CLOEXEC);

x86-64 syscall进入：

::

   __x64_sys_epoll_create1
   → do_epoll_create(EPOLL_CLOEXEC)
   → ep_alloc(&EP)

``ep_alloc`` 分配并初始化 ``struct eventpoll EP``：

::

   mutex_init(EP->mtx)
   spin_lock_init(EP->lock)
   seqcount_spinlock_init(EP->seq)
   init_waitqueue_head(EP->wq)
   init_waitqueue_head(EP->poll_wait)
   INIT_LIST_HEAD(EP->rdllist)
   EP->rbr = RB_ROOT_CACHED
   EP->ovflist = EP_UNACTIVE_PTR
   EP->refcount = 1

几个对象的职责必须分开：

* ``EP->rbr``：保存interest set中的 ``epitem``；
* ``EP->rdllist``：保存当前ready的 ``epitem``；
* ``EP->wq``：供 ``epoll_wait`` 调用者阻塞；
* ``EP->poll_wait``：当这个epoll file本身又被别人poll或epoll监视时使用；
* ``EP->lock``：IRQ-safe地保护ready-list与waiter状态；
* ``EP->mtx``：序列化ctl、ready扫描和删除操作。

随后创建：

::

   anon_inode_getfile("[eventpoll]", eventpoll_fops, EP, O_RDWR|O_CLOEXEC)
   → eventpoll file F7
   → F7->private_data = EP
   → reserve and publish fd 7
   → EP->file = F7

parent返回用户态时：

::

   fd 6 = eventfd file F6
   fd 7 = eventpoll file F7

两者是两个独立anonymous file，不共享 ``private_data``。

epoll_ctl怎样解析两个fd
-----------------------

parent执行：

.. code-block:: c

   epoll_ctl(7, EPOLL_CTL_ADD, 6, &ev);

syscall先把用户态 ``struct epoll_event`` 复制到内核栈：

::

   epds.events = EPOLLIN
   epds.data   = 0xEFD6

``do_epoll_ctl`` 分别解析：

::

   epfd 7 → eventpoll file F7
   target fd 6 → eventfd file F6

并构造key：

::

   tf.file = F6
   tf.fd   = 6

key同时包含file指针与fd整数。这样即使同一个 ``struct file`` 通过dup出现在多个fd上，epoll仍能区分不同的 ``(file, fd)`` 注册项。

进入 ``do_epoll_ctl_file`` 后先检查：

* ``F6`` 提供 ``poll`` operation；
* ``F7`` 确实是eventpoll file；
* ``F7 != F6``；
* 没有非法 ``EPOLLEXCLUSIVE`` 组合。

内核自动扩展interest mask
------------------------

对于 ``EPOLL_CTL_ADD``，内核执行：

.. code-block:: c

   epds.events |= EPOLLERR | EPOLLHUP;

因此用户只写了 ``EPOLLIN``，最终保存在epitem中的mask是：

::

   EPOLLIN | EPOLLERR | EPOLLHUP

``EPOLLERR`` 与 ``EPOLLHUP`` 不需要用户显式请求。它们始终属于epoll要报告的异常/终止状态。

固定场景没有 ``EPOLLET``，所以这是level-triggered注册；没有 ``EPOLLONESHOT``，第一次交付后不会自动disable。

epitem怎样进入interest rbtree
-----------------------------

fast path获取：

::

   mutex_lock(EP->mtx)

``ep_find`` 在空 ``EP->rbr`` 中确认没有同key项目。 ``ep_insert`` 随后分配 ``struct epitem I``：

::

   I->ep             = EP
   I->ffd.file       = F6
   I->ffd.fd         = 6
   I->event.events   = EPOLLIN | EPOLLERR | EPOLLHUP
   I->event.data     = 0xEFD6
   I->rdllink        = empty/unlinked
   I->pwqlist        = NULL
   I->ovflist_next   = EP_UNACTIVE_PTR

``ep_register_epitem`` 把它装入两个索引：

#. 在 ``F6->f_ep`` 对应的hlist中加入 ``I->fllink``，使watched file最终close时可以反向找到所有监视它的epoll；
#. 在 ``EP->rbr`` 中按 ``(F6, 6)`` key插入 ``I->rbn``。

注册项还为 ``EP`` 增加一个reference：

::

   EP->refcount: 1 → 2

第一个reference属于eventpoll file ``F7``；第二个reference属于epitem ``I`` 的存在期。

这里没有为 ``F6`` 永久增加普通file refcount。watched file通过 ``file->f_ep`` 反向链与 ``eventpoll_release_file`` 协调关闭；本场景fd 6保持open，所以 ``F6`` 在后续路径中稳定存在。

poll_wait怎样安装epoll callback
------------------------------

``ep_insert`` 初始化poll table：

::

   epq.epi = I
   epq.pt._qproc = ep_ptable_queue_proc

随后调用：

::

   ep_item_poll(I, &epq.pt, 1)
   → vfs_poll(F6, &epq.pt)
   → eventfd_poll(F6, &epq.pt)

``eventfd_poll`` 第一件事是：

.. code-block:: c

   poll_wait(F6, &E->wqh, &epq.pt);

由于poll table带有 ``ep_ptable_queue_proc``，这不是空操作。回调分配 ``struct eppoll_entry P``：

::

   P->base       = I
   P->whead      = &E->wqh
   P->wait.func  = ep_poll_callback
   P->wait.private = NULL

本场景没有 ``EPOLLEXCLUSIVE``，所以使用：

.. code-block:: c

   add_wait_queue(&E->wqh, &P->wait);

这会把 ``P->wait`` 作为non-exclusive entry加入eventfd的wait queue，并将 ``P`` 链入：

::

   I->pwqlist

因此监视关系真正落地为：

::

   eventfd E->wqh
   → eppoll_entry P
   → wait.func = ep_poll_callback
   → epitem I
   → eventpoll EP

当eventfd以后执行 ``wake_up_locked_poll(..., EPOLLIN)`` 时，通用wait queue代码会调用 ``ep_poll_callback``，而不是直接唤醒parent。

为什么注册完成时还不ready
-------------------------

安装wait entry后， ``eventfd_poll`` 读取：

::

   E->count = 0

它返回：

::

   EPOLLOUT

因为counter仍有写入空间；没有 ``EPOLLIN``。 ``ep_item_poll`` 最后执行：

::

   returned events & I->event.events

``I`` 只关心 ``EPOLLIN|EPOLLERR|EPOLLHUP``，不关心 ``EPOLLOUT``，所以结果为0。

因此 ``ep_insert`` 不把 ``I`` 加入 ``EP->rdllist``：

::

   EP->rbr      = contains I
   EP->rdllist  = empty

这体现了interest与ready两个集合的区别：

* interest rbtree表示“以后监视它”；
* ready list表示“现在有用户请求的事件可交付”。

注册完成与返回
------------

``ep_insert`` 成功后：

::

   ep_ctl_unlock
   → mutex_unlock(EP->mtx)
   → epoll_ctl returns 0

parent回到CPL 3。此时没有线程阻塞，也没有事件被消费。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* scheduling class：``SCHED_NORMAL``；
* latest syscall/result：``epoll_ctl(7, ADD, 6, ...) = 0``；
* shared fd 6：eventfd file ``F6``，open、blocking、close-on-exec；
* eventfd ctx ``E``：active；
* ``E->count``：0；
* ``E->wqh``：包含一个non-exclusive epoll callback entry ``P``；
* shared fd 7：eventpoll file ``F7``，open、close-on-exec；
* eventpoll ``EP``：active；
* ``EP->refcount``：2；
* ``EP->rbr``：包含epitem ``I``；
* ``EP->rdllist``：empty；
* ``EP->ovflist``：``EP_UNACTIVE_PTR``；
* ``EP->wq``：empty；
* ``EP->poll_wait``：empty；
* ``I->event.events``：``EPOLLIN|EPOLLERR|EPOLLHUP``；
* ``I->event.data``：``0xEFD6``；
* ``I->pwqlist``：包含 ``P``；
* eventfd file ``F6->f_ep``：包含 ``I->fllink``；
* parent/helper：均未阻塞于本场景；
* filesystem/block I/O：none；
* next control entry：parent调用 ``epoll_wait(7, events, 1, -1)``。

关键边界
--------

#. eventfd file与eventpoll file是两个独立anonymous file。
#. ``EP->rbr`` 是interest set， ``EP->rdllist`` 是ready set。
#. epoll key包含 ``(struct file *, fd)``，不仅包含fd整数。
#. 内核会自动把 ``EPOLLERR|EPOLLHUP`` 加入interest mask。
#. ``epitem`` 同时进入eventpoll rbtree与watched file的反向 ``f_ep`` 链。
#. ``ep_ptable_queue_proc`` 把 ``ep_poll_callback`` 安装到eventfd的 ``E->wqh``。
#. 未使用 ``EPOLLEXCLUSIVE`` 时，该callback wait entry是non-exclusive。
#. eventfd counter为0时仅报告 ``EPOLLOUT``；因interest不含它，epitem不会ready。
#. callback注册成功不等于有task正在 ``epoll_wait``。
#. epoll注册不读取或修改eventfd counter。

下一任务
--------

下一章追踪：

::

   parent epoll_wait(7, events, 1, -1)
   → EP->rdllist empty
   → stack wait entry joins EP->wq exclusively
   → parent TASK_INTERRUPTIBLE
   → schedule_hrtimeout_range(NULL, ...)
   → helper becomes current on CPU0

资料
----

* `Linux 7.2-rc1 fs/eventpoll.c：epoll create、ctl、epitem与poll callback安装 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
* `Linux 7.2-rc1 fs/eventfd.c：eventfd_poll与ctx wait queue <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventfd.c>`_
* `Linux 7.2-rc1 include/linux/poll.h：poll_wait与poll table <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/poll.h>`_
* `Linux 7.2-rc1 kernel/sched/wait.c：add_wait_queue与wait callback dispatch <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/wait.c>`_
