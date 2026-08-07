第002章：The Core System Chain Hardware, Kernel, Driver, Service, Framework, App
==============================================================================

核心知识点
----------

* 移动系统能力可以统一理解为一条责任链：``Hardware → Kernel → Driver → HAL / Driver Framework → System Service → Framework API → App``。不同平台名词不同，责任角色相似。
* Hardware 是能力源头。CPU、GPU、NPU、ISP、modem、sensor、secure element 等提供物理能力，但硬件存在不等于 App 自动获得使用权。
* Kernel 对 CPU 时间、虚拟内存、进程隔离、文件描述符、网络栈、设备对象、中断、DMA 和电源状态拥有底层控制权。
* Driver 把寄存器、总线、firmware command、interrupt、DMA queue 等设备细节包装成 kernel 可管理的控制接口和事件。
* HAL 或 Driver Framework 的核心作用是形成 vendor boundary：上层系统面对稳定能力接口，厂商实现隐藏在接口之后，便于设备适配和系统升级。
* System Service / daemon 是能力代理和资源所有者。它维护设备状态、调用者身份、权限、并发会话、生命周期、错误恢复和策略仲裁。
* Framework API 是公开能力表面。它把底层复杂状态转换为对象、方法、callback、error code 和生命周期事件，让 App 表达“想做什么”，而不是“如何操作硬件”。
* IPC 把 App 和能力所有者连接起来。Android 典型使用 Binder/AIDL；Apple 平台常见 Framework + XPC / Mach IPC + daemon 的组合。
* 请求路径和返回路径同样重要。成功结果、permission denied、device busy、unsupported configuration、timeout、preemption、thermal downgrade 都必须逐层翻译回 App。
* Android 典型链路可读作 ``App → Framework → Binder → system/native service → HAL → Linux driver/kernel → hardware``。
* Apple 典型链路可读作 ``App → public Framework → IPC / daemon → entitlement / policy → XNU / driver framework → hardware``；私有 daemon 细节不应当成稳定架构事实记忆。
* 故障定位应按边界判断：授权失败看 service/policy，设备忙看资源仲裁，stream 配置失败看 HAL/vendor，硬件超时看 driver/firmware，卡顿再结合 buffer、scheduler、GPU/display 和 power state。

关键路径
--------

能力请求：

::

   app intent
   → framework API
   → IPC with caller identity
   → system service / daemon
   → permission + lifecycle + ownership checks
   → HAL / driver framework
   → kernel driver
   → hardware

返回路径：

::

   hardware result / error
   → driver event / buffer / status
   → HAL normalized result
   → service policy translation
   → IPC callback / exception
   → framework object
   → app-visible state

资源释放：

::

   app exits / crashes / loses priority
   → IPC client death or session close
   → service revokes ownership
   → HAL closes stream
   → driver releases buffers and device state
   → power domain may idle

概念辨析
--------

* **Hardware capability 与 system capability**：前者是物理设备能做什么，后者是系统经过抽象和策略后愿意开放什么。
* **Kernel ownership 与 service ownership**：kernel 持有底层资源控制权，system service 持有平台层的逻辑会话和策略状态。
* **Driver 与 HAL**：driver 面向 kernel 和具体硬件协议；HAL 面向平台稳定接口和厂商实现边界。
* **Framework 与 system service**：Framework 是 App 使用的公开表面，service 才通常是真正执行权限、仲裁和状态管理的能力所有者。
* **API 调用与本地函数调用**：高层看似普通方法调用，常会很快跨越 IPC 边界进入另一个进程。

本章结论
--------

移动 OS 的能力不是从 App 直接落到硬件，而是经过一条分层责任链。硬件提供原始能力，kernel 和 driver 建立可执行控制面，HAL 隔离厂商差异，system service 负责授权与仲裁，Framework 提供稳定 API，IPC 连接各进程。定位系统问题时，应沿这条链寻找第一个发生拒绝、降级、超时或状态失真的边界。