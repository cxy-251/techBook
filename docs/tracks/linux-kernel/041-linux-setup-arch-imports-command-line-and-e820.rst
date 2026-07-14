第四十一章：Linux setup_arch 怎样接管命令行并导入 E820 内存图？
===================================================================

第四十章结束时，通用 ``start_kernel()`` 已经建立 ``init_task`` 的最早状态、登记 CPU 0、保持中断关闭，并停在：

.. code-block:: c

   setup_arch(&command_line);

``setup_arch()`` 位于 ``arch/x86/kernel/setup.c``。它不是一个简单的“体系结构初始化钩子”，而是 x86 把 bootloader 留下的物理机器描述，转换成 Linux 后续内存管理能够使用的内部状态的主入口。

这一章先追踪它的前半段，直到基础 E820 表和 ``setup_data`` 扩展链被导入。此时 Linux 已经知道“物理地址空间由哪些区间组成”，但还没有把这些 RAM 区间正式加入 memblock，也没有建立完整 direct map。

先确定最终生效的命令行
----------------------

``x86_64_start_kernel()`` 已经把 bootloader 提供的命令行复制到全局 ``boot_command_line``。当前固定配置中，它的内容是：

.. code-block:: text

   root=/dev/sda1 ro console=ttyS0

``setup_arch()`` 在 x86-64 路径首先输出这条命令行，然后处理编译期 ``CONFIG_CMDLINE``。

编译期命令行存在三种情况：

* 没有配置 ``CONFIG_CMDLINE_BOOL``：直接使用 bootloader 命令行；
* 配置了内建命令行但没有 ``CONFIG_CMDLINE_OVERRIDE``：内建字符串放在前面，bootloader 字符串追加在后面；
* 配置了 ``CONFIG_CMDLINE_OVERRIDE``：完全用内建字符串覆盖 bootloader 命令行。

最终结果被复制到 x86 自己的静态缓冲区：

.. code-block:: c

   strscpy(command_line, boot_command_line, COMMAND_LINE_SIZE);
   *cmdline_p = command_line;

这里同时出现三个名字：

.. code-block:: text

   boot_command_line   从 bootloader 启动数据复制来的全局原始字符串
   command_line        setup_arch() 持有的可处理副本
   *cmdline_p          返回给 start_kernel() 的指针

后面的 ``setup_command_line()``、``parse_early_param()`` 和普通内核参数解析会继续复制或原地修改字符串，所以不能让所有阶段共享同一个不可区分的缓冲区。

为什么先建立 traps、CPU 特征和 early ioremap
------------------------------------------

命令行准备好后，控制流依次执行：

.. code-block:: c

   olpc_ofw_detect();
   idt_setup_early_traps();
   early_cpu_init();
   jump_label_init();
   static_call_init();
   early_ioremap_init();

当前 QEMU q35 普通 PC 路径不会进入 OLPC OFW 专用逻辑，但其余调用都很关键。

``idt_setup_early_traps()`` 把更完整的早期异常入口放入 IDT。前面 ``head_64.S`` 建立的 IDT 主要保证最早汇编和页表故障能够生存；从现在开始，C 代码即将读取固件表、映射物理地址并探测 CPU，异常处理能力必须进一步完善。

``early_cpu_init()`` 建立 boot CPU 的早期能力描述和厂商相关钩子。它还不是最终的 ``identify_boot_cpu()`` 全流程，但后续 NX、APIC、MTRR 和页表决策已经需要一份可靠的 CPU feature 基础。

``jump_label_init()`` 与 ``static_call_init()`` 很早出现，是因为 x86 架构初始化本身已经会经过使用静态分支和静态调用的代码。这里建立的是最早可用状态，``start_kernel()`` 返回后还会再次完成通用层所需的初始化。

``early_ioremap_init()`` 建立临时映射窗口。此时完整 ``ioremap()``、vmalloc allocator 和最终页表都不存在，内核仍需要短暂访问不在当前直接映射中的物理固件数据，因此使用固定 slot 的 early ioremap 机制。

``parse_boot_params()`` 把协议字段转成内核变量
--------------------------------------------

``boot_params`` 是 Linux/x86 Boot Protocol 的交接对象。前面的章节已经说明 GRUB 填写它，``x86_64_start_kernel()`` 再把它复制到正式内核全局对象。

