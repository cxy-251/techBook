第十九章：SeaBIOS怎样发现q35的AHCI磁盘并把它加入启动列表？
================================================================

第018章结束在BSP上的SeaBIOS ``MainThread`` 从 ``ps2port_setup()`` 返回之后。处理器仍在
32位保护模式，分页关闭，MainThread自身的IF为0；PS/2初始化worker可能还在同一个BSP上
通过协作式调度等待ACK或BAT。 ``device_hardware_setup()`` 的下一条语句正是：

.. code-block:: c

   block_setup();

本章只追踪固定q35 ICH9 AHCI SATA port 0硬盘如何成为一个 ``BootList`` 候选，以及哪个
barrier才使这个候选稳定。它不提前分配BIOS drive number，也不读取MBR。

block_setup先留下两个容易被“没有设备”掩盖的状态
----------------------------------------------

MainThread按固定顺序调用：

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

这些入口逐个扫描自己认识的硬件，并不是互斥分支。固定QEMU q35把
``MachineClass.no_floppy`` 设为1，CMOS floppy type因而没有drive位；SeaBIOS不会创建
``drive_s`` 或floppy启动项。不过 ``floppy_setup()`` 仍复制diskette parameter table，
把IVT 1Eh指向该表，并通过 ``enable_hwirq(6, entry_0e)`` 安装IRQ6入口、解除master PIC
上的IRQ6屏蔽。没有FDC就没有设备能拉起这条线，但“没有floppy drive”和“setup无状态
变化”不是同一结论。

紧接着的 ``ata_setup()`` 遍历既有 ``PCIDevices``。它的表匹配PCI IDE class和一项特定
ATI兼容AHCI设备；固定00:1f.2是ICH9 SATA class、prog-if 1，不命中legacy ATA表，也不会
创建ATA channel worker。这个空扫描之后，MainThread仍把BDA ``disk_control_byte`` 写成
``0xc0``，并安装INT 76h/解除slave PIC IRQ14屏蔽。IRQ14开放同样不表示当前有legacy IDE
controller发中断。

至此，PIC在第018章状态上又开放了IRQ6和IRQ14；固定启动盘还没有 ``drive_s``。随后才
进入真正命中的 ``ahci_setup()``。

QEMU已经把port 0后端接到六端口ICH9 HBA
-------------------------------------

固定QEMU commit在PC machine初始化时默认令 ``sata_enabled=true``。 ``pc_q35_init()``
因而在00:1f.2创建 ``ich9-ahci``，其PCI class为SATA、programming interface为AHCI 1.x，
并注册BAR5的MMIO窗口。实现把 ``ports`` 固定为6，初始化HBA时把Ports Implemented写成：

::

   PI = (1 << 6) - 1 = 0x3f

因此PI的bit 0—5都表示实现了port register block。PI并不表示六个端口都连接了设备。
QEMU先按IDE backend index收集最多六个 ``DriveInfo``，再把非空的index ``i`` 接到AHCI
port ``i`` 的unit 0；本书固定的硬盘位于index/port 0，ports 1—5没有backend。

这组QEMU对象在SeaBIOS执行前已经存在：

::

   PCI function 00:1f.2
   → AHCIPCIState / AHCIState
   → six AHCIDevice + IDEBus objects
   → port 0 IDEDrive
   → fixed block backend

SeaBIOS只通过PCI config、ABAR和标准ATA command观察它们，不直接访问host磁盘文件。

AHCI匹配与have_driver在worker创建前已经完成
-----------------------------------------

仍在MainThread上， ``ahci_scan()`` 遍历 ``PCIDevices``，要求：

::

   pci->class   == PCI_CLASS_STORAGE_SATA
   pci->prog_if == 1

00:1f.2唯一命中固定存储主线，控制流进入 ``ahci_controller_setup(pci)``。该函数先调用
``create_bounce_buf()``；全局 ``bounce_buf_fl`` 还为空时，它从low memory分配一个
2048-byte buffer，供后来不能直接DMA的未对齐请求共用。分配失败会让整个controller
探测返回，不产生硬盘项。

