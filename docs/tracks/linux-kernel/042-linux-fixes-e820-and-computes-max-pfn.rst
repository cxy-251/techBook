第四十二章：Linux 怎样修正 E820 并计算自己真正能管理的物理页？
================================================================

第四十一章结束时，CPU0仍在 ``setup_arch`` 内、IF=0；x86有效command line已经形成，基础E820
已导入working/firmware/kexec三表，kernel、initramfs与BIOS low range也已写入
``memblock.reserved``。但 ``memblock.memory`` 仍为空，CPU的CR3仍指向 ``early_top_pgt``。

当前下一条调用是：

.. code-block:: c

   setup_initial_init_mm(_text, _etext, _edata, (void *)_brk_end);

本章沿fixed Linux 7.2-rc1继续到 ``early_alloc_pgt_buf()`` 第一条语句尚未执行。自然边界内，
Linux建立 ``init_mm`` 的kernel范围，解析一次early parameters，修整working E820与resource tree，
计算 ``max_pfn/max_possible_pfn/max_low_pfn``，但不提前完成第043章的memblock RAM导入或direct
map建立。

``init_mm`` 只登记kernel virtual boundaries
----------------------------------------------

``init_mm`` 是静态 ``mm_struct``，初始 ``pgd=swapper_pg_dir``；在x86-64中
``swapper_pg_dir`` 是 ``init_top_pgt`` 的宏别名。它还带静态初始化的 ``mm_users=2``、
``mm_count=1``、maple tree与锁对象。

当前函数只写四个字段：

.. code-block:: c

   init_mm.start_code = (unsigned long)_text;
   init_mm.end_code   = (unsigned long)_etext;
   init_mm.end_data   = (unsigned long)_edata;
   init_mm.brk        = (unsigned long)_brk_end;

这些值是kernel virtual addresses，用来描述内核代码、数据与当前early brk边界。调用没有增加
``mm_users/mm_count``，没有创建PID 1的用户mm，也没有执行 ``load_cr3(init_top_pgt)``；CPU继续用
``early_top_pgt``，而 ``init_mm.pgd`` 只是指向正在逐步准备的长期root。

NX capability先进入supported PTE mask
--------------------------------------

下一步 ``x86_configure_nx()`` 检查第041章early CPU identify得到的
``X86_FEATURE_NX``：支持时把 ``_PAGE_NX`` 加入 ``__supported_pte_mask``，不支持时清掉。

这个顺序刻意早于early parameter parsing。某些early option可能建立debug console/fixmap并写
PTE；page-table code必须先知道hardware是否接受NX bit。配置或CPU不支持NX不会在这里凭空增加
能力，稍后的 ``x86_report_nx`` 只报告结果。

``parse_early_param`` 在整个boot中只真正执行一次
-----------------------------------------------

``setup_arch`` 现在调用：

.. code-block:: c

   parse_early_param();

helper先检查静态 ``done``，当前首次调用时把有效 ``boot_command_line`` 复制进临时buffer，再把
每个注册为 ``early_param`` 的option送入对应callback，最后设置 ``done=1``。因此
``setup_arch`` 返回后generic ``start_kernel`` 虽然还会在源码中再次调用同一函数，第二次会在
``if (done) return`` 立即结束，并不会把 ``mem=`` 或 ``memmap=`` 应用两遍。

固定GRUB字符串本身只有 ``BOOT_IMAGE``、 ``root``、 ``ro`` 与 ``console``，没有 ``mem`` /
``memmap``。但最终 ``.config`` 未固定，built-in ``CONFIG_CMDLINE`` 可能在第041章追加或覆盖，
所以working E820是否成为user-defined仍保持build条件：

* 没有额外memory option时，working表保持firmware map；
* ``mem=`` 可移除给定上界以上的RAM；
* ``memmap=`` 可清空为exact map、增加/删除range或改变type；
* malformed callback会警告；最终表无法sanitize时后续收尾panic。

这正是本章不写死RAM容量或PFN数值的原因，不影响固定函数顺序本身。

BIOS路径跳过两段EFI处理
------------------------

第一次条件：

.. code-block:: c

   if (efi_enabled(EFI_BOOT))
       efi_memblock_x86_reserve_range();

第041章已确认SeaBIOS/GRUB i386-pc没有EFI loader signature，条件为假，不从EFI memory map增加
reserved ranges。稍后 ``e820__finish_early_params`` 之后的 ``efi_init()`` 条件也同样为假。

这两个skip只说明当前boot interface是BIOS，不表示fixed kernel一定没有编译EFI支持。

APIC static calls先准备，但IF仍为0
---------------------------------

