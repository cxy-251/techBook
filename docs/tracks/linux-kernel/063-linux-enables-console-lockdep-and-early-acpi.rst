第六十三章：Linux 怎样启用正式 console、锁依赖检查并完成 early ACPI？
====================================================================

第六十二章结束时，CPU0 已执行 ``local_irq_enable()``，普通 maskable external interrupt 第一次可以进入内核。当前仍只有 PID 0 沿 ``start_kernel()`` 执行，打开 IF 位不会自动创建进程或切换任务。

接下来的控制流是：

.. code-block:: c

   kmem_cache_init_late();
   console_init();
   lockdep_init();
   locking_selftest();

   /* validate initrd placement */
   setup_per_cpu_pageset();
   numa_policy_init();
   acpi_early_init();

本章追踪到 ``acpi_early_init()`` 返回，停在 ``late_time_init()`` 之前。

``kmem_cache_init_late()`` 收尾 slab 启动阶段
------------------------------------------

第五十五章已经让 slab allocator 可以提供普通对象。这里的 ``kmem_cache_init_late()`` 不是重新创建一套 allocator，而是把只能在中断、调度和更完整内存环境可用后完成的晚期工作接上。

具体行为取决于构建选择的 SLAB/SLUB 实现，通常包括：

* 完成 allocator 的晚期调试和随机化状态；
* 让前期 bootstrap cache 转入正式运行方式；
* 准备后续 sysfs/debugfs、memory hotplug 和 per-CPU fast path 所需关系；
* 释放或转换只为启动阶段服务的临时状态。

当前调用返回后，不能据此断言 ``/sys/kernel/slab`` 已经出现。sysfs 本身和 slab 的 sysfs initcall 仍在后面。

为什么打开 IRQ 后才正式初始化 console
------------------------------------

``start_kernel()`` 的源码把 ``console_init()`` 放在 ``local_irq_enable()`` 之后，并明确说明这个位置很早：PCI 等设备初始化尚未完成，但内核希望在后续复杂初始化出错时能够输出日志。

``console_init()`` 运行链接到 console initcall 区间的初始化函数。它根据构建配置、平台和命令行，把可用 console backend 接到 printk console 层。

固定命令行包含：

.. code-block:: text

   console=ttyS0

这表达用户希望使用第一个串口 console。最终能否在这一刻由 8250/串口 backend 接管，仍取决于固定内核配置和平台 console 支持。本书没有固定 ``.config``，因此不能把某个具体 serial driver 的所有寄存器初始化写成必然路径。

正式 console 与 early console 不同
--------------------------------

早期 banner 和之前的日志可能通过 earlycon、boot console 或固件提供的最小路径输出。正式 console 初始化后：

.. code-block:: text

   printk ring buffer
   → registered console
   → console write callback
   → serial/VGA/other backend

boot console 可以在正式 console 接管后被注销。这里建立的是内核日志输出终端，不代表：

* 用户态已经打开 ``/dev/console``；
* tty device model 已全部枚举；
* getty 或 shell 已运行；
* PCI 显卡、DRM 或完整串口驱动均已 probe。

``panic_later`` 为什么在 console 后检查
------------------------------------

命令行解析阶段若参数或环境变量数量超出上限，内核先记录 ``panic_later``，没有立刻 panic。

把检查放到 ``console_init()`` 后，可以尽量确保用户看到明确错误：

.. code-block:: c

   if (panic_later)
       panic("Too many boot %s vars ...");

固定命令行很短，不会触发该分支。

``lockdep_init()`` 建立锁依赖图基础
--------------------------------

lockdep 不是普通互斥锁实现。它是内核的动态锁依赖验证器，用于记录：

* lock class；
* 获取顺序；
* hardirq/softirq 安全属性；
* 递归、反向顺序和潜在环路；
* held-lock stack。

例如运行路径曾观察到：

.. code-block:: text

   lock A → lock B

另一条路径又出现：

.. code-block:: text

   lock B → lock A

即使当前没有真正死锁，lockdep 也可以从依赖图发现潜在环路。

没有启用 ``CONFIG_LOCKDEP`` 时，相关入口可能为空或大幅退化。正文只能说执行了统一初始化入口。

为什么 ``locking_selftest()`` 必须在 IF=1 后运行
---------------------------------------------

源码注释明确要求中断已打开，因为 selftest 要验证：

* hardirq on/off；
* softirq on/off；
* irq-safe 与 irq-unsafe lock class；
* 不同上下文中的反向锁顺序。

测试会主动构造预期的锁依赖场景，检查 lockdep 是否能正确识别。它不是对所有驱动和未来锁使用的证明，只是验证 lockdep 核心机制与当前构建组合能够工作。

initramfs 在这里仍未解包
-----------------------

``CONFIG_BLK_DEV_INITRD`` 路径会再次检查：

.. code-block:: c

   initrd PFN < min_low_pfn

若 initrd 被放在内核不能安全访问的低端区域，内核打印 critical 日志并把 ``initrd_start`` 清零，避免把已经被覆盖或不安全的内存当作归档读取。

正常固定路径中，GRUB 已按 boot protocol 把 initramfs 放在允许的高地址，前面的 ``setup_arch()`` 也已保留该范围，因此检查通过。

这一步只验证地址，没有：

* 解压 cpio；
* 创建 ``/init``；
* 挂载 rootfs；
* 启动 PID 1。

``setup_per_cpu_pageset()`` 启用 buddy 的 CPU 本地缓存
---------------------------------------------------

buddy allocator 可以从 zone 的全局 free area 分配页，但每次都获取 zone 锁会产生高开销。per-CPU pageset 为 order-0 和部分小批量页提供 CPU 本地缓存：

