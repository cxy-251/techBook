第十三章：SeaBIOS 怎样把 CPU、IRQ 和内存信息写成固件表？
=========================================================

上一章结束时，SeaBIOS 已经唤醒所有当前存在的 AP，记录 APIC ID，把每 CPU MSR 设置同步给它们，再将 AP 停在
``HLT``。控制流回到：

::

   qemu_platform_setup()

接下来执行：

.. code-block:: c

   if (MaxCountCPUs <= 255) {
       pirtable_setup();
       mptable_setup();
   }
   smbios_setup();

这三类表都在向后续软件描述机器，但描述对象不同：

``PIRQ table``
   传统 PCI INTx pin 可以通过哪些 PIRQ link 与 ISA IRQ 路由。

``Intel MP table``
   处理器、local APIC、I/O APIC、总线和中断连接关系。

``SMBIOS``
   BIOS、系统、处理器插槽、内存设备和机器身份等清单式信息。

这些表也不等同于 ACPI。现代操作系统通常优先使用 ACPI 的 MADT、``_PRT``、SRAT 等结构；PIRQ 与 MP table 是更早的
兼容接口，SMBIOS则继续广泛用于硬件清单和系统身份信息。

本章沿下面的真实控制流前进：

::

   qemu_platform_setup()
   → 检查 MaxCountCPUs <= 255
   → pirtable_setup()
   → 生成 $PIR header 与 6 个 slot entry
   → 计算 checksum
   → 复制到 F-segment
   → mptable_setup()
   → 建立 PCMP configuration table
   → 写 CPU / PCI / ISA / IOAPIC entry
   → 写 PCI 与 ISA interrupt source entry
   → 写 ExtINT / NMI local interrupt entry
   → 建立 _MP_ floating pointer
   → 复制到 F-segment
   → smbios_setup()
   → 优先读取 QEMU fw_cfg SMBIOS anchor/tables
   → 条件补入 SeaBIOS Type 0
   → 或回退到 SeaBIOS legacy SMBIOS 生成器
   → 安装 SMBIOS 2.1 或 3.0 entry point
   → smbios_setup() 返回

本章结束在 ACPI table loader 之前。

本章固定使用：

::

   SeaBIOS repository: coreboot/seabios
   SeaBIOS commit:     c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   QEMU repository:    qemu/qemu
   QEMU commit:        a759542a2c62f0fd3b65f5a66ad9868201014669

为什么 MaxCountCPUs 超过 255 时跳过两张旧表
---------------------------------------

源码把 PIRQ table 与 MP table 放在同一个条件中：

.. code-block:: c

   if (MaxCountCPUs <= 255) {
       pirtable_setup();
       mptable_setup();
   }

真正与 255 限制直接相关的是 legacy MP table。它的 processor entry 使用 8 位 APIC ID，SeaBIOS 的
``FoundAPICIDs`` 也是 256 位 bitmap，只能直接描述 APIC ID ``0-255``。

当 ``MaxCountCPUs`` 超过 255 时，系统需要 x2APIC 和现代 ACPI MADT 等更宽的描述方式。SeaBIOS因此不再生成 MP table。

PIRQ table 本身不描述 CPU ID，仍因源码外层条件而一同被跳过。这是当前实现的控制流，不应误解成 PIRQ 规范本身有
255 CPU 限制。

PIRQ table 是什么
-----------------

PIRQ 是 PCI Interrupt Routing 的传统 BIOS 数据结构。PCI 设备提供最多四个 legacy interrupt pin：

::

   INTA#
   INTB#
   INTC#
   INTD#

这些 pin 不一定一一对应固定 ISA IRQ。主板或芯片组通常先把 pin 接到 PIRQ link，再由 interrupt router 把 link 映射到
IRQ 线。

传统软件需要知道：

* 某个 PCI slot 的 INTA-D 分别接到哪个 link；
* 每个 link 允许使用哪些 ISA IRQ；
* interrupt router 位于哪个 PCI BDF；
* 表本身是否完整且 checksum 正确。

SeaBIOS 生成的是一个静态 emulator compatibility table
------------------------------------------------------

``src/fw/pirtable.c`` 定义：

.. code-block:: c

   struct pir_table {
       struct pir_header pir;
       struct pir_slot slots[6];
   };

