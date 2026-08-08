第197章：Mobile Architecture Extension Paths
============================================

核心知识点
----------

* 后续深入移动系统应按“现象 → 责任链 → 专项路径”组织，而不是按名词平均阅读；同一个问题先确定主导瓶颈，再进入 Kernel、Graphics、Media、Security、Runtime 或 Tooling 路径。
* Kernel Path 关注调度、内存、驱动、电源与安全：先找线程、buffer、I/O、wakeup、thermal 和访问控制事实，再进入 Linux / XNU 与设备实现。
* Graphics Path 关注一帧的生产、队列、合成和显示：主线程 / render、GPU command、surface / layer、fence、compositor、VSync、display deadline 是核心对象。
* Media Path 关注 stream、buffer、timestamp、codec、container、camera、audio 与 backpressure；录制和播放问题要拆成采集、处理、编码、封装、存储和输出多条流。
* Security Path 关注身份、签名、权限、sandbox、MAC、TEE / Secure Enclave、secure boot 与 exploit mitigation；先确定“谁在访问什么资源、在哪个检查点被拒绝”。
* Runtime Path 关注应用启动、代码加载、对象生命周期、JIT / AOT、GC / ARC、dyld、Swift / Objective-C runtime 和 native bridge；它决定 App 何时能发出请求和消费回调。
* Tooling Path 负责把不同层的证据对齐到统一时间线。Android 侧常用 logcat、dumpsys、bugreport、Perfetto、tombstone；Apple 侧常用 Instruments、Console、MetricKit、sysdiagnose、Crash Logs。
* Android Source Reading 应以 AOSP 能力路径为主，从 Framework / Binder / Service / HAL 进入公开源码，再在 vendor 边界停止或转向设备材料。
* Apple Documentation Reading 应以公开 Framework、headers、entitlement、错误码和诊断工具为主，对私有 daemon / driver 维持证据等级。
* 平台工程能力的最终标准是：面对新现象能够选择正确路径、找到责任所有者、组织证据、验证结论，并明确停止追踪的边界。

关键路径
--------

* 总入口：``User-visible Symptom → Capability Path → Timeline → Dominant Bottleneck → Specialized Path``。
* Kernel：``App / Service Delay → Thread Scheduling / Memory / I/O → Driver Queue / Fence → Power / Thermal → Hardware``。
* Graphics：``Input / State Update → Layout / Render → GPU → Buffer / Layer → Compositor → VSync / Present → Display``。
* Media：``Camera / Audio Capture → Buffer + Timestamp → Processing → Codec → Mux / File → Playback / Upload``。
* Security：``Caller Identity → Signature / Entitlement / Permission → Service Enforcement → Sandbox / SELinux → Secure Hardware / Resource``。
* Runtime：``Process Launch → Code / Framework Loading → Runtime Initialization → Object / Memory Management → App Lifecycle Entry``。
* Tooling：``Symptom Time → Logs → Thread / Process Trace → Service Event → Kernel / Driver Event → Hardware / Thermal Counter``。

概念辨析
--------

* 深入学习 ≠ 从源码第一行开始：先有能力路径和问题假设，再决定阅读层级。
* 性能专项 ≠ 只看 CPU：GPU、memory bandwidth、I/O、network、thermal 和系统策略常共同决定结果。
* Media pipeline ≠ Codec：相机、音频、buffer、timestamp、container、storage 都属于同一媒体责任链。
* Security ≠ Permission：签名、身份、沙箱、MAC、硬件信任和系统服务检查同样关键。
* Tool ≠ Conclusion：trace、log 和 profiler 提供证据，归因仍要依靠正确的系统模型。
* Source availability ≠ Analysis quality：Android 源码更开放，Apple 实现更封闭，但两者都可以用责任边界和运行证据建立可靠结论。

本章结论
--------

完成移动 OS 架构学习后，继续深入的正确方式是围绕真实系统问题选择专项路径。无论进入内核、图形、媒体、安全、运行时还是工具链，都保持同一套“能力路径 + 横切策略 + 证据边界”方法，最终把知识转化为可迁移的平台分析能力。