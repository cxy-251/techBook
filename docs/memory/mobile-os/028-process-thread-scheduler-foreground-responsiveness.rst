第028章：Process, Thread, Scheduler, Foreground Responsiveness
==============================================================

核心知识点
----------

* Process 是代码、地址空间、文件描述符、IPC 引用与安全身份的资源容器；Thread 是 Scheduler 实际分配 CPU 的执行单元。
* 一个移动 App 进程通常包含 UI thread、render thread、worker、runtime/GC、network/database callback 等线程；System Service、daemon 与 XPC/Binder 服务也以进程和线程形式参与同一 CPU 竞争。
* 前台响应性的核心是让“用户正在等待的执行链”尽快获得 CPU，而不是让所有线程平均获得资源。
* Scheduler 的输入包括 runnable 状态、优先级/QoS、cgroup/task profile、CPU affinity、核心 capacity、负载、抢占关系以及平台电源和 thermal 状态。
* Worker 从主线程移走耗时工作只解决阻塞位置，不消除总 CPU 成本。Worker 数量过多、持锁、同步等待或回调风暴仍会压缩 UI thread 的运行窗口。
* Binder/XPC 等 IPC 会把前台路径跨到另一个进程。App 线程等待 System Service 时，即使本进程 CPU 占用不高，也可能出现用户可见卡顿。
* Android 会把前台、可见、服务、缓存等进程重要性与 cgroup/task profile 等资源策略叠加到 Linux 调度上；Apple 使用 QoS、后台状态和系统策略向 XNU 表达工作紧迫性。
* 大小核、DVFS、线程迁移与 thermal throttling 会改变同一任务的实际完成时间。冷机流畅、热机卡顿可能来自可用核心 capacity 和频率上限变化。
* Jank、ANR、输入迟滞和发热应分别从线程阻塞、run queue 延迟、IPC 等待、CPU 饱和和 thermal 状态寻找证据。

关键路径
--------

一次前台滑动：

::

   touch event
   → UI thread runnable
   → state / layout work
   → render preparation
   → system compositor dependency
   → Scheduler selects CPU
   → frame deadline
   → present or jank

调度压力定位：

::

   user-visible delay
   → identify waiting thread
   → running / runnable / blocked ?
   → inspect lock / IPC / I/O wait
   → inspect run queue and priority / QoS
   → inspect core placement and frequency
   → inspect thermal / power restriction

概念辨析
--------

* **Process 与 Thread**：Process 定义资源和隔离边界，Thread 定义具体执行流；Scheduler 调度的是 Thread。
* **主线程阻塞与调度延迟**：前者是线程在执行长任务或等待资源，后者是线程已经 runnable 却迟迟拿不到 CPU。
* **后台线程与低优先级工作**：后台线程只是 App 内部组织方式；系统是否降级还取决于进程状态、QoS/cgroup 和平台策略。
* **CPU 使用率与响应性**：总体 CPU 使用率不直接代表前台是否及时运行，关键是目标线程在 deadline 前是否获得足够 capacity。
* **ANR 与 Jank**：Jank 通常是短时间错过帧 deadline；ANR 是更长时间无法处理关键事件，两者时间尺度和证据不同。

本章结论
--------

移动调度的核心不是“线程越多越快”，而是把有限 CPU 时间优先给用户正在等待的路径，并把可延迟工作压到更低资源位置。分析卡顿时，先找到用户等待的线程，再区分它是执行过久、阻塞、等待 IPC，还是 runnable 但被调度延迟，最后再检查核心拓扑、频率和 thermal 状态。