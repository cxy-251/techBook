第十五章：SeaBIOS 怎样沿 RSDP 找到 FADT、受限解析 DSDT 并结束平台表阶段？
============================================================================

第十四章已经把 ``find_acpi_rsdp()`` 的结果写入全局 ``RsdpAddr``。BSP仍在SeaBIOS
``MainThread`` 上执行，CPU mode、中断状态与PIC mask均未改变。现在控制流第一次按
RSDP搜索结果分叉：

.. code-block:: c

   if (RsdpAddr) {
       acpi_dsdt_parse();
       virtio_mmio_setup_acpi();
       return;
   }
   if (!loader_err)
       warn_internalerror();
   acpi_setup();

固定q35默认ACPI build的正常结果是 ``RsdpAddr != NULL``。不过本章必须把found与
not-found两个出口都闭合，因为loader逐命令失败不会汇总到 ``loader_err``，RSDP搜索
也可能独立成功或失败。

RSDP本身不是所有ACPI表的容器
-----------------------------

RSDP只保存root table地址。ACPI 1.0使用32位RSDT，ACPI 2.0+还可以提供64位XSDT：

::

   RSDP
   ├── rsdt_physical_address  → RSDT → 32-bit child addresses
   └── xsdt_physical_address  → XSDT → 64-bit child addresses

QEMU把FACS、DSDT、FADT、MADT以及其他条件表放进 ``etc/acpi/tables`` blob；table-loader
已经把root entry和表间pointer改成最终客户机地址。SeaBIOS本章不是重新生成这张图，
而是消费其中一条很窄的路径：

::

   RSDP → XSDT/RSDT → FADT → 32-bit DSDT → limited AML device cache

MADT、MCFG等表即使已经存在，也不是 ``acpi_dsdt_parse()`` 当前执行链上的访问对象。
它们继续留给之后的操作系统按root table发现。

find_acpi_table为什么优先XSDT
----------------------------

``acpi_dsdt_parse()`` 首先调用：

.. code-block:: c

   find_acpi_table(FACP_SIGNATURE)

``find_acpi_table()`` 确认 ``RsdpAddr`` 非空且signature仍为 ``RSD PTR ``，然后分别取得
RSDT与XSDT地址。SeaBIOS当前是32位固件；如果RSDP中的XSDT地址达到或超过4 GiB，代码
直接令 ``xsdt=NULL``，不会尝试临时映射64位物理地址。

若XSDT在4 GiB以下且signature为 ``XSDT``，BSP先遍历它的64位entry。每个child地址
达到4 GiB便跳过；低于4 GiB的地址转为32位pointer，目标signature等于 ``FACP`` 时
立即返回。XSDT不存在、signature不对或没有找到目标时，函数再遍历RSDT的32位entry。

所以“优先XSDT”不是“只要有XSDT便永不看RSDT”。对同一个目标signature，RSDT仍是
逐次查找的fallback。

这次查找信任哪些字段
--------------------

第十四章已经完整验证RSDP的基本及条件扩展checksum。但 ``find_acpi_table()`` 当前只
检查root signature与每个候选child signature，并信任root header中的 ``length`` 来
决定entry迭代终点。它没有在这里重新验证：

* RSDT/XSDT checksum；
* root length是否至少覆盖header且按entry宽度对齐；
* FADT checksum或FADT length；
* 目标表所在内存是否属于某个已登记allocation。

正常QEMU builder与table-loader协议保证这些输入相互匹配；SeaBIOS函数本身却不是通用
的不可信ACPI validator。正文必须把“固定QEMU正常输入成立”与“函数做过哪些检查”分开。

FADT为什么是本章唯一查找的子表
-------------------------------

FADT的signature是 ``FACP``。它把固定ACPI硬件接口与其他关键结构地址汇总在一个表中。
对本章控制流真正重要的是 ``dsdt`` 字段：

.. code-block:: c

   struct fadt_descriptor_rev1 *fadt = find_acpi_table(FACP_SIGNATURE);
   if (!fadt)
       return;
   u8 *dsdt = (void *)(fadt->dsdt);
   if (!dsdt)
       return;

SeaBIOS这个解析器使用FADT中的32位 ``dsdt``，没有在此优先读取扩展 ``X_DSDT``。
QEMU builder为固定PC路径修补32位DSDT字段，主ACPI blob也被要求放进HIGH但保持固件可用
的低4 GiB地址范围，所以正常路径可以沿该字段进入DSDT。

找不到FADT或 ``dsdt==0`` 时， ``acpi_dsdt_parse()`` 只是返回；它不会清掉已经验证的
``RsdpAddr``，也不会宣告整套ACPI表无效。操作系统以后仍可自己遍历root table。

DSDT入口还信任了什么
-------------------

取得非零pointer后，SeaBIOS直接读取：