``parse_boot_params()`` 不重新读取磁盘，也不访问 BIOS。它只是把协议结构中的字段翻译成后续代码更容易使用的全局状态，包括：

* ``root_dev`` 转成旧式 ``ROOT_DEV`` 编码；
* ``screen_info`` 和可选 EDID 复制到系统 framebuffer 描述；
* 保存 ``vid_mode``；
* 解析 ``type_of_loader``、``ext_loader_type`` 和版本字段；
* 读取 ramdisk 相关兼容字段；
* 判断 EFI loader signature；
* 根据 ``root_flags`` 决定是否清除只读根挂载标志。

当前主线来自 SeaBIOS + GRUB i386-pc，不是 EFI loader，因此不会设置 ``EFI_BOOT`` 标志。命令行中的 ``ro`` 仍会在后续参数解析阶段决定根文件系统初始只读语义。

bootloader 类型字段有什么用
---------------------------

``type_of_loader`` 不是“当前磁盘设备类型”。它标识是谁按照 Linux Boot Protocol 装入了内核。

内核把旧字段和扩展字段组合为：

.. code-block:: text

   bootloader_type
   bootloader_version

后续日志、兼容判断和某些启动器特例可以据此区分 GRUB、LILO、syslinux、EFI stub 等入口。它不会改变当前 CPU 已经处于 long mode 的事实，也不会让 Linux继续调用 GRUB。

先保留，再把 RAM 加入 allocator
-----------------------------

接下来 ``setup_arch()`` 调用：

.. code-block:: c

   x86_init.oem.arch_setup();
   early_reserve_memory();

默认 PC 路径的 OEM 钩子通常为空。真正重要的是 ``early_reserve_memory()``。

此时 memblock 的 ``reserved`` 集合已经能记录不可覆盖范围，但 E820 中的普通 RAM 还没有批量加入 ``memblock.memory``。Linux 故意先做保留，原因很直接：

.. code-block:: text

   如果先告诉 allocator“这些都是可用 RAM”
   再补记 kernel / initrd / setup_data
   中间的早期分配就可能覆盖启动所必需的数据

因此顺序必须是：

.. code-block:: text

   先登记绝对不能动的物理区间
   → 再导入固件 RAM 图
   → 再允许 memblock 从 RAM 中分配

保留正式内核映像
----------------

第一项是：

.. code-block:: c

   memblock_reserve_kern(__pa_symbol(_text),
                         __end_of_kernel_reserve - _text);

它保留从正式内核 ``_text`` 到 ``__end_of_kernel_reserve`` 的物理区间。

这里不是只保留可执行代码。范围还覆盖早期仍必须存在的只读数据、普通数据、BSS、brk 以及链接脚本明确放入 kernel reserve 区间的对象。

``__end_of_kernel_reserve`` 之后的特殊 section 不会被自动包含；需要保留的内容必须由各自代码另行调用 ``memblock_reserve()``。这条规则防止链接脚本新增 section 后被无意永久保留，也防止启动早期错误释放仍在使用的 section。

为什么先保留低 64 KiB
----------------------

随后：

.. code-block:: c

   memblock_reserve(0, SZ_64K);

理论上 page 0 和 BIOS 数据区已经能从 E820/低端布局中推断，Linux 仍明确保留前 64 KiB，原因包括：

* 第一页通常属于 BIOS/实模式遗留区域；
* 历史 BIOS 可能在启动后仍破坏低端内存；
* page 0 不能被普通内核对象使用；
* L1TF 等漏洞使 page 0 内容具有额外安全风险；
* AP real-mode trampoline 还要在 1 MiB 以下寻找安全位置。

后面找到 trampoline 后，Linux 会进一步保留整个低 1 MiB。当前这里只先建立不可被早期分配踩中的最小边界。

initramfs 此时只做物理保留
-------------------------

``early_reserve_initrd()`` 从 ``boot_params`` 合并 32 位和扩展高 32 位字段：

.. code-block:: text

   ramdisk_image = ext_ramdisk_image : ramdisk_image
   ramdisk_size  = ext_ramdisk_size  : ramdisk_size

只要 bootloader 类型、起始地址和大小有效，就执行：