header 采用：

::

   version             = 0x0100
   size                = sizeof(struct pir_table)
   router_devfunc      = 0x08
   compatible_devid    = 0x122e8086

``router_devfunc = 0x08`` 编码 device 1、function 0；``0x122e8086`` 则是 Intel vendor/device 组合的传统兼容标识。

这里需要特别谨慎：当前固定平台是 q35，实际 ICH9 LPC function 常见于 ``00:1f.0``，前面章节也已经通过 ICH9
``PIRQA-H`` 寄存器完成真实中断路由。这个静态 ``$PIR`` 表保留的是老式 emulator/BIOS 兼容布局，不能用它反推当前
q35 LPC 的真实 BDF。

SeaBIOS 源码自己也写着：

::

   DO NOT ADD NEW FEATURES HERE

现代 q35 路由的权威描述将在 ACPI ``_PRT`` 等结构中出现。

六个 slot entry 怎样轮转 INTA-D
------------------------------

表中有六个 slot entry：

* 第一个表示 embedded PCI-to-ISA 位置，``slot_nr = 0``；
* 后五个表示 PCI slot 1-5。

每个 entry 为 INTA-D 指定 link ``0x60-0x63``。不同 slot 会旋转 link：

::

   slot 1: INTA→0x61 INTB→0x62 INTC→0x63 INTD→0x60
   slot 2: INTA→0x62 INTB→0x63 INTC→0x60 INTD→0x61
   slot 3: INTA→0x63 INTB→0x60 INTC→0x61 INTD→0x62

这种 rotation 用来把不同 slot 的 INTA 请求分散到不同 PIRQ link，避免所有设备默认集中到同一条线。

bitmap 0xdef8 表示哪些 IRQ 可选
------------------------------

每个 link 都携带：

::

   bitmap = 0xdef8

bitmap 的 bit ``n`` 表示 IRQ ``n`` 可用。展开后允许：

::

   IRQ 3, 4, 5, 6, 7,
   IRQ 9, 10, 11, 12,
   IRQ 14, 15

IRQ0、1、2、8、13 被排除，因为它们具有时钟、键盘、级联、RTC、数学异常等传统固定用途。

这只是可选集合，不是当前实际路由。前面 q35 ICH9 初始化已经把 PIRQ A-H 实际写到 IRQ10/IRQ11。

PIRQ checksum 怎样生成
---------------------

``pirtable_setup()`` 先写入 signature：

::

   $PIR

然后执行：

.. code-block:: c

   PIR_TABLE.pir.checksum -=
       checksum(&PIR_TABLE, sizeof(PIR_TABLE));

目标是让整个表所有字节按 8 位求和后结果为 0。

``copy_pir()`` 会再次验证：

* signature 正确；
* size 至少覆盖 header；
* checksum 为 0；
* 尚未安装另一份 PIRQ table。

验证通过后，表被复制到 F-segment 分配区，并由 ``PirAddr`` 保存最终地址。

为什么表要复制到 F-segment
-------------------------

传统 BIOS 数据结构通常需要位于 1 MiB 以下、可由实模式软件扫描的区域。SeaBIOS 的 F-segment 位于传统 BIOS
``0xf0000-0xfffff`` 范围。

生成用的 C 对象可以在普通数据区，最终对外公布的副本必须落在旧软件能够找到的位置。

MP table 描述的范围比 PIRQ 更广
-----------------------------

``mptable_setup()`` 生成 Intel MultiProcessor Specification 1.4 风格结构，包含两部分：

``MP Floating Pointer Structure``
   以 ``_MP_`` 开头，告诉软件 configuration table 在哪里。

``MP Configuration Table``
   以 ``PCMP`` 开头，包含 CPU、bus、I/O APIC 和 interrupt entries。

SeaBIOS 先从临时高端内存申请 32 KiB：

.. code-block:: c

   config = malloc_tmp(32 * 1024);

这块空间用于逐项构造，完成后再复制到最终传统 BIOS 区。

Configuration header 保存什么
-----------------------------

SeaBIOS 写入：

::

   signature = "PCMP"
   spec      = 4
   local APIC address = 0xfee00000

还填入 OEM ID、product ID、entry count、总长度与 checksum。

