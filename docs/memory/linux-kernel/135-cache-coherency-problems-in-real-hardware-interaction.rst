第135章：真实硬件交互中的缓存一致性问题
======================================

本章必须记住
------------

#. DMA 数据正确性的核心问题是：谁刚写过这段内存，下一步谁要读，以及当前是否已完成对应所有权切换。
#. CPU 通过 cache 和虚拟地址访问 buffer；设备通过 DMA address 访问内存，两者可能看到不同时间点的内容。
#. Cache coherency 回答“双方是否能看到最新数据”；memory ordering 回答“多个字段按什么顺序可见”。
#. 即使平台是 DMA coherent，描述符字段发布仍可能需要 barrier；coherent 不等于自动有序。
#. 非一致性平台必须通过 DMA API 执行 cache clean、invalidate 或等价所有权转移。
#. 驱动不应直接调用架构 cache 指令代替 DMA API，因为 IOMMU、bounce、方向和平台规则需要统一处理。
#. ``DMA_TO_DEVICE`` 表示 CPU 准备数据、设备读取；设备开始前必须看到 CPU 的最后修改。
#. ``DMA_FROM_DEVICE`` 表示设备写入数据、CPU读取；CPU 读取前必须看到设备的最后写入。
#. ``DMA_BIDIRECTIONAL`` 只用于真正双向访问，不能用它掩盖不清晰的 ownership 设计。
#. Streaming mapping 的 map、sync、unmap 都携带 direction，方向错误会导致 stale data 或权限问题。
#. 对 ``DMA_TO_DEVICE`` buffer，CPU 最后写入后再 map/sync for device，然后停止修改直到设备完成。
#. 对 ``DMA_FROM_DEVICE`` buffer，设备完成后先 sync for CPU 或 unmap，CPU 才能读取。
#. 同一 streaming buffer 长期复用时，``dma_sync_single_for_cpu()`` 与 ``dma_sync_single_for_device()`` 表达阶段性交接。
#. Sync for CPU 后若还要重新交给设备，必须 sync for device；只做一半会让后续周期读到旧内容。
#. Unmap 通常包含结束映射所需同步，但它同时终止旧 DMA address 的有效性。
#. CPU 在 map 给设备后继续写 buffer，可能在设备读期间改变数据或污染 cache line。
#. 设备在 CPU 已接管后继续 DMA，可能覆盖 CPU 正在读取或已交给上层的数据。
#. Completion IRQ 只是一种通知；驱动仍需确认 descriptor owner/status 与 DMA visibility 协议成立。
#. Coherent DMA memory 常用于 descriptor ring，因为 CPU 与设备长期共享同一控制结构。
#. ``dma_alloc_coherent()`` 保证的是平台定义的 coherent 可见性，不保证多字段描述符的发布原子性。
#. CPU 应先写地址、长度和控制字段，再通过 ``dma_wmb()`` 等保证顺序，最后发布 owner/valid 位。
#. CPU 观察设备写回的 completion/owner 位后，常需 ``dma_rmb()`` 再读取长度、状态和时间戳字段。
#. 具体 barrier 选择必须遵循设备协议和 DMA API，不能用普通 ``barrier()`` 替代硬件顺序。
#. ``barrier()`` 主要阻止编译器重排，不保证 CPU cache、互连或设备可见顺序。
#. ``smp_wmb()`` 面向 CPU 间普通内存顺序，未必足以表达 CPU→设备 DMA descriptor 发布。
#. ``dma_wmb()/dma_rmb()`` 用于 coherent DMA memory 的设备共享顺序，精确实现随架构变化。
#. MMIO doorbell 与 descriptor memory 的顺序需要同时满足：描述符先对设备可见，再通知设备消费。
#. Doorbell read-back 解决 posted MMIO write 到达问题，不能替代 descriptor memory barrier。
#. Cache line 是一致性和覆盖风险的重要粒度，DMA buffer 不应与 CPU 高频修改的无关字段共享 cache line。
#. 设备写入一个 cache line 的部分字节时，CPU 对同一 line 的脏缓存写回可能覆盖设备新数据。
#. CPU 修改 DMA buffer 邻接字段时，cache maintenance 可能影响同一 cache line 上的设备数据。
#. 小型 DMA buffer 嵌入普通结构体尤其危险，应考虑 cache-line 对齐和独立分配。
#. False sharing 不只发生在 CPU 之间，也可能发生在 CPU cache 与设备 DMA 共享区域之间。
#. Streaming mapping 的 size 应覆盖设备实际访问的完整范围；设备越过 mapping 长度属于严重 bug。
#. Size 太小可能造成 cache line 边界处理错误或 IOMMU fault；size 太大扩大设备访问授权。
#. Partial sync 必须遵守 DMA API 的 offset/length 与 cache-line 限制，不能任意对齐到错误范围。
#. Device descriptor 中的长度、offset、headroom 和 tailroom 应与映射范围保持一致。
#. Scatter-gather mapping 后，设备可见 segment 可能被合并，cache 同步应围绕映射后的 DMA 段和 API 合同处理。
#. CPU virtual address 和 DMA address 不能混用；cache sync API 需要传入创建 mapping 时返回的 DMA address。
#. IOMMU 提供地址翻译，不自动解决 cache visibility；翻译正确仍可能读到旧 cache 内容。
#. 没有 IOMMU fault 也不能证明 cache 同步正确，因为 stale data 通常仍落在合法映射内。
#. Coherent 架构上 bug 可能被掩盖，在 non-coherent Arm、RISC-V 或嵌入式平台上才稳定暴露。
#. 驱动不能因 x86 测试通过就删除 DMA sync 或 barrier；可移植语义由 DMA API 定义。
#. 同一 SoC 上不同设备也可能具有不同 coherency 属性，不能按 CPU 架构一概而论。
#. Device Tree/ACPI、IOMMU 和平台总线可能描述设备是否 DMA coherent，驱动通常不应自行猜测。
#. ``dma-coherent`` 等固件属性的使用应由平台/绑定定义，不能在板级描述中随意添加掩盖硬件问题。
#. Coherent memory 仍可能经过 CPU store buffer、互连和设备预取，因此字段协议与 doorbell 顺序不可省略。
#. 设备可能预取 descriptor，驱动修改已交给设备的 descriptor 会产生竞态。
#. Ring owner 位是 CPU/设备所有权协议的一部分；owner 转移后原 owner 不应继续修改其余字段。
#. Producer/consumer 索引也需正确 barrier，否则设备可能看见新索引但仍读到旧 descriptor。
#. RX 路径中，设备先写 packet 和 metadata，再写 completion/owner；CPU 应先观察完成，再 barrier 后读数据。
#. TX 路径中，CPU 先写 packet/descriptor，再发布 owner；设备完成后 CPU 才能 unmap 和释放 buffer。
#. DMA_FROM_DEVICE buffer 在设备使用期间不应被 CPU speculative/ordinary access 依赖；通过 API ownership 管理可见性。
#. DMA_TO_DEVICE buffer 若 CPU 在传输后还需要读取，仍要等设备完成，避免设备尚在读时复用。
#. DMA_BIDIRECTIONAL 不能解决设备和 CPU 同时无锁写同一字段；共享写仍需明确协议或硬件原子机制。
#. 描述符控制字段可由 CPU 写、状态字段由设备写，但应避免双方写同一 cache line 的相同字节。
#. Firmware mailbox 和 command queue 也遵循相同原则：payload、owner、doorbell 和 completion 必须按顺序发布。
#. Device memory consistency 与 C 语言数据竞争是两个层级；CPU 线程间仍需锁、原子和 RCU。
#. 持 spinlock 不能自动刷新 DMA cache，也不能让设备停止访问 buffer。
#. IRQ disable 不能自动同步 DMA buffer；它只影响通知和 handler 执行。
#. ``synchronize_irq()`` 等待 handler，不会执行缺失的 DMA sync，也不会停止硬件写内存。
#. 设备 reset 前应停止新 DMA，reset 后应确认旧 bus master 访问已经结束，再回收 buffer。
#. 过早复用 buffer 是常见数据损坏根因：旧设备写入可能命中新业务对象。
#. Generation/tag 只能帮助识别迟到 completion，不能阻止设备实际覆盖已复用内存。
#. 安全 teardown 需要硬件停止、DMA completion 结束、IRQ/worker 收束、mapping 撤销和内存释放的完整顺序。
#. 数据偶发全 0/旧值时，应检查 direction、sync 点、completion 顺序和设备是否真正完成。
#. 数据头部正确、尾部旧时，应检查 DMA 长度、segment、partial sync 和设备实际写入长度。
#. 相邻字段被随机破坏时，应检查 cache-line 共享、越界 DMA 和 descriptor length。
#. 只在高负载或多核出现时，应检查 ring wrap、barrier、owner 位、CPU 并发和 buffer 复用。
#. 只在某架构出现时，应优先检查 non-coherent DMA、accessor 和 barrier，而不是先归咎设备质量。
#. DMA API debug 可发现错误 map/unmap/direction；KASAN 通常不能捕获设备直接 DMA 的全部越界。
#. IOMMU fault 可捕获映射外访问，但合法大窗口中的越界可能仍静默破坏数据。
#. 设备 trace、descriptor dump 和内存快照应在不触发寄存器副作用的前提下采集。
#. 诊断必须记录 CPU owner、device owner、DMA address、mapping size、direction、descriptor index 和时间线。
#. 精确 cache maintenance 指令、coherent 属性、barrier 实现和 sync 成本属于架构/平台敏感细节。
#. 稳定源码阅读顺序是：buffer 分配 → mapping/direction → CPU 最后访问 → owner 发布 → 设备 DMA → completion → sync → 回收。

