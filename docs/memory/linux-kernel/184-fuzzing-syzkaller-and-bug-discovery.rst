第184章：Fuzzing、syzkaller 与缺陷发现
=====================================

本章必须记住
------------

#. 内核 Fuzzing 用自动生成、变异和组合的输入持续探索用户态可达的内核路径。
#. Fuzzing 的目标不是随机制造错误码，而是进入更深状态，触发边界条件、非法顺序、生命周期竞态和并发缺陷。
#. 纯随机 Syscall Number、无效 fd 和随机指针通常停在浅层参数检查，覆盖价值有限。
#. 有效 Fuzzer 会先构造足够合法的对象，再在长度、Flag、顺序、并发和释放时机上制造异常。
#. 内核 Fuzz 输入可以是 Syscall 序列、Ioctl、Netlink Message、Packet、Filesystem Image、BPF Program、设备协议和线程时序。
#. Syscall 序列是状态程序，不是独立函数调用集合。
#. ``openat()``、``socket()``、``mount()``、``mmap()``、BPF Map 创建等调用会为后续调用生产资源。
#. fd、Socket、Mount、Namespace、BPF Map、File、VMA 等资源关系决定深层路径是否可达。
#. 读 Fuzz Reproducer 时应先找资源生产调用，再找状态转换，最后找触发报告的调用。
#. Attack Surface 指用户态可触达、可携带输入并可改变内核状态的接口集合。
#. 普通 Syscall、Ioctl、Netlink、BPF、Filesystems、Procfs 写入口和设备节点都可能构成攻击面。
#. 攻击面大小不仅取决于入口数量，还取决于参数复杂度、长期状态、异步行为和权限范围。
#. 非特权可达、复杂嵌套 UAPI、状态跨调用延续和异步 Teardown 会提高 Fuzz 价值与风险。
#. Capability、User Namespace、LSM、Seccomp 和设备权限会改变同一入口的可达性。
#. Fuzz 报告必须记录 Sandbox、Namespace、Credential、Config、Architecture 和 Kernel Commit。
#. Coverage-guided Fuzzing 使用运行覆盖反馈，优先保留能进入新代码区域的输入。
#. Coverage 说明某些指令、基本块或比较被执行，不说明执行结果正确。
#. 新 Coverage 是探索信号，不是 Bug 证据。
#. Crash、WARN、KASAN、KCSAN、Lockdep、RCU Stall、Hung Task、Leak 或行为差异才构成进一步调查信号。
#. KCOV 是 Linux 为 Coverage-guided Fuzzing 提供的内核覆盖接口。
#. KCOV 通常通过 Debugfs ``/sys/kernel/debug/kcov`` 暴露用户接口，具体可用性取决于 Config、Mount 和权限。
#. KCOV 主要按 Task 收集稳定、与输入相关的覆盖，减少调度器和中断噪声。
#. 异步 Workqueue、IRQ 或其它 Task 中执行的路径不一定天然归入发起 Task 覆盖。
#. KCOV Remote Coverage 等能力可扩展异步上下文，精确 API 与支持范围依版本而定。
#. KCOV 可以输出 PC Coverage，也可输出 Comparison Operands，帮助 Fuzzer推测 Magic Value、长度和边界条件。
#. KCOV Buffer 的启用、映射、收集和关闭必须遵守 UAPI 生命周期。
#. KCOV 本身不判断内存安全、锁顺序或业务错误，只提供路径反馈。
#. syzkaller 是面向操作系统内核的 Coverage-guided Fuzzer。
#. syzkaller 的核心链是 Syscall Description → Program Generation/Mutation → Executor → KCOV/Crash Feedback → Corpus → Reproducer。
#. ``sys/linux/*.txt`` 等声明式描述定义 Syscall、Ioctl、Struct、Flag、Resource 和方向关系。
#. 声明式描述使工具能够生成“足够合法”的调用和资源依赖，而不只是随机字节。
#. 常量提取和代码生成把目标内核 UAPI 转换为 syzkaller 可执行的描述数据。
#. ``prog`` 层表示和变异 Syscall Program；Executor 在目标 VM 或设备中执行具体调用。
#. Manager 负责 Corpus、VM、崩溃归类、复现和调度，精确组件名与职责按 syzkaller 版本确认。
#. Corpus 保存能产生新覆盖或重要行为的程序，后续 Mutation 以其为种子继续探索。
#. 程序变异可修改参数、插入或删除调用、改变资源、并发执行和重复策略。
#. Fuzzer 执行环境通常包括 VM、测试内核、Rootfs、SSH/Agent、Crash Monitor 和重启恢复。
#. 测试内核应启用 KCOV、必要 Sanitizer、Debug Info 和目标子系统配置。
#. 开启所有 Debug 能力会增加开销、改变时序和内存布局，报告必须记录配置。
#. syzbot 是基于 syzkaller 的持续内核 Fuzzing 与报告服务，不等同于 syzkaller 工具本身。
#. 崩溃归类通常依据报告类型、栈和标题；相同标题不保证根因完全相同。
#. 一个 Bug 可能产生多个不同栈，一个相似栈也可能来自不同生命周期错误。
#. Fuzz 报告中的第一条 Warning 或 Sanitizer Header 通常比后续 Panic 更接近原始失败。
#. Panic 可能只是系统在前一个对象破坏后继续运行的二次结果。
#. 报告应同时保存 Console Log、Kernel Commit、Config、Compiler、Dashboard 信息和 Reproducer。
#. ``repro.syz`` 是 syzkaller DSL 形式的最小化程序，能保留资源与执行器语义。
#. C Reproducer 尝试转换为普通 C 程序，便于开发者编译和单步理解。
#. 某些触发条件依赖 syzkaller Executor、Sandbox、Threading、Fault Injection、Network Injection 或特定内存布局，只能稳定使用 Syz Reproducer。
#. 没有 C Reproducer 不表示报告无效。
#. Reproducer 的价值是把大规模随机探索收缩成最小、可重复的对象路径。
#. 最小化会删除看似无关的 Syscall，但保留的奇怪 Flag、地址、长度和重复次数可能正是触发条件。
#. 不应为了让 Reproducer“像正常程序”而擅自简化其异常参数。
#. 阅读 Reproducer 的稳定顺序是：环境选项 → 资源创建 → 目标对象状态 → 并发/重复 → 触发调用 → 报告栈。
#. 复现率低可能来自竞态窗口、CPU 数、虚拟化、时钟、设备、调度和 Debug 配置差异。
#. 复现次数和概率应记录，不能把一次成功和九十九次失败压成“可复现”。
#. 复现时要使用报告对应的 Commit、Config 和 Architecture，随后再向新旧版本做 Bisect 或验证。
#. 直接在不同版本上复现失败，不能说明原报告错误；路径和内存布局可能已经变化。
#. 覆盖率增加但长期无崩溃，可能表示路径安全，也可能表示 Bug Oracle、输入语义或并发探索不足。
#. Fuzzing Filesystem 时，文件系统镜像、Mount Option、Crash/Remount、Journal 和 Block Error 都是输入状态。
#. Fuzzing eBPF 时，Program Type、Map、Verifier、Helper、Attach Point 和 Privilege 都决定可达路径。
#. Fuzzing Network 时，Socket State、Netlink Attribute、Namespace、Packet Sequence 和并发 Close 都是重要维度。
#. Fuzzing Driver Ioctl 时，设备节点权限、硬件存在性、Firmware 和 Reset 会限制自动化环境。
#. 没有真实硬件时可以使用虚拟设备、Dummy Driver 或协议模型，但结论只覆盖模拟路径。
#. Fuzzer 发现 Use-after-free 后，根因仍需沿对象 Alloc → Publish → Use → Remove → Free 路径分析。
#. KASAN 报告提供访问、分配和释放栈时，应优先重建对象生命周期，而不是只修补崩溃行。
#. KCSAN 报告需要找两个访问者、缺失同步和允许的数据竞争语义。
#. Lockdep 报告需要重建锁类和依赖链，不能只修改锁获取顺序使当前 Reproducer 安静。
#. WARN/BUG 报告需要判断是否违反真实不变量，还是非法用户输入不应触发内核告警。
#. 用户可控无效输入通常应返回错误，不应导致 WARN、Oops 或 Panic。
#. Fuzzing 产生的 Reproducer 应转化为最接近根因的回归测试。
#. 纯内部逻辑 Bug 可增加 KUnit；用户接口行为可增加 kselftest；复杂 Syscall 序列可保留专用 Reproducer 或 Fuzz Regression。
#. 修复后只运行一次 Reproducer 不足，应同时运行相关 Corpus、Sanitizer 和子系统回归。
#. 修复不能只隐藏报告，例如删除 WARN 或屏蔽 KASAN；必须恢复对象、边界和同步语义。
#. 安全报告可能包含尚未公开漏洞，日志、Reproducer 和访问权限需要按安全流程管理。
#. Fuzzing 基础设施应隔离在 VM、实验机或可自动恢复设备，避免损坏生产数据和网络。
#. 持久化磁盘、外部设备、真实网络和凭证不应无控制暴露给 Fuzzer。
#. 稳定调查顺序是：报告类型 → 首个失败栈 → 环境/Commit/Config → Reproducer 资源流 → 对象生命周期 → 最小修复 → 回归固定。

