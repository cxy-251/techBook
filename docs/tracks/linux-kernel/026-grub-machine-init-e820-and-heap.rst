第二十六章：GRUB怎样通过BIOS E820建立自己的堆？
==============================================

第025章把正式GRUB core放到链接地址 ``0x9000``，清零BSS并以
``grub_boot_device=0x80ffffff`` 调用 ``grub_main()``。BSP处于32位flat保护模式、分页
关闭、A20已验证，IF=0、DF=0，保护模式IDT的limit为0；高端 ``0x100000`` 解压区仍保存
临时kernel副本、module-info和原始预装对象。

此刻普通C代码已经能运行，但 ``grub_malloc()`` 还没有可分配region。 ``grub_main`` 若按
构建选项启用了stack protector会先更新guard；第一个无条件机器初始化入口随后是：

.. code-block:: c

   grub_machine_init();

本章只追踪这次调用，停在它返回、尚未记录 ``After machine init`` 时间点之前。它必须在没有
heap的条件下完成早期console注册，借BIOS桥重新枚举E820，排除仍被GRUB自身占用的高端对象，
再把剩余RAM交给allocator。

为什么先处理VIA C3兼容分支
--------------------------

``grub_machine_init`` 的第一步是 ``grub_via_workaround_init()``。它先检查CPUID是否存在，
再比较vendor string ``CentaurHauls``，只对VIA C3及更早model把BIOS bridge里的两组NOP改成
``wbinvd`` 并立即执行一次 ``wbinvd``。

当前固定条件没有唯一指定QEMU ``-cpu`` 参数或CPU model，因此不能把vendor固定成AMD，也不能
把这条分支直接删掉。非Centaur或较新model会原样返回，bridge代码保持NOP；只有满足源码门槛的
VIA CPU才会改写并flush。两条正常路径都汇合到下一条 ``grub_modbase`` 赋值；差别只在后续
BIOS桥是否带这个旧CPU cache workaround。

grub_modbase为什么必须在heap之前确定
------------------------------------

下一条写入全局变量：

.. code-block:: c

   grub_modbase = 0x100000 + (_edata - _start);

第025章只把解压输出中的 ``_start.._edata`` 复制回 ``0x9000``。所以高端
``0x100000..0x100000+(_edata-_start)`` 是已经不再取指的临时initialized kernel副本，
紧随其后的 ``grub_modbase`` 才是 ``struct grub_module_info32``。

固定i386-pc镜像由 ``grub-mkimage`` 写入magic ``0x676d696d``（字节为 ``gmim``）、对象
起始offset和总size。 ``grub_modules_get_end()`` 因而返回：

::

   modend = grub_modbase + module_info.size

这个end同时覆盖module-info、原始ELF模块、embedded prefix以及可能存在的config/key等对象。
具体 ``_edata``、对象总size与 ``modend`` 取决于实际构建artifact，本章只保留符号边界。

console初始化还没有输出字符
---------------------------

``grub_console_init()`` 接着把名为 ``console`` 的input/output终端结构注册到GRUB term链表。
output函数以后用INT 10h，input函数以后用INT 16h；但init本身只登记两个静态对象，不调用BIOS，
也没有分配堆内存。

因此本章此处并未显示 ``Welcome to GRUB!``。欢迎文本在 ``grub_machine_init`` 返回后才由
``grub_main`` 输出，属于第027章的入口。

保护模式C代码怎样调用E820
-------------------------

内存枚举入口是：

.. code-block:: c

   grub_machine_mmap_iterate(mmap_iterate_hook, NULL);

PC BIOS实现把临时结构固定在物理 ``0x68000``：

::

   0x68000  entry.size   # GRUB自己记录BIOS返回长度
   0x68004  entry.addr
   0x6800c  entry.len
   0x68014  entry.type

每次调用前先把这24字节结构清零；传给BIOS的缓冲区从 ``entry.addr`` 开始，所以实际
``ES:DI=6800:0004``，请求长度 ``ECX=20``，而不是把私有的 ``entry.size`` 也交给固件。
寄存器还包括：

::

   EAX = 0x0000e820
   EDX = 0x534d4150       # "SMAP"
   EBX = continuation     # first call is 0

``grub_bios_interrupt`` 先保存32位保护模式现场，经 ``prot_to_real`` 恢复real-mode IDT、0段
和实模式栈，再按PC BIOS默认flags令IF=1后执行INT 15h。返回后
``real_to_prot`` 重新装GDT、保护模式栈与limit-0 IDT，所以每一项都产生一次完整
protected→real→protected往返；主执行路径回到C时仍是IF=0。

SeaBIOS怎样交出每一项
---------------------

固定SeaBIOS的 ``handle_15e820`` 检查SMAP、continuation index和20字节buffer，随后把
``e820_list[EBX]`` 的20字节 ``addr/size/type`` 复制到 ``ES:DI``。成功返回：

