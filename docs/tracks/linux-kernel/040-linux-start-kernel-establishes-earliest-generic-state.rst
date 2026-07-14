第四十章：Linux 怎样进入 start_kernel 并建立最早的通用内核状态？
================================================================

第三十九章结束时，``x86_64_start_kernel()`` 已经清理早期 identity mapping、清零 BSS、复制 ``boot_params`` 和命令行、加载 BSP microcode，并调用：

.. code-block:: c

   x86_64_start_reservations(real_mode_data);

这是 x86 专用启动代码进入通用 ``start_kernel()`` 前的最后一层。

为什么还保留 ``real_mode_data`` 参数
------------------------------------

``x86_64_start_kernel()`` 已经执行过 ``copy_bootdata()``，正常情况下全局 ``boot_params.hdr.version`` 必定非零。

``x86_64_start_reservations()`` 仍保留一道防护：

.. code-block:: c

   if (!boot_params.hdr.version)
       copy_bootdata(__va(real_mode_data));

这使其他特殊入口若绕过前一层清理，也能在进入通用内核前补齐启动参数。当前固定 GRUB 主线不会再次复制，因为 ``boot_params`` 已经有效。

建立最早的平台兼容假设
----------------------

函数随后调用：

.. code-block:: c

   x86_early_init_platform_quirks();

这里的 ``quirks`` 不是扫描具体 PCI 设备，而是先定义“这类 x86 平台默认具有什么传统组件”。初始值包括：

.. code-block:: text

   i8042 keyboard controller  expected present
   RTC                        present
   warm reset                 supported
   PnP BIOS                   permitted

随后根据 ``boot_params.hdr.hardware_subarch`` 调整。

当前固定平台是 QEMU q35，经 SeaBIOS 和 GRUB 走普通 PC boot protocol，所以属于 ``X86_SUBARCH_PC``。该分支开启：

.. code-block:: c

   x86_platform.legacy.reserve_bios_regions = 1;

这告诉后续内存初始化：传统 BIOS 相关低端区域需要识别和保留，不能因为已经进入 64 位内核就把整段低内存当作普通 RAM。

Xen、Intel MID、CE4100 等路径会关闭部分 RTC、PnP BIOS 或 i8042 假设，但当前主线不进入这些分支。

``hardware_subarch`` 的第二次分流
-------------------------------

紧接着又有一个 switch：

.. code-block:: c

   switch (boot_params.hdr.hardware_subarch) {
   case X86_SUBARCH_INTEL_MID:
       x86_intel_mid_early_setup();
       break;
   default:
       break;
   }

普通 PC/q35 进入 ``default``，不执行 Intel MID 的专用无传统 PC 固件初始化。

到这里，x86 专用入口已经完成。控制流正式进入：

.. code-block:: c

   start_kernel();

``start_kernel()`` 是什么边界
-----------------------------

``start_kernel()`` 位于 ``init/main.c``，是所有体系结构最终汇合的通用内核启动函数。

之前的代码一直在回答：

* x86 CPU 怎样进入 long mode；
* 页表怎样让内核高半区可执行；
* bootloader 参数怎样保存；
* x86 GDT、IDT、GSBASE 和微码怎样准备。

从现在开始，主线逐渐转向：

* 通用内存管理；
* 调度器；
* 中断与时间；
* VFS；
* initcall；
* 用户空间 init。

不过 ``start_kernel()`` 的第一批调用仍然极早，很多常见内核设施尚不可用。

给 ``init_task`` 栈底写入哨兵
----------------------------

第一条调用是：

.. code-block:: c

   set_task_stack_end_magic(&init_task);

内核在线程栈边界写入固定 magic。后续检查若发现该值被覆盖，可以判断栈已经越过合法边界。

当前只有静态创建的 ``init_task`` 在执行。普通进程栈分配器和调度器尚未初始化，因此必须先给这一个最早任务建立基本的栈溢出检测标记。

再次建立通用层看到的 processor ID
---------------------------------

接下来：

.. code-block:: c

   smp_setup_processor_id();

第三十八章已经在 x86 汇编里选择 CPU 0，并建立 per-CPU offset。这里是通用启动代码给予体系结构的 processor-ID 初始化钩子，使 ``smp_processor_id()`` 等通用接口从一开始就有一致语义。

不同架构可以在这里从硬件 ID、固件 ID 或启动寄存器建立逻辑 CPU 编号。当前 x86 主线的 BSP 仍是逻辑 CPU 0，没有唤醒任何 AP。

最早期 debug objects
--------------------

随后调用：

.. code-block:: c

   debug_objects_early_init();

debug objects 用来追踪 timer、work、RCU head 等内核对象的生命周期，发现“未初始化就使用”“已经释放又激活”等错误。

此刻 slab allocator 尚不可用，所以 early init 只能使用静态对象池和最小哈希结构。它建立的是调试框架的生存基础，不代表所有对象类型已经注册。

记录当前内核映像的 build ID
--------------------------

.. code-block:: c

   init_vmlinux_build_id();

构建系统可以把 GNU build ID 放入 ELF note。内核在极早阶段保存它，后续崩溃转储、模块匹配、调试工具和日志可以精确识别正在运行的是哪一个 ``vmlinux`` 构建产物。

