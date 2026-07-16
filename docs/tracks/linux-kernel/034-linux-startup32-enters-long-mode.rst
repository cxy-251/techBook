.. SPDX-License-Identifier: GPL-2.0

================================================================
第三十四章：Linux startup_32 怎样建立 4 GiB 映射并进入 64 位模式？
================================================================

第033章停在GRUB relocator的最后一次far jump之后。BSP / CPU0已经位于32位protected
mode，paging与PAE关闭，IF与DF均为0；``EIP=K``，``ESI=Z``。这里的 ``K`` 是GRUB最终
搬好的protected payload物理起点，``Z`` 是最终 ``struct boot_params`` 物理地址。当前即将
执行的第一条指令来自固定Linux 7.2-rc1：

.. code-block:: asm

   arch/x86/boot/compressed/head_64.S:

   startup_32:
       cld
       cli

这是compressed kernel的32位入口，不是16位setup，也不是解压后
``arch/x86/kernel/head_64.S`` 中的正式内核入口。本章沿着 ``startup_32`` 完成runtime基址、
Linux自有GDT、CPU能力验证、早期页表和long-mode切换，停在当前压缩镜像内
``startup_64`` 的第一条指令之前。

先把缺失的artifact量保留为符号
----------------------------------

固定commit没有附带最终build ``.config`` 或可读取的 ``bzImage``，因此本章不能把构建期和
链接期量伪装成源码常数。沿用 ``K``、``Z`` 和第031章的 ``I=hdr.init_size``，再定义：

::

   G  = Z中经过GRUB调整后实际交给Linux的hdr.kernel_alignment
   L  = 固定build产生的LOAD_PHYSICAL_ADDR
   E  = rva(_end)，即compressed运行映像总跨度
   O0 = 解压输出的初步物理基址
   B  = compressed映像准备搬往的安全运行基址

``G``、``L``、``I`` 和 ``E`` 都依赖最终build/link artifact；``K`` 和 ``Z`` 依赖GRUB运行时
分配。固定源码能证明它们怎样参与运算，却不能从commit alone补出具体地址或长度。

``cld`` 与 ``cli`` 重新声明Linux自己的入口条件
-----------------------------------------------

GRUB已经交付DF=0、IF=0，Linux仍首先执行 ``cld`` 和 ``cli``。这不是多余动作：compressed
入口是一个可被不同bootloader调用的ABI，不能把字符串方向或maskable interrupt状态继续
寄托在某个调用者的实现细节上。

从这一步到本章结束，CPU一直是BSP / CPU0，没有调度器、task切换或AP参与。``cli`` 只屏蔽
maskable interrupt；NMI和同步异常不是由IF屏蔽，但此刻Linux还没有建立本阶段自己的完整
异常环境，所以后续每个模式切换步骤都必须在源码规定的窄路径内成功。

借用 ``boot_params.scratch`` 取得当前 ``startup_32`` 地址
------------------------------------------------------------

32位代码没有RIP-relative寻址，而compressed payload可以被GRUB放到构建地址之外。Linux先把
``boot_params`` 中偏移 ``0x1e4`` 的scratch字段尾部借作一次性4-byte stack：

.. code-block:: asm

   leal (BP_scratch+4)(%esi), %esp
   call 1f
1: popl %ebp
   subl $rva(1b), %ebp

``ESI=Z``，所以 ``call`` 把返回EIP写入 ``[Z+BP_scratch,Z+BP_scratch+4)``；紧接着的
``popl`` 又取走它。Linux不是在这里建立长期stack，也不把scratch里的旧内容当成输入。

``head_64.S`` 把：

.. code-block:: c

   #define rva(X) ((X) - startup_32)

定义为符号相对入口的链接期偏移。弹出的运行时标签地址减去 ``rva(1b)`` 后得到：

::

   EBP = K

从此在32位早期汇编中，``rva(symbol)(%ebp)`` 就是当前compressed副本中 ``symbol`` 的运行
地址。这个计算只确定当前镜像基址 ``K``，还没有确定最终解压地址，也没有搬动任何字节。

Linux加载自己的GDT并刷新 ``CS``
---------------------------------

GRUB的flat GDT满足handoff协议，但不属于Linux compressed环境。Linux用 ``K`` 修正内嵌在
``gdt`` 开头的32位GDTR descriptor，再加载它：

