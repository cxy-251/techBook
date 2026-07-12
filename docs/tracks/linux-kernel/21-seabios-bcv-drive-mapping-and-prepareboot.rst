第二十一章：SeaBIOS 怎样执行 BCV 并把启动盘映射成 BIOS 0x80？
================================================================

上一章结束时，普通 Option ROM 已经完成部署和解析：

::

   internal AHCI/USB/CD entries ─┐
   legacy ROM BCV entries ───────┤
   PnP BCV/BEV entries ──────────┤→ BootList
   CBFS payload entries ─────────┘

``BootList`` 已经按 priority 排序，但它仍是 SeaBIOS POST 阶段的内部候选表。

此时还没有：

* 执行 legacy 或 PnP BCV；
* 把 ``drive_s`` 放进 BIOS ``IDMap``；
* 把第一块硬盘变成 ``DL=0x80``；
* 建立最终 ``BEV[]`` 启动尝试数组；
* 读取 MBR。

``maininit()`` 接下来执行：

.. code-block:: c

   interactive_bootmenu();
   wait_threads();
   prepareboot();

本章追踪到 ``prepareboot()`` 返回。下一章才会锁定 BIOS shadow RAM 并进入 ``INT 19h``。

启动菜单并不直接启动设备
----------------------

``interactive_bootmenu()`` 首先读取：

::

   etc/show-boot-menu
   etc/boot-menu-wait
   etc/boot-menu-key
   etc/boot-menu-message

默认提示类似：

::

   Press ESC for boot menu.

SeaBIOS 使用前面已经建立的 ``INT 16h`` 键盘服务等待按键。按键来源可能是：

* PS/2 IRQ1；
* USB HID boot keyboard；
* 条件 serial console input。

这些来源都已经汇入 BDA keyboard ring，所以启动菜单不需要区分具体输入控制器。

如果等待时间内没有按下 menu key，函数直接返回，``BootList`` 保持原顺序。

如果用户进入菜单并选择某项，SeaBIOS 做的核心动作只是：

.. code-block:: c

   hlist_del(&boot->node);
   boot->priority = 0;
   hlist_add_head(&boot->node, &BootList);

也就是把选中的 ``bootentry_s`` 移到链表头部。它不会在菜单函数里读取磁盘、执行 PXE 或跳进 Option ROM。

为什么菜单后还要再次 wait_threads
-------------------------------

``maininit()`` 在菜单返回后执行：

.. code-block:: c

   wait_threads();

固定默认路径在 Option ROM 前已经同步等待过设备线程。这里仍然保留第二道 barrier，因为 SeaBIOS 还支持：

* ``threads_during_optionroms()`` 为真的配置；
* Option ROM 执行期间继续推进的硬件线程；
* 菜单显示前仍未结束的条件设备探测。

因此 ``prepareboot()`` 开始时，BootList 不会再被迟到的设备线程修改。

prepareboot 的固定执行顺序
-------------------------

``src/post.c`` 定义：

.. code-block:: c

   void prepareboot(void)
   {
       tpm_prepboot();
       bcv_prepboot();
       cdrom_prepboot();
       pmm_prepboot();
       malloc_prepboot();
       e820_prepboot();
       HaveRunPost = 2;
       BiosChecksum -= checksum((u8*)BUILD_BIOS_ADDR,
                                BUILD_BIOS_SIZE);
   }

这里不是一个单纯的“准备启动”标记。它依次关闭或冻结 POST 阶段仍可变化的状态。

``tpm_prepboot()``
   在离开 BIOS POST 前完成条件 TPM physical-presence 与 measured-boot 状态处理。

``bcv_prepboot()``
   执行 BCV、建立 BIOS drive map，并把 BootList 转成最终启动尝试序列。

``cdrom_prepboot()``
   完成 El Torito/CD emulation 相关准备。

``pmm_prepboot()``
   关闭 POST Memory Manager 对 Option ROM 的分配入口。

``malloc_prepboot()``
   清理临时分配、归还可归还的高端内存，并把最终低端占用写入 E820。

``e820_prepboot()``
   输出并确认最终 E820 map。

最后设置 ``HaveRunPost=2`` 并计算 BIOS checksum。

本章重点是中间的 ``bcv_prepboot()``。

BootList 和 BEV 数组不是同一个结构
--------------------------------

``BootList`` 是 POST 期间的完整候选表，每个条目包含：

::

   type
   priority
   drive pointer 或 vector
   description

最终启动代码 ``do_boot()`` 不直接遍历 BootList。``bcv_prepboot()`` 会把它转换为固定大小的：

