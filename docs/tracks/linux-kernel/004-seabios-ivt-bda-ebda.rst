第四章：SeaBIOS 怎样在低端内存建立 IVT、BDA 和 EBDA？
====================================================

上一章结束时，SeaBIOS 已经把一次性初始化代码搬到普通 RAM，并跳入重定位后的：

::

   post.c:maininit()

CPU 仍然处于 32 位保护模式，分页关闭。早期栈顶最初设为 ``0x7000``；经过前一章的多层C调用后，
当前 ``ESP`` 位于该地址以下，不能再把 ``0x7000`` 当成当前栈指针。E820 初始内存地图已经存在，
SeaBIOS 也已经有了临时内存分配区。

现在它要做的不是马上找磁盘，而是先建立传统 BIOS 软件约定的低端内存结构。后面的键盘、显示、磁盘、
定时器和启动服务，都需要通过这些结构交换状态。

本章固定使用：

::

   repository: coreboot/seabios
   commit: c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf

当前路径使用该提交的默认QEMU配置： ``CONFIG_MALLOC_UPPERMEMORY=y``、
``CONFIG_ENTRY_EXTRASTACK=y``，而 ``CONFIG_COREBOOT_FLASH=n``、
``CONFIG_MULTIBOOT=n``。这些配置决定EBDA位置、额外栈入口以及两条非QEMU文件来源
是否执行。

maininit 先建立内部接口
---------------------

``post.c:maininit()`` 的第一条调用是：

.. code-block:: c

   static void
   maininit(void)
   {
       interface_init();
       platform_hardware_setup();
       /* 后续设备初始化与启动流程 */
   }

``interface_init()`` 处理的不是某个具体硬件设备，而是固件内部和传统 BIOS 软件可见的基础接口：

.. code-block:: c

   void
   interface_init(void)
   {
       malloc_init();

       qemu_cfg_init();
       coreboot_cbfs_init();
       multiboot_init();

       ivt_init();
       bda_init();

       boot_init();
       bios32_init();
       pmm_init();
       pnp_init();
       kbd_init();
       mouse_init();
   }

本章只走到 ``bda_init()`` 完成。此时 IVT、BDA、EBDA 和额外中断栈已经建立，接下来才轮到磁盘启动、
BIOS32、PMM、PnP、键盘和鼠标接口。

malloc_init 修复重定位后的内存管理状态
-----------------------------------

上一章已经把 ``code32init`` 复制到新的 RAM 地址，并修正了代码中的重定位项。代码可以运行，不代表所有
内部链表指针都已经自动变成正确状态。

SeaBIOS 的内存分配器把可用区域组织成多个链表：

* ``ZoneTmpLow``：初始化阶段使用的低端临时内存；
* ``ZoneTmpHigh``：初始化阶段使用的高端临时内存；
* ``ZoneLow``：需要在传统低端地址长期保留的数据；
* ``ZoneFSeg``：F-segment 中可分配的空间；
* ``ZoneHigh``：需要长期保留的高端内存。

``malloc_init()`` 首先修复链表头中的反向指针：

.. code-block:: c

   if (CONFIG_RELOCATE_INIT) {
       int i;
       for (i=0; i<ARRAY_SIZE(Zones); i++) {
           struct zone_s *zone = Zones[i];
           if (zone->head.first)
               zone->head.first->pprev = &zone->head.first;
       }
   }

为什么只需要特别修复 ``pprev``？

SeaBIOS 使用的是一种哈希链表结构。第一个节点的 ``pprev`` 不是简单指向另一个普通节点，而是指向链表头
结构中保存 ``first`` 指针的位置。初始化代码整体搬家后，这个“指向链表头内部字段”的地址可能仍然指向
旧区域，所以必须重新指向当前链表头。

这不是通用的 C 语言规则，而是由当前链表结构和运行时重定位共同造成的问题。

varlow：给 16 位代码保留可写数据
-----------------------------

SeaBIOS 随后执行：

.. code-block:: c

   memmove(VSYMBOL(final_varlow_start),
           VSYMBOL(varlow_start),
           SYMBOL(varlow_end) - SYMBOL(varlow_start));

``VARLOW`` 标记的数据需要放在传统低端内存中。原因是 SeaBIOS 后面仍然会频繁在 16 位和 32 位代码之间
切换。16 位 BIOS 中断处理代码不能随意使用任意高地址，所以一部分共享状态必须位于它能够稳定寻址的低端
区域。

