第二十二章：SeaBIOS 怎样把硬盘第一扇区读到 0x7c00 并交给 GRUB？
===================================================================

上一章结束时，SeaBIOS 已经完成启动前最后一轮数据结构收尾：

::

   AHCI port 0 drive_s
   → IDMap[EXTTYPE_HD][0]
   → BIOS drive 0x80
   → final BEV[]
   → PMM closed
   → E820 frozen
   → BIOS checksum updated

控制流仍在 ``maininit()`` 的 32 位保护模式环境中：

.. code-block:: c

   prepareboot();
   make_bios_readonly();
   startBoot();

这一章到达固件前传中的第一个真正执行者交接点：SeaBIOS 读取硬盘 LBA 0 的 512 字节，将其放到物理地址 ``0x7c00``，检查末尾签名，然后跳到 ``0000:7c00``。

固定主线规定该扇区由 GRUB i386-pc 安装，因此跳转后执行者从 SeaBIOS 变为 GRUB 的 ``boot.img``。本章只追到 GRUB 第一条指令即将执行的位置，下一章再进入 GRUB 源码。

为什么启动前还要把 BIOS shadow RAM 锁回只读
---------------------------------------

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

随后 SeaBIOS 修改 PAM：

* 已确认的 Option ROM 区域关闭写入；
* ``0xf0000`` 到 ``0xfffff`` BIOS segment 关闭写入；
* 读取仍来自 shadow RAM；
* 未被 ROM 占用的 upper-memory 区是否保留可写能力由构建配置和分配上界决定。

这一步保护的是已经生成的固件运行期镜像，不是重新把执行切回最初的 flash 内容。

为什么 startBoot 要清空 0x7000 到 EBDA 之前
--------------------------------------

``startBoot()`` 先执行：

.. code-block:: c

   memset((void*)BUILD_STACK_ADDR, 0,
          BUILD_EBDA_MINIMUM - BUILD_STACK_ADDR);

固定常量为：

::

   BUILD_STACK_ADDR  = 0x00007000
   BUILD_EBDA_MINIMUM = 0x00090000

因此被清理的范围大致是：

::

   0x00007000 .. 0x0008ffff

这是 POST 阶段临时栈和低端临时分配曾经使用的区域。清理它符合 PMM 收尾要求，也避免把固件临时数据无意暴露给启动代码。

几个关键区域不会被破坏：

* IVT 位于 ``0x00000``，低于清理起点；
* BDA 位于 ``0x00400``，低于清理起点；
* EBDA 位于实际分配的高端低内存区域，边界由 BDA 保存；
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
---------------------------

``ahci_process_op()`` 对 ``CMD_READ`` 调用 AHCI read path。

上一章已经建立并保留：

* command list；
* command table；
* received FIS buffer；
* HBA MMIO base；
* port number；
* port engine 状态。

读取时 SeaBIOS：

#. 构造 READ DMA 或 READ DMA EXT command FIS；
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

TPM 为什么在跳转前测量这 512 字节
-------------------------------

签名通过后，SeaBIOS 条件调用：

.. code-block:: c

   tpm_add_bcv(0x80,
               MAKE_FLATPTR(0x07c0, 0),
               512);

在启用 measured boot 的路径中，这把即将执行的 boot sector 纳入 TPM event/PCR 测量链。

前面 Option ROM 已被测量；这里测量的是真正从磁盘读取、马上取得控制权的启动代码。

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

第二十二章结束时的机器状态
-----------------------

控制流已经走过：

::

   maininit()
   → make_bios_readonly()
   → wbinvd
   → q35 PAM write-protect shadow BIOS/ROM
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
* 模式：16 位实模式；
* 分页：关闭；
* ``CS:IP``：``0000:7c00``；
* ``DL``：``0x80``；
* ``AX``：``0xaa55``；
* FLAGS.IF：1；
* 物理 ``0x7c00..0x7dff``：硬盘 LBA 0 的 512 字节；
* MBR signature：已通过 ``0x55aa`` 检查；
* q35 AHCI controller：仍由 SeaBIOS BIOS disk service 支持，供 GRUB 继续通过 ``INT 13h`` 使用；
* GRUB ``core.img``：尚未由 ``boot.img`` 读取；
* GRUB protected-mode core：尚未执行；
* Linux bzImage：尚未读取；
* Linux：尚未取得控制权。

下一条主流程入口不再属于 SeaBIOS：

::

   GRUB i386-pc boot.img @ 0000:7c00

下一章需要先固定 GRUB i386-pc 的准确源码版本和磁盘安装布局，再从 ``boot.img`` 的第一条汇编指令追踪它怎样找到并读取 ``core.img``。

资料
----

* `SeaBIOS src/post.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/post.c>`_；
* `SeaBIOS src/fw/shadow.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/shadow.c>`_；
* `SeaBIOS src/boot.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/boot.c>`_；
* `SeaBIOS src/disk.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/disk.c>`_；
* `SeaBIOS src/block.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/block.c>`_；
* `SeaBIOS src/hw/ahci.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/ahci.c>`_；
* `SeaBIOS src/stacks.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/stacks.c>`_；
* `SeaBIOS src/romlayout.S <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/romlayout.S>`_；
* `SeaBIOS src/std/disk.h <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/std/disk.h>`_；
* `BIOS Enhanced Disk Drive Specification <https://www.t13.org>`_。