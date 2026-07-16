第二十章：SeaBIOS怎样扫描普通Option ROM并登记BCV、BEV？
=========================================================

第019章结束时，BSP上的SeaBIOS ``MainThread`` 已从同步设备初始化路径的第一次
``wait_threads()`` 返回。它仍在32位保护模式、分页关闭且自身IF=0的环境；固定PS/2和
AHCI worker都已退出。 ``BootList`` 只有priority 101的ICH9 AHCI port 0硬盘，
``IDMap`` 尚空。 ``maininit()`` 现在调用：

.. code-block:: c

   optionrom_setup();

本章处理的是VGA阶段之后的普通Option ROM。与第017—019章采用的QEMU默认设备基线一致，
当前没有 ``-nodefaults``、 ``-net none`` 或自定义NIC override：q35默认e1000e及其组合
ROM因此是确定命中，不再只写成“可能存在PXE”。显式增加其他PCI设备或standalone ROM仍
属于条件分支。

post_vga把本轮扫描与VGA驻留区分开
--------------------------------

``CONFIG_OPTIONROMS`` 开启时，MainThread先在当前32位栈上建立 ``sources[]`` 并清零。
数组以2 KiB ``OPTION_ROM_ALIGN`` 为槽，覆盖 ``0xc0000`` 到 ``0xeffff`` 的传统ROM
驻留范围；每个非零元素稍后保存该低端ROM来自哪个 ``pci_device`` 或 ``romfile_s``。

接着：

.. code-block:: c

   u32 post_vga = rom_get_last();

第017章已把standard VGA image部署在 ``BUILD_ROM_START=0xc0000`` 一侧，并由
``rom_confirm`` 推进 ``RomEnd``。 ``post_vga`` 记住VGA之后的第一个空闲边界；本章第二遍
只从这里扫描，既不再次初始化VGA，也不把它登记为普通BCV/BEV。

第一遍先按PCI身份排除两类设备
----------------------------

MainThread遍历第007章建立的 ``PCIDevices``：

.. code-block:: c

   if (pci->class == PCI_CLASS_DISPLAY_VGA ||
       pci->class == PCI_CLASS_DISPLAY_OTHER ||
       pci->have_driver)
       continue;

固定standard VGA按display class跳过。固定ICH9 AHCI则按第019章在
``pci_enable_membar(BAR5)`` 已同步置位的 ``have_driver=1`` 跳过；即使某个port后来探测
失败，这个C侧标志也不会由 ``wait_threads`` 才生成或自动回滚。

``have_driver`` 只属于SeaBIOS的 ``pci_device`` cache，不是PCI config bit，更不是“操作
系统驱动已加载”。Option ROM在16位环境里修改真实PCI寄存器，也不会直接改这一个C字段。

固定e1000e为什么进入扫描
------------------------

QEMU PC通用默认网络开关在没有 ``-net/-netdev/-nic`` override时创建一组 ``nic,user``；
q35 machine class把默认NIC类型定为 ``e1000e``。其PCI class是Ethernet，SeaBIOS没有内建
e1000e网络驱动，所以对应 ``pci_device.have_driver`` 仍为0。

固定QEMU e1000e class还指定：

.. code-block:: c

   c->romfile = "efi-e1000e.rom";

名字容易让人误以为文件只有UEFI image。固定QEMU blob实际是multi-image PCI Expansion
ROM：

::

   first image
     ROM signature = 0xaa55
     vendor/device = 8086:10d3
     PCIR code type = 0 (x86)
     $PnP header    = present
     BCV            = 0
     BEV            = 0x0385

   following image
     PCIR code type = 3 (EFI)
     last-image bit = 1

因此legacy SeaBIOS能选择首幅x86/iPXE image；它不会试图执行后面的EFI image。该blob在
固定QEMU commit中的git object与SHA-256均记录在本批审计报告，避免只凭文件名推断格式。

init_pcirom先查SeaBIOS romfile，再退到PCI ROM BAR
-----------------------------------------------

