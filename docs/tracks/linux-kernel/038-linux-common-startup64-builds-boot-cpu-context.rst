.. SPDX-License-Identifier: GPL-2.0

======================================================================
第三十八章：Linux common_startup_64 怎样建立 boot CPU 的最早运行上下文？
======================================================================

第037章结束时，BSP已通过修正后的 ``early_top_pgt`` 第一次在正式kernel high mapping上进入
``common_startup_64``。CPU仍是64-bit long mode，IF/DF为0； ``R15=Z``， ``phys_base=O``；
页表同时保留无global的temporary identity mapping与正式高半区mapping。当前stack是
``__top_init_kernel_stack``，GSBASE仍为0，bringup IDT只按build提供早期 ``#VC``。

``common_startup_64`` 位于 ``secondary_startup_64`` 的公共后半段，BSP和以后启动的AP共用。
本章只选择当前boot CPU实际分支，建立logical CPU0的stack、GDT与GS/per-CPU环境，再规范化
EFER、CR0和flags，停在 ``x86_64_start_kernel(Z)`` 第一条C语句之前。

CR4先丢弃未列入preserve mask的状态
-------------------------------------

入口构造：

::

   preserve = CR4.PAE | CR4.LA57
   preserve |= CR4.MCE                  if CONFIG_X86_MCE
   value = current CR4 & preserve

PAE必须保留；LA57必须与compressed阶段选择的page-table层级一致；某些强制machine-check环境
不能安全清MCE，所以只有相应build才保留。其他bootloader/decompressor残留CR4 feature不继续
进入正式CPU上下文。

源码随后先在 ``value`` 中设置PSE并写CR4，再设置PGE并第二次写CR4。第一写刻意不含PGE，通用
代码借此保证若入口原有global translations，它们不会跨过该边界；第二写重新允许正式kernel
使用global mappings。当前BSP路径在第035章已经把CR4收窄到PAE/MCE/LA57，第037章切换用的
identity PMD又明确不带global，所以这里不能夸写成“本次必然刚清掉一批compressed global
TLB”；它首先是BSP/AP共享的状态规范化序列。

PSE在long mode page walk中即使被硬件忽略，源码也统一为所有logical CPU设置；PGE则从此对
正式kernel page-table entry生效。

BSP的logical CPU number来自静态 ``smpboot_control=0``
-----------------------------------------------------

在 ``CONFIG_SMP`` build中，共享代码读取 ``smpboot_control``。并行AP路径会带
``STARTUP_READ_APICID``，再从x2APIC MSR或APIC MMIO取hardware ID并扫描
``cpuid_to_apicid``。当前是第一次启动的BSP，固定 ``smpboot_control`` 初值为0，没有control
flag，低24位直接编码logical CPU number：

::

   ECX = 0
   RDX = __per_cpu_offset[0]

若build没有SMP，汇编直接令 ``RDX=0``。两种build都进入boot CPU的initial per-CPU区；不能因
缺少 ``.config`` 编造NR_CPUS或APIC ID，也没有AP在本章参与。

``current_task[CPU0]`` 把stack落实到 ``init_task``
--------------------------------------------------

有了per-CPU offset，汇编读取：

.. code-block:: asm

   movq current_task(%rdx), %rax
   movq TASK_threadsp(%rax), %rsp

CPU0的 ``current_task`` 初值指向静态 ``init_task``， ``thread.sp`` 给出它的boot stack top。
这一步把第037章仅供最早入口/verify使用的RIP-relative ``__top_init_kernel_stack``，收口为
“当前task所拥有的stack”。两者可能落在同一initial stack对象，但所有权表达已经从固定symbol
转成per-CPU current task。

AP从real-mode trampoline进入时会在拥有自己的stack后释放 ``trampoline_lock``。当前BSP的
``trampoline_lock`` pointer初值为NULL，test后直接跳到GDT设置，不写任何low trampoline lock。

GDTR改指向CPU0的per-CPU ``gdt_page``
-------------------------------------

