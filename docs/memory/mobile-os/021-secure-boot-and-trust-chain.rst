第021章：Secure Boot and Trust Chain
=====================================

核心知识点
----------

* Secure Boot 的核心是“当前已被信任的阶段，在移交控制权前验证下一阶段”。Chain of Trust 因此是一串局部验证，而不是一次全局检查。
* Root of Trust 通常由 Boot ROM、硬件保护公钥或公钥摘要、熔丝和安全存储组成。它给出最初的验证者，后续信任从这里逐级扩展。
* 启动链必须分别回答来源、完整性、版本和设备状态四类问题：谁签的、内容有没有变、版本是否过旧、当前设备是否允许这类镜像运行。
* Hash 证明内容与记录摘要一致；code signature 证明内容由持有授权私钥的主体签署；certificate 组织公钥授权关系；rollback counter 限制旧版本回放。
* Key hierarchy 允许根密钥授权中间密钥、分区密钥或 firmware 密钥，降低所有组件共用单一私钥的风险，并支持 key rotation 与职责分离。
* Android AVB 使用 ``vbmeta``、descriptor、chain partition、rollback index 等对象组织启动信任关系；Apple 公开链路则以 Boot ROM、iBoot、kernel 和相关 firmware 的逐级签名验证为核心。
* Bootloader、kernel、firmware、baseband 等对象属于不同可信边界，可能由不同发布主体、验证密钥和版本策略管理，不能把“系统签名”理解为一把密钥覆盖所有软件。
* Boot state 必须继续传给 kernel 与 userspace。启动完成后，系统仍需要知道自己来自 locked/unlocked、green/orange 等何种信任状态。
* Secure Boot 保护的是启动代码接受范围，不等同于运行时权限系统；App sandbox、SELinux、entitlement、KeyStore/Keychain 等机制建立在可信平台启动之后。

关键路径
--------

逐级验证：

::

   hardware root of trust
   → Boot ROM verifies next loader
   → bootloader verifies vbmeta / boot objects
   → verify kernel and required firmware
   → check rollback state
   → pass trust state to kernel
   → kernel and userspace continue policy enforcement

镜像判断：

::

   image bytes
   → calculate digest
   → verify signature with authorized public key
   → validate certificate / delegated key if used
   → compare rollback counter
   → accept / warn / reject / recover

密钥层级：

::

   root key
   → intermediate or delegated key
   → partition / firmware signing key
   → signed image metadata
   → verified executable object

概念辨析
--------

* **Hash 与 signature**：Hash 只说明内容一致，signature 进一步说明摘要由授权私钥签署。
* **Signature 与 certificate**：签名验证某份内容，证书用于建立“这个公钥是否被更高层信任主体授权”。
* **合法签名与安全版本**：签名合法的旧镜像仍可能因 rollback index 过低而被拒绝。
* **Root of Trust 与用户权限**：Root of Trust 是启动期信任起点，用户权限属于系统启动后的运行时访问控制。
* **Device unlocked 与完全无校验**：解锁通常扩大镜像接受范围并降低信任状态，但不同平台仍可能保留部分签名、完整性或硬件安全约束。

本章结论
--------

安全启动的稳定模型是“硬件根信任 → 逐级验证 → 版本检查 → 状态传递”。分析一份镜像为什么被接受或拒绝时，应分别检查根密钥、签名、hash、证书/委托关系、rollback counter 和 device state；这些对象共同决定启动控制权能否继续向下一级转移。