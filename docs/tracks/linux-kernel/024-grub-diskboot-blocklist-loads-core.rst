第二十四章：GRUB diskboot.img 怎样按 blocklist 读完 core.img？
===========================================================

上一章采用clean-gap布局约定；在该约定下， ``boot.img`` 已经把启动盘LBA 1的512字节复制到
物理地址 ``0x8000``，随后直接跳到：

::

   CS:IP = 0000:8000

这 512 字节是 ``core.img`` 的第一个扇区，也是由
``grub-core/boot/i386/pc/diskboot.S`` 生成的 ``diskboot.img``。

它仍然是 16 位实模式代码，也仍然依靠 SeaBIOS ``INT 13h`` 读盘。它比 ``boot.img`` 多知道的
关键内容，是安装器写进本扇区末尾的 ``blocklist``。

为什么 core.img 还需要一个扇区级加载器
------------------------------------

``boot.img`` 只有 512 字节，而且 LBA 0 还必须容纳分区表。它只保存一个 64 位地址：

::

   core.img 第一个扇区的 LBA

单凭这个地址，``boot.img`` 不知道 ``core.img`` 有多大，也不知道它是否被分成多个不连续磁盘
范围。

因此 ``core.img`` 的第一个 sector 自己承担第二级加载器角色：

::

   boot.img
       只读 core.img sector 0

   diskboot.img = core.img sector 0
       读取 blocklist
       读入 core.img sector 1..end

   startup_raw + compressed core
       切换模式、修复数据、解压并进入 GRUB 核心

这里依然没有文件系统解析。``diskboot.img`` 读取的不是 ``/boot/grub/i386-pc/core.img`` 这个
文件名，而是安装时已经记录好的物理 sector 范围。

入口为什么是 0000:8000
-----------------------

``diskboot.S`` 明确假设：

.. code-block:: asm

   _start is loaded at 0x8000
   CS:IP = 0:0x8000

上一章中的宏关系是：

::

   GRUB_BOOT_I386_PC_KERNEL_SEG = 0x800
   GRUB_BOOT_MACHINE_KERNEL_ADDR = 0x800 << 4 = 0x8000

所以 ``boot.img`` 把第一扇区复制到 ``0x8000`` 后，不需要额外重定位。

``diskboot.img`` 还继承了 ``boot.img`` 建立的环境：

* ``CS=0``；
* ``DS=0``；
* ``SS=0``、 ``SP=0x1ffe``，栈顶word是 ``boot.img`` 保存的启动 ``DX``；
* ``ES=0``、FLAGS.IF=1、DF=0、A20开启；
* ``SI`` 仍指向 ``boot.img`` 创建的 disk address packet；
* ``SI-1`` 的mode byte为1，表示上一章选择了EDD/LBA；
* ``DL`` 仍是启动盘号 ``0x80``。

源码注释直接说明它继续使用 ``boot.img`` 的栈，并依赖若干寄存器已经处于预期状态。

为什么一开始又 push DX
----------------------

入口首先执行：

.. code-block:: asm

   pushw %dx

``DL`` 是 BIOS 磁盘号。接下来每一次 ``INT 13h`` 都可能修改通用寄存器，所以
``diskboot.img`` 再次把它保存在栈上。

然后屏幕上继续输出：

::

   loading

每完成一批读取，它还会输出一个点。典型启动提示因此逐渐形成：

::

   GRUB loading....

这里的前半段 ``GRUB `` 来自 ``boot.img``，后半段 ``loading...`` 来自 ``diskboot.img``。

blocklist 放在扇区末尾
---------------------

``diskboot.img`` 本身必须容纳：

* 读盘代码；
* 错误处理；
* 输出字符串；
* 一组安装器可修改的 blocklist entries。

每个 entry 固定 12 字节：

::

   offset  size  meaning
   0x00    8     start LBA
   0x08    2     sector count
   0x0a    2     destination segment

对应 C 结构是：