``x86_report_nx`` 先按boot CPU能力记录NX active或missing。随后
``apic_setup_apic_calls`` 把当前APIC driver的EOI、read/write、IPI与secondary-wakeup operations
更新进static-call sites。

``acpi_mps_check`` 只在特定build组合中因ACPI IRQ路径不可用且未编入MP parser而返回nonzero；
若发生，源码把 ``apic_is_disabled`` 置true并清 ``X86_FEATURE_APIC``。当前q35固件具备前面章节
已核验的ACPI/MP资料，但kernel config与有效early options仍决定最终选择，因此正文记录条件分支，
不把APIC mode提前写死。

无论分支结果如何，本章没有设置IF=1，没有安装normal external IRQ gates，也没有启动local APIC
timer。

``e820__finish_early_params`` 只收尾user-defined表
--------------------------------------------------

如果 ``mem``/``memmap`` callback设置了 ``userdef``，
``e820__finish_early_params`` 对working ``e820_table`` 执行一次update/sanitize；失败直接panic，
成功则打印user-defined map。没有user-defined option时它是no-op。

第041章保存的 ``e820_table_firmware`` 不随这些用户限制修改； ``e820_table_kexec`` 也不是对每次
working-table edit做机械镜像。这样当前kernel可以在working表上限制自己，又保留供hibernation/
kexec使用的loader视图。

iBFT、DMI、hypervisor、TSC与ROM依次探测
----------------------------------------

EFI skip之后，源码顺序固定为：

.. code-block:: c

   reserve_ibft_region();
   x86_init.resources.dmi_setup();
   init_hypervisor_platform();
   tsc_early_init();
   x86_init.resources.probe_roms();

各项都不能被标题压缩成“平台初始化完成”：

* 编入iBFT finder时，BIOS路径扫描规定的low-memory range；只有发现有效 ``iBFT/BIFT`` signature
  与未越过1 MiB的length，才写 ``ibft_phys_addr`` 并reserve page-aligned table；否则没有新对象；
* ordinary PC的DMI hook读取SeaBIOS提供的SMBIOS/DMI entry与records，建立后续quirk可查询的
  identity；具体字段来自firmware table，不由kernel猜测；
* hypervisor helper遍历compiled-in detectors，只有某项返回最高非0priority才复制其init/runtime
  callbacks并执行platform init；QEMU是否通过选定 ``-cpu`` 暴露hypervisor身份未固定，不能把
  “运行在QEMU进程里”直接等同于某个Linux paravirt backend已选中；
* ``tsc_early_init`` 只有CPU声明TSC且early frequency determination成功时，才设置early
  sched-clock/cyc2ns状态；失败会留给后续 ``tsc_init`` 重试；
* ``probe_roms`` 按ordinary PC hook扫描并登记legacy ROM ranges；它不执行一遍Option ROM，也不
  再回到SeaBIOS。

这些调用可能使用early remap和memblock reserve，却仍没有把E820 RAM填入
``memblock.memory``。

kernel四段进入 ``iomem_resource`` tree
---------------------------------------

``setup_kernel_resources`` 用physical symbol conversion填写四个resource：

.. code-block:: text

   Kernel code    [_text,          _etext - 1]
   Kernel rodata  [__start_rodata, __end_rodata - 1]
   Kernel data    [_sdata,         _edata - 1]
   Kernel bss     [__bss_start,    __bss_stop - 1]

然后依次 ``insert_resource(&iomem_resource, ...)``。resource tree用自己的lock保护结构，但当前仍
是CPU0/IF=0的无并发插入。它服务 ``/proc/iomem``、debug/kdump等物理资源关系，不是页分配器；
插入resource不会等价为memblock reserve，也不会创建PTE。

kernel E820修复与kernel memblock reservation不是一件事
-----------------------------------------------------

``e820_add_kernel_range`` 检查physical ``[_text,_end)`` 是否全部标作
``E820_TYPE_RAM``。正常GRUB map覆盖时直接返回；如果firmware或user exactmap把kernel落点排除，
它警告、删除该范围现有working entries并重新加为RAM，让后续MM至少能管理正在运行的image。

这一步检查到 ``_end``，而第041章memblock reserve止于 ``__end_of_kernel_reserve``；E820 type
修复和不可分配reservation具有不同endpoint与用途，不能相互替代。若机器真的把kernel放在非RAM
硬件上，源码也只说明系统很可能稍后crash，并没有证明修表能修复hardware。

BIOS range在working E820上单独修整
----------------------------------

``trim_bios_range`` 先把working E820中page 0覆盖的RAM改为reserved，再从RAM entries删除
``[BIOS_BEGIN,BIOS_END)``，即640 KiB到1 MiB，最后update/sanitize working table。

