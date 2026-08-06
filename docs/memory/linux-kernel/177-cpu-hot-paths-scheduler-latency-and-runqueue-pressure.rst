第177章：CPU 热路径、调度延迟与 Runqueue 压力
==============================================

核心知识点
----------

CPU 问题先区分执行成本与等待成本
   On-CPU 表示任务正在执行指令，Runnable Waiting 表示任务已经可运行但尚未获得 CPU。两者都能造成请求变慢，却需要完全不同的证据与修复。

Sampling 只解释正在运行的代码
   ``perf record/report`` 的样本分布说明 CPU 时间集中在哪些函数与调用链，不包含任务睡眠、排队或被 Cgroup Throttle 的完整墙钟时间。

热点函数只是阅读入口
   Flat Hotspot 需要结合 Caller/Callee、对象身份和上下文解释。同一 ``copy_*_user``、锁 Slowpath 或调度函数可由文件、网络、驱动、IRQ 和不同系统调用触发。

PMU 用于解释热点为何昂贵
   Cycles、Instructions、Cache/TLB Miss、Branch Miss 和 Stall 描述不同微架构成本。事件含义依 CPU 型号与虚拟化环境，过多事件还会发生 Multiplexing。

整机平均会隐藏局部饱和
   单 CPU、单 RX Queue、单线程、单 Cgroup、单 NUMA Node 或单锁可以先达到极限，而系统总体仍有大量空闲 CPU。

调度延迟来自 Wakeup 到 Switch-in
   ``sched_wakeup`` 记录任务成为 Runnable，``sched_switch`` 记录任务真正开始运行。二者时间差可近似 Runnable Waiting，但必须结合 PID/TID、CPU、优先级和 Generation 关联。

Runqueue 压力有多个来源
   普通任务竞争、RT/DL 任务、IRQ/Softirq、CPU Affinity、Cpuset、Cgroup Quota、CPU Offline 和迁移策略都可能延迟目标任务获得 CPU。

CPU Throttle 不等于 CPU 饱和
   Cgroup Quota 用尽时，即使宿主有空闲 CPU，目标组仍会等待下一个周期。需要检查 ``cpu.max``、``cpu.stat`` 和目标 Cgroup，而不是只看 ``top``。

迁移和绑核是局部性权衡
   绑核可减少迁移与 Cache 抖动，也可能造成负载倾斜。迁移可平衡 Runqueue，却可能增加 NUMA 远端访问与工作集重热成本。

并行度受共享对象限制
   增加线程只有在还有 CPU、队列和可分片工作时有效。线程过多会增加 Context Switch、Runqueue、锁争用、Cache Miss 和内存带宽压力。

关键路径
--------

CPU 热点定位：

::

   固定负载和目标范围
   → perf stat 观察总事件
   → perf record 采集 On-CPU 样本
   → perf report 找到热点函数
   → 展开 Caller/Callee
   → 对齐 Kernel/Module 符号
   → 用 PMU 解释 Cache、Branch、TLB 或 Stall
   → 计算每请求成本

Runnable Waiting：

::

   事件唤醒 Task
   → sched_wakeup
   → Task 进入目标 Runqueue
   → 与普通任务、RT、IRQ 和 Quota 竞争
   → sched_switch 选择 Task
   → Task 真正 Running
   → Wakeup 到 Switch-in 构成调度等待

局部饱和诊断：

::

   总 CPU 看似有余量
   → 检查 Per-CPU 与 IRQ/Softirq
   → 检查 Task、Queue 和 Worker Affinity
   → 检查 Cpuset 与 Cgroup Quota
   → 检查单线程、单 Queue 和锁热点
   → 对齐 NUMA 与工作集
   → 决定分片、迁移或减少工作

概念辨析
--------

* Hotspot 与根因：样本落点必须结合调用来源、对象和工作量解释。
* On-CPU 与 Runnable Waiting：前者正在执行，后者有资格运行却未得到 CPU。
* Runnable Waiting 与 Blocking Sleep：前者等待调度资源，后者等待锁、I/O、Timer 或其它事件。
* CPU 总利用率与局部饱和：整机平均值可能隐藏单 CPU、Cgroup、Queue 和 NUMA Node 压力。
* Cycles 与 Instructions：Cycles 包含停顿，Instructions 表示退休工作量。
* CPU Throttle 与 CPU 竞争：Throttle 来自策略限额，竞争来自可运行任务争夺处理器。
* Affinity 与性能保证：固定位置只改变运行范围，不创造新的 CPU 服务能力。
* Context Switch 与调度器缺陷：切换数量需要结合原因、等待时间和业务模型解释。

本章结论
--------

CPU 性能分析必须同时回答“CPU 正在执行什么”和“目标任务为什么还没运行”；Sampling、PMU 与调度时间线缺一不可。