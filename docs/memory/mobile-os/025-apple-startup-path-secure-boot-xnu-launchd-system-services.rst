第025章：Apple Startup Path Secure Boot, XNU, launchd, System Services
=====================================================================

核心知识点
----------

* Apple 平台公开可追踪的启动主线是 ``Boot ROM → iBoot / boot stage → XNU → launchd → system daemons → graphical session → SpringBoard / desktop``。
* Boot ROM 是硬件 root of trust，持有 Apple Root CA 相关验证材料；每一级启动组件验证下一阶段，签名或策略失败会进入 Recovery / DFU 等恢复路径。
* iBoot 到 XNU 的交接包含受验证的内核对象、启动参数、设备描述、安全状态和必要 firmware。XNU 接到的是已经经过启动策略筛选的运行上下文。
* XNU 的稳定公开模型由 Mach、BSD、IOKit 等部分组成：Mach 提供 task/thread/VM/port，BSD 提供 process/file/socket/POSIX，IOKit 提供设备匹配、驱动对象和电源管理基础。
* XNU 初始化完成后，``launchd`` 成为用户态服务树根。它注册 socket/port/file descriptor、读取服务描述，并按需或按策略启动 daemon。
* System daemon 持有大量系统能力状态；Framework 通常只是 App 可见入口，真实资源和策略由 daemon、XPC/Mach IPC、entitlement、sandbox 与底层驱动共同执行。
* Entitlement、code signing、sandbox 和用户数据保护不是 UI 层附加规则，而是在启动完成后形成系统服务访问环境的一部分。
* 图形会话准备需要 display/input/window/system UI 等多条路径成立。SpringBoard 或桌面出现，意味着内核、launchd、相关 daemon 和图形服务已经共同达到可交互状态。
* Apple 私有 daemon 名称和内部顺序会随版本变化；稳定读法应关注“谁验证、谁启动、谁持有服务、谁负责图形会话”，而不是死记私有进程清单。

关键路径
--------

安全启动：

::

   power on
   → Boot ROM hardware root
   → verify iBoot / next boot stage
   → verify kernel-related boot objects
   → prepare firmware + boot args + security state
   → enter XNU

用户态启动：

::

   XNU initializes Mach / BSD / IOKit
   → mount required system resources
   → exec launchd as user-space root
   → register service endpoints
   → start / activate system daemons
   → frameworks gain backend services
   → graphical session becomes available

进入主屏：

::

   display and input devices ready
   → window / composition services ready
   → user session and system UI services ready
   → SpringBoard / desktop process presents interface
   → input routed to visible UI

概念辨析
--------

* **Boot ROM 与 iBoot**：Boot ROM 是不可变硬件信任起点，iBoot 属于后续受验证的启动控制阶段，承担更丰富的镜像与策略处理。
* **XNU 与 macOS/iOS 整体**：XNU 是内核，不等于完整 Apple OS；framework、daemon、launchd、sandbox、UI 服务都位于内核之上。
* **Mach port 与 XPC**：Mach port 是更底层的 IPC 能力基础，XPC 是面向服务通信的更高层系统模型。
* **launchd 与普通 daemon**：launchd 是用户态服务树根和服务激活管理者，普通 daemon 是由它管理的能力实现进程。
* **Framework 与 service ownership**：Framework 暴露稳定 API，资源所有权和策略执行通常位于系统 daemon 与底层设备路径中。

本章结论
--------

Apple 启动应按“安全启动链 → XNU 资源环境 → launchd 服务树 → system daemon → 图形会话”阅读。看到恢复模式、卡启动标志、服务不可用或主屏未出现时，应先判断故障属于签名链、内核/驱动、用户态服务根、daemon backend 还是图形会话，而不是依赖版本敏感的私有进程名称。