第041章已经在memblock reserved记录0—64 KiB及BDA/EBDA推导的 ``[bios_start,1MiB)``。现在的
E820修整回答“哪些range继续被视为RAM”；前章reservation回答“allocator必须避开什么”。两步即使
覆盖范围相近也不能删掉其一。

x86-64 GART检查是条件E820 mutation
----------------------------------

32-bit特有PPro hole路径在当前build不编译；x86-64执行 ``early_gart_iommu_check``。它首先要求
AMD GART存在且允许early PCI access，随后才检查aperture register一致性，并可能把遗留/冲突GART
range从RAM改为reserved。

fixed q35 storage topology不固定QEMU CPU vendor与全部PCI设备，所以这里仍保留runtime条件；若
working E820被修正，接下来的PFN计算自然使用修正后的表。

``max_pfn`` 来自working E820而不是RAM字节数除法
-------------------------------------------------

源码现在执行：

.. code-block:: c

   max_pfn = e820__end_of_ram_pfn();

helper只考虑type为 ``E820_TYPE_RAM`` 或 ``E820_TYPE_ACPI`` 的entry，计算exclusive end对应的
PFN，取所有候选最大值，并限制到 ``MAX_ARCH_PFN``。它给出内核需要覆盖的最高page-frame边界，
不是可分配page数量：中间可能有reserved holes，kernel/initramfs也仍处于reserved overlay。

entry末尾不足一整页时， ``(addr+size)>>PAGE_SHIFT`` 不把尾部残片算作可管理完整frame。最终数值
依赖fixed机器RAM容量、可能的built-in ``mem/memmap``、BIOS/GART修整，当前条件不足以给出一个
诚实的十六进制常量。

MTRR/cache修整后可能必须重算
------------------------------

``cache_bp_init`` 建立boot CPU的cache/MTRR early state。随后：

.. code-block:: c

   if (mtrr_trim_uncached_memory(max_pfn))
       max_pfn = e820__end_of_ram_pfn();

只有MTRR policy实际从working E820裁掉non-WB RAM时才重算。QEMU CPU model、MTRR exposure与
kernel config未固定，所以本章记录“最多一次条件重算”，不宣称一定裁内存，也不把首次
``max_pfn`` 当作不可改变。

最终值随后复制给：

.. code-block:: c

   max_possible_pfn = max_pfn;

这是当前arch可管理physical-frame上界的快照；它仍不是 ``memblock.memory`` 已经产生。

memory KASLR只先选择virtual layout
-----------------------------------

``kernel_randomize_memory()`` 必须在 ``max_pfn`` 已知、各memory region base被使用之前调用。
关闭 ``CONFIG_RANDOMIZE_MEMORY`` 时是空inline；启用时先设direct-map可表达的physical end，并在
memory KASLR实际开启时，根据 ``max_pfn``、4/5-level paging、vmalloc/vmemmap需求和entropy调整：

.. code-block:: text

   page_offset_base
   vmalloc_base
   vmemmap_base
   direct_map_physmem_end

它随机化的是physical direct-map、vmalloc与vmemmap的virtual layout，不是第036—037章kernel
image的physical output O，也没有在这一调用里遍历E820建立全部page tables。

``max_low_pfn`` 与x2APIC状态在页表buffer前固定
-----------------------------------------------

x86-64先调用 ``check_x2apic``：若hardware已启用x2APIC，记录mode/state并切换APIC ops；若CPU不
具备feature则标disabled；没有编入x2APIC支持但hardware已开时，还可能禁用APIC并警告。这里仍
只选择状态，不开启maskable interrupts。

随后：

.. code-block:: c

   if (max_pfn > (1UL << (32 - PAGE_SHIFT)))
       max_low_pfn = e820__end_of_low_ram_pfn();
   else
       max_low_pfn = max_pfn;

如果内存边界越过4 GiB，helper只在4 GiB限制内从RAM/ACPI entries求end PFN；否则low与total相同。
``max_low_pfn_mapped`` 是“当前direct map实际覆盖到哪里”的另一个变量，本章没有把它偷换成
``max_low_pfn``。

最后 ``x86_init.mpparse.find_mptable()`` 运行ordinary PC MP-table finder。编入MP parser并找到
合法floating pointer/config table时，它把相关low-memory bytes加入memblock reserved；找不到则
返回，不会伪造table。前面SeaBIOS资料存在也不改变“由当前build hook执行扫描”的源码边界。

下一条就是：

.. code-block:: c

   early_alloc_pgt_buf();

