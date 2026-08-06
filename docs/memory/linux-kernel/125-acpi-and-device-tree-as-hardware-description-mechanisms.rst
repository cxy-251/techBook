第125章：ACPI 与 Device Tree 作为硬件描述机制
=============================================

本章必须记住
------------

#. ACPI 与 Device Tree 都用于把无法由通用总线协议完整自枚举的硬件事实交给 Linux 设备模型。
#. 它们的共同目标是让内核得到可创建设备、可匹配驱动、可取得资源、可管理电源和可建立父子依赖的数据。
#. 固件描述是设备模型的输入，不是驱动私有配置文件；驱动 ``probe`` 面对的是 ``struct device``、fwnode 和资源对象。
#. PCI、USB 等可枚举设备仍可能依赖 ACPI/DT 描述 host bridge、IOMMU、interrupt controller、power domain 和平台约束。
#. 设备是否可自枚举与是否需要固件描述不是绝对互斥关系；两者可以在不同层级共同构成完整拓扑。
#. Device Tree 主要使用节点、属性、phandle 和父子层级声明硬件结构。
#. ACPI 主要使用系统表、命名空间对象、资源方法和平台控制方法描述设备与电源语义。
#. Device Tree 通常强调声明式硬件连接；ACPI 常包含 firmware-mediated 方法和更强的平台控制逻辑。
#. Linux 最终需要把两种来源都关联到通用 ``struct device``，让 driver core 继续处理匹配、引用和生命周期。
#. ``struct fwnode_handle`` 是通用 firmware node 抽象，底层可以表示 OF node、ACPI node 或其它属性来源。
#. ``dev_fwnode()``、``device_property_read_*()``、GPIO/clock/regulator 等通用 consumer API 可减少驱动直接绑定单一固件格式。
#. 通用 property API 只统一查询入口，不保证 ACPI 与 DT 在所有电源方法、拓扑和资源语义上完全等价。
#. Device Tree 的运行时来源通常是 bootloader/firmware 交付的 DTB，内核早期扫描后再 unflatten 成节点树。
#. DT 根节点、``/chosen``、memory 和 CPU 等部分会在早期启动阶段使用，普通设备通常在后续 population 中创建。
#. 一个 DT 节点通常以设备名和 unit-address 命名，例如 ``serial@10000000``；节点名不是驱动匹配的主要合同。
#. ``compatible`` 是 Device Tree 设备身份与驱动匹配的核心属性。
#. Compatible 列表通常从最具体实现排列到更通用兼容实现，驱动可根据命中项选择 quirks 或能力表。
#. ``compatible`` 字符串是 ABI，发布后不能随意改名或把不兼容硬件伪装成旧字符串。
#. 驱动通过 ``struct of_device_id`` 和 ``of_match_table`` 声明支持的 compatible。
#. ``MODULE_DEVICE_TABLE(of, ...)`` 可导出模块 alias，支持根据 OF modalias 自动加载候选模块。
#. ``reg`` 描述地址和长度，但其 cell 数量与地址翻译依赖父节点的 ``#address-cells``、``#size-cells`` 和 ``ranges``。
#. 驱动不能把 DTS 中裸数值直接当 CPU 物理地址；OF/platform core 先完成层级地址翻译并形成 resource。
#. ``interrupts`` 的解释依赖 ``interrupt-parent`` 和中断控制器 binding，最终还需 irqdomain 转成 Linux IRQ。
#. ``clocks``、``resets``、``power-domains``、``iommus``、``dmas`` 和 GPIO 等属性通过 phandle 指向 provider。
#. Consumer ``probe`` 可能早于 provider 完成注册，因此依赖查询需要支持 ``-EPROBE_DEFER``。
#. ``status = "disabled"`` 常用于禁用当前板型不存在或不应启用的节点；精确可用判断应使用内核 OF helper。
#. 节点存在但未被 population，不会自动形成 platform/I2C/SPI device；必须检查父总线创建规则。
#. ``simple-bus`` 常用于描述可枚举子节点的简单内存映射总线，但具体 population 规则仍受 compatible 和父层实现影响。
#. I2C/SPI 子节点通常由对应 controller driver 创建 client/device，不应由全局 platform population 重复创建。
#. DT overlay 可以在运行期增加或修改部分节点，涉及动态设备创建、绑定和移除，支持范围与安全边界具有平台差异。
#. Device Tree binding 定义节点允许和要求的属性、类型、依赖和示例，是固件与驱动之间的长期合同。
#. 现代 binding 常用 YAML/JSON Schema 描述，并由 ``dt-schema``、``dtbs_check`` 等流程验证。
#. Schema 验证能发现属性拼写、类型、required 和结构错误，不能证明硬件原理图、地址或时序实际正确。
#. Binding 中未声明的私有属性会增加长期兼容成本，应优先使用已有公共属性和子系统规范。
#. Driver 新增 DT property 时必须同步 binding 文档和 schema，不能只在代码里静默解析。
#. ACPI 通过 RSDP、XSDT/RSDT 引导到 FADT、DSDT、SSDT 等表，并把 AML 定义组织成命名空间。
#. ACPI namespace 中的 Device、Processor、Thermal Zone、Power Resource 等对象可被 Linux 扫描成内核对象关系。
#. ``_HID`` 表示硬件 ID，``_CID`` 表示兼容 ID，``_ADR`` 常表示父总线下的地址或位置。
#. ``_CRS`` 返回设备当前资源，例如 MMIO、I/O port、IRQ、GPIO、Serial Bus 和 DMA 描述。
#. ``_DSD`` 可提供设备属性，Linux 可把部分内容接入统一 property API。
#. ``_STA`` 描述设备存在、启用和工作状态；返回状态会影响对象是否被枚举和绑定。
#. ``_DEP`` 可表达设备枚举或初始化依赖；电源资源和 device link 还可能参与 probe/PM 顺序。
#. ``_PR0``、``_PR3``、``_PS0``、``_PS3``、``_PRW`` 等对象/方法参与电源状态和唤醒语义，具体使用取决于平台与设备类。
#. ACPI 方法是固件代码，执行可能访问 Embedded Controller、GPIO、Operation Region 或其它平台资源。
#. 驱动不应绕过 ACPI 平台控制逻辑直接假设寄存器和电源状态，除非设备规范明确由 OS 完全接管。
#. ``struct acpi_device`` 表示 ACPI namespace 对象在 Linux 中的设备层表示，物理 ``struct device`` 可通过 companion/handle 与其关联。
#. ACPI matching 使用 ``struct acpi_device_id``，driver core/fwnode 路径再把匹配结果交给具体 bus driver。
#. ACPI 也能枚举 platform、I2C、SPI 等设备；设备最终归属的 bus 仍决定传输和 ``probe`` 对象类型。
#. ACPI namespace 路径与 sysfs canonical device path 是不同命名体系，需要通过 companion 链接和日志关联。
#. DT 与 ACPI 通常由平台选用其一作为主要硬件描述，不应为同一设备重复创建两个内核对象。
#. 某些系统会同时使用 ACPI 和少量 DT/overlay 或其它 firmware node，驱动应依赖明确的设备对象来源而非全局假设。
#. Firmware description 错误可表现为设备不出现、资源冲突、IRQ 错误、clock defer、GPIO 反相或 suspend/resume 故障。
#. 设备对象未出现时，先检查固件节点/ACPI 对象、状态、父层 population 和内核配置。
#. 设备存在无 driver 时，检查 ``compatible``/``_HID``、match table、modalias 和模块。
#. Probe 资源错误时，检查 ``reg``/``_CRS``、IRQ、provider phandle、property 名称和依赖状态。
#. Runtime PM 或系统睡眠故障时，检查 power-domain、ACPI power method、wake 属性和 parent/supplier 顺序。
#. ``/proc/device-tree`` 是运行时 DT 视图之一，文件编码和节点内容应按 OF 语义解释，不是原始 DTS 文本。
#. ``acpidump``、``iasl`` 等工具可取得和反编译 ACPI 表，但输出必须与当前启动日志和 Linux 设备对象对齐。
#. Sysfs ``firmware_node``、``of_node``、``physical_node`` 等链接是否存在及名称具有版本和对象类型差异。
#. 固件提供的数据可能被 bootloader、quirk、overlay 或内核修正路径修改，运行时事实应以实际设备对象和日志验证。
#. 不应让驱动依赖板型名称判断寄存器差异；差异应通过 compatible/ID match data、property 或正式 quirk 表表达。
#. Board compatible 与 device compatible 处于不同层级，前者描述整板/SoC，后者描述具体设备实现。
#. ACPI ID、DT compatible 和 bus-specific ID 都是匹配材料，不是安全边界；用户空间可加载模块不代表硬件可信。
#. Firmware 数据属于系统信任根的一部分，错误或恶意描述可能导致资源冲突和设备访问风险。
#. 稳定源码阅读顺序是：固件输入 → 节点/namespace 对象 → device population → match table → resource/property → ``probe`` → PM。
#. 精确 OF population、ACPI scan、fwnode helper 和 schema 工具选项具有版本差异，应以目标内核和 binding 为准。
#. ACPI/DT 的工程核心是把硬件事实变成可验证的长期 ABI，使驱动代码独立于具体板级硬编码。