::

   EAX = 0x534d4150
   ECX = 20
   CF  = 0
   EBX = next index, or 0 after the last entry

GRUB接受的长度范围是20到 ``0x400``；若CF置位、EAX不是SMAP或长度越界，就把
``entry.size`` 留为0并结束主枚举。当前q35 SeaBIOS已经建立了含非零长度项的E820 list，
所以循环沿continuation读到最后一项， ``e820_works`` 置1。

只有一项非零长度E820都没有得到时，GRUB才依次组合INT 12h、INT 15h E801h或AH=88h的旧式
结果。固定成功路径不执行这些fallback。SeaBIOS在第021章末的 ``e820_prepboot()`` 只是
dump map，没有把它freeze；本章读的是同一固件列表的BIOS接口视图。

哪些E820范围能进入候选region
----------------------------

每个非零条目交给机器初始化自己的 ``mmap_iterate_hook``，按以下顺序筛选：

#. 若范围完全位于1 MiB以下，丢弃；若跨过1 MiB，把起点裁到
   ``GRUB_MEMORY_MACHINE_UPPER_START=0x100000``；
#. 只接受 ``type == GRUB_MEMORY_AVAILABLE``；
#. 起点必须不高于 ``0xffffffff``，跨过4 GiB的尾部裁掉；
#. 把结果放入固定的 ``mem_regions[32]``；32项之后的候选被静默忽略。

所以这里建立的不是E820原样副本。IVT、BDA、低端GRUB core、 ``0x68000`` scratch、保护模式
栈、VGA/ROM区、ACPI/NVS/reserved/bad RAM以及4 GiB以上RAM都不会成为当前普通heap。
固定q35内存容量没有在项目条件中给出，本章也不写具体E820端点或总可用字节数。

compact_mem_regions做了什么
---------------------------

``compact_mem_regions()`` 先按物理起点升序排列候选，再合并相互重叠或首尾相接的区间。
这里只有经过available/type/address筛选后的range，reserved gap不会被凭空跨越。合并完成后，
每一项都是可独立注册的半开物理范围：

::

   [region.addr, region.addr + region.size)

排序和合并都在静态32项数组内完成，不依赖尚未存在的heap。

为什么初始heap必须越过modend
----------------------------

随后先调用 ``grub_modules_get_end()``。对每个候选range：

.. code-block:: c

   beg = region.addr;
   fin = region.addr + region.size;
   if (modend && beg < modend)
       beg = modend;
   if (beg < fin)
       grub_mm_init_region((void *) beg, fin - beg);

当前包含1 MiB的available range会把 ``beg`` 提升到 ``modend``，从而同时保护高端临时kernel
副本和所有原始预装对象。完全落在 ``modend`` 以下的range被跳过；从更高地址开始的独立
available range保持原起点。

这也解释了为什么不能凭“E820说available”就覆盖1 MiB解压区。E820描述平台RAM属性，不知道
GRUB刚把自己的对象放在哪里； ``modend`` 是bootloader在固件map之上增加的所有权边界。

grub_mm_init_region怎样建立正式allocator
----------------------------------------

i386的GRUB allocator以16字节cell为单位。首次注册一个range时，它：

* 把 ``struct grub_mm_region`` 对齐放在range开头；
* 紧随其后建立一个带free magic的block header；
* 让该free block的 ``next`` 指回自身，形成单向环；
* 记录前后因16字节对齐无法使用的碎片；
* 若range触及32位地址空间顶端，截掉最后的溢出保护区。

后续注册的相邻range可以与已有region从上方或下方合并；不相邻的range则进入region链表。于是
``grub_malloc/free/memalign`` 得到的是多region allocator，不是一个假定物理连续的
``heap_start/heap_end`` 数对。

在本章出口，原始module区仍未加载，因而 ``[0x100000,modend)`` 还不在heap。第027章只有在
模块代码已搬到allocator、prefix/config已复制后，才有权回收这个范围。

时间源怎样在最后安装
--------------------

``grub_machine_init`` 最后调用 ``grub_tsc_init()``。它先检查CPUID TSC位；当前固定条件
没有唯一指定CPU model，所以这里保留两条正常结果。

CPU公布TSC时，固定q35提供的i8254 PIT可用于校准：

#. 记录当前 ``RDTSC`` 为 ``tsc_boot_time``；
#. 把PIT channel 2装成 ``0xffff`` ticks，等待约55 ms；
#. 读取前后TSC差，求得每 ``2^32`` TSC ticks对应的毫秒数；
#. 把 ``grub_tsc_get_time_ms`` 安装成GRUB时间函数。

