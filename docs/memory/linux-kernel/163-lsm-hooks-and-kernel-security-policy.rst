第163章：LSM Hook 与内核安全策略
================================

本章必须记住
------------

#. Linux Security Module（LSM）把安全策略检查放到内核真实对象访问路径中。
#. 用户态传入路径、进程名和参数；LSM 看到的通常是 ``cred``、``inode``、``file``、``task_struct``、``sock``、IPC、Key 或 BPF 对象。
#. LSM 的稳定价值是让安全策略跟随内核对象和操作，而不是只依赖用户态字符串。
#. LSM Framework 提供 Hook 基础设施，SELinux、AppArmor、Smack、TOMOYO、Landlock、Yama 等模块提供具体策略。
#. 一个 Hook 是内核对象路径主动调用的 ``security_*`` 包装接口。
#. Hook 参数通常包含主体、目标对象、访问掩码、创建状态或操作参数。
#. 授权类 Hook 通常返回 0 表示放行，返回负 Errno 表示拒绝。
#. 对象初始化类 Hook 可为新 Credential、Inode、File、Socket 等分配或初始化 Security Blob。
#. LSM 不是单一系统调用过滤器；它覆盖文件、进程、网络、IPC、Key、BPF、模块、Mount 等对象访问点。
#. 文件路径中常见 Path、Inode、File 三类 Hook，分别对应路径操作、文件系统对象和已打开文件状态。
#. 同一次 ``openat()`` 可在路径解析、Inode 权限、File 打开和后续读写阶段触发不同 Hook。
#. 只找到 ``security_inode_permission()`` 不代表已经覆盖该文件操作的全部安全检查。
#. Socket 路径可在创建、绑定、连接、监听、发送、接收和 Socket Option 等阶段触发不同 Hook。
#. Task 路径可在 Signal、Ptrace、Credential 变更、调度属性或进程关系上触发 Hook。
#. BPF、Perf、Key、Module 和 Kernel Read-file 路径也有专门安全接口，精确范围依版本与配置。
#. LSM Hook 通常位于内核已经确定目标对象和操作语义之后，因此比纯 Syscall Number 更接近真实授权对象。
#. Seccomp 在 Syscall 入口裁剪接口面；LSM 在对象访问点执行安全策略，两者不能互相替代。
#. DAC 和 Capability 是基础权限材料；LSM 可在它们允许后继续拒绝。
#. Landlock 等 LSM 只能继续收紧已有权限，不能把 DAC 或其它 LSM 已拒绝的操作改成允许。
#. 多个 LSM 可以同时启用并参与同一 Hook 链，这称为 LSM Stacking。
#. 对授权类 Hook，只要一个实际参与的 LSM 返回拒绝，最终访问通常失败。
#. 所有相关 LSM 都放行，只表示安全 Hook 阶段通过，后续对象状态和执行仍可能失败。
#. ``/sys/kernel/security/lsm`` 是观察当前活跃 LSM 与顺序的重要运行时接口。
#. 该文件缺失时应先检查 Securityfs 是否挂载、内核配置和访问权限。
#. 活跃列表只是模块顺序，不说明某个具体访问由哪条策略拒绝。
#. 诊断具体拒绝还要读取 Audit、内核日志、主体属性和模块专用工具。
#. LSM 选择和顺序受内核配置、``CONFIG_LSM``、启动参数和发行版策略影响。
#. 同一应用在不同发行版上可能经过不同 LSM 组合，不能从应用配置推断内核实际安全栈。
#. Capability LSM/基础能力检查通常总是安全栈的一部分，但精确内部组织随版本演进。
#. Security Blob 是 LSM 附着到内核对象上的私有安全状态。
#. 常见 Blob 宿主包括 ``cred``、``inode``、``file``、``super_block``、``task_struct`` 相关状态、``sock``、IPC、Key 和 BPF 对象。
#. Blob 可以保存 Security ID、Label、Profile 指针、Ruleset、缓存状态或其它模块私有数据。
#. Blob 生命周期必须跟随宿主对象创建、复制、发布和最终释放。
#. Credential Copy-and-commit 时，LSM 必须为新 ``cred`` 准备、复制并提交对应 Security Blob。
#. Inode Security State 可能来自文件系统扩展属性、Mount 选项、默认标签或模块内部计算。
#. File Security State 可保留打开阶段的安全上下文，支持后续 ``read``、``mmap``、``ioctl`` 等检查。
#. Security Blob 不是用户态稳定 ABI，结构与偏移可随内核版本和启用 LSM 变化。
#. 内核代码不应绕过 LSM Helper 直接解释其它模块 Blob。
#. SELinux 的核心读法是 Subject Context、Target Context、Object Class 与 Requested Permission。
#. SELinux 常把进程 Domain 与对象 Type 通过策略矩阵连接。
#. SELinux Inode Label 常来自 ``security.selinux`` xattr，具体显示和继承还受文件系统与 Mount 选项影响。
#. AVC 用于缓存 SELinux 访问决策；``avc: denied`` 是常见拒绝证据。
#. SELinux Enforcing 模式会执行拒绝；Permissive 模式通常记录本应拒绝的事件但允许继续，用于诊断而非长期关闭保护。
#. 单个 Domain 设为 Permissive 与整个系统 Permissive 是不同范围。
#. AppArmor 的核心读法是当前 Task Profile、目标路径/对象和请求操作。
#. AppArmor 是 Task-centered 策略，Profile 可包含文件、Capability、Network、Mount 和执行转换规则。
#. 路径重命名、Mount Namespace、Bind Mount 和 OverlayFS 会影响路径策略的实际对象关系。
#. AppArmor 日志中的 Profile、Operation、Name、Requested Mask 和 Denied Mask 是主要证据。
#. Smack 的核心读法是 Subject Label、Object Label 和访问位规则。
#. TOMOYO 的核心读法是 Domain、名称规则和程序执行造成的 Domain Transition。
#. Landlock 的核心读法是进程创建并叠加的 Ruleset、Handled Access 与对象规则。
#. Landlock 允许非特权进程限制自己和后代，通常要求 ``no_new_privs`` 或对应规则前提。
#. Landlock Ruleset 是单向收紧；普通进程不能解除已经施加给自己的限制。
#. Yama 主要提供 Ptrace 等进程关系的额外限制，常与其它主 LSM 一起堆叠。
#. 不同 LSM 的策略表达不同，但最终都落到内核 Hook 上返回允许或拒绝。
#. 不能用 SELinux 的标签模型解释 AppArmor Profile，也不能用 AppArmor 路径规则解释 Landlock Ruleset。
#. LSM Hook 的参数由具体访问点决定；同一个模块在不同 Hook 上可使用不同对象信息。
#. Path Hook 与 Inode Hook 的对象语义不同，路径操作可能依赖当前 Mount/Path，Inode Hook 更接近底层文件对象。
#. 已打开 File 的后续访问可能不再拥有原始用户路径字符串，因此 File Blob 和 Inode Label 更稳定。
#. Hard Link、Rename、Bind Mount 和 fd 传递说明对象策略不能只靠最初路径字符串维持。
#. LSM Label 与 UID/GID 是不同安全维度；相同 UID 的两个进程可处在不同 Domain/Profile。
#. 同一文件 Mode 允许访问，LSM Label 仍可拒绝。
#. Capability 允许高权限操作，LSM 仍可按 Domain、Profile 或规则限制该 Capability 的使用。
#. LSM Hook 本身不是审计日志；模块可通过 Audit Framework 记录拒绝和上下文。
#. 没有 Audit 记录不等于没有 LSM 检查，可能是日志策略、Rate Limit、Permissive 模式或模块输出路径不同。
#. Audit 记录也可能只展示最终拒绝模块，不能直接列出所有已放行模块。
#. ``/proc/<pid>/attr/current`` 一类接口可显示当前 LSM Subject 状态，精确文件和格式依模块。
#. SELinux 可用 ``ps -Z``、``ls -Z``、``matchpathcon``、``ausearch`` 等辅助观察。
#. AppArmor 可用 ``aa-status`` 和内核/Audit 日志观察 Profile 状态。
#. 工具输出是管理视图，内核事实仍由活跃 LSM、对象 Blob、Hook 参数和返回值决定。
#. LSM 拒绝常表现为 ``EACCES`` 或 ``EPERM``，具体 Errno 由 Hook 和调用路径决定。
#. 应用日志中的“Permission denied”无法区分 DAC、Capability、LSM、Seccomp 或只读对象状态。
#. ``strace`` 用于定位失败 Syscall、参数和 Errno；之后必须进入对象权限链继续判断。
#. 诊断第一步固定宿主 PID、失败 Syscall、目标对象和时间窗口。
#. 第二步读取 `/sys/kernel/security/lsm`，确认真实安全栈。
#. 第三步读取主体 Credential、User Namespace、Capability 和当前 LSM Subject/Profile。
#. 第四步解析目标对象的 Mount、Inode、Label、Path 与 File 状态。
#. 第五步查询同一时间窗口的 Audit/Kernel Log，寻找模块、Hook、Class、Permission 或 Profile 证据。
#. 第六步定位策略源文件或 Ruleset，确认拒绝是预期安全边界还是部署标签错误。
#. 不应通过关闭整个 LSM、设为全局 Permissive 或删除所有 Profile 作为长期修复。
#. 正确修复应缩小到具体 Subject、Object、Class/Operation 和必要权限。
#. 修改 SELinux Label 前应判断文件来自哪个文件系统、是否会被 Restorecon、Package 或容器重建覆盖。
#. 修改 AppArmor 路径规则前应确认真实 Mount Namespace、可执行路径和 Profile Transition。
#. Landlock 拒绝来自进程自己或祖先施加的 Ruleset，无法通过系统管理员外部“放宽”当前进程已进入的单向限制。
#. 多 LSM Stacking 下，修复一个模块后访问仍可能被另一个模块拒绝，必须重新收集完整证据。
#. LSM Policy Update 与对象 Cache/Label 的生效边界依模块而定，应验证旧进程、已打开 fd 和新对象。
#. 策略加载成功不表示所有对象标签正确，也不表示业务路径已经覆盖测试。
#. Policy Reload 可能改变运行中访问决策，生产系统应维护版本、回滚和 Audit Generation。
#. LSM Hooks 位于热路径时必须控制性能成本；AVC、Profile Cache 和静态分支等用于降低重复决策开销。
#. 安全缓存命中不改变策略语义；缓存失效和策略更新必须保证旧决策不会越过新策略生命周期。
#. 逐操作 Audit 可产生高日志量，规则和 Rate Limit 必须在可观测性与系统负载之间权衡。
#. LSM 初始化顺序发生在内核启动早期，部分模块无法在运行中任意卸载或重新排序。
#. 内核模块不能假设某个特定主 LSM 一定启用，应调用通用 ``security_*`` 接口。
#. 新增内核对象或敏感操作时，应在正确对象边界调用现有 LSM Hook 或设计新的正式 Hook。
#. 把 Hook 放得太早会缺少真实对象信息，放得太晚可能已经产生不可回滚副作用。
#. Hook 失败路径必须在对象发布、资源申请和用户可见状态之间正确回滚。
#. LSM Hook 允许也不代表对象生命周期自动安全；引用、RCU、锁和 Teardown 仍由宿主子系统负责。
#. 精确 Hook 名、参数、Blob 布局、Stacking 顺序和模块能力具有版本差异。
#. 稳定源码阅读顺序是：Syscall/Object Path → DAC/Capability → ``security_*`` Wrapper → Active Hook Chain → Module Blob/Policy → Audit → Return/Release。

