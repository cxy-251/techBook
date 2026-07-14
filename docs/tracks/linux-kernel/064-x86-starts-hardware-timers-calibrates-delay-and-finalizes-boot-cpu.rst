第六十四章：x86 怎样启动真实定时器、校准延时并完成 boot CPU 收尾？
=======================================================================

第六十三章结束时，CPU0 已允许普通外部中断，ACPICA early subsystem 也已建立，但 x86 的最终 interrupt mode、HPET/PIT、TSC 和 scheduler clock 仍未完成。

``start_kernel()`` 接下来执行：

.. code-block:: c

   if (late_time_init)
       late_time_init();
   sched_clock_init();
   calibrate_delay();

   arch_cpu_finalize_init();

当前 x86 的 ``late_time_init`` 指向 ``x86_late_time_init()``。本章追踪到 ``arch_cpu_finalize_init()`` 返回，停在 ``pid_idr_init()`` 之前。

为什么 x86 把定时器初始化拆成 early 和 late
----------------------------------------

第六十一章中的 ``time_init()`` 只执行：

.. code-block:: c

   late_time_init = x86_late_time_init;

原因是 HPET、IOAPIC 和部分 timer 路径需要 ioremap、ACPI 与中断路由信息。若在 allocator、ACPI early 和 IRQ 入口尚未完成时直接访问这些 MMIO register，会把时间系统绑在不完整的平台状态上。

现在这些前提已经具备，``start_kernel()`` 才调用真正的 x86 late time path。

``x86_late_time_init()`` 的固定顺序
--------------------------------

源码中的顺序是：

.. code-block:: c

   x86_init.irqs.intr_mode_select();
   x86_init.timers.timer_init();
   x86_init.irqs.intr_mode_init();
   tsc_init();

普通 PC 默认函数表把它们连接为：

.. code-block:: text

   intr_mode_select → apic_intr_mode_select
   timer_init       → hpet_time_init
   intr_mode_init   → apic_intr_mode_init

平台、hypervisor 或特殊 x86 子架构可以在更早阶段替换这些函数指针。固定 QEMU q35/SeaBIOS 主线采用普通 PC 默认路径，仍必须保留 HPET 失败和传统 PIC/PIT fallback。

先选择 interrupt mode，再决定 PIT 是否需要
----------------------------------------

``apic_intr_mode_select()`` 综合前面得到的：

* MADT 与 IOAPIC 信息；
* ACPI 是否启用；
* Local APIC 能力；
* 命令行中的 ``noapic``、``nolapic`` 等限制；
* legacy PIC 是否存在；
* 平台和虚拟化 quirk。

它选择系统准备使用的中断模式。此时只是做决策和准备，最终模式接通仍在 ``apic_intr_mode_init()``。

之所以先选择，是因为 PIT 的初始化方法取决于 IRQ0 将经 PIC、virtual wire 还是 IOAPIC 投递。不能先启动 timer，再决定它的中断去哪里。

``hpet_time_init()`` 优先尝试 HPET
--------------------------------

普通 x86 timer hook 是：

.. code-block:: c

   void __init hpet_time_init(void)
   {
       if (!hpet_enable()) {
           if (!pit_timer_init())
               return;
       }
       setup_default_timer_irq();
   }

这里的语义需要按返回值理解：

.. code-block:: text

   hpet_enable() 成功
       → 使用可用 HPET 路径
       → 注册 legacy timer IRQ handler

   hpet_enable() 失败
       → 尝试 pit_timer_init()
       → PIT 自己完成所需 setup 时可直接返回
       → 否则继续注册默认 IRQ0 handler

QEMU q35 通常可以提供 HPET，但是否最终采用它还受构建配置、ACPI table、命令行和运行时检测影响。正文不能把“平台可能有 HPET”写成“必然选择 HPET”。

clocksource 和 clock-event 再次分开
---------------------------------

HPET 既可以提供连续计数器，也可以提供 comparator 中断，但两种角色由不同框架管理：

.. code-block:: text

   clocksource
       → 读取连续 counter，计算经过时间

   clock-event device
       → 编程 deadline，届时产生 IRQ

PIT 通常只适合作为低精度 clock-event/fallback。TSC 通常更适合作为高分辨率 clocksource 和 sched_clock 基础。

所以“HPET 初始化”“TSC 初始化”和“周期 tick 开始”不是同一句话。

为什么无条件准备 legacy IRQ0 handler
---------------------------------

``setup_default_timer_irq()`` 调用：

.. code-block:: c

   request_irq(0, timer_interrupt,
               IRQF_NOBALANCING | IRQF_IRQPOLL | IRQF_TIMER,
               "timer", NULL);

即使系统不使用传统 PIC/PIT，HPET timer 0 也可能以 legacy replacement mode 通过 IRQ0 投递。因此 Linux 保留统一入口：

