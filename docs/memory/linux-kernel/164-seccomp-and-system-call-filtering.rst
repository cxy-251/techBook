第164章：Seccomp 与系统调用过滤
===============================

本章必须记住
------------

#. Seccomp 的核心作用是缩小进程可触达的系统调用接口面。
#. 它在系统调用进入具体内核实现前，根据 Syscall Number、Architecture、Instruction Pointer 和最多六个参数值决定处置动作。
#. Seccomp 过滤的是 Syscall ABI 入口，不是文件、Socket、Inode 等对象级权限。
#. Seccomp 不能替代 DAC、Capability、LSM、Namespace、Cgroup 或文件系统布局。
#. 一个 Syscall 被 Seccomp 允许后，具体实现仍会继续执行参数、对象、Capability 和 LSM 检查。
#. 一个 Syscall 被 Seccomp 拒绝时，具体 Syscall 主体通常不会执行。
#. Seccomp 的工程价值是让漏洞利用后的进程只能调用工作负载真正需要的内核入口。
#. 最小攻击面设计应从真实运行所需 Syscall 集合开始，而不是从“允许所有再封几个危险调用”开始。
#. Seccomp 状态跟随线程，并可继承到子进程和 ``execve()`` 后的新程序镜像。
#. 已安装的 Seccomp 限制是单向收紧，普通进程不能撤销已有 Filter。
#. 多个 Filter 可以叠加，内核按动作优先级和组合规则决定最终结果，精确规则以目标 UAPI 为准。
#. Seccomp 主要有 Strict Mode 与 Filter Mode。
#. ``SECCOMP_MODE_STRICT`` 使用内核固定的极小 Syscall 集，适合输入输出 fd 已准备好的简单计算任务。
#. Strict Mode 过于狭窄，无法满足现代多线程、网络、动态链接和复杂 Runtime 的普通需求。
#. ``SECCOMP_MODE_FILTER`` 使用 Classic BPF 风格 Filter 对 ``struct seccomp_data`` 做判断。
#. Filter Mode 是浏览器、容器、服务 Sandbox 和最小权限进程的主流模式。
#. 用户态可通过 ``seccomp()`` Syscall 或 ``prctl(PR_SET_SECCOMP, ...)`` 安装状态，具体推荐接口依版本和库而定。
#. 无特权线程安装 Filter Mode 通常必须先设置 ``no_new_privs``，或在相关 User Namespace 中具备足够权限。
#. ``no_new_privs`` 保证后续 ``execve()`` 不会通过 Setuid、Setgid 或 File Capability 获得新特权。
#. ``no_new_privs`` 是单向状态，普通线程设置后不能清除。
#. Filter 输入 ``struct seccomp_data`` 至少包含 ``nr``、``arch``、``instruction_pointer`` 与 ``args[6]``。
#. Filter 必须同时检查 Architecture 与 Syscall Number，避免不同 ABI 使用相同编号造成绕过。
#. x86_64、x32、兼容 32 位和其它体系结构的 Syscall 表不同，不能只按名称生成一个不带 Arch 的编号规则。
#. Filter 看到的是参数数值，不应直接解引用用户指针读取路径字符串或复杂结构体。
#. 不能读取用户指针内容是重要安全边界，可避免基于可变用户内存做策略产生 TOCTOU。
#. Seccomp 可以检查 fd、Flags、Command Number、长度等整数参数，但参数语义仍需按 ABI 和位宽解释。
#. 对 Pointer 参数只比较地址值通常没有稳定业务意义，也不能证明其指向内容安全。
#. Syscall Multiplexer、Ioctl、BPF Command、Socket Option 等单一入口可承载大量操作，只按 Syscall 名允许可能仍暴露较大攻击面。
#. 对 ``ioctl``、``bpf``、``prctl``、``fcntl``、``clone`` 等入口可按 Command/Flags 做更细参数过滤，但维护复杂度和兼容性随之增加。
#. Filter 返回值是 ``SECCOMP_RET_*`` Action 与可选 Data 的组合。
#. ``SECCOMP_RET_ALLOW`` 允许 Syscall 继续进入内核实现。
#. ``SECCOMP_RET_ERRNO`` 不执行 Syscall 主体，并向用户态返回指定 Errno。
#. ``SECCOMP_RET_TRAP`` 通常触发 ``SIGSYS``，由进程信号处理路径观察。
#. ``SECCOMP_RET_KILL_THREAD`` 终止当前线程。
#. ``SECCOMP_RET_KILL_PROCESS`` 终止整个线程组，适合出现即代表策略突破的入口。
#. ``SECCOMP_RET_TRACE`` 把处置交给 Ptrace Tracer，行为依 Tracer 和内核版本，不能当作普通拒绝。
#. ``SECCOMP_RET_LOG`` 记录事件并允许 Syscall 继续执行，适合观测而不是阻断。
#. ``SECCOMP_RET_USER_NOTIF`` 把请求送给用户态 Supervisor，由其决定继续、返回值或代理操作。
#. User Notification 适合容器 Broker、兼容层和受控代理，但引入新的高权限控制面和竞态边界。
#. Supervisor 收到通知时，目标线程通常被阻塞等待处置。
#. User Notification 不能天然安全代理所有 Pointer 参数；用户内存和 Task 状态可能在通知期间变化。
#. 设计 Broker 时应优先使用稳定 fd、Pidfd、Addfd 等正式机制，并按目标内核 UAPI 处理对象身份。
#. ``CONTINUE`` 一类通知处置会让原 Syscall 在目标线程中继续，可能产生 TOCTOU，必须谨慎使用。
#. Filter Action 有优先级；多个 Filter 结果不是简单“最后一个生效”。
#. 规则生成器必须理解 Action 优先级、Data 截断和返回值编码。
#. Filter 安装成功只说明内核接受规则，不说明策略覆盖完整，也不说明应用能正常运行。
#. Filter 安装失败要区分权限、``no_new_privs``、程序无效、长度、Flags、不支持 Action 和线程同步失败。
#. Seccomp Filter 使用的是受限 BPF 过滤模型，不等同于通用 eBPF Program/Map/Helper 体系。
#. 不应把 Seccomp BPF 与 XDP/Tracing eBPF 的 Program Type、Map 和 Attach 语义混用。
#. Filter 必须保证所有控制流返回有效 Action。
#. 安装 Filter 的成本主要在配置阶段；运行期每个 Syscall 都要执行过滤逻辑，因此热路径规则应短且有序。
#. 常见 Syscall 应优先走快速 Allow 分支，极少命中的复杂规则放在后面，以降低平均开销。
#. 过长线性 Allowlist 会增加每个 Syscall 成本，生成器可使用跳转树或优化布局，但必须保持可审计性。
#. Syscall 频率远高于进程启动频率，微小每调用成本也会被放大。
#. 安全策略不能只按开发环境 ``strace`` 一次输出生成，错误路径、Signal、DNS、Locale、Dynamic Loader、Thread 和故障恢复会调用额外入口。
#. 建立 Allowlist 应覆盖正常路径、启动、Reload、Shutdown、OOM、Crash Handler、日志轮转和升级。
#. 动态链接程序在 Exec 后早期需要文件、内存映射、随机数、线程本地存储和权限查询相关 Syscall。
#. Filter 安装过早会阻止初始化；安装过晚会留下较大的攻击窗口。
#. 常见顺序是先建立 Namespace、Mount、fd、Network 和资源，再 Drop Capability，设置 ``no_new_privs``，最后安装运行期 Filter。
#. 多阶段 Sandbox 可在初始化后追加更严格 Filter，例如关闭 ``openat``、``execve`` 或网络创建入口。
#. 后续追加 Filter 只能进一步限制，不能恢复早期误删的 Syscall。
#. 多线程程序需要确认 Filter 是否覆盖线程组。
#. ``SECCOMP_FILTER_FLAG_TSYNC`` 一类标志用于同步线程组 Filter，安装可能因线程状态不兼容而失败。
#. 只给一个线程安装 Filter 会让同进程其它线程保留更大 Syscall 面，可能成为绕过路径。
#. 子线程创建和 Exec 的继承规则必须纳入策略测试。
#. Fork/Clone 被允许后，子 Task 通常继承 Seccomp 状态，不能假设新进程重新获得默认接口面。
#. Exec 不清除 Seccomp，因此目标程序及动态加载器必须兼容已有规则。
#. Filter 是否允许 ``seccomp``、``prctl`` 影响后续是否能继续收紧，但不能用它解除已有规则。
#. 容器 Runtime 通常在容器 Init 进程 Exec 前安装 OCI Seccomp Profile。
#. OCI/YAML Profile 是管理意图，真实运行状态要通过目标 Task、Audit 和失败行为验证。
#. Profile 中 ``SCMP_ACT_ERRNO``、``KILL``、``LOG``、``NOTIFY`` 等高层动作需映射到目标内核支持的 Seccomp Action。
#. Runtime、Libseccomp 与 Kernel 版本不同会影响 Syscall 名称解析、Action 支持和参数比较能力。
#. 新内核增加 Syscall 后，Default Allow + Denylist 策略可能意外允许新入口。
#. Default Deny + Explicit Allowlist 对新 Syscall 更保守，但升级兼容成本更高。
#. 安全关键 Sandbox 通常偏向 Default Deny，并维护经过测试的允许集合。
#. 容器通用 Profile 常为兼容性采用较宽规则，不能自动视为应用最小权限。
#. Seccomp 不理解路径，因此无法表达“只允许打开 /srv/data”。
#. 文件路径与对象策略应由 Mount Namespace、只读 Rootfs、fd 预打开、DAC 或 LSM 完成。
#. Seccomp 不理解 TCP 目的地址或 Socket 生命周期，只能限制相关 Syscall 和部分整数参数。
#. 网络访问策略应由 Network Namespace、Netfilter、Cgroup/BPF、LSM 或应用 Broker 补充。
#. Seccomp 不限制 CPU、内存和 I/O 消耗；Cgroup 负责资源统计与限制。
#. Seccomp 不改变 UID/GID 或 Capability；Credential 与 User Namespace 负责身份和授权。
#. Syscall 返回 ``EPERM`` 不一定来自 Seccomp，也可能来自 Capability、LSM 或对象状态。
#. ``SIGSYS``、进程突然终止、Audit ``SECCOMP`` Record 和 Runtime 日志是 Seccomp 拒绝的重要线索。
#. ``strace`` 可能看到 Syscall 返回指定 Errno；KILL Action 下可能只看到信号或进程消失。
#. ``/proc/<pid>/status`` 中 ``Seccomp``、``Seccomp_filters`` 和 ``NoNewPrivs`` 等字段可提供运行状态，字段随版本变化。
#. ``Seccomp: 2`` 常表示 Filter Mode，但脚本应按目标 Procfs 文档解释。
#. 目标进程退出后无法再读取其 Procfs 状态，故障采集应保留 Audit、Core/Signal 和 Runtime 事件。
#. Audit ``SECCOMP`` Record 可记录 Architecture、Syscall、Code、PID、Comm 等，具体字段依版本。
#. 没有 Audit Record 不表示没有 Filter，可能是 Action、Audit 配置、Rate Limit 或日志权限所致。
#. ``SECCOMP_RET_LOG`` 是否真正记录还受内核 Audit 配置与 Action Logging 控制。
#. 诊断第一步找到失败 Task 的宿主 PID、Architecture、Syscall Number 和参数。
#. 第二步确认 ``NoNewPrivs``、Seccomp Mode、Filter 数和线程组覆盖。
#. 第三步读取 Runtime/OCI Profile，确认默认动作与匹配规则。
#. 第四步按 Architecture 映射 Syscall Number，检查最先匹配的规则与返回 Action。
#. 第五步查询同一时间窗口的 Audit ``SECCOMP``、``SIGSYS`` 和应用日志。
#. 第六步确认请求若被允许，后续是否仍会被 Capability/LSM 拒绝。
#. 修复不能简单把 Default Action 改成 Allow，应只添加应用确实需要的入口与参数范围。
#. 对陌生 Syscall 的兼容修复前，应确认它由哪个库、线程、错误路径或攻击链触发。
#. 将 Filter 临时改为 LOG 可帮助收集调用集，但 LOG 模式不提供原有阻断，必须在受控环境使用。
#. User Notification Supervisor 是安全边界，必须最小权限、验证请求、处理目标退出和通知 ID 复用。
#. Supervisor 崩溃、fd 关闭或响应超时会影响被监管线程，应设计明确失败策略。
#. Filter/Listener fd 生命周期、Fork 继承和传递需要显式管理。
#. Teardown 时普通进程退出即可释放 Seccomp 状态；长期 Supervisor 还要关闭 Listener、停止新请求并处理在途通知。
#. 精确 Action、Flags、Procfs 字段、Syscall 表和通知 UAPI 具有版本差异。
#. 稳定源码阅读顺序是：Arch Syscall Entry → Secure Computing Check → Filter Chain → Action → Syscall Implementation 或拒绝路径 → Audit/Signal/Notification。