.. code-block:: asm

   leal rva(gdt)(%ebp), %eax
   movl %eax, 2(%eax)
   lgdt (%eax)

该GDT包含32位code、64位code、flat data以及早期TSS descriptor。随后Linux把
``DS/ES/FS/GS/SS`` 全部改为 ``__BOOT_DS``，再把 ``ESP`` 切到当前compressed副本中的：

.. code-block:: asm

   leal rva(boot_stack_end)(%ebp), %esp

x86-64 compressed build的 ``BOOT_STACK_SIZE`` 由固定源码无条件定义为 ``0x4000``，即16 KiB。
这次切换结束了对 ``boot_params.scratch`` 的临时使用。

仅执行 ``lgdt`` 不会更新当前 ``CS`` 的hidden descriptor cache，因此源码压入Linux自己的
``__KERNEL32_CS`` 与当前副本中的返回地址，再执行 ``lretl``。这次far return仍在paging关闭的
32位protected mode内；它只把代码段切到Linux GDT中的32位descriptor，尚未进入long mode。

``verify_cpu`` 成功是本场景继续运行的必要条件
------------------------------------------------

若build启用 ``CONFIG_AMD_MEM_ENCRYPT``，源码先调用 ``startup32_load_idt``，为可能的SEV-ES
``#VC`` 准备32位异常入口；未启用该config时这段代码根本不存在。它不能被写成所有q35启动
都会执行的动作。

随后无条件调用：

.. code-block:: asm

   call verify_cpu
   testl %eax, %eax
   jnz .Lno_longmode

固定 ``verify_cpu.S`` 先保存调用者flags并临时清除危险flags，然后验证CPUID可用、basic leaf 1
存在、build生成的 ``REQUIRED_MASK0`` 基础能力满足、extended leaf ``0x80000001`` 存在且
``REQUIRED_MASK1`` 满足，并单独检查SSE/SSE2要求。对特定旧AMD CPU，它可以清除
``MSR_K7_HWCR`` 的SSE disable bit后重试；对符合family/model条件的Intel CPU，它还可能清除
``IA32_MISC_ENABLE.XD_DISABLE``。这些vendor修正只有相应CPUID身份和MSR位条件成立才发生。

成功返回值是0，并恢复进入函数时的flags；失败返回1，``startup_32`` 跳到
``.Lno_longmode`` 的永久 ``hlt``/jump循环。固定叙事能够继续到后续章节，本身就约定当前QEMU
CPU提供这个64位内核build要求的能力；但没有固定CPU model参数，正文不再制造具体CPUID
leaf数值或宣称某个vendor修正一定执行。

先算初步输出 ``O0``，再算搬迁基址 ``B``
------------------------------------------

CPU验证成功后，``EBP`` 仍是当前compressed基址 ``K``。在 ``CONFIG_RELOCATABLE`` build中，
源码把 ``K`` 向上按 ``G`` 对齐，并以 ``L`` 为下限：

::

   O0 = max(ALIGN_UP(K,G), L)

若build没有 ``CONFIG_RELOCATABLE``，该对齐分支不编译，``O0=L``。这里读取的是GRUB实际交付
在 ``boot_params`` 中的 ``kernel_alignment``；它源于build header，但GRUB在第031章的分配
回退中可以把交付值调整为实际采用的alignment，因此不能简单替换为一个未经artifact验证的
``CONFIG_PHYSICAL_ALIGN`` 数字。

源码接着执行：

.. code-block:: asm

   addl BP_init_size(%esi), %ebx
   subl $rva(_end), %ebx

所以：

::

   B = O0 + I - E
   B + E = O0 + I

``O0`` 是解压输出的初步基址；``B`` 则是compressed运行映像以后要搬到的位置。把
compressed副本的 ``_end`` 贴在整个 ``init_size`` 窗口末端，才为从 ``O0`` 向上增长的原地
解压留下安全空间。本章只完成地址计算，真正的倒序复制在第035章。

PAE打开时paging仍然关闭
------------------------

源码读取 ``CR4``、只把 ``X86_CR4_PAE`` 置1后写回。此刻：

::

   CR4.PAE = 1
   CR0.PG  = 0

所以地址翻译尚未开始。PAE只是让随后打开paging时采用long mode需要的64-bit page-table
entry格式。

六页早期页表建在未来 ``B`` 副本，不在当前 ``K`` 副本
-----------------------------------------------------------

