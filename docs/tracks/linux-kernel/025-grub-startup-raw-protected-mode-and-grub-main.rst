第二十五章：GRUB startup_raw怎样进入保护模式并调用grub_main？
=============================================================

第024章把 ``core.img`` 的N个嵌入扇区连续装入从物理 ``0x8000`` 开始的低端内存，
最后以 ``ljmp $0,$0x8200`` 把BSP交给第二扇区。此刻处理器仍在16位实模式、分页关闭，
``CS:IP=0000:8200``、 ``DL=0x80``、 ``DS=SS=0``、 ``SP=0x1ffe``、IF=1、DF=0；
A20虽然已经由SeaBIOS开启，但还没有被GRUB验证。保护模式、解压后的GRUB core、堆和模块
注册均不存在。

本章只沿固定GRUB 2.14 i386-pc入口前进到 ``startup.S`` 执行 ``call grub_main``。这一段
不再读盘：它重建自己的栈和段环境，保存启动盘号，经固定GDT进入32位保护模式，验证A20，
在内存中完成Reed–Solomon恢复与LZMA解压，再把正式core放到链接地址 ``0x9000``。

入口远跳为什么要跨过特殊字段
----------------------------

物理 ``0x8200`` 对应 ``startup_raw.S:_start``。第一条指令不是顺着下一字节执行，而是：

.. code-block:: asm

   ljmp $0, $ABS(codestart)

它再次把 ``CS`` 规范为0，并跳过 ``_start`` 开头由镜像生成器或安装器填写的特殊区：

::

   +0x08  compressed_size             32 bit
   +0x0c  uncompressed_size           32 bit
   +0x10  reed_solomon_redundancy     32 bit
   +0x14  no_reed_solomon_length      16 bit
   +0x18  boot_dev[0..2], boot_drive  4 bytes

这些字节是数据而不是可顺序执行的指令。 ``grub-mkimage`` 为i386-pc强制选择LZMA，把压缩
主体大小写入 ``compressed_size``，把 ``kernel_size + total_module_size`` 写入
``uncompressed_size``； ``grub-setup`` 在有额外embedding空间时还会填写RS冗余长度。没有
具体 ``core.img`` artifact，本章不编造三个大小值。

codestart怎样切断旧栈继承
------------------------

``codestart`` 先关中断，再把 ``DS``、 ``SS``、 ``ES`` 全部设成0：

.. code-block:: asm

   cli
   xorw %ax, %ax
   movw %ax, %ds
   movw %ax, %ss
   movw %ax, %es
   movl $GRUB_MEMORY_MACHINE_REAL_STACK, %ebp
   movl %ebp, %esp
   sti

``GRUB_MEMORY_MACHINE_REAL_STACK`` 是 ``0x2000-0x10=0x1ff0``，所以 ``ESP=EBP=1ff0``。
在 ``.code16`` 中使用32位 ``ESP`` 会同时清掉高16位； ``SS=0`` 又使栈地址与物理地址相同。
第024章留在 ``0x1ffe`` 的旧DX副本仍是内存残值，却已经不在新栈的活动范围内，GRUB不会再
通过 ``pop`` 取回它。

先保存DL，再调用INT 13h reset
-----------------------------

``xorw %ax,%ax`` 已把 ``AH`` 置0。重新开中断后，固定源码严格按这个顺序执行：

.. code-block:: asm

   movb %dl, boot_drive
   int  $0x13

先保存 ``DL=0x80`` 很重要：BIOS调用不再承担启动盘身份的所有权。特殊区原来是
``ff ff ff 00``；写入最后一个字节后，按little-endian读取为：

::

   boot_dev = 0x80ffffff

高字节是BIOS drive ``0x80``；随后会用到的DOS和BSD partition字节仍是 ``0xff``，表示早期
启动设备编码没有硬写分区号。

