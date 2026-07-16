第二十二章：SeaBIOS 怎样把硬盘第一扇区读到 0x7c00 并交给 GRUB？
===================================================================

上一章结束时，SeaBIOS 已经完成启动前最后一轮数据结构收尾：

::

   AHCI port 0 drive_s
   → IDMap[EXTTYPE_HD][0]
   → BIOS drive 0x80
   → final BEV[]
   → PMM入口已撤销
   → 当前E820 map完成最后一次dump
   → BIOS checksum updated

控制流仍在 ``maininit()`` 的 32 位保护模式环境中：

.. code-block:: c

   prepareboot();
   make_bios_readonly();
   startBoot();

这一章到达固件前传中的第一个真正执行者交接点：SeaBIOS 读取硬盘 LBA 0 的 512 字节，将其放到物理地址 ``0x7c00``，检查末尾签名，然后跳到 ``0000:7c00``。

固定主线规定该扇区由 GRUB i386-pc 安装，因此跳转后执行者从 SeaBIOS 变为 GRUB 的 ``boot.img``。本章只追到 GRUB 第一条指令即将执行的位置，下一章再进入 GRUB 源码。

为什么启动前还要收回 BIOS shadow RAM 的写权限
-------------------------------------------

SeaBIOS 在较早的 POST 阶段调用 ``make_bios_writable()``，通过 q35 host bridge 的 PAM 寄存器，使 ``0xc0000`` 到 ``0xfffff`` 的 shadow RAM 可写。

这样才能完成：

* 重定位和修补 BIOS 数据；
* 部署 VGA 与普通 Option ROM；
* 写入运行期表和 checksum；
* 允许 Option ROM 完成初始化。

``prepareboot()`` 返回后，这些内容已经稳定。``make_bios_readonly()`` 对 q35 路径调用：

.. code-block:: c

   make_bios_readonly_intel(ShadowBDF,
                            Q35_HOST_BRIDGE_PAM0);

第一步是：

.. code-block:: c

   wbinvd();

它把处理器缓存中的脏数据写回并使缓存失效，避免尚未落入 shadow RAM 的修改在写保护开启后丢失。

随后 SeaBIOS 修改 PAM。固定QEMU target默认
``CONFIG_MALLOC_UPPERMEMORY=y``、 ``CONFIG_WRITABLE_UPPERMEMORY=n``；因此F segment的
``PAM0`` 被写成 ``0x10``，QEMU把 ``0xf0000..0xfffff`` 映射为只读RAM alias。SeaBIOS随后
从低地址遍历六个Option-ROM PAM byte：位于 ``rom_get_max()`` 以下的完整32 KiB窗口收紧为
``0x11``；边界落在窗口中间时写 ``0x31``，然后停止，边界以上承载运行期ZoneLow对象的窗口
保持 ``0x33``：

* nibble ``1`` 表示读来自shadow RAM、写不再落入该RAM；
* nibble ``3`` 表示该16 KiB半区仍读写shadow RAM；
* ``rom_get_max()`` 以下的Option ROM/清零padding范围被写保护；
* 边界以上仍承载运行期upper-memory分配的半区必须保持可写，不能把整个
  ``0xc0000..0xeffff`` 一概写成只读。

这一步保护的是已经生成的固件运行期镜像，不是重新把执行切回最初的 flash 内容。

为什么 startBoot 要清空固定的低端临时窗口
------------------------------------

``startBoot()`` 先执行：

.. code-block:: c

   memset((void*)BUILD_STACK_ADDR, 0,
          BUILD_EBDA_MINIMUM - BUILD_STACK_ADDR);

固定常量为：

::

   BUILD_STACK_ADDR  = 0x00007000
   BUILD_EBDA_MINIMUM = 0x00090000

因此被清理的范围精确是：

::

   0x00007000 .. 0x0008ffff

