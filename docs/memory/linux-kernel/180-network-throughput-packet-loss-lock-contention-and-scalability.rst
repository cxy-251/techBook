第180章：网络吞吐、丢包、锁争用与可扩展性
==========================================

本章必须记住
------------

#. 网络性能调查必须把包路径按 NIC、Driver、IRQ、NAPI、Protocol Stack、qdisc、Socket 和 Application 分层。
#. 吞吐不足表示某一阶段服务率低于输入率，结果会表现为 Queue 增长、Drop、Retransmit 或 Tail Latency。
#. CPU 总利用率有余量不表示网络路径有余量；单 RX Queue、单 IRQ CPU、单 Flow 或单锁可先饱和。
#. 接收主线是 NIC RX Queue → IRQ → NAPI Poll → ``sk_buff`` → IP/TCP/UDP → Socket Receive Queue → Application。
#. 发送主线是 Application → Socket Send Queue → TCP/IP → qdisc → Netdev TX Queue → Driver Ring → NIC。
#. 每个阶段都有自己的 Queue、所有权、Drop Counter 和 Completion 边界。
#. NIC Ring Overflow 说明设备或驱动附近来不及回收/补充 Buffer，不能归因于应用 Socket Buffer。
#. NAPI Budget 耗尽说明一次 Poll 达到处理上限，不自动等于 Packet 已丢弃。
#. Softnet Backlog 压力表示包已进入 CPU 网络处理路径，但该 CPU 服务率不足或预算受限。
#. Socket Receive Queue 堆积通常说明应用消费慢、线程调度不足或接收 Buffer 已接近上限。
#. qdisc Backlog 属于发送调度层，不等于 Driver TX Ring 已满。
#. TCP Send Queue 堆积可来自对端窗口、拥塞控制、qdisc、网络丢包或应用写入速度过高。
#. ``sk_buff`` 是网络 Packet 元数据与数据引用对象，经过多层 Queue 时所有权会变化。
#. Packet 进入下一层后，上层不能继续按原所有权释放或修改它。
#. RX 和 TX Offload 会改变 Packet 在抓包、计数和 CPU 上呈现的大小与数量。
#. GRO 可在接收侧聚合多个 Packet；GSO/TSO 可让大 ``skb`` 在后续软件或硬件分段。
#. 抓包看到大 Packet 不自动说明线上发送了超 MTU Frame。
#. RSS 使用 NIC Hash 把 Flow 分配到硬件 RX Queue 和对应 IRQ。
#. RPS 在软件层把接收处理转移到其它 CPU；RFS 进一步尝试对齐应用消费 CPU。
#. XPS 影响发送 Queue/CPU 选择；这些机制解决不同阶段的负载分布。
#. 增加 RX/TX Queue 数量只有在 IRQ、NAPI、Worker、NUMA 和设备能力共同支持时才会增加并行度。
#. Queue 数量超过有效 CPU、MSI-X Vector、设备 Engine 或应用分片后，不会线性提高吞吐。
#. IRQ Affinity 决定硬件事件主要由哪些 CPU 接收。
#. RPS/RFS 可分散 Softirq，但会增加 IPI、Cache Miss 和跨 CPU ``skb`` 移动。
#. RSS Queue 应尽量与 NAPI CPU、Application Worker 和 NIC NUMA Node 对齐。
#. 单 Queue 热点可使一个 CPU 的 Softirq 饱和，而其它 CPU 仍空闲。
#. 单大 Flow 通常只命中一个 RSS Hash/Queue，增加 Queue 数不一定能拆分单连接处理。
#. 多 Flow 扩展性依赖 Hash 分布、连接数、协议路径和应用 Sharding。
#. ``/proc/interrupts`` 用于观察 IRQ/Queue CPU 分布，不能单独说明每个中断处理了多少 Packet。
#. ``/proc/net/softnet_stat`` 是 Per-CPU 软网络统计，列含义具有版本边界，必须按目标源码解释。
#. ``ip -s link`` 提供接口汇总 Counter；``ethtool -S`` 提供驱动和硬件 Queue 细节。
#. Driver Counter 名称不是统一 ABI，同名或相似名在不同 NIC 上语义可能不同。
#. ``ss -tinmp`` 可观察 TCP 状态、RTT、Retransmit、Send-Q、Recv-Q 和 Socket Memory，但字段依版本而定。
#. ``tc -s qdisc`` 用于发送调度层的 Backlog、Drop、Overlimit 和 Requeue。
#. ``nstat`` 等协议 Counter 用于观察 TCP/IP 事件，不能代替 Queue 位置诊断。
#. Packet Drop 的第一问题是“在哪一层丢”，不是“把所有 Buffer 调大”。
#. NIC/Driver Drop、Softnet Drop、qdisc Drop、Socket Drop、Netfilter Drop 和远端 Drop 属于不同位置。
#. 增大前一层 Queue 可能暂时减少 Drop，也会增加内存和排队延迟。
#. Drop Counter 上升必须和输入 Packet Rate、Queue、CPU 和应用消费速度放在同一窗口。
#. TCP Retransmit 是端到端恢复动作，不自动证明本机网卡丢包。
#. Retransmit 可来自本机发送、远端接收、中间网络、ACK 丢失、严重乱序或超时估计。
#. 双端抓包并对齐 Sequence/ACK/SACK 是缩小丢包位置的重要证据。
#. 本机 ``tcpdump`` 看到 Packet 只证明 Packet 到达抓包 Hook，不能证明 NIC、NAPI、Socket 或对端完整成功。
#. 接收侧 Drop 调查顺序应是 NIC Ring → Driver/NAPI → Softnet → Protocol/Filter → Socket → Application。
#. 发送侧 Drop/Queue 调查顺序应是 Socket → TCP/Pacing → qdisc → Netdev Queue → Driver Ring → NIC → Network。
#. Recv-Q 长期高位通常指向应用读取速度不足、Worker 调度或协议处理后的消费瓶颈。
#. Send-Q 长期高位需结合对端窗口、拥塞窗口、RTT、Loss、qdisc 和应用写入节奏。
#. Zero Window 指向接收端流量控制，不能和拥塞窗口缩小混为一谈。
#. Congestion Window 属于发送端网络拥塞控制；Advertised Window 属于接收端应用/Buffer 流量控制。
#. qdisc Shaping、Policing、AQM 和 Fair Queueing 会改变发送顺序、速率、Drop 和尾延迟。
#. qdisc Overlimit 不一定发生 Drop；它表示策略边界被触发。
#. Bufferbloat 是过深排队导致 RTT 和尾延迟增长，不是简单“Buffer 太多”单一结论。
#. NAPI、Softirq 和 Ksoftirqd 属于接收/完成 CPU 服务路径。
#. Ksoftirqd 高占用通常是上游网络工作量或预算溢出的结果，需要继续找 Queue 和输入率。
#. NAPI Poll 长时间占用 CPU 会减少普通 Task 调度机会，也可能提高 Packet 处理吞吐。
#. Interrupt Coalescing 降低中断率，却会增加单批等待和突发处理；需要在吞吐与延迟之间测量。
#. Coalescing、NAPI Budget、Ring Size 和 Backlog 是不同层级的批处理/缓存控制。
#. 锁争用会把多 CPU 并行路径压缩成共享临界区。
#. 网络锁可能位于 Socket、qdisc、Route/Neighbor、Conntrack、Driver Queue、Statistics 或其它共享对象。
#. ``queued_spin_lock_slowpath`` 热点只说明 CPU 在自旋，必须用 Call Graph 找到具体锁使用者。
#. 睡眠锁等待需要 Off-CPU 和 Owner 证据，Cycles Profile 可能看不到等待者完整时间。
#. Lock Contention 要回答锁地址/对象、持有者、等待者、争用频率、等待时间和临界区工作量。
#. 单个全局表、全局 Queue 或共享 Counter 可成为扩展性瓶颈。
#. Per-CPU、Per-Queue、Sharding 和 RCU 可减少共享写，但会增加聚合、内存和生命周期复杂度。
#. False Sharing 会让不同 CPU 修改同一 Cacheline 上的不同字段，形成 Cacheline Bounce 而不一定出现显式锁。
#. Cacheline Bounce 可表现为高 Cycles、较低 IPC、远端 Cache Hit 和多核扩展性下降。
#. 将字段改为 Per-CPU 或重新布局前，必须证明共享 Cacheline 是真实热点。
#. Conntrack、Netfilter、BPF、Traffic Control 和 Security Hook 会增加每 Packet CPU 成本。
#. 每 Packet 固定成本在小包高 PPS 场景中更明显，Byte Throughput 正常时 PPS 仍可能饱和 CPU。
#. 吞吐必须同时按 Bits/s、Packets/s、Connections/s 和 Requests/s 观察。
#. Jumbo Frame 可减少 Packet 数和每 Packet 成本，也会改变 MTU、网络路径和丢包影响范围。
#. Offload 可降低 CPU，也会改变抓包形态、延迟批次和错误定位方式。
#. XDP 可在 ``skb`` 前处理 Packet，减少完整协议栈成本，但不自动保留 Socket/Netfilter 语义。
#. AF_XDP/Zero-copy 可减少复制和对象成本，仍需要 Queue、UMEM 和应用消费能力匹配。
#. NUMA 会影响 NIC DMA Buffer、NAPI CPU、Socket Worker 和应用内存访问。
#. NIC 位于 Node A，而 IRQ/Worker/Buffer 位于 Node B 时，跨 Socket 数据和 Cacheline 会降低扩展性。
#. IRQ、Queue 和 Worker 调整应与 PCIe NUMA Node、CPU Topology 和内存位置共同验证。
#. CPU Affinity 调整可能降低 Cache Miss，也可能造成单 CPU 饱和和故障迁移困难。
#. 盲目增加 Socket Buffer、Backlog 或 Ring 会把 Drop 转化为更高 Queueing Delay。
#. 盲目增加应用线程会增加 Runqueue、Socket Lock、Cache Miss 和上下文切换。
#. 网络 Sysctl 只能改变已有机制策略，不能创造 NIC Queue、CPU 周期或对端带宽。
#. 修改前必须保存接口、Queue、IRQ、RSS/RPS/RFS/XPS、qdisc、Socket 和 Sysctl 配置。
#. 单变量实验应同时比较 Throughput、PPS、Drop、Retransmit、RTT、Queue、CPU/Packet 和 ``p99``。
#. 平均吞吐提升但 Retransmit、RTT 或 Tail Latency 恶化，不是完整成功。
#. 多核扩展性应比较 1、2、4、8 等 Worker/Queue 下每增量 CPU 带来的吞吐与争用变化。
#. 吞吐不再增长而 Lock/Cacheline/Runqueue 增长，说明并行路径已经进入串行化或局部饱和。
#. 稳定调查顺序是：Flow/Packet Rate → NIC Queue → IRQ/NAPI CPU → Protocol/qdisc → Socket Queue → Application → Lock/NUMA。

