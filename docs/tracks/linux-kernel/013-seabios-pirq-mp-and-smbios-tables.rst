第十三章：SeaBIOS 怎样把 CPU、IRQ 和内存信息写成固件表？
=========================================================

第十二章结束时，BSP已经从 ``smp_setup()`` 返回。CPU仍在32位保护模式，分页关闭、
A20开启、IF=0，CMOS NMI保持屏蔽；当前执行者仍是SeaBIOS ``MainThread``，没有发生
线程切换。PIC mask也没有改变：master只放行级联IRQ2，slave只放行IRQ13。

需要先保留第十二章已经收紧的CPU数量分支。当前固定条件没有规定 ``-smp``：

* 无override时QEMU缺省只有BSP，没有AP执行 ``entry_smp``；
* 显式配置多CPU时，在场AP才已经登记APIC ID、重放日志中实际保留的MSR前缀，并在
  IF=0下停在HLT循环；
* ``MaxCountCPUs`` 保存的是QEMU发布的APIC-ID上界，不是已经启动CPU的精确数量。

接下来的真实控制流是：

.. code-block:: c

   if (MaxCountCPUs <= 255) {
       pirtable_setup();
       mptable_setup();
   }
   smbios_setup();

这三类表都是给之后的软件读取的描述对象。它们不会在这里重新编程PIC、IOAPIC、
local APIC、ICH9 PIRQ寄存器或DRAM控制器，也不会唤醒新的CPU。

为什么PIR和MP共享255这个外层门
---------------------------------

SeaBIOS只在 ``MaxCountCPUs <= 255`` 时调用 ``pirtable_setup()`` 与
``mptable_setup()``。MP结构中的APIC ID字段只有8位；SeaBIOS把这个限制放在两次
兼容表调用外层，因此一旦APIC-ID上界超过255，两张表一起跳过。

这个判断不等于“当前有255颗CPU”。例如只有少量在场vCPU、但machine topology允许
更大的APIC-ID空间时， ``MaxCountCPUs`` 仍可能大于实际 ``CountCPUs``。反过来，
缺省单CPU的上界满足条件时，两张兼容表仍会构造。

两个函数内部还有各自的构建开关。固定SeaBIOS QEMU默认配置启用
``CONFIG_PIRTABLE`` 与 ``CONFIG_MPTABLE``，所以正常路径进入构造；但后续分配、
校验与FSEG复制仍可能失败，调用发生不能扩大成表必然安装成功。

PIR表从一份静态模板开始
------------------------

``pirtable_setup()`` 不遍历当前 ``PCIDevices`` 来推导q35的实际路由，而是修改并复制
``src/fw/pirtable.c`` 中的静态 ``pir_table``。表头的关键值是：

::

   signature          = "$PIR"
   version            = 0x0100
   table size         = header + 6 slot entries
   router bus         = 0
   router devfn       = 0x08          # 00:01.0
   compatible device  = 8086:122e
   exclusive IRQs     = 0

六个slot entry覆盖device 1至6、function 0；slot number依次为0至5。每个slot有INTA到
INTD四个pin，link值在 ``0x60``、 ``0x61``、 ``0x62``、 ``0x63`` 间轮转，形成传统
PCI slot swizzle。所有link都带相同bitmap：

::

   bitmap = 0xdef8
          = IRQ3,4,5,6,7,9,10,11,12,14,15

这个bitmap只表达兼容软件可以尝试的IRQ集合，不是“当前每个pin已经接到哪个IRQ”。

为什么这张PIR表不能冒充q35真实路由
-----------------------------------

固定平台是q35，ICH9 LPC通常位于 ``00:1f.0``，有PIRQA—PIRQH八条路由输入；前面的
PCI章节已经按q35逻辑为设备写入 ``PCI_INTERRUPT_LINE`` 并设置ICH9路由寄存器。
静态PIR表却保留router devfn ``00:01.0``、四个link和i440fx时代的兼容device ID。

因此本章必须把三层信息分开：

::

   已生效硬件状态       = q35/ICH9寄存器与设备PCI_INTERRUPT_LINE
   legacy发现接口       = 本节复制的静态$PIR表
   现代OS权威描述       = 后续ACPI namespace中的_PRT等对象

