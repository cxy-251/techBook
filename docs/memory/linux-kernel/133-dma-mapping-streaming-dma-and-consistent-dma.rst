第133章：DMA Mapping、Streaming DMA 与 Consistent DMA
====================================================

本章必须记住
------------

#. DMA 允许设备主动读写系统内存，CPU 负责准备 buffer、建立映射、发布地址和处理完成。
#. 驱动必须区分 CPU virtual address、CPU physical address 和 device-visible DMA address。
#. CPU virtual address 供内核代码解引用；DMA address 供设备写入寄存器或描述符。
#. 设备不能使用 CPU 虚拟地址，因为设备访问不经过 CPU 页表。
#. DMA address 也不等同于 CPU physical address；IOMMU、host bridge、bounce buffer 和 DMA mask 都可能改变映射。
#. ``dma_addr_t`` 表示设备可见地址，不能当普通指针解引用。
#. 普通驱动应通过 DMA API 建立设备访问，不应自行把 ``virt_to_phys`` 结果写给设备。
#. ``dma_set_mask_and_coherent()`` 声明设备能表达的地址宽度，通常应在 probe 早期完成。
#. Streaming DMA 适合一次性或短期传输，例如 packet buffer、块 I/O 页或临时命令 payload。
#. Coherent/consistent DMA 适合 CPU 与设备长期共享的小型控制内存，例如 descriptor ring、mailbox 和 command queue。
#. Streaming 和 coherent 是访问模式选择，不是“低速”和“高速”的简单分类。
#. ``dma_map_single()`` 输入 CPU buffer、长度和方向，返回设备可用的 DMA address。
#. 每次 map 后都必须检查 ``dma_mapping_error()``，失败地址不能继续写入硬件。
#. ``dma_unmap_single()`` 结束映射；unmap 后旧 DMA address 不得继续被设备使用。
#. Map/unmap 参数中的设备、长度和 direction 应与创建映射时一致。
#. ``DMA_TO_DEVICE`` 表示设备读取内存；CPU 应在设备开始前完成内容准备。
#. ``DMA_FROM_DEVICE`` 表示设备写入内存；CPU 应在设备完成并同步后再读取。
#. ``DMA_BIDIRECTIONAL`` 只在设备确实双向访问同一 buffer 时使用，通常成本和权限更保守。
#. Direction 不只是文档，它可影响 cache maintenance、IOMMU 权限和 DMA debug 检查。
#. Streaming mapping 的稳定所有权模型是：CPU 阶段 → map/sync for device → 设备阶段 → sync for CPU/unmap → CPU 阶段。
#. Map 后到 sync/unmap 前，CPU 不应随意访问设备当前拥有的 streaming buffer。
#. CPU 在设备 DMA 期间修改 buffer，会让设备读取或覆盖哪个版本变得未定义。
#. ``dma_sync_single_for_cpu()`` 把仍保持映射的 buffer 暂时交还 CPU 观察。
#. ``dma_sync_single_for_device()`` 表示 CPU 已结束访问，buffer 再次交给设备。
#. 同一映射循环复用时，sync 点必须成对表达所有权切换。
#. 若传输结束且不再复用，应 unmap，而不是只 sync 后遗忘映射。
#. Coherent DMA 通过 ``dma_alloc_coherent()`` 返回 CPU pointer 和 DMA address 两个视角。
#. ``dma_free_coherent()`` 必须使用原设备、大小、CPU pointer 和 DMA address 释放。
#. Coherent 表示 cache 可见性由平台维持，不表示描述符字段发布顺序自动正确。
#. CPU 填写 coherent descriptor 后，仍可能需要 ``dma_wmb()`` 或设备规定的 barrier，再发布 valid/owner 位。
#. 设备更新 coherent completion 状态后，CPU 仍需按协议使用 ``dma_rmb()`` 等顺序保证，再读取其余字段。
#. Coherent memory 通常不需要 streaming ``dma_sync_*``，但 precise API 取决于分配方式和平台。
#. ``dma_pool`` 适合大量固定大小、具有对齐或边界要求的 coherent 小对象。
#. Streaming buffer 的来源必须适合 DMA mapping；并非所有 vmalloc、栈内存或任意内核地址都可直接 map。
#. 栈对象生命周期短且物理布局不适合通用 DMA，不能把栈地址交给设备异步访问。
#. ``vmalloc`` 虚拟连续但物理分散，普通 ``dma_map_single`` 不能按单段连续物理 buffer 假设处理。
#. 分页或分散数据应使用 page/SG 接口，例如 ``dma_map_page()``、``dma_map_sg()``。
#. ``dma_map_sg()`` 可以合并相邻 entry，返回设备可见 DMA segment 数。
#. 驱动遍历设备段时应使用映射后的 DMA entry；unmap 时通常传入原始 ``nents``。
#. SG 映射返回段数可以小于原 scatterlist entry 数，这不是数据丢失。
#. 设备 segment 数、长度、边界和对齐仍受 queue limits 与硬件描述符格式限制。
#. DMA API 可以使用 bounce buffer，使低地址能力设备访问原本不可寻址的内存。
#. 使用 bounce 时，CPU pointer、真实物理页和设备 DMA address 更不应混同。
#. IOMMU 可以为分散物理页建立连续 IOVA，但驱动只能依赖 DMA API 返回的地址和长度合同。
#. DMA mapping 不自动分配业务 buffer；分配和映射是两个生命周期阶段。
#. DMA mapping 也不自动启动设备；驱动仍需填写 descriptor、barrier、doorbell 和设备寄存器。
#. 发布 descriptor 前应先完成所有 DMA mapping，失败时按逆序 unmap 已成功段。
#. 设备完成前不能 unmap、free、复用或把 buffer 归还其它 owner。
#. Completion IRQ 到达后，也应先确认硬件已停止访问对应 descriptor/buffer，再执行 unmap。
#. Request cancel 不等于设备已停止 DMA；取消路径必须等待硬件确认或 reset 后再回收内存。
#. Reset 路径可能让旧 DMA completion 迟到，驱动应通过 generation/tag 防止命中新对象。
#. 设备移除时应先停止新提交，再停止 DMA engine，等待在途访问结束，最后 unmap/free。
#. 仅释放 IRQ 不会停止设备 DMA；仅 unmap 也不会让设备自动停止使用旧地址。
#. 长期 pin 或注册大量 DMA buffer 会限制回收、迁移、NUMA 和内存热插拔。
#. 用户页用于 DMA 时，需要正确 pin、方向、dirty accounting 和解除 pin；精确 API 具有版本差异。
#. 设备向用户页写数据后，解除 pin 前可能需要标记页面 dirty，具体规则由使用的 pin/DMA 路径决定。
#. DMA API 调用通常以 ``struct device`` 为入口，因为 DMA mask、IOMMU domain 和架构后端属于具体设备。
#. 不能拿一个设备创建的 DMA mapping 给另一设备使用，除非明确通过共享框架重新映射。
#. DMA-BUF 等跨设备共享框架会为每个 attachment 管理各自映射，不等于共享一个裸 DMA address。
#. ``dma_map_resource()`` 面向设备可访问的资源地址，语义与普通系统 RAM buffer mapping 不同。
#. MMIO BAR 地址不能默认作为 streaming DMA buffer；设备对设备资源访问需要专用能力和拓扑支持。
#. DMA 地址写入 descriptor 时还要处理设备规定的字节序和位宽。
#. 32 位设备若收到截断的 64 位 DMA address，可能访问错误内存；不能只强制 cast 消除编译警告。
#. 描述符 ring 的 CPU producer/consumer 与设备 producer/consumer 需要独立的所有权协议。
#. Cache coherency、内存顺序和设备完成是三个不同层级：可见、先后、是否执行完成不能互相替代。
#. DMA debug 可发现方向、size、double unmap、未映射和错误 API 使用，但会有额外开销。
#. IOMMU fault 往往提示设备访问未映射/越权 IOVA，但根因可能是过早 unmap、地址截断或旧 descriptor。
#. 数据内容错误而无 fault 时，应检查 sync、cache line 共享、方向和设备写长度。
#. 设备 timeout 时应同时检查 descriptor 发布、DMA mapping 成功、doorbell 和 IRQ completion。
#. 精确 DMA ops、IOMMU 后端、bounce 策略和 cache maintenance 属于架构与版本敏感实现。
#. 稳定源码阅读顺序是：buffer 来源 → DMA mask → map → direction → descriptor 发布 → 设备完成 → sync/unmap → buffer 回收。

