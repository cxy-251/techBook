.. SPDX-License-Identifier: GPL-2.0

====================================================================
第三十七章：Linux 怎样解压 ELF 内核并进入正式 startup_64？
====================================================================

第036章结束时，BSP / CPU0仍在relocated compressed副本 ``B`` 的
``extract_kernel()`` 内，64-bit long mode、IF=0、DF=0。stage2 IDT已能为普通non-present
supervisor fault补一个2 MiB identity mapping； ``O`` 与 ``V`` 已选定并通过硬检查，但 ``O``
处尚未写入正式内核。

当前下一条源码是：

.. code-block:: c

   entry_offset = decompress_kernel(O, V, error);

本章先完成bitstream、ELF与relocation，再撤销compressed异常环境，以 ``RSI=Z`` 跳进解压后
``arch/x86/kernel/head_64.S:startup_64``。随后追到它切换 ``early_top_pgt`` 并第一次在正式
内核高半区进入 ``common_startup_64``；该入口第一条指令留给第038章。

当前heap已经建立，fallback不会重置它
-------------------------------------

``decompress_kernel()`` 开头保留一个防御分支：若 ``free_mem_ptr`` 仍为0，就把它指向
``boot_heap``。当前路径在第036章已经按compression build设置 ``free_mem_ptr/free_mem_end_ptr``，
所以该条件为false，现有linear boot heap原样继续使用。

固定源码根据最终 ``CONFIG_KERNEL_*`` 只编入gzip、bzip2、LZMA、XZ、LZO、LZ4或Zstd中的一套
decoder。缺少build ``.config``，不能选定算法；但所有算法在这里共享同一调用边界：

.. code-block:: c

   __decompress(input_data, input_len,
                NULL, NULL,
                O, output_len,
                NULL, error)

``input_data/input_len`` 位于已搬到 ``B`` 的compressed映像，``O/output_len`` 描述解压输出
buffer。若decoder报告负值，wrapper返回 ``ULONG_MAX``；实际error callback是 ``__noreturn``
的 ``error()``，它打印诊断后永久 ``hlt``。成功主线不会把sentinel当成入口继续执行。

第一次写高地址 ``O`` 可以在这里fault-in
-----------------------------------------

选址本身没有把所有 ``O`` 映射进页表。若 ``O`` 在第034章低4 GiB mapping之外，decoder的第一
次store产生non-present ``#PF``；第036章stage2 handler以CR2所在PMD范围调用
``kernel_add_identity_map``， ``iretq`` 后重试store。后续每跨入未映射的2 MiB范围都可以重复
这个过程。

因此“decoder写到了高物理输出”和“036主动预建整段输出mapping”不是同一结论。当前IF仍为0，
同步 ``#PF`` 不受IF屏蔽；保护、user或reserved-bit fault仍是fatal，不能借demand mapping掩盖。

decoder先在 ``O`` 还原一份ELF容器
---------------------------------

成功 ``__decompress`` 把压缩流还原到 ``[O,O+output_len)``。这一步得到的不是已经按运行地址
摆好的连续裸内核，而是带ELF header、program headers、loadable file bytes及末尾relocation
tables的中间映像。因此wrapper接着调用：

.. code-block:: c

   entry = parse_elf(O);

``parse_elf`` 先把 ``Elf64_Ehdr`` 复制到当前stack上的局部变量并验证四个ELF magic bytes。
失败调用 ``error`` 永久停止。

program headers先复制到heap，再移动segments
---------------------------------------------

函数按 ``e_phnum`` 从boot heap分配整张 ``Elf64_Phdr`` 数组，再从 ``O+e_phoff`` 复制进去。
先复制metadata很重要：后面的segment ``memmove`` 源和目标都可能落在同一个 ``O`` buffer，若
继续直接遍历原program-header位置，它可能被先移动的segment覆盖。

循环只处理 ``PT_LOAD``。x86-64固定源码还要求每个load segment的 ``p_align`` 是2 MiB的整数
倍；不满足就停止。其他 ``PT_*`` 被忽略，不因此创建运行对象。

对 ``CONFIG_RELOCATABLE`` build，每个目标是：

::

   dest = O + (phdr.p_paddr - L)

``L=LOAD_PHYSICAL_ADDR`` 是ELF物理布局基准；括号内保留链接时segment相对位置， ``O`` 把整套
布局平移到本次物理基址。non-relocatable build直接使用 ``dest=phdr.p_paddr``；该build的前置
路径又保证 ``O=L``。

