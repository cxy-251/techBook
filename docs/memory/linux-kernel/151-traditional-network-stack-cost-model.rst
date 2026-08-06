第151章：传统网络栈成本模型
===========================

本章必须记住
------------

#. 传统 Linux 网络栈的主要价值是提供统一、完整、可组合的网络语义，而不是让每个 Packet 以最少指令穿过系统。
#. 完整语义包括设备抽象、NAPI、``sk_buff``、协议解析、路由、Netfilter、Namespace、Socket、拥塞控制、重传、qdisc、统计和可观测性。
#. 每一层都解决真实工程问题，也会增加每 Packet 固定成本、对象生命周期、队列和 Cache 访问。
#. 高性能网络优化的第一步不是选择 XDP 或 AF_XDP，而是判断当前业务真正需要多少协议栈语义。
#. 需要可靠 TCP 字节流、内核拥塞控制、路由、防火墙和普通 Socket API 时，完整网络栈的成本对应必要功能。
#. 只需按 L2/L3/L4 Header 过滤、采样、重定向或负载均衡时，较早的处理点可以避免后续通用成本。
#. 普通 RX 主线是：NIC RX Queue → DMA Buffer → NAPI Poll → ``sk_buff`` → 协议栈 → Socket Queue → 应用唤醒。
#. 普通 TX 主线是：应用 → Socket/协议队列 → IP/Route → Netfilter → qdisc → Netdev Queue → Driver Ring → NIC。
#. 传统路径的成本不集中在单个函数，而是分散在对象创建、层间分派、队列切换、策略 Hook 和调度唤醒中。
#. ``struct sk_buff`` 是传统网络路径的核心 Packet 元数据对象，实际 Packet 字节通常位于关联 Buffer 或 Page Fragment 中。
#. skb 记录数据边界、Header Offset、设备、协议、Checksum、GSO/GRO、Route、Mark、Socket 归属和引用状态。
#. skb 的通用性让 Bridge、Tunnel、Netfilter、qdisc、抓包和协议层共享同一个 Packet 表示。
#. 构造 skb 需要分配或取得元数据对象、初始化字段、建立 Buffer 关系并设置协议上下文。
#. skb 分配和释放可能使用 Per-CPU Cache、Slab、Page Pool 或驱动专用回收路径，精确实现具有版本和驱动差异。
#. 单个分配看似很小，在每秒数百万 Packet 时会成为显著 CPU、Allocator 和内存带宽成本。
#. 每 Packet 固定成本比每 Byte 成本更容易在小 Packet 场景成为瓶颈。
#. 同样的字节吞吐下，64 字节 Packet 的 Packet/s 和协议处理次数远高于大 Packet。
#. 因此只看 Gbit/s 无法判断网络栈压力，必须同时观察 Packet/s、CPU/Packet 和 Drop。
#. 元数据初始化会写入多个 Cache Line，后续驱动、协议、路由、Netfilter 和 Socket 又会读取或修改这些字段。
#. Packet 穿过的层越多，共享元数据和关联对象被触碰的次数通常越多。
#. Clone、Mirror、抓包、重传和 Tunnel 可增加引用计数、共享 Buffer 和 Copy-on-write 成本。
#. ``skb_clone()`` 减少 Payload 复制，不消除元数据对象和共享引用管理成本。
#. ``skb_copy()``、Linearize、Expand 和 Header COW 会增加复制、分配和内存带宽压力。
#. GRO 通过接收聚合减少上层每 Packet 固定成本；GSO/TSO 通过延迟分段减少发送路径对象数量。
#. Offload 降低通用路径成本，但仍需要正确元数据、Feature 检查和软件 Fallback。
#. Cache 压力不仅来自对象大小，还来自同一 Packet 在多个子系统之间移动和被不同 CPU 访问。
#. RSS、RPS、RFS、XPS、IRQ Affinity 和应用 CPU 亲和性共同决定 Packet 的 CPU 迁移与 Cache Locality。
#. NIC 把 Packet DMA 到某个 NUMA Node，而应用在远端 Node 处理时，会产生 Remote Memory 和 Cache 迁移成本。
#. 增加 CPU 数量不自动提高吞吐；Flow、Queue、IRQ 和应用线程未正确分散时，负载仍可能集中在单核。
#. 传统 RX 路径通常跨越硬件 Ring、NAPI Poll、Softirq、协议队列、Socket Queue 和应用调度等多个排队点。
#. 每个队列都能吸收短时 Burst，也会占用内存并增加排队延迟。
#. 队列存在不等于发生故障；持续到达速率高于服务速率时，Backlog 才会不断增长并最终 Drop。
#. NAPI 用受 Budget 控制的批处理替代逐包完整中断，减少 IRQ 和上下文切换成本。
#. NAPI Batch 越大，单位 Packet 固定成本通常越低，但单轮 CPU 占用和等待时间可能增加。
#. ``NET_RX_SOFTIRQ`` 可以在中断返回路径执行，也可在压力下由 ``ksoftirqd`` 承担。
#. ``ksoftirqd`` CPU 高说明 Softirq 工作积压或被推迟，不自动证明 NIC 已达到线速或硬件故障。
#. Softirq 长时间占用 CPU 会压缩应用线程运行时间，使 Socket Queue 增长并增加端到端延迟。
#. 应用被唤醒不表示它立即运行；Runqueue、调度类、CPU 亲和性和其它中断都会增加交付延迟。
#. Readiness 通知、系统调用和用户复制是普通 Socket 路径成本的一部分。
#. UDP Receive 通常仍需经过 Socket Lookup、Receive Queue 和从内核 Buffer 到用户 Buffer 的复制。
#. TCP 还要维护序列空间、ACK、窗口、重传、拥塞控制、定时器和有序字节流语义。
#. 绕开完整协议栈意味着应用或新路径不再自动获得这些语义，不能把“路径更短”解释为“功能等价”。
#. Netfilter、Conntrack、Routing 和 qdisc 都会引入查表、状态访问或 Hook 分派成本。
#. 规则数量多不必然线性变慢，具体数据结构和快速路径依子系统与版本而定；必须用真实 Profile 判断。
#. Conntrack 为 Flow 保存双向状态，适合防火墙和 NAT；无状态早期过滤若不需要这些语义，可选择更早 Hook。
#. qdisc 提供 Flow 公平、Pacing、Shaping 和 AQM；绕过 qdisc 也会失去这些发送调度能力。
#. XDP 的收益来自在 skb 形成前作出早期决策，常用于明显 Drop、Redirect、采样和简单 L4 处理。
#. XDP 不直接提供完整 Socket、TCP、Conntrack、qdisc 或应用层语义。
#. Generic XDP 已进入 skb 路径，主要用于兼容和功能验证；Native XDP 才能最大程度避免传统 RX 成本。
#. AF_XDP 可以把早期 Frame 交给用户态 Ring/UMEM，减少普通 Socket 路径和 Payload Copy。
#. AF_XDP 不自动减少应用业务计算、跨 NUMA 访问、无效轮询、过小 Batch 或 Ring 管理成本。
#. Zero-copy 只是数据搬运维度，不能替代队列、所有权、同步和错误处理。
#. 高性能路径会把部分内核通用职责转移到 BPF 程序、用户态控制面和 Buffer 生命周期管理中。
#. 优化前应建立成本账本：每 Packet 分配、协议处理、Map/规则查找、队列、复制、唤醒和设备服务各占多少。
#. ``ip -s link`` 提供 Netdev 汇总包数和 Drop，不能指出所有驱动、XDP、协议或 Socket Drop。
#. ``ethtool -S`` 可提供 Queue、Ring、XDP 和硬件私有统计，字段名称与含义由驱动定义。
#. ``/proc/interrupts`` 观察 IRQ 分布，``/proc/softirqs`` 和 ``/proc/net/softnet_stat`` 观察软件接收压力。
#. ``ss`` 观察 Socket Queue、TCP 状态和窗口；它不能说明 Packet 是否仍停留在 NAPI 或 Driver Ring。
#. ``perf`` 用于定位 CPU 时间和 Cache/分支热点，Ftrace/eBPF 用于连接具体路径阶段。
#. 单一工具只能观察一个层级，性能结论必须把计数、时间线和 CPU Profile 对齐。
#. Packet 未进入 Socket 不一定是 Drop：它可能被 XDP Redirect、被转发、被 Netfilter 接管或仍在队列中。
#. Packet 未出现在 tcpdump 不一定未到达 NIC：XDP_DROP、硬件过滤和更早驱动 Drop 可能发生在抓取点之前。
#. 抓到 Packet 不表示应用已经收到，因为 Route、Netfilter、Socket Queue 和调度仍可能阻止交付。
#. 选择完整栈、XDP、TC、AF_XDP 或用户态协议栈时，要比较功能范围、故障恢复、安全性和维护成本。
#. 微基准峰值 Packet/s 不能代表生产收益，必须同时测 P99、Drop、CPU、功耗、内存和异常恢复。
#. 稳定优化顺序是：定义所需语义 → 画出实际路径 → 建立每层计数 → 找最大成本 → 只移动必要工作 → 再验证正确性。
#. 稳定源码阅读顺序是：Driver RX → NAPI → skb 构造 → Core Receive → Protocol/Policy → Socket → Wakeup → TX/qdisc 对称路径。

