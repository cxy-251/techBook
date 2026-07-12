第二十六章：GRUB 怎样通过 BIOS E820 建立自己的堆？
=================================================

上一章结束时，GRUB 已经把正式核心复制到链接地址 ``0x9000``，清零 BSS，并在 32 位保护模式下
调用：

.. code-block:: c

   grub_main();

此时 GRUB 已经可以执行普通 C 代码，却还不能随意调用 ``grub_malloc()``。原因很直接：它尚未把
哪段物理内存属于可用 RAM、哪段仍被自身映像和预装模块占用，转换成自己的内存分配器。

``grub_main()`` 的第一条主流程调用因此是：

.. code-block:: c

   grub_machine_init();

这一章只追踪 ``grub_machine_init()``。它会建立早期控制台，从 SeaBIOS 重新取得 E820 内存地图，
排除低端保留区和 GRUB 自身模块，然后把剩余 RAM 注册成 GRUB 的堆。

当前代码与数据在哪里
--------------------

进入 ``grub_machine_init()`` 时，关键内存可以先画成：

::

   0x00000..0x003ff   IVT
   0x00400..          BDA 等传统低端结构
   0x01ff0            GRUB 早期实模式栈顶
   0x09000...         已搬回链接地址的正式 GRUB core
   0x68000..0x70fff   GRUB BIOS 调用 scratch 区
   0x7fff0             GRUB 保护模式栈顶附近
   0xa0000..0xfffff   VGA、Option ROM、BIOS 区域
   0x100000...         解压输出留下的预装模块和模块元数据

分页仍然关闭，GRUB 使用平坦段，所以当前 C 指针的数值就是对应的物理地址。

先检查一个只针对旧 VIA CPU 的兼容分支
-------------------------------------

``grub_machine_init()`` 首先调用：

.. code-block:: c

   grub_via_workaround_init();

它通过 CPUID 检查 CPU 厂商字符串是否为 ``CentaurHauls``，并且只对较旧的 VIA C3 及更早模型设置
额外的 ``wbinvd`` 兼容补丁。

当前 QEMU q35 主线不会命中这个分支。这里仍要在时间线上交代，因为它发生在任何 BIOS 调用之前；
源码明确要求某些 VIA 处理器必须先修正缓存一致性问题，后面通过 BIOS 中断取得内存地图才安全。

定位留在 1 MiB 区域中的预装模块
-------------------------------

接下来执行：

.. code-block:: c

   grub_modbase = GRUB_MEMORY_MACHINE_DECOMPRESSION_ADDR
                  + (_edata - _start);

其中：

::

   GRUB_MEMORY_MACHINE_DECOMPRESSION_ADDR = 0x100000

``_start.._edata`` 是正式 GRUB core 中已经初始化的代码和数据范围。上一章中，``startup.S`` 只把
这部分从 1 MiB 解压区复制回链接地址 ``0x9000``；紧随其后的预装模块没有一起搬回低端内存。

因此 ``grub_modbase`` 指向：

::

   0x100000 + 正式 core 的已初始化映像大小

这里首先是 ``struct grub_module_info``，其 magic 为 ``0x676d696d``，也就是字节形式的 ``gmim``；
后面依次排列 ELF 模块、嵌入配置、prefix 字符串等对象。

这个地址马上会参与堆边界计算。GRUB 不能把仍保存 ``biosdisk``、分区模块、文件系统模块和
``normal`` 等对象的区域当成空闲 RAM。

为什么控制台要在堆完全建立前初始化
----------------------------------

随后执行：

.. code-block:: c

   grub_console_init();

PC BIOS 目标的早期 console 把 GRUB 的终端输入、输出连接到传统 BIOS 服务。后面的
``Welcome to GRUB!``、错误信息和 rescue shell 都依赖它。

此时尚未建立图形菜单，也没有加载字体或主题。当前只是让 GRUB 拥有最基本的字符输入输出能力，
并继续借用 SeaBIOS 已经建立的键盘和显示服务。

GRUB 在保护模式中不能直接执行 int 15h
---------------------------------------

内存地图入口是：

.. code-block:: c

   grub_machine_mmap_iterate(mmap_iterate_hook, NULL);