.. code-block:: c

   struct grub_pc_bios_boot_blocklist
   {
       grub_uint64_t start;
       grub_uint16_t len;
       grub_uint16_t segment;
   } __packed;

``diskboot.S`` 把第一项放在：

::

   0x200 - 12 = 0x1f4

也就是当前 512 字节扇区的最后 12 字节。

如果需要多个 entry，它们从高地址向低地址增长：

::

   ...
   terminator
   block 3
   block 2
   block 1  ← firstlist at 0x1f4

读取完当前 entry 后，代码执行：

.. code-block:: asm

   subw $12, %di

移动到前一个 entry。``len=0`` 的项是结束标志。

安装器怎样生成 blocklist
------------------------

``grub-setup`` 在安装阶段已经知道 embedding area 中每个 ``core.img`` sector 的真实位置。
它执行 ``save_blocklists()``，把相邻 sector 合并成一项：

::

   start   第一扇区 LBA
   len     连续扇区数量
   segment 读入内存后的目的 segment

如果下一段磁盘 sector 正好紧接上一段：

::

   previous.start + previous.len == next.start

安装器只增加上一项的 ``len``，不会浪费一个新的 12 字节 entry。

当前clean-gap布局约定中，安装器获得连续的LBA 1..N。 ``save_blocklists()`` 第一次收到LBA 1
时只把它保存为 ``first_sector``，因为该扇区已由 ``boot.img`` 单独读取；它从第二次callback
才为剩余内容建立entry：

::

   LBA 1      diskboot.img，已由 boot.img 读取
   LBA 2..N   core.img 剩余部分

所以当前约定精确产生一个有效entry，而不是仅仅“通常”如此：

::

   start   = 2
   len     = N - 1
   segment = 0x0820

``save_blocklists()`` 把后续相邻扇区合并进这一项；安装器随后在下一个更低的12字节槽写入全零
terminator。 ``N`` 是安装器实际取得并写入的总扇区数，可能包含为Reed–Solomon冗余扩大的
padding；固定源码版本与模块集合并不足以在没有构建产物时给出它的具体数值。

为什么目的 segment 从 0x0820 开始
--------------------------------

``diskboot.img`` 本身占据：

::

   0000:8000..0000:81ff

下一扇区应紧接在物理 ``0x8200``。实模式 segment 表示为：

::

   0x0820 * 16 = 0x8200

安装器初始化第一个目的 segment 时使用：

::

   GRUB_BOOT_I386_PC_KERNEL_SEG + 0x20
   = 0x0800 + 0x0020
   = 0x0820

其中 ``0x20`` 个 paragraph 正好等于一个 512 字节 sector：

::

   0x20 * 16 = 0x200 = 512

blocklist 因此同时描述磁盘位置和内存拼接位置。

firstlist 的第一项怎样进入循环
-----------------------------

``diskboot.img`` 设置：

.. code-block:: asm

   movw $firstlist, %di
   movl (%di), %ebp

``DI`` 指向第一项。``EBP`` 暂存该项的低 32 位起始 sector，供后续启动代码保留这一安装信息。

主循环首先检查：

.. code-block:: asm

   cmpw $0, 8(%di)
   je bootit

也就是检查当前 entry 的 ``len``。

* ``len != 0``：还有 sector 要读；
* ``len == 0``：所有 blocklist 已完成，进入下一阶段。

当前第一项的 ``len`` 非零，因此进入读盘路径。

继续沿用 boot.img 的 LBA/CHS 模式判断
------------------------------------

``SI`` 仍指向上一章构造的 disk address packet 附近。``boot.img`` 在它前一个字节保存了模式：

::

   0   使用 CHS
   非0 使用 EDD/LBA

``diskboot.img`` 检查：

.. code-block:: asm

   cmpb $0, -1(%si)
   je chs_mode

SeaBIOS 已通过 EDD 探测，所以当前路径继续使用 LBA。