代码在当前stack临时放16-byte ``desc_ptr``：limit为 ``GDT_SIZE-1``，base为
``gdt_page+RDX``，执行 ``lgdt`` 后立即回收这16 bytes。随后把 ``DS/SS/ES/FS/GS`` visible
selectors全部清0。

这与第037章startup GDT不是重复的同一所有权边界：startup helper先提供物理入口可用的
正式kernel descriptor；这里根据logical CPU/per-CPU offset切到CPU0自己的GDT page，为以后每
颗CPU独立descriptor state建立规则。当前没有加载最终TSS或完整runtime GDT内容，那些属于后续
CPU初始化。

GSBASE此时才获得正式per-CPU语义
--------------------------------

汇编把64-bit ``RDX`` 拆成 ``EDX:EAX``，写入 ``MSR_GS_BASE``：

::

   GSBASE = __per_cpu_offset[0]          CONFIG_SMP
   GSBASE = 0                            !CONFIG_SMP

第037章正式startup曾明确把GSBASE清0；从当前写MSR之后， ``%gs:percpu_symbol`` 才按CPU0
initial per-CPU区解释。boot CPU在完整per-CPU areas建立前继续使用init data section，这不是
percpu allocator已经运行。

``early_setup_idt`` 仍只管理bringup IDT
---------------------------------------

接着调用 ``early_setup_idt()``。如果build含 ``CONFIG_AMD_MEM_ENCRYPT``，它先
``setup_ghcb()``，再让bringup IDT的 ``#VC`` entry指向能够使用GHCB的 ``vc_boot_ghcb``；否则
handler为NULL。最后复用 ``startup_64_load_idt`` 加载同一类bringup table。

这里仍没有把32个exception vectors指向 ``early_idt_handler_array``，也没有建立
``do_early_exception`` 的page-fault补图环境。那个动作是第039章KASAN和SME early flags准备完
以后由 ``idt_setup_early_handler()`` 完成。旧稿把本次bringup IDT提前描述成通用early
``#PF`` handler，已修正。

EFER先保证SYSCALL，再按CPUID决定NXE
-----------------------------------

汇编执行CPUID ``0x80000001``，保存EDX feature bits，再读 ``MSR_EFER``。它无条件设置
``EFER.SCE``，允许以后配置好的 ``SYSCALL/SYSRET`` 机制；此刻还没有写正式syscall target MSR，
用户态也不存在。

若CPUID EDX bit20报告NX，源码同时：

::

   EFER.NXE = 1
   early_pmd_flags.NX = 1

前者让hardware解释page-table NX bit，后者令以后early direct-map PMD默认不可执行。源码保留
原EFER低32位，只有结果发生变化才 ``wrmsr``，避免TDX等环境中的无意义敏感MSR write。

这里的CPUID能力由当前CPU runtime决定；固定QEMU commit但未固定 ``-cpu``，正文只固定分支。
``verify_cpu`` 在前面已尽力清除旧Intel ``XD_DISABLE``，当前代码再按实际NX bit发布结果。

CR0与RFLAGS再次归一
------------------

源码写完整：

::

   CR0 = CR0_STATE = PE|MP|ET|NE|WP|AM|PG

随后 ``pushq 0/popfq`` 清可写RFLAGS。IF与DF保持0，frame pointer稍后清0。当前仍没有开启任何
maskable interrupt，也没有scheduler或interrupt controller dispatch。

``initial_code`` 为BSP选择第一个正式C入口
-----------------------------------------

汇编恢复第一个参数：

.. code-block:: asm

   movq %r15, %rdi
   xorl %ebp, %ebp
   callq *initial_code(%rip)

``RDI=Z`` 仍是bootloader交付的 ``boot_params`` 物理地址。 ``initial_code`` 的静态初值是
``x86_64_start_kernel``；AP boot、hotplug或恢复路径可以在以后改这个function pointer，但当前
BSP没有修改它。

