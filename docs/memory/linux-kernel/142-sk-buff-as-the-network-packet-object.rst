第142章：sk_buff 作为网络 Packet 对象
======================================

核心知识点
----------

``sk_buff`` 主要是 Packet 元数据对象
   ``struct sk_buff`` 保存长度、指针、协议位置、路由、设备、队列和 offload 状态；真实字节可位于 head buffer、page fragments 或关联 skb 中。

Buffer 几何定义当前可访问范围
   ``head``、``data``、``tail``、``end`` 描述线性缓冲区边界。``data`` 前是 headroom，``tail`` 后是 tailroom，所有扩展都必须先证明空间足够。

总长度不等于线性长度
   ``len`` 包含全部数据，``data_len`` 表示非线性部分。直接解引用协议头前，必须保证所需字节已位于线性区并完成长度校验。

Header Offset 独立于当前 ``data``
   MAC、network、transport header 记录相对 head 的位置。``skb_pull`` 改变当前数据起点后，已设置的头部仍可通过对应 helper 定位。

Push、Pull、Put 只修改几何状态
   ``skb_push`` 向前添加头部，``skb_pull`` 消费前部，``skb_put`` 扩展尾部，``skb_reserve`` 预留 headroom；这些操作不替调用者验证外部 packet 格式。

Clone、引用和复制是不同共享层级
   ``skb_get`` 共享同一个 skb 对象；``skb_clone`` 创建新元数据但通常共享数据；``skb_copy`` 同时复制元数据和 packet 数据。

修改共享数据前必须建立独占状态
   元数据独立不代表底层字节可写。修改 header 或 payload 前应使用 unshare/COW helper，并在可能移动 head 后重新获取所有裸指针。

Metadata 决定后续处理路径
   ``dev``、``sk``、``protocol``、``mark``、``priority``、route/dst、VLAN、hash、checksum 和 GSO 字段会影响协议分发、策略、qdisc 与驱动选择。

一个 skb 不一定等于一个 Wire Packet
   GSO/TSO 允许一个大 skb 代表多个发送 segment，GRO 允许多个接收 segment 聚合成一个 skb。抓包结果取决于观察点和 offload 阶段。

队列决定当前所有者
   Socket queue、backlog、qdisc 和驱动 ring 都会接管 skb 生命周期。调用网络 API 后是否仍拥有 skb，必须按该 API 的成功与失败合同判断。

最终释放还要处理从属资源
   skb 最终释放可能归还 head buffer、page frags、frag_list、dst、socket 记账和 destructor。DMA 使用中的数据必须存活到 completion 后才能释放。

关键路径
--------

发送构造：

::

   分配 skb 并预留 headroom
   → 放入 payload 或 page frags
   → 设置 transport header
   → push IP header
   → 设置 network header 与 route
   → push MAC header
   → 设置 checksum/GSO metadata
   → 交给 qdisc 和驱动

接收推进：

::

   驱动从 RX buffer 构造 skb
   → 设置 dev、protocol、checksum、hash
   → 设置 MAC header
   → pull 链路层头部
   → 定位 network/transport header
   → IP/TCP/UDP 解析
   → 进入 socket receive queue

Clone 后修改 Header：

::

   skb_clone
   → 新元数据共享 packet data
   → 检查 cloned/header shared 状态
   → skb_cow_head 或 unshare
   → 必要时复制/扩展 head
   → 重新取得 header 指针
   → 修改字节

最终释放：

::

   出队、drop 或 TX completion
   → 递减 skb 引用
   → 执行 destructor 与 socket 记账
   → 释放 dst 和协议引用
   → 归还 head/page frags/frag_list
   → 生命周期结束

概念辨析
--------

* skb 元数据与 Packet 数据：skb 保存状态和引用；字节可位于共享或分散的 backing storage。
* ``len`` 与 ``data_len``：前者是总长度；后者只统计非线性部分。
* ``skb_get`` 与 ``skb_clone``：前者共享同一元数据对象；后者创建新元数据并通常共享数据区。
* Clone 与可写：克隆可独立修改部分元数据；修改共享字节前仍需 COW。
* 逻辑 skb 与 Wire Packet：Offload 可让一个 skb 对应多个实际 segment，或反向聚合多个 segment。
* 队列持有与 DMA 持有：软件出队不一定表示设备已停止访问 backing buffer。

本章结论
--------

``sk_buff`` 是 packet 在内核中的状态载体。正确处理依赖 buffer 几何、协议头位置、共享关系、当前队列所有者与 DMA 生命周期同时成立。