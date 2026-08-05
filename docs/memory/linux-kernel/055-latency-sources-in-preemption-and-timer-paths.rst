第055章：抢占与定时器路径中的延迟来源
=====================================

本章必须记住
------------

#. 调度延迟是 task 已经 runnable 到真正运行之间的时间，timer 延迟是逻辑到期到回调实际执行之间的时间。
#. 两类延迟经常共享根因：长不可抢占区、长关中断区、重 timer 回调、softirq 拥塞和 CPU 局部压力。
#. ``need_resched`` 已经设置时，当前 CPU 仍可能因为 ``preempt_count``、锁或 IRQ 状态不能立即切换。
#. 长不可抢占区会让更高优先级 runnable task 等待当前临界区结束。
#. 不可抢占区常由 ``preempt_disable()``、spinlock、raw spinlock、硬中断和 softirq 状态形成。
#. 判断临界区是否危险，应看覆盖范围、最坏循环次数、调用频率和是否会被输入规模放大。
#. 固定极短临界区通常只是同步成本；包含大循环、回调、日志或设备访问的临界区容易形成长尾延迟。
#. 自旋锁问题不仅影响当前 CPU 抢占，还可能让其它 CPU 上等待同一锁的路径停顿。
#. 缩短不可抢占区通常通过拆分批次、缩小锁范围、预计算或把复杂工作移到线程上下文实现。
#. ``preemptoff`` tracer 可定位抢占关闭最长区间，``preemptirqsoff`` 可观察抢占与中断同时关闭的区间。
#. 关闭本地中断会推迟该 CPU 接收普通 IRQ、clockevent 和 timer 处理入口。
#. Timer 已经逻辑到期时，如果本地 IRQ 仍关闭，回调通常只能等待 IRQ 恢复后再处理。
#. ``local_irq_disable()``、``local_irq_save()``、``spin_lock_irqsave()`` 和 raw 变体是常见关中断入口。
#. 关中断和关抢占是不同限制；``spin_lock_irqsave()`` 一类路径可能同时产生二者。
#. 高精度 timer 不能消除长关中断区造成的交付延迟，精确到期表达与实际处理时机是两回事。
#. ``irqsoff`` tracer 关注本地中断关闭持续时间，可帮助解释 timer 和设备 IRQ 晚到。
#. Timer 回调运行过久会占用 timer softirq 或 hrtimer 相关时间路径，推迟后续到期项。
#. 普通 timer 回调不能睡眠，长循环和复杂状态机应移到 workqueue 或内核线程。
#. 大量日志输出会显著放大 timer、IRQ 和不可抢占路径耗时，调试日志本身可能改变现象。
#. 回调只应完成到期标记、最小状态更新、唤醒或排队工作。
#. ``timer_expire_entry`` 到 ``timer_expire_exit`` 的时间可用来测量普通 timer 回调耗时。
#. hrtimer tracepoint、function graph 和 IRQ 事件可以补齐高精度 timer 到期与执行链。
#. Timer callback overrun 不仅推迟同类 timer，也可能推迟 softirq、调度检查和被回调唤醒的 task。
#. 把工作移到 workqueue 会增加一次排队和调度延迟，但能避免阻塞 atomic 时间路径。
#. 是否延后工作取决于哪种延迟更重要：回调必须立即完成的最小部分应保留，其余部分转移。
#. CPU 正在长硬中断或 softirq 路径中执行时，用户 task 即使 runnable 也可能迟迟不能运行。
#. IRQ storm、网络 softirq backlog、timer storm 和高频短回调都可能制造局部 CPU 延迟。
#. Timer 数量多不必然有问题；关键是同一时间窗口的到期密度、回调成本和 CPU 分布。
#. Per-CPU timer 或 pinned timer 会把压力集中到特定 CPU，必须结合 CPU affinity 和 IRQ affinity 分析。
#. Timer 迁移可以分散空闲 CPU 的唤醒，但会改变回调 CPU、缓存局部性和对象锁竞争。
#. PREEMPT_RT 会改变 IRQ 线程化和部分锁语义，延迟分析必须记录内核抢占模型。
#. PREEMPT_RT 仍保留 raw spinlock 和真正不可抢占底层区间，不能假设实时内核没有关中断延迟。
#. 调度器 tick 晚到、timer 晚到和 task 晚上 CPU 可能连续发生，必须按时间线拆成独立区间。
#. ``sched_wakeup`` 到 ``sched_switch next`` 测量 task 的 wakeup-to-run 延迟。
#. Timer 计划到期到 expire entry 测量 timer 交付延迟，expire entry 到 exit 测量回调执行时间。
#. IRQ handler entry/exit、softirq entry/exit 和 function graph 能说明延迟期间 CPU 在执行什么。
#. 只看一次最大延迟容易受偶发噪声影响，应保留多次样本、CPU、调用栈和高分位分布。
#. 平均延迟良好不表示实时路径安全，最坏值和 P99/P99.9 更能暴露不可抢占区和 IRQ 抖动。
#. Trace buffer 覆盖、事件过滤和 tracer 自身开销可能造成证据不完整，采集后必须检查丢失情况。
#. 修改抢占、IRQ 或 scheduler 参数前，应先保存基线并一次只改变一个变量。
#. 优化结果必须同时观察响应延迟、吞吐、CPU 利用率、功耗和错误路径，不能只看单一最小值。
#. 最终结论应指出：事件何时应发生、何时实际进入内核、CPU 中间执行了什么、哪个边界阻止了及时处理。

