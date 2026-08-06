第149章：Checksum、TSO、GRO、GSO 与硬件 Offload
==============================================

本章必须记住
------------

#. Network Offload 的本质是把部分协议工作移动到更晚的软件阶段或硬件边界。
#. Offload 不改变 TCP/IP 的外部协议语义，只改变内核和设备在哪个阶段完成校验、分段或聚合。
#. 每个 Offload 都由 ``skb`` 元数据和 ``net_device`` Feature 共同表达，驱动与硬件必须按同一合同解释。
#. ``features`` 表示接口当前启用能力；``hw_features`` 表示硬件可供用户切换的能力集合。
#. ``wanted_features`` 表示期望状态，最终 Feature 还要经过依赖修正和驱动配置。
#. 某个 Feature 在接口上启用，不表示每个 Packet 都符合使用条件。
#. 发送前核心路径会根据 skb 类型、Header、封装、GSO Type 与目标设备 Feature 决定硬件执行还是软件 Fallback。
#. Checksum Offload 解决的是协议校验和计算或验证工作的位置。
#. TX ``CHECKSUM_PARTIAL`` 表示校验和尚未最终完成，skb 提供计算起点和结果写入位置。
#. ``csum_start`` 与 ``csum_offset`` 描述硬件或软件 Helper 应处理的校验和字段。
#. TX Checksum Offload 一般只直接表达一个 IP-style Checksum 写入点。
#. Tunnel Packet 可能同时有 Outer 与 Inner Checksum，需额外协议与 Feature 语义处理。
#. 驱动接收 ``CHECKSUM_PARTIAL`` skb 时，只能在硬件真实支持该协议、封装和 Header Offset 时交给设备。
#. 不支持时必须由核心或驱动前的 Helper 完成软件 Checksum，不能把未完成字段直接上线。
#. RX Checksum Offload 是设备验证后由驱动把结果写入 skb 状态。
#. ``CHECKSUM_UNNECESSARY`` 表示适用的协议校验已被可信验证，不表示 Packet 所有外层和内层校验都已验证。
#. ``CHECKSUM_NONE`` 通常表示上层仍需按普通软件路径验证，不能解释为校验失败。
#. 驱动错误地把未验证 Packet 标为已验证，可能让损坏数据进入协议栈。
#. 驱动过度保守会增加 CPU 计算，但通常比错误宣称验证更安全。
#. TSO 是硬件执行 TCP Segmentation；GSO 是 Linux 通用软件 Segmentation 框架。
#. TSO/GSO 允许一个大 skb 在网络栈较长路径中表示多个最终 Wire Segment。
#. ``gso_size`` 表示目标 Segment Payload 尺度，``gso_type`` 表示协议和封装类型。
#. ``gso_segs`` 可记录或估计最终 Segment 数，具体维护时点随路径变化。
#. GSO skb 的 ``len`` 可以远大于 MTU，Wire 上仍应产生符合路径 MTU/MSS 的合法 Packet。
#. 硬件 TSO 需要知道 MAC、Network、Transport Header 位置以及 Checksum 语义。
#. TSO 通常依赖 TX Checksum Offload，因为每个最终 Segment 都要修正长度、序号和校验和。
#. 关闭 TX Checksum Feature 可能连带关闭 TSO，属于能力依赖而非工具故障。
#. Scatter-Gather 让大 skb 的 Head/Frags 可由多个 DMA Segment 描述，常与 TSO 配合。
#. TSO Feature 启用但硬件 Segment 数、Header 长度或封装类型超限时，仍可能走软件 GSO。
#. 软件 GSO 把大 skb 切成多个小 skb，再分别进入普通发送路径。
#. GSO 是硬件 Offload 的必要 Fallback 基础，因为 Packet 可能被 Redirect 到不支持原能力的设备。
#. Bridge、VLAN、Tunnel、Veth、IFB 和物理 NIC 之间转发时，Offload 能力要在新的输出边界重新验证。
#. 不能假设源设备支持的 TSO 能力会自动传递给目标设备。
#. GRO 是接收侧的软件 Packet 聚合，在 NAPI/协议入口附近把兼容的小 skb 合成较大 skb。
#. GRO 的目标是减少 IP/TCP 等上层每 Packet 固定开销。
#. GRO 发生在线缆接收之后，因此 Wire 上仍然是多个合法 Packet。
#. GRO 通常按 Flow、协议 Header、Sequence、Checksum 与封装状态判断是否可合并。
#. Sequence 不连续、Header 不兼容、Checksum 不可信或 Flow 不同的 Packet 不能合并。
#. GRO 结果可能使用大 skb、Frags 或 Frag List 表达，具体形态依协议和实现。
#. GRO 合并必须保留可再次分段的协议语义；理想上可由 GSO 重新拆回合法 Segment。
#. NAPI Batch 越充分，GRO 越可能同时看到相邻 Packet，但批量也影响交付延迟。
#. Hardware GRO/RSC 在设备侧先做聚合，软件 GRO 在内核 NAPI 路径执行，两者的可见性和限制不同。
#. 硬件聚合必须由驱动正确描述 Segment/Checksum/Flow 元数据，否则上层无法可靠解释。
#. GRO 与 LRO 不是简单同义词；具体硬件大包聚合能力及其 Forwarding 适用性应按 Feature 文档验证。
#. GSO/TSO 是 TX Segmentation，GRO 是 RX Aggregation，方向和时间点不能混用。
#. Checksum Offload 只移动校验和工作，不自动完成加密、完整性认证或所有协议验证。
#. VLAN Offload 可由硬件插入/剥离 Tag，但 skb VLAN Metadata 与 Wire Header 必须保持一致。
#. Tunnel Offload 同时涉及 Outer/Inner Header、Checksum、Segmentation 与 MTU，能力组合更严格。
#. ``NETIF_F_*`` Feature 位名称与组合随内核演进，稳定结论是按 Packet 语义和设备合同求交集。
#. ``ndo_fix_features`` 用于修正互斥和依赖；``ndo_set_features`` 把最终变化应用到硬件。
#. ``netdev_features_check``、``ndo_features_check`` 等路径可按单个 skb 进一步缩小可用 Feature，具体接口随版本变化。
#. Feature 更新必须同步硬件状态，不能只改变用户可见位图。
#. 驱动启用硬件能力失败时必须返回错误或降级，不能显示 Enabled 而硬件仍按旧模式运行。
#. Feature 关闭后，在途 Descriptor 仍可能按旧配置执行，驱动需按硬件合同序列化变化。
#. Offload Metadata 属于 skb 生命周期；Clone、Copy、Encapsulation、Decapsulation 和 Reroute 都可能要求更新。
#. Header 被 ``skb_push/pull``、Expand、Linearize 或 COW 后，应重新确认 Offload Offset。
#. 修改 Packet Header 后若不修正 Checksum/GSO 状态，会造成错误 Checksum、错误 Segment 或 Drop。
#. Netfilter、TC/BPF、Tunnel 和 NAT 修改 Header 后必须维持 skb Offload 合同。
#. ``skb_checksum_help()``、``skb_gso_segment()`` 等软件 Helper 是 Fallback 路径，精确函数组织具有版本差异。
#. Fallback 可能触发线性化、分配、复制和多 skb 生成，造成明显 CPU 与内存压力。
#. Offload 的性能收益主要来自减少每 Packet CPU 工作和减少协议栈遍历次数。
#. 大 skb 也会增加单对象处理时间、DMA Segment 数、队列突发和 Completion 批量。
#. TSO 可能形成较大 Burst，qdisc/Pacing/BQL 需要控制发送节奏和驱动排队。
#. GRO 降低 Packets/s 处理成本，也可能让上层看到更大批量并改变延迟分布。
#. 高吞吐改善不自动代表小流或 P99 延迟改善。
#. Packet Capture 的观察形态受抓取点和 Offload 影响。
#. 发送侧抓到超大 TCP Packet 常是尚未 TSO/GSO 分段的大 skb，不代表 Wire 出现超 MTU Frame。
#. 接收侧抓到大 Packet 可能是 GRO/RSC 聚合结果，不代表 NIC 收到一个超大 Wire Packet。
#. 抓包显示“Bad Checksum”可能因为 TX Checksum 尚待硬件填写，而抓取点位于硬件之前。
#. 必须在接收端、硬件后抓取点或关闭相关 Offload 后复核，才能判断真实 Wire Checksum。
#. 临时关闭 Offload 会改变 CPU、Packet 粒度、队列和时序，只适合作为受控诊断变量。
#. ``ethtool -k`` 显示 Feature 状态，``ethtool -K`` 会改变运行状态，修改应在可恢复环境进行。
#. ``ethtool -S`` 可提供硬件 Checksum、TSO、Drop 和 Queue 统计，字段由驱动定义。
#. ``ip -s link`` 和协议统计不能单独证明某个 skb 使用了哪个 Offload。
#. Ftrace/eBPF 可观察 GSO Segment、GRO Receive、Xmit Validate 与 Drop，事件名具有版本边界。
#. Perf 可比较软件 Checksum、Segmentation、GRO 与驱动 CPU 成本。
#. Offload 声明错误常表现为只在特定 VLAN、Tunnel、IPv6 Extension Header 或小部分流量中损坏。
#. 只在关闭 TSO 后恢复可能指向硬件 TSO、Descriptor Context、Header Offset 或 Driver Feature Bug。
#. 只在关闭 GRO 后恢复可能指向 RX Checksum、聚合条件、Driver Metadata 或协议 GRO Bug。
#. 只在虚拟设备/隧道路径失败，通常要检查 Feature 继承、Inner Header 与软件 Fallback。
#. MTU 改变后出现 Offload 故障，应重新验证 GSO Max Size、Segment Count、RX Buffer 和硬件帧限制。
#. Feature 看似相同但不同 Queue/Function 表现不同，可能来自 SR-IOV VF、Firmware 或 Queue Context 差异。
#. 数据正确性优先于性能；无法证明硬件合同成立时应降级软件路径。
#. Offload 优化必须同时记录吞吐、CPU/Byte、Packets/s、P99、Drop 和错误计数。
#. 精确 Feature、Helper、Tunnel 类型与硬件能力具有版本和设备差异。
#. 稳定源码阅读顺序是：skb Checksum/GSO Metadata → 目标 netdev Features → Per-skb Capability Check → Hardware/Fallback → Driver Descriptor → RX Metadata/GRO。

