第151章：传统网络栈成本模型
===========================

核心知识点
----------

完整语义具有逐包成本
   传统网络栈用设备抽象、``sk_buff``、协议、路由、Netfilter、Socket、拥塞控制和 qdisc 提供通用语义；每层都会增加对象、查表、队列和状态维护。

接收路径跨越多个所有者
   普通 RX 从 NIC、DMA Buffer、NAPI、skb、协议栈进入 Socket Queue，最后由应用通过系统调用取得数据。每次所有权转移都可能增加同步和排队。

发送路径同样分层推进
   普通 TX 从 Socket/协议队列经过路由、策略、qdisc、Netdev Queue 和驱动 Ring 到达 NIC。应用 ``send`` 成功只表示本地协议栈接受数据。

``sk_buff`` 是通用性成本中心
   skb 统一承载 Header、Route、Checksum、GSO/GRO、Mark、Socket 和引用状态，使各子系统可以组合，也产生分配、初始化、共享和释放成本。

小 Packet 放大固定开销
   系统压力必须同时看 Packet/s、Byte/s 和平均包长。相同吞吐下，小 Packet 会执行更多对象操作、协议分派和队列切换。

队列既吸收突发也制造等待
   RX Ring、NAPI Backlog、Socket Queue、qdisc 和 TX Ring 都能缓冲短时 Burst；到达速率持续高于服务速率时，Backlog 才会增长为延迟和 Drop。

CPU 与 NUMA 局部性决定隐藏成本
   RSS、IRQ Affinity、RPS/RFS、XPS 和应用线程位置共同决定 Packet 是否跨 CPU、跨 Cache 和跨 NUMA Node 移动。

策略层成本必须由 Profile 证明
   Routing、Conntrack、Netfilter、Tunnel 和 qdisc 会增加状态访问，但不能只按规则数量猜测热点，应以真实调用路径和 CPU Profile 为依据。

Offload 改变处理粒度
   GRO 减少 RX 上层处理次数，GSO/TSO 延迟 TX 分段；它们降低每 Packet 成本，却仍依赖正确 Metadata、Feature 检查和软件回退。

绕过内核会转移责任
   XDP、AF_XDP 或用户态协议栈可以缩短路径，同时失去或重建 TCP、Socket、路由、策略、排队、公平和故障恢复等通用能力。

优化必须建立成本账本
   应把分配、解析、查表、排队、复制、唤醒和设备服务分别量化，再移动占比最大且业务不需要的工作。

关键路径
--------

传统 RX 成本链：

::

   NIC DMA 写 RX Buffer
   → IRQ 调度 NAPI
   → Poll 清理 Descriptor
   → 构造 sk_buff
   → GRO / L2 / IP / Policy
   → TCP / UDP Socket Lookup
   → Socket Receive Queue
   → 唤醒应用
   → recvmsg 复制到用户 Buffer

传统 TX 成本链：

::

   应用 send
   → Socket 与协议发送队列
   → IP Route / Netfilter
   → qdisc 排队与调度
   → 选择 Netdev Queue
   → Driver DMA Ring
   → NIC Completion
   → 释放 skb 与发送记账

路径选型：

::

   明确业务必需语义
   → 需要 TCP、Socket、路由和策略
   → 保留传统栈并优化 Offload、Queue 与 Locality

   只需早期 Header 决策
   → 评估 Native XDP

   需要用户态 Raw Frame 和自管 Buffer
   → 评估 AF_XDP

概念辨析
--------

* 每 Packet 成本与每 Byte 成本：小包主要放大固定对象和分派开销；大包更容易受复制和内存带宽限制。
* 队列缓冲与持续拥塞：短时 Backlog 可以吸收 Burst；长期服务不足才会形成不断增长的延迟和 Drop。
* Zero-copy 与零成本：减少 Payload Copy 后，Ring、同步、Cache、NUMA、轮询和用户逻辑仍然存在。
* 完整协议语义与最短路径：传统栈提供通用可靠性和策略；早期路径只应承担其信息边界内的工作。
* 抓包可见与真实路径：XDP Drop、硬件过滤、Redirect 和 Offload 可能发生在抓取点之前或之后。

本章结论
--------

传统网络栈用逐包对象、策略和队列成本换取完整通用语义；高性能优化应先证明哪些语义不需要，再缩短对应路径。
