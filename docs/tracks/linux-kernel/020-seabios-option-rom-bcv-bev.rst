第二十章：SeaBIOS 怎样扫描普通 Option ROM 并把 BCV、BEV 加入启动列表？
=====================================================================

上一章结束时，SeaBIOS 已经完成内建设备驱动探测：

::

   AHCI port 0 disk
   → IDENTIFY DEVICE
   → boot_add_hd()
   → wait_threads()
   → 所有 USB、PS/2、AHCI 和其他设备线程结束

控制流仍在 ``maininit()`` 的 32 位平坦地址环境中，下一条调用是：

.. code-block:: c

   optionrom_setup();

这里处理的不是前面已经执行过的 VGA Option ROM，而是普通非显示设备的 Expansion ROM。常见用途包括：

* 网络控制器的 PXE ROM；
* 自带 BIOS 驱动的存储控制器 ROM；
* 兼容 PnP BIOS 的其他启动 ROM；
* QEMU 或 coreboot 通过固件文件系统提供的 ``genroms/`` payload。

本章结束时，这些 ROM 只会被转换成 ``BootList`` 中的 BCV 或 BEV 条目。BCV 还没有执行，硬盘也还没有取得 BIOS 驱动号 ``0x80``。

为什么 VGA ROM 必须单独提前执行
-----------------------------

VGA ROM 已在第十七章由 ``vgarom_setup()`` 执行。它需要在设备扫描阶段前建立 ``INT 10h`` 和文字控制台，使后续 POST 信息、错误提示和启动菜单可以显示。

普通 Option ROM 不承担这个基础控制台职责，因此放在内建设备驱动探测完成以后：

::

   vgarom_setup()
   → enable_vga_console()
   → device_hardware_setup()
   → wait_threads()
   → optionrom_setup()

这样还带来一个重要结果：SeaBIOS 已经成功接管的 PCI 设备，可以在普通 ROM 扫描时被排除，避免同一控制器同时由 SeaBIOS 内建驱动和设备 ROM 初始化。

optionrom_setup 先记住 VGA ROM 之后的边界
-------------------------------------

``src/optionroms.c`` 进入：

.. code-block:: c

   void optionrom_setup(void)
   {
       u64 sources[(BUILD_BIOS_ADDR - BUILD_ROM_START)
                   / OPTION_ROM_ALIGN];
       memset(sources, 0, sizeof(sources));
       u32 post_vga = rom_get_last();
       ...
   }

Option ROM 的传统驻留区位于低于 1 MiB 的 ``0xc0000`` 到 ``0xf0000`` 之间。SeaBIOS 常量为：

::

   BUILD_ROM_START = 0x000c0000
   BUILD_BIOS_ADDR = 0x000f0000
   OPTION_ROM_ALIGN = 2048

VGA ROM 已经占据这段区域的前部。``rom_get_last()`` 返回当前已确认 ROM 的末尾，``post_vga`` 因而成为本轮普通 ROM 扫描的起点。

后面的第二遍扫描只从 ``post_vga`` 开始，不会再次把 VGA ROM 当成普通 BCV 或 BEV 处理。

sources 数组为什么要记录 ROM 的来源
--------------------------------

``sources`` 按 2 KiB ROM 对齐槽位记录每个已部署 ROM 来自哪里：

* 某个 ``struct pci_device``；
* 某个 ``romfile_s`` 固件文件。

它不参与执行 ROM 代码。它用于稍后计算启动优先级。

QEMU 的 ``bootorder`` 使用设备路径，例如 PCI BDF、USB 端口、ATA port 或 ROM 名称表达启动顺序。ROM 被复制到 ``0xc0000`` 区域以后，单看目标地址已经无法知道它原来属于哪个 PCI function。``sources`` 保留这种关联，使 SeaBIOS 可以调用：

::

   bootprio_find_pci_rom(pci, instance)

或：

::

   bootprio_find_named_rom(file->name, instance)

因此 ROM 的低端内存地址和启动优先级不是一回事。

哪些 PCI 设备不会再扫描 Option ROM
--------------------------------

