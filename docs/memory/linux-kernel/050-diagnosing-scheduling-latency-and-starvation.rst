第050章：诊断调度延迟与饥饿
===========================

核心知识点
----------

首先区分执行慢与等待 CPU
   task 已经获得 CPU 但执行很慢，属于执行路径问题；task 已经 runnable 却迟迟没有被调度，才属于调度延迟或饥饿问题。

调度延迟有明确时间边界
   一次关键样本从 task 变为 runnable 开始，到它作为 next task 被切入 CPU 结束。这个 wakeup-to-run 区间才是直接的调度等待时间。

睡眠不属于 runqueue 等待
   task 等待 I/O、futex、锁或设备事件时处于 sleeping 状态，没有参与 CPU 竞争。必须先证明 task 持续 runnable，才能讨论调度饥饿。

load average 不能直接代表 CPU 压力
   load average 同时包含 runnable task 和不可中断睡眠 task。高 load 可能来自 CPU 队列拥塞，也可能来自大量 ``D`` 状态等待。

schedstat 可以分离运行与等待
   在接口可用且格式已确认时，``/proc/<pid>/schedstat`` 可提供实际运行时间和 runqueue 等待时间。等待增量远大于运行增量，是 task 正在等 CPU 的强证据。

调度事件可以重建时间线
   ``sched_wakeup`` 表示 task 进入 runnable 路径，``sched_migrate_task`` 表示位置变化，``sched_switch`` 表示真正切入或切出 CPU。三类事件组合后可还原等待位置和执行区间。

饥饿通常来自竞争或约束
   常见原因包括更高调度类长期占用、普通任务竞争、过窄 affinity、cpuset 限制、cgroup quota 节流、局部 runqueue 热点和 IRQ/softirq 干扰。

优先级反转必须证明资源链
   只有同时找到高优先级等待者、低优先级资源持有者和可能持续抢占持有者的中间任务，才能确认优先级反转，而不是普通 CPU 竞争。

关键路径
--------

判断 task 是否在等 CPU：

::

   确认目标 TID
   → 读取 task 当前状态
   → 区分 runnable 与 sleeping
   → 同窗口采样 CPU utilization、procs_running 和 schedstat
   → 比较运行时间增量与 runqueue 等待增量
   → 等待显著增长时进入调度事件分析

建立 wakeup-to-run 时间线：

::

   捕获目标 task 的 sched_wakeup
   → 记录唤醒时间与目标 CPU
   → 跟踪可能发生的 sched_migrate_task
   → 找到 task 首次作为 sched_switch 的 next
   → 计算 wakeup 到 sched-in 延迟
   → 找到它作为 prev 被切出的时刻
   → 计算本次运行区间
   → 对多次样本统计分布与长尾

定位调度饥饿原因：

::

   证明 task 持续 runnable
   → 检查同 CPU 运行者的 policy 与 priority
   → 检查 RT、deadline、IRQ 和 softirq 干扰
   → 检查 affinity、cpuset 与调度域
   → 检查 cgroup quota、weight 与 throttling
   → 检查迁移事件和局部 rq 压力
   → 判断是竞争、策略压制还是位置限制

定位优先级反转：

::

   高优先级 task 阻塞在锁或资源
   → 找到实际持有者
   → 确认持有者优先级较低
   → 检查持有者是否被中间优先级任务抢占
   → 确认锁是否支持优先级继承
   → 测量持锁时间与唤醒延迟
   → 修正临界区、优先级或同步协议

概念辨析
--------

CPU 执行慢与等待 CPU
   前者 task 正在 CPU 上运行；后者 task 已 runnable 但仍在 runqueue 排队。

Load average 与 CPU utilization
   load 包含 runnable 和不可中断等待；utilization 描述 CPU 时间实际被怎样使用。

Runnable 与 sleeping
   runnable task 竞争 CPU；sleeping task 等待条件、资源或事件。

调度延迟与系统调用耗时
   调度延迟只是 syscall 墙钟耗时的一部分，后者还可能包含执行、锁等待、I/O 和信号处理。

普通竞争与优先级反转
   普通竞争是多个 runnable task 排队；优先级反转是高优先级 task 被低优先级持有的资源阻塞。

Affinity 限制与 quota 节流
   affinity 限制可运行位置；quota 限制一段周期内可使用的 CPU 时间。

平均延迟与长尾延迟
   平均值描述总体水平；P99、最大值和单次 wakeup-to-run 时间线决定实时性与交互体验。

本章结论
--------

诊断调度延迟必须先证明 task 已经 runnable，再用 wakeup、迁移和 sched-in 事件说明它在哪里等待、谁占用了 CPU，以及哪项策略或约束阻止它及时运行。
