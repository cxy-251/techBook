第十九章：SeaBIOS 怎样发现 q35 的 AHCI 磁盘并把它加入启动列表？
================================================================

上一章停在：

.. code-block:: c

   device_hardware_setup()
   {
       usb_setup();
       ps2port_setup();
       block_setup();
       ...
   }

USB 和 PS/2 线程已经启动，主线程现在进入 ``block_setup()``。

从这一章开始，为了让后续读取 MBR、进入 GRUB i386-pc 的路径可复现，固定存储主线为：

::

   QEMU q35
   → ICH9 内置 AHCI controller
   → SATA port 0
   → 一块包含后续 GRUB 启动链的硬盘

虚拟机仍然可以额外添加 USB、virtio-blk、NVMe 或 SCSI 设备，但它们不进入本书当前主线。

block_setup 不是“初始化一个磁盘驱动”
--------------------------------

SeaBIOS 依次调用：

.. code-block:: c

   floppy_setup();
   ata_setup();
   ahci_setup();
   sdcard_setup();
   ramdisk_setup();
   virtio_blk_setup();
   virtio_scsi_setup();
   lsi_scsi_setup();
   esp_scsi_setup();
   megasas_setup();
   pvscsi_setup();
   mpt_scsi_setup();
   nvme_setup();

这是一组“各自扫描是否存在匹配硬件”的入口，不是互斥选择。

同一台机器可以同时发现：

* SATA 硬盘；
* ATAPI 光驱；
* USB 存储；
* virtio-blk；
* NVMe；
* Option ROM 后续注册的网络启动入口。

每个驱动发现设备后，把它作为启动候选加入统一 ``BootList``。真正的启动优先级由前面读取的 bootorder、设备路径和默认类别顺序决定。

为什么固定 q35 主线跳过 floppy 和 legacy ATA
----------------------------------------

QEMU q35 machine class 设置：

.. code-block:: c

   m->no_floppy = 1;

所以默认机器没有传统 floppy controller/drive。

q35 的内置 SATA controller 由 QEMU 创建为：

::

   device 31, function 2
   → typical BDF 00:1f.2

QEMU 常量明确写着：

.. code-block:: c

   ICH9_SATA1_DEV  = 31
   ICH9_SATA1_FUNC = 2

它是 AHCI SATA function，不是传统 PIIX IDE controller。``ata_setup()`` 仍会扫描可能存在的 legacy IDE controller，但当前固定启动盘由后面的 ``ahci_setup()`` 发现。

QEMU 怎样在 SeaBIOS 运行前创建这块 AHCI 设备
----------------------------------------

``pc_q35_init()`` 在 SATA 启用时创建：

.. code-block:: c

   pci_create_simple_multifunction(
       pcibus,
       PCI_DEVFN(ICH9_SATA1_DEV, ICH9_SATA1_FUNC),
       "ich9-ahci");

QEMU ICH9 AHCI 实现提供六个 SATA ports：

::

   MAX_SATA_PORTS = 6

随后 QEMU 取得用户配置的 block backends，并把 drive devices 挂到 AHCI ports。

这里再次体现“模拟器和固件的职责分界”：

* QEMU 在客户机启动前创建 AHCI PCI function、MMIO registers、ports 和后端磁盘；
* SeaBIOS 通过普通 PCI/AHCI 协议发现它们；
* SeaBIOS 不直接调用 QEMU host API 读取磁盘文件。

ahci_setup 用 class code 和 programming interface 匹配
-----------------------------------------------

``ahci_scan()`` 遍历第七章建立的 ``PCIDevices``，只接受：

::

   class   = PCI mass storage / SATA
   prog_if = 1

``prog_if=1`` 表示 AHCI 1.x programming interface。

因此“设备名称里带 AHCI”不是驱动绑定依据。SeaBIOS 根据标准 PCI class/prog-if 判断 controller 类型。

匹配后调用：

.. code-block:: c

   ahci_controller_setup(pci);

BAR5 是 AHCI HBA register window
-------------------------------

SeaBIOS 读取并启用：

.. code-block:: c

   pci_enable_membar(pci, PCI_BASE_ADDRESS_5);

AHCI controller 的 ABAR 通常位于 PCI BAR5。这个 MMIO window 包含两层 registers。

HBA global registers：

::

   CAP      capabilities
   GHC      global host control
   PI       ports implemented