.. code-block:: c

   struct bev_s {
       int type;
       u32 vector;
   };

   static struct bev_s BEV[20];

这里的 ``BEV[]`` 名称容易造成误解。数组中不只放 PnP BEV，还可能放：

* floppy 类启动项；
* hard-disk 类启动项；
* CD-ROM；
* CBFS payload；
* 真正的 Option ROM BEV；
* HALT。

它代表 SeaBIOS 最终的启动尝试序列，而不是只代表 PnP header 中的 ``bev`` 字段。

bcv_prepboot 先处理 HALT priority
-------------------------------

函数开始时查找 bootorder 中的特殊路径：

.. code-block:: c

   int haltprio = find_prio("HALT");
   if (haltprio >= 0)
       bootentry_add(IPL_TYPE_HALT, haltprio, 0, "HALT");

QEMU 可以在 ``bootorder`` 中插入 ``HALT``。它的作用是在指定优先级位置停止继续尝试，而不是一种硬件设备。

固定磁盘启动路径通常不依赖它，但它说明 BootList 也能表达启动策略控制项。

BCV 为什么要在最终驱动映射前执行
-------------------------------

``bcv_prepboot()`` 按 BootList 顺序遍历：

.. code-block:: c

   hlist_for_each_entry(pos, &BootList, node) {
       switch (pos->type) {
       case IPL_TYPE_BCV:
           call_bcv(...);
           add_bev(IPL_TYPE_HARDDISK, 0);
           break;
       ...
       }
   }

BCV 的职责是把某个 Option ROM 控制的设备接入传统 BIOS 磁盘体系。典型 storage ROM 可能在 BCV 中：

* 安装或链式接管 ``INT 13h``；
* 构造自己的 drive table；
* 声明可供传统硬盘启动路径访问的设备。

所以 BCV 不能等到 ``INT 19h`` 已经开始读取 ``DL=0x80`` 后才执行。

SeaBIOS 调用：

.. code-block:: c

   call_bcv(pos->vector.seg, pos->vector.offset);

最终进入与 ROM init 类似的 ``__callrom()``，在 16 位 big-real 环境执行 ROM 提供的 BCV，然后返回 SeaBIOS 32 位主流程。

执行 BCV 后，SeaBIOS向最终序列加入一个 generic hard-disk boot entry。它不假设 ROM 的设备一定使用 SeaBIOS 自己的 ``drive_s``；ROM 可以通过它安装的 ``INT 13h`` 路径提供磁盘服务。

内建 AHCI 硬盘不需要 BCV
----------------------

固定 q35 AHCI port 0 磁盘的 BootList 类型是：

::

   IPL_TYPE_HARDDISK

它来自：

.. code-block:: c

   ahci_port_detect()
   → boot_add_hd(&port->drive, ...)

它不依赖 Option ROM，因此 ``bcv_prepboot()`` 对它执行：

.. code-block:: c

   map_hd_drive(pos->drive);
   add_bev(IPL_TYPE_HARDDISK, 0);

这里 ``map_hd_drive()`` 才真正把抽象 ``drive_s`` 接入 BIOS ``INT 13h`` 驱动号空间。

第一块硬盘怎样成为 0x80
---------------------

``map_hd_drive()`` 读取 BDA：

.. code-block:: c

   struct bios_data_area_s *bda =
       MAKE_FLATPTR(SEG_BDA, 0);
   int hdid = bda->hdcount;

启动前 ``hdcount`` 通常为 0。第一块硬盘执行：

.. code-block:: c

   add_drive(IDMap[EXTTYPE_HD],
             &bda->hdcount,
             drive);

结果是：

::

   IDMap[EXTTYPE_HD][0] = AHCI port 0 drive_s
   BDA hdcount          = 1

``INT 13h`` 收到 ``DL=0x80`` 时，SeaBIOS 计算：

.. code-block:: c

   extdrive - EXTSTART_HD
   = 0x80 - 0x80
   = 0

然后取得：

.. code-block:: c

   getDrive(EXTTYPE_HD, 0)
   → IDMap[EXTTYPE_HD][0]
   → AHCI port 0 drive_s

因此“第一块硬盘是 0x80”不是 AHCI 探测时直接写进设备结构的属性。它由 BootList 排序和 ``map_hd_drive()`` 的映射顺序决定。

用户在启动菜单中把另一块硬盘条目移到链表头部时，那块盘可能先进入 ``IDMap[...][0]``，从而成为 ``0x80``。

为什么还要建立逻辑 CHS
--------------------

``map_hd_drive()`` 随后调用：

