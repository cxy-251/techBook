第145章：TCP/IP 状态、拥塞与 Packet 诊断
========================================

本章必须记住
------------

#. TCP 是有状态、可靠、有序的双向字节流协议；每个连接由 socket 状态、序列空间、窗口、定时器和队列共同推进。
#. TCP socket state 表达连接生命周期，不直接表达当前吞吐、队列长度或 packet 所在设备位置。
#. 常见状态包括 LISTEN、SYN-SENT、SYN-RECV、ESTABLISHED、FIN-WAIT-1/2、CLOSE-WAIT、LAST-ACK、TIME-WAIT、CLOSED。
#. 主动打开通常从 CLOSED → SYN-SENT → ESTABLISHED；被动打开从 LISTEN → SYN-RECV → ESTABLISHED。
#. 本端先关闭通常经过 FIN-WAIT；对端先发送 FIN 后本端进入 CLOSE-WAIT，等待本地应用关闭。
#. 大量 CLOSE-WAIT 通常说明应用未及时 close 已收到 EOF 的连接，不应首先调整 TCP 内核参数。
#. TIME-WAIT 表示主动关闭侧保留四元组与迟到 segment 处理状态，不表示原应用 fd 仍然打开。
#. 大量 TIME-WAIT 需要结合短连接速率、主动关闭方向、端口空间和连接复用判断，不能自动视为泄漏。
#. 大量 SYN-SENT 表示主动连接尚未建立，可能来自路由、邻居、防火墙、丢包、远端未监听或回包路径问题。
#. 大量 SYN-RECV 表示服务端握手尚未完成，需要检查 SYN backlog、ACK 回包、负载和攻击防护。
#. LISTEN socket 与已建立连接 socket 是不同对象；accept 返回新的连接 fd。
#. TCP 半连接队列与 accept queue 不同，backlog 参数还受系统上限和实现约束。
#. ``struct sock`` 保存通用 socket 状态，``struct inet_connection_sock`` 承载连接型协议定时器等状态，``struct tcp_sock`` 保存 TCP 私有序列号、窗口和重传状态。
#. 精确结构嵌入和字段名随版本演进，稳定对象关系是通用 socket → 连接型协议 → TCP 私有状态。
#. TCP 发送数据按字节编号，ACK 表示累计确认到某个序列位置；SACK 可额外描述已收到的不连续区间。
#. 发送队列、重传队列和“网络中在途数据”不是同一个集合。
#. 用户 send 成功表示本地 TCP 接受字节，不表示字节已经发出、收到 ACK 或被远端应用读取。
#. TCP 接收成功返回有序字节流，packet 和 skb 边界通常不会暴露给应用。
#. 吞吐受多个许可共同限制：对端接收窗口、本地拥塞窗口、发送队列、pacing、qdisc/设备能力和应用供数速度。
#. 对端 advertised receive window 是流量控制：防止发送端超过接收方缓存与应用消费能力。
#. Congestion window（cwnd）是发送端对网络路径容量与拥塞状态的控制，不代表接收端 buffer 大小。
#. 实际可发送在途量通常受 ``min(cwnd, advertised receive window)`` 等协议约束，并受已在途字节扣减。
#. Receive window 与 congestion window 解决不同问题，不能把“窗口小”不加区分地归因于网络拥塞。
#. 对端窗口变为零时，发送端停止推进新数据，并使用 persist/zero-window probe 等机制探测窗口恢复。
#. 零窗口常说明对端应用读取慢、接收 buffer 压力或接收路径停顿，不等于链路丢包。
#. cwnd 下降通常由拥塞控制根据丢包、ECN、ACK、RTT 或算法状态调整。
#. ``ssthresh`` 把 slow start 与 congestion avoidance 等阶段联系起来，精确算法由选定 congestion control 决定。
#. 不同拥塞算法使用不同带宽/RTT/丢包模型，不能只比较算法名称推断性能。
#. ``tcp_congestion_control`` 影响新建连接默认算法，已有连接可能继续使用创建时的算法或 socket 专属设置。
#. Pacing 控制 packet 发送节奏，避免一次性突发；它与 cwnd 共同限制发送，但角色不同。
#. MSS 表示 TCP segment payload 尺度，通常由 MTU、选项和路径约束推导；它不是链路 MTU 本身。
#. Window scaling 在握手时协商，决定 16 位窗口字段可表达的实际接收窗口范围。
#. 未协商 window scaling 的现有连接无法通过运行中调大 sysctl 自动获得新的扩展能力。
#. Socket send/receive buffer 自动调优和全局 tcp memory pressure 会改变窗口与排队能力。
#. 增大 ``tcp_rmem``/``tcp_wmem`` 不能修复丢包、CPU 过载、qdisc 拥塞或应用不读取。
#. 过大 buffer 会增加内存占用和排队延迟，形成 bufferbloat。
#. RTT 是发送到确认之间的路径时间样本；RTO 是基于 RTT 估计和方差计算的重传超时，二者不是同一数值。
#. RTO 触发是保守的丢失恢复路径，通常比基于重复 ACK/SACK/时间排序的快速恢复更慢。
#. RTO 会重传未确认数据，并通常退避计时与降低发送许可，形成明显延迟尖峰。
#. 重复 ACK、SACK block、RACK 等机制可在 RTO 前推断部分 segment 丢失，精确启用与实现具有版本差异。
#. SACK 告诉发送端哪些非连续字节块已到达，减少不必要的整体重传。
#. SACK 不改变累计 ACK 的基本语义，发送端仍需维护重传记分和序列空间。
#. Fast retransmit/fast recovery 根据 ACK 反馈快速重传疑似丢失 segment，并调整拥塞状态。
#. Tail Loss Probe 等机制用于更早探测尾部丢包，精确算法和 sysctl 已随内核演进。
#. RACK 主要利用时间排序和 ACK/SACK 信息推断丢失，不能简单等同于“收到三个重复 ACK”。
#. Packet 重排可能被误判为丢失，TCP 会通过 reordering 相关状态和算法尽量适应。
#. 丢包恢复会产生重传和重复数据，但 TCP 向应用仍提供有序字节流。
#. 接收端对重复 segment 通常确认并丢弃重复字节，不会把重复数据交给应用。
#. ACK 丢失不一定导致数据重传，因为后续累计 ACK 可以覆盖已收到数据。
#. Data packet 丢失与 ACK packet 丢失在抓包上表现不同，诊断需同时观察双向流。
#. Retransmission 是发送端根据自身状态作出的判断；抓包工具的“retransmission”标签是分析器推断，不是内核直接字段。
#. 抓包点只看到该位置的 packet；offload、namespace、隧道、NAT 和不对称路由会改变可见形态。
#. 发送侧抓到大 packet 可能是 GSO/TSO skb，wire 上会被分段；接收侧大 packet 可能来自 GRO。
#. 要诊断真实 segment，应选择合适抓取位置或临时控制 offload，并记录改变带来的扰动。
#. SYN、SYN-ACK、ACK 的缺失方向能区分请求未到、回复未回或客户端最终 ACK 未到。
#. RST 表示连接被明确复位，来源可以是目标端口未监听、协议状态不匹配、应用 abort 或中间设备。
#. FIN 表示有序关闭一个发送方向；FIN 后仍可接收反方向数据，直到双方关闭。
#. EOF 与 RST 不同：EOF 通常来自正常 FIN；RST 常使应用收到连接重置错误并丢失未读语义。
#. Keepalive、user timeout、application heartbeat 和 TCP retransmission timeout 是不同存活/失败检测机制。
#. TCP keepalive 通常在连接长时间空闲后探测 peer，不是低延迟业务心跳的默认替代。
#. ``TCP_USER_TIMEOUT`` 等 socket 选项控制未确认数据可持续多久，语义和可用范围应按版本/API 验证。
#. ``ss -tan`` 用于观察连接状态和 Recv-Q/Send-Q；队列字段含义随监听/连接状态不同。
#. 已建立连接的 Recv-Q 常表示应用尚未读取的数据；Send-Q 常表示尚未确认或未推进的数据视图，不能直接当作 qdisc backlog。
#. LISTEN 行的 Recv-Q/Send-Q 常表达当前/最大 accept backlog 等不同语义，必须结合工具文档解释。
#. ``ss -tin`` 可显示 RTT、RTO、cwnd、ssthresh、MSS、pacing、bytes_acked、bytes_retrans 等内部信息，实际字段随内核和 iproute2 版本变化。
#. 单次 ``ss`` 快照无法证明趋势，应周期采样并关联同一五元组、socket inode 或 cookie。
#. RTT 高但无重传可能来自路径传播、排队或应用 ACK 行为；重传高但 RTT 低可能来自局部丢包/乱序。
#. cwnd 大但吞吐低时，应检查 receive window、应用供数、pacing、qdisc、CPU 和设备。
#. receive window 大但发送停顿时，应检查 cwnd、loss recovery、send queue、route/neighbor 和本地排队。
#. Send-Q 持续增长说明应用产生数据快于后续路径消化，瓶颈可能在 TCP、qdisc、设备或远端反馈。
#. Recv-Q 持续增长说明内核收到数据快于应用读取，可能导致窗口收缩或 socket drop。
#. ``nstat``/``/proc/net/snmp``/``netstat -s`` 可观察协议累计计数，例如重传、失败、reset、listen overflow 等。
#. 聚合计数不能直接归因到某个连接，需要与时间窗口、namespace 和抓包关联。
#. ``/proc/sys/net/ipv4/*`` 展示系统策略与默认值，不是当前每个 socket 的实时状态。
#. 修改 sysctl 可能只影响新连接或特定路径，诊断前应先记录原值并避免同时改多个参数。
#. ``tcpdump`` 用于观察 packet 时间线、flags、seq/ack、window、SACK、重传和 ICMP。
#. 相对序列号便于阅读，但跨抓包点或分析工具对齐时可能需要绝对字段与五元组。
#. 抓包显示 ACK 延迟时，还需区分接收端 delayed ACK、CPU 调度、GRO、应用读取和路径延迟。
#. 抓包未看到 packet 不表示应用未发送：packet 可能仍在 socket/qdisc，或被更早规则/XDP 丢弃。
#. 抓包看到 packet 不表示远端应用收到：后续链路、远端协议和应用仍可能失败。
#. Ftrace/tracepoint 可观察 TCP 状态变化、重传、probe、socket 和 netif 路径，事件名与字段随版本变化。
#. eBPF 可按 socket cookie/五元组关联状态，但程序必须处理对象生命周期、namespace 和采样开销。
#. Perf 用于定位 TCP input/output、checksum、copy、qdisc、softirq 和锁竞争 CPU，不能单独证明网络丢包位置。
#. ``dropwatch``/skb drop reason 等机制可补充本机 drop 位置，支持程度和枚举随版本演进。
#. 连接建立慢应先拆成 DNS、connect syscall、SYN 发出、SYN-ACK 返回、最终 ACK 和应用 accept。
#. DNS 不属于 TCP 握手；把域名解析时间算入 connect 会混淆问题层级。
#. 服务端 listen queue 溢出与应用处理建立后连接慢是不同故障。
#. 吞吐低应先判断应用限速、接收窗口、cwnd/loss、RTT、qdisc、设备和 CPU 哪一项在限制。
#. 周期性卡顿应检查 RTO/backoff、zero-window、GC/CPU stall、qdisc burst 和设备 reset。
#. 单流慢、多流总吞吐正常常指向单流 cwnd/RTT、窗口或 CPU locality；所有流都慢更可能是共享链路/设备/CPU。
#. 只在跨地域慢时应计算带宽时延积，确认 cwnd/receive window 是否足以填满路径。
#. 只在高并发建连失败时应检查端口空间、listen backlog、SYN cookies、conntrack 和资源限制。
#. NAT/conntrack 使抓包地址与 socket 地址视图可能不同，应在转换前后抓取并关联 flow。
#. 不对称路由可能让两个方向经过不同主机/规则，单点抓包无法构成完整连接证据。
#. PMTU 黑洞常表现为握手成功、小包正常、大包停顿；应检查 ICMP、MSS、MTU 和隧道开销。
#. ECN、DSACK、F-RTO、RACK 等机制具有配置和版本边界，不能从一个字段名称推出完整算法状态。
#. TCP 调优必须通过同一 workload 的吞吐、P99、重传、RTT、CPU、队列和内存对照验证。
#. 随意关闭 SACK、timestamps、window scaling 或修改重传参数可能降低鲁棒性，应有明确证据和回滚。
#. 生产诊断应优先只读观测；抓包、trace 和高频采样也会增加 CPU/存储开销。
#. 稳定诊断顺序是：连接状态 → Socket 队列 → RTT/RTO/窗口/cwnd → 双向 packet → 本机 drop/queue → route/neighbor/device → 对端应用。