必背路径
--------

拆解一次 timer 唤醒延迟：

::

   记录 timer 计划到期时间
   → 找到 clockevent / IRQ 实际进入时间
   → 计算 timer 交付延迟
   → 找到 timer_expire_entry
   → 测量回调执行时长
   → 找到回调触发的 sched_wakeup
   → 找到目标 task 作为 sched_switch next
   → 计算 wakeup-to-run 延迟
   → 分别归因 IRQ、回调或调度等待

定位长不可抢占区：

::

   捕获 preemptoff 或 preemptirqsoff 最大样本
   → 找到开始关闭抢占的位置
   → 找到重新打开的位置
   → 检查期间的锁、循环和回调
   → 判断耗时是否随负载增长
   → 缩小临界区或拆分批次
   → 重复相同负载验证长尾

定位长关中断区：

::

   捕获 irqsoff 最大样本
   → 找到 local_irq_save 或 irqsave 锁入口
   → 找到对应恢复点
   → 检查硬件访问、循环和日志
   → 对照 timer 与 IRQ 晚到时间
   → 把非必要工作移出关中断区

减轻重 timer 回调：

::

   回调读取并确认到期状态
   → 完成最小原子更新
   → queue_work 或唤醒专用线程
   → 立即返回 timer 路径
   → worker 执行可睡眠复杂处理
   → teardown 同步 timer 与 work 生命周期

必须区分
--------

不可抢占与关中断
   不可抢占阻止 task 切换；关中断还会阻止 timer 和设备 IRQ 及时进入 CPU。

Timer 精度与 timer 交付
   精度表示时间表达粒度；交付仍可能被 IRQ 和执行路径延迟。

Timer 交付延迟与回调耗时
   前者是到期到回调入口；后者是回调入口到退出。

回调唤醒与 task 实际运行
   回调使 task runnable 后，task 仍可能继续在 runqueue 中等待。

延后工作与消除延迟
   Workqueue 保护 atomic 时间路径，但复杂工作本身仍需要 CPU 和调度时间。

平均延迟与最坏延迟
   平均值反映总体水平；最坏值和高分位决定实时抖动边界。

一句话结论
----------

抢占和 timer 延迟必须按“事件交付、回调执行、任务调度”三段测量；长关中断区、长不可抢占区和重回调分别阻塞不同阶段。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 11，Context Switching, Preemption, Timers, and Timekeeping；
* AIBook 章节：Chapter 55，Latency Sources in Preemption and Timer Paths；
* 源文件：``docs/LinuxK/Part_11_Context_Switching_Preemption_Timers_and_Timekeeping/Chapter_055_Latency_Sources_in_Preemption_and_Timer_Paths.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_11_Context_Switching_Preemption_Timers_and_Timekeeping/Chapter_055_Latency_Sources_in_Preemption_and_Timer_Paths.md>`_。