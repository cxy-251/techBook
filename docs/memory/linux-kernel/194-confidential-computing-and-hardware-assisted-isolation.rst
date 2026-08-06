第194章：机密计算与硬件辅助隔离
================================

本章必须记住
------------

#. 机密计算面对的对手比传统 Linux 权限模型更强：宿主机、Hypervisor、部分 Firmware 和云管理面可能不可信。
#. 传统 Linux 主要由内核保护用户态；机密计算进一步要求硬件保护 Guest，使宿主高权限软件无法直接读取 Guest 私有状态。
#. 机密计算的核心对象是 Private Memory、Shared Memory、受保护 vCPU State、Attestation 和 Host/Device Communication。
#. Memory Encryption 保护运行中内存内容，不能单独证明启动代码可信或设备 I/O 安全。
#. Attestation 证明 Guest 身份和初始度量，不能替代运行期输入校验。
#. TEE 或 Confidential VM 定义受硬件强制保护的执行边界。
#. 远端 Owner 通常先验证 Attestation，再决定是否向 Guest 释放密钥和敏感配置。
#. Attestation Report 应绑定平台身份、Guest 度量、策略和 Freshness Nonce。
#. 只验证签名而不验证 Measurement、TCB Version 和 Nonce，会留下重放和错误环境风险。
#. Guest 接收密钥后，应让明文工作集留在 Private Memory 中。
#. 与 Host、VMM 或设备通信时，Guest 通常需要显式使用 Shared Memory 或 Bounce Buffer。
#. Private Page 不能被普通不可信 Host/Device 路径直接解释为明文共享缓冲区。
#. Shared Page 是主动扩大的信任边界，其中数据必须视为 Host 可读、可修改和可重放。
#. Page 从 Private 转为 Shared、再恢复 Private 时，需要遵守架构规定的状态转换和清理顺序。
#. 恢复为 Private 前应清除 Host 可控旧数据，并重新建立页所有权和映射不变量。
#. 加密页属性通常落到页表、平台能力和架构专用内存管理路径。
#. ``cc_platform_has()`` 一类抽象用于查询平台机密计算属性，精确能力枚举随版本演进。
#. x86 CoCo 代码可分布在 ``arch/x86/coco/``、SEV/SNP、TDX 和通用内存/DMA 路径中。
#. Arm CCA 使用不同的 Realm 与管理组件模型，不能把 x86 接口机械套用到 Arm。
#. AMD SEV/SEV-SNP、Intel TDX 和 Arm CCA 的共同目标相似，内存状态、证明和异常通信机制不同。
#. 架构名称不能替代精确威胁模型；必须说明保护 CPU State、Memory Confidentiality、Integrity 和 Replay 的具体范围。
#. 某些方案只提供机密性，另一些增强页归属、完整性和启动证明。
#. Host 仍控制 vCPU 调度、资源分配、I/O 可用性和中断时机，机密计算通常不防止 Denial of Service。
#. Host 可能无法读取 Private Memory，仍可通过调度、I/O 时序和资源压力影响 Guest。
#. Side Channel、Traffic Analysis、Page Fault Pattern 和设备时序可能超出基础内存加密保护范围。
#. Guest Kernel 必须把 Hypercall、MMIO、Port I/O、Shared Buffer 和 Host 注入事件视为不可信输入。
#. 机密 Guest 的攻击面会从普通设备驱动扩展到 Host/Guest 通信协议本身。
#. #VC、#VE、GHCB、TDVMCALL 等异常和通信路径具有架构差异，应按目标平台源码确认。
#. Host 返回的长度、状态、地址、Feature 和错误码都需要边界检查。
#. Host 能控制响应时序，因此 Guest 还要处理 Timeout、重复完成和状态不同步。
#. 不可信 Host 输入不应触发 Guest Kernel WARN、Oops 或 Panic；应尽量返回受控错误。
#. DMA 是机密计算的关键边界，因为普通设备可能无法直接访问加密 Private Memory。
#. Guest 常通过 SWIOTLB、Bounce Buffer 或共享 DMA 区域与设备交换数据。
#. DMA 发送路径通常是 Private Source → Shared Bounce Buffer → Device。
#. DMA 接收路径通常是 Device → Shared Bounce Buffer → Guest 校验 → Private Destination。
#. Bounce Buffer 增加 Copy、内存占用和延迟，不是纯安全元数据操作。
#. 设备完成前，Shared Buffer 仍由 Device/Host 路径控制，不能提前当作可信 Private Data 使用。
#. IOMMU 可以限制设备地址范围，不能自动让不可信 Host 返回的数据可信。
#. Virtio 等半虚拟化设备依赖 Shared Ring、Descriptor 和 Buffer，Guest 必须验证所有 Host 可改字段。
#. Descriptor Length、Index、Feature Bit 和 Completion 顺序都可能成为攻击输入。
#. Confidential Guest 中启用设备 Feature 前，应确认该 Feature 与 Private/Shared Memory 模型兼容。
#. PCI Passthrough、Device Assignment 和 Protected I/O 具有更复杂的平台支持边界，不能默认等同于普通 VM Passthrough。
#. Guest Firmware、Bootloader、Kernel、Initramfs 和 Command Line 都可能进入启动度量或信任策略。
#. Attestation Measurement 不一定覆盖运行后加载的所有模块、配置和用户数据。
#. 需要把 Secure Boot、Measured Boot、IMA、Module Signature 和 Attestation 各自的范围分开。
#. Secure Boot 控制启动组件签名，Attestation 让远端验证实际环境，两者不是同一机制。
#. Disk Encryption 保护静态存储，TLS 保护传输，Confidential Computing 保护运行中状态，三者需要组合。
#. Host 仍可能观察磁盘访问、包大小和运行时间等外部行为。
#. Attestation 验证服务本身属于信任链，包括证书、TCB 状态、撤销和策略更新。
#. TCB Version 过旧或平台存在已知漏洞时，即使报告签名有效也不应自动释放密钥。
#. Guest Image 更新会改变 Measurement，密钥释放策略必须配套更新。
#. Confidential VM 的可迁移性、快照和恢复会影响密钥、计数器、证明和 Replay 模型。
#. 快照恢复可能重复旧状态，应用协议应考虑 Rollback Protection。
#. Live Migration 需要源、目标平台和迁移通道共同维持机密边界，具体支持高度平台相关。
#. Host Kernel 作为 KVM 管理方时负责创建和调度受保护 Guest，某些方案中它不属于 Guest TCB。
#. Guest Kernel 与 Host Kernel 对同一页的“可见性”不同，调试时必须先确认运行角色。
#. Host 侧看不到 Private Memory 会降低传统 Crash Dump 和调试能力。
#. Guest 内部应提前配置日志、Pstore、Kdump 或远端观测，以保留故障证据。
#. 向 Host 共享调试信息会扩大信息泄漏面，生产策略要权衡可观测性与机密性。
#. Guest Panic 后的内存转储可能包含敏感明文，保存和传输必须受保护。
#. 性能评估应分别测量内存加密、Shared Conversion、Bounce Copy、Attestation 和 I/O 路径成本。
#. 只比较 CPU Benchmark 不能说明网络和存储负载成本。
#. 大量 Shared/Private 转换会增加 TLB、页表和平台通信成本。
#. 机密计算不会自动修复 Guest 内部的普通 Root、LSM、Seccomp 和应用权限问题。
#. Guest 内部仍需 Namespace、Cgroup、Capability、LSM 和常规内核安全机制。
#. 机密边界保护 Guest 免受 Host 读取，不等于 Guest 内不同租户自动隔离。
#. Host 无法读 Private Memory，也不意味着 Guest Kernel 或 Guest Root 不可信。
#. 威胁模型必须明确哪些组件在 TCB 内：CPU、Security Module、Firmware、Guest Firmware、Guest Kernel、证明服务和应用。
#. 供应链风险包括镜像构建、Firmware、微码、证明证书和密钥服务。
#. 平台 Feature 可用不表示云实例、Kernel Config、Firmware 和管理服务已正确启用。
#. 诊断应先确认平台类型、Guest/Host 角色、Feature Detection、Page State、Attestation 和 I/O 路径。
#. Shared Buffer 数据异常时，应定位最早由 Host/Device 可修改的字段，而不是只修补 Guest 最后崩溃点。
#. Attestation 失败应区分签名、证书链、Measurement、Nonce、TCB、Policy 和网络服务问题。
#. DMA 失败应区分页状态、Bounce Buffer、IOMMU、Device Feature、Mapping 和 Completion。
#. 机密 Guest 启动失败可能来自 Firmware、Kernel Feature、Memory Acceptance、Page Conversion 或 VMM 协议不匹配。
#. 内核源码只能说明边界如何实现，不能单独证明云平台运营、证书服务和供应链全部可信。
#. 稳定分析顺序是：Threat Model → TCB → Attestation → Private/Shared Memory → Host Input → DMA/I/O → Runtime Evidence。

