第六十二章：Linux怎样完成启动随机数初始化并首次允许普通中断？
================================================================

第六十一章结束时，CPU0上的 ``start_kernel()`` 已经发布通用 ``timekeeper``，但
``x86_late_time_init()`` 尚未执行，IF位仍为0。此后源码先完成依赖计时状态的初始化，再越过
启动期保持普通中断关闭的边界：

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

本章跟踪到 ``local_irq_enable()`` 执行。上述统一入口有多项构建与运行分支，不能把一次顺序
调用写成所有子系统均已启用。

``random_init()`` 混入计时器能够提供的新输入
-------------------------------------------

早先的 ``random_init_early()`` 已经混入硬件随机值、潜在熵、系统身份和命令行。现在通用计时
已经可读， ``random_init()`` 取得 ``ktime_get_real()`` 的墙上时间和
``random_get_entropy()`` 的架构计数值，把二者混入输入池，再调用 ``add_latent_entropy()``。

这些值使不同启动实例的池状态更难相同，但“混入数据”和“确认可计入多少可信熵”是两件事。
时间戳本身不会使尚未达到安全阈值的随机数生成器自动越过阈值。

随机数可用状态取决于较早阶段累计结果
------------------------------------

如果较早阶段已经使 ``crng_init`` 达到 ``CRNG_READY``，而 ``crng_is_ready`` 静态分支尚未
公布， ``random_init()`` 才调用 ``crng_set_ready()``。随后只有
``crng_ready()`` 为真时才调用 ``crng_reseed()``；否则仍等待后续输入。

函数还登记 ``pm_notifier``，使电源状态变化能够进入随机数维护路径。登记失败会触发警告；如果
``random_get_entropy()`` 得到零，函数也只警告缺少周期计数器和备用计时来源，不会把缺失输入
伪装成可信熵。因此本章能够确认正式入口已经执行，不能确认所有构建与运行条件下随机数生成器都
已经达到同一状态。

``kfence_init()`` 只在配置和运行条件允许时启用抽样
---------------------------------------------------

未启用 ``CONFIG_KFENCE`` 时， ``kfence_init()`` 是空函数。启用时，它先用
``get_random_u32()`` 设置 ``stack_hash_seed``，再检查 ``kfence_sample_interval``：

* 间隔为0时立即结束；
* 启动期预留池无法转成KFENCE对象与保护页时，记录错误并结束；
* 正常路径初始化可延后的或普通的 ``kfence_timer``，登记可选通知器，把
  ``kfence_enabled`` 置为真，并向 ``system_dfl_wq`` 排入第一次分配门工作。

第六十章前的 ``workqueue_init_early()`` 已允许创建和排队工作，但是普通工作线程仍未启动。
因此队列状态已经变化，不代表 ``toggle_allocation_gate()`` 已由工作线程执行，也不代表当前
已经产生KFENCE抽样对象。

启动任务的栈保护值受构建配置控制
--------------------------------

启用 ``CONFIG_STACKPROTECTOR`` 时， ``boot_init_stack_canary()`` 调用
``get_random_canary()``，把结果同时写入当前 ``init_task.stack_canary`` 和CPU0逐CPU变量
``__stack_chk_guard``。64位构建会把最低字节清零，保留其余随机位并阻断没有终止符的字符串
越界继续伪装成普通字符串。

未启用栈保护时，该入口为空。即使启用，这个值保护的是编译器插入检查的函数栈帧，与线程栈
边界处的 ``STACK_END_MAGIC`` 不是同一对象，也不会为尚未创建的PID 1或应用处理器空闲任务设置
保护值。

``perf_event_init()`` 建立可选性能事件核心
------------------------------------------

未启用 ``CONFIG_PERF_EVENTS`` 时， ``perf_event_init()`` 是空函数。启用时，正常路径执行的
主要状态变化包括：

#. 初始化性能监控单元标识分配器和延后栈回溯工作；
#. 为所有可能CPU初始化软件事件散列表、调度回调链和 ``perf_cpu_context``；
#. 初始化保护性能监控单元列表的SRCU对象；
#. 登记软件事件、CPU时钟、任务时钟和追踪点性能监控单元；
#. 使当前CPU0的性能事件上下文上线；
#. 登记重启通知器并尝试初始化硬件断点；
#. 以 ``SLAB_PANIC`` 创建 ``perf_event_cache``。

硬件断点初始化失败只产生警告。这个入口没有创建用户性能事件，没有为某个任务编程采样周期，
也不能证明x86通用硬件性能监控单元已经开始产生中断。

传统性能分析可以完全不分配缓冲区
--------------------------------

``profile_init()`` 与性能事件核心相互独立。未启用 ``CONFIG_PROFILING`` 时它直接返回0；启用
以后，如果命令行没有使 ``prof_on`` 非零，同样不会分配缓冲区。

只有选择了 ``profile=`` 模式时，函数才按内核正文范围和 ``prof_shift`` 计算
``prof_len``，依次尝试 ``kzalloc()``、 ``alloc_pages_exact()`` 和 ``vzalloc()``。三种方式
都失败时返回 ``-ENOMEM``，而 ``start_kernel()`` 没有检查该返回值。固定GRUB命令行没有
``profile=``，但内建命令行与启动配置未固定，所以正文保留启用、禁用和分配失败三种状态。

``call_function_init()`` 区分队列头和CPU0发送端资源
--------------------------------------------------

``call_function_init()`` 先遍历 ``cpu_possible_mask``，初始化每个
``call_single_queue`` 的无锁链表头。它随后只对当前CPU0调用 ``smpcfd_prepare_cpu()``，尝试
申请两个CPU掩码和逐CPU的 ``call_single_data_t`` 存储。

