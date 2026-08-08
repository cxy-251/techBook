第034章：Kernel Isolation, Access Control, Attack Surface
=========================================================

核心知识点
----------

* Kernel Boundary 是移动平台最高权限边界。进程隔离、页表、文件权限、device access、IPC 基础设施和 Driver 都依赖 Kernel 正确执行。
* 上层权限弹窗、签名、Sandbox 和 System Service policy 最终都要落到进程凭据、对象 label、页权限、fd/port/handle、device node 或 Driver 检查上。
* Process Isolation 依赖独立地址空间与 Kernel credential；Memory Protection 依赖 page permission、user/kernel split、不可执行页、ASLR 和受控 copy/mapping。
* 高性能共享 buffer 不取消隔离要求。dma-buf、IOSurface 或其它共享对象必须明确 creator、reader、writer、export handle、DMA 权限和生命周期。
* Device Driver 是高风险攻击面，因为 ``ioctl``、mmap、firmware parser、netlink/socket、DMA buffer、sysfs/debug interface 等入口会把不可信数据带入高权限代码。
* Driver 参数校验必须覆盖 pointer、length、offset、enum、handle、flag、object ownership、current state 与 integer overflow 等条件。
* Android 以 UID sandbox、SELinux、seccomp、Binder identity、device-node policy 等机制收缩应用到 Kernel/Driver 的入口；Apple 以 sandbox、entitlement、code signing、Mach rights 与系统服务边界实现类似目标。
* System Call Surface、IPC Surface、Driver Surface 和 Network Surface 都属于攻击面。安全设计目标不是让入口消失，而是缩小入口数量、限制调用者并使失败可审计。
* Kernel compromise 会动摇所有上层安全假设：攻击者可能读取其他进程、伪造身份、绕过 Sandbox、控制设备或隐藏持久化状态，因此 Kernel 漏洞的后果远高于普通 App crash。
* 最小权限、驱动隔离、用户态 Driver、IOMMU、签名/完整性校验和系统服务代理，都是减少 Kernel attack surface 的常见方向。

关键路径
--------

受控相机访问：

::

   untrusted App
   → Framework permission surface
   → System Service identity / lifecycle check
   → IPC with caller identity
   → HAL / daemon constrained interface
   → Kernel object + SELinux / sandbox enforcement
   → Driver validates command and buffer ownership
   → hardware

攻击面分析：

::

   external or low-privilege input
   → syscall / IPC / ioctl / parser / shared buffer
   → validate identity + bounds + object state
   → privileged operation
   → observable error or success

概念辨析
--------

* **Sandbox 与 Kernel Isolation**：Sandbox 是平台语义，Kernel Isolation 是其底层执行基础；只靠 Framework 约定无法形成硬隔离。
* **权限拒绝与漏洞利用**：正常权限拒绝说明边界按设计工作；内存破坏、UAF、越界或错误对象所有权可能让输入越过边界。
* **攻击面与漏洞**：暴露接口本身不等于漏洞，但接口越复杂、调用者越广、状态越多，验证负担越大。
* **Root 权限与 Kernel compromise**：高权限用户态仍受 Kernel 自身约束；控制 Kernel 意味着可以改变这些约束本身。
* **共享内存与信任共享**：共享 buffer 只共享被授权的数据对象，不应自动扩大调用者对其它内存或设备的权限。

本章结论
--------

移动平台安全最终要在 Kernel object 和 Driver boundary 上成立。分析能力访问时，应固定“调用者身份 → 目标对象 → 执行检查点 → 高权限入口 → 失败证据”这条路径，并重点关注 syscall、IPC、Driver、DMA 与共享 buffer 的输入验证和所有权。Kernel 一旦失守，上层 Sandbox、权限和服务策略都会失去可信执行基础。