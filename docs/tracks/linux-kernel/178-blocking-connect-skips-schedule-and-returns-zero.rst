第一百七十八章：blocking connect为什么无需真正睡眠就返回0？
=======================================================

上一章结束时，TCP三次握手已经在CPU0内核路径中完成：

::

   client:
       CS.state        = SS_CONNECTING
       C.sk_state      = TCP_ESTABLISHED
       CW.flags        = WQ_FLAG_WOKEN

   server:
       L.sk_state      = TCP_LISTEN
       H.sk_state      = TCP_ESTABLISHED
       accept head     = R
       R.sk            = H
       L.sk_ack_backlog = 1

parent从未离开CPU0，也没有调用scheduler。它仍在blocking ``connect()`` 的内核调用栈中，等待从client SYN-ACK处理和嵌套NET_RX返回。

本章只解释等待协议与系统调用收尾： ``__release_sock`` 怎样完成backlog清理， ``wait_woken`` 为什么看到提前到达的wake flag后跳过 ``schedule_timeout``，通用socket层怎样把 ``SS_CONNECTING`` 改为 ``SS_CONNECTED``，以及 ``connect()`` 最终如何向用户态返回0。server ``accept()`` 留给下一批。

嵌套NET_RX返回后怎样结束SYN-ACK处理
----------------------------------

server消费最终ACK后，执行返回链：

::

   NET_RX_SOFTIRQ returns
   → rcu_read_unlock_bh returns
   → __dev_queue_xmit returns
   → tcp_send_ack returns

``tcp_rcv_synsent_state_process`` 已经完成client建立，返回一个让上层消费SYN-ACK skb的结果。随后：

::

   tcp_rcv_state_process
   → tcp_v4_do_rcv
   → sk_backlog_rcv
   → __release_sock

原先从 ``C.sk_backlog`` 摘下的SSYNACK被释放。旧链没有第二个skb。

__release_sock怎样完成backlog accounting
---------------------------------------

``__release_sock`` 重新取得 ``C.sk_lock.slock``，检查在处理旧链期间是否有producer建立了新backlog链。本场景没有新packet，因此：

::

   C.sk_backlog.head = NULL
   C.sk_backlog.tail = NULL

最后写：

::

   C.sk_backlog.len = 0

这一步不能在处理旧链前完成，因为receive路径需要正确的backlog memory accounting。处理结束后socket backlog真正为空。

release_sock怎样释放用户ownership
---------------------------------

控制回到 ``release_sock(C)``。固定没有需要延后到 ``tcp_release_cb`` 的额外TCP工作，随后执行：

::

   sock_release_ownership(C)

把：

::

   C.sk_lock.owned : 1 → 0

如果另一个task正在等待取得C的用户锁， ``sk_lock.wq`` 会被唤醒；本场景没有竞争者。

最后：

::

   spin_unlock_bh(&C.sk_lock.slock)

第一次 ``release_sock(C)`` 返回到 ``inet_wait_for_connect``。这次调用不仅“解锁”，也已经同步完成client SYN-ACK、最终ACK、server child和accept readiness。

wait_woken为什么不会调用scheduler
--------------------------------

代码接着执行：

::

   wait_woken(&CW, TASK_INTERRUPTIBLE, timeo)

进入时：

::

   CW.flags & WQ_FLAG_WOKEN = true

这个flag来自client进入 ``TCP_ESTABLISHED`` 时的 ``sk_state_change``。 ``wait_woken`` 先写：

::

   current->state = TASK_INTERRUPTIBLE

并执行配对memory barrier，然后检查：

::

   if (!(CW.flags & WQ_FLAG_WOKEN))
       schedule_timeout(timeo)

条件为false，所以：

::

   schedule_timeout() = skipped

parent没有从runqueue移除，也没有上下文切换。随后立即恢复：

::

   current->state = TASK_RUNNING

并用 ``smp_store_mb`` 清除：

::

   CW.flags &= ~WQ_FLAG_WOKEN

这就是blocking调用可以“走过等待函数却不真正睡眠”的原因。blocking描述的是API允许等待，不保证每次一定发生调度。

