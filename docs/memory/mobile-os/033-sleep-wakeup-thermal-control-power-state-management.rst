第033章：Sleep, Wakeup, Thermal Control, Power State Management
===============================================================

核心知识点
----------

* Mobile power management 同时管理 CPU idle、device runtime PM、system suspend、wakeup source、DVFS、thermal zone 和 Framework 后台策略。
* CPU idle 处理短时无任务时核心进入低功耗状态；runtime PM 处理单个设备是否挂起；system suspend 处理整机进入更深睡眠；Doze-like policy 则是 Framework 对后台工作和网络的进一步收缩。
* App 进程仍在内存中不代表它可以持续执行。系统可以保留进程状态，同时限制 CPU、Network、Alarm 和 Job，直到维护窗口或用户交互发生。
* Wakeup Event 可能来自 touch、power key、RTC、modem、charger、sensor hub 或高优先级推送；Wakeup Reason 是诊断信息，不应把唤醒后执行的第一个 App 误认为真正触发者。
* CPU/GPU frequency scaling 用更高频率换取更短执行时间，同时增加电流和热量；thermal policy 会在温度升高后限制频率、刷新率、亮度、相机能力和后台并发。
* Thermal state 应被理解为多个 sensor、power rail、surface temperature 和功能安全限制合成的系统状态，而不是只看某个温度读数。
* Camera、Modem、Display、GPU/CPU 是典型高功耗热点。录像 + 高亮屏 + 5G 弱网上传等组合负载会快速耗尽同一 thermal envelope。
* Kernel power policy 管设备状态、frequency、runtime PM 和 suspend 原语；Framework/System Service 决定 App 是否前台、是否允许后台工作、是否降级功能。两层必须同时阅读。
* 热恢复通常存在 hysteresis：负载停止后温度下降需要时间，系统不会在阈值附近频繁恢复/限速。

关键路径
--------

锁屏进入低功耗：

::

   screen off / user inactive
   → Framework background policy shrinks work
   → devices runtime suspend
   → CPU enters deeper idle
   → Kernel system suspend when wake sources ready
   → legal wake event
   → resume devices and services
   → limited work or foreground interaction

高负载热控制：

::

   camera + display + CPU/GPU + modem load
   → power rises
   → thermal sensors report state
   → thermal service / governor raises severity
   → frequency / brightness / frame rate / background limits
   → temperature falls
   → hysteresis-controlled recovery

概念辨析
--------

* **CPU idle 与 system suspend**：前者是 CPU 局部空闲，后者是整机级低功耗状态；设备和唤醒条件不同。
* **Runtime PM 与 App 生命周期**：runtime PM 管硬件设备是否上电，App 生命周期管用户态执行资格，两者会联动但不是同一机制。
* **Wakeup Event 与 Wakeup Reason**：前者是真正触发恢复的事件，后者是系统记录/归因证据，可能粒度有限。
* **Power throttling 与 Thermal throttling**：电流/电池预算和温度预算都能降级性能，触发条件与恢复节奏不同。
* **前台高优先级与无限性能**：前台任务会被优先保护，但仍受电池、安全与 thermal hard limit 约束。

本章结论
--------

移动电源管理的核心是分层休眠、事件分级和热量预算。排查锁屏耗电、通知延迟、游戏降频或相机录制降级时，先确认设备所处 power state，再确认真正 wake source，随后检查 DVFS/thermal 状态，最后看 Framework 如何把底层限制转换成 App 生命周期、后台执行与用户可见降级。