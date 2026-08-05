第168章：sysctl 作为运行时内核控制接口
======================================

本章必须记住
------------

#. sysctl 是 Linux 在系统运行中调整部分内核策略的正式控制接口。
#. ``/proc/sys`` 是 sysctl 的文件系统视图；点分名称 ``net.ipv4.ip_forward`` 对应 ``/proc/sys/net/ipv4/ip_forward``。
#. 读写 ``/proc/sys`` 不是普通磁盘文件 I/O，而是 VFS/procfs 把文本输入转交给内核 sysctl 表项与处理函数。
#. 一个 sysctl 表项通常包含名称、权限、数据位置、长度、处理函数以及可选范围约束。
#. ``struct ctl_table`` 是理解 sysctl 注册和处理关系的重要对象，精确字段随版本演进。
#. ``procname`` 决定文件名，``mode`` 决定基础访问权限，``proc_handler`` 负责文本读写和校验。
#. 通用处理函数可完成整数、字符串、位图或范围受限值的解析；复杂项可使用自定义处理函数。
#. 写入成功只说明内核接受了新值，不证明业务目标已经实现。
#. sysctl 控制的是后续进入子系统路径时采用的策略，不一定回溯重建所有已存在对象。
#. 某些参数立即影响所有后续操作，某些只影响新连接、新接口、新映射或下一次回收周期。
#. 读当前值必须在目标 Namespace 和目标系统上下文中完成。
#. 许多 ``net.*`` sysctl 按 Network Namespace 分片，容器内值和宿主 Initial Netns 值可以不同。
#. ``kernel.*``、``vm.*``、``fs.*`` 中多数项更接近整机或 Initial Namespace 策略，但精确作用域必须按文档确认。
#. 不能从目录名机械推断作用域；必须找注册位置和数据对象。
#. ``/proc/sys/kernel`` 常承载通用内核、崩溃、调试、安全与性能策略。
#. ``/proc/sys/vm`` 常承载内存分配、回收、写回、Overcommit、OOM 与虚拟内存限制。
#. ``/proc/sys/fs`` 常承载 VFS 资源上限、文件句柄和文件系统安全策略。
#. ``/proc/sys/net`` 常承载协议栈、接口默认值、路由、Socket 与 Network Namespace 策略。
#. 目录族只是定位入口，具体语义必须读取目标参数官方文档和源码。
#. ``kernel.panic`` 一类参数控制 Panic 后策略，不等于当前系统已发生 Panic。
#. ``kernel.perf_event_paranoid`` 一类参数改变非特权 Perf 访问边界，不能只按性能开关理解。
#. ``vm.swappiness`` 表达交换 I/O 与文件页回收的相对成本倾向，不是“使用 Swap 的百分比”。
#. ``vm.dirty_*`` 参数共同影响脏页阈值与 Writeback 节奏，不能孤立解释单个值。
#. Ratio 参数按内存规模计算，有些 Byte 参数与 Ratio 参数互斥或具有优先级。
#. ``vm.max_map_count`` 限制 VMA 数量，不直接等于进程可用虚拟内存总量。
#. ``fs.file-max`` 是系统 File Handle 资源边界之一，不等于单进程 ``RLIMIT_NOFILE``。
#. ``fs.nr_open``、``file-max`` 与进程软硬限制属于不同层级。
#. ``net.ipv4.ip_forward`` 控制 IPv4 转发策略；值为 1 不表示 Route、Firewall 和接口配置已经允许转发。
#. 网络参数常存在 ``all``、``default``、具体接口三层，三者组合规则需逐项查文档。
#. ``default`` 常影响以后创建的接口，不一定重写现有接口值。
#. ``all`` 的含义并非所有参数都统一采用“覆盖全部接口”，不能凭名称推断。
#. sysctl 文件权限只是第一层；Credential、User Namespace、Mount、LSM、Lockdown 还可拒绝写入。
#. 容器中 ``/proc/sys`` 可能只读、被掩盖或只暴露 Namespace-scoped 参数。
#. 容器内 Root 通常不能修改宿主全局 VM/Kernel 参数。
#. 写入返回 ``EACCES``/``EPERM`` 常表示权限或安全策略拒绝。
#. 写入返回 ``EINVAL`` 常表示格式、范围、状态或 Handler 语义不接受。
#. 写入文本中的换行、空格、多个值和数组格式由具体 Handler 解释。
#. 不能假设 Shell ``echo`` 与 ``sysctl -w`` 在错误报告和转义上完全相同。
#. ``sysctl -w key=value`` 与直接写 ``/proc/sys`` 最终进入同类内核控制路径。
#. ``sysctl -a`` 可产生大量输出、触发读取副作用或权限错误，不适合在高压系统无差别频繁执行。
#. 精确观察应只读取目标参数和直接相关统计。
#. sysctl 运行时修改通常在当前 Boot 内立即生效，重启后会恢复默认或启动配置值。
#. 持久化由用户态配置管理完成，常见来源为 ``/etc/sysctl.conf`` 与 ``/etc/sysctl.d/*.conf``。
#. 配置文件存在不证明当前内核值已应用；必须回读 ``/proc/sys``。
#. 当前值正确不证明重启后会持久；必须检查实际加载顺序和配置源。
#. systemd-sysctl、发行版脚本、容器 Runtime 或网络管理器可能在不同阶段重复写同一参数。
#. 多个配置文件冲突时，加载顺序和文件名优先级由用户态实现决定，不是内核 sysctl 决定。
#. 临时 ``sysctl -w`` 可能稍后被配置管理器覆盖。
#. 调优记录应包含当前值、配置来源、写入时间、写入主体和后续覆盖者。
#. 参数默认值可能由编译配置、架构、启动参数或 Namespace 创建逻辑决定。
#. 新 Network Namespace 的默认值可能从当前模板复制，而不是动态引用宿主后续变化。
#. Namespace 创建时间对 ``default`` 类网络参数尤其重要。
#. sysctl 注册可以是静态或动态的；模块或子系统卸载后对应文件可消失。
#. 文件不存在可能来自内核版本、配置未启用、模块未加载、Namespace 不支持或接口已删除。
#. 自动化应把“文件不存在”与“值不符合预期”分开处理。
#. 不应为兼容脚本盲目创建普通文件替代缺失的 ``/proc/sys`` 节点。
#. sysctl UAPI 的稳定程度依具体项而异；文档化参数一般较稳定，调试/实验项可能变化。
#. 参数单位必须确认：页、字节、KB、毫秒、Jiffies、百分比、数量或布尔值不能混用。
#. 时间参数的单位在不同子系统甚至相似名称之间可能不同。
#. 参数边界值 ``0``、``-1``、``max`` 或空字符串常有特殊语义，不能按普通数值线性理解。
#. 写入极大值即使通过范围检查，也可能造成内存占用、延迟、队列或安全风险。
#. 修改 VM 参数前应观察 Memory Pressure、Reclaim、Writeback、Swap、OOM 和 PSI。
#. 修改 Network 参数前应观察 Route、Socket、Packet Drop、Retransmit、Netfilter 和接口统计。
#. 修改 FS 参数前应观察 File Handle、VFS 错误、进程限制和真实工作负载。
#. 修改 Kernel/Security 参数前应评估攻击面、审计、Perf、Crash 和多租户影响。
#. sysctl 调优不能替代应用、硬件和容量问题修复。
#. 增大 Queue/Backlog 可能把 Drop 转化为更高延迟和内存占用。
#. 增大 Timeout 可能延迟错误暴露，不能修复丢失 Completion 或硬件卡死。
#. 降低安全限制可能让工具恢复工作，却扩大所有进程的攻击面。
#. 参数之间可相互作用，例如 Dirty Threshold、Writeback Interval、Memory High 和 Device Queue 共同决定写入尾延迟。
#. 一次改变多个 sysctl 会破坏因果归因。
#. 修改前必须记录业务负载和目标指标，而不是只保存旧参数值。
#. 修改后要同时验证目标收益和副作用。
#. 写入 ``ip_forward=1`` 后，应验证实际 Packet 是否进入 Forward Path、Route/Netfilter 是否允许以及 Counter 是否变化。
#. 写入 ``swappiness`` 后，应观察 Reclaim、Swap I/O、Major Fault、PSI 和业务延迟，不只看 Swap Used。
#. 写入 Dirty 参数后，应观察 Dirty/Writeback、Block Queue、I/O PSI 和读写尾延迟。
#. 参数效果可能有滞后，需要按子系统周期和对象生命周期定义观察窗口。
#. 观察窗口过短会误判未生效，过长又可能被负载和其它变更污染。
#. 生产修改必须有明确停止条件和回滚值。
#. 回滚写回旧值不一定立即恢复旧对象状态，需验证队列、连接、缓存和硬件是否回到预期。
#. 某些参数具有不可逆或仅影响新对象的效果，回滚可能需要重建对象或重启。
#. 修改前应判断参数的 Scope、Lifetime、Reversibility 和 Persistence。
#. Scope 回答影响整机、Namespace、接口、Cgroup 还是进程。
#. Lifetime 回答立即读取、周期读取、对象创建时复制还是启动期固定。
#. Reversibility 回答写回旧值是否足够。
#. Persistence 回答重启、Namespace 重建和模块重载后如何恢复。
#. sysctl 写入是管理动作，应通过变更记录、最小权限和审计保护。
#. 允许容器任意写宿主 ``/proc/sys`` 会把全局策略控制面暴露给工作负载。
#. 某些参数可通过 User Namespace 范围授权，但不能假设所有 sysctl 都 Namespace-safe。
#. LSM 可对 sysctl 文件或相关对象继续限制。
#. Audit 可记录部分 sysctl 写入和主体信息，规则覆盖和日志容量需单独配置。
#. 读源码时先搜索 sysctl 名称或 ``ctl_table`` 注册点。
#. 找到表项后，记录 Data 指针、Handler、Extra Min/Max、注册 Namespace 和注销路径。
#. 再搜索子系统运行路径如何读取该数据或触发静态分支。
#. 如果 Handler 有副作用，应分析写入失败和部分更新语义。
#. 动态注册表需要确认对象/Namespace 销毁时如何 ``unregister_sysctl_table``。
#. 打开的 procfs fd 与表项注销存在生命周期同步，不能在自定义代码中释放表内存过早。
#. Sysctl Handler 必须正确处理用户缓冲区、偏移、部分读写和并发。
#. 自定义 Handler 不应绕过范围、权限和锁规则。
#. 并发写入同一参数时，最终值和副作用顺序由锁与 Handler 决定。
#. 读取值是某一时刻快照，不证明参数在整个故障窗口保持不变。
#. 诊断应记录时间戳并监控参数漂移。
#. 配置管理系统应对目标值、实际值和来源进行持续核对，而不是高频盲写。
#. 高危参数应在 Staging 使用真实负载回放和故障注入测试。
#. 内核升级前应检查参数是否废弃、改名、单位变化或默认值变化。
#. 启动日志中的 Unknown Sysctl 来自用户态加载不存在参数，与 Kernel Command Line Unknown Parameter 不同。
#. 配置工具忽略错误可能让部分参数应用、部分失败，必须检查退出状态和日志。
#. 稳定排障顺序是：确认参数存在 → 确认作用域 → 回读当前值 → 找注册与 Handler → 找运行使用点 → 对齐统计和行为。
#. 精确 Sysctl 文件、Handler、Namespace 范围和默认值具有内核版本与发行版差异。
#. 稳定源码阅读顺序是：``/proc/sys`` Name → ``ctl_table`` → Permission/Handler → Data/Side Effect → Subsystem Read → Runtime Evidence → Unregister。