为什么不能只检查TCP_ESTABLISHED而不使用wake flag
---------------------------------------------

时序可以是：

::

   add_wait_queue(CW)
   → release_sock(C)
   → backlog processing changes state to TCP_ESTABLISHED
   → wake callback runs
   → release_sock returns
   → wait_woken begins

状态变化发生在真正的wait函数之前。如果没有 ``WQ_FLAG_WOKEN`` 与memory barrier协议，task可能在条件已变化后错误进入睡眠。当前实现同时依赖：

* wait entry先加入queue；
* wake side设置 ``WQ_FLAG_WOKEN``；
* wait side在设置TASK_INTERRUPTIBLE后检查flag；
* 两侧barrier约束状态和flag的可见顺序。

所以本章不是“碰巧没有睡”，而是等待协议明确保证提前wakeup不会丢失。

重新取得socket lock后为什么循环结束
----------------------------------

``wait_woken`` 返回后执行：

::

   lock_sock(C)

此时没有其他owner，快速取得用户锁。 ``inet_wait_for_connect`` 回到while条件：

::

   (1 << C.sk_state) & (TCPF_SYN_SENT | TCPF_SYN_RECV)

当前：

::

   C.sk_state = TCP_ESTABLISHED

所以条件为false，循环结束。

随后清理等待对象：

::

   remove_wait_queue(sk_sleep(C), &CW)
   C.sk_write_pending -= writebias

本场景 ``writebias=0``，所以 ``sk_write_pending`` 保持0。

inet_wait_for_connect返回什么
----------------------------

没有真正调用 ``schedule_timeout``，原blocking timeout仍为非零值。函数返回该剩余 ``timeo``。

回到 ``__inet_stream_connect`` 后依次检查：

::

   signal_pending(current) = false
   disconnect generation   = unchanged
   C.sk_state              != TCP_CLOSE
   C.sk_err                = 0

所以不会返回 ``-EINTR``、 ``-EPIPE``、 ``-ECONNABORTED`` 或socket error。

socket API层何时变成SS_CONNECTED
--------------------------------

TCP协议层已经在第176章写入 ``TCP_ESTABLISHED``。现在通用层才执行：

::

   CS.state = SS_CONNECTED
   err = 0

两层状态最终对齐：

::

   socket API state = SS_CONNECTED
   TCP state        = TCP_ESTABLISHED

``SS_CONNECTED`` 表示后续socket API调用不再把fd 7视为正在connect； ``TCP_ESTABLISHED`` 表示传输控制块已经完成握手并可收发数据。

外层inet_stream_connect为什么还要release_sock
-------------------------------------------

``__inet_stream_connect`` 返回0时， ``lock_sock(C)`` 在等待循环末尾重新取得的用户锁仍由parent持有。外层执行：

::

   inet_stream_connect(...)
   {
       lock_sock(C)
       err = __inet_stream_connect(...)
       release_sock(C)
       return err
   }

因此还会第二次调用：

::

   release_sock(C)

此时：

::

   C.sk_backlog.tail = NULL
   no delayed handshake work
   no lock contender

它只是正常释放ownership，不再处理packet。

syscall怎样回到用户态
--------------------

返回链继续：

::

   inet_stream_connect
   → __sys_connect_file
   → __sys_connect
   → __x64_sys_connect
   → syscall_exit_to_user_mode
   → x86-64 CPL 3

用户态得到：

::

   connect(7, &server_addr, sizeof(server_addr)) = 0

fd 7仍是原先发布的blocking、close-on-exec socket file；没有创建新client fd，也没有替换 ``struct socket`` 或 ``tcp_sock``。

server为什么已经可accept却还没有fd 8
-----------------------------------

握手完成后server侧已有：

::

   L.sk_ack_backlog = 1
   accept queue head = R
   R.sk = H
   H.sk_state = TCP_ESTABLISHED

但 ``H.sk_socket=NULL``，它没有sockfs inode、file或fd。只有未来：

::

   accept4(6, ..., SOCK_CLOEXEC)

