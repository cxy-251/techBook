第141章：Socket API 与内核 Socket 对象
======================================

核心知识点
----------

Socket 是 fd 背后的协议状态机
   稳定对象链是 fd → ``struct file`` → ``struct socket`` → ``struct sock`` → TCP、UDP 等协议私有状态。整数 fd 只是进程局部句柄。

``struct socket`` 与 ``struct sock`` 分工不同
   ``struct socket`` 承接 VFS/BSD Socket API，``struct sock`` 保存协议状态、队列、内存记账、错误、锁和回调。前者通过 ``socket->sk`` 关联后者。

Socket API 与协议实现分层分派
   ``proto_ops`` 承接 bind、connect、accept、sendmsg、recvmsg 等用户语义；协议内部再通过 ``struct proto`` 和私有对象推进 TCP/UDP 状态。

创建端点不等于建立连接
   ``socket()`` 只创建通信端点。``bind`` 绑定本地身份，``listen`` 建立被动打开语义，``accept`` 创建新的连接 socket，``connect`` 推进主动建立状态。

TCP 与 UDP 的数据边界不同
   TCP 向用户提供有序字节流，单次 send 与 recv 不保持边界；UDP 保留数据报边界，接收缓冲不足时可能截断一个报文。

发送成功只表示本地接收数据
   TCP/UDP 的 send 返回表示本地协议栈接受了相应字节或报文，不表示数据已离开网卡、被远端确认或被远端应用读取。

队列与内存记账形成背压
   接收队列、协议发送队列、重传状态和 socket buffer 限额共同决定读写是否推进。``SO_SNDBUF``、``SO_RCVBUF`` 不是纯 payload 字节容量。

Poll/Epoll 是就绪模型
   Readiness 表示操作当前可能推进，不表示某次 I/O 已完成。非阻塞事件循环必须处理短 I/O、EOF、错误，并持续操作到 ``-EAGAIN``。

唤醒之后必须重新检查状态
   数据到达、发送空间释放或错误发生时，协议通过等待队列和 ``sk_data_ready``、``sk_write_space`` 等回调唤醒任务；并发消费者可能已改变条件。

关闭 fd 与协议结束不是同一时刻
   ``shutdown`` 改变一个或两个传输方向；``close`` 只撤销一个 fd 引用。复制 fd、异步工作、协议定时器和 TIME-WAIT 状态可能继续延长相关对象或协议状态。

Network Namespace 决定网络视图
   Socket 创建时关联 ``struct net``，其端口、路由、设备、Netfilter 和协议表都属于对应网络命名空间。

关键路径
--------

创建 Socket：

::

   socket(family, type, protocol)
   → 选择 network namespace 与协议族
   → 分配 struct socket
   → 设置 proto_ops
   → 分配 struct sock 与协议私有状态
   → 创建 struct file
   → 安装进程 fd

非阻塞 Connect：

::

   connect
   → 协议发送建连请求
   → 返回 -EINPROGRESS
   → epoll 报告可写或错误
   → getsockopt(SO_ERROR)
   → 确认成功或取得最终错误

阻塞接收：

::

   recv 检查接收队列
   → 无数据且允许等待
   → 登记 socket 等待队列并睡眠
   → 协议入队数据、EOF 或错误
   → 回调唤醒任务
   → 重新检查状态
   → 返回数据、0 或负 errno

关闭 Socket：

::

   close(fd)
   → 从 fdtable 移除表项
   → 递减 struct file 引用
   → 最后引用触发 socket release
   → 协议撤销哈希、队列和定时器
   → 剩余协议引用结束
   → 最终释放对象

概念辨析
--------

* ``struct socket`` 与 ``struct sock``：前者是 BSD/VFS 接口对象；后者是协议核心状态对象。
* Readiness 与 Completion：poll/epoll 报告可能推进；它不表示某个 send/recv 请求已完成。
* Send 返回与远端交付：前者表示本地协议接受；后者还依赖网络、ACK 和远端应用。
* TCP 字节流与 UDP 数据报：TCP 不保留调用边界；UDP 保留单个报文边界。
* Close 与 TIME-WAIT：Close 结束 fd 使用；TIME-WAIT 是协议为迟到 segment 保留的状态。
* ``O_NONBLOCK`` 与 ``MSG_DONTWAIT``：前者作用于打开实例；后者只作用于当前调用。

本章结论
--------

Socket 是文件句柄、协议对象、队列、内存记账和等待唤醒组成的状态机。理解网络系统调用必须沿 fd、``struct socket``、``struct sock`` 和协议私有状态逐层追踪。