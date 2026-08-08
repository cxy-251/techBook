第143章：Power as First-Class System Resource
==============================================

核心知识点
----------

* Power 是移动系统的一等资源。CPU、GPU、display、modem、camera、storage、sensor 和后台任务最终都共享同一块电池与热预算。
* Power Budget 不只看一次调用耗多少电，还看任务持续多久、唤醒多少次、是否让硬件退出低功耗状态，以及是否有明确用户价值。
* 前台任务和后台任务的能耗资格不同。用户正在等待的导航、通话、拍摄、上传可获得更高预算；低可见性的同步、预取、轮询更容易被延迟、批处理或降级。
* CPU 的主要成本来自持续 runnable work、频率提升与内存访问；GPU 主要受渲染、合成和高帧率影响；Display 受亮度、刷新率、HDR 和常亮时间影响。
* Modem / Wi-Fi 的成本常由 radio wakeup、弱信号、上行传输、长连接和重试放大；Camera 会同时驱动 sensor、ISP、GPU/NPU、display preview、encoder 与存储。
* Wakeup、network polling、location update、sensor sampling 的危险点在“频率”。低数据量但高频唤醒也可能比一次批量任务更耗电。
* 系统倾向把可延迟工作合并到同一调度窗口，在充电、Wi-Fi、设备活跃或资源充足时执行，以增加 deep idle 驻留时间。
* Power Policy 是跨层的：Kernel 管理 idle/suspend/frequency/device power state；System Service 管理任务资格与硬件所有权；Framework 暴露受控 API；App 描述业务意图和约束。
* 用户可见性是能耗授权的重要输入。长期高成本工作通常需要前台状态、通知、媒体/导航/通话等可解释理由。
* Thermal 与 Power 不能分开。高瞬时功耗积累成热量，热状态反过来限制频率、帧率、camera、network 与后台执行。
* App Lifecycle、Notification、Network、Thermal 看似不同，最终都在回答同一问题：当前任务是否值得继续消耗电池与热余量。

关键路径
--------

用户任务进入能耗策略：

::

   user intent
   → App request
   → Framework API
   → system service owns resource state
   → lifecycle + battery + network + thermal policy
   → kernel / driver power decision
   → CPU / GPU / display / modem / camera work
   → energy + heat cost
   → continue / batch / throttle / suspend / stop
   → user-visible result

低功耗优化路径：

::

   many small background operations
   → repeated wakeups / radio activation
   → poor idle residency
   → system batches work
   → fewer wakeups
   → longer idle / suspend residency
   → lower average power

概念辨析
--------

* **Power 与 Performance**：高性能通常需要更高瞬时功耗，但“更快完成后休眠”有时比长时间低速运行更省电，必须看整段时间成本。
* **Instant Power 与 Energy**：瞬时功率描述当前消耗速度，能量描述一段时间累计消耗；移动系统主要优化后者与热累积。
* **Foreground Work 与 Background Work**：区别不只在进程状态，更在用户是否能理解并控制这段资源消耗。
* **Network Bytes 与 Network Energy**：字节量不是唯一指标，radio wakeup、弱信号、tail time、keepalive 和重试都会放大能耗。
* **Power Policy 与 Thermal Policy**：前者管理电池与低功耗状态，后者防止热边界失控；实际系统会联合决策。

本章结论
--------

移动系统的 Power 模型应压缩为 ``User Intent → Resource Demand → System Budget → Hardware Activity → Energy/Heat → Policy Feedback``。分析耗电问题时，不应只看某个 API 或某个硬件，而要同时检查任务可见性、持续时间、唤醒频率、网络/定位策略、生命周期和热状态。