这是本章最容易混写的地址边界。固定汇编清零页表时使用：

.. code-block:: asm

   leal rva(pgtable)(%ebx), %edi
   movl $(BOOT_INIT_PGT_SIZE/4), %ecx
   rep stosl

此时 ``EBX=B``，不是 ``EBP=K``。因此24 KiB早期页表位于：

::

   [B + rva(pgtable), B + rva(pgtable) + 6*4096)

这块 ``.pgtable`` 是NOBITS启动空间；它无需先从 ``K`` 复制过来，``rep stosl`` 直接在未来
安全运行区中把它创建出来。当前CPU仍从 ``K`` 取指，当前stack也仍在 ``K`` 副本；只有将被
装入CR3的页表已经落在 ``B`` 地址域。旧文若只说“在compressed image中建页表”，会掩盖这
两个并存的运行基址。

``BOOT_INIT_PGT_SIZE=6*4096`` 对应：

::

   1页 level-4 table
   1页 level-3 table
   4页 level-2 table

level-4第0项指向level-3页；level-3前4项分别指向4个level-2页。每个level-2页有512项，
总计 ``4*512=2048`` 个2 MiB mapping。

2048个PDE形成低4 GiB identity map
-----------------------------------

level-2 entry从 ``0x00000183`` 开始，每项物理地址递增 ``0x00200000``。``0x183`` 给出
present、read/write、page-size与global等位，因此PDE本身直接映射2 MiB page，不再分配4 KiB
PTE层：

::

   2048 * 2 MiB = 4 GiB
   linear address X -> physical address X，0 <= X < 4 GiB

这张表没有建立正式内核高半区映射，也不是 ``start_kernel()`` 最终使用的页表。它只保证当前
32-bit boot-protocol路径中位于4 GiB以下的compressed代码、stack、``boot_params``、命令行和
搬迁窗口在开启paging后仍能用同一数值访问。

SEV encryption mask只在build与runtime同时满足时进入页表
------------------------------------------------------------

``EDX`` 先被清零。只有build含 ``CONFIG_AMD_MEM_ENCRYPT``，源码才调用
``get_sev_encryption_bit``；只有运行时报告SEV active，它才把位于bit 31以上的C-bit转换为页表
高32位mask，并令当前 ``K`` 副本中的 ``sev_status`` 暂记SEV enabled。建立各级entry时，这个
``EDX`` 被加入entry高半部分。

因此固定源码给出两个合法结果：普通路径的mask为0；SEV路径的early identity entries带C-bit。
QEMU版本固定不等于guest encryption配置固定，本章保留条件，不能把任一路径写成无条件事实。

``CR3`` 指向 ``B`` 中的页表，``EFER.LME`` 只先解除入口闩锁
-----------------------------------------------------------

页表完成后：

.. code-block:: asm

   leal rva(pgtable)(%ebx), %eax
   movl %eax, %cr3

由于 ``CR0.PG`` 仍为0，写CR3只是发布page-walk root，还没有改变当前取指地址。随后Linux通过
``rdmsr/wrmsr`` 设置 ``EFER.LME=1``。单独设置LME也不会立刻执行64位指令；此刻仍是32位
protected mode。

源码再以selector 0执行 ``lldt``，令LDTR无效；把 ``__BOOT_TSS`` 装入TR。若AMD encryption
代码存在，还会调用 ``startup32_check_sev_cbit`` 验证active SEV环境中的C-bit位置。任何这些
必要步骤失败都不会形成可继续叙事的另一条成功路径。

写 ``CR0_STATE`` 先进入compatibility submode
-----------------------------------------------

Linux把当前 ``K`` 副本中 ``startup_64`` 的地址与 ``__KERNEL_CS`` 压到当前boot stack：

.. code-block:: asm

   leal rva(startup_64)(%ebp), %eax
   pushl $__KERNEL_CS
   pushl %eax

目标是 ``K+rva(startup_64)``，不是未来的 ``B+rva(startup_64)``。源码随后不是简单对CR0执行
OR，而是写入完整 ``CR0_STATE``：

::

   PE | MP | ET | NE | WP | AM | PG

关键新增位是 ``CR0.PG``。由于 ``CR4.PAE=1``、CR3已就绪且 ``EFER.LME=1``，打开paging同时
令long mode active；但当前 ``CS`` 仍是 ``__KERNEL32_CS``，descriptor的L=0、D=1，所以CPU先
处于long mode的32位compatibility submode。

