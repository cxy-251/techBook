第050章：诊断调度延迟与饥饿
===========================

本章必须记住
------------

#. 程序变慢时，必须先区分“已经获得 CPU 但执行很慢”和“已经可运行却长期排不上 CPU”。
#. 调度延迟是 task 从变为 runnable 到真正被调度上 CPU 之间的时间。
#. 运行时间是 task 已经占用 CPU 执行的时间；等待运行时间是 task 在 runqueue 中等待 CPU 的时间。
#. task 正在睡眠、等待 I/O、futex、锁或设备时，不属于 runnable 队列等待，不能直接判定为调度饥饿。
#. CPU 饥饿表示 task 长期处于 runnable 状态，却因为竞争、优先级、亲和性、配额或更高调度类干扰而得不到足够 CPU。
#. 系统 load average 统计可运行任务和不可中断睡眠任务，不能直接等同于 CPU 使用率。
#. load average 高可能来自 CPU runqueue 拥塞，也可能来自大量 ``D`` 状态 I/O 等待。
#. ``/proc/stat`` 的 CPU 时间、``procs_running`` 和 ``procs_blocked`` 应与 load average 在同一采样窗口中解释。
#. CPU busy 高说明 CPU 时间被执行路径占用；runqueue pressure 高说明有多个 runnable task 正在竞争 CPU。
#. CPU 全局仍有大量 idle，而目标 task 等待运行时间很高时，应优先检查 affinity、cpuset、CPU quota、隔离 CPU 和局部热点。
#. 单个 CPU 满载而其它 CPU 空闲，可能来自 task affinity、IRQ affinity、per-CPU 工作、调度域边界或不可迁移状态。
#. 当进程级 schedstat 可用时，``/proc/<pid>/schedstat`` 可以提供实际运行时间、runqueue 等待时间和运行次数等调度统计。
#. schedstat 字段与可用性受内核版本和配置影响，使用前应核对当前内核文档与输出格式。
#. 两次采样之间等待时间增长远大于运行时间增长，是目标 task 正在等 CPU 的强证据。
#. ``sched_wakeup`` 表示 task 被唤醒并进入 runnable 路径，``sched_switch`` 表示 CPU 实际切换执行者。
#. 对同一 task，``sched_wakeup`` 到它作为 ``sched_switch`` 的 next task 之间的时间，就是一次关键调度延迟样本。
#. task 作为 ``sched_switch`` 的 next 出现后，到它作为 prev 被切出之间的时间，是一次 CPU 运行区间。
#. 若 task 被唤醒后很快上 CPU，但马上因等待条件再次睡眠，瓶颈更可能在锁、I/O、futex 或业务条件，不是 runqueue 饥饿。
#. ``perf sched timehist`` 可以展示等待时间、调度延迟和运行时间，适合快速建立 task 级时间线。
#. ftrace/tracefs 的 ``sched_wakeup``、``sched_waking``、``sched_switch`` 和 ``sched_migrate_task`` 能提供更直接的调度事件证据。
#. tracing 会增加开销并改变时序，采集窗口、事件范围和目标 PID 应尽量缩小。
#. ``strace`` 只能看到系统调用边界耗时，不能单独区分 syscall 内部在运行、睡眠还是等待调度。
#. 一个 syscall 墙钟耗时很长，可能包含 CPU 执行、runqueue 等待、锁等待、I/O 和信号重启。
#. 普通 CFS 压力表现为多个普通 runnable task 争用 CPU；应结合 nice、cgroup weight、quota 和实际等待时间分析。
#. 更高实时优先级或 deadline task 长期 runnable，会压制普通任务和低优先级实时任务。
#. RT throttling 事件或统计可说明实时带宽用尽，但具体接口受内核配置和版本影响。
#. 优先级反转的典型形态是：高优先级 task 等待锁，锁由低优先级 task 持有，而中间优先级 task 又持续抢占持锁者。
#. 诊断优先级反转必须同时证明高优先级等待对象、低优先级持有者和中间干扰者，不能只看最终阻塞栈。
#. PI mutex 或 rtmutex 可以提升持锁者优先级，但普通 mutex、用户态自定义锁和设备协议不一定具备相同机制。
#. cgroup CPU quota 用尽会让 runnable task 被节流；此时机器可能仍有空闲 CPU，但该 cgroup 暂时不能继续运行。
#. Affinity 太窄会让 task 被限制在拥塞 CPU；扩大 affinity 只有在锁、缓存和 NUMA 成本允许时才可能改善延迟。
#. Scheduler debugfs、sysctl 和特性开关是版本敏感控制面，读取可用于取证，修改前必须保存原值和恢复方案。
#. 调度器参数调整可能改变公平、吞吐、功耗和实时性，不能把单次改善直接当成通用配置结论。
#. 可靠诊断必须统一用户日志、perf、tracefs、dmesg 和墙钟时间基准。
#. 最终结论应回答：task 何时 runnable、在哪个 CPU 排队、谁在占用 CPU、为何不能迁移、何时真正运行。
#. 平均值会隐藏长尾延迟；调度问题应保留每次 wakeup-to-run 样本和高分位分布。