``INT 13h AH=00`` 在当前固定SeaBIOS中先按 ``DL=80`` 找回AHCI port 0的 ``drive_s``，构造
``CMD_RESET``。AHCI的 ``ahci_process_op`` 只专门处理READ/WRITE；RESET落入
``default_process_op``，直接以成功结束。因此这次调用会清SeaBIOS的disk interrupt flag并
更新last-status/CF/AH，却不会执行 ``ahci_port_reset``、COMRESET、重新枚举设备或改写
``IDMap``。GRUB也完全不检查返回的CF/AH：无论reset报告什么，下一条都是模式切换。

real_to_prot怎样迁移返回地址
----------------------------

实模式代码用 ``calll real_to_prot``，所以CPU在新实模式栈上压入的是32位返回offset。固定
``realmode.S`` 内含五个GDT descriptor：

::

   selector 0x00  null
   selector 0x08  base 0, 4 GiB limit, 32-bit execute/read code
   selector 0x10  base 0, 4 GiB limit, 32-bit read/write data
   selector 0x18  base 0, 64 KiB limit, 16-bit pseudo-real code
   selector 0x20  base 0, 64 KiB limit, 16-bit pseudo-real data

``real_to_prot`` 再次 ``CLI``，令 ``DS=0``， ``LGDT`` 后把 ``CR0.PE`` 置1，再远跳
``0x08:protcseg``。远跳同时重装 ``CS`` 的隐藏descriptor cache；只写 ``CR0.PE`` 而不远跳
不能得到32位code属性。到 ``protcseg`` 后， ``DS/ES/FS/GS/SS`` 全部装入 ``0x10``，逻辑
offset因此就是linear address。

旧返回地址仍位于实模式栈。代码先把它暂存到物理 ``0x1ff0``，再把保护模式栈设置为：

::

   GRUB_MEMORY_MACHINE_PROT_STACK
   = 0x68000 + 0x9000 + 0xf000 - 0x10
   = 0x7fff0

然后把返回地址写到新 ``ESP`` 顶端， ``ret`` 回到 ``startup_raw`` 的32位续点。栈迁移没有
复制旧栈帧；它只搬运这一个由 ``calll`` 建立的返回地址。

保护模式为什么保持IF为0
-----------------------

模式转换在 ``CLI`` 后没有执行 ``STI``。代码用 ``SIDT`` 保存从实模式继承的BIOS IDTR，再
装入一个limit为0的保护模式IDTR。此后GRUB主体运行在IF=0、空保护模式IDT的受控环境中；
分页仍关闭， ``CR0.PE=1``。

GDT中的0x18/0x20和保存下来的实模式IDTR不是当前主执行段，而是后续
``prot_to_real → BIOS INT → real_to_prot`` 桥的基础。每次桥接才暂时恢复实模式段、栈、IDT
和BIOS要求的IF，返回保护模式后又恢复空IDT与IF=0。

A20检查不会盲信SeaBIOS
----------------------

32位续点先 ``CLD``，再调用 ``grub_gate_a20``。检测例程比较物理 ``0x8000`` 与
``0x108000``：它保存低地址原字节，暂时写入与高地址不同的值，串行化访问，再读取高地址并
恢复低地址。如果A20关闭， ``0x108000`` 会回绕到 ``0x8000``；若两处独立，返回值表示A20已开。

第024章继承的A20确实开启，所以固定成功路径第一次检查就返回，不执行后备动作。源码中的完整
失败循环仍有明确边界：

#. 经模式桥调用 ``INT 15h AX=2401``；
#. 写system control port A ``0x92``；
#. 操作i8042 ``0x64/0x60``；
#. 仍失败则回到BIOS方法继续循环。

没有“全部方法失败后继续解压”的分支；A20没有确认开启，控制流就不会越过这个循环。

Reed–Solomon实际保护哪一段
--------------------------

A20确认后， ``startup_raw`` 无条件调用：

.. code-block:: c

   grub_reed_solomon_recover(reed_solomon_part,
                             protected_data_size,
                             reed_solomon_redundancy);