源码最终需要调用 BIOS：

::

   INT 15h
   EAX = 0xe820
   EDX = 0x534d4150   "SMAP"

CPU 当前处于 32 位保护模式。传统 BIOS 中断处理程序仍是 16 位实模式代码，所以 GRUB 使用上一章
已经保留下来的 ``prot_to_real`` / ``real_to_prot`` 桥：

::

   32 位 GRUB C 代码
   → 保存保护模式现场
   → 切到实模式和实模式栈
   → 执行 INT 15h
   → 恢复 GDT、保护模式栈和寄存器
   → 返回 32 位 C 代码

所以“GRUB 调用 BIOS”不是保护模式下直接执行一条 ``int`` 就结束。中间实际发生了一次 CPU 模式
往返。

E820 返回缓冲区为什么放在 0x68000
--------------------------------

PC BIOS 的 mmap 代码把临时结构放到：

::

   GRUB_MEMORY_MACHINE_SCRATCH_ADDR = 0x68000

这个区域位于 1 MiB 以下，实模式可以使用 ``ES:DI`` 表示它，同时又避开 ``0x7c00``、GRUB core、
保护模式栈以及 BIOS 区域。

GRUB 为每次 E820 调用准备：

::

   EAX = 0xe820
   EDX = "SMAP"
   ECX = 20 字节以上的返回缓冲长度
   EBX = continuation value
   ES:DI = scratch 区中 entry.addr 的实模式地址

第一次调用 ``EBX=0``。SeaBIOS 返回一项后，把新的 continuation value 放回 ``EBX``；GRUB 用它继续
请求下一项，直到 ``EBX=0`` 或调用失败。

每项至少包含：

::

   addr   64 位物理起点
   len    64 位长度
   type   32 位类型

GRUB 同时检查：

* Carry Flag 必须清零；
* 返回 ``EAX`` 仍然是 ``SMAP``；
* 返回长度不能小于 20 字节；
* 长度不能超过本地允许的上限。

当前 SeaBIOS 路径能够正常返回 E820，所以 ``INT 15h E801h``、``AH=88h`` 和 ``INT 12h`` 等旧式
回退路径不会执行。它们只用于兼容不提供 E820 的老固件。

为什么 GRUB 不把 E820 中所有 RAM 都加入堆
-----------------------------------------

SeaBIOS 返回的 E820 是平台物理内存地图。GRUB 的 ``mmap_iterate_hook()`` 还要做自己的筛选。

第一条规则是跳过 1 MiB 以下区域：

::

   GRUB_MEMORY_MACHINE_UPPER_START = 0x100000

当前实现没有把低端常规内存加入通用堆。低端内存中仍存在 IVT、BDA、EBDA、BIOS scratch、实模式
栈、保护模式栈和其他兼容结构；让普通 ``grub_malloc()`` 从这里分配会让后续 BIOS 调用变得危险。

第二条规则是只接收：

::

   type == GRUB_MEMORY_AVAILABLE

ACPI reclaim、ACPI NVS、reserved 和 bad RAM 都不会进入堆。

第三条规则是当前 i386-pc core 只接收 4 GiB 以下的可寻址部分。GRUB 此时使用 32 位指针且没有
分页映射机制，不能把 4 GiB 以上物理 RAM 直接变成普通 C 指针。

因此这里建立的是“GRUB 当前能安全分配的内存集合”，不是对 E820 的原样复制。

先排序、再合并内存区间
----------------------

筛选后的区间先暂存在最多 32 项的 ``mem_regions[]`` 中。``compact_mem_regions()`` 会：

#. 按起始物理地址升序排列；
#. 合并重叠区间；
#. 合并首尾相接的区间。

这样可以避免同一片 RAM 被注册成多个相互覆盖的 allocator region。

为什么堆起点必须越过 grub_modules_get_end()
--------------------------------------------

接下来：

.. code-block:: c

   modend = grub_modules_get_end();

``grub_modules_get_end()`` 读取 ``gmim`` 头中的总大小，计算预装模块区末端。对于每个可用 E820
区域，GRUB 使用：

.. code-block:: c

   beg = region.addr;
   fin = region.addr + region.size;

   if (modend && beg < modend)
       beg = modend;

