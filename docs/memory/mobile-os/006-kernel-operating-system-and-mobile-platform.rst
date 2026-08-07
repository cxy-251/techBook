第006章：Kernel, Operating System, and Mobile Platform
=====================================================

核心知识点
----------

* Kernel、Operating System、Mobile Platform 是三个不同层级。Kernel 管理底层资源，OS 把 kernel、service、runtime、framework 和 policy 组合成完整系统，Mobile Platform 再叠加 app model、签名、分发、SDK 和生态规则。
* Kernel 的核心职责是 CPU 调度、虚拟内存、进程隔离、文件、网络、设备、中断、同步和电源管理。它提供移动平台能够运行的底层执行基础。
* Kernel 不直接决定绝大多数用户可见平台策略。相机权限弹窗、后台运行限制、通知策略和应用审核都发生在 kernel 之上。
* Operating System 的 system service / daemon 负责资源状态、身份、权限、生命周期、并发访问和错误恢复，是把底层资源转换为平台行为的关键层。
* Runtime 负责 App 代码如何装载和执行。Android 典型包含 Zygote、ART、DEX、class loader、JNI；Apple 典型包含 dyld、Swift/Objective-C runtime、Mach-O 和 native ABI。
* Framework 决定开发者看到什么 API、对象、callback 和错误模型。它是稳定公开表面，不等于能力的真实所有者。
* System Policy 把 privacy、power、thermal、lifecycle、background、enterprise management 等条件叠加到能力请求上。
* Mobile Platform 进一步约束 App 如何被签名、安装、更新、分发，哪些 API 对第三方开放，哪些能力需要 entitlement、特殊声明或审核。
* Android 的平台结构应理解为 Linux kernel 之上的 HAL、Binder、ART、system services、Framework、permission、SELinux、signing 和 distribution model。
* Apple 平台应理解为 XNU 之上的 frameworks、runtime、XPC/Mach IPC、system daemons、entitlements、sandbox、code signing 与 distribution policy。
* “Android 是 Linux”或“iOS 是 XNU”只说明 kernel lineage，不能解释完整移动平台行为。
* 排查问题时先判断属于 kernel resource、OS policy/service，还是 platform distribution/app-model；三个层级混在一起会导致错误归因。

关键路径
--------

层级关系：

::

   hardware
   → kernel resource control
   → OS services / runtime / frameworks / policy
   → mobile app model / signing / distribution / ecosystem rules
   → third-party app behavior

一次相机请求：

::

   app framework call
   → OS service checks permission and ownership
   → OS policy applies lifecycle / thermal constraints
   → kernel schedules threads and controls device resources
   → hardware produces frames
   → framework returns app-visible result

问题归因：

::

   symptom
   → kernel resource problem?
   → service / policy problem?
   → runtime / framework problem?
   → platform signing / entitlement / distribution problem?
   → identify responsible layer

概念辨析
--------

* **Kernel 与 OS**：Kernel 是 OS 的底层核心，但完整 OS 还包含服务、运行时、框架、安全与系统策略。
* **OS 与 Mobile Platform**：OS 解决设备运行和系统能力；Mobile Platform 还定义第三方 App 的开发、签名、分发和生态边界。
* **Kernel lineage 与 platform identity**：Android 使用 Linux、Apple 使用 XNU；真正决定 App 边界的是 kernel 之上的平台架构。
* **Framework API 与 OS implementation**：Framework 是公开契约，内部 service、daemon、HAL 和 driver 负责实现能力。
* **System policy 与 hardware limitation**：系统可能主动限制一个硬件本来可以完成的动作，这属于平台策略而不是硬件缺陷。

本章结论
--------

Kernel 提供底层资源原语，Operating System 把这些原语组织成可授权、可调度、可恢复的系统能力，Mobile Platform 再决定第三方 App 如何进入这套能力体系。理解移动系统时必须区分这三个层级，不能用 kernel 来源替代对 service、runtime、policy、signature 和 distribution 的分析。