对e1000e， ``init_pcirom()`` 用vendor/device拼出：

::

   pci8086,10d3.rom

这是SeaBIOS在自己的romfile目录里查找的替代文件名，并不是QEMU设备class的
``efi-e1000e.rom`` 名称。固定基线没有同名fw_cfg替代文件，于是 ``file=NULL``。

第017章已读取：

::

   RunPCIroms = romfile_loadint("etc/pci-optionrom-exec", 2)

默认值2允许普通PCI ROM BAR，所以控制流进入 ``map_pcirom(pci)``。如果显式把该设置改为
0或1，非VGA e1000e ROM不会从BAR映射，本章固定iPXE BEV也不会出现。

ROM BAR只在复制期间临时打开
--------------------------

``map_pcirom`` 先要求normal PCI header，保存 ``PCI_ROM_ADDRESS`` 原值，再写sizing值并
读回实现的mask。它拒绝未实现/全1、与原值相同或落入源码禁止地址范围的结果；失败都会
恢复原值并返回NULL。

固定e1000e ROM BAR有效。SeaBIOS把原地址与 ``PCI_ROM_ADDRESS_ENABLE`` 一起写回，使
QEMU ROM memory region暂时可读，然后从第一幅image开始检查：

::

   0xaa55 header
   → PCIR signature
   → vendor/device match
   → code type 0

若一幅image不匹配且PCIR last-image bit未置位，指针按 ``ilen * 512`` 前进；固定首幅
已经匹配。 ``copy_rom()`` 按首幅ROM header的 ``size * 512`` 在低端ROM区预留空间并
复制它，随后立即把PCI ROM BAR恢复到原值。后续init、PnP解析和BEV调用都使用低端副本，
不要求BAR继续decode。

checksum一直计算，EnforceChecksum才决定是否拒绝
----------------------------------------------

``init_optionrom()`` 对低端副本调用 ``is_valid_rom()``。它总是检查signature和非零
size，也总是对 ``size * 512`` bytes计算8-bit checksum。checksum非零一定打印诊断；
只有第017章默认读取的 ``EnforceChecksum=1`` 才把它变成拒绝条件。

固定首幅image通过校验。MainThread再调用 ``rom_reserve`` 确认驻留空间，并执行
``tpm_option_rom``。第016章已证明固定机器没有TPM2/TCPA table、 ``TPM_working=0``，
所以measurement helper不创建event log或PCR变化。

PnP header让init vector现在就执行
--------------------------------

固定首幅image的 ``rom_header.pnpoffset`` 指向有效 ``$PnP`` header，因此
``init_optionrom`` 立即调用标准offset 3。 ``__callrom()`` 构造16位寄存器帧：

::

   AX = e1000e PCI BDF
   BX = 0xffff
   DX = 0xffff
   ES = 0xf000
   DI = PnP installation structure offset
   FLAGS.IF = 1
   CS:IP = ROM segment:0003

``start_preempt → farcall16big`` 把执行者交给低端iPXE x86 image。该二进制的内部实现不在
固定SeaBIOS源码里，本章不猜测它留下的私有NIC数据结构；当前成功主线只使用可观察边界：
init调用返回， ``finish_preempt()`` 恢复SeaBIOS MainThread，且本章最后从PnP header
取得固定BEV。

调用前后， ``init_pcirom`` 比较IVT 19h。只有同时满足“本次调用新捕获INT 19h、ROM来自
PCI ROM BAR而非SeaBIOS替代file、非VGA、并有PnP header”时，它才把vector恢复为
``entry_19_official``。这条保护不等于禁止所有ROM改IVT，也不删除ROM声明的BEV。

无PnP legacy ROM此刻反而不会执行
------------------------------

``init_optionrom`` 的调用条件是：

.. code-block:: c

   if (isvga || get_pnp_rom(newrom))
       callrom(newrom, bdf);

因此显式附加的无PnP legacy ROM在第一遍只会部署，不会在这里调用offset 3。稍后第二遍
会把offset 3登记成BCV，到第021章的 ``bcv_prepboot`` 才执行。PnP init、BCV和BEV是三个
不同时间边界：

