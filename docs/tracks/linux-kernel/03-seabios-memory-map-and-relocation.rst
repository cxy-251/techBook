第三章：SeaBIOS 怎样识别内存并把初始化代码搬到 RAM？
=====================================================

上一章结束时，BSP 已经进入 32 位保护模式，并跳入：

::

   src/post.c:handle_post()

当前 CPU 使用平坦代码段和数据段，分页仍然关闭，栈位于 ``0x7000``。这只是让 C 代码能够运行起来，
还不代表 SeaBIOS 已经知道哪些内存可用，也不代表 BIOS 所在区域能够写入。

本章继续使用固定源码：

::

   repository: coreboot/seabios
   commit: c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf

故事从 ``handle_post()`` 的第一条调用开始，结束在一次性初始化代码完成重定位，重定位后的
``maininit()`` 开始执行。

handle_post 只有五个调用
-----------------------

``src/post.c`` 中的入口本身很短：

.. code-block:: c

   void VISIBLE32FLAT
   handle_post(void)
   {
       if (!CONFIG_QEMU && !CONFIG_COREBOOT)
           return;

       serial_debug_preinit();
       debug_banner();
       xen_preinit();
       make_bios_writable();
       dopost();
   }

这五个调用不是完整 POST。它们先建立最低限度的调试输出，判断当前虚拟化环境，让 BIOS 映射可写，
然后才进入 ``dopost()`` 准备内存地图和初始化代码重定位。

为什么先建立调试输出
------------------

启动早期还没有 VGA 文本界面，也没有操作系统日志。某条指令失败后，屏幕上可能什么都看不到。
SeaBIOS 因此先执行：

.. code-block:: c

   serial_debug_preinit();
   debug_banner();

``serial_debug_preinit()`` 位于 ``src/hw/serialio.c``。启用了串口调试的构建会把调试串口设置为
``8N1``：8 个数据位、无奇偶校验、1 个停止位，同时关闭串口中断。

它直接访问串口寄存器，不依赖 Linux 驱动：

.. code-block:: c

   oldparam = serial_debug_read(SEROFF_LCR);
   serial_debug_write(SEROFF_LCR, 0x03);

   oldier = serial_debug_read(SEROFF_IER);
   serial_debug_write(SEROFF_IER, 0);

当前 CPU 的普通硬件中断本来就处于关闭状态。串口也使用轮询方式输出：代码反复读取线路状态寄存器，
直到发送寄存器可写，再把字符送出。这样即使中断控制器尚未初始化，SeaBIOS 仍然能留下启动痕迹。

没有启用相应调试配置时，这个函数直接返回。它不会改变启动主流程，只决定早期错误是否容易被观察。

``debug_banner()`` 随后输出 SeaBIOS 版本和构建信息：

.. code-block:: c

   void
   debug_banner(void)
   {
       dprintf(1, "SeaBIOS (version %s)\n", VERSION);
       dprintf(1, "BUILD: %s\n", BUILDINFO);
   }

这里的输出通常进入 QEMU debugcon、串口或其他已启用的调试通道，不等同于用户稍后看到的 BIOS 启动画面。

先排除 Xen 路径
--------------

接下来执行：

.. code-block:: c

   xen_preinit();

SeaBIOS 同一份代码可以运行在不同虚拟化环境中。Xen HVM 会通过一组 CPUID 叶子暴露：

::

   XenVMMXenVMM

``xen_preinit()`` 从 ``0x40000000`` 开始按 ``0x100`` 递增扫描 hypervisor CPUID 空间。如果找到 Xen
签名，它会切换到 Xen 的调试端口、读取 Xen 提供的信息结构，并把平台状态标记为 Xen。

当前主线是普通的 ``QEMU q35``，没有 Xen HVM 信息结构，因此这个函数不会改变平台路径。把检测放在
这里很重要：后面的 BIOS 内存映射、内存表来源和设备初始化方式会因 Xen 与普通 QEMU 而不同。

BIOS 为什么不能直接修改自己的变量
-------------------------------

CPU 当前正在执行 SeaBIOS 的 32 位 C 代码，但 SeaBIOS 最初来自 ROM 映像。ROM 中的字节可以取指和读取，
不能像普通 RAM 一样随意修改。

SeaBIOS 的固定运行代码和一部分全局变量位于传统 BIOS 区域：

::

   0x000f0000 - 0x000fffff