复制长度只有 ``p_filesz``，使用 ``memmove`` 而非 ``memcpy`` 来处理重叠。``p_memsz-p_filesz``
对应的BSS不是在这里逐segment清零；第039章正式内核会统一清 ``__bss`` 与early brk。

所有headers处理完后释放临时phdr数组，并返回：

::

   entry_offset = ehdr.e_entry - L

所以最终物理入口可以统一写成 ``O+entry_offset``，不把link-time entry误当成当前可跳地址。

relocation处理发生在ELF segment搬运之后
--------------------------------------

``parse_elf`` 返回后，wrapper调用：

.. code-block:: c

   handle_relocations(O, output_len, V);

若build不含 ``CONFIG_X86_NEED_RELOCS``，该函数编译为空inline。若包含，fixed 7.2-rc1先计算：

::

   physical_delta = O - L
   map            = physical_delta - __START_KERNEL_map
   min_addr       = O
   max_addr       = O + (VO___bss_start - VO__text)

``map`` 把relocation table中以正式内核虚拟地址表达的location转换成当前 ``O`` self-map里的可写
指针。对于x86-64，真正加到location内容上的delta随后改成：

::

   relocation_delta = V - L

所以 ``O`` 决定“去哪里写被修正的word”， ``V`` 决定“那个word要加多少虚拟KASLR偏移”。两者
不能用一个KASLR base代替。若 ``V=L``，delta为0，函数直接返回，不扫描尾表。

固定尾表只有32-bit与64-bit两组
--------------------------------

当前 ``misc.c`` 的格式是从output末端向前读：

::

   ... 0, 64-bit relocation locations..., 0, 32-bit relocation locations...
                                                        ^ output末端一侧

每个location自身以signed 32-bit值存放。第一轮从 ``O+output_len-4`` 向低地址扫描32-bit组；
遇0后再越过terminator，第二轮扫描64-bit组。旧历史稿所写的“inverse 32-bit第三组”不在这份
固定实现和emit格式中，已删除。

每个location先sign-extend并加 ``map`` 得到当前物理self-map指针；源码检查它没有落到
``[min_addr,max_addr]`` 之外，然后分别对 ``uint32_t`` 或 ``uint64_t`` 内容加
``V-L``。越界意味着损坏的relocation metadata，直接 ``error``。

compressed异常环境在得到入口后撤销
------------------------------------

``decompress_kernel`` 返回 ``entry_offset`` 后，``extract_kernel`` 输出完成信息，再调用：

.. code-block:: c

   cleanup_exception_handling();

固定实现先按条件关闭SEV-ES GHCB，再把IDTR descriptor的size与address都写0并 ``lidt``。这会
撤销第036章stage2 ``#PF/NMI/#VC`` 环境；正式内核必须建立自己的bringup IDT，不能继续依赖
compressed handler。IF仍为0。

若compressed期间收到过NMI， ``spurious_nmi_count`` 此时只被打印；源码没有因此回滚已生成的
内核。最后：

.. code-block:: c

   return O + entry_offset;

返回值进入 ``RAX``。回到 ``.Lrelocated`` 后，汇编恢复 ``RSI=R15=Z`` 并 ``jmp *%rax``。
这是永久离开 ``arch/x86/boot/compressed`` 的near jump，不压返回地址，也不期待正式内核返回。

正式 ``startup_64`` 与compressed同名但不是同一对象
------------------------------------------------------

``RAX`` 指向解压后 ``arch/x86/kernel/head_64.S:startup_64``。此刻CPU仍在identity mapping下用
物理地址取指， ``RSI=Z``，IDTR为空；compressed ``B`` 副本及heap不再是主流程对象。

正式入口立即保存 ``R15=Z``，把 ``RSP`` 切到RIP-relative
``__top_init_kernel_stack``。这只是正式内核映像内的最早stack； ``common_startup_64`` 稍后还
会通过per-CPU ``current_task`` 重新取得task stack。

接着它把 ``MSR_GS_BASE`` 写成0。旧稿声称这里已经指向 ``fixed_percpu_data`` 不符合固定
7.2-rc1汇编；真正的CPU0 per-CPU GS base要到第038章由 ``__per_cpu_offset[0]`` 建立。此阶段的
position-independent helper不能假定per-CPU环境已经存在。

