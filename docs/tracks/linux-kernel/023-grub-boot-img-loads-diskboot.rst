第二十三章：GRUB boot.img 怎样从 0x7c00 读出 core.img 的第一扇区？
====================================================================

上一章结束时，SeaBIOS 已经把启动盘 LBA 0 的 512 字节放到物理地址 ``0x7c00``，
并以如下状态把控制权交给它：

::

   CS:IP = 0000:7c00
   DL    = 0x80
   AX    = 0xaa55
   CPU   = 16 位实模式
   paging = off

从这一刻开始，当前执行者不再是 SeaBIOS，而是磁盘主引导记录中的 GRUB ``boot.img``。

本书从这里固定 GRUB 源码版本
----------------------------

为了让后面的每个字段、偏移和跳转都能复现，本书固定使用：

::

   GNU GRUB release: 2.14
   release date:     2026-01-14
   source mirror:    GitMirroring/grub
   release commit:   d38d6a1a9b79427848976f53d474392cd29c2a71
   target:           i386-pc

权威发布物是 GNU 官方 ``grub-2.14.tar.xz``；GitHub 镜像只用于提供稳定、可直接点击到具体
源码文件和发布提交的引用。

源码、平台条件与磁盘布局约定必须分开
------------------------------------

合同固定了MBR、第一分区从LBA 2048开始以及GRUB i386-pc，但仓库没有保存本次安装产生的
逐扇区磁盘镜像。 ``pc_partition_map_embed()`` 会先提供从LBA 1递增的post-MBR扇区，同时扫描
若干已知的第三方签名；命中时会跳过相应扇区。因此“第一分区从LBA 2048开始”本身不能证明
``core.img`` 必定从LBA 1开始，也不能证明blocklist只有一项。

为了让本书的数值路径保持唯一，本章继续采用一个**明确的磁盘布局约定**：post-MBR gap没有
触发GRUB签名避让，安装器取得的embedding sectors从LBA 1连续递增。在这个约定下：

::

   disk LBA 0      GRUB boot.img + 原有 MBR partition table
   disk LBA 1      core.img sector 0，也就是 diskboot.img
   disk LBA 2..N   core.img 剩余部分
   first partition 从 LBA 2048 开始

这是固定源码上的clean-gap成功分支，不是假称已经从一个缺失的磁盘artifact中读出的事实。
运行时真正权威的地址仍是安装器写入 ``boot.img`` 的 ``kernel_sector`` 以及
``diskboot.img`` 的blocklist；如果以后加入可复现磁盘构建物，应以解析产物所得值替换本约定。

boot.img 不是安装时原样写入的模板
---------------------------------

``grub-core/boot/i386/pc/boot.S`` 编译得到一个恰好 512 字节的 ``boot.img`` 模板。
``grub-setup`` 在把它写入 LBA 0 前会修改多个位置。

首先，它读取磁盘原来的 LBA 0，然后保存其中已有的：

* BIOS Parameter Block 区域；
* Windows NT disk signature；
* 四项 MBR partition table。

对应偏移是：

::

   0x003..0x059   可保留的 BPB 区域
   0x1b8..0x1bd   disk signature 与保留字段
   0x1be..0x1fd   四项 MBR partition table
   0x1fe..0x1ff   新boot.img模板自带的0x55aa，不从旧MBR复制

``setup.c`` 总会复制 ``0x003..0x059`` 的possible DOS BPB；在当前硬盘/MBR路径还复制
``0x1b8..0x1fd``。复制范围明确在 ``0x1fe`` 前结束，最终签名由新 ``boot.img`` 模板自身的
``.word 0xaa55`` 提供。安装GRUB因此既不是整扇区盲覆盖，也不是原样保留旧MBR。

接着，``write_rootdev()`` 修改 ``boot.img`` 内部两个关键字段：

``boot_drive``
   位于偏移 ``0x64``。BIOS版 ``write_rootdev()`` 明确写入 ``0xff``，表示运行时使用BIOS
   传入的 ``DL``，而不是
   强制指定另一个驱动号。

``kernel_sector``
   位于偏移 ``0x5c``，宽度为 64 位。这里写入 ``core.img`` 第一个扇区的绝对 LBA。
   当前clean-gap布局约定中，它被写成 ``1``。

因此，磁盘上的 LBA 0 已经不是一个完全通用的 GRUB 模板。它已经被安装器绑定到这块磁盘上
``core.img`` 的实际位置。

为什么第一条指令先跨过 BPB
--------------------------

``boot.S`` 的入口是：

.. code-block:: asm

   _start:
   start:
       jmp after_BPB
       nop

CPU 从 ``0x7c00`` 开始执行时，先跳过从偏移 ``0x03`` 开始的 BPB 兼容区域。

