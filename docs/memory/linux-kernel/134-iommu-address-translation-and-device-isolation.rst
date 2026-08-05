第134章：IOMMU、地址转换与设备隔离
==================================

本章必须记住
------------

#. IOMMU 位于设备 DMA 请求与系统内存之间，为设备提供地址翻译、权限检查和隔离。
#. CPU MMU 翻译 CPU 虚拟地址；IOMMU 翻译设备发出的 IOVA/DMA address。
#. IOVA 是设备视角地址，不是 CPU virtual address，也不必等于 CPU physical address。
#. 普通驱动通常只调用 DMA API，由 DMA mapping 层和 IOMMU core 建立设备映射。
#. ``struct iommu_domain`` 表示一组设备可见地址空间、页表和权限状态。
#. 设备必须 attachment 到某个 domain，之后 DMA 请求才按该 domain 的映射和权限处理。
#. Domain attachment 的生命周期通常长于单次 DMA mapping；每次 map 只在当前 domain 中建立映射窗口。
#. ``dma_map_*()`` 的 ``struct device`` 参数决定使用哪个 DMA mask、IOMMU domain 和后端。
#. ``dma_addr_t`` 在启用 IOMMU 时通常是 IOVA；驱动只应依赖 DMA API 合同，不能猜物理地址。
#. ``iommu_map()``、``iommu_unmap()`` 是 IOMMU core 的低层操作，普通设备驱动不应绕过 DMA API直接管理。
#. IOMMU 映射需要 IOVA、物理页、长度、页粒度和读写权限全部匹配。
#. ``DMA_TO_DEVICE`` 通常要求设备读权限；``DMA_FROM_DEVICE`` 通常要求设备写权限。
#. Direction 错误可能在严格 IOMMU 平台上表现为权限 fault，而不是静默数据错误。
#. IOMMU 能把不连续物理页映射成连续 IOVA，但仍受设备 segment、长度和边界限制。
#. 连续 IOVA 不表示连续物理内存，也不表示 CPU 获得连续虚拟映射。
#. IOMMU aperture、保留区和设备 DMA mask 共同限制可分配 IOVA 范围。
#. 32 位 DMA 设备即使系统内存位于高地址，也可能借助 IOMMU/bounce 获得可表达的低 IOVA。
#. 映射失败时必须检查 ``dma_mapping_error()``，不能继续把无效地址提交给设备。
#. Unmap 撤销设备访问授权；设备仍在使用旧 IOVA 时 unmap 会触发 fault 或数据损坏。
#. 过早 unmap、重复 unmap、长度错误和 direction 不匹配是常见 fault 根因。
#. 设备 reset 后旧 descriptor 仍可能发出 DMA，请在撤销 mapping 前确认 DMA engine 真正停止。
#. IOMMU 提供隔离能力，但隔离粒度取决于硬件拓扑、requester ID 和 IOMMU group。
#. IOMMU group 表示无法被软件安全拆分的最小设备隔离集合，常受 PCIe ACS、桥和平台拓扑影响。
#. Group 不是性能队列，也不是一个进程；它表达设备间 DMA 隔离边界。
#. 两个 function 位于同一 group 时，设备直通通常需要把整个 group 作为安全单元处理。
#. SR-IOV VF 是否能独立隔离取决于 requester ID、ACS、IOMMU 和平台实现，不能只看 sysfs function 数量。
#. VFIO 使用 IOMMU group/domain 将设备 DMA 限制到用户空间显式映射的内存。
#. IOMMUFD 是较新的用户空间 I/O 地址空间管理接口，具体能力和对象模型具有版本边界。
#. Passthrough 模式可能减少翻译成本，但弱化或取消 DMA 隔离，不能当作无风险性能开关。
#. Identity mapping 让 IOVA 与物理地址数值接近，但仍可能有权限、保留区和平台限制。
#. IOMMU 开启不等于所有设备都在严格 translated domain；需检查实际 domain/type 和内核配置。
#. 部分设备可能 bypass IOMMU、使用 identity domain 或因平台限制不能被 remap。
#. IOMMU 不解决 CPU cache coherency；地址翻译正确后仍需 DMA API 同步和内存顺序。
#. IOMMU 也不保证设备协议正确；错误长度、越界 descriptor 和固件 bug 仍可访问被映射窗口内的错误位置。
#. 映射粒度和 IOTLB 会影响性能；大量短生命周期 mapping 会增加 IOVA 分配、页表和失效成本。
#. Streaming DMA map/unmap 可以触发 IOMMU map/unmap 和 IOTLB invalidation，具体优化由后端决定。
#. 长期 coherent ring 通常保持稳定 IOVA，减少热路径映射开销，但会长期占用地址空间和内存。
#. Batch mapping、SG mapping 和固定 buffer 可减少映射频率，但扩大生命周期与内存占用。
#. Device TLB/IOTLB 缓存设备地址翻译，unmap 后必须完成必要 invalidation 才能安全重用 IOVA。
#. 驱动通常不直接执行 IOTLB flush；IOMMU/DMA 后端负责映射可见性和失效顺序。
#. ATS 允许部分 PCIe 设备缓存地址翻译，PASID/SVA 可提供更细地址空间语义，均属硬件与版本敏感能力。
#. SVA/PASID 让设备请求关联进程地址空间时，页错误、进程退出和设备取消路径更复杂。
#. 不能从“支持 ATS/PASID”推断设备可任意访问进程地址；仍受绑定、权限和生命周期管理。
#. IOMMU fault 是设备 DMA 地址空间异常，常包含设备身份、地址、访问方向和原因。
#. Intel 平台日志常出现 DMAR，AMD 平台常见 AMD-Vi，Arm 常见 SMMU；字段格式随硬件驱动变化。
#. Fault address 应按 IOVA 解释，不要直接当作 CPU virtual address 在进程 maps 中查找。
#. Fault 中的 requester/device identity 应先映射回 PCI BDF、platform device 或具体 queue。
#. Read fault 常对应设备读取无权限/未映射内存；write fault 常对应设备写入无权限/未映射内存。
#. Fault 地址在合法 mapping 边界附近时，应检查长度、segment、off-by-one 和 descriptor 编码。
#. Fault 指向已释放区域时，应检查提前 unmap、旧 completion、reset race 和对象复用。
#. Fault 随高负载出现时，应检查 ring wrap、producer/consumer、tag 重用和并发 teardown。
#. 没有 fault 也不证明 DMA 正确；bypass、宽映射或同 domain 内越界可能不触发隔离错误。
#. IOMMU strict/lazy invalidation 策略影响 fault 时机和性能，精确选项依内核与平台。
#. DMA API debug 与 IOMMU fault 是互补证据：前者检查 API 生命周期，后者报告设备硬件访问异常。
#. Sysfs ``iommu_group`` 链接可观察 group；启动日志和内核参数可确认 IOMMU 是否启用。
#. ``lspci -t/-vv``、sysfs driver/group、IOMMU 日志可共同还原设备拓扑与隔离边界。
#. 虚拟机直通故障应区分 guest IOVA、host IOVA、VFIO mapping 和最终物理页多个层级。
#. 设备直通前还需处理 BAR、IRQ remapping、reset isolation 和 host driver unbind，不只 DMA domain。
#. Interrupt remapping 与 DMA remapping 是相关但不同能力；IOMMU 名称不能概括所有中断隔离细节。
#. Shared group 中任一设备可影响同一隔离边界，因此安全判断不能只审查目标 function。
#. IOMMU 自身页表和命令队列也有生命周期，系统 suspend/resume/reset 时需由核心重建。
#. Resume 后设备若恢复旧 DMA 地址而 domain 映射尚未恢复，会触发 fault 或超时。
#. 热拔插时应先停止设备 DMA，再解除 domain/mapping，最后移除对象。
#. ``iommu_detach_device`` 或 group teardown 不会替驱动停止硬件发出的请求。
#. 精确 domain 类型、group 形成、IOTLB、ATS/PASID 和 fault API 属于版本/硬件敏感实现。
#. 稳定源码阅读顺序是：设备身份 → DMA API → domain attachment → IOVA mapping → device request → fault/unmap → teardown。