随后 ``pci_enable_membar(pci, PCI_BASE_ADDRESS_5)`` 验证BAR5是4 GiB以下的有效memory
BAR，打开PCI memory decode，并立即执行：

.. code-block:: c

   pci->have_driver = 1;

所以固定AHCI在普通Option ROM扫描中被跳过的身份，此刻就已同步发布；它既不等待port
worker，也不由后面的 ``wait_threads()`` 产生。BAR失败则尚未置位并直接返回。

BAR成功后，SeaBIOS在F-segment分配持久的 ``ahci_ctrl_s``，记录PCI临时描述符、ABAR和
PCI interrupt-line值，再由 ``pci_enable_busmaster()`` 置PCI Command.BusMaster。后者
再次保持 ``have_driver=1``。SeaBIOS的AHCI路径实际轮询MMIO完成状态，没有在这里安装
AHCI handler、打开 ``PxIE`` 或全局AHCI interrupt enable；记录irq号不等于本章依赖该
中断。

HBA reset先于任何port command
----------------------------

MainThread读取GHC、置 ``HR``，给硬件500 ms deadline，并在轮询HR自动清零时调用
``yield()``。每次yield都可能让第018章留下的PS/2 worker推进；从MainThread恢复时
``check_irqs()`` 可短暂开放硬件中断，函数返回后MainThread仍保持IF=0。

固定QEMU HBA正常清除HR。SeaBIOS随后在GHC置 ``AE`` 并回读一次完成posted-write flush，
再读取 ``CAP`` 和 ``PI``。若HR到deadline仍不清零，当前实现释放controller并返回；由于
BAR helper早已置位， ``have_driver`` 不会随该失败回滚，但也不会出现硬盘
``BootList`` 项。

PI=0x3f让MainThread创建六份temporary port对象
--------------------------------------------

SeaBIOS从port 0扫描到31，只为PI中置位的bit继续。固定PI=0x3f，于是port 0—5各调用一次
``ahci_port_alloc()``。每份成功对象包含：

* ``malloc_tmp`` 的 ``ahci_port_s`` metadata；
* 1024-byte、1024-byte aligned的command list；
* 256-byte、256-byte aligned的received-FIS area；
* 256-byte、256-byte aligned的command table。

后三者此时也来自temporary allocator并被清零。SeaBIOS把list和FIS的低32位地址写入
``PxCLB``、 ``PxFB``；QEMU CAP声明64-bit address能力时还把对应高32位写成0。command
table地址稍后放入slot 0 header，而不是写入独立port register。

一次分配任一对象失败，就不会为该port调用 ``run_thread``；当前函数对已经取得的局部
temporary分配没有即时逐项回滚，这是失败路径边界，不能写成完整事务。固定成功路径六份
都分配成功，MainThread逐一：

.. code-block:: c

   run_thread(ahci_port_detect, port);

这些不是六个vCPU。它们是同一BSP上的SeaBIOS协作线程，只在当前执行者调用yield或线程
结束时切换。

每个worker先停旧engine并清轮询状态
--------------------------------

一个port worker进入 ``ahci_port_detect()`` 后，先调用 ``ahci_port_reset()``。它清
``PxCMD.FRE`` 和 ``PxCMD.ST``，等待FIS receive/list running位一起清零，再把 ``PxIE``
写0并以write-one-to-clear清 ``PxIS``。固定QEMU在deadline内完成停止；源码的通用超时
分支只告警并跳出等待，不能把“先停干净”扩写成任意硬件上的绝对保证。

接着 ``ahci_port_setup()`` 重新置 ``FRE``，并在 ``PxCMD`` 选择spin-up、power-on与
active ICC。worker轮询 ``PxSSTS.DET``：

