第十五章：SeaBIOS 怎样沿 RSDP 读懂 ACPI 表图并解析 DSDT？
========================================================

上一章结束时，QEMU 生成的 ACPI blobs 已经被 SeaBIOS 分配、链接和校验，``find_acpi_rsdp()`` 也已经在 F-segment 找到有效 RSDP。

当前控制流是：

.. code-block:: c

   RsdpAddr = find_acpi_rsdp();

   if (RsdpAddr) {
       acpi_dsdt_parse();
       virtio_mmio_setup_acpi();
       return;
   }

本章不把 ACPI 简化成“几张硬件表”。它实际上由两类内容组成：

* 固定二进制结构，用地址、长度和标志描述 CPU、APIC、PCI ECAM、时钟、电源管理寄存器等；
* AML 字节码，用 namespace、Device、Method、``_CRS``、``_PRT`` 等对象描述无法只靠固定表表达的平台关系。

SeaBIOS 在这里不会实现完整 ACPI 操作系统。它只建立一张足够后续固件代码查询的轻量设备索引，然后返回 ``platform_hardware_setup()``。Linux 以后会用自己的 ACPICA 解释器重新发现和解释整套 ACPI namespace。

RSDP 是表图入口，不是整张 ACPI 表
------------------------------

RSDP，全称 Root System Description Pointer，自己只保存少量根信息。ACPI 2.0 及以后版本的核心字段可以概括为：

::

   signature = "RSD PTR "
   revision
   rsdt_physical_address
   length
   xsdt_physical_address
   checksum
   extended_checksum

它提供两条进入表图的路径：

``RSDT``
   Root System Description Table。表项是 32 位物理地址，每项 4 字节。

``XSDT``
   Extended System Description Table。表项是 64 位物理地址，每项 8 字节。

两者保存的不是表类型枚举，而是一组其他 ACPI table header 的物理地址。软件必须逐项读取目标表头的 4 字节 signature，才能知道该项是 FADT、MADT、MCFG、HPET 还是其他表。

::

   RSDP
   ├── RSDT ─┬── FADT
   │          ├── MADT
   │          ├── MCFG
   │          └── ...
   └── XSDT ─┬── FADT
              ├── MADT
              ├── MCFG
              ├── HPET
              ├── TPM2 / TCPA
              └── 条件扩展表

RSDT 与 XSDT 不是两套互相矛盾的配置。XSDT 是能够携带 64 位表地址的新入口，RSDT 用于兼容只理解 ACPI 1.0 结构的软件。

SeaBIOS 查表时优先使用 XSDT
-------------------------

``find_acpi_table(signature)`` 先验证全局 ``RsdpAddr``，随后取得：

.. code-block:: c

   rsdt = RsdpAddr->rsdt_physical_address;
   xsdt = RsdpAddr->xsdt_physical_address;

它先遍历 XSDT，再遍历 RSDT。每个候选目标都必须满足：

::

   pointer != NULL
   target->signature == requested_signature

SeaBIOS 当前主流程仍是 32 位 flat code，函数把超过 4 GiB 的 XSDT 地址和 XSDT 表项跳过：

.. code-block:: c

   if (xsdt_address >= 0x100000000)
       xsdt = NULL;

   if (entry >= 0x100000000)
       continue;

这不是 ACPI 规范禁止表位于 4 GiB 以上，而是当前 SeaBIOS 查询实现只直接解引用能表示成 32 位 flat pointer 的目标。QEMU 因此会把 SeaBIOS 启动期需要访问的核心表分配在可达地址。

FADT 把固定电源管理接口与 DSDT 接起来
--------------------------------

FADT 的 signature 是 ``FACP``，全称 Fixed ACPI Description Table。它承担两种连接任务。

第一种是指向其他结构：

::

   FADT → FACS
   FADT → DSDT

``FACS``
   Firmware ACPI Control Structure。保存 firmware waking vector 等运行期状态，不使用普通 ACPI table checksum 格式。

``DSDT``
   Differentiated System Description Table。表头之后是 AML namespace 的主体。

第二种是公布固定硬件接口。QEMU q35 从 ICH9 LPC 状态生成 FADT，包含：

* SCI 中断号；
* SMI command port；
* ACPI enable/disable command；
* PM1 event block；
* PM1 control block；
* PM timer；
* GPE block；
* reset register 与 reset value；
* RTC century register；
* 平台是否支持 S3/S4 等标志。

当前 q35 路径中，SeaBIOS 先前已经把 ICH9 PMBASE 配置到真实 I/O 地址。FADT 再把同一组端口以标准 ACPI 结构公布给后续软件。因此：

::

   第九章写芯片组寄存器
   → 当前 FADT 描述这些寄存器
   → Linux 按 FADT 重新发现并使用它们