在 QEMU q35 中，这段低地址区域由芯片组的 PAM，也就是 Programmable Attribute Map 寄存器控制。
PAM 决定相应地址范围的读取来自固件 ROM 还是 shadow RAM，以及写操作是否允许进入 RAM。

所谓 shadow RAM，是在与传统 ROM 相同的 CPU 地址上提供一份 RAM 后备。对 CPU 来说地址仍然是
``0xf0000`` 附近，底层存储已经可以修改。

handle_post 调用：

.. code-block:: c

   make_bios_writable();

这个函数位于 ``src/fw/shadow.c``。它遍历 PCI 配置空间，寻找当前平台的主桥。q35 主桥被识别后，
SeaBIOS 使用 ``Q35_HOST_BRIDGE_PAM0`` 对应的 PAM 寄存器修改 ``0xc0000-0x100000`` 区域属性。

为什么要从高地址固件副本执行复制代码
--------------------------------

q35 的固件内容同时存在一个高地址映射。SeaBIOS 把两者之间的差值定义为：

.. code-block:: c

   #define BIOS_SRC_OFFSET 0xfff00000

因此：

::

   低地址 BIOS 区：0x000f0000
   加上偏移：      0xfff00000
   高地址固件区：  0xffff0000

如果低地址 BIOS 区还没有 RAM 后备，SeaBIOS 不能一边改变这一区域的映射，一边继续从同一区域执行代码。
映射切换到 RAM 后，原先正在取指的 ROM 字节可能立即消失。

源码采用的办法是先计算 ``__make_bios_writable_intel()`` 在高地址固件副本中的位置：

.. code-block:: c

   u32 pos = (u32)__make_bios_writable_intel + BIOS_SRC_OFFSET;
   void (*func)(u16 bdf, u32 pam0) = (void*)pos;
   func(bdf, pam0);

CPU 暂时从 ``0xffff0000`` 附近的固件映射执行辅助函数。辅助函数打开 PAM 的 RAM 读写属性，再把永久
32 位运行代码从高地址固件副本复制到低地址 shadow RAM：

.. code-block:: c

   memcpy(VSYMBOL(code32flat_start),
          VSYMBOL(code32flat_start) + BIOS_SRC_OFFSET,
          SYMBOL(code32flat_end) - SYMBOL(code32flat_start));

复制完成后，低地址 ``0xf0000`` 区域保存的不再只是不可修改的 ROM 映射，而是一份可写的 RAM 副本。
后面的全局状态、重定位指针和运行时数据才能安全更新。

HaveRunPost 在这里变成 1
-----------------------

``make_bios_writable()`` 成功处理 q35 主桥后调用：

.. code-block:: c

   code_mutable_preinit();

这个函数执行：

.. code-block:: c

   if (HaveRunPost)
       return;

   rtc_write(CMOS_RESET_CODE, 0);
   barrier();
   HaveRunPost = 1;
   barrier();

``HaveRunPost`` 就是第二章在 ``entry_post`` 检查的变量。

它的状态可以理解为：

::

   0：POST 尚未开始
   1：POST 正在进行
   2：POST 已完成，准备启动操作系统

这里把它设为 ``1``，意味着从现在起再次经过复位向量时，SeaBIOS 不应把机器当成从未初始化过。

``barrier()`` 是编译器屏障，用来阻止编译器把关键内存操作跨过状态更新随意重排。它不是 CPU 缓存刷新，
也不是多核同步协议；这里的目标是让源代码规定的状态发布顺序保留下来。

handle_post 进入 dopost
----------------------

完成 shadow RAM 准备后，``handle_post()`` 调用：

.. code-block:: c

   dopost();

``dopost()`` 的源码是：

.. code-block:: c

   void VISIBLE32INIT
   dopost(void)
   {
       code_mutable_preinit();

       qemu_preinit();
       coreboot_preinit();
       malloc_preinit();

       reloc_preinit(maininit, NULL);
   }

第一行再次调用 ``code_mutable_preinit()``。在当前 q35 路径中，``make_bios_writable()`` 已经把
``HaveRunPost`` 设为 ``1``，所以第二次调用立即返回。

这个重复调用不是重复执行 POST。它让其他构建路径也能在进入 ``dopost()`` 时完成同样的状态初始化，
同时依靠 ``HaveRunPost`` 保持幂等性。

qemu_preinit 先确认自己运行在哪个平台
-----------------------------------

``qemu_preinit()`` 位于 ``src/fw/paravirt.c``。它先执行：