必背路径
--------

Device Tree 创建设备：

::

   Bootloader/Firmware 交付 DTB
   → 内核 early scan
   → unflatten 为运行时节点
   → 检查 status 与父总线
   → of_platform_populate 或 controller 创建子设备
   → 关联 of_node/fwnode
   → compatible 匹配 driver
   → probe 通过统一资源 API 取得依赖

DT 资源解析：

::

   节点 reg/interrupts/clocks/resets/GPIO
   → 父节点 cell 与 ranges 地址翻译
   → irqdomain 解析中断
   → phandle 找到 provider
   → 形成 resource、IRQ、clock、reset、descriptor
   → consumer probe 获取并启用
   → remove 时按依赖逆序释放

ACPI 枚举：

::

   Firmware 交付 ACPI tables
   → AML 构建 namespace
   → 扫描 Device 对象与 _STA
   → 读取 _HID/_CID/_ADR
   → 解析 _CRS 与 _DSD
   → 创建/关联 struct acpi_device 和物理 device
   → ACPI/bus ID match
   → probe 获取资源与平台控制语义

Binding 验证：

::

   定义设备硬件合同
   → 编写或更新 YAML schema
   → 声明 compatible、required、properties 和 examples
   → 编译 DTS
   → 运行 schema/dtbs_check
   → 修复结构和类型错误
   → 在真实板上验证资源、IRQ、时钟和 PM