硬件配置与固件表描述必须一致。只写 PMBASE 而不生成正确 FADT，操作系统不知道端口在哪里；只写 FADT 而芯片组没有解码对应端口，操作系统访问的只是空地址。

MADT 把 CPU、local APIC、I/O APIC 和中断覆盖连起来
---------------------------------------------

MADT 的 signature 是 ``APIC``，全称 Multiple APIC Description Table。它通常包含若干不同类型的 variable-length entries，例如：

* Processor Local APIC；
* Processor Local x2APIC；
* I/O APIC；
* Interrupt Source Override；
* Local APIC NMI；
* x2APIC NMI。

上一章的 MP table 是旧式多处理器发现接口。MADT 是现代 ACPI 路径中的主要 CPU 与 APIC 描述。

Processor entry 会把：

::

   ACPI processor UID
   APIC ID
   enabled / online-capable flags

关联起来。I/O APIC entry 则公布：

::

   I/O APIC ID
   MMIO address
   GSI base

Interrupt Source Override 用于表达 ISA IRQ 与 Global System Interrupt 不完全一一对应的情况。PC/q35 常见例子是 legacy IRQ0 被覆盖到 GSI 2。SeaBIOS 第十三章生成 MP table 时也读取了 QEMU 的 ``etc/irq0-override``；MADT 以 ACPI 标准结构表达同一个平台事实。

Linux 以后不会因为 SeaBIOS 曾经唤醒过 AP，就直接沿用固件的临时 AP 状态。它会读取 MADT，建立自己的 CPU/APIC 拓扑，再按内核自己的 SMP 启动流程重新启动 AP。

MCFG 公布 PCI Express 配置空间窗口
------------------------------

MCFG 的 signature 是 ``MCFG``。它告诉操作系统 PCI Express Enhanced Configuration Access Mechanism，简称 ECAM/MMCONFIG，位于哪里。

每个 allocation structure 描述：

::

   base address
   PCI segment group
   start bus
   end bus

当前固定 q35 主线已经在第八章启用：

::

   MMCONFIG base = 0xb0000000
   size          = 256 MiB

MCFG 把这段硬件配置重新编码成操作系统可发现的标准描述。Linux 读取后，可以用：

::

   ecam_base
   + (bus << 20)
   + (device << 15)
   + (function << 12)
   + register

访问每个 function 的 4 KiB PCIe configuration space，而不必继续使用 ``0xcf8 / 0xcfc`` 的旧式 256 字节窗口。

HPET、TPM2 与其他表都是条件存在
----------------------------

RSDT/XSDT 不是固定长度清单。QEMU 根据实际虚拟机配置选择附加表：

``HPET``
   存在 High Precision Event Timer 时，公布 HPET MMIO 地址和属性。

``TPM2`` 或 ``TCPA``
   存在 TPM 2.0 或 TPM 1.2 measured-boot 配置时，公布 TPM 接口以及 event log buffer 的地址和长度。

``SRAT`` / ``SLIT`` / ``HMAT``
   在 NUMA 或异构内存拓扑需要时描述内存亲和性和距离。

``DMAR`` / ``IVRS``
   条件描述 Intel VT-d 或 AMD IOMMU。

``WAET``、``BGRT``、``HEST``、``ERST`` 等
   由机器类型和启用设备决定。

因此不能把“q35 一定存在某张扩展表”写死。可靠方法是从 RSDT/XSDT 实际枚举 signature。

DSDT 与固定表的区别
------------------

固定表擅长描述数组和寄存器，DSDT 则携带 AML 字节码，用 namespace 表达设备和方法。例如：

::

   \_SB.PCI0
   \_SB.PCI0.LPCB
   \_SB.PCI0.SATA
   \_SB.PCI0._PRT
   \_SB.PCI0._CRS

常见预定义对象包括：

``_HID``
   Hardware ID，标识设备类型，例如 PNP ID 或字符串 ID。

``_CID``
   Compatible ID。

``_STA``
   设备当前存在、启用、可显示和工作状态。

``_CRS``
   Current Resource Settings，返回 MMIO、I/O port、IRQ、DMA 和 bus number 等资源模板。

``_PRT``
   PCI Routing Table，把 device/pin 路由到 PIRQ link device 或 GSI。

``_S3``、``_S4``、``_S5``
   描述睡眠和关机状态编码。

``_EJ0``、``_PS0``、``_PS3`` 等 Method
   描述热拔出和电源状态转换动作。

AML 不是 C 结构体。它包含 opcode、package length、namestring、整数、Buffer、Package、Method 和控制流。操作系统通常需要完整 AML interpreter 才能执行任意 Method。

SeaBIOS 为什么解析 DSDT
---------------------