本章停在call之前。early brk仍未封存， ``init_top_pgt`` 尚未成为active CR3，E820 RAM也尚未
转换为memblock memory。

本章结束状态
------------

* current executor：CPU0上的 ``setup_arch``，即将调用 ``early_alloc_pgt_buf()``；callee尚未
  执行；
* CPU/mode：BSP/logical CPU0，64-bit long mode，IF=0；无schedule、无AP bring-up；
* active CR3：仍为 ``early_top_pgt``；
* ``init_mm``： ``pgd=init_top_pgt``，start_code/end_code/end_data/brk已登记；静态引用计数未因
  本次调用变化；
* NX： ``__supported_pte_mask`` 已按boot CPU capability设置并报告；
* early parameters：已真正解析一次， ``done=1``；generic后续同名调用将直接返回；
* EFI：BIOS路径未执行EFI range reserve或 ``efi_init``；
* E820 firmware/kexec snapshots：保留loader视图；working表已接受条件early parameters、kernel
  range fix、BIOS trim、条件GART/MTRR修整；
* resource tree：kernel code/rodata/data/bss及条件ROM资源已登记；
* ``max_pfn`` / ``max_possible_pfn`` / ``max_low_pfn``：已从最终到此处的working E820计算，具体
  数值因RAM/build/runtime条件保持符号值；
* memory KASLR layout：按build/runtime选择完成或no-op；direct-map page tables尚未据此建立；
* APIC/x2APIC、hypervisor、TSC、DMI/iBFT/MP-table：按build/runtime完成本阶段探测与必要reserve；
* memblock reserved：继承041并可能增加iBFT/MP等range；
* ``memblock.memory``：仍未从E820填充；
* initramfs：R/N继续reserved，未relocate、未unpack；
* early brk/page-table buffer：brk仍开放， ``early_alloc_pgt_buf`` 尚未取页。

关键边界
--------

#. ``setup_initial_init_mm`` 只写virtual boundaries； ``init_mm.pgd`` 指向init_top不等于CR3已切换。
#. NX mask必须早于可能建立PTE的early option；report不创造feature。
#. ``parse_early_param`` 由静态 ``done`` 保证只执行一次，generic第二次调用不是重复应用参数。
#. GRUB字符串无 ``mem/memmap``，但built-in command line未固定；working E820的用户修正必须保留
   条件边界。
#. firmware/kexec快照与working E820在early parameters和quirks后可以分离。
#. iomem resource、E820 type和memblock reserved是三套不同identity，任何一套都不等于已建PTE。
#. ``e820_add_kernel_range`` 检查到 ``_end``；kernel memblock reserve止于
   ``__end_of_kernel_reserve``。
#. max PFN helper考虑RAM与ACPI end并受架构上界限制；它不是可分配页计数。
#. MTRR trim有返回值时才重算max PFN；不能把第一次结果提前冻结。
#. memory KASLR选择virtual bases，不是再次搬kernel，也不建立完整direct map。
#. ``max_low_pfn`` 与 ``max_low_pfn_mapped`` 含义不同。
#. 本章精确停在 ``early_alloc_pgt_buf`` 前；memblock RAM导入属于043。

下一入口
--------

第043章从fixed ``arch/x86/mm/init.c``：

.. code-block:: c

   void __init early_alloc_pgt_buf(void)
   {
       unsigned long tables = INIT_PGT_BUF_SIZE;
       phys_addr_t base;
       base = __pa(extend_brk(tables, PAGE_SIZE));
       ...

开始。进入前early brk仍可扩展， ``max_pfn`` 与memory-layout bases已经确定，
``memblock.reserved`` 有效而 ``memblock.memory`` 尚未由E820建立。

资料
----

* `Linux 7.2-rc1固定提交：setup_arch从init_mm到early page-table buffer <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c#L968-L1066>`_；
* `Linux 7.2-rc1固定提交：init_mm静态对象与boundary赋值 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/init-mm.c#L20-L60>`_；
* `Linux 7.2-rc1固定提交：early parameter一次性done边界 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L720-L755>`_；
* `Linux 7.2-rc1固定提交：working/firmware/kexec E820职责 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/e820.c#L22-L64>`_；
* `Linux 7.2-rc1固定提交：E820 RAM/ACPI end-PFN计算 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/e820.c#L857-L904>`_；
* `Linux 7.2-rc1固定提交：kernel resource与BIOS/E820 range修整 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c#L665-L794>`_；
* `Linux 7.2-rc1固定提交：memory KASLR依赖max_pfn选择virtual layout <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/kaslr.c#L43-L124>`_；
* `Linux 7.2-rc1固定提交：early page-table buffer下一入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/init.c#L170-L197>`_。
