第195章：Mobile OS Misreading Patterns
======================================

核心知识点
----------

* “Android 就是 Linux”只描述内核基础，遗漏 Framework、Binder、system_server / native service、HAL、GMS / OEM、移动电源与生命周期策略。
* “iOS 就是 Unix”只描述 Darwin / XNU 背景，遗漏 code signing、entitlement、TCC、sandbox、Framework / daemon、Secure Enclave、分发和平台策略。
* Framework API 是能力表面，不是完整系统实现；API 之后仍有 IPC、服务状态、权限检查、资源仲裁、HAL / driver、硬件和返回路径。
* Permission Prompt 只代表用户授权交互，不等于完整安全模型。身份、签名、沙箱、MAC、服务检查、Verified Boot / secure boot 与硬件信任仍独立存在。
* OEM 系统差异的核心不在 UI Skin；真正影响 App 行为的是后台、电源、权限、推送、相机、调度、更新、vendor service 和区域生态。
* 性能问题不能只归因于 App 代码。调度、GC / ARC、GPU、I/O、网络、内存压力、热降频、后台竞争和硬件状态都可能改变结果。
* 硬件规格不是系统能力。Sensor、GPU、NPU、Camera、Modem 等硬件必须经过 driver、HAL / Framework、权限和策略才能变成 App 可使用的能力。
* 平台封闭性不代表架构简单。封闭平台仍包含复杂的 kernel、daemon、runtime、driver、硬件和安全链，只是第三方可见证据不同。

关键路径
--------

* 误读修正：``App-visible Symptom → Framework Entry → IPC / Service Owner → Identity / Permission → Lifecycle / Power / Thermal Policy → HAL / Driver / Kernel → Hardware``。
* Android：``App → Android Framework → Binder → system_server / native service → HAL → Linux Kernel → Hardware``，并叠加 GMS / OEM 服务。
* Apple：``App → Public Framework → XPC / Daemon Boundary → Entitlement / TCC / Sandbox → XNU / Driver Boundary → Hardware``。
* 性能：``User Symptom → Main Thread / Runtime → Scheduler / Memory → GPU / I/O / Network → Thermal / Power → Hardware``。
* OEM 差异：``Public Android API → System Service → OEM Policy / Vendor Service → HAL / Driver → User-visible Behavior``。

概念辨析
--------

* Linux kernel ≠ Android platform；Darwin / XNU ≠ Apple mobile platform。
* Permission granted ≠ security complete；用户同意只是多层安全链中的一环。
* UI customization ≠ system policy customization；视觉变化和后台执行规则属于不同责任层。
* App bug ≠ system bottleneck；需要时间线和资源证据才能归因。
* Hardware present ≠ third-party API available；平台可能隐藏、限制、降级或只向系统应用开放能力。
* Closed source ≠ unknowable；可以用公开 API、headers、错误码、工具和行为实验建立受约束结论。

本章结论
--------

移动 OS 的常见误读都来自过早把跨层系统压缩成一个熟悉名词。正确方法是先沿能力路径恢复被省略的服务、策略和硬件边界，再根据证据确定责任层；只有这样，平台比较、性能判断和设备差异才不会停留在表面印象。