``pirtable_setup()`` 只填入signature并令checksum字节减去整表8位和，使最终字节和为
0。 ``copy_pir()`` 随后重新检查signature、最小长度与checksum；若已有 ``PirAddr``、
校验失败或FSEG分配失败，它直接保留旧值或空值。成功时才把整表复制到FSEG并发布
``PirAddr``。

MP表为什么先在32 KiB临时区构造
--------------------------------

``mptable_setup()`` 从 ``ZoneTmp`` 申请32 KiB并清零。分配失败只告警并返回；成功后，
BSP在这块临时区依次写MP Configuration Table Header和entry。表头包括：

::

   signature       = "PCMP"
   spec revision   = 4
   OEM ID          = BUILD_CPUNAME8       # 默认BOCHSCPU
   product ID      = "0.1"
   local APIC addr = 0xfee00000

这仍是BSP普通POST控制流中的内存写入，没有锁竞争。已经停驻的AP不读取这块临时区。

CPU entry按package跨度写入
--------------------------

SeaBIOS读取CPUID leaf 1。若EDX的HTT位没有设置， ``pkgcpus`` 保持1；若设置，则取
EBX[23:16]的logical processor count并向上取到2的幂。随后循环不是逐一走过每个
可能APIC ID，而是：

.. code-block:: c

   for (i = 0; i < MaxCountCPUs; i += pkgcpus)
       mptable_init_processor(..., apic_id_is_present(i), i == 0);

也就是说，MP表为每个推导出的package写一个CPU entry，entry的APIC ID取该package
第一个logical ID。 ``apic_id_is_present(i)`` 决定enabled flag；ID 0还设置BSP flag。
local APIC version来自当前BSP的APIC version register。

这里有三条不能越过固定条件的边界：

#. CPU模型没有固定，HTT位和EBX logical count不能提前写死；
#. ``MaxCountCPUs`` 是APIC-ID上界，循环可以写disabled的潜在package entry；
#. 缺省单CPU路径只有ID 0为present；只有显式多CPU路径才可能让更多entry enabled。

MP bus与IOAPIC entry
--------------------

固定q35已经枚举到PCI设备，所以 ``PCIDevices`` 非空。SeaBIOS先写PCI bus 0，再写
ISA bus 1；若列表为空，代码才会省略PCI并让ISA使用bus ID 0。然后写一个I/O APIC
entry：

::

   id       = BUILD_IOAPIC_ID = 0
   version  = 0x11
   enabled  = yes
   address  = 0xfec00000

这些值描述兼容MP视图。写entry不会访问 ``0xfec00000``，也不会改动第十二章已经建立
的BSP LINT状态。

PCI INTx entry怎样从已枚举设备生成
-----------------------------------

``mptable_setup()`` 遍历按BDF排序的 ``PCIDevices``，只处理bus 0；一遇到后续bus便
结束循环。每个function读取 ``PCI_INTERRUPT_PIN`` 与 ``PCI_INTERRUPT_LINE``。
没有INTx pin的设备跳过；同一device的同一pin只写一次，避免多function设备重复描述
共享slot pin。

MP entry把source编码为PCI bus/device/pin，把destination APIC ID写成
``BUILD_IOAPIC_ID``，并把刚读到的 ``PCI_INTERRUPT_LINE`` 原样用作destination
input。第九章已经按q35 slot/pin映射计算并写好了这个配置字节，所以本章消费的是已
提交结果，不再调用平台路由函数重新计算，也不触发任何中断。

ISA源、IRQ0 override与local interrupt
--------------------------------------

SeaBIOS再为传统ISA IRQ 0—15建立I/O interrupt entry。 ``BUILD_PCI_IRQS`` 把
IRQ5、9、10、11保留给PCI兼容路由，这四项从ISA循环跳过。

SeaBIOS在 ``etc/irq0-override`` 文件缺失时使用0；固定QEMU PC fw_cfg则无条件为
``FW_CFG_IRQ0_OVERRIDE`` 发布值1，所以当前q35正常路径命中override。ISA timer的
source仍是IRQ0，但destination改为I/O APIC input 2，同时不再为source IRQ2另建普通
ISA项。若该fw_cfg输入为0，IRQ0才保持接到input 0。

最后两项不是I/O APIC source，而是local interrupt：

::

   ExtINT: ISA IRQ0 → APIC ID 0, LINT0
   NMI:    source 0 → all APIC IDs (0xff), LINT1