必背路径
--------

主动建立连接：

::

   connect
   → socket 进入 SYN-SENT
   → 路由、Netfilter、neighbor、设备发送 SYN
   → 服务端 LISTEN 收到 SYN
   → 服务端 SYN-RECV 并发送 SYN-ACK
   → 客户端收到 SYN-ACK
   → 更新序列与窗口状态并发送 ACK
   → 双方进入 ESTABLISHED
   → 非阻塞客户端通过 SO_ERROR 确认结果

发送许可：

::

   应用数据进入 Socket Send Queue
   → 检查对端 advertised receive window
   → 检查 congestion window
   → 扣除当前 bytes in flight
   → 检查 pacing 与协议发送条件
   → 构造/发送 segment
   → ACK/SACK 到达
   → 更新 RTT、已确认字节、cwnd 和重传状态
   → 释放发送内存并唤醒应用

丢包恢复：

::

   Segment 发出并进入未确认状态
   → ACK/SACK 反馈出现缺口或时间超序
   → 快速恢复/RACK 等判断丢失
   → 重传疑似丢失范围
   → 调整 cwnd / ssthresh
   → 若反馈不足且 RTO 到期
   → RTO 重传并退避
   → 后续 ACK 重新推进发送状态

诊断吞吐低：

::

   ss 确认 ESTABLISHED 与 Send-Q/Recv-Q
   → 读取 RTT、RTO、cwnd、ssthresh、pacing
   → 抓包确认对端窗口、SACK、重传和 ACK 节奏
   → 判断 flow control 或 congestion control
   → 检查 qdisc、设备、CPU 和 drop
   → 对端同步检查应用读取和 Socket 状态
   → 用固定 workload 对照验证

