第141章：Socket API 与内核 Socket 对象
======================================

本章必须记住
------------

#. 用户态看到的 socket 是整数 fd；内核中它对应一组分层对象，而不是一个单独结构体。
#. 稳定对象链是：fd → ``struct file`` → ``struct socket`` → ``struct sock`` → TCP/UDP 等协议私有状态。
#. fd 是进程局部句柄；``struct file`` 是打开实例；``struct socket`` 是 BSD socket/VFS 接口对象；``struct sock`` 是网络协议核心对象。
#. Socket fd 进入 VFS，因此能复用 ``close``、``fcntl``、``poll``、``epoll`` 和文件引用生命周期。
#. ``file->private_data`` 通常关联 ``struct socket``，``socket->sk`` 指向 ``struct sock``。
#. ``struct socket`` 主要保存 socket 类型、状态、操作表、文件对象、等待队列和 ``sk`` 指针。
#. ``struct sock`` 主要保存协议状态、收发队列、内存记账、错误、锁、回调和网络命名空间关系。
#. TCP、UDP、UNIX、Netlink 等协议在 ``struct sock`` 基础上扩展各自私有状态。
#. ``socket()`` 创建的是尚未完成 bind/connect/listen 的通信端点，不是已经建立的 TCP 连接。
#. ``socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)`` 先选择协议族、类型和协议实现，再创建对象并安装 fd。
#. 创建路径会处理 ``SOCK_NONBLOCK``、``SOCK_CLOEXEC`` 等嵌入 type 参数的文件标志。
#. ``__sock_create()`` 一类入口根据 network namespace、family、type 和 protocol 选择协议族创建函数。
#. 对 ``AF_INET``，协议族创建逻辑会设置 ``socket->ops`` 并分配相应 ``struct sock``。
#. ``socket->ops`` 指向 ``struct proto_ops``，面向 bind、connect、accept、sendmsg、recvmsg、poll 等 BSD 操作。
#. ``sk->sk_prot`` 一类协议实现指针面向协议内部的发送、接收、分配、回收和哈希等操作。
#. ``proto_ops`` 与 ``struct proto`` 是不同分派层：前者承接 Socket API，后者承接协议核心实现。
#. ``bind()`` 绑定本地地址或名字；它不自动进入监听状态，也不自动建立远端连接。
#. ``listen()`` 把连接型 socket 转成被动打开端点，并建立握手/accept 队列语义。
#. ``accept()`` 返回新的连接 socket；监听 socket 继续存在并接收后续连接。
#. ``connect()`` 对阻塞 socket 可等待建立结果；对非阻塞 socket 常返回 ``-EINPROGRESS``。
#. 非阻塞 connect 的最终结果应通过可写事件和 ``SO_ERROR`` 等接口确认，不能只把一次可写当成连接成功。
#. ``send``/``recv`` 最终通常统一到 ``sendmsg``/``recvmsg`` 形态，以承载 iovec、控制消息、地址和 flags。
#. Socket 系统调用层负责用户参数复制、fd lookup、安全检查和协议操作分派。
#. TCP 序列号、拥塞控制、重传和窗口不在通用系统调用层完成，而在协议私有路径中完成。
#. UDP 保留报文边界；TCP 向用户提供有序字节流，单次 send 与单次 recv 不保持一一对应。
#. ``SOCK_STREAM`` 的一次 ``recv`` 可以返回部分字节；返回 0 通常表示对端已完成有序关闭且接收队列已无数据。
#. ``SOCK_DGRAM`` 的接收以数据报为单位，buffer 太小时可能截断，具体 flags 决定结果呈现。
#. ``struct sock`` 中的 ``sk_receive_queue`` 等队列保存协议已接收但尚未被应用消费的数据。
#. 发送路径可能使用协议专用 write queue、retransmission queue 和 backlog，不能只用一个“发送队列”概括 TCP。
#. ``sk_sndbuf``、``sk_rcvbuf`` 表示 socket 级内存限额，不等同于当前队列中纯 payload 字节数。
#. 网络内存记账通常包含 skb 元数据、分配粒度、协议开销和预留，因此 ``SO_SNDBUF`` 与应用可排队 payload 不必相等。
#. 应用 send 成功表示数据已被本地协议栈接受，不表示已经发到链路、被远端接收或被远端应用读取。
#. TCP send buffer 满时，阻塞写会等待空间；非阻塞写通常返回部分字节或 ``-EAGAIN``。
#. 可写事件表示当前可能有发送空间或 connect 结果待取，不保证任意长度 write 都能完整成功。
#. 可读事件可能来自数据、EOF、监听队列、错误队列或状态变化，必须结合 socket 类型和操作结果解释。
#. ``poll``/``epoll`` 是 readiness 模型：它报告继续执行操作可能有进展，不是某次 I/O 已经完成的 completion 模型。
#. Readiness 到达后仍必须循环执行非阻塞 read/write，直到 ``-EAGAIN`` 或业务条件结束。
#. Edge-triggered epoll 下若未排空当前可处理状态，后续可能没有新的边沿通知。
#. Level-triggered epoll 在条件仍成立时会重复报告，仍不能代替正确的读写循环。
#. Socket 等待通过等待队列和 ``sk_data_ready``、``sk_write_space``、``sk_error_report`` 等回调连接协议事件与任务唤醒。
#. 数据进入接收队列后，协议路径更新状态并唤醒睡眠 recv 或 poll/epoll 等待者。
#. 发送内存释放后，协议路径可能调用 write-space 回调，唤醒等待可写的任务。
#. 唤醒只表示条件可能变化；任务真正运行时状态可能已被其它线程消费，因此必须重新检查。
#. 同一个 socket 被多个线程并发读写时，协议和 socket lock 保护内核状态，但应用消息边界与业务顺序仍需自行定义。
#. ``SO_RCVTIMEO``、``SO_SNDTIMEO`` 影响阻塞等待上限，不改变 TCP 的网络重传和 RTO 定时器。
#. ``MSG_DONTWAIT`` 是单次操作级非阻塞标志；``O_NONBLOCK`` 是打开实例级文件状态标志。
#. ``MSG_WAITALL`` 只是尽量等待请求长度，信号、EOF、错误和协议条件仍可导致短返回。
#. ``MSG_PEEK`` 读取而不消费接收数据，会影响后续队列压力和应用状态机。
#. ``shutdown(SHUT_WR)`` 停止本端后续发送并推动协议半关闭；它不等于立即销毁 socket。
#. ``close(fd)`` 移除一个 fd 引用；复制 fd、异步请求或内核其它引用可能继续保留 ``struct file`` 和 socket 对象。
#. Socket release 需要撤销协议哈希、队列、定时器和引用，最终释放时间不一定等于用户 close 返回时刻。
#. TCP 的 TIME-WAIT 通常由独立的轻量状态对象继续存在，不表示原应用 fd 仍打开。
#. ``SO_LINGER`` 可以改变 close 时阻塞和未发送数据处理，但不能把应用 close 简化成远端确认事务。
#. 异步错误可能写入 ``sk_err`` 或 error queue，并在后续 socket 操作、poll 或 ``SO_ERROR`` 中报告。
#. UDP/原始 socket 的 ICMP 错误、TCP connect 错误和本地发送错误具有不同传播路径。
#. 网络命名空间隔离 socket 所见的协议栈实例、端口、路由、Netfilter 和设备视图。
#. Socket 创建时关联的 ``struct net`` 决定后续查找和协议状态所在 namespace。
#. 同一地址和端口在不同 network namespace 中可以由不同 socket 使用。
#. ``SO_REUSEADDR``、``SO_REUSEPORT`` 改变 bind 冲突和分流规则，二者语义不同且受协议、状态和平台版本影响。
#. 监听 socket 的 SYN 队列、accept 队列和用户态 backlog 参数不是同一概念。
#. ``listen(backlog)`` 的值还会受系统上限和协议实现约束，不能直接等同于可容纳的所有半连接数量。
#. 大量 ``SYN-RECV``、accept queue 满和应用 accept 慢属于不同问题，需要分别观察。
#. Socket buffer 调优必须与 RTT、带宽、应用读取速度、拥塞窗口和全局网络内存压力一起判断。
#. 无限增大 buffer 会增加内存占用和排队延迟，不自动提高有效吞吐。
#. Socket memory pressure 可让协议收缩缓存、拒绝分配或提前丢包，影响读写 readiness 和吞吐。
#. ``ss`` 能显示 socket 状态、队列和部分协议内部信息；它是运行态视图，不是单次 packet 路径证明。
#. ``/proc/net/*`` 通常是当前 network namespace 的协议表视图，格式和字段具有版本边界。
#. ``strace`` 能观察 fd、flags、返回值和 errno，不能解释 skb、路由、拥塞窗口或设备排队。
#. Packet 抓包显示线上或抓取点看到的报文，不直接展示用户 socket 队列、未发送数据和应用调度延迟。
#. Ftrace/eBPF 可连接系统调用、socket、TCP 和网络核心事件，但事件名与字段随版本变化。
#. 稳定源码阅读顺序是：syscall → fd/file → ``struct socket`` → ``proto_ops`` → ``struct sock`` → 协议私有状态 → 队列/唤醒/释放。