GRUB 仍保留这块布局，因为同一个 512 字节启动映像既可能被放进 MBR，也可能被安装到某些
文件系统或分区的 boot sector。许多工具和固件会期待开头存在类似 FAT/HPFS BPB 的空间。

这里的跳转还有一个很现实的约束：

* 主引导记录总共只有 512 字节；
* 最后 66 字节要容纳 partition table 与 ``0x55aa``；
* BPB 兼容区也不能随意占用；
* ``boot.img`` 只能完成最小环境整理和读取下一个扇区。

它没有空间理解文件系统、读取 ``grub.cfg`` 或解析 ELF。那些能力都在后面的 ``core.img``。

先关闭中断，再修正 BIOS 传入的启动盘号
------------------------------------

进入 ``after_BPB`` 后，第一条操作是：

.. code-block:: asm

   cli

当前段寄存器和栈还没有由 GRUB 自己建立，代码不能允许一个硬件中断在这个窗口里使用未知的
``SS:SP``。

随后是 ``boot_drive_check``。在硬盘安装时，``grub-setup`` 会把模板中的短跳转改成两个
``NOP``，启用这段兼容检查：

.. code-block:: asm

   testb $0x80, %dl
   jz    maybe_bad_drive
   testb $0x70, %dl
   jz    drive_ok
   movb  $0x80, %dl

合法的传统 BIOS 驱动号通常属于：

::

   0x00..0x0f   floppy-like drive
   0x80..0x8f   hard disk

某些旧 BIOS 即使从硬盘启动，也可能错误传入 ``DL=0x00`` 或其他异常值。GRUB 在确认自己安装于
硬盘时，可以把明显错误的值修正为 ``0x80``。

当前clean-gap安装约定同时采用 ``grub-setup`` 默认 ``allow_floppy=0``；目标又是hard disk，
所以安装器确实把原两字节跳转改成两个
``NOP`` 并启用检查。SeaBIOS本来就正确传入 ``DL=0x80``；第一项test不跳到纠正分支，第二项
确认 ``0x70`` mask为0，最终不改 ``DL``。

为什么还要远跳转到 0000:real_start
----------------------------------

SeaBIOS 当前明确使用：

::

   CS:IP = 0000:7c00

GRUB 仍然执行：

.. code-block:: asm

   ljmp $0, $real_start

原因是有些 BIOS 会使用等价的另一种表示：

::

   07c0:0000

两者都指向物理地址 ``0x7c00``：

::

   0x0000 * 16 + 0x7c00 = 0x7c00
   0x07c0 * 16 + 0x0000 = 0x7c00

然而后续代码中的标签地址、``DS=0`` 数据访问和近跳转都按 ``CS=0`` 的布局编写。远跳转会同时
重新装载 ``CS`` 和 ``IP``，把两种可能的 BIOS 入口统一成：

::

   CS = 0
   IP = real_start 的物理偏移

建立 GRUB 自己的实模式栈
------------------------

``real_start`` 执行：

.. code-block:: asm

   xorw %ax, %ax
   movw %ax, %ds
   movw %ax, %ss
   movw $0x2000, %sp
   sti

此时：

::

   DS:offset 直接表示低端物理地址
   SS:SP = 0000:2000
   栈顶物理地址 = 0x2000

这里的 ``GRUB_BOOT_MACHINE_STACK_SEG`` 名字容易误导。宏值是 ``0x2000``，但代码把它直接写入
``SP``，而 ``SS`` 已经是 0，所以实际栈顶是物理地址 ``0x2000``，不是 segment ``0x2000``
对应的 ``0x20000``。

栈建立后才重新 ``sti``。SeaBIOS 的时钟和键盘中断服务仍然存在，GRUB 后面进行 BIOS 调用时
可以继续使用这些固件设施。

第一时间保存 DL
---------------

GRUB 先读取安装器可能写入的 ``boot_drive`` 字段：

.. code-block:: asm

   movb boot_drive, %al
   cmpb $0xff, %al
   je   use_bios_drive
   movb %al, %dl

当前字段为 ``0xff``，因此保持 SeaBIOS 传入的 ``DL=0x80``。

随后立即：

.. code-block:: asm

   pushw %dx

这是因为 BIOS ``INT 13h`` 接口只承诺返回规定的输出寄存器。现实中的固件实现甚至可能错误破坏
``DL``。GRUB 不把启动盘号长期寄存在一个随时可能被 BIOS 调用修改的寄存器里，而是先压栈保存。

屏幕上为什么会出现 GRUB 字样
----------------------------

``boot.img`` 使用：

.. code-block:: asm

   movw $notification_string, %si
   call message