必背路径
--------

普通 DMA 映射经过 IOMMU：

::

   驱动持有 CPU buffer
   → dma_map_single(dev, ...)
   → DMA backend 选择 IOVA
   → IOMMU domain 建立 IOVA→physical 映射
   → 返回 dma_addr_t
   → 驱动写入 descriptor
   → 设备向 IOVA 发起 DMA
   → IOMMU 检查权限并翻译
   → 访问系统 RAM
   → 完成后 dma_unmap_single

IOMMU Fault 诊断：

::

   保存 fault 日志中的设备、IOVA、读写方向和原因
   → 映射到 PCI BDF / platform device / queue
   → 查找当前 DMA mapping 生命周期
   → 检查 direction 与权限
   → 检查长度、边界和地址截断
   → 检查是否提前 unmap/free
   → 检查 reset/teardown 后旧 DMA
   → 对齐 descriptor、IRQ 和对象 generation

VFIO 直通：

::

   确认 IOMMU group 隔离边界
   → 从 host driver 解绑设备
   → 建立 VFIO/IOMMUFD context
   → 把 group/device 接入受控 domain
   → 用户映射 guest/user memory 为 IOVA
   → 设备只访问已授权窗口
   → 注入/路由中断
   → 停止设备后撤销映射和绑定

安全移除：

::

   阻止新请求
   → mask IRQ
   → 停止并确认 DMA engine idle
   → 等待 completion/worker
   → unmap 所有 IOVA
   → 解除长期 coherent/pinned memory
   → detach/release domain 关系
   → 释放设备对象

必须区分
--------

IOVA 与 CPU Physical Address
   IOVA 是设备请求地址；IOMMU 将它翻译到物理页，数值不必相同。

IOMMU Domain 与 IOMMU Group
   Domain 是翻译与权限状态；group 是最小安全隔离设备集合。

地址翻译与 Cache Coherency
   IOMMU 决定访问哪一页；DMA coherency 决定 CPU/设备何时看见最新内容。

Mapping 存在与设备已停止
   Unmap 前必须确认设备不再使用 IOVA；撤销页表不会主动停止硬件。

IOMMU 启用与严格隔离
   系统存在 IOMMU 不代表每个设备都处于 translated、独立、安全 domain。

一句话结论
----------

IOMMU 把设备 DMA 变成受 domain 页表和权限约束的地址空间访问；可靠性要求设备身份、IOVA mapping、权限和硬件停止顺序在同一生命周期中严格闭合。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 27，IRQ, DMA, MMIO, IOMMU, Cache Coherency, and Hardware Resources；
* AIBook 章节：Chapter 134，IOMMU, Address Translation, and Device Isolation；
* 源文件：``docs/LinuxK/Part_27_IRQ_DMA_MMIO_IOMMU_Cache_Coherency_and_Hardware_Resources/Chapter_134_IOMMU_Address_Translation_and_Device_Isolation.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_27_IRQ_DMA_MMIO_IOMMU_Cache_Coherency_and_Hardware_Resources/Chapter_134_IOMMU_Address_Translation_and_Device_Isolation.md>`_。