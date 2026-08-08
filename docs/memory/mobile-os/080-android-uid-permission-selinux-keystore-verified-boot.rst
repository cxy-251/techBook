第080章：Android UID, Permission, SELinux, Keystore, Verified Boot
=================================================================

核心知识点
----------

* Android 安全链可以按 ``UID → Permission → AppOps → SELinux → Keystore / KeyMint → Verified Boot`` 阅读，每一层只解决一类问题。
* UID 是 Android App 的核心运行身份之一。安装时系统为 App 分配 UID，进程以该 UID 运行，Linux DAC、文件 owner、Binder caller identity 都围绕它工作。
* Permission 是 Framework 能力边界。Manifest 声明只是需求声明，运行时 grant 才代表当前授权；真正调用系统服务时还会再次进行服务端检查。
* AppOps 是敏感 operation 的运行期控制和审计层。它可以表达 ``allowed / ignored / foreground / errored`` 等状态，因此“权限已 granted”仍可能因为 AppOps 或生命周期而无结果。
* SELinux 提供 Mandatory Access Control。它用 process domain、object type、allow rule 与 neverallow 限制 system_server、App、vendor daemon、HAL、device node 等对象之间的访问关系。
* Linux DAC 回答“这个 UID 是否按 owner / mode 可访问”；SELinux MAC 继续回答“即使 DAC 允许，这个 domain 是否被平台 policy 允许”。两层不能互相替代。
* Android Keystore 把密钥能力交给系统服务和 KeyMint / TEE / StrongBox 等安全边界管理。App 通常获得 key alias 和可执行密码操作，不应直接获得不可导出的私钥材料。
* 密钥策略可以绑定用户认证、锁屏状态、设备硬件、rollback resistance 与用途。进程拥有文件权限不代表拥有密钥使用资格。
* Verified Boot 从 hardware root of trust 开始验证 bootloader、boot image、vbmeta 与 verified partitions；dm-verity 等机制负责运行时检测受保护块设备完整性。
* Verified Boot 保护系统基础可信度，不能替代 App sandbox、runtime permission 或服务端授权；这些层共同构成纵深防御。

关键路径
--------

普通 App 访问自己的文件：

``App Process UID → open/read syscall → Linux DAC → SELinux → App Private File``

敏感 Framework API：

``App → Framework Manager → Binder → Service reads Calling UID / Package → Permission → AppOps → Lifecycle / Policy → Resource``

硬件密钥：

``App → Keystore API → Keystore Service → UID / Authorization Set / User Authentication → KeyMint / TEE / StrongBox → Crypto Operation Result``

系统启动完整性：

``Hardware Root of Trust → Boot ROM → Bootloader → vbmeta / Boot Verification → Verified Partitions / dm-verity → Trusted Android Runtime``

排查拒绝时应从最接近现象的层开始：文件访问先看 UID / DAC / SELinux；Framework 能力先看 Permission / AppOps；密钥问题先看 authorization 与硬件 backend；启动异常再看 Verified Boot 和 rollback state。

概念辨析
--------

* **UID 与 Permission**：UID 回答“调用者是谁”；Permission 回答“这个主体是否被授予某类 Framework 能力”。
* **Permission 与 AppOps**：Permission 是授权状态；AppOps 是一次 operation 的运行期策略与审计，两者经常联合判断。
* **DAC 与 SELinux MAC**：DAC 依赖 owner、group、mode；SELinux 依赖 domain / type policy。通过其中一层不代表通过另一层。
* **Keystore 与普通文件加密**：Keystore 保护的是密钥生命周期和使用权限；数据文件是否加密、如何组织仍由上层应用或系统存储机制决定。
* **Verified Boot 与 Runtime Security**：Verified Boot 证明系统镜像链可信；runtime security 再限制可信系统上每个 App 能做什么。

本章结论
--------

Android 安全不是“一个权限弹窗”，而是从 Linux 身份、Framework 授权、运行期 operation、SELinux 域、硬件密钥到启动完整性的多层防线。正确定位问题时必须先确定失败属于哪一层，再沿 UID、Permission、AppOps、SELinux、Keystore、Verified Boot 的责任链继续追踪。