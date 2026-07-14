第一百五十六章：EPOLL_CTL_DEL怎样拆除pidfd callback与epitem？
====================================================================

上一章结束时，post-reap pidfd仍是永久ready：

::

   fd 6             = open pidfd F6
   fd 7             = open eventpoll F7
   P task linkage   = none
   P->wait_pidfd    = [CB]
   EP.rbr           = [I]
   EP.rdllist       = [I]
   EP.refcount      = 2

parent现在执行：

.. code-block:: c

   epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL);

本章固定条件：

* CPU0是唯一online CPU；
* parent是当前执行者；
* fd 6/7都保持open；
* 没有并发 ``epoll_wait``、close、pidfd wake或file teardown；
* ``I`` 是fd 6在 ``EP`` 中唯一registration；
* ``CB`` 是 ``P->wait_pidfd`` 上唯一epoll callback；
* 没有 ``EPOLLWAKEUP`` wakeup source；
* 所有临时file reference都能成功取得。

本章结束时，callback ``CB`` 已同步移除并释放， ``I`` 已从rbtree和ready list删除并进入RCU延迟回收， ``EP.refcount`` 从2回到1。pidfd本身仍open，旧 ``struct pid P`` 也仍由pidfs inode保持。

DEL怎样解析两个fd
-----------------

syscall入口：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_epoll_ctl
   → do_epoll_ctl
   → do_epoll_ctl_file

内核分别解析：

::

   epfd 7 → eventpoll file F7 → eventpoll EP
   fd 6   → pidfd file F6

这两个解析过程都取得临时file reference，所以在本次ctl结束前：

* ``F7`` 不会被最终释放；
* ``F6`` 不会进入final ``__fput``；
* ``EP``、 ``I`` 和pidfs path保持可访问。

为什么DEL的event参数可以是NULL
-----------------------------

``EPOLL_CTL_DEL`` 不需要新的interest mask或data。内核用registration key查找目标：

::

   key = (F6, fd number 6)

因此第四个参数可以是 ``NULL``。真正参与查找的是已经解析出的file pointer和整数fd，而不是用户event结构。

EP.mtx怎样串行化删除
--------------------

``ep_ctl_lock`` 对DEL只获取：

::

   mutex_lock(EP.mtx)

不需要全局 ``epnested_mutex``，因为删除不会创建新的epoll拓扑边。

持有 ``EP.mtx`` 后， ``ep_find`` 在 ``EP.rbr`` 中找到 ``I``。从这里到删除完成：

* 其他ctl不能修改同一eventpoll；
* eventpoll close不能并发drain该tree；
* ``ep_send_events`` 不能同时scan ``I``。

删除为什么先拆poll wait callback
-------------------------------

``ep_remove`` 的第一步是：

::

   ep_unregister_pollwait(EP, I)

``I->pwqlist`` 中保存一个 ``eppoll_entry``，它包含：

::

   base  = I
   whead = &P->wait_pidfd
   wait.func = ep_poll_callback

``ep_remove_wait_queue`` 在RCU read-side临界区读取 ``whead``，然后调用：

::

   remove_wait_queue(&P->wait_pidfd, &CB.wait)

wait queue内部spinlock把callback removal与任何潜在wake串行化。固定没有并发wake，因此删除直接完成。

为什么CB必须先释放
-----------------

若先释放 ``I``，而 ``CB`` 仍挂在 ``P->wait_pidfd`` 上，未来任何wake都可能通过 ``CB.base`` 解引用已经释放的epitem。

严格顺序必须是：

::

   detach callback from target wait queue
   → free eppoll_entry CB
   → remove epitem I from file/tree/ready list

``ep_unregister_pollwait`` 遍历完整 ``pwqlist``，逐个移除wait entry，再通过 ``kmem_cache_free`` 同步释放callback storage。

完成后：

::

   P->wait_pidfd = empty
   I->pwqlist    = NULL
   CB            = freed

为什么仍要再次pin F6
-------------------

虽然syscall入口已经持有目标file reference， ``ep_remove`` 自己仍通过 ``epi_fget(I)`` 取得一个专用于removal path的file pin。

这个pin证明：

::

   F6 final refcount has not reached zero

因此removal path可以安全操作：

* ``F6->f_lock``；
* ``F6->f_ep``；
* ``I->fllink``。

若final ``__fput`` 已经开始， ``epi_fget`` 会失败，删除工作将交给watched-file close path。本场景fd 6仍open，所以pin成功。

怎样从F6反向watcher链移除I
--------------------------

``ep_remove_file`` 获取：

::

   spin_lock(F6->f_lock)

``I`` 是 ``F6`` 的最后一个watcher，因此：

.. code-block:: c

   WRITE_ONCE(F6->f_ep, NULL);
   hlist_del_rcu(&I->fllink);