::

   PnP init vector → deployment phase now
   BCV             → prepareboot phase
   BEV             → INT 19h boot-attempt phase

固定e1000e有PnP init和BEV，没有BCV。

其他PCI function与genroms分支
-----------------------------

第一遍继续遍历其余未认领、非display PCI functions。没有ROM BAR或匹配x86 image的设备
在 ``init_pcirom`` 内恢复BAR并返回，不留下source或BootList条目。

随后：

.. code-block:: c

   run_file_roms("genroms/", 0, sources);

它处理QEMU ``-option-rom``、direct-kernel辅助ROM或其他显式standalone image经fw_cfg
形成的 ``genroms/`` 文件。固定主线没有这些输入，目录遍历为空。这里不能把PCI
e1000e ROM BAR副本再算作一个 ``genroms`` 文件。

所有来源部署完后， ``rom_reserve(0)`` 结束当前reservation。低端地址已稳定，
``sources[]`` 仍只在本次 ``optionrom_setup`` 栈帧内保存“驻留槽→来源”的对应关系。

第二遍只登记启动能力
--------------------

MainThread从 ``post_vga`` 走到新的 ``rom_get_last()``。每个2 KiB槽先再次做
``is_valid_rom``；无效槽前进2 KiB，有效ROM按其 ``size * 512`` 向上对齐后跨过整个
image。固定e1000e低端副本有效且有PnP header，于是进入header链。

首个header的 ``bev=0x0385`` 非零，优先于 ``bcv`` 分支：

.. code-block:: c

   boot_add_bev(rom_segment, 0x0385, productname, priority);

``getRomPriority`` 通过 ``sources[]`` 找回e1000e ``pci_device``，调用
``bootprio_find_pci_rom(pci, instance=0)``。固定没有NIC bootindex，查找返回-1；
``boot_add_bev`` 使用QEMU CMOS old-style boot order留下的
``DefaultBEVPrio=9999``。PnP product name指向 ``iPXE``，所以新增条目是：

::

   type        = IPL_TYPE_BEV
   vector      = ROM segment:0385
   priority    = 9999
   description = iPXE

``nextoffset=0`` 结束该ROM的PnP链。固定AHCI hard disk原有priority 101，因此排序后的
BootList仍以磁盘开头，iPXE BEV在后；PCI扫描先后没有覆盖这个priority比较。

条件BCV怎样被登记
----------------

第二遍对其他可能的ROM遵守两条互斥规则：

* 没有PnP header：把standard offset 3登记为 ``IPL_TYPE_BCV``，描述为
  ``Legacy option rom``；
* 有PnP header：每个header先看 ``bev``，只有它为0才看 ``bcv``；两者都为0就停止该链。

``boot_add_bcv`` 和 ``boot_add_bev`` 都只分配 ``bootentry_s`` 并按priority插入
BootList。它们不在本章执行BCV/BEV，不创建 ``drive_s``，也不改BDA ``hdcount``。固定
默认ROM集合没有BCV，只有e1000e的iPXE BEV。

optionrom_setup返回时仍是POST主控制流
-----------------------------------

第二遍结束后 ``sources[]`` 随函数栈退出；低端ROM副本和BootList条目继续存在。
MainThread没有从 ``optionrom_setup`` 创建新的SeaBIOS协作worker；第019章的
``have_threads=false`` 仍成立。控制流回到 ``maininit()``，下一条调用是
``interactive_bootmenu()``。

本章结束状态
------------

* current executor：BSP上的SeaBIOS ``MainThread``，已从 ``optionrom_setup()`` 返回；
* CPU/mode：32位保护模式，分页关闭，A20开启，MainThread IF=0；
* threads：固定没有协作worker， ``have_threads=false``；
* VGA ROM：保持第017章低端驻留状态，本章按class和 ``post_vga`` 边界跳过；
* fixed AHCI： ``have_driver=1``，本章未映射或执行其PCI ROM；
* fixed default NIC：QEMU e1000e存在，SeaBIOS无内建driver；首幅x86/iPXE image已从ROM
  BAR复制到低端ROM区并调用PnP init，PCI ROM BAR已恢复；
