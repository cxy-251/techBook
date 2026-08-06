第147章：RX/TX Ring、Descriptor 与 DMA
=====================================

本章必须记住
------------

#. 网卡高速数据面建立在 Ring、Descriptor、DMA Buffer 与 Completion 的所有权协议上。
#. Descriptor Ring 是驱动与 NIC 共享的循环描述符数组，通常记录 DMA 地址、长度、控制位和完成状态。
#. Ring 本身常使用 Coherent DMA 内存；Packet Buffer 常使用 Streaming DMA Mapping。
#. Coherent 只解决 CPU 与设备对共享控制内存的可见性，不自动解决 Descriptor 发布顺序。
#. Streaming Mapping 需要按方向、生命周期和 CPU/Device Ownership 使用 ``dma_map_*``、``dma_sync_*``、``dma_unmap_*``。
#. CPU 虚拟地址、CPU 物理地址和设备 DMA 地址是不同地址空间。
#. Descriptor 中必须写入 DMA API 返回的 ``dma_addr_t``，不能把普通指针或物理地址直接交给设备。
#. Ring 的核心状态是 Producer、Consumer/Clean Index 与可用槽位数量。
#. 软件索引、硬件 Head/Tail Register、Completion Queue 与 Descriptor Done Bit 可能共同表达同一生命周期。
#. 精确字段因硬件而异，稳定阅读顺序是 Ring Size → Next-to-use → Next-to-clean → Doorbell → Completion。
#. 每个 Descriptor 至少经历 Free、Prepared、Device-owned、Done、Reclaimed 等状态。
#. 驱动填好 Descriptor 后，通过内存屏障发布字段，再更新 Owner/Producer，最后写 Doorbell。
#. Doorbell 只通知设备“有新工作”，不表示设备已经读取 Descriptor 或完成 Packet。
#. TX Completion 之前，驱动不能解除 DMA Mapping、释放 skb 或复用对应 Descriptor。
#. RX Completion 之前，CPU 不能把设备仍拥有的 Buffer 当作有效 Packet 读取或复用。
#. RX 路径必须提前投递空 Buffer，因为 Packet 到达时设备不能等待驱动临时分配内存。
#. RX Buffer 常以 ``DMA_FROM_DEVICE`` 映射，表示设备将数据写入内存。
#. 驱动把 RX Buffer DMA 地址和容量写入 Descriptor，再推进 RX Tail/Producer。
#. NIC 收到 Frame 后把数据 DMA 到 Buffer，并在 Descriptor 或 Completion Entry 中写入结果。
#. RX Completion 常包含长度、错误、Checksum、VLAN、RSS Hash、Timestamp 等元数据。
#. 驱动只应把硬件真实验证过的元数据转换成 skb 标志。
#. RX 错误位可能表示 CRC、长度、Truncation、DMA 或硬件错误，应在规定层级统计并 Drop。
#. 驱动在 CPU 读取 RX Buffer 前，需要执行对应 DMA Sync 或 Unmap。
#. 使用 Page Pool 等长期映射优化时，Buffer 可重复在设备和 CPU 之间转移，仍必须遵守 Ownership 与 Sync 合同。
#. Page Pool、Build-SKB、XDP 与 AF_XDP 会改变 Buffer 分配和回收细节，属于驱动与版本敏感路径。
#. RX 驱动可复制小 Packet 到新 skb，也可把 Page Fragment 挂入 skb 减少复制。
#. 构造 skb 后必须正确设置长度、Protocol、Device、Checksum、Hash、VLAN 与 Header 状态。
#. RX Buffer 被交给 skb 后，最终释放可能发生在协议栈更深处，驱动不能立即复用同一内存。
#. Page Pool 回收路径可以在 skb 释放后把 Page 归还 Pool，具体标记与 helper 随版本演进。
#. RX Refill 是接收能力的一部分；只清理完成项而不补充空槽，Ring 最终会耗尽。
#. RX Buffer 分配或 DMA Mapping 失败会减少可用槽位，并可能形成硬件 Miss/Drop。
#. 驱动应统计 Refill Failure、No Buffer、Descriptor Error 与 Hardware Drop，不能把它们都压成一个 RX Drop。
#. TX 输入是协议栈交给 ``ndo_start_xmit`` 的 ``skb``。
#. skb 线性区和 Frags 可能需要映射为多个 DMA Segment，每个 Segment 占用一个或多个 Descriptor。
#. 驱动必须在映射前计算所需 Descriptor 数，并预留最坏情况空间。
#. TSO、Checksum、VLAN、Tunnel 与 Context Descriptor 会增加 Descriptor 需求。
#. TX 线性区通常使用 ``dma_map_single(..., DMA_TO_DEVICE)``，Frags 常使用 ``dma_map_page()``，具体 API 依 Buffer 类型。
#. 每次 DMA Mapping 都必须检查 ``dma_mapping_error()``。
#. 多 Segment Mapping 中途失败时，必须逆序解除已经成功的 Mapping，并保持 skb 所有权合同。
#. 在所有 Mapping 和 Descriptor 准备完成前，不能把部分请求发布给设备。
#. 软件 Shadow Ring/Buffer Info 必须保存 skb、DMA Address、Length、方向和第一个/最后一个 Descriptor 关系。
#. Completion 路径依赖这些软件元数据完成 Unmap、统计与 skb 释放。
#. 多 Descriptor 对应一个 skb 时，通常只在代表 End-of-Packet 的位置保存或释放 skb，具体格式依驱动。
#. TX Descriptor 发布需要确保 Payload 对设备可见、Descriptor 字段完成，再更新 Owner/Tail。
#. ``dma_wmb()``、``wmb()``、MMIO Doorbell 顺序的精确选择取决于 DMA API、架构和设备协议。
#. 普通 CPU Memory Barrier、DMA Barrier 与 MMIO Read-back 解决不同边界，不能互换。
#. TX Completion 表示设备不再需要相应 Descriptor/Buffer，驱动才能解除 Mapping 并归还 Ring 空间。
#. 设备报告 Completion 不一定表示远端收到 Packet，只表示本地硬件完成了约定的发送处理。
#. TX Timestamp、错误状态与队列状态可能让 Completion 处理继续保留部分对象，具体路径具有硬件差异。
#. Completion 必须恰好处理一次；重复 Unmap/Free 会导致 UAF，遗漏 Completion 会造成 Ring 泄漏和永久 Stop。
#. TX Ring 可用空间不足时，驱动应调用 ``netif_stop_subqueue()`` 一类接口建立背压。
#. Stop Queue 之后必须重新检查 Ring 空间，处理“刚 Stop 时 Completion 已释放空间”的竞态。
#. 如果空间已经恢复，驱动应重新 Wake Queue，避免 Lost Wakeup。
#. Completion 回收达到安全阈值后，驱动调用 ``netif_wake_subqueue()`` 或等价接口恢复提交。
#. Stop/Wake 阈值应为最大 skb Descriptor 需求留出余量，不能只按单 Descriptor Packet 计算。
#. ``NETDEV_TX_BUSY`` 不应成为正常 Ring 满控制机制；频繁 BUSY 表示 Stop/Wake 时机或空间估算有问题。
#. Byte Queue Limits（BQL）按在途字节反馈控制核心向驱动 Ring 推送的数据量。
#. BQL 管理字节级软件队列压力，不取代 Descriptor Ring 的槽位计数。
#. 驱动提交时向 BQL 报告入队字节，Completion 时报告完成字节，具体 helper 依版本实现。
#. BQL 目标是减少驱动/硬件过度缓存与 Bufferbloat，同时保持设备利用率。
#. 多队列 NIC 为每个 Queue Pair 维护独立 Ring、锁、NAPI、IRQ Vector 与统计。
#. Queue 数量增加可降低锁竞争并提高 CPU 并行，但会增加 Ring 内存、IRQ、Cache 与配置成本。
#. RSS 通常决定 RX Flow 进入哪个 Queue；XPS/Queue Mapping 影响 TX Flow 到哪个 Queue。
#. Queue 与 CPU/NUMA 不匹配会增加 Cache Miss、Remote Memory 与 Completion 跨核成本。
#. Descriptor Ring 可以由设备按顺序消费，也可能配合独立 Completion Queue，不能把一种格式套到所有 NIC。
#. 设备可能要求 Descriptor 对齐、边界限制、最大 Segment 数和最大长度，驱动必须按 DMA Mask 与硬件规格设置。
#. IOMMU 可以把分散物理页映射成设备可访问 IOVA，仍不消除 Segment 数和硬件 Descriptor 限制。
#. Scatter-Gather 只是让设备读取多个内存片段，不表示一个 skb 一定只用一个 Descriptor。
#. DMA Mapping 成功不表示 Descriptor 格式正确；长度、Endian、Control Bit 和 Header Offset 仍由驱动负责。
#. Reset 前必须停止新提交、停止设备 DMA、等待或放弃硬件 Ownership，再回收 Mapping 和 skb。
#. 仅 Mask IRQ 不会停止 DMA，也不证明 Ring 已静止。
#. NAPI Disable 只收束 Poll，不会自动让 NIC 停止写 RX Buffer。
#. Remove/Reset 时释放 Ring 前必须确认设备 Bus Mastering、DMA Engine 与 Doorbell 路径已停止。
#. 强制 Reset 后无法信任旧 Completion Generation，应通过 Queue Generation、Index Reset 或硬件合同识别旧结果。
#. DMA Buffer 被错误提前复用时，设备可能覆盖新对象，CPU 侧 KASAN 不一定能直接定位。
#. IOMMU Fault、DMA API Debug、KASAN、驱动 Descriptor Dump 与 Hardware Counter 要组合使用。
#. Ring Full 可能来自设备发送慢、Completion IRQ 丢失、NAPI 不运行、索引计算错误或 Descriptor 泄漏。
#. RX Drop 可能来自 Ring 无空槽、CPU/NAPI 清理慢、Buffer 分配失败、硬件过滤或错误 Frame。
#. ``ethtool -g`` 常显示 Ring 配置，``ethtool -S`` 可显示 Queue/Descriptor 私有统计，具体支持依驱动。
#. ``/proc/interrupts`` 与 NAPI/Softirq 统计用于判断 Completion 是否被 CPU 处理，不能直接证明 Descriptor 正确。
#. 抓包看不到 Packet 不自动说明 TX Ring 未提交；Packet 可能在 qdisc、驱动、硬件或链路任一层丢失。
#. 稳定源码阅读顺序是：Ring 分配 → RX Refill/TX Mapping → Descriptor 发布 → Doorbell → Completion → Unmap/Recycle → Stop/Wake → Reset/Free。

