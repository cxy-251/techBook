第162章：Capabilities 与特权拆分
================================

核心知识点
----------

Capability 把传统 Root 权力拆成操作族
   Linux 不再把所有高权限操作只归结为 EUID 0，而是在具体内核路径检查 ``CAP_*`` 位。每个位覆盖一组明确但并不总是狭窄的能力。

授权必须带 User Namespace 语境
   ``capable()``、``ns_capable()`` 等检查读取当前 Credential 的 Capability，并结合目标对象所属 User Namespace 判断作用范围。容器内拥有某个位，不代表能管理 Initial User Namespace 的全局对象。

Capability 是线程 Credential 的一部分
   内核最终检查当前 Task 的 ``struct cred``。多线程程序可以出现不同线程拥有不同集合，用户态所谓“进程 Capability”只是管理层抽象。

Effective Set 决定当前授权
   当前 ``capable()`` 类检查通常读取 Effective 集合。某个位只存在于 Permitted、Inheritable、Bounding 或 Ambient 中，不等于当前操作已经获得授权。

Permitted Set 是可启用上限
   Permitted 表示线程当前可以保留或启用的 Capability 资格。普通线程不能把不在允许来源中的位凭空加入 Effective 或 Permitted。

Bounding Set 限制未来获得路径
   Bounding 主要裁剪后续通过 ``execve()`` 和 File Capability 获得的权限。删除通常是单向的，适合在初始化后封死未来重新提权路径。

Inheritable 与 Ambient 服务 Exec 传播
   Inheritable 参与与可执行文件属性的组合，Ambient 允许少量权限跨普通非特权 Exec 保留。Ambient 必须满足严格前提，并会在特权 Exec 边界被清理。

``execve()`` 重新计算 Capability
   旧 Credential、File Capability、Setuid/Setgid、Bounding、Ambient、``no_new_privs``、Securebits、Ptrace 和 User Namespace 共同生成新 Credential。

File Capability 把权限绑定到可执行文件
   ``security.capability`` xattr 可让程序获得有限授权，而不必成为完整 Setuid-root 程序。它仍受文件完整性、Mount、文件系统支持、Bounding 与 ``no_new_privs`` 约束。

``no_new_privs`` 阻止 Exec 获得新特权
   一旦设置，后续 ``execve()`` 不能通过 Setuid、Setgid 或 File Capability 增加权限。该状态单向生效，常用于 Seccomp 与沙箱边界。

``CAP_SYS_ADMIN`` 不是普通管理位
   它覆盖大量不相关高风险路径，应视为接近完整 Root 的授权。能够使用更窄 Capability、预打开 fd、Broker 或专用接口时，不应把它作为通用修复。

Capability 不能越过其它安全层
   Capability 放行后，LSM、Seccomp、只读 Mount、不可变对象、设备策略和子系统状态仍可拒绝。一个 ``EPERM`` 也不能自动证明缺少 Capability。

最小权限需要阶段化收缩
   初始化阶段可短暂保留 Mount、Network、BPF 或设备配置所需权限；进入稳定运行前应删除不再需要的 Effective、Permitted 与 Bounding 位，并验证重启路径不会重新注入。

关键路径
--------

Capability 检查：

::

   线程发起敏感操作
   → 进入具体对象或子系统路径
   → 确定目标 User Namespace
   → 调用 capable/ns_capable 类检查
   → 读取 current cred 的 Effective Set
   → 命中目标 CAP_* 则继续
   → 对象状态与 LSM 仍可拒绝

Exec 权限变换：

::

   旧 Permitted/Inheritable/Ambient/Bounding
   + 文件 Setuid/Setgid/File Capability
   + no_new_privs/Securebits/Ptrace/User Namespace
   → 计算新 Permitted
   → 计算新 Effective 与 Ambient
   → 构造新 Credential
   → commit_creds
   → 新程序按新集合运行

阶段化最小权限：

::

   列出初始化与运行期操作
   → 定位真实 CAP_* 检查点
   → 初始化阶段保留必要位
   → 完成 Mount、Network、Device 等配置
   → 删除不再需要的 Effective/Permitted
   → 收缩 Bounding 与 Ambient
   → 设置 no_new_privs、LSM 与 Seccomp

权限失败诊断：

::

   strace 固定失败系统调用
   → 读取 CapInh/CapPrm/CapEff/CapBnd/CapAmb
   → 确认当前与目标 User Namespace
   → 在源码中定位 required CAP_*
   → 检查 File Capability 与 Exec 来源
   → 对齐 LSM、Seccomp 和 Audit 证据

概念辨析
--------

* Effective 与 Permitted：Effective 决定当前检查结果；Permitted 表示当前可保留或启用的上限。
* Inheritable 与 Ambient：前者参与 Exec 组合；后者允许受约束地跨普通 Exec 保留权限。
* Bounding 与当前权限：Bounding 主要限制未来获得，不等于立即清空现有 Effective。
* File Capability 与 Setuid-root：前者授予指定能力；后者进入更宽的 Root 兼容语义。
* Capability 与隔离：Capability 负责授权，Namespace 负责视图，Cgroup 负责资源，LSM/Seccomp 继续收紧。

本章结论
--------

Capability 是带 User Namespace 范围的内核授权位；正确设计必须同时控制当前 Effective、Exec 来源、Bounding 上限与运行阶段，而不是把“容器内 Root”或某个配置字符串当作完整权限证明。