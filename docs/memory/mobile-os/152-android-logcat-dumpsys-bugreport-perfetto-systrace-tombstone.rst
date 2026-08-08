第152章：Android logcat, dumpsys, bugreport, Perfetto, systrace, tombstone
============================================================================

核心知识点
----------

* Android 调试工具的责任分工应固定理解：``logcat → 离散事件``、``dumpsys → System Service 状态``、``bugreport → 设备级快照``、``Perfetto / systrace → 跨层时间线``、``tombstone → Native Crash 现场``、``ANR trace → 响应失败线程栈``。
* ``logcat`` 的首要作用是定位故障时间点和主体。常见字段包括 timestamp、pid、tid、priority、tag、message；main/system/events/crash 等 buffer 用于承载不同来源的事件。
* ``dumpsys`` 直接对应 Android System Service 模型。activity、window、input、power、batterystats、SurfaceFlinger、media.camera 等 dump 可以回答资源所有权、焦点、队列、客户端和系统状态。
* dumpsys 更接近“当前状态快照”，缺少完整历史因果。故障恢复后再采集时，关键瞬时状态可能已经消失，因此应与 log、ANR、trace 联合使用。
* ``bugreport`` 将 logcat、dumpsys、ANR、tombstone、kernel log、系统属性、版本和其他诊断材料放进统一采集边界，适合偶发故障和用户设备问题。
* ``Perfetto`` 把线程调度、Binder、CPU frequency、frame timeline、counter、custom trace、进程和系统服务放在同一时间轴，是判断“时间耗在哪里”的核心工具。
* ``systrace`` 是较早期的系统 trace 入口；现代 Android 分析应优先围绕 Perfetto 数据模型和 UI 展开，旧 systrace 概念仍有助于理解 trace category 与 slice。
* ``tombstone`` 用于 Native Crash，重点字段是 signal、fault address、register、backtrace、memory map、abort message、Build fingerprint 和符号信息。
* ANR 排查时要把主线程状态与 Binder、Looper、锁和远端服务一起看。主线程卡在同步 Binder 调用时，责任链必须继续追到对端进程，而不是停在调用点。
* Android 调试最稳的路径不是“全量抓数据”，而是 ``Log → Dump → Trace → Tombstone/ANR → Source``，每一步解决一个更具体的问题。
* Source 阅读应位于证据链后端。先用运行时材料确认责任边界，再回到 AOSP / App / native library 源码定位实现，能显著减少无目标源码搜索。

关键路径
--------

Android 通用调试路径：

::

   reproduce symptom
   → logcat fixes timestamp + pid/tid/tag
   → dumpsys checks related service state
   → bugreport preserves whole-device context
   → Perfetto finds scheduling / Binder / frame / freq delay
   → ANR trace or tombstone identifies failure thread
   → symbolicate
   → map evidence back to App / Framework / Service / Kernel / Driver source

卡顿路径：

::

   InputDispatcher timeout / user-visible jank
   → main thread state
   → Looper / lock / synchronous Binder?
   → remote service thread
   → sched / freq / queue in Perfetto
   → dumpsys service ownership
   → root cause

概念辨析
--------

* **logcat 与 dumpsys**：前者给事件时间线，后者给系统服务状态；一个偏历史事件，一个偏当前对象状态。
* **bugreport 与 Perfetto**：bugreport 是宽范围设备快照，Perfetto 是高时间精度执行轨迹。
* **ANR trace 与 tombstone**：ANR trace 面向“没及时响应”，tombstone 面向 native 异常终止。
* **Perfetto 与 profiler**：Perfetto 关注全系统时间轴和跨进程关系，单进程 profiler 更偏函数或资源热点。
* **工具输出与根因**：工具只提供证据；根因必须由多份证据在同一时间窗口内相互印证。

本章结论
--------

Android 调试应沿 ``Log → Service State → System Trace → Failure Snapshot → Source`` 逐层推进。logcat 定时间，dumpsys 定状态，bugreport 保现场，Perfetto 定等待与调度，ANR/tombstone 定线程和终止点，最后才回到源码完成责任闭环。