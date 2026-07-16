.. SPDX-License-Identifier: GPL-2.0

================================================================
第三十九章：x86_64_start_kernel 怎样清理临时环境并保存启动数据？
================================================================

第038章以 ``callq *initial_code`` 把BSP / logical CPU0交给
``x86_64_start_kernel(real_mode_data)``。当前 ``real_mode_data=Z`` 仍是bootloader参数的物理
地址数值；CPU处于kernel high mapping、IF/DF为0，GSBASE已是CPU0 initial per-CPU offset，
current task是 ``init_task``。 ``early_top_pgt`` 仍同时含kernel high mapping和第037章切换所需
的temporary identity entries，正式kernel BSS/brk尚未清零，IDT仍是只有条件 ``#VC`` 的
bringup表。

本章按fixed Linux 7.2-rc1 ``head64.c`` 的runtime顺序收掉这些临时状态，把外部boot data复制
进正式kernel对象，停在 ``x86_64_start_reservations(Z)`` 第一条语句之前。第040章再进入platform
quirks和generic ``start_kernel()``。

开头的 ``BUILD_BUG_ON`` 不产生runtime阶段
------------------------------------------

函数前几项检查kernel image、module area、fixmap与PMD alignment的link-time关系。它们在成功
build中全部由编译器消去，不是CPU当前逐项执行的if chain。本章第一条有runtime效果的语句是：

.. code-block:: c

   cr4_init_shadow();

它把第038章已经规范化的hardware CR4同步到CPU0 per-CPU software shadow。后续
``cr4_set_bits/cr4_clear_bits`` 和TLB helper依赖这份起点；shadow建立不再改变实际CR4位。

``reset_early_page_tables`` 撤销低地址identity entries
-----------------------------------------------------

下一步：

.. code-block:: c

   memset(early_top_pgt, 0, sizeof(pgd_t) * (PTRS_PER_PGD-1));
   next_early_pgt = 0;
   write_cr3(__sme_pa_nodebug(early_top_pgt));

函数清 ``early_top_pgt`` 前511项，只保留最后一个kernel high-map entry，再重载同一root。第037章
为物理到高半区切换建立的identity top-level entries到此不再present； ``early_dynamic_pgts``
存储虽尚在，但allocator index重置为0，旧下级内容不再由root引用。

因此当前参数 ``Z`` 不能再被当成可直接解引用的identity virtual pointer。函数只把该数值继续
保存在 ``real_mode_data`` 中；真正copy时显式使用 ``__va(Z)``，通过direct-map地址访问。

若第035章启用了5-level paging，源码此时把动态virtual layout变量改成L5版本：

::

   page_offset_base = __PAGE_OFFSET_BASE_L5
   vmalloc_base     = __VMALLOC_BASE_L5
   vmemmap_base     = __VMEMMAP_BASE_L5

4-level路径保留它们的L4初始化值。这一步必须在后面的 ``__va`` 和early direct-map补图之前
完成。

正式kernel BSS与early brk现在才获得zero-init语义
--------------------------------------------------

``clear_bss()`` 依次清：

::

   [__bss_start,__bss_stop)
   [__brk_base,__brk_limit)

第037章 ``parse_elf`` 只按 ``PT_LOAD.p_filesz`` 搬file bytes，并未用 ``p_memsz`` 逐段清零。
所以普通静态zero-initialized globals不能在这个边界之前被随意假定为0；本函数在只依赖明确
initialized data完成CR4、CR3和layout切换后，统一兑现ELF BSS语义。

``brk`` 是完整memory allocator可用前的early linear reservation区，不是用户态 ``brk``
syscall对象。把它清零防止 ``O`` 原内存残留被当成allocator metadata。

``init_top_pgt`` 必须在KASAN写入前清空
-------------------------------------

当前执行仍使用 ``early_top_pgt``，所以源码可以安全：

.. code-block:: c

   clear_page(init_top_pgt);

``init_top_pgt`` 将承接更长期的kernel/direct-map页表。它必须先清再调用 ``kasan_early_init``；
反序会擦掉KASAN刚写入的shadow mappings。

SME先修early PMD flags，KASAN再建最小shadow
-------------------------------------------

``sme_early_init()`` 在build/runtime SME active时把encryption mask加入 ``early_pmd_flags`` 与
supported PTE mask，并发布memory-encryption callbacks；普通路径是no-op。它必须早于任何可能
产生direct-map page fault的访问，否则 ``early_make_pgtable`` 可能用错误C-bit建立PMD。