必背路径
--------

RX Buffer 投递：

::

   分配 Page / Buffer
   → DMA Map 为 DMA_FROM_DEVICE
   → 保存 CPU 与 DMA 元数据
   → 写 RX Descriptor 地址和长度
   → DMA Barrier 发布 Descriptor
   → 更新 RX Tail / Doorbell
   → 设备取得 Buffer Ownership

RX Completion：

::

   NIC DMA 写入 Packet
   → 写 Completion / Done 状态
   → IRQ 调度 NAPI
   → Poll 读取长度与错误
   → DMA Sync / Unmap for CPU
   → 构造 skb 或执行 XDP
   → 交给 GRO / 网络栈
   → 补充新的 RX Buffer

TX 提交：

::

   ndo_start_xmit 收到 skb
   → 计算 Segment 与 Descriptor 数
   → 检查 Ring 空间
   → DMA Map Head 与 Frags
   → 填写 Context/Data Descriptor
   → 保存 Shadow Ring 元数据
   → Barrier 发布 Descriptor
   → 更新 Tail / Doorbell
   → NETDEV_TX_OK 转移 skb 所有权

TX Completion：

::

   NIC 完成发送
   → 更新 Completion / Head
   → IRQ/NAPI 清理 TX Ring
   → 确认设备不再访问 Buffer
   → DMA Unmap 每个 Segment
   → 释放 skb 与附加资源
   → 更新 BQL 与统计
   → Ring 空间充足时 Wake Subqueue

