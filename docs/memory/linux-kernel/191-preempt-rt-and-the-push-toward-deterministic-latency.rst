第191章：PREEMPT_RT 与确定性延迟
================================

本章必须记住
------------

#. PREEMPT_RT 的目标不是提高平均吞吐，而是缩短并约束高优先级任务的最坏等待时间。
#. 实时系统首先关注最大延迟、尾延迟和 Deadline Miss，不以平均值作为充分证明。
#. 高优先级任务被唤醒后，仍可能被 Hardirq、不可抢占区、Raw Spinlock、锁持有者和调度队列阻塞。
#. 实时调度策略只决定可调度点上的选择顺序，不能自动穿透不可抢占执行区间。
#. 一次实时延迟应拆成：事件到达、IRQ 处理、任务唤醒、Runnable 等待、锁等待、调度切换和实际执行。
#. ``sched_wakeup`` 到目标任务 ``sched_switch`` 的间隔是调度唤醒延迟的重要证据。
#. 定时器到期时间与任务真正执行时间之差包含中断、抢占、调度和锁等待成本。
#. ``CONFIG_PREEMPT_RT`` 会改变部分中断、锁和 Softirq 路径的执行语义。
#. PREEMPT_RT 尽量把设备中断主体移入可调度 IRQ Thread。
#. Threaded IRQ 的 Primary Handler 仍在 Hardirq Context 中运行，只应完成最小确认、屏蔽和唤醒动作。
#. Primary Handler 返回 ``IRQ_WAKE_THREAD`` 后，``thread_fn`` 在内核线程上下文中继续处理。
#. IRQ Thread 进入调度器后，才能通过线程优先级显式表达设备处理与业务实时线程的先后关系。
#. 并非所有中断都可以普通线程化；NMI、部分 Per-CPU、中断控制器和架构低级路径必须保留特殊语义。
#. Force-threaded IRQ 能扩大线程化覆盖，仍要检查带 ``IRQF_NO_THREAD`` 等特殊限制的路径。
#. IRQ 线程化不会消除中断工作，只是把工作从不可调度上下文移入可调度上下文。
#. PREEMPT_RT 通过减少长时间 ``preempt_disable()``、IRQ-off 和不可睡眠临界区来降低延迟尖峰。
#. 看到 ``local_irq_disable()``、``raw_spin_lock()`` 或长时间关闭抢占时，应把该区间视为实时延迟上界候选。
#. PREEMPT_RT 下普通 ``spinlock_t`` 和 ``rwlock_t`` 的实现语义会向基于 ``rt_mutex`` 的睡眠锁转换。
#. PREEMPT_RT 下普通 ``spinlock_t`` 不应机械按非 RT 的“始终自旋且关闭抢占”模型理解。
#. ``raw_spinlock_t`` 在 RT 与非 RT 内核中都保持严格自旋和原子上下文语义。
#. Raw Spinlock 临界区必须短，不能调用可能睡眠的函数。
#. ``local_lock`` 在 RT 配置下具有显式锁语义，不能只把它看成普通 Preemption Disable 包装。
#. 同一份驱动代码必须同时满足 RT 与非 RT 的 Context、Locking 和 Sleepability 合同。
#. 在普通 ``spin_lock()`` 保护区里调用底层原子 API 是否安全，必须结合目标配置和锁类型判断。
#. Priority Inversion 指高优先级任务等待低优先级任务持有的资源，而低优先级任务又被中优先级任务抢占。
#. Priority Inheritance 会临时提升锁持有者优先级，使其尽快释放高优先级任务等待的锁。
#. ``rt_mutex`` 是 Linux 实时优先级继承锁机制的核心对象。
#. PI 只处理受支持锁上的优先级反转，不解决 Raw Spinlock、IRQ-off、长不可抢占区和设备固件延迟。
#. PI 链可能跨多个锁和任务传播，应检查等待者、持有者和依赖链。
#. 锁持有时间本身仍必须受控；Priority Inheritance 不能让过长临界区变得合理。
#. 实时线程使用 ``SCHED_FIFO`` 或 ``SCHED_RR`` 时，应明确优先级、CPU Affinity 和资源依赖。
#. ``SCHED_FIFO`` 高优先级线程若不阻塞、不让出或不受预算约束，可能饿死普通任务和系统服务。
#. 实时线程优先级不应高于其必须依赖的关键 IRQ Thread，否则可能阻塞产生自身数据的设备处理。
#. IRQ Thread、控制线程、Worker 和用户服务的优先级应按真实依赖图设计。
#. CPU Affinity 可以减少迁移和共享干扰，不能消除同 CPU 上的 IRQ-off、锁和调度延迟。
#. CPU Isolation、IRQ Affinity、RCU Offload 和 Tick 配置可减少干扰，具体能力与版本、架构和启动参数有关。
#. 隔离 CPU 仍可能受到 NMI、Machine Check、Firmware、SMI 和不可屏蔽硬件事件影响。
#. SMI 等固件级延迟可能不在普通 Linux Trace 中完整可见。
#. 实时性必须在目标硬件、Firmware、BIOS、驱动和实际负载下验证。
#. ``cyclictest`` 测量周期线程被唤醒后真正运行的延迟分布，是实时基线工具之一。
#. ``cyclictest`` 的最大值必须结合运行时长、CPU、Priority、Clock、负载和采样次数解释。
#. 一次漂亮的 ``cyclictest`` 结果不能证明生产最坏情况已被覆盖。
#. 测试应叠加真实磁盘、网络、图形、内存压力、日志和设备中断负载。
#. 应同时观察 Minimum、Average、Maximum、Histogram 和异常尖峰时间点。
#. 最大延迟样本应和 ftrace、Scheduler Tracepoint、IRQ Trace 和锁证据对齐。
#. ``irqsoff`` Tracer 用于定位长时间关闭中断区间。
#. ``preemptoff`` 或相关延迟 Tracer 用于定位长时间关闭抢占区间，具体 Tracer 名称和配置按目标内核确认。
#. ``wakeup`` 与 ``wakeup_rt`` 类 Tracer 用于观察任务从唤醒到调度运行的延迟。
#. Scheduler Tracepoint 应关注 ``sched_wakeup``、``sched_waking``、``sched_switch`` 和迁移事件。
#. IRQ Trace 应区分 Hardirq Handler、Threaded Handler 和 Softirq 活动。
#. Function Graph 可以定位长函数和调用嵌套，Instrumentation 开销会改变实时路径。
#. Trace Buffer、Clock、CPU Filter 和 Event Filter 必须记录，否则不同采集结果不可比较。
#. Trace 本身可能增加延迟，生产测量应先最小化 Event 和 Buffer 范围。
#. 延迟尖峰应先定位“最早阻塞高优先级任务的区间”，不能只看最后发生调度切换的函数。
#. 高优先级任务 Runnable 但未运行，优先检查 CPU 上当前 Context、IRQ-off、抢占状态和更高优先级实体。
#. 任务处于阻塞状态时，应检查等待的锁、Completion、Futex、I/O 或设备事件。
#. IRQ 到达很晚或设备未及时产生事件时，问题可能在硬件、Firmware、总线或设备队列，而非调度器。
#. 控制线程已经运行但完成过慢，应检查 On-CPU Hot Path、Cache、NUMA 和算法成本。
#. PREEMPT_RT 可以降低内核延迟尖峰，不能替代应用 Deadline 设计、容量规划和设备实时能力。
#. RT 内核可能牺牲部分吞吐、增加 Context Switch 和改变锁竞争行为。
#. 性能比较必须同时看最坏延迟、吞吐、CPU、功耗和系统稳定性。
#. 驱动在 RT 下暴露问题，常见原因包括在错误 Context 睡眠、使用 Raw Lock 过久、错误 IRQ 优先级或未线程化工作过多。
#. 读 RT 代码时必须标记每个函数的 Context、可抢占性、可睡眠性、锁类型和最大执行时间。
#. 实时内核不是“所有代码都可抢占”；仍存在必须保持原子性的低级路径。
#. 确定性不是绝对零抖动，而是最坏延迟在目标条件下可测、可解释并满足系统预算。
#. 稳定分析顺序是：Deadline → 唤醒源 → Hardirq → Threaded IRQ → Runnable → Lock/PI → Scheduler → Task Execution。