设置 ``F6->f_ep=NULL`` 很关键。稍后close fd 6进入 ``__fput`` 时， ``eventpoll_release(F6)`` 可以走fast path，不再扫描任何eventpoll registration。

若per-file ``epitems_head`` 不再被其他reader使用，它也在该步骤之后释放。

I怎样离开rbtree与ready list
--------------------------

接着 ``ep_remove_epi`` 执行：

::

   rb_erase_cached(&I->rbn, &EP->rbr)

此后用 ``EP.lock`` 保护ready-list修改：

.. code-block:: c

   if (ep_is_linked(I))
       list_del_init(&I->rdllink);

上一章level-triggered交付后， ``I`` 确实仍在 ``EP.rdllist``，所以该分支会执行。

完成后：

::

   EP.rbr     = empty
   EP.rdllist = empty

永久ready的pidfd仍存在，但eventpoll已经不再观察它。

为什么I使用kfree_rcu
--------------------

``I`` 还可能被只持有RCU read lock的反向路径检查代码看到，因此不能在rbtree和hlist删除后立即 ``kfree``。

``ep_remove_epi`` 执行：

.. code-block:: c

   kfree_rcu(I, rcu);

从这一刻起：

* ``I`` 已退出活动对象图；
* 任何新ctl/wait都找不到它；
* storage要等RCU grace period后才真正释放。

这是logical lifetime与storage lifetime的分界。

EP.refcount为什么从2回到1
------------------------

创建eventpoll时，eventpoll file持有初始reference：

::

   EP.refcount = 1

成功ADD一个epitem时， ``ep_register_epitem`` 调用 ``ep_get``：

::

   EP.refcount = 2

删除 ``I`` 后， ``ep_remove`` 调用 ``ep_put``：

::

   EP.refcount: 2 → 1

它不会在这里归零，因为fd 7对应的eventpoll file仍open。 ``WARN_ON_ONCE(ep_put(EP))`` 应当为false。

DEL返回时对象状态
-----------------

``ep_ctl_unlock`` 释放 ``EP.mtx``。syscall入口归还临时 ``F6`` 和 ``F7`` references，然后返回：

::

   epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL) = 0

回到CPL 3时：

* pidfd仍可直接poll；
* pidfd依旧返回 ``EPOLLIN|EPOLLRDNORM|EPOLLHUP``；
* fd 7的eventpoll为空；
* 再调用零超时 ``epoll_wait(7, ...)`` 会返回0；
* 不会再有pidfd callback把item加入 ``EP.rdllist``。

DEL不会释放哪些对象
-------------------

本次操作不会释放：

* pidfd file ``F6``；
* pidfs dentry ``D``；
* pidfs inode ``N``；
* old ``struct pid P``；
* ``P->attr`` exit metadata；
* eventpoll file ``F7``；
* eventpoll ``EP``。

它只结束registration层：

::

   callback CB
   epitem I
   file↔eventpoll reverse link

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU：CPU0，CPL 3；
* last syscall：``epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)``；
* last result/RAX：0；
* fd 6：open pidfd ``F6``；
* fd 7：open eventpoll ``F7``；
* ``P->wait_pidfd``：empty；
* callback ``CB``：freed synchronously；
* ``F6->f_ep``：NULL；
* ``EP.rbr``：empty；
* ``EP.rdllist``：empty；
* epitem ``I``：logical lifetime ended；
* ``I`` storage：queued/freed through ``kfree_rcu``；
* ``EP.refcount``：1；
* old ``struct pid P``：active，无task linkage；
* pidfs ``D/N``：active；
* numeric PID ``C``：可复用，本章未重新分配；
* filesystem/block I/O：none；
* next entry：``close(6)``，随后 ``close(7)``。

关键边界
--------

#. DEL用 ``(file, fd)`` 查找registration，event参数可以为NULL。
#. ``EP.mtx`` 串行化ctl、delivery和eventpoll close。
#. callback必须先从target wait queue移除，再释放epitem。
#. target waitqueue lock串行化wake与callback removal。
#. callback storage同步释放，epitem storage通过RCU延迟释放。
#. ``epi_fget`` 证明watched file没有进入final ``__fput``。
#. 最后watcher删除时 ``F6->f_ep`` 变为NULL。
#. ``I`` 必须同时从rbtree和ready list删除。
#. 删除registration不改变pidfd自身的永久readiness。
#. epitem持有一个eventpoll reference；DEL使refcount从2降到1。
#. 本章没有释放pidfs inode、 ``struct pid`` 或eventpoll。

固定源码依据
------------

* `fs/eventpoll.c：ep_unregister_pollwait <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c#L900-L936>`_
* `fs/eventpoll.c：ep_remove_file、ep_remove_epi与ep_remove <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c#L1070-L1165>`_
* `fs/eventpoll.c：EPOLL_CTL_DEL dispatch <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c#L2665-L2690>`_
* `include/linux/pid.h：struct pid wait_pidfd <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/pid.h#L60-L76>`_
