第165章：Audit、攻击面与安全可观测性
===================================

本章必须记住
------------

#. Linux Audit 是安全事件证据层，用于记录谁在什么时间通过哪个内核入口对哪个对象执行了什么动作，以及结果为何允许或拒绝。
#. 安全策略只有同时具备阻断能力与可解释运行证据，才能被调试、验证和长期维护。
#. Audit 不是安全策略本身；DAC、Capability、LSM、Seccomp 等机制负责决策，Audit 负责记录已进入审计路径的事件。
#. Audit 也不是应用日志；它描述内核看到的主体、对象、系统调用、权限和返回值。
#. 完整排障要把应用请求 ID、Runtime 日志、Audit Event、内核对象和策略版本连接起来。
#. 一次安全事件经常由多条 Audit Record 组成，而不是一行日志。
#. 同一 Event ID 下的 ``SYSCALL``、``PATH``、``CWD``、``EXECVE``、``AVC``、``SECCOMP`` 等 Record 共同描述一次事件。
#. 分析时必须先按 Event ID 聚合完整 Record，再解释单个字段。
#. ``SYSCALL`` Record 常包含 Architecture、Syscall Number、Success、Exit、PID、PPID、Comm、Exe、UID 与 Audit UID。
#. ``PATH`` Record 常包含路径、Inode、Device、Name Type 和对象索引。
#. ``CWD`` Record 提供相对路径解释所需的当前工作目录。
#. ``EXECVE`` Record 可记录执行参数片段，具体可见范围和截断受版本与规则影响。
#. SELinux 等 LSM 可产生 ``AVC`` 或模块专用 Record，描述 Subject Context、Target Context、Class 和 Requested Permission。
#. Seccomp 可产生 ``SECCOMP`` Record，描述 Architecture、Syscall、Action/Code 和 Task 身份。
#. Capability 拒绝、User Namespace、Device、BPF 和其它安全事件可能使用不同 Record Type，精确类型以目标 UAPI 为准。
#. Audit Record 中相同 PID/Comm 不足以证明同一事件，必须优先使用 Event ID 和时间。
#. PID 可在 Task 退出后复用，长期关联应加入 Boot ID、Timestamp、Exec、Cgroup/Container ID 和业务 Generation。
#. ``auid``/Login UID 追踪用户登录身份，通常不同于当前 ``uid``、``euid`` 或容器内 UID。
#. Audit UID 的价值是让进程经过 sudo、su 或 Credential 变化后仍保留原始登录主体线索。
#. 服务和容器进程可能没有普通登录会话，``auid`` 可为未设置值，不能据此否定事件有效。
#. ``uid``、``euid``、``fsuid`` 等字段描述不同 Credential 维度，应按 Record 定义解释。
#. ``comm`` 是短进程名，可能被修改或截断；``exe`` 指向执行映像路径，但 Namespace 和 Deleted File 会影响显示。
#. Pathname 是人类可读线索，Device+Inode 更接近文件对象身份。
#. Rename、Hard Link、Bind Mount、OverlayFS 和 Mount Namespace 会让同一对象拥有多个路径或不同视图。
#. 容器内路径与宿主 Audit 路径不一定一致，需要结合 Mount Namespace、Overlay Layer 和 Rootfs 解析。
#. Syscall Number 必须与 ``arch`` 字段一起解释，不同体系结构和兼容 ABI 的编号不同。
#. ``exit`` 为负值时通常编码 ``-errno``；应转换为对应错误而不是直接当作返回数据。
#. Audit Event 表示内核记录了该动作，不自动说明业务请求是否最终成功。
#. 一个 Syscall 允许后，后续用户态处理仍可失败；一个 Syscall 被拒绝也可能被应用重试或降级。
#. Audit Rule 决定哪些候选事件被记录、过滤或排除。
#. Rule 可按 Syscall、Architecture、路径/目录、权限、UID/AUID、结果、对象标签和其它字段过滤。
#. Exit Filter 常在 Syscall 退出时结合结果和对象信息决定记录。
#. Filesystem Watch/Directory Rule 适合观察对象范围，Syscall Rule 适合观察接口面，二者语义不同。
#. ``-S`` 选择 Syscall，``-F`` 选择字段条件，``-k``/Key 为规则提供便于查询的标签；具体语法以 Audit Userspace 版本为准。
#. Architecture 条件应在 Syscall 名称解析前明确，避免只记录一个 ABI。
#. 只记录失败事件可降低日志量，但会失去成功访问基线；只记录成功事件也无法解释拒绝。
#. 高价值对象可同时记录成功和失败，高频路径应使用精确过滤避免日志风暴。
#. Rule Key 是管理标签，不是安全对象身份；重用 Key 会把不同规则结果混在一起。
#. Audit Rule 写入成功只表示内核接受配置，不表示目标 Workload 已命中，也不保证日志后端正常持久化。
#. ``auditctl -l`` 显示当前规则，配置文件和 Runtime 实际规则必须同时核对。
#. 发行版可在启动时从多个规则目录合并配置，最终内核规则顺序和内容应以运行状态为准。
#. Audit Subsystem 有 Enabled、Failure Mode、Rate Limit、Backlog Limit 等运行参数。
#. Backlog 满或用户态 Audit Daemon 跟不上时，事件可能丢失、Rate-limit 或触发 Failure 策略。
#. “没有 Audit 记录”不能直接推出“事件没有发生”，必须检查 Audit 是否启用、规则是否匹配、Backlog/Lost 计数和权限。
#. Audit 丢失是安全观测完整性问题，生产系统必须监控 Lost、Backlog 和 Daemon 状态。
#. 将 Audit Failure Mode 配置为 Panic 会把审计不可用提升为系统可用性风险，只适合明确合规场景。
#. Auditd 负责从内核接收、写盘、轮转和转发事件；内核与用户态队列形成完整数据链。
#. Auditd 退出、磁盘满、日志轮转错误和插件阻塞都会破坏证据链。
#. 日志持久化、时间同步、权限和防篡改属于用户态运维边界，不由内核 Audit 自动保证。
#. ``ausearch`` 可按 Event、PID、AUID、Key、Message Type、时间等聚合查询。
#. ``aureport`` 等工具提供报表视图，原始 Record 仍是精确字段解释依据。
#. 查询工具版本可能影响字段解码和显示，原始日志与 Kernel UAPI 是最终边界。
#. SELinux 拒绝通常应把 ``AVC``、``SYSCALL`` 和 ``PATH`` 放在同一事件中读取。
#. ``scontext`` 表示主体安全上下文，``tcontext`` 表示目标上下文，``tclass`` 表示对象类别。
#. ``denied { read write open ... }`` 表示策略请求权限，不等于 Unix Mode 字符串。
#. ``permissive=1`` 常表示策略本应拒绝但处于 Permissive 语境；必须区分记录与实际阻断。
#. AppArmor 日志通常提供 Profile、Operation、Name、Requested Mask 和 Denied Mask，字段布局不同于 SELinux。
#. LSM Stacking 下同一操作可能经过多个模块；日志通常突出拒绝者，不列出所有放行模块。
#. ``/sys/kernel/security/lsm`` 用于确认当前安全模块列表和顺序。
#. Seccomp ``ERRNO``、``TRAP``、``KILL``、``LOG``、``USER_NOTIF`` 的运行表现不同，Audit Record 必须与应用 Errno/Signal 共同解释。
#. ``SECCOMP_RET_LOG`` 允许 Syscall 继续执行，因此出现日志不表示被阻断。
#. ``ERRNO`` 会让 Syscall 主体不执行并返回指定错误，应用日志可能把它误判为普通权限失败。
#. ``KILL`` 类 Action 可能只留下 ``SIGSYS``、退出和 Audit 证据，应用没有机会写正常错误日志。
#. User Notification 还要检查 Supervisor 决策和 Listener 生命周期，Audit 只覆盖其中一部分。
#. Capability 检查失败时应确认具体 ``CAP_*``、Effective Set、User Namespace 与目标对象范围。
#. 将所有 ``EPERM`` 都解释为缺少 Capability 是错误的，LSM、Seccomp、对象状态也可返回同类错误。
#. Attack Surface 是进程可触达的内核入口、对象、权限、全局资源与后续横向路径的集合。
#. 缩小攻击面不是只部署一个机制，而是组合多层边界。
#. Namespace 缩小进程可见的 PID、Mount、Network、IPC、User 和其它资源视图。
#. Cgroup 控制 CPU、内存、I/O、PIDs 和设备/资源消耗，防止单一 Workload 拖垮系统。
#. Credential 与 UID/GID 定义主体身份和对象基础权限关系。
#. Capability 删除不必要的高风险内核授权位。
#. LSM 把强制策略附着到真实对象访问点。
#. Seccomp 缩小允许进入的 Syscall ABI 集合。
#. Read-only Rootfs、预打开 fd、设备最小化和 Network Policy 缩小可访问对象集合。
#. Audit 把拒绝、异常和策略使用变成可复盘证据。
#. 一层允许不等于整体允许，一层隔离也不等于完整 Sandbox。
#. Namespace 不限制资源；Cgroup 不隐藏对象；Seccomp 不判断路径；Capability 不表达业务对象策略。
#. 组合机制时应确保边界互补，而不是重复配置后留下未覆盖层。
#. 最小权限顺序通常是：只暴露必要对象 → 设置 Namespace/Cgroup → Drop Capability → 设置 LSM → ``no_new_privs`` → Seccomp。
#. 初始化阶段可能需要更大权限，运行阶段应进一步收紧并记录策略 Generation。
#. 安全策略变更应可回滚、可测试、可关联到部署版本。
#. Audit Event 应包含或外部关联 Policy Version、Container Image、Executable Hash、Config Generation 和业务实例。
#. 没有版本信息时，同一条拒绝在策略升级前后很难复盘。
#. 生产观测应优先记录高价值拒绝、特权操作、身份变化、策略加载和关键对象修改。
#. 对每个普通读写 Syscall 全量审计会产生巨大成本和噪声，可能反过来影响系统可用性。
#. 规则设计要平衡合规覆盖、调查价值、性能、存储和隐私。
#. Audit Log 可能包含路径、参数、用户名和安全上下文，访问权限与保留周期必须受控。
#. 逐条日志告警会产生风暴，应先按 Event 聚合，再按主体、对象、策略和时间窗口关联。
#. 安全检测应区分策略性预期拒绝、应用 Bug、攻击探测和基础设施错误。
#. 某服务持续尝试被 Seccomp 禁止的 Syscall，可能是版本升级引入的新依赖，也可能是利用行为。
#. 某 LSM 拒绝突然出现，可能是对象 Label 漂移、Mount 变化、策略升级或执行 Domain 变化。
#. 同一拒绝数量下降不一定表示问题修复，可能是 Rule 被删除、日志丢失或 Workload 不再到达该路径。
#. 安全指标必须同时监控事件量、Audit Lost、Daemon 健康、规则数量和 Workload 流量基线。
#. 调查第一步固定绝对时间窗口、宿主 PID/Container ID、Boot ID 与 Audit Event ID。
#. 第二步聚合同一 Event 的全部 Record。
#. 第三步还原 Subject：AUID、UID/EUID、Credential、Capability、Namespace、LSM Context/Profile。
#. 第四步还原 Object：Path、Device、Inode、Class、Label、Mount Namespace 和设备/Socket 状态。
#. 第五步还原 Operation：Arch、Syscall、Args、Requested Permission、Seccomp Action。
#. 第六步确认第一个拒绝机制和最终用户态结果。
#. 第七步对照策略仓库和部署 Generation，判断拒绝是否预期。
#. 第八步做最小修复并用相同事件场景验证。
#. 不应仅依据日志生成工具的自动建议直接放宽 SELinux/AppArmor 策略。
#. 自动建议可能把攻击尝试或错误路径永久加入允许集合。
#. 修复前应确认业务确实需要该对象和操作，并评估更小的 fd Broker、Mount、Capability 或 Syscall 方案。
#. 任何安全例外都应有 Owner、理由、范围、期限和回归测试。
#. Audit 规则与策略自身也属于敏感控制面，修改操作应被授权和记录。
#. 攻击者若能关闭 Audit、修改规则或删除日志，证据可信度会降低；应限制相关 Capability 与文件权限。
#. Kernel Lockdown、Immutable Audit 配置和远程日志可提高防篡改能力，具体部署需权衡可恢复性。
#. 时间戳依赖系统时间，跨主机调查还需 NTP/PTP、Boot Time 和单调时间线辅助。
#. Audit 的同步写盘策略会影响性能与持久性，不能假设日志出现即已稳定落盘。
#. 系统崩溃或磁盘故障可能丢失最近事件，关键环境应设计远程转发与完整性验证。
#. Audit 不是 Packet Trace、Scheduler Trace 或应用 Trace，性能/因果调查仍需其它观测工具补充。
#. Tracepoint/eBPF 可补充低层时序，但不能替代受控、持久和结构化的安全审计语义。
#. 精确 Record Type、Field、Rule List、Rate Limit 和工具输出具有版本与发行版差异。
#. 稳定源码阅读顺序是：Security Decision/Event Source → Audit Context → Rule Filter → Record Collection → Netlink Queue → Auditd → Search/Correlation。

