第073章：Caller Identity, Permission Check, Capability Boundary
==============================================================

核心知识点
----------

* IPC 权限判断的核心问题是：服务端必须知道“谁在请求什么能力”，并把调用者身份与权限、生命周期、资源状态和系统策略联合判断。
* Android Binder 在 transaction 上下文中提供 calling UID / PID。UID 是主体锚点，PID 主要用于当前进程实例定位；包名等客户端参数必须和 UID 归属关系交叉校验。
* Android 的授权链通常包含 UID / user、runtime permission、AppOps、前后台状态和 SELinux domain。任一层拒绝都可能使能力失败。
* Apple 平台以代码签名身份、audit credential、entitlement、sandbox、用户隐私授权和 daemon-side check 共同形成能力边界。
* Framework 可以做快速检查，但最终授权应落在拥有真实资源状态的 System Service / Daemon 侧。
* Capability token、Binder handle、Mach port right、session handle 都代表某种受控访问资格。拿到 token 之后，服务仍可根据状态撤销、降级或拒绝后续操作。
* 身份切换必须谨慎。Android 服务使用 ``clearCallingIdentity`` 前应先完成 caller 授权，使用服务自身身份完成内部动作后必须恢复原上下文。

关键路径
--------

Android 敏感能力判断：

``Binder transaction → calling UID/PID → UID/package ownership → runtime permission → AppOps → foreground/background state → SELinux / service policy → resource arbitration``

Apple 通用判断：

``Framework/XPC request → connection/audit identity → code-signing / entitlement → sandbox / privacy authorization → daemon policy → resource state``

相机请求只有在身份、权限和当前资源状态同时满足时才建立 session；失败可能表现为 SecurityException、错误回调、空结果或受限能力。

概念辨析
--------

* **Package / Bundle ID ≠ trustworthy caller identity**：字符串是声明，必须结合 IPC 或签名凭据验证。
* **Permission ≠ AppOps / runtime policy**：静态或运行时授权通过后，操作仍可能被前后台策略、AppOps 或系统开关限制。
* **Entitlement ≠ user consent**：entitlement 表示平台能力资格，用户对相机、定位、照片等敏感数据的授权是另一层。
* **Sandbox ≠ permission prompt**：sandbox 限制默认可达对象，用户授权决定受控能力是否允许当前主体使用。
* **Handle / token ≠ ownership of hardware**：句柄只代表访问能力，真实资源所有权仍由服务端维护。

本章结论
--------

IPC 是移动 OS 权限执行的关键可信边界。安全分析时应从系统提供的 caller identity 出发，再逐层检查权限、运行态策略、sandbox / SELinux 和资源状态，而不能把客户端传入的身份字段或单一权限结果当作最终授权依据。