.. code-block:: text

   IRQ0
   → timer_interrupt()
   → global_clock_event->event_handler()
   → tick layer

``timer_interrupt()`` 本身不决定 jiffies、NO_HZ 或高分辨率策略。它把硬件事件交给当前 ``global_clock_event`` 的通用 handler。

``request_irq(0)`` 与 CPU IF=1 的关系
----------------------------------

上一章之前 CPU0 已经打开 IF。当前 ``request_irq(0)`` 把 IRQ0 的 ``irq_desc`` 与 ``timer_interrupt`` action 连接，并由 irq_chip/flow handler 管理 mask、ack 和 dispatch。

只有 source 被编程、路由被接通且 IRQ unmask 后，timer event 才会实际到达。注册 handler 是必要条件，不等于调用瞬间已经发生一次 tick。

``apic_intr_mode_init()`` 接通最终路由
-----------------------------------

timer source 确认后，``apic_intr_mode_init()`` 根据前面选择的模式完成：

* Local APIC/IOAPIC 路径接通；
* legacy PIC 与 virtual wire 的必要处理；
* IRQ override 和 vector route；
* 旧模式到最终 APIC mode 的切换；
* legacy IRQ vector 的最终归属。

前面的第五十九章已经安装 CPU 可以进入的 IDT gate；这里解决的是硬件中断控制器怎样把某个 source 投递到那个 vector。

``tsc_init()`` 建立 TSC 时间基础
------------------------------

TSC（Time Stamp Counter）是 x86 CPU 的 cycle counter。``tsc_init()`` 会结合 CPUID、platform calibration、HPET/PIT/reference clock 与 hypervisor 信息，判断：

* TSC frequency；
* 是否 constant/nonstop；
* 是否可靠；
* 是否可以作为 clocksource；
* 是否适合 sched_clock；
* 多 CPU 之间是否可能不同步；
* 是否需要标记 unstable。

在虚拟机中，KVM/TCG 可能提供不同的 TSC 特性。固定主线没有限定 QEMU accelerator，因此正文只跟随内核判定，不预先声称 TSC 一定 stable。

``tsc_init()`` 不会唤醒 AP
------------------------

它处理 boot CPU 已可见的 TSC 和全局时间候选。其他 CPU 的 TSC 同步与 per-CPU clockevent 会在 AP bring-up、CPU hotplug 和后续 clocksource watchdog 路径继续检查。

当前仍只有 CPU0 online，没有 INIT/SIPI，也没有执行 ``smp_init()``。

``sched_clock_init()`` 让调度时间戳进入正式阶段
-------------------------------------------

scheduler 需要快速、单调的时间戳，用于：

* runtime accounting；
* scheduler statistics；
* trace timestamps；
* printk 时间；
* delay accounting；
* watchdog 和 latency 测量。

``sched_clock_init()`` 在架构 clock 基础已经建立后确认 sched_clock 可用并建立启动基线。它不是 scheduler tick 本身；sched_clock 可以被代码主动读取，而 tick 是 clock-event 产生的周期/one-shot interrupt。

``calibrate_delay()`` 为什么还需要 loops_per_jiffy
-----------------------------------------------

内核中某些极低层路径不能睡眠，也可能尚未有适合的 clock-event deadline，因此需要 busy loop：

.. code-block:: c

   udelay(n)
   mdelay(n)

``calibrate_delay()`` 计算或确认 ``loops_per_jiffy``，使空循环大致对应目标时间。它可能使用：

* 架构提前提供的频率；
* known CPU frequency；
* timer tick 测量；
* calibration fallback。

TSC 或平台已提供可靠频率时，可以避免长时间的传统 trial loop。最终数值仍受虚拟机调度、CPU frequency 和平台实现影响。

busy wait 不是普通任务睡眠
------------------------

``udelay()`` 在当前 CPU 上持续执行指令，不让出 CPU。它适合硬件 register 间需要几微秒等待的 atomic 路径，不适合毫秒级普通等待。

后续 scheduler 和 timer 完整可用后，普通代码应优先使用可睡眠 delay、timer 或 completion，避免浪费 CPU。

``arch_cpu_finalize_init()`` 重新识别 boot CPU
------------------------------------------

时间和延时基础完成后，x86 执行架构 CPU 收尾。固定实现首先：

.. code-block:: c

   identify_boot_cpu();
   select_idle_routine();
   cpu_smt_set_num_threads(...);
   cpu_select_mitigations();
   arch_smt_update();

早期阶段已经读取过 CPUID，但一些 feature 选择、static key、microcode 结果、mitigation 和平台事实要到通用 allocator、alternatives 和更完整 CPU 环境具备后才能最终确定。

选择 idle routine 不等于进入 idle
--------------------------------

``select_idle_routine()`` 决定未来 boot idle task 在无 runnable task 时使用 ``hlt``、poll 或平台 idle 路径。

