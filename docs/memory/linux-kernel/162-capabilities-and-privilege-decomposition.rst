第162章：Capabilities 与特权拆分
================================

本章必须记住
------------

#. Linux Capability 把传统 UID 0 的大块特权拆成按操作族检查的独立授权位。
#. 读特权失败时，不应只问“是不是 root”，而应问目标路径检查哪个 Capability、主体在哪个 User Namespace 中拥有它。
#. Capability 是 Per-thread Credential 属性，保存在 ``struct cred`` 的多组 Capability Set 中。
#. 内核实际授权点通常调用 ``capable()``、``ns_capable()``、``file_ns_capable()`` 或子系统封装，精确接口依版本而定。
#. ``capable(CAP_X)`` 关注当前 Credential 在默认相关 User Namespace 中是否拥有 Capability。
#. ``ns_capable(user_ns, CAP_X)`` 把授权绑定到目标 User Namespace，容器和 Namespace 管理路径必须按此语境读取。
#. 同一个线程可在自己的 User Namespace 中拥有 Capability，同时在 Initial User Namespace 中没有对应权力。
#. 容器内 UID 0 与宿主全局 Capability 是不同概念。
#. ``CAP_NET_RAW``、``CAP_NET_ADMIN``、``CAP_SYS_PTRACE``、``CAP_DAC_OVERRIDE``、``CAP_BPF`` 等分别覆盖不同操作族。
#. 拥有 ``CAP_NET_ADMIN`` 不表示自动拥有 ``CAP_NET_RAW``，Capability 之间通常不能互相替代。
#. ``CAP_SYS_ADMIN`` 覆盖范围极大，应视为接近“新 root”的高风险授权，而不是普通管理开关。
#. 新增更窄 Capability 的工程目的通常是把原本堆积在 ``CAP_SYS_ADMIN`` 下的权力拆小。
#. Capability 检查只回答该授权位是否有效，不自动绕过对象状态、LSM、Seccomp、Mount 或子系统限制。
#. Capability 允许后，LSM 仍可拒绝；Seccomp 也可能在进入具体对象路径前阻止 Syscall。
#. 当前线程的 Capability 至少要区分 Permitted、Effective、Inheritable、Bounding 与 Ambient 五组集合。
#. Effective Set 是当前内核权限检查直接使用的集合。
#. Permitted Set 是当前线程可保持或启用 Capability 的上限资格集合。
#. Inheritable Set 是跨 ``execve()`` 参与继承计算的候选集合。
#. Bounding Set 限制后续通过 File Capability 等路径能够获得的 Capability 上限。
#. Ambient Set 允许有限 Capability 跨非特权 ``execve()`` 传播。
#. “某 Capability 出现在 Permitted”不表示当前 ``capable()`` 一定成功；检查通常看 Effective。
#. “某 Capability 不在 Effective”也不表示它永远无法启用；还要看 Permitted 与 Credential 变换权限。
#. Inheritable 本身通常不直接通过当前访问检查，它要与可执行文件的 File Inheritable 集合共同参与 Exec 计算。
#. Bounding Set 主要限制未来获得路径，不一定立即清除已经存在的 Effective 位。
#. Ambient Capability 必须同时属于 Permitted 与 Inheritable，精确约束以目标内核为准。
#. 执行 Setuid、Setgid 或带 File Capability 的特权文件通常会清空 Ambient Set，防止权限来源叠加失控。
#. ``execve()`` 是 Capability 集合重新计算的核心边界。
#. Exec 前线程 Capability、File Capability、Bounding、Ambient、``no_new_privs``、Ptrace 和 User Namespace 共同决定新 Credential。
#. 新程序开始执行后，权限已经进入新的 ``struct cred``，后续对象检查只读取新 Credential。
#. File Capability 存储在可执行文件的 ``security.capability`` 扩展属性中。
#. File Capability 的核心价值是让一个程序获得有限授权，而不必成为完整 Setuid-root 程序。
#. 设置 File Capability 通常需要 ``CAP_SETFCAP``，并受文件系统、Mount 和 User Namespace 支持限制。
#. File Capability 不等于文件运行后“自动拥有所有权限”，只参与 Exec 时指定 Capability 集合计算。
#. File Permitted、File Inheritable 和 File Effective Bit 具有不同作用，不能把 ``getcap`` 的字符串当作单一布尔值。
#. Bounding Set 会裁剪 File Permitted 进入新 Permitted 的路径。
#. ``no_new_privs`` 会阻止后续 Exec 通过 Setuid、Setgid 或 File Capability 获得新特权。
#. ``NoNewPrivs: 1`` 是单向承诺，普通线程不能清除；它常作为 Seccomp 与沙箱安装前提。
#. Setuid-root 兼容语义仍可能影响 Capability 集合，但现代源码应按 Exec Credential 变换读取，而不是只按 EUID 0 推断。
#. Root 特殊处理还受 Securebits 影响。
#. Securebits 可控制 UID 0 的 Capability 兼容、Setuid Fixup、Keep Caps 等行为，具体位和锁定位需按目标内核确认。
#. ``PR_SET_KEEPCAPS`` 一类机制可以让线程在 UID 切换时暂时保留 Permitted Capability，仍需显式建立 Effective 状态。
#. Bounding Set 通常可通过 ``prctl(PR_CAPBSET_DROP, ...)`` 单向删除 Capability。
#. 一旦从 Bounding Set 删除，后代通常不能通过 File Capability 重新获得该位。
#. Ambient Set 也通过 ``prctl`` 一类接口管理，具体 API 和前提具有版本边界。
#. ``capset()`` 修改 Capability Set 时受当前 Permitted、Inheritable、Securebits 和 User Namespace 权限约束。
#. 普通线程不能凭空把任意位加入 Permitted 或 Effective。
#. Capability 属于线程，用户态线程库可能为进程级 API 协调线程组成员；内核最终仍检查当前 Task Credential。
#. 多线程程序中只修改一个线程的 Capability 可能造成同一进程不同线程权限不同。
#. 服务管理器和容器 Runtime 通常在 Exec 前统一设置 Bounding、Permitted、Effective、Inheritable 和 Ambient。
#. Capability Dropping 应尽早完成，但必须晚于初始化阶段真正需要的特权操作。
#. 初始化后仍保留高风险 Capability 会扩大漏洞利用后的内核攻击面。
#. 先使用 Capability 完成 Mount、Network、BPF 或设备设置，再删除不再需要的位，是常见收缩顺序。
#. 删除 Capability 前要确认异步 Helper、子进程和后续 Resume/Reload 是否仍需该权力。
#. Capability 只能表达内核预定义的操作族，不能替代业务级授权模型。
#. ``CAP_DAC_OVERRIDE`` 可绕过很多普通文件 DAC 检查，但不自动绕过 LSM、只读文件系统或不可变属性。
#. ``CAP_DAC_READ_SEARCH`` 主要覆盖读取与目录搜索相关 DAC 绕过，不能当作任意写权限。
#. ``CAP_CHOWN``、``CAP_FOWNER``、``CAP_FSETID`` 分别覆盖不同文件所有权和元数据操作。
#. ``CAP_SYS_PTRACE`` 参与 Ptrace、跨进程内存和部分进程检查，仍受 Yama/LSM 和 Dumpable 状态约束。
#. ``CAP_NET_ADMIN`` 覆盖接口、路由、TC、部分 Socket Option 与网络 Namespace 管理，授权范围很大。
#. ``CAP_NET_RAW`` 允许 Raw/Packet Socket 等路径，可能绕过应用层网络约束。
#. ``CAP_BPF``、``CAP_PERFMON``、``CAP_CHECKPOINT_RESTORE`` 是较新拆分，目标内核不一定支持或独立使用。
#. BPF 能力还可能依赖 ``CAP_SYS_ADMIN`` 兼容、Unprivileged BPF Sysctl、LSM、Lockdown 和 Program Type。
#. Load Module、Kexec、Mount、Namespace 等高风险操作常涉及多个 Capability 或额外安全策略。
#. 查看 `/proc/<pid>/status` 中 ``CapInh``、``CapPrm``、``CapEff``、``CapBnd``、``CapAmb`` 可得到线程集合位图。
#. 位图必须按目标内核 Capability 编号解码，不能把十六进制值凭记忆解释。
#. ``capsh --decode``、``getpcaps``、``getcap`` 可辅助观察，但内核事实仍是目标 Task Credential 与目标文件 xattr。
#. ``getcap`` 输出为空可能来自没有 xattr、文件系统不支持、Namespace 映射不匹配或读取权限问题。
#. Namespaced File Capability 会记录 Root UID 映射语义，不能机械按宿主普通 File Capability 解释。
#. OverlayFS、Copy-up、镜像构建和归档工具可能丢失或改变 ``security.capability`` xattr。
#. 容器镜像中声明 Capability 不等于 Runtime 最终保留；Runtime Bounding/Effective 与 LSM 仍可收缩。
#. Kubernetes、Systemd 或 OCI 配置是管理意图，必须回读目标进程 ``/proc`` 状态和 File xattr 验证。
#. Capability 权限失败通常表现为 ``EPERM``，但同一 Errno 还可能来自 LSM、Seccomp、对象状态或 Namespace 规则。
#. ``strace`` 只能找到失败 Syscall 和 Errno，不能单独证明缺少哪个 Capability。
#. Audit、LSM Log、源码检查点和最小实验共同决定真实拒绝原因。
#. 搜索源码时应从失败系统调用进入具体对象路径，定位 ``capable``/``ns_capable`` 的 Capability 常量。
#. 仅在整个源码树搜索 ``CAP_SYS_ADMIN`` 会得到大量命中，必须结合调用链和目标对象缩小范围。
#. Capability 检查可能封装在子系统 Helper 中，例如 Network、Mount、Perf、BPF 或 IPC 专用函数。
#. 一次操作可能检查多个 Capability；满足前一个检查不表示后续检查一定通过。
#. Namespace 作用域也可能随目标对象不同而变化，例如 Network 操作常关联目标 ``struct net`` 的 User Namespace。
#. 判断授权应记录：当前 User Namespace、目标对象所属 User Namespace、目标 Capability 和 Effective Set。
#. 容器内进程拥有 ``CAP_SYS_ADMIN`` 仍不等于可以操作宿主 Initial User Namespace 的 Mount、Device 或 Kernel Global 对象。
#. User Namespace 降低部分管理操作的全局影响，但并非所有内核子系统都允许 Namespace-scoped 管理。
#. Capability 不是隔离机制；它只是授权位，资源可见性仍由 Namespace，资源限制仍由 Cgroup 管理。
#. Capability 也不是审计机制；是否被使用和拒绝需要 Audit、Trace 或子系统事件提供证据。
#. 最小权限设计应先列出工作负载所需 Syscall 与对象，再映射到具体 Capability，而不是从“大概需要 root”开始。
#. 优先选择更窄 Capability，避免使用 ``CAP_SYS_ADMIN`` 作为万能修复。
#. 能通过普通 DAC、fd 传递、专用 Broker 或设备接口完成的操作，不应无条件授予全进程 Capability。
#. Broker 模型可以让高权限进程执行少量受验证操作，低权限 Worker 通过受限 IPC 请求。
#. File Capability 适合权限与特定可执行文件绑定；Ambient 适合非特权 Exec 链保留少量权限；两者风险模型不同。
#. Setuid-root 程序把完整 Root 兼容路径交给可执行文件，通常比窄 File Capability 攻击面更大。
#. 但 File Capability 也会让任何能执行该文件的主体获得指定权力，因此文件可写性、完整性和 Mount 来源必须受保护。
#. 可执行文件被非信任用户替换时，File Capability 会把攻击者代码提升到授权位；部署必须保证 Inode 与 xattr 完整性。
#. Dropping Capability 后应验证目标操作失败、普通业务仍成功、子进程和 Restart 不会重新获得旧权限。
#. 进程重启可能由 Service Manager 再次注入 Capability，运行时临时删除不是永久策略修改。
#. Capability 集合变更、Exec 与 Credential 发布都涉及引用和并发规则，内核模块不能直接修改共享 ``cred``。
#. 精确 Capability 编号、检查点、Securebits 和 Exec 变换具有内核版本差异。
#. 稳定源码阅读顺序是：Operation → Object/User Namespace → Required Capability → Current Effective → Exec/File Source → Bounding/NoNewPrivs → LSM/Seccomp。

