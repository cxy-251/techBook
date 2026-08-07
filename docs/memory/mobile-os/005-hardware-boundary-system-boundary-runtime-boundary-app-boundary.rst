第005章：Hardware Boundary, System Boundary, Runtime Boundary, App Boundary
=========================================================================

核心知识点
----------

* 移动 OS 的能力路径会连续跨越 hardware、vendor、system、runtime 和 app boundary。边界的作用是分配资源所有权、策略执行权、故障隔离和兼容性责任。
* Hardware Boundary 位于 device、firmware、driver 和 kernel interface 之间。它负责设备发现、寄存器/firmware 控制、DMA、buffer、中断、电源状态和底层错误信号。
* Vendor Boundary 隔离 SoC/vendor/OEM 实现与平台系统。Android 常通过 HAL、vendor image、firmware、VINTF 和稳定接口维持 system/vendor 可独立演进；Apple 的硬件与系统整合更集中，但 driver framework、firmware 和签名能力仍形成边界。
* System Boundary 位于 App 与 system service/daemon 之间。IPC 把调用者身份和请求送到可信能力所有者，由服务执行 permission、lifecycle、resource ownership、privacy 和 policy 判断。
* Runtime Boundary 位于应用进程内部的 loader、VM/runtime、native code 与系统调用/IPC 入口之间。Android 典型涉及 Zygote、ART、class loader、JNI、native library；Apple 典型涉及 dyld、Swift/Objective-C runtime、Mach-O 和 native ABI。
* App Boundary 由 sandbox、container、identity、permission、entitlement 和 code signing 共同形成。它决定一个第三方 App 默认能看到哪些文件、IPC endpoint、设备能力和其他应用数据。
* 一次相机黑屏可能分别来自不同边界：权限拒绝属于 system/app policy，stream configuration 失败可能属于 vendor boundary，sensor 不出帧属于 hardware boundary，App callback thread 阻塞属于 runtime boundary。
* 边界并不是单纯的软件分层图，而是责任合同。每个边界都应能回答：谁输入、谁输出、谁验证、谁拥有状态、失败如何回收。
* IPC 连接断开是重要的故障隔离信号。App crash 后 system service 应识别 client death，释放 session；service restart 后 App 持有的旧 handle/token 可能失效。
* Runtime 错误与系统策略错误要分开：类加载失败、native ABI 不匹配、JNI crash 属于进程执行环境；permission denied、background restriction 属于系统能力边界。
* App 身份不是进程 PID。移动系统会把 package/bundle identity、UID、signature、entitlement、user profile 和 permission state 作为长期安全主体。
* 跨版本稳定性取决于边界是否清晰：Framework API、IPC interface、HAL/vendor interface、ABI、signature policy 都是平台升级需要维护的契约。

关键路径
--------

边界定位：

::

   app-visible symptom
   → app boundary: identity / sandbox / permission?
   → runtime boundary: loader / VM / native execution?
   → system boundary: service / IPC / policy / ownership?
   → vendor boundary: HAL / firmware / board support?
   → hardware boundary: driver / DMA / interrupt / device?

相机能力路径：

::

   app process
   → public framework
   → IPC
   → system service / daemon
   → HAL / driver framework
   → kernel driver
   → firmware / sensor / ISP
   → buffer and status return

故障回收：

::

   client or service failure
   → IPC connection invalidated
   → ownership records removed
   → buffers / handles released
   → HAL / driver session closed
   → app receives disconnect or relaunches

概念辨析
--------

* **Layer 与 boundary**：Layer 表示结构位置，boundary 强调跨层时的身份、接口、责任和失败合同。
* **Vendor boundary 与 hardware boundary**：前者关注平台与厂商实现的兼容契约，后者关注 driver/firmware/device 的真实控制路径。
* **System boundary 与 runtime boundary**：前者跨进程进入可信系统服务，后者主要发生在 App 自身进程的代码装载和执行环境。
* **App sandbox 与 process isolation**：进程地址空间隔离是 kernel 基础，App sandbox 还叠加文件、IPC、能力和数据访问规则。
* **PID 与 app identity**：PID 是一次进程实例，应用身份跨进程重启长期存在并用于权限与数据所有权判断。

本章结论
--------

理解移动 OS 应优先识别边界，而不是只记组件名称。Hardware、vendor、system、runtime 和 app boundary 分别承担设备控制、厂商兼容、能力代理、代码执行和应用隔离；出现问题时沿边界寻找第一个责任合同失效的位置，才能把同一个“打不开、卡顿、崩溃”准确归到不同系统层。