bringup GDT/IDT先替换compressed描述符环境
------------------------------------------

入口调用 ``__pi_startup_64_setup_gdt_idt``。fixed helper以RIP-relative地址加载正式内核
``gdt_page``，把 ``DS/SS/ES`` 改成 ``__KERNEL_DS``，并加载一张page-aligned
``bringup_idt_table``。

这张IDT不是第039章的完整early exception table。默认entry为0；只有build含
``CONFIG_AMD_MEM_ENCRYPT`` 时，helper才安装早期 ``#VC -> vc_no_ghcb``。随后汇编通过
``lretq`` 重新装入正式GDT中的 ``__KERNEL_CS``，保证IRET所依赖的code descriptor存在。

若build含AMD memory encryption，接下来以 ``RDI=Z`` 调用 ``__pi_sme_enable``，在任何后续
CPUID前准备SME/SEV/SNP状态。然后调用同一份 ``verify_cpu`` 来sanitize CPU。这里汇编没有
``test %eax`` 或失败跳转：compressed入口已经为当前boot CPU完成可继续启动的能力检查，本次
调用主要保留vendor/MSR修正；返回值在fixed正式入口中没有被分支使用。

``p2v_offset`` 从同一symbol的物理与虚拟地址差得到
--------------------------------------------------

当前RIP-relative ``common_startup_64`` 地址是它在identity map中的实际物理地址；
``.Lcommon_startup_64`` 中的quad则是link-time高半区虚拟地址。汇编相减：

.. code-block:: asm

   leaq common_startup_64(%rip), %rdi
   subq .Lcommon_startup_64(%rip), %rdi

得到：

::

   p2v_offset = current physical address - linked virtual address

再以 ``RSI=Z`` 调用position-independent ``__pi___startup_64(p2v_offset,Z)``。这套公式避免在
页表修好之前把一个高半区link address误当成当前可解引用C pointer。

``__startup_64`` 把 ``phys_base`` 记成实际 ``O``
--------------------------------------------------

helper用 ``rip_rel_ptr(_text)`` 得到当前正式内核 ``_text`` 物理地址，并检查它没有超过
``MAX_PHYSMEM_BITS``。随后固定表达式是：

.. code-block:: c

   phys_base = load_delta = __START_KERNEL_map + p2v_offset;

对当前布局，该值是实际物理内核基址 ``O``，不是 ``O-L``。名称 ``load_delta`` 表示它将被加到
静态页表内以 ``symbol-__START_KERNEL_map`` 编码的物理pointer上； ``phys_base`` 则供后续
physical/virtual转换。 ``O`` 若不是2 MiB aligned，helper永久循环，前章对齐约束在此再次被
硬验证。

helper同时从 ``CR4.LA57`` 读取compressed阶段已经选择的层级，并据此发布
``__pgtable_l5_enabled/pgdir_shift/ptrs_per_p4d``。它不在这里重新做CPUID随机选择。

修正高半区table并建立无global的切换identity map
-----------------------------------------------

``O`` 加上条件SME mask后，被用于修正 ``early_top_pgt``、5-level时的
``level4_kernel_pgt``、 ``level3_kernel_pgt`` 与fixmap下级table的物理pointer。

helper再从 ``early_dynamic_pgts`` 取页，为当前 ``[_text,_end)`` 建立临时identity mapping。
PMD entry使用2 MiB executable large mapping并明确清除 ``_PAGE_GLOBAL``，使以后撤销1:1 map时
不会留下不可由普通CR3 reload清掉的global translation。

静态 ``level2_kernel_pgt`` 原本按link layout覆盖整个kernel image window。helper把正式映像
之前的PMD清present，只给 ``[_text,_end]`` 对应present entries加实际 ``O`` 与条件encryption
mask，再清除映像之后的present。这样未经firmware可用内存检查的旁邻物理范围不会因宽泛高半区
mapping而允许speculative access。

最后 ``sme_postprocess_startup`` 按条件加密kernel，并处理 ``.bss..decrypted`` 的mapping，返回
应加入CR3的SME modifier；非SME路径返回0。

切换 ``early_top_pgt`` 后跳入高半区
-------------------------------------

汇编用RIP-relative得到当前 ``early_top_pgt`` 物理地址，加helper返回的SME modifier；AMD
encryption build还调用 ``sev_verify_cbit``。然后：

.. code-block:: asm

   movq %rax, %cr3
   jmp *.Lcommon_startup_64(%rip)

