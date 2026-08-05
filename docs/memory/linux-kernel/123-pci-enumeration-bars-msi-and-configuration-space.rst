第123章：PCI 枚举、BAR、MSI 与配置空间
======================================

本章必须记住
------------

#. PCI/PCIe 是可枚举总线：平台先提供 host bridge 和配置空间访问，PCI core 再扫描 bus/device/function 并创建设备对象。
#. “可枚举”不等于完全自包含；host bridge、资源窗口、IOMMU、interrupt remapping 和固件保留区仍由平台提供。
#. PCI 配置空间用于发现和配置设备身份、BAR、command/status 与 capability，不是设备正常数据面的全部寄存器空间。
#. ``struct pci_dev`` 表示一个 PCI function，并嵌入 ``struct device`` 接入 driver core。
#. PCI 地址通常写作 domain:bus:device.function；该地址标识当前拓扑位置，不等于设备永久序列号。
#. PCI bridge 把多个 bus 连接成层级，扫描需要递归读取下游 bus number 和资源窗口。
#. PCI core 读取有效 vendor ID 后，继续取得 device ID、class code、header type、BAR 和 capability 链。
#. 扫描成功只证明 device object 已建立；驱动是否存在、是否匹配和 probe 是否成功属于后续阶段。
#. ``struct pci_device_id`` 是驱动支持声明，常见匹配字段包括 vendor、device、subvendor、subdevice、class 和 mask。
#. Vendor/device 匹配适合厂商专用硬件；class 匹配适合遵循标准编程接口的一类设备。
#. Subsystem ID 常用于区分同一芯片在不同板卡上的连线、固件或功能差异。
#. ``driver_data`` 可把匹配项映射到驱动内部能力表，driver core 不解释其内容。
#. ``MODULE_DEVICE_TABLE(pci, ...)`` 把 PCI ID table 导出为模块 alias，支持 modalias 自动加载。
#. ID table 命中只产生候选 driver；``probe`` 仍需验证 revision、capability、BAR 形态和设备状态。
#. 配置空间读写应使用 PCI helper 和符号定义，不能在驱动中随意硬编码偏移并绕过并发与架构规则。
#. Standard capability 与 PCIe extended capability 是两类链，MSI、MSI-X、PCIe、AER、SR-IOV 等能力位于相应结构中。
#. Capability 存在表示硬件声明支持，驱动仍需检查内核策略、资源和实际启用结果。
#. BAR 描述设备请求的 MMIO 或 I/O port 窗口；它提供大小、类型和地址属性，不说明寄存器语义。
#. 64-bit BAR 可能占用两个连续 BAR 槽位；prefetchable 属性影响资源和映射策略。
#. PCI core/firmware 为 BAR 分配系统地址后，结果保存在 ``pci_dev`` 的 resource 中。
#. 驱动应先启用设备、申请对应 BAR region，再建立 MMIO 映射，避免与其它驱动或资源冲突。
#. ``pci_enable_device*()`` 使设备进入可访问状态并配置 command bits，不能被当作申请 BAR 所有权的替代。
#. ``pci_request_regions()`` 或 managed variant 申请 BAR 资源所有权；``pci_iomap*()`` 一类接口建立内核虚拟映射。
#. BAR 起始地址是 CPU/PCI 资源地址，不是可直接普通解引用的 C 指针。
#. MMIO 映射应使用 ``readl/writel`` 等 accessor；posted write、字节序和 ordering 不能按普通 RAM 推断。
#. ``ioremap`` 返回地址也不能直接转换成设备 DMA 地址；CPU MMIO 和设备 DMA 是不同地址空间。
#. 驱动在申请 BAR 后应根据设备手册验证寄存器范围，不能越过 resource 长度访问隐藏区域。
#. PCI DMA 路径必须先设置 streaming/coherent DMA mask，再通过 DMA API 映射 buffer。
#. ``dma_set_mask_and_coherent()`` 成功表示平台可为该设备建立对应位宽映射，不表示所有物理页地址都可直接交给设备。
#. IOMMU 可把分散物理页映射成设备可见 IOVA，驱动仍必须遵守 DMA map/unmap 与同步规则。
#. PCI bus mastering 允许设备发起 DMA；启用 master 前应保证描述符、IOMMU 和错误路径已经准备好。
#. 设备停止和 remove 时，应先停止新 DMA、让硬件停止访问，再解除 DMA 映射和释放 buffer。
#. Legacy INTx 是共享电平中断模型；MSI/MSI-X 使用内存写消息投递中断，避免传统共享线语义。
#. MSI 通常提供一个或多个向量；MSI-X 提供更灵活的表项和向量分配，适合多队列设备。
#. 现代驱动应使用 ``pci_alloc_irq_vectors()`` 一类统一接口请求允许的 MSI-X/MSI/legacy 范围，具体 flags 以目标内核为准。
#. 请求多个向量只表达期望范围，实际返回数量可能更少；驱动必须按实际数量配置队列和 affinity。
#. 每个 MSI-X vector 可关联独立队列或事件，但硬件能力、CPU 数、IRQ domain 和系统策略会限制最终分布。
#. IRQ vector 数量不等于设备真实并行度；队列、DMA engine、固件和介质仍可能共享内部资源。
#. ``pci_irq_vector()`` 等 helper 把已分配向量索引转换成 Linux IRQ 号，驱动再申请 handler。
#. MSI/MSI-X 启用失败时可以按驱动设计回退到更少向量或 legacy INTx，不能假设所有平台都提供相同能力。
#. Shared INTx handler 必须判断中断是否来自本设备，并正确返回 ``IRQ_NONE`` 或 ``IRQ_HANDLED``。
#. MSI/MSI-X 通常不共享传统线，但 handler 仍要正确清除设备状态和同步队列完成。
#. Interrupt affinity、MSI-X vector、blk-mq/net queue 和 CPU NUMA 局部性应联合配置与观测。
#. PCIe AER 报告链路和事务错误；错误恢复可能进入 error_detected、slot_reset、resume 等驱动回调。
#. AER recovery、hot reset、function reset 和 remove 是不同状态机，不能用同一个布尔量粗暴表示。
#. Reset 会让寄存器、队列和 DMA 状态失效，驱动必须重新初始化并防止旧 completion 命中新 generation。
#. Function Level Reset 是否存在取决于 capability；即使支持，也不保证上层业务状态自动恢复。
#. PCI power state D0-D3 与 runtime/system PM 相关；设备对象存活不表示当前处于可访问 D0 状态。
#. Suspend 前要停止 DMA/IRQ 并保存必要状态；resume 后要恢复配置空间、BAR、队列和设备私有寄存器。
#. ``pci_save_state``/``pci_restore_state`` 只处理部分 PCI 配置状态，不能代替设备专用恢复。
#. Hotplug 移除时硬件可能突然消失，MMIO 读可能返回全 1 或总线错误，驱动必须先关闭入口并容忍失联。
#. ``lspci`` 显示配置空间和拓扑视图；sysfs ``resource``、``driver``、``enable`` 等提供内核对象证据。
#. ``lspci -k`` 能显示候选/当前驱动，但不能证明 ``probe`` 后所有队列和 DMA 都工作正常。
#. ``/sys/bus/pci/devices/<BDF>/resource`` 可观察 BAR 资源范围，不能说明寄存器布局含义。
#. ``/proc/interrupts`` 可观察向量计数；需结合 BDF、队列映射和 handler 名解释 MSI-X 分布。
#. 设备未出现时先查 host bridge、配置访问和枚举；设备出现无 driver 时再查 ID、alias 和模块。
#. Probe 失败应按启用、BAR、DMA、IRQ、固件和上层子系统的顺序定位。
#. 驱动错误路径通常按相反顺序撤销：上层接口 → IRQ → DMA/队列 → MMIO → BAR region → disable device。
#. Managed PCI API 可以简化部分回滚，但不会自动停止硬件 DMA、业务 work 和已发布接口。
#. 精确 PCI core 扫描函数、MSI domain、devres helper 和 AER 回调具有版本与架构差异。
#. 稳定源码阅读顺序是：配置空间枚举 → ``pci_dev`` → ID match → enable/BAR → DMA → IRQ → 上层注册 → reset/remove。
#. PCI 驱动真正的工程难点不在“找到设备”，而在完整管理 BAR、DMA、中断、电源、reset 和热拔插生命周期。