构建时的 ``varlow_start`` 是这些变量在固件映像中的初始位置；``final_varlow_start`` 是启动后真正长期使用
的位置。``memmove()`` 把变量初值复制过去，后面的 16 位和 32 位代码都通过链接器生成的符号访问同一份
低端数据。

随后 ``malloc_init()`` 把剩余低端空间登记到 ``ZoneLow``，并把 F-segment 中允许分配的区域清零后登记到
``ZoneFSeg``：

.. code-block:: c

   alloc_add(&ZoneLow, ...);

   memset(VSYMBOL(zonefseg_start), 0,
          SYMBOL(zonefseg_end) - SYMBOL(zonefseg_start));
   alloc_add(&ZoneFSeg, SYMBOL(zonefseg_start), SYMBOL(zonefseg_end));

F-segment 指传统物理地址：

::

   0x000f0000 - 0x000fffff

这里既要保存运行时 BIOS 代码和固定入口，也要容纳少量兼容数据。SeaBIOS 不能把整个 64 KiB 都当成
普通堆，所以只能登记链接布局明确留下的空闲区域。

qemu_cfg_init 把 QEMU 提供的文件注册给固件
---------------------------------------

上一章中的 ``qemu_preinit()`` 已经通过 ``fw_cfg`` 读取早期 E820 信息。这里再次调用的
``qemu_cfg_init()`` 目标不同：它要建立完整的 QEMU firmware configuration 文件目录。

SeaBIOS 先读取 ``fw_cfg`` 签名：

.. code-block:: c

   qemu_cfg_select(QEMU_CFG_SIGNATURE);

   char *sig = "QEMU";
   for (i = 0; i < 4; i++)
       if (inb(PORT_QEMU_CFG_DATA) != sig[i])
           return 0;

签名成立后，它读取 ``QEMU_CFG_FILE_DIR``，逐项获得：

* 文件名；
* 文件大小；
* 读取该文件时使用的 selector。

源码中的目录项结构是：

.. code-block:: c

   struct QemuCfgFile {
       u32 size;
       u16 select;
       u16 reserved;
       char name[56];
   };

这些并不是客户机磁盘文件。它们是 QEMU 在虚拟硬件边界上提供给固件的数据对象，例如 ACPI 表装载说明、
SMBIOS 信息、启动顺序、Option ROM 数据和其他平台配置。

SeaBIOS 把每个条目登记成内部 ``romfile``。后面的初始化代码可以按名字寻找：

::

   etc/e820
   etc/table-loader
   etc/boot-menu-wait
   etc/threads
   ...

这一步让固件不用理解 QEMU 命令行和宿主机对象，只需要按约定名称读取平台交给它的数据。

每个目录项都要先从临时区分配一个 ``qemu_romfile_s``。正常成功路径会把条目接入
romfile链表；若某一项分配失败，源码只发出警告并跳过该项，不会回滚此前已经登记的
条目，也不会把整个POST倒回上一阶段。

``interface_init()`` 随后仍会调用 ``coreboot_cbfs_init()`` 和 ``multiboot_init()``。
在当前默认QEMU构建中，前者因 ``CONFIG_COREBOOT_FLASH=n`` 返回，后者因
``CONFIG_MULTIBOOT=n`` 返回；两者都没有创建romfile，控制流继续进入 ``ivt_init()``。

IVT 为什么必须放在物理地址 0
--------------------------

``interface_init()`` 接着调用：

.. code-block:: c

   ivt_init();

IVT 是 Interrupt Vector Table，即实模式中断向量表。传统 x86 实模式把它固定在物理地址：

::

   0x00000 - 0x003ff

原因很直接：

* 一共有 256 个中断向量；
* 每个向量保存一个 16 位 offset 和一个 16 位 segment；
* 每项 4 字节；
* ``256 × 4 = 1024`` 字节。

所以 IVT 恰好占据最低的 1 KiB。

SeaBIOS 的结构定义是：

.. code-block:: c

   struct rmode_IVT {
       struct segoff_s ivec[256];
   };

``SET_IVT(vector, segoff)`` 最终向 ``SEG_IVT = 0`` 指向的这张表写入一个 ``segment:offset``。

为什么先把 256 项全部指向默认返回入口
----------------------------------

``ivt_init()`` 第一轮循环是：

.. code-block:: c

   for (i=0; i<256; i++)
       SET_IVT(i, FUNC16(entry_iret_official));

