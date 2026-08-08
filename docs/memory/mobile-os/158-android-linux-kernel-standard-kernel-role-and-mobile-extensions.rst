第158章：Android Linux Kernel Standard Kernel Role and Mobile Extensions
========================================================================

核心知识点
----------

* Android Kernel 的第一身份是 Linux Kernel。进程、线程、调度、虚拟内存、VFS、socket、网络协议栈、中断、DMA、设备驱动、timer、CPU idle 和 frequency scaling 都来自 Linux 基础。
* Android 在 Linux 资源模型上增加移动平台需要的 Binder IPC、安全隔离、cgroup 资源控制、电源管理、热管理、GKI / vendor module 等工程约束。
* App、Java Thread、Kotlin coroutine 最终都落成 Linux task/thread，由内核调度器决定何时运行、运行在哪个 CPU、获得多少时间片。
* 内存管理负责地址空间、页表、匿名页、文件映射、页缓存、回收和压力统计；现代 Android 常由 userspace ``lmkd`` 结合进程优先级和 PSI 等信号实施低内存回收。
* 文件和网络最终回到 Linux fd 模型：普通文件、socket、pipe、eventfd、epoll、Binder fd、设备节点都通过文件描述符进入内核资源体系。
* Binder driver 是 Android IPC 的内核基础，维护 binder node/ref、transaction、buffer、等待队列和线程唤醒，并把调用身份带到服务端。
* UID 提供基础 DAC 隔离；SELinux 提供强制访问控制。Framework runtime permission 通过，不代表 SELinux、设备节点或服务策略必然允许访问。
* cgroup / task profile 把进程和线程归入不同资源组，用于 CPU、内存、调度和后台资源控制；Framework 的进程重要性最终要在内核资源层落实。
* namespace、mount、credential 与 SELinux 共同构成 App、system service、vendor process 的隔离基础。
* Android 电源路径围绕 suspend、wakeup source、WakeLock、CPU idle/frequency 和 thermal feedback 展开。频繁 wakeup 会破坏深度低功耗驻留。
* GKI 将通用 kernel core 与 vendor module 分离，KMI 约束模块与内核的接口，目标是降低 Android 平台升级与厂商驱动之间的耦合。
* Camera、display、audio、sensor、modem 等硬件最终都要进入具体 driver / vendor module；同一上层 API 的设备差异常在 HAL、driver、firmware 和硬件层出现。

关键路径
--------

::

   App / Framework request
   → Binder / system service
   → HAL / vendor process
   → Linux syscall / Binder driver / device fd
   → scheduler / memory / SELinux / cgroup checks
   → device driver / vendor module
   → interrupt / DMA / hardware
   → event or buffer returned upward

概念辨析
--------

* **Android Kernel 与 Android OS**：Kernel 提供底层资源与驱动基础，完整 Android 还包括 Framework、system service、runtime、HAL、应用模型和平台策略。
* **Linux UID 与 Android Permission**：UID 是内核身份基础，Android permission 是更高层授权模型，二者共同参与安全判断。
* **SELinux 与 runtime permission**：runtime permission 面向用户授权；SELinux 面向进程 domain 与系统对象之间的强制访问控制。
* **WakeLock 与后台执行权**：WakeLock 只影响执行窗口内的唤醒保持，不能绕过 Doze、后台配额、权限或网络策略。
* **GKI 与 Vendor Module**：GKI 提供通用内核核心，vendor module 承载设备相关实现；KMI 是二者的接口约束。

本章结论
--------

Android Kernel 应同时用两张图阅读：一张是 Linux 的 ``task / mm / fd / socket / driver`` 资源图，一张是 Android 的 ``App / Binder / Service / HAL / Vendor`` 服务图。复杂问题通常发生在两张图的接缝处。