这是 POST 阶段临时栈和低端临时分配曾经使用的区域。清理它符合 PMM 收尾要求，也避免把
固件临时数据无意暴露给启动代码。这里的上界是编译期常量
``BUILD_EBDA_MINIMUM``，不是运行时从BDA读取的实际EBDA起点；实际EBDA只需保证不低于这个
边界。

几个关键区域不会被破坏：

* IVT 位于 ``0x00000``，低于清理起点；
* BDA 位于 ``0x00400``，低于清理起点；
* 实际EBDA位于 ``0x90000`` 或更高的低内存高端，起点仍由BDA保存；
* BIOS/Option ROM 位于 ``0xc0000`` 以上；
* ``0x7c00`` 此时会被清零，随后马上由磁盘第一扇区覆盖。

startBoot 不直接调用 boot_disk
-----------------------------

清理完成后：

.. code-block:: c

   struct bregs br;
   memset(&br, 0, sizeof(br));
   br.flags = F_IF;
   call16_int(0x19, &br);

SeaBIOS 仍沿用传统 BIOS 启动接口 ``INT 19h``，而不是从 32 位 C 代码直接调用某个磁盘函数。

这样保留了两个兼容能力：

* Option ROM 或兼容层可以按规则参与 ``INT 19h`` 入口；
* 启动失败后可以通过 ``INT 18h`` 继续下一个启动项。

从 32 位 C 到 INT 19h 前发生一次模式切换
-------------------------------------

``call16_int()`` 最终进入 SeaBIOS 的 16 位 thunk。``transition16`` 在汇编中完成：

::

   装载 16 位段描述符
   → 远跳转到 16 位代码段
   → CR0.PE = 0
   → 远跳转刷新取指队列
   → 装载 real-mode IDT
   → 清理 DS/ES/FS/GS/SS
   → 进入 16 位 real-mode 环境

因此 ``INT 19h`` 的外部接口仍表现为传统实模式 BIOS 服务。

SeaBIOS 的 ``INT 19h`` 入口随后会通过自己的入口 thunk 再进入 32 位 ``handle_19()`` 执行主要策略代码。这里存在两次环境转换：

::

   32-bit maininit
   → 16-bit INT 19h interface
   → SeaBIOS 32-bit handle_19
   → 后续再调用 16-bit INT 13h

传统中断接口是外部 ABI，主要实现仍可放在 32 位 C 代码中。

handle_19 怎样选择第一个启动动作
-------------------------------

``src/boot.c`` 定义：

.. code-block:: c

   void handle_19(void)
   {
       BootSequence = 0;
       do_boot(0);
   }

``BootSequence`` 记录当前正在尝试 ``BEV[]`` 中的第几项。

``do_boot(0)`` 读取第一项并按类型分派：

::

   floppy       → boot_disk(0x00, ...)
   hard disk    → boot_disk(0x80, 1)
   CD-ROM       → boot_cdrom(...)
   CBFS         → boot_cbfs(...)
   Option ROM   → boot_rom(vector)
   HALT         → boot_fail()

固定主线把 AHCI port 0 硬盘放在启动顺序首位，因此进入：

.. code-block:: c

   boot_disk(0x80, 1);

如果 QEMU ``bootorder``、启动菜单选择或 PXE ROM 优先级不同，``do_boot(0)`` 可以进入另一分支。这里继续固定的 hard-disk 路径。

boot_disk 为什么使用旧式 CHS 读取
-------------------------------

``boot_disk()`` 构造一次传统 ``INT 13h AH=02h`` 调用：

.. code-block:: c

   u16 bootseg = 0x07c0;

   memset(&br, 0, sizeof(br));
   br.flags = F_IF;
   br.dl = 0x80;
   br.es = 0x07c0;
   br.ah = 0x02;
   br.al = 1;
   br.cl = 1;
   call16_int(0x13, &br);

因为 ``bregs`` 先被清零，完整 CHS 和缓冲区参数是：

::

   AH = 0x02       read sectors
   AL = 1          read one sector
   CH = 0          cylinder 0
   CL = 1          sector 1
   DH = 0          head 0
   DL = 0x80       first BIOS hard disk
   ES = 0x07c0
   BX = 0x0000