``protected_data_size`` 由 ``compressed_size`` 加上
``decompressor_end-reed_solomon_part`` 得出。安装器使用同一个
``no_reed_solomon_length`` 边界：第一扇区 ``diskboot.img`` 以及 ``startup_raw`` 中必须先
运行到decoder的前缀不在编码范围；从 ``reed_solomon_part`` 到压缩主体末端的数据才与尾随
冗余一起校验、就地修复。

这不能写成“恢复BIOS没有读出的sector”。第024章的INT 13h若返回错误， ``diskboot.img`` 已经
打印错误并自旋，根本到不了这里。RS能处理的是成功读进内存但内容发生可校正破坏的字节。若
``reed_solomon_redundancy=0``，recover立即返回且不修改映像；具体是否有冗余以及字节数依赖
实际embedding结果，本章保持未知。

LZMA为什么输出到1 MiB
---------------------

i386-pc镜像生成路径强制使用LZMA。RS返回后，固定代码设置：

::

   EDI = 0x00100000
   ESI = decompressor_end
   ECX = uncompressed_size

然后调用内嵌 ``_LzmaDecodeA``。低端 ``startup_raw``/压缩输入继续作为源，未压缩的GRUB
kernel initialized image、模块信息头和原始预装对象从物理 ``0x100000`` 起连续产生。分页
仍关闭，因此这些也是平坦保护模式中的linear address。A20若没开，这次写会回绕覆盖低端代码，
正是前一步必须闭合的原因。

此路径没有一个可返回rescue界面的“解压失败”分支。decoder返回后代码直接准备三个桥接地址并
跳到 ``ESI=0x100000``；不可校正的映像损坏可能导致错误输出或随后失控，但不能被叙述成一次
显式回滚。

startup.S怎样留下正式低端core
-----------------------------

解压输出的第一条代码来自 ``grub-core/kern/i386/pc/startup.S``。它先把
``real_to_prot``、 ``prot_to_real`` 和保存的real-mode IDTR地址写进高端副本自己的槽位，
使这些值随后一起被复制。接着：

.. code-block:: asm

   ECX = _edata - _start
   ESI = 0x100000
   EDI = _start              # link address 0x9000
   rep movsb

这里只复制GRUB kernel的已初始化 ``_start.._edata``，不是整个解压输出。紧随其后的
``struct grub_module_info`` 与原始ELF/prefix/config对象仍留在：

::

   grub_modbase = 0x100000 + (_edata - _start)

复制完成时CPU还在1 MiB临时副本中，于是用按链接地址解析的 ``cont`` 做间接跳转，开始从
``0x9000`` 正式副本取指。随后以0填充 ``BSS_START_SYMBOL..END_SYMBOL``；低端正式core的
未初始化全局状态由此建立，而高端原始模块区保持不动。

boot device怎样进入C全局变量
----------------------------

跳入解压输出前， ``startup_raw`` 已把特殊区四字节读入 ``EDX``。低端正式
``startup.S`` 在清BSS后执行：

.. code-block:: asm

   movl %edx, grub_boot_device
   call grub_main

所以SeaBIOS最初给出的 ``DL=0x80`` 已经穿过 ``boot.img``、 ``diskboot.img``、
``startup_raw``、LZMA解压和core搬移，最终成为低端BSS中的 ``0x80ffffff``。 ``grub_main``
被声明为 ``noreturn``；这个 ``call`` 只为C ABI建立返回地址，不存在本章可用的正常返回路径。

本章结束状态
------------

控制流已经走过：

::

   startup_raw at 0000:8200
   → far jump across special fields
   → CLI; DS=SS=ES=0; ESP=1ff0
   → STI; save DL=80
   → INT 13h AH=00 (AHCI reset is a no-op success)
   → calll real_to_prot
   → CR0.PE=1; CS=08; data/stack selectors=10
   → migrate return address to protected stack 0x7fff0
   → save real IDTR; load limit-0 protected IDTR
   → verify inherited A20
   → optional in-place Reed–Solomon recovery
   → LZMA decode to 0x100000
   → startup.S copies _start.._edata to 0x9000
   → jump to low formal copy; clear BSS
   → grub_boot_device=0x80ffffff
   → call grub_main

