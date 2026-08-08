第151章：Logs, Crash Reports, ANR, Watchdog, System Diagnostics
================================================================

核心知识点
----------

* 移动系统诊断资料应按时间粒度和责任边界拆分：``Log`` 记录运行事件，``Crash Report`` 保存异常终止现场，``ANR / Hang`` 保存响应失败现场，``Watchdog`` 监控系统服务健康，``System Diagnostics`` 保存整机快照。
* Log 的核心字段是 timestamp、process、thread、tag/category、level 和 message。诊断价值来自事件顺序，而不是某一条孤立错误日志。
* Crash Report 的稳定阅读顺序是 ``termination reason / exception / signal → crashed thread → backtrace → binary image / symbol``。Native crash 还要看 fault address、register、memory map、abort message。
* Android ANR 与 Apple hang 的核心问题不是“进程死了”，而是“哪个线程本应响应却没有响应”。首先检查 main thread / service callback / run loop / lock / synchronous IPC。
* ANR 常见根因包括主线程长计算、磁盘 I/O、同步 Binder 调用、锁竞争和消息队列长期阻塞。超时只是系统观察结果，真正责任可能继续延伸到远端服务或底层资源。
* Watchdog 关注 system_server、daemon 或关键系统线程的健康。它与 App ANR 的区别在于监控对象更靠近系统控制面，故障可能触发服务重启、进程终止或系统恢复。
* System Diagnostics 把进程列表、内存、电源、网络、系统服务、日志、trace、crash、ANR 等材料放进同一个采集窗口，适合分析偶发和跨层故障。
* Symbolication 是诊断闭环的必要步骤。地址只有和正确版本的符号、Build ID、UUID、dSYM、mapping 等匹配后，才能还原到函数或源码位置。
* 线程栈必须结合线程状态阅读：running 表示正在执行，runnable 表示等待 CPU，blocked 表示等待锁或同步对象，sleeping/waiting 表示等待事件、I/O、IPC 或 timer。
* 多份诊断资料必须使用同一个时间基准。可靠结论通常来自“日志事件 + 线程栈 + 系统状态 + 资源状态”相互印证，而不是单份报告。
* Crash、ANR、watchdog、memory pressure termination 可能表现为相似的“闪退/卡死/重启”，必须先确认系统记录的终止类型，再进入具体责任链。

关键路径
--------

异常终止：

::

   user action
   → runtime events in logs
   → process terminates
   → crash / tombstone / diagnostic report
   → termination reason
   → crashed thread + backtrace
   → symbolication
   → correlate pre-crash logs and resource state
   → root cause boundary

响应失败：

::

   user event or service request
   → expected thread fails deadline
   → ANR / hang / watchdog record
   → inspect blocked thread
   → find lock / IPC / I/O / queue owner
   → inspect related process or system service
   → correlate system diagnostics

概念辨析
--------

* **Crash 与 ANR / Hang**：crash 已发生异常终止，ANR/hang 是仍未及时响应；二者首要证据不同。
* **ANR 与 Watchdog**：ANR 主要关注 App 响应窗口，watchdog 更关注系统关键服务和线程健康。
* **Stack Trace 与完整因果链**：stack 只说明采样或崩溃时线程位于哪里，根因还需结合时间线、锁持有者、远端 IPC 与资源状态。
* **Symbolication 与反编译**：symbolication 用构建符号把地址映射回函数；它不是从二进制重新推断全部源码。
* **System Diagnostics 与 Log**：日志提供事件骨架，诊断包提供更大的设备上下文；诊断包仍需以故障时间点进行筛选。

本章结论
--------

移动系统诊断应按 ``事件 → 终止/超时类型 → 线程状态 → 资源等待 → 系统上下文 → 符号化`` 阅读。真正的根因不是“出现了 ANR”或“某线程崩溃”，而是明确哪个线程在什么时间等待或执行什么资源，以及责任如何沿 App、IPC、System Service、Kernel 或 Hardware 继续传递。