每个 port 的 register block：

::

   PxCLB    command-list base
   PxFB     received-FIS base
   PxIS     interrupt status
   PxIE     interrupt enable
   PxCMD    command and status
   PxTFD    task-file data
   PxSIG    device signature
   PxSSTS   SATA status
   PxSCTL   SATA control
   PxSERR   SATA error
   PxCI     command issue

第八章只是给 BAR 分配地址，第九章只是打开 memory decode。当前章节才第一次按 AHCI register layout 真正驱动这个 MMIO region。

为什么还要打开 PCI bus master
--------------------------

AHCI 不通过 CPU 对 data port 逐字节搬运扇区。

controller 会 DMA 访问：

* command list；
* command table；
* host-to-device FIS；
* received FIS；
* PRDT 指向的数据缓冲区。

因此 SeaBIOS 调用：

.. code-block:: c

   pci_enable_busmaster(pci);

如果 PCI Command.BusMaster=0，CPU 虽然能读写 ABAR，controller 仍不能从 RAM 获取 command 或把磁盘数据写入 buffer。

HBA reset 与 AHCI Enable
----------------------

SeaBIOS 先向 global host-control register 设置 HBA reset：

::

   GHC.HR = 1

硬件完成内部 reset 后自动清零。SeaBIOS 使用 500 ms deadline 轮询，期间不断 ``yield()``，让 USB、PS/2 和其他 disk threads 继续运行。

reset 完成后设置：

::

   GHC.AE = 1

也就是 AHCI Enable。随后读取：

``CAP``
   controller capability，例如是否支持 64 位地址。

``PI``
   Ports Implemented bitmap。bit N 为 1 才表示 port N 由 controller 实现。

QEMU controller 有六个 ports，不表示六个 ports 都连接了 drive。``PI`` 决定哪些 port registers 存在，``PxSSTS`` 再告诉固件端口上是否真的建立 SATA link。

为什么每个 port 单独创建线程
-------------------------

``ahci_controller_setup()`` 遍历 ``PI`` 中的 implemented bits，对每个 port：

.. code-block:: c

   port = ahci_port_alloc(ctrl, pnr);
   run_thread(ahci_port_detect, port);

不同 SATA port 的 link training、device-ready 和 IDENTIFY 等待互不依赖。如果 port 0 的磁盘正在 spin-up，port 1 的 ATAPI 光驱可以同时推进。

这也解释了为什么本章最终必须经过 ``wait_threads()`` 才能确定设备发现完成。

command list、received FIS 和 command table 为什么有三块内存
------------------------------------------------------

SeaBIOS 为每个 port 分配：

::

   command list   1024 bytes, 1024-byte aligned
   received FIS    256 bytes, 256-byte aligned
   command table   256 bytes, 256-byte aligned

它们承担不同职责。

``command list``
   最多保存多个 command header。SeaBIOS 当前主要使用 slot 0。

``command table``
   保存该 command 的 host-to-device FIS、ATAPI command 和 PRDT entries。

``received FIS``
   controller 把 device-to-host register FIS、PIO setup FIS 等返回状态 DMA 到这里。

地址分别写入：

::

   PxCLB / PxCLBU
   PxFB  / PxFBU

当前 SeaBIOS 只使用 4 GiB 以下 DMA addresses，高 32 位写零。即使 controller 声明支持 64 位地址，固件也没有必要把这些早期结构放到高于 4 GiB 的位置。

开始探测前为什么先停 command engine
--------------------------------

``ahci_port_reset()`` 清除：

::

   PxCMD.FRE  FIS receive enable
   PxCMD.ST   command-list running

然后等待硬件状态：

::

   PxCMD.FR = 0
   PxCMD.CR = 0

这保证 controller 已停止读取旧 command list 或写旧 received-FIS area。SeaBIOS 随后关闭 port interrupt enable，并清除遗留 ``PxIS``。

如果不先停 engine 就替换 ``PxCLB``、``PxFB`` 和缓冲区，controller 可能 DMA 到已经释放或重新分配的内存。

PxSSTS.DET=3 才表示 SATA link 真正建立
----------------------------------

SeaBIOS 打开：

::

   PxCMD.FRE  = 1
   PxCMD.SUD  = 1
   PxCMD.POD  = 1
   PxCMD.ICC  = active

