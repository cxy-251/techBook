第133章：DMA Mapping、Streaming DMA 与 Consistent DMA
====================================================

核心知识点
----------

DMA 是设备访问内存的授权协议
   CPU 准备 buffer 和描述符，DMA API 为具体设备建立可访问地址，设备执行传输，完成后驱动再收回访问权。

三类地址必须分开
   CPU virtual address 供内核解引用；CPU physical address 表示物理页位置；``dma_addr_t`` 是设备可见地址，可能经过 IOMMU、host bridge 或 bounce buffer 转换。

DMA address 不能由驱动猜测
   普通驱动不得把 ``virt_to_phys`` 结果直接写给设备。必须使用以 ``struct device`` 为上下文的 DMA API，因为 mask、domain 和架构后端都属于具体设备。

DMA mask 约束设备寻址能力
   ``dma_set_mask_and_coherent()`` 应在 probe 早期建立设备可表达的地址宽度。截断较宽 DMA address 会让设备访问错误内存。

Streaming mapping 表达阶段性交接
   ``dma_map_single/page/sg`` 适合一次或一段时间的传输。Map 成功后到 sync/unmap 前，CPU 与设备必须按 direction 和所有权协议访问 buffer。

Direction 是执行语义
   ``DMA_TO_DEVICE`` 表示设备读取 CPU 准备的数据；``DMA_FROM_DEVICE`` 表示设备写入后由 CPU 读取；``DMA_BIDIRECTIONAL`` 只用于真实双向访问。

映射失败必须立即处理
   ``dma_map_*`` 返回后要检查 ``dma_mapping_error()``。无效地址不能写入 descriptor，部分成功的 SG 或多段映射要逆序回滚。

Sync 与 Unmap 职责不同
   ``dma_sync_*_for_cpu/device`` 在保留映射时切换访问权；``dma_unmap_*`` 结束设备对该 DMA address 的授权。

Coherent allocation 适合长期共享控制结构
   ``dma_alloc_coherent()`` 同时返回 CPU pointer 和 DMA address，常用于 descriptor ring、mailbox 和 command queue。

Coherent 不等于有序
   Cache 可见性由平台维护，不代表多个字段自动按协议顺序发布。CPU 写完 descriptor 后仍可能需要 ``dma_wmb()``，观察 completion 后可能需要 ``dma_rmb()``。

SG 映射会重塑段
   ``dma_map_sg()`` 可以合并相邻 entry，返回的设备段数可能小于原始 ``nents``。驱动应遍历映射后的 DMA segment，而 unmap 通常使用原始 entry 数。

并非所有内存都能直接 DMA
   栈对象生命周期太短；``vmalloc`` 仅虚拟连续；分页数据应使用 page/SG API。Buffer 分配和 DMA mapping 是两个独立生命周期阶段。

Completion 前不能回收
   设备完成并停止访问前，buffer 不能 unmap、free、复用或转交其它 owner。取消请求、释放 IRQ 或收到 timeout 都不自动意味着 DMA 已停止。

Teardown 先停 engine 再撤销映射
   先阻止新提交、停止 DMA engine、等待 idle 和 completion，再同步 IRQ/worker，最后 unmap streaming buffer、释放 coherent ring 和解除用户页 pin。

关键路径
--------

Streaming TX：

::

   CPU 构造 buffer
   → dma_map(..., DMA_TO_DEVICE)
   → 检查 mapping error
   → 写 DMA address/length 到 descriptor
   → dma_wmb 并发布 owner
   → MMIO doorbell
   → 设备读取 buffer
   → completion
   → dma_unmap
   → 释放或复用 buffer

Streaming RX 复用：

::

   分配 RX buffer
   → dma_map(..., DMA_FROM_DEVICE)
   → 发布 descriptor
   → 设备写入数据
   → completion
   → dma_sync_for_cpu
   → CPU 读取数据
   → dma_sync_for_device 后重新发布
   → 最终 dma_unmap

Coherent ring：

::

   dma_alloc_coherent
   → 获得 CPU pointer 与 DMA address
   → 配置 ring 基址
   → CPU 写 descriptor 字段
   → dma_wmb
   → 发布 valid/owner
   → 设备完成并写状态
   → dma_rmb 后 CPU 读取结果
   → 停止设备后 dma_free_coherent

概念辨析
--------

* CPU virtual address 与 DMA address：前者供 CPU 使用；后者供设备或 IOMMU 使用。
* Streaming mapping 与 coherent allocation：前者围绕阶段性交接；后者适合长期共享控制内存。
* Cache coherency 与 memory ordering：前者保证双方看见最新内容；后者保证字段按协议先后出现。
* Sync 与 unmap：Sync 暂时切换 owner；unmap 结束当前映射授权。
* IRQ completion 与 DMA stop：中断是通知；回收前仍须确认设备不再访问内存。

本章结论
--------

DMA mapping 的本质是向具体设备授予一段内存的限时访问权。地址、direction、sync、descriptor 发布、completion 与最终回收必须围绕同一 buffer 生命周期严格配对。
