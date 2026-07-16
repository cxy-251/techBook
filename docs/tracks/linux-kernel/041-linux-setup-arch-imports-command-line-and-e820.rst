第四十一章：Linux setup_arch 怎样接管命令行并导入 E820 内存图？
===================================================================

第四十章结束时，BSP/CPU0仍以 ``init_task`` 在64-bit kernel high mapping中执行，IF=0；CPU0
已经加入possible、present、online与active masks。 ``start_kernel`` 的下一条调用是：

.. code-block:: c

   setup_arch(&command_line);

本章沿fixed Linux 7.2-rc1 ``arch/x86/kernel/setup.c`` 的前半段执行，先建立x86实际采用的
command line与boot-CPU能力，再按“先reserve、后导入E820”的顺序保存启动对象，停在
``setup_initial_init_mm(...)`` 尚未执行的位置。

先打印bootloader字符串，再处理built-in command line
---------------------------------------------------------

x86-64分支首先执行：

.. code-block:: c

   printk(KERN_INFO "Command line: %s\n", boot_command_line);
   boot_cpu_data.x86_phys_bits = MAX_PHYSMEM_BITS;

此刻 ``boot_command_line`` 还是第039章从GRUB buffer复制的有效字符串：

::

   BOOT_IMAGE=/boot/bzImage root=/dev/sda1 ro console=ttyS0

所以第一条command-line日志记录的是这个bootloader版本。 ``x86_phys_bits`` 暂以架构最大值作
早期上界；本章稍后的 ``early_cpu_init`` 会用CPUID address-size信息更新boot CPU描述，不能把
这次赋值当成QEMU CPU已经支持全部 ``MAX_PHYSMEM_BITS``。

接下来才处理build-time ``CONFIG_CMDLINE``：

* 未启用 ``CONFIG_CMDLINE_BOOL``：保留GRUB字符串；
* 启用但不override，且built-in string非空：形成
  ``<builtin> + " " + <GRUB string>``；
* 启用 ``CONFIG_CMDLINE_OVERRIDE``：用built-in string覆盖GRUB字符串。

最后：

.. code-block:: c

   strscpy(command_line, boot_command_line, COMMAND_LINE_SIZE);
   *cmdline_p = command_line;

``command_line`` 是x86静态缓冲， ``*cmdline_p`` 把它交还generic ``start_kernel``。固定磁盘
约定足以确定GRUB字符串，却没有提供最终kernel ``.config``，因此后续“有效command line”必须
保留上述三分支；不能把 ``BOOT_IMAGE=...`` 既误删，也不能擅自断言它一定没有被built-in
override。

OLPC探测不把当前q35改成OFW平台
--------------------------------

``olpc_ofw_detect()`` 先检查OLPC OFW交接标记。当前是SeaBIOS/GRUB i386-pc，未携带该OFW
handoff，普通q35路径不会安装OLPC callbacks或因 ``reserve_top`` 调整fixmap。源码仍把探测放在
触碰early ioremap area之前，以保证真正的OLPC入口有机会先改layout。

``idt_setup_early_traps`` 只替换选定exception gate
----------------------------------------------------

第039章 ``idt_setup_early_handler`` 已把前32个exception vector接到
``early_idt_handler_array``，其中 ``#PF`` 能为formal early direct map补PMD。现在：

.. code-block:: c

   idt_setup_early_traps();

在同一个 ``idt_table`` 中把 ``#DB`` 与 ``#BP`` 换成真实early debug/int3 entry，TDX guest build
还可替换 ``#VE``，随后reload IDTR。x86-64此时故意不替换 ``#PF``：real page-fault gate要等
``cpu_init`` 建好TSS/IST之后，当前memory initialization仍依赖第039章的
``early_make_pgtable`` handler。

所以这一步不是“安装一张完全不同且完整的最终IDT”。普通external IRQ gates、IST版本的NMI/
DF/MC和最终page-fault entry仍未就绪，IF也没有打开。

``early_cpu_init`` 建立boot CPU最小能力描述
------------------------------------------

下一条调用初始化compiled-in CPU vendor表，然后对 ``boot_cpu_data`` 执行
``early_identify_cpu``。有CPUID时，它读取vendor、family/model、capabilities与physical/virtual
address sizes，解析CPU相关early options，建立early topology，并运行vendor的early/BSP hooks；
最终把boot CPU index固定为0。

这正是前面 ``x86_phys_bits=MAX_PHYSMEM_BITS`` 被实际CPU address-size结果收紧的边界。QEMU
``-cpu`` model和kernel config未固定，所以正文不制造family、model、NX、MTRR或physical-bit
具体数值；但从这里以后， ``boot_cpu_data`` 已足够支持本批后续的NX、APIC、E820 resource-end与
cache决策。

