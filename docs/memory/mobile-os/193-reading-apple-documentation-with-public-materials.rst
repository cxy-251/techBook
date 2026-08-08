第193章：Reading Apple Documentation with Public Materials
=========================================================

核心知识点
----------

* Apple 平台分析要建立证据层级：Developer Documentation 描述公开契约，SDK headers 描述类型与 availability，entitlement / Info.plist 描述能力声明，Instruments / Console / sysdiagnose 描述运行证据，Darwin / XNU 公开源码解释底层通用模型。
* Framework API 是最稳定的入口。Session、delegate、notification、error domain、authorization status 和 lifecycle state 都可用于推断系统服务边界。
* Entitlement、runtime authorization、privacy prompt 和 sandbox 分别属于不同控制面：签名能力声明、用户授权、用户交互与资源隔离不能混为一层。
* App 持有 ``AVCaptureSession``、``CLLocationManager`` 等对象，只代表持有公开能力入口；真实硬件、后台预算、并发资源和系统策略由平台服务持有。
* Apple 平台的私有 daemon、驱动协议和内部策略通常没有完整公开源码；结论必须区分“公开事实”“运行观察”“合理推断”“未知实现”。
* XNU / Darwin 公开材料适合解释 Mach、BSD、VM、socket、VFS、IOKit 等基础模型，不能据此直接推出某个 iOS 私有 Framework 的全部调用链。
* 错误码、interruption reason、authorization state、系统设置与日志时间线是封闭平台上定位责任边界的核心证据。
* 保守推断原则：能由公开 API 和工具证据确认的写成事实；只由现象指向系统服务的写成边界推断；私有类名、调度规则与 daemon 内部协议没有证据时不固化。

关键路径
--------

* 资料链：``App Phenomenon → Public Framework Docs → Authorization / Error Semantics → Entitlement / Privacy Declaration → SDK Headers → Instruments / Console / sysdiagnose → Darwin / XNU Model → Bounded Conclusion``。
* Camera：``AVFoundation API → authorization status → session / device state → system media service boundary → driver / ISP / sensor → callback / interruption / error``。
* Location：``Core Location API → authorization + accuracy state → system location service → radio / sensor sources → delegate callback``。
* File access：``User Selection / File API → Sandbox / Entitlement → security-scoped access → VFS / storage → result``。
* 后台能力：``Public Background API → entitlement / declared mode → system scheduler → power / lifecycle policy → callback or deferral``。

概念辨析
--------

* Public API Surface ≠ Private System Architecture：公开 API 定义契约，不等于暴露系统内部结构。
* Entitlement ≠ Permission Prompt：前者是签名能力声明，后者是用户授权交互。
* Authorization state ≠ Hardware availability：权限允许后仍可能因资源占用、生命周期或系统策略失败。
* Darwin / XNU source ≠ iOS full source：公开内核材料只能支撑通用底层模型。
* Process name in logs ≠ verified internal design：日志能证明某进程参与当次运行，不能自动证明其完整职责和内部调用关系。

本章结论
--------

阅读 Apple 平台应从公开 Framework 行为出发，用 entitlement、授权状态、错误语义和诊断工具建立运行证据，再用 Darwin / XNU 公开模型解释底层边界。对私有实现保持证据等级，才能得到长期稳定、可复查的架构结论。