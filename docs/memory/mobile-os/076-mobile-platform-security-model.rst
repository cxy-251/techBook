第076章：Mobile Platform Security Model
======================================

核心知识点
----------

* 移动平台安全不是单一“权限系统”，而是一条连续信任链：``Hardware Trust → Boot Trust → Kernel Trust → System Service Policy → App Identity → User Consent → Capability Access``。
* Hardware Trust 提供不可变启动代码、设备密钥和安全存储等信任起点；Boot Trust 逐级验证 bootloader、kernel、关键 firmware 与系统分区。
* Kernel Trust 负责进程隔离、地址空间、系统调用、设备节点和强制访问控制；系统服务在此基础上持有资源状态并执行最终能力授权。
* App Trust 由安装身份、代码签名、包或 Bundle 标识、运行进程与平台授权状态共同构成。Android 典型对象包括 UID、package、signing certificate、permission、AppOps、SELinux；Apple 典型对象包括 Bundle ID、Team ID、code signing、entitlement、sandbox、TCC。
* ``Isolation`` 决定默认不能访问什么；``Identity`` 决定谁在请求；``Permission / Consent`` 决定用户或系统是否开放能力；``Signature`` 决定代码来源和身份连续性。四者不能互相替代。
* 相机、麦克风、定位、蓝牙、通知、密钥等高价值能力都应由 system service / daemon 代理。App 获得的是受控能力，不是原始硬件所有权。
* 用户授权只表达用户意图，真正执行仍在服务端、内核和硬件边界。已授权不代表资源当前一定可用，也不代表后台状态一定允许访问。
* 安全状态是动态的：权限可撤销、App 可进入后台、设备可锁定、密钥可要求认证、系统完整性状态也会影响可用能力。

关键路径
--------

一次敏感能力请求应按下面的顺序阅读：

``App → Framework API → IPC → Caller Identity → Permission / Entitlement / TCC / AppOps → Lifecycle / Resource Policy → System Service / Daemon → HAL / Driver → Hardware``

以麦克风为例：

``App 请求录音 → Framework 封装请求 → IPC 传递真实调用者身份 → 服务检查用户授权与前后台状态 → 音频服务仲裁输入设备 → Driver / DSP 采集 → Buffer 返回 App``

该运行期路径成立还有一条更早的信任前提：

``Hardware Root of Trust → Boot ROM → Bootloader → Verified Kernel / System Image → Runtime Security Policy``

如果问题发生在安装或启动前，优先检查签名与完整性；如果 API 已经进入服务端，优先检查调用者身份、授权状态、生命周期和资源占用；如果服务已经放行，再进入 HAL、driver 与硬件状态。

概念辨析
--------

* **Trust 与 Permission**：Trust 回答“执行这些检查的平台本身是否可信”；Permission 回答“可信平台是否允许某主体使用某能力”。
* **Identity 与 Signature**：Identity 是运行期主体；Signature 是建立和延续该主体的重要证据。PID 不是长期 App 身份。
* **Sandbox 与 Permission**：Sandbox 先收缩默认资源面；Permission 通过系统服务在特定能力上开受控通道。
* **User Consent 与 Enforcement**：弹窗和设置记录是 consent；system service、daemon、kernel、driver 的实际拒绝或放行才是 enforcement。
* **Capability Handle 与 Raw Resource**：Binder handle、Mach port、session token、file descriptor 等代表受控能力；它们不等于 App 获得服务端对象或硬件的直接所有权。

本章结论
--------

移动平台安全应按“系统可信 → 主体可信 → 授权有效 → 隔离边界允许 → 服务策略允许 → 硬件可用”逐层判断。任何敏感 API 的成功都不是单点授权结果，而是 Hardware、Boot、Kernel、Service、App Identity 与 User Consent 多层状态同时成立的结果。