``spec = 4`` 表示 MP Specification 1.4。local APIC 地址来自固定：

::

   BUILD_APIC_ADDR = 0xfee00000

后续软件不用猜 local APIC MMIO 基址。

为什么 MP table 不一定列出每个 SMT 逻辑线程
----------------------------------------

SeaBIOS 读取 ``CPUID.01H`` 的 processor signature、feature bits 和 logical processor count。

如果 CPUID 的 HTT bit 存在，源码计算：

.. code-block:: c

   pkgcpus = (ebx >> 16) & 0xff;
   pkgcpus = round_up_to_power_of_two(pkgcpus);

随后 CPU entry 循环不是 ``i++``，而是：

.. code-block:: c

   for (i = 0; i < MaxCountCPUs; i += pkgcpus)

源码注释明确说明：

::

   Only populate the MPS tables with the first logical CPU in each package

因此 legacy MP table 可能只列每个 package 的第一个逻辑处理器，而不是完整展示 SMT sibling。现代操作系统应依赖
ACPI MADT 和 CPUID topology，而不是把旧 MP table 当成完整现代 CPU 拓扑。

CPU entry 怎样区分 present 与 possible
------------------------------------

每个 processor entry 写入：

* APIC ID；
* local APIC version；
* CPUID signature；
* CPUID feature flags；
* enabled flag；
* bootstrap processor flag。

flag 计算为：

.. code-block:: c

   enabled = apic_id_is_present(i) ? 1 : 0;
   bootstrap = (i == 0) ? 2 : 0;

上一章实际运行过的 CPU 才会在 ``FoundAPICIDs`` 中出现，因此 enabled bit 来自真实 AP 报到结果。

循环上界使用 ``MaxCountCPUs``，所以表可以包含当前未启用但处于最大范围内的位置；这些 entry 的 enabled bit 为 0。

代码还假定 BSP 使用 APIC ID 0。固定 QEMU PC 平台通常满足这个约定，不能把它扩展成所有 x86 平台的架构定律。

MP table 只建立 root PCI bus 与 ISA bus
-------------------------------------

如果 ``PCIDevices`` 非空，SeaBIOS 添加：

::

   bus 0: "PCI   "

随后总是添加：

::

   next bus id: "ISA   "

它没有在这里完整描述前面发现的所有 secondary PCI bus。这再次体现 MP table 是兼容结构；复杂 PCIe 拓扑和 bridge
routing 将由 ACPI 与 PCI 配置空间本身描述。

I/O APIC entry
--------------

SeaBIOS 添加一个 enabled I/O APIC：

::

   APIC ID  = BUILD_IOAPIC_ID = 0
   version  = 0x11
   address  = 0xfec00000

``0xfec00000`` 与前面 PCI MMIO 窗口的上界相邻。第八章已经避免把普通 PCI BAR 分配到这个固定 I/O APIC MMIO
范围。

PCI interrupt source entry 怎样生成
---------------------------------

SeaBIOS 遍历 ``PCIDevices``，只处理 bus 0。遇到第一个非 bus 0 设备后结束这段扫描。

对于每个使用 INTx 的 function，它读取：

::

   PCI_INTERRUPT_PIN
   PCI_INTERRUPT_LINE

前者是 INTA-D pin，后者是第九章已经写入的 legacy IRQ line。

source bus IRQ 编码为：

.. code-block:: c

   (device << 2) | (pin - 1)

目的端是 I/O APIC，``dstirq`` 就是 ``PCI_INTERRUPT_LINE``。

同一个 device 的相同 pin 只生成一次 entry，避免多 function 设备重复描述同一条共享 pin。

MP table 使用了前面章节的真实结果
--------------------------------

这一层不是重新计算 PCI 路由。它把已经配置好的结果序列化：

::

   第九章：
      PCI pin → q35 slot rotation → IRQ10/IRQ11
      写入 PCI_INTERRUPT_LINE

   本章：
      读取 PCI_INTERRUPT_PIN / LINE
      → 写成 MP interrupt source entry

固件表因此是机器当前配置的描述，不是设备配置动作本身。

ISA IRQ entry 与 IRQ0 override
-----------------------------

SeaBIOS 对 ISA IRQ0-15 建立 I/O APIC source entries，但跳过：

