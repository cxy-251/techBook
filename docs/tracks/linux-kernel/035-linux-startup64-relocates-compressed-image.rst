.. SPDX-License-Identifier: GPL-2.0

================================================================
第三十五章：Linux startup_64 怎样把压缩内核搬到安全解压位置？
================================================================

第034章结束时，BSP / CPU0刚通过far return进入当前 ``K`` 副本中偏移 ``0x200`` 的
compressed ``startup_64``。CPU已经处于64-bit long mode，IF与DF为0；``CR3`` 指向未来
``B`` 地址域中由 ``startup_32`` 创建的六页page tables，低4 GiB identity-mapped。代码、
已初始化data和当前stack仍在 ``K`` 副本，真正的搬迁尚未发生。

本章继续使用：

::

   K  = GRUB交付的当前compressed payload基址
   Z  = boot_params物理地址
   G  = boot_params中实际交付的kernel_alignment
   L  = build产生的LOAD_PHYSICAL_ADDR
   I  = hdr.init_size
   E  = rva(_end)
   O0 = 解压输出的初步物理基址
   B  = O0 + I - E，compressed安全搬迁基址

本章的自然出口是CPU跳入 ``B`` 副本的 ``.Lrelocated``，其第一条指令尚未执行。解压、ELF
装载与正式内核入口都留在后续章节。

64位入口先清理flags与segment selectors
------------------------------------------

固定源码从：

.. code-block:: asm

   startup_64:
       cld
       cli
       xorl %eax, %eax
       movl %eax, %ds
       movl %eax, %es
       movl %eax, %ss
       movl %eax, %fs
       movl %eax, %gs

开始。``cld`` 与 ``cli`` 再次把DF和IF压到Linux要求的值。把 ``DS/ES/SS/FS/GS`` selector
写0会去掉bootloader/32位过渡阶段留下的selector身份；在64位模式的普通寻址中，
``DS/ES/SS`` base不再像legacy segmentation那样参与地址计算。这里没有打开interrupt，也没有
建立正式内核的per-CPU segment状态。

``startup_64`` 必须独立重算 ``O0`` 与 ``B``
--------------------------------------------

虽然当前路径刚从 ``startup_32`` 计算过这些地址，64位入口仍不能继承 ``RBP/RBX`` 作为ABI
事实，因为64位bootloader也可以直接进入payload ``+0x200``。固定源码因此从头计算。

在 ``CONFIG_RELOCATABLE`` build中：

.. code-block:: asm

   leaq startup_32(%rip), %rbp
   movl BP_kernel_alignment(%rsi), %eax
   ...

当前identity mapping令RIP-relative得到的 ``startup_32`` 数值同时是当前线性和物理基址；在
本场景中它等于 ``K``。向上按 ``G`` 对齐并以 ``L`` 为下限后：

::

   RBP = O0 = max(ALIGN_UP(K,G),L)     if CONFIG_RELOCATABLE
   RBP = O0 = L                       otherwise

然后：

.. code-block:: asm

   movl BP_init_size(%rsi), %ebx
   subl $rva(_end), %ebx
   addq %rbp, %rbx

重新得到：

::

   RBX = B = O0 + I - E
   B + E = O0 + I

``RBP`` 与 ``RBX`` 的含义不同：前者是正式内核解压输出的初步物理起点，后者是compressed
启动环境自己的未来运行起点。后面的KASLR还可能修改最终 ``output``，但不会回头改变本章
已经选定的compressed运行副本 ``B``。

stack先切到 ``B``，再搬代码
----------------------------

源码立即执行：

.. code-block:: asm

   leaq rva(boot_stack_end)(%rbx), %rsp

于是 ``RSP=B+rva(boot_stack_end)``。此时 ``B`` 中的 ``.bss`` 还没有从文件复制，也没有整体
清零；但stack不需要旧内容，后续push/call只需在GRUB按 ``init_size`` 预留且early page table
可达的16 KiB范围内写入自己的frame。

这一步也解释了为什么第034章把页表预先建在 ``B``：在代码搬迁之前，64位入口已经开始使用
未来运行区中的stack和可能的top-level table buffer。当前取指仍来自 ``K``，但运行数据逐步
切换到 ``B`` 地址域。

重新加载GDT并把 ``CS`` 绑定到当前Linux表
-------------------------------------------

