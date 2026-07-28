第五十五章：Linux怎样把 ``memblock`` 中的空闲内存交给伙伴系统？
================================================================

第五十四章结束时，CPU0仍在内核态执行 ``start_kernel()``，当前任务仍是 ``init_task``，
``IF=0``。命令行与初始化参数已经分派完毕，内存节点、内存区域和 ``struct page`` 等描述结构也已存在，
但是普通空闲内存还没有进入伙伴系统。当前控制流依次执行：

.. code-block:: c

   random_init_early(command_line);
   setup_log_buf(0);
   vfs_caches_init_early();
   sort_main_extable();
   trap_init();
   mm_core_init();

本章按照Linux 7.2-rc1固定提交追踪到 ``mm_core_init()`` 执行完毕。最重要的所有权变化发生在
``memblock_free_all()``：在它之前， ``memblock`` 仍负责记录普通空闲内存；在它之后，这些页面
进入伙伴系统， ``SLUB`` 和 ``vmalloc`` 才能建立运行期分配基础。

早期随机初始化混入哪一份命令行
------------------------------

``random_init_early(command_line)`` 运行时，中断和完整计时系统都尚未启用。启用
``LATENT_ENTROPY_PLUGIN`` 时，函数先混入编译期种子，然后反复尝试
``arch_get_random_seed_longs()``；硬件无法继续提供种子时，再尝试
``arch_get_random_longs()``。每个都未取得数据的位置只会减少可计入的位数，内核不会把空缺位置
当成熵。

随后，函数混入 ``init_utsname()`` 以及参数 ``command_line`` 指向的字符串。这一字符串是
``setup_arch()`` 交回的架构命令行，不包含第五十一章通过 ``bootconfig`` 另行加入的内核参数或
初始化参数。
因此，保存后用于显示的完整命令行、实际参数分派顺序与这里的随机池输入不能混为一谈。

如果随机数生成器此前已经就绪，函数调用 ``crng_reseed()``；否则只有 ``trust_cpu`` 为真时才把
取得的架构随机位计入初始化位数。函数执行结束不保证随机数生成器已经就绪，也不代表稍后加入
时间戳的 ``random_init()`` 已经执行。

日志缓冲区先启用正式的每CPU数据
------------------------------

``setup_log_buf(0)`` 首先执行 ``set_percpu_data_ready()``，使日志子系统可以使用第五十二章建立的正式
每CPU区域。架构阶段若已经把 ``log_buf`` 从静态数组切换到动态缓冲区，本次执行到这里便结束，
不会再次分配。

仍在使用静态缓冲区时，如果命令行没有要求新的长度， ``log_buf_add_cpu()`` 会根据
``cpu_possible_mask`` 中的CPU数量
判断是否需要扩大。最终仍不需要扩大时，函数只输出一次缓冲区占用统计。需要扩大时，它依次从
``memblock`` 分配文本区、描述符数组和 ``printk_info`` 数组；任一分配失败都会释放本次已经取得
的区域，并继续保留原有静态缓冲区。

三个区域全部分配成功后，函数初始化 ``printk_rb_dynamic``，在保存本地中断状态的区间内迁移静态
记录并切换全局指针。切换后，它再复制迁移期间可能由NMI写入静态缓冲区的尾部记录。这里没有注册
控制台驱动，分配失败也不会触发 ``panic()``。

VFS哈希表是否在这里分配取决于 ``hashdist``
-----------------------------------------

``vfs_caches_init_early()`` 先初始化固定的 ``in_lookup_hashtable``，然后调用
``dcache_init_early()`` 和 ``inode_init_early()``。两项调用都先检查 ``hashdist``：

* ``hashdist=false`` 时，函数通过 ``alloc_large_system_hash()`` 从早期分配器取得目录项和索引节点哈希表；
* ``hashdist=true`` 时，两项函数直接结束，把哈希表分配推迟到 ``vfs_caches_init()``，届时可以利用
  已建立的 ``vmalloc`` 空间在多个NUMA内存节点之间分布内存。

