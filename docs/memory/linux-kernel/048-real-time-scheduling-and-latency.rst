第048章：实时调度类与延迟保证
=============================

本章必须记住
------------

#. 实时调度关注的是可预测的响应延迟，不等于任务永远最快，也不等于延迟为零。
#. Linux 固定优先级实时策略主要包括 ``SCHED_FIFO`` 和 ``SCHED_RR``，二者都属于实时调度类。
#. Linux 用户态可见的实时优先级通常为 1—99，数值越大，实时优先级越高。
#. 实时任务优先于普通公平类任务；同一 CPU 上存在可运行的高优先级实时任务时，普通任务可能长期得不到运行。
#. ``SCHED_FIFO`` 同优先级任务按队列顺序运行，当前任务会持续运行，直到阻塞、主动让出、退出、被更高优先级任务抢占或被带宽机制节流。
#. ``SCHED_FIFO`` 没有普通公平调度意义上的时间片轮转。
#. ``SCHED_RR`` 继承固定优先级规则，并在同一实时优先级的 RR 任务之间使用时间片轮转。
#. RR 时间片只解决同优先级实时任务的轮换，不会让低优先级实时任务或普通任务自动获得相同机会。
#. 实时任务的 priority 与普通任务的 nice 是两套不同机制；nice 不会压过更高调度类中的可运行实时任务。
#. 一个高优先级 FIFO 线程若持续计算且不阻塞，可能造成低优先级任务和普通任务饥饿。
#. 实时线程应具有明确的最坏执行时间、阻塞点、周期、资源边界和故障恢复方式。
#. 实时带宽控制用 period 和 runtime 限制一段窗口内实时类可占用的 CPU 时间。
#. ``sched_rt_period_us`` 表示带宽窗口，``sched_rt_runtime_us`` 表示窗口内允许的实时运行预算；具体默认值受内核与系统配置影响。
#. 将实时 runtime 设为无限制会扩大失控实时线程拖死系统的风险。
#. 实时带宽用尽后，相关实时队列会被暂时节流，让普通任务和恢复路径获得 CPU。
#. cgroup 实时组调度是否可用取决于内核配置和控制器实现，不能把某个接口路径视为所有系统都存在。
#. ``SCHED_DEADLINE`` 属于 deadline 调度类，通常在固定优先级实时类之前参与选择。
#. Deadline 任务用 ``runtime``、``deadline`` 和 ``period`` 描述每个周期所需 CPU 预算和时间约束。
#. 常见合法关系是 ``runtime <= deadline <= period``；内核还会执行参数校验和准入控制。
#. Deadline 的 runtime 是预算，deadline 是相对截止时间，period 是任务激活周期；三者不能互换。
#. Deadline 调度通常结合最早截止时间优先和 CBS 预算控制，避免任务无限透支 CPU。
#. 准入控制用于避免接受一组理论上无法同时满足预算的 deadline 参数。
#. 实时调度只能约束调度层面的 CPU 获得时机；IRQ 延迟、不可抢占区、锁等待、缺页、内存回收和设备响应仍会增加端到端延迟。
#. 一个任务被及时调度到 CPU，不代表它能在截止时间前完成；还必须控制执行时间和阻塞时间。
#. 高优先级任务等待低优先级任务持有的锁会产生优先级反转。
#. 支持优先级继承的锁可以临时提升持锁者，缩短高优先级等待，但不能消除所有依赖和死锁风险。
#. 实时任务执行普通用户内存缺页、动态分配、日志刷屏或不可预测 I/O，会放大延迟抖动。
#. CPU affinity 可以隔离实时工作和普通工作，也可能把多个实时任务挤到同一个 CPU 上形成局部干扰。
#. 中断和软中断运行位置会影响实时线程，即使用户 task 已经绑定到独立 CPU。
#. PREEMPT_RT、内核抢占模型、IRQ 线程化和驱动实现会改变可达到的最坏延迟，需要按目标内核验证。
#. 实时保证必须通过最坏情况测试、调度 trace、IRQ/锁延迟和预算监控验证，不能只看平均延迟。
#. 设置实时策略通常需要相应权限和资源限制；失败可能来自 capability、RLIMIT 或 cgroup 策略。

必背路径
--------

固定优先级实时选择：

::

   task 变为 runnable
   → 根据 policy 进入 RT sched_class
   → 放入对应实时优先级队列
   → 比较当前 CPU 上最高可运行 RT priority
   → 高优先级任务抢占低优先级或 fair task
   → FIFO 运行到阻塞、让出或被抢占
   或 RR 在同优先级内按 quantum 轮转

实时带宽控制：

::

   周期窗口开始
   → RT task 消耗 runtime 预算
   → 更新 RT 带宽统计
   → 预算尚有剩余时继续按 priority 调度
   → 预算耗尽后 throttle RT 队列
   → fair task 获得运行机会
   → 下个 period 补充预算并解除节流

Deadline 任务：

::

   用户提交 runtime、deadline、period
   → 内核验证参数关系与权限
   → 执行带宽准入控制
   → task 进入 deadline class
   → 每次激活获得 runtime 预算
   → 按有效 deadline 参与选择
   → 预算耗尽时节流或等待补充
   → 进入下一个周期

排查实时延迟：

::

   确认 policy、priority 或 deadline 参数
   → 确认 task 何时变为 runnable
   → 测量 wakeup 到 sched-in 延迟
   → 检查更高优先级 task 与 RT throttling
   → 检查 IRQ、softirq 和不可抢占区
   → 检查锁等待与优先级反转
   → 检查缺页、分配和 I/O 阻塞
   → 用最坏情况窗口验证截止时间

必须区分
--------

``SCHED_FIFO`` 与 ``SCHED_RR``
   FIFO 运行到阻塞或被抢占；RR 在同一实时优先级内加入时间片轮转。

实时优先级与 nice
   实时优先级决定 RT 类内顺序；nice 只影响普通公平类份额。

固定优先级实时与 deadline
   FIFO/RR 按静态 priority；deadline 按预算、截止时间和周期约束。

调度延迟与执行时间
   调度延迟是 runnable 后等 CPU 的时间；执行时间是拿到 CPU 后完成工作的时间。

实时与高吞吐
   实时追求延迟上界和可预测性；高吞吐追求单位时间完成更多工作。

优先级反转与普通抢占
   普通抢占是更高优先级任务占用 CPU；优先级反转是高优先级任务被低优先级持有的资源阻塞。

一句话结论
----------

实时调度通过固定优先级或 runtime/deadline/period 预算缩短可运行任务的等待时间，但端到端保证仍取决于执行时间、锁、中断、内存和设备路径。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 10，Scheduler Architecture, CFS, Real-Time Classes, and CPU Time；
* AIBook 章节：Chapter 48，Real-Time Scheduling Classes and Latency Guarantees；
* 源文件：``docs/LinuxK/Part_10_Scheduler_Architecture_CFS_Real_Time_Classes_and_CPU_Time/Chapter_048_Real-Time_Scheduling_Classes_and_Latency_Guarantees.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_10_Scheduler_Architecture_CFS_Real_Time_Classes_and_CPU_Time/Chapter_048_Real-Time_Scheduling_Classes_and_Latency_Guarantees.md>`_。