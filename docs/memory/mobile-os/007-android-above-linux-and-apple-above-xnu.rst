第007章：Android Above Linux and Apple Above XNU
================================================

核心知识点
----------

* “Android 基于 Linux”“Apple 基于 XNU”描述的是 kernel lineage，不等于完整移动平台架构。App 实际面对的权限、生命周期、服务、运行时和分发规则都位于 kernel 之上。
* Linux 为 Android 提供进程、线程、虚拟内存、文件系统、网络、driver、cgroup、SELinux hook 等底层机制；Android 再叠加 HAL、Binder、ART、system services、Framework 和 App policy。
* XNU 由 Mach、BSD、I/O Kit 等体系构成，为 Apple 平台提供调度、虚拟内存、进程、文件、网络、IPC 和驱动基础；Apple 再叠加 frameworks、runtime、system daemons、XPC、entitlements、sandbox 和 code signing。
* Android 的架构重点之一是多厂商硬件生态上的稳定边界。HAL、Treble、AIDL 等机制让 framework/system 与 vendor implementation 尽量解耦。
* Binder 是 Android 的核心跨进程骨架。App Framework 代理、``system_server``、native service 和部分 HAL service 通过 Binder/AIDL 形成能力调用链。
* ART 是 Android App 的 managed runtime，和 Zygote、DEX、AOT/JIT、GC、JNI 共同决定应用代码如何在 Linux 进程内执行。
* ``system_server`` 承载大量 Java Framework system services；native service 负责图形、媒体、相机等部分系统能力。服务层比 kernel 更直接决定 App 的平台行为。
* Apple 平台通过 public Framework 向 App 暴露能力，Framework 背后通常由 system daemon 持有状态，并使用 XPC、Mach IPC 或其他系统机制通信。
* Entitlement 是签名二进制的能力声明，sandbox 是运行时访问限制，TCC 类隐私授权是用户敏感资源控制；这些机制和 XNU kernel 权限共同形成多层安全边界。
* ``launchd`` 体现 Apple 系统服务生命周期管理思想：daemon 可由系统注册、按需启动并持有特权能力；App 不直接拥有底层服务资源。
* Android 与 Apple 都必须解决 capability mediation、resource arbitration、app isolation、runtime startup、power management 和 privacy，只是责任边界与公开接口不同。
* 不应把平台差异写成“开放 vs 封闭”的评价，应比较同一架构角色在两套系统中的实现位置和控制方式。

关键路径
--------

Android：

::

   App
   → Java/Kotlin Framework API
   → Binder / AIDL
   → system_server or native service
   → permission / AppOps / lifecycle policy
   → HAL / vendor service
   → Linux kernel / driver
   → hardware

Apple：

::

   App
   → public Framework
   → XPC / Mach IPC / system service boundary
   → daemon + entitlement / sandbox / privacy policy
   → XNU / driver framework
   → hardware

跨平台阅读：

::

   identify app-visible capability
   → identify public framework
   → identify IPC boundary
   → identify capability owner
   → identify policy checks
   → identify driver / kernel boundary
   → compare equivalent roles, not names

概念辨析
--------

* **Android 与 Linux**：Android 使用 Linux kernel，但 Android Framework、Binder 服务体系、ART、HAL 和应用模型才构成 Android 平台主体。
* **Apple Platform 与 XNU**：XNU 是底层 kernel，iOS/iPadOS 的 framework、daemon、entitlement、sandbox 和 distribution policy 位于其上。
* **Binder 与 XPC**：两者都服务跨进程能力调用，但对象模型、接口生态和平台组织方式不同。
* **SELinux 与 sandbox/entitlement**：都属于平台安全控制的一部分，不能简单一一对应；应按“谁能访问什么资源、在哪个边界检查”比较。
* **开放生态与垂直整合**：这是厂商/系统组织方式差异，不应替代对 HAL、service、driver、signing 等具体机制的分析。

本章结论
--------

Linux 与 XNU 解释的是两套平台底层资源模型的来源，Android 与 Apple 的移动平台身份则主要形成于 kernel 之上的 IPC、system service、runtime、hardware abstraction、安全策略和应用分发体系。跨平台比较应以相同责任角色为坐标，而不是只比较名词或 kernel 血统。