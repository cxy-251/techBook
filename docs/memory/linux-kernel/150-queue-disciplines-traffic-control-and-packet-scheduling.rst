第150章：Queue Discipline、Traffic Control 与 Packet Scheduling
==============================================================

本章必须记住
------------

#. qdisc 是 Linux 发送路径中位于协议栈输出与驱动 ``ndo_start_xmit`` 之间的 Packet 排队与调度层。
#. 协议栈决定 Packet 发向哪里；qdisc 决定哪个 Packet 先发、等多久、超限时丢哪个。
#. qdisc 处理的核心对象是 ``skb``，通过 Enqueue、Dequeue、Drop、Reset 和统计操作接入网络核心。
#. ``struct Qdisc`` 表示一个 qdisc 实例，``struct Qdisc_ops`` 表示算法操作表。
#. ``dev_queue_xmit()`` 一类入口把 skb 带到目标 ``net_device`` 与 TX Queue，并进入 qdisc 或直接发送路径。
#. 具体函数拆分随版本变化，稳定路径是协议栈 → TX Queue → qdisc → 驱动。
#. qdisc 与驱动 TX Ring 是不同队列：qdisc 理解 Flow、Class、Pacing 和策略；Ring 理解 Descriptor、DMA 和硬件 Ownership。
#. qdisc 已出队不表示 Packet 已上线；它还要经过驱动 Ring、NIC 和链路。
#. TX Ring 有空间不表示 qdisc 没有积压；两层 Queue 可以同时存在。
#. BQL 控制驱动层在途字节，不替代 qdisc 的分类和调度。
#. 多队列设备常使用 ``mq`` 一类根结构，把流量分到每个 TX Queue 的叶子 qdisc。
#. 根 qdisc、Class、Leaf qdisc 与 Hardware Queue 是不同层级，不能只看一个名称判断全部排队位置。
#. 某些虚拟设备或 Noqueue 接口可绕过常规软件排队，但 Socket、协议或下层设备仍可能排队。
#. Classless qdisc 不提供用户可见层级 Class；Classful qdisc 可建立 Class 树并挂载叶子 qdisc。
#. FIFO 按到达顺序排队，策略简单，主要通过 Packet/Byte Limit 控制队列长度。
#. FIFO 的低实现成本不等于低延迟；Bulk Flow 可让交互 Packet 在长队列后等待。
#. FQ 按 Flow 分队列并提供公平发送机会，常与 Socket Pacing 配合。
#. FQ 的主要目标是 Flow 公平和节奏，不是表达复杂的多层带宽保证。
#. fq_codel 结合 Flow Queuing 与 CoDel AQM，目标是多流公平并控制持续排队时延。
#. CoDel 主要观察 Packet 在队列中的 Sojourn Time，而不只看瞬时队列长度。
#. AQM 在队列完全填满前主动 Drop/Mark，目的是让发送端更早获得拥塞反馈。
#. 主动 Drop 不是故障本身；在可控队列中，它可能是降低 Bufferbloat 的设计行为。
#. HTB 是 Classful Token Bucket 调度器，用 Rate、Ceil、Priority 与层级表达带宽保证和上限。
#. Token Bucket 用时间补充 Token，Packet 发送消耗 Token；Token 不足时 Class 需要等待或按规则 Borrow。
#. HTB Class 常挂 FIFO、FQ 或 fq_codel 等 Leaf qdisc，Class 调度和叶子排队需分别观察。
#. Shaping 通过延迟发送把平均速率控制在目标值；Policing 通常在超速时 Drop/Remark，不保存长时间等待队列。
#. Egress Shaping 应放在真正瓶颈之前，目标速率通常略低于不可控下游链路容量。
#. 在错误接口或错误 Namespace 上配置 qdisc，不会控制实际瓶颈。
#. Tunnel、Veth、Bridge 和物理接口串联时，Packet 可经过多个 qdisc 或 TC Hook。
#. ``tc`` 通过 Netlink 创建 qdisc、Class、Filter 和 Action。
#. qdisc 是调度容器；Class 是 Classful qdisc 的策略节点；Filter 决定 Packet 属于哪里；Action 执行修改或转移。
#. Filter 可根据地址、端口、协议、VLAN、Mark、Priority、Cgroup、Flower 字段或 BPF 结果分类。
#. Mark 只有在当前策略中才有意义；设置 Mark 不自动改变路由或 Class，必须有后续 Rule/Filter 使用。
#. Classifier 命中后可选择 Class，也可执行 Drop、Police、Redirect、Mirror、skbedit 或 BPF Action。
#. ``mirred`` Redirect 会改变 Packet 后续设备和 qdisc 路径，原设备统计不再描述完整发送结果。
#. Ingress qdisc/``clsact`` 提供设备入口或出口的 TC Hook，主线 Egress qdisc 与这些 Hook 位置不同。
#. Ingress 侧无法像正常 Egress Shaping 那样延迟已经到达的远端发送，常使用 Policing、Redirect 到 IFB 或更早控制。
#. TC Action 接管或 Redirect skb 后，调用者必须遵守新的 Ownership 与生命周期合同。
#. Hardware TC Offload 可把部分 Flower/Action 规则下沉 NIC，但支持范围、统计与 Fallback 具有驱动差异。
#. ``skip_sw``/``skip_hw`` 等控制语义依 TC 接口和版本；不能只看规则存在就推断实际执行位置。
#. Hardware Offload 后，Packet/Byte Counter 可能来自硬件并有刷新延迟，需确认 ``in_hw`` 等状态。
#. qdisc 的 Queue Limit 可以按 Packet、Byte、时间或算法内部状态表达，不是统一单一数值。
#. Backlog 是当前排队量；Drops 是被算法或资源拒绝的 Packet；Overlimits 常表示策略限制被触发，不一定等于 Drop。
#. Requeues 表示 Packet 因下层暂时无法接收而重新排队，持续增长需检查驱动 Stop/Wake 和队列合同。
#. qdisc Statistics 的字段语义由算法决定，必须结合该 qdisc 文档解释。
#. ``tc -s qdisc show dev X`` 是查看 qdisc 类型、Backlog、Drop、Overlimit 和 Requeue 的主要入口。
#. ``tc -s class show`` 用于 Classful 调度器的 Class 速率、Token 与队列证据。
#. ``tc -s filter show`` 用于确认分类规则、Action 与 Counter 是否命中。
#. qdisc Counter 不增长可能因为 Packet 走了其它 Queue、Namespace、设备、Offload 或绕过路径。
#. ``ip -s link`` 是 Netdev 聚合统计，不能替代 qdisc 或 Driver Queue 统计。
#. ``ethtool -S`` 可补充 Ring/Hardware Counter，字段由驱动定义。
#. Bufferbloat 是队列过深导致吞吐仍高但 RTT/P99 延迟显著增加的现象。
#. 增大队列可吸收短时 Burst，也会增加最坏排队时间。
#. 仅以 Drop 为零作为优化目标，常会得到更深队列和更差交互延迟。
#. 队列等待近似取决于 Backlog Bytes 与实际发送速率；同样 Packet 数在不同 MTU 下等待时间不同。
#. 上行满载时 Ping 延迟大幅上升，是发送方向 Bufferbloat 的常见证据，不自动说明网络丢包。
#. fq_codel 等 AQM 通过 Flow 隔离和早期反馈减少单个 Bulk Flow 占满队列。
#. FQ/Pacing 可平滑 Burst，但下层硬件 Ring、Firmware 与交换设备仍可能再次形成队列。
#. qdisc 只能控制本机可见的发送点，不能直接控制远端 ISP、交换机或接收端队列。
#. TCP 会把 qdisc Drop 解释为拥塞反馈并调整发送；UDP 应用可能没有同等反馈，需应用或策略限速。
#. ECN 可在支持的 AQM 和协议中用 Mark 替代部分 Drop，具体启用和路径支持需单独验证。
#. GSO skb 在 qdisc 中可能按一个逻辑对象排队，但代表多个最终 Segment。
#. qdisc 的 Packet/Byte Accounting 与最终 Wire Packet 数可能受 GSO/TSO 影响。
#. TSO 大 skb 可形成较大下层 Burst；Pacing、qdisc 与 BQL 共同限制它进入 Ring 的节奏。
#. GSO Segmentation 在 qdisc 前后何时发生取决于设备能力和路径，统计解释必须确认抓取点。
#. Multi-Queue qdisc 中 Flow 到 TX Queue 的映射会影响公平性、锁竞争与硬件并行。
#. XPS、skb Queue Mapping、TC Queue Mapping 与硬件 TC 共同决定最终 TX Queue。
#. 不同 Queue 各有 Leaf qdisc 时，只查看一个 Queue 的统计会漏掉其它流量。
#. Queue Stop 时 qdisc 可继续保留 Packet；驱动 Wake 后调度继续。
#. 驱动频繁 ``NETDEV_TX_BUSY`` 会触发 Requeue 或异常调度，正常实现应依靠 Stop/Wake 避免。
#. Watchdog/TX Timeout 表示 Packet 长时间未由设备完成，不等同于 qdisc 排队超时。
#. qdisc Lock、Per-CPU/Lockless 优化和 RCU 生命周期属于内部实现细节，随版本与算法变化。
#. 配置替换 qdisc 时，旧对象需要 Reset、Drain/Drop Queue、撤销 Filter/Action 并等待引用安全结束。
#. 删除 qdisc 可能立即丢弃其 Backlog，属于会改变流量的操作。
#. TC Filter/Action 可持有设备、BPF Program、Police State 和硬件 Offload 资源，Teardown 需要按框架生命周期释放。
#. Network Namespace 拥有各自的 Netdev 与 TC 配置，必须在 Packet 所在 Namespace 中观察和修改。
#. 容器 Veth 两端属于不同 Namespace，Ingress/Egress 方向相对各自端点解释。
#. 排查高延迟时，应按 Socket Queue → TCP/Pacing → qdisc → Netdev Queue/BQL → Driver Ring → Hardware 顺序定位。
#. 排查 qdisc Drop 时，应区分 Queue Limit、AQM、Policing、Classifier Action 与下层 Requeue。
#. 排查 HTB 未限速时，应确认 Classify 命中、目标 Class、Leaf qdisc、Rate 单位、Offload 和真实瓶颈位置。
#. 排查 Flow 不公平时，应确认 Flow Hash、NAT/Tunnel 五元组、GSO 粒度和单 Queue 集中。
#. 排查配置存在但无 Counter 时，应检查 Namespace、Direction、Parent/Handle、Protocol、Chain 与 Hardware 执行位置。
#. 性能实验应同时记录 Throughput、RTT/P99、Backlog、Drop、CPU、qdisc Counter 与 Driver Counter。
#. 一次只调整一种 qdisc、Limit、Target、Rate 或 Queue Mapping，才能建立因果关系。
#. 精确默认 qdisc、算法参数、Netlink 属性和 TC Offload 支持随发行版与内核版本变化。
#. 稳定源码阅读顺序是：``dev_queue_xmit`` → TX Queue → Root/Leaf qdisc → Enqueue/Dequeue → Driver Xmit → BQL/Ring → Completion 与统计。