必背路径
--------

文件访问安全链：

::

   用户发起 open/read/write/mmap
   → VFS 解析 Mount、Dentry、Inode 或已有 File
   → 检查对象状态、DAC 与 Capability
   → 调用对应 security_path/security_inode/security_file Hook
   → 遍历当前活跃 LSM
   → 每个模块读取 Subject 与 Object Security State
   → 任一拒绝则返回 Errno 并可生成 Audit
   → 全部放行后继续对象操作

Security Blob 生命周期：

::

   创建 Cred/Inode/File/Socket 等宿主对象
   → LSM 分配或初始化 Blob
   → 从 xattr、父对象或策略建立 Label/Profile 状态
   → Hook 在访问时读取 Blob
   → 对象复制/发布时复制或转移状态
   → 最后引用归零
   → LSM 释放 Blob

LSM 拒绝诊断：

::

   strace 找到失败 Syscall 与 Errno
   → cat /sys/kernel/security/lsm
   → 读取主体 Cred、Capability、Profile/Context
   → 解析目标 Mount/Inode/Label
   → 查询同一 Audit Event
   → 确认拒绝模块、Class/Operation 与规则
   → 做最小策略或标签修复

Stacking 判断：

::

   DAC/Capability 基础检查
   → LSM A Hook 返回 0
   → LSM B Hook 返回拒绝
   → 最终访问失败
   → 修复 B 后重新执行
   → 仍需检查其它 LSM 与后续对象状态

必须区分
--------

* LSM Framework 与具体安全模块：Framework 提供 Hook 和对象接入；SELinux、AppArmor、Landlock 等实现具体策略。
* Path、Inode 与 File Hook：三者分别对应路径关系、文件系统对象和已打开对象状态，信息边界不同。
* DAC/Capability 允许与 LSM 允许：基础权限通过后，强制策略仍可继续拒绝。
* Subject Label/Profile 与普通 UID：LSM 安全身份是独立维度，相同 UID 可有不同策略角色。
* Audit 记录与完整策略：Audit 是运行事件证据，不等于策略文件的完整内容，也不证明未记录路径没有检查。

一句话结论
----------

LSM 把强制安全策略钉在内核对象访问点上：最终授权取决于当前主体、真实目标对象、操作语义和全部活跃安全模块的共同结果。