随后 ``kasan_early_init()`` 依build而成为真实函数或空inline。启用时，它用共享early shadow
page/table填充最小KASAN层级，并同时把shadow mapping加入 ``early_top_pgt`` 与刚清过的
``init_top_pgt``。这只让接下来的instrumented early C code安全运行，不代表完整KASAN memory
layout已经完成。

源码在KASAN之后调用：

.. code-block:: c

   __native_tlb_flush_global(this_cpu_read(cpu_tlbstate.cr4));

它清理由trampoline/早期table可能留下的global TLB entries。顺序不能提前：某些KASAN build会
instrument ``native_write_cr4``，shadow未就绪就调用global-flush helper反而会fault。第038章的
CR4 PGE序列和这里的explicit global flush是两个边界，旧稿不能用前者替代后者。

general early exception table到这里才安装
-----------------------------------------

``idt_setup_early_handler()`` 为 ``NUM_EXCEPTION_VECTORS`` 中每个vector把 ``idt_table`` entry
指向对应 ``early_idt_handler_array[i]``，再加载正式 ``idt_descr``。从这里开始，页错误、VE、
VC及其他early exception才进入统一frame并调用 ``do_early_exception``。

其中page fault分支尝试 ``early_make_pgtable(CR2)``：仅当CR2是direct-map范围、当前CR3仍是
``early_top_pgt`` 且dynamic table可用时，按 ``early_pmd_flags`` 建2 MiB PMD并返回重试。它与
第036—037章compressed stage2 ``#PF`` 不是同一IDT、同一allocator或同一address-space helper。

无法补图的exception继续交给 ``early_fixup_exception``；AMD ``#VC`` 和TDX ``#VE`` 也有各自
条件handler。安装一般early IDT以后， ``tdx_early_init()`` 才建立供后续
``cc_platform_has()`` 使用的TDX状态；非TDX build/runtime不改变当前普通路径。

``copy_bootdata`` 用 ``__va(Z)`` 接回外部参数
--------------------------------------------

主函数调用：

.. code-block:: c

   copy_bootdata(__va(real_mode_data));

此时 ``real_mode_data`` 的数值仍是物理 ``Z``； ``__va`` 按已经选择好的L4/L5
``page_offset_base`` 形成direct-map virtual address。若相关PMD尚不存在，刚安装的general early
``#PF`` 可以补图。

``copy_bootdata`` 先按条件让SME host-memory-encryption路径为boot params与command line建立
decrypted mappings，再执行：

.. code-block:: c

   memcpy(&boot_params, __va(Z), sizeof(boot_params));
   sanitize_boot_params(&boot_params);

全局 ``boot_params`` 属于正式kernel BSS，刚刚清零并从此获得内核所有权。它接收E820、screen
info、RSDP、setup header、initramfs ``R/N`` 等协议字段；copy后再次sanitize外部ABI。

命令行地址由低32位 ``hdr.cmd_line_ptr`` 与高32位 ``ext_cmd_line_ptr`` 拼成。非零时转成
``__va``，固定复制整个 ``COMMAND_LINE_SIZE=2048`` buffer到 ``boot_command_line``，不是只复制
到NUL。当前字符串精确为：

::

   BOOT_IMAGE=/boot/bzImage root=/dev/sda1 ro console=ttyS0

旧稿遗漏 ``BOOT_IMAGE=/boot/bzImage`` 前缀，已修正。copy完成后SME路径撤销临时decrypted
boot-data mappings；外部Z/C buffer不再是正式kernel保存参数所必需的所有权对象。

``load_ucode_bsp`` 是一次条件尝试，不保证发生update
-----------------------------------------------

接着无条件写在C控制流中的调用是 ``load_ucode_bsp()``。若build没有 ``CONFIG_MICROCODE``，
header把它编译为空inline；若有，helper解析 ``microcode=``/legacy disable参数、检查CPUID与
hypervisor bit、CPU vendor/family及loader禁用条件，再选择Intel或AMD early loader。

固定command line没有microcode参数，但QEMU CPU model、vendor与build config未固定，仓库也没有
提供一个可核对的early microcode blob。因此本章只能固定“BSP执行这次helper调用”；不能把它
写成“微码revision已经更新”。QEMU暴露hypervisor bit时，非debug loader还会主动禁用early
update。

``init_top_pgt`` 只先继承kernel high top entry
-----------------------------------------------

源码最后执行：

.. code-block:: c

   init_top_pgt[511] = early_top_pgt[511];