必背路径
--------

普通 Egress：

::

   Socket / TCP / IP 生成 skb
   → Route 与 Neighbor 确定输出设备
   → 选择 TX Queue
   → dev_queue_xmit
   → Root / Leaf qdisc Enqueue
   → qdisc 按策略 Dequeue
   → ndo_start_xmit
   → Driver Ring / NIC

HTB 分类与发送：

::

   skb 进入 HTB Root
   → Filter 按 Header / Mark / BPF 分类
   → 选择 Class
   → 进入 Class 的 Leaf qdisc
   → Token 与 Priority 允许发送
   → Leaf Dequeue
   → 交给 Driver

Bufferbloat：

::

   应用发送速率超过瓶颈
   → Socket / qdisc / Ring Backlog 增长
   → Packet Sojourn Time 上升
   → RTT 与 P99 增大
   → AQM Drop/ECN 或 Queue Limit 触发
   → TCP 收到拥塞反馈并降速

分层诊断：

::

   ss 查看 Socket Send-Q 与 TCP Pacing
   → tc -s qdisc 查看 Backlog/Drop/Overlimit
   → tc -s class/filter 确认分类命中
   → ip -s link 查看 Netdev 聚合统计
   → ethtool -S 查看 Queue/Ring/Hardware
   → 抓包对齐实际发送时间
   → 定位排队发生在哪一层