::

   DET == 3  → device present and PHY communication established
   otherwise → continue until 10 ms link deadline

固定ports 1—5没有backend，因而到deadline仍不是3。它们返回失败，
``ahci_port_release()`` 再停各自engine，释放temporary list/FIS/table和metadata。它们
从未创建 ``drive_s``，也不会给BootList留下空项。

port 0还要跨过ready边界
-----------------------

port 0由QEMU backend建立link，DET成为3。worker清 ``PxSERR`` 后继续读取 ``PxTFD``，给
设备最长32 s让BSY和DRQ同时清零。link up只证明SATA通信已建立；BSY/DRQ清零才允许发送
第一条ATA command。固定虚拟盘正常ready，worker随后置 ``PxCMD.ST`` 启动command-list
engine。

SeaBIOS先准备 ``ATA_CMD_IDENTIFY_PACKET_DEVICE``。固定port 0是ATA硬盘而非ATAPI设备，
所以这次命令返回error； ``ahci_command()`` 清中断状态、写 ``PxCI bit 0``，在轮询中
读取 ``PxIS``/received FIS/PxTFD并进入non-queued error recovery。它停ST等待CR清零、
清SERR/PxIS，只有TFD仍带BSY或DRQ时才额外发COMRESET，最后重新置ST。

这个预期失败只把 ``port->atapi`` 设为0并转入第二次识别：

.. code-block:: c

   ATA_CMD_IDENTIFY_DEVICE

第二次成功返回512 bytes，也就是256个16-bit IDENTIFY words。一次command的硬件可见
边界是：

::

   fill host-to-device FIS and PRDT[0]
   → fill command header slot 0
   → PxCI = 1
   → QEMU DMA-reads header/table/FIS
   → device model executes command
   → QEMU DMA-writes data/received FIS
   → PxIS/PxTFD report completion
   → SeaBIOS polling worker resumes

SeaBIOS只使用一个PRDT entry和slot 0；buffer/list/table地址都写成低32位，高32位为0。

IDENTIFY先形成drive状态，再尝试设置传输模式
------------------------------------------

port 0 worker从IDENTIFY读取removable位、PCHS提示、model、ATA version和容量。若word 83
bit 10置位，就取words 100—103的LBA48 sector count；否则取words 60—61。固定
``drive_s`` 此时具有：

::

   type     = DTYPE_AHCI
   blksize  = 512
   sectors  = IDENTIFY-derived count
   cntl_id  = 0

容量与model来自模拟ATA协议，不来自SeaBIOS对QEMU配置的旁路读取。磁盘总容量没有在本书
固定条件中给出，所以正文不制造具体sector数或LCHS值。

``bootprio_find_ata_device(00:1f.2, 0, 0)`` 用PCI/drive路径查询fw_cfg ``bootorder``；
``boot_lchs_find_ata_device`` 同样查询条件 ``bios-geometry`` 覆盖。没有per-device
``bootindex`` 或显式逻辑几何时，这两个查询分别返回-1和未命中，后续仍有默认priority
与几何translation。

SeaBIOS再检查IDENTIFY words 53、63、64、88，按UDMA、multiword DMA、advanced PIO、
default PIO的顺序选候选值并发送 ``SET FEATURES / SET TRANSFER MODE``。固定QEMU通常
接受该命令，但源码把失败只记日志，仍让 ``ahci_port_setup()`` 返回成功。因此本章可以
确认“选择并尝试设置”，不能把传输模式命令成功当成drive登记的硬门。

持久化阶段是替换DMA缓冲，不是搬运旧内容
-------------------------------------

IDENTIFY成功后， ``ahci_port_detect()`` 调用 ``ahci_port_realloc()``。这一步先在
F-segment分配新 ``ahci_port_s``，复制metadata并释放旧temporary metadata；随后停port
engine，释放旧temporary command list、received-FIS和command table，再分别从high
memory重新分配1024/256/256-byte的持久buffer。

