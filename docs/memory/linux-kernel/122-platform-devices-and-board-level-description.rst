第122章：Platform 设备与板级硬件描述
====================================

本章必须记住
------------

#. Platform bus 主要服务不能通过统一硬件协议自枚举、但已由板级设计或固件明确描述的设备。
#. 常见 platform device 包括 SoC UART、GPIO、I2C/SPI controller、watchdog、timer、PWM、clock、reset 和 interrupt controller。
#. Platform bus 不表示这些设备使用同一种电气总线，它是 Linux 为板级或固件描述设备提供的匹配与生命周期域。
#. ``struct platform_device`` 表示一个 platform 设备实例，并嵌入通用 ``struct device``。
#. ``struct platform_driver`` 表示能处理一类 platform 设备的驱动，并嵌入 ``struct device_driver``。
#. Platform 设备必须先由 Device Tree、ACPI、板级代码、MFD 子设备或其它内核框架创建，驱动注册本身不会凭空产生设备。
#. 非自发现设备的存在、地址和依赖来自硬件描述；驱动只消费这些事实，不能通过探测任意物理地址推断设备存在。
#. 典型路径是：firmware node → platform device → platform bus match → ``probe`` → 注册上层功能。
#. Device Tree 的 ``compatible``、ACPI ID、``platform_device_id`` 和设备名称是常见匹配输入。
#. 具体匹配优先级和 wrapper 细节具有版本差异，稳定结论是固件身份先与驱动支持表对齐，再进入 ``probe``。
#. ``probe(struct platform_device *pdev)`` 的输入已经包含设备模型身份、firmware node、parent、DMA 属性和资源描述。
#. ``platform_device`` 的 resource 数组常用于 MMIO、I/O port 和 IRQ；clock、reset、regulator、GPIO 等通常通过 provider framework 和 fwnode 查询。
#. ``struct resource`` 描述地址区间和资源类型，不是已经可直接解引用的寄存器指针。
#. MMIO 资源必须经 resource claim 和 ``ioremap`` 一类路径转换成 ``void __iomem *``，访问时使用 I/O accessor。
#. ``devm_platform_ioremap_resource()`` 一类 helper 可组合资源取得、范围检查和托管映射，具体可用 helper 以目标内核为准。
#. ``__iomem`` 是地址空间语义标记，不能把 MMIO 指针当普通 RAM 指针随意解引用或传给普通内存 API。
#. ``platform_get_irq()`` 把固件中断描述解析成 Linux IRQ 号，负返回值必须原样处理。
#. 得到 IRQ 号只说明路由已解析，驱动仍要申请 handler、配置硬件触发源并正确清除中断状态。
#. Clock 是设备工作频率和时序依赖，驱动通常先 ``clk_get``，再按硬件顺序 prepare/enable。
#. Reset controller 管理设备复位线，驱动必须根据手册决定 assert/deassert 与 clock、power 的顺序。
#. Regulator 表示电源轨，启用成功后也可能需要等待电压稳定或执行设备专用上电延迟。
#. GPIO descriptor 可能表示 enable、reset、chip-select、interrupt 或模式选择，方向和有效电平应来自 binding，而不是硬编码板级假设。
#. Pinctrl 决定引脚复用和电气状态，设备可在 default、sleep 等状态之间切换。
#. Power domain 和 runtime PM 决定设备何时真正有电；对象存在不表示寄存器在任意时刻都可访问。
#. IOMMU、DMA mask 和 coherent 属性也可以由固件层级和 parent 关系影响，不能只看设备私有节点。
#. Platform ``probe`` 的稳定初始化顺序通常是：取得依赖 → 上电/开时钟 → 解除复位 → 映射寄存器 → 初始化硬件 → 申请 IRQ/DMA → 注册功能。
#. 真实顺序必须服从设备手册，不能把通用模板机械套到所有 IP。
#. 依赖 provider 未就绪时，clock、reset、regulator、GPIO、PHY、IOMMU 等查询可能返回 ``-EPROBE_DEFER``。
#. ``-EPROBE_DEFER`` 是可重试依赖状态；永久缺少必要属性通常应返回明确错误。
#. 可选资源接口和必需资源接口必须区分，不能把任何 ``-ENOENT`` 都当作可忽略。
#. Firmware binding 决定某属性是 required、optional 还是 mutually exclusive；驱动必须与 binding 保持一致。
#. ``devm_*`` 把部分资源释放挂到 device 生命周期，减少 probe 失败回滚代码。
#. Devm 不会自动撤销 netdev、cdev、clock provider、子设备、工作线程或其它已经发布的业务对象。
#. 托管资源也不能替代正确停止硬件；IRQ 释放前仍应关闭设备中断源，DMA buffer 释放前仍应停止在途 DMA。
#. Platform driver 的 ``remove`` 应撤销 ``probe`` 建立的运行能力，而不是只等待 devres 自动释放内存。
#. 删除设备时应先阻止新请求，注销上层接口，停止 DMA/IRQ/work，再关闭 clock/power 并释放映射。
#. Parent platform device 可以创建多个子设备，例如 MFD core 把一个芯片拆成 GPIO、RTC、codec 等功能对象。
#. 子设备的资源范围和 parent 引用必须明确，不能让多个驱动无协调地控制同一寄存器或 IRQ。
#. Platform device name 与实例 id 可用于传统匹配和 sysfs 命名，但 firmware ``compatible`` 通常更稳定地表达硬件类型。
#. Board file 是由 C 代码直接创建 platform device 和 resource 的传统方式，容易把板级硬件事实固化进内核源码。
#. Device Tree 和 ACPI 把硬件连接转成数据描述，使同一驱动可服务多个板型而无需编译板级常量。
#. 从 board file 迁移到 DT/ACPI 不只是换语法，还要建立稳定 binding、provider 关系和资源命名。
#. Device Tree 适合声明式表达 SoC/板级拓扑；ACPI 常同时表达资源、方法、电源和平台控制语义。
#. 同一个 platform driver 可以通过通用 device property API 支持 DT 与 ACPI，但仍要验证两种描述的等价性。
#. ``status = "disabled"`` 的 DT 节点通常不会形成可用 platform device，精确 population 规则依父总线和内核实现。
#. 父节点未被 population、compatible 错误或地址 cell 解释错误，会导致设备对象根本不出现。
#. 设备对象出现但无 driver 时，应检查 OF/ACPI match table、名称、modalias 和模块加载链。
#. Driver 链接存在但 ``probe`` 失败时，应检查 MMIO、IRQ、clock、reset、regulator、GPIO 和 provider defer。
#. Resource 地址正确不表示硬件时钟已打开；IRQ 号正确也不表示触发类型与设备状态匹配。
#. Probe 中读芯片 ID 是驱动能力验证，不应被用来扫描未描述地址空间寻找未知硬件。
#. Platform 驱动不能假设资源编号在所有固件版本中永远一致，能使用按名称查询时应遵循 binding。
#. Resource 名称本身也属于 binding ABI，改变名称会破坏旧 DT/ACPI 与驱动兼容性。
#. Sysfs 中 platform 设备路径说明对象已被实例化，不代表所有 provider 依赖已经成功绑定。
#. Deferred probe 诊断应关联 consumer、supplier、firmware node 和错误码，不能只重复加载驱动。
#. Platform 总线通常不提供外设数据传输协议；数据面由设备 IP 驱动、MMIO、DMA 和其上层子系统定义。
#. I2C/SPI controller 可以是 platform device，而挂在 controller 下的 sensor/flash 应进入 I2C/SPI bus，不应全部扁平化为 platform device。
#. 稳定源码阅读顺序是：设备描述 → platform device 创建 → match table → ``probe`` 资源获取 → 上层注册 → remove。
#. ``platform_driver_probe()``、remove 回调签名和自动注销 helper 等精确接口具有版本差异，应以目标内核源码为准。
#. Platform 模型的核心不是“虚拟总线”，而是让板级事实获得可匹配、可观察、可引用和可释放的设备身份。

