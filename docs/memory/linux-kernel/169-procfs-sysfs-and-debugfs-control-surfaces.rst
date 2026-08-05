第169章：procfs、sysfs 与 debugfs 控制面
=========================================

本章必须记住
------------

#. Linux 把大量观察和控制接口表现成虚拟文件，但相同的 ``read``/``write`` 形式不代表相同作用域、稳定性或风险。
#. 看到一个可写文件时，必须先问：它属于哪个文件系统、绑定哪个内核对象、调用哪个回调、承诺什么 ABI。
#. procfs 主要暴露进程状态、系统统计和部分运行时控制。
#. sysfs 主要投影 Kobject/Device Model 中的对象层级与属性。
#. debugfs 主要服务内核开发、诊断、实验和内部状态暴露。
#. ``/proc/sys`` 虽位于 procfs 树中，语义上是 sysctl 运行策略控制面。
#. 控制文件不是磁盘文件；VFS 操作最终进入该虚拟文件系统提供的回调。
#. 文件内容只是文本协议或触发参数，真正状态变化发生在内核回调和下游子系统中。
#. 路径是第一条线索，回调、对象、作用域和生命周期才是最终语义。
#. procfs 的 ``/proc/<pid>`` 通常绑定 Task、MM、FD、Namespace 或进程相关状态。
#. ``/proc/<pid>/clear_refs`` 一类写入口是对特定地址空间执行控制动作，不是全局 VM 调优。
#. ``/proc/<pid>/oom_score_adj`` 影响目标进程 OOM 选择倾向，不等于设置 Memory Cgroup 限制。
#. 访问 ``/proc/<pid>`` 时，PID Namespace、Ptrace 权限、Credential、Hidepid 和 LSM 会影响可见性与写权限。
#. 进程退出后 ``/proc/<pid>`` 可消失；已打开 fd 和对象引用的具体行为依接口实现。
#. PID 可能复用，长期自动化不能只凭数字把旧对象和新 Task 视为同一实体。
#. procfs 中系统级文件可能是全局、Namespace-scoped 或子系统级状态，不能统一归类。
#. ``/proc/net`` 常按当前 Network Namespace 展示网络状态。
#. ``/proc/meminfo``、``/proc/vmstat`` 等提供整机或内核级统计，具体字段和单位具有版本边界。
#. ``/proc/sys`` 通过 sysctl 表项把路径连接到内核变量或 Handler。
#. 普通 procfs 文件常通过 ``proc_ops``、``seq_file`` 或专用读写回调实现。
#. ``seq_file`` 解决迭代输出和大文本读取，不改变接口的作用域和 ABI 承诺。
#. Procfs 写 Handler 必须解析用户输入、验证权限和对象状态，并处理并发和生命周期。
#. 写入返回成功只说明 Handler 接受请求，不证明异步动作完成。
#. procfs 中一部分文件是正式 UAPI，一部分只是管理接口或观测格式，稳定程度必须逐文件查文档。
#. 不能因为路径在 ``/proc`` 就假设格式永久稳定。
#. sysfs 的目录通常来自 ``kobject`` 层级。
#. 注册的 Device、Driver、Bus、Class、Module 等对象可在 sysfs 中拥有目录和属性。
#. ``/sys/devices`` 是设备对象的规范物理/逻辑层级主视图。
#. ``/sys/class``、``/sys/bus``、``/sys/block`` 常通过 Symlink 提供功能或匹配视图。
#. 解释 sysfs 属性前应使用 ``readlink -f`` 找到规范对象路径。
#. Sysfs Attribute 通常由 ``struct attribute`` 及具体包装类型的 ``show``/``store`` 回调实现。
#. ``DEVICE_ATTR``、``DRIVER_ATTR``、``BUS_ATTR`` 等宏把属性名、模式和对象回调连接起来。
#. sysfs 倾向一个文件表达一个值，并使用 ASCII 文本协议。
#. 这一风格约束不表示所有值都只有一个 Token；具体格式仍以 ABI 文档为准。
#. 属性属于对象，控制范围通常由目录对应的 Device/Driver/Queue/Module 决定。
#. ``/sys/class/net/eth0/mtu`` 控制 ``eth0`` 对应的 Network Device 属性，不是全局网络 MTU。
#. ``/sys/block/sda/queue/scheduler`` 控制对应 Block Queue，不代表所有磁盘调度策略。
#. ``/sys/module/<name>/parameters`` 是模块参数当前变量视图，不等同于具体设备实际状态。
#. 属性 ``store`` 可只更新字段，也可触发复杂重配置；必须读回调源码确认。
#. Store 返回写入长度通常表示请求被接受，不表示设备异步恢复、Reset 或 Training 已完成。
#. 对象注销后 Sysfs 目录会被撤销；用户态必须处理设备热拔插和路径消失。
#. Sysfs 删除可阻止新查找，但已进入回调或持有对象引用的路径仍需生命周期同步。
#. 内核必须确保 ``show``/``store`` 执行时宿主对象有效。
#. 用户态不能长期缓存 Sysfs 层级路径并假设设备永不重新枚举。
#. PCI BDF、USB Port、Netdev Name 和 Block Device Name 都可能在重启、热插拔或规则变化后改变。
#. 稳定身份应结合 Serial、WWN、Firmware ID、Devlink、Udev 属性或管理层 Generation。
#. Sysfs Attribute 是否属于稳定 ABI 应查 ``Documentation/ABI`` 和子系统文档。
#. 已文档化 ``stable`` ABI 与 ``testing``/``obsolete`` 接口的兼容承诺不同。
#. 用户态不应依赖未文档化的中间目录、Symlink 布局或内核私有字段。
#. Udev 和 Libudev 提供更高层设备事件与属性访问，适合减少对路径布局的直接耦合。
#. Debugfs 的目标是让开发者快速暴露内部状态、计数器、调试命令和实验开关。
#. Debugfs 理论上不承诺稳定用户态 ABI。
#. 文件名、目录、格式、命令和副作用可随内核版本、驱动重构和配置变化。
#. 生产业务逻辑不应把 Debugfs 当成长期控制协议。
#. Debugfs 可输出复杂多行状态、二进制 Blob、寄存器 Dump、队列和内部对象，不受 Sysfs 单值约束。
#. 灵活性越高，越需要源码、版本和访问权限约束。
#. ``debugfs_create_file`` 等 Helper 把 File Operations 和私有数据连接到调试节点。
#. 驱动可用 ``debugfs_create_bool``、``u32``、``x64`` 等简单 Helper 暴露变量。
#. 简单变量可写不等于修改安全；驱动仍需考虑锁、硬件状态和 Teardown。
#. Dynamic Debug 的 Control 文件常位于 Debugfs 或 Proc/Control 视图，具体挂载与版本需确认。
#. Debugfs 可能未挂载、未编译或被安全策略隐藏，文件缺失不表示功能代码不存在。
#. 容器通常不应获得宿主 Debugfs 写权限。
#. Debugfs 可能暴露寄存器、地址、内存和控制命令，是高价值攻击面。
#. Lockdown、LSM、Mount Permission 和 Capability 可限制访问。
#. Tracefs 与 Debugfs 是不同文件系统；现代 Tracing 接口通常位于 ``/sys/kernel/tracing``。
#. 不能把 Tracefs 的相对稳定 Event 机制和 Debugfs 私有节点统一视为同一 ABI。
#. Configfs 也不同：它通常通过用户创建目录/对象来驱动内核对象配置生命周期。
#. Securityfs、Cgroupfs、BPFfs、Pstore 等各有独立对象和协议边界。
#. “所有控制都像文件”是 VFS 统一入口，不表示这些文件系统可以互换。
#. 判断接口 Scope 时，先找挂载点和 Superblock 类型。
#. 再找路径对应的进程、Namespace、Kobject、Device、Module 或 Debug Private Data。
#. 再找读写回调和下游状态变换。
#. 最后查 ABI 文档、权限、生命周期和回滚能力。
#. ``stat -f``、``findmnt -T`` 可帮助确认路径实际属于哪个文件系统。
#. Bind Mount 可把 Debugfs/Sysfs 子树呈现在其它路径，不能只按字符串前缀判断文件系统类型。
#. Mount Namespace 可让同一路径在不同进程视图中指向不同 Mount 或完全不可见。
#. 只读 Bind Mount 能阻止普通写入，但不改变宿主对象本身的全局作用域。
#. Overlayfs 不应用于覆盖 procfs/sysfs/debugfs 的内核对象语义。
#. 写接口前要保存旧值、输入格式、目标对象身份、Kernel Version 和当前状态。
#. 只读观察也可能有成本，例如生成巨大 Dump、遍历锁或读取硬件寄存器。
#. 高频轮询 Sysfs/Procfs 会产生系统调用、格式化、锁和设备访问开销。
#. 监控应优先使用稳定统计接口、批量 Netlink、Perf/Event 或专用 Telemetry。
#. Debugfs 大型 Dump 应在受控窗口使用，避免污染 Cache、日志和时序。
#. 某些读操作会清零计数、消费事件或触发硬件访问，不能假设 Read 永远无副作用。
#. 文档必须明确 Read-to-clear、Write-one-to-clear 或 Snapshot 语义。
#. 对可写控制文件，必须区分 Set Value 与 Command Trigger。
#. Set Value 文件表达持续状态；Command 文件可能每次写入都执行一次动作。
#. 向 Reset/Rescan/Remove/Inject 文件重复写入可能重复执行破坏性操作。
#. 写 ``1`` 后文件读回 ``0`` 可能表示一次性 Trigger，而不是写入失败。
#. Sysfs 的 ``remove``、``rescan``、``unbind``、``reset`` 等控制会改变对象生命周期。
#. 写入 Driver Unbind 前必须确认上层使用者、DMA、Mount、Network 和管理面后果。
#. Debugfs Fault Injection 节点可故意制造失败，只应在隔离测试环境使用。
#. Procfs ``drop_caches`` 一类控制不会“释放所有应用内存”，且会污染性能实验。
#. 任何控制接口都不能脱离子系统语义按文件名猜测效果。
#. 权限判断包括文件 Mode、Mount Read-only、Credential、User Namespace、Capability、LSM 与 Lockdown。
#. Root 能写不表示写入符合硬件状态机或业务安全。
#. 用户态工具可能在写入后做额外验证，直接 ``echo`` 绕过工具检查可能更危险。
#. 优先使用子系统正式管理工具，例如 ``ip``、``ethtool``、``tc``、``nvme``、``devlink``、``sysctl``。
#. 正式工具可处理 Netlink、ExtAck、对象身份和事务语义，通常优于直接写低层文件。
#. 直接文件写入适合明确文档化的简单接口或故障诊断。
#. 自动化写入前应校验目标路径是预期文件系统、对象和 ABI 版本。
#. 不能仅检查文件存在就写入；同名节点在不同设备/版本上语义可能不同。
#. 使用 Symlink 时应防止路径替换和设备重新枚举造成错误对象写入。
#. 可通过打开目录 fd、核对 Major:Minor/UEVENT/Serial 等方式绑定目标对象。
#. 安全控制接口应拒绝部分写、超长输入、非法状态和权限不足。
#. 内核回调必须正确使用 ``copy_from_user``、Kstrtox、锁和引用。
#. 回调返回错误前要保证没有留下半更新状态。
#. 可睡眠的 Store 不能在不允许睡眠的上下文中被调用，框架通常从进程上下文进入。
#. Store 与 Remove/Hotplug 并发时，需要对象锁、Device Lock 或其它生命周期协议。
#. Debugfs 私有数据在节点删除后不能过早释放，打开 fd 可能继续调用 File Operations。
#. ``debugfs_remove_recursive`` 撤销目录不自动等待所有自定义异步工作结束。
#. Procfs 自定义节点也要处理模块卸载、Open fd 和 ``seq_file`` 私有数据生命周期。
#. Sysfs 属性由 Kobject 引用与 Active Protection 协调，但驱动仍负责硬件和私有状态 Teardown。
#. Interface Removal、Object Removal 和 Memory Free 是不同边界。
#. 诊断写入不生效时，先检查实际 Mount 和 Namespace，再检查权限与 Handler Error。
#. 再检查写入是否只改变变量、是否需要对象重建或驱动 Reload。
#. 最后用真实对象状态、日志、事件和下游行为验证。
#. 诊断接口消失时，检查对象是否注销、模块是否加载、配置是否启用和 Mount 是否存在。
#. 版本升级前应列出生产依赖的 Procfs/Sysfs/Debugfs 节点，并按 ABI 级别分类。
#. 任何依赖 Debugfs 的生产自动化都应准备接口变化和完全缺失的回退方案。
#. 稳定接口优先级通常是：正式 Syscall/Netlink/Ioctl → 文档化 Sysfs/Procfs → 管理工具 → Debugfs 私有接口。
#. 精确文件、回调、ABI 状态和权限具有版本、配置、驱动与发行版差异。
#. 稳定源码阅读顺序是：Mount Type → Path Scope → Backing Object → Read/Write Callback → State Change → ABI Promise → Teardown。