随后等待 ``PxSSTS`` 的 Device Detection 字段：

::

   DET = 3

它表示 device present 且 PHY communication established。

几种常见状态不能混淆：

``DET=0``
   未检测到 device。

``DET=1``
   检测到 device，但 PHY 尚未建立通信。

``DET=3``
   device present，link established。

SeaBIOS 当前 link timeout 只有约 10 ms，适合 QEMU 虚拟设备的即时 link；真实物理固件通常需要更复杂的 hot-plug、COMRESET 和 spin-up 策略。

link up 后为什么还要等 BSY 和 DRQ 清零
-----------------------------------

SATA PHY 已连通，只证明主机和设备能交换 primitives，不代表 ATA command interface 已经空闲。

SeaBIOS 继续读取 ``PxTFD``，等待：

::

   BSY = 0
   DRQ = 0

``BSY`` 表示设备仍在处理内部状态；``DRQ`` 表示设备处于需要数据传输的阶段。只有两者都清零，固件才开始发送 IDENTIFY。

IDENTIFY 为什么先试 PACKET DEVICE
-------------------------------

同一个 AHCI port 可能连接：

* ATA hard disk；
* SATA SSD；
* ATAPI optical device。

SeaBIOS 先发送：

::

   ATA IDENTIFY PACKET DEVICE

成功则按 ATAPI 设备处理。失败后再发送：

::

   ATA IDENTIFY DEVICE

成功则按普通 ATA disk 处理。

这是通过设备实际 command response 区分 ATA 与 ATAPI，不只是读取 ``PxSIG`` 后猜测。

一个 AHCI command 怎样被硬件看到
-----------------------------

SeaBIOS 为一次 command 填写 slot 0。

command table 中的 register FIS：

::

   FIS type = 0x27  Host-to-Device Register FIS
   C bit    = 1     command
   command  = IDENTIFY / READ DMA / SET FEATURES ...

command header 指明：

* FIS length；
* 是否写入 device；
* 是否为 ATAPI；
* PRDT entry 数；
* command-table physical address。

PRDT entry 指明数据 buffer 的物理地址和字节数。

准备完成后，SeaBIOS 写：

::

   PxCI bit 0 = 1

controller 看到 command issue bit 后：

::

   DMA 读取 command header
   → DMA 读取 command table/FIS/PRDT
   → 向 SATA device 发送 command
   → 按 PRDT 在 RAM 与 device 之间搬运数据
   → 把返回 FIS 写入 received-FIS area
   → 更新 PxIS / PxTFD / PxCI

SeaBIOS 轮询完成状态和 error bits；超时或 task-file error 时返回失败。

IDENTIFY 的 512 字节里保存了什么
-----------------------------

ATA IDENTIFY DEVICE 返回 256 个 16 位 words。SeaBIOS 重点读取：

``word 0``
   设备基本类型和 removable 标志。

``word 1 / 3 / 6``
   传统 physical CHS 信息。

``word 27–46``
   model string。ATA 字符串在每个 16 位 word 内按特殊字节顺序保存，读取时需要交换。

``word 60–61``
   28 位 LBA 可寻址 sector 数。

``word 83 bit 10``
   是否支持 48 位 LBA。

``word 88``
   支持的 Ultra DMA modes。

``word 100–103``
   48 位 LBA sector count。

SeaBIOS 不是从 QEMU 配置文件直接读取“磁盘 20 GiB”。它通过标准 IDENTIFY response 得到 sector count，再计算显示容量。

LBA48 为什么改变容量读取字段
-------------------------

如果 ``word 83 bit 10`` 为 1，SeaBIOS 使用：

::

   words 100–103 → 64-bit sector count

否则使用：

::

   words 60–61 → 32-bit LBA28 sector count

每个普通 ATA sector 为 512 bytes，因此磁盘字节容量为：

::

   sectors × 512

LBA28 最多描述约 128 GiB 二进制容量；更大磁盘必须使用 LBA48 command 和 sector-count fields。

PCHS、LCHS 和 LBA 是三个不同概念
-----------------------------

SeaBIOS 保存：

``PCHS``
   IDENTIFY 返回的 physical/legacy geometry fields。

``LCHS``
   BIOS 向旧式 ``INT 13h`` CHS 调用者公开的 logical geometry。

``LBA``
   实际线性 sector number。