``gdt64`` 的base字段初始保存 ``gdt-gdt64`` 相对值。源码用当前RIP求出 ``gdt64`` 地址，把
该runtime地址加到descriptor的base字段，再执行 ``lgdt``。之后压入 ``__KERNEL_CS`` 与
``.Lon_kernel_cs`` 当前地址并 ``lretq``。

这次far return不切换paging level或执行副本；它确保当前 ``CS`` selector对应刚加载的Linux
GDT中真实存在的64位code descriptor。后面的paging trampoline需要在64/32位code descriptor
之间转换，不能依赖一个只留在hidden cache、而当前GDT中不存在的旧 ``CS``。

``R15`` 固定保存 ``boot_params``
--------------------------------

进入 ``.Lon_kernel_cs`` 时，``RSI=Z`` 仍是boot protocol输入。但 ``RSI`` 在x86-64 C ABI中是
caller-saved，接下来多个C函数都可以覆盖它。源码因此执行：

.. code-block:: asm

   movq %rsi, %r15

``R15`` 是callee-saved register。从这里直到跳向解压后内核，compressed汇编都用：

::

   R15 = Z
   RBP = O0
   RBX = B

作为长期状态。各C helper按ABI必须保留三者。

stage1 IDT只提供当前阶段真正安装的入口
----------------------------------------

``load_stage1_idt()`` 无条件把 ``boot_idt_desc.address`` 指向当前 ``boot_idt`` 并执行
``lidt``。但固定实现并没有在这里安装普通 ``#PF``、NMI或完整异常表：只有build启用
``CONFIG_AMD_MEM_ENCRYPT`` 时，才把 ``#VC`` vector指向 ``boot_stage1_vc``；其他entry仍是
零。

因此stage1 IDT的精确作用是为SEV-ES/SNP相关早期 ``#VC`` 提供第一阶段入口，并发布一张
compressed环境自己的IDT。它不是“已经能够处理所有分页错误”的泛化边界；按需page-fault
mapping要等第036章的stage2 IDT。

同样只有 ``CONFIG_AMD_MEM_ENCRYPT`` 存在时，源码才以 ``RDI=R15`` 调用 ``sev_enable()``。
该helper会在相应runtime guest类型下完成SEV检测与准备。固定QEMU source commit没有固定启动
参数中的SEV/SEV-ES/SNP配置，所以本章保留build/runtime双重条件。

切换paging level之前收窄 ``CR4``
---------------------------------

源码读取CR4，只保留：

::

   X86_CR4_PAE | X86_CR4_MCE | X86_CR4_LA57

再写回CR4。PAE是long mode page walk的必要位；MCE和当前LA57状态需要跨过下面的检查。其他
bootloader或固件残留CR4 feature不继续带入compressed C环境。

随后调用：

.. code-block:: asm

   movq %r15, %rdi
   leaq rva(top_pgtable)(%rbx), %rsi
   call configure_5level_paging

第二个参数明确是 ``B+rva(top_pgtable)``，即未来compressed副本预留的一页，不是当前
``K`` 副本中的同名符号。

五级分页的目标由命令行与runtime CPUID决定
--------------------------------------------

固定7.2-rc1 ``configure_5level_paging()`` 先调用 ``sanitize_boot_params(bp)``，再令全局
``boot_params_ptr=bp``，因为接下来需要解析command line。也就是说，``boot_params`` 在本章
已经被清洗过一次；第036章搬迁并清BSS后，``extract_kernel()`` 还会重新建立全局指针并再次
清洗，不能把后者误写成全流程第一次。

函数把目标设为5-level的条件精确为：

::

   command line没有no5lvl
   && CPUID basic max leaf >= 7
   && CPUID.(EAX=7,ECX=0):ECX[16] LA57 = 1

本项目固定command line没有 ``no5lvl``，但没有固定QEMU的 ``-cpu`` model，因此最终由runtime
CPUID决定。旧稿增加一个 ``CONFIG_X86_5LEVEL`` 前提并不符合这份固定源码：当前x86-64
compressed实现中没有以该config包围这段目标判断。

