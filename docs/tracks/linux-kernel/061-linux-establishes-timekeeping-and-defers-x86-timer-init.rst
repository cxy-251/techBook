第六十一章：Linux 怎样建立 timekeeping，并把 x86 定时器初始化延后？
====================================================================

第六十章结束时，tick、timer wheel、hrtimer 和 softirq 已经拥有软件管理结构，但系统还没有建立正式的 VDSO 时间数据页，也没有把 wall clock、monotonic clock 与初始 clocksource 组合成通用 timekeeper。

``start_kernel()`` 接下来执行：

.. code-block:: c

   vdso_setup_data_pages();
   timekeeping_init();
   time_init();

本章追踪到 ``time_init()`` 返回，停在 ``random_init()`` 之前。

这一段会建立“内核现在怎样表示时间”，但 x86 真正的 PIT、HPET、TSC 和最终 interrupt mode 初始化仍没有执行。

为什么 timekeeping 前先准备 VDSO 数据页
-------------------------------------

用户程序调用 ``clock_gettime()``、``gettimeofday()`` 等接口时，若每次都进入系统调用，读取时间的开销会很高。

Linux 通过 VDSO 和 VVAR 数据页把经过保护的时间参数映射到用户空间，使用户态可以：

.. code-block:: text

   read VVAR time data
   → read hardware counter when supported
   → convert cycles to nanoseconds
   → avoid entering the kernel

当前还没有用户进程和用户 ``mm``，但 timekeeping 更新路径马上就会写这些数据，因此 backing pages 必须先存在。

``vdso_setup_data_pages()`` 从 initdata 迁移到正式页
-------------------------------------------------

启动最早阶段，VDSO 数据暂时放在静态 ``vdso_initdata`` 中。

``lib/vdso/datastore.c`` 执行：

.. code-block:: c

   pages = alloc_pages(GFP_KERNEL, order);
   split_page(pages, order);
   memcpy(page_address(pages), vdso_initdata, ...);

然后把全局指针切换到新页：

.. code-block:: text

   vdso_k_time_data
   vdso_k_rng_data
   vdso_k_arch_data

具体哪些页存在由构建配置决定。

这些页以后会逐页映射到用户 VMA，所以分配出的高阶页被拆成独立 ``struct page``，每页可以分别维护引用计数。

当前只完成 backing storage
------------------------

``vdso_setup_data_pages()`` 不会：

* 建立任何用户进程；
* 立即创建 ``[vdso]`` 或 ``[vvar]`` VMA；
* 让用户代码开始读取时间；
* 选择最终 clocksource。

它只是把后续 timekeeping、VDSO getrandom 和架构数据需要的共享页从临时 initdata 搬到正式内存。

wall clock、monotonic 和 raw clock 的关系
--------------------------------------

通用 timekeeper 同时维护多种时间语义：

.. code-block:: text

   CLOCK_REALTIME
       → 日历时间，可被管理员或时间同步调整

   CLOCK_MONOTONIC
       → 从启动基准持续增长，不因修改日历时间而跳变

   CLOCK_MONOTONIC_RAW
       → 更接近底层 counter，不应用普通 NTP 频率修正

   CLOCK_BOOTTIME
       → monotonic 再加 suspend 时间

``timekeeping_init()`` 必须建立这些 clock 之间的 offset 和共同 counter 转换参数。

x86 从 CMOS/RTC 读取 persistent wall clock
----------------------------------------

通用入口先调用：

.. code-block:: c

   read_persistent_wall_and_boot_offset(
       &wall_time,
       &boot_offset);

x86 覆盖了 ``read_persistent_clock64()``，经由 ``x86_platform.get_wallclock()`` 读取平台 wall clock。标准 PC/QEMU q35 路径最终可以从 MC146818 兼容 CMOS RTC 取得日期和时间。

读取 RTC 不依赖普通设备 IRQ。CPU 可以在 IF 位关闭时通过 I/O port 同步访问 CMOS。

若平台返回无效值，通用代码会把 wall time 退回零值。若值有效，则记录 persistent clock 可用。

为什么还要计算 ``wall_to_monotonic``
------------------------------------

内核建立关系：

.. code-block:: text

   wall time + wall_to_monotonic = boot-time monotonic base

