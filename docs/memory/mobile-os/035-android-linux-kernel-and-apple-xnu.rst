第035章：Android Linux Kernel and Apple XNU
===========================================

核心知识点
----------

* Android 与 Apple 的上层 API、IPC、Driver 与生态控制差异很大，但 Kernel 都承担进程、线程、虚拟内存、文件、网络、设备、调度、电源和安全执行等底层职责。
* Android 典型能力路径是 ``Framework API → Binder → System/Native Service → HAL → Linux Kernel → Vendor Driver → Hardware``。
* Android Kernel 以 Linux LTS/ACK 为基础，并通过 GKI、KMI 与 vendor module 边界分离通用 Kernel 和设备相关驱动，降低平台升级与硬件适配耦合。
* Binder driver 负责 transaction、对象引用、线程唤醒和调用者身份传递；SELinux 执行 MAC；cgroup/task profile 与 scheduler 负责资源分配；power management 负责 suspend、runtime PM、frequency 和 thermal 原语。
* HAL 是 Android Framework 与 vendor implementation 之间的标准能力接口。App 的硬件请求先经过 Service policy，再进入 HAL 与 Kernel/Driver，而不是直接访问设备。
* Apple XNU 由 Mach、BSD、IOKit 等组件共同形成 Kernel environment：Mach 负责 task/thread/VM/port/IPC，BSD 负责 process/fd/VFS/socket/POSIX，IOKit/DriverKit 负责设备模型和 Driver 边界。
* Apple 典型能力路径可抽象为 ``Framework API → XPC/System Daemon → XNU → IOKit/DriverKit → Hardware``；具体移动平台私有 daemon 名称和内部协议不应当作稳定架构前提。
* Mach port right 是 Apple IPC 能力模型的重要基础；XPC 是更高层服务封装。BSD fd/socket 与 Mach port 可以同时存在于同一系统路径中。
* Android 更显式暴露 AOSP、HAL、VINTF、vendor partition、GKI/vendor module 等多厂商边界；Apple 以软硬件垂直整合和 Framework/entitlement/sandbox 形成更集中控制面。
* 跨平台比较应按“架构角色”映射，而不是机械寻找同名组件：Binder 与 XPC、Linux fd 与 Mach port、HAL 与 Apple daemon/driver boundary 并非一一同构，但解决相似的身份传递、能力代理和资源访问问题。

关键路径
--------

Android 相机请求：

::

   App Camera API
   → Binder transaction
   → Camera/System Service policy
   → HAL session
   → ioctl / mmap / dma-buf / fence
   → Linux Kernel + vendor driver
   → camera hardware
   → frame result returns upward

Apple 相机请求：

::

   App framework
   → privacy / entitlement policy
   → XPC or system IPC
   → capability daemon
   → XNU resource objects
   → IOKit / DriverKit boundary
   → hardware
   → framework callback

概念辨析
--------

* **Linux Kernel 与 Android OS**：Android Kernel 是底层资源层；Android OS 还包含 AOSP Framework、System Service、ART、HAL、系统应用与平台策略。
* **XNU 与 iOS/iPadOS**：XNU 是 Kernel；完整 Apple 移动平台还包含 launchd、daemon、Framework、Sandbox、entitlement 与应用模型。
* **Binder 与 XPC**：两者都是上层 IPC 体系，但 Binder 有专门的 Linux binder driver 与对象模型；XPC 构建在 Apple IPC/daemon 体系之上，底层与 Mach 权利模型密切相关。
* **HAL 与 Driver**：HAL 是用户态硬件抽象接口，Driver 负责更底层设备控制；二者不应混为同一层。
* **开放生态与一体化生态**：这是供应链与平台控制模型差异，不改变 Kernel 必须完成隔离、调度、设备和内存管理的基本职责。

本章结论
--------

比较 Android Linux 与 Apple XNU 时，最稳定的方法是先对齐角色：谁承载 App、谁代理系统能力、谁传递 IPC 身份、谁拥有 Kernel object、谁控制 Driver 和硬件。Android 更适合沿 Binder/HAL/vendor boundary 追踪，Apple 更适合沿 Framework/XPC-daemon/XNU/IOKit 追踪；名称不同，底层资源与安全问题具有共同结构。