``smpcfd_prepare_cpu()`` 可以因三次分配中的任意一次失败而返回 ``-ENOMEM``，但
``call_function_init()`` 不传播这个结果。其他可能CPU的发送端资源要在各自启动阶段准备。
当前应用处理器没有执行，队列为空，也没有发送跨CPU函数调用中断。

打开中断前的检查不负责补救
--------------------------

``WARN(!irqs_disabled(), ...)`` 验证从前一已验证边界到此处没有函数错误地留下IF位为1。与更早
会主动调用 ``local_irq_disable()`` 的检查不同，这一处只记录警告，不改变硬件状态。正常连续
路径仍保持IF位为0。

随后， ``early_boot_irqs_disabled`` 先从真变为假，表示内核不再处于要求整个启动前缀保持
普通中断关闭的阶段。这个软件变量不会修改处理器标志，真正的架构边界由紧接着的
``local_irq_enable()`` 建立。

``local_irq_enable()`` 允许中断而不制造中断
-------------------------------------------

启用中断标志追踪时， ``local_irq_enable()`` 先调用 ``trace_hardirqs_on()``；x86原生入口随后
执行 ``sti``，把RFLAGS.IF置为1。可选半虚拟化入口可以替换底层实现，但必须保持本地普通中断
已经允许的架构语义。

此后某个可屏蔽中断能否实际进入CPU0，还取决于中断源、控制器路由、IRQ屏蔽状态和处理动作。
第五十九章已经建立FRED或IDT入口以及向量账本，但最终x86中断模式和硬件时钟事件要等
``x86_late_time_init()``。 ``local_irq_enable()`` 本身不会产生时钟中断，不会把软中断待处理
位置位，也不会触发任务切换；如果已有符合条件的中断待处理，它可以在架构允许的时点异步进入。

本章结束状态
------------

``local_irq_enable()`` 执行后， ``random_init()`` 已混入通用计时与架构计数输入，并按较早
熵状态决定是否公布和重新播种随机数生成器。KFENCE、栈保护、性能事件和传统性能分析已经分别
走过各自配置与失败分支；所有可能CPU的跨CPU函数调用队列头已经初始化，CPU0发送端资源只保证
已经尝试申请。 ``early_boot_irqs_disabled`` 为假，CPU0的IF位为1。当前执行者仍是CPL0中的
``init_task``，没有应用处理器、任务切换、PID 1、PID 2或初始内存盘解包。

关键边界
--------

* ``random_init()`` 已执行，不等于所有运行条件下 ``crng_ready()`` 都为真。
* KFENCE排入延迟工作不等于普通工作线程已经运行；配置关闭、采样间隔为0和池初始化失败都会
  阻止启用。
* 栈保护和性能事件均可在构建时关闭；传统性能分析还受 ``profile=`` 与缓冲区分配结果控制。
* 所有可能CPU只统一取得 ``call_single_queue`` 队列头；本章仅为CPU0尝试申请发送端数据。
* ``early_boot_irqs_disabled`` 是软件阶段标志， ``local_irq_enable()`` 才改变CPU接收普通
  可屏蔽中断的状态。
* IF位置1不代表硬件时钟事件、最终中断模式或任何具体设备处理动作已经建立。

下一入口
--------

``start_kernel()`` 的下一条语句是：

.. code-block:: c

   kmem_cache_init_late();

第六十三章将从SLUB晚期清理工作队列开始，继续经过控制台、可选锁自检、逐CPU页面集、NUMA
策略和早期ACPI。

资料
----

* `Linux 7.2-rc1 init/main.c：随机数初始化到首次允许普通中断的顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L1090-L1105>`_
* `Linux 7.2-rc1 drivers/char/random.c：计时输入、可用状态与重新播种 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/char/random.c#L890-L918>`_
* `Linux 7.2-rc1 mm/kfence/core.c：KFENCE条件启用与延迟工作 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/kfence/core.c#L966-L1005>`_
* `Linux 7.2-rc1 include/linux/kfence.h：未启用KFENCE时的空入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/kfence.h#L225-L232>`_
* `Linux 7.2-rc1 arch/x86/include/asm/stackprotector.h：CPU0与启动任务的栈保护值 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/include/asm/stackprotector.h#L36-L54>`_
* `Linux 7.2-rc1 include/linux/stackprotector.h：64位保护值掩码和关闭配置时的空入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/stackprotector.h#L9-L34>`_
* `Linux 7.2-rc1 kernel/events/core.c：性能事件核心和CPU0上下文 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/events/core.c#L15102-L15133>`_
* `Linux 7.2-rc1 kernel/events/core.c：性能监控单元、硬件断点和对象缓存 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/events/core.c#L15308-L15337>`_
* `Linux 7.2-rc1 include/linux/perf_event.h：关闭性能事件配置时的空入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/perf_event.h#L1975-L2011>`_
* `Linux 7.2-rc1 kernel/profile.c：传统性能分析缓冲区及失败路径 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/profile.c#L50-L115>`_
* `Linux 7.2-rc1 include/linux/profile.h：传统性能分析的构建分支 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/profile.h#L18-L64>`_
* `Linux 7.2-rc1 kernel/smp.c：CPU0资源准备和所有可能CPU的队列头 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/smp.c#L54-L112>`_
* `Linux 7.2-rc1 x86 irqflags.h：STI对应的原生入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/include/asm/irqflags.h#L35-L43>`_