.. code-block:: c

   setup_translation(drive);

真实现代磁盘按 LBA 访问，传统 ``INT 13h AH=02h`` 仍使用 cylinder/head/sector 参数。

SeaBIOS 因而保存两套信息：

``pchs``
   设备 IDENTIFY 或控制器提供的物理/传统几何提示。

``lchs``
   BIOS 对调用者呈现的逻辑 CHS 几何。

QEMU 可以通过 CMOS 提供 translation mode；否则 SeaBIOS 根据容量和几何选择 none、large 或 LBA translation。

这一步不改变磁盘实际扇区布局。它只决定传统 CHS 请求怎样翻译成 LBA：

.. code-block:: c

   lba = ((cylinder * heads) + head) * sectors_per_track
         + sector - 1

下一章 SeaBIOS 读取 MBR 时使用的正是旧式 ``AH=02h`` CHS 调用，因此这里的逻辑几何必须先完成。

FDPT 为什么写进 EBDA
------------------

对前两块硬盘，``fill_fdpt()`` 在 EBDA 填写 Fixed Disk Parameter Table：

::

   logical cylinders
   logical heads
   sectors per track
   physical geometry hints
   translation signature/checksum

第一块硬盘的 FDPT 地址写入 IVT vector ``0x41``，第二块写入 ``0x46``。

这是 legacy BIOS 软件查询固定磁盘参数时使用的兼容结构。现代 GRUB 通常更偏向 EDD/LBA 扩展，但 SeaBIOS 仍需维持完整传统接口。

为什么多块硬盘只产生一个 generic hard-disk BEV
-------------------------------------------

``add_bev()`` 对 hard disk 和 floppy 做去重：

.. code-block:: c

   if (type == IPL_TYPE_HARDDISK && HaveHDBoot++)
       return;

所以多个 ``IPL_TYPE_HARDDISK`` BootList 条目会依次映射进：

::

   0x80
   0x81
   0x82
   ...

最终 ``BEV[]`` 中只需要一个 generic hard-disk 启动动作：

::

   boot_disk(0x80, ...)

这不是忽略后续硬盘。它表示传统 BIOS 的默认硬盘启动总是从当前映射的第一块硬盘 ``0x80`` 开始。

如果启动失败，固件可以继续尝试下一个启动类型；硬盘内部的分区选择和后续读取由该硬盘上的 boot code 负责。

CD-ROM 条目怎样进入最终序列
-------------------------

对 ``IPL_TYPE_CDROM``：

.. code-block:: c

   map_cd_drive(pos->drive);
   add_bev(IPL_TYPE_CDROM, pos->data);

``map_cd_drive()`` 把 ``drive_s`` 放进 CD IDMap。随后 ``do_boot()`` 可以进入 El Torito 路径，而不是把它伪装成普通 ``0x80`` 磁盘。

代码中的 ``NO BREAK`` 让 CD 条目在完成 map 后继续走通用 ``add_bev()``。

真正的 Option ROM BEV 不在这里执行
--------------------------------

``IPL_TYPE_BEV``、``IPL_TYPE_CBFS`` 和其他直接启动类型在当前遍历中只执行：

.. code-block:: c

   add_bev(pos->type, pos->data);

它们被复制到最终 ``BEV[]``，等待 ``INT 19h`` 后的 ``do_boot()`` 按顺序尝试。

因此：

* BCV 在 ``prepareboot()`` 中执行；
* BEV 在真正启动尝试时执行。

这一区分保持了“先建立设备连接，再选择启动入口”的顺序。

为什么最后还强制加入 floppy 和 hard disk
------------------------------------

遍历结束后执行：

.. code-block:: c

   add_bev(IPL_TYPE_FLOPPY, 0);
   add_bev(IPL_TYPE_HARDDISK, 0);

如果前面已经加入同类型，去重计数器会阻止重复。

如果没有发现对应 BootList 条目，仍保留传统 floppy/hard-disk 尝试入口。真正访问时若 ``IDMap`` 中没有设备，``INT 13h`` 会返回错误，然后 ``INT 18h`` 进入下一个启动项。

这保持了经典 BIOS 的恢复语义，也允许某些通过外部方式挂接 ``INT 13h`` 的环境继续工作。

PMM 为什么在 BCV 之后失效
-----------------------

Option ROM init 和 BCV 执行期间，ROM 可能通过 Post Memory Manager 请求临时或永久内存。

所有 BCV 执行完成后：

.. code-block:: c

   pmm_prepboot();

会清除：

::

   PMMHEADER.signature
   PMMHEADER.entry