为什么一次最多读取 0x7f 个 sector
--------------------------------

对一个 blocklist entry，代码先把单次最大读取量设成：

::

   0x7f sectors = 127 sectors

理由写在源码中：Phoenix EDD实现存在单次数量限制。即使blocklist的 ``len`` 更大，GRUB也会
把它拆成多批。对当前SeaBIOS还有一个可验证的结果： ``127 * 512 = 65024``，没有越过
``process_op()`` 拒绝的 ``>64 KiB`` 单次传输边界。

每一批执行：

::

   count = min(remaining_len, 0x7f)

然后立即更新内存中的 blocklist entry：

::

   remaining_len -= count
   start_lba     += count

这意味着 entry 在加载过程中本身就是可变游标，而不是只读配置数据。

重新填写 Disk Address Packet
----------------------------

LBA 模式下，每一批把 DAP 更新为：

::

   packet size  = 0x10
   sector count = 当前批数量
   buffer       = 7000:0000
   start LBA    = 当前 entry.start

随后调用：

.. code-block:: asm

   AH = 0x42
   DL = 0x80
   DS:SI = DAP
   INT 13h

SeaBIOS 再次沿 ``IDMap[HD][0]`` 找到 q35 AHCI port 0，把这一批 sector DMA 到物理
``0x70000``。

当前clean-gap entry全部位于LBA 2到LBA 2047之间，且每批少于256扇区；
``sata_prep_readwrite()`` 因而每批都选择非queued ``ATA_CMD_READ_DMA(0xc8)``，将当前LBA、
count和 ``0x70000`` PRDT写入slot 0。若blocklist指向 ``lba+count >= 2^28`` 的条件布局，
SeaBIOS才会改用 ``READ DMA EXT``；这不是当前数值路径。

为什么每一批仍先落到 0x70000
----------------------------

和 ``boot.img`` 一样，``diskboot.img`` 不要求 BIOS 直接写最终连续地址，而是一直使用固定
bounce buffer：

::

   7000:0000
   physical 0x70000

这样可以统一规避：

* 64 KiB segment 边界；
* 老 BIOS 的 DMA 地址限制；
* 单次跨 segment 的复杂性；
* LBA 与 CHS 两条路径的不同缓冲规则。

读盘成功后，再由 CPU 把数据复制到 blocklist 指定的目的 segment。

怎样计算下一批目的地址
----------------------

当前批读取 ``AX`` 个 sector。每个 sector 是 512 字节，也就是 32 个 paragraph：

::

   512 / 16 = 32 = 0x20

代码执行：

.. code-block:: asm

   shlw $5, %ax
   addw %ax, 10(%di)

左移 5 位等于乘以 32，所以目的 segment 增量是：

::

   sector_count * 0x20

例如第一批读取 16 个 sector：

::

   destination start = 0x0820
   increment         = 16 * 0x20 = 0x0200
   next segment      = 0x0a20

物理地址增加：

::

   0x0200 * 16 = 0x2000 = 8192 bytes
   16 * 512             = 8192 bytes

两种计算完全一致。

从 bounce buffer 复制到目的 segment
----------------------------------

读盘完成后：

::

   source      DS:SI = 7000:0000
   destination ES:DI = entry.segment:0000

复制长度从 sector 数换算成 word 数：

.. code-block:: asm

   shlw $3, %ax
   movw %ax, %cx
   rep movsw

因为：

::

   one sector = 512 bytes = 256 words = 2^8 words

这里进入复制代码前，``AX`` 已先乘过 32 用来更新 segment；再左移 3 位，总乘数为：

::

   2^5 * 2^3 = 2^8 = 256 words per sector

所以 ``REP MOVSW`` 精确复制当前批的所有字节。

为什么 blocklist 可以描述不连续 core.img
--------------------------------------

如果 ``core.img`` 在磁盘上被分成多段，安装器会生成多项：