必背路径
--------

PCI 枚举：

::

   平台注册 PCI host bridge
   → 提供配置空间与资源窗口
   → PCI core 扫描 bus/device/function
   → 读取 vendor/device/class/header
   → 探测 BAR 与 capability
   → 创建 struct pci_dev
   → 接入 driver core 与 sysfs
   → 根据 ID table 尝试绑定

PCI Probe：

::

   pci_driver ID 命中
   → pci_enable_device
   → 设置 DMA mask
   → 申请 BAR regions
   → 映射 MMIO
   → 初始化设备并启用 bus master
   → 分配 MSI-X/MSI/legacy vectors
   → 申请 IRQ 和建立队列
   → 注册 net/block/DRM 等功能对象

MSI-X 多队列：

::

   请求 IRQ vector 范围
   → 内核返回实际 vector 数量
   → 按数量创建或缩减设备队列
   → vector 索引转换为 Linux IRQ
   → 申请 handler 并设置 affinity hint
   → 设备把每个队列事件写入对应 MSI-X entry
   → handler 完成队列并唤醒上层

错误恢复：

::

   AER/timeout 检测错误
   → 停止新请求和 DMA
   → 标记设备进入恢复 generation
   → reset function/link/slot
   → 恢复 PCI 配置与 BAR
   → 重建设备队列和 IRQ
   → 丢弃或验证旧 completion
   → 恢复上层功能或报告永久失败

