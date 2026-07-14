第四十四章：Linux 怎样扩大启动日志并确认 initramfs 与 ACPI 表可以安全访问？
==========================================================================

第四十三章结束时，Linux 已经把 E820 中的 RAM 转换成 ``memblock.memory``，建立覆盖目标 RAM 的 early direct map，并执行：

.. code-block:: c

   memblock_set_current_limit(get_max_mapped());

从这一刻开始，memblock 不再只能从低 1 MiB 中返回内存。``setup_arch()`` 可以分配更大的启动期对象，也可以直接访问 GRUB 放在高端 RAM 中的 initramfs。

当前下一条调用是：

.. code-block:: c

   setup_log_buf(1);

本章追踪到 ``acpi_boot_table_init()`` 返回。期间 Linux 会扩大 printk ring buffer、确认或重定位 initramfs，并找到、校验和保留固件提供的 ACPI 表。

早期 printk 为什么先使用静态 ring buffer
---------------------------------------

内核从 ``startup_64``、``x86_64_start_kernel()`` 到 ``setup_arch()`` 已经输出了不少消息，但早期阶段不能立即申请一个很大的动态缓冲区。

原因包括：

* E820 尚未转换成 memblock；
* direct map 尚未覆盖全部目标 RAM；
* 普通 page allocator 和 slab allocator 尚未存在；
* ring buffer 自身的描述符、元数据和文本区都必须位于可持续访问的内存。

因此 printk 最初使用编译进内核映像的静态对象：

.. code-block:: text

   printk_rb_static
   __log_buf

这个缓冲区能让最早的汇编/C 初始化阶段记录消息，但容量有限。

``setup_log_buf(1)`` 的 ``1`` 表示什么
------------------------------------

函数参数名是 ``early``：

.. code-block:: c

   void __init setup_log_buf(int early)

``setup_arch()`` 传入 ``1``，表示当前仍处在 per-CPU area 尚未完成的早期调用。

它不会执行：

.. code-block:: c

   set_percpu_data_ready();

后面 ``start_kernel()`` 在 per-CPU area 建立后还会以 ``early = 0`` 再调用一次，用于补充按 CPU 数量扩大的容量和宣布 printk per-CPU 数据可用。

当前调用只解决一个问题：既然 memblock 和 direct map 已经可用，就把静态小 ring buffer 换成需要的动态容量。

动态 printk ring buffer 不只有一块字符数组
-----------------------------------------

现代 printk ring buffer 至少需要三类内存：

.. code-block:: text

   text buffer    保存日志正文
   descriptors    保存每条 record 的状态和位置
   printk_info    保存时间戳、级别、facility、caller 等元数据

``setup_log_buf()`` 根据 ``new_log_buf_len`` 计算 descriptor 数量：

.. code-block:: c

   new_descs_count = new_log_buf_len >> PRB_AVGBITS;

随后分别通过 memblock 分配：

.. code-block:: c

   new_log_buf = memblock_alloc(new_log_buf_len, LOG_ALIGN);
   new_descs   = memblock_alloc(new_descs_size, LOG_ALIGN);
   new_infos   = memblock_alloc(new_infos_size, LOG_ALIGN);

这里已经能看出第四十三章建立 direct map 的直接价值：memblock 返回的物理页必须能立即通过内核虚拟地址访问，否则 ``prb_init()`` 无法初始化这些数组。

如果没有请求更大的 ``new_log_buf_len``，当前调用可能直接返回。容量可以受编译配置、``log_buf_len=`` early 参数和后续 CPU 数量调整影响。因此“调用了 ``setup_log_buf(1)``”不等于每台机器都一定重新分配。

怎样迁移已经产生的日志
----------------------

若成功分配动态缓冲区，Linux 不能简单切换指针，因为静态 ring buffer 中已经有启动日志。

它先初始化新 ring buffer：

.. code-block:: c

   prb_init(&printk_rb_dynamic, ...);

随后在保存本地 IRQ 状态的区域内：

#. 更新 ``log_buf_len`` 和 ``log_buf``；
#. 遍历 ``printk_rb_static`` 中已有 record；
#. 逐条复制正文与 ``printk_info``；
#. 把全局 ``prb`` 指向动态 ring buffer。

复制的不是拼接后的纯字符串，而是每条完整 record，包括：

* ``text_len``；
* facility 和 level；
* flags；
* 纳秒时间戳；
* caller ID；
* 设备信息。

切换过程中 NMI 上下文仍可能向旧 ring buffer 写入。为缩小丢失窗口，函数在切换后还会从上一次 sequence 位置继续扫描静态 buffer，把迟到的 record 再复制一次。

若 sequence 仍对不上，它会报告丢失了多少条消息。

因此这里完成的是 ring buffer 的在线迁移，不是清空日志重新开始。

扩大日志缓冲不等于控制台已经完整初始化
--------------------------------------