必背路径
--------

判断是否在等 CPU：

::

   确认目标线程的 TID
   → 读取 task 状态
   → 判断它是 runnable 还是 sleeping
   → 同窗口采样 CPU utilization、procs_running 和 schedstat
   → 比较运行时间增量与 runqueue 等待增量
   → 等待显著增加时进入调度时间线分析

建立 wakeup-to-run 时间线：

::

   捕获目标 task 的 sched_wakeup
   → 记录唤醒时间和目标 CPU
   → 跟踪后续 sched_migrate_task
   → 找到 task 首次作为 sched_switch next
   → 计算 wakeup 到 sched-in 的延迟
   → 找到 task 作为 prev 被切出的时刻
   → 计算本次运行区间
   → 对多次样本统计分布和长尾

定位调度饥饿原因：

::

   确认 task 持续 runnable
   → 检查同 CPU 上运行者的 policy 与 priority
   → 检查 RT、deadline 和 IRQ/softirq 干扰
   → 检查 affinity、cpuset 和调度域
   → 检查 cgroup quota、weight 与 throttling
   → 检查迁移事件和局部 runqueue 压力
   → 再判断是普通拥塞、策略压制还是位置限制

定位优先级反转：

::

   高优先级 task 阻塞在锁或资源
   → 找到当前持有者
   → 确认持有者优先级较低
   → 检查持有者是否被中间优先级 task 抢占
   → 确认锁是否支持优先级继承
   → 测量持锁区间和唤醒延迟
   → 缩短临界区、修正优先级或更换同步协议

调整参数前：

::

   保存当前内核、配置与调度参数
   → 建立未修改基线
   → 一次只修改一个变量
   → 在相同负载下重复采样
   → 同时观察延迟、吞吐、CPU 与能耗
   → 验证长尾和故障场景
   → 无稳定收益时恢复原值

必须区分
--------

CPU 执行慢与等待 CPU
   前者 task 已在 CPU 上运行；后者 task 已 runnable 但仍在 runqueue 中排队。

Load average 与 CPU utilization
   load 包含 runnable 和不可中断等待；utilization 描述 CPU 时间被怎样使用。

Runnable 与 sleeping
   runnable task 参与 CPU 竞争；sleeping task 等待的是条件、资源或事件。

调度延迟与系统调用耗时
   调度延迟只是 syscall 墙钟时间中的一个可能组成部分。

普通竞争与优先级反转
   普通竞争是多个 runnable task 排队；优先级反转是高优先级 task 被低优先级持有资源阻塞。

Affinity 限制与 quota 节流
   affinity 限制可运行位置；quota 限制一定周期内可使用的 CPU 时间。

平均延迟与长尾延迟
   平均值描述总体水平；P99、最大值和单次时间线决定实时与交互体验。

一句话结论
----------

诊断调度延迟必须证明 task 已经 runnable，并用 wakeup、迁移和 sched-in 时间线说明它在哪里等待、谁占用了 CPU，以及哪项策略阻止它及时运行。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 10，Scheduler Architecture, CFS, Real-Time Classes, and CPU Time；
* AIBook 章节：Chapter 50，Diagnosing Scheduling Latency and Starvation；
* 源文件：``docs/LinuxK/Part_10_Scheduler_Architecture_CFS_Real_Time_Classes_and_CPU_Time/Chapter_050_Diagnosing_Scheduling_Latency_and_Starvation.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_10_Scheduler_Architecture_CFS_Real_Time_Classes_and_CPU_Time/Chapter_050_Diagnosing_Scheduling_Latency_and_Starvation.md>`_。