::

   BUILD_PCI_IRQS = IRQ5, IRQ9, IRQ10, IRQ11

这些 IRQ 被预留给 PCI/ACPI 相关用途，避免再生成普通 ISA identity mapping。

QEMU通过 fw_cfg 提供：

::

   etc/irq0-override

当前 QEMU PC 路径发布值 1。启用时：

* ISA IRQ0 被路由到 I/O APIC input 2；
* ISA IRQ2 source entry 被省略。

这是经典 PC 中 PIT IRQ0 与 8259A cascade IRQ2 在 I/O APIC 模式下的兼容处理。

Local interrupt entries 与上一章 LINT 配置对应
-------------------------------------------

MP table 最后添加两条 local interrupt assignment：

``ExtINT``
   ISA bus IRQ0 → BSP APIC ID 0 的 LINT0。

``NMI``
   ISA bus source → 所有 local APIC 的 LINT1。

上一章已经实际把 BSP local APIC 配置为：

::

   LINT0 = ExtINT
   LINT1 = NMI

本章把同样的连接关系写进 MP table，供旧式多处理器软件读取。

_MP_ floating pointer 怎样指向 PCMP table
---------------------------------------

完成所有 entry 后，SeaBIOS 计算 configuration table 长度、entry count 和 checksum。

然后构造 16 字节 floating pointer：

::

   signature = "_MP_"
   physaddr  = temporary PCMP address
   length    = 1             # 16-byte units
   spec_rev  = 4

``copy_mptable()`` 验证 signature、floating checksum 和 PCMP length，再把两部分一起复制到 F-segment。

复制后必须修改 floating pointer 中的 ``physaddr``，让它指向新副本后面的 configuration table，并重新计算 checksum。

为什么 MP table 可能因为过大而被丢弃
----------------------------------

SeaBIOS 规定：

::

   BUILD_MAX_MPTABLE_FSEG = 600 bytes

如果 floating pointer 加 configuration table 超过 600 字节，``copy_mptable()`` 会打印跳过信息，不安装最终副本。

所以外层 ``MaxCountCPUs <= 255`` 只是 APIC ID 表达能力限制，不保证最终表一定足够小。CPU entry 或 interrupt entry 太多时，
旧表仍可能超过 F-segment 预算。

现代 ACPI 表没有这个 600 字节兼容上限，因此大型系统更依赖 MADT 等现代结构。

SMBIOS 与中断路由无关
--------------------

PIRQ 和 MP table 主要描述中断与处理器连接。SMBIOS 的定位不同：它是一套带类型编号的机器信息结构。

常见类型包括：

::

   Type 0    BIOS Information
   Type 1    System Information
   Type 3    System Enclosure
   Type 4    Processor Information
   Type 16   Physical Memory Array
   Type 17   Memory Device
   Type 19   Memory Array Mapped Address
   Type 20   Memory Device Mapped Address
   Type 32   System Boot Information
   Type 127  End-of-Table

操作系统和工具可以通过 SMBIOS 获得厂商、产品名、UUID、CPU socket、内存条式描述和 BIOS 版本等信息。

smbios_setup 优先采用 QEMU 预生成表
---------------------------------

``smbios_setup()`` 首先调用：

.. code-block:: c

   if (smbios_romfile_setup())
       return;

它查找两个 fw_cfg romfile：

::

   etc/smbios/smbios-anchor
   etc/smbios/smbios-tables

QEMU 可以依据 machine type、命令行 SMBIOS 参数、CPU 型号与内存布局提前生成 anchor 和 structure table blob，再通过
fw_cfg 交给 SeaBIOS。

这种分工让 QEMU 决定虚拟机向客户操作系统呈现的机器身份，SeaBIOS 负责把数据放到客户机内存并完成 entry point。

支持 SMBIOS 2.1 与 SMBIOS 3.0 entry point
---------------------------------------

SeaBIOS 根据 anchor 长度和 signature 区分：

``SMBIOS 2.x``
   signature 为 ``_SM_``，还包含 ``_DMI_`` intermediate anchor。

``SMBIOS 3.x``
   signature 为 ``_SM3_``。

两条路径都会验证结构大小和 signature，再建立最终 table blob、修正地址与长度、计算 checksum，最后把 entry point 复制到
F-segment。