第一遍循环是：

.. code-block:: c

   foreachpci(pci) {
       if (pci->class == PCI_CLASS_DISPLAY_VGA ||
           pci->class == PCI_CLASS_DISPLAY_OTHER ||
           pci->have_driver)
           continue;
       init_pcirom(pci, 0, sources);
   }

三类设备被跳过。

VGA 和其他显示设备
   它们已经在专门的 VGA 阶段处理，不能再次执行。

``have_driver`` 为真的设备
   SeaBIOS 内建驱动已经认领并启用了该 PCI function。

``have_driver`` 不是抽象的“操作系统驱动已加载”标志。它是 SeaBIOS 在自己的 PCI cache 中维护的一位状态。

以下 helper 成功启用设备资源时会把它设为 1：

.. code-block:: c

   pci_enable_busmaster(pci);
   pci_enable_iobar(pci, bar);
   pci_enable_membar(pci, bar);

例如上一章的 AHCI 路径已经执行：

::

   pci_enable_membar(AHCI, BAR5)
   pci_enable_busmaster(AHCI)
   → pci->have_driver = 1

所以 q35 内置 ICH9 AHCI function 不会再被 ``optionrom_setup()`` 当作“等待 Option ROM 提供驱动”的设备。

这正是 ``wait_threads()`` 必须先完成的原因之一。只有内建设备线程已经结束，``have_driver`` 状态才稳定。

SeaBIOS 优先寻找 QEMU 提供的同名 ROM 文件
------------------------------------

``init_pcirom()`` 根据 PCI vendor ID 和 device ID 构造：

.. code-block:: c

   pciVVVV,DDDD.rom

例如某个设备可能对应：

::

   pci8086,10d3.rom

它先调用 ``romfile_find()``。在 QEMU 路径中，这类 ROM 可以通过 fw_cfg 暴露给 SeaBIOS。

找到文件时，SeaBIOS 使用 ``deploy_romfile()``：

::

   rom_reserve(file->size)
   → 在低端 Option ROM 区预留空间
   → file->copy()
   → 把 ROM 内容复制进去

这样 SeaBIOS 不必直接映射设备的 PCI Expansion ROM BAR。

找不到固件文件时，才根据 ``RunPCIroms`` 决定是否读取设备自身的 ROM BAR：

.. code-block:: c

   if (file)
       rom = deploy_romfile(file);
   else if (RunPCIroms > 1 || (RunPCIroms == 1 && isvga))
       rom = map_pcirom(pci);

第十七章的 ``vgarom_setup()`` 已读取：

::

   etc/pci-optionrom-exec

默认值为 2，表示允许普通 PCI Option ROM 扫描。平台可以通过 romfile 配置关闭或限制执行。

PCI Expansion ROM BAR 怎样被探测
-------------------------------

``map_pcirom()`` 只处理普通 PCI header type。它首先保存 ``PCI_ROM_ADDRESS`` 原值，然后写入掩码形式读取 ROM BAR 大小。

概念上与普通 BAR sizing 类似：

::

   保存原值
   → 向 ROM BAR 写 sizing mask
   → 读回设备实现的地址位
   → 判断 ROM 是否存在以及大小是否合法
   → 恢复或临时启用 ROM decode

SeaBIOS 还拒绝明显危险的地址：

* 未实现或全 1；
* 落在低 16 MiB；
* 落在 RAM 顶部最后 4 MiB 附近；
* 与 sizing 返回值表现得不合理。

通过检查后，它设置 ``PCI_ROM_ADDRESS_ENABLE``，让设备 ROM 暂时出现在 PCI 地址空间中。

一个 ROM BAR 里可能有多个 image
-----------------------------

PCI Expansion ROM 可以串联多个 image。SeaBIOS 从第一个 image 开始检查：

::

   0xaa55 ROM header
   → rom->pcioffset
   → "PCIR" data structure
   → vendor/device
   → code type
   → image length
   → indicator: 是否最后一个 image

固定结构定义中：

