第一百六十七章：EPOLL_CTL_DEL怎样从persistent-ready Unix socket拆除callback与epitem？
============================================================================================

上一章结束时，fd 6对应的Unix stream接收端已经得到peer half-close：

::

   SA.sk_state       = TCP_ESTABLISHED
   SA.sk_shutdown    = RCV_SHUTDOWN
   SA.receive_queue  = empty
   unix_peer(SA)     = SB

   SB.sk_state       = TCP_ESTABLISHED
   SB.sk_shutdown    = SEND_SHUTDOWN
   unix_peer(SB)     = SA

parent最后一次 ``read(6)`` 已经返回EOF 0。由于 ``RCV_SHUTDOWN`` 是持久状态，level-triggered epitem ``I`` 仍在eventpoll ready list：

::

   EP.rbr     = { I }
   EP.rdllist = { I }
   EP.refcount= 2

callback ``P`` 仍挂在socket A的wait queue：

::

   A.wq.wait = { P }

parent现在执行：

.. code-block:: c

   int rc = epoll_ctl(8, EPOLL_CTL_DEL, 6, NULL);

本章固定：

* parent与helper共享同一个 ``files_struct``；
* fd 6、fd 7、fd 8均open；
* fd 6和fd 7都是最后的用户file references；
* fd 8对应eventpoll ``EP``；
* registration只包含fd 6，interest为 ``EPOLLIN|EPOLLRDHUP``；
* ``I`` 同时位于RB tree与ready list；
* callback ``P`` 是 ``I`` 唯一的poll wait entry；
* 不发生并发wake、close、signal、copy fault或allocation failure；
* DEL之后不再使用epoll监视fd 6；
* 本章结束时fd 6/7/8仍然open，但registration与callback已经彻底拆除。

DEL为什么允许event参数为NULL
----------------------------

x86-64 syscall入口进入：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_epoll_ctl
   → do_epoll_ctl(8, EPOLL_CTL_DEL, 6, NULL)

``EPOLL_CTL_ADD`` 和 ``EPOLL_CTL_MOD`` 需要从用户地址读取 ``struct epoll_event``； ``EPOLL_CTL_DEL`` 不改变interest mask或用户data，因此不读取event结构。

所以：

::

   epoll_ctl(8, EPOLL_CTL_DEL, 6, NULL)

是合法调用。 ``NULL`` 不是错误，也不会触发 ``-EFAULT``。

内核怎样稳定eventpoll与target file
---------------------------------

控制路径先从共享fdtable取得：

::

   epfd 8 → eventpoll file F8 → EP
   fd   6 → socket file F6    → socket A

syscall持有临时file references，所以在本章固定无并发close条件下， ``F8``、 ``EP``、 ``F6`` 与socket A都不会在操作中消失。

内核随后取得：

::

   mutex_lock(&EP.mtx)

并按file pointer与原始fd number组成的key查找：

::

   ep_find(EP, F6, 6) → I

这里同时使用file与fd值，是因为同一个open file description可以通过 ``dup`` 出现在多个fd位置，而epoll registration需要保持精确关系。

为什么persistent-ready不会阻止DEL
---------------------------------

``I`` 当前仍是真正ready：如果再次调用 ``epoll_wait``， ``unix_poll`` 仍会因为 ``RCV_SHUTDOWN`` 返回 ``EPOLLIN|EPOLLRDHUP``。

DEL不要求target先变成not-ready，也不要求用户先把ready event“消费干净”。它直接删除registration本身：

::

   relationship = (EP watches F6 through I)

因此即使 ``I`` 仍在 ``EP.rdllist``，DEL也可以同步把它从ready list移除。

callback怎样从socket wait queue注销
----------------------------------

找到 ``I`` 后，控制流进入：

::

   ep_remove(EP, I)
   → ep_unregister_pollwait(EP, I)

``I.pwqlist`` 中只有一项 ``P``。 ``ep_remove_wait_queue`` 读取 ``P.whead``，固定场景中它仍指向：

::

   &A.wq.wait

函数取得该wait queue head的自旋锁并执行：

::

   remove_wait_queue(&A.wq.wait, &P.wait)

状态变化为：

::

   A.wq.wait: { P } → empty

这一步与可能正在运行的wake callback同步。固定场景没有并发wake；即便存在并发，wait queue lock与eventpoll的POLLFREE协议也会阻止callback在entry释放后继续解引用 ``I``。

随后：

::

   kmem_cache_free(pwq_cache, P)

所以callback ``P`` 的逻辑生命周期和storage生命周期都在DEL syscall内同步结束。

为什么还要临时pin住F6
---------------------

注销callback后， ``ep_remove`` 调用：

::

   epi_fget(I)

它尝试增加 ``F6`` 的file reference。这个临时pin保证下面修改 ``F6.f_ep`` 与反向hlist时，不会与target file的最后一次 ``__fput`` 交错。

固定场景没有并发close，因此pin成功：

::

   F6 file refcount: N → N+1 temporarily