必背路径
--------

控制文件识别：

::

   得到一个可写路径
   → findmnt/stat -f 确认文件系统类型
   → 解析 Symlink 到规范对象路径
   → 判断进程/Namespace/Kobject/Device/Module/Debug 私有对象
   → 找到 show/store/proc_ops/file_operations
   → 查文档化 ABI 与输入格式
   → 评估作用域、生命周期和回滚

Sysfs 写入：

::

   用户写对象 Attribute
   → VFS/Kernfs 找到 Kobject 与 Attribute
   → 检查权限和对象 Active 状态
   → 转换为具体 Device/Driver/Queue 对象
   → 调用 store Callback
   → 验证输入并修改字段或重配置硬件
   → 用实际对象状态验证结果

Debugfs 诊断：

::

   确认 CONFIG_DEBUG_FS 与挂载点
   → 核对 Kernel/Driver Version
   → 阅读创建节点和 File Operations 源码
   → 评估读取成本与写入副作用
   → 在受控窗口执行
   → 保存输出、时间和对象 Generation
   → 不把格式当作长期 ABI

对象退出：

::

   标记对象退出并阻止新控制请求
   → 删除 Procfs/Sysfs/Debugfs 可见节点
   → 等待在途回调和打开对象
   → 停止异步工作与硬件访问
   → 最后释放私有数据和宿主对象

