第一百六十九章：close(7)与close(8)怎样释放两端Unix socket和空eventpoll？
================================================================================

上一章结束时，fd 6已经关闭，但peer引用让dead ``SA`` 暂时继续存在：

::

   fd 6 = closed
   fd 7 → F7 → socket B → SB
   fd 8 → F8 → eventpoll EP

   SA:
       orphan/dead
       sk_state    = TCP_CLOSE
       sk_shutdown = SHUTDOWN_MASK
       unix_peer   = NULL
       kept alive by unix_peer(SB)

   SB:
       sk_state    = TCP_ESTABLISHED
       sk_shutdown = SHUTDOWN_MASK
       unix_peer   = SA

   EP:
       rbr      = empty
       rdllist  = empty
       refcount = 1

parent依次执行：

.. code-block:: c

   int r1 = close(7);
   int r2 = close(8);

本章固定：

* fd 7是socket file ``F7`` 的最后file reference；
* fd 8是eventpoll file ``F8`` 的最后file reference；
* 两端receive queue均为空；
* 不存在 ``SCM_RIGHTS``、OOB数据、pending error或异步I/O；
* eventpoll中已经没有registration、callback或waiter；
* parent与helper不会并发访问fd 7/8；
* 不发生signal、allocation failure、RCU stall或close race；
* 本章结束时fd 6/7/8均关闭，两个Unix socket和eventpoll均退出活动对象图。

close(7)怎样撤销最后一个socket fd
--------------------------------

parent先执行：

::

   close(7)
   → close_fd_get_file(7)

共享fdtable在锁保护下清除：

::

   fdt->fd[7] = NULL
   open_fds bit 7 = 0
   close_on_exec bit 7 = 0

parent与helper随后都不能再通过数字7访问 ``F7``。

由于这是最后file reference，close同步进入：

::

   __fput(F7)

fd 7从未被epoll监视，所以 ``F7.f_ep`` 为NULL；eventpoll target-release fastpath不执行任何额外工作。

B怎样进入unix_release_sock
--------------------------

``F7`` 的 ``socket_file_ops.release`` 调用：

::

   sock_close(sockfs inode B, F7)
   → __sock_release(socket B, inode B)
   → unix_release(B)
   → unix_release_sock(SB, 0)

``unix_release_sock`` 先把SB从Unix socket表移除，然后在state lock下执行：

::

   sock_orphan(SB)
   SB.sk_shutdown = SHUTDOWN_MASK
   SB.sk_state    = TCP_CLOSE

SB本来已经是 ``SHUTDOWN_MASK``，所以shutdown bits不再变化； ``sk_state`` 从 ``TCP_ESTABLISHED`` 进入 ``TCP_CLOSE``。

最后的peer pointer怎样清除
-------------------------

release路径读取：

::

   skpair = unix_peer(SB) = SA

随后清除：

::

   unix_peer(SB) = NULL

现在两边都不再保存peer pointer：

::

   unix_peer(SA) = NULL
   unix_peer(SB) = NULL

由于 ``skpair`` 非NULL且类型为 ``SOCK_STREAM``，路径仍会锁住dead SA并写入：

::

   SA.sk_shutdown = SHUTDOWN_MASK

该值已经成立。SA receive queue为空， ``embrion=0``，所以不会设置 ``SA.sk_err``。

随后调用：

::

   SA.sk_state_change(SA)
   sk_wake_async(SA, SOCK_WAKE_WAITD, POLL_HUP)

SA已经orphan且没有用户waiter，因此不会唤醒任务。这些调用保持release路径在普通、监听与并发等待场景中的统一语义。

SA的最后peer reference怎样释放
-----------------------------

B清除peer pointer后执行：

::

   sock_put(SA)

这归还socketpair建立时B为 ``unix_peer(SB)=SA`` 持有的reference。

上一章已经归还SA自身file/socket拥有reference；因此本次 ``sock_put(SA)`` 可以使SA的socket reference下降到0，并进入最终socket释放。

最终析构路径调用 ``unix_sock_destructor(SA)``。它确认：

::

   SA.receive_queue is empty
   SA is unhashed
   SA.sk_socket == NULL or detached
   SOCK_DEAD is set

随后：

* 若有Unix address则下降address reference；本场景没有address；
* ``unix_nr_socks`` 下降1；
* network namespace中的Unix protocol in-use计数下降1；
* ``struct unix_sock UA`` / ``struct sock SA`` storage最终归还。