SeaBIOS 在继续自身硬件初始化时，也可能需要发现只通过 ACPI 描述的设备。当前最直接的使用者是 ``virtio_mmio_setup_acpi()``。

它需要知道：

::

   哪些 ACPI Device 的 _HID 是 "LNRO0005"
   对应 _CRS 中的 MMIO 地址是什么
   IRQ 是什么

因此 SeaBIOS 在启动设备驱动前建立一个轻量 ``acpi_device`` 列表：

.. code-block:: c

   struct acpi_device {
       char name[16];
       u8 *hid_aml;
       u8 *sta_aml;
       u8 *crs_data;
       int crs_size;
   };

这里保存的是指向已装载 DSDT AML 的位置，不是把所有 AML 对象转换成完整抽象语法树。

acpi_dsdt_parse 怎样找到 AML 主体
-------------------------------

函数先通过：

.. code-block:: c

   fadt = find_acpi_table(FACP_SIGNATURE);

取得 FADT，再读取它的 DSDT 物理地址。DSDT 自己仍有标准 ACPI table header：

::

   signature
   length
   revision
   checksum
   OEM fields
   AML bytes...

SeaBIOS 从 offset ``0x24`` 开始解析，因为标准 ACPI table header 长 36 字节：

.. code-block:: c

   length = *(u32 *)(dsdt + 4);
   offset = 0x24;
   parse_termlist(&state, dsdt, offset, length);

前 36 字节是普通表头，真正 AML term list 从后面开始。

这个 parser 不是完整 AML interpreter
--------------------------------

SeaBIOS parser 只识别当前固件需求涉及的一部分语法，例如：

* Scope；
* Device；
* Name；
* Buffer；
* Package 的长度编码；
* 常见整数常量；
* ``_HID``、``_STA``、``_CRS``；
* 一些可以安全跳过的 Method 和未知 package。

它不会执行通用 AML 控制流，也不会完整实现：

* If/Else/While 的运行期语义；
* OperationRegion 和 Field 的全部读写规则；
* Mutex、Event 和同步；
* 任意 Method 调用；
* namespace 名称解析的全部边界情况；
* ACPI interpreter 的对象类型转换。

当 ``_STA`` 是静态 Name 常量时，它可以直接判断设备是否存在；如果 ``_STA`` 是 Method，函数返回“unknown”，不会尝试执行该 Method。

解析深度被限制为 16 层。遇到未知内容或长度越界时，parser 标记错误并跳出当前 term list，防止损坏 AML 导致无限递归或越界扫描。

_CRS resource template 怎样被拆开
-----------------------------

``_CRS`` 通常是 Buffer，内部由 ACPI resource descriptors 串联而成。SeaBIOS 支持当前需要的常见 descriptor：

small resource：

* IRQ；
* I/O range；
* Fixed I/O；
* End Tag。

large resource：

* 32-bit Fixed Memory Range；
* WORD Address Space；
* DWORD Address Space；
* QWORD Address Space；
* Extended IRQ。

``acpi_dsdt_find_mem()``、``acpi_dsdt_find_io()`` 和 ``acpi_dsdt_find_irq()`` 顺序扫描 descriptors，返回第一个匹配范围。

这套实现适合从简单静态 ``_CRS`` 中提取设备地址；如果资源由 AML Method 动态计算，SeaBIOS 不会像 Linux ACPICA 那样执行 Method 得到结果。

virtio-mmio 怎样借 ACPI 发现设备
------------------------------

``virtio_mmio_setup_acpi()`` 遍历所有：

::

   _HID = "LNRO0005"

的设备。对每个设备分别读取 ``_CRS`` 中的 memory range 和 IRQ：

.. code-block:: c

   acpi_dsdt_find_mem(dev, &mem, &unused);
   acpi_dsdt_find_irq(dev, &irq);

随后把 MMIO base 交给：

.. code-block:: c

   virtio_mmio_setup_one(mem);

当前实现只直接访问 4 GiB 以下地址。它先读取：

::

   offset 0x00  magic
   offset 0x04  version
   offset 0x08  device id

magic 必须是：

::

   0x74726976   ASCII little-endian "virt"

version 接受：

::

   1  legacy virtio-mmio
   2  virtio 1.0+

当前 SeaBIOS 会为 device id 2 的 virtio-blk 和 device id 8 的 virtio-scsi 创建初始化线程。其他设备可以被识别和打印，但不在这里成为 BIOS block device。

标准 q35 常把 virtio 设备挂在 PCI 总线上，所以本函数可能找不到任何 ``LNRO0005``，然后无操作返回。它仍然存在，是因为同一套 SeaBIOS/QEMU 代码还支持通过 ACPI 描述的 virtio-mmio 设备。