必背路径
--------

TX Checksum Offload：

::

   TCP/UDP 构造 skb
   → 设置 CHECKSUM_PARTIAL
   → 设置 csum_start / csum_offset
   → 输出路径保持 Header Contract
   → 发送前检查 netdev Feature
   → 支持则驱动配置 Hardware Checksum
   → 不支持则 Software Checksum Helper
   → Descriptor 提交并发送

TSO/GSO：

::

   应用写入大数据
   → TCP 生成大 skb
   → 设置 gso_size / gso_type / Header Offset
   → qdisc 处理逻辑大 Packet
   → 输出设备支持 TSO
   → NIC 分成多个 Wire Segment

   输出设备不支持
   → skb_gso_segment 软件切分
   → 多个普通 skb 分别发送

RX GRO：

::

   NIC 收到多个 Wire Packet
   → Driver 构造 skb 与 Checksum Metadata
   → napi_gro_receive
   → 比较 Flow、Header、Sequence 与 Checksum
   → 兼容则聚合成大 skb
   → Flush 后进入 IP/TCP
   → Socket 仍看到有序字节流

Feature 更新：

::

   用户改变 ethtool Feature
   → 更新 wanted_features
   → 修正依赖与冲突
   → Driver 配置 Hardware
   → 更新 active features
   → 新 skb 按新能力验证
   → 在途请求按设备协议安全结束

