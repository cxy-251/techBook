第142章：sk_buff 作为网络 Packet 对象
======================================

本章必须记住
------------

#. ``struct sk_buff`` 是 Linux 网络栈中表示一次 packet 处理实例的核心元数据对象。
#. skb 本体主要保存元数据和指针；packet 字节位于关联 head buffer、page fragment 或其它 skb 链中。
#. 同一份 packet 数据可以被多个 skb 元数据对象共享，因此“skb 对象”和“skb 数据区”必须分开计数。
#. 稳定阅读顺序是：几何位置 → 协议头位置 → 共享/所有权 → 路径元数据 → 队列归属。
#. ``head`` 指向 head buffer 起点，``data`` 指向当前有效数据起点，``tail`` 指向线性有效数据末尾，``end`` 指向 head buffer 数据区边界。
#. ``data`` 前方是 headroom，供下层协议向 packet 前部压入头部。
#. ``tail`` 后方是 tailroom，供路径向 packet 尾部追加字节。
#. ``len`` 表示整个 packet 当前总长度，包含线性区和非线性区。
#. ``data_len`` 表示非线性数据长度；线性有效长度可用 ``skb_headlen()`` 一类 helper 获得。
#. ``truesize`` 是网络内存记账估值，不等同于 packet wire length 或 payload 长度。
#. ``skb_shared_info`` 位于 head buffer 尾部，保存 page frags、GSO 信息和数据共享引用等状态。
#. ``frags[]`` 引用 page 中的数据片段，使大 payload 能以 scatter-gather 形态传递。
#. ``frag_list`` 可以关联其它 skb，常出现在聚合、分段或特殊协议路径中。
#. 非线性 skb 的协议头通常仍需位于可直接访问的线性区。
#. 代码直接按结构体读取协议头前，应确保所需字节在线性区且长度验证完成。
#. ``pskb_may_pull()`` 一类 helper 用于确保前部所需字节可线性访问；具体 helper 与上下文具有版本差异。
#. ``skb_linearize()`` 会把非线性数据整理为连续数据，可能发生分配和复制，不能视为无成本操作。
#. ``skb_reserve()`` 在空 skb 中移动 ``data`` 和 ``tail``，预留 headroom，不增加有效数据长度。
#. ``skb_put()`` 扩展尾部有效数据，返回新追加区域；调用前必须保证 tailroom 足够。
#. ``skb_push()`` 向前扩展有效数据，常用于发送路径添加链路层或网络层头部。
#. ``skb_pull()`` 从前部消费字节，常用于接收路径逐层移除当前已处理头部。
#. Push/pull/put 改变指针与长度合同，不自动验证硬件 packet 是否真的包含对应字节。
#. 解析任何外部 packet 前必须先验证总长度、头部长度、fragment 状态和协议字段。
#. ``mac_header``、``network_header``、``transport_header`` 记录各协议头相对 head 的位置。
#. Header offset 与当前 ``data`` 指针是不同概念；pull 后旧头部仍可通过正确 header helper 定位。
#. 接收路径通常从 MAC 层开始设置并推进 header；发送路径通常从传输层向外压入 IP 和链路层头部。
#. ``skb->protocol`` 常表示当前二层负载的网络协议类型，例如 IPv4 或 IPv6。
#. ``skb->dev`` 关联当前入口或出口网络设备，路径中可能因 bridge、VLAN、tunnel 或 redirect 改变。
#. ``skb->sk`` 可关联 socket，用于发送内存记账、ownership 和回调，但并非所有 skb 都必须关联用户 socket。
#. ``mark``、``priority``、traffic class、hash、VLAN、tc metadata 等会影响 routing、qdisc、Netfilter 和队列选择。
#. ``dst`` 相关状态保存路由结果和后续输出操作；路由失效或 reroute 时可能被替换。
#. Checksum 元数据表达“哪些校验工作已完成或应由硬件完成”，不是单纯的校验和值字段。
#. ``CHECKSUM_NONE``、``CHECKSUM_UNNECESSARY``、``CHECKSUM_PARTIAL`` 等状态具有不同方向和可信语义。
#. TX ``CHECKSUM_PARTIAL`` 通常配合 ``csum_start``、``csum_offset`` 请求设备完成指定校验和。
#. RX 报告 checksum 已验证时，驱动必须只在硬件确实覆盖对应协议范围时设置可信状态。
#. GSO 元数据描述一个大 skb 后续如何分段，wire 上通常仍是多个符合 MTU/MSS 的 packet。
#. ``gso_size``、``gso_segs``、``gso_type`` 等字段应与协议头和设备 feature 一致。
#. GRO 在接收侧把多个兼容 packet 聚合成较大 skb，减少后续协议处理次数。
#. GSO/GRO 改变的是内核处理粒度，不改变对端协议必须看到合法 packet 的要求。
#. skb 可以同时有对象引用共享和数据区共享，二者由不同引用状态表达。
#. ``skb_get()`` 增加同一个 skb 对象引用，调用者仍共享同一元数据对象。
#. ``skb_clone()`` 创建新的 skb 元数据，但通常共享 packet data buffer。
#. Clone 适合需要独立队列/元数据视图而不复制 payload 的路径。
#. ``skb_copy()`` 创建新的 skb 和新的数据副本，成本高于 clone。
#. ``pskb_copy()``、``skb_copy_expand()`` 等 helper 在复制范围和 headroom/tailroom 上具有不同语义。
#. skb 元数据未共享，不代表底层数据可写；修改前仍需检查 cloned/shared data 状态。
#. ``skb_cloned()``、``skb_shared()``、``skb_header_cloned()`` 回答不同共享层级，不能互换使用。
#. 修改共享数据前通常需要 unshare 或 copy-on-write helper，例如 ``skb_unshare()``、``skb_cow_head()``。
#. ``skb_cow_head()`` 常用于确保 header 可写并提供足够 headroom，可能触发 head 复制或扩容。
#. Clone 后只修改各自独立元数据通常安全；修改共享 packet 字节必须先建立独占可写状态。
#. TCP 重传、packet tap、mirror、bridge、Netfilter 和 tunnel 都可能克隆 skb，所有权路径必须按实际调用点判断。
#. 不能假设函数返回后仍拥有 skb；许多网络 API 成功时会接管 skb，失败时所有权规则可能不同。
#. 例如发送入口常在调用后接管或释放 skb，调用者不能无条件再次 ``kfree_skb()``。
#. ``NETDEV_TX_OK`` 表示驱动已接管 skb；``NETDEV_TX_BUSY`` 表示 skb 仍归网络核心，驱动不应修改或释放。
#. 不同 API 的 ownership 合同必须查函数文档与调用约定，不能只凭函数名判断。
#. skb 进入队列后，队列通常持有其生命周期；出队、drop 或 completion 路径负责最终释放。
#. ``skb_queue_head``、``skb_queue_tail`` 等队列操作包含链表与锁语义，裸操作与 ``__skb_*`` 版本的锁要求不同。
#. Socket receive queue、qdisc queue、driver TX ring 和 backlog 都是不同所有者和不同排队阶段。
#. ``kfree_skb()``/``consume_skb()`` 都减少引用并最终释放，但调用意图和 trace 语义可能不同。
#. Drop 路径应保留可观察原因时使用相应 drop helper；精确 API 随版本演进。
#. skb 释放会递归处理 head buffer、page frags、frag_list、dst、socket 记账和 destructor。
#. ``destructor`` 可用于在最终释放时归还 socket 内存等资源，因此延迟释放会延迟相应记账下降。
#. skb 被驱动 DMA 使用时，数据页和 DMA mapping 必须存活到 TX/RX completion。
#. 卸载或 reset 设备时，不能因软件队列已清空就释放仍被设备使用的 skb buffer。
#. RX 驱动可从 page pool 获取 buffer，并把页片段附加到 skb；归还路径需遵守 page pool 与 DMA 同步合同。
#. XDP buffer 与 skb 是不同 packet 表示，XDP_PASS 后可能才转换成 skb。
#. AF_XDP、zero-copy、page pool 和 build_skb 路径会改变 buffer 所有者与释放方式，属于版本/驱动敏感实现。
#. ``build_skb()`` 可让现有 buffer 成为 skb head，但调用者必须满足对齐、空间和释放合同。
#. skb 的 ``cb`` 控制区供某一阶段协议私有临时使用；跨层使用必须遵守覆盖规则。
#. 不同协议层可复用同一 ``cb``，把旧私有内容跨越不兼容层级保存会造成数据破坏。
#. skb metadata 中的指针和 offset 在重分配、expand、linearize 后可能变化，不能长期保存裸 data 指针。
#. 调用可能移动 head 的 helper 后，应重新获取 header 指针和 data 指针。
#. Route、Netfilter、tunnel decapsulation/encapsulation 可以重置 header 和 checksum 状态。
#. 封装 packet 常同时存在 outer 与 inner header 元数据，offload 路径需要区分二者。
#. MTU/GSO 处理前必须确认 skb 代表的逻辑 packet、外层 packet 与最终 wire packet 粒度。
#. Packet 抓包看到的形态可能受 GRO/GSO、抓取点和硬件 offload 影响，不能直接等同于 wire 上单个 frame。
#. 在 TX 抓包点看到超大 TCP packet 可能只是 GSO skb，设备稍后才完成分段。
#. 在 RX 抓包点看到聚合 packet 可能来自 GRO，而不是网卡真正收到一个超大 frame。
#. skb allocation 失败、headroom 扩展失败和 linearization 失败都可能形成 packet drop。
#. 高频复制、线性化和 expand 会增加 CPU 与内存带宽成本，并可能放大 tail latency。
#. 诊断数据损坏时应记录 ``len``、``data_len``、headroom、tailroom、header offset、clone 状态和 checksum/GSO 字段。
#. 诊断 use-after-free 时应沿 enqueue、dequeue、clone、completion、drop 和 destructor 的所有权变化追踪。
#. KASAN 可发现 CPU 侧部分越界/UAF；设备 DMA 越界仍需要 IOMMU、DMA debug 和驱动证据。
#. BPF/tracepoint 可以观察 skb 生命周期和 drop，但事件字段、reason 枚举与开销具有版本边界。
#. 稳定源码阅读顺序是：分配来源 → buffer 几何 → header 转换 → clone/copy → 队列所有者 → offload → completion/drop → 释放。