函数退出时通过自动 ``fput`` 归还该临时reference。

F6上的反向epoll关系怎样清除
---------------------------

``ep_remove_file`` 在 ``F6.f_lock`` 下检查target file的watcher list。当前fd 6只被这个eventpoll监视，因此 ``I.fllink`` 是最后一个node。

状态变化：

::

   F6.f_ep: epitems_head → NULL
   remove I.fllink from target-file reverse hlist
   free last epitems_head when safe

把 ``F6.f_ep`` 发布为NULL很重要。后续 ``close(6)`` 进入 ``__fput`` 时，eventpoll release fastpath可以直接判断：

::

   F6 has no epoll watchers

因此无需再取得 ``EP.mtx`` 或从target-file close路径反向删除registration。

I怎样同时退出RB tree和ready list
--------------------------------

``ep_remove_epi`` 先删除查找关系：

::

   rb_erase_cached(&I.rbn, &EP.rbr)

随后取得 ``EP.lock``。因为 ``I`` 当前位于ready list：

::

   list_del_init(&I.rdllink)

最终：

::

   EP.rbr     = empty
   EP.rdllist = empty

这一步不会调用 ``unix_poll``。DEL已经决定删除registration，没有必要再次确认fd 6是否仍ready。

为什么I不是立即kfree
-------------------

RB tree、ready list和target-file reverse hlist都不再引用 ``I`` 后，内核执行：

::

   kfree_rcu(I, rcu)

``I`` 的逻辑生命周期立即结束，但storage要等RCU grace period之后才能真正归还。原因是eventpoll存在RCU读侧路径，可能刚刚观察过反向关系。

DEL返回前保证：

* 新的socket wake不会再通过 ``P`` 访问 ``I``；
* ``I`` 已不在任何用户可达的eventpoll结构中；
* 未来 ``epoll_wait(8, ...)`` 不会再报告fd 6；
* 不保证RCU callback已经执行。

EP reference怎样下降
--------------------

registration建立时为eventpoll增加了一份reference：

::

   EP.refcount: 1 → 2

``ep_remove`` 删除registration后调用 ``ep_put``：

::

   EP.refcount: 2 → 1

剩余的一份base reference由仍open的eventpoll file ``F8`` 持有。因此DEL不会释放 ``EP``。

syscall返回
----------

控制流释放 ``EP.mtx``，归还临时的 ``F6``、 ``F8`` references，并返回：

::

   epoll_ctl(8, EPOLL_CTL_DEL, 6, NULL) = 0

fdtable没有变化：

::

   fd 6 → F6
   fd 7 → F7
   fd 8 → F8

DEL删除的是监视关系，不是任何fd。

本章结束状态
------------

* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* parent： ``TASK_RUNNING``， ``on_rq=1``、 ``on_cpu=1``；
* helper：blocked outside socket objects；
* ``EPOLL_CTL_DEL`` result/RAX：0；
* fd 6/7/8：open；
* ``SA.sk_state=TCP_ESTABLISHED``；
* ``SA.sk_shutdown=RCV_SHUTDOWN``；
* ``SB.sk_state=TCP_ESTABLISHED``；
* ``SB.sk_shutdown=SEND_SHUTDOWN``；
* ``unix_peer(SA)=SB``、 ``unix_peer(SB)=SA``；
* callback ``P``：freed synchronously；
* ``A.wq.wait``：empty；
* epitem ``I``：logically dead，storage queued through RCU；
* ``EP.rbr=empty``、 ``EP.rdllist=empty``；
* ``EP.refcount=1``；
* ``F6.f_ep=NULL``；
* next entry：parent ``close(6)``。

关键边界
--------

#. DEL不读取用户 ``struct epoll_event``，因此event参数可以是NULL。
#. persistent-ready registration可以直接删除，不需要先消费或清除readiness。
#. callback注销在target socket wait queue lock下完成。
#. callback ``P`` 在DEL中同步free。
#. ``epi_fget`` 临时pin住target file，避免与最后 ``__fput`` 竞争。
#. 最后一个watcher删除时， ``F6.f_ep`` 被发布为NULL。
#. DEL同时从RB tree、ready list和target-file反向hlist移除关系。
#. 删除registration不调用 ``unix_poll``。
#. epitem逻辑生命周期立即结束，storage通过RCU延迟回收。
#. registration reference下降后，eventpoll仍由fd 8的file base reference持有。
#. DEL不会修改socket shutdown、peer relation或fdtable。

下一入口
--------

parent将执行：

::

   close(6)

该调用会释放socket A对应的sockfs file，把A设为 ``TCP_CLOSE|SHUTDOWN_MASK``，并通知仍open的peer B连接已经彻底断开。

资料
----

* `Linux 7.2-rc1 fs/eventpoll.c：ep_unregister_pollwait、ep_remove_file、ep_remove_epi与ep_remove <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
* `Linux 7.2-rc1 net/socket.c：socket file与poll wait queue入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/socket.c>`_