必背路径
--------

Streaming TX：

::

   CPU 构造发送 buffer
   → dma_map_single(..., DMA_TO_DEVICE)
   → 检查 dma_mapping_error
   → 把 DMA address/length 写入 descriptor
   → dma_wmb / 发布 owner 位
   → MMIO doorbell
   → 设备读取 buffer
   → completion
   → dma_unmap_single
   → 释放或复用 CPU buffer

Streaming RX 复用：

::

   分配 RX buffer
   → dma_map_single(..., DMA_FROM_DEVICE)
   → 发布 RX descriptor
   → 设备写入数据
   → completion
   → dma_sync_single_for_cpu
   → CPU 检查数据
   → 继续复用时 dma_sync_single_for_device
   → 重新发布 descriptor
   → 最终停止时 dma_unmap_single

Coherent Descriptor Ring：

::

   dma_alloc_coherent
   → 得到 CPU pointer 与 DMA address
   → 把 ring DMA address 配置给设备
   → CPU 写 descriptor 字段
   → dma_wmb 发布 valid/owner
   → 设备消费并更新 completion
   → dma_rmb 后 CPU 读取完成字段
   → 停止设备后 dma_free_coherent

安全 Teardown：

::

   阻止新请求
   → mask IRQ
   → 停止 DMA engine / queue
   → 等待设备 idle 与 completion 结束
   → synchronize IRQ 和 worker
   → unmap 所有 streaming mappings
   → free coherent rings/pools
   → 解除用户页 pin 和私有对象

必须区分
--------

* CPU Virtual Address 与 DMA Address：前者供 CPU 解引用；后者供设备/IOMMU 发起 DMA 请求。
* Streaming Mapping 与 Coherent Allocation：Streaming 围绕阶段性交接；coherent 适合长期共享控制结构。
* Cache Coherency 与 Memory Ordering：Coherency保证最新内容可见；barrier 保证字段按协议顺序发布。
* Sync 与 Unmap：Sync 在保留映射时切换访问权；unmap 结束这次设备访问授权。
* IRQ Completion 与 DMA 停止：中断是完成通知；回收前仍须确认设备不再访问对应内存。

一句话结论
----------

DMA mapping 的本质是给具体设备授予一段内存的限时访问权；CPU 地址、DMA 地址、方向、同步点和最终回收必须围绕同一 buffer 生命周期严格匹配。