因此dead SA从上一章的“逻辑已关闭但storage仍存活”变成真正释放。

B自身怎样释放
-------------

``unix_release_sock(SB)`` 接着清空SB receive queue。本场景为空，不需要释放skb或传递的file references。

随后调用：

::

   sock_put(SB)

A关闭时已经归还A持有的SB peer reference；现在fd 7对应的file/socket主reference也归还。SB reference下降到0， ``unix_sock_destructor(SB)`` 完成：

* 检查empty receive queue；
* 确认socket已dead和unhashed；
* 下降 ``unix_nr_socks``；
* 下降Unix stream protocol使用计数；
* 释放 ``UB/SB`` storage。

两个socket的最终storage释放顺序可能表现为：

::

   sock_put(SA) → free SA
   ...
   sock_put(SB) → free SB

关键不是绝对指令间距，而是引用约束：SA必须等SB清除peer reference；SB必须等自己的file reference与A先前持有的peer reference均已归还。

F7与sockfs inode怎样收尾
-----------------------

``unix_release`` 设置：

::

   B->sk = NULL

``__sock_release`` 随后清除：

::

   B->ops  = NULL
   B->file = NULL

通用 ``__fput`` 释放 ``F7``、sockfs pseudo dentry和sockfs inode B。绑定在该inode中的 ``struct socket B`` 随inode生命周期结束。

全局sockfs mount继续active；关闭最后一个用户socket不会卸载sockfs。

返回：

::

   close(7) = 0

此时：

::

   fd 6/7 closed
   SA freed
   SB freed
   F6/F7 freed
   socket A/B VFS objects gone

close(8)怎样进入eventpoll release
--------------------------------

parent继续执行：

::

   close(8)
   → close_fd_get_file(8)

共享fdtable清除：

::

   fdt->fd[8] = NULL
   open_fds bit 8 = 0
   close_on_exec bit 8 = 0

最后file reference进入：

::

   __fput(F8)
   → eventpoll file_operations.release
   → ep_eventpoll_release(inode, F8)
   → ep_clear_and_put(EP)

EP为什么不需要再次拆callback
----------------------------

当前：

::

   EP.rbr       = empty
   EP.rdllist   = empty
   EP.poll_wait = empty
   EP.refcount  = 1

``ep_clear_and_put`` 首先检查poll-on-ep waiters。当前没有其他epoll或poll对象等待F8，所以不需要wake。

随后取得 ``EP.mtx`` 并执行两遍teardown：

::

   ep_drain_pollwaits(EP)
   ep_drain_tree(EP)

两次遍历都发现RB tree为空：

* 没有poll callback需要注销；
* 没有target-file reverse link需要移除；
* 没有epitem需要再次 ``kfree_rcu``；
* 不会访问已经关闭的socket files。

这也是上一章先DEL再close socket的结果：eventpoll final close只处理空容器。

EP reference怎样到0
------------------

释放 ``EP.mtx`` 后， ``ep_clear_and_put`` 下降eventpoll file持有的base reference：

::

   EP.refcount: 1 → 0

返回值表明这是最后reference，因此调用：

::

   ep_free(EP)

``ep_free`` 清理eventpoll自身资源，包括：

* mutex与内部计数关联；
* user epoll accounting reference；
* optional wakeup-source与busy-poll状态；
* eventpoll对象的内部等待与锁状态。

最终：

::

   kfree_rcu(EP)

EP从所有用户可达结构中立即消失，但其storage可以在 ``close(8)`` 返回后，等RCU grace period完成再真正释放。

F8与anon_inodefs怎样释放
-----------------------

``ep_eventpoll_release`` 返回后，通用 ``__fput`` 继续释放：

* eventpoll file ``F8``；
* per-file ``[eventpoll]`` pseudo dentry；
* per-file anon_inodefs mount reference；
* file credential与owner状态。

全局anon_inodefs mount和singleton anon inode继续active。

返回：

::

   close(8) = 0

完整收尾顺序
------------

本批三个章节可以压缩为：

