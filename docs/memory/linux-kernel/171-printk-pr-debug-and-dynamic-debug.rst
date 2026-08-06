第171章：printk、pr_debug 与 Dynamic Debug
=========================================

本章必须记住
------------

#. ``printk()`` 是 Linux 内核最基础的文本日志入口；``pr_err()``、``pr_warn()``、``pr_info()``、``pr_debug()`` 等 Helper 在其上表达消息等级与使用意图。
#. 内核日志不是“直接向屏幕打印”。稳定路径是 Callsite → 格式化与 Log Level → Kernel Log Ring Buffer → Console、``/dev/kmsg``、``dmesg`` 或用户态日志服务。
#. Ring Buffer 是第一保存点；Console 只是消费者之一。控制台没有显示，不等于消息没有进入 Ring Buffer。
#. ``dmesg`` 读取的是内核日志缓冲；Journald/Syslog 是否保存、过滤或持久化属于后续用户态策略。
#. 严重级别数字越小，优先级越高：Emerg、Alert、Crit、Err、Warning、Notice、Info、Debug。
#. ``pr_err()`` 应记录当前操作失败或对象无法继续工作；``pr_warn()`` 应记录已降级或风险状态；``pr_info()`` 应记录低频、可解释的正常状态；``pr_debug()`` 应保存按需开启的调试细节。
#. Log Level 不是“是否写入 Ring Buffer”的简单开关；它主要参与消息严重性表达和 Console 过滤。
#. ``/proc/sys/kernel/printk`` 提供 Console Log Level 等运行状态；其值不能证明某条 Callsite 是否执行。
#. 每条日志应尽量回答：哪个对象、哪个阶段、发生什么、错误码或关键状态是什么、后续路径如何变化。
#. ``failed``、``error`` 这类缺少对象、阶段和返回值的消息几乎没有取证价值。
#. 驱动中应优先使用 ``dev_err()``、``dev_warn()``、``dev_info()``、``dev_dbg()`` 等带设备上下文的 Helper；纯子系统代码可使用 ``pr_*``。
#. ``pr_fmt()`` 可为同一编译单元的 ``pr_*`` 日志增加统一前缀，但它不能替代对象 ID、状态与错误码。
#. 内核格式化规则与用户态 ``printf`` 不完全相同；禁止使用浮点格式，指针和内核对象应使用文档化的 ``%p`` 扩展。
#. 普通 ``%p`` 可能进行地址哈希；日志中看不到裸内核地址通常是安全策略，而不是格式化失败。
#. 直接输出敏感地址、密钥、用户数据或未经限制的 Buffer 会扩大信息泄漏风险。
#. ``%pe`` 可用于错误指针，``%pS``/``%ps`` 可用于符号，网络地址、UUID、MAC 等也有专用格式；精确格式以目标内核文档为准。
#. ``pr_debug()`` 的编译与运行行为取决于 ``DEBUG``、``CONFIG_DYNAMIC_DEBUG``、``CONFIG_DYNAMIC_DEBUG_CORE`` 和模块构建方式。
#. Dynamic Debug 把调试粒度收缩到具体 Callsite，而不是只能打开整个模块的所有日志。
#. 一个 Dynamic Debug Callsite 通常记录 Source File、Line、Module、Function、Flags 和 Format String。
#. ``/proc/dynamic_debug/control`` 或兼容的 Debugfs 路径是运行时控制目录；文件不存在可能表示配置未启用、文件系统未挂载或访问受限。
#. Dynamic Debug Query 可按 ``file``、``func``、``line``、``module``、``format``、``class`` 选择 Callsite。
#. ``+p`` 打开打印，``-p`` 关闭打印；其它 Flag 可增加 Module、Function、Line、Thread ID 或调用栈装饰，具体字符依版本而定。
#. 打开一个函数、格式串或文件的 Dynamic Debug 前，必须先估计触发频率和输出量。
#. Dynamic Debug 控制写入成功只说明 Query 被接受，不证明目标 Callsite 会在当前负载中执行。
#. Callsite 没有输出时要区分：路径没有发生、Query 没匹配、日志被过滤、Ring Buffer 被覆盖、访问权限不足或构建时未启用动态调试。
#. ``pr_debug()`` 适合成功路径细节、状态转换和分支选择，不应承载唯一的关键错误证据。
#. 关键失败必须用默认可见的错误日志、Tracepoint、Counter 或返回值证据记录，不能要求现场先知道要打开哪个 Debug Callsite。
#. ``printk_ratelimit()``、``pr_*_ratelimited()``、``dev_*_ratelimited()`` 用于限制高频重复消息。
#. Rate Limit 的核心目标是防止日志路径成为新的性能和可用性故障。
#. ``*_once()`` 只适合“一次出现足以证明问题”的状态；它会隐藏后续次数和变化，不能用于需要频率统计的事件。
#. 高频日志会消耗格式化、锁、Ring Buffer、Console、用户态读取和写盘资源。
#. 慢速串口 Console 可把一条热路径日志放大成严重延迟，甚至改变竞态和调度时序。
#. 日志风暴会覆盖更早、更关键的 Ring Buffer 记录，使系统“输出很多但证据更少”。
#. 在 IRQ、NMI、锁持有区、内存回收和 Panic 路径打印具有更严格上下文约束。
#. Printk 子系统会尽力在复杂上下文中保存记录，但调用者不能把日志当作同步、延迟或硬件完成机制。
#. ``printk()`` 返回不表示消息已经被物理 Console 输出，也不表示 Journald 已经持久化。
#. 日志顺序通常反映提交到 Printk 体系的顺序，不能自动等同于多个 CPU 上真实硬件事件的全局因果顺序。
#. 多 CPU 日志需要结合时间戳、CPU、PID、Task、Sequence Number、Tracepoint 和对象 Generation 解释。
#. 相邻两行消息可能来自不同 CPU、不同 Task 或异步 Worker；不能仅凭文本邻接推断调用链。
#. 延续日志的 ``pr_cont()`` 等接口容易形成跨 CPU/上下文混合，应谨慎使用。
#. 多行状态应尽量形成完整、自包含记录，避免依赖其它消息拼接语义。
#. ``dmesg -w`` 或读取 ``/dev/kmsg`` 会持续消费/显示新记录，但观测工具本身也可能增加系统负载。
#. ``dmesg_restrict``、Kernel Lockdown、Capability 和 LSM 可限制非特权进程读取内核日志。
#. 读取失败不表示 Ring Buffer 为空，应确认 Credential、安全策略和容器 Procfs/Devfs 暴露方式。
#. 容器通常共享宿主内核日志对象，但 Runtime 常隐藏或限制 ``dmesg``，不能把容器视图当作独立 Kernel Log。
#. 用户态日志服务可能对重复消息限速、截断或丢弃；内核 Ring Buffer 与持久日志应分别核对。
#. 启动早期日志还涉及 Early Console、Boot Console、正式 Console 接管和 Ring Buffer 大小。
#. ``earlycon`` 能让普通驱动模型出现前的消息可见；它与运行期 Dynamic Debug 属于不同阶段。
#. Panic、Oops 和 Lockup 后普通日志路径可能不可靠，重要现场还要依赖 Pstore/Ramoops、Kdump 和 Vmcore。
#. ``WARN_ON*``、``BUG_ON``、Stack Dump 等不是普通日志等级选择，它们会产生额外控制流或诊断副作用。
#. 不应为了输出错误而把可恢复问题改成 WARN/BUG；应按问题是否违反内核不变量选择机制。
#. 错误路径日志应在资源仍可安全读取时记录，避免 Teardown 后访问已释放对象以“打印更多信息”。
#. 日志调用也要遵守对象生命周期；格式参数中引用的字符串、设备、Buffer 和指针在格式化期间必须有效。
#. 在释放路径中反复打印对象字段可能掩盖 Use-after-free，不能用日志稳定性证明生命周期正确。
#. 日志应保留真实负 Errno，避免只打印“失败”；Errno 能连接用户态返回值、源码分支和恢复策略。
#. 同一错误被多层重复打印会产生噪声；通常由最了解对象和语义的层记录一次，上层传播 Errno。
#. 若上层需要补充新的上下文，应增加对象和阶段，不应原样重复下层消息。
#. 成功路径日志要控制基数。每次 Packet、Request、Page、Syscall 或循环迭代打印通常不适合常态运行。
#. 统计型问题优先使用 Counter、Tracepoint、Histogram 或 Rate，而不是为每次事件打印文本。
#. Debug Callsite 应具有可搜索的稳定关键词和对象上下文，便于按 Format/String 精确开启。
#. Dynamic Debug Class 可把同一功能域的 Callsite 分组，具体支持与宏接口具有版本差异。
#. 修改 Dynamic Debug 状态是运行期控制操作，应记录 Query、时间、目标模块和回滚命令。
#. 生产诊断应先打开最小 Callsite 集合、限制时间窗口，再立即关闭并保存证据。
#. 不能直接执行 ``module * +p`` 之类全量开启后长时间运行；其输出与性能影响通常不可控。
#. 模块卸载后其 Dynamic Debug Callsite 会消失；重新加载时状态是否继承要按配置和启动参数确认。
#. Built-in 代码和 Loadable Module 的 Callsite 注册时机不同，启动期 Dynamic Debug 可通过 Kernel Command Line 配置，精确语法依版本。
#. ``dyndbg=``、``module.dyndbg=`` 等启动配置可以在早期启用 Callsite，但错误 Query 可能在启动时制造日志风暴。
#. Dynamic Debug 不是 Tracepoint：它输出自由文本，字段稳定性和解析能力低于专门事件。
#. Printk 不是性能采样器：它无法可靠回答函数占比、调度等待、锁竞争或硬件 PMU 成本。
#. 日志最适合记录低频状态、关键错误、配置和生命周期边界；路径证明用 Ftrace/Tracepoint，时间集中位置用 Perf。
#. 设计新日志前先问：没有这条消息，现场是否无法区分两个重要状态；若答案是否定，通常不应增加常态日志。
#. 日志消息属于用户可见接口的一部分，自动化可能依赖文本，但内核日志一般不承诺稳定机器解析 ABI。
#. 稳定自动化应依赖 Sysfs、Netlink、Tracepoint、Counter 或正式 UAPI，不应解析非文档化日志字符串。
#. 修复日志问题时，应同时评估可观察性、隐私、性能、限速和升级兼容性。
#. 源码阅读顺序是：Callsite → Helper/Level → Format 参数生命周期 → Printk Ring Buffer → Console/Reader → Rate Limit/Dynamic Debug → 实际运行证据。