static key/call必须早于会使用它们的arch路径
----------------------------------------------

控制流继续：

.. code-block:: c

   jump_label_init();
   static_call_init();
   early_ioremap_init();

前两项先修正built-in jump-label与static-call sites，使接下来的x86探测可以安全经过相关分支。
generic ``start_kernel`` 在 ``setup_arch`` 返回后还会再次调用这两个公开入口；初始化实现必须处理
重复入口，不能据此想象本章执行了两遍当前代码。

``early_ioremap_init`` 建立完整vmalloc/ioremap之前的临时mapping slots。后续读取setup_data、
firmware table或其他不宜直接解引用的physical range时，可以短时map/unmap；它不把所有E820 RAM
加入direct map，也不是普通ioremap allocator已经可用。

``parse_boot_params`` 只翻译已复制的boot protocol对象
------------------------------------------------------

``parse_boot_params()`` 不回到GRUB或BIOS取数据。它从global ``boot_params`` 建立：

* 由 ``hdr.root_dev`` decode的 ``ROOT_DEV``；
* ``screen_info`` 与条件EDID对应的primary display描述；
* ``saved_video_mode``；
* 组合 ``type_of_loader/ext_loader_type`` 与扩展version后的bootloader type/version；
* 条件ramdisk兼容字段；
* EFI loader signature flags；
* ``root_flags==0`` 时对初始 ``root_mountflags`` 的可写调整。

当前loader是GRUB，但 ``type_of_loader`` 表示Linux boot-protocol loader身份，不表示SATA设备或
root filesystem类型。SeaBIOS加GRUB i386-pc没有写EFI loader signature，所以
``EFI_BOOT`` 不会在这里置位。命令行里的 ``root=``、 ``ro`` 与 ``console=`` 仍要由后续参数
解析，不在 ``parse_boot_params`` 内消费。

ordinary PC的OEM arch hook为空
------------------------------

``setup_olpc_ofw_pgd()`` 在当前非OLPC路径不改页表，随后
``x86_init.oem.arch_setup()`` 调用fixed ordinary PC默认 ``x86_init_noop``。某些平台能在这里替换
hook，但当前q35没有产生新的OEM对象或额外reservation。

先写 ``memblock.reserved``，再提供 ``memblock.memory``
------------------------------------------------------

下一条关键调用：

.. code-block:: c

   early_reserve_memory();

此时memblock的reserved集合已经能记录区间，E820 RAM却还没有批量进入
``memblock.memory``。顺序刻意如此：如果先允许allocator看到全部RAM，再补记kernel、initramfs
与setup data，中间的任何allocation都可能覆盖仍在使用的boot object。

整个调用期间仍只有CPU0、IF=0，没有另一CPU或interrupt allocator与它竞争；这里依赖single-
threaded early-boot顺序，而不是后期buddy/slab锁域。

kernel reserve范围不是任意整个解压区
-------------------------------------

第一项：

.. code-block:: c

   memblock_reserve_kern(__pa_symbol(_text),
                         __end_of_kernel_reserve - _text);

它保留正式kernel从物理 ``_text`` 到 ``__end_of_kernel_reserve`` 的linked reserve范围。这个范围
覆盖链接脚本指定的early不可回收内容，但 ``__end_of_kernel_reserve`` 之后的section不会自动
因为“属于vmlinux”而被纳入；需要保留者必须另有显式reserve。

这份memblock identity与E820 type不同。firmware/GRUB仍可能把kernel所在区写作RAM；reserved
overlay负责让后续allocator从RAM候选中排除它。

最低64 KiB无条件进入reserved
------------------------------

接着：

.. code-block:: c

   memblock_reserve(0, SZ_64K);

这同时覆盖page 0安全边界与历史BIOS可能破坏low memory的保守区间。它不是“已经保留整个低
1 MiB”；real-mode trampoline定位后还有更宽的low-memory处理。当前也没有在这一步读取E820
并把类型改成reserved。

initramfs保留R到page-aligned end
--------------------------------

``early_reserve_initrd`` 从setup header的low/high字段重组 ``R`` 和真实size ``N``，并检查
loader type、start与size非0。固定GRUB路径满足条件，因此执行：

.. code-block:: text

   memblock_reserve_kern(R, PAGE_ALIGN(R + N) - R)

这只保护initramfs原始physical bytes不被allocator覆盖。 ``initrd_start/initrd_end`` 尚未形成
长期direct-map virtual identity，也没有搬迁、解压或解析cpio；这些都不是early reserve的效果。