SMBIOS 2.x entry point 使用 32 位 structure table address；SMBIOS 3.x entry point支持更宽地址字段。当前 SeaBIOS 分配器仍把
最终 blob 放在其可管理的低于 4 GiB 区域。

为什么 SeaBIOS 可能补一个 Type 0
------------------------------

QEMU提供的 ``etc/smbios/smbios-tables`` 不一定包含 BIOS Information。SeaBIOS 扫描全部 structure：

* 找到 Type 0：保持 QEMU 提供内容；
* 没找到 Type 0：在最终 blob 前补入自己的 Type 0。

补入的默认字符串包括：

::

   BIOS vendor  = SeaBIOS
   BIOS version = SeaBIOS build VERSION
   BIOS date    = 04/01/2014

日期是源码中的兼容默认字符串，不代表当前编译或启动日期。

SMBIOS table blob 放在 F-segment 还是高端内存
------------------------------------------

如果最终 structure table 长度不超过：

::

   BUILD_MAX_SMBIOS_FSEG = 600 bytes

SeaBIOS 将 blob 放进 F-segment。超过 600 字节则放入高端内存。

entry point 本身仍复制到 F-segment，传统扫描程序先找到 entry point，再通过其中的 physical address 定位真正 table blob。

这允许 SMBIOS 包含较多 CPU 与内存结构，又不耗尽狭小的 F-segment。

QEMU 没有提供完整 anchor/tables 时怎样回退
---------------------------------------

如果两个 fw_cfg 文件不存在、大小不对或 signature 无效，``smbios_setup()`` 调用：

.. code-block:: c

   smbios_legacy_setup();

legacy 生成器先申请 32 KiB temporary buffer，然后按类型依次构造表。

它还支持更细粒度的 QEMU 输入：

::

   smbios/field<type>-<offset>
   smbios/table<type>-<instance>

外部 table 可以替换 SeaBIOS 对某个 type 的默认生成；外部 field 可以覆盖单个字段。

legacy Type 4 为什么按 MaxCountCPUs 生成
--------------------------------------

处理器结构循环是：

.. code-block:: c

   for (cpu_num = 1;
        cpu_num <= MaxCountCPUs;
        cpu_num++)
       add_struct(4, ...);

所以 Type 4 数量按最大 CPU 容量，而不是仅按本次实际 ``CountCPUs``。

这适合 CPU hotplug 模型：SMBIOS 可以提前描述潜在 socket/CPU 位置。但 legacy 默认 Type 4 的 status 直接写成“socket populated,
CPU enabled”，无法精细表达现代复杂 hotplug 状态。这也是优先使用 QEMU 预生成 SMBIOS 的原因之一。

内存设备为什么按 16 GiB 分块
--------------------------

legacy 生成器计算：

.. code-block:: c

   ram_mb = (RamSize + RamSizeOver4G) >> 20;
   nr_mem_devs = (ram_mb + 0x3fff) >> 14;

``0x4000 MiB`` 是 16 GiB，因此它把总内存拆成最多 16 GiB 的 Type 17 Memory Device chunks。

例如 40 GiB 内存会形成近似：

::

   device 0: 16 GiB
   device 1: 16 GiB
   device 2:  8 GiB

这些是 SMBIOS 逻辑 memory device，不一定对应宿主机真实 DIMM，也不表示 QEMU 内部一定创建了三根物理内存条。

Type 19 怎样绕过 4 GiB PCI hole
------------------------------

SeaBIOS 为低端连续 RAM建立 Type 19：

::

   start = 0
   size  = RamSize

如果存在 4 GiB 以上 RAM，再建立第二个 Type 19：

::

   start = 4096 MiB
   size  = RamSizeOver4G

这不会把低于 4 GiB 的 PCI hole 当成系统 RAM。低端 memory range 到 ``RamSize`` 结束，高端 memory range 从 4 GiB重新开始。

Type 20 再把每个逻辑 Type 17 device 映射到对应 Type 19 address range。

Type 32 与 Type 127
------------------

legacy 生成器加入：

``Type 32``
   System Boot Information，默认 boot status 为“no errors detected”。

``Type 127``
   End-of-Table marker。

Type 127 必须最后出现。SeaBIOS会在它之前加入所有尚未消费的外部 SMBIOS structures。