版本号 ``6.12.95`` 只能描述源码发布版本；build ID 进一步区分不同配置、编译器和本地修改生成的二进制。

为什么 cgroup 在调度器前就出现
-----------------------------

接下来：

.. code-block:: c

   cgroup_init_early();

这一步不会挂载 cgroupfs，也不会创建完整控制器层级。它先把 ``init_task`` 接到初始 cgroup 结构，并建立后续调度、CPU accounting 等代码能够依赖的最小关系。

许多内核子系统初始化时会读取当前任务的 cgroup 信息，所以根任务不能等到用户空间或 VFS 完成后才拥有归属。

重新强制关闭本地中断
--------------------

虽然从 GRUB 交接开始中断一直关闭，``start_kernel()`` 仍明确执行：

.. code-block:: c

   local_irq_disable();
   early_boot_irqs_disabled = true;

原因是 ``start_kernel()`` 是通用边界，不能仅靠“前面应该已经关闭”这种隐含约定。

``early_boot_irqs_disabled`` 是软件状态标记。后续代码若过早打开中断，内核可以检测并报告。此时 IDT、IRQ descriptor、local APIC、timer 和调度器都没有完成，任何普通硬件中断都不能安全处理。

把 boot CPU 加入四类 CPU mask
---------------------------

``boot_cpu_init()`` 将当前 CPU 登记为：

.. code-block:: text

   possible
   present
   online
   active

这些词含义不同：

* ``possible``：内核数据结构允许该逻辑 CPU 存在；
* ``present``：固件/硬件表明该 CPU 实际存在；
* ``online``：该 CPU 已经运行内核代码；
* ``active``：调度与迁移逻辑可以把它作为活动 CPU 使用。

对 CPU 0，四个条件此时都成立。其他 AP 可能是 possible/present，却尚未 online/active；它们要等后面的 SMP bring-up。

``page_address_init()`` 的兼容位置
---------------------------------

随后：

.. code-block:: c

   page_address_init();

该接口主要为无法永久映射全部物理页的 HIGHMEM 架构建立 ``struct page`` 到临时虚拟地址的关联表。

在当前 x86-64 主线中，物理内存最终通过 64 位 direct map 访问，不采用传统 32 位 HIGHMEM page-address 哈希机制，因此该调用通常退化为空实现。

它仍保留在通用顺序中，因为 ``start_kernel()`` 同时服务不同体系结构和配置。

第一条正式内核 banner
---------------------

接下来：

.. code-block:: c

   pr_notice("%s", linux_banner);

``linux_banner`` 包含版本、编译用户/主机、编译器和构建时间等信息。

这通常是用户串口或控制台上看到的第一条正式内核 banner。前面的 SeaBIOS、GRUB 和 compressed ``Decompressing Linux`` 输出都不属于正式通用内核日志系统。

需要注意：此时完整 console、ring buffer 扩容和 printk kthread 尚未初始化。早期 printk 仍依赖架构和 early console 提供的最小输出路径。

停在 ``setup_arch()`` 入口
-------------------------

下一条调用是：

.. code-block:: c

   setup_arch(&command_line);

这是一个非常自然的章节边界。

``start_kernel()`` 是通用函数，但它必须先让具体架构把：

* firmware/E820 内存图；
* 内核、initramfs 与 boot data 保留区；
* direct map 和最终早期页表；
* CPU feature；
* ACPI、NUMA、PCI 早期资源；
* 命令行；

转换成通用内核可以继续使用的状态。

因此 ``setup_arch()`` 不是一个小辅助函数，而是 x86 从“能执行正式内核 C 代码”走向“通用内存管理能够启动”的大型交接阶段。下一批会从这里逐层展开，不能一句“架构初始化完成”跳过。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 6.12.95 ``start_kernel()``；
* 当前停点：即将调用 ``setup_arch(&command_line)``；
* CPU：BSP / Linux CPU 0；
* CPU 0 masks：possible、present、online、active；
* current task：``init_task``；
* init task 栈哨兵：已写入；
* interrupts：关闭；
* ``early_boot_irqs_disabled``：true；
* early debug objects：已建立静态基础；
* vmlinux build ID：已记录；
* init_task 初始 cgroup 关系：已建立；
* linux banner：已提交到早期日志；
* architecture memory setup：尚未执行；
* initramfs：尚未展开；
* scheduler：尚未初始化；
* VFS：尚未初始化；
* initcall：尚未执行；
* 用户空间 ``init``：尚未创建。

下一段从 ``arch/x86/kernel/setup.c:setup_arch()`` 开始，首先接管命令行、``boot_params``、E820 和早期保留区，再逐步建立 memblock 与 x86 内存布局。

资料
----

* `Linux 6.12.95 head64.c：x86_64_start_reservations 到 start_kernel <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/head64.c>`_
* `Linux 6.12.95 platform-quirks.c：普通 PC、Xen、Intel MID 的 legacy feature 初值 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/platform-quirks.c>`_
* `Linux 6.12.95 init/main.c：start_kernel 最早调用顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c>`_
* `Linux 6.12.95 kernel/cpu.c：boot CPU mask 初始化 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/cpu.c>`_
* `Linux 6.12.95 mm/highmem.c：page_address_init 条件实现 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/highmem.c>`_
* `Linux 6.12.95 debugobjects.c：early debug objects 静态池 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/lib/debugobjects.c>`_