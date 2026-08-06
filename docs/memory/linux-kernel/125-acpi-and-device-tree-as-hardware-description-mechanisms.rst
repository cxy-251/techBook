第125章：ACPI 与 Device Tree 作为硬件描述机制
=============================================

核心知识点
----------

固件描述连接硬件事实与设备模型
   ACPI 与 Device Tree 都用于告诉内核设备存在、连接关系、地址、中断、电源和依赖，使 driver core 能创建设备并进入匹配与 probe。

自枚举设备也可能依赖固件
   PCI、USB 可以发现下游设备，但 host bridge、IOMMU、interrupt controller、power domain 和平台约束仍常来自 ACPI 或 Device Tree。

Device Tree 是声明式节点树
   节点、属性、phandle 和父子层级表达板级拓扑。``compatible`` 是设备身份与驱动匹配的核心合同，节点名称不是主要匹配依据。

地址与中断需要层级翻译
   ``reg`` 要结合父节点的 address/size cells 与 ``ranges`` 解释；``interrupts`` 要通过 interrupt-parent 和 irqdomain 转换成 Linux IRQ。

Phandle 表达 Provider 依赖
   Clock、reset、regulator、GPIO、DMA、IOMMU 和 power domain 等属性指向 provider。Consumer probe 早于 provider 就绪时可能返回 ``-EPROBE_DEFER``。

节点不自动等于 Linux Device
   DTB 被解析成运行时节点后，还要由 platform population 或 I2C/SPI controller 创建对应 device，之后才有 bus match 和 probe。

DT Binding 是长期 ABI
   YAML/JSON Schema 规定 compatible、required 属性、类型和结构。Schema 可发现格式错误，但不能证明原理图、地址和时序真实正确。

ACPI 结合表、命名空间与方法
   RSDT/XSDT、DSDT、SSDT 等表构成 ACPI 输入；``_HID``、``_CID``、``_ADR``、``_CRS``、``_STA`` 与电源方法描述身份、资源和平台控制。

ACPI 方法可能执行平台逻辑
   AML 方法可以访问 EC、GPIO 和 operation region。驱动不能无视 ACPI 电源与平台控制，直接假设设备始终由 OS 独占管理。

Fwnode 提供通用属性入口
   ``struct fwnode_handle`` 与 ``device_property_read_*()`` 允许驱动复用部分 DT/ACPI 属性读取逻辑，但不会消除两种模型在方法、电源和拓扑语义上的差异。

设备只能有明确的描述来源
   同一硬件不应由 DT 与 ACPI 重复实例化。诊断时必须确认实际 device 来源、firmware node、bus 类型和 match table。

运行时对象才是最终证据
   Bootloader、firmware、quirk、overlay 或内核修正都可能改变输入，最终应以当前 ``struct device``、sysfs、资源和日志验证实际状态。

关键路径
--------

Device Tree 创建设备
   Firmware/Bootloader 交付 DTB
   → 内核 early scan 与 unflatten
   → 检查节点 status 与父总线
   → Platform population 或 controller 创建子设备
   → 关联 OF node/fwnode
   → ``compatible`` 匹配 driver
   → Probe 取得 resource 与 provider 依赖

DT 资源解析
   ``reg``、``interrupts``、``clocks``、``resets``、GPIO 等属性
   → 父节点完成地址 cell 与 ``ranges`` 翻译
   → irqdomain 解析中断
   → phandle 找到 provider
   → 形成 resource、IRQ 和 provider 句柄
   → Consumer probe 申请并启用

ACPI 枚举
   Firmware 交付 ACPI Tables
   → AML 建立 namespace
   → 扫描 Device 对象与 ``_STA``
   → 读取 ``_HID/_CID/_ADR``
   → 解析 ``_CRS`` 与 ``_DSD``
   → 创建或关联 ``acpi_device`` 和物理 device
   → ACPI/bus ID 匹配
   → Probe 使用资源和平台控制语义

未绑定设备诊断
   判断设备应来自 DT 还是 ACPI
   → 确认节点/命名空间存在且 enabled
   → 确认是否已创建 ``struct device``
   → 检查 ``compatible`` 或 ``_HID``
   → 检查 modalias、模块和 match table
   → 检查资源解析与 provider defer
   → 对齐 sysfs、dmesg 与 firmware dump

概念辨析
--------

硬件描述与驱动实现
   ACPI/DT 说明设备、资源和依赖；驱动实现寄存器协议、数据路径和运行状态机。

DT Node 与 Linux Device
   Node 是固件数据对象；只有被 population 或 controller 实例化后，才形成可绑定 device。

``compatible`` 与节点名称
   ``compatible`` 是稳定匹配合同；节点名称主要表达类型和 unit-address。

ACPI Namespace 与 Sysfs Tree
   ACPI Namespace 是固件对象层级；sysfs 是 Linux 设备模型投影，二者通过 companion/fwnode 关系连接。

Schema 正确与硬件正确
   Schema 只能验证结构和属性合同；真实连线、IRQ、电源和时序仍需运行验证。

通用 Property API 与完全相同语义
   Fwnode API 统一查询入口；ACPI 方法与 DT 声明式依赖仍保留不同执行模型。

本章结论
--------

ACPI 与 Device Tree 的核心作用，是把平台硬件事实转换成 Linux 可实例化、匹配、取资源和管理电源的对象合同。描述、provider 关系与运行验证必须同时成立。