必背路径
--------

Sysctl 读写：

::

   用户读取或写入 net.ipv4.ip_forward
   → 转换为 /proc/sys/net/ipv4/ip_forward
   → VFS 进入 procfs
   → proc_sysctl 查找 ctl_table
   → 检查 mode、Credential、Namespace 与 LSM
   → 调用 proc_handler
   → 文本解析、范围验证、更新变量或执行副作用
   → 后续网络路径按新策略运行

持久化：

::

   在受控窗口临时 sysctl -w
   → 回读当前值并验证效果
   → 把确认值写入正式 sysctl.d 配置
   → 记录加载顺序与配置 Owner
   → 重启或重载后再次回读 /proc/sys
   → 验证没有被其它管理器覆盖

安全调优：

::

   记录业务与内核基线
   → 查目标参数文档、单位、作用域和版本
   → 保存原值与回滚命令
   → 一次修改一个参数
   → 观察目标指标、错误与副作用
   → 无改善立即回滚
   → 有改善后验证重启持久性

源码定位：

::

   搜索 sysctl 名称
   → 找 ctl_table 注册位置
   → 确认数据指针、Handler、Min/Max 与 Namespace
   → 查子系统读取或副作用路径
   → 查注销和生命周期
   → 用运行统计验证实际影响

必须区分
--------

