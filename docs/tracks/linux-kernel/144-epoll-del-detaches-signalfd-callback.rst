第一百四十四章：EPOLL_CTL_DEL 怎样拆除signalfd callback与epitem？
================================================================================

上一章结束时，zero-time ``epoll_wait`` 已经重新poll signalfd并清除了stale-ready membership：

::

   EP->rbr      contains I
   EP->rdllist  empty
   I->pwqlist   contains P
   P            attached to sighand->signalfd_wqh
   EP refcount  = 2

parent现在执行：

.. code-block:: c

   epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL);

本章固定条件：

* CPU0是唯一online CPU；
* parent与helper共享 ``files_struct``、 ``signal_struct`` 与 ``sighand_struct``；
* fd 6是signalfd file ``F6``，fd 7是eventpoll file ``F7``；
* ``EP->rbr`` 中只有一个epitem ``I``；
* ``I`` 当前不在 ``EP->rdllist``；
* ``I->pwqlist`` 只有一个 ``eppoll_entry P``；
* ``P->whead`` 指向共享 ``sighand->signalfd_wqh``；
* ``F6->f_ep`` 只包含 ``I`` 这一名watcher；
* 没有并发signal、poll callback、epoll wait、ctl、close或sighand teardown；
* 没有fd lookup、lock、allocation或scheduler failure。

本章结束在registration已经删除： ``P`` 同步释放， ``I`` 退出活动对象图并通过 ``kfree_rcu`` 延迟回收， ``EP->refcount`` 从2降为1；两个fd仍然open。

为什么DEL可以传NULL event
-------------------------

native x86-64进入：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_epoll_ctl
   → do_epoll_ctl

对于 ``EPOLL_CTL_ADD`` 与 ``EPOLL_CTL_MOD``，内核需要从用户地址复制 ``struct epoll_event``。对于 ``EPOLL_CTL_DEL``，event参数不参与删除目标识别：

::

   target key = (target struct file F6, integer fd 6)

因此固定调用中的第四参数可以是NULL。删除依据是epoll内部rbtree中的key，而不是用户再次提交的event mask或data。

fd lookup怎样暂时pin两个file
---------------------------

``do_epoll_ctl`` 分别解析：

::

   epfd 7 → eventpoll file F7 → eventpoll EP
   tfd  6 → signalfd file F6

fd lookup在syscall期间持有临时file references，保证：

* ``F7`` 不会在操作中途进入final ``__fput``；
* ``F6`` 不会在查找registration时被释放；
* shared fdtable中即使存在其他线程，当前固定场景也不会发生close竞态。

内核确认：

* fd 7确实是eventpoll file；
* fd 6不是fd 7自身；
* operation为合法 ``EPOLL_CTL_DEL``；
* ``I`` 可通过key在 ``EP->rbr`` 中找到。

随后获取：

::

   mutex_lock(EP->mtx)

``EP->mtx`` 串行化同一eventpoll上的ADD、MOD、DEL、event delivery和release tree walk。

为什么先移除P再释放I
--------------------

删除入口最终调用：

::

   ep_remove(EP, I)

第一步是：

.. code-block:: c

   ep_unregister_pollwait(EP, I);

它遍历 ``I->pwqlist``。固定只有 ``P``：

::

   I->pwqlist → P → NULL

``ep_remove_wait_queue(P)`` 通过acquire load读取 ``P->whead``。当前没有 ``POLLFREE`` teardown，所以得到：

::

   P->whead = &shared_sighand->signalfd_wqh

随后：

::

   remove_wait_queue(signalfd_wqh, &P->wait)
   → lock signalfd_wqh.lock
   → unlink P.wait.entry
   → unlock signalfd_wqh.lock

wait queue removal与任何可能正在运行的 ``ep_poll_callback`` 使用同一waitqueue lock串行化。固定场景没有in-flight callback，因此返回后可以确定：

::

   no future callback can start through P

接着：

::

   kmem_cache_free(pwq_cache, P)

``P`` 是同步释放的，不经过 ``kfree_rcu``。这是因为waitqueue unlink和锁同步已经结束它的callback可达性。

共享signalfd wait queue为什么没有被释放
-------------------------------------

``P`` 被移除的是共享：

::

   sighand->signalfd_wqh

这个wait queue属于 ``sighand_struct``，不属于 ``signalfd_ctx S``，也不属于epitem ``I``。删除registration只改变queue membership：

::

   signalfd_wqh entries: [ P ] → empty

wait queue head本身继续存在，因为parent与helper仍共享并引用同一个 ``sighand_struct``。

``signalfd_cleanup`` 中的 ``wake_up_pollfree`` 只在sighand teardown时处理queue lifetime；本次 ``EPOLL_CTL_DEL`` 不会调用它。

epi_fget为什么再次pin F6
-----------------------

移除poll wait entries后， ``ep_remove`` 执行：

::

   file = epi_fget(I)

``epi_fget`` 对 ``I->ffd.file`` 执行不可复活的file reference获取。成功说明 ``F6`` 尚未进入final ``__fput``，当前删除路径可以安全操作：

::

   F6->f_lock
   F6->f_ep
   I->fllink

固定fd lookup本身已经pin住 ``F6``，所以 ``epi_fget`` 必然成功。这个额外pin属于 ``ep_remove`` 的内部竞态防护，离开函数时由scoped ``fput`` 归还。

最后watcher怎样清空F6->f_ep
---------------------------

``ep_remove_file`` 在持有 ``EP->mtx`` 的同时获取：