诊断未绑定设备：

::

   判断设备应来自 DT 还是 ACPI
   → 检查节点/namespace 是否存在且 enabled
   → 检查是否创建 struct device
   → 检查 compatible/_HID 与 match table
   → 检查 modalias 和模块
   → 检查 resource/property 解析
   → 检查 provider defer 与电源依赖
   → 对齐 sysfs、dmesg 和 firmware dump

必须区分
--------

* 硬件描述与驱动实现：ACPI/DT 说明设备存在、资源和依赖；驱动实现寄存器、协议和运行状态机。
* Device Tree 节点与 Linux Device：节点是固件数据对象；population 后才形成可绑定的 ``struct device``。
* ``compatible`` 与节点名称：Compatible 是驱动匹配合同；节点名称主要表达设备类型和 unit-address。
* ACPI Namespace 与 Sysfs Tree：ACPI 是固件对象层级；sysfs 是 Linux 设备模型投影，二者通过 companion 关系连接。
* Schema 通过与硬件正确：Schema 验证格式和合同；真实地址、连线、时序仍需板级运行验证。
* 通用 Property API 与完全相同语义：Fwnode API 统一属性查询；ACPI 方法和 DT 声明式依赖仍有本质差异。

一句话结论
----------

ACPI 与 Device Tree 把平台硬件事实转成 Linux 可创建、匹配、取资源和管理电源的设备对象；正确性依赖描述 ABI、provider 关系、driver match 与运行验证同时成立。
