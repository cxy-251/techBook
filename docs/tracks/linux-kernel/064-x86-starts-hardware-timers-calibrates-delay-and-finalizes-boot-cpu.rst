第六十四章：x86怎样完成延后时间初始化与启动CPU收尾？
========================================================

第六十三章结束时，CPU0仍以 ``init_task`` 的身份执行 ``start_kernel()``，RFLAGS.IF已经为1。
通用 ``timekeeper`` 已经发布， ``late_time_init`` 也已指向 ``x86_late_time_init()``，但
最终中断模式、硬件时钟事件、TSC晚期状态、调度时钟起点和延时循环尚未收尾。本章从条件调用
``late_time_init`` 开始，沿固定源码执行到 ``arch_cpu_finalize_init()`` 返回，并停在
``pid_idr_init()`` 之前。

延后入口怎样恢复x86时间初始化
-----------------------------

``start_kernel()`` 先检查函数指针：

.. code-block:: c

   if (late_time_init)
       late_time_init();

固定x86路径已经在第061章的 ``time_init()`` 中写入该指针，因此正常继续启动时会进入
``x86_late_time_init()``。条件判断仍有边界意义：通用启动代码不假定每种体系结构都提供该
入口；这里能够确定调用发生，是因为当前体系结构前面已经完成赋值。

``x86_late_time_init()`` 依次执行：

.. code-block:: c

   x86_init.irqs.intr_mode_select();
   x86_init.timers.timer_init();
   x86_init.irqs.intr_mode_init();
   tsc_init();

   if (static_cpu_has(X86_FEATURE_WAITPKG))
       use_tpause_delay();

标准PC函数表最初把三个函数指针分别设为 ``apic_intr_mode_select()``、
``hpet_time_init()`` 和 ``apic_intr_mode_init()``。平台或虚拟化初始化可以在更早阶段替换
这些指针；固定平台没有限定QEMU加速器、CPU模型、内核配置和完整启动参数，因此本章以实际
函数指针为执行者，并用标准PC实现解释没有被替换时的路径。

中断模式选择先决定PIT是否有必要
------------------------------

标准 ``apic_intr_mode_select()`` 根据APIC是否被启动参数关闭、启动CPU是否具有本地APIC、
ACPI MADT或MP表是否提供处理器配置，以及SMP是否被限制，选择 ``APIC_PIC``、
``APIC_VIRTUAL_WIRE_NO_CONFIG``、 ``APIC_VIRTUAL_WIRE``、
``APIC_SYMMETRIC_IO_NO_ROUTING`` 或 ``APIC_SYMMETRIC_IO``。该函数只把结果写入
``apic_intr_mode``，尚未完成最终控制器设置。

这个选择必须早于硬件定时器。 ``pit_timer_init()`` 内部的 ``use_pit()`` 会在启动CPU没有
TSC时要求使用PIT；存在TSC时，则让 ``apic_needs_pit()`` 依据刚选出的中断模式判断是否仍需
PIT。顺序表达的是一个真实依赖：先确定中断投递方式，才能知道传统IRQ0时钟是否还承担启动
职责。

HPET结果不能压缩为成功或失败
----------------------------

标准定时器入口 ``hpet_time_init()`` 的控制流是：

.. code-block:: c

   if (!hpet_enable()) {
       if (!pit_timer_init())
           return;
   }
   setup_default_timer_irq();

``hpet_enable()`` 只有在HPET能力、映射、寄存器、周期、通道和计数器检查均通过后，才会登记
``clocksource_hpet``。如果硬件还支持旧式替代路由，它会把第0通道登记为旧式时钟事件并返回
1；没有旧式替代路由时，即使时钟源已经登记，它仍返回0。因此这里至少存在三类结果：

* HPET可用且提供旧式时钟事件： ``global_clock_event`` 指向HPET旧式事件，随后尝试登记
  IRQ0处理动作；
* HPET不可用，或只可作为时钟源，而 ``use_pit()`` 要求PIT： ``pit_timer_init()`` 初始化
  ``i8253_clockevent``，把它写入 ``global_clock_event``，随后尝试登记IRQ0处理动作；
* ``hpet_enable()`` 返回0且 ``use_pit()`` 判定不需要PIT：内核停用可能空耗虚拟机时间的PIT，
  ``hpet_time_init()`` 直接结束，不在此登记IRQ0。

固定QEMU q35能够提供HPET硬件模型，但是否启用HPET、是否具有可用旧式路由、APIC是否需要PIT，
仍受配置、命令行、CPU能力和运行检测结果控制。正文因而不能把第一类结果写成固定结论，也
不能把返回0一律解释为HPET完全不可用。

