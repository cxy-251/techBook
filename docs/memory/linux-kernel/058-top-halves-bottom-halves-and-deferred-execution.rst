第058章：上半部、下半部与延迟执行
=================================

本章必须记住
------------

#. 中断处理要拆成必须立即完成的 top half 和可以稍后完成的 bottom half。
#. Top half 通常运行在 hardirq context，目标是尽快把硬件事件收敛成内核可继续处理的状态。
#. Bottom half 是 top half 安排的延迟工作，具体能力取决于它运行在 softirq、tasklet、workqueue 还是 IRQ thread 中。
#. Top half 的稳定职责是：确认中断来源、确认或屏蔽硬件、保存最小状态、安排后续处理。
#. Shared IRQ 中，handler 必须先读取设备状态；事件不属于当前设备时返回 ``IRQ_NONE``。
#. 设备状态属于当前设备时，handler 才完成 ACK、mask、clear 或其它必要硬件动作。
#. Top half 应避免长循环、复杂状态机、大量日志、阻塞等待和可能睡眠的内存分配。
#. Top half 持续时间越长，被打断的 task、其它 IRQ 和同 CPU 延迟路径等待越久。
#. 设备事件确认不完整时，电平中断可能重复触发；确认过早或状态保存不完整时，边沿事件可能丢失。
#. Top half 的输出通常是状态位、ring 指针、队列项、唤醒动作或延迟工作调度。
#. Bottom half 的输入通常是 top half 已经保存的内核对象状态，而不是临时寄存器值或用户指针。
#. 延迟执行不等于普通线程；softirq 和 tasklet 仍属于不可睡眠的中断相关上下文。
#. Workqueue 与 threaded IRQ 使用内核线程执行主体工作，通常允许睡眠、mutex 和 ``GFP_KERNEL``。
#. Softirq 适合高频、低延迟、可跨 CPU 并发的内核级批处理，例如网络和 timer 路径。
#. Tasklet 建立在 softirq 之上，为单个 tasklet 实例提供串行化执行，但仍不能睡眠。
#. Tasklet 主要用于理解存量代码；新增代码应优先比较 NAPI、workqueue 和 threaded IRQ 等机制。
#. Workqueue 适合需要睡眠、等待资源、复杂错误恢复和较长处理的异步工作。
#. Threaded IRQ 把 primary handler 与 ``thread_fn`` 绑定在同一 IRQ 注册协议中，适合设备确认后由可调度线程完成主体处理。
#. ``IRQ_WAKE_THREAD`` 表示 primary handler 已完成必要硬中断动作，并请求唤醒 IRQ thread。
#. ``IRQF_ONESHOT`` 常用于在线程处理完成前保持 IRQ line 屏蔽，避免线程尚未处理完就再次进入。
#. 网络高负载路径常用 NAPI：硬中断安排 poll，softirq 按预算批量处理数据，处理完成后再恢复中断。
#. 批处理可以减少每个事件都进入完整 IRQ 和协议栈的开销，但预算过大也会压缩用户 task 运行机会。
#. 选择机制时必须先判断：能否睡眠、允许怎样并发、延迟要求、对象生命周期和拆除协议。
#. 排队动作和执行动作可能在不同上下文，例如 IRQ 中 ``queue_work()``，实际 work function 在 kworker 中执行。
#. 延迟工作必须持有宿主对象的有效引用或由拆除顺序保证对象在回调结束前存活。
#. 设备 remove 路径应先阻止新 IRQ，再同步 handler、关闭 bottom half、取消 work/timer，最后释放对象。
#. 只删除 IRQ handler 不能自动取消已经排队的 softirq、tasklet、workqueue 或线程工作。
#. Bottom half 过重仍会造成 softirq backlog、worker 拥塞和调度延迟；移动工作只改变执行边界，不会消除工作量。

必背路径
--------

一次分层中断处理：

::

   设备产生 IRQ
   → generic IRQ 调用 top half
   → 检查中断是否属于本设备
   → 读取并确认最小硬件状态
   → 保存 ring、状态位或队列项
   → 安排 softirq、tasklet、workqueue 或 IRQ thread
   → top half 快速返回
   → bottom half 批量或复杂处理
   → 更新对象状态并恢复设备事件入口

选择延迟执行机制：

::

   判断工作是否需要睡眠
   → 需要睡眠时选 workqueue 或 threaded IRQ
   → 不需睡眠且属于高频核心路径时考虑 softirq/NAPI
   → 存量串行 bottom half 可能使用 tasklet
   → 判断是否允许多 CPU 并发
   → 判断 latency、吞吐和缓存局部性
   → 设计取消、flush 和对象释放顺序

Threaded IRQ 路径：

::

   设备产生 IRQ
   → primary handler 确认来源并保存状态
   → 必要时 mask 设备或 IRQ line
   → 返回 IRQ_WAKE_THREAD
   → generic IRQ 唤醒 irq/<n>-<name> 线程
   → thread_fn 执行可睡眠主体处理
   → 处理完成后恢复设备和 IRQ

安全拆除：

::

   对象进入 stopping 状态
   → 禁止设备产生新中断
   → disable 或 mask IRQ
   → synchronize_irq 等待 top half 和 thread
   → 停止 NAPI、tasklet、workqueue 和 timer
   → flush 或 cancel 已排队工作
   → free_irq
   → 最后释放宿主对象

必须区分
--------

Top half 与 bottom half
   Top half 负责立即确认和排队；bottom half 负责稍后完成较多工作。

延迟执行与可睡眠
   Softirq 和 tasklet 延后执行但仍不能睡眠；workqueue 和 IRQ thread 通常可以睡眠。

确认控制器与清除设备状态
   Generic IRQ 层处理控制器流控；驱动还要按设备协议清除具体 pending 原因。

排队点与执行点
   调度工作的位置决定排队上下文；回调实际运行位置决定 API 约束。

工作转移与工作减少
   移到下半部可以缩短 hardirq，却不会自动降低总 CPU 工作量。

一句话结论
----------

中断设计的核心是让 top half 只完成必须立即做的硬件动作，并把其余工作放到具备合适睡眠、并发和调度能力的下半部。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 12，Interrupts, Exceptions, Softirq, Tasklet, and Workqueue；
* AIBook 章节：Chapter 58，Top Halves, Bottom Halves, and Deferred Execution；
* 源文件：``docs/LinuxK/Part_12_Interrupts_Exceptions_Softirq_Tasklet_and_Workqueue/Chapter_058_Top_Halves_Bottom_Halves_and_Deferred_Execution.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_12_Interrupts_Exceptions_Softirq_Tasklet_and_Workqueue/Chapter_058_Top_Halves_Bottom_Halves_and_Deferred_Execution.md>`_。