所以生命期变化是：

::

   temporary metadata  → copied into F-segment metadata
   temporary DMA areas → freed
   new ZoneHigh areas  → written into PxCLB/PxFB/header later

源码没有把旧DMA区内容“搬到”新地址。分配全成功后，SeaBIOS重写 ``PxCLB``、 ``PxFB``，
置 ``FRE|ST`` 重新启动engine。任一新buffer失败就释放新metadata和已分配buffer并返回
NULL，不登记drive；固定成功路径越过该回滚边界。

boot_add_hd只登记候选，不分配0x80
--------------------------------

持久化完成后worker才调用：

.. code-block:: c

   boot_add_hd(&port->drive, port->desc, port->prio);

QEMU PC默认boot order是 ``cad``。SeaBIOS在 ``boot_init()`` 已由CMOS把hard disk默认
priority设为101；port 0没有独立bootindex时 ``port->prio=-1``， ``boot_add_hd`` 通过
``defPrio`` 使用101。 ``bootentry_add`` 把一个 ``IPL_TYPE_HARDDISK`` 条目按priority、
type以及drive type/controller id插入 ``BootList``。

条目保存 ``drive_s`` 指针、priority和描述，但此刻仍没有：

* 写 ``IDMap[EXTTYPE_HD]``；
* 增加BDA ``hdcount``；
* 决定 ``DL=0x80``；
* 读取LBA 0或检查 ``0x55aa``；
* 进入GRUB。

这些边界分别属于第021章的 ``bcv_prepboot()`` 和第022章的INT 19h。

第一次wait_threads才封闭内建设备发现
----------------------------------

``ahci_setup()`` 在创建六个worker后就返回， ``block_setup()`` 继续扫描其余driver。
固定基线没有sdcard、ramdisk、virtio、SCSI或NVMe启动设备，所以这些入口不增加
``BootList``；显式附加硬件仍可走各自条件分支。MainThread随后完成
``lpt_setup()``、 ``serial_setup()`` 与空的QEMU ``cbfs_payload_setup()``，从
``device_hardware_setup()`` 返回。

第018章已经固定 ``threads_during_optionroms()=false``。因此 ``maininit()`` 紧接着：

.. code-block:: c

   wait_threads();

``wait_threads`` 在32位MainThread上反复检查 ``have_threads()`` 并yield，直到除
MainThread以外没有协作线程。固定成功出口由这个barrier证明：

* PS/2 keyboard worker已经成功或非致命失败并退出；
* AHCI ports 1—5已经link-down并释放temporary对象；
* AHCI port 0已经登记持久 ``drive_s`` 与hard-disk BootList条目；
* 没有迟到的内建设备线程再修改BootList。

``have_driver`` 早于这个barrier；BootList完整性才依赖它。barrier返回后MainThread仍在
BSP的32位保护模式、分页关闭、IF=0环境，下一条调用是 ``optionrom_setup()``。

本章结束状态
------------

* current executor：BSP上的SeaBIOS ``MainThread``，已从第一次 ``wait_threads()`` 返回；
* CPU/mode：32位保护模式，分页关闭，A20开启，MainThread IF=0；
* cooperative threads：固定PS/2与六个AHCI port worker均已退出， ``have_threads=false``；
* floppy/legacy ATA：没有drive/controller对象，但IVT 1Eh已更新，IRQ6和IRQ14已安装入口并
  解除PIC屏蔽，BDA ``disk_control_byte=0xc0``；
* q35 AHCI：00:1f.2 BAR5 memory decode与bus master开启， ``have_driver=1``，HBA AE开启；
* AHCI ports：PI=0x3f；ports 1—5没有持久对象，port 0 engine使用持久CLB/FIS/table；
* fixed disk：port 0 ``DTYPE_AHCI``、512-byte sectors、IDENTIFY-derived model/PCHS/capacity
  已记录；SET FEATURES已经尝试，失败不阻止登记；
