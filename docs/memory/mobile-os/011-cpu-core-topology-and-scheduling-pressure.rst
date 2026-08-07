第011章：CPU Core Topology and Scheduling Pressure
==================================================

核心知识点
----------

* 手机 CPU 常采用异构核心。Performance Core 提供低延迟与短时峰值能力，Efficiency Core 适合持续、低优先级和可延迟工作；调度目标是把有限高性能预算优先给用户正在等待的路径。
* CPU topology 不只包含核心数量，还包括 cluster、cache 共享、最大 capacity、频率域和电源域。线程放在哪个核心会改变缓存局部性、可用频率和能耗。
* DVFS 动态调整电压与频率。更高频率缩短执行时间，也提高瞬时功耗和温度；移动系统必须在交互延迟与持续功耗之间平衡。
* Scheduler 的输入是 runnable 线程、优先级、调度组、CPU capacity、负载、affinity、QoS/uclamp 等信息；输出是线程在何时、哪个 CPU 上运行。
* 一帧是否流畅取决于 deadline。60 Hz、90 Hz、120 Hz 显示下可用 CPU 时间越来越短，UI thread、render thread、系统 IPC callback 和后台工作必须在同一时间窗内竞争运行机会。
* Android 在 Linux scheduler 之上使用 cgroup、task profile、uclamp、EAS 等机制表达前后台与性能需求；Apple 公开接口更多以 QoS 和工作类别表达任务紧急程度。共同目标都是保护交互路径并压低后台成本。
* 线程迁移可以利用空闲核心或更高 capacity，也会损失 cache locality 并引入迁移开销。频繁迁移并不自动等于更快。
* 后台任务只有在 runnable 时才直接制造 CPU 竞争；大量解码、同步、索引、压缩线程同时 runnable 会挤压前台线程的 frame budget。
* Thermal throttling 会降低高性能核心可持续频率。冷机时正常、长时间录像或游戏后变慢，必须把温控状态纳入 CPU 分析。
* CPU 利用率不能单独证明瓶颈。低优先级限制、E-core 饱和、频率提升滞后、锁等待或错误线程放置都可能在总体利用率不高时造成交互延迟。

关键路径
--------

一帧交互：

::

   touch / VSync wakes UI thread
   → UI work becomes runnable
   → scheduler selects CPU
   → choose capacity / cluster
   → DVFS sets frequency
   → UI and render work complete before deadline?
   → smooth frame or jank

调度压力定位：

::

   visible latency
   → inspect runnable threads
   → inspect priority / QoS / cgroup
   → inspect CPU placement and migration
   → inspect frequency response
   → inspect thermal limits
   → identify delayed critical thread

移动端优先级：

::

   user-visible work
   → high urgency / foreground policy
   → scheduler protects latency
   → background work receives lower urgency
   → idle / cached work deferred or reclaimed

概念辨析
--------

* **P-core 与“前台专属核心”**：P-core 是高 capacity 资源，并非永久绑定某个 App；具体放置由调度器根据负载和策略决定。
* **频率与性能**：高频能缩短单次执行，但持续高频会消耗热预算，长期性能可能反而下降。
* **CPU 利用率与调度延迟**：平均利用率低也可能存在关键线程长时间等不到运行机会。
* **线程优先级与业务重要性**：业务上重要的任务只有被正确表达为 foreground/QoS/priority，系统调度器才有依据保护它。
* **迁移与负载均衡**：把线程换核可以避开拥塞，也可能增加 cache miss；负载均衡不是无成本操作。

本章结论
--------

移动 CPU 性能问题本质上是“关键线程能否在 deadline 前获得足够 capacity”。分析交互延迟时，应同时观察异构核心、runqueue、优先级/QoS、DVFS、迁移和 thermal state，而不是只看 CPU 百分比或核心峰值频率。