最后的 ``lret`` 弹出 ``startup_64`` offset与 ``__KERNEL_CS``。新code descriptor的L=1，
这次far control transfer才真正令CPU开始解码64位指令。``startup_64`` 由 ``.org 0x200`` 固定
在protected payload起点后 ``0x200``，故当前下一RIP是：

::

   K + 0x200

压缩镜像仍未搬走，正式内核也仍未解压。

本章结束状态
------------

* current executor：Linux 7.2-rc1 compressed ``startup_64``，第一条 ``cld`` 尚未执行；
* CPU：BSP / CPU0，无调度、无AP参与；
* CPU mode：64-bit long mode；
* current RIP：``K+rva(startup_64)=K+0x200``；
* current compressed code/data：仍在 ``K`` 副本；
* ``RBP`` 的低32位所代表基址：``K``；
* ``RBX=B=O0+I-E``；
* ``RSI=Z``，仍指向最终 ``boot_params``；
* current stack：仍是 ``K`` 副本中的16 KiB ``boot_stack``；
* ``CR0``：等于 ``CR0_STATE``，其中PE/MP/ET/NE/WP/AM/PG为1；
* ``CR4.PAE=1``；
* ``EFER.LME=1`` 且 ``EFER.LMA=1``；
* paging：active，当前为startup_32建立的4-level page tables；
* ``CR3=B+rva(pgtable)``；
* mapping：低4 GiB identity-mapped，主体使用2 MiB pages；
* SEV C-bit：依build与runtime条件，不能从固定commit单独确定；
* IF=0，DF=0；
* Linux compressed BSS：尚未清零；
* compressed搬迁：尚未执行；
* KASLR、解压、ELF装载与initramfs解析：均未执行。

关键边界
--------

#. ``boot_params.scratch`` 只承载一次 ``call`` return address，随后stack立刻切到当前镜像的
   ``boot_stack``。
#. ``EBP=K`` 是当前compressed入口基址；``O0`` 是初步解压基址；``B`` 是未来compressed
   搬迁基址，三者不可互换。
#. ``G/L/I/E`` 依赖最终build/link artifact；固定commit只固定公式，不固定它们的数字。
#. ``verify_cpu`` 使用build生成的required masks；当前成功路径不等于QEMU CPU model已被固定。
#. 24 KiB页表直接创建在 ``B+rva(pgtable)``，此时CPU仍从 ``K`` 取指。
#. early table只identity-map低4 GiB；它不是正式内核高半区页表。
#. SEV代码需要 ``CONFIG_AMD_MEM_ENCRYPT``，C-bit还需要runtime SEV active；两层条件不能省略。
#. ``EFER.LME=1`` 不是64位取指的充分条件；CR0.PG使long mode active，far return换入L=1的
   ``CS`` 后才开始执行64位指令。
#. far return进入的是当前 ``K+0x200``，不是尚未复制的 ``B`` 副本。

下一入口
--------

第035章从当前compressed副本的64位入口开始：

.. code-block:: asm

   startup_64:
       cld
       cli
       xorl %eax, %eax
       movl %eax, %ds
       ...

它将独立重算 ``O0`` 与 ``B``，把stack切到 ``B`` 地址域，按运行时CPUID/命令行决定是否从
4-level切到5-level paging，再把compressed代码和已初始化data倒序复制到 ``B``，最后跳入
新副本的 ``.Lrelocated``。

资料
----

* `Linux 7.2-rc1固定提交：compressed startup_32与startup_64 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/head_64.S#L82-L278>`_；
* `Linux 7.2-rc1固定提交：verify_cpu检查与vendor条件修正 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/verify_cpu.S#L38-L143>`_；
* `Linux 7.2-rc1固定提交：boot stack与early page-table大小 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/include/asm/boot.h#L9-L71>`_；
* `Linux 7.2-rc1固定提交：CR0_STATE位集合 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/include/uapi/asm/processor-flags.h#L179-L181>`_；
* `Linux 7.2-rc1固定提交：compressed linker的BSS、pgtable与_end边界 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/vmlinux.lds.S#L25-L81>`_；
* `Linux 7.2-rc1固定提交：x86 boot protocol 32/64-bit入口条件 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/arch/x86/boot.rst>`_。