::

   epoll_ctl(8, DEL, 6, NULL)
   → remove P from socket A wait queue
   → free P synchronously
   → clear F6.f_ep and reverse hlist
   → erase I from EP.rbr and EP.rdllist
   → kfree_rcu(I)
   → EP.refcount 2 -> 1

   close(6)
   → unpublish fd 6
   → final __fput(F6)
   → unix_release_sock(SA)
   → SA orphan, TCP_CLOSE, SHUTDOWN_MASK
   → clear unix_peer(SA)
   → SB gains SHUTDOWN_MASK and HUP semantics
   → drop SA-held reference to SB
   → drop file/socket reference to SA
   → SA remains alive because unix_peer(SB)=SA
   → free F6 and socket A sockfs VFS objects

   close(7)
   → unpublish fd 7
   → unix_release_sock(SB)
   → SB orphan, TCP_CLOSE, SHUTDOWN_MASK
   → clear unix_peer(SB)
   → drop final peer reference to SA
   → final destroy SA
   → drop final SB reference
   → final destroy SB
   → free F7 and socket B sockfs VFS objects

   close(8)
   → unpublish fd 8
   → empty ep_clear_and_put
   → EP.refcount 1 -> 0
   → logical free and kfree_rcu(EP)
   → free F8 and eventpoll pseudo path

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：Unix stream socketpair data, half-close and final teardown complete；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* parent：``TASK_RUNNING``，``on_rq=1``、``on_cpu=1``；
* helper：blocked outside released objects；
* ``EPOLL_CTL_DEL`` result：0；
* ``close(6)`` result：0；
* ``close(7)`` result：0；
* final syscall/result：``close(8)=0``；
* fd 6/7/8：closed and unallocated；
* callback ``P``：freed synchronously；
* epitem ``I``：logical lifetime ended，storage through RCU；
* socket file ``F6/F7``：freed；
* socket A/B sockfs VFS objects：freed；
* ``SA/UA``：freed；
* ``SB/UB``：freed；
* Unix peer references：none；
* receive queues：destroyed after empty teardown；
* global sockfs：active；
* eventpoll ``EP``：logical lifetime ended，storage through RCU；
* eventpoll file ``F8``：freed；
* global anon_inodefs：active；
* filesystem/block/device/network packet I/O：none；
* next runtime scenario：unselected。

关键边界
--------

#. fd 7关闭时先清除B的peer pointer，再下降最后的SA peer reference。
#. dead SA的storage生命周期可以跨越 ``close(6)``，直到peer B释放引用。
#. socket file、sockfs inode/``struct socket`` 与 ``struct sock`` 具有不同生命周期边界。
#. SB在自己的close中进入orphan、 ``TCP_CLOSE`` 与 ``SHUTDOWN_MASK``。
#. 两端queue为空，因此关闭不产生 ``ECONNRESET`` 或skb丢弃分支。
#. ``unix_sock_destructor`` 负责最终Unix socket accounting与storage释放。
#. sockfs是全局pseudo filesystem，不因用户socket全部关闭而卸载。
#. 显式DEL使eventpoll final close面对空RB tree，无需反向访问socket file。
#. eventpoll base reference由fd 8的file持有，close时从1下降到0。
#. EP逻辑生命周期在close中结束，storage通过RCU延迟释放。
#. anon_inodefs全局对象不会因eventpoll关闭而卸载。
#. 整个socketpair场景没有经过IP、路由、网卡、ext4或块设备。

下一任务
--------

当前场景已经完整闭环。下一主线不预设总章数，按源码覆盖自然推进。优先候选是TCP/IPv4 loopback建立连接的前半段：

::

   server socket(AF_INET, SOCK_STREAM|SOCK_CLOEXEC, 0)
   → bind(127.0.0.1:fixed_port)
   → listen(backlog)
   client socket(AF_INET, SOCK_STREAM|SOCK_CLOEXEC, 0)
   → connect(127.0.0.1:fixed_port)
   → loopback route and TCP SYN processing
   → accept4 publishes connected server fd

开始前必须固定network namespace、loopback device、路由、端口、socket state、request socket、SYN/SYN-ACK/ACK、softirq/NAPI边界与scheduler顺序。

资料
----

* `Linux 7.2-rc1 net/unix/af_unix.c：unix_release_sock、peer reference与unix_sock_destructor <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/unix/af_unix.c>`_
* `Linux 7.2-rc1 net/socket.c：sock_close、__sock_release、sockfs file与inode lifetime <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/socket.c>`_
* `Linux 7.2-rc1 fs/eventpoll.c：ep_clear_and_put、ep_eventpoll_release与ep_free <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
