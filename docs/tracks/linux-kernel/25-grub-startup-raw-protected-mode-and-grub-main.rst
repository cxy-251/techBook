第二十五章：GRUB startup_raw 怎样进入保护模式并调用 grub_main？
============================================================

上一章结束时，``diskboot.img`` 已经根据 blocklist 把 ``core.img`` 的剩余内容装入低端内存，
并以如下状态进入第二扇区：

::

   CS:IP = 0000:8200
   DL    = 0x80
   CPU   = 16 位实模式
   paging = off

物理 ``0x8200`` 开始的代码来自
``grub-core/boot/i386/pc/startup_raw.S``。它不是完整 GRUB 内核，而是一个早期解压器和模式切换
入口。它要完成四件事：

#. 整理实模式执行环境并保存启动盘信息；
#. 建立 GDT，进入 32 位保护模式；
#. 检查 A20，并对嵌入映像执行可选 Reed–Solomon 恢复；
#. 把压缩 GRUB core 解压到 1 MiB，再搬到链接地址并调用 ``grub_main()``。

core.img 在内存中的组成
----------------------

当前低端内存中的 ``core.img`` 可以概括为：

::

   0x8000..0x81ff   diskboot.img
   0x8200...         startup_raw / real-mode transitions / decompressor
   ...               compressed GRUB kernel image
   ...               built-in modules and metadata
   ...               optional Reed–Solomon redundancy

``diskboot.img`` 已经完成磁盘读取。接下来直到 GRUB 自己的磁盘模块初始化前，主要动作都发生在
内存中。

为什么入口先执行一次远跳转
--------------------------

``startup_raw.S`` 的第一条有效流程是：

.. code-block:: asm

   _start:
   base:
       ljmp $0, $ABS(codestart)

它的注释写明，要保证主体代码被视为加载在：

::

   0000:8200

虽然上一章已经明确跳到 ``CS=0``，这里仍再次远跳转，目的是让同一个映像在不同进入方式下都把
``CS`` 规范化，并跳过开头一小段专用数据字段。

这些字段不是普通指令
--------------------

``startup_raw`` 开头保留了一组由 ``grub-mkimage`` 或 ``grub-setup`` 填写的字段：

::

   offset  meaning
   0x08    compressed_size
   0x0c    uncompressed_size
   0x10    reed_solomon_redundancy
   0x14    no_reed_solomon_length
   0x18    encoded boot device area

因此入口不能简单地从 ``0x8200`` 顺序执行全部字节。第一条远跳转跨过这些数据，进入真正的
``codestart``。

GRUB i386-pc 默认使用 LZMA
-------------------------

GRUB 2.14 的 ``i386-pc`` image target 在 ``util/mkimage.c`` 中声明：

::

   flags               = PLATFORM_FLAGS_DECOMPRESSORS
   link_addr           = 0x9000
   default_compression = LZMA

因此当前固定路径中的 ``core.img`` 不是把完整 GRUB 核心原样塞进低端 embedding area。
它包含一个较小的解压器，以及经过 LZMA 压缩的主体映像。

这样做有两个直接目的：

* 减少 MBR 与第一分区之间所需的 embedding sectors；
* 让更完整的 GRUB 内核和内建模块能够装入有限的 BIOS 启动空间。

重新建立实模式段寄存器和栈
--------------------------

进入 ``codestart`` 后：

.. code-block:: asm

   cli
   xorw %ax, %ax
   movw %ax, %ds
   movw %ax, %ss
   movw %ax, %es
   movl $GRUB_MEMORY_MACHINE_REAL_STACK, %ebp
   movl %ebp, %esp
   sti

宏值为：

::

   GRUB_MEMORY_MACHINE_REAL_STACK = 0x2000 - 0x10 = 0x1ff0

所以新的实模式栈顶位于物理地址 ``0x1ff0``。

这一步不再依赖 ``boot.img`` 和 ``diskboot.img`` 沿用的旧栈。GRUB 从这里开始建立可供模式切换
例程反复使用的固定栈位置。

为什么 ESP 可以在 16 位代码中使用
--------------------------------

代码虽然处于 ``.code16``，仍可以通过 operand-size prefix 使用 32 位寄存器。写 ``ESP`` 的好处是
清除其高 16 位，避免旧环境遗留的高位与 ``SP`` 拼成错误地址。

当前 ``SS=0``，因此：

::

   stack physical address = 0x0000 * 16 + 0x1ff0 = 0x1ff0

保存 DL 时为什么连同三个 0xff 字节一起编码
---------------------------------------

``startup_raw`` 的特殊数据区是：