.. code-block:: c

   #define OPTION_ROM_SIGNATURE 0xaa55
   #define PCI_ROM_SIGNATURE    0x52494350  /* "PCIR" */
   #define PCIROM_CODETYPE_X86  0

SeaBIOS 要求：

* ``PCIR`` vendor/device 与当前 PCI function 匹配；
* code type 为传统 x86 image。

如果当前 image 不匹配且 ``indicator`` 说明后面还有 image，它按 ``ilen * 512`` 前进到下一幅 image。

找到合适的 x86 image 后，``copy_rom()`` 将其复制到 ``0xc0000`` 以下的传统 ROM 驻留区，并恢复 PCI ROM BAR 原值。后续执行不再依赖设备 ROM BAR 继续保持映射。

ROM header 中的 size 为什么以 512 字节为单位
-----------------------------------------

SeaBIOS 的结构为：

.. code-block:: c

   struct rom_header {
       u16 signature;
       u8  size;
       u8  initVector[4];
       ...
       u16 pcioffset;
       u16 pnpoffset;
   };

``size`` 表示 512-byte blocks，因此 ROM 总长度是：

.. code-block:: c

   len = rom->size * 512;

``is_valid_rom()`` 检查：

#. signature 必须是 ``0xaa55``；
#. size 不能为 0；
#. 整个 image 的 8 位 checksum 应为 0。

当 ``etc/optionroms-checksum`` 开启时，checksum 错误会直接拒绝该 ROM。

ROM 为什么还要复制到 1 MiB 以下
------------------------------

Option ROM 的初始化入口、PnP expansion header 和 BCV/BEV 都使用 16 位 segment:offset 表达。

SeaBIOS 随后会通过 ``farcall16big()`` 执行这些入口。把 ROM 保存在 ``0xc0000`` 到 ``0xeffff`` 的传统区域，满足旧 BIOS 软件对地址和段式调用的预期。

``rom_reserve()`` 以 ``OPTION_ROM_ALIGN`` 对齐分配；``rom_confirm()`` 按 ROM 实际报告的 size 确认占用。这样 ROM 返回后修改自己的 size 字段时，SeaBIOS仍以最后确认值推进下一槽位。

为什么不是所有 ROM 都立即调用 offset 3
-----------------------------------

标准初始化入口位于 ROM header 内的 ``initVector``，即相对 ROM 起点 offset 3。

SeaBIOS 的 ``init_optionrom()`` 执行：

.. code-block:: c

   tpm_option_rom(newrom, size);

   if (isvga || get_pnp_rom(newrom))
       callrom(newrom, bdf);

这意味着当前普通扫描阶段：

* PnP ROM 会立即执行初始化入口；
* VGA ROM 已在前一阶段立即执行；
* 没有 PnP expansion header 的 legacy ROM 暂不执行。

legacy ROM 后面会被注册为 BCV，并在 ``bcv_prepboot()`` 中按启动顺序执行 offset 3。

这样可以先完成所有 ROM 的部署和优先级排序，再决定 legacy storage ROM 的执行顺序。

调用 ROM 前 SeaBIOS 准备哪些寄存器
--------------------------------

``__callrom()`` 构造 16 位调用上下文：

::

   AX = PCI BDF
   BX = 0xffff
   DX = 0xffff
   ES = 0xf000
   DI = PnP installation structure offset
   FLAGS.IF = 1
   CS:IP = ROM segment:entry offset

随后：

.. code-block:: c

   start_preempt();
   farcall16big(&br);
   finish_preempt();

``farcall16big()`` 让 ROM 在 16 位 big-real 环境中执行，同时保持对扩展地址的访问能力。ROM 返回后，SeaBIOS恢复自己的 32 位主流程。

PnP ROM 不应偷偷夺走 INT 19h
--------------------------

某些旧 ROM 会在初始化阶段改写 ``INT 19h``，试图直接控制系统启动。SeaBIOS 对 PnP ROM 做额外防护：

::

   调用前记录 INT 19h 是否已经被捕获
   → 执行 ROM init
   → 检查 INT 19h 是否出现新的修改
   → 对不符合当前规则的普通 PnP PCI ROM恢复 SeaBIOS entry_19_official

