第121章：总线框架作为驱动匹配与资源模型
========================================

核心知识点
----------

总线框架定义设备合同
   Linux 中的 bus 不只是数据传输通道，而是设备发现、身份表示、驱动匹配、资源交付、事件通知和移除规则的组合模型。

Driver Core 只统一公共骨架
   ``struct device``、``struct device_driver``、引用计数、sysfs、uevent 和绑定状态由 driver core 管理；地址、传输、错误和热插拔语义仍由具体总线解释。

设备发现先于驱动匹配
   PCI、USB 可通过协议枚举设备；platform、I2C、SPI 常依赖 ACPI、Device Tree 或板级描述创建设备对象。不存在 device 时，驱动 ID 表不会触发 ``probe``。

总线专用对象承载真实身份
   ``pci_dev``、``usb_interface``、``i2c_client``、``spi_device`` 和 ``platform_device`` 都嵌入通用 ``struct device``，并补充各自的地址、描述符、资源和协议状态。

Match 与 Probe 是两个阶段
   ``match`` 只判断某个 driver 是否是候选控制者；``probe`` 才申请资源、初始化硬件、建立私有状态并发布用户可见功能。

匹配表连接身份与代码
   PCI ID、USB descriptor、OF ``compatible``、ACPI ID 和总线专用 ID table 表达不同身份体系。``MODULE_DEVICE_TABLE()`` 可把这些表导出为模块 alias。

Modalias 只负责候选模块发现
   设备 uevent 提供 ``MODALIAS``，用户空间据此加载候选模块；模块加载后仍必须完成 driver 注册、bus match 和 probe。

资源在 Probe 前应已被描述
   MMIO、IRQ、DMA 限制、clock、reset、regulator、GPIO、IOMMU、endpoint、adapter 地址或 chip-select 等信息应先进入 device/fwnode/bus 对象。

资源描述不等于资源所有权
   总线或固件说明资源在哪里，驱动在 ``probe`` 中申请、映射、启用并承担错误回滚责任。取得 IRQ 号不等于 handler 已注册，取得 resource 也不等于 MMIO 已映射。

依赖未就绪可触发延迟探测
   Clock、regulator、PHY、IOMMU 等 supplier 尚未注册时，consumer 可返回 ``-EPROBE_DEFER``。延迟探测应尽量发生在发布外部接口之前。

总线模型塑造数据路径
   USB 围绕 interface、endpoint 和 URB；I2C 围绕 adapter、client 和 message；SPI 围绕 controller、chip-select 和 transfer；PCI/platform 常围绕 MMIO、DMA、IRQ 与设备队列。

移除必须遵循总线特定协议
   Driver core 负责撤销绑定关系，驱动仍需停止新请求，取消或等待在途传输，收束 IRQ、DMA、work 和旧引用，再释放实例资源。

关键路径
--------

设备绑定路径
   硬件枚举或固件实例化
   → 创建总线专用宿主对象
   → 初始化内嵌 ``struct device``
   → 设置 bus、parent、fwnode 与资源
   → 注册 device
   → 注册或发现候选 driver
   → ``bus->match``
   → 总线 Probe 包装层
   → 驱动 ``probe`` 建立功能

模块自动加载路径
   驱动定义设备 ID 表
   → ``MODULE_DEVICE_TABLE()`` 导出 alias
   → 设备注册并产生 ``MODALIAS``
   → 用户空间加载候选模块
   → 模块注册 driver
   → bus 重新执行匹配与探测

设备移除路径
   总线检测移除或收到 unbind
   → 设置 stopping/disconnected
   → 阻止新 open 与新传输
   → 注销 class/子系统入口
   → 取消或等待总线专用请求
   → 停止 IRQ、DMA 和硬件
   → 驱动 ``remove`` 完成资源回收
   → 撤销绑定和 sysfs 关系
   → 最后引用归零后释放对象

概念辨析
--------

设备发现与驱动匹配
   发现负责创建设备对象；匹配只在已经存在的 device 与 driver 之间选择候选关系。

Match 与 Probe
   Match 比较身份；probe 建立实际硬件能力、私有状态和用户接口。

资源描述与资源占有
   Firmware/bus 描述地址和依赖；驱动负责申请、启用、同步和释放。

Bus 与 Class
   Bus 定义设备来源和驱动匹配域；class 按 block、net、tty、input 等用户功能重新组织对象。

Modalias 与成功绑定
   Modalias 只能帮助加载模块；最终是否可用取决于 match、probe、资源和硬件状态。

公共设备模型与总线专用语义
   Driver core 统一生命周期外壳；传输单位、错误码、取消和热插拔边界仍由具体总线决定。

本章结论
--------

总线框架把设备来源、身份、资源和移除规则收敛为驱动合同。阅读驱动时应先确认设备怎样被创建，再进入匹配、``probe`` 和运行数据路径。