这表示 POST 内存分配服务已经关闭。启动代码不能继续把 PMM 当成运行期 BIOS API。

关闭时机必须在 BCV 之后，否则需要内存的 storage ROM 连接代码会失去服务；也必须在跳转 boot sector 前，否则启动软件可能误用只在 POST 有效的分配器。

malloc_prepboot 怎样冻结固件内存布局
--------------------------------

``malloc_prepboot()`` 完成几项关键动作：

#. 清零最后一个已确认 ROM 到 ROM allocation 上界之间的未使用区域；
#. 条件放置 dummy Option ROM header，描述 upper-memory 使用范围；
#. 把低端保留区加入 E820 ``RESERVED``；
#. 清理未使用的 F-segment RAM；
#. 把未使用的 ``ZoneHigh`` 页面归还为 E820 ``RAM``；
#. 重新计算传统可用内存大小。

在此之前，SeaBIOS 仍可能为了设备线程、ROM 和表结构调整分配。此后，交给 bootloader 的内存地图必须稳定。

e820_prepboot 本身为什么只 dump map
--------------------------------

当前实现中：

.. code-block:: c

   void e820_prepboot(void)
   {
       dump_map();
   }

真正的 E820 增删已经在前面的平台初始化、ACPI/SMBIOS 表分配、PMM 和 ``malloc_prepboot()`` 中完成。

这里输出最终列表，意味着后续 ``INT 15h E820`` 查询将看到已经冻结的结果。

HaveRunPost 和 BIOS checksum
--------------------------

``prepareboot()`` 最后设置：

.. code-block:: c

   HaveRunPost = 2;

该状态用于区分：

* 尚未完成 POST；
* POST 正常完成并准备启动；
* reboot 恢复 shadow BIOS 时的异常循环状态。

随后对 ``0xf0000`` 开始的 64 KiB BIOS segment 计算 checksum，并调整 ``BiosChecksum`` 使整体校验符合预期。

这一步发生在 shadow RAM 写保护之前，因为 checksum 字节仍需写入。

第二十一章结束时的机器状态
-----------------------

控制流已经走过：

::

   maininit()
   → interactive_bootmenu()
   → 条件把用户选择的 BootList entry 移到链表头
   → wait_threads()
   → prepareboot()
   → tpm_prepboot()
   → bcv_prepboot()
   → 执行所有 BCV
   → map_floppy_drive() / map_hd_drive() / map_cd_drive()
   → AHCI port 0 drive_s 写入 IDMap[HD][0]
   → BDA hdcount = 1
   → 逻辑 CHS translation
   → EBDA FDPT 与 IVT 0x41
   → 构造最终 BEV[] 启动尝试序列
   → cdrom_prepboot()
   → 关闭 PMM
   → 冻结 malloc 与 E820 布局
   → HaveRunPost = 2
   → 计算 BIOS checksum
   → prepareboot() 返回

此刻：

* 当前执行者：SeaBIOS ``maininit()``；
* 当前主流程 CPU：BSP；
* 模式：32 位保护模式；
* 分页：关闭；
* BCV：已经按 BootList 顺序执行；
* 固定 AHCI port 0 硬盘：已映射为第一块 BIOS 硬盘；
* ``DL=0x80``：将解析到 ``IDMap[EXTTYPE_HD][0]``；
* BDA ``hdcount``：固定单盘路径为 1；
* FDPT/逻辑 CHS：已经建立；
* 最终 ``BEV[]``：已经形成；
* PMM：已经关闭；
* E820：已经冻结；
* BIOS checksum：已经更新；
* MBR sector 0：尚未读取；
* ``0x7c00``：尚未写入启动扇区；
* GRUB：尚未执行；
* Linux：尚未装入内存。

``maininit()`` 下一步执行：

.. code-block:: c

   make_bios_readonly();
   startBoot();

下一章将锁定 q35 shadow BIOS，通过 ``INT 19h`` 选择 generic hard-disk 启动项，再沿 ``INT 13h AH=02h`` 把 LBA 0 的 512 字节读到物理地址 ``0x7c00``。

资料
----

* `SeaBIOS src/post.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/post.c>`_；
* `SeaBIOS src/boot.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/boot.c>`_；
* `SeaBIOS src/block.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/block.c>`_；
* `SeaBIOS src/disk.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/disk.c>`_；
* `SeaBIOS src/pmm.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/pmm.c>`_；
* `SeaBIOS src/malloc.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/malloc.c>`_；
* `SeaBIOS src/e820map.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/e820map.c>`_；
* `BIOS Enhanced Disk Drive Specification <https://www.t13.org>`_。