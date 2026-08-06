第123章：PCI 枚举、BAR、MSI 与配置空间
======================================

核心知识点
----------

PCI 是可枚举总线
   平台先提供 host bridge、配置空间访问和资源窗口，PCI core 再扫描 bus/device/function，读取身份与能力并创建 ``struct pci_dev``。

可枚举不等于脱离平台描述
   Host bridge、IOMMU、interrupt remapping、NUMA、保留内存和热插拔控制仍可能依赖 ACPI、Device Tree 或平台固件。

配置空间负责标准发现与控制
   Vendor ID、device ID、class、command/status、BAR 和 capability 位于配置空间；设备运行期私有寄存器通常位于 BAR 映射的 MMIO 空间。

``pci_dev`` 表示一个 PCI Function
   Domain:bus:device.function 标识当前拓扑位置。该地址适合定位运行对象，但不等于跨重插永久不变的设备序列号。

ID 表只声明候选兼容性
   ``struct pci_device_id`` 可匹配 vendor、device、subsystem 和 class。命中后仍要由 ``probe`` 验证 revision、capability、BAR 形态与设备状态。

BAR 描述地址窗口需求
   BAR 表达 MMIO 或 I/O port 类型、大小和属性；PCI core/firmware 分配系统地址后，驱动仍需启用设备、申请 region 并建立映射。

MMIO 地址与 DMA 地址属于不同空间
   BAR 映射得到 CPU 可访问的 ``__iomem`` 指针；设备访问内存时必须经过 DMA API，使用 bus/IOMMU 可见地址。

DMA 能力必须先建立
   驱动应设置 streaming/coherent DMA mask，准备描述符和错误路径后再启用 bus mastering。停止设备时则先终止 DMA，再解除映射和释放缓冲区。

MSI 与 MSI-X 提供消息中断
   Legacy INTx 是共享电平中断；MSI/MSI-X 通过内存写消息投递中断。MSI-X 更适合把多个队列分配到独立向量。

向量数量是协商结果
   ``pci_alloc_irq_vectors()`` 请求一个范围，实际返回数量可能更少。驱动必须按实际向量数缩放队列、handler 和 affinity 设计。

中断向量不等于设备并行度
   多向量只提供多个通知通道；DMA engine、firmware、队列和介质仍可能共享内部执行资源。

Reset、PM 与 Remove 是不同状态机
   Reset 目标是重建同一设备实例；suspend/resume 改变电源与运行状态；remove 永久撤销绑定和外部功能。

关键路径
--------

PCI 枚举路径
   平台注册 PCI host bridge
   → 提供配置空间和资源窗口
   → PCI core 扫描 bus/device/function
   → 读取 vendor、device、class 和 header
   → 解析 BAR 与 capability
   → 创建 ``pci_dev``
   → 注册到 Driver Core 与 sysfs
   → 按 ID 表尝试绑定

PCI Probe 路径
   ID 表命中
   → ``pci_enable_device()``
   → 设置 DMA mask
   → 申请 BAR region
   → 映射 MMIO
   → 初始化设备并启用 bus master
   → 分配 MSI-X/MSI/INTx 向量
   → 申请 IRQ、建立 DMA 队列
   → 注册 net/block/DRM 等功能对象

错误恢复路径
   AER、timeout 或设备异常
   → 停止新请求和 DMA
   → 标记新的恢复 generation
   → reset function/link/slot
   → 恢复配置空间与 BAR
   → 重建 IRQ、队列和设备寄存器
   → 拒绝旧 generation completion
   → 恢复上层功能或报告永久失败

安全 Remove 路径
   注销上层功能
   → 阻止新请求
   → 停止 DMA 和设备中断源
   → 同步并释放 IRQ 向量
   → 解除 DMA 映射并释放队列
   → unmap MMIO
   → release BAR region
   → disable device
   → 释放私有对象

概念辨析
--------

配置空间与 BAR 空间
   配置空间用于标准枚举和控制；BAR 映射设备专用运行寄存器或窗口。

枚举与绑定
   枚举创建 ``pci_dev``；ID match 和 probe 决定哪个驱动真正接管。

BAR Resource 与 MMIO 指针
   Resource 是系统地址范围；映射后才得到可通过 I/O accessor 使用的 ``__iomem`` 指针。

CPU MMIO 与设备 DMA
   CPU 通过页表访问 BAR；设备通过 DMA API 和 IOMMU 地址访问内存。

MSI-X 向量与硬件队列
   向量是通知资源；队列是数据路径执行资源，两者可以关联但并非同一对象。

Reset 与 Remove
   Reset 重建运行状态并继续使用同一实例；remove 收束所有入口并结束绑定生命周期。

本章结论
--------

PCI core 负责从配置空间发现并组织设备，驱动则必须把 BAR、DMA、MSI、电源、错误恢复和热插拔纳入同一资源生命周期。