源码计算：

.. code-block:: c

   wall_to_mono = timespec64_sub(
       boot_offset,
       wall_time);

这样以后即使 ``CLOCK_REALTIME`` 被校时，monotonic 时间仍通过 offset 保持连续。

启动时的默认 clocksource 是 jiffies
----------------------------------

``timekeeping_init()`` 调用：

.. code-block:: c

   clock = clocksource_default_clock();

通用默认实现会注册并返回 ``clocksource_jiffies``。

它的特征是：

* ``read()`` 返回当前 ``jiffies``；
* rating 只有 1，是最低有效等级；
* 分辨率受 ``HZ`` 限制；
* 丢失 timer interrupt 会造成精度问题；
* 不适合作为最终 high-resolution clocksource。

这里选择 jiffies 的原因不是它最好，而是它是所有架构都能理解的安全启动基线。

当前周期 tick 尚未开始，因此 jiffies clocksource 也不会凭空前进。后续注册 TSC、HPET 等更高 rating clocksource 后，clocksource framework 可以再选择更好的来源。

``tk_setup_internals()`` 建立 cycle 到 nanosecond 转换
----------------------------------------------------

clocksource 提供：

* counter read function；
* mask；
* ``mult``；
* ``shift``；
* 可安全处理的最大 cycle delta。

``tk_setup_internals()`` 把这些参数复制并整理到 timekeeper 的 read base 中：

.. code-block:: text

   cycles delta
       × mult
       >> shift
       → nanoseconds delta

同时记录：

* 当前 ``cycle_last``；
* NTP 更新 interval；
* monotonic 与 raw 的 conversion state；
* clocksource ID；
* 最大安全 delta；
* clocksource change sequence。

这使 ``ktime_get()`` 等接口以后可以在 sequence counter 保护下读取 counter，并把增量加到 timekeeper base。

``timekeeping_init()`` 建立初始时间状态
------------------------------------

在 ``tk_core.lock`` 保护下，初始化路径依次完成：

#. 初始化 timekeeper lock 和 sequence counter；
#. 初始化可选 auxiliary timekeepers；
#. 初始化 NTP 状态；
#. 安装默认 jiffies clocksource；
#. 设置 realtime 的初始 wall time；
#. 把 raw seconds 设为零；
#. 设置 ``wall_to_monotonic``；
#. 更新正式 timekeeper、fast timekeeper 和 VDSO/VVAR 数据。

sequence counter 允许大量时间读取者无锁读取，只在恰好撞上更新时重试。

fast timekeeper 为什么单独存在
----------------------------

普通 timekeeper 读取使用 sequence counter。NMI 等特殊上下文不能安全依赖普通锁路径，因此内核维护 latch-based fast timekeeper。

启动最早阶段，fast timekeeper 使用 ``local_clock()`` 兼容的 dummy clock。安装正式初始 clocksource 后，``timekeeping_update_from_shadow()`` 会同步：

* fast monotonic base；
* fast raw base；
* VDSO time data；
* paravirtual clock data。

这让不同读取上下文共享一致的初始时间基线。

VDSO 数据为什么必须由内核持续更新
--------------------------------

用户态不能自行决定当前 clocksource，也不能在 clocksource 切换、NTP 校正或 suspend/resume 后猜测 offset。

内核会把以下数据写入 VVAR：

* sequence；
* clock mode；
* cycle_last；
* mask、mult、shift；
* realtime 与 monotonic base；
* timezone/time namespace 相关值。

用户态按 sequence 协议读取。若更新过程中 sequence 改变，就重新读取，避免把旧 base 与新 conversion 参数混用。

``time_init()`` 为什么几乎什么都不做
----------------------------------

x86 的 ``arch/x86/kernel/time.c`` 实现是：

.. code-block:: c

   void __init time_init(void)
   {
       late_time_init = x86_late_time_init;
   }

当前只保存一个函数指针，没有立即调用：

* ``hpet_time_init()``；
* ``pit_timer_init()``；
* ``setup_default_timer_irq()``；
* ``tsc_init()``；
* 最终 interrupt mode 初始化。

这是本章最重要的状态边界。

为什么 x86 timer 初始化必须延后
-----------------------------

``x86_late_time_init()`` 需要完成：