必背路径
--------

普通日志路径：

::

   内核 Callsite 执行 pr_err/pr_info/printk
   → 组合 Log Level 与 Format String
   → 格式化对象、状态和 Errno
   → 提交到 Kernel Log Ring Buffer
   → Console 按 Console Log Level 输出
   → /dev/kmsg、dmesg、Journald 等读取
   → 用户保存并与时间线关联

Dynamic Debug：

::

   编译时启用 Dynamic Debug
   → pr_debug/dev_dbg Callsite 进入 Catalog
   → 读取 /proc/dynamic_debug/control 找到 File/Func/Line/Format
   → 写入最小 Query +p
   → 运行目标负载
   → 从 dmesg/日志读取匹配消息
   → 写入 -p 回滚
   → 保存 Query、Kernel、时间窗口与结果

日志风暴控制：

::

   发现重复高频消息
   → 统计触发对象和频率
   → 判断是否应改为 Counter/Tracepoint
   → 必须保留时使用 ratelimited/once
   → 缩小 Format 与对象数据
   → 验证 Ring Buffer、Console 与 CPU 开销

故障取证：

::

   固定 Boot ID、Kernel Release 与时间窗口
   → 读取 dmesg Ring Buffer
   → 读取持久 Journal/Pstore
   → 按 CPU、PID、对象 ID、Errno 排序
   → 用 Dynamic Debug 补充最小缺失状态
   → 用 Tracepoint/Ftrace 证明路径

必须区分
--------

* Ring Buffer 与 Console：Ring Buffer 保存记录；Console 是按等级和状态输出记录的设备路径。
* ``pr_err`` 与 ``pr_debug``：前者记录默认应保留的失败事实；后者记录按 Callsite 开启的调试细节。
* 日志顺序与因果顺序：文本提交顺序不自动证明多 CPU、异步 Worker 和硬件事件的全局因果关系。
* Rate Limit 与问题消失：限速只减少输出，不修复事件源，也不表示故障频率下降。
* Printk 与 Tracepoint：Printk 输出自由文本；Tracepoint 提供结构化事件字段与更适合统计的接口。
* Dynamic Debug 与模块 Debug 开关：Dynamic Debug 控制具体 Callsite；驱动私有 Debug 参数可能改变完全不同的代码路径。
* 日志可见与日志产生：用户态没看到消息可能是权限、过滤、消费或覆盖问题，不等于 Callsite 未执行。

一句话结论
----------

``printk`` 的价值不是输出更多文字，而是在最小运行扰动下，把对象、阶段、状态和错误保存为可与其它内核证据关联的记录。
