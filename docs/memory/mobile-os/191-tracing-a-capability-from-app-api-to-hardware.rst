第191章：Tracing a Capability from App API to Hardware
======================================================

核心知识点
----------

* Capability Trace 的目标是把 App 可见现象还原成 ``API → Framework → IPC → System Service / Daemon → Policy → HAL / Driver Framework → Kernel / Driver → Hardware`` 的责任链。
* 追踪必须同时记录正向请求与返回路径：前者携带参数、调用者身份和资源申请，后者携带错误码、回调、buffer、metadata 与状态变化。
* Framework 负责把业务意图整理成系统可执行的 session、request、surface、callback 与状态机；系统服务才持有资源所有权、并发状态和策略判断。
* IPC 是第一个硬边界。Android 重点看 Binder、AIDL、caller UID / PID、service owner；Apple 重点看公开 Framework、XPC、签名身份、entitlement、sandbox 和系统 daemon 边界。
* Permission、AppOps、TCC、entitlement、sandbox、前后台状态、设备策略和资源占用属于能力执行前的控制面，用户弹窗只是其中一个节点。
* HAL / Driver Framework 把平台语义连接到具体硬件实现；Kernel / Driver 最终承担调度、buffer、设备队列、firmware 交互与硬件错误。
* Trace 的结论应落到“请求在哪一层被接受、拒绝、排队、降级或失败”，而不是停留在“API 调用失败”或“硬件坏了”。

关键路径
--------

* 通用下行：``App API → Framework State Machine → IPC → Service Ownership → Permission / Lifecycle / Resource Policy → HAL / Driver Framework → Kernel / Driver → Hardware``。
* 通用上行：``Hardware Event / Buffer → Driver → HAL / Driver Framework → Service State → IPC Callback / Shared Buffer → Framework → App``。
* Camera：``openCamera / AVCaptureSession → Service / Daemon → Authorization + Foreground + Resource Arbitration → HAL / Driver → Sensor / ISP → Preview Buffer → App``。
* Touch：``Touch Controller → Driver → Input Service → Framework Event → Hit Test / Gesture → App Callback``。
* Frame：``App State → UI / Layer → Render / Buffer → System Compositor → Display Hardware → Present``。
* Audio：``App Audio API → Audio Service → Route / Focus Policy → HAL / Driver → Codec / Speaker / Microphone``。
* Network：``App Request → Network Framework → DNS / TLS / Route Policy → Kernel Network Stack → Wi-Fi / Modem → Response``。

概念辨析
--------

* API 调用成功 ≠ 能力成功：大量移动能力采用异步 callback，方法返回只表示请求被接收。
* Permission granted ≠ 资源可用：服务仍会检查生命周期、资源占用、系统策略、温控和设备状态。
* IPC 延迟 ≠ 硬件延迟：服务线程、锁、Binder / XPC 排队就可能让 App 看起来像“硬件慢”。
* Framework object ≠ 硬件所有权：App 持有 session 或 manager，只是持有受控入口。
* Hardware capability ≠ App capability：硬件规格还要经过驱动、HAL、Framework、权限与平台策略才能成为第三方 App 可用能力。

本章结论
--------

分析任何移动系统问题时，先固定一个 App 可见行为，再按能力路径逐层确认请求、身份、策略、资源所有者和返回证据。能够明确指出失败发生在哪个边界，才算完成一次有效的系统追踪。