现代磁盘内部早已不按 cylinder/head/sector 机械布局寻址。CHS 主要是 legacy BIOS 接口兼容编码。

SeaBIOS 先尝试从 QEMU 提供的 ``bios-geometry`` 路径匹配 LCHS；没有明确覆盖时，后续 drive mapping 会根据容量生成可兼容的 logical geometry。

为什么还要发送 SET FEATURES 选择传输模式
-----------------------------------

从 IDENTIFY data 中，SeaBIOS按优先级寻找：

::

   Ultra DMA
   → Multiword DMA
   → advanced PIO 3/4
   → default PIO

找到最高支持模式后，发送：

::

   ATA SET FEATURES
   feature = SET TRANSFER MODE

即便当前 QEMU 后端没有真实 SATA 线缆电气速率，这一步仍保持 ATA 设备初始化语义，让 SeaBIOS driver 与标准设备模型一致。

探测完成后为什么重新分配 port 结构和 DMA buffer
-----------------------------------------

初始探测使用 temporary memory，因为很多 ports 最终没有 device，失败时可以全部释放。

设备确认可用后，``ahci_port_realloc()``：

* 把 ``ahci_port_s`` metadata 搬到 F-segment；
* 把 command list、received FIS 和 command table 搬到可长期保留的 high memory；
* 再次停止 port engine；
* 重新写 ``PxCLB`` 和 ``PxFB``；
* 重新打开 ``FRE`` 和 ``ST``。

这样 POST 结束、temporary allocator 被收缩以后，``INT 13h`` 仍然能通过这些结构访问磁盘。

“探测时可用”不够，BIOS disk service 需要在 SeaBIOS init code 被释放后继续可用，所以持久结构的内存生命周期必须覆盖整个 bootloader 阶段。

硬盘与光驱怎样分流
----------------

普通 ATA disk：

::

   drive.type    = DTYPE_AHCI
   drive.blksize = 512
   drive.sectors = IDENTIFY sector count
   → boot_add_hd()

ATAPI optical device：

::

   drive.type    = DTYPE_AHCI_ATAPI
   drive.blksize = 2048
   → boot_add_cd()

ATAPI device 还必须在 IDENTIFY PACKET data 中声明 peripheral type 为 CD/DVD。其他 packet-device 类型不会被当作可启动光驱注册。

boot priority 来自设备路径，不来自发现先后
------------------------------------

AHCI driver 构造设备路径并调用：

.. code-block:: c

   bootprio_find_ata_device(controller, port, 0);

路径大致表达：

::

   PCI root
   → ICH9 AHCI function
   → drive@port
   → disk@0

它与 QEMU fw_cfg ``bootorder`` 中的路径进行匹配。匹配成功得到显式 priority；没有显式匹配时使用硬盘类别默认 priority。

所以 port 0 thread 比 USB thread 先完成，不等于它一定排在 USB 前面。``BootList`` 按 priority、启动类型、drive type 和 controller id 排序，不按线程完成时间简单追加。

boot_add_hd 此时做了什么，又没做什么
---------------------------------

``boot_add_hd()`` 调用：

.. code-block:: c

   bootentry_add(IPL_TYPE_HARDDISK,
                 priority,
                 drive,
                 description);

它创建 ``bootentry_s``，保存：

* type = hard disk；
* ``drive_s`` 指针；
* priority；
* 显示描述；
* BootList 链表节点。

它此时没有：

* 给硬盘分配 BIOS drive number ``0x80``；
* 读取 sector 0；
* 检查 ``0x55aa`` MBR signature；
* 执行 GRUB boot.img；
* 读取 partition table。

后面的 ``prepareboot():bcv_prepboot()`` 才会按排序后的 BootList 调用 ``map_hd_drive()``，建立 BIOS ``0x80`` drive map。再往后的 ``INT 19h`` 启动流程才会读取第一个 sector。

因此当前章节虽然已经有“可启动硬盘候选”，控制权仍然完全在 SeaBIOS POST 中。

block_setup 后面的三个入口
------------------------

``block_setup()`` 返回主线程后，``device_hardware_setup()`` 继续：

.. code-block:: c

   lpt_setup();
   serial_setup();
   cbfs_payload_setup();

它们分别建立传统并口、串口和条件 CBFS payload 支持。

当前 q35 + SeaBIOS 主线的启动磁盘结论不依赖这些入口；它们可以在 AHCI port thread 等待硬件时推进。

