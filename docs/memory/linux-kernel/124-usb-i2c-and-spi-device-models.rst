第124章：USB、I2C 与 SPI 设备模型
=================================

核心知识点
----------

三种总线共享 Driver Core 外壳
   USB、I2C 和 SPI 都使用 device、driver、match、probe 与 remove，但发现方式、请求对象、错误模型和断开语义完全不同。

USB 是热插拔的层级协议总线
   Host 与 hub 枚举物理设备，读取 descriptor，并建立 device、configuration、interface、alternate setting 和 endpoint 等对象层级。

USB 驱动通常绑定 Interface
   一个复合设备可有多个 interface，并由不同 function driver 分别控制。``usb_device`` 表示物理设备，``usb_interface`` 才常是功能驱动绑定单位。

URB 表达 USB 异步传输
   URB 保存 endpoint、buffer、长度、状态、completion 和上下文。``usb_submit_urb()`` 成功只表示请求被接收，资源必须活到完成或取消收束。

USB Disconnect 是常态路径
   拔出后硬件立即不可用，驱动必须先设置 disconnected、阻止新提交，再 kill/unlink URB、注销用户接口，旧 fd 只能返回断开错误。

I2C 使用 Adapter 与 Client 模型
   ``i2c_adapter`` 表示控制器，``i2c_client`` 表示某 adapter 上一个地址的外设实例。地址只定位外设，不说明芯片类型和寄存器协议。

I2C 设备通常依赖固件实例化
   Device Tree、ACPI、board info 或 MFD 创建 client；加载 driver 不应依靠盲扫所有地址来发现设备。

I2C Message 表达总线事务
   ``i2c_msg`` 数组可组成 repeated-start 事务。成功返回值、短完成、NACK、arbitration loss、timeout 和 bus stuck 必须按 adapter 与设备协议分别解释。

SPI 使用 Controller 与 Chip Select 模型
   ``spi_controller`` 执行总线传输，``spi_device`` 表示一个 chip-select 上的外设。身份、mode、频率和位宽通常来自固件描述。

SPI Message 组织同步移位事务
   ``spi_transfer`` 描述 buffer、长度、速度和位宽，多个 transfer 组成 ``spi_message``。纯读也需要发送 dummy data，因为发送与接收同时发生。

同步与异步接口决定资源终点
   ``spi_sync()`` 返回时 message 已结束；``spi_async()`` 和 URB 必须等待 completion。异步 buffer 不能来自即将失效的栈对象。

总线控制器与外设属于不同层级
   SoC I2C/SPI controller 可能是 platform device；其下挂 sensor、flash 或 codec 才是 I2C/SPI device，不能把两层对象混为一体。

关键路径
--------

USB 枚举与绑定
   Hub 检测端口变化
   → USB Core 分配地址并读取 descriptor
   → 创建 ``usb_device``、interface 与 endpoint
   → 按 ``usb_device_id`` 匹配 interface driver
   → Probe 解析 endpoint 并创建 URB/功能接口
   → HCD 提交与完成传输

USB Disconnect
   Core 调用 disconnect
   → 设置 disconnected
   → 阻止新 URB 和用户操作
   → 注销 cdev、media、audio 等入口
   → unlink/kill anchored URB
   → 等待 completion 结束
   → 释放 buffer 和私有对象
   → 旧引用仅保留安全错误返回能力

I2C 设备路径
   Firmware 描述 adapter、address 与 compatible
   → I2C Core 创建 ``i2c_client``
   → I2C/OF/ACPI ID 匹配 driver
   → Probe 检查 adapter capability
   → 初始化芯片寄存器
   → 注册 hwmon、IIO、input 等功能
   → 通过 SMBus helper 或 ``i2c_transfer()`` 通信

SPI 事务路径
   Firmware 描述 controller、chip-select、mode 与 frequency
   → SPI Core 创建 ``spi_device``
   → Driver match 与 probe
   → 构造一个或多个 ``spi_transfer``
   → 组成 ``spi_message``
   → Controller 排队并驱动 chip-select
   → 同步返回或异步 completion

概念辨析
--------

USB Device 与 USB Interface
   Device 表示整个物理外设；interface 表示可独立绑定驱动的功能单元。

I2C Adapter 与 I2C Client
   Adapter 是控制器；client 是该控制器上一个地址对应的外设对象。

SPI Controller 与 SPI Device
   Controller 提供总线执行能力；device 表示一个 chip-select 上的目标外设。

总线地址与设备身份
   I2C 地址和 SPI chip-select 只完成寻址；硬件类型仍由 compatible、ID 表和协议定义。

同步返回与异步完成
   同步 helper 返回时请求生命周期结束；异步请求必须等 completion 后才能复用 buffer 和上下文。

总线错误与设备业务错误
   Bus Core 只报告传输层状态；寄存器内容、芯片状态和协议错误仍由设备驱动解释。

本章结论
--------

USB、I2C、SPI 的共同点只是设备模型骨架。真正决定驱动结构的是各自的发现方式、请求对象、完成协议和移除边界。