诊断连接建立慢：

::

   分离 DNS 与 connect 时间
   → 确认 SYN 是否离开本机
   → 确认 SYN 是否到达服务端
   → 确认 SYN-ACK 是否返回
   → 检查客户端最终 ACK
   → 检查服务端 SYN/accept queue
   → 检查 conntrack/NAT/防火墙与 reply route
   → 定位丢失或排队的第一个阶段

必须区分
--------

TCP State 与 Conntrack State
   TCP state 属于 socket 协议生命周期；conntrack state 属于网络规则的 flow 跟踪。

Receive Window 与 Congestion Window
   前者保护接收端缓存；后者控制发送端对网络的在途负载。

RTT 与 RTO
   RTT 是路径时间样本；RTO 是基于估计与方差形成的超时阈值。

Send 返回与 ACK 确认
   Send 表示本地接受字节；ACK 才表示远端 TCP 已确认对应序列范围。

抓包推断与内核事实
   分析器标记的重传/乱序是基于抓取点数据推断，需要与 Socket 状态和双向证据验证。

一句话结论
----------

TCP 诊断必须把连接状态、接收窗口、拥塞窗口、在途数据、ACK/SACK、重传定时器和本机各层队列放到同一时间线上，才能判断连接究竟受应用、主机还是网络路径限制。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 29，Socket Layer, sk_buff, Routing, Netfilter, and TCP IP Stack；
* AIBook 章节：Chapter 145，TCP IP State, Congestion, and Packet Diagnostics；
* 源文件：``docs/LinuxK/Part_29_Socket_Layer_sk_buff_Routing_Netfilter_and_TCP_IP_Stack/Chapter_145_TCP_IP_State_Congestion_and_Packet_Diagnostics.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_29_Socket_Layer_sk_buff_Routing_Netfilter_and_TCP_IP_Stack/Chapter_145_TCP_IP_State_Congestion_and_Packet_Diagnostics.md>`_。