``message`` 逐字节读取字符串，并用 BIOS：

::

   INT 10h
   AH = 0x0e   teletype output

输出：

::

   GRUB 

这串字符不仅是提示。早期机器如果停在：

::

   GRUB Read Error

就能大致判断：

* SeaBIOS 已经成功读取 LBA 0；
* ``boot.img`` 已经开始执行；
* 错误发生在读取 ``core.img`` 第一扇区时。

boot.img 先询问 BIOS 是否支持 EDD/LBA
------------------------------------

传统 ``INT 13h AH=02h`` 只能使用 CHS 地址。现代 BIOS 扩展提供 EDD 接口，可以直接使用 64 位
LBA。

GRUB 执行：

.. code-block:: asm

   AH = 0x41
   BX = 0x55aa
   DL = 0x80
   INT 13h

成功条件包括：

::

   Carry Flag = 0
   BX = 0xaa55
   CX bit 0 = 1

SeaBIOS ``disk_1341()`` 在这块硬盘上返回 ``BX=0xaa55``、 ``CX=0x0007``、 ``AH=0x30`` 并清
CF，因此当前主线进入 ``lba_mode``，不会使用后面的CHS几何换算回退。

调用返回后，GRUB 仍然把压栈保存的 ``DX`` 恢复再重新压回去，因为历史上确实存在会破坏
``DL`` 的 BIOS。

构造 16 字节 Disk Address Packet
--------------------------------

EDD ``INT 13h AH=42h`` 不把完整请求塞进通用寄存器，而是由 ``DS:SI`` 指向一个 16 字节
Disk Address Packet：

::

   offset  size  meaning
   0x00    2     packet size = 0x0010
   0x02    2     sector count = 1
   0x04    2     buffer offset = 0
   0x06    2     buffer segment = 0x7000
   0x08    8     starting LBA = 1

当前clean-gap布局约定下：

::

   source disk range = LBA 1, one sector
   destination       = 7000:0000
   physical address  = 0x70000

为什么不直接读到 0x8000
-----------------------

``boot.img`` 使用固定 bounce buffer：

::

   GRUB_BOOT_MACHINE_BUFFER_SEG = 0x7000
   buffer physical range        = 0x70000...

这个缓冲区被设计成 32 KiB，并且不会跨越 64 KiB 边界，符合老式 BIOS 磁盘 DMA 和 EDD 实现常见
的边界约束。

即使当前 SeaBIOS 的 AHCI 后端能够把数据 DMA 到更多地址，GRUB 也要兼容真实旧 BIOS。它先读入
安全缓冲区，再由 CPU 复制到最终目的地。

INT 13h AH=42h 怎样回到 SeaBIOS AHCI
------------------------------------

``boot.img`` 发起：

.. code-block:: asm

   movb $0x42, %ah
   int  $0x13

请求中的：

::

   DL = 0x80
   LBA = 1
   count = 1
   buffer = 0x70000

沿上一批章节已经建立的 BIOS 路径向下传递：

::

   GRUB INT 13h
   → SeaBIOS entry_13
   → handle_13()
   → IDMap[EXTTYPE_HD][0]
   → q35 ICH9 AHCI port 0 drive_s
   → extended_access()
   → CMD_READ, LBA 1, count 1
   → ATA READ DMA(0xc8), slot 0, one PRDT
   → AHCI command table / PRDT
   → HBA DMA 512 bytes 到 0x70000
   → Carry Flag 清零

``LBA=1,count=1`` 仍满足SeaBIOS的28-bit选择条件，所以这里精确使用非queued
``ATA_CMD_READ_DMA(0xc8)``。GRUB此时没有自己的AHCI驱动；最小的 ``boot.img`` 完全依靠
BIOS磁盘服务。

把 diskboot.img 从 0x70000 搬到 0x8000
-------------------------------------

读盘成功后，GRUB 设置：

::

   source DS:SI = 7000:0000
   destination ES:DI = 0000:8000
   CX = 0x100 words

然后执行：

.. code-block:: asm

   cld
   rep movsw

``0x100`` 个 word 等于：

::

   0x100 * 2 = 512 bytes

所以完整的 LBA 1 被复制到：

::

   physical 0x8000..0x81ff

这 512 字节正是 ``core.img`` 的第一个 sector，也就是由 ``diskboot.S`` 生成的
``diskboot.img``。

为什么它既叫 core.img 第一扇区，又叫 diskboot.img
-----------------------------------------------

GRUB 构建 ``core.img`` 时，把多个部分连接在一起：

::

   core.img sector 0       diskboot.img
   core.img sector 1...    startup_raw/decompressor、压缩 core、内建模块等

