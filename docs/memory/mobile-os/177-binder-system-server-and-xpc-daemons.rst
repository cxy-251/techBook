第177章：Binder system_server and XPC Daemons
==============================================

核心知识点
----------

* 移动 OS 把敏感能力和全局资源放在 App 进程之外，Framework API 只是客户端入口，真正的状态所有权和策略执行位于系统服务。
* Android 的 Binder 是系统服务 IPC 主干：proxy / stub、transaction、Binder driver、线程池、caller UID/PID、对象引用和 death notification 共同构成调用模型。
* 同步 Binder 调用会把调用方等待时间与服务端执行绑定；服务线程池拥塞、锁竞争和下游硬件延迟都可能反向表现为 App 卡顿或 ANR。
* ``system_server`` 集中承载大量 Java system service，便于共享 package、process、window、power、permission 等全局状态，也形成更大的共享故障域。
* SurfaceFlinger、AudioFlinger、CameraService 等 native service 常以独立 native 进程存在，用 Binder / ServiceManager 暴露能力。
* Apple 以 Mach port、XPC、launchd、daemon / agent / XPC service 组织系统服务访问；launchd 可以按需激活服务，XPC connection 负责 message、reply、interruption 与 invalidation。
* Apple 服务入口常结合 audit token、code signing identity、entitlement、TCC 与 sandbox 判断调用资格；具体 iOS 私有 daemon 名称和内部协议不是稳定公开契约。
* Android 更容易沿 Binder transaction 和 service map 追踪公开路径；Apple 更多依赖 public API 行为、系统日志、Instruments / sysdiagnose 和服务边界推断。

关键路径
--------

::

   Android:
   App → Framework Proxy → Binder Driver
       → system_server / Native Service
       → Permission / AppOps / Resource Arbitration
       → HAL / Driver / Hardware
       → Binder Callback / Result

   Apple:
   App → Public Framework → XPC / Mach Service
       → launchd-resolved Daemon
       → Entitlement / TCC / Sandbox Check
       → Driver / Hardware or Protected Resource
       → Reply / Callback

遇到远程调用失败时，先区分“IPC 没到达”“服务拒绝”“服务等待下游”“服务死亡”四种状态。

概念辨析
--------

* ``Binder`` 与 ``system_server`` 不是同一概念：Binder 是 IPC 机制，system_server 是大量 Java service 的宿主进程。
* ``XPC`` 与 ``daemon`` 也不是同一概念：XPC 是通信模型，daemon 是能力后端进程；launchd 负责服务生命周期和发现。
* ``同步 IPC`` 不等于本地函数调用：远端线程调度、锁、服务重启和下游硬件都进入延迟预算。
* ``进程拆分`` 不自动代表更高性能；它主要改变隔离、权限边界、恢复方式和可观测性。

本章结论
--------

Android 用 Binder 把 framework、system_server、native service 和 HAL 串成可追踪的服务主干；Apple 用 XPC / Mach + launchd + daemon 把系统能力拆成受控服务。两者都把调用者身份带到服务入口，并在服务侧完成权限和资源仲裁，差异主要在服务布局、故障域和可观测方式。