.. code-block:: text

   local allocation/free
   → per-CPU page list
   → refill/drain in batches
   → zone buddy lists

``setup_per_cpu_pageset()`` 为 zone 分配正式的 per-CPU pageset 与 zonestat backing，并设置 batch/high/low 等阈值。

此刻只有 CPU0 online，其他 possible CPU 的结构仍需提前存在，便于后续 AP online 时直接进入 allocator hotplug 路径。

per-CPU pageset 不会改变物理页归属
--------------------------------

页面仍属于原来的 NUMA node 和 zone。pageset 只是缓存少量空闲页，减少全局锁竞争。必要时可以 drain 回 buddy，例如：

* 内存回收；
* CPU offline；
* memory hotplug；
* 大块连续内存分配；
* allocator 参数更新。

``numa_policy_init()`` 建立内存策略基础
------------------------------------

NUMA policy 决定任务或 VMA 在多个 node 之间如何选择内存，例如 default、preferred、bind、interleave 和 weighted interleave。

``numa_policy_init()`` 初始化 mempolicy 使用的对象 cache、共享策略和全局基础。当前 ``init_task`` 尚未进入用户态，也没有普通用户 VMA，所以这里只是准备策略对象，不会立即把现有内核页迁移到其他 node。

单 node 配置中，很多策略最终退化为本地/default 行为；统一入口仍然存在。

``acpi_early_init()`` 与前面的 ACPI 解析不是重复
--------------------------------------------

``setup_arch()`` 期间 Linux 已经读取过 RSDP、FADT、MADT、SRAT、HPET 等早期表，以便建立 CPU、NUMA、APIC 和内存布局。

当前 ``acpi_early_init()`` 进入 ACPICA 核心层，执行：

.. code-block:: text

   apply DMI/DSDT quirks
   → reallocate ACPI root table
   → acpi_initialize_subsystem()
   → populate ACPICA table/namespace foundations
   → finalize SCI routing information needed by x86

它让 ACPI tables 可以通过 ACPICA 统一访问，并为后续 interpreter、namespace object 和设备扫描建立基础。

此时仍不能任意执行 AML
----------------------

源码注释明确说明：``acpi_early_init()`` 返回后表可以访问，但 event handling 和 ACPI global lock 尚未初始化，因此此处不应执行普通 AML method。

完整的 ACPI 启用分成多个阶段：

.. code-block:: text

   setup_arch early table parsing
   → acpi_early_init()
   → late_time_init uses ACPI/APIC facts
   → acpi_subsystem_init()
   → later ACPI bus/interpreter/device scan initcalls

所以这里没有创建完整 ACPI device tree，也没有把所有 ``_HID`` 设备绑定到驱动。

为什么 late timer 初始化要等到 ACPI early 之后
--------------------------------------------

x86 需要根据 ACPI/IOAPIC/SCI 和 HPET 信息决定：

* 使用 PIC 还是 APIC interrupt mode；
* PIT 是否仍需作为 fallback；
* HPET 是否存在且可用；
* legacy IRQ0 如何路由；
* timer interrupt 应通过哪套控制器投递。

因此顺序是：

.. code-block:: text

   acpi_early_init()
   → late_time_init()
   → interrupt mode select
   → HPET/PIT setup
   → final interrupt mode
   → TSC init

打开 CPU IF 位早于这一阶段，并不代表最终周期 tick 已经配置完成。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 7.2-rc1 ``init/main.c:start_kernel()``；
* 精确位置：``acpi_early_init()`` 已返回，``late_time_init()`` 尚未调用；
* CPU：只有 CPU0 online；
* current：``init_task`` / ``swapper/0`` / PID 0；
* interrupts：CPU0 IF=1，普通 maskable IRQ 已允许进入；
* slab：晚期启动收尾入口已完成，slab sysfs 仍待后续 initcall；
* console：正式 console initcalls 已执行，具体 backend 由构建与平台决定；
* lockdep：按配置初始化并完成启动 selftest；
* initramfs：地址通过安全检查，归档仍未解包；
* buddy：正式 per-CPU pageset 与 zonestat 基础已建立；
* NUMA policy：策略对象基础已建立；
* ACPI：ACPICA early subsystem 和 table/namespace 基础已建立，普通 AML event/device scan 尚未开始；
* x86 hardware timer：尚未执行 ``late_time_init()``；
* AP、PID 1、PID 2：尚未创建。

下一条控制流是：

.. code-block:: c

   if (late_time_init)
       late_time_init();

当前固定 x86 路径中，函数指针指向 ``x86_late_time_init()``。

资料
----

* `Linux 7.2-rc1 init/main.c：IRQ enable 后的 slab、console、lockdep、pageset 与 ACPI 顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c>`_
* `Linux 7.2-rc1 mm/slub.c：SLUB 启动与晚期状态 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/slub.c>`_
* `Linux 7.2-rc1 kernel/printk/printk.c：console registration 与 printk console 层 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/printk/printk.c>`_
* `Linux 7.2-rc1 kernel/locking/lockdep.c：lock dependency graph <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/locking/lockdep.c>`_
* `Linux 7.2-rc1 lib/locking-selftest.c：hardirq/softirq locking selftests <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/lib/locking-selftest.c>`_
* `Linux 7.2-rc1 mm/page_alloc.c：per-CPU pageset 与 buddy fast path <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/page_alloc.c>`_
* `Linux 7.2-rc1 mm/mempolicy.c：NUMA policy 初始化 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/mempolicy.c>`_
* `Linux 7.2-rc1 drivers/acpi/bus.c：acpi_early_init 与后续 ACPI 阶段 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/acpi/bus.c>`_