安全替换 qdisc：

::

   保存现有 qdisc/class/filter 配置
   → 确认操作 Namespace 与设备方向
   → 评估 Backlog Drop 和业务影响
   → 原子/有序替换规则
   → 检查 Counter 与分类结果
   → 比较吞吐、RTT、Drop 和 CPU
   → 失败时恢复原配置

必须区分
--------

qdisc 与 Driver Ring
   qdisc 负责策略排队；Ring 负责 DMA Descriptor 执行，两层可同时积压。

Shaping 与 Policing
   Shaping 延迟发送以控制速率；Policing 通常超限即 Drop/Remark。

Drop 与 Overlimit
   Drop 是 Packet 被丢弃；Overlimit 表示策略边界被触发，未必每次都丢包。

FQ 与 HTB
   FQ 主要提供 Flow 公平/Pacing；HTB 主要表达层级带宽保证和上限。

配置存在与实际执行
   规则可能未命中、位于错误 Namespace/方向，或已下沉硬件，必须结合 Counter 与状态确认。

一句话结论
----------

qdisc 是发送路径的时间与顺序控制器：它在驱动前组织 Flow、公平性、带宽和主动丢弃，而端到端延迟必须继续把 Socket、qdisc、Ring 与硬件队列分层测量。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 30，Network Device Drivers, NAPI, Queues, Offloads, and Packet Scheduling；
* AIBook 章节：Chapter 150，Queue Disciplines, Traffic Control, and Packet Scheduling；
* 源文件：``docs/LinuxK/Part_30_Network_Device_Drivers_NAPI_Queues_Offloads_and_Packet_Scheduling/Chapter_150_Queue_Disciplines_Traffic_Control_and_Packet_Scheduling.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_30_Network_Device_Drivers_NAPI_Queues_Offloads_and_Packet_Scheduling/Chapter_150_Queue_Disciplines_Traffic_Control_and_Packet_Scheduling.md>`_。