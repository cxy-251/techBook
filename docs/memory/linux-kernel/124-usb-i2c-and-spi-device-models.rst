第124章：USB、I2C 与 SPI 设备模型
=================================

本章必须记住
------------

#. USB、I2C、SPI 都接入 Linux driver model，但它们的发现方式、地址模型、传输单位和断开语义完全不同。
#. 读驱动时必须先判断总线模型，再解释 ``probe``、请求对象、错误码和 teardown；不能只看函数名相似。
#. USB 是 host 控制、hub 分层、descriptor 描述、interface 绑定和 endpoint 传输的热插拔总线。
#. I2C 是 adapter 发起、以 client address 选择外设、常用于低速寄存器访问的共享串行总线。
#. SPI 是 controller 主导、以 chip-select 选择外设、由 mode/clock/transfer 描述同步全双工事务的串行总线。
#. USB 设备能通过标准 descriptor 自报告大量身份和接口信息；I2C/SPI 外设通常需要固件或板级描述提前实例化。
#. USB 的物理设备、configuration、interface、alternate setting 和 endpoint 是不同对象层级。
#. Linux USB function driver 通常绑定 ``struct usb_interface``，不是整个物理 ``struct usb_device``。
#. 一个复合 USB 设备可包含多个 interface，并由不同驱动分别绑定，例如视频、音频和控制功能。
#. ``struct usb_device`` 表示物理 USB 设备；``struct usb_interface`` 表示一个可绑定功能接口。
#. Endpoint 描述方向、传输类型和最大包等属性；驱动只能使用当前 alternate setting 中有效的 endpoint。
#. USB control、bulk、interrupt、isochronous 传输具有不同可靠性、时序和带宽语义。
#. URB 是 USB 异步请求对象，保存 endpoint、buffer、长度、完成回调、状态和上下文。
#. ``usb_submit_urb()`` 成功只表示请求被 usbcore 接收，不表示传输已完成或 buffer 可复用。
#. URB buffer 和上下文必须存活到 completion、unlink 或 kill 完成。
#. USB completion 可能发生在与提交不同的上下文，回调中不能执行不允许的睡眠或长期阻塞操作。
#. Anchor 可以组织一组 URB，便于 disconnect、suspend 或错误路径统一取消和等待。
#. ``usb_unlink_urb()`` 发起异步取消；``usb_kill_urb()`` 等同步接口用于确保回调结束，具体上下文限制以目标内核为准。
#. USB disconnect 的第一步是设置 disconnected 并阻止新提交，之后取消 URB、撤销用户接口，最后释放对象。
#. 设备拔出后旧 fd 或映射可能仍保持软件对象引用，但所有操作必须返回断开错误，不能继续访问 endpoint。
#. USB reset、altsetting 切换、runtime PM 和 disconnect 是不同状态变化，驱动要定义一致状态机。
#. I2C core 的核心对象是 ``struct i2c_adapter``、``struct i2c_client`` 和 ``struct i2c_driver``。
#. Adapter 表示控制器和底层传输能力；client 表示某个 adapter 上一个 7-bit/10-bit 地址的设备实例。
#. I2C 地址只选择外设，不提供统一设备身份、寄存器布局或数据格式。
#. I2C client 通常由 Device Tree、ACPI、board info、MFD 或显式用户控制路径创建。
#. 没有 client 对象时，加载 ``i2c_driver`` 不会可靠地自动扫描所有地址寻找设备。
#. I2C 地址盲扫可能触发设备副作用或总线故障，生产驱动应依赖明确描述和安全检测协议。
#. ``struct i2c_driver`` 可结合 I2C ID、OF match、ACPI match 等材料匹配 client。
#. ``probe(struct i2c_client *client)`` 获得地址、adapter、IRQ、firmware properties 和通用 device 生命周期。
#. I2C 事务通常通过 ``struct i2c_msg`` 数组和 ``i2c_transfer()`` 表达，也可使用受支持的 SMBus helper。
#. 一组 ``i2c_msg`` 可能通过 repeated-start 形成一个逻辑事务，adapter 是否支持由 capability 决定。
#. SMBus helper 与原生 I2C transfer 不是完全等价，驱动应检查 ``i2c_check_functionality()`` 等能力。
#. I2C 传输返回值要按接口解释：成功 message 数、负 errno 和短完成不能混为一层。
#. NACK 可能表示无设备、设备忙、寄存器非法或协议状态不满足，不能只用一个“断线”结论解释。
#. Clock stretching、arbitration loss、controller timeout 和 bus stuck 都可能表现为 I2C 传输错误。
#. Regmap 可抽象寄存器地址、位宽、缓存和锁，但不能改变底层 I2C 事务与设备时序要求。
#. I2C remove/runtime suspend 前应阻止新传输，并确保上层 hwmon/IIO/input/codec 等接口不再进入 client。
#. SPI core 的核心对象是 ``struct spi_controller``、``struct spi_device``、``struct spi_message`` 和 ``struct spi_transfer``。
#. Controller 表示主控硬件和队列；``spi_device`` 表示某个 chip-select 上的外设实例。
#. SPI 设备身份通常来自 firmware description，包括 controller、chip-select、max frequency、mode、bits-per-word 和 IRQ。
#. Chip-select 只选择外设，不提供标准身份查询；驱动仍依赖 OF、ACPI、SPI ID 或名称匹配。
#. SPI mode 定义 CPOL/CPHA 等时序，mode 配错可能得到稳定但完全错误的数据。
#. ``max_speed_hz`` 是设备允许上限之一，实际速率还受 controller 分频、transfer override 和硬件限制。
#. ``struct spi_transfer`` 描述一次 tx/rx buffer、长度、速度、位宽和片选行为。
#. ``struct spi_message`` 把多个 transfer 组成一个逻辑事务，可在 transfer 之间保持或改变 chip-select。
#. SPI 是移位式全双工总线：发送与接收同时发生，纯读通常也需要发送 dummy bytes。
#. 同步 ``spi_sync()`` 等待 message 完成；异步 ``spi_async()`` 通过 completion 回调结束请求生命周期。
#. 异步 SPI buffer 必须存活到 message completion，不能使用函数栈上即将失效的临时对象。
#. Controller 通常串行化同一总线上的 message，多个设备共享带宽和 controller runtime PM 状态。
#. SPI NOR、显示屏、ADC 和触摸控制器虽然同属 SPI，但上层协议、数据规模和延迟要求不同。
#. USB 是 packet/endpoint 模型，I2C 更接近 addressed register/message 模型，SPI 是 controller-driven transfer 模型。
#. USB 错误常围绕 disconnect、stall、short packet、timeout 和 URB 状态；I2C/SPI 错误更依赖 controller 与外设协议。
#. USB short packet 在部分传输类型中可以是合法边界；不能机械当作错误。
#. I2C/SPI 上层驱动必须定义寄存器字节序、地址宽度、CRC、延迟和状态轮询，bus core 不知道芯片业务语义。
#. 三类总线都可使用 runtime PM，但挂起边界不同：USB 涉及 interface/device autosuspend，I2C/SPI 涉及 adapter/controller 与 client 依赖。
#. 总线控制器本身可能是 PCI 或 platform device；其下挂外设再进入 USB、I2C 或 SPI 对象层级。
#. 例如 SoC I2C controller 是 platform device，温度传感器是该 controller 下的 ``i2c_client``，两者不能混为同一对象。
#. Sysfs canonical path 可展示 controller、hub、interface、adapter 和 client 的父子层级，但 class 入口可能隐藏底层连接方式。
#. 诊断 USB 应记录 port path、VID:PID、interface number、endpoint 和 URB 状态。
#. 诊断 I2C 应记录 adapter 编号、总线地址、adapter capability、message 和 firmware node。
#. 诊断 SPI 应记录 controller、chip-select、mode、频率、bits-per-word 和 message/transfer 边界。
#. ``lsusb``、``usb-devices``、sysfs 和 usbmon 提供 USB 不同层证据；任何单一工具都不覆盖全部生命周期。
#. ``i2cdetect`` 等探测工具可能对某些设备有副作用，不应在未知生产总线上无条件使用。
#. SPI 通常缺少通用安全扫描命令，因为 chip-select 和协议必须由板级描述明确。
#. 总线错误恢复不能只重试：拔出设备、永久 NACK、错误 mode 或 controller reset 需要不同状态处理。
#. Teardown 的稳定原则是先阻止新请求，再取消/等待 bus-specific 在途请求，最后释放 client/interface/device 私有状态。
#. 精确 USB 回调上下文、I2C probe 签名、SPI controller API 和 helper 名称具有版本差异。
#. 稳定源码阅读顺序是：设备创建来源 → bus-specific object → match → probe → transfer object → completion → disconnect/remove。
#. 总线决定驱动的形状：发现方式决定身份，传输模型决定请求对象，热插拔能力决定 teardown 状态机。

