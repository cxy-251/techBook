第一百五十章：EPOLL_CTL_DEL 怎样拆除timerfd callback与epitem？
================================================================================

上一章结束时，timerfd已经没有实际readiness：

::

   T->ticks       = 0
   T->expired     = 0
   EP->rdllist    = empty

registration仍然存在：

::

   EP->rbr contains epitem I
   T->wqh contains callback P
   EP->refcount = 2

parent现在执行：

.. code-block:: c

   epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL);

本章固定条件：

* fd 6仍指向timerfd file ``F6``；
* fd 7仍指向eventpoll file ``F7``；
* ``I`` 的key是 ``(F6, fd 6)``；
* ``I`` 是 ``F6`` 的唯一epoll watcher；
* ``P`` 是 ``I->pwqlist`` 中唯一eppoll entry；
* ``P`` 仍挂在 ``T->wqh``，但没有callback正在执行；
* ``I`` 不在 ``EP->rdllist`` 或 ``EP->ovflist``；
* 没有并发timer expiration、pollfree、close、ADD、MOD或DEL；
* fd与slab操作均成功。

本章结束在registration已被完整删除： ``P`` 同步释放， ``I`` 退出活动对象图并通过 ``kfree_rcu`` 等待回收， ``EP->refcount`` 从2降回1。

DEL syscall怎样定位两个file
---------------------------

x86-64控制路径为：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_epoll_ctl
   → do_epoll_ctl

内核分别解析：

::

   epfd 7 → eventpoll file F7 → eventpoll EP
   fd   6 → timerfd file F6

这两个查找都取得临时file reference，确保本次ctl期间 ``F6`` 与 ``F7`` 不会进入最终 ``__fput``。

``EPOLL_CTL_DEL`` 不读取用户 ``event`` 内容，所以第四个参数可以为NULL。删除目标由：

::

   (watched struct file *, source fd number)

共同组成的key确定。在本场景中就是 ``(F6, 6)``。

EP.mtx保护哪些结构
------------------

``do_epoll_ctl`` 获取：

::

   mutex_lock(&EP->mtx)

然后在 ``EP->rbr`` 中找到 ``I``。 ``EP->mtx`` 在本次删除期间保护：

* rbtree membership；
* ``I->pwqlist``；
* registration event mask与data；
* epitem删除顺序；
* 与eventpoll close及watched-file close teardown的串行化。

此时 ``I`` 已不在ready list，所以后续ready unlink步骤不会改变list内容。

第一步为什么必须先拆除P
----------------------

删除进入：

::

   ep_remove(EP, I)
   → ep_unregister_pollwait(EP, I)

``ep_unregister_pollwait`` 遍历 ``I->pwqlist``。本场景只有 ``P``：

::

   pwq = P
   P->whead = &T->wqh

``ep_remove_wait_queue`` 在RCU read-side临界区内以acquire语义读取 ``P->whead``。因为timerfd没有发出 ``POLLFREE``，该指针仍然非NULL，于是执行：

::

   remove_wait_queue(&T->wqh, &P->wait)

``remove_wait_queue`` 获取 ``T->wqh.lock``，把 ``P`` 从目标wait queue删除。这个waitqueue lock与可能的：

::

   wake_up_locked_poll(&T->wqh, EPOLLIN)

共享同一串行化边界。因此一旦remove返回，本场景中不存在一个已经取得queue lock、随后还会调用 ``P->wait.func`` 的timerfd wake路径。

之后：

::

   kmem_cache_free(P)
   I->pwqlist = NULL

``P`` 的storage同步释放，不使用 ``kfree_rcu``。

为什么callback必须早于epitem释放
------------------------------

``P->base`` 指向 ``I``， ``P->wait.func`` 是 ``ep_poll_callback``。若先释放 ``I``，再从 ``T->wqh`` 移除 ``P``，并发wake可能通过 ``P->base`` 解引用已经结束生命周期的epitem。

因此所有epitem removal路径保持严格顺序：

::

   unregister poll callbacks
   → detach reverse file link
   → erase/free epitem

本固定场景没有并发callback，锁与顺序仍然不能省略。

epi_fget为什么还要临时pin F6
----------------------------

callback拆除后， ``ep_remove`` 调用：

::

   file = epi_fget(I)

``epi_fget`` 对 ``I->ffd.file`` 执行file reference获取。成功表示 ``F6`` 尚未进入最终 ``__fput``；本次DEL可以安全访问：

* ``F6->f_lock``；
* ``F6->f_ep``；
* ``I->fllink``。

本章固定没有close并发，因此pin成功。临时reference在 ``ep_remove`` 返回后由cleanup路径配对 ``fput``。

最后watcher怎样让F6.f_ep变成NULL
-------------------------------

``ep_remove_file`` 获取：

::

   spin_lock(&F6->f_lock)

``I`` 是 ``F6`` 的唯一watcher，所以：

::

   hlist_is_singular_node(&I->fllink, F6->f_ep) = true

内核发布：

::

   WRITE_ONCE(F6->f_ep, NULL)

然后：

::

   hlist_del_rcu(&I->fllink)