在64位NUMA构建中， ``hashdist`` 初始为真；如果前面的内存初始化只发现一个拥有内存的节点，
``fixup_hashdist()`` 会把它改为假。第五十四章解析的 ``hashdist=`` 也可能改变结果。由于本书没有固定
最终 ``.config``、NUMA拓扑和该参数，本章必须保留这两条路径。

无论选择哪条路径，这里都没有分配目录项或索引节点对象，也没有挂载文件系统。静态的
``init_fs``、 ``init_files`` 等启动对象已经存在，因此不能笼统地说“系统中不存在VFS对象”；
能够确定的是运行期VFS对象缓存、根挂载和初始内存盘解包尚未开始。

主内核异常表只在需要时排序
--------------------------

``sort_main_extable()`` 同时检查 ``main_extable_sort_needed`` 和主异常表是否非空。构建工具没有提前
排序且表中存在记录时，内核才按故障指令地址排序 ``__ex_table``；已经排序或空表时不执行任何操作。
模块和BPF拥有各自的异常表生命周期，这次调用不处理它们，也不会主动触发异常。

x86陷阱初始化仍然保持IF为0
--------------------------

x86的 ``trap_init()`` 先建立CPU入口区域，再按运行环境初始化SEV-ES的GHCB/VC处理页。接着，
``cpu_init_exception_handling(true)`` 建立启动CPU的TSS和IST条件；不使用FRED时，
``idt_setup_traps()`` 安装正式异常入口，最后 ``cpu_init()`` 完成启动CPU的相关状态。

早期IDT此前已经能够处理启动故障，本次调用建立的是运行期异常基础。它不执行 ``init_IRQ()``，
不设置 ``IF``，也不会让设备中断进入内核；SEV、FRED和虚拟化分支仍由实际CPU与构建配置决定。

内存管理核心先完成仍依赖 ``memblock`` 的准备
-----------------------------------------

``mm_core_init()`` 首先调用x86-64的 ``arch_mm_preinit()``，进入 ``pci_iommu_alloc()``。该函数根据
已经探测到的IOMMU类型准备所需内存，不能仅凭q35机器类型断言具体分支。随后
``init_zero_page_pfn()`` 取得 ``ZERO_PAGE(0)`` 对应的PFN，为以后共享只读零页提供标识；此时没有
创建任何用户映射。

``build_all_zonelists(NULL)`` 为所有内存节点建立内存区域回退顺序，为
``cpu_possible_mask`` 中的CPU初始化启动期 ``pageset`` 和 ``zonestat``，并设置当前任务允许使用的
内存节点。此时伙伴系统的搜索结构已经具备，普通空闲页仍未进入空闲链表。
``page_alloc_init_cpuhp()`` 通过 ``cpuhp_setup_state_nocalls()`` 注册页面分配器的CPU上线和下线
处理函数，不会为已经在线的CPU0
补执行一次回调。

接下来的 ``alloc_tag_sec_init()``、 ``page_ext_init_flatmem()``、
``mem_debugging_and_hardening_init()``、 ``kfence_alloc_pool_and_metadata()``、
``kmsan_init_shadow()`` 与 ``stack_depot_early_init()`` 按构建配置准备分配标签、页面扩展信息、
初始化清零策略、KFENCE、KMSAN和栈记录存储。关闭相应配置时，这些入口可能为空操作；正文不能把
其中任何可选设施写成必然启用。

KHO必须在伙伴系统接管前处理
---------------------------

``kho_memory_init()`` 处理 ``kexec`` 接管时需要保留的内存以及暂存区域。源码要求它在
``memblock`` 仍可用时执行，并尽量靠近伙伴系统初始化；未启用KHO时，该入口为空操作。

随后， ``memblock_free_all()`` 依次执行：

