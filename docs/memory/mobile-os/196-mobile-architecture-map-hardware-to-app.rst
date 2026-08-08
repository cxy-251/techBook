第196章：Mobile Architecture Map Hardware to App
================================================

核心知识点
----------

* 移动系统的总图由两条方向组成：``Hardware → App`` 的上行封装路径，以及 ``App → Hardware`` 的下行请求执行路径。
* 上行路径把中断、DMA buffer、firmware 状态和硬件信号转换成 App 可理解的 event、frame、sample、metadata、callback 和 error。
* 下行路径把 App 意图转换成受控操作：Framework 整理请求，IPC 传递身份，系统服务执行权限和资源仲裁，HAL / Driver Framework 连接设备实现，Kernel / Driver 最终调度硬件。
* Kernel 管理进程、线程、内存、文件、网络、设备和安全基础；Driver 管设备控制与数据搬运；Service 持有系统资源和策略；Runtime 管代码执行与对象生命周期；Framework 提供稳定公共能力表面。
* Android Full Map 可压缩为 ``App → Framework → Binder → Service → HAL → Kernel → Hardware``，返回方向通过 callback、shared buffer、metadata 和 event 回到 App。
* Apple Full Map 可压缩为 ``App → Public Framework → XPC / Daemon Boundary → XNU / Driver Boundary → Hardware``，并由 code signing、entitlement、TCC、sandbox 和系统生命周期策略控制。
* Security、Privacy、Power、Thermal、Lifecycle 不是单独“层”，而是横切控制面，会在多个节点改变请求是否允许、何时执行、以什么性能执行。
* Graphics、Input、Media、Camera、Network 都可放回同一个分析框架：找 producer、consumer、service owner、policy、buffer / message 和 hardware endpoint。
* 最终心智模型不是记组件名，而是“能力路径 + 横切策略 + 平台生态”：任何用户现象都应能映射到这三类结构。

关键路径
--------

* 上行：``Hardware Signal → Driver Event → Kernel Object / Buffer → HAL / Driver Framework → System Service State → Framework Callback → App``。
* 下行：``App Intent → Framework API → Permission / Identity → IPC → System Service / Daemon → Resource Policy → HAL / Driver → Hardware``。
* Android：``App → SDK / Framework → Binder → system_server / native service → AIDL/HIDL HAL → Linux Kernel / Driver → Hardware``。
* Apple：``App → Public Framework → authorization / entitlement / sandbox → XPC / System Daemon → XNU / IOKit / DriverKit Boundary → Hardware``。
* Camera：``App Request → Service Arbitration → Sensor / ISP → Frame Buffer + Metadata → Preview / Capture Callback``。
* Input：``Touch Hardware → Driver → Input Service → Framework Event → Gesture / Responder → App``。
* Graphics：``App State → Render → Buffer / Layer → Compositor → Display Engine → Panel``。
* Media：``Capture / Decode → Sample Buffer → Codec → Mux / Render → File / Display``。
* Network：``App Request → Network Service / Policy → Kernel Stack → Wi-Fi / Modem → Response``。

概念辨析
--------

* 上行路径 ≠ callback only：buffer、shared memory、surface 更新和状态事件都属于硬件事实向 App 的封装。
* 下行请求 ≠ direct hardware access：移动 OS 通过服务和策略集中管理敏感、共享和耗电硬件。
* Service ≠ Runtime：Service 管系统资源，Runtime 管进程中的代码加载、执行和对象生命周期。
* Driver ≠ HAL / Driver Framework：前者直接处理设备，后者提供平台与设备实现之间的能力边界。
* 横切策略 ≠ 单点权限：电源、温控、隐私、生命周期会在整条路径上持续影响结果。

本章结论
--------

手机系统可以统一理解为双向能力路径：App 请求向下经过 Framework、服务、策略和驱动到达硬件，硬件结果再向上被封装成 App 事件和数据。把安全、电源、温控、隐私以及平台生态叠加到这张图上，就得到分析 Android、Apple 和 OEM 差异的完整心智模型。