``setup_log_buf(1)`` 只改变内核保存日志 record 的位置和容量。

它不代表：

* 串口驱动已经作为正式 console 注册；
* printk kthread 已经运行；
* scheduler 已经可用；
* 所有消息都已经输出到屏幕；
* ``/dev/kmsg`` 已经存在。

当前 ``console=ttyS0`` 仍会在后续控制台初始化阶段发挥作用。此处首先保证早期消息不会因为静态缓冲区太小而过早覆盖。

为什么现在才确认 initramfs 的虚拟地址
------------------------------------

GRUB 已经把 ``/boot/initramfs-6.12.95.img`` 放入物理 RAM，并在 ``boot_params`` 中填写：

.. code-block:: text

   hdr.ramdisk_image
   hdr.ramdisk_size
   ext_ramdisk_image
   ext_ramdisk_size

第四十一章的 ``early_reserve_initrd()`` 已经把这段物理地址加入 ``memblock.reserved``，防止页表和其他早期对象覆盖它。

但“被保留”只回答：

.. code-block:: text

   这段物理内存不能被重新分配

它还没有回答：

.. code-block:: text

   当前 direct map 是否真的覆盖了整段 initramfs

现在 ``init_mem_mapping()`` 已经完成，Linux 才能调用：

.. code-block:: c

   reserve_initrd();

重新组合 64 位 initramfs 地址和大小
-----------------------------------

``get_ramdisk_image()`` 把低 32 位和扩展高 32 位合并：

.. code-block:: c

   ramdisk_image  = boot_params.hdr.ramdisk_image;
   ramdisk_image |= (u64)boot_params.ext_ramdisk_image << 32;

``get_ramdisk_size()`` 对大小执行同样操作。

这使 boot protocol 可以描述位于 4 GiB 以上的 initramfs。当前 GRUB i386-pc 主线通常把 initramfs 放在低于它允许上界的 RAM 中，但 Linux 不能把 32 位字段当作完整地址。

``reserve_initrd()`` 首先验证：

.. code-block:: c

   boot_params.hdr.type_of_loader != 0
   ramdisk_image != 0
   ramdisk_size != 0

任何一项不成立都表示没有有效 bootloader initrd。

initramfs 已在 direct map 中时
-----------------------------

Linux 把物理范围换算成 PFN，并检查：

.. code-block:: c

   pfn_range_is_mapped(PFN_DOWN(ramdisk_image),
                       PFN_DOWN(ramdisk_end))

如果整段范围已经被 ``pfn_mapped[]`` 覆盖，最简单路径是：

.. code-block:: c

   initrd_start = ramdisk_image + PAGE_OFFSET;
   initrd_end   = initrd_start + ramdisk_size;

这里没有复制任何字节。

``PAGE_OFFSET`` 把物理地址转换为 direct-map 虚拟地址。后续 initramfs 代码通过 ``initrd_start`` 和 ``initrd_end`` 读取归档内容。

initramfs 超出当前映射时怎样搬迁
------------------------------

如果不是所有 PFN 都已映射，``reserve_initrd()`` 调用 ``relocate_initrd()``。

它先在当前可映射上限内申请一段页对齐内存：

.. code-block:: c

   relocated_ramdisk = memblock_phys_alloc_range(
       PAGE_ALIGN(ramdisk_size), PAGE_SIZE,
       0, PFN_PHYS(max_pfn_mapped));

然后建立新的 direct-map 虚拟地址并复制：

.. code-block:: c

   initrd_start = relocated_ramdisk + PAGE_OFFSET;
   initrd_end   = initrd_start + ramdisk_size;
   copy_from_early_mem((void *)initrd_start,
                       ramdisk_image,
                       ramdisk_size);

复制成功后，旧物理区间从 memblock reserved 中释放：

.. code-block:: c

   memblock_phys_free(ramdisk_image,
                      ramdisk_end - ramdisk_image);

因此条件搬迁的目的不是整理文件格式，而是保证后续代码能通过正式 direct map 连续访问全部 initramfs 字节。

当前固定主线怎样走
------------------

第三十二章中 GRUB 已经依据 ``initrd_addr_max``、内核目标范围与可用 RAM，选择一个较高但合法的地址。第四十三章又建立了覆盖目标 memblock RAM 的 direct map。

所以固定主线预期进入“已经映射”的快路径：只设置 ``initrd_start`` / ``initrd_end``，不发生搬迁。

正文仍保留搬迁分支，因为：

* bootloader 可能把 initrd 放到早期 direct map 未覆盖的范围；
* 特殊内存布局可能产生高端空洞；
* 32 位和某些受限配置的直接映射范围更小。

``reserve_initrd()`` 仍没有展开 initramfs
----------------------------------------

这一点必须明确：此时 initramfs 只是内存中的一个压缩或未压缩归档字节流。

当前没有：