释放 ``F6->f_lock`` 后，最后一个动态分配的 ``epitems_head`` 可以被释放。

``F6->f_ep=NULL`` 的意义是：下一章timerfd file进入 ``__fput`` 时，通用 ``eventpoll_release(F6)`` 能走没有watcher的fast path，不需要再扫描或删除epitem。

I怎样退出rbtree与ready状态
-------------------------

接着执行：

::

   ep_remove_epi(EP, I)

步骤为：

#. ``rb_erase_cached(&I->rbn, &EP->rbr)``；
#. 获取 ``EP->lock``；
#. 检查 ``I`` 是否仍在ready list；
#. 本场景中 ``I`` 已不linked，因此不执行list删除；
#. 释放 ``EP->lock``；
#. 注销可选wakeup source；
#. ``kfree_rcu(I, rcu)``；
#. 下降用户epoll-watch计数。

从 ``rb_erase_cached`` 完成起，新的 ``epoll_ctl`` 与 ``epoll_wait`` 已无法通过 ``EP`` 找到 ``I``。 ``kfree_rcu`` 延迟的是memory storage回收，不是registration的逻辑存活时间。

为什么I使用kfree_rcu
--------------------

某些epoll拓扑检查在RCU read-side临界区中沿watched-file反向链接观察 ``I``。即使本场景没有嵌套epoll，通用实现仍使用：

::

   kfree_rcu(I, rcu)

这保证旧RCU reader完成前，不会复用 ``I`` 所在memory。

因此本章结束时需要区分：

::

   I logical lifetime = ended
   I storage          = queued for / completed after RCU grace period

EP.refcount为什么从2降到1
------------------------

创建eventpoll时，eventpoll file持有初始reference：

::

   EP refcount = 1

成功注册 ``I`` 时， ``ep_register_epitem`` 调用 ``ep_get(EP)``：

::

   EP refcount = 2

删除完成后 ``ep_remove`` 执行：

::

   ep_put(EP)

本次结果为：

::

   EP refcount: 2 → 1

返回false，表示这不是最后一个eventpoll reference。剩余reference由fd 7对应的eventpoll file持有，因此本章不会调用 ``ep_free``。

DEL怎样返回用户态
-----------------

``ep_remove`` 完成后：

* 释放 ``EP->mtx``；
* 释放对 ``F6`` 与 ``F7`` 的syscall临时file references；
* ``do_epoll_ctl`` 返回0；
* syscall exit恢复CPL 3， ``RAX=0``。

删除registration不会：

* 关闭fd 6或fd 7；
* 改变timerfd ``ticks``；
* 改变timerfd hrtimer状态；
* 自动释放timerfd ctx；
* 自动释放eventpoll object；
* 向用户events数组写入内容。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* last syscall：``epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)``；
* last result/RAX：0；
* fd 6：open timerfd file ``F6``；
* timerfd ctx ``T``：active；
* embedded hrtimer：inactive；
* ``T->ticks``：0；
* ``T->expired``：0；
* ``T->wqh``：empty；
* callback ``P``：synchronously freed；
* fd 7：open eventpoll file ``F7``；
* eventpoll ``EP``：active， ``refcount=1``；
* ``EP->rbr``：empty；
* ``EP->rdllist``：empty；
* ``EP->ovflist``：``EP_UNACTIVE_PTR``；
* epitem ``I``：logical lifetime ended；
* ``I`` storage：queued/freed through RCU grace period；
* ``F6->f_ep``：NULL；
* helper：阻塞在timerfd/epoll之外；
* filesystem/block I/O：none；
* next control entry：``close(6)``，随后 ``close(7)``。

关键边界
--------

#. ``EPOLL_CTL_DEL`` 通过 ``(file, fd)`` key定位registration。
#. DEL不读取用户event对象，第四参数可为NULL。
#. ``EP->mtx`` 串行化ctl、delivery与close removal路径。
#. callback必须在epitem之前拆除。
#. target waitqueue lock同步wake callback执行与callback removal。
#. ``P`` 同步释放，不使用RCU延迟。
#. ``epi_fget`` pin阻止watched file在删除中途进入最终 ``__fput``。
#. 最后watcher删除时 ``F6->f_ep`` 被发布为NULL。
#. ``I`` 从rbtree删除后registration立即失效。
#. ``kfree_rcu(I)`` 只延迟storage复用，不延长逻辑registration。
#. epitem持有一个eventpoll reference，DEL使refcount从2降到1。
#. timerfd和eventpoll file仍保持open。

下一任务
--------

下一章依次执行：

::

   close(6)
   → timerfd_release
   → hrtimer_cancel(inactive) returns 0
   → kfree_rcu(T)

   close(7)
   → empty ep_clear_and_put
   → EP refcount 1 → 0
   → ep_free / kfree_rcu(EP)

资料
----

* `Linux 7.2-rc1 fs/eventpoll.c：ep_unregister_pollwait、ep_remove_file与ep_remove_epi <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
* `Linux 7.2-rc1 fs/timerfd.c：timerfd wait queue与release入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/timerfd.c>`_