IRQ0登记失败只记录信息
----------------------

需要旧式时钟事件时， ``setup_default_timer_irq()`` 调用 ``request_irq(0, ...)``，把
``timer_interrupt()`` 作为IRQ0动作。该处理函数只取出 ``global_clock_event``，再执行其
``event_handler``；时钟滴答、单次事件或高分辨率策略由时钟事件层继续决定，不在这个薄入口
中实现。

``request_irq()`` 失败时，调用者只打印 ``Failed to register legacy timer interrupt``，
没有停止启动，也没有把错误返回给 ``start_kernel()``。因此正常越过本入口只能证明“已经按
需要尝试登记”，不能无条件证明IRQ0动作存在，更不能证明第一次硬件事件已经到达。CPU0此时
允许普通外部中断，但事件源还必须被编程、路由和解除屏蔽，才可能进入处理函数。

最终中断模式怎样接通
--------------------

定时器选择之后，标准 ``apic_intr_mode_init()`` 读取先前保存的 ``apic_intr_mode``。
``APIC_PIC`` 分支保持8259模式并直接结束；其余四种模式先确定是否按单处理器方式设置，再执行
``x86_64_probe_apic()``、可选的 ``x86_platform.apic_post_init()`` 和
``apic_bsp_setup()``。这里才把启动CPU的APIC投递方式推进到所选模式。

前面章节已经建立CPU能够进入的FRED或IDT入口；当前代码解决的是硬件控制器怎样投递中断。两者
不能合并为“安装向量后时钟就已经运行”。本章也没有启动应用处理器，所有设置仍由CPU0在
``start_kernel()`` 上下文中完成。

TSC晚期初始化保留运行分支
-------------------------

``tsc_init()`` 首先检查 ``X86_FEATURE_TSC``。没有TSC时，它清除
``X86_FEATURE_TSC_DEADLINE_TIMER`` 后结束。存在TSC但早期没有得到 ``tsc_khz`` 时，它再次
尝试确定频率；再次失败会把TSC标记为不稳定、清除TSC截止时间定时器能力并结束。

获得频率后，函数初始化其他可能CPU的周期到纳秒换算数据，按配置启用调度器中断时间统计，把
``get_loops_per_jiffy()`` 保存到 ``lpj_fine``，再检查系统级TSC可靠性。检测到不同步时，
TSC会被标记为不稳定；否则内核按可靠性决定是否停用时钟源看门狗，并登记早期TSC时钟源和检测
ART。固定平台没有限定CPU模型和加速器，所以本章不预判TSC一定可靠，也不把登记TSC时钟源写成
无条件结果。

如果启动CPU具有 ``X86_FEATURE_WAITPKG``，随后的 ``use_tpause_delay()`` 会把延时实现改为
基于 ``TPAUSE`` 的路径。该能力不存在时，函数不执行。这个选择只改变忙等待实现，不会在此
创建调度任务或时钟事件。

调度时钟切换时短暂关闭中断
--------------------------

返回 ``start_kernel()`` 后，CPU0执行 ``sched_clock_init()``。x86使用可处理不稳定调度时钟
的实现：它先以 ``local_irq_disable()`` 暂时清除IF，根据当前CPU的
``sched_clock_data`` 计算 ``__gtod_offset``，再以 ``local_irq_enable()`` 恢复IF，最后增加
``sched_clock_running`` 静态分支计数。

该偏移使调度时钟从启动期读数切到正式运行状态时保持连续。它不是周期时钟滴答，也不会触发
调度。由于第062章已经确认进入本函数前IF为1，函数正常返回后IF仍为1；中间的关闭区间只保护
本次基准转换。

延时校准按既有证据逐级选择
--------------------------

``calibrate_delay()`` 为当前CPU0确定 ``loops_per_jiffy``，选择次序不是单一的测量循环：

#. 复用当前CPU已有的 ``cpu_loops_per_jiffy``；
#. 采用启动参数给出的 ``preset_lpj``；
#. 首次打印时采用TSC或定时器此前写入的 ``lpj_fine``；
#. 采用体系结构能够复用的已知值；
#. 使用定时器专用直接校准；
#. 前面都不能给出结果时执行收敛校准。

得到数值后，函数同时写入CPU0的逐CPU字段和全局 ``loops_per_jiffy``，只在首次校准时打印
BogoMIPS，并执行弱定义的 ``calibration_delay_done()``。这个数值服务于不能睡眠的短时忙
等待；它不表示用户可见时间精度，也不等同于CPU频率。

启动CPU收尾怎样改变可用能力
--------------------------