``callq`` 压入返回地址后把RIP交给
``arch/x86/kernel/head64.c:x86_64_start_kernel(real_mode_data)``。该函数声明
``__noreturn``；汇编在call之后放 ``ud2``，若错误返回就触发invalid opcode，不会顺序落入未知
代码。本章停在C函数第一条runtime语句之前。

本章结束状态
------------

* current executor：Linux 7.2-rc1 ``x86_64_start_kernel(Z)``，第一条runtime语句尚未执行；
* CPU：BSP / logical CPU0；无AP执行；
* CPU mode：64-bit long mode，RIP在kernel high mapping；
* IF=0，DF=0，frame pointer=0；
* ``CR3``：修正后的 ``early_top_pgt``，high与temporary identity mappings仍共存；
* ``CR4``：保留PAE/LA57及条件MCE，并统一设置PSE/PGE；
* current task：CPU0 ``current_task -> init_task``；
* stack：``init_task.thread.sp`` 指定的initial task stack；
* GDT：CPU0 ``gdt_page``；visible data/FS/GS selectors为0；
* ``MSR_GS_BASE``：CPU0 initial per-CPU offset；
* IDT：bringup IDT；只有AMD-encryption build条件下的 ``#VC`` handler；
* general early ``#PF`` handler：尚未安装；
* ``EFER.SCE=1``；NX CPU时 ``EFER.NXE=1`` 且 ``early_pmd_flags.NX=1``；
* ``CR0=CR0_STATE``；
* ``RDI=Z``，以物理地址形式传入C函数；
* 正式kernel BSS/brk：尚未清零；
* global boot_params/boot_command_line：尚未从Z复制；
* initramfs：未unpack；generic ``start_kernel``：未调用。

关键边界
--------

#. common代码服务BSP/AP，但当前 ``smpboot_control=0`` 精确选择logical CPU0，不读取APIC ID。
#. !SMP与SMP build的取offset指令不同，但当前都建立boot CPU initial per-CPU上下文。
#. stack从固定top symbol过渡为 ``current_task[0]->thread.sp`` 的task所有权。
#. 第037章GSBASE=0；本章写CPU0 offset后才有正式GS-relative per-CPU语义。
#. ``early_setup_idt`` 只重载bringup IDT/条件 ``#VC``，不是一般early exception table。
#. current identity PMDs不带global，且PGE此前已清；CR4序列仍按BSP/AP共同契约省略再重开PGE。
#. EFER.SCE只启用指令机制，不表示syscall entry或用户态已经可用。
#. NX需要runtime CPUID；build/QEMU source commit alone不能保证该bit。
#. ``initial_code`` 是可改function pointer，但当前初值精确指向 ``x86_64_start_kernel``。
#. C入口是 ``call`` 且noreturn；若返回，唯一后继是 ``ud2``。

下一入口
--------

第039章从fixed ``head64.c`` 开始：

.. code-block:: c

   x86_64_start_kernel(char *real_mode_data)
   {
       /* BUILD_BUG_ON checks produce no runtime code */
       cr4_init_shadow();
       reset_early_page_tables();
       ...

它将撤销temporary identity root entries、清正式BSS/brk、建立KASAN/SME与通用early IDT，使用
``__va(Z)`` 复制boot params和完整command line，再进入 ``x86_64_start_reservations(Z)``。

资料
----

* `Linux 7.2-rc1固定提交：common_startup_64到initial_code <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/head_64.S#L198-L420>`_；
* `Linux 7.2-rc1固定提交：smpboot_control、early tables与phys_base data <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/head_64.S#L600-L684>`_；
* `Linux 7.2-rc1固定提交：bringup GDT/IDT loader <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/startup/gdt_idt.c#L12-L70>`_；
* `Linux 7.2-rc1固定提交：early_setup_idt只准备条件VC <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/head64.c#L313-L323>`_；
* `Linux 7.2-rc1固定提交：CPU0 current_task初值 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/cpu/common.c#L2235>`_；
* `Linux 7.2-rc1固定提交：CR0_STATE <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/include/uapi/asm/processor-flags.h#L179-L181>`_。