``diskboot.img`` 自己仍然只有一个扇区。它的任务是读取 ``core.img`` 的剩余扇区。

这就是 GRUB BIOS 启动链中的第二级最小加载器：

::

   boot.img      知道 diskboot.img 的第一个 LBA
   diskboot.img  内含剩余 core.img 的 blocklist
   core          才具备完整 GRUB 内核和模块能力

最后的间接跳转
--------------

``boot.img`` 内有一个安装时固定的 16 位地址字段：

.. code-block:: asm

   kernel_address:
       .word 0x8000

复制结束后执行：

.. code-block:: asm

   jmp *(kernel_address)

当前 ``CS=0``，因此新的执行位置是：

::

   CS:IP = 0000:8000
   physical = 0x8000

这不是 C 函数调用，也没有返回地址。``boot.img`` 的使命到此结束。

本章结束状态
------------

控制流已经走过：

::

   GRUB boot.img at 0000:7c00
   → jump across BPB
   → CLI
   → validate/fix DL
   → far jump to CS=0
   → DS=SS=0, SP=0x2000
   → STI
   → preserve DL=0x80
   → print "GRUB "
   → INT 13h AH=41h EDD probe
   → build 16-byte DAP
   → INT 13h AH=42h
   → read disk LBA 1 to physical 0x70000
   → copy 512 bytes to physical 0x8000
   → jump to 0000:8000

此刻：

* 当前执行者：GRUB 2.14 ``diskboot.img``；
* 当前 CPU：BSP；
* 模式：16位实模式，分页关闭，A20开启；
* ``CS:IP``：``0000:8000``；
* ``DS``、 ``SS``、 ``ES``：0；FLAGS.IF=1、DF=0；
* ``SP``： ``0x1ffe``； ``boot.img`` 从初始 ``0x2000`` 压入的启动 ``DX`` 位于
  ``SS:0x1ffe``，尚未弹出；
* ``DL``：仍表示 BIOS 启动盘 ``0x80``；
* ``SI``：仍指向 ``boot.img`` 的disk address packet，前一字节 ``mode=1``；
* 物理 ``0x8000..0x81ff``：``core.img`` 第一扇区；
* 物理 ``0x70000..0x701ff``：仍保留刚由BIOS读入的同一扇区bounce副本；
* ``core.img`` 剩余扇区：尚未装入内存；
* 保护模式：尚未进入；
* GRUB C 代码：尚未执行；
* Linux bzImage：尚未读取。

关键边界
--------

* LBA 1与连续embedding是本章显式clean-gap布局约定；固定MBR/LBA 2048条件本身只能保证有
  post-MBR gap，不能排除安装器因已知签名而跳过扇区。
* 安装器复制旧MBR的BPB、disk signature和partition table，但不复制旧 ``0x55aa``；签名来自
  新 ``boot.img``。
* ``GRUB_BOOT_MACHINE_STACK_SEG`` 虽名为SEG，却被写入 ``SP``；实际栈顶是物理
  ``0x2000``，不是 ``0x20000``。
* EDD probe成功后第一次AH=42h若仍失败， ``boot.S`` 会退回CHS；固定SeaBIOS成功路径不走该
  分支。
* BIOS先读到 ``0x70000``，CPU再复制到 ``0x8000``； ``jmp *(kernel_address)`` 是不压返回
  地址的间接近跳转， ``CS`` 继续为0。

下一入口
--------

下一章从 ``grub-core/boot/i386/pc/diskboot.S:_start`` 开始，解释第一扇区末尾的blocklist
怎样描述 ``core.img`` 剩余磁盘范围，以及 ``diskboot.img`` 怎样分批读取、搬运并最终跳到
``0000:8200``。

资料
----

* `GNU GRUB 2.14官方发布包目录 <https://ftp.gnu.org/gnu/grub/>`_；
* `GRUB 2.14固定发布提交 <https://github.com/GitMirroring/grub/commit/d38d6a1a9b79427848976f53d474392cd29c2a71>`_；
* `GRUB固定提交：boot.img入口、EDD与复制 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/boot/i386/pc/boot.S#L119-L455>`_；
* `GRUB固定提交：boot.img字段偏移 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/include/grub/i386/pc/boot.h#L24-L66>`_；
* `GRUB固定提交：安装器patch boot.img与blocklist <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/util/setup.c#L100-L206>`_；
* `GRUB固定提交：MBR保存范围与drive workaround <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/util/setup.c#L373-L424>`_；
* `GRUB固定提交：MSDOS embedding sector选择 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/partmap/msdos.c#L235-L412>`_；
* `SeaBIOS固定提交：EDD probe/read实现 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/disk.c#L407-L435>`_。