.. code-block:: text

   free_unused_memmap()
   → reset_all_zones_managed_pages()
   → memblock_clear_kho_scratch_only()
   → free_low_memory_core_early()
   → totalram_pages_add(pages)

``free_low_memory_core_early()`` 先初始化仍需保留区域对应的页面描述，再遍历
``memblock.memory - memblock.reserved``。每段可释放区间按照PFN对齐和剩余长度选择合法阶数，通过
``memblock_free_pages()`` 交给伙伴系统。内核映像、页表、初始内存盘、固件表、每CPU区域、日志缓冲区和
其他早期分配仍位于保留区，不会被这次遍历释放。

因此，固件报告的全部E820 RAM不等于伙伴系统能够管理的页数。释放循环得到的页面总数加入
``totalram_pages``，内存区域的 ``managed_pages`` 和空闲链表也随实际释放页更新。 ``memblock`` 的记录
可以继续存在一段时间，但普通空闲页的分配所有权已经转交给伙伴系统。

x86 ``mem_init()`` 跨过启动期内存阶段
------------------------------------

x86-64的 ``mem_init()`` 将 ``after_bootmem`` 设为1，再执行
``x86_init.hyper.init_after_bootmem()``。随后， ``register_page_bootmem_info()`` 按配置为相关内存节点登记
启动期页面信息；存在 ``vsyscall`` VMA时，内核把它加入 ``/proc/kcore`` 的区域清单。

最后， ``preallocate_vmalloc_pages()`` 为所有进程页表都必须共享的 ``vmalloc`` 高层页表预先分配页面。
这些页面缺失会使以后创建的进程页表不完整，因此分配失败会触发 ``panic()``。这里准备的是页表层级，
还没有建立通用的 ``vmap`` 地址管理器。

SLUB和 ``vmap`` 地址管理器依次建立
--------------------------------

伙伴系统可以提供页面后， ``kmem_cache_init()`` 先用静态启动对象建立
``kmem_cache_node`` 和 ``kmem_cache``，把 ``slab_state`` 推进到 ``PARTIAL``。完成两个启动缓存的
自举后，它创建 ``kmalloc`` 缓存和 ``sheaf``，初始化空闲链表随机化，并用
``cpuhp_setup_state_nocalls()`` 注册SLUB的CPU下线处理函数。此后基础
``kmalloc()`` 和 ``kmem_cache_alloc()`` 可以使用；分配工作队列的
``kmem_cache_init_late()`` 仍未执行。

``page_ext_init_flatmem_late()`` 让需要栈记录与SLUB的 ``FLATMEM`` 页面扩展使用者完成后半段初始化。
随后，内核依次初始化内存泄漏检测、页表锁缓存、架构页表缓存和调试对象子系统。关闭相应配置时，这些
入口保持为空操作。

``vmalloc_init()`` 创建 ``vmap_area`` 缓存，为 ``cpu_possible_mask`` 中的每个CPU初始化
``vmap_block`` 和延迟释放状态，建立 ``vmap_node``，并把早期 ``vmlist`` 条目导入占用树。完成
空闲虚拟地址区间计算后，它设置 ``vmap_initialized=true``。最后的内存收缩器分配失败只会使该
收缩器缺失，不会撤销已经公布的虚拟地址映射管理器。

``mm_core_init()`` 的尾部不能截在 ``vmalloc``
--------------------------------------------

没有延迟初始化 ``struct page`` 时，内核现在执行通用 ``page_ext_init()``。随后
``init_espfix_bsp()`` 在第一个非初始化线程出现前建立CPU0的 ``espfix`` 条件， ``pti_init()`` 又必须位于
``espfix`` 之后。最后依次执行KMSAN运行期初始化、 ``mm_cache_init()`` 和 ``execmem_init()``。

这些入口可能因构建配置或CPU能力成为空操作，但是 ``mm_core_init()`` 的源码出口始终位于
``execmem_init()`` 之后。CPU0从该函数返回时仍在 ``start_kernel()`` 中执行，没有发生调度。