必背路径
--------

创建 Socket：

::

   socket(family, type, protocol)
   → 处理 NONBLOCK / CLOEXEC 标志
   → __sock_create(net, family, type, protocol)
   → 分配 struct socket
   → 协议族 create
   → 设置 socket->ops
   → 分配并初始化 struct sock
   → 创建 struct file
   → 安装 fd

发送数据：

::

   send / sendmsg
   → fd lookup 得到 struct socket
   → socket->ops->sendmsg
   → 协议检查状态与发送内存
   → 从用户数据构造协议发送单元 / skb
   → 加入协议队列并推进输出路径
   → 返回已接受字节数或错误
   → 后续路由、qdisc、驱动和 ACK 独立推进

阻塞接收：

::

   recv / recvmsg
   → 检查协议接收队列
   → 有数据则复制/搬运到用户 buffer
   → 无数据且仍可等待
   → 把任务加入 socket 等待队列
   → 协议数据到达或状态变化
   → data_ready / error 回调唤醒
   → 重新检查队列与状态
   → 返回数据、EOF 或错误

非阻塞事件循环：

::

   fd 设置 O_NONBLOCK
   → epoll 等待 readiness
   → 收到 readable / writable / error
   → 循环 recv/send
   → 处理短 I/O、EOF 和 SO_ERROR
   → 直到 EAGAIN
   → 更新业务状态并继续等待

关闭 Socket：

::

   close(fd)
   → 从进程 fdtable 移除表项
   → file 引用减少
   → 最后 file 引用触发 socket release
   → 协议停止新操作并处理队列/定时器
   → 撤销绑定与哈希关系
   → 等待剩余协议引用
   → 最终释放对象

必须区分
--------

* ``struct socket`` 与 ``struct sock``：前者承接 BSD/VFS 操作；后者承载协议状态、队列、内存与回调。
* Readiness 与 Completion：Poll/epoll 表示操作可能推进；不表示某次 send/recv 请求已经完成。
* Send 返回与远端接收：Send 通常只表示本地协议栈接受数据；远端交付还要经过网络、ACK 和应用读取。
* Socket Buffer 大小与 Payload 字节：Buffer 记账包含协议和分配开销，不等于纯用户数据容量。
* Close fd 与协议状态结束：Fd 引用结束后，TCP 状态、异步工作和其它引用仍可能继续存在。

一句话结论
----------

Socket 是由 fd 暴露的协议状态机：``struct socket`` 连接 VFS 与 BSD 操作，``struct sock`` 连接队列、内存记账、等待唤醒和具体 TCP/UDP 状态。