必背路径
--------

接收性能路径：

::

   Packet 到达 NIC RX Queue
   → NIC DMA 写入 RX Buffer
   → MSI-X / IRQ 通知目标 CPU
   → NAPI Schedule 与 Poll
   → Driver 构造/交付 skb
   → GRO / XDP 后续或普通协议栈
   → IP / Netfilter / TCP/UDP
   → Socket Receive Queue
   → Application recv
   → Buffer Refill 与所有权回收

发送性能路径：

::

   Application send
   → Socket Send Buffer
   → TCP Segmentation / Pacing / Congestion
   → Routing / Netfilter / Neighbor
   → qdisc
   → Netdev TX Queue
   → Driver Descriptor / DMA
   → NIC Hardware Queue
   → Wire
   → TX Completion / skb Release

丢包定位：

::

   固定 Interface、Queue、CPU、Flow 与时间窗口
   → 检查 NIC/Driver Counter
   → 检查 IRQ 分布与 NAPI/Softnet
   → 检查 Protocol/Netfilter Drop
   → 检查 qdisc Backlog/Drop
   → 检查 Socket Send-Q/Recv-Q 与 Memory
   → 检查 Application 消费
   → 双端抓包对齐 TCP Sequence/ACK
   → 找到最早出现缺口或队列溢出的层

