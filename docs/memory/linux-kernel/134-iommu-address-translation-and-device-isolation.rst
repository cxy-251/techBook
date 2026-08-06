第134章：IOMMU、地址转换与设备隔离
==================================

核心知识点
----------

IOMMU 管理设备地址空间
   CPU MMU 翻译 CPU 虚拟地址；IOMMU 翻译设备发出的 IOVA/DMA address，并执行页表、权限和隔离检查。

IOVA 不是 CPU 地址
   IOVA 属于设备视角，既不是 CPU virtual address，也不必等于 CPU physical address。驱动只应使用 DMA API 返回的 ``dma_addr_t``。

Domain 保存翻译与权限状态
   ``struct iommu_domain`` 表示一组设备可见页表、地址空间和访问权限。设备先 attachment 到 domain，单次 DMA mapping 再在其中建立授权窗口。

DMA API 是普通驱动入口
   ``dma_map_*()`` 根据 ``struct device`` 选择 DMA mask、IOMMU domain 和后端。``iommu_map/unmap`` 属于更低层接口，普通驱动不应绕过 DMA API。

Direction 可以转化为权限
   ``DMA_TO_DEVICE`` 通常需要设备读权限，``DMA_FROM_DEVICE`` 通常需要设备写权限。Direction 错误在严格平台上可能直接产生 IOMMU fault。

连续 IOVA 不代表连续物理页
   IOMMU 可以把分散页映射成连续设备地址，但设备 segment、长度、边界和 DMA mask 约束仍然存在。

Mapping 是限时授权
   Unmap 会撤销设备访问。设备若仍使用旧 IOVA，会产生 fault 或数据破坏，因此必须先确认 DMA engine 和旧 descriptor 已停止。

Group 表达最小安全隔离边界
   IOMMU group 由 requester ID、桥和 ACS 等拓扑决定，表示无法被软件安全拆分的设备集合，不是性能队列或进程。

VFIO 依赖完整隔离合同
   设备直通需要 group/domain、用户内存映射、IRQ remapping、reset 隔离和 host driver 解绑共同成立，不能只检查“系统已开启 IOMMU”。

Translated、identity 与 bypass 不同
   系统存在 IOMMU 不表示每个设备都处于严格 translated domain。Identity mapping、passthrough 或 bypass 会提供不同的地址与隔离语义。

IOMMU 不负责 cache coherency
   地址翻译只决定设备访问哪一页；CPU/设备何时看到最新内容仍由 DMA sync、coherency 和 barrier 协议保证。

映射与 IOTLB 有性能成本
   高频短生命周期 map/unmap 会增加 IOVA 分配、页表更新和失效开销。长期映射减少热路径成本，也会长期占用地址空间与内存。

Fault 必须按设备时间线解释
   日志中的 device/requester、IOVA、方向和原因要映射回具体 queue、descriptor 和 mapping 生命周期，不能拿 IOVA 去查进程虚拟地址。

没有 Fault 不代表 DMA 正确
   Bypass、过宽映射或合法窗口内越界可能不触发 IOMMU fault。DMA API debug、descriptor 证据和数据校验仍然必要。

关键路径
--------

普通 DMA 映射：

::

   驱动持有 CPU buffer
   → dma_map_single(dev, ...)
   → DMA backend 分配 IOVA
   → domain 建立 IOVA→physical 映射
   → 返回 dma_addr_t
   → 驱动发布 descriptor
   → 设备向 IOVA 发起 DMA
   → IOMMU 检查权限并翻译
   → 完成后 dma_unmap_single

IOMMU Fault 诊断：

::

   保存 device、IOVA、方向和原因
   → 映射到 BDF/platform device/queue
   → 查找当前 mapping 生命周期
   → 检查 direction 与权限
   → 检查长度、边界和地址截断
   → 检查提前 unmap/free
   → 检查 reset/teardown 后旧 DMA
   → 对齐 descriptor 与 generation

安全移除：

::

   阻止新请求
   → mask IRQ
   → 停止 DMA engine 并确认 idle
   → 等待 completion 和 worker
   → unmap 所有 IOVA
   → 释放 coherent/pinned memory
   → detach/release domain 关系
   → 释放设备对象

概念辨析
--------

* IOVA 与 CPU physical address：前者是设备请求地址；IOMMU 将其翻译到物理页。
* IOMMU domain 与 IOMMU group：Domain 保存翻译和权限；group 表示最小安全隔离设备集合。
* Address translation 与 cache coherency：前者决定访问哪一页；后者决定双方看到哪一版内容。
* Mapping 存在与设备已停止：页表授权仍在不代表设备正在使用；撤销映射也不会主动停止硬件。
* IOMMU enabled 与 strict isolation：启用基础设施不代表所有设备都处于独立 translated domain。

本章结论
--------

IOMMU 把设备 DMA 变成受 domain 页表和权限约束的地址空间访问。安全性依赖设备身份、IOVA mapping、访问权限、group 边界和硬件停止顺序完整闭合。