.. code-block:: c

   qemu_detect();
   kvm_detect();

``qemu_detect()`` 读取 PCI 配置空间中 ``00:00.0`` 的主桥标识。当前 q35 主桥的设备 ID 是：

::

   0x29c0

SeaBIOS 还检查 QEMU 使用的子系统厂商和设备标识。匹配后设置 ``PF_QEMU``，并使用 CPUID 判断处理器的
物理地址位数以及是否支持 long mode。

这里还没有进入 64 位模式。检测 long mode 只是记录这颗虚拟 CPU 将来是否具备运行 64 位操作系统的能力。

``kvm_detect()`` 检查 hypervisor CPUID 签名 ``KVMKVMKVM``。使用 QEMU TCG 时不会找到它；使用
QEMU + KVM 加速时会记录 KVM 能力。无论是否使用 KVM，客户机看到的 q35、SeaBIOS 和后续 Linux 启动
主线保持一致，差别主要在虚拟 CPU 由软件翻译还是硬件虚拟化执行。

SeaBIOS 第一次建立 E820 内存地图
-----------------------------

确定普通 QEMU 路径后，``qemu_preinit()`` 需要回答一个基础问题：

   客户机物理地址空间中，哪些范围是真正可用的 RAM，哪些范围必须保留？

它首先调用 ``qemu_early_e820()``。E820 是传统 PC 固件向启动软件描述物理地址范围的内存地图格式。
每一项至少包含：

* 起始物理地址；
* 长度；
* 类型。

常见类型包括：

``E820_RAM``
   可以作为普通内存使用。

``E820_RESERVED``
   被固件、设备窗口或平台结构占用，不能当普通 RAM 分配。

``E820_SOFT_RESERVED``
   平台希望保留，由后续软件按照更具体规则处理。

QEMU 通过 ``fw_cfg`` 接口向固件提供配置数据。``qemu_early_e820()`` 先检查 ``fw_cfg`` 签名是否为
``QEMU``，然后在文件目录中查找：

::

   etc/e820

此时正式的 SeaBIOS 内存分配器尚未建立，所以源码特意只使用栈上结构，并分块读取 ``fw_cfg``。找到文件后，
它逐项读取 E820 表，把范围加入 SeaBIOS 的内部 ``e820_list``，同时计算：

``RamSize``
   4 GiB 以下连续 RAM 的上界。

``RamSizeOver4G``
   4 GiB 以上 RAM 的规模。

如果较老的 QEMU 没有提供 ``etc/e820``，SeaBIOS 才退回 CMOS 中的内存容量字段，构造一条基础 RAM
记录。当前路径优先使用 ``fw_cfg`` 提供的完整地图。

最后，SeaBIOS额外保留 4 GiB 顶部的 256 KiB：

.. code-block:: c

   e820_add(0xfffc0000, 256 * 1024, E820_RESERVED);

这个范围包含固件高地址映射，不能被后面的通用内存分配覆盖。

为什么此时就要有 E820
-------------------

E820 不只是稍后交给 Linux 的一张表。SeaBIOS 自己马上就需要它：

* 找出可以存放临时初始化代码的 RAM；
* 保留 BIOS、设备窗口和固件表使用的区域；
* 建立内部内存分配区域；
* 最终通过 BIOS 接口把整理后的地图提供给 bootloader 和内核。

因此这里的顺序不能反过来。SeaBIOS 必须先知道哪里是 RAM，才能安全建立内存分配器和搬运代码。

coreboot_preinit 为什么什么也没做
-------------------------------

``dopost()`` 随后无条件写着：

.. code-block:: c

   coreboot_preinit();

SeaBIOS 也能作为 coreboot 的 payload 使用。在那条路径中，``coreboot_preinit()`` 会寻找 coreboot table，
读取 coreboot 提供的内存地图。

当前构建使用 QEMU 自己加载 SeaBIOS，``CONFIG_COREBOOT`` 不成立，因此函数在入口直接返回。源码保留同一条
调用序列，是为了让不同平台共享 POST 主流程；真正执行哪一条平台分支由构建配置和运行检测共同决定。

malloc_preinit 把 E820 变成可分配区域
---------------------------------

有了 E820 地图后，``malloc_preinit()`` 开始建立 SeaBIOS 自己的早期内存区域。

第一步先处理传统 PC 的特殊地址窗口：

.. code-block:: c

   e820_remove(BUILD_LOWRAM_END,
               BUILD_BIOS_ADDR - BUILD_LOWRAM_END);
   e820_add(BUILD_BIOS_ADDR, BUILD_BIOS_SIZE, E820_RESERVED);