扩展性调查：

::

   逐步增加 Flow、Queue、Worker 或 CPU
   → 记录 Throughput、PPS、CPU/Packet 与 p99
   → 检查 Per-queue/Per-CPU 分布
   → 展开 Lock Slowpath Call Graph
   → 检查 Cacheline、NUMA 和单 Flow 热点
   → 找到吞吐停止增长时最先饱和的共享对象
   → 分片、对齐或减少共享写
   → 同规模重新测试

必须区分
--------

* NIC Drop 与 TCP Retransmit：设备局部丢弃和端到端恢复事件不同。
* NAPI Budget Exhaustion 与 Drop：处理达到预算不表示 Packet 已经丢失。
* Softnet Backlog 与 Socket Queue：CPU 网络处理排队和应用接收排队不同。
* qdisc Queue 与 Driver Ring：软件发送调度和硬件执行队列不同。
* RSS、RPS、RFS 与 XPS：硬件接收分流、软件接收分流、应用局部性和发送选择不同。
* Bit Throughput 与 Packet Rate：大包带宽和小包 PPS 的 CPU 模型不同。
* Congestion Window 与 Receive Window：网络拥塞控制和接收端流量控制不同。
* Lock Contention 与 False Sharing：显式同步等待和隐式 Cacheline 争用不同。
* CPU 总余量与 Queue CPU 余量：整机空闲可与单队列 CPU 饱和同时存在。
* Buffer 增长与能力增长：更深队列不等于更高服务率。

一句话结论
----------

网络可扩展性调查必须先找 Packet 停在哪个 Queue，再判断该层是 CPU/设备服务率不足、应用消费慢，还是共享锁与 Cacheline 把多核路径重新串行化。

来源
----

* 教材：AIBook Linux Kernel
* Part：Part 36 — Kernel Performance Engineering for CPU, Memory, I/O, Network, and Lock Contention
* 章节：Chapter 180 — Network Throughput, Packet Loss, Lock Contention, and Scalability
* 源文件：``docs/LinuxK/Part_36_Kernel_Performance_Engineering_for_CPU_Memory_IO_Network_and_Lock_Contention/Chapter_180_Network_Throughput_Packet_Loss_Lock_Contention_and_Scalability.md``
* 固定版本：`18386764582829f2b807b7b0947785eb77b50446 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_36_Kernel_Performance_Engineering_for_CPU_Memory_IO_Network_and_Lock_Contention/Chapter_180_Network_Throughput_Packet_Loss_Lock_Contention_and_Scalability.md>`_