.. code-block:: asm

   boot_dev:
       .byte 0xff, 0xff, 0xff
   boot_drive:
       .byte 0x00

代码执行：

.. code-block:: asm

   movb %dl, boot_drive

当前 ``DL=0x80``，四个连续字节按 little-endian 解释为：

::

   bytes = ff ff ff 80
   value = 0x80ffffff

GRUB 把这个 32 位值作为早期 ``grub_boot_device``：

::

   bits 31:24   BIOS drive = 0x80
   bits 23:16   DOS partition = 0xff, unknown/not hardcoded
   bits 15:8    BSD partition = 0xff, unknown/not hardcoded
   bits 7:0     reserved/unknown = 0xff

后面的 ``grub_machine_get_bootlocation()`` 会从最高字节恢复 ``boot_drive``，并把 ``0x80`` 解释为
第一块 BIOS hard disk，也就是 ``hd0``。

为什么先复位 BIOS 磁盘系统
--------------------------

保存 ``DL`` 前，代码已经通过 ``xorw %ax,%ax`` 把 ``AH`` 清零。因此：

.. code-block:: asm

   int $0x13

实际调用的是：

::

   INT 13h AH=00h
   reset disk system

这一步清理 BIOS 磁盘服务可能残留的错误状态。它没有重新探测 AHCI，也不会丢失 SeaBIOS 已经建立的
``IDMap``。对当前 q35 路径，它最终仍指向 AHCI port 0。

calll real_to_prot 为什么使用 32 位返回地址
-----------------------------------------

接下来执行：

.. code-block:: asm

   calll real_to_prot

这里仍是 16 位模式，但 ``calll`` 明确压入 32 位返回地址。模式转换后，代码会切换到 32 位栈，
需要保留完整的线性返回位置。

``real_to_prot`` 来自被直接包含进映像的 ``grub-core/kern/i386/realmode.S``。

GRUB 建立了怎样的 GDT
--------------------

早期 GDT 包含五项：

::

   selector 0x00   null descriptor
   selector 0x08   32-bit code, base 0, 4 GiB limit
   selector 0x10   32-bit data, base 0, 4 GiB limit
   selector 0x18   16-bit pseudo-real code
   selector 0x20   16-bit pseudo-real data

``0x08`` 与 ``0x10`` 建立平坦 32 位地址空间：

::

   logical offset == linear address

后两项不是当前进入保护模式所必需，却为以后临时返回 BIOS 实模式服务准备了过渡 segment。
GRUB core 运行期间仍会调用 SeaBIOS ``INT 10h``、``INT 13h``、``INT 15h`` 等接口，所以必须保留
双向模式切换能力。

设置 CR0.PE 之后为什么还要远跳转
--------------------------------

``real_to_prot`` 执行：

.. code-block:: asm

   cli
   lgdt gdtdesc
   movl %cr0, %eax
   orl  $CR0_PE, %eax
   movl %eax, %cr0
   ljmpl $0x08, $protcseg

设置 ``CR0.PE=1`` 只改变处理器模式标志，旧 ``CS`` 的隐藏 descriptor cache 仍然没有装入新的
32 位代码段属性。

远跳转完成：

* ``CS=0x08``；
* 重新从 GDT 载入 base、limit 和 32-bit default operand size；
* 清空旧预取路径；
* 从 ``protcseg`` 继续执行 32 位指令。

随后：

.. code-block:: asm

   DS = ES = FS = GS = SS = 0x10

GRUB 至此正式进入 32 位保护模式。

保护模式栈位于哪里
------------------

GRUB 的低端保留区定义为：

::

   scratch base       = 0x68000
   scratch size       = 0x09000
   protected stack size = 0x0f000

栈顶计算：

::

   0x68000 + 0x09000 + 0x0f000 - 0x10
   = 0x7fff0

所以：

::

   ESP = EBP = 0x0007fff0

模式切换代码把实模式栈顶的返回地址搬到新栈，再执行 ``ret``，返回
``startup_raw`` 中 ``calll real_to_prot`` 的下一条 32 位指令。

IDT 为什么暂时是空的
--------------------

切换过程中，GRUB：

* 用 ``SIDT`` 保存 BIOS 实模式 IDT 描述符；
* 加载一个 limit 为 0 的保护模式 IDT；
* 保持中断关闭。

此刻 GRUB 还没有建立自己的异常处理体系。如果发生保护模式中断或异常，空 IDT 会造成严重故障。
所以这一小段代码必须非常受控，不能随意 ``STI``。

A20 已经开过，为什么 GRUB 仍重新检查
-----------------------------------

SeaBIOS 第二章已经打开 A20，GRUB 不直接信任前一个执行者的状态。

``grub_gate_a20`` 比较：