.. code-block:: text

   select interrupt mode
   → initialize HPET or PIT
   → request legacy timer IRQ when required
   → finalize interrupt mode
   → initialize TSC

其中 HPET、IOAPIC 和 ACPI 路径可能需要更完整的 ACPI/IO mapping 环境。

因此 ``start_kernel()`` 先把 callback 保存到 ``late_time_init``，随后继续初始化。更后面执行：

.. code-block:: c

   acpi_early_init();
   if (late_time_init)
       late_time_init();

这时才真正选择 q35 上的 timer 和 interrupt delivery 路径。

``hpet_time_init()`` 的回退关系
-----------------------------

默认 x86 timer callback 指向 ``hpet_time_init()``。

它尝试：

.. code-block:: text

   enable HPET
       → success: use HPET path
       → failure: try PIT
       → register legacy timer IRQ when needed

但这段当前尚未执行。不能因为 ``time_init()`` 已返回，就声称 HPET、PIT 或 IRQ0 已经开始产生 tick。

TSC 当前也没有完成正式初始化
--------------------------

TSC 在更早阶段可能已经被早期代码用于延时、sched clock 探测或 CPU 特征判断，但这里所说的 ``tsc_init()`` 尚未运行。

所以当前不能断言：

* TSC 已成为最终 clocksource；
* Local APIC timer 已成为 CPU0 clock-event device；
* high-resolution timers 已进入 active 模式；
* scheduler tick 已开始周期触发。

当前只建立了以 jiffies 为安全基线的通用 timekeeper，并登记了未来执行的 x86 late callback。

三个“时间已初始化”的不同层次
----------------------------

此时应把状态分成：

.. code-block:: text

   1. software timer structures initialized
      → timer wheel / hrtimer / softirq

   2. generic timekeeping initialized
      → wall/mono/raw bases + default jiffies clocksource

   3. architecture hardware time initialized
      → HPET/PIT/TSC/clock-event registration

本章完成第 2 层，只登记第 3 层的 callback。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 6.12.95 ``init/main.c:start_kernel()``；
* 精确位置：``time_init()`` 已返回，``random_init()`` 尚未调用；
* CPU：只有 CPU0 online；
* current：``init_task`` / ``swapper/0`` / PID 0；
* VDSO/VVAR：正式 backing pages 已分配，time data pointer 已切换；
* wall clock：已尝试从 x86 persistent clock/CMOS RTC 读取；
* timekeeper：realtime、monotonic、raw 与 offset 基础已建立；
* initial clocksource：通用 jiffies clocksource；
* x86 late callback：``late_time_init = x86_late_time_init``；
* HPET/PIT：尚未在 late callback 中初始化；
* TSC：正式 ``tsc_init()`` 尚未执行；
* CPU0 clock-event device：尚未在当前控制流中最终建立；
* scheduler tick：尚未开始；
* interrupts：IF 位仍关闭，``early_boot_irqs_disabled`` 仍为 true；
* AP、initramfs、PID 1、PID 2：均未开始。

下一条控制流是：

.. code-block:: c

   random_init();

下一批会继续完成正式随机数基础、KFENCE、stack canary、perf/profile、SMP call-function，并最终到达 ``local_irq_enable()``。到那一刻，CPU0 才真正允许普通 maskable external IRQ 异步打断 ``start_kernel()``。

资料
----

* `Linux 6.12.95 init/main.c：VDSO、timekeeping、time_init 与 random_init 顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c>`_
* `Linux 6.12.95 lib/vdso/datastore.c：VDSO/VVAR backing pages <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/lib/vdso/datastore.c>`_
* `Linux 6.12.95 kernel/time/timekeeping.c：初始 wall clock、timekeeper 与 conversion state <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/timekeeping.c>`_
* `Linux 6.12.95 kernel/time/jiffies.c：默认 jiffies clocksource <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/jiffies.c>`_
* `Linux 6.12.95 arch/x86/kernel/rtc.c：x86 persistent wall clock 与 CMOS RTC <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/rtc.c>`_
* `Linux 6.12.95 arch/x86/kernel/time.c：deferred x86_late_time_init、HPET/PIT 与 TSC <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/time.c>`_
* `Linux timekeeping 文档 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/core-api/timekeeping.rst>`_