此刻：

* 当前执行者：BSP，刚进入GNU GRUB 2.14 ``grub_main()``；
* CPU mode：32位保护模式， ``CR0.PE=1``、分页关闭；
* segments： ``CS=0x08``， ``DS=ES=FS=GS=SS=0x10``，均为base 0的flat段；
* FLAGS：IF=0、DF=0；保护模式IDTR的limit为0；
* A20：开启并已经由GRUB实际检测；
* 活动栈：GRUB保护模式栈区域；进入C以后不再声明某个精确 ``ESP``；
* 正式GRUB core initialized image：链接地址 ``0x9000`` 起；低端BSS已清零；
* 高端解压区：从 ``0x100000`` 起仍保存临时kernel副本，随后是有效module-info与原始对象；
* ``grub_boot_device=0x80ffffff``，其中启动盘为BIOS ``0x80``，分区字段未知；
* BIOS bridge：real/protected转换地址与real IDTR已保存在正式core中；
* heap、已加载模块、 ``cmdpath/root/prefix``、normal mode和菜单：均尚未建立；
* Linux：尚未读取，也没有执行。

关键边界
--------

* 固定顺序是先保存 ``DL``，再调用INT 13h reset；reset结果不被检查。
* 当前AHCI reset不会触发hardware port reset或重新探测，只由SeaBIOS通用fallback成功结束。
* ``real_to_prot`` 只迁移一个32位返回地址，不继承第024章的旧栈帧。
* 保护模式主路径保持IF=0并使用空IDT；BIOS桥只在调用期间暂时恢复实模式环境。
* RS不能补救一次已经令 ``diskboot.img`` 自旋的BIOS读失败；它只处理已在内存中的编码数据。
* ``0x100000`` 是解压目标和原始模块区，不是正式kernel执行链接地址；正式core从 ``0x9000`` 运行。
* 具体压缩大小、冗余大小、 ``_edata``、模块区末端都需要实际构建artifact，本章不制造数值。

下一入口
--------

下一章从 ``grub_main()`` 的第一个无条件机器入口 ``grub_machine_init()`` 开始；若构建启用了
stack protector，源码会先更新guard，但它不改变本章交出的CPU/内存边界。入口时heap尚不存在，
``grub_machine_init`` 必须先定位高端module-info、注册console、重新取得E820并初始化allocator。

资料
----

* `GRUB固定提交：startup_raw入口、保存DL与模式转换 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/boot/i386/pc/startup_raw.S#L36-L117>`_；
* `GRUB固定提交：A20检测与后备方法 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/boot/i386/pc/startup_raw.S#L135-L266>`_；
* `GRUB固定提交：LZMA出口与桥接handoff <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/boot/i386/pc/startup_raw.S#L332-L356>`_；
* `GRUB固定提交：GDT、栈迁移与IDTR <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/i386/realmode.S#L80-L195>`_；
* `GRUB固定提交：正式core复制、BSS与grub_main <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/i386/pc/startup.S#L55-L124>`_；
* `GRUB固定提交：i386-pc强制LZMA与大小字段 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/util/mkimage.c#L885-L913>`_；
* `GRUB固定提交：decompressor拼接与uncompressed_size <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/util/mkimage.c#L1186-L1265>`_；
* `GRUB固定提交：安装器RS边界与冗余 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/util/setup.c#L612-L640>`_；
* `GRUB固定提交：RS零冗余与就地恢复 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/lib/reed_solomon.c#L404-L441>`_；
* `GRUB固定提交：实模式/保护模式栈常量 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/include/grub/i386/memory_raw.h#L23-L56>`_；
* `SeaBIOS固定提交：INT 13h reset构造CMD_RESET <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/disk.c#L193-L207>`_；
* `SeaBIOS固定提交：AHCI命令分派 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/ahci.c#L301-L315>`_；
* `SeaBIOS固定提交：RESET通用成功分支 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/block.c#L525-L540>`_。