也就是说，在安装任何具体服务之前，所有中断向量都先指向一个最小默认处理入口。这个入口最终执行
``iret`` 返回。

这样做比保留随机内存内容安全。某个未安装的中断被意外触发时，CPU 至少会进入固件已知代码，而不是把
低端内存中的旧字节解释成 segment 和 offset，再跳到不可预测的位置。

``FUNC16()`` 把 SeaBIOS 中一个 16 位函数的平坦地址转换成：

::

   segment = 0xf000
   offset  = function_address - 0x000f0000

因此 IVT 中保存的不是 32 位 C 函数指针，而是传统实模式可使用的 ``f000:offset``。

硬件中断先安装两组默认 PIC 入口
-----------------------------

SeaBIOS 随后覆盖传统 PIC 使用的硬件中断范围：

.. code-block:: c

   for (i=BIOS_HWIRQ0_VECTOR; i<BIOS_HWIRQ0_VECTOR+8; i++)
       SET_IVT(i, FUNC16(entry_hwpic1));

   for (i=BIOS_HWIRQ8_VECTOR; i<BIOS_HWIRQ8_VECTOR+8; i++)
       SET_IVT(i, FUNC16(entry_hwpic2));

经典 PC 使用两片级联的 8259A PIC，每片提供 8 条 IRQ。此时具体设备还没有完成初始化，所以 SeaBIOS 先
让这 16 个硬件向量进入统一的默认 PIC 处理入口。

后面定时器、键盘、磁盘等设备建立自己的中断处理时，会继续覆盖对应向量。

BIOS 软件服务也通过 IVT 暴露
-------------------------

接下来安装的是传统 BIOS 软件中断入口：

.. code-block:: c

   SET_IVT(0x02, FUNC16(entry_02));
   SET_IVT(0x05, FUNC16(entry_05));
   SET_IVT(0x10, FUNC16(entry_10));
   SET_IVT(0x11, FUNC16(entry_11));
   SET_IVT(0x12, FUNC16(entry_12));
   SET_IVT(0x13, FUNC16(entry_13_official));
   SET_IVT(0x14, FUNC16(entry_14));
   SET_IVT(0x15, FUNC16(entry_15_official));
   SET_IVT(0x16, FUNC16(entry_16));
   SET_IVT(0x17, FUNC16(entry_17));
   SET_IVT(0x18, FUNC16(entry_18));
   SET_IVT(0x19, FUNC16(entry_19_official));
   SET_IVT(0x1a, FUNC16(entry_1a_official));
   SET_IVT(0x40, FUNC16(entry_40));

其中后面最重要的几个入口包括：

``INT 10h``
   视频服务。

``INT 13h``
   磁盘服务。GRUB 的早期阶段会依赖它读取磁盘。

``INT 15h``
   系统服务，其中包括向 bootloader 提供 E820 内存地图的接口。

``INT 16h``
   键盘服务。

``INT 19h``
   启动引导入口。SeaBIOS 完成 POST 后会通过它开始寻找启动设备。

目前这些向量只是指向 SeaBIOS 的入口代码。入口背后的设备状态和服务数据还会在后续初始化中继续建立。

保留给用户的向量不是默认iret入口
----------------------------------

安装具体入口之后， ``ivt_init()`` 还把 ``INT 60h`` 到 ``INT 66h`` 逐项写成
``0000:0000``，并把兼容软件使用的 ``INT 79h`` 同样清零。它们不是继续保留为
``entry_iret_official``：零向量明确表示当前没有由SeaBIOS安装的处理入口。因而“先把
256项全部设为默认返回”只是初始化中间态，不是函数返回时每个未列出向量的最终值。

BDA 固定在 0x400
---------------

IVT 后面紧接着是 BIOS Data Area：

::

   IVT: 0x00000 - 0x003ff
   BDA: 0x00400 - 传统约定的固定区域

SeaBIOS 用：

.. code-block:: c

   #define SEG_BDA 0x0040

表示 BDA。实模式物理地址计算为：

::

   0x0040 × 16 = 0x00000400

``bda_init()`` 先取得这个地址并把整个结构清零：

.. code-block:: c

   struct bios_data_area_s *bda = MAKE_FLATPTR(SEG_BDA, 0);
   memset(bda, 0, sizeof(*bda));

BDA 不是 SeaBIOS 私有结构。它是一块历史悠久的公共状态区，BIOS 中断处理程序、bootloader 和旧式操作
系统会直接读取其中固定偏移。

SeaBIOS 的 BDA 结构中包含：