::

   spin_lock(F6->f_lock)

固定 ``I`` 是 ``F6->f_ep`` 中唯一watcher，因此：

::

   WRITE_ONCE(F6->f_ep, NULL)
   hlist_del_rcu(&I->fllink)

对于非epoll target file，承载reverse hlist的 ``epitems_head`` 在确认没有并发publication后也被释放。

把 ``F6->f_ep`` 设为NULL有一个重要后续效果：下一章关闭fd 6时，通用 ``eventpoll_release(F6)`` 可以走无watcher fast path，不需要从target-file侧反向搜索和删除registration。

I怎样退出rbtree与ready list
--------------------------

接着 ``ep_remove_epi`` 执行：

::

   rb_erase_cached(&I->rbn, &EP->rbr)

上一章已经清除stale-ready membership，所以在 ``EP->lock`` 下检查：

::

   ep_is_linked(I) = false

无需再次 ``list_del_init``。固定状态变化：

::

   EP->rbr     : [ I ] → empty
   EP->rdllist : empty → empty

随后解除可能的wakeup source bookkeeping，并执行：

::

   kfree_rcu(I, rcu)

从这一步起， ``I`` 已经不再是合法可访问对象。其slab memory可能在RCU grace period之后才真正归还allocator。

为什么EP refcount从2降到1
------------------------

创建 ``EP`` 时，eventpoll file持有基础reference：

::

   EP refcount = 1

``epoll_ctl(ADD)`` 成功注册 ``I`` 时执行 ``ep_get(EP)``：

::

   EP refcount = 2

``ep_remove`` 完成后调用：

::

   ep_put(EP)

固定转换：

::

   EP refcount: 2 → 1

结果不会为0，因为fd 7对应的eventpoll file仍持有基础reference。代码中的 ``WARN_ON_ONCE(ep_put(EP))`` 因此不会触发。

DEL返回时哪些对象仍存在
----------------------

释放 ``EP->mtx`` 并归还临时file references后，syscall返回0：

::

   epoll_ctl(7, DEL, 6, NULL) = 0

此时：

* fd 6仍然open；
* signalfd ctx ``S`` 仍然active；
* fd 7仍然open；
* eventpoll ``EP`` 仍然active；
* ``P`` 已同步释放；
* ``I`` 已logical-dead，storage由RCU延迟回收；
* ``EP->rbr`` 与 ``EP->rdllist`` 都为空；
* ``F6->f_ep`` 为NULL；
* shared ``sighand->signalfd_wqh`` 存在且为空。

DEL只删除relationship，不隐式关闭任一fd，也不修改signal mask或pending queues。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* latest syscall：``epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)``；
* return/RAX：0；
* fd 6：open blocking signalfd file ``F6``，close-on-exec；
* signalfd ctx ``S``：active；
* ``F6->f_ep``：NULL；
* fd 7：open eventpoll file ``F7``，close-on-exec；
* eventpoll ``EP``：active；
* ``EP->refcount``：1；
* ``EP->rbr``：empty；
* ``EP->rdllist``：empty；
* ``EP->wq``：empty；
* callback ``P``：freed synchronously；
* epitem ``I``：unregistered、logical lifetime ended；
* ``I`` storage：queued/freed through ``kfree_rcu`` grace period；
* shared ``sighand->signalfd_wqh``：active、empty；
* parent/helper blocked mask：仍包含 ``SIGUSR1``；
* parent private pending与shared pending：无 ``SIGUSR1``；
* filesystem/block I/O：none；
* next control entry：``close(6)``，随后 ``close(7)``。

关键边界
--------

#. ``EPOLL_CTL_DEL`` 用 ``(file, fd)`` key查找registration，不读取用户event对象。
#. syscall fd lookup与 ``epi_fget`` 是不同层次的file lifetime保护。
#. callback entry必须先从target wait queue移除，再允许epitem退出生命周期。
#. waitqueue lock把callback执行与callback removal串行化。
#. ``P`` 在unlink后同步free，不使用RCU延迟。
#. ``sighand->signalfd_wqh`` 属于共享sighand，不随 ``P`` 或 ``I`` 消失。
#. 最后watcher删除时 ``F6->f_ep`` 被publication为NULL。
#. ``I`` 从rbtree删除后通过 ``kfree_rcu`` 延迟回收storage。
#. ready-list为空与registration删除是两个先后独立步骤。
#. epitem持有一个eventpoll reference；删除后 ``EP->refcount`` 从2降为1。
#. DEL不关闭fd 6或fd 7，也不修改blocked mask或pending signal。

下一任务
--------

下一章完成两个final close：

::

   close(6)
   → synchronous final __fput(F6)
   → eventpoll_release fast path because F6->f_ep=NULL
   → signalfd_release kfree(S)
   → release [signalfd] pseudo path and file

   close(7)
   → synchronous final __fput(F7)
   → ep_eventpoll_release
   → empty pollwait/tree drain
   → EP refcount 1 → 0
   → ep_free / kfree_rcu(EP)
   → release [eventpoll] pseudo path and file

资料
----

* `Linux 7.2-rc1 fs/eventpoll.c：ep_unregister_pollwait、ep_remove与epitem RCU释放 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
* `Linux 7.2-rc1 include/linux/eventpoll.h：target file反向watcher fast path <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/eventpoll.h>`_
* `Linux 7.2-rc1 fs/signalfd.c：共享sighand wait queue使用方式 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/signalfd.c>`_