必背路径
--------

USB 枚举与绑定：

::

   Hub 检测端口变化
   → USB core 分配地址并读取 descriptor
   → 建立 usb_device、configuration、interface、endpoint
   → 按 usb_device_id 匹配 interface driver
   → probe 解析 endpoint 并建立 URB/用户接口
   → 提交 URB
   → HCD 完成传输
   → completion 回调处理结果

USB Disconnect：

::

   Core 报告 interface disconnect
   → 设置 disconnected
   → 阻止新 URB 和用户请求
   → 注销 class/cdev/video/audio 等入口
   → unlink/kill anchored URB
   → 等待 completion 结束
   → 释放 endpoint 相关 buffer 和私有对象
   → 旧 fd 仅返回设备已断开

I2C Client：

::

   Firmware 描述 adapter、address 和 compatible
   → I2C core 创建 i2c_client
   → i2c_driver ID/OF/ACPI match
   → probe 检查 adapter capability
   → 读取芯片 ID 和初始化寄存器
   → 注册 hwmon/IIO/input 等接口
   → 运行期通过 SMBus helper 或 i2c_transfer 通信

SPI Message：

::

   Firmware 描述 controller、chip-select、mode、frequency
   → SPI core 创建 spi_device
   → spi_driver match/probe
   → 构造一个或多个 spi_transfer
   → 加入 spi_message
   → controller 排队并切换 chip-select
   → 同步返回或异步 completion
   → 调用者释放 message buffer

