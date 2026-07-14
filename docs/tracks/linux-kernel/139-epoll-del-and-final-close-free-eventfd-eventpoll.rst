第一百三十九章：EPOLL_CTL_DEL与close()怎样拆除callback并释放eventfd/eventpoll？
================================================================================

上一章结束时，eventfd已经不再满足 ``EPOLLIN``，ready list也已清空，但epoll registration仍然存在：

::

   fd 6                  = eventfd file F6
   E->count              = 0
   E->wqh                = contains callback P
   fd 7                  = eventpoll file F7
   EP->rbr               = contains epitem I
   EP->rdllist           = empty
   I->pwqlist            = contains P
   EP->refcount          = 2

parent依次执行：

.. code-block:: c

   epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL);
   close(6);
   close(7);

本章固定条件：

* CPU0是唯一online CPU；
* parent是三个syscall的执行者；
* helper继续阻塞在eventfd之外；
* parent与helper共享 ``files_struct``；
* 没有并发write、read、epoll_wait、epoll_ctl或close；
* 没有in-flight ``ep_poll_callback``；
* ``I`` 是 ``EP`` 中唯一registration；
* ``P`` 是 ``I`` 唯一poll-wait entry；
* ``EP->rdllist`` 与 ``EP->wq`` 均为空；
* eventfd file和eventpoll file都只有fdtable持有的长期reference；
* syscall内部临时file reference按正常scope释放；
* 没有epoll nesting、EPOLLWAKEUP、FASYNC、LSM错误或copy fault；
* 所有slab、RCU与VFS teardown正常执行。

本章结束在fd 6和fd 7均关闭，eventfd ctx和两份anon-inode file/path均结束生命周期；epitem ``I`` 与eventpoll ``EP`` 已经逻辑释放并通过 ``kfree_rcu`` 等待或完成RCU grace period后的memory回收。

EPOLL_CTL_DEL为什么可以传NULL event
----------------------------------

parent首先执行：

::

   epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)

``SYSCALL_DEFINE4(epoll_ctl)`` 只在 ``ep_op_has_event(op)`` 为true时从用户态复制 ``struct epoll_event``。 ``EPOLL_CTL_DEL`` 不需要新interest mask，因此：

* ``event=NULL`` 合法；
* 不执行 ``copy_from_user``；
* 不访问用户event memory。

syscall通过fd 7取得eventpoll file ``F7``，通过fd 6取得target file ``F6``，构造key：

::

   key.file = F6
   key.fd   = 6

两个CLASS(fd)对象在syscall期间持有临时file references，防止对象在控制操作中被最终关闭。

ep_ctl为什么只锁EP->mtx
----------------------

``do_epoll_ctl_file`` 确认：

* ``F6`` 支持poll；
* ``F7`` 确实是eventpoll file；
* target不是 ``F7`` 自身。

对于 ``EPOLL_CTL_DEL``， ``ep_ctl_lock`` 只获取：

::

   mutex_lock(&EP->mtx)

它不运行ADD时的cycle/path检查，也不需要 ``epnested_mutex``。在mutex保护下， ``ep_find`` 用 ``(F6, fd 6)`` key在RB tree中找到 ``I``。

ep_unregister_pollwait怎样移除P
-------------------------------

DEL进入：

::

   ep_remove(EP, I)

第一步是：

.. code-block:: c

   ep_unregister_pollwait(EP, I);

它遍历 ``I->pwqlist``，本场景只有 ``P``。 ``ep_remove_wait_queue`` 在RCU read-side中读取：

::

   P->whead = &E->wqh

固定没有 ``POLLFREE`` teardown，所以指针非NULL。随后：

::

   remove_wait_queue(&E->wqh, &P->wait)

``remove_wait_queue`` 获取 ``E->wqh.lock``，把callback entry从eventfd wait queue摘除，再释放锁。返回后：

::

   E->wqh      = empty
   I->pwqlist  = NULL

``P`` 随后由 ``kmem_cache_free(pwq_cache, P)`` 同步归还slab。自此eventfd的任何wake都不可能再通过旧 ``P`` 访问 ``I``。

为什么先拆callback再释放epitem
----------------------------

顺序必须是：

::

   unregister poll wait entry
   → detach epitem from file/tree
   → free epitem

wait queue callback可能在eventfd wake路径中运行，并解引用 ``P->base=I``。先在 ``E->wqh.lock`` 保护下移除 ``P``，会与任何in-flight callback串行化。固定场景没有in-flight callback，但teardown仍执行完整同步协议。

epi_fget为什么临时增加F6引用
-----------------------------

callback拆除后， ``ep_remove`` 调用：

::

   file = epi_fget(I)

它对 ``I->ffd.file=F6`` 执行 ``file_ref_get``。此时fd 6仍打开，final ``__fput`` 尚未开始，所以pin成功。

这个临时reference保证后续可以安全操作：

* ``F6->f_lock``；
* ``F6->f_ep``；
* ``I->fllink``。

``ep_remove`` 返回时cleanup attribute自动执行 ``fput(F6)``。由于fdtable长期reference仍存在，这次fput只撤销临时pin，不触发 ``eventfd_release``。

