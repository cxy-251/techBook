第176章：Linux Kernel + HAL and XNU + Apple-Controlled Driver Framework
=======================================================================

核心知识点
----------

* Android 的底层建立在 Linux kernel 之上；进程、线程、虚拟内存、文件系统、网络、设备驱动、SELinux、DMA 与中断等通用资源模型最终承接 framework 和 HAL 的请求。
* Android 用 HAL 把 framework / system side 与 vendor hardware implementation 分开。现代 HAL 主要通过 AIDL，历史上还存在 HIDL；VINTF 用 manifest / compatibility matrix 约束双方可组合关系。
* GKI / KMI 进一步把通用 Android kernel 与 vendor module 边界稳定化，降低 kernel fragmentation 和设备升级时的耦合。
* Apple 使用 XNU 作为内核基础：Mach 负责 task、thread、VM、message 等低层抽象；BSD 提供 process、VFS、socket、POSIX；IOKit / DriverKit 组织设备服务与驱动边界。
* Apple 的公开 framework、系统 daemon、XNU、驱动框架和自有硬件处于一条集中控制链；iPhone 内置硬件的具体 driver / firmware / ISP 路径大量属于私有实现。
* Android 的关键边界是 ``platform ↔ vendor``；Apple 的关键边界更接近 ``public API ↔ Apple-controlled implementation``。
* 两个平台都不会让普通 App 直接控制硬件寄存器；App 获得的是经过身份、权限、资源仲裁和设备能力裁剪后的系统能力。

关键路径
--------

::

   Android:
   App → Framework API → Binder / System Service
       → HAL Interface → Vendor Implementation
       → Linux Driver → Hardware

   Apple:
   App → Public Framework → XPC / System Daemon
       → XNU / Apple Driver Boundary → Hardware

   Hardware result → Driver / HAL or Daemon → Framework callback → App

相机黑屏、音频无声、传感器无数据时，应先从 API / service 向下定位，再判断是接口契约、vendor 实现、driver、firmware 还是硬件问题。

概念辨析
--------

* ``Linux kernel`` 不等于完整 Android：Android 还包括 Binder、system service、ART、HAL、vendor、权限与应用框架。
* ``XNU`` 不等于完整 iOS：iOS 还包含大量私有 daemon、framework、TCC、sandbox、媒体和图形系统。
* ``HAL`` 是稳定硬件接口边界，不是硬件驱动本身；HAL 下方仍可能存在 vendor library、firmware 和 kernel driver。
* ``接口稳定`` 不等于 ``体验一致``：相同 HAL 契约下，硬件规格、算法、调校、热策略和实现质量仍可明显不同。

本章结论
--------

Android 通过 Linux + HAL / VINTF / GKI 把平台和厂商硬件解耦；Apple 通过 XNU + 自控驱动与服务链把硬件能力集中管理。两者差异最终体现为设备适配方式、更新责任、调试入口、兼容成本和长期维护模型。