运行时值与持久化配置
   ``/proc/sys`` 是当前内核事实；``sysctl.d`` 是下次或重载时的用户态意图。

写入成功与目标改善
   Handler 接受值不代表性能、可靠性或安全目标实现，必须用相关路径指标验证。

全局参数与 Namespace 参数
   相同路径名在不同 Namespace 中可能引用不同状态；并非所有参数都允许 Namespace 内修改。

新对象默认值与已有对象状态
   ``default`` 类参数可只影响以后创建对象，旧接口或连接保持原值。

参数恢复与系统恢复
   写回旧值不保证已创建队列、连接、缓存和对象自动回到旧状态。

一句话结论
----------

sysctl 是把文本策略注入正在运行的内核子系统：只有确认作用域、生命周期、处理函数和运行证据，参数值才具有工程意义。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 34，Kernel Parameters, Sysctl, Control Interfaces, and Runtime Tuning；
* AIBook 章节：Chapter 168，sysctl as a Runtime Kernel Control Interface；
* 源文件：``docs/LinuxK/Part_34_Kernel_Parameters_Sysctl_Control_Interfaces_and_Runtime_Tuning/Chapter_168_sysctl_as_a_Runtime_Kernel_Control_Interface.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_34_Kernel_Parameters_Sysctl_Control_Interfaces_and_Runtime_Tuning/Chapter_168_sysctl_as_a_Runtime_Kernel_Control_Interface.md>`_。