它读取的是 CHS ``0/0/1``，即传统磁盘的第一个扇区。

这里没有使用 ``INT 13h Extensions AH=42h``，因为读取第一个扇区的 CHS 地址始终可表示。GRUB 获得控制权后可以再探测 EDD/LBA 扩展，读取更远位置的 ``core.img``。

0x07c0:0000 为什么等于物理地址 0x7c00
-----------------------------------

实模式线性地址计算是：

::

   physical = segment * 16 + offset

代入：

::

   0x07c0 * 16 + 0x0000
   = 0x00007c00

因此磁盘数据缓冲区是物理地址 ``0x7c00``。

这不是由磁盘控制器决定的地址。SeaBIOS 在调用 ``INT 13h`` 时明确选择了它。

INT 13h 怎样从 DL=0x80 找回 AHCI drive_s
---------------------------------------

``handle_13()`` 取得：

.. code-block:: c

   u8 extdrive = regs->dl;

固定路径没有活动的 CD emulation，因此进入：

.. code-block:: c

   handle_legacy_disk(regs, 0x80);

硬盘索引计算为：

::

   0x80 - EXTSTART_HD
   = 0

随后：

.. code-block:: c

   getDrive(EXTTYPE_HD, 0)
   → IDMap[EXTTYPE_HD][0]
   → q35 AHCI port 0 drive_s

这一步使用了上一章 ``map_hd_drive()`` 建立的映射。

如果没有那个映射，``DL=0x80`` 只是一串数字，SeaBIOS 无法知道应该调用哪一个控制器驱动。

disk_1302 怎样把 CHS 变成 LBA 0
-----------------------------

``AH=02h`` 分派到：

.. code-block:: c

   disk_1302(regs, drive)
   → basic_access(regs, drive, CMD_READ)

``basic_access()`` 解析：

::

   count    = AL = 1
   cylinder = CH + CL 高两位 = 0
   head     = DH = 0
   sector   = CL 低六位 = 1

然后使用上一章建立的逻辑 CHS：

.. code-block:: c

   lba = ((cylinder * heads) + head)
         * sectors_per_track
         + sector - 1;

代入 ``0/0/1``：

::

   lba = 0

缓冲区转换为：

.. code-block:: c

   dop.buf_fl = MAKE_FLATPTR(0x07c0, 0x0000);

最终形成：

::

   command = CMD_READ
   drive   = AHCI port 0 drive_s
   lba     = 0
   count   = 1
   buffer  = 0x00007c00

16 位 INT 13h 为什么还能调用 32 位 AHCI 驱动
---------------------------------------

``send_disk_op()`` 在 16 位 BIOS 服务环境中进入 ``process_op()``。

AHCI 驱动本身属于 32 位平坦模式路径。分派过程是：

::

   process_op()
   → process_op_16()
   → 当前 drive type 不是传统 ATA/floppy
   → process_op_both()
   → call32(process_op_32, ...)
   → DTYPE_AHCI
   → ahci_process_op()

SeaBIOS 再次通过 thunk 打开 ``CR0.PE``，进入 32 位模式运行 AHCI 代码，完成后返回 16 位 ``INT 13h`` 调用现场。

所以启动扇区读取横跨三个层次：

::

   legacy INT 13h ABI
   → SeaBIOS disk_op abstraction
   → 32-bit AHCI DMA engine

这说明“BIOS 使用 CHS”只描述外部接口。底层控制器仍按 LBA 和 DMA 执行。

AHCI 怎样把 LBA 0 读进 0x7c00
----------------------------

``ahci_process_op()`` 对 ``CMD_READ`` 调用 AHCI read path。

上一章已经建立并保留：

* command list；
* command table；
* received FIS buffer；
* HBA MMIO base；
* port number；
* port engine 状态。

读取时 SeaBIOS：