当前 PID 0 仍在 ``start_kernel()`` 中运行，并没有进入 ``cpu_startup_entry()``。真正的 idle loop 要等 ``rest_init()`` 创建 PID 1/PID 2 并完成第一次调度后。

FPU 和 mitigation 在这里正式收尾
--------------------------------

``arch_cpu_finalize_init()`` 继续执行：

.. code-block:: text

   fpu__init_system()
   → fpu__init_cpu()
   → copy boot_cpu_data to per-CPU cpu_info
   → mark CPU0 initialized
   → alternative_instructions()

它还根据 CPU feature 和命令行选择 speculative-execution mitigations，并更新 SMT 相关策略。

``alternative_instructions()`` 根据最终 feature bits 修补内核 text，把通用指令序列换成当前 CPU 支持的更优或更安全实现。之前的 text poking 基础使运行期/启动期受控 patch 成为可能。

EFI 和 BIOS 固定主线的差异
-------------------------

若以 EFI runtime services 启动，FPU 初始化后可能执行 ``efi_enter_virtual_mode()``。固定主线是 SeaBIOS + GRUB i386-pc，不设置 EFI runtime services，因此该分支跳过。

内存加密收尾
------------

函数末尾调用 ``mem_encrypt_init()``。它为 AMD SEV、TDX 等 confidential-computing/内存加密环境处理 SWIOTLB bounce buffer 等共享/解密属性。

普通未启用内存加密的 QEMU 主线中，该入口可能基本为空。把它保留在时间线中，是因为同一 x86 内核要支持加密 guest；不能只根据固定普通路径删除架构调用。

本章结束时 timer 到了什么状态
----------------------------

现在可以确认：

.. code-block:: text

   interrupt mode 已选择并完成架构初始化
   HPET/PIT fallback 已执行选择
   legacy timer handler 已按路径登记
   TSC 基础已初始化并评估
   sched_clock 已进入正式阶段
   delay loop 已校准

仍不能在没有运行日志和固定 ``.config`` 的情况下断言：

* 最终 clocksource 一定是 TSC；
* clock-event 一定是 HPET；
* Local APIC timer 已经是最终每 CPU tick device；
* high-resolution timer mode 已经切换完成；
* NO_HZ 已经进入最终运行状态。

clocksource watchdog、AP online、Local APIC timer、clocksource selection 和 tick mode 还会继续演化。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 7.2-rc1 ``init/main.c:start_kernel()``；
* 精确位置：``arch_cpu_finalize_init()`` 已返回，``pid_idr_init()`` 尚未调用；
* CPU：只有 CPU0 online；
* current：``init_task`` / ``swapper/0`` / PID 0；
* interrupts：CPU0 IF=1；
* x86 interrupt mode：已完成 late select/init；
* timer：HPET 已被优先尝试，失败时进入 PIT fallback；最终实际选择依赖运行时检测；
* IRQ0：按所选 timer 路径建立默认 timer action；
* TSC：已初始化、校准并按能力评估；
* sched_clock：正式初始化入口已完成；
* delay calibration：``loops_per_jiffy`` 已确认；
* boot CPU：feature、idle routine、SMT、mitigation、FPU、alternatives 和 memory-encryption 收尾已完成；
* AP：尚未启动；
* PID allocator：尚未执行 ``pid_idr_init()``；
* PID 1 / PID 2：尚未创建；
* initramfs：尚未解包。

下一条控制流是：

.. code-block:: c

   pid_idr_init();

后续将进入 PID、匿名 VMA、线程栈、凭据、fork、namespace、VFS/page cache 与安全框架等“创建进程前的对象基础”。

资料
----

* `Linux 7.2-rc1 init/main.c：late time、sched clock、delay calibration 与 CPU finalize 顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c>`_
* `Linux 7.2-rc1 arch/x86/kernel/time.c：x86_late_time_init、HPET/PIT 与 IRQ0 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/time.c>`_
* `Linux 7.2-rc1 arch/x86/kernel/x86_init.c：普通 PC IRQ 与 timer function table <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/x86_init.c>`_
* `Linux 7.2-rc1 arch/x86/kernel/apic/apic.c：interrupt mode selection 与 APIC initialization <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/apic/apic.c>`_
* `Linux 7.2-rc1 arch/x86/kernel/hpet.c：HPET enable 与 clockevent/clocksource support <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/hpet.c>`_
* `Linux 7.2-rc1 arch/x86/kernel/tsc.c：TSC calibration、clocksource 与 sched_clock <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/tsc.c>`_
* `Linux 7.2-rc1 init/calibrate.c：loops_per_jiffy calibration <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/calibrate.c>`_
* `Linux 7.2-rc1 arch/x86/kernel/cpu/common.c：arch_cpu_finalize_init <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/cpu/common.c>`_