第六十一章：Linux怎样建立通用计时并延后x86硬件时间初始化？
================================================================

第六十章结束时，CPU0上的 ``start_kernel()`` 仍由 ``init_task`` 执行，处于x86-64长模式、
CPL0，IF位为0。普通定时器轮、CPU0高精度定时器基和相关软中断入口已经存在，但是它们尚未取得
硬件时钟事件；通用 ``timekeeper`` 也尚未发布。接下来的三条语句依次处理数据页、通用计时和
x86延后入口：

.. code-block:: c

   vdso_setup_data_pages();
   timekeeping_init();
   time_init();

本章跟踪到 ``time_init()`` 返回。这个边界只建立当前可读的时间表示，并没有执行
``x86_late_time_init()``。

``vdso_setup_data_pages()`` 把启动期数据移入正式页面
------------------------------------------------------

VDSO时间数据、可选随机数数据和可选架构数据最初位于按页对齐的 ``vdso_initdata``。这些静态
数据可以在普通页分配器可用前被其他初始化代码写入，但是初始化内存最终会释放，用户映射也需要
独立的页面引用，因此不能一直使用这块存储。

``vdso_setup_data_pages()`` 根据 ``VDSO_NR_PAGES`` 计算分配阶数并调用
``alloc_pages(GFP_KERNEL, order)``。分配失败会立即触发 ``panic()``，正常路径则执行
``split_page()``，使高阶分配中的每一页拥有独立引用计数。随后函数复制已有数据，并按构建配置
切换以下全局指针：

* ``CONFIG_GENERIC_GETTIMEOFDAY`` 启用时切换 ``vdso_k_time_data``；
* ``CONFIG_VDSO_GETRANDOM`` 启用时切换 ``vdso_k_rng_data``；
* ``CONFIG_ARCH_HAS_VDSO_ARCH_DATA`` 启用时切换 ``vdso_k_arch_data``。

函数返回时只是内核侧数据页已经稳定存在。PID 1尚未创建，没有用户 ``mm``，也没有
``[vvar]`` 或 ``[vdso]`` VMA；这些页面要等进程映射和缺页路径才会取得面向用户地址空间的
引用。

``timekeeping_init()`` 先建立同步边界
------------------------------------

``timekeeping_init()`` 首先通过 ``tkd_basic_setup()`` 初始化 ``tk_core.lock`` 和与该锁关联的
``tk_core.seq``，并把核心 ``timekeeper`` 标为有效。可选辅助时钟的状态由
``tk_aux_setup()`` 单独准备；未启用相应配置时该入口为空。

更新者以后持有 ``tk_core.lock`` 修改影子副本，读取者则通过序列计数器判断一次读取是否跨越了
更新。当前只有CPU0执行并且IF位仍为0，但初始化代码仍在这里建立后续多CPU和中断上下文必须
遵守的同步协议。

墙上时间和启动偏移来自不同入口
------------------------------

``read_persistent_wall_and_boot_offset()`` 先调用 ``read_persistent_clock64()`` 填写
``wall_time``，再用 ``local_clock()`` 的当前值估计 ``boot_offset``。x86的
``read_persistent_clock64()`` 继续调用 ``x86_platform.get_wallclock``：

* 普通PC默认函数指针指向 ``mach_get_cmos_time()``，它同步读取MC146818兼容RTC；
* 平台或虚拟化初始化可以替换该函数指针；
* 当前没有普通设备中断也不妨碍同步读取持久时钟。

固定平台包含QEMU ``q35``，但加速器、CPU特性和最终内核配置没有固定，因此正文不能把默认RTC入口
写成所有运行条件下唯一可能的函数。

``timekeeping_init()`` 只把有效且大于零的 ``wall_time`` 记为存在持久时钟。无效的非零值会
发出警告并清零；如果墙上时间反而小于 ``boot_offset``，函数也会把启动偏移清零。随后计算：

.. code-block:: c

   wall_to_mono = timespec64_sub(boot_offset, wall_time);

于是初始关系满足“墙上时间加 ``wall_to_mono`` 等于启动后的估计经过时间”。日历时间以后可以
校正，而单调时间通过偏移保持自己的基线。

当前默认时钟源是 ``clocksource_jiffies``
------------------------------------------

``clocksource_default_clock()`` 是弱定义；x86没有提供覆盖实现，所以本次调用会在尚未登记时先
登记 ``clocksource_jiffies``，再返回它。该时钟源的 ``read`` 方法读取 ``jiffies``，评级为1，
掩码为32位，换算参数由 ``TICK_NSEC`` 和 ``JIFFIES_SHIFT`` 给出。

这个选择提供了所有x86构建都可使用的启动基线，不代表它会成为最终时钟源。第六十章没有建立
硬件时钟事件，第六十一章也尚未运行x86的TSC或HPET初始化，所以周期性 ``jiffies`` 增长仍未
开始；后续登记更高评级的时钟源后，时钟源框架还可以切换。

``tk_setup_internals()`` 固定周期换算参数
----------------------------------------