总线模型选择：

::

   判断设备是否由 descriptor 动态枚举
   → 是：优先检查 USB interface/endpoint 模型
   → 判断是否以共享地址和双线事务通信
   → 是：I2C adapter/client 模型
   → 判断是否由 controller、chip-select 和同步移位通信
   → 是：SPI device/message 模型
   → 再进入对应 match、传输和 teardown 路径

必须区分
--------

* USB Device 与 USB Interface：Device 表示物理外设；功能驱动通常绑定其中一个 interface。
* I2C Adapter 与 I2C Client：Adapter 是控制器；client 是某个地址上的外设实例。
* SPI Controller 与 SPI Device：Controller 执行总线传输；device 表示一个 chip-select 上的外设。
* 同步调用返回与异步请求完成：同步 helper 返回时请求结束；URB、``spi_async`` 等必须等 completion 才能释放资源。
* 总线地址与设备身份：I2C 地址、SPI chip-select 只定位外设；硬件类型仍来自固件与匹配表。
* 总线错误与设备业务错误：Bus core 报告传输状态；寄存器内容、协议状态和芯片错误仍由设备驱动解释。

一句话结论
----------

USB、I2C、SPI 共享 driver core 外壳，却分别由 interface/endpoint、adapter/client、controller/chip-select 模型塑造请求、完成和移除路径，驱动必须按真实总线语义设计。