::

   physical 0x00008000
   physical 0x00108000

如果 A20 关闭，后一个地址会回绕到前一个地址，两处访问会互相影响。代码通过临时修改字节并再次
读取，判断两地址是否真正独立。

当前 SeaBIOS 已打开 A20，所以第一次测试通常直接成功。

如果失败，GRUB 会依次尝试：

#. ``INT 15h AX=2401h`` BIOS A20 service；
#. system control port A ``0x92``；
#. i8042 keyboard controller ``0x64/0x60``；
#. 全部失败则重新循环。

这里再次体现了启动代码的原则：前一阶段建立的状态可以利用，关键条件仍要自行验证。

为什么保护模式代码还会临时回实模式
----------------------------------

A20 的第一种备用方法需要调用 BIOS ``INT 15h``。保护模式下不能直接执行传统实模式 IVT 中断。

因此 ``grub_gate_a20`` 可以调用：

::

   prot_to_real()
   → INT 15h AX=2401h
   → real_to_prot()

之前 GDT 中预留的 ``0x18``、``0x20`` 伪实模式 descriptors，以及保存的 real-mode IDT，正是为
这种往返服务。

Reed–Solomon 在启动阶段修复什么
-------------------------------

进入 32 位模式并确认 A20 后，``startup_raw`` 读取：

::

   compressed_size
   reed_solomon_redundancy
   no_reed_solomon_length

然后调用：

.. code-block:: c

   grub_reed_solomon_recover(...)

GRUB 安装器可以在 embedding area 有富余空间时，为 ``core.img`` 的主体添加 Reed–Solomon
冗余。它用于恢复少量连续 sector 损坏或读出错误。

并不是整个 ``core.img`` 都参与编码。``diskboot.img`` 和必须先执行的解码代码位于保护区之外；
只有在恢复函数已经可以运行后，其余压缩数据才有机会被修复。

当前 QEMU 虚拟磁盘一般不会自然产生物理坏扇区，这条路径仍然是固定源码的一部分。冗余长度为 0
时，恢复函数不会凭空修改映像。

LZMA 解压的输入和输出在哪里
---------------------------

默认 ``ENABLE_LZMA`` 路径设置：

::

   destination EDI = 0x00100000
   output size ECX = uncompressed_size
   input ESI       = decompressor_end

然后调用内嵌的 ``_LzmaDecodeA``。

这意味着：

* 低端 ``0x8200...`` 保存解压器和压缩输入；
* 1 MiB 处 ``0x100000...`` 接收未压缩 GRUB 核心；
* A20 必须开启，否则 ``0x100000`` 会回绕覆盖低端内存。

解压阶段仍然没有开启分页。``0x100000`` 是直接的物理地址，也是平坦保护模式下的线性地址。

为什么解压到 0x100000 后还要复制到 0x9000
----------------------------------------

LZMA 输出的第一条代码来自 ``grub-core/kern/i386/pc/startup.S``。``startup_raw`` 把
``ESI=0x100000``，然后直接跳到该地址。

``startup.S`` 先保存三个重要入口：

::

   ECX = real_to_prot address
   EDI = prot_to_real address
   EAX = saved real-mode IDT descriptor address

这些地址属于仍在低端的 decompressor/transition code，完整 GRUB core 后面需要它们继续调用 BIOS。

接着它执行：

::

   source ESI      = 0x100000
   destination EDI = _start = 0x9000
   length          = _edata - _start
   rep movsb

``GRUB_KERNEL_I386_PC_LINK_ADDR`` 是 ``0x9000``。完整 GRUB 核心被链接成在该地址运行，所以必须
把需要按固定地址执行的主体复制回 ``0x9000``。

``0x100000`` 不是最终代码地址，它还是后续内建模块区域的基准。GRUB 会把解压输出中的模块保留在
高端位置，同时让核心代码在低端链接地址执行。

跳到 cont 为什么不是普通 ret
----------------------------

代码复制完后，当前 CPU 仍在执行 1 MiB 那份临时副本。它执行：

.. code-block:: asm

   movl $cont, %esi
   jmp  *%esi

``cont`` 是按链接地址 ``0x9000`` 计算的符号。这个跳转把取指位置切换到刚复制完成的低端正式副本。

从此：

* ``0x9000`` 一带是 GRUB core 正式代码；
* ``0x100000`` 一带主要保留模块和高端数据；
* 临时解压副本不再作为主执行代码。

清零 BSS
--------

进入低端正式副本后，GRUB 计算：

::

   BSS length = END_SYMBOL - BSS_START_SYMBOL

然后：

.. code-block:: asm

   xor %eax, %eax
   rep stosb

