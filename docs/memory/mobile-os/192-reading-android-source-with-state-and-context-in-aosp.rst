第192章：Reading Android Source with State and Context in AOSP
=============================================================

核心知识点
----------

* AOSP 阅读应从“一个能力请求”开始，而不是从目录遍历开始；先固定 App 行为，再沿状态对象和跨层边界追踪。
* 常用目录只提供线索：``frameworks/base`` 多为 Framework API 与 Java system service，``frameworks/native`` / ``frameworks/av`` 多为 native service、图形与媒体，``hardware/interfaces`` 定义 HAL 接口，``system/core`` 提供系统基础设施，vendor / device / kernel 方向进入设备实现。
* 从 Framework API 反向找服务时，优先建立 ``Manager Class → Service Name → Binder Interface → Service Implementation`` 四元组。
* AIDL 是 Binder 协议边界；阅读时同时追踪请求 interface 与 callback interface，记录 caller identity、资源 id、policy input、callback binder 和 death handling。
* ``system_server`` 中的服务重点看启动注册、持有状态、权限检查、Handler / Binder 线程、锁、watchdog 与下游依赖；不能假设所有 Android 能力都由 ``system_server`` 直接实现。
* Native Service 到 HAL 的路径通常经过 ServiceManager、AIDL/HIDL interface、provider 或 vendor service；HAL 接口是 Framework / system 与 vendor 实现之间的稳定边界。
* HAL 之后进入 vendor library、device node、sysfs、ioctl、driver log、kernel trace 等范围；AOSP 通常只能完整解释到公开 interface，具体 OEM 实现要结合设备源码和运行证据。
* 源码结论必须绑定 Android 版本、branch、设备、SoC、GMS / OEM 环境；同名 API 在不同版本和设备上可能拥有不同后端路径。

关键路径
--------

* 标准源码阅读：``App API → Manager Class → Context / Service Registry → Binder Proxy / AIDL → Service Registration → Service Implementation → HAL Interface → Vendor Implementation → Kernel Boundary``。
* Camera 示例：``CameraManager.openCamera → ICameraService → native CameraService → Camera Provider / HAL → vendor camera stack → driver / ISP / sensor``。
* Java service：``Context.getSystemService → Manager → AIDL Proxy → Binder Driver → system_server Service Stub → permission / state check → downstream component``。
* Native service：``Framework client → Binder native interface → ServiceManager → native daemon → AIDL/HIDL HAL → vendor service``。
* 证据链：``source search → service registration → interface definition → implementation → runtime log / dumpsys / trace → device-specific boundary``。

概念辨析
--------

* 目录位置 ≠ 责任所有者：同一能力可能跨 ``frameworks/base``、``frameworks/av``、HAL 和 vendor；要以 service registration 和状态持有者为准。
* Manager Class ≠ System Service：Manager 是 App 侧代理，真正服务可能位于 ``system_server`` 或独立 native daemon。
* AIDL interface ≠ 业务实现：AIDL 固定跨进程协议，策略和状态在服务实现中。
* AOSP source ≠ 具体手机完整源码：OEM HAL、firmware、vendor daemon、GMS 和区域策略可能不在 AOSP。
* Call graph ≠ Runtime truth：源码路径还要用日志、trace、错误码和设备状态验证真实执行分支。

本章结论
--------

阅读 AOSP 的稳定方法是围绕能力、状态和边界推进：从公开 API 找 manager，再找 Binder interface、服务所有者、HAL 与 vendor / kernel 边界，并用运行证据验证。源码规模本身不是问题，缺少明确追踪对象才会让阅读失控。