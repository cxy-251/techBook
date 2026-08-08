第194章：Comparative Analysis Method for Mobile Systems
=====================================================

核心知识点
----------

* 横向比较必须先固定“同一个系统问题”，再用同一组维度比较 Android 与 Apple：入口 API、调用身份、IPC、服务所有权、权限执行点、资源仲裁、硬件边界、生命周期、可观测证据和失败表现。
* Kernel Boundary 比较的是最低资源事实：Linux 与 XNU 都负责进程、线程、内存、文件、网络和设备访问，但用户可见行为还由上层移动平台策略决定。
* Driver Boundary 的重点是“硬件如何被包装成系统能力”。Android 通过 HAL / vendor interface 组织多厂商硬件；Apple 通过自控 Framework、daemon、XNU 与 DriverKit / IOKit 边界组织垂直整合能力。
* IPC Boundary 比较 Binder 与 XPC / Mach 时，应重点看 caller identity、同步 / 异步语义、服务发现、进程隔离、错误传播和可观测性，而不是只做名词对应。
* Security Boundary 应把 Android 的 UID / permission / AppOps / SELinux 与 Apple 的 code signing / entitlement / TCC / sandbox 放到“谁能调用、用户是否同意、平台是否允许、服务是否放行”的共同模型中。
* Runtime Boundary 比较 ART / Zygote / DEX / JIT / AOT / GC 与 Mach-O / dyld / Swift / Objective-C Runtime / ARC，重点看启动、加载、动态分发、内存管理和运行时成本。
* Graphics、Media、Camera 适合用数据流比较：frame、buffer、timestamp、surface / layer、codec session、camera request 都能映射到生产者、系统服务、硬件处理和返回路径。
* 平台差异最终要放回生态结构：硬件控制权、OEM / vendor 协作、分发渠道、更新责任、区域策略和第三方能力开放度都会改变工程结果。

关键路径
--------

* 通用比较模板：``Same User-visible Problem → API Entry → Identity → IPC → Service Owner → Policy → Driver Boundary → Kernel / Hardware → Returned Result``。
* Camera：``Camera2 / CameraService / HAL`` 对比 ``AVFoundation / system media service boundary / Apple-controlled driver path``。
* IPC：``Binder Proxy → Binder Driver → Service Stub`` 对比 ``Framework → XPC / Mach Service → Daemon``。
* Security：``UID + Permission + AppOps + SELinux`` 对比 ``Code Signing + Entitlement + TCC + Sandbox``。
* Runtime：``Zygote Fork → ART → DEX/JIT/AOT/GC`` 对比 ``Process Launch → dyld → Mach-O → Swift/ObjC Runtime → ARC``。
* Graphics：``View / RenderThread / Skia → Surface / BufferQueue → SurfaceFlinger / HWC`` 对比 ``View / CALayer → Core Animation / Metal → Display Server``。

概念辨析
--------

* 名词相似 ≠ 责任相同：Binder 与 XPC 都是 IPC，但服务布局、身份模型和可观测方式不同。
* Kernel difference ≠ Platform difference 全部：真正影响 App 的还有服务、权限、生命周期、vendor / daemon 和生态策略。
* HAL ≠ Driver：HAL 是平台与 vendor 的能力接口，driver 负责更底层设备控制。
* Open ecosystem ≠ 无约束；Integrated ecosystem ≠ 无复杂性：两者只是控制权与协作边界不同。
* API feature parity ≠ 实际能力一致：同名能力还会受到设备硬件、后台政策、权限和系统版本影响。

本章结论
--------

Android 与 Apple 的有效比较应围绕共同系统问题和共同责任边界展开。只有把入口、身份、服务、策略、硬件和用户结果放在同一张路径图上，平台差异才会从品牌印象变成可验证的工程判断。