必背路径
--------

实时任务唤醒：

::

   Timer / Device Event
   → Hardirq 最小处理
   → IRQ Thread 或 Timer Path
   → 唤醒实时 Task
   → Task 进入 Runqueue
   → 检查 IRQ-off / Preempt-off / Lock / Higher Priority Entity
   → sched_switch
   → 实时 Task 执行

延迟调查：

::

   cyclictest 发现最大延迟
   → 固定 CPU、Priority、时间点与负载
   → 对齐 sched_wakeup 与 sched_switch
   → 检查 Hardirq / Threaded IRQ / Softirq
   → 检查 raw_spinlock 与 Preempt-off 区间
   → 检查 rt_mutex 与 PI Chain
   → 定位最早不可推进点
   → 缩短临界区或调整线程与优先级
   → 相同条件复测最大值

必须区分
--------

* 平均延迟与最坏情况延迟：平均值描述总体水平；实时系统是否满足 Deadline 由最大值和长尾上界决定。
* 实时调度优先级与 CPU 当前是否可被抢占：高优先级决定调度点上的选择；Hardirq、Raw Spinlock 和 Preempt-off 区间仍会阻止立即切换。
* Threaded IRQ 主体与 Hardirq Primary Handler：Primary Handler 在硬中断上下文完成最小确认并唤醒线程；Threaded Handler 在可调度线程中执行设备主体工作。
* ``spinlock_t`` 的 RT 语义与 ``raw_spinlock_t`` 的严格原子语义：PREEMPT_RT 下普通 ``spinlock_t`` 可映射为可睡眠并支持 PI 的锁；``raw_spinlock_t`` 始终保持不可睡眠的低级自旋语义。
* Priority Inheritance 与消除所有延迟来源：PI 缩短支持锁上的优先级反转；它不能解决 IRQ-off、Raw Lock、Firmware、设备或算法执行时间。
* CPU Isolation 与完全没有硬件和固件干扰：Isolation 减少调度、Tick、IRQ 和 RCU 干扰；NMI、SMI、Machine Check 和硬件事件仍可能出现。
* 一次 Benchmark 最大值与经过足够负载和时长验证的延迟上界：单次最大值只是样本；可用上界必须在目标硬件、长期压力和真实干扰下重复验证。

一句话结论
----------

PREEMPT_RT 通过线程化中断、缩短不可抢占区间和引入优先级继承，把高优先级任务的等待路径变成可调度、可追踪并可约束的最坏延迟问题。
