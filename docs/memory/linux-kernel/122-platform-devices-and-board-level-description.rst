第122章：Platform 设备与板级硬件描述
====================================

核心知识点
----------

Platform Bus 为非自枚举硬件建立身份
   SoC UART、GPIO、watchdog、clock、reset、PWM 和许多控制器无法通过统一协议自行报告存在，必须由固件或板级代码创建 ``platform_device``。

Platform 不是一种物理总线
   它是 Linux 为板级和片上设备提供的匹配与生命周期域。设备之间可能使用完全不同的寄存器、时钟和数据路径。

设备描述先于驱动注册
   Device Tree、ACPI、MFD、板级代码或其它框架先创建实例；``platform_driver`` 只声明如何匹配和控制已有设备。

Platform 对象连接固件与 Driver Core
   ``struct platform_device`` 嵌入 ``struct device`` 并携带 resource、fwnode、parent、DMA 属性和实例身份；``platform_driver`` 嵌入通用 driver 对象。

匹配来源具有多种形式
   OF ``compatible``、ACPI ID、``platform_device_id`` 和名称都可参与匹配。具体优先级会变化，稳定合同是固件身份与驱动支持表对齐。

Resource 只是硬件范围描述
   ``struct resource`` 可描述 MMIO、I/O port 或 IRQ 范围；驱动必须通过资源 helper 申请并映射，之后才能得到 ``__iomem`` 地址或 Linux IRQ。

Provider Framework 表达功能依赖
   Clock、reset、regulator、GPIO、pinctrl、power domain、PHY、DMA channel 和 IOMMU 通常通过 provider/consumer 关系取得，而不是全部塞入 resource 数组。

Probe 顺序受硬件手册支配
   常见过程是取得电源依赖、启用 clock、解除 reset、映射寄存器、初始化硬件、建立 IRQ/DMA，最后注册上层接口；实际顺序必须符合芯片状态机。

必需资源与可选资源必须分开
   缺少 required property 或资源应失败；optional helper 的缺失才可按约定忽略。不能把所有 ``-ENOENT`` 都当成可选情况。

延迟探测表示 Supplier 尚未就绪
   Clock、regulator、GPIO、PHY 等依赖返回 ``-EPROBE_DEFER`` 时，驱动应停止继续发布，并让 driver core 在条件变化后重试。

Managed Resource 只简化部分回收
   ``devm_*`` 可把 MMIO、IRQ 等资源归还绑定到 device 生命周期，但不会自动注销 netdev、cdev、子设备，也不会替代停止 DMA、work 和硬件中断源。

Platform Remove 必须撤销运行能力
   驱动应先关闭用户入口和新请求，排空 IRQ、DMA、timer、work，再按依赖逆序关闭硬件、电源和时钟。

关键路径
--------

固件节点到设备对象
   DT/ACPI 描述 compatible、地址、中断和依赖
   → 固件核心解析节点
   → 父层执行 population
   → 创建 ``platform_device``
   → 设置 resource、fwnode、parent 和 DMA 属性
   → Platform Bus 匹配 driver
   → 调用 ``probe``

典型 Probe 路径
   读取 match data 与属性
   → 获取 regulator/power domain
   → 获取并启用 clock
   → 配置 pinctrl、GPIO 与 reset
   → 获取并映射 MMIO
   → 获取 IRQ 与 DMA 能力
   → 初始化硬件
   → 申请 IRQ、启动数据路径
   → 注册上层功能对象

安全 Remove 路径
   设置 stopping
   → 注销功能接口与子设备
   → 阻止新事务
   → 停止 DMA 和设备中断源
   → 同步 IRQ、work、timer
   → 关闭硬件并恢复 reset 状态
   → 关闭 clock、regulator 与 power domain
   → 释放私有对象和最终引用

概念辨析
--------

Platform Device 与 Platform Driver
   Device 是已经描述出的硬件实例；driver 是支持某类实例的控制代码。

Resource 与 MMIO 映射
   Resource 说明地址范围；申请和 ``ioremap`` 后才得到可访问的 ``__iomem`` 指针。

设备存在与硬件可访问
   Sysfs 中存在 device 对象不表示 clock、电源或 reset 已处于允许寄存器访问的状态。

永久错误与 Probe Defer
   永久错误表示描述或能力不成立；``-EPROBE_DEFER`` 表示依赖可能稍后就绪。

Devm 与完整 Teardown
   Devres 负责归还已托管资源；外部接口、异步执行和硬件停止仍需驱动显式处理。

Platform Controller 与下挂设备
   I2C/SPI controller 可作为 platform device；其外设应进入对应协议总线，而不是全部扁平化为 platform device。

本章结论
--------

Platform Bus 把板级和片上硬件描述转换为可匹配设备对象。驱动正确性取决于固件资源、供应者依赖、上电顺序和退出顺序完整闭合。