::

   length = *(u32 *)(dsdt + 4)
   AML start offset = 0x24

然后以整个table ``length`` 作为term list终点调用 ``parse_termlist()``。当前入口没有
先验证DSDT signature、checksum、最小36字节header长度或 ``length`` 对实际allocation
的边界；这些仍由固定QEMU生成链保证。

``CONFIG_ACPI_PARSE`` 在固定SeaBIOS默认配置中开启。若构建时关闭，函数在查FADT之前
直接返回，随后 ``virtio_mmio_setup_acpi()`` 的查找接口也都返回空；已链接ACPI表仍留
给OS，不会因为SeaBIOS不解析AML而消失。

这个AML parser为什么不是解释器
-------------------------------

``src/fw/dsdt_parser.c`` 只识别启动期设备发现所需的小子集。它能够沿Scope与Device
package递归，处理Name、Buffer、有限整数/string、Alias，以及少量extended opcode；
Method、Package、Field、Processor、PowerResource、ThermalZone等大多只按package length
跳过。遇到未知opcode或层级达到16，会记录parse error并停止当前term list，而不是
执行完整AML语义。

每遇到Device，解析器从SeaBIOS临时zone申请一个 ``struct acpi_device`` 并加入全局
``acpi_devices`` hlist。对象只缓存后续固件探测需要的摘要：

::

   name[16]
   pointer to _HID AML
   pointer to _STA AML
   pointer/size of _CRS buffer

这些pointer都指回已经保留的DSDT blob，不复制完整AML对象。 ``_STA`` 若是简单Name
整数可判定present；若是Method则返回unknown，因为解析器不会执行方法。

_CRS资源解析到底支持哪些内容
-----------------------------

当Device内的 ``_CRS`` 是Buffer时，解析器缓存resource byte stream。公开查找函数只
提取第一项匹配资源，并支持有限descriptor：

* small IRQ、I/O与fixed I/O；
* large 32-bit fixed memory；
* WORD、DWORD、QWORD address space；
* large IRQ；
* end tag。

它不构建操作系统意义上的完整resource tree，也不解析DSDT里的 ``_PRT`` PCI routing
package。本章因此不能说SeaBIOS已经通过AML重做q35 PCI中断路由；第九章生效的ICH9
寄存器仍保持原状， ``_PRT`` 留给之后的ACPI interpreter。

virtio_mmio_setup_acpi消费了什么
--------------------------------

受限解析返回后，BSP立即调用 ``virtio_mmio_setup_acpi()``。该函数遍历缓存中原始AML
``_HID`` 为字符串 ``LNRO0005`` 的Device；每个候选必须同时能从 ``_CRS`` 取到memory
range与IRQ，否则跳过。它没有在这个循环里调用 ``_STA`` present判断。

对合格候选， ``virtio_mmio_setup_one()`` 还有硬边界：

#. MMIO base必须低于4 GiB；
#. offset 0的magic必须为 ``0x74726976``；
#. version只能是legacy 1或modern 2；
#. 读取device ID后，当前代码只为virtio-blk与virtio-scsi启动初始化线程，其他ID只记录。

固定q35主线的磁盘是ICH9 AHCI SATA port 0，不是由这一函数创建的virtio-mmio block。
普通q35 PCI设备也不会因为存在ACPI表就匹配 ``LNRO0005``。因此默认没有此类附加设备
时，遍历为空并立即返回；只有显式加入ACPI描述的virtio-mmio设备，才进入上述条件
初始化。

found分支怎样结束
-----------------

无论DSDT解析是否找到FADT、是否遇到受限opcode、是否发现virtio-mmio，调用链最后都
执行 ``return``，直接离开 ``qemu_platform_setup()``。 ``loader_err`` 即使是 ``-1``
也不会在RSDP found分支触发告警；源码选择信任已经通过独立FSEG验证的RSDP。

此时ACPI表的最终HIGH/FSEG allocation继续存活， ``RsdpAddr`` 继续指向FSEG。解析缓存
只服务SeaBIOS内部条件探测，OS以后仍从RSDP重新发现完整表图，两者不是同一套生命周期。

not-found分支为什么已经没有内建表回退
------------------------------------

若 ``RsdpAddr==NULL``，SeaBIOS先看 ``loader_err``：

* loader返回0却没有RSDP，说明“命令流可遍历”没有产生应有入口，调用
  ``warn_internalerror()``；
* loader返回 ``-1`` 时，不再追加这一条内部错误告警。

随后两种情况都落到 ``acpi_setup()``。当前固定SeaBIOS提交中的实现只有：

.. code-block:: c

   if (!CONFIG_ACPI)
       return;
   dprintf(1, "ACPI tables for qemu 1.6 and older are not supported any more.\n");

