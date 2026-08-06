第058章：上半部、下半部与延迟执行
=================================

核心知识点
----------

中断处理必须分层
   立即完成的工作放在 top half，能够稍后完成的工作放到 bottom half。分层目标是缩短 hardirq 占用时间，同时保证硬件状态不会丢失或反复触发。

Top half 负责收敛硬件事件
   它通常运行在 hardirq context，必须确认事件来源、读取最小状态、执行必要的 ACK、mask 或 clear，并把后续处理所需信息保存到内核对象中。

共享 IRQ 必须先判断来源
   Handler 只有确认事件属于本设备后才能处理状态；不属于当前设备时应返回 ``IRQ_NONE``，避免误清除其它设备的共享事件。

Top half 必须保持短小
   长循环、复杂状态机、大量日志、阻塞等待和可能睡眠的分配都会延长 hardirq 时间，推迟被打断 task、其它 IRQ 和同 CPU 延迟路径。

Bottom half 是执行能力的选择
   延迟处理可以运行在 softirq、tasklet、NAPI、workqueue 或 IRQ thread 中。它们都能推迟工作，但睡眠能力、并发模型和调度方式不同。

Softirq 与 tasklet 仍不可睡眠
   二者属于中断相关的 atomic context。Tasklet 只保证同一实例通常不并发执行，不能因此忽略其它 IRQ、CPU 或拆除路径对宿主对象的访问。

Workqueue 提供线程上下文
   Work function 由 kworker 执行，通常可以使用 mutex、等待条件和 ``GFP_KERNEL``。它适合复杂状态机、错误恢复和可能阻塞的设备操作。

Threaded IRQ 绑定 IRQ 生命周期
   Primary handler 在 hardirq 中确认来源并返回 ``IRQ_WAKE_THREAD``，``thread_fn`` 随后在线程上下文完成主体处理。``IRQF_ONESHOT`` 可在处理完成前维持屏蔽语义。

NAPI 用预算批量处理事件
   网络路径常由硬中断安排 poll，再在 softirq 中按 budget 批量处理。它能降低每包中断成本，但过大预算会增加 softirq 占用和用户 task 延迟。

排队上下文与执行上下文不同
   IRQ 中调用 ``queue_work()`` 只说明工作在 hardirq 中被提交；真正 work function 运行在 kworker 中，API 约束应以执行点为准。

延迟工作必须持有对象生命期
   Top half 保存的状态、队列项和宿主对象必须在 bottom half 完成前保持有效。Remove 路径要先阻止新 IRQ，再同步所有已排队和正在运行的后续工作。

工作转移不会消除工作量
   把复杂处理移出 hardirq 能改善响应边界，却不会减少总 CPU 成本。Bottom half 过重仍可能造成 softirq backlog、worker 拥塞和调度延迟。

关键路径
--------

一次分层中断处理：

::

   设备产生 IRQ
   → generic IRQ 调用 top half
   → 检查事件是否属于本设备
   → 读取并确认最小硬件状态
   → 保存 ring、状态位或队列项
   → 安排 softirq、NAPI、workqueue 或 IRQ thread
   → top half 快速返回
   → bottom half 完成批量或复杂处理
   → 更新对象状态并恢复设备事件入口

选择延迟执行机制：

::

   判断工作是否需要睡眠
   → 需要睡眠时选择 workqueue 或 threaded IRQ
   → 不需睡眠且属于高频核心路径时选择 softirq 或 NAPI
   → 存量串行 bottom half 可能使用 tasklet
   → 判断允许的并发与 CPU 局部性
   → 评估延迟、吞吐和生命周期
   → 设计 cancel、flush 与拆除顺序

Threaded IRQ 路径：

::

   设备产生 IRQ
   → primary handler 确认来源并保存状态
   → 必要时屏蔽设备或 IRQ line
   → 返回 IRQ_WAKE_THREAD
   → generic IRQ 唤醒 IRQ thread
   → thread_fn 在可调度上下文处理主体工作
   → 完成后恢复设备和 IRQ

安全拆除：

::

   对象进入 stopping 状态
   → 禁止设备产生新中断
   → disable 或 mask IRQ
   → 等待 top half 与 IRQ thread 退出
   → 停止 NAPI、tasklet、workqueue 和 timer
   → cancel 或 flush 已排队工作
   → free_irq
   → 最后释放宿主对象

概念辨析
--------

Top half 与 bottom half
   Top half 负责必须立即完成的硬件动作；bottom half 负责可以延后的批量或复杂处理。

延迟执行与可睡眠
   Softirq 和 tasklet 虽然延后执行，仍不能睡眠；workqueue 和 IRQ thread 通常可以睡眠。

控制器确认与设备清除
   Generic IRQ 层处理控制器流控；驱动仍需按设备协议清除具体 pending 原因。

排队点与执行点
   工作在哪里被提交决定排队上下文；回调在哪里运行决定真正的 API 能力。

工作转移与工作减少
   转移工作缩短 hardirq 临界时间，不会自动降低总处理成本。

本章结论
--------

中断分层的本质是让 top half 只完成无法推迟的硬件动作，再把其余工作放到具备合适睡眠、并发和调度能力的 bottom half 中。