第176章：建立内核性能调查模型
==============================

核心知识点
----------

性能问题必须先转化为时间路径
   “系统慢”不能直接映射到参数。应先把一次请求拆成用户态排队、On-CPU、Runnable Waiting、Blocking Wait、子系统排队、设备服务、完成唤醒与重试。

调查闭环由假设驱动
   稳定流程是症状定义、对象级路径假设、最小测量点、运行证据、最小修复和同口径复测。工具选择应服从假设，不能先全量采集再拼接解释。

症状需要固定比较边界
   调查必须记录负载、时间窗口、对象范围、延迟分布、吞吐、错误率和正常基线。平均值、单次快照和整机总量都容易掩盖局部长尾。

On-CPU 与 Off-CPU 是第一分叉
   On-CPU 表示任务正在执行指令，适合用 Sampling、Call Graph 和 PMU 解释；Off-CPU 包含等待调度、锁、I/O、内存、网络和定时事件，需要事件时间线与对象状态。

利用率和饱和度不能混用
   利用率描述资源忙碌比例，饱和度描述是否已有额外工作排队。并行设备可以高利用率且低延迟，单 CPU、单队列或单锁也可在整机平均值不高时先饱和。

每类阶段需要不同证据
   CPU 热路径看样本与 PMU，Runnable Waiting 看 ``sched_wakeup`` 到 ``sched_switch``，存储看 Submit、Issue、Complete，网络看逐层 Queue 和 Drop，锁争用看等待者、持有者与锁对象。

计数器必须转换为时间窗口事实
   ``/proc``、sysfs 和设备统计多为累计值，必须计算增量与速率。采集还要保存 Boot ID、PID/TID、Cgroup、CPU、设备、接口和 Generation，避免重启与编号复用污染结论。

多源证据必须能关联同一对象
   应用请求 ID、时间戳、Task、CPU、Queue、Sector、Flow 或设备身份用于连接用户态、Tracepoint、Perf、日志与硬件统计。仅有时间相近不等于存在因果关系。

最小修改用于验证因果
   修改线程数、队列深度、缓冲区、Timeout 或 sysctl 前，必须说明预期改变的中间状态。一次只改一个关键变量，并同时验证收益、长尾、错误和邻居负载。

观测本身属于系统负载
   高频 Sampling、Function Graph、逐事件 Printk 和全量 Trace 都会改变时序。应从低成本 Counter 与 Histogram 开始，再逐步缩小到短时、按对象过滤的深入追踪。

关键路径
--------

端到端时间分解：

::

   Request Arrival
   → User-space Queue
   → User On-CPU
   → Syscall / Kernel On-CPU
   → Runnable Waiting 或 Blocking Wait
   → Subsystem Queue
   → Hardware / Network Service
   → Completion 与 Wakeup
   → User Completion
   → Response

调查闭环：

::

   固定症状、负载与基线
   → 提出对象级路径假设
   → 选择最小测量点
   → 对齐时间、范围和对象身份
   → 找到最早出现等待或饱和的阶段
   → 实施一个最小修改
   → 复测中间状态与业务结果
   → 回滚或固化

证据选择：

::

   On-CPU → perf Sampling / PMU
   Runnable Waiting → Scheduler Trace / PSI
   锁等待 → Lock Event / Owner / Off-CPU Stack
   存储等待 → Writeback + Block Stage + Device Stats
   网络等待 → NIC + NAPI + Stack + Socket + Application

概念辨析
--------

* On-CPU 与 Off-CPU：前者正在执行，后者处于等待、排队、节流或设备服务阶段。
* Runnable 与 Running：Runnable 已具备运行资格；Running 才实际占用 CPU。
* 延迟与吞吐：前者描述单个工作完成时间，后者描述单位时间完成量。
* 利用率与饱和度：资源忙碌不等于已有工作排队，局部饱和也可能被整机平均隐藏。
* Counter 与 Rate：累计计数必须结合两个时间点才能解释当前窗口。
* 路径存在与路径发生：源码证明机制可能执行，运行证据证明当前窗口实际经过。
* 相关性与因果：同步变化只是线索，路径顺序和受控修改才支持因果判断。
* 参数回读与修复成功：控制面数值变化不证明下游状态与用户指标已经改善。

本章结论
--------

内核性能调查的核心，是把墙钟时间拆成执行、等待、排队、服务和重试，再用同一对象、同一窗口的证据找到最早停止推进的位置。