#. ``sata_prep_readwrite()`` 看到 ``count=1`` 且 ``lba+count < 2^28``，精确选择
   ``ATA_CMD_READ_DMA``（``0xc8``），不是 ``READ DMA EXT``；
#. 设置 LBA=0、sector count=1；
#. 在 PRDT 中填写目标 buffer ``0x7c00`` 和长度 512；
#. 写 ``PxCI`` bit 0 提交 command slot；
#. 等待 completion FIS/interrupt status；
#. 检查 ``BSY``、``DF``、``ERR`` 和 ``RDY``；
#. 返回 ``DISK_RET_SUCCESS`` 或错误码。

``0x7c00`` 是偶数对齐地址，因此 AHCI 路径可以直接 DMA 到目标缓冲区，不需要为奇地址使用 bounce buffer。

成功返回时 INT 13h 怎样表示结果
-----------------------------

``basic_access()`` 把实际传输扇区数写回 ``AL``，然后 ``disk_ret()``：

* 在 BDA 更新最后一次硬盘状态；
* 成功时清除 Carry Flag；
* 失败时设置 Carry Flag 并返回 BIOS disk status code。

``boot_disk()`` 检查：

.. code-block:: c

   if (br.flags & F_CF) {
       printf("Boot failed: could not read the boot disk\n");
       return;
   }

固定正常路径中 CF 清零，物理地址 ``0x7c00..0x7dff`` 现在包含硬盘 sector 0。

为什么还要检查 0x55aa
--------------------

SeaBIOS 把 ``0x7c00`` 解释为 ``struct mbr_s``。其末尾：

::

   offset 0x1fe: u16 signature

检查代码是：

.. code-block:: c

   if (mbr->signature != MBR_SIGNATURE)
       ...

其中：

.. code-block:: c

   #define MBR_SIGNATURE 0xaa55

x86 是小端序，所以扇区最后两个字节实际排列为：

::

   offset 510 = 0x55
   offset 511 = 0xaa

缺少签名时，SeaBIOS 报告 ``not a bootable disk``，不会跳入扇区内容。

签名只证明它符合传统 boot-sector 标记，不证明代码一定正确，也不证明分区表或 GRUB ``core.img`` 完整。

固定无TPM时为什么测量调用没有状态变化
----------------------------------

签名通过后，SeaBIOS 条件调用：

.. code-block:: c

   tpm_add_bcv(0x80,
               MAKE_FLATPTR(0x07c0, 0),
               512);

在存在并启用TPM的条件路径中，这会把即将执行的boot sector纳入event/PCR测量链；但第016章
已经固定当前QEMU机器没有TPM。当前调用因此不创建event、不扩展PCR，也不改变本批对象账本。
它仍位于签名检查之后、执行交接之前，不能因为固定路径无状态变化而把调用顺序删掉。

为什么最终跳转使用 0000:7c00 而不是 07c0:0000
------------------------------------------

两组 segment:offset 指向同一物理地址。SeaBIOS 在跳转前规范化：

.. code-block:: c

   u16 bootip = (bootseg & 0x0fff) << 4;
   bootseg &= 0xf000;

原始：

::

   bootseg = 0x07c0

计算后：

::

   bootip  = 0x7c00
   bootseg = 0x0000

因此调用入口是：

::

   CS:IP = 0000:7c00

它与 ``07c0:0000`` 的物理地址相同，形式更适合让 offset 直接表示低端物理地址。

SeaBIOS 交给启动扇区哪些寄存器
----------------------------

``call_boot_entry()`` 构造新的寄存器状态：

.. code-block:: c

   memset(&br, 0, sizeof(br));
   br.flags = F_IF;
   br.code = SEGOFF(0x0000, 0x7c00);
   br.dl = 0x80;
   br.ax = 0xaa55;
   farcall16(&br);

在这条具体 SeaBIOS 路径中：

::

   CS:IP = 0000:7c00
   DL    = 0x80
   AX    = 0xaa55
   IF    = 1