* 串口和并口基地址；
* EBDA 段地址；
* 设备存在标志；
* 可用传统内存大小；
* 键盘状态和键盘环形缓冲区；
* 显示模式、列数、光标位置；
* BIOS 定时器计数；
* 磁盘状态；
* 串并口超时值。

现在先清零，后续每个设备初始化函数再把自己负责的字段填进去。

EBDA 为什么通常位于 0x9fc00
-------------------------

BDA 容量固定，后来增加的 BIOS 状态需要另一块区域，于是产生了 Extended BIOS Data Area，也就是 EBDA。

当前默认QEMU配置使用 ``CONFIG_MALLOC_UPPERMEMORY=y``。SeaBIOS 定义：

.. code-block:: c

   #define BUILD_LOWRAM_END 0xa0000

   #define EBDA_SIZE_START \
       DIV_ROUND_UP(sizeof(struct extended_bios_data_area_s), 1024)

   #define EBDA_SEGMENT_START \
       FLATPTR_TO_SEG(BUILD_LOWRAM_END - EBDA_SIZE_START*1024)

当前 ``extended_bios_data_area_s`` 的结构结束偏移为 ``0x121``，小于 1 KiB，向上取整后：

::

   EBDA_SIZE_START = 1 KiB

所以 EBDA 起始物理地址是：

::

   0x000a0000 - 0x400 = 0x0009fc00

转换成实模式段值：

::

   0x9fc00 / 16 = 0x9fc0

于是 ``bda_init()`` 把：

.. code-block:: c

   SET_BDA(ebda_seg, 0x9fc0);

写进 BDA。以后软件先从 BDA 读取 EBDA 段地址，再定位 EBDA；它不应该把 ``0x9fc00`` 永久写死。

这里的精确地址依赖当前默认配置。若关闭 ``CONFIG_MALLOC_UPPERMEMORY``，
``bda_init()`` 会改从 ``final_varlow_start`` 向下对齐并预留EBDA，不能继续沿用
``0x9fc00``；本章不把那个替代构建写成当前执行路径。

为什么传统可用内存会变成 639 KiB
------------------------------

SeaBIOS 同时设置：

.. code-block:: c

   SET_BDA(mem_size_kb, ebda_seg / (1024/16));

代入 ``ebda_seg = 0x9fc0``：

::

   0x9fc0 / 64 = 0x27f = 639

因此传统 BIOS 报告的可用 conventional memory 是：

::

   639 KiB

许多人只记得“传统 PC 有 640 KiB 低端内存”。这里少掉的 1 KiB 就是初始 EBDA。BIOS 不能一边把
``0x9fc00-0x9ffff`` 当成自己的数据区，一边又告诉 bootloader 这段内存可以自由覆盖。

EBDA 也要进入 E820 保留区
-----------------------

SeaBIOS 清空 EBDA、写入大小后，还执行：

.. code-block:: c

   e820_add((u32)ebda,
            BUILD_LOWRAM_END - (u32)ebda,
            E820_RESERVED);

这会把：

::

   0x0009fc00 - 0x0009ffff

标记为 ``E820_RESERVED``。

于是同一事实通过两种兼容接口表达：

* 老式软件从 BDA 的 ``mem_size_kb`` 看见可用内存只到 639 KiB；
* 新式 bootloader 通过 E820 看见顶部 1 KiB 被 BIOS 保留。

两套接口描述的是同一块物理内存边界。

额外栈为什么不能省
----------------

``bda_init()`` 最后设置：

.. code-block:: c

   StackPos = &ExtraStack[BUILD_EXTRA_STACK_SIZE]
              - SYMBOL(zonelow_base);

``ExtraStack`` 在 ``stacks.c`` 中定义为一块 ``VARLOW`` 数据：

.. code-block:: c

   u8 ExtraStack[BUILD_EXTRA_STACK_SIZE+1] VARLOW __aligned(8);
   u8 *StackPos VARLOW;

当前 ``BUILD_EXTRA_STACK_SIZE`` 是：

::

   0x800 = 2048 字节

外部程序调用 BIOS 中断时，调用者提供的栈可能很小、位置异常，或者已经接近边界。复杂 BIOS 服务若直接在
调用者栈上保存大量寄存器并调用 C 函数，容易破坏调用者数据。

SeaBIOS 因此准备一块自己的低端额外栈。需要时，16 位入口会：