相关常量是：

::

   BUILD_LOWRAM_END = 0x000a0000
   BUILD_BIOS_ADDR  = 0x000f0000
   BUILD_BIOS_SIZE  = 0x00010000

因此：

* ``0x000a0000-0x000f0000`` 不被声明成普通 RAM；
* ``0x000f0000-0x00100000`` 明确标记为 BIOS 保留区域。

``0xa0000`` 以上、1 MiB 以下的地址传统上混有 VGA 显存、扩展 ROM、设备窗口和 BIOS。即使某份粗略内存
容量数据覆盖这里，也不能把它直接交给普通分配器。

临时低端内存区
--------------

SeaBIOS 建立：

::

   ZoneTmpLow = 0x00007000 - 0x00090000

源码对应：

.. code-block:: c

   alloc_add(&ZoneTmpLow, BUILD_STACK_ADDR, BUILD_EBDA_MINIMUM);

其中：

::

   BUILD_STACK_ADDR  = 0x7000
   BUILD_EBDA_MINIMUM = 0x90000

第二章建立的早期栈位于这一区域起点。后续初始化代码可以从临时低端区分配小块内存。

这片区域没有永久从操作系统内存中扣除。POST 结束前，SeaBIOS 会清理并停止使用它，所以名字中带有
``Tmp``。把临时内存误当成永久内存，会让固件在启动操作系统后继续访问已经被内核重新使用的地址。

临时高端区和永久表区
------------------

``malloc_preinit()`` 从 E820 的高地址端向下扫描 4 GiB 以下的 ``E820_RAM`` 区域。

大部分可用 RAM 被加入：

::

   ZoneTmpHigh

它用于 POST 阶段的大块临时分配，例如即将搬迁的一次性初始化代码。

在最高的一段合适 RAM 顶部，SeaBIOS 还会预留 ``ZoneHigh``。它的大小通常在 256 KiB 到 16 MiB 之间，
用于稍后保存需要跨越固件启动阶段继续存在的结构，例如 ACPI、SMBIOS、MP table 和部分 DMA 缓冲区。

``ZoneHigh`` 会通过 E820 标为 ``E820_RESERVED``，避免 bootloader 或 Linux 把它当作普通 RAM 覆盖；
``ZoneTmpHigh`` 则只在初始化阶段使用，最终可以归还。

为什么要搬走初始化代码
--------------------

此时 SeaBIOS 的一次性 POST 代码仍然和运行时 BIOS 代码一起占用传统 ``0xc0000-0x100000`` 区域。
这里空间很紧张，还要容纳：

* VGA 与其他 Option ROM；
* 传统 BIOS 固定入口；
* 运行时 BIOS 代码和变量；
* BIOS 表与兼容区域。

大量设备初始化函数只会在开机时执行一次。操作系统启动后，这些代码没有继续留在传统 BIOS 区的价值。
SeaBIOS 因此把“只在初始化阶段可达”的 32 位代码识别为 ``code32init``，启动时把它搬到普通 RAM 执行。

构建系统已经提前完成两件事：

#. 找出从 ``VISIBLE32INIT`` 入口可达、只用于初始化的函数；
#. 记录这些代码中需要在搬迁后修正的地址位置。

``dopost()`` 自身带有 ``VISIBLE32INIT``，``maininit()`` 以及它调用的大量初始化函数由此归入一次性初始化
代码集合。

reloc_preinit 选择新地址
-----------------------

``dopost()`` 最后调用：

.. code-block:: c

   reloc_preinit(maininit, NULL);

``reloc_preinit()`` 先取得初始化代码的原始范围和大小：

.. code-block:: c

   u32 initsize = SYMBOL(code32init_end) - SYMBOL(code32init_start);
   u32 codealign = SYMBOL(_reloc_min_align);
   void *codedest = memalign_tmp(codealign, initsize);
   void *codesrc = VSYMBOL(code32init_start);

``memalign_tmp()`` 从刚刚建立的临时内存区中寻找满足大小和对齐要求的空间。通常优先使用临时高端 RAM，
空间不足时才考虑其他允许的临时区域。

得到目标地址后，SeaBIOS 复制整段初始化代码：

.. code-block:: c

   memcpy(codedest, codesrc, initsize);

单纯 memcpy 为什么还不能执行
--------------------------