必背路径
--------

发送路径构造 skb：

::

   分配 skb 并预留 headroom
   → 放入 payload 或附加 page frags
   → 设置 transport_header
   → IP 层 skb_push 网络头
   → 设置 network_header 与 route/dst
   → 链路层 skb_push MAC 头
   → 设置 mac_header、protocol、checksum/GSO
   → 交给 qdisc / netdev / driver

接收路径推进 skb：

::

   驱动从 RX buffer 构造 skb
   → 设置 dev、protocol、checksum、hash
   → 设置 mac_header
   → pull 链路层头部
   → 设置 network_header 并解析 IP
   → pull/定位传输层头部
   → 设置 transport_header
   → 交给 TCP/UDP 和 socket queue

Clone 后修改 Header：

::

   skb_clone 共享 packet data
   → 新 skb 拥有独立元数据
   → 检查 header/data 是否 shared
   → skb_cow_head / unshare
   → 必要时复制或扩展 head
   → 重新取得 header 指针
   → 安全修改 packet 字节

skb 最终释放：

::

   队列出队 / drop / TX completion
   → 减少 skb 对象引用
   → 处理 destructor 与 socket 记账
   → 释放 dst 和协议引用
   → 释放/归还 head buffer
   → 释放 page frags / frag_list
   → 对象生命周期结束

诊断 skb 性能成本：

::

   检查是否频繁扩展 headroom
   → 检查是否触发 linearize
   → 检查 clone 后是否发生 COW
   → 检查 frags 与设备 SG 能力
   → 检查 GSO/GRO 和 checksum fallback
   → 对齐 allocation、drop 与 CPU profile

必须区分
--------

* skb 元数据与 Packet 数据：``struct sk_buff`` 保存状态和指针；真实字节可位于共享 head 或 page fragments。
* 对象共享与数据共享：``skb_get`` 共享同一 skb；``skb_clone`` 通常创建新元数据但共享数据区。
* 线性长度与总长度：线性区只占 ``len`` 的一部分；``data_len`` 表示非线性部分。
* Coherency 与可写独占：数据内容可见不表示当前 clone 有权直接修改共享字节。
* 逻辑 skb 与 Wire Packet：GSO/GRO 会让一个 skb 代表多个发送或接收 segment。

一句话结论
----------

``sk_buff`` 是 packet 穿过 Linux 网络栈时携带的“护照”：它记录字节位置、协议层级、共享关系、路由/offload 状态和当前所有者，而数据复制只在路径确实需要独占或连续内容时发生。