本章结束状态
------------

* 当前执行者：CPU0上的 ``start_kernel()``，当前任务为 ``init_task``；
* 精确位置： ``mm_core_init()`` 已结束， ``maple_tree_init()`` 尚未执行；
* CPU状态：x86-64内核态， ``IF=0``，只有CPU0执行；
* 随机子系统：已混入架构随机数据、UTS信息和架构命令行；是否就绪取决于实际输入和配置；
* 日志子系统：正式每CPU数据可用；动态缓冲区已经存在、迁移成功或继续使用静态缓冲区；
* VFS： ``in_lookup_hashtable`` 已初始化；目录项和索引节点哈希表按 ``hashdist`` 在本章分配或继续推迟；
* 异常处理：主异常表按需排序，CPU0的TSS、IST以及FRED或IDT条件已经建立；
* 普通空闲内存：已经从 ``memblock`` 交给伙伴系统，保留区仍保持占用；
* ``after_bootmem``：1； ``totalram_pages`` 已计入实际释放页面；
* SLUB：基础缓存和 ``kmalloc`` 缓存可用， ``kmem_cache_init_late()`` 尚未执行；
* ``vmalloc``：虚拟地址映射管理器已经公布；
* 调度器、设备中断、控制台、初始内存盘和PID 1：均未初始化、启用、解包或创建。

关键边界
--------

#. ``random_init_early()`` 混入的 ``command_line`` 不包含 ``bootconfig`` 后来追加的文本，也不保证随机数生成器就绪。
#. 日志缓冲区迁移失败时继续使用静态缓冲区，不会触发 ``panic()``。
#. ``hashdist=true`` 会把目录项和索引节点哈希表分配推迟到 ``vfs_caches_init()``。
#. 异常入口和TSS/IST已经建立，不等于设备中断已经初始化或 ``IF`` 已经置1。
#. 内存区域回退表和启动期 ``pageset`` 存在，不等于普通内存已经进入伙伴系统；交接点是
   ``memblock_free_all()``。
#. 可释放区间是 ``memblock.memory - memblock.reserved``，不是全部E820 RAM。
#. ``mem_init()`` 的 ``vmalloc`` 页表预分配与 ``vmalloc_init()`` 的地址区间管理是两个阶段。
#. SLUB基础可用不等于后半段初始化已经完成。
#. ``mm_core_init()`` 的出口位于 ``espfix``、PTI、KMSAN、MM缓存和 ``execmem`` 初始化之后。

下一入口
--------

第056章从：

.. code-block:: c

   maple_tree_init();

开始，随后准备x86文本修补页表、动态函数追踪记录和早期追踪缓冲区；调度器留到第057章。

资料
----

* `Linux 7.2-rc1固定提交：start_kernel中从随机初始化到mm_core_init的顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L1023-L1041>`_；
* `Linux 7.2-rc1固定提交：random_init_early的混入与计入规则 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/char/random.c#L849-L888>`_；
* `Linux 7.2-rc1固定提交：VFS早期哈希表的hashdist分支 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/dcache.c#L3443-L3518>`_；
* `Linux 7.2-rc1固定提交：mm_core_init完整顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/mm_init.c#L2696-L2749>`_；
* `Linux 7.2-rc1固定提交：memblock向伙伴系统交接空闲页 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/memblock.c#L2351-L2409>`_；
* `Linux 7.2-rc1固定提交：x86陷阱初始化 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/traps.c#L1661-L1677>`_；
* `Linux 7.2-rc1固定提交：x86-64 mem_init与vmalloc页表预分配 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/init_64.c#L1376-L1401>`_；
* `Linux 7.2-rc1固定提交：SLUB自举 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/slub.c#L8559-L8617>`_；
* `Linux 7.2-rc1固定提交：vmap地址管理器的公布 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/vmalloc.c#L5510-L5569>`_。