#. 保存原来的 ``SS:ESP``；
#. 把 ``SS`` 切到 SeaBIOS 的低端数据段；
#. 把 ``ESP`` 切到 ``StackPos``；
#. 在自己的栈上运行处理逻辑；
#. 返回前恢复调用者的栈。

``StackPos`` 保存的是数组尾部相对 ``zonelow_base`` 的段内偏移，因为16位入口会把
``SS`` 切换到 ``SEG_LOW``。它选择数组尾部，是因为 x86 栈从高地址向低地址增长。
当前只是准备这块栈；尚未发生一次外部BIOS中断调用。

本章结束状态
------------

控制权目前走过：

::

   relocated maininit()
   → interface_init()
   → malloc_init()
   → 修复重定位后的内存区链表
   → 把 VARLOW 数据放到最终低端地址
   → 建立 ZoneLow 和 ZoneFSeg
   → qemu_cfg_init()
   → 注册 fw_cfg 文件目录
   → coreboot CBFS / multiboot路径按当前配置返回
   → ivt_init()
   → 在 0x00000 建立 256 项 IVT
   → 安装默认硬件与 BIOS 软件中断入口
   → 清零 INT 60h—66h 与 INT 79h
   → bda_init()
   → 在 0x00400 建立 BDA
   → 在 0x9fc00 建立 1 KiB EBDA
   → 把 EBDA 标记为 E820_RESERVED
   → 建立 2 KiB 额外中断栈

此刻：

* 当前执行者：SeaBIOS ``interface_init()``；
* 当前 CPU：BSP；
* CPU 模式：32 位保护模式；
* 分页：关闭；
* 可屏蔽中断：关闭；NMI仍由CMOS index bit 7屏蔽；
* 当前 ``ESP``：低于初始栈顶 ``0x7000``，精确值不固定；
* IVT：已经建立；
* IVT保留项： ``INT 60h—66h`` 与 ``INT 79h`` 为 ``0000:0000``；
* BDA：已经建立，后续设备字段仍待填充；
* EBDA：位于 ``0x9fc00``，初始大小 1 KiB；
* traditional memory size：639 KiB；
* E820：EBDA 区域已经标记为保留；
* 固件额外 16 位栈：已经建立；
* GRUB：尚未被搜索；
* Linux：尚未装入内存。

关键边界
--------

#. ``0x7000`` 是早期栈顶初值，不是本章结束时的精确 ``ESP``；
   ``call16_override()`` 后续只要求当前栈没有越过该上界。
#. 当前默认QEMU构建只由 ``qemu_cfg_init()`` 添加fw_cfg romfile；coreboot CBFS和
   multiboot模块路径在各自配置检查处返回。
#. IVT先统一填默认入口，再覆盖硬件和软件服务，最后明确清零用户保留向量；不能把
   第一轮循环当成最终IVT全貌。
#. ``0x9fc00``、639 KiB和1 KiB EBDA是默认 ``CONFIG_MALLOC_UPPERMEMORY=y``
   路径的共同结果，不是所有SeaBIOS构建的不变量。
#. BDA的传统内存计数与E820保留项从两个接口描述同一块EBDA所有权；两者不能只更新一个。
#. ``ExtraStack`` 和 ``StackPos`` 此时只建立可用空间，没有证明任何外部中断已经发生。

下一入口
--------

控制流仍在 ``interface_init()``，下一条真实调用是 ``boot_init()``。此时具体启动设备、
PCI枚举、PS/2控制器和磁盘控制器都尚未初始化。

资料
----

* `SeaBIOS src/post.c：IVT、BDA与interface_init <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/post.c#L32-L123>`_；
* `SeaBIOS src/malloc.c：重定位后malloc修复 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/malloc.c#L493-L528>`_；
* `SeaBIOS src/fw/paravirt.c：fw_cfg romfile目录 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/paravirt.c#L691-L727>`_；
* `SeaBIOS src/biosvar.h：IVT和EBDA定位 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/biosvar.h#L15-L71>`_；
* `SeaBIOS src/std/bda.h：BDA与EBDA布局 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/std/bda.h#L13-L159>`_；
* `SeaBIOS src/stacks.c：ExtraStack切换 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/stacks.c#L321-L367>`_；
* `SeaBIOS src/Kconfig：额外栈与低端分配默认配置 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/Kconfig#L105-L130>`_；
* `SeaBIOS Memory model <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/docs/Memory_Model.md>`_；
* `SeaBIOS execution and code flow <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/docs/Execution_and_code_flow.md>`_。
