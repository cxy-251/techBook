第六十二章：Linux 怎样完成启动期随机数并第一次打开外部中断？
================================================================

第六十一章结束时，Linux 已经建立通用 timekeeping，并把 x86 的实际定时器初始化登记到 ``late_time_init``。IRQ descriptor、x86 vector domain 和外部中断 IDT gate 都已存在，但 CPU0 的 RFLAGS.IF 仍为 0。

``start_kernel()`` 接下来执行：

.. code-block:: c

   random_init();
   kfence_init();
   boot_init_stack_canary();
   perf_event_init();
   profile_init();
   call_function_init();
   WARN(!irqs_disabled(), "Interrupts were enabled early\n");

   early_boot_irqs_disabled = false;
   local_irq_enable();

本章追踪到 ``local_irq_enable()`` 返回，停在 ``kmem_cache_init_late()`` 之前。这是启动链中一个重要状态切换：CPU0 第一次允许普通 maskable external interrupt 通过 IF 位进入已经安装好的 IDT 入口。

固定源码版本的纠正
------------------

本书从第三十四章开始实际使用的固定 Linux 源码提交一直是：

.. code-block:: text

   gregkh/linux
   7404ce51637231382873d0b55edabc2f3b841a9d

该提交的 ``Makefile`` 明确写着：

.. code-block:: text

   VERSION = 7
   PATCHLEVEL = 2
   SUBLEVEL = 0
   EXTRAVERSION = -rc1

因此本书固定 Linux 源码应标记为 ``Linux 7.2-rc1``，而不是此前状态文件误写的 ``Linux 6.12.95``。真正的 ``v6.12.95`` 指向另一棵源码，``start_kernel()`` 调用顺序也不同。后续正文以固定 commit 为唯一事实来源；旧章节中残留的版本显示字符串属于标签错误，不代表切换了源码。

``random_init()`` 为什么必须等到 timekeeping 之后
-------------------------------------------------

更早的 ``random_init_early()`` 在时间系统可用前已经混入：

* CPU 提供的硬件随机值；
* 编译期 latent entropy；
* 内核版本与系统身份信息；
* 启动命令行。

当前调用的 ``random_init()`` 已经可以读取：

.. code-block:: c

   unsigned long entropy = random_get_entropy();
   ktime_t now = ktime_get_real();

它把当前时间和架构 cycle counter 派生值混入 input pool，再加入 latent entropy。时间值本身不等于不可预测熵；它的作用是让不同启动实例的池状态进一步分化。真正可以计入多少 entropy，仍由具体来源和信任策略决定。

正式初始化不保证 CRNG 此刻一定 ready
-----------------------------------

``random_init()`` 会检查早期阶段是否已经把 CRNG 推进到 ready：

.. code-block:: text

   early CPU / bootloader seed sufficient
   → expose crng_is_ready static branch
   → reseed base CRNG

若早期来源不足，它不会伪造“已经安全”的结论。后续硬件中断时间、输入设备、块设备和硬件 RNG 仍会继续向池中加入数据。

所以这里应表述为：

.. code-block:: text

   正式 RNG 运行结构已经接通
   ≠ 每种机器都已经获得足够可信熵

函数还登记 PM notifier，使 suspend/resume 边界能够混入新的时间与计数器状态，并在条件满足时重新播种 CRNG。

为什么 KFENCE 要在 RNG 后初始化
-----------------------------

``kfence_init()`` 首先取得：

.. code-block:: c

   stack_hash_seed = get_random_u32();

KFENCE 是低开销的抽样式堆越界和 use-after-free 检测器。它把少量对象放入由 guard page 隔开的专用池，并周期性打开分配 gate。

随机 seed 用于打散 allocation stack hash 的碰撞模式，避免每次启动都出现完全相同的 hash 分布。若构建未启用 KFENCE，或 ``kfence.sample_interval=0``，该入口会退化为空操作或立即返回。

KFENCE 的 pool 和 metadata 可能已在更早的 memblock 阶段预留。当前 ``kfence_init()`` 负责验证 pool、建立 metadata/freelist、初始化 delayed work，并在配置允许时启用抽样。worker 真正运行仍依赖后面的正式 workqueue 线程环境。

boot task 获得随机 stack canary
------------------------------

``boot_init_stack_canary()`` 调用 ``get_random_canary()``，随后写入：

.. code-block:: c

   current->stack_canary = canary;
   this_cpu_write(__stack_chk_guard, canary);

当前 ``current`` 仍是 ``init_task`` / ``swapper/0``。编译器在受保护函数的栈帧中保存 canary，返回前再比较；连续栈写越过局部对象并覆盖 canary 时，内核可以在控制流返回前发现破坏。

这与第四十章写入线程栈边界的 ``STACK_END_MAGIC`` 不同：

.. code-block:: text

   STACK_END_MAGIC
       → 检查线程栈是否越过整体边界

   stack canary
       → 检查单个函数栈帧附近是否被覆盖

``perf_event_init()`` 建立性能事件核心
------------------------------------

随后 ``perf_event_init()`` 初始化 perf event 的通用核心、软件事件和每 CPU 上下文，使后续 PMU、tracepoint、software counter 与 ``perf_event_open()`` 有统一对象模型。