``tk_setup_internals()`` 把当前时钟源同时装入单调读取基和原始读取基，读取一次周期值作为
``cycle_last``，再记录掩码、乘数和位移。它依据NTP更新间隔反算固定的周期区间，并建立
``cycle_interval``、 ``xtime_interval``、 ``raw_interval`` 和误差换算字段。

当前时钟源的 ``mult`` 同时写入单调与原始读取基，后续NTP调整只会改变计时器保存的换算状态，
不会擅自改写时钟源对象。 ``cs_was_changed_seq`` 在这里递增，使以后切换时钟源的读取者能够
识别变化。

影子状态在锁和序列计数器保护下发布
----------------------------------

取得 ``tk_core.lock`` 后，初始化路径依次执行 ``ntp_init()``、安装时钟源内部参数、写入初始
墙上时间、把 ``raw_sec`` 置为0，并保存 ``wall_to_mono``。最后
``timekeeping_update_from_shadow()`` 开始一次序列计数器写区间：

#. 更新各类 ``ktime`` 基值和墙上时间偏移；
#. 更新VDSO时间数据、半虚拟化时间数据以及快速单调和快速原始读取副本；
#. 把影子 ``timekeeper`` 复制到公开副本；
#. 结束序列计数器写区间。

因此普通读取路径、NMI可用的快速读取路径和VDSO数据不会观察到由新旧字段拼成的状态。
``guard(raw_spinlock_irqsave)`` 在当前IF位为0的条件下保存并恢复同一中断状态，本函数不会提前
打开普通中断。

``time_init()`` 只登记x86延后函数
--------------------------------

x86实现的 ``time_init()`` 只有一项状态变化：

.. code-block:: c

   late_time_init = x86_late_time_init;

它没有在此调用HPET、PIT或TSC初始化，也没有选择最终中断模式。上述工作依赖更后的ACPI和中断
路由状态，将在第六十四章通过 ``late_time_init`` 执行。CPU0的硬件时钟事件设备、周期时钟滴答
和高精度模式仍不能视为已经建立。

本章结束状态
------------

``time_init()`` 返回后，VDSO相关静态数据已经复制到可逐页计数的正式页面，核心
``timekeeper`` 已在 ``tk_core.lock`` 和 ``tk_core.seq`` 保护下发布。墙上时间已按平台函数
指针尝试读取，单调基线由 ``boot_offset`` 与 ``wall_time`` 的差建立，当前时钟源是
``clocksource_jiffies``。 ``late_time_init`` 已指向 ``x86_late_time_init``，但该函数尚未
执行。CPU0仍在CPL0执行 ``init_task``，IF位仍为0，普通工作线程、应用处理器、PID 1与PID 2
仍不存在。

关键边界
--------

* 正式VDSO数据页已经分配，不等于任何用户地址空间已经建立VDSO或VVAR映射。
* ``wall_time`` 来自x86平台墙上时钟入口， ``boot_offset`` 的通用默认值来自
  ``local_clock()``；二者不是同一硬件读数。
* x86使用通用的 ``clocksource_jiffies`` 启动基线；当前尚无周期硬件事件推动
  ``jiffies`` 增长。
* ``timekeeping_update_from_shadow()`` 同步发布计时器、VDSO和快速读取状态，不会选择新的
  硬件时钟源。
* ``time_init()`` 只保存函数指针；HPET、PIT、TSC、最终中断模式和CPU0硬件时钟事件均未在
  本章初始化。

下一入口
--------

``start_kernel()`` 的下一条语句是：

.. code-block:: c

   random_init();

第六十二章将从通用计时可读后的随机数初始化开始，并跟踪到CPU0第一次允许普通可屏蔽中断。

资料
----

* `Linux 7.2-rc1 init/main.c：VDSO数据页、通用计时和x86时间入口顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L1080-L1091>`_
* `Linux 7.2-rc1 lib/vdso/datastore.c：正式数据页分配与全局指针切换 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/lib/vdso/datastore.c#L32-L63>`_
* `Linux 7.2-rc1 kernel/time/timekeeping.c：持久时钟校验与核心计时器初始化 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/timekeeping.c#L1981-L2080>`_
* `Linux 7.2-rc1 kernel/time/timekeeping.c：时钟源周期换算参数 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/timekeeping.c#L329-L421>`_
* `Linux 7.2-rc1 kernel/time/timekeeping.c：影子状态、VDSO和快速读取状态的同步发布 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/timekeeping.c#L789-L837>`_
* `Linux 7.2-rc1 kernel/time/jiffies.c：启动默认时钟源 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/jiffies.c#L32-L72>`_
* `Linux 7.2-rc1 arch/x86/kernel/rtc.c：x86持久时钟入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/rtc.c#L56-L111>`_
* `Linux 7.2-rc1 arch/x86/kernel/x86_init.c：普通PC的默认墙上时钟函数 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/x86_init.c#L149-L160>`_
* `Linux 7.2-rc1 arch/x86/kernel/time.c：延后的x86硬件时间初始化 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/time.c#L67-L96>`_