为什么必须在这里 wait_threads
--------------------------

``device_hardware_setup()`` 返回后，``maininit()`` 立即执行：

.. code-block:: c

   wait_threads();

实现是：

.. code-block:: c

   while (have_threads())
       yield();

主线程反复让出执行权，直到所有 USB port、USB class、PS/2 keyboard、AHCI port 和其他 block-controller threads 都结束。

这个 barrier 保证普通 Option ROM 扫描开始前：

* 内建设备驱动已经完成探测；
* 由内建驱动管理的 PCI function 已设置 ``have_driver``；
* 已发现的硬盘、光驱和 USB storage 已加入 BootList；
* 不会把仍由 SeaBIOS driver 初始化的设备再次交给普通 Option ROM；
* 启动菜单之后读取 BootList 时不会缺少迟到设备。

为什么 BootList 仍然不是最终版本
-----------------------------

``wait_threads()`` 只保证内建设备探测结束。

下一步 ``optionrom_setup()`` 还可能发现：

* storage controller Option ROM 的 BCV；
* network PXE ROM 的 BEV；
* CBFS ``genroms/`` 中的 legacy ROM；
* 其他 PnP Option ROM 启动入口。

这些入口也会加入 BootList。因此本章结束时 BootList 已经包含内建设备结果，却仍未最终封闭。

第十九章结束时的机器状态
----------------------

控制权目前走过：

::

   device_hardware_setup()
   → block_setup()
   → floppy / ATA conditional scans
   → ahci_setup()
   → 匹配 q35 ICH9 SATA AHCI function 00:1f.2
   → BAR5 / bus master
   → HBA reset / AHCI enable
   → CAP / PI
   → per-port threads
   → PxCLB / PxFB / command table
   → port link DET=3
   → wait BSY/DRQ clear
   → IDENTIFY PACKET or IDENTIFY DEVICE
   → LBA capacity / model / geometry / transfer mode
   → persistent AHCI structures
   → boot_add_hd() or boot_add_cd()
   → 其他 block driver 条件扫描
   → lpt_setup() / serial_setup() / cbfs_payload_setup()
   → device_hardware_setup() 返回
   → wait_threads()
   → 所有当前设备线程完成

此刻：

* 当前执行者：SeaBIOS ``maininit()``；
* 当前主流程 CPU：BSP；
* 模式：32 位保护模式；
* 分页：关闭；
* 固定启动盘 controller：q35 ICH9 AHCI，典型 BDF ``00:1f.2``；
* 固定启动盘位置：SATA port 0；
* HBA 与 port engine：已经初始化；
* disk IDENTIFY：已经完成；
* sector count、model、LBA48 能力和 transfer mode：已经记录；
* persistent AHCI command/FIS buffers：已经建立；
* ``BootList``：已经包含 AHCI hard-disk entry，以及条件 USB/CD/其他内建设备；
* BIOS drive ``0x80`` 映射：尚未在 ``bcv_prepboot()`` 中完成；
* MBR sector 0：尚未读取；
* 普通非 VGA Option ROM：尚未扫描；
* GRUB：尚未被读取或执行；
* Linux：尚未装入内存。

``maininit()`` 的下一条主流程调用是：

.. code-block:: c

   optionrom_setup();

下一章将扫描普通 PCI/CBFS Option ROM，解释 BCV、BEV、PXE 与 ``have_driver`` 的关系，并观察这些 ROM 怎样继续扩充 BootList。

资料
----

* `SeaBIOS src/post.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/post.c>`_；
* `SeaBIOS src/block.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/block.c>`_；
* `SeaBIOS src/hw/ahci.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/ahci.c>`_；
* `SeaBIOS src/boot.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/boot.c>`_；
* `SeaBIOS src/stacks.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/stacks.c>`_；
* `QEMU hw/i386/pc_q35.c <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/pc_q35.c>`_；
* `QEMU include/hw/southbridge/ich9.h <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/include/hw/southbridge/ich9.h>`_；
* `AHCI Specification 1.3.1 <https://www.intel.com/content/www/us/en/io/serial-ata/serial-ata-ahci-spec-rev1-3-1.html>`_；
* `ATA/ATAPI Command Set standards <https://www.t13.org>`_；
* `PCI Firmware Specification <https://pcisig.com/specifications>`_。