检测依据是 IVT 中 ``INT 19h`` vector 是否仍指向 SeaBIOS 官方入口。

这不是禁止 ROM 提供启动能力。正确路径是通过 PnP header 的 BCV 或 BEV 声明启动入口，由 SeaBIOS纳入统一 BootList，而不是在初始化时直接覆盖整个启动流程。

CBFS genroms 与 PCI ROM 的区别
----------------------------

PCI 扫描结束后执行：

.. code-block:: c

   run_file_roms("genroms/", 0, sources);

它遍历固件文件系统中名字以 ``genroms/`` 开头的文件，将其部署到相同的低端 Option ROM 区。

这类 ROM 不一定关联某个 PCI function。它们的启动优先级通过文件名路径计算：

::

   /rom@genroms/<name>

因此 ``sources`` 必须同时支持 PCI device pointer 和 romfile pointer 两种来源。

为什么要在部署后再进行第二遍扫描
------------------------------

所有 PCI 和 CBFS ROM 部署完成后，SeaBIOS 调用：

.. code-block:: c

   rom_reserve(0);

随后从 ``post_vga`` 扫描到 ``rom_get_last()``。

第一遍工作的重点是：

* 找到 ROM 来源；
* 选择匹配的 x86 image；
* 验证并复制到低端内存；
* 条件执行 PnP init；
* 保留来源到优先级的映射。

第二遍工作的重点是：

* 按最终驻留布局重新验证每个 ROM；
* 读取 PnP expansion header；
* 生成 BCV 或 BEV ``BootList`` 条目。

分成两遍后，BootList 构造面对的是稳定的最终 ROM 地址，而不是仍可能移动的临时来源地址。

没有 PnP header 的 ROM怎样处理
-----------------------------

如果 ``get_pnp_rom()`` 返回空，SeaBIOS 把它视为 legacy ROM：

.. code-block:: c

   boot_add_bcv(rom_segment,
                OPTION_ROM_INITVECTOR,
                0,
                priority);

这里把标准 offset 3 当成 BCV。

它此时仍没有执行 ROM。``boot_add_bcv()`` 只是向 BootList 插入：

::

   type = IPL_TYPE_BCV
   vector = ROM segment:0003
   priority = ROM 对应的启动优先级
   description = "Legacy option rom"

执行要等到 ``prepareboot():bcv_prepboot()``。

PnP expansion header 怎样声明 BCV 和 BEV
-------------------------------------

``rom_header.pnpoffset`` 指向 ``struct pnp_data``。当前 SeaBIOS 使用的关键字段是：

::

   "$PnP" signature
   nextoffset
   productname
   bcv
   bev

一个 ROM 可以通过 ``nextoffset`` 串联多个 PnP header，因而可以声明多个启动实例。

第二遍扫描按每个 PnP header 判断：

.. code-block:: c

   if (pnp->bev)
       boot_add_bev(...);
   else if (pnp->bcv)
       boot_add_bcv(...);

``BCV``——Boot Connection Vector
   用于把设备接入传统 BIOS 磁盘启动路径。执行 BCV 后，ROM 通常安装或扩展自己的磁盘服务，使设备能作为硬盘类启动来源。

``BEV``——Boot Execution Vector
   是可以直接尝试启动的入口。PXE ROM 常通过 BEV 进入网络启动环境。

两者不会在 ``optionrom_setup()`` 中直接开始最终启动。它们先成为 BootList 的不同类型条目。

为什么 BEV 与 BCV 不能混为一种入口
-------------------------------

BCV 的职责偏向“建立传统设备连接”：

::

   执行 ROM 连接代码
   → 安装设备服务或扩展 INT 13h
   → 把该类设备加入硬盘启动路径

BEV 的职责偏向“直接尝试从该 ROM 启动”：

::

   选择该启动项
   → 直接 far call 到 BEV
   → ROM 自己完成网络或其他启动协议

所以后续 ``bcv_prepboot()`` 会先执行 BCV；BEV 则保留在最终启动尝试序列中。

BootList 怎样保持确定顺序
-----------------------