它不申请表内存、不构造RSDP/RSDT/FADT/DSDT，也不修复前面局部链接结果。因此把这条
路径称为“SeaBIOS内建兼容ACPI生成”是错误的；它只是报告旧QEMU表路径已不再支持并
返回。若 ``CONFIG_ACPI`` 关闭，连该消息也跳过。

平台表阶段怎样交给下一段硬件初始化
----------------------------------

found分支的显式 ``return`` 与not-found分支中 ``acpi_setup()`` 返回，最终都使
``qemu_platform_setup()`` 结束。控制流回到：

.. code-block:: c

   platform_hardware_setup()
   {
       qemu_platform_setup();
       coreboot_platform_setup();
       timer_setup();
       clock_setup();
       tpm_setup();
   }

固定QEMU q35不会把 ``coreboot_platform_setup()`` 变成另一条平台主线；第十六章将从
这一返回边界继续，区分SeaBIOS内部deadline timer、传统BIOS clock与条件TPM初始化。

本章结束状态
------------

* current executor：BSP上的SeaBIOS ``MainThread``；
* CPU/mode：32位保护模式，分页关闭，A20开启，IF=0，CMOS NMI屏蔽；
* AP状态：缺省无AP；显式多CPU时在场AP仍停在IF=0的HLT循环；
* normal q35 ``RsdpAddr``：指向FSEG中通过signature、范围与checksum验证的RSDP；
* ACPI table allocations：linked blob保持在HIGH，RSDP保持在FSEG；
* SeaBIOS当前table lookup：只按需要查FADT，XSDT优先、RSDT回退；
* DSDT pointer：取自FADT的32位 ``dsdt`` 字段；
* DSDT parse cache：保存已识别Device的name、 ``_HID``、 ``_STA`` 与 ``_CRS`` 摘要；
* MADT/MCFG/ ``_PRT``：未被本章SeaBIOS控制流解释，继续留给后续OS；
* virtio-mmio：仅条件匹配 ``LNRO0005`` 与资源；固定AHCI磁盘不走此路径；
* no-RSDP fallback：不生成内建ACPI表，只条件打印旧QEMU不支持消息；
* ``qemu_platform_setup()``：已经返回；
* next entry： ``coreboot_platform_setup()``，随后 ``timer_setup()``。

关键边界
--------

#. RSDP只指向root，ACPI子表不内嵌在RSDP中。
#. ``find_acpi_table()`` 对同一目标先查低4 GiB XSDT，再回退RSDT。
#. 当前查找只核对signature并信任length，不重新验证root或FADT checksum。
#. ``acpi_dsdt_parse()`` 当前只查FADT，不遍历MADT、MCFG等整张ACPI图。
#. SeaBIOS使用FADT的32位 ``dsdt``，本入口不优先使用 ``X_DSDT``。
#. DSDT signature、checksum与allocation边界不由当前解析入口重新验证。
#. AML parser只建立有限设备摘要，不能执行通用Method或替代OS ACPI interpreter。
#. ``_CRS`` 的有限资源提取不等于解析 ``_PRT`` 或重新配置PCI路由。
#. ``virtio_mmio_setup_acpi()`` 只消费 ``LNRO0005``；q35 AHCI磁盘不属于此路径。
#. found分支不受 ``loader_err`` 否决，并在virtio-mmio探测后直接返回。
#. 当前 ``acpi_setup()`` 已退化为提示，不是有效的内建表生成回退。
#. ACPI表对象与SeaBIOS解析缓存保留给不同消费者，不能合并生命周期。

下一入口
--------

下一章从：

::

   qemu_platform_setup returns
   → coreboot_platform_setup()       # fixed QEMU path does not take over
   → timer_setup()
   → clock_setup()
   → tpm_setup()

开始，先确定SeaBIOS内部deadline timer是否已由KVM pvclock或ICH9 PM timer建立，再处理
传统PIT/RTC BIOS时钟与条件TPM对象。

资料
----

* `SeaBIOS固定提交：QEMU平台RSDP分支与返回边界 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/paravirt.c#L301-L324>`_
* `SeaBIOS固定提交：XSDT优先、RSDT回退的表查找 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/biostables.c#L123-L177>`_
* `SeaBIOS固定提交：受限DSDT解析与设备缓存 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/dsdt_parser.c#L1-L677>`_
* `SeaBIOS固定提交：ACPI描述的virtio-mmio探测 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/virtio-mmio.c#L1-L90>`_
* `SeaBIOS固定提交：旧QEMU ACPI fallback现状 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/acpi.c#L1-L22>`_
* `QEMU固定提交：FACS、DSDT、FADT、MADT构造顺序 <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/acpi-build.c#L2025-L2105>`_
* `QEMU固定提交：FADT指针重定位 <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/acpi/aml-build.c#L2460-L2560>`_
