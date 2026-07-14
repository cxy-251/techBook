第一百六十八章：close(6)怎样释放socket A，却让dead SA继续被peer reference保持？
====================================================================================

上一章已经删除fd 6对应的epoll registration：

::

   A.wq.wait = empty
   F6.f_ep   = NULL
   EP.rbr    = empty
   EP.rdllist= empty
   EP.refcount=1

Unix stream pair仍处于half-close状态：

::

   SA.sk_state       = TCP_ESTABLISHED
   SA.sk_shutdown    = RCV_SHUTDOWN
   unix_peer(SA)     = SB

   SB.sk_state       = TCP_ESTABLISHED
   SB.sk_shutdown    = SEND_SHUTDOWN
   unix_peer(SB)     = SA

parent现在执行：

.. code-block:: c

   int rc = close(6);

本章固定：

* parent与helper共享同一个 ``files_struct``；
* fd 6是socket file ``F6`` 的最后file reference；
* fd 7和fd 8保持open；
* 两端receive queue均为空；
* 不存在未读skb、 ``SCM_RIGHTS``、OOB数据或pending error；
* fd 6已经不再被任何eventpoll监视；
* helper不会并发访问fd 6或fd 7；
* 不发生signal、allocation failure或close race；
* 本章结束时fd 6已关闭，fd 7仍open；
* socket A已经orphan、dead并进入 ``TCP_CLOSE``，但其 ``struct sock SA`` 仍可能因B保存的peer reference而继续存在。

close怎样先撤销fdtable发布
-------------------------

x86-64 syscall入口进入：

::

   close(6)
   → __x64_sys_close
   → close_fd_get_file(6)

在共享fdtable锁保护下，内核清除：

::

   fdt->fd[6] = NULL
   open_fds bit 6 = 0
   close_on_exec bit 6 = 0

从这一刻起，parent和helper都不能再通过数字6取得 ``F6``。共享 ``files_struct`` 意味着close不是“只关闭parent自己的fd 6”。

内核随后对取得的 ``F6`` 执行同步close路径。固定场景中它是最后file reference，因此进入最后一次：

::

   __fput(F6)

为什么eventpoll release fastpath不再做事
--------------------------------------

``__fput`` 在调用file-specific ``release`` 前先处理eventpoll反向关系。上一章已经发布：

::

   F6.f_ep = NULL

因此eventpoll release fastpath直接跳过慢路径：

* 不取得 ``EP.mtx``；
* 不删除epitem；
* 不操作ready list；
* 不触碰socket wait queue。

这证明显式 ``EPOLL_CTL_DEL`` 已经把eventpoll关系完整拆除。

sock_close怎样进入Unix协议release
---------------------------------

``F6`` 使用 ``socket_file_ops``，其 ``release`` 为：

::

   sock_close(inode, F6)
   → __sock_release(socket A, sockfs inode A)

``__sock_release`` 在sockfs inode锁下调用：

::

   A->ops->release(A)
   → unix_release(A)

``unix_release`` 取得：

::

   sk = A->sk = SA

随后依次执行：

::

   SA.sk_prot->close(SA, 0)
   → unix_close(SA, 0)

   unix_release_sock(SA, 0)

当前Unix stream协议的 ``unix_close`` 不执行额外工作；真正的关系拆除和状态转换位于 ``unix_release_sock``。

SA怎样退出Unix socket表
-----------------------

``unix_release_sock`` 首先执行：

::

   unix_remove_socket(net, SA)
   unix_remove_bsd_socket(SA)

本场景socketpair未bind，因此没有pathname或abstract address需要从命名表解除；它仍需要从unbound Unix socket表移除。

移除后，新的Unix socket查找不会再发现SA。

orphan与shutdown状态怎样建立
----------------------------

内核取得SA的Unix state lock并执行：

::

   sock_orphan(SA)
   SA.sk_shutdown = SHUTDOWN_MASK
   SA.sk_state    = TCP_CLOSE