机器码中可能嵌入绝对地址，也可能包含指向其他初始化函数或永久运行时代码的引用。

假设一段代码原来位于：

::

   0x000f4000

现在被复制到：

::

   0x03a00000

代码中的绝对函数地址、全局地址或跨区域引用仍然保存旧值，CPU 会跳回原位置或访问错误数据。
所以复制完成后必须处理重定位。

SeaBIOS 构建阶段生成了几组重定位位置表。运行时计算：

::

   delta = codedest - codesrc

然后依次修正：

* 初始化代码中的绝对地址；
* 初始化代码中的相对引用；
* 永久运行时代码中指向初始化代码的引用。

源码对应：

.. code-block:: c

   updateRelocs(codedest,
                VSYMBOL(_reloc_abs_start),
                VSYMBOL(_reloc_abs_end),
                delta);

   updateRelocs(codedest,
                VSYMBOL(_reloc_rel_start),
                VSYMBOL(_reloc_rel_end),
                -delta);

   updateRelocs(VSYMBOL(code32flat_start),
                VSYMBOL(_reloc_init_start),
                VSYMBOL(_reloc_init_end),
                delta);

不同表中记录的是“哪一个 32 位值需要修正”，正负 ``delta`` 取决于该值代表绝对地址还是相对位移。
这些位置已经由链接阶段计算，启动时不需要反汇编并猜测每条指令。

maininit 的函数指针也要跟着移动
---------------------------

传给 ``reloc_preinit()`` 的 ``maininit`` 指针最初指向旧代码区域。复制后，函数入口也移动了 ``delta``。
源码检查它是否落在原始初始化代码范围内：

.. code-block:: c

   if (f >= codesrc && f < VSYMBOL(code32init_end))
       func = f + delta;

随后执行：

.. code-block:: c

   barrier();
   func(arg);

这不是一次会返回原处的普通阶段调用。``maininit()`` 被声明为不会返回；从这里开始，CPU 在新 RAM 地址
执行重定位后的一次性初始化代码。原先传统 BIOS 区中对应的空间以后可以让给运行时固件、Option ROM 和
其他兼容数据。

第三章结束时的机器状态
--------------------

控制权目前走过：

::

   post.c:handle_post()
   → 建立早期调试输出
   → 排除 Xen 路径
   → q35 PAM 打开 shadow RAM 写入
   → 从高地址固件副本复制 32 位运行代码
   → HaveRunPost = 1
   → post.c:dopost()
   → 检测 QEMU / KVM
   → 从 fw_cfg 读取 E820
   → 建立临时低端区、临时高端区和永久高端区
   → 复制 code32init
   → 修正重定位项
   → 跳入重定位后的 maininit()

此刻：

* 当前执行者：重定位后的 SeaBIOS ``maininit()``；
* 当前 CPU：BSP；
* CPU 模式：32 位保护模式；
* 分页：关闭；
* 当前栈：仍位于低端地址 ``0x7000``；
* BIOS 低地址映射：shadow RAM，可写；
* E820：已经形成初始内存地图；
* 临时内存分配区：已经建立；
* 一次性初始化代码：已经搬到普通 RAM；
* GRUB：尚未被搜索；
* Linux：尚未装入内存。

下一段控制流从 ``maininit()`` 开始。它将初始化 SeaBIOS 内部接口、IVT、BDA、EBDA、平台设备和计时
设施，随后才逐步获得访问磁盘、键盘、显示设备和其他启动资源的能力。

章节导航
--------

* `上一章：SeaBIOS 怎样从 16 位入口进入 32 位 C 代码？ <02-seabios-entry-to-32bit-c.rst>`_
* `返回 Linux Kernel 目录 <index.rst>`_

资料
----

* `SeaBIOS src/post.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/post.c>`_；
* `SeaBIOS src/fw/shadow.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/shadow.c>`_；
* `SeaBIOS src/fw/paravirt.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/paravirt.c>`_；
* `SeaBIOS src/fw/xen.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/fw/xen.c>`_；
* `SeaBIOS src/malloc.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/malloc.c>`_；
* `SeaBIOS src/output.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/output.c>`_；
* `SeaBIOS src/hw/serialio.c <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/hw/serialio.c>`_；
* `SeaBIOS Linking overview <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/docs/Linking_overview.md>`_；
* `SeaBIOS Memory model <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/docs/Memory_Model.md>`_；
* `SeaBIOS execution and code flow <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/docs/Execution_and_code_flow.md>`_。