它们与第十二章对BSP LINT0/LINT1的实际编程相呼应，但这里只是在表中发布发现信息。

为什么MP表可能构造成功却没有安装
----------------------------------

全部entry完成后，SeaBIOS填写header length、entry count与header checksum，再紧跟一份
16字节 ``_MP_`` floating pointer并计算其checksum。 ``copy_mptable()`` 会检查floating
signature、物理配置表指针和floating checksum，然后计算：

::

   total = floating length + PCMP base-table length

FSEG中的固定上限是 ``BUILD_MAX_MPTABLE_FSEG = 600``。超过上限时复制被放弃；成功时
它把floating structure与PCMP表连续复制到新FSEG空间，重写floating structure中的
物理指针并重算其checksum。复制函数没有在这里重新验证PCMP signature或PCMP
checksum。临时32 KiB区最后总会释放，所以是否留下一张可发现MP表取决于FSEG复制
是否成功。

SMBIOS的输入其实已经由QEMU准备
------------------------------

``smbios_setup()`` 不受255这个外层门限制。固定提交中的q35别名指向
``pc-q35-11.1``；PC machine class默认：

::

   smbios_defaults          = true
   default SMBIOS ep type   = AUTO
   legacy mode              = false

QEMU在客户机执行固件之前已经按machine、CPU socket与E820 RAM布局生成结构blob。
``AUTO`` 先尝试SMBIOS 2.x约束；若表长、结构数等不能满足2.x，才丢弃该次结果并尝试
SMBIOS 3.x。生成成功后，fw_cfg发布：

::

   etc/smbios/smbios-tables
   etc/smbios/smbios-anchor

因此不能仅凭最新q35就断言入口一定是SMBIOS 3。固定条件没有规定RAM大小、socket数或
``-smbios`` 覆盖，正确结论是按 ``AUTO`` 的2.x优先、3.x回退选择。

SeaBIOS怎样接管QEMU的anchor
---------------------------

``smbios_romfile_setup()`` 必须同时找到anchor与tables。它只接受两种大小和签名组合：

* ``struct smbios_21_entry_point`` 与 ``_SM_``；
* ``struct smbios_30_entry_point`` 与有效 ``_SM3_`` signature。

SeaBIOS先按anchor声明的table length核对fw_cfg文件大小，再把QEMU结构blob读入临时
high memory扫描。若blob已经有Type 0，保持它；若缺少Type 0且16位总长度仍容纳得下，
就在最终blob前置一项SeaBIOS Type 0，vendor为 ``SeaBIOS``、version为当前SeaBIOS
``VERSION``、date为 ``04/01/2014``。

最终结构blob不超过600字节时放入FSEG，否则放入high zone。2.x入口需要32位表地址、
16位表长，并更新max structure size、structure count及两段checksum；3.x入口更新64位
address字段、max size与checksum。入口本身经 ``copy_smbios_21()`` 或
``copy_smbios_30()`` 复制到FSEG，成为后续软件可扫描对象。

这一步建立的是新的固件表内存所有权：临时输入buffer释放，最终结构blob和FSEG入口
保留。它没有创建SeaBIOS线程，也没有改变CPU mode或中断开关。

legacy SMBIOS为何只能是失败回退
--------------------------------

只有romfile输入缺失、anchor无效、tables长度不匹配或最终分配失败时，
``smbios_setup()`` 才调用 ``smbios_legacy_setup()``。该函数在32 KiB临时区自己生成
Type 0、1、3、4、16、17、19、20、32、127，并接纳外部提供的替换项，最后安装一份
SMBIOS 2.4入口。

legacy路径按 ``1..MaxCountCPUs`` 为每个编号生成Type 4，而且默认把每项status标成
“socket populated, CPU enabled”；RAM则按最多16 GiB一个Type 17切块。这是旧接口的
兼容行为，不等同于QEMU正常路径按实际socket和E820生成的内容，更不能用它证明当前
有 ``MaxCountCPUs`` 颗在场CPU。

三类表完成后的精确边界
------------------------

正常固定q35默认路径下，BSP已经尝试安装静态PIR表、兼容MP表，并从QEMU fw_cfg接管
SMBIOS结构。任一兼容表的具体存在仍受本节列出的门与分配结果约束；多CPU配置下的AP
仍停在各自HLT循环，缺省单CPU路径仍没有AP。