``farcall16()`` 先用 ``call16_override(0)`` 建立普通实模式环境；默认
``CONFIG_DISABLE_A20=n``，所以A20保持开启。进入INT 19h的32位handler时暂时屏蔽的NMI也在
回到外部16位环境时恢复。 ``bregs`` 中的通用寄存器和 ``DS/ES`` 来自清零后的结构，只有上面
列出的 ``AX``、 ``DL``、 ``CS:IP`` 和FLAGS被明确改写； ``SS:SP`` 则仍是SeaBIOS调用栈，
GRUB不能把它当成自己的长期栈。

其余由 ``bregs`` 表达的通用寄存器被清零。SeaBIOS thunk 使用普通 real-mode ``farcall16``，而不是 Option ROM 使用的 big-real 版本。

对可移植 boot sector 来说，真正应依赖的传统关键信息是 ``DL``：它标识 BIOS 从哪一个 drive 启动。启动代码应自行建立可靠的 ``DS``、``ES``、``SS:SP`` 和方向标志环境，不应把某个 BIOS 实现的附加初值当作通用规范保证。

farcall16 怎样真正进入 0000:7c00
------------------------------

``farcall16()`` 先调用：

.. code-block:: c

   call16_override(0);

SeaBIOS 选择普通实模式环境，然后 ``_farcall16()`` 进入汇编 ``__farcall16``。

汇编将目标 flags 和 ``CS:IP`` 压入栈，恢复 ``bregs`` 中的寄存器，最后执行：

.. code-block:: asm

   iretw

``iretw`` 同时装载：

* ``IP=0x7c00``；
* ``CS=0x0000``；
* 包含 ``IF=1`` 的 FLAGS。

下一条被取出的指令来自刚刚读入内存的 sector 0。

如果启动扇区最终执行远返回，``farcall16`` 仍保留返回 SeaBIOS 的路径；正常 bootloader 会继续加载自身阶段而不返回。

启动失败时为什么会进入 INT 18h
----------------------------

``do_boot()`` 在当前启动方法返回后执行：

.. code-block:: c

   call16_int(0x18, &br);

``handle_18()`` 增加 ``BootSequence``，再调用 ``do_boot(next)`` 尝试 ``BEV[]`` 下一项。

因此失败恢复链是：

::

   hard disk read/signature/boot code returns
   → INT 18h
   → next BEV[] entry
   → CD / PXE / CBFS / 其他入口
   → 全部失败后等待并重启

固定正常路径不会走到这里，因为 GRUB boot code 接管后继续加载后续阶段。

0x7c00 中的内容为什么现在可以称为 GRUB boot.img
--------------------------------------------

SeaBIOS 本身只知道：

* 这是 BIOS drive ``0x80`` 的第一个 512-byte sector；
* 末尾有 ``0x55aa``；
* 它应该作为传统 boot sector 执行。

SeaBIOS 不识别其中是否为 GRUB、Windows boot code、SYSLINUX 或其他程序。

固定主线额外规定这块硬盘已由 GRUB i386-pc 安装，所以 sector 0 的执行代码属于 GRUB ``boot.img``。这个结论来自磁盘构建前提，不来自 ``INT 19h`` 的自动识别。

从下一条指令开始，SeaBIOS 不再决定主流程。GRUB ``boot.img`` 将使用 ``DL=0x80`` 和 BIOS 磁盘服务定位并加载嵌入区中的后续代码。

本章结束状态
------------

控制流已经走过：

::

   maininit()
   → make_bios_readonly()
   → wbinvd
   → q35 PAM撤销F segment和rom_get_max以下ROM/padding范围的写权限
   → startBoot()
   → 清理 0x7000..0x8ffff
   → call16_int(0x19)
   → transition16 / real-mode IDT
   → handle_19()
   → BootSequence = 0
   → do_boot(0)
   → fixed hard-disk entry
   → boot_disk(0x80, checksig=1)
   → INT 13h AH=02h CHS 0/0/1
   → IDMap[HD][0]
   → AHCI port 0 drive_s
   → CHS 转 LBA 0
   → call32(process_op_32)
   → ahci_process_op(CMD_READ)
   → ATA READ DMA(0xc8), slot 0, one PRDT
   → DMA 512 bytes 到 0x7c00
   → CF=0
   → 检查 0x55aa
   → 条件 TPM 测量
   → 规范化为 0000:7c00
   → AX=0xaa55, DL=0x80, IF=1
   → farcall16 / iretw