::

   entry A: LBA 100, len 8,  segment 0x0820
   entry B: LBA 400, len 12, segment 0x0920
   entry C: LBA 900, len 5,  segment 0x0aa0

``diskboot.img`` 并不关心这些 sector 是否属于哪个文件系统。它只逐项：

::

   读取磁盘范围
   → 复制到指定内存 segment
   → entry 完成后 DI -= 12
   → 读取下一项

最终内存中的 ``core.img`` 仍然连续。

不过 GRUB 安装器优先使用 embedding area。把 ``core.img`` 留在普通文件系统中再依赖 blocklist
是不可靠的，因为文件移动或碎片整理会让物理 sector 改变。源码也明确警告这种安装方式不可靠，
默认不愿继续。

当前布局约定为什么只有一个 entry
---------------------------------

本批沿用的显式约定是：

::

   MBR partition table
   first partition starts at LBA 2048
   core.img embedded contiguously from LBA 1

所以 ``grub-setup`` 获得连续embedding sectors，并在 ``save_blocklists()`` 中不断合并。
仅有“第一分区LBA 2048”而没有clean-gap约定时，MSDOS embed实现仍可能避开已知签名，不能推出
这一项式结果。

结果相当于：

::

   entry.start   = 2
   entry.len     = N - 1
   entry.segment = 0x0820
   terminator.len = 0

这种布局不依赖文件系统blocklist，也最适合逐地址追踪； ``N`` 的确切值仍留给实际构建产物，
正文不编造 ``core.img`` 大小。

加载范围为什么不能无限增长
--------------------------

安装器会限制 BIOS 平台 ``core.img`` 的 embedding 大小。相关计算以：

::

   0x78000 - GRUB_KERNEL_I386_PC_LINK_ADDR

为低端装载空间上限之一。

``setup.c`` 把 ``maxsec`` 截到这个差值除以512；embedding provider返回的 ``nsec`` 若小于
实际 ``core_sectors`` 就直接报错。这里能从源码确定的是安装器的硬上限与失败门，不能把没有
保存的构建结果扩写成某个精确末地址，也不能仅凭该表达式臆测每一块早期内存的用途。

加载完成后怎样找到下一入口
--------------------------

当前 entry 的 ``remaining_len`` 归零后，代码移动到前一项。遇到 ``len=0`` terminator 时进入：

.. code-block:: asm

   bootit:
       print "\r\n"
       popw %dx
       ljmp $0, $(GRUB_BOOT_MACHINE_KERNEL_ADDR + 0x200)

地址计算是：

::

   GRUB_BOOT_MACHINE_KERNEL_ADDR = 0x8000
   0x8000 + 0x0200              = 0x8200

远跳转后的状态：

::

   CS:IP = 0000:8200
   DL    = 恢复后的 0x80

``0x8200`` 正是 ``core.img`` 第二扇区的开头，也就是 ``startup_raw.S`` 的入口。

为什么这里用远跳转
------------------

``ljmp $0, $0x8200`` 同时明确重新装载 ``CS``，防止任何 BIOS 调用或兼容路径留下非零代码段。

下一阶段的汇编使用绝对低端地址，并很快建立自己的 GDT。固定 ``CS=0`` 可以消除
``0000:8200`` 与其他等价 segment:offset 表示之间的歧义。

本章结束状态
------------

控制流已经走过：

::

   GRUB diskboot.img at 0000:8000
   → preserve DL
   → print "loading"
   → DI = first blocklist entry
   → read start/len/destination segment
   → choose LBA mode
   → split request into <= 0x7f-sector batches
   → INT 13h AH=42h to 0x70000
   → ATA READ DMA(0xc8) on fixed clean-gap LBAs
   → copy batch to entry.segment:0
   → advance LBA, len and destination segment
   → move backward through blocklist entries
   → reach zero-length terminator
   → restore DL=0x80
   → far jump to 0000:8200

此刻：