必背路径
--------

传统 RX 成本链：

::

   NIC RX Queue
   → DMA 写入驱动 Buffer
   → IRQ 调度 NAPI
   → Poll 清理 Descriptor
   → 构造 struct sk_buff
   → GRO / Core Receive
   → L2 / IP / Routing / Netfilter
   → TCP / UDP Socket Lookup
   → Socket Receive Queue
   → 唤醒应用
   → recvmsg 复制到用户 Buffer

每 Packet 成本账本：

::

   Descriptor 与 DMA Ownership
   → skb 分配和元数据初始化
   → Header 解析与协议分派
   → Route / Policy / Map 查找
   → Queue Enqueue / Dequeue
   → 引用、Clone、Copy 与 Free
   → Softirq / 调度 / 系统调用
   → 用户态复制和业务处理

判断是否前移处理：

::

   明确 Packet 需要的最终语义
   → 需要完整 TCP/Socket/Netfilter/qdisc
   → 保留传统栈并优化 Queue/Offload/Locality

   只需早期 Header 决策
   → 评估 Native XDP

   需要用户态 Raw Frame 与自管 Pipeline
   → 评估 AF_XDP / Zero-copy

分层观测：

::

   ethtool -S 查看硬件和 Queue
   → /proc/interrupts 查看 IRQ 分布
   → /proc/softirqs 与 softnet_stat 查看 NAPI/Softirq
   → BPF/Trace 查看早期 Action 与 Drop
   → ss 查看 Socket Queue
   → perf 查看 CPU 与 Cache 热点
   → 对齐同一时间窗口和 Flow

优化验证：

::

   固定流量模型与 Packet Size
   → 记录 Packet/s、Bit/s、CPU、P99、Drop
   → 每次只改变一个路径层级
   → 比较传统栈与早期路径
   → 检查功能、策略和故障恢复是否等价
   → 只保留有可重复收益的改变

必须区分
--------

* 完整协议语义与最短处理路径：传统栈提供可靠性、策略和兼容性；早期路径只适合所需信息更少的决策。
* 每 Packet 成本与每 Byte 成本：小 Packet 放大对象与分派开销；大 Packet 更容易受复制和内存带宽限制。
* 队列吸收 Burst 与持续积压：短时 Backlog 是缓冲；服务速率长期低于到达速率才形成延迟和 Drop。
* Zero-copy 与零管理成本：减少 Payload Copy 后，Ring、同步、NUMA、轮询和用户逻辑仍有成本。
* 抓包可见性与实际 Packet 路径：抓取点只看到路径的一部分，早期 Drop、Redirect 和 Offload 会改变可见形态。

一句话结论
----------

传统网络栈用每 Packet 对象、队列和策略成本换取完整通用语义；高性能优化必须先证明哪些语义不需要，再把决策前移，而不是盲目绕过内核。
