第121章：总线框架作为驱动匹配与资源模型
========================================

本章必须记住
------------

#. Linux bus framework 不是单纯的数据传输接口，而是设备发现、身份匹配、资源描述、驱动绑定和生命周期管理的组合模型。
#. Driver core 统一管理 ``struct device``、``struct device_driver``、引用、sysfs、uevent 和绑定骨架；各总线负责解释设备怎样出现以及什么叫匹配。
#. 分析任何驱动前，先回答四个问题：设备由谁创建、匹配依据是什么、``probe`` 前已有何种资源、设备移除由谁通知。
#. ``struct bus_type`` 表示一个 device 与 driver 的匹配域，常见职责包括 ``match``、``probe`` 包装、``remove``、uevent、DMA 和电源管理协作。
#. Bus 的发现语义和匹配语义必须分开：设备先要被枚举或实例化，之后才有机会与驱动匹配。
#. PCI 设备通常由配置空间扫描发现；USB 设备由 host/hub 枚举和 descriptor 发现。
#. I2C、SPI 和大量 platform 设备不能靠外设自身通用协议完整自发现，通常依赖 Device Tree、ACPI、板级描述或显式实例化。
#. Driver core 看到的是通用 ``struct device``；bus-specific wrapper 保存该总线的地址、ID、资源和协议状态。
#. 常见 wrapper 包括 ``struct pci_dev``、``struct usb_interface``、``struct i2c_client``、``struct spi_device`` 和 ``struct platform_device``。
#. Bus-specific driver 也通常嵌入 ``struct device_driver``，例如 ``struct pci_driver``、``struct usb_driver`` 和 ``struct platform_driver``。
#. 匹配规则必须与设备身份来源对应，不能把 PCI ID、USB descriptor、I2C 地址和 DT ``compatible`` 当成同一类证据。
#. PCI 常按 vendor/device/subsystem/class 匹配；USB 可按 vendor/product 或 interface class/subclass/protocol 匹配。
#. I2C、SPI 和 platform 驱动常结合 OF、ACPI、bus-specific ID table 或对象名称匹配。
#. ``match`` 成功只产生候选绑定，不申请驱动私有资源，也不证明设备真正可用。
#. 只有 ``probe`` 成功返回 0 后，驱动才完成该设备实例的资源取得、硬件初始化和功能接口注册。
#. 设备先注册时会尝试已有 driver；driver 后注册时也会扫描同一 bus 上尚未绑定的 device。
#. 这种对称性让启动期设备、模块后加载和热插拔设备都能进入同一绑定骨架。
#. Bus-specific ``probe`` 参数已经是该总线语义下的对象，说明 generic device 已经被 wrapper 转回具体类型。
#. Driver 的 ID table 是“支持声明”，不是设备发现机制；没有 device 对象时，再完整的 ID table 也不会触发 ``probe``。
#. ``MODULE_DEVICE_TABLE()`` 把匹配表交给模块别名生成链，支持基于 modalias 自动加载候选模块。
#. Modalias 链通常是：设备身份 → uevent ``MODALIAS`` → 用户空间模块加载器 → ``modules.alias`` → 加载候选模块。
#. 自动加载模块只让 driver 进入 bus 匹配域，仍可能出现 match 失败、probe defer、资源错误或初始化失败。
#. ``driver_data`` 等 ID table 私有字段可把多个硬件 ID 映射到同一驱动内部能力表，不能由 driver core 解释。
#. 设备资源必须在 ``probe`` 前形成可查询对象，否则驱动无法可靠建立实例状态。
#. 资源不只包括 MMIO 和 IRQ，也包括 DMA 限制、clock、reset、regulator、GPIO、pinctrl、power domain、IOMMU 和 firmware property。
#. PCI 的 BAR、IRQ capability 和 DMA 线索来自总线枚举；platform/I2C/SPI 常从 firmware description 取得资源关系。
#. USB interface 的 endpoint 与 descriptor 是 ``probe`` 前由 usbcore 建立的资源语义，不是传统 ``struct resource`` 数组。
#. I2C client 的 adapter 与地址、SPI device 的 controller/chip-select/mode 都是 bus 在 ``probe`` 前建立的身份和传输约束。
#. Resource description 与 resource ownership 必须区分：固件或 bus 描述资源，驱动 ``probe`` 才申请、映射、启用并承担回滚责任。
#. 设备树中的 ``reg`` 只是地址描述，驱动还要经 resource helper 和 ``ioremap`` 才能获得可访问 MMIO 指针。
#. IRQ 描述转换成 Linux IRQ 号后，驱动仍要申请 handler、配置硬件中断源并在 teardown 时同步结束。
#. Clock、regulator、reset 和 power-domain provider 可能尚未准备好，资源查询可返回 ``-EPROBE_DEFER``。
#. ``-EPROBE_DEFER`` 表示依赖尚未就绪，不等于设备永久不存在或驱动不匹配。
#. Defer 应尽量发生在用户可见接口、子设备和异步路径发布之前，避免重试时重复注册和复杂回滚。
#. Firmware node 是通用设备属性入口，底层来源可以是 Device Tree、ACPI 或其它固件描述。
#. ``device_property_read_*()`` 等通用接口允许部分驱动减少对 OF/ACPI 私有 API 的直接依赖，但不能抹去两种固件模型的语义差异。
#. Bus 还塑造传输单位：USB 围绕 URB/endpoint，I2C 围绕 message/client address，SPI 围绕 message/transfer/chip-select。
#. PCI 和 platform 设备驱动更常围绕 MMIO、DMA、IRQ 和上层队列构建设备数据面。
#. Bus 还塑造热插拔边界：USB disconnect 是常态；PCI 热插拔依赖平台能力；I2C/SPI/platform 通常更静态，但也可能动态实例化或移除。
#. 设备对象删除不等于协议请求自动结束；每种 bus 都有自己的取消、断开、reset 或传输收束规则。
#. USB 需要 kill/unlink URB 并处理 interface disconnect；PCI 需要停止 DMA、IRQ 并处理设备消失或 AER/reset。
#. I2C/SPI 传输常由 controller 串行化，remove 时仍要阻止新事务并等待正在执行的 message。
#. Platform 设备 remove 需要停止 MMIO 设备活动、IRQ、DMA、clock 和外部功能对象。
#. Bus 的 ``remove`` 包装和 driver 的实例回调属于不同层；公共框架撤销绑定，具体资源仍由驱动和子系统收束。
#. Parent-child 关系常来自总线拓扑或固件层级，但 supplier-consumer 依赖可能由 device link 单独表达。
#. 总线层级影响 sysfs 路径、热插拔顺序和 PM；功能 class 则按 net、block、input 等用户语义组织对象。
#. ``/sys/bus/<bus>/devices`` 表明设备属于某匹配域，``driver`` 链接才表明当前成功绑定。
#. ``modalias`` 有值不表示当前已有驱动绑定，只说明用户空间可据此寻找候选模块。
#. 总线枚举失败、设备未实例化、ID 不匹配、probe defer 和 probe 失败必须分成不同诊断阶段。
#. 没有 ``struct device`` 时先查硬件发现与 firmware population；有 device 无 driver 时再查 alias 和 match table。
#. 有 driver 链接但功能不可用时，应进入 ``probe`` 后资源、固件、IRQ、DMA、PM 和上层子系统路径。
#. 同一个驱动可能通过多个固件匹配表支持不同平台，必须确认实际命中的是 OF、ACPI 还是 bus-specific ID。
#. 匹配表顺序、具体 helper、回调签名和 driver core 锁属于版本敏感实现，稳定模型是“发现 → 身份 → 资源 → probe”。
#. 读取总线源码时应先看 bus-specific 对象定义，再看设备创建，再看 ``match``，最后看 probe wrapper 和 teardown。
#. 调试时应记录完整稳定身份，例如 PCI BDF、USB port/interface、I2C adapter+address、SPI controller+chip-select 或 firmware path。
#. 设备名、``eth0``、``ttyUSB0`` 等功能名称可能变化，不能作为唯一跨重启或重插身份。
#. 总线框架的工程价值是把硬件差异压缩进明确的发现、匹配、资源和生命周期合同，而不是让所有驱动看起来完全相同。