``qemu_platform_setup()`` 的下一条语句不是启动设备，而是进入ACPI romfile loader：

.. code-block:: c

   if (CONFIG_FW_ROMFILE_LOAD) {
       int loader_err;
       loader_err = romfile_loader_execute("etc/table-loader");
       ...
   }

本章停在调用 ``romfile_loader_execute()`` 之前。

本章结束状态
------------

* current executor：BSP上的SeaBIOS ``MainThread``；
* CPU/mode：32位保护模式，分页关闭，A20开启，IF=0，CMOS NMI屏蔽；
* PIC mask：master仅IRQ2、slave仅IRQ13；
* AP状态：缺省无AP；显式多CPU时，仅在场AP停在IF=0的HLT循环；
* ``MaxCountCPUs``：APIC-ID上界，未改写；
* ``PCIDevices``：保持，可供后续固件阶段使用；
* PIR表：在 ``MaxCountCPUs <= 255``、开关开启且校验/分配成功时位于FSEG；
* MP表：同一外层门下构造，且总复制长度不超过600并成功分配时位于FSEG；
* QEMU SMBIOS输入：默认q35按 ``AUTO`` 生成，2.x优先、3.x回退；
* SMBIOS最终blob/入口：romfile成功时已由SeaBIOS修补并安装；失败时才尝试legacy 2.4；
* hardware routing/APIC/RAM state：未被三类表重新配置；
* next entry： ``romfile_loader_execute("etc/table-loader")``。

关键边界
--------

#. ``MaxCountCPUs <= 255`` 检查的是APIC-ID上界，不是在场CPU数。
#. AP执行与HLT驻留是显式多CPU条件分支，不能写成缺省固定事实。
#. PIR表是静态legacy兼容模板，不是q35 ICH9真实路由寄存器的镜像。
#. ``copy_pir()`` 成功后才发布 ``PirAddr``；调用本身不保证表存在。
#. MP CPU entry按CPUID推导的package跨度写入，enabled位来自present APIC-ID集合。
#. MP表只处理bus 0 PCI设备，并对同device/pin去重。
#. IRQ0 override、ExtINT与NMI entry只发布发现信息，不重新编程中断控制器。
#. MP临时表可以成功构造，却因600字节FSEG上限而不被安装。
#. 最新q35的SMBIOS ``AUTO`` 先尝试2.x，不等于无条件选择3.x。
#. QEMU正常romfile路径与SeaBIOS legacy fallback是互斥选择，不能拼成一张实际表。
#. legacy Type 4按 ``MaxCountCPUs`` 生成，不能反证相同数量CPU已经在场。
#. 本章没有进入ACPI loader，也没有改变CPU执行上下文。

下一入口
--------

下一章从：

::

   qemu_platform_setup
   → romfile_loader_execute("etc/table-loader")
   → load fixed-size linker command entries
   → allocate ACPI blobs in HIGH/FSEG
   → patch pointers and checksums
   → find_acpi_rsdp()

开始，并区分loader函数级失败、逐命令软失败与RSDP独立搜索结果。

资料
----

* `SeaBIOS固定提交：QEMU平台表调用顺序 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/paravirt.c#L282-L324>`_
* `SeaBIOS固定提交：静态PIR表与复制入口 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/pirtable.c#L1-L103>`_
* `SeaBIOS固定提交：MP表CPU、中断与floating pointer构造 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/mptable.c#L1-L197>`_
* `SeaBIOS固定提交：PIR/MP复制验证与600字节边界 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/biostables.c#L1-L82>`_
* `SeaBIOS固定提交：SMBIOS romfile输入与入口安装 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/biostables.c#L262-L639>`_
* `SeaBIOS固定提交：legacy SMBIOS结构构造 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/smbios.c#L1-L590>`_
* `QEMU固定提交：q35 latest与machine默认值 <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/pc_q35.c#L349-L405>`_
* `QEMU固定提交：SMBIOS fw_cfg发布 <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/fw_cfg.c#L62-L115>`_
* `QEMU固定提交：SMBIOS AUTO的2.x优先与3.x回退 <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/smbios/smbios.c#L1096-L1248>`_
* `QEMU固定提交：x86 fw_cfg发布IRQ0 override <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/fw_cfg.c#L119-L152>`_
