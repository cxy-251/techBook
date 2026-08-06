第175章：crash 工具与事后内核分析
================================

本章必须记住
------------

#. ``crash`` 是读取 Linux Vmcore 或 Live Kernel 状态的交互式分析工具；本章重点是 Post-mortem Vmcore 分析。
#. 事后分析面对的是“冻结时刻的内核世界”，不是崩溃前完整事件录像。
#. ``vmcore`` 提供崩溃时内存内容；带符号和调试信息的 ``vmlinux`` 提供函数、类型、结构偏移和源码映射。
#. Vmcore 与 Vmlinux 必须精确配对。相同 ``uname -r`` 不一定代表相同 Build、Config、Compiler、Module 或结构布局。
#. 启动镜像 ``vmlinuz`` 通常不能替代未压缩并带 Debuginfo 的 ``vmlinux``。
#. 第一检查必须是 Kernel Release、Build ID、Architecture、KASLR、Page Size、Config 与 Module Generation 是否匹配。
#. Vmlinux 不匹配会导致结构字段错位、错误符号、异常 Backtrace、命令崩溃或看似合理但实际错误的对象解释。
#. “工具能打开 Vmcore”不等于符号和类型完全正确；必须用多个基础对象验证自洽性。
#. ``sys``、``log``、``bt``、``ps`` 是建立初始边界的最小命令集。
#. ``sys`` 用于确认系统、Kernel、CPU、时间、Panic 字符串和 Dump 基本元数据。
#. ``log`` 读取冻结 Vmcore 中的 Kernel Log Buffer，可提供 Oops、BUG、Panic、Lockup、RCU Stall、Driver Error 等入口。
#. ``bt`` 显示当前 Task 的 Kernel Stack；Dump 启动时当前上下文通常指向 Panicking Task，但要按工具输出确认。
#. ``ps`` 显示冻结时刻 Task 集合、PID、CPU、State 和 Task 地址，帮助判断单点故障还是系统性堆积。
#. Panic Task 不一定是最初制造坏状态的 Task；它可能只是第一个访问被破坏对象或检测到全局不变量失败。
#. 调用栈说明最后控制流，不自动说明根因发生时间和对象生命周期。
#. NULL Dereference、BUG_ON、Page Fault 或 Slab Corruption 的检测位置可能离真正破坏点很远。
#. 可靠结论应至少连接控制流、数据对象和并发/系统状态中的两个以上独立证据。
#. ``bt -a`` 或按 CPU 查看栈可显示冻结时其它 CPU 正在执行什么。
#. 多 CPU 分析要区分 Panicking CPU、停止在 NMI/Stop 路径的 CPU、仍在设备/IRQ/锁路径中的 CPU。
#. 其它 CPU 栈不完整可能来自 NMI 响应失败、Hard Lockup、Dump 缺页或 Unwinder 限制。
#. ``set`` 可切换当前 Task 上下文；``foreach bt`` 可批量查看 Task Stack，但输出量很大，应先过滤目标状态或函数。
#. Task State 是冻结快照，不提供状态持续时间；D State Task 是否长期阻塞还要结合日志、计时字段和共同等待点。
#. ``runq`` 可观察 Runqueue、当前 Task、Runnable Task 和调度状态，精确输出依架构与 Crash 版本。
#. Runqueue 堆积说明冻结时存在 Runnable Pressure，不自动证明调度器 Bug。
#. 锁问题要回答：锁对象是什么、谁持有、谁等待、等待路径是否一致、持有者是否还能运行。
#. 栈中出现 ``mutex_lock``、``schedule``、Spinlock Slowpath 只是入口，需要继续读取具体锁对象和调用者。
#. ``struct mutex``、``struct rw_semaphore``、Wait Queue、Lockdep 日志和 Task Stack 可共同重建锁关系。
#. 锁内部字段布局高度依赖 Kernel Version、Config 和 Debug Option，必须使用匹配类型解释。
#. 没有 Lockdep 信息不等于没有死锁；生产内核常未开启完整 Debug Lock 配置。
#. RCU Stall、Hung Task、Soft Lockup 和 Hard Lockup 的对象与时间模型不同，不能统一归因于“死锁”。
#. 内存分析首先要判断地址属于用户空间、Direct Map、Vmalloc、Module、Slab、Page、MMIO 或无效区域。
#. ``vtop``、``ptov``、``rd``、``struct``、``p``、``kmem`` 等命令用于连接地址转换、原始值、类型和分配器状态。
#. 一个可读地址不表示对象仍处于有效生命周期；已释放 Slab 可能仍保留旧字段。
#. 一个不可读地址也不必然表示崩溃时无效，可能是 Makdumpfile 过滤、损坏或地址转换元数据缺失。
#. Use-after-free 分析要同时看 Fault Address、Slab Cache、对象字段、引用/状态、释放路径和异步使用路径。
#. Double Free 分析要找对象第二次释放栈、Free List/Allocator 报告和所有权转移不匹配。
#. NULL Dereference 要定位哪个基址为 NULL、哪一层应建立它、错误路径是否跳过初始化或 Teardown 是否提前清空。
#. Wild Pointer 要检查地址模式、Poison、Redzone、Freelist、Generation 和可能的越界写。
#. Slab Poison/Redzone 字节只在对应 Debug 配置下有明确语义，不能跨配置凭记忆解释。
#. Page Fault in Kernel Mode 需要结合 Fault Address、Access Type、Page Table、Current Context 和 ``copy_*_user`` 边界。
#. Kernel Stack 中的寄存器和函数参数能帮助定位对象，但编译优化、内联和 Calling Convention 会影响可恢复程度。
#. Crash 的 ``dis``、``sym``、``whatis``、``struct`` 可连接指令、符号和类型。
#. 指令级分析必须使用崩溃内核相同的 Binary 和地址重定位；不能用另一构建的 Objdump 结果替代。
#. ``files`` 可从 Task 的 File Table 进入 ``struct file``、Inode、Dentry、Mount 等对象。
#. 文件系统故障要结合 Current File/Inode、Superblock、Journal/Transaction、Page Cache 和 Block Request 状态。
#. ``mount``、``dev``、Block/Driver 私有结构可扩展分析，具体 Crash Extension 与命令随版本而定。
#. 网络故障要从 Current Stack 或 Socket/Skb/Netdev 对象进入，不能无目标遍历全部全局网络列表。
#. ``net``、``struct sock``、``sk_buff``、Ring Descriptor 和驱动私有对象需要与对应 Kernel Module Debuginfo 配对。
#. 模块符号缺失会使驱动栈显示地址或不完整名称；必须取得崩溃时实际加载的 Module Build。
#. Module Reload、DKMS 和外部驱动可能使同一文件名对应不同 Build，必须使用 Build ID/Hash 管理。
#. Panic 日志是最早入口，不是最终结论。它通常给出 Exception、Fault Address、Registers、Call Trace 和 Tainted Flags。
#. Tainted Flags 表示内核曾加载外部模块、发生 WARN/Oops 或使用某些状态；它不能单独证明根因来自哪个模块。
#. ``log`` 中最后一条消息不一定是最后真实事件，Ring Buffer 可并发写入、覆盖或在 Crash 前未完整提交。
#. 多行 Call Trace 可能包含 Exception Stack、IRQ/NMI Stack 和普通 Task Stack，需要按边界读取。
#. ``?`` 标记或不可靠栈帧表示 Unwinder 置信度较低，不能把每一帧都当作真实调用关系。
#. 函数返回地址出现在栈中可能是残留值；可靠 Frame 取决于 Unwinder、Stack Metadata 和架构。
#. 还原失败路径的稳定顺序是：Panic Reason → Current CPU/Task → Reliable Stack → Fault/Assert Object → 其它 CPU/Task → 对象生命周期 → 源码错误路径。
#. 对关键栈帧，应读取函数源码，确定输入对象、锁状态、Context、返回语义和可失败分支。
#. 只按函数名搜索旧版本源码会造成误判，应固定到崩溃 Build 的 Source Commit 或发行版 SRPM。
#. 对象状态需要验证结构内多个字段是否自洽，例如 Refcount、List Link、State、Owner、Ops、Device、Parent 和 Generation。
#. 单个字段异常可能来自 Dump 缺页或内存破坏；多个关联字段共同异常更能支持对象损坏假设。
#. List 分析要检查 Prev/Next、Head、成员偏移和遍历终止，损坏链表不能盲目继续遍历。
#. 从损坏指针开始批量遍历可能让 Crash 命令失败或产生误导，应先 ``rd``/``struct`` 局部验证。
#. 引用计数为 0 不自动证明对象已释放；要结合发布状态、RCU、最后 Put、Release Callback 和 Allocator 状态。
#. 引用计数为正也不自动证明物理设备或底层资源可用；硬件可能已经 Remove/Disconnect。
#. RCU 保护的对象可能已从可见集合删除但尚未完成 Grace Period，冻结时刻必须结合发布/释放状态解释。
#. Workqueue/Timer/Tasklet/IRQ/Urb/Bio 等异步对象要检查 Pending/Running/Completion 与 Owner 生命周期。
#. “Remove 已返回”后仍有 Worker 访问私有对象，通常指向 Cancel/Flush/Synchronize 顺序错误。
#. DMA 相关崩溃要检查映射方向、Descriptor Ownership、Completion、IOMMU Fault、Buffer 生命周期和设备是否仍运行。
#. Vmcore 通常不能显示设备内部寄存器在崩溃前的完整历史，MMIO 状态可能已经变化或第二内核重置。
#. Firmware 状态、DMA Engine 和外设内部 Queue 需要结合设备日志、AER/IOMMU Fault 和硬件 Dump。
#. Crash 能显示冻结时内核内存，不能直接访问第一内核已经消失的设备运行现场。
#. Makdumpfile 过滤会影响 User Page、Page Cache、Free Page 和某些对象可见性；分析前必须读取 Dump Metadata。
#. 缺失页面时应降低结论强度，说明哪些对象无法验证，而不是填补猜测。
#. 内存破坏严重时，Vmlinux 类型正确也无法保证对象字段可信；应寻找未被破坏的旁证。
#. 日志、Stack、Allocator Metadata、邻接对象、其它 CPU 和 Trace/Pstore 可以交叉验证。
#. Freeze Snapshot 无法说明两个字段谁先改变；时间顺序必须来自 Log、Tracepoint、Sequence、Timestamp 或复现。
#. Crash 分析常能形成最可能假设，但最终代码修复仍需要复现、动态追踪、Sanitizer 或 Fault Injection 验证。
#. Post-mortem 结论应明确分成：已证实事实、强支持推断、无法确认部分和版本边界。
#. 不应把工具输出全部复制成报告；报告应围绕对象、路径、失败条件和修复边界组织。
#. 一份最小崩溃报告应包含 Kernel Build、Boot ID、Panic Reason、Current Task/CPU、可靠 Stack、关键对象、其它 CPU/Task 状态和结论证据。
#. 报告应记录 Vmcore 是否过滤、Vmlinux 来源、Module Debuginfo、Crash 版本和执行的关键命令。
#. 原始 Vmcore 应只读保存；Crash Session、命令输出和脚本使用分析副本。
#. Vmcore 含敏感内存，分析环境应隔离，输出也可能泄露路径、密钥、数据和地址。
#. Crash Extension 与自定义脚本属于代码执行边界，只应加载可信版本。
#. 分析脚本不能假设所有 Kernel 结构字段长期稳定，应根据 ``whatis``、类型和版本做适配。
#. Live ``crash`` 可读取运行内核，但其一致性与权限模型不同于冻结 Vmcore，本章结论不能全部机械套用。
#. Live System 中对象持续变化，读取多个字段不具备同一时刻一致性；Vmcore 则是冻结快照但缺少时间历史。
#. ``gdb`` 也可与 Vmlinux/Vmcore 结合，但 Crash 提供面向 Linux Task、Memory、Runqueue、Files 等对象的高层命令。
#. Drgn 等工具提供 Python 化对象分析，选择工具不改变必须匹配符号、验证对象和承认快照边界的原则。
#. Kdump 收集失败时，Crash 无法凭空恢复 Vmcore；此时只能依赖 Pstore、Console、Journal、BMC 和复现。
#. 分析成功也应回头验证 Kdump 质量：页面是否缺失、日志是否完整、Module 是否配对、收集是否及时。
#. Crash 工具自身版本需要支持目标 Kernel 的结构和 Dump 格式；过旧工具可能无法正确识别新特性。
#. 工具报错时先检查版本、Vmcore 完整性、Vmlinux Build 和 Debuginfo，不应马上把错误解释为内核对象损坏。
#. 源码阅读顺序是：Dump Metadata → Panic Path → Task/CPU → Reliable Stack → Object Type/Address → Ownership/Lifetime → Other Tasks/CPUs → Version-matched Source → 可验证假设。