.. code-block:: c

   memblock_reserve_kern(ramdisk_image,
                         PAGE_ALIGN(ramdisk_image + ramdisk_size)
                         - ramdisk_image);

这里还没有解析 cpio，也没有创建根文件系统。

它仅表示：

.. code-block:: text

   这段物理内存属于 GRUB 装入的 initramfs
   在 Linux 决定是否需要重定位和何时解包之前，任何 allocator 都不能覆盖它

真正的 ``reserve_initrd()`` 在 direct map 建立以后才判断该区间是否已经全部可映射；必要时会把 initramfs 搬到更低、已建立 direct map 的 RAM。

保留 ``setup_data`` 链本身
-------------------------

Boot Protocol 的固定 ``boot_params`` 放不下所有未来扩展，因此 ``hdr.setup_data`` 可以指向一个物理链表。每个节点包含：

.. code-block:: c

   struct setup_data {
       u64 next;
       u32 type;
       u32 len;
       u8  data[];
   };

``memblock_x86_reserve_range_setup_data()`` 先遍历链表，并保留每个节点的 header 与 payload。

如果节点是 ``SETUP_INDIRECT``，payload 还会描述另一段真正的数据地址；只要间接类型没有再次指向 ``SETUP_INDIRECT``，那段目标物理内存也会被保留。

此时只解决“不能覆盖”。节点内容的语义解析要等基础 E820 图导入后再执行。

保留传统 BIOS 区域
------------------

``reserve_bios_regions()`` 根据第四十章建立的普通 PC legacy 标志处理传统 BIOS 所需区域。QEMU q35 虽然是虚拟现代芯片组，当前启动路径仍经过 SeaBIOS，低端 EBDA、ROM window 和实模式兼容数据仍然不能当成普通 RAM。

``trim_snb_memory()`` 是 Sandy Bridge 集显硬件缺陷的条件 workaround。固定 q35 虚拟平台不会命中真实 SNB 集显 ID，因此主线不会额外保留那几页物理地址。

建立物理地址资源上限
--------------------

早期 CPU 检测给出物理地址位数后，``setup_arch()`` 设置：

.. code-block:: c

   iomem_resource.end = (1ULL << boot_cpu_data.x86_phys_bits) - 1;

这定义的是 Linux 全局物理内存资源树的地址上限，不代表范围内全部是 RAM。

例如 CPU 支持 46 位物理地址，只表示资源树能够描述 ``0`` 到 ``2^46-1``；其中仍可能包含 RAM、PCI MMIO、固件表、空洞和保留区。

把 bootloader E820 表导入 Linux
------------------------------

随后调用：

.. code-block:: c

   e820__memory_setup();

默认 PC 实现从：

.. code-block:: c

   boot_params.e820_table
   boot_params.e820_entries

复制基础 E820 项。

这张表的上游链路已经贯穿前面的章节：

.. code-block:: text

   QEMU q35 创建物理内存布局
   → SeaBIOS 形成 E820 map
   → GRUB 通过 BIOS 接口读取它
   → GRUB 写入 Linux boot_params
   → Linux e820__memory_setup() 导入

Linux 首先尝试追加标准 E820 项。如果表无效，才会退回 ``INT 15h AH=88h`` / E801 风格的旧内存大小字段，伪造 ``0–640 KiB`` 与 ``1 MiB–end`` 两段 RAM。固定主线拥有有效 E820 表，不进入该降级路径。

为什么要 sanitize E820
----------------------

固件表可能存在：

* 项目无序；
* 相邻同类型区间可合并；
* 区间重叠；
* 同一物理范围被不同类型覆盖；
* 零长度项目。

``e820__update_table()`` 对内核工作表进行整理，使后续查询能够按有序、无歧义区间工作。

然后内核复制出三份角色不同的表：

.. code-block:: text

   e820_table           当前内核会继续修改的工作表
   e820_table_firmware  尽量保留 firmware 原始视图
   e820_table_kexec     为未来 kexec 内核准备的传递视图

后续 ``mem=``、``memmap=``、BIOS 修正、MTRR trim 等操作主要作用在工作表上。保留其他副本，可以避免“Linux 自己修改过的结果”被误认为固件最初报告。

基础 E820 与扩展 E820 为什么分两步
---------------------------------

``e820__memory_setup()`` 只导入 ``boot_params`` 固定数组中的基础项目。紧接着：