ep_remove_file怎样断开watched-file反向链接
-----------------------------------------

``ep_remove_file`` 在 ``EP->mtx`` 已持有的情况下再获取：

::

   spin_lock(&F6->f_lock)

``I`` 是 ``F6`` 的最后且唯一watcher，所以：

::

   F6->f_ep = NULL
   hlist_del_rcu(&I->fllink)

普通non-epoll target使用一个独立 ``epitems_head`` 包装反向hlist。最后watcher移除后，该head同步归还 ``ephead_cache``。

``F6->f_ep=NULL`` 很重要：稍后 ``close(6)`` 进入通用 ``eventpoll_release(F6)`` 时，可以走fast path，不再调用 ``eventpoll_release_file`` 搜索旧registration。

ep_remove_epi怎样结束I的活动身份
--------------------------------

随后 ``ep_remove_epi``：

::

   rb_erase_cached(&I->rbn, &EP->rbr)

``EP->rdllist`` 已在上一章清空，因此 ``EP->lock`` 下不需要执行实际ready-list删除。没有 ``EPOLLWAKEUP``，对应wakeup source为空。

然后：

::

   kfree_rcu(I, rcu)
   percpu_counter_dec(epoll_watches)

从此 ``I`` 已从所有活动索引结构中消失：

* 不在 ``EP->rbr``；
* 不在 ``EP->rdllist``；
* 不在 ``F6->f_ep`` hlist；
* 不再拥有poll wait entry。

``kfree_rcu`` 表示storage回收延迟到RCU grace period后。DEL返回时不能再合法访问 ``I``，即使其物理memory可能尚未交还slab。

EP refcount为什么从2降到1
------------------------

创建eventpoll时：

::

   EP->refcount = 1

每个成功注册的epitem再通过 ``ep_get(EP)`` 增加一个reference。当前只有 ``I``，因此DEL前为2。

``ep_remove`` 最后执行：

::

   ep_put(EP)

转换为：

::

   EP->refcount: 2 → 1

结果不为0，因为eventpoll file ``F7`` 仍持有基础reference。 ``WARN_ON_ONCE(ep_put(EP))`` 不触发， ``EP`` 不会在 ``epoll_ctl`` 内被释放。

``EP->mtx`` 解锁后， ``epoll_ctl`` 返回0。此时：

::

   E->wqh       = empty
   F6->f_ep     = NULL
   EP->rbr      = empty
   EP->rdllist  = empty
   EP->refcount = 1

close(6)怎样释放eventfd
----------------------

parent接着执行 ``close(6)``。共享fdtable中的slot 6、open bit和close-on-exec bit先被清除，helper也同时失去fd 6。

固定fdtable reference为最后file reference， ``fput_close_sync(F6)`` 同步进入 ``__fput(F6)``。通用 ``eventpoll_release(F6)`` 看到：

::

   F6->f_ep = NULL

因此没有registration需要由watched-file close路径清理。

``eventfd_release`` 执行：

::

   wake_up_poll(&E->wqh, EPOLLHUP)

但 ``E->wqh`` 已因DEL变为空，所以没有callback或task被唤醒。随后：

::

   eventfd_ctx_put(E)
   → E kref 1 → 0
   → ida_free(E->id)
   → kfree(E)

``__fput`` 再释放 ``[eventfd]`` pseudo dentry、per-file anon_inodefs mount reference与 ``F6`` 本身。close返回0。

close(7)怎样释放空eventpoll
--------------------------

最后执行 ``close(7)``。fd 7先从共享fdtable撤销， ``fput_close_sync(F7)`` 同步进入最终 ``__fput``。

``F7->f_op->release`` 是：

::

   ep_eventpoll_release
   → ep_clear_and_put(EP)

``EP->poll_wait`` 为空，不需要wake poll-on-ep observer。 ``ep_clear_and_put`` 获取 ``EP->mtx`` 后运行两遍teardown：

#. ``ep_drain_pollwaits``；
#. ``ep_drain_tree``。

由于DEL已经使 ``EP->rbr`` 为空，两次遍历都没有对象可处理。释放mutex后：

::

   ep_put(EP)
   → EP->refcount 1 → 0

于是调用 ``ep_free(EP)``：

::

   ep_resume_napi_irqs
   mutex_destroy(&EP->mtx)
   free_uid(EP->user)
   wakeup_source_unregister(EP->ws)
   kfree_rcu(EP, rcu)

本场景没有NAPI与EPOLLWAKEUP状态，相应清理没有额外observer。 ``EP`` 的逻辑生命周期在此结束；storage可能在RCU grace period后才真正归还allocator。

随后 ``__fput(F7)`` 释放 ``[eventpoll]`` pseudo dentry、per-file anon_inodefs mount reference和 ``F7``。 ``close(7)`` 返回0。

为什么先DEL再close不是强制要求
-----------------------------

Linux允许直接关闭watched fd或eventpoll fd，相关release路径会自动清理registration。本章显式执行DEL，是为了把三条边界分开观察：