若目标层级与当前 ``CR4.LA57`` 一致，函数直接返回。当前控制流来自 ``startup_32`` 创建的
4-level table，所以本场景只有两种成功结果：CPU不暴露LA57时保持4-level；CPU暴露LA57时
执行4-to-5 transition。helper中用于5-to-4的反向代码服务于64位bootloader/kexec等入口，
不是当前32位GRUB交接路径实际选择的分支。

层级不匹配时为什么需要低端8 KiB trampoline
---------------------------------------------

active long mode下直接翻转 ``CR4.LA57`` 会触发 ``#GP``。helper必须暂时关闭paging/long-mode
active状态，而且32位过渡代码只能用32位值装CR3。因此它从legacy BIOS低端内存中寻找
``TRAMPOLINE_32BIT_SIZE=2*PAGE_SIZE`` 的位置。

当前是i386-pc legacy BIOS，``efi_loader_signature`` 为空。``find_trampoline_placement()``
读取BDA中的EBDA与conventional-memory上界，并从GRUB交付的E820 entries倒序寻找该上界以下
最后一个足够大的RAM区，把8 KiB放在选定末端之下。源码没有把这块临时位置追加成新的E820
reserved entry；它先把原8 KiB保存到compressed ``trampoline_save``，使用结束后逐字节恢复。

4-to-5路径把当前4-level ``CR3`` 作为新level-5 table的第0项，第二页放32位toggle code。代码
临时离开long mode、设置LA57、重新开启paging并返回64位后，helper把trampoline中的最终顶级
页复制到调用者给出的 ``B+rva(top_pgtable)``，把CR3改指向这份长期副本，再恢复低端8 KiB。
原来位于 ``B+rva(pgtable)`` 的4-level root继续充当level-5 entry 0指向的下一层。

若无需切换，CR3仍直接指向 ``B+rva(pgtable)``，``top_pgtable`` 不承担当前root。两条路径都
保持当前compressed代码、``Z`` 和 ``B`` stack可访问。

复制之前把 ``RFLAGS`` 归零
----------------------------

``configure_5level_paging()`` 返回后，汇编执行：

.. code-block:: asm

   pushq $0
   popfq

可写flags被归零，IF和DF仍为0。下面会为倒序复制临时设置DF，结束后再显式清除；C代码不会
继承 ``std`` 状态。

倒序复制的精确边界是 ``[startup_32,_bss)``
------------------------------------------------

源码从已初始化范围的最后一个qword开始：

.. code-block:: asm

   leaq (_bss-8)(%rip), %rsi
   leaq rva(_bss-8)(%rbx), %rdi
   movl $(_bss-startup_32), %ecx
   shrl $3, %ecx
   std
   rep movsq
   cld

源范围是：

::

   [K, K+rva(_bss))

目标范围是：

::

   [B, B+rva(_bss))

它覆盖compressed ``.head.text``、压缩bitstream、代码、只读数据和已初始化 ``.data``，不
复制 ``[_bss,_ebss)``，也不覆盖位于BSS之后的 ``.pgtable`` NOBITS区。后两类空间已经按不同
方式处理：BSS将在新副本中清零，early page tables早已直接创建在 ``B``。

``std`` 令 ``RSI/RDI`` 每次减少8，从高地址向低地址复制。这个方向允许目标处于初始化窗口
高端且可能与源区重叠，不会先覆盖后面尚未读取的压缩输入或代码。``rep movsq`` 结束后的
``cld`` 是不可省略的交接边界。

copy过程中，当前指令仍从 ``K`` 取出；只有整个已初始化范围完成后才允许跳到 ``B``。当前
stack本来就在BSS中的 ``B`` 范围，不属于被复制区，因此不会被这次 ``rep movsq`` 覆盖。

GDTR改指向 ``B`` 后才跳入新副本
----------------------------------

此前GDTR仍指向 ``K`` 中的GDT。旧区域随后可能被解压输出覆盖，所以源码计算
``B+rva(gdt64)`` 和 ``B+rva(gdt)``，修正新descriptor的base并 ``lgdt``。这次不必再far return：
当前 ``CS`` hidden descriptor已经可继续执行，重要的是让以后需要查表的操作不再依赖旧
``K`` 内存。

最后：

.. code-block:: asm

   leaq rva(.Lrelocated)(%rbx), %rax
   jmp *%rax