``sock_orphan`` 断开 ``struct sock`` 与用户socket/file拥有关系，并设置dead语义。随后保存旧peer：

::

   skpair = unix_peer(SA) = SB

再清除A这一侧的peer pointer：

::

   unix_peer(SA) = NULL

释放state lock后，A的状态为：

::

   SA is orphan/dead
   SA.sk_state    = TCP_CLOSE
   SA.sk_shutdown = RCV_SHUTDOWN | SEND_SHUTDOWN
   unix_peer(SA)  = NULL

这里没有同时清除：

::

   unix_peer(SB)

因此peer关系暂时变成单向：

::

   SA --X--> SB
   SB -----> SA

这是Unix socket关闭引用管理的重要中间态。

为什么B会得到完整shutdown
-------------------------

``skpair`` 非NULL且socket类型为 ``SOCK_STREAM``，所以A的release路径锁住SB并执行：

::

   SB.sk_shutdown = SHUTDOWN_MASK

上一章中SB已有 ``SEND_SHUTDOWN``；现在它进一步获得 ``RCV_SHUTDOWN``：

::

   SB.sk_shutdown:
       SEND_SHUTDOWN
       → SEND_SHUTDOWN | RCV_SHUTDOWN
       → SHUTDOWN_MASK

由于A的receive queue为空，而且本场景不是未完成accept的embryonic socket：

::

   skb == NULL
   embrion == 0

所以不会给SB设置 ``ECONNRESET``：

::

   SB.sk_err remains 0

如果A在close时仍有未读数据，release路径会把peer error设为 ``ECONNRESET``；本章固定空queue，避免引入“关闭时丢弃未读数据”的额外分支。

B怎样收到HUP语义
----------------

更新SB shutdown bits后，A的release路径调用：

::

   SB.sk_state_change(SB)
   sk_wake_async(SB, SOCK_WAKE_WAITD, POLL_HUP)

fd 7当前没有被eventpoll监视，也没有线程睡眠在B的socket wait queue，因此本场景没有实际task被唤醒。

但poll语义已经改变。若此时用户对fd 7执行poll/epoll re-poll，完整shutdown会使Unix poll报告：

::

   EPOLLIN
   EPOLLRDHUP
   EPOLLHUP

``EPOLLIN`` 允许read取得EOF； ``EPOLLRDHUP`` 表示peer不再发送； ``EPOLLHUP`` 表示该连接的通信方向已经完整结束。

B的 ``sk_state`` 并未在这里改为 ``TCP_CLOSE``：

::

   SB.sk_state remains TCP_ESTABLISHED

fd 7对应的本端socket对象仍open，只有shutdown mask已经完整关闭。

peer reference为什么需要单独下降
--------------------------------

socketpair建立时，A为了保存 ``unix_peer(SA)=SB`` 取得了SB的一份socket reference。现在A清除了自己的peer pointer，因此调用：

::

   sock_put(SB)

这下降的是A持有的peer reference，不是fd 7的file reference。

SB仍由：

* open socket file ``F7``；
* 其自身socket/inode关系；

保持存活，因此不会在本章释放。

为什么SA不能立刻析构
--------------------

``unix_release_sock`` 最后会：

::

   sock_put(SA)

这归还A由file/socket拥有的主要reference。但SB仍保存：

::

   unix_peer(SB) = SA

该pointer在socketpair建立时对应一份 ``sock_hold(SA)`` reference。因此即使fd 6、 ``F6`` 和socket A的用户拥有关系已经结束， ``SA`` 仍不能被释放。

当前对象图为：

::

   fd 7 → F7 → socket B → SB
                          |
                          +-- unix_peer(SB) → dead SA

   dead SA:
       orphan
       TCP_CLOSE
       SHUTDOWN_MASK
       unix_peer = NULL
       no file owner
       kept alive by SB peer reference

这避免SB的peer pointer在fd 7仍open时悬空。

A的receive queue怎样收尾
------------------------