* 当前执行者：GRUB 2.14 ``startup_raw``；
* 当前 CPU：BSP；
* 模式：16位实模式，分页关闭，A20仍开启；FLAGS.IF=1、DF=0；
* ``CS:IP``：``0000:8200``；
* ``DL``：``0x80``；
* ``SS``：0， ``SP=0x1ffe``； ``boot.img`` 保存的那个启动 ``DX`` 仍在栈顶；
* ``DS``：0； ``ES`` 保留最后一批复制使用的目的segment，下一入口不会依赖它；
* ``EBP``：第一项起始LBA的低32位，当前clean-gap约定为2；
* blocklist有效项：已被当作游标原地修改， ``len=0``、start和segment已推进到末端；
* ``DI``：指向其下方的zero-length terminator；
* ``core.img`` 的N个嵌入扇区：已经全部装入从 ``0x8000`` 开始的低端内存；
* ``diskboot.img``：位于 ``0x8000..0x81ff``；
* ``startup_raw``：从 ``0x8200`` 开始；
* 压缩 GRUB core 与内建模块：已经位于后续低端地址；
* A20：仍开启，下一阶段会自行验证而非盲信继承值；
* 保护模式：尚未由 GRUB 开启；
* 解压后的 GRUB core：尚未写到 ``0x100000``；
* ``grub_main()``：尚未调用；
* Linux bzImage：尚未读取。

关键边界
--------

* ``boot.img`` 只知道 ``core.img`` 第一扇区； ``diskboot.img`` 的blocklist只描述余下扇区，
  第一项的目标因此从 ``0x0820`` 而不是 ``0x0800`` 开始。
* ``save_blocklists()`` 把第一callback单独保存为 ``first_sector``；连续的余下扇区才合并成当前
  ``start=2,len=N-1`` 的单项。LBA 1和单项结果属于显式clean-gap约定。
* 每批先减少len并增加start，再调用BIOS；失败时内存entry已经前移。当前成功路径每批至多127
  扇区，既满足GRUB的Phoenix兼容限制，也不超过SeaBIOS的64 KiB边界。
* 当前低LBA批次精确使用AHCI ``READ DMA(0xc8)``。BIOS只写 ``0x70000`` bounce buffer，GRUB
  再用 ``rep movsw`` 写最终segment。
* ``diskboot.img`` 的read/geometry error只打印错误并自旋，不执行INT 18h；不能套用
  ``boot.img`` 的失败恢复链。
* ``ljmp $0,$0x8200`` 不建立返回地址；此时blocklist已经被原地消耗为游标终态。

下一入口
--------

下一章从 ``startup_raw.S:_start`` 的 ``ljmp $0,$ABS(codestart)`` 开始，追踪它怎样重建栈、
保存 ``DL``、复位BIOS磁盘系统、进入32位保护模式，随后验证A20并处理压缩core。第025章既有
开头对保存 ``DL`` 与 ``INT 13h AH=0`` 的先后描述仍待下一批按源码修正。

资料
----

* `GRUB固定提交：diskboot blocklist循环 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/boot/i386/pc/diskboot.S#L36-L301>`_；
* `GRUB固定提交：blocklist槽与默认值 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/boot/i386/pc/diskboot.S#L355-L378>`_；
* `GRUB固定提交：kernel segment <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/include/grub/offsets.h#L38-L41>`_；
* `GRUB固定提交：blocklist结构 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/include/grub/offsets.h#L159-L165>`_；
* `GRUB固定提交：安装器合并blocklist <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/util/setup.c#L135-L206>`_；
* `GRUB固定提交：embedding大小、terminator与写盘 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/util/setup.c#L505-L648>`_；
* `GRUB固定提交：MSDOS embedding连续候选与签名避让 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/partmap/msdos.c#L330-L394>`_；
* `SeaBIOS固定提交：EDD与64 KiB disk_op边界 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/block.c#L618-L638>`_；
* `SeaBIOS固定提交：AHCI read命令选择 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/ahci.c#L27-L61>`_。
