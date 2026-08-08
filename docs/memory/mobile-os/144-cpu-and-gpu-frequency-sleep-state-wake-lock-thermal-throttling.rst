第144章：CPU and GPU Frequency, Sleep State, Wake Lock, Thermal Throttling
==========================================================================

核心知识点
----------

* CPU / GPU frequency scaling 用于在性能与功耗之间动态取舍。系统会根据 runnable load、frame deadline、QoS、boost、功耗和热状态调整频率与核心使用。
* 频率不是越高越好。高频能缩短任务时间，但通常伴随更高电压、瞬时功耗和热量；任务是否真的受 CPU/GPU 算力限制决定升频是否有效。
* Idle State 面向短暂无任务的处理器低功耗驻留；System Sleep / Suspend 面向更深的整机休眠。更深状态功耗更低，但进入/退出成本和 wake latency 更高。
* Target residency 与 exit latency 是理解低功耗状态的两个关键指标：预计空闲不够长时，进入深状态反而得不偿失。
* Wake Lock / Assertion 表达“当前工作需要系统保持某类清醒状态”。它能延迟休眠，不会自动获得网络、后台执行、权限或更高调度优先级。
* Wake Lock 的主要风险是缩短 deep idle / suspend 驻留时间。高频 acquire/release 或忘记 release 都会制造持续耗电。
* Thermal Sensor 覆盖 SoC、CPU/GPU、battery、modem、camera/display 等热源；系统把传感器读数整理成 thermal zone / thermal state。
* Thermal Throttling 不是单纯 CPU 降频。系统可以同时降低 CPU/GPU 频率、限制 display refresh rate、camera 模式、modem 吞吐、充电速度和后台工作量。
* 高刷新率游戏、4K 录像、实时滤镜、5G 上传、热点共享等场景会同时占用多个热源，常出现“冷机快、热机慢”的阶段性性能变化。
* Android 可通过 Power/Thermal service、HAL、kernel governor、wakelock 等路径观察和调节；Apple 普通 App 主要通过 thermal state、QoS 和系统公开能力感知降级，而底层频率策略属于系统内部。
* Power State 与 Thermal State 会共同改变用户体验。同一 workload 在充电、低电量、弱网、高环境温度下可能得到完全不同的性能预算。

关键路径
--------

性能与热反馈：

::

   App workload
   → scheduler / graphics / media / network demand
   → CPU/GPU frequency and resource boost
   → faster execution + higher power
   → thermal sensors rise
   → thermal policy
   → frequency / frame rate / camera / modem / charging throttling
   → reduced workload or user-visible slowdown

休眠与唤醒：

::

   no runnable work
   → shallow idle
   → predicted idle long enough
   → deep idle / suspend
   → wake source fires
   → restore clocks/devices
   → scheduler resumes work

概念辨析
--------

* **DVFS 与 Thermal Throttling**：DVFS 是日常性能-功耗调节机制，thermal throttling 是热边界逼近后更强的保护性降级。
* **Idle 与 Suspend**：Idle 通常是 CPU/局部电源域低功耗状态，Suspend 是更深的系统级休眠状态。
* **Wake Lock 与 Background Permission**：Wake Lock 只能保持清醒，不能绕过 Doze、后台网络限制、权限或系统调度配额。
* **High Frequency 与 High Performance**：频率升高只提高对应计算单元的能力，若瓶颈在内存、ISP、modem、I/O 或锁竞争，性能可能不会线性提升。
* **Thermal State 与 Battery Level**：电量低和温度高是两个独立约束，系统可以同时因二者收缩资源预算。

本章结论
--------

移动设备的性能应按 ``Workload → Frequency/Power → Idle Opportunity → Wakeup Cost → Thermal Feedback → Throttling`` 理解。出现持续掉帧、录像降级、上传变慢或锁屏后任务停止时，应同时检查频率、休眠状态、Wake Lock、热状态和生命周期策略，而不是只看 CPU 使用率。