* TPM：仍不存在；Option ROM measurement无状态变化；
* fixed ordinary ROM capabilities：e1000e PnP header提供BEV 0x0385、BCV 0；
  ``genroms/`` 为空，没有legacy/PnP BCV；
* ``BootList``：依次包含AHCI hard disk(priority 101)与iPXE BEV(priority 9999)；
* ``IDMap``、BDA ``hdcount``、FDPT与最终 ``BEV[]``：尚未建立， ``hdcount=0``；
* MBR、GRUB、Linux：均未读取或执行；
* next entry： ``interactive_bootmenu()``。

关键边界
--------

#. ``post_vga`` 是第二遍普通ROM扫描起点，不是整个ROM区起点。
#. fixed AHCI由 ``have_driver`` 跳过；该标志早在BAR5 helper成功时置位。
#. 固定默认e1000e的 ``efi-e1000e.rom`` 是包含x86首幅image的组合ROM，文件名不能替代
   PCIR/header检查。
#. SeaBIOS先查 ``pciVVVV,DDDD.rom`` 替代file；固定e1000e实际走PCI ROM BAR。
#. checksum总会计算； ``EnforceChecksum`` 只控制坏checksum是否拒绝。
#. PnP ROM的offset 3 init现在执行；无PnP legacy offset 3作为BCV留到第021章。
#. INT 19h恢复只覆盖来自PCI BAR的非VGA PnP ROM在本次新捕获的窄条件。
#. ``boot_add_bev`` 只登记vector；固定iPXE尚未执行，固定硬盘也尚未映射成0x80。
#. fixed BootList没有BCV；“SeaBIOS支持BCV”不能改写成“本次已经执行BCV”。

下一入口
--------

``maininit()`` 的下一条调用是：

.. code-block:: c

   interactive_bootmenu();

第021章固定沿默认无按键输入路径等待2500 ms后保持BootList顺序，再经过第二次
``wait_threads()`` 进入 ``prepareboot()``。只有在那里才处理条件BCV类型、把固定AHCI
``drive_s`` 写入 ``IDMap[EXTTYPE_HD][0]``，并另行构造最终启动尝试 ``BEV[]``。

资料
----

* `SeaBIOS：普通Option ROM两遍扫描 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/optionroms.c#L359-L419>`_；
* `SeaBIOS：ROM校验、PnP/PCI header与调用帧 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/optionroms.c#L29-L145>`_；
* `SeaBIOS：romfile部署与source记录 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/optionroms.c#L147-L203>`_；
* `SeaBIOS：PCI ROM BAR选择、复制与恢复 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/optionroms.c#L206-L310>`_；
* `SeaBIOS：init_pcirom与INT 19h窄恢复条件 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/optionroms.c#L312-L356>`_；
* `SeaBIOS：VGA阶段加载RunPCIroms和checksum策略 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/optionroms.c#L450-L489>`_；
* `SeaBIOS：Option ROM与PnP结构字段 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/std/optionrom.h#L1-L57>`_；
* `SeaBIOS：BootList排序、BCV与BEV登记 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/boot.c#L499-L584>`_；
* `QEMU：q35默认NIC为e1000e <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/pc_q35.c#L355-L370>`_；
* `QEMU：q35构建默认启用e1000e支持 <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/Kconfig#L101-L119>`_；
* `QEMU：无network override时创建默认nic,user <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/system/vl.c#L1343-L1457>`_；
* `QEMU：e1000e PCI身份与默认ROM文件 <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/net/e1000e.c#L676-L708>`_；
* `QEMU固定e1000e组合ROM blob <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/pc-bios/efi-e1000e.rom>`_；
* `QEMU：PCI设备默认ROM装载到ROM BAR <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/pci/pci.c#L2538-L2645>`_；
* `PCI Firmware Specification <https://pcisig.com/specifications>`_。