此刻：

* 当前执行者：即将从 SeaBIOS 切换到 GRUB ``boot.img``；
* CPU：BSP；
* 模式：16位实模式，分页关闭，A20开启，NMI已恢复；
* ``CS:IP``：``0000:7c00``；
* ``DL``：``0x80``；
* ``AX``：``0xaa55``；
* FLAGS.IF：1，方向标志为0；
* 物理 ``0x7c00..0x7dff``：硬盘 LBA 0 的 512 字节；
* MBR signature：已通过 ``0x55aa`` 检查；
* q35 PAM：F segment和 ``rom_get_max()`` 以下shadow已收回写权限；其上运行期ZoneLow分配
  仍可写；
* q35 AHCI controller：仍由SeaBIOS BIOS disk service支持，供GRUB继续通过 ``INT 13h`` 使用；
* GRUB ``core.img``：尚未由 ``boot.img`` 读取；
* GRUB protected-mode core：尚未执行；
* Linux bzImage：尚未读取；
* Linux：尚未取得控制权。

关键边界
--------

* ``e820_prepboot()`` 只dump当前map；本章没有继承或制造E820 ``frozen`` 状态。
* ``startBoot()`` 清零到固定 ``BUILD_EBDA_MINIMUM``，不是遍历到运行时EBDA，也不清IVT/BDA。
* SeaBIOS外部使用CHS ``0/0/1``，内部转换为LBA 0；固定AHCI命令是非queued
  ``READ DMA(0xc8)``，不是EDD调用或 ``READ DMA EXT``。
* ``0x55aa`` 只证明传统boot-sector签名存在；“内容是GRUB”来自固定安装前提，不来自SeaBIOS
  识别。
* 当前无TPM， ``tpm_add_bcv()`` 不产生event/PCR状态； ``call_boot_entry()`` 则确实固定
  ``AX=0xaa55``、 ``DL=0x80`` 与 ``IF=1``。
* 一旦 ``iretw`` 取出 ``0000:7c00``，当前执行者已经是磁盘代码；只有它返回时SeaBIOS才沿
  INT 18h尝试下一项。

下一入口
--------

下一条主流程入口不再属于SeaBIOS：

::

   GRUB i386-pc boot.img @ 0000:7c00

第023章从固定GRUB 2.14 ``grub-core/boot/i386/pc/boot.S:_start`` 的跳过BPB指令开始，先区分
安装器写入字段与本书采用的磁盘布局约定，再追踪它读取 ``core.img`` 第一扇区。

资料
----

* `SeaBIOS固定提交：prepareboot与startBoot <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/post.c#L160-L234>`_；
* `SeaBIOS固定提交：q35 shadow写保护 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/shadow.c#L77-L167>`_；
* `QEMU固定提交：PAM alias语义 <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/pci-host/pam.c#L33-L69>`_；
* `SeaBIOS固定提交：boot_disk与INT 19h策略 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/boot.c#L865-L1046>`_；
* `SeaBIOS固定提交：CHS与EDD disk_op <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/disk.c#L118-L189>`_；
* `SeaBIOS固定提交：16/32位disk dispatch <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/block.c#L542-L638>`_；
* `SeaBIOS固定提交：AHCI FIS、PRDT与轮询 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/ahci.c#L27-L315>`_；
* `SeaBIOS固定提交：real-mode transition与farcall <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/romlayout.S#L69-L163>`_；
* `SeaBIOS固定提交：外部16位调用环境 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/stacks.c#L409-L453>`_。