此时不能写成“硬件 PMU 已经开始采样”。具体 x86 PMU 驱动、NMI delivery、事件约束和用户创建的 event 还要在后续初始化与运行阶段接入。当前建立的是核心管理框架。

旧式 ``profile_init()`` 默认通常直接返回
--------------------------------------

``profile_init()`` 对应传统 ``profile=`` 启动参数。没有设置该参数时，``prof_on`` 为零，函数直接返回。

若启用，它按照内核 text 范围和 ``prof_shift`` 分配计数 buffer，之后周期 tick 可以按 instruction pointer 对 bucket 增加命中次数。这是旧式 kernel-only profiling，与现代 perf event 不是同一套接口。

``call_function_init()`` 先准备未来的跨 CPU 调用
---------------------------------------------

``call_function_init()`` 为每个 possible CPU 初始化：

.. code-block:: c

   per_cpu(call_single_queue, cpu)

并为当前 CPU0 准备 ``smp_call_function`` 所需的 per-CPU 数据。

未来其他 CPU online 后，调用者可以把 callback 放入目标 CPU 的 queue，再发送 call-function IPI。当前 AP 尚未启动，因此这里没有实际向其他 CPU 发送 IPI，也没有发生远端 callback。

打开中断前再做一次硬性检查
--------------------------

源码先执行：

.. code-block:: c

   WARN(!irqs_disabled(), "Interrupts were enabled early\n");

这不是普通提示。它验证从 ``start_kernel()`` 开头到当前为止，没有某个初始化函数错误地留下 IF=1。

前面已经分别完成：

.. code-block:: text

   irq_desc 软件状态
   → x86 vector mapping
   → IDT external gates
   → timer/hrtimer/softirq 软件结构
   → timekeeper
   → RNG / canary / perf / call-function 基础

只有这些前提成立，CPU 才能安全接收普通外部中断。

软件标志和硬件 IF 位分两步切换
-----------------------------

真正的边界是：

.. code-block:: c

   early_boot_irqs_disabled = false;
   local_irq_enable();

第一行更新内核的软件阶段标志，说明“极早期必须全局保持 IRQ off”的约束结束。

第二行在 x86 上最终执行允许中断的指令语义，把 RFLAGS.IF 置为 1。此后，未被 interrupt controller 和 irq_chip mask 的普通中断可以通过 vector 和 IDT gate 进入内核。

``local_irq_enable()`` 不会主动制造一次中断
-----------------------------------------

IF 从 0 变为 1 只表示 CPU 接受 maskable interrupt。要真正进入 handler，还需要：

* 某个硬件 source 产生事件；
* PIC、IOAPIC、Local APIC 或 MSI 路由允许投递；
* 对应 IRQ 没有保持 masked/disabled；
* vector 已映射到有效 ``irq_desc``；
* 驱动或核心代码已经登记 handler。

当前 x86 PIT/HPET/TSC 的 late 初始化尚未运行，scheduler tick 仍不应宣称已经稳定产生。打开 IF 也不会强制任务切换；CPU0 仍从 ``local_irq_enable()`` 后顺序执行 ``start_kernel()``。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 7.2-rc1 ``init/main.c:start_kernel()``；
* 固定源码：``gregkh/linux`` commit ``7404ce51637231382873d0b55edabc2f3b841a9d``；
* 精确位置：``local_irq_enable()`` 已返回，``kmem_cache_init_late()`` 尚未调用；
* CPU：只有 BSP / Linux CPU0 online；
* current：``init_task`` / ``swapper/0`` / PID 0；
* RNG：正式初始化入口已执行，是否达到 CRNG ready 取决于已获得的可信 entropy；
* stack protector：boot task 与 CPU0 canary 已设置；
* KFENCE：按构建和启动参数条件启用；
* perf/profile：通用 perf 基础已建立，传统 profile 按参数条件启用；
* SMP call function：possible CPU queues 已建立，AP 尚未 online；
* interrupts：``early_boot_irqs_disabled = false``，CPU0 IF=1；
* IRQ：descriptor、vector 和 IDT gate 已存在，具体 source/handler 仍按子系统逐步启用；
* scheduler tick：尚不能宣称已由最终 x86 clock-event 持续驱动；
* PID 1 / PID 2：尚未创建；
* initramfs：尚未解包。

下一条控制流是：

.. code-block:: c

   kmem_cache_init_late();

资料
----

* `Linux 7.2-rc1 Makefile：固定 commit 的真实版本 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Makefile>`_
* `Linux 7.2-rc1 init/main.c：RNG、canary、perf、call-function 与首次打开 IRQ <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c>`_
* `Linux 7.2-rc1 drivers/char/random.c：random_init 与 CRNG readiness <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/char/random.c>`_
* `Linux 7.2-rc1 mm/kfence/core.c：KFENCE pool、随机 seed 与 sampling gate <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/kfence/core.c>`_
* `Linux 7.2-rc1 x86 stackprotector.h：boot stack canary <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/include/asm/stackprotector.h>`_
* `Linux 7.2-rc1 kernel/events/core.c：perf event core <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/events/core.c>`_
* `Linux 7.2-rc1 kernel/profile.c：传统 profile buffer <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/profile.c>`_
* `Linux 7.2-rc1 kernel/smp.c：call_function_init 与 per-CPU queues <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/smp.c>`_