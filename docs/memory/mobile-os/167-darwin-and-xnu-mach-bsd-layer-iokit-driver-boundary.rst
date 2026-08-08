第167章：Darwin and XNU Mach, BSD Layer, IOKit, Driver Boundary
================================================================

核心知识点
----------

* Darwin 是 Apple 平台可公开回溯的底层操作系统基础，XNU 是其中的内核；完整 iOS / macOS 还叠加大量闭源 framework、daemon、权限策略与产品级集成。
* XNU 是 hybrid kernel，核心责任可以按 ``Mach + BSD + IOKit`` 理解：Mach 管 task/thread/port/message/VM，BSD 管 process/file/network/POSIX，IOKit 管设备服务与驱动对象。
* Mach task 更接近地址空间与资源容器，Mach thread 是调度执行单元，Mach port/message 构成 Apple IPC 的底层基础，VM 管虚拟内存映射与保护。
* BSD layer 提供 PID、credential、file descriptor、VFS、socket、signal、syscall、POSIX 等 Unix 语义。
* IOKit 提供设备匹配、驱动对象、registry、user client、电源管理等能力；DriverKit 将更多驱动能力移到用户态，提高隔离性和可恢复性。
* App 的一个行为通常同时横跨多套对象模型，例如一次文件保存既涉及 BSD/VFS，也涉及 VM/cache，必要时还会经过 XPC/Mach service 和存储驱动。
* XNU 源码可以解释公开底座，但不能据此推出某个 iOS 私有 daemon、TCC 数据库、媒体服务或硬件 firmware 的完整实现。

关键路径
--------

* 普通容器文件写入可压缩为 ``Foundation → libsystem / POSIX → BSD syscall → VFS / filesystem → VM / buffer cache → IOKit storage → driver / hardware``。
* 需要系统代理的资源访问会分叉：``Framework → XPC / Mach message → system daemon → policy check → BSD / driver``。
* IPC 问题优先看 Mach port/message 和调用双方；文件与网络问题优先看 BSD/VFS/socket；硬件问题再进入 IOKit / DriverKit 与 driver boundary。
* 内存压力问题先区分 Mach/VM 提供的内存机制与完整平台的 Jetsam、进程优先级和生命周期策略。
* 诊断时先定位错误来自 framework、daemon、POSIX errno、filesystem、driver 还是 hardware，再选择对应证据，而不是从“App 失败”直接跳到内核。

概念辨析
--------

* ``Darwin`` 是底层开源基础集合；``XNU`` 是 Darwin 的核心内核，二者不是同义词。
* ``Mach task/thread`` 与 ``BSD process`` 描述同一进程的不同系统视角：前者偏地址空间、调度和 IPC，后者偏 Unix 身份、fd、文件与网络。
* ``IOKit`` 是内核侧设备驱动模型；``DriverKit`` 代表把适合的驱动迁入用户态的现代边界。
* ``POSIX permission``、``sandbox``、``entitlement`` 属于不同检查层，出现 EACCES/EPERM 时不能只看 Unix 文件权限。
* ``XNU 可见源码`` 只覆盖底层机制；``Apple 平台策略`` 仍可能在闭源服务层决定最终行为。

本章结论
--------

理解 Apple 底层时，应把问题放回 Mach、BSD、IOKit 三套责任模型，而不是把 XNU 当成一个无法拆分的黑盒。进程、IPC、VM 看 Mach，文件网络和 Unix 身份看 BSD，设备访问看 IOKit / DriverKit；平台级授权、后台策略和私有服务则继续向 XNU 之上的完整 Apple 系统定位。