如果整个区间都位于 ``modend`` 以下，它会被跳过；如果同一 E820 RAM 区从 1 MiB 延伸到高地址，
堆只从模块区末端之后开始。

这一步保护的内容包括：

* ``struct grub_module_info``；
* 已嵌入 core.img 的 ELF 模块；
* embedded prefix；
* 可选 embedded config、密钥和其他对象。

这些对象稍后还要被 ``grub_main()`` 遍历和加载，不能提前被内存分配覆盖。

GRUB 的堆不是一段连续大数组
--------------------------

每个通过筛选的区间都会调用：

.. code-block:: c

   grub_mm_init_region((void *) beg, fin - beg);

GRUB allocator 支持多个互不连续的 region。每个 region 的开头直接存放 ``struct grub_mm_region``，
后面的空间被切成 allocator cell。

在当前 32 位目标中，一个 cell 是 16 字节。已分配块和空闲块都在数据前保存 header：

::

   region metadata
   → free/allocated block header
   → returned payload
   → next block ...

空闲块组成单向环形链表。分配器可以在多个 E820 可用区间之间寻找空间，而不要求整台机器的 RAM
物理连续。

``grub_mm_init_region()`` 还会处理：

* 起止地址对齐；
* region metadata 自身占用；
* 邻接 region 合并；
* block magic 校验；
* 尾部溢出保护。

所以这里不是简单保存一个 ``heap_start`` 和 ``heap_end``。GRUB 已经建立了能够支持
``malloc/free/memalign`` 的正式内存管理器。

最后把 TSC 校准成毫秒时间源
--------------------------

堆建立后，``grub_machine_init()`` 最后调用：

.. code-block:: c

   grub_tsc_init();

如果 CPU 支持 ``RDTSC``，PC BIOS 路径优先使用 PIT 校准 TSC。校准结果保存为每 ``2^32`` 个 TSC
 tick 对应的毫秒数，此后 GRUB 可以把：

::

   current_tsc - tsc_boot_time

转换为毫秒。

若 CPU 不支持 TSC，PC BIOS 目标回退到 ``INT 1Ah`` 提供的约 18.2 Hz BIOS tick。当前 QEMU 的
x86 CPU 支持 TSC，因此走 TSC 校准路径。

这一时间源会用于超时、菜单倒计时、性能时间戳和设备等待，但它还不是 Linux 内核以后建立的
clocksource。

本章结束时的状态
----------------

``grub_machine_init()`` 返回时：

::

   当前执行者      GNU GRUB 2.14 grub_main()
   CPU 模式         32 位保护模式
   paging           off
   console          早期 BIOS 字符终端已注册
   BIOS bridge      仍可往返实模式
   E820             已重新通过 SeaBIOS INT 15h 取得
   heap source      1 MiB 以上、4 GiB 以下的 E820 available RAM
   low memory       未加入普通 GRUB heap
   module area      已由 grub_modbase/modend 排除
   allocator        多 region 堆已经建立
   time source      TSC 已用 PIT 校准
   embedded modules 尚未加载执行
   root/prefix      尚未建立
   hd0              尚未作为 GRUB disk backend 打开
   grub.cfg         尚未读取
   Linux bzImage    尚未读取

``grub_main()`` 接下来会输出欢迎信息，初始化 verifier，遍历 core.img 中的预装对象并加载 ELF 模块。

资料
----

* `GNU GRUB 2.14 grub-core/kern/main.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/main.c>`_
* `GNU GRUB 2.14 grub-core/kern/i386/pc/init.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/i386/pc/init.c>`_
* `GNU GRUB 2.14 grub-core/kern/i386/pc/mmap.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/i386/pc/mmap.c>`_
* `GNU GRUB 2.14 grub-core/kern/mm.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/mm.c>`_
* `GNU GRUB 2.14 grub-core/kern/i386/tsc.c <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/i386/tsc.c>`_
* `GNU GRUB 2.14 include/grub/i386/memory.h <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/include/grub/i386/memory.h>`_
* `GNU GRUB 2.14 include/grub/kernel.h <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/include/grub/kernel.h>`_