必背路径
--------

通用绑定：

::

   Bus framework 发现或实例化设备
   → 创建 bus-specific container
   → 初始化内嵌 struct device
   → 设置 bus、parent、firmware node 和资源
   → device 注册到 bus
   → driver 注册到同一 bus
   → bus->match 比较身份
   → 调用 bus-specific probe wrapper
   → 驱动 probe 建立实例能力

模块自动加载：

::

   驱动定义 bus-specific ID table
   → MODULE_DEVICE_TABLE 导出 alias
   → depmod 生成 modules.alias
   → 设备注册并发出 MODALIAS
   → 用户空间查找候选模块
   → 加载模块并注册 driver
   → bus 再次执行 match/probe

资源交付：

::

   硬件或固件描述资源
   → Bus/Firmware core 解析地址、IRQ 和依赖
   → 形成 device/resource/fwnode 对象
   → probe 使用专用 helper 获取资源
   → 申请、映射和启用资源
   → 初始化硬件
   → 注册上层功能

诊断未绑定：

::

   确认设备是否被发现并形成 /sys/devices 对象
   → 确认所属 bus 与稳定地址
   → 读取 modalias
   → 检查候选模块和 ID table
   → 检查 driver 链接
   → 检查 deferred probe
   → 检查 probe 返回码与资源依赖
   → 检查功能 class 对象是否发布

安全移除：

::

   Bus 报告设备移除或请求解绑
   → 设置 disconnected/stopping
   → 阻止新传输和新打开
   → 撤销 class/subsystem 入口
   → 取消或等待 bus-specific 在途请求
   → 停止 IRQ、DMA、controller 或 endpoint
   → 执行 driver remove
   → 撤销绑定和 sysfs 关系
   → 最后引用归零后释放对象

必须区分
--------

* 设备发现与驱动匹配：发现创建设备对象；匹配只在已有 device 和 driver 之间建立候选关系。
* Match 与 Probe：Match 比较身份；probe 取得资源、初始化实例并注册功能接口。
* 资源描述与资源所有权：Bus/firmware 描述资源；驱动申请并负责运行期启停和错误回滚。
* Bus 与 Class：Bus 定义发现和匹配语义；class 按用户空间功能组织设备。
* Modalias 与成功绑定：Modalias 支持加载候选模块；最终仍需 match 和 probe 成功。
* Driver core 共性与 Bus-specific 语义：Driver core 统一对象生命周期；地址、传输、错误和热插拔规则仍由具体总线决定。

一句话结论
----------

Linux 总线框架把设备来源、身份匹配、资源交付和移除规则组合成驱动合同，正确读驱动必须先读清总线怎样创建设备，再进入 ``probe`` 的硬件实现。