* AHCI memory：共享bounce buffer在low memory，controller/port metadata在F-segment，
  command list、received FIS和command table在ZoneHigh；
* ``BootList``：包含priority 101的固定AHCI hard-disk条目；普通Option ROM条目尚未加入；
* ``IDMap`` 与BDA ``hdcount``：仍为空/0，BIOS ``0x80`` 尚未建立；
* MBR、GRUB、Linux：均未读取或执行；
* next entry： ``optionrom_setup()``。

关键边界
--------

#. ``floppy_setup``/``ata_setup`` 没有发现drive，仍分别改变IVT/PIC与BDA/PIC状态。
#. QEMU PI=0x3f表示六个port均实现，不表示六个port都有device；固定只连接port 0。
#. ``pci_enable_membar`` 成功时就置 ``have_driver``；第一次 ``wait_threads`` 只封闭worker
   与BootList，不负责发布该标志。
#. SeaBIOS AHCI在本章使用轮询加yield，没有开启AHCI硬件中断。
#. port reset的通用超时只告警后继续；本章“engine已停”绑定固定QEMU成功分支。
#. ATA硬盘先让IDENTIFY PACKET失败，再由IDENTIFY DEVICE成功识别；前一次失败不是整port
   探测失败。
#. ``SET FEATURES`` 失败非致命；persistent reallocation失败才阻止 ``boot_add_hd``。
#. ``ahci_port_realloc`` 替换而非复制旧DMA buffer内容。
#. ``boot_add_hd`` 只登记候选； ``0x80``、FDPT和MBR均属于后续边界。

下一入口
--------

``maininit()`` 已完成固定同步初始化路径中的第一次barrier，下一条语句是：

.. code-block:: c

   optionrom_setup();

第020章从普通Option ROM扫描开始。固定ICH9 AHCI因 ``have_driver=1`` 被跳过；无网络
override的默认q35 e1000e没有SeaBIOS内建driver，其组合ROM将成为本轮确定命中。

资料
----

* `SeaBIOS：device_hardware_setup、wait与相邻调用 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/post.c#L125-L234>`_；
* `SeaBIOS：block_setup扫描顺序 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/block.c#L503-L523>`_；
* `SeaBIOS：floppy无drive时仍发布的状态 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/floppy.c#L134-L174>`_；
* `SeaBIOS：legacy ATA扫描与setup出口 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/ata.c#L996-L1054>`_；
* `SeaBIOS：AHCI command轮询与错误恢复 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/ahci.c#L103-L215>`_；
* `SeaBIOS：AHCI temporary/persistent对象与port setup <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/ahci.c#L317-L606>`_；
* `SeaBIOS：AHCI登记、controller reset与PCI匹配 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/ahci.c#L608-L720>`_；
* `SeaBIOS：BootList排序与hard-disk登记 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/boot.c#L451-L615>`_；
* `SeaBIOS：PCI helper发布have_driver <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/pcidevice.c#L137-L191>`_；
* `SeaBIOS：协作式yield与wait_threads <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/stacks.c#L623-L669>`_；
* `QEMU：q35默认SATA、六端口controller与backend连接 <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/pc_q35.c#L284-L303>`_；
* `QEMU：ICH9 AHCI PCI class、prog-if与BAR5 <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/ide/ich.c#L123-L190>`_；
* `QEMU：AHCI CAP、PI与六个port对象 <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/ide/ahci.c#L544-L560>`_；
* `QEMU：把IDE backend index连接到同号AHCI port <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/ide/ahci.c#L1806-L1815>`_；
* `QEMU：PC默认boot order为cad <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/pc.c#L1683-L1706>`_；
* `AHCI 1.3.1 Specification <https://www.intel.com/content/www/us/en/io/serial-ata/serial-ata-ahci-spec-rev1-3-1.html>`_；
* `ATA/ATAPI Command Set standards <https://www.t13.org>`_。
