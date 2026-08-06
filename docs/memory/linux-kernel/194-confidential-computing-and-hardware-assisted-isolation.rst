第194章：机密计算与硬件辅助隔离
================================

核心知识点
----------

机密计算采用更强对手模型
   宿主机、Hypervisor、部分 Firmware 和云管理面可能不可信。硬件需要保护 Guest 的私有内存和部分 CPU 状态，使高权限宿主软件不能直接读取敏感数据。

Private 与 Shared Memory 是核心边界
   私有页用于保存受保护工作集；与 Host 或设备通信时，Guest 通常必须显式使用共享页或 Bounce Buffer。共享内容应始终视为可被读取、修改和重放。

远程证明建立密钥释放条件
   Attestation 将平台身份、Guest 度量、TCB 状态和 Nonce 绑定成报告。远端验证通过后才释放密钥，且签名有效不等于度量、版本和新鲜度满足策略。

Host/Guest 通信属于不可信输入
   Hypercall、MMIO、共享 Descriptor、长度、Feature、状态和完成顺序都需要边界检查。Host 即使不能读取私有页，仍能控制响应时序和资源可用性。

设备 I/O 需要显式跨越信任边界
   DMA 常通过共享 Bounce Buffer 完成。接收数据必须先由 Guest 校验，再复制回 Private Memory；IOMMU 只能限制地址范围，不能证明设备返回内容可信。

保护范围不包含全部风险
   机密计算通常不能阻止 DoS、Side Channel、流量分析和 Guest 内部的 Root 或应用权限问题。Namespace、LSM、Capability 和常规安全机制仍然必要。

TCB 与运行证据必须明确
   CPU、安全模块、Firmware、Guest Firmware、Guest Kernel、证明服务和密钥服务共同构成信任链。诊断必须区分 Guest/Host 角色、页状态、证明阶段和 I/O 路径。

关键路径
--------

远程信任建立：

::

   定义允许的平台、镜像与 TCB 策略
   → 启动 Confidential Guest
   → 硬件度量初始状态
   → 生成带 Nonce 的 Attestation Report
   → 验证签名、证书、Measurement 与 TCB
   → 释放密钥
   → 明文仅在 Private Memory 中使用

设备 I/O：

::

   Private Buffer
   → 复制或转换到 Shared Buffer
   → Host / Device 处理
   → Shared Completion
   → Guest 校验长度、Descriptor 与状态
   → 复制回 Private Buffer
   → 清理 Shared Memory

概念辨析
--------

* **Memory Encryption 与 Attestation**：内存加密保护运行中私有页；Attestation 让远端验证平台和初始状态后再释放密钥。
* **Private Memory 与 Shared Buffer**：Private Memory 受硬件保护；Shared Buffer 主动进入 Host/Device 可读写边界，内容必须校验。
* **Host 不可读取与 Host 不可拒绝服务**：机密性增强不意味着 Host 失去调度、I/O 和资源控制能力。
* **IOMMU 隔离与数据可信**：IOMMU 限制 DMA 可达地址，不验证设备响应和共享描述符语义。
* **Secure Boot 与远程证明**：Secure Boot 在本机验证启动签名；远程证明向外部报告实际度量和 TCB 状态。
* **Guest 受宿主保护与 Guest 内部隔离**：Confidential VM 保护整个 Guest，Guest 内部进程仍依赖常规 Linux 安全机制。

本章结论
--------

机密计算把信任边界下沉到硬件，并通过 Private Memory 与远程证明保护 Guest；相应地，Shared Memory、Hypercall 和设备 I/O 都必须作为来自更强对手的不可信输入处理。