必背路径
--------

Device Tree 到 Platform：

::

   DT 节点描述 compatible、reg、interrupts 和依赖
   → 内核解析 firmware tree
   → 父总线 population
   → 创建 platform_device
   → 设置 resources、fwnode、parent 和 DMA 属性
   → platform bus match
   → 调用 platform_driver probe

Platform Probe：

::

   检查 match data 与设备属性
   → 获取 regulator/power domain
   → 获取并启用 clock
   → 控制 reset 和 GPIO/pinctrl
   → 获取并映射 MMIO
   → 获取 IRQ 与 DMA 能力
   → 初始化硬件状态
   → 申请 IRQ/启动 DMA
   → 注册 tty/net/input/clock 等功能接口

Probe 失败：

::

   某个必需资源返回错误
   → 区分永久错误与 EPROBE_DEFER
   → 不发布新的用户接口
   → 停止已启动硬件和异步路径
   → 逆序关闭 reset/clock/power
   → 让 devres 或显式路径释放资源
   → 返回原始错误码

Remove：

::

   设置 stopping
   → 注销上层功能和子设备
   → 阻止新传输
   → 停止 DMA 与设备中断源
   → 同步 IRQ、work、timer
   → 关闭设备并 assert reset
   → disable clock/regulator/power
   → 释放创建者引用和私有状态

诊断设备未出现：

::

   检查 firmware 节点是否存在并启用
   → 检查父总线是否 population
   → 检查地址和 cell/ranges 解释
   → 检查 platform device sysfs
   → 检查 modalias 与 match table
   → 检查 deferred probe 与 provider
   → 检查 probe 资源错误

必须区分
--------

Platform Device 与 Platform Driver
   前者是已描述的设备实例；后者是声明支持某类实例并实现控制逻辑的驱动。

Resource 描述与 MMIO 映射
   ``reg``/``struct resource`` 只描述范围；驱动经申请和映射后才获得 ``__iomem`` 地址。

必需资源与可选资源
   缺少必需资源必须失败；可选资源的缺失应按 binding 明确处理。

永久错误与 Probe Defer
   永久错误表示描述或硬件不成立；defer 表示 supplier 暂未准备好。

Devm 释放与完整 Remove
   Devres 归还托管资源；驱动仍要停止硬件、异步回调和已发布功能对象。

Platform Controller 与其下挂设备
   Controller 可是 platform device；挂在其协议总线上的外设应由 I2C、SPI 等总线模型表示。

一句话结论
----------

Platform bus 把无法自枚举的板级硬件描述转换成 ``platform_device``，驱动再按固件身份取得 MMIO、IRQ 与电源依赖，并以严格的上电和 teardown 顺序建立设备能力。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 25，Bus Frameworks Platform, PCI, USB, I2C, SPI, ACPI, and Device Tree；
* AIBook 章节：Chapter 122，Platform Devices and Board-Level Description；
* 源文件：``docs/LinuxK/Part_25_Bus_Frameworks_Platform_PCI_USB_I2C_SPI_ACPI_and_Device_Tree/Chapter_122_Platform_Devices_and_Board_Level_Description.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_25_Bus_Frameworks_Platform_PCI_USB_I2C_SPI_ACPI_and_Device_Tree/Chapter_122_Platform_Devices_and_Board_Level_Description.md>`_。