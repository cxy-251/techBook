第027章：Kernel Responsibilities in a Mobile Platform
======================================================

核心知识点
----------

* Kernel 是移动平台底层资源所有者，负责把 CPU、Memory、Device、Interrupt、File、Network 和 Power 变成可分配、可隔离、可回收的系统资源。
* App 与 Framework 表达能力意图，System Service 负责权限、生命周期和资源仲裁，Kernel 与 Driver 负责把这些策略落到真实进程、线程、内存映射、设备对象和硬件状态上。
* CPU 管理关注 runnable thread、优先级、抢占、核心选择与调度延迟；Memory 管理关注地址空间、物理页、共享 buffer、page cache 与回收；Device 管理关注设备节点、驱动对象、队列和状态机。
* Interrupt 把硬件事件送入 Kernel；DMA 让相机帧、音频、网络包等大块数据在设备与内存之间移动；Power 子系统决定设备是否保持 active、进入 runtime suspend 或允许 system suspend。
* User Space 与 Kernel Space 是核心权限边界。普通 App 不能直接访问内核内存或任意设备寄存器，只能通过 syscall、IPC、fd、port、socket、ioctl 或受控共享内存请求资源。
* Driver、VFS、network stack、security hook 与 power subsystem 是 Kernel 向上层系统能力提供出口的主要子系统。
* Android 使用 Linux Kernel 承担调度、内存、Binder driver、SELinux、cgroup、power management 与 vendor driver 等职责；Apple XNU 通过 Mach、BSD、IOKit 等组件承担对应角色。
* 移动系统故障定位必须区分“策略拒绝”和“底层执行失败”：前者常发生在 Framework/System Service，后者常表现为 kernel errno、driver timeout、buffer failure、I/O error 或设备状态异常。

关键路径
--------

一次相机拍摄并上传：

::

   App
   → Framework API
   → System Service permission / ownership check
   → HAL or daemon
   → Kernel device / process / memory objects
   → Driver queue + DMA + interrupt
   → frame completion
   → file system write
   → network stack upload

用户态进入内核态：

::

   user-space request
   → syscall / Binder ioctl / Mach trap / socket / mmap
   → parameter and identity validation
   → resolve kernel object
   → perform resource operation
   → return status / errno / callback

概念辨析
--------

* **Kernel 与 Operating System**：Kernel 是 OS 的最高权限资源管理层；完整 OS 还包含 System Service、Runtime、Framework、UI 与系统策略。
* **System Service 仲裁与 Kernel 仲裁**：System Service 决定“谁应该获得能力”，Kernel/Driver 决定“如何安全地占用并执行底层资源”。
* **API 失败与 Kernel 失败**：权限不足、后台限制属于上层策略失败；``EACCES``、``ENODEV``、driver timeout、DMA 错误更接近底层执行边界。
* **Android Linux 与 Apple XNU**：二者内部结构不同，但都承担进程、线程、内存、文件、网络、设备和安全执行的 Kernel 角色。
* **共享 Buffer 与直接硬件访问**：共享 buffer 只是受控的数据交换机制，不等于 App 获得设备寄存器或 DMA 的直接控制权。

本章结论
--------

移动 Kernel 的稳定阅读模型是：先找上层能力请求，再定位 System Service 的策略判断，随后沿 Kernel object、Driver、Interrupt、DMA、File/Network 和 Power 路径确认资源如何真正被执行。Kernel 不是所有用户体验策略的制定者，却是这些策略最终能够被可靠隔离、调度和落地的共同底座。