安全 Remove：

::

   注销上层功能
   → 阻止新请求
   → 停止设备 DMA 与中断源
   → 同步并释放 IRQ vectors
   → 解除 DMA 映射和释放队列
   → unmap MMIO
   → release BAR regions
   → disable PCI device
   → 最后释放私有对象

必须区分
--------

配置空间与 BAR 寄存器空间
   配置空间用于标准发现和控制；BAR 映射设备专用运行寄存器。

设备枚举与驱动绑定
   枚举创建 ``pci_dev``；ID match 和 probe 决定哪个驱动接管。

BAR 资源地址与 MMIO 指针
   Resource 描述系统地址范围；映射后才得到 ``__iomem`` 访问地址。

CPU MMIO 地址与 DMA 地址
   CPU 经页表访问 BAR；设备 DMA 经 DMA API 使用总线/IOMMU 地址。

MSI-X 向量数与真实并行度
   向量提供独立通知通道；设备内部执行资源仍可能共享。

Reset 与 Remove
   Reset 目标是重建同一设备运行状态；remove 永久撤销绑定和所有功能入口。

一句话结论
----------

PCI core 先通过配置空间枚举并整理 ``pci_dev``，驱动再用 ID 表接管设备，完整正确性取决于 BAR、DMA、MSI、电源、reset 与热拔插资源按同一生命周期闭合。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 25，Bus Frameworks Platform, PCI, USB, I2C, SPI, ACPI, and Device Tree；
* AIBook 章节：Chapter 123，PCI Enumeration, BARs, MSI, and Configuration Space；
* 源文件：``docs/LinuxK/Part_25_Bus_Frameworks_Platform_PCI_USB_I2C_SPI_ACPI_and_Device_Tree/Chapter_123_PCI_Enumeration_BARs_MSI_and_Configuration_Space.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_25_Bus_Frameworks_Platform_PCI_USB_I2C_SPI_ACPI_and_Device_Tree/Chapter_123_PCI_Enumeration_BARs_MSI_and_Configuration_Space.md>`_。