``boot_add_bcv()`` 与 ``boot_add_bev()`` 最终都调用 ``bootentry_add()``。

BootList 按以下条件排序：

#. priority 较小者靠前；
#. priority 相同按启动类型；
#. 磁盘类条目还按 drive type 和 controller id 排序。

因此：

* ROM 在 PCI bus 上的扫描先后不直接决定启动先后；
* ROM 初始化线程完成先后不决定启动先后；
* QEMU ``bootorder`` 和默认类别优先级决定主要顺序。

如果 PnP ROM 有多个 header，``instance`` 会参与 ``bootprio_find_pci_rom()`` 或 ``bootprio_find_named_rom()``，使同一 ROM 的多个启动入口也可分别排序。

固定 q35 AHCI 磁盘在本章中发生什么
--------------------------------

固定启动盘已经由 SeaBIOS AHCI 驱动认领：

::

   ICH9 AHCI
   → pci_enable_membar(BAR5)
   → pci_enable_busmaster()
   → have_driver = 1
   → optionrom_setup() 跳过

因此这块盘不会依靠存储 Option ROM 重新出现。它原有的 ``IPL_TYPE_HARDDISK`` 条目继续保留在 BootList 中。

普通 ROM 扫描可能额外加入：

* 条件网络 PXE BEV；
* 条件第三方存储 BCV；
* 条件 CBFS ROM；
* 其他 PnP 启动入口。

具体是否存在取决于 QEMU 命令行、固件 ROM 文件和已配置设备。固定主线只要求 AHCI port 0 硬盘存在，不把条件 ROM 当作必然设备。

第二十章结束时的机器状态
----------------------

控制流已经走过：

::

   maininit()
   → optionrom_setup()
   → 记录 post_vga 边界
   → 遍历非显示、未被 have_driver 认领的 PCI function
   → 优先查找 pciVVVV,DDDD.rom
   → 条件映射 PCI Expansion ROM BAR
   → 选择匹配 vendor/device 的 x86 image
   → 复制到 0xc0000..0xeffff
   → 验证 0xaa55 / size / checksum
   → TPM 条件测量
   → 条件执行 PnP ROM init vector
   → 条件恢复被错误捕获的 INT 19h
   → 部署 genroms/
   → 第二遍扫描最终 ROM 驻留区
   → legacy ROM 转成 BCV
   → PnP header 转成 BCV 或 BEV
   → 插入按优先级排序的 BootList
   → optionrom_setup() 返回

此刻：

* 当前执行者：SeaBIOS ``maininit()``；
* 当前主流程 CPU：BSP；
* 模式：32 位保护模式；
* 分页：关闭；
* VGA ROM：已经在更早阶段执行；
* 普通 PCI/CBFS ROM：已经部署和解析；
* PnP ROM init vector：已经条件执行；
* legacy BCV：尚未执行；
* PnP BCV：尚未执行；
* BEV：已经登记，尚未作为启动入口调用；
* ``BootList``：已包含内建设备条目及条件 BCV/BEV/CBFS 条目；
* BIOS drive ``0x80`` mapping：尚未建立；
* MBR sector 0：尚未读取；
* GRUB：尚未执行；
* Linux：尚未装入内存。

``maininit()`` 的下一条调用是：

.. code-block:: c

   interactive_bootmenu();

启动菜单可以临时把用户选择的 BootList 条目移到链表头部。随后 ``prepareboot():bcv_prepboot()`` 才会执行 BCV、建立 BIOS 驱动映射并生成最终启动尝试序列。

资料
----

* `SeaBIOS src/post.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/post.c>`_；
* `SeaBIOS src/optionroms.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/optionroms.c>`_；
* `SeaBIOS src/std/optionrom.h <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/std/optionrom.h>`_；
* `SeaBIOS src/hw/pcidevice.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/pcidevice.c>`_；
* `SeaBIOS src/boot.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/boot.c>`_；
* `PCI Firmware Specification <https://pcisig.com/specifications>`_；
* `QEMU fw_cfg specification <https://www.qemu.org/docs/master/specs/fw_cfg.html>`_。