legacy 路径最终生成 SMBIOS 2.4 entry point
---------------------------------------

``smbios_21_entry_point_setup()`` 建立：

::

   signature       = "_SM_"
   intermediate    = "_DMI_"
   major.minor     = 2.4
   BCD revision    = 0x24

它填写 structure table address、length、structure count、max structure size，并分别计算主 checksum 和 intermediate checksum。

然后 ``copy_smbios_21()`` 验证两段 checksum，再把 entry point 复制到 F-segment。

表已经生成，ACPI 仍未开始
----------------------

本章三类表完成后：

* legacy PCI routing 可以通过 ``$PIR`` 被旧软件发现；
* legacy SMP 软件可以通过 ``_MP_`` 找到 CPU、APIC、bus 与 IRQ 连接；
* SMBIOS 软件可以通过 ``_SM_`` 或 ``_SM3_`` 找到系统、CPU 和内存清单。

仍然没有：

* ACPI RSDP、RSDT/XSDT 的当前装载确认；
* MADT 中完整 CPU 与 I/O APIC 描述；
* DSDT ``_PRT`` 中 q35 PCI routing；
* FADT 电源管理接口描述；
* 存储控制器驱动和磁盘读取；
* GRUB。

第十三章结束时的机器状态
----------------------

控制权目前走过：

::

   qemu_platform_setup()
   → smp_setup() 返回
   → 条件 MaxCountCPUs <= 255
   → pirtable_setup()
   → $PIR table checksum 与 F-segment copy
   → mptable_setup()
   → PCMP CPU/bus/IOAPIC/interrupt entries
   → _MP_ floating pointer
   → F-segment copy
   → smbios_setup()
   → 优先使用 QEMU fw_cfg anchor/tables
   → 条件补入 SeaBIOS Type 0
   → 或 legacy SMBIOS fallback
   → 安装 SMBIOS entry point
   → smbios_setup() 返回

此刻：

* 当前执行者：SeaBIOS ``qemu_platform_setup()``；
* 当前主流程 CPU：BSP；
* 模式：32 位保护模式；
* 分页：关闭；
* AP：已完成固件报到并停在 ``HLT``；
* PIRQ table：在配置允许且 ``MaxCountCPUs <= 255`` 时已安装；
* MP table：在配置允许、CPU 范围与 F-segment 大小允许时已安装；
* SMBIOS：已通过 QEMU romfile 路径或 SeaBIOS legacy 路径安装；
* legacy 表最终 entry/floating pointer：位于 F-segment；
* SMBIOS structure blob：位于 F-segment 或高端内存；
* ACPI table loader：尚未执行；
* ACPI RSDP：尚未由当前阶段确认；
* ATA、AHCI、NVMe、USB、virtio 与网络驱动：尚未探测介质；
* ``BootList``：尚无具体启动设备；
* GRUB：尚未被读取或执行；
* Linux：尚未装入内存。

``smbios_setup()`` 返回后，下一段是：

.. code-block:: c

   if (CONFIG_FW_ROMFILE_LOAD) {
       loader_err = romfile_loader_execute("etc/table-loader");
       RsdpAddr = find_acpi_rsdp();
       ...
   }

下一章将进入 QEMU 的 ACPI ``table-loader``：它怎样分配 table blob、执行 pointer/length/checksum patch，怎样找到 RSDP，
以及为什么现代 q35 的 CPU、APIC、PCI routing 和电源管理最终主要由 ACPI 表描述。

资料
----

* `SeaBIOS src/fw/pirtable.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/pirtable.c>`_；
* `SeaBIOS src/fw/mptable.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/mptable.c>`_；
* `SeaBIOS src/fw/smbios.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/smbios.c>`_；
* `SeaBIOS src/fw/biostables.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/biostables.c>`_；
* `SeaBIOS src/fw/paravirt.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/paravirt.c>`_；
* `QEMU hw/i386/fw_cfg.c <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/fw_cfg.c>`_；
* `PCI BIOS Specification and PCI Firmware Specification <https://pcisig.com/specifications>`_；
* `System Management BIOS Reference Specification <https://www.dmtf.org/standards/smbios>`_；
* `Intel MultiProcessor Specification <https://www.intel.com/design/pentium/datashts/242016.htm>`_。