必背路径
--------

打开 Dump：

::

   取得原始 Vmcore
   → 取得崩溃第一内核的匹配 Vmlinux
   → 校验 Release、Build ID、Architecture、Config 与 Module
   → crash vmlinux vmcore
   → sys / log / bt / ps 建立初始边界
   → 记录 Crash 与工具版本

失败路径重建：

::

   从 Panic Reason 与 Fault Address 开始
   → 确认 Panicking CPU 和 Current Task
   → 识别可靠 Stack Frame
   → 读取关键函数源码和参数对象
   → struct/rd/kmem 验证对象状态
   → bt -a / ps / foreach bt 检查其它 CPU 与 Task
   → 连接所有权、锁、异步和释放路径
   → 形成版本受限假设

Use-after-free 分析：

::

   定位 Fault Address 和访问指令
   → 判断地址区域与 Slab Cache
   → 读取对象 Type、State、Refcount 与 Poison
   → 找当前异步使用路径
   → 找 Remove/Release/Free 路径
   → 检查 Cancel/Flush/Synchronize/RCU
   → 用动态 Sanitizer 或复现验证

报告输出：

::

   已证实的系统事实
   → 当前 Task/CPU 与可靠调用栈
   → 关键对象字段和地址归属
   → 其它 Task/CPU 的支持证据
   → 最可能失败条件
   → 无法验证的缺页/时间线
   → 修复与复现建议