必背路径
--------

远端信任建立：

::

   Owner 定义允许的 Platform / Image / TCB Policy
   → 启动 Confidential Guest
   → Hardware / Security Manager 度量初始状态
   → Guest 获取带 Nonce 的 Attestation Report
   → Owner 验证签名、证书、Measurement 与 TCB
   → 验证通过后释放密钥
   → 明文仅在受保护 Guest 内使用

设备 I/O：

::

   Private Guest Buffer
   → 复制或转换到 Shared Buffer
   → Virtio / Device / Host 处理
   → Shared Completion
   → Guest 校验 Descriptor、Length 与状态
   → 复制到 Private Buffer
   → 清理或回收 Shared Page

必须区分
--------

* Memory Encryption 与 Attestation：内存加密限制宿主读取运行中私有页；Attestation 让远端验证平台、镜像和初始状态后再释放密钥。
* Private Memory 与 Shared Communication Buffer：Private Memory 受硬件保护且不应直接暴露给 Host；Shared Buffer 主动进入 Host/Device 可读写边界，内容必须校验。
* Host 无法读取 Guest 私有页与 Host 无法拒绝服务：机密计算保护机密性和部分完整性；Host 仍能暂停 vCPU、延迟 I/O 或撤销资源造成 DoS。
* IOMMU 地址隔离与 Host/Device 数据可信：IOMMU 限制 DMA 可达地址；它不证明设备响应、Descriptor、长度和完成状态可信。
* Secure Boot 与远程证明：Secure Boot 在本机启动时验证签名链；远程证明向外部 Owner 报告实际度量和 TCB 状态。
* Confidential VM 边界与 Guest 内部进程隔离：Confidential VM 保护整个 Guest 免受 Host 读取；Guest 内部仍依赖 Credential、LSM、Namespace 和应用权限隔离进程。
* 平台支持某技术与目标实例整条信任链已正确配置：硬件能力只是前提；Firmware、Kernel、VMM、证书、Attestation Service 和密钥策略都必须匹配。

一句话结论
----------

机密计算依靠硬件保护的 Private Memory 和远程证明把信任边界下沉到操作系统之下，同时迫使 Guest 将 Shared Memory、Hypercall 与设备 I/O 全部视为来自更强对手的输入。