前面整页已清零、KASAN可能加入shadow mappings；这里再把 ``early_top_pgt`` 的第511项，即当前
正式kernel high-map subtree，复制给长期root。它没有在一条赋值里建立完整physical direct map、
vmalloc或用户空间页表；那些仍由后续memory setup完成。

随后：

.. code-block:: c

   x86_64_start_reservations(real_mode_data);

传入的仍是物理数值 ``Z``。该callee声明 ``__noreturn``；本章停在其第一条语句之前，不越过第
040章提前展开platform quirks或generic ``start_kernel``。

本章结束状态
------------

* current executor：Linux 7.2-rc1 ``x86_64_start_reservations(Z)``，第一条语句尚未执行；
* CPU：BSP / logical CPU0；64-bit long mode；IF=0，DF=0；
* current task/stack： ``init_task`` / initial task stack；
* GSBASE：CPU0 initial per-CPU offset；CR4 shadow已同步；
* ``early_top_pgt``：前511项已清，只保留/重建kernel high与条件KASAN shadow mapping；
* temporary low identity mapping：已从active root撤销；
* paging layout variables：与实际4-level或5-level一致；
* formal ``[__bss_start,__bss_stop)`` 与 ``[__brk_base,__brk_limit)``：已清零；
* ``init_top_pgt``：已清，含条件KASAN shadow及复制来的entry 511 kernel high mapping；
* SME early flags：按build/runtime完成或no-op；
* general early IDT：已加载32个early exception entries；
* early direct-map ``#PF`` helper：现在可用；
* TDX early state：按build/runtime完成或no-op；
* global ``boot_params``：已从 ``__va(Z)`` 复制并sanitize；
* ``boot_command_line``：已复制完整2048-byte buffer，字符串含 ``BOOT_IMAGE`` 前缀；
* early microcode：helper已调用；是否加载update未由固定条件确定；
* initramfs：global boot params中仍记录 ``R/N``，内容尚未unpack；
* generic ``start_kernel``：尚未调用。

关键边界
--------

#. 开头BUILD_BUG_ON只做build-time验证；第一条runtime动作是 ``cr4_init_shadow``。
#. reset root后Z不再是identity virtual pointer；copy必须使用 ``__va(Z)``。
#. L5 layout变量在任何后续 ``__va`` / direct-map fault之前更新。
#. formal kernel BSS到本章才统一清零；第037章PT_LOAD只复制 ``p_filesz``。
#. ``init_top_pgt`` 必须在KASAN映射前clear；SME必须在可能生成early PMD之前更新flags。
#. general early IDT到 ``idt_setup_early_handler`` 才安装；038的bringup IDT不能处理一般 ``#PF``。
#. formal early ``#PF`` 使用early_top/dynamic pgts；它不是compressed ``kernel_add_identity_map``。
#. command line固定复制2048 bytes，当前有效字符串包含 ``BOOT_IMAGE=/boot/bzImage``。
#. ``load_ucode_bsp`` 调用不等于revision更新；config、hypervisor、vendor、family和blob仍是条件。
#. ``init_top_pgt[511]`` 只继承kernel high subtree，不代表完整direct map已经建成。
#. reservations参数仍是物理Z；fallback是否再次copy由下一章检查global header version决定。

下一入口
--------

第040章从：

.. code-block:: c

   x86_64_start_reservations(char *real_mode_data)
   {
       if (!boot_params.hdr.version)
           copy_bootdata(__va(real_mode_data));
       ...

开始。当前global ``boot_params`` 已有效，所以正常GRUB路径不再次copy；函数将建立ordinary PC
platform quirks并调用generic ``start_kernel()``。第040章仍为pending历史稿，留给下一批审查。

资料
----

* `Linux 7.2-rc1固定提交：x86_64_start_kernel与reservations入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/head64.c#L222-L310>`_；
* `Linux 7.2-rc1固定提交：early page tables、BSS与copy_bootdata <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/head64.c#L46-L220>`_；
* `Linux 7.2-rc1固定提交：general early IDT安装 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/idt.c#L327-L341>`_；
* `Linux 7.2-rc1固定提交：early exception entry与do_early_exception <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/head_64.S#L488-L542>`_；
* `Linux 7.2-rc1固定提交：KASAN early shadow <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/kasan_init_64.c#L287-L316>`_；
* `Linux 7.2-rc1固定提交：SME bootdata mapping与early flags <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/mem_encrypt_amd.c#L156-L215>`_；
* `Linux 7.2-rc1固定提交：BSP early microcode条件 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/cpu/microcode/core.c#L114-L205>`_。