BSS 在磁盘映像中不占实际初始化数据，必须在运行时清零。后续 C 代码依赖全局未初始化变量初值为 0。

把启动设备写入 grub_boot_device
--------------------------------

``startup_raw`` 在跳入解压后核心前，把编码后的启动设备放进 ``EDX``：

::

   EDX = 0x80ffffff

``startup.S`` 执行：

.. code-block:: asm

   movl %edx, grub_boot_device

这一步把最初由 SeaBIOS 传入的 ``DL=0x80``，跨越：

::

   boot.img
   → diskboot.img
   → startup_raw
   → LZMA decompressor
   → startup.S

一直保存到 GRUB C 世界。

调用 grub_main 是新的执行层次
-----------------------------

最后：

.. code-block:: asm

   call grub_main

这不是 Linux 的 ``start_kernel()``，也不是 GRUB 菜单循环本身。它是 GRUB 核心通用初始化入口。

进入 ``grub_main()`` 时：

* CPU 已处于 32 位保护模式；
* flat code/data segments 已经建立；
* 分页仍关闭；
* 正式 GRUB core 已位于链接地址 ``0x9000``；
* 模块区位于 1 MiB 附近及其后；
* BSS 已清零；
* ``grub_boot_device`` 已保存为 ``0x80ffffff``；
* BIOS 模式切换入口仍可供 GRUB 调用；
* SeaBIOS ``INT 13h`` 仍然是早期磁盘访问后端。

GRUB 到这里才从几个极小汇编加载器，变成能够运行较大 C 代码、初始化内存管理、终端、模块、
磁盘抽象和配置文件解析的 bootloader core。

第二十五章结束时的机器状态
--------------------------

控制流已经走过：

::

   GRUB startup_raw at 0000:8200
   → far jump across special fields
   → CLI
   → DS=SS=ES=0
   → real-mode stack = 0x1ff0
   → save DL into encoded boot device
   → INT 13h AH=00h disk reset
   → real_to_prot()
   → LGDT
   → CR0.PE = 1
   → far jump CS=0x08
   → DS/ES/FS/GS/SS=0x10
   → protected stack = 0x7fff0
   → save BIOS IDT / load empty protected IDT
   → verify A20
   → optional Reed–Solomon recovery
   → LZMA decompress to 0x100000
   → jump to decompressed startup.S
   → copy core code to link address 0x9000
   → jump to low-memory formal copy
   → clear BSS
   → grub_boot_device = 0x80ffffff
   → call grub_main()

此刻：

* 当前执行者：GNU GRUB 2.14 ``grub_main()``；
* 当前 CPU：BSP；
* 模式：32 位保护模式；
* ``CS``：flat 32-bit code selector；
* 数据段：flat 32-bit data selector；
* 分页：关闭；
* A20：开启并已由 GRUB 验证；
* GRUB core 正式代码：位于链接地址 ``0x9000``；
* GRUB 内建模块：位于 1 MiB 附近的模块区域；
* GRUB BSS：已清零；
* ``grub_boot_device``：``0x80ffffff``，启动盘为 BIOS ``0x80``；
* BIOS 调用桥：已经保存，可在保护模式与实模式之间往返；
* ``grub.cfg``：尚未读取；
* GRUB 菜单：尚未建立；
* Linux bzImage：尚未读取；
* Linux：尚未取得控制权。

下一章从 ``grub_main()`` 开始，追踪 GRUB 怎样初始化机器、控制台、内存区域和内建模块，怎样从
``grub_boot_device`` 推导 ``hd0``，以及它在读取 ``grub.cfg`` 之前建立了哪些基础设施。

资料
----

* `GRUB 2.14 grub-core/boot/i386/pc/startup_raw.S <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/boot/i386/pc/startup_raw.S>`_；
* `GRUB 2.14 grub-core/kern/i386/realmode.S <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/i386/realmode.S>`_；
* `GRUB 2.14 grub-core/kern/i386/pc/startup.S <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/i386/pc/startup.S>`_；
* `GRUB 2.14 grub-core/kern/i386/pc/init.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/i386/pc/init.c>`_；
* `GRUB 2.14 include/grub/i386/memory_raw.h <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/include/grub/i386/memory_raw.h>`_；
* `GRUB 2.14 include/grub/i386/pc/memory.h <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/include/grub/i386/pc/memory.h>`_；
* `GRUB 2.14 include/grub/offsets.h <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/include/grub/offsets.h>`_；
* `GRUB 2.14 util/mkimage.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/util/mkimage.c>`_；
* `GNU GRUB 2.14 official release archive <https://ftp.gnu.org/gnu/grub/grub-2.14.tar.xz>`_。