::

   EPOLL_CTL_DEL  = remove relationship
   close(6)       = destroy eventfd endpoint/context
   close(7)       = destroy eventpoll container

显式DEL后：

* close eventfd不再需要 ``eventpoll_release_file`` 反向拆除item；
* close eventpoll面对空RB tree；
* callback、relationship与两个file object的lifetime清晰分离。

完整对象结束顺序
----------------

本章顺序可以压缩为：

::

   epoll_ctl DEL
   → lock EP.mtx
   → remove P from E.wqh
   → free P
   → pin F6 temporarily
   → clear F6.f_ep and remove I.fllink
   → erase I from EP.rbr
   → kfree_rcu(I)
   → EP.refcount 2 → 1
   → unlock EP.mtx
   → epoll_ctl returns 0

   close(6)
   → remove fd 6 publication
   → final __fput(F6)
   → empty EPOLLHUP wake
   → E kref 1 → 0
   → free E id/ctx/path/file
   → close returns 0

   close(7)
   → remove fd 7 publication
   → final __fput(F7)
   → ep_eventpoll_release
   → empty drain passes
   → EP.refcount 1 → 0
   → kfree_rcu(EP)
   → free eventpoll path/file
   → close returns 0

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：level-triggered eventfd/epoll lifecycle complete；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* scheduling class：``SCHED_NORMAL``；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、 ``on_cpu=1``；
* last syscall：``close(7)``；
* last result/RAX：0；
* ``epoll_ctl DEL`` result：0；
* ``close(6)`` result：0；
* shared fd 6：closed and unallocated；
* shared fd 7：closed and unallocated；
* eventfd file ``F6``：freed；
* eventfd ctx ``E``：freed；
* eventfd internal id：returned to ``eventfd_ida``；
* callback entry ``P``：freed synchronously duringDEL；
* target ``F6->f_ep``：对象已不存在；DEL前已设NULL；
* epitem ``I``：unregistered、logical lifetime ended；
* ``I`` storage：queued/freed through RCU grace period；
* eventpoll file ``F7``：freed；
* eventpoll ``EP``：logical lifetime ended；
* ``EP`` storage：queued/freed through RCU grace period；
* ``EP->rbr``：释放前为空；
* ``EP->rdllist``：释放前为空；
* singleton ``anon_inode_inode``：仍active；
* global ``anon_inode_mnt``：仍mounted；
* helper：仍阻塞在eventfd之外；
* shared ``files_struct``：仍active，fd 0..5保持原状；
* filesystem/block I/O：none；
* next runtime scenario：unselected。

关键边界
--------

#. ``EPOLL_CTL_DEL`` 不读取用户 ``struct epoll_event``，event参数可以为NULL。
#. callback entry必须在epitem释放前从目标wait queue同步移除。
#. ``ep_unregister_pollwait`` 通过目标waitqueue lock与in-flight callback串行化。
#. ``epi_fget`` 临时pin watched file，防止与final ``__fput`` 竞态。
#. 最后watcher移除时， ``F6->f_ep`` 被设为NULL。
#. DEL移除registration，不关闭target fd或eventpoll fd。
#. epitem reference使 ``EP->refcount`` 从1增到2，DEL再降回1。
#. ``kfree_rcu(I)`` 后I已不可访问，即使storage尚待grace period回收。
#. 显式DEL让eventfd close时的 ``eventpoll_release`` 走空fast path。
#. eventfd close在空wait queue上发送HUP，不产生observer。
#. eventpoll close对空RB tree执行两遍空drain，再把refcount从1降到0。
#. ``kfree_rcu(EP)`` 结束逻辑lifetime，并延迟实际memory回收。
#. 两个anonymous file的dentry/mount reference分别由各自 ``__fput`` 释放。
#. 全局singleton anon inode与anon_inodefs mount不随这两个fd关闭而消失。

下一任务
--------

当前没有已选定场景。优先候选是 ``signalfd4`` 与epoll组合：

::

   block SIGUSR1 in parent/helper
   → signalfd4(-1, mask(SIGUSR1), SFD_CLOEXEC) creates fd 6
   → epoll_create1 creates fd 7
   → EPOLL_CTL_ADD signalfd EPOLLIN
   → parent epoll_wait blocks
   → helper tgkill sends SIGUSR1 to parent
   → signal remains blocked and pending
   → signalfd poll callback marks epitem ready
   → epoll_wait returns EPOLLIN
   → read signalfd_siginfo consumes pending signal

开始前必须固定signal target、shared/private pending queue、mask ownership、signalfd wait queue、task wake规则、epoll callback和read dequeue顺序。

资料
----

* `Linux 7.2-rc1 fs/eventpoll.c：EPOLL_CTL_DEL、ep_remove、RCU free与eventpoll release <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
* `Linux 7.2-rc1 fs/eventfd.c：eventfd release与ctx free <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventfd.c>`_
* `Linux 7.2-rc1 fs/file_table.c：final __fput通用file/path teardown <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/file_table.c>`_
* `Linux 7.2-rc1 fs/open.c：close与fput_close_sync <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/open.c>`_