PIT没有开始计数、TSC没有前进或计算结果为0时，源码会使用代表800 MHz的hardcoded rate；
如果CPU没有TSC，PC BIOS目标改装以INT 1Ah读取约55 ms BIOS tick的RTC时间函数。两条分支都会
在返回前提供 ``grub_get_time_ms``，而具体选择取决于运行时CPUID，不能由“QEMU x86-64”代替
固定CPU model。

本章结束状态
------------

控制流已经走过：

::

   grub_main
   → grub_machine_init
   → apply or skip VIA workaround according to runtime CPU model
   → grub_modbase = 0x100000 + (_edata - _start)
   → register BIOS console input/output objects
   → iterate SeaBIOS E820 through protected/real bridge
   → retain available [1 MiB, 4 GiB) fragments, at most 32
   → sort and merge candidate regions
   → raise overlapping heap start to modend
   → grub_mm_init_region for each surviving range
   → install TSC/PIT or BIOS RTC millisecond source according to CPUID
   → return to grub_main

此刻：

* 当前执行者：BSP上的 ``grub_main()``， ``grub_machine_init()`` 刚返回；
* CPU mode：32位flat保护模式，分页关闭，A20开启，IF=0、DF=0，limit-0保护模式IDT仍有效；
* BIOS bridge：可用；每次BIOS调用后都回到当前保护模式环境；
* ``grub_modbase``：指向高端有效module-info； ``modend`` 可由其size计算；
* console：名为 ``console`` 的BIOS input/output后端已注册，但欢迎文本尚未输出；
* E820：已经通过SeaBIOS重新枚举；旧式memory-size fallback未执行；
* heap：由1 MiB以上、4 GiB以下的available范围组成，重叠高端对象的起点已抬到 ``modend``；
* ``[0x100000,modend)``：仍由临时kernel副本和原始预装对象占有，尚未回收；
* time source：毫秒函数已安装；有TSC时由q35 PIT校准（失败可用hardcoded rate），无TSC时
  使用BIOS RTC tick；
* embedded ELF模块：尚未重定位、init或注册； ``biosdisk/part_msdos/ext2`` 后端均未生效；
* ``cmdpath/root/prefix``、normal command、menu与 ``grub.cfg``：均尚未建立或打开；
* Linux：尚未读取，也没有执行。

关键边界
--------

* ``grub_modbase`` 在heap初始化前由固定地址算出，不需要也不能依赖 ``grub_malloc``。
* console init只注册静态term对象；第一次欢迎输出发生在machine init返回之后。
* E820的 ``ES:DI`` 指向 ``0x68004`` 的 ``entry.addr``，20字节固件payload不包含私有size字段。
* 低端RAM、非available类型、4 GiB以上RAM和第33个以后候选不会进入本章heap。
* E820 available是物理属性， ``modend`` 才是防止allocator覆盖GRUB自身对象的所有权边界。
* 本章不回收高端module输入区；先加载对象、后回收的顺序不能交换。
* 固定条件未唯一指定CPU model；VIA workaround和TSC/RTC选择必须保留为运行时条件分支。

下一入口
--------

下一章从machine init返回后的 ``grub_boot_time("After machine init.")`` 和
``Welcome to GRUB!`` 开始；随后进入 ``grub_verifiers_init()``、
``grub_load_config()``、core导出符号注册与embedded ELF装载。开始前heap可用，但所有原始
module对象仍只由 ``grub_modbase..modend`` 持有。

资料
----

* `GRUB固定提交：PC machine init与heap候选 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/i386/pc/init.c#L108-L272>`_；
* `GRUB固定提交：PC E820调用与fallback <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/i386/pc/mmap.c#L25-L193>`_；
* `GRUB固定提交：protected/real BIOS interrupt桥 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/i386/int.S#L19-L134>`_；
* `GRUB固定提交：console注册与BIOS终端对象 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/term/i386/pc/console.c#L250-L309>`_；
* `GRUB固定提交：module-info结构与遍历边界 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/include/grub/kernel.h#L25-L113>`_；
* `GRUB固定提交：allocator region建立与相邻合并 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/mm.c#L157-L308>`_；
* `GRUB固定提交：i386 16字节allocator cell <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/include/grub/mm_private.h#L27-L113>`_；
* `GRUB固定提交：TSC选择与fallback <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/i386/tsc.c#L28-L78>`_；
* `GRUB固定提交：PIT channel 2校准 <https://github.com/GitMirroring/grub/blob/d38d6a1a9b79427848976f53d474392cd29c2a71/grub-core/kern/i386/tsc_pit.c#L30-L84>`_；
* `SeaBIOS固定提交：INT 15h E820返回 <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/system.c#L259-L325>`_；
* `QEMU固定提交：q35通用PC设备建立PIT <https://github.com/qemu/qemu/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/pc.c#L1039-L1131>`_。