必背路径
--------

Audit 事件生成：

::

   Task 发起 Syscall 或安全操作
   → 内核建立/使用 Audit Context
   → 对象路径产生 SYSCALL/PATH/LSM/SECCOMP 等 Record
   → Audit Rule 与过滤器决定是否记录
   → 多条 Record 共享同一 Event ID
   → 进入内核 Backlog/Netlink
   → Auditd 接收、写盘和转发

安全拒绝还原：

::

   固定时间窗口与 Event ID
   → 聚合全部 Record
   → 从 SYSCALL 读取 Arch、入口、返回值和 Task
   → 从 PATH/CWD 还原对象
   → 从 AVC/LSM 读取 Subject、Target、Class、Permission
   → 从 SECCOMP 读取过滤动作
   → 对照 Credential/Capability/Namespace
   → 找到第一个拒绝机制

攻击面收缩：

::

   最小 Rootfs、Mount、Device 与预打开 fd
   → Namespace 隔离资源视图
   → Cgroup 限制资源
   → 最小 UID/GID 与 Capability
   → LSM 约束对象访问
   → no_new_privs
   → Seccomp 限制 Syscall 面
   → Audit 监测拒绝和异常

Audit 完整性检查：

::

   查看 Audit Enabled/Failure/Rate/Backlog 状态
   → 确认 Auditd 正常
   → 监控 Lost 与 Backlog
   → 验证规则已加载
   → 触发受控测试事件
   → ausearch 聚合完整 Record
   → 验证写盘、轮转和远程转发

