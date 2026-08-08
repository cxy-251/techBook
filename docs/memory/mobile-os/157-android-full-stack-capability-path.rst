第157章：Android Full Stack Capability Path
===========================================

核心知识点
----------

* Android 一项系统能力的稳定主链是 ``App → Framework API → Binder → System / Native Service → Policy → HAL → Vendor Implementation → Kernel Driver → Hardware``。
* App 层首先由包名、UID、进程、组件、用户、生命周期和授权状态确定调用身份；系统服务判断的是“谁在什么状态下请求什么能力”。
* Framework API 是公开能力表面。Manager 类、Callback、Exception 和权限声明把底层能力转换成 SDK 可依赖的稳定契约。
* Binder 是 Framework 与系统服务的 IPC 主干，负责 transaction、对象引用、caller UID/PID、回调和进程死亡通知；控制流通常走 Binder，大数据流更常走共享内存、BufferQueue、fd 或 DMA buffer。
* System Service / Native Service 是系统资源所有者，承担权限检查、AppOps、前后台状态、并发占用、资源仲裁、状态机和错误恢复。
* HAL 是 Android system side 与 vendor side 的稳定边界。现代 Android 主要通过 AIDL / Stable AIDL 等接口约束 system 与 vendor 的独立升级，历史设备还可能存在 HIDL 等形态。
* Vendor implementation 把标准 HAL 调用映射到具体 SoC、firmware、板级配置和硬件能力。相同 Framework API 在不同设备上出现能力差异，常从这里开始分叉。
* Linux Kernel 提供进程、线程、调度、虚拟内存、文件、网络、Binder driver、SELinux、cgroup、设备驱动、中断和 DMA 等基础。
* 返回路径同样重要：hardware event / buffer / error 经 driver、HAL、service、Binder callback 回到 App。只追请求不追结果，会遗漏大量真实故障点。
* 排查能力问题时应逐层确认：API 是否发出、caller identity 是否正确、service 是否接受、policy 是否放行、HAL 是否可用、driver/hardware 是否执行、结果是否成功返回。

关键路径
--------

::

   App process
   → Framework manager / API
   → Binder proxy / transaction
   → system_server service or native service
   → permission / AppOps / lifecycle / resource policy
   → HAL interface
   → vendor implementation
   → Linux kernel driver
   → hardware
   → event / buffer / status / error
   → service callback
   → Binder
   → App

概念辨析
--------

* **Framework API 与 System Service**：Framework API 是应用可见入口，System Service 才是全局状态和资源的实际所有者。
* **Binder 与业务逻辑**：Binder 负责跨进程传输、身份和对象生命周期，不负责替服务完成资源策略或硬件处理。
* **System Service 与 HAL**：前者属于 Android 平台控制面，后者是 system / vendor 硬件接口边界。
* **HAL 与 Driver**：HAL 把标准平台接口映射到厂商实现；Driver 在内核中直接管理设备、中断、DMA 和硬件资源。
* **权限通过与能力可用**：权限允许只表示安全门禁通过，资源占用、后台策略、HAL 状态和硬件故障仍可让请求失败。

本章结论
--------

Android Full Stack 的核心不是记服务名，而是把任何能力还原成 ``Identity → API → IPC → Owner → Policy → HAL → Kernel → Hardware → Return``。定位问题时，从用户可见入口向下确认责任主体，再沿返回链找第一个没有按预期完成的边界。