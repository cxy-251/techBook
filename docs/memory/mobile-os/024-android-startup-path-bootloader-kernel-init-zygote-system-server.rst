第024章：Android Startup Path Bootloader, Kernel, init, Zygote, system_server
===========================================================================

核心知识点
----------

* Android 正常启动主线是 ``Bootloader → Linux Kernel → first-stage init → second-stage init → Zygote → system_server → Launcher``。
* Bootloader 负责验证并加载 kernel、ramdisk、device tree/bootconfig，并把 slot、Verified Boot state、启动模式和硬件描述交给内核。
* Kernel 接管后建立调度、内存、VFS、中断、设备和安全基础；driver probe 把硬件描述转换成 block device、input device、binder device、sysfs/uevent 等可用对象。
* first-stage init 负责最早期挂载和运行环境准备；second-stage init 进入完整 Android init 逻辑，解析 rc、启动 property service、ueventd 和 native daemon。
* ``init.rc`` 的本质是启动图和服务生命周期配置。Action、trigger、service、class、socket、user/group、SELinux label 与 restart policy 共同决定 daemon 何时出现和如何恢复。
* SELinux policy、property contexts、service contexts 在启动期建立访问控制环境。服务进程存在不等于服务可用，它还必须拥有访问设备、文件、Binder service 和 property 的正确权限。
* Zygote 是 ART/Java 世界的进程模板。它由 init 启动，预加载共享类和资源，监听 zygote socket，并 fork App 进程与 ``system_server``。
* ``system_server`` 承载 Framework 背后的大量核心 System Service；Activity、Package、Window、Power、Location 等能力只有在相应服务注册并 ready 后才真正对上层可用。
* Launcher 首屏可交互不是单个进程启动完成的结果，而是 kernel、init、native daemon、Zygote、system_server、Window/Input/Package 等多条依赖链共同进入 ready 状态的结果。
* “卡开机动画”“桌面空白”“某服务缺失”应分别映射到 kernel/driver、init/native service、Zygote/system_server 或 Launcher/Window/Input 阶段，而不是统一称为启动慢。

关键路径
--------

正常启动：

::

   bootloader verifies and loads boot objects
   → Linux kernel entry
   → scheduler / memory / VFS / driver probe
   → PID 1 first-stage init
   → mount required partitions
   → second-stage init parses rc and starts native daemons
   → start Zygote
   → Zygote starts system_server
   → system_server registers core services
   → Activity/Window/Package stack starts Launcher
   → first interactive frame

服务启动：

::

   init trigger / property change
   → service definition matched
   → create process + socket + credentials
   → SELinux domain transition
   → daemon registers Binder/socket endpoint
   → framework client can use capability

用户可交互：

::

   system services ready
   → package/user state loaded
   → WindowManager and display ready
   → input pipeline ready
   → Launcher process started
   → window attached and frame presented
   → touch routed to Launcher

概念辨析
--------

* **Kernel ready 与 Android ready**：Kernel 能运行 PID 1 只说明底层资源环境成立，Framework 和用户界面仍未建立。
* **init 与 system_server**：init 是用户态根进程和 native service 管理者；system_server 是 Java Framework 核心服务容器。
* **Zygote 与 App process**：Zygote 是预热进程模板，普通 App 进程由它 fork 后再进入各自 UID、SELinux domain 和应用代码。
* **Service process 与 Binder service**：进程存在不等于服务已经注册；Binder endpoint、权限环境和依赖状态都必须准备完成。
* **Boot completed 与首屏可见**：系统可见桌面、系统广播 boot completed、后台服务全部稳定并不是同一时间点。

本章结论
--------

Android 启动是一条从可信 boot image 到可交互 Framework 的逐层建设过程。排查时应沿 Bootloader、Kernel/driver、init/rc、SELinux/property、Zygote、system_server、Launcher 逐级确认“上一层交付了什么、下一层是否真的 ready”，这样才能把启动失败定位到具体责任边界。