最后， ``arch_cpu_finalize_init()`` 再次执行 ``identify_boot_cpu()``，据最终特性选择空闲
例程，并把每个核心的最大线程数交给通用SMT代码。它随后选择推测执行缓解措施，执行
``arch_smt_update()``，再初始化系统和CPU0的FPU状态。仅32位构建会执行i486下限检查和
``utsname`` 机器名调整；当前x86-64路径不进入该分支。

FPU初始化之后，只有EFI运行时服务已启用时才进入EFI虚拟地址模式。固定启动链采用SeaBIOS和
GRUB ``i386-pc``，不提供EFI运行时服务，因此这条条件路径不会成为当前状态。

函数接着把最终 ``boot_cpu_data`` 复制到CPU0的逐CPU ``cpu_info``，设置
``initialized=true``，再执行 ``alternative_instructions()``。后者依据最终CPU特性修补内核
指令替代点；其完成不代表应用处理器也已初始化。

在x86-64分支中，函数把 ``USER_PTR_MAX`` 设为 ``TASK_SIZE_MAX`` 并发布运行常量；如果没有
使用直接映射的一吉字节大页，还会把物理地址起始处所在的前2 MiB区域改用4 KiB页映射，以避开
固定MTRR与大页重叠问题。最后 ``mem_encrypt_init()`` 按内存加密环境处理SWIOTLB缓冲区。
这些分支依赖最终CPU特性、页表选择和内存加密状态，但调用顺序是固定的。

本章结束状态
------------

::

   当前执行者          = CPU0上的start_kernel()；arch_cpu_finalize_init()已返回
   下一入口            = pid_idr_init()
   CPU模式             = x86-64长模式，CPL0
   IF                  = 1；sched_clock_init()内部曾短暂关闭后重新打开
   当前任务            = init_task / swapper/0 / PID 0
   CPU在线且活动       = 仅CPU0
   应用处理器          = 尚未启动
   中断模式            = 按运行检测选择并完成启动CPU设置
   HPET/PIT            = 按能力、配置和中断模式选择；可能不在此登记IRQ0
   IRQ0动作            = 需要时已经尝试登记；失败只记录信息
   TSC                 = 按能力和校准结果登记、标记不稳定或停用相关能力
   调度时钟            = 启动基准已经切换，sched_clock_running已推进
   延时循环            = CPU0与全局loops_per_jiffy已经写入
   启动CPU信息         = 最终boot_cpu_data已复制到CPU0并标记initialized
   指令替代            = alternative_instructions()已经执行
   空闲例程            = 已选择但尚未进入
   普通工作线程        = 尚未启动
   任务切换            = 尚未发生
   PID1/PID2           = 尚未创建

关键边界
--------

* ``hpet_enable()`` 返回0不必然表示HPET时钟源未登记；旧式时钟事件能力和连续计数时钟源是两
  个不同结果；
* ``setup_default_timer_irq()`` 只在HPET旧式事件或PIT需要IRQ0时执行，登记失败不会阻止启动；
* ``tsc_init()`` 的调用固定，但TSC频率、同步性、可靠性和时钟源登记结果由运行检测决定；
* ``sched_clock_init()`` 建立调度时间基准，不等于时钟滴答已经产生；
* ``arch_cpu_finalize_init()`` 只完成启动CPU收尾，没有创建新任务、启动应用处理器或进入空闲
  循环。

下一入口
--------

``start_kernel()`` 下一条语句是 ``pid_idr_init()``。第065章将继续建立初始PID名字空间的
分配器与对象缓存，然后依次处理匿名映射、线程栈、凭据、任务对象和进程共享对象；直到这些
基础完成之前，PID 1仍不会被创建。

资料
----

* `start_kernel()中的第064—066章调用边界
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L1138-L1164>`_
* `x86_late_time_init()、HPET/PIT选择与IRQ0登记
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/time.c#L34-L96>`_
* `标准PC的中断与定时器函数表
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/x86_init.c#L62-L105>`_
* `APIC模式选择和启动CPU最终设置
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/apic/apic.c#L1250-L1393>`_
* `PIT是否启用及其返回语义
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/i8253.c#L17-L56>`_
* `HPET检查、时钟源登记和旧式时钟事件结果
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/hpet.c#L988-L1102>`_
* `TSC晚期初始化的频率、同步和时钟源分支
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/tsc.c#L1518-L1561>`_
* `调度时钟基准切换
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/clock.c#L201-L223>`_
* `延时循环数值的选择和发布
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/calibrate.c#L278-L318>`_
* `arch_cpu_finalize_init()的完整收尾顺序
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/cpu/common.c#L2576-L2666>`_