必须区分
--------

Vmcore 与 Vmlinux
   前者保存崩溃内存，后者提供符号、类型和结构布局。

Panic Task 与根因 Task
   当前 Task 可能只是发现坏状态的一方，真正破坏可能来自更早的其它上下文。

调用栈与完整时间线
   栈显示冻结时控制流，不能展示所有先前事件顺序。

地址可读与对象有效
   已释放内存仍可能可读；对象生命周期需结合分配器、引用和发布状态。

页面缺失与对象不存在
   过滤或损坏可使页面不可读，不能据此断言崩溃时对象不存在。

锁等待与死锁
   冻结时等待只是一张快照；死锁结论还需 Holder、Waiter 和可进展性证据。

工具输出与工程结论
   命令输出是原始证据，结论必须围绕对象关系、源码路径和版本边界组织。

冻结状态与运行历史
   Vmcore 提供一个时刻的世界；日志、Trace 和复现补充此前时间线。

一句话结论
----------

``crash`` 分析的本质是用匹配的类型与符号，把 Vmcore 中的冻结字节重建为 Task、Stack、Lock、Memory 和子系统对象，再用多源证据还原最后失败条件。

来源
----

* 书籍：Linux Kernel AIBook；
* Part：Part 35 — Kernel Debugging, printk, Dynamic Debug, ftrace, perf, kdump, and crash；
* 章节：Chapter 175 — crash Utility and Post-Mortem Kernel Analysis；
* 源文件：``docs/LinuxK/Part_35_Kernel_Debugging_printk_Dynamic_Debug_ftrace_perf_kdump_and_crash/Chapter_175_crash_Utility_and_Post_Mortem_Kernel_Analysis.md``；
* 固定提交：``18386764582829f2b807b7b0947785eb77b50446``；
* 固定来源：``https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_35_Kernel_Debugging_printk_Dynamic_Debug_ftrace_perf_kdump_and_crash/Chapter_175_crash_Utility_and_Post_Mortem_Kernel_Analysis.md``。