必背路径
--------

Filter Mode 安装：

::

   进程完成需要特权的初始化
   → Drop 不再需要的 Capability
   → 设置 no_new_privs
   → 构造带 Architecture 检查的 Seccomp Filter
   → seccomp/prctl 提交 Filter
   → 内核验证程序和 Flags
   → 发布到当前线程或 TSYNC 线程组
   → 后代 Fork/Exec 继承限制

系统调用处置：

::

   用户执行 syscall 指令
   → Architecture Entry 解析 nr 与 args
   → 检查当前 Task Seccomp 状态
   → 执行全部 Filter
   → 组合最高优先级 Action
   → ALLOW: 进入具体 Syscall
   → ERRNO/TRAP/KILL/TRACE/LOG/NOTIFY: 执行对应处置

拒绝诊断：

::

   固定宿主 PID 与时间窗口
   → 记录 Arch、Syscall Number、Args、Errno/Signal
   → 读取 /proc/PID/status 的 Seccomp/NoNewPrivs
   → 对照 Runtime Profile 与 Filter 默认动作
   → 查询 Audit SECCOMP Record
   → 判断是否在对象访问前被阻断
   → 只添加最小必要规则

安全 Sandbox 组合：

::

   Namespace 缩小可见资源
   → Mount/预打开 fd 缩小对象集合
   → Cgroup 限制资源
   → Drop Capability
   → LSM 约束对象访问
   → no_new_privs
   → Seccomp 缩小 Syscall 面
   → Audit 记录拒绝与异常

必须区分
--------

* Seccomp 与 LSM：Seccomp 过滤 Syscall ABI 入口；LSM 在真实内核对象访问点执行策略。
* Strict Mode 与 Filter Mode：Strict 是固定极小集合；Filter 可按 Syscall、Arch 和整数参数返回多种 Action。
* ``ERRNO`` 与 ``KILL``：前者让应用按错误路径继续；后者把调用视为严重策略违规并终止执行单元。
* Filter 安装成功与 Sandbox 正确：安装只证明规则合法，业务兼容、覆盖范围和绕过风险仍需测试。
* Syscall 名称与稳定 ABI：同名 Syscall 在不同 Architecture/ABI 上编号可能不同，规则必须先验证 Arch。

一句话结论
----------

Seccomp 通过在系统调用入口执行单向过滤，把进程可触达的内核接口缩成最小集合；它负责入口面，不负责对象级授权和资源隔离。