才会：

* 从accept queue取出R/H；
* 分配新的 ``struct socket``；
* 把H graft到该socket；
* 创建sockfs file；
* reserve并发布最低空闲fd 8；
* 将新socket API state设置为 ``SS_CONNECTED``。

所以 ``connect()=0`` 与server尚未调用 ``accept()`` 可以同时成立。

本章结束状态
------------

* current executor：parent；
* CPU/mode：CPU0，返回x86-64 CPL 3用户态；
* final syscall/result： ``connect(7,127.0.0.1:28080)=0``；
* parent schedule count in this connect wait：0；
* wait entry ``CW``：已从 ``sk_sleep(C)`` 删除；
* ``CW.WQ_FLAG_WOKEN``：已清除；
* client fd 7：open、blocking、close-on-exec；
* ``CS.state=SS_CONNECTED``；
* ``C.sk_state=TCP_ESTABLISHED``；
* client tuple：``127.0.0.1:40000 → 127.0.0.1:28080``；
* client ehash与bind/bind2 ownership：active；
* client retransmission tree：empty；
* client socket backlog：empty；
* client ``snd_una=snd_nxt=C_ISN+1``；
* client ``rcv_nxt=S_ISN+1``；
* server fd 6：open、blocking、close-on-exec；
* listener ``L``：``TCP_LISTEN``；
* request SYN qlen/young：0/0；
* listener ``sk_ack_backlog=1``；
* accept queue：head/tail为R；
* ``R.sk=H``，R作为accept FIFO节点存在；
* server child ``H``：``TCP_ESTABLISHED``，established ehash active；
* H bind/bind2 owner：active；
* H ``sk_socket=NULL``，无file、无fd；
* network packet backlog：empty；
* next userspace entry： ``accept4(6, ..., SOCK_CLOEXEC)``；
* lowest free fd for accepted socket：8。

关键边界
--------

#. ``__release_sock`` 的backlog消费可以在第一次 ``release_sock`` 内完成整个loopback握手。
#. client state-change发生在 ``wait_woken`` 之前， ``WQ_FLAG_WOKEN`` 防止提前wakeup丢失。
#. ``wait_woken`` 可以设置TASK_INTERRUPTIBLE后立即恢复TASK_RUNNING，而不调用scheduler。
#. blocking socket不等于每次blocking syscall都必须上下文切换。
#. waiting loop重新加锁并重读 ``C.sk_state``，不会只相信wake event。
#. TCP ``TCP_ESTABLISHED`` 先于socket API ``SS_CONNECTED``。
#. 外层第二次 ``release_sock`` 释放等待循环重新取得的用户锁。
#. ``connect()=0`` 只说明client主动建立成功，不说明server应用已经执行accept。
#. server child在accept queue中已经是 ``TCP_ESTABLISHED``，但没有用户可见fd。
#. R从SYN request身份转为accept queue节点；此时不能把它描述为已经释放。
#. listener继续保留fd 6和 ``TCP_LISTEN``，可接受后续连接。
#. 下一批从 ``accept4`` 的queue removal、socket graft与fd 8发布开始。

下一入口
--------

::

   accept4(6, user_addr, user_addrlen, SOCK_CLOEXEC)
   → resolve listener L
   → remove R/H from accept queue
   → L.sk_ack_backlog 1 → 0
   → allocate accepted struct socket
   → graft H to accepted socket
   → create blocking close-on-exec sockfs file
   → publish fd 8
   → copy peer address 127.0.0.1:40000
   → return 8

资料
----

* `Linux 7.2-rc1 net/core/sock.c：__release_sock与release_sock收尾 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/core/sock.c>`_
* `Linux 7.2-rc1 kernel/sched/wait.c：wait_woken与woken_wake_function <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/wait.c>`_
* `Linux 7.2-rc1 net/ipv4/af_inet.c：inet_wait_for_connect与SS_CONNECTED提交 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/af_inet.c>`_
* `Linux 7.2-rc1 net/ipv4/inet_connection_sock.c：accept queue保存R/H <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/inet_connection_sock.c>`_
