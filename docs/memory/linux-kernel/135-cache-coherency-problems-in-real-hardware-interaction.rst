第135章：真实硬件交互中的缓存一致性问题
======================================

核心知识点
----------

DMA 正确性从所有权开始
   任何 buffer 都要回答：刚才由谁写、下一步由谁读、当前 owner 是否已经完成交接。CPU 与设备不能无协议地同时访问同一内存。

Coherency 与 Ordering 不同
   Cache coherency 解决双方是否看见最新内容；memory ordering 解决多个字段以什么顺序可见。平台 coherent 也不代表描述符自动有序。

Direction 定义数据流
   ``DMA_TO_DEVICE`` 表示 CPU 准备、设备读取；``DMA_FROM_DEVICE`` 表示设备写入、CPU 消费；``DMA_BIDIRECTIONAL`` 不能替代清晰的 owner 协议。

Streaming DMA 依靠显式交接
   CPU 最后访问后执行 map/sync for device，再停止访问；设备完成后执行 sync for CPU 或 unmap，CPU 才能可靠读取和复用。

Coherent memory 仍需要发布协议
   ``dma_alloc_coherent()`` 适合 ring 和 mailbox，但 CPU 仍应先写数据字段，经 ``dma_wmb()`` 后发布 owner/valid；观察完成后经 ``dma_rmb()`` 再读取其余字段。

编译器屏障不能替代 DMA 屏障
   ``barrier()`` 只限制编译器；``smp_*`` 主要处理 CPU 间顺序；``dma_*`` barrier 用于 CPU 与设备共享 coherent memory 的协议顺序。

Doorbell 与描述符可见性是两件事
   DMA barrier 保证描述符先可见，MMIO doorbell 通知设备消费。Read-back 只能处理 posted MMIO write，不能补上缺失的描述符屏障。

Cache line 是共享风险边界
   小 DMA buffer 若与 CPU 高频修改字段共享 cache line，cache clean/invalidate 可能覆盖相邻设备数据。应考虑独立分配和 cache-line 对齐。

双方不能写同一字段
   ``DMA_BIDIRECTIONAL`` 不能让 CPU 与设备同时无锁修改同一字节。描述符应划分 CPU-owned 字段、device-owned 字段和明确的 owner 位。

Mapping 范围必须覆盖真实访问
   Descriptor length、offset、headroom、tailroom 与 DMA mapping size 必须一致。范围过小可能 fault 或遗漏同步，范围过大则扩大设备访问授权。

IOMMU 不解决 stale data
   IOMMU 只保证设备访问被映射页。数据仍可能因为错误 direction、缺失 sync 或 cache-line 共享而陈旧，即使完全没有 fault。

Coherent 平台会掩盖错误
   在 x86 上偶然正常的驱动，可能在 non-coherent Arm、RISC-V 或嵌入式平台稳定失败。可移植性必须依赖 DMA API，而不是本机现象。

IRQ 和锁都不能同步 DMA 数据
   Spinlock 保护 CPU 并发，IRQ disable/synchronize 控制通知路径；它们都不会自动执行 cache maintenance 或停止设备访问 buffer。

迟到 DMA 比迟到 completion 更危险
   Generation/tag 可识别旧完成，但无法阻止旧设备请求覆盖已经复用的内存。Teardown 必须真正停止 bus master，再回收 buffer。

关键路径
--------

TX 可见性：

::

   CPU 写 payload
   → map/sync for device，DMA_TO_DEVICE
   → 写 descriptor 地址和长度
   → dma_wmb
   → 发布 owner/valid
   → MMIO doorbell
   → 设备读取数据
   → completion
   → unmap
   → CPU 释放或复用 buffer

RX 可见性：

::

   map RX buffer，DMA_FROM_DEVICE
   → 发布 descriptor
   → 设备写 packet 与 metadata
   → 设备发布 completion/owner
   → CPU 观察完成
   → dma_rmb / sync for CPU
   → CPU 读取数据
   → unmap 或 sync for device 后复用

数据损坏诊断：

::

   确认当前 owner
   → 确认 direction
   → 还原 map/sync/unmap 时间线
   → 检查 mapping size 与设备 length
   → 检查 cache-line 共享
   → 检查 barrier、owner 和 producer
   → 检查迟到 DMA 与 buffer 复用
   → 跨 coherency 平台验证

概念辨析
--------

* Coherency 与 ordering：前者保证最新内容可见；后者保证字段按协议顺序出现。
* DMA sync 与 IRQ synchronize：前者维护 buffer 可见性；后者只等待中断处理路径。
* IOMMU mapping 与 cache visibility：前者决定设备访问哪一页；后者决定双方看到哪一版内容。
* Completion notification 与 device stop：完成通知结束某项工作；回收仍须证明设备不再访问内存。
* Coherent architecture 与无需 barrier：硬件 cache 一致不代表 descriptor 和 doorbell 可以任意重排。

本章结论
--------

真实硬件中的 DMA 正确性依赖明确的 CPU/设备所有权交接。Direction、sync、cache-line 隔离、描述符 barrier、completion 和 buffer 生命周期必须作为一个协议整体设计。