``unix_release_sock`` 随后循环清空SA receive queue。本章固定queue为空，所以：

::

   skb_dequeue(&SA.sk_receive_queue) → NULL

没有skb被丢弃，没有write-memory accounting需要在此归还，也没有 ``SCM_RIGHTS`` file references需要释放。

最后安排Unix GC检查：

::

   unix_schedule_gc(NULL)

本场景没有in-flight file descriptor passing graph，GC不会改变上述peer reference事实。

socket A与F6怎样分离
-------------------

``unix_release`` 返回后设置：

::

   A->sk = NULL

``__sock_release`` 继续：

::

   A->ops  = NULL
   A->file = NULL

然后 ``sock_close`` 返回0。通用 ``__fput`` 继续释放：

* socket file ``F6``；
* sockfs pseudo dentry；
* sockfs inode中与 ``struct socket A`` 绑定的VFS对象；
* file credential与owner状态。

sockfs全局mount继续active。未命名socketpair没有磁盘socket文件需要unlink。

close怎样返回
-------------

所有同步file teardown完成后：

::

   close(6) = 0

这个返回值只说明数字fd 6的关闭和file release完成。它不要求 ``SA`` storage已经释放；SA的最后peer reference仍由SB持有。

本章结束状态
------------

* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* parent： ``TASK_RUNNING``， ``on_rq=1``、 ``on_cpu=1``；
* helper：blocked outside socket objects；
* ``close(6)`` result/RAX：0；
* fd 6：closed and unallocated；
* fd 7/8：open；
* socket file ``F6``：freed；
* socket A用户/VFS拥有关系：ended；
* ``SA``：orphan/dead、 ``TCP_CLOSE``、 ``SHUTDOWN_MASK``；
* ``unix_peer(SA)=NULL``；
* ``SA.receive_queue=empty``；
* ``SA`` storage：still alive because SB holds peer reference；
* ``SB.sk_state=TCP_ESTABLISHED``；
* ``SB.sk_shutdown=SHUTDOWN_MASK``；
* ``SB.sk_err=0``；
* ``unix_peer(SB)=SA``；
* socket file ``F7``：active；
* eventpoll ``EP``：empty， ``refcount=1``；
* no callback or epitem remains active；
* next entry：parent ``close(7)``。

关键边界
--------

#. close先撤销共享fdtable中的数字6，再进入最后 ``__fput``。
#. 显式DEL已让 ``F6.f_ep=NULL``，所以target close不再进入eventpoll慢路径。
#. socket file release经过 ``sock_close → __sock_release → unix_release``。
#. ``unix_release_sock`` 把SA设为orphan、 ``TCP_CLOSE`` 与 ``SHUTDOWN_MASK``。
#. A关闭时只清除 ``unix_peer(SA)``，不会同步清除 ``unix_peer(SB)``。
#. peer B得到完整 ``SHUTDOWN_MASK`` 与HUP语义，但其 ``sk_state`` 仍为 ``TCP_ESTABLISHED``。
#. A receive queue为空，所以B不会得到 ``ECONNRESET``。
#. A持有的SB peer reference在A close时下降。
#. SB持有的SA peer reference仍存在，因此dead SA不能立即析构。
#. ``F6`` 与sockfs VFS对象可以先释放， ``SA`` storage由独立socket引用计数控制。
#. 未命名socketpair close不产生ext4或块设备I/O。

下一入口
--------

parent将执行：

::

   close(7)

B的release会清除 ``unix_peer(SB)=SA`` 并下降最后的SA peer reference，随后B自身也结束生命周期。最后再关闭空eventpoll fd 8。

资料
----

* `Linux 7.2-rc1 net/unix/af_unix.c：unix_release、unix_release_sock与Unix socket destructor <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/unix/af_unix.c>`_
* `Linux 7.2-rc1 net/socket.c：sock_close、__sock_release、sockfs inode与socket file teardown <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/socket.c>`_