必须区分
--------

安全决策与 Audit 记录
   LSM、Seccomp、Capability 等负责允许或拒绝；Audit 负责记录进入审计路径的证据。

Event 与单条 Record
   一次事件常由多条 Record 共同描述，必须按 Event ID 聚合。

AUID 与当前 UID
   AUID 追踪登录身份；当前 UID/EUID/FSUID 描述运行时 Credential。

日志为空与事件未发生
   Audit 未启用、规则未匹配、Backlog 丢失或权限问题都可能导致看不到记录。

记录了 Seccomp 与阻断了 Syscall
   LOG Action 可记录后继续执行；必须结合 Action、返回值和进程状态判断。

一句话结论
----------

Linux 安全可维护性的关键，是用 Audit 把主体、对象、入口、策略和结果连接成可复盘事件，再用多层最小权限机制共同缩小真实攻击面。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 33，Credentials, Capabilities, Permissions, LSM, Seccomp, and Audit；
* AIBook 章节：Chapter 165，Audit, Attack Surface, and Security Observability；
* 源文件：``docs/LinuxK/Part_33_Credentials_Capabilities_Permissions_LSM_Seccomp_and_Audit/Chapter_165_Audit_Attack_Surface_and_Security_Observability.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_33_Credentials_Capabilities_Permissions_LSM_Seccomp_and_Audit/Chapter_165_Audit_Attack_Surface_and_Security_Observability.md>`_。