必背路径
--------

Coverage-guided Fuzzing：

::

   Syscall / UAPI Description
   → 生成或变异 Program
   → Executor 在目标内核运行
   → KCOV 返回 Coverage / Comparison
   → 新路径进入 Corpus
   → Sanitizer / WARN / Crash 触发报告
   → 最小化为 repro.syz / C Reproducer
   → 根因分析与回归测试

Reproducer 阅读：

::

   固定 Kernel Commit / Config / Architecture
   → 读取 Sandbox 与执行选项
   → 找资源创建调用
   → 找对象状态转换
   → 找并发与释放窗口
   → 对齐首个失败栈
   → 重建对象生命周期

必须区分
--------

* 随机输入与语义化状态探索：随机字节常停在浅层校验；语义化 Fuzzing 先构造有效资源和状态，再变异顺序、长度、并发和释放时机。
* Coverage 增长与发现 Bug：Coverage 增长只证明进入新路径；Sanitizer、WARN、Crash、Hang 或错误行为才是缺陷信号。
* Crash 标题与经过验证的根因：标题用于报告聚类；根因必须由首个失败证据、对象生命周期和可重复路径共同证明。
* ``repro.syz`` 与 C Reproducer：``repro.syz`` 保留 syzkaller 的资源、并发和执行器语义；C Reproducer 更便于独立编译阅读，但可能无法表达全部触发条件。
* 触发崩溃的最后调用与最初破坏对象的路径：最后调用只是暴露损坏的位置；真正根因可能发生在更早的分配、发布、并发访问或释放路径。
* 模拟设备覆盖与真实硬件覆盖：模拟环境验证协议模型和软件路径；真实硬件还包含 Firmware、总线、DMA、Reset 和物理时序。
* 报告消失与缺陷已正确修复：报告消失可能来自时序、配置或路径变化；修复必须恢复不变量，并由旧 Reproducer 和回归测试验证。

一句话结论
----------

Fuzzing 用资源感知的输入和覆盖反馈系统探索人工没有规划的内核状态，而 Reproducer 将一次随机发现收缩成可读、可修复、可回归验证的对象路径。