诊断疑似 Offload Bug：

::

   保存接口 Feature 与 MTU
   → 按五元组抓取发送端和接收端
   → 判断抓取点在分段/聚合之前还是之后
   → 检查 skb Header、Checksum、GSO Metadata
   → 一次关闭一个相关 Feature 复测
   → 对齐 Driver/Hardware Error Counter
   → 确认 Software Fallback 是否正确

必须区分
--------

* TSO 与 GSO：TSO 由硬件分段；GSO 是内核软件分段框架和 Fallback。
* GRO 与 Wire 大包：GRO 在接收后聚合多个 Packet；Wire 上仍是合法的小 Segment。
* Feature Enabled 与 Packet 实际使用：接口具备能力不表示当前 skb 的协议、封装和 Header 符合条件。
* Bad Checksum 抓包与真实线缆错误：硬件前抓包可能看到尚未填写的 TX Checksum，需在正确点位复核。
* Offload 降级与协议语义改变：软件 Fallback 只改变工作位置，不应改变最终 Wire Packet 的协议语义。

一句话结论
----------

Offload 是由 skb 元数据和 netdev Feature 共同定义的跨软硬件合同：移动工作可以提高吞吐，任何 Header、Checksum、Segment 或 Fallback 解释不一致都会直接破坏数据正确性。