必须区分
--------

procfs 与 ``/proc/sys``
   普通 procfs 文件可绑定进程或系统状态；``/proc/sys`` 是 sysctl 策略表的文件视图。

Sysfs Class Path 与规范设备路径
   ``/sys/class`` 是功能视图，真实对象层级通常沿 Symlink 落到 ``/sys/devices``。

Sysfs 与 Debugfs
   Sysfs 面向对象属性并有 ABI 规范；Debugfs 面向调试，通常不承诺稳定格式。

Set Value 与 Command Trigger
   前者保存持续状态；后者每次写入都可能执行 Rescan、Reset、Remove 或 Fault Injection。

文件节点删除与对象释放
   撤销用户可见入口不等于回调、打开 fd、异步工作和宿主内存已经结束。

一句话结论
----------

虚拟控制文件的真正语义来自其背后的对象与回调：先识别文件系统和作用域，再判断 ABI、状态变化与生命周期。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 34，Kernel Parameters, Sysctl, Control Interfaces, and Runtime Tuning；
* AIBook 章节：Chapter 169，procfs, sysfs, and debugfs Control Surfaces；
* 源文件：``docs/LinuxK/Part_34_Kernel_Parameters_Sysctl_Control_Interfaces_and_Runtime_Tuning/Chapter_169_procfs_sysfs_and_debugfs_Control_Surfaces.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_34_Kernel_Parameters_Sysctl_Control_Interfaces_and_Runtime_Tuning/Chapter_169_procfs_sysfs_and_debugfs_Control_Surfaces.md>`_。