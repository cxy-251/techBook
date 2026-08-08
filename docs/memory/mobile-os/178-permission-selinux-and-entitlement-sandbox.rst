第178章：Permission + SELinux and Entitlement + Sandbox
========================================================

核心知识点
----------

* 移动安全不是单一“权限开关”，而是身份、能力声明、用户授权、服务检查、内核 / 沙箱限制和硬件安全域共同组成的多检查点责任链。
* Android 以 Linux UID 建立 App 身份和基础文件隔离；manifest permission 表达能力声明，runtime grant 表达用户授权，AppOps 表达具体敏感操作的运行时控制与审计。
* Android 的 system service 是关键 enforcement 点：服务读取 Binder caller identity，再结合 permission、AppOps、前后台状态、设备策略和资源占用决定是否接受请求。
* SELinux 提供强制访问控制，限制 App、system service、HAL、device node 等不同 domain / type 的访问关系；即使 root 进程也受策略约束。
* Apple 以 code signing identity 建立调用者身份；entitlement 是签名中受平台控制的能力声明，不能由 App 在运行时自行获得。
* TCC 记录用户对相机、麦克风、定位、照片等隐私数据的授权；sandbox 约束文件、IPC、容器和系统资源访问；Keychain / Secure Enclave 再提供秘密存储与硬件隔离边界。
* 用户点“允许”只解决 user consent；平台 entitlement、service policy、sandbox / SELinux 与资源仲裁仍可能继续拒绝。
* 安全故障排查要沿检查点定位，不能把所有拒绝都归为“权限问题”。

关键路径
--------

::

   Android:
   App UID → Manifest Permission → Runtime Grant
       → Binder Caller Identity → Service Enforcement / AppOps
       → SELinux / HAL / Driver Boundary → Resource

   Apple:
   Code-Signed App Identity → Entitlement
       → TCC User Consent → Framework / Daemon Check
       → Sandbox / Keychain / Driver / Secure Enclave Boundary
       → Resource

常见证据应映射到层级：``SecurityException`` 看 permission / service；``AppOps deny`` 看运行时操作；``avc: denied`` 看 SELinux；Apple 的 denied / restricted 状态看 TCC、entitlement、sandbox 与系统策略。

概念辨析
--------

* ``Permission`` 不等于 ``AppOps``：permission 是能力授权事实，AppOps 更接近某次敏感操作的运行时模式与审计。
* ``UID sandbox`` 不等于 ``SELinux``：UID / DAC 负责基础身份与所有权，SELinux / MAC 进一步约束跨域访问。
* ``Entitlement`` 不等于 ``TCC``：entitlement 是平台准入资格，TCC 是用户隐私授权；二者可能同时要求满足。
* ``用户同意`` 不等于 ``系统最终放行``：system service / daemon 仍会结合生命周期、并发资源、设备策略和安全边界继续判断。

本章结论
--------

Android 用 UID + Permission + AppOps + SELinux 建立分层能力控制；Apple 用 code signing + Entitlement + TCC + Sandbox 建立类似的多检查点链。两套模型的共同原则是：先确认调用者身份，再确认声明与用户授权，最终由系统服务和底层安全边界决定真实资源访问。