新CR3同时保留刚建的identity mapping与修正后的正式高半区mapping。间接jump从quad取得
link-time ``common_startup_64`` 高地址；CPU第一次以正式内核虚拟RIP取指，而物理后端仍是
``O`` 中刚装好的segment。

本章结束状态
------------

* current executor：Linux 7.2-rc1 ``arch/x86/kernel/head_64.S:common_startup_64``，第一条
  CR4 mask指令尚未执行；
* CPU：BSP / CPU0；64-bit long mode；IF=0，DF=0；
* current RIP：正式内核高半区虚拟地址；
* ``R15=Z``，boot params物理地址仍被保留；
* stack：正式映像中的 ``__top_init_kernel_stack``；
* ``MSR_GS_BASE=0``；正式per-CPU base尚未建立；
* GDT：正式内核startup ``gdt_page``； ``CS=__KERNEL_CS``；
* IDT：bringup IDT，只有build条件下的早期 ``#VC`` entry；
* ``phys_base=O``；
* ``CR3``：实际 ``early_top_pgt`` 物理地址加条件SME modifier；
* mappings：正式kernel high mapping与无global的临时identity mapping同时存在；
* paging level：沿用compressed阶段4-level或5-level结果，并已发布相应变量；
* compressed bitstream：已解码；ELF magic/program headers已验证；
* ``PT_LOAD``：已按 ``p_filesz`` 搬到实际物理布局；正式BSS尚未清零；
* relocation：依 ``CONFIG_X86_NEED_RELOCS`` 与 ``V-L`` 完成或成为no-op；
* compressed IDT/GHCB：已清理；compressed控制流不会返回；
* initramfs：仍是 ``R`` 处原始 ``N`` bytes，未unpack；
* scheduler、AP与generic ``start_kernel``：均未进入。

关键边界
--------

#. 当前heap已在036建立， ``decompress_kernel`` 的zero-pointer fallback不执行。
#. decoder写高地址O依stage2 ``#PF`` demand mapping；选址不等于提前映射。
#. ``parse_elf`` 先复制phdr table，再 ``memmove`` ``PT_LOAD.p_filesz``；BSS不在此处清零。
#. relocatable segment destination用O，64-bit relocation content delta用V；两者不可混用。
#. fixed relocation tail只有32-bit和64-bit两组，没有旧稿的inverse 32-bit第三组。
#. ``cleanup_exception_handling`` 把IDTR置空；正式startup必须另建bringup IDT。
#. 正式startup先把GSBASE清0，per-CPU GS到common路径才建立。
#. 正式startup的 ``verify_cpu`` 返回值没有被测试；能力失败halt属于compressed 034边界。
#. ``p2v_offset`` 是同一symbol当前物理地址减link-time虚拟地址； ``phys_base=O``，不是O-L。
#. temporary identity PMDs明确不带global；高半区PMDs只保留实际kernel image范围。
#. 写CR3后通过绝对高半区quad跳转；这是物理identity RIP到正式kernel virtual RIP的边界。

下一入口
--------

第038章从：

.. code-block:: asm

   common_startup_64:
       movl $(X86_CR4_PAE | X86_CR4_LA57), %edx
       ...

开始。它将规范化CR4，为BSP选出logical CPU0与per-CPU offset，切到 ``init_task`` stack，加载
CPU0 GDT和GSBASE，准备bringup IDT/EFER/CR0，最后通过 ``initial_code`` 调用
``x86_64_start_kernel(Z)``。

资料
----

* `Linux 7.2-rc1固定提交：decompress、ELF、relocation与extract返回 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/misc.c#L197-L362>`_；
* `Linux 7.2-rc1固定提交：extract cleanup与正式入口jump <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/misc.c#L514-L536>`_；
* `Linux 7.2-rc1固定提交：compressed .Lrelocated最终jump <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/head_64.S#L463-L476>`_；
* `Linux 7.2-rc1固定提交：正式startup_64与高半区jump <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/head_64.S#L38-L144>`_；
* `Linux 7.2-rc1固定提交：startup bringup GDT/IDT <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/startup/gdt_idt.c#L12-L70>`_；
* `Linux 7.2-rc1固定提交：__startup_64页表修正与identity map <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/startup/map_kernel.c#L17-L216>`_；
* `Linux 7.2-rc1固定提交：compressed error永久halt <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/error.c#L10-L24>`_。