必背路径
--------

Capability 检查：

::

   用户发起特权操作
   → 进入具体对象或子系统路径
   → 确定目标 User Namespace
   → 调用 capable/ns_capable 类检查
   → 读取 current cred 的 Effective Set
   → 命中目标 Capability 则继续
   → 后续对象状态和 LSM 仍可拒绝

Exec 权限变换：

::

   旧 Credential 的 Permitted/Inheritable/Ambient/Bounding
   + 可执行文件 Setuid/Setgid/File Capability
   + no_new_privs/Securebits/Ptrace/User Namespace
   → 构造新 Credential
   → 计算新 Permitted
   → 计算新 Effective 与 Ambient
   → commit_creds
   → 新程序按新集合接受权限检查

最小权限收缩：

::

   列出初始化和运行期所需操作
   → 映射每个操作的真实 Capability 检查点
   → 初始化阶段临时保留必要位
   → 完成 Network/Mount/Device 等设置
   → 删除不再需要的 Effective/Permitted/Bounding 位
   → 设置 no_new_privs 和 Seccomp/LSM
   → 验证 Restart 与故障路径

运行时诊断：

::

   strace 找到失败 Syscall
   → 读取 /proc/PID/status 的五组 Capability
   → 确认 PID/User Namespace
   → 定位源码所需 CAP_* 常量
   → 检查 File Capability 与 Exec 来源
   → 检查 Bounding/NoNewPrivs
   → 检查 LSM/Audit/Seccomp

必须区分
--------

* Permitted 与 Effective：Permitted 是可启用资格上限；Effective 才是当前大多数 Capability 检查使用的集合。
* Bounding 与当前权限：Bounding 主要限制未来 Exec 获得路径，不一定立即删除已有 Effective 位。
* File Capability 与 Ambient Capability：前者由可执行文件 xattr 注入 Exec 计算；后者由线程在非特权 Exec 链中传播。
* 容器内 Capability 与宿主全局 Capability：授权必须带 User Namespace 和目标对象所有权语境判断。
* Capability 允许与最终成功：对象状态、DAC、LSM、Seccomp、Lockdown 和子系统规则仍可能拒绝。

一句话结论
----------

Capability 把 Root 权力拆成按对象路径检查的授权位，但每个位仍是真实内核权力，必须结合 Effective Set、Exec 来源、Bounding 和 User Namespace 精确判断。