这是一次同一CPU、同一long-mode、同一页表体系中的near indirect jump。变化的是RIP所属的
物理副本：CPU从 ``K`` 取指切换为从 ``B`` 取指。``.Lrelocated`` 第一条清BSS指令尚未执行。

本章结束状态
------------

* current executor：Linux 7.2-rc1 compressed ``.Lrelocated``，第一条 ``xorl %eax,%eax``
  尚未执行；
* CPU：BSP / CPU0，无调度、无AP参与；
* CPU mode：64-bit long mode；
* ``RIP=B+rva(.Lrelocated)``；
* ``R15=Z``，保存 ``boot_params``；
* ``RBP=O0``，保存初步解压输出物理基址；
* ``RBX=B=O0+I-E``，保存relocated compressed基址；
* ``RSP=B+rva(boot_stack_end)``，stack当前为空；
* IF=0，DF=0，其余可写RFLAGS已由 ``pushq 0/popfq`` 清零；
* compressed ``[startup_32,_bss)``：已倒序复制到 ``B``；
* compressed BSS ``[_bss,_ebss)``：尚未清零；
* early page tables：位于 ``B`` 的 ``.pgtable`` 区；
* paging：若runtime CPU无LA57则保持4-level；若有LA57则已切到5-level；
* ``CR3``：4-level时为 ``B+rva(pgtable)``；5-level时为
  ``B+rva(top_pgtable)``，其entry 0接到原4-level root；
* low trampoline：若使用，其原8 KiB内容已恢复；
* GDTR：指向 ``B`` 副本中的GDT；
* stage1 IDT：active；只按build条件提供第一阶段 ``#VC``；
* KASLR最终 ``output/virt_addr``：尚未选择；
* decompression、ELF装载、initramfs解析：均未执行。

关键边界
--------

#. 64位入口独立重算 ``O0/B``，不能依赖32位入口留下的register作为direct-entry ABI。
#. ``RBP=O0`` 与 ``RBX=B`` 分属解压输出和compressed运行副本；KASLR以后只可能修改前者传入
   C代码形成的 ``output``。
#. stack先进入 ``B``，代码后搬；该stack位于BSS，旧内容无意义但地址已预留并映射。
#. stage1 IDT不是page-fault-on-demand环境；``#PF`` 与NMI要到stage2才安装。
#. fixed command line排除了 ``no5lvl``，但未固定CPU model；paging level仍是runtime结果。
#. 这份固定源码的5-level目标判断没有额外 ``CONFIG_X86_5LEVEL`` gate。
#. 当前32位GRUB路径只会保持4-level或执行4-to-5；5-to-4是helper支持但本次未选的替代入口路径。
#. 低端trampoline是save/use/restore的临时工作区，不因这次使用永久变成E820 reserved。
#. ``rep movsq`` 只复制到 ``_bss`` 之前；BSS清零与 ``.pgtable`` 创建是另外两个边界。
#. 只有GDTR与整个initialized range都切到 ``B`` 后，CPU才跳入 ``B`` 的 ``.Lrelocated``。

下一入口
--------

第036章从新副本第一条指令开始：

.. code-block:: asm

   .Lrelocated:
       xorl %eax, %eax
       leaq _bss(%rip), %rdi
       leaq _ebss(%rip), %rcx
       subq %rdi, %rcx
       shrq $3, %rcx
       rep stosq

随后它将加载stage2 IDT、初始化可按需扩展的identity maps，并进入
``extract_kernel(Z,O0)`` 完成参数清洗、early console、KASLR和解压前硬检查。

资料
----

* `Linux 7.2-rc1固定提交：compressed startup_64搬迁路径 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/head_64.S#L276-L442>`_；
* `Linux 7.2-rc1固定提交：configure_5level_paging及低端trampoline <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/pgtable_64.c#L12-L200>`_；
* `Linux 7.2-rc1固定提交：stage1/stage2 IDT精确入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/idt_64.c#L7-L78>`_；
* `Linux 7.2-rc1固定提交：16 KiB stack、8 KiB trampoline与page-table空间 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/include/asm/boot.h#L35-L79>`_；
* `Linux 7.2-rc1固定提交：compressed section边界 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/vmlinux.lds.S#L25-L81>`_；
* `Linux 7.2-rc1固定提交：x86 boot protocol 64-bit entry <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/arch/x86/boot.rst>`_。