安全 Reset：

::

   阻止新 ndo_start_xmit
   → Stop 所有 TX Queue
   → Mask 设备 IRQ
   → 停止 RX/TX DMA Engine
   → 等待硬件 Idle / Reset 完成
   → synchronize IRQ 与 NAPI
   → 回收或终止所有 Descriptor
   → Unmap/Free Buffer
   → 重新初始化 Ring Generation

必须区分
--------

* Descriptor Ring 与 Packet Buffer：Ring 是共享控制结构；Packet Buffer 是实际 DMA 数据对象，生命周期和映射类型通常不同。
* Doorbell 与 Completion：Doorbell 发布工作；Completion 才结束设备对 Descriptor 和 Buffer 的所有权。
* Queue Stop 与硬件停止：Stop Subqueue 只阻止网络核心继续提交，不会停止 NIC 已在执行的 DMA。
* BQL 字节限制与 Ring 槽位：BQL 控制在途字节；驱动仍需独立保证 Descriptor 空间充足。
* DMA Mapping 与数据正确：Mapping 只建立设备地址；Descriptor 格式、顺序和 Ownership 仍需驱动正确实现。

一句话结论
----------

网卡 Ring 的正确性来自严格的 Descriptor 与 Buffer 所有权转换：发布前完整准备，Completion 前绝不复用，回收时每个 Mapping 和 skb 恰好结束一次。