必背路径
--------

TX 可见性：

::

   CPU 写 packet payload
   → dma_map/sync for device，DMA_TO_DEVICE
   → 填写 descriptor 地址和长度
   → dma_wmb
   → 发布 owner/valid
   → MMIO doorbell
   → 设备读取 packet
   → completion
   → unmap
   → CPU 才能释放或复用 buffer

RX 可见性：

::

   分配并 map RX buffer，DMA_FROM_DEVICE
   → 发布 descriptor 给设备
   → 设备写 packet 和 metadata
   → 设备发布 completion/owner
   → CPU 观察完成
   → dma_rmb / sync for CPU
   → CPU 读取 packet
   → unmap 后交给上层
   → 或 sync for device 后重新挂回 ring

Coherent Ring 发布：

::

   CPU 填写 descriptor data fields
   → dma_wmb
   → 写 owner/valid 位
   → 更新 producer
   → 写 MMIO doorbell
   → 设备消费 descriptor
   → 设备写 completion 字段
   → CPU 观察 owner 返回
   → dma_rmb 后读取其余字段

数据损坏诊断：

::

   确认 buffer 当前 owner
   → 确认 direction
   → 确认 map/sync/unmap 时间线
   → 检查 mapping size 和设备 length
   → 检查 cache-line 共享
   → 检查 descriptor barrier/owner
   → 检查迟到 DMA 与 buffer 复用
   → 在不同 coherency 平台复现验证

必须区分
--------

* Coherency 与 Ordering：Coherency保证最新内容能被看见；ordering保证多个写入按协议先后出现。
* DMA Sync 与 IRQ Synchronize：DMA sync维护buffer可见性；IRQ synchronize只等待中断处理路径。
* IOMMU Mapping 与 Cache Visibility：IOMMU决定设备访问哪一页；cache维护决定双方看到哪一版内容。
* Completion 通知与设备停止访问：Completion通常表示一个请求结束；回收前仍需遵守设备队列和所有权协议。
* Coherent Architecture 与无需 Barrier：硬件cache一致不代表描述符字段和doorbell可以任意重排。

一句话结论
----------

真实硬件中的 DMA 正确性取决于明确的 CPU/设备所有权交接：direction、sync、cache-line 隔离、描述符 barrier 和 buffer 生命周期缺一不可。