* 解 gzip/xz/zstd；
* 解析 ``newc`` cpio header；
* 创建目录和 inode；
* 建立 ``rootfs``；
* 执行 ``/init``。

真正的内建 initramfs 和外部 initrd 处理会在 ``populate_rootfs()`` 等 initcall 路径中发生。

为什么 ACPI override 会在 initramfs 展开前出现
----------------------------------------------

紧接着调用：

.. code-block:: c

   acpi_table_upgrade();

Linux 支持把替换 ACPI 表放在 initrd 中特定路径，例如：

.. code-block:: text

   kernel/firmware/acpi/

启动早期代码可以直接扫描 initrd 中的 cpio 记录，找到 DSDT、SSDT 等 override 表，使它们在 ACPI 表初始化前生效。

这不是普通 rootfs 解包。它只是针对特定 ACPI 文件名和 table header 的早期扫描。

当前固定 initramfs 是否包含 override 表并未预设；普通构建通常没有，因此该调用可能不修改任何表。它仍必须排在 ACPI 初始表定位之前，否则固件原表一旦被正式注册，替换时机已经太晚。

``acpi_boot_table_init()`` 先定位和保留，不做完整设备枚举
------------------------------------------------------

随后：

.. code-block:: c

   acpi_boot_table_init();

函数先执行 ACPI DMI blacklist 检查。真实旧机器可能因为损坏表而禁用 ACPI、禁用 IRQ 路由或强制使用 RSDT。

当前 QEMU q35 + SeaBIOS 提供规范化的虚拟固件表，不预期命中这些旧硬件 blacklist。

若 ACPI 未被禁用，它调用：

.. code-block:: c

   acpi_locate_initial_tables();

这一阶段从前面保存的 RSDP 出发，定位 RSDT/XSDT 以及它们引用的 table header，检查签名、长度和校验和，并建立 ACPICA 初始 table list。

成功后执行：

.. code-block:: c

   acpi_reserve_initial_tables();

把固件表占用的物理区间加入保留集合，避免后续内存分配覆盖。

为什么 E820 标成 ACPI 仍需要显式保留
----------------------------------

E820 的 ``ACPI_RECLAIM`` 表示这段内存在操作系统完成 ACPI 初始化后可以回收，不等于从第一刻起就能任意复用。

Linux 必须先：

#. 找到所有正在使用的 table；
#. 保证解析期间内容不变；
#. 根据表的寿命决定复制、永久保留或以后释放。

``acpi_reserve_initial_tables()`` 建立的正是这个解析期保护。

本章结束时还没有完整解析 MADT、FADT 和 SRAT
------------------------------------------

``acpi_boot_table_init()`` 的主要结果是：

.. code-block:: text

   RSDP 已知
   → RSDT/XSDT 初始 table list 已建立
   → table 物理区已保留

它尚未完成：

* 从 MADT 登记所有 LAPIC/IOAPIC；
* 从 FADT 建立 SCI、PM timer 和电源管理接口；
* 从 SRAT 建立 NUMA node；
* 执行 AML；
* 枚举 ACPI namespace 中的设备。

下一章的 ``early_acpi_boot_init()`` 才开始读取早期 MADT，并为 NUMA 初始化创造条件。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 6.12.95 ``arch/x86/kernel/setup.c:setup_arch()``；
* CPU：BSP / Linux CPU 0；
* mode：64 位 long mode；
* interrupts：关闭；
* printk：若配置需要，已从静态 ring buffer 迁移到 memblock 动态 ring buffer；
* 旧启动日志：已尽量按 record/sequence 迁移；
* initramfs 物理区：仍保留；
* ``initrd_start`` / ``initrd_end``：已建立，必要时已条件搬迁；
* initramfs：尚未解压、尚未建立 rootfs；
* ACPI override：已完成条件扫描；
* ACPI 初始表：已定位并保留；
* MADT/SRAT 的早期拓扑解析：尚未完成；
* ``setup_arch()``：仍未返回。

下一条控制流从：

.. code-block:: c

   vsmp_init();

继续，随后进入 early platform quirks、``early_acpi_boot_init()``、MP table fallback 和 NUMA node 建立。

资料
----

* `Linux 6.12.95 setup.c：setup_log_buf、reserve_initrd、ACPI 初始化调用顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c>`_
* `Linux 6.12.95 printk.c：动态 ring buffer 分配与旧 record 迁移 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/printk/printk.c>`_
* `Linux 6.12.95 setup.c：early_reserve_initrd、reserve_initrd 与 relocate_initrd <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c>`_
* `Linux 6.12.95 ACPI tables.c：initrd ACPI table override <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/acpi/tables.c>`_
* `Linux 6.12.95 x86 ACPI boot.c：初始表定位、保留与后续 early ACPI 入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/acpi/boot.c>`_
* `Linux x86 boot protocol：ramdisk_image、ramdisk_size 与扩展字段 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/arch/x86/boot.rst>`_