.. code-block:: c

   parse_setup_data();

才遍历 ``hdr.setup_data`` 链。

如果遇到 ``SETUP_E820_EXT``，调用：

.. code-block:: c

   e820__memory_setup_extended(pa_data, data_len);

原因是固定 ``boot_params.e820_table`` 容量有限。bootloader 若需要传递更多项目，可以把剩余项目放入扩展节点。

顺序必须是：

.. code-block:: text

   先有基础 E820 工作表
   → 再追加扩展 E820
   → 后面统一执行 early 参数修正和 memblock 转换

``setup_data`` 还能携带什么
-------------------------

``parse_setup_data()`` 识别的节点包括：

* ``SETUP_E820_EXT``：额外 E820 项；
* ``SETUP_DTB``：设备树 blob；
* ``SETUP_EFI``：额外 EFI setup 信息；
* ``SETUP_IMA``：IMA kexec buffer；
* ``SETUP_KEXEC_KHO``：kexec handover 数据；
* ``SETUP_RNG_SEED``：bootloader 随机种子。

随机种子节点被加入内核熵池后，payload 和长度会用 ``memzero_explicit()`` 清除，避免同一秘密被后续代码重复读取。

当前固定 ``grub.cfg`` 没有显式配置 DTB、kexec handover 或额外 RNG 节点；解析器仍必须支持这些 Boot Protocol 扩展，因为同一个 Linux 映像可以由其他 loader 和平台启动。

复制 BIOS EDD 信息
------------------

如果启用 EDD 支持，``copy_edd()`` 把 ``boot_params`` 中的 MBR signature 与 BIOS Enhanced Disk Drive 描述复制到长期安全对象。

这并不会继续使用 BIOS ``INT 13h`` 读盘。它保存的是启动磁盘身份和几何信息，后续 EDD 子系统、日志和启动盘匹配可能需要这些数据。

当前章节的自然终点
------------------

到这里，Linux 已经完成两类不同工作：

.. code-block:: text

   保护工作
   kernel / low 64 KiB / initramfs / setup_data / BIOS regions

   描述导入
   boot_params fields / 基础 E820 / 扩展 setup_data / EDD

但还没有执行：

.. code-block:: text

   e820 RAM → memblock.memory
   max_pfn 计算
   MTRR 对 RAM 的裁剪
   early page-table buffer 分配
   direct map 建立

下一条关键调用是：

.. code-block:: c

   setup_initial_init_mm(_text, _etext, _edata, (void *)_brk_end);

它开始把正式内核自身的 text/data/brk 边界登记到 ``init_mm``，随后进入 NX、early 参数、资源树和 E820 修正阶段。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 6.12.95 ``arch/x86/kernel/setup.c:setup_arch()``；
* CPU：BSP / Linux CPU 0；
* mode：64 位 long mode；
* interrupts：关闭；
* 有效命令行：已复制到 x86 ``command_line``；
* ``boot_params``：关键协议字段已翻译；
* kernel physical range：已加入 memblock reserved；
* 低 64 KiB：已保留；
* initramfs physical range：已保留，尚未解析；
* ``setup_data`` 节点与间接 payload：已保留；
* 基础 E820：已从 ``boot_params`` 导入并整理；
* 扩展 ``setup_data``：已解析；
* EDD：已复制到安全对象；
* ``memblock.memory``：尚未由 E820 RAM 建立；
* ``max_pfn``：尚未计算；
* direct map：尚未重建；
* ``start_kernel()``：仍等待 ``setup_arch()`` 返回。

资料
----

* `Linux 6.12.95 setup.c：setup_arch、parse_boot_params、early_reserve_memory、setup_data 与 initrd 保留 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c>`_
* `Linux 6.12.95 e820.c：e820__memory_setup_default 与 e820__memory_setup <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/e820.c>`_
* `Linux/x86 Boot Protocol：boot_params、E820 与 setup_data ABI <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/arch/x86/boot.rst>`_
* `Linux 6.12.95 bootparam.h：boot_params、setup_header 与 setup_data 类型 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/include/uapi/asm/bootparam.h>`_
* `Linux 6.12.95 early_ioremap.c：最终内存管理建立前的临时映射机制 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/early_ioremap.c>`_
