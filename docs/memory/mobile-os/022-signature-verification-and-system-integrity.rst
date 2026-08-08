第022章：Signature Verification and System Integrity
====================================================

核心知识点
----------

* Signature Verification 是启动期完整性入口：系统先确认镜像来自受信任主体，再决定是否允许执行、挂载或继续启动。
* 小型启动镜像通常适合整体 hash/signature 验证；``system``、``vendor`` 等大分区更适合使用 hash tree，在读取时按 block 校验。
* Android AVB 把分区 hash、hashtree root、签名、rollback metadata 和链式分区关系组织进可信元数据；bootloader 先验证元数据，再验证对应对象。
* ``dm-verity`` 位于 block device 路径，在实际读取系统分区数据时沿 Merkle/hash tree 验证到可信 root hash，使“启动时可信”延伸到“运行时读取仍可信”。
* Firmware 与 baseband 往往拥有独立执行环境。其完整性至少包含两层：固件文件所在系统分区可信，以及协处理器/外设本身接受该 firmware 的签名和版本。
* Driver、kernel module 或 kernel extension 越接近内核与硬件，载入前的信任要求越高。平台可通过受验证分区、模块签名、受控扩展框架等方式限制特权代码进入内核路径。
* Rollback protection 解决“合法旧版本”问题。签名只能证明来源，anti-rollback state 决定某个旧版本是否仍可被当前设备接受。
* Tamper detection 的结果不是单一错误码：不同阶段可能表现为 bootloader 警告、recovery/DFU、挂载失败、I/O error、重启循环或系统服务缺失。
* System Integrity 与 User Data Protection 相连但不相同。完整性保证平台代码和系统分区可信，数据保护再使用用户凭据和硬件密钥决定哪些用户数据可解封。

关键路径
--------

启动镜像验证：

::

   Boot ROM / bootloader trust anchor
   → verify boot metadata and signature
   → verify boot / kernel image
   → check rollback state
   → accept image or enter warning / recovery

大分区读取：

::

   trusted vbmeta descriptor
   → trusted hashtree root
   → dm-verity target
   → block read
   → hash path verification
   → data returned or integrity failure

固件加载：

::

   verified system/vendor storage
   → driver / firmware loader
   → peripheral or coprocessor signature check
   → firmware execution
   → hardware capability becomes available

概念辨析
--------

* **镜像级验证与 block-level 验证**：前者验证整体启动对象，后者支持大型分区按需读取时持续校验。
* **AVB 与 dm-verity**：AVB 组织启动信任元数据，dm-verity 是其中面向块设备运行时完整性的执行机制。
* **系统分区可信与 firmware 可执行**：固件文件所在分区可信，不一定等于硬件端一定接受该 firmware，后者可能还有独立签名策略。
* **Kernel module 与普通 App**：模块进入内核特权域，信任门槛和故障影响远高于普通沙箱应用。
* **System integrity 与 user data confidentiality**：前者防系统代码被替换，后者控制用户数据何时、由谁解密访问。

本章结论
--------

系统完整性是一条从启动签名到运行期分区读取、firmware/driver 载入和版本状态检查的连续链。分析篡改、OTA 后启动失败或旧版本回退时，应区分镜像来源验证、block-level 完整性、firmware 执行信任、driver 载入和 rollback protection，并把用户数据保护视为建立在可信平台之上的另一层安全边界。