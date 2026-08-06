第147章：RX/TX Ring、Descriptor 与 DMA
=====================================

核心知识点
----------

Ring 是驱动与 NIC 的共享工作队列
   Descriptor Ring 通常是循环数组，记录 DMA 地址、长度、控制位与完成状态。核心索引是生产位置、清理位置和可用槽位。

Ring 与 Packet Buffer 是不同对象
   Ring 常使用 Coherent DMA 内存；Packet Buffer 常使用 Streaming DMA Mapping。前者保存控制结构，后者承载实际数据。

Descriptor 具有明确所有权状态
   一个槽位通常经历 Free、Prepared、Device-owned、Done 和 Reclaimed。所有权转交后，原 owner 不能再修改或复用对应对象。

发布顺序必须闭合
   驱动先完成 Buffer Mapping 与 Descriptor 字段，再用适当 Barrier 发布 Owner/Producer，最后写 Doorbell。Doorbell 只通知新工作，不表示完成。

RX 必须提前投递 Buffer
   驱动把 ``DMA_FROM_DEVICE`` Buffer 放入 RX Ring，NIC 到包后直接 DMA 写入。没有可用槽位时，设备只能丢包或暂停接收。

RX Completion 才能交还 CPU
   驱动读取长度和错误，执行 DMA Sync/Unmap，再构造 skb 或进入 XDP。交给 skb 后，Buffer 生命周期通常延伸到协议栈最终释放。

RX Refill 是持续接收的必要条件
   清理完成项后必须补充新 Buffer。分配失败、Mapping 失败、No Buffer 与硬件错误应分别统计。

TX 可能消耗多个 Descriptor
   skb 的线性区、Frags、TSO Context 和 Tunnel 元数据可能映射成多个 DMA Segment。提交前必须计算最坏槽位需求。

Mapping 失败必须原子回滚
   多段 Mapping 中途失败时，已建立的 Mapping 要逆序撤销，且不能把部分 Descriptor 暴露给设备。

Shadow Ring 保存软件侧生命周期
   驱动需记录 skb、DMA 地址、长度、Descriptor 范围和 Completion 关系，以便恰好一次 Unmap、释放和记账。

Completion 是资源回收边界
   TX Completion 后才能 Unmap、释放 skb、更新 BQL 并归还 Ring 空间。完成只证明本地设备不再使用 Buffer，不证明远端收到 Packet。

Stop/Wake 建立驱动背压
   Ring 空间不足时停止对应 Subqueue；Completion 恢复足够空间后再唤醒。Stop 后需重新检查空间，避免 Lost Wakeup。

Reset 必须先夺回设备所有权
   Mask IRQ 或 Disable NAPI 都不能停止 DMA。释放 Ring 前必须停止硬件 Queue、确认 DMA Idle、收束 Completion，并处理旧 Generation。

关键路径
--------

RX Buffer 投递：

::

   分配 Buffer
   → DMA Map 为 DMA_FROM_DEVICE
   → 保存 CPU/DMA 元数据
   → 填写 RX Descriptor
   → Barrier 发布
   → 更新 Tail 或 Doorbell
   → 设备取得所有权

RX Completion：

::

   NIC DMA 写入 Packet
   → 写 Done/Completion
   → IRQ 调度 NAPI
   → Poll 读取长度与错误
   → DMA Sync/Unmap
   → 构造 skb 或执行 XDP
   → 交给网络栈
   → Refill 新 Buffer

TX 提交与完成：

::

   ndo_start_xmit 收到 skb
   → 计算 Descriptor 需求
   → DMA Map Head 与 Frags
   → 填写 Descriptor 与 Shadow Ring
   → Barrier 后发布并 Doorbell
   → NIC 发送
   → Completion
   → Unmap、释放 skb、更新 BQL
   → 归还槽位并 Wake Queue

安全 Reset：

::

   Stop TX Subqueue
   → 阻止新提交
   → Mask IRQ
   → 停止 RX/TX DMA Engine
   → 等待硬件 Idle
   → synchronize IRQ 与 Disable NAPI
   → 回收全部 Descriptor 和 Mapping
   → 重建 Ring Generation

概念辨析
--------

* Descriptor Ring 与 Packet Buffer：Ring 保存控制条目；Buffer 保存实际 Packet 数据。
* Doorbell 与 Completion：Doorbell 发布工作；Completion 结束设备所有权。
* Queue Stop 与硬件停止：Stop 只阻止核心继续提交，不能停止已运行的 DMA。
* BQL 与 Ring 槽位：BQL 控制在途字节；Ring 仍需独立管理 Descriptor 数量。
* DMA Mapping 与正确发送：Mapping 只提供设备地址；格式、顺序和所有权仍由驱动保证。

本章结论
--------

网卡 Ring 的正确性来自严格的 Descriptor 与 Buffer 所有权协议：发布前完整准备，Completion 前禁止复用，回收时每个 Mapping 与 skb 恰好结束一次。