q35 的 PCI _PRT 由 AML 留给后续操作系统
-----------------------------------

第九章已经把每个 PCI function 的 ``PCI_INTERRUPT_LINE`` 和 ICH9 PIRQA-H 寄存器配置好。DSDT 中的 ``_PRT`` 则从 ACPI namespace 的角度描述 PCI INTx routing。

两者作用不同：

::

   芯片组配置寄存器
      决定中断事务现在怎样实际传播

   DSDT _PRT
      告诉 ACPI-aware 操作系统这个传播关系是什么

SeaBIOS 当前轻量 parser 不需要完整执行 ``_PRT``。Linux 以后会解析 PCI root bridge 的 ``_PRT``，把 device/pin 映射到 link device 或 GSI，再建立自己的 PCI IRQ routing domain。

qemu_platform_setup 在这里结束
----------------------------

当 RSDP 存在时，SeaBIOS 完成：

.. code-block:: c

   acpi_dsdt_parse();
   virtio_mmio_setup_acpi();
   return;

这里的 ``return`` 结束的是 ``qemu_platform_setup()``，不是整个 SeaBIOS POST。

如果 table-loader 不存在、执行失败或最终没有找到 RSDP，代码才会落入 ``acpi_setup()`` 的 SeaBIOS 内建兼容路径。当前固定 QEMU q35 主线采用成功的 fw_cfg table-loader 路径，不混写 fallback 的生成细节。

第十五章结束时的机器状态
----------------------

控制权目前走过：

::

   qemu_platform_setup()
   → find_acpi_rsdp() 返回 RsdpAddr
   → 从 XSDT 优先、RSDT 兼容地查找 ACPI 表
   → FADT 连接固定 PM 接口、FACS 与 DSDT
   → MADT 描述 CPU、local APIC、I/O APIC 与 interrupt override
   → MCFG 描述 q35 ECAM/MMCONFIG
   → acpi_dsdt_parse()
   → 从 DSDT offset 0x24 解析受限 AML term list
   → 建立 acpi_device 索引
   → 条件 virtio_mmio_setup_acpi()
   → qemu_platform_setup() 返回

此刻：

* 当前执行者：SeaBIOS ``platform_hardware_setup()``；
* 当前主流程 CPU：BSP；
* 模式：32 位保护模式；
* 分页：关闭；
* AP：已完成固件报到并停在 ``HLT``；
* RSDP、RSDT/XSDT 和核心 ACPI 表：已经安装；
* FADT：已公布 ICH9 电源管理、SCI、PM timer 与 reset 接口；
* MADT：已描述 CPU/APIC 拓扑；
* MCFG：已描述 q35 MMCONFIG；
* DSDT：已由 SeaBIOS 建立受限设备索引；
* AML Method：没有被 SeaBIOS 通用执行；
* 条件 virtio-mmio block/SCSI：可能已经启动探测线程；
* qemu_platform_setup：已经返回；
* ``timer_setup()``、``clock_setup()``：尚未执行；
* TPM：尚未初始化；
* 普通 PCI/ATA/AHCI/NVMe/USB block driver：尚未进入 ``device_hardware_setup()``；
* ``BootList``：尚无完整启动设备集合；
* GRUB：尚未被读取或执行；
* Linux：尚未装入内存。

``platform_hardware_setup()`` 接下来依次执行：

.. code-block:: c

   coreboot_platform_setup();
   timer_setup();
   clock_setup();
   tpm_setup();

当前 QEMU/SeaBIOS 构建不会进入 coreboot 平台初始化主线。下一章将从 ``timer_setup()`` 开始，区分“SeaBIOS 内部延时使用的时间源”和“每秒约 18.2 次更新 BDA 的传统 PIT IRQ0”，最后处理 RTC、INT 1Ah 与条件 TPM measured boot 初始化。

资料
----

* `SeaBIOS src/fw/paravirt.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/paravirt.c>`_；
* `SeaBIOS src/fw/biostables.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/biostables.c>`_；
* `SeaBIOS src/fw/dsdt_parser.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/dsdt_parser.c>`_；
* `SeaBIOS src/hw/virtio-mmio.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/virtio-mmio.c>`_；
* `SeaBIOS src/std/acpi.h <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/std/acpi.h>`_；
* `QEMU hw/i386/acpi-build.c <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/acpi-build.c>`_；
* `QEMU hw/acpi/aml-build.c <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/acpi/aml-build.c>`_；
* `QEMU include/hw/acpi/aml-build.h <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/include/hw/acpi/aml-build.h>`_；
* `ACPI Specification <https://uefi.org/specifications>`_；
* `Virtio Specification <https://docs.oasis-open.org/virtio/virtio/v1.2/virtio-v1.2.html>`_。