当前 ``setup_data=0``，不会虚构扩展链
--------------------------------------

``memblock_x86_reserve_range_setup_data`` 从 ``boot_params.hdr.setup_data`` 遍历linked nodes，
通常会reserve每个header+payload，并为合法indirect node再reserve目标range。

固定GRUB 2.14 i386-pc loader先清零整个 ``linux_params``，再复制setup header和显式填写的字段；
本场景没有创建setup_data node，因此第039章复制来的 ``hdr.setup_data=0``。当前while loop一次也
不进入，没有 ``SETUP_E820_EXT``、DTB、EFI、IMA、KHO或RNG seed对象凭空出现。

这并不是Linux不支持这些node，而是当前GRUB handoff没有交出它们。

PC policy现在才读取BDA/EBDA并保留BIOS区
---------------------------------------

第040章设置的 ``reserve_bios_regions=1`` 在这里由 ``reserve_bios_regions()`` 消费。它通过
direct-map读取BDA ``0x413`` 的conventional-memory KiB值，限制到128—640 KiB可信区间，再读取
EBDA segment pointer；若EBDA起点更低且合理，就把它作为 ``bios_start``。最终：

.. code-block:: c

   memblock_reserve(bios_start, 0x100000 - bios_start);

因此这项reservation的精确start来自运行时BDA/EBDA内容，不由“q35”三个字符制造。无论start
取何合法值，它都只写memblock reserved，不替代第042章对working E820的BIOS range修整。

最后的 ``trim_snb_memory`` 先早期读取PCI ``00:02.0`` vendor/device；只有命中列出的Intel
Sandy Bridge graphics IDs时，才额外reserve五个已知bad pages。fixed机器只规定q35与AHCI，
没有固定display device/QEMU完整CLI，所以该quirk保持运行时条件，不能写成必然命中或必然未
执行。

Z没有出现在reservation清单中
------------------------------

至此被显式保护的是kernel、0—64 KiB、R/N、非空setup_data targets、BIOS low region与条件SNB
pages。原始boot params Z和其旧command-line buffer没有被reserve；039已把二者复制到formal
kernel globals，所以后续 ``e820__memblock_setup`` 可以把其RAM重新交给系统。

“Z可被重用”不表示本章此刻已经发生覆盖： ``memblock.memory`` 仍未从E820建立，allocator还没
得到那片候选RAM。

physical address resource上界在E820导入前确定
---------------------------------------------

``early_cpu_init`` 已识别CPU address size，源码现在设置：

.. code-block:: c

   iomem_resource.end = (1ULL << boot_cpu_data.x86_phys_bits) - 1;

这是全局physical I/O-memory resource tree的address上界，不是RAM大小，也不表示上界内每个地址
可用。实际RAM topology由下一条E820 import给出。

基础E820先进入working table，再复制两份快照
---------------------------------------------

ordinary PC的 ``x86_init.resources.memory_setup`` 默认指向
``e820__memory_setup_default``。fixed GRUB已在 ``boot_params.e820_table`` 提供非空、有效的
SeaBIOS memory map，因此default helper逐项append address/size/type，随后
``e820__update_table`` 排序、处理overlap并合并可合并range；不走 ``alt_mem_k/ext_mem_k`` 的
fallback map。

返回后 ``e820__memory_setup`` 立即把整理后的working ``e820_table`` 整体复制为：

.. code-block:: text

   e820_table_firmware
   e820_table_kexec

并打印BIOS-provided map。三者此刻内容相同，但职责不同：firmware表保持loader原图；kexec表供
后续kernel handoff使用并只接受特定修正；working表还会被command-line、BIOS trim、MTRR等
继续修改。

E820中的RAM identity不会抹掉先前reserved集合。K、R和Z都可能仍落在
``E820_TYPE_RAM`` range中；其中K/R由memblock reserved排除，Z没有这份排除。两套结构表达的是
不同问题。

``parse_setup_data`` 当前循环为空
---------------------------------

紧接着的 ``parse_setup_data()`` 再从 ``hdr.setup_data`` 遍历扩展链。若存在
``SETUP_E820_EXT``，它会append超过boot_params前128项的E820 entries，update working table并
刷新firmware/kexec快照；其他type可交给DTB、EFI、IMA、KHO或RNG seed helper。

当前链头为0，所以这些switch branch全部未选择，三份E820表保持基础import后的状态。正文只能
说明这些是未发生的支持路径，不能用一页node百科替代当前时间线。

EDD copy是最后一个build条件步骤
--------------------------------

