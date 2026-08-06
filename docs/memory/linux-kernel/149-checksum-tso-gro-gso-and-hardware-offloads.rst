第149章：Checksum、TSO、GRO、GSO 与硬件 Offload
==============================================

核心知识点
----------

Offload 只移动工作位置
   Checksum、分段和聚合仍必须保持相同 TCP/IP 外部语义。变化的是内核或设备在哪个阶段完成工作。

Offload 由 skb 元数据与设备能力共同决定
   ``net_device`` Feature 表示路径能力；skb 的 Checksum、GSO、Header 与封装元数据描述当前 Packet 需求。二者求交集后才能决定硬件执行或软件 Fallback。

Feature 启用不等于每包都使用
   协议类型、Header 长度、Tunnel、Segment 数、目标设备和队列限制都可能使单个 skb 退回软件处理。

TX Checksum 使用未完成状态
   ``CHECKSUM_PARTIAL`` 表示校验和仍待完成，``csum_start`` 与 ``csum_offset`` 指定计算与写入位置。驱动只能在硬件真实支持该布局时下发。

RX Checksum 是可信声明
   驱动设置 ``CHECKSUM_UNNECESSARY`` 表示适用校验已被可靠验证；``CHECKSUM_NONE`` 通常表示仍需软件检查，不等于校验失败。

TSO 与 GSO 分层
   TSO 由 NIC 对大 TCP skb 做硬件分段；GSO 是内核通用分段框架和软件 Fallback。最终 Wire Packet 仍必须满足 MTU/MSS。

GSO skb 是逻辑大包
   ``gso_size``、``gso_type`` 和 Header Offset 描述怎样拆分。一个大 skb 可以代表多个最终 Segment，并可能包含多个 DMA Fragment。

GRO 在接收后聚合
   GRO 在 NAPI/协议入口把同一 Flow 中兼容的小 Packet 合并，减少上层每包成本。它不表示线缆上出现超大 Frame。

聚合与分段必须可逆地保持语义
   Sequence、Header、Checksum、封装和 Flow 不兼容时不能 GRO。经 GRO 形成的大 skb 后续仍要能被 GSO/协议路径正确处理。

跨设备路径要重新验证能力
   Bridge、VLAN、Tunnel、Veth、IFB 或 Redirect 改变输出设备后，原设备能力不能自动继承，必须在新边界重新检查。

Header 修改必须同步元数据
   NAT、Netfilter、TC/BPF、封装、解封装、COW 或 Linearize 后，Checksum Offset、GSO 类型和 Header 指针都可能需要重建。

软件 Fallback 有显著成本
   Software Checksum、GSO Segment、Linearize 和 Copy 会增加 CPU、内存带宽和对象数量，但正确降级优先于错误使用硬件能力。

抓包形态受 Offload 影响
   发送侧大包可能尚未 TSO/GSO 分段；接收侧大包可能已 GRO；硬件前抓到 Bad Checksum 可能只是字段尚待设备填写。

Feature 更新必须与硬件同步
   ``wanted_features`` 经依赖修正后由驱动应用到硬件。不能只改变位图，也要处理在途 Descriptor 与新旧配置边界。

关键路径
--------

TX Checksum：

::

   协议构造 skb
   → 设置 CHECKSUM_PARTIAL
   → 设置 csum_start / csum_offset
   → 检查目标 netdev Feature
   → 支持则配置硬件 Descriptor
   → 不支持则软件计算
   → 发送合法 Wire Packet

TSO/GSO：

::

   TCP 生成大 skb
   → 设置 GSO Metadata
   → 输出路径验证设备能力
   → 支持 TSO：NIC 分段
   → 不支持：软件 GSO 生成多个 skb
   → 每个 Segment 满足 MTU/MSS

RX GRO：

::

   NIC 收到多个 Packet
   → 驱动设置可信 RX Metadata
   → napi_gro_receive
   → 比较 Flow、Header、Sequence 与 Checksum
   → 兼容则聚合
   → Flush 后进入 IP/TCP

疑似 Offload 故障：

::

   保存 MTU 与 Feature 状态
   → 判断抓包点位于分段/聚合前后
   → 检查 skb Header、Checksum 与 GSO Metadata
   → 一次关闭一个相关 Feature
   → 对齐接收端抓包与硬件统计
   → 验证软件 Fallback

概念辨析
--------

* TSO 与 GSO：TSO 是硬件 TCP 分段；GSO 是通用软件分段框架。
* GRO 与 Wire 大包：GRO 聚合已接收 Packet，线缆上仍是合法 Segment。
* Feature Enabled 与 Packet 实际使用：能力存在不表示当前 skb 满足条件。
* 抓包 Bad Checksum 与真实错误：硬件前抓包可能看到尚未完成的 TX Checksum。
* 软件降级与协议变化：Fallback 只移动工作位置，不应改变最终协议语义。

本章结论
--------

Offload 是 skb 元数据与 netdev Feature 共同定义的跨软硬件合同。Header、Checksum、Segment 和 Fallback 的任何解释不一致都会从性能优化直接变成数据正确性故障。