本章最后执行 ``copy_edd()``。启用 ``CONFIG_EDD`` 或module support时，它把
``boot_params`` 中MBR signature buffer、EDD info和entry counts复制到kernel-owned ``edd``
对象；否则是空inline。它不读磁盘、不提交AHCI command，也不修改E820。

下一条调用已经是：

.. code-block:: c

   setup_initial_init_mm(_text, _etext, _edata, (void *)_brk_end);

本章在call前停止。此刻E820只是x86 early memory description，仍未由
``e820__memblock_setup`` 转换成 ``memblock.memory``。

本章结束状态
------------

* current executor：CPU0上的 ``setup_arch``， ``copy_edd()`` 已返回，
  ``setup_initial_init_mm(...)`` 尚未调用；
* CPU/mode：BSP/logical CPU0，64-bit long mode，IF=0；没有schedule或AP bring-up；
* bootloader command line：
  ``BOOT_IMAGE=/boot/bzImage root=/dev/sda1 ro console=ttyS0``；
* effective ``boot_command_line`` / x86 ``command_line``：已按build-time
  ``CONFIG_CMDLINE`` 保留、前置追加或覆盖；因 ``.config`` 未固定而保持条件值；
* IDT： ``#DB/#BP`` 与条件 ``#VE`` 已换early trap； ``#PF`` 仍为039的early page-table
  helper；普通IRQ/IST IDT未完成；
* ``boot_cpu_data``：已做early identify并获得运行CPU address sizes/capabilities，具体model值未
  固定；
* memblock reserved：kernel reserve范围、0—64 KiB、R到 ``PAGE_ALIGN(R+N)``、BIOS low range，
  以及条件SNB pages；
* setup_data：链头0，无node被reserve或parse；
* old boot data Z/旧command buffer：未reserve，formal global copies已接管内容；
* E820：基础map已sanitize，working/firmware/kexec三表已建立且当前相同；
* ``memblock.memory``：尚未从E820填充；
* ``iomem_resource.end``：已按boot CPU physical-address bits设置；kernel child resources尚未插入；
* initramfs：R/N受保护，未relocate、未unpack；
* ``init_mm``：静态对象存在，但本章尚未填写start/end/brk字段，也未切换CR3。

关键边界
--------

#. 第一条日志打印GRUB字符串，built-in append/override随后发生；两者不能混成一个“固定命令行”。
#. ``x86_phys_bits`` 先取架构上界，再由 ``early_cpu_init`` 的CPUID结果收紧。
#. ``idt_setup_early_traps`` 不在x86-64替换 ``#PF``，否则early direct-map自举会被提前拆掉。
#. ``early_reserve_memory`` 先写reserved；E820 RAM转 ``memblock.memory`` 要到043。
#. kernel reservation止于 ``__end_of_kernel_reserve``，不是凭印象保留任意解压输出区。
#. initramfs这里只reserve R/N，未获得长期virtual identity，更没有unpack。
#. 当前 ``setup_data=0``；Linux支持扩展node不等于这次实际收到node。
#. BIOS memblock reservation与042 working-E820 trim是两个不同边界。
#. Z明确不reserve；copy完成后的可重用性是设计行为，不是遗漏。
#. E820 working/firmware/kexec三表先复制相同内容，后续修改规则不同。
#. E820把一段标作RAM与memblock把同一区间列为reserved可以同时成立。

下一入口
--------

第042章从：

.. code-block:: c

   setup_initial_init_mm(_text, _etext, _edata, (void *)_brk_end);

开始。CPU当前CR3仍是 ``early_top_pgt``； ``init_mm.pgd`` 静态指向x86-64
``init_top_pgt``，但调用只会登记kernel virtual boundaries，不会在入口瞬间load CR3。

资料
----

* `Linux 7.2-rc1固定提交：setup_arch命令行至init_mm边界 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c#L884-L968>`_；
* `Linux 7.2-rc1固定提交：parse_boot_params与setup_data reserve <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c#L479-L606>`_；
* `Linux 7.2-rc1固定提交：early_reserve_memory精确清单 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c#L796-L826>`_；
* `Linux 7.2-rc1固定提交：initramfs early reservation <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c#L293-L360>`_；
* `Linux 7.2-rc1固定提交：PC BDA/EBDA BIOS reservation <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/ebda.c#L51-L98>`_；
* `Linux 7.2-rc1固定提交：基础E820导入与三表复制 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/e820.c#L1231-L1286>`_；
* `Linux 7.2-rc1固定提交：early trap只替换DB/BP/条件VE <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/idt.c#L59-L76>`_；
* `GRUB 2.14固定提交：linux_params清零与setup header装入 <https://github.com/rhboot/grub2/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/loader/i386/linux.c#L796-L837>`_。
