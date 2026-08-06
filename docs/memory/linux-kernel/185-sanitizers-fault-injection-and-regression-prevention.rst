第185章：Sanitizer、Fault Injection 与回归防止
=============================================

本章必须记住
------------

#. 内核修复的工程终点不是“报告消失”，而是缺陷可观察、触发条件可复现、修复行为可自动回归验证。
#. Sanitizer 把已经发生的内存、未定义行为或并发违规转换成运行时报告。
#. Lockdep、Refcount 和 RCU 检查器验证锁依赖、引用和读侧保护等对象规则。
#. Fault Injection 主动制造低概率失败，使错误路径稳定进入。
#. Regression Test 固定旧 Bug 的触发条件和修复后的预期行为。
#. 稳定闭环是：失败信号 → 分类错误模型 → 选择检测器 → 稳定触发 → 修复对象协议 → 增加回归测试 → 持续验证。
#. KASAN 主要检测 Heap/Stack/Global 等内存区域中的越界和 Use-after-free，具体覆盖依模式和架构。
#. KASAN 报告应按 Error Type → Bad Access Stack → Allocation Stack → Free Stack → Object/Cache → Shadow/Tag 阅读。
#. 崩溃行只是非法访问发生点，根因通常位于更早的分配、发布、释放或异步取消路径。
#. Generic KASAN 主要使用 Shadow Memory 与编译器插桩，检测能力强、开销较高。
#. Software/Hardware Tag-based KASAN 使用 Tag 机制，能力和报告边界依架构与模式。
#. KASAN 未报告不证明没有内存缺陷；路径未执行、对象未被选中或模式覆盖有限都可能造成漏检。
#. UBSAN 检测 C 语言未定义行为，例如部分整数、移位、对齐、类型和边界违规。
#. UBSAN 报告说明某个运算违反语言规则，修复仍需检查输入范围、UAPI、数据类型和算术语义。
#. 不能简单关闭某个 UBSAN Check 掩盖真实输入验证缺失。
#. KCSAN 是动态数据竞争检测器，使用采样和 Watchpoint 观察未同步并发访问。
#. KCSAN 报告的核心证据是同一地址上的两个访问者、读写类型、大小、调用栈和缺失同步。
#. KCSAN 没有报告不证明竞争不存在，因为它是概率性动态检测。
#. ``data_race()`` 等注解只应用于经过证明、语义允许的竞争，不能用于压制未分析报告。
#. 数据竞争修复必须回到锁、Atomic、RCU、Sequence Counter 或 LKMM 所要求的同步协议。
#. KFENCE 使用采样和 Guarded Object 以较低开销检测部分 Heap 越界、Use-after-free 和 Invalid Free。
#. KFENCE 适合较长时间、真实负载和低概率缺陷观察，不能替代高覆盖调试环境中的 KASAN。
#. KASAN、UBSAN、KCSAN 和 KFENCE 检测不同错误类，不能只启用一种后声称内存与并发均安全。
#. Sanitizer 会改变内存布局、时序、性能和可复现概率，报告必须记录 Config、Compiler 和模式。
#. Lockdep 的基本对象是 Lock Class 和依赖图，不只是单个锁地址。
#. Lockdep 记录锁获取顺序、IRQ/Softirq 使用状态、递归和依赖链，用于发现潜在死锁和上下文冲突。
#. 读 Lockdep 报告要区分“正在获取的锁”“已经持有的锁”“历史依赖链”和“可能形成的环”。
#. Lockdep 报告可能在尚未发生真实死锁时出现，因为它证明当前依赖组合可以形成非法环。
#. 不能通过随机交换锁顺序让一个 Reproducer 安静；必须建立全局一致的锁层级。
#. ``lockdep_assert_held()`` 等断言把函数的锁前提写入源码，并在调试配置下验证调用者合同。
#. Lockdep 未启用或未覆盖某条路径，不证明锁顺序正确。
#. ``refcount_t`` 与 ``kref`` 表达对象持有关系，比普通 ``atomic_t`` 更适合引用生命周期。
#. Refcount Warning 常指从零增加、下溢、溢出、重复 Put 或异常状态。
#. 引用为正不证明底层硬件和资源仍有效；引用只保护软件对象存储和约定生命周期。
#. 引用为零也不自动证明对象已释放，Release Callback、RCU 和延迟工作可能仍参与最终销毁。
#. Refcount Bug 应按 Get 来源、所有权转移、Put 路径、最后 Release 和异步持有者重建。
#. RCU 检查器验证 ``rcu_dereference()``、RCU Read-side、发布和 Grace Period 前提。
#. RCU 保护读取安全不等于对象业务状态仍有效；对象可能已从可见集合撤销。
#. ``synchronize_rcu()`` 等待旧读者，不取消 Work、Timer、IRQ 或 DMA。
#. RCU Warning 的修复不能只替换访问宏，还要验证指针发布、删除和释放顺序。
#. Fault Injection 的目标是主动触发现实中低概率但必须正确处理的失败。
#. Linux 通用故障注入框架以 ``struct fault_attr``、``should_fail()`` 和 Debugfs/Boot 参数控制失败概率与范围。
#. ``fail_page_alloc`` 用于页分配失败路径；``failslab`` 用于 Slab 分配失败路径。
#. ``fail_make_request`` 用于块 I/O 提交错误；精确支持路径和设备范围依版本而定。
#. ``fail_function`` 可让允许注入的函数返回指定错误，目标函数需要明确标注和支持。
#. ``ALLOW_ERROR_INJECTION()`` 表示某函数可被错误注入框架替换返回，不应随意添加到无法安全跳过的函数。
#. 注入点必须对应真实可能发生、调用者有合同处理的失败。
#. 在不可失败或已产生不可逆副作用后强制返回错误，可能制造现实中不存在的状态。
#. Fault Injection 配置通常包含 Probability、Interval、Times、Space、Task Filter、Stack Filter 或 Verbose，具体字段依设施而定。
#. 100% 失败适合验证单个错误点；概率失败适合并发和长时间压力，但重现需要保存随机状态与配置。
#. 注入应限制到目标 Task、Callsite、Module、Device 或时间窗口，避免整个系统无差别失败。
#. 测试页分配失败时，要区分目标代码分配失败与测试框架、日志、网络或 SSH 自身分配失败。
#. Fault Injection 可能使测试基础设施失效，因此应准备串口、Pstore、Kdump 或 VM 自动重启。
#. 注入前必须记录原始参数，结束后必须恢复和验证状态。
#. 错误路径测试应按资源申请序列逐点失败。
#. 初始化为 A → B → C 时，应验证 A 失败、B 失败撤销 A、C 失败撤销 B/A。
#. 对每个故障点至少检查返回值、对象发布、资源计数、异步活动、重复调用和后续恢复。
#. 只检查“没有 Panic”不够；泄漏、残留 Sysfs、重复 IRQ、队列卡死和状态污染都可能静默存在。
#. I/O 故障测试要验证 Partial Completion、Retry、Timeout、Abort、Reset 和错误上报语义。
#. Timeout 注入不能只延长等待，应验证请求最终恰好完成一次或被明确失败一次。
#. 设备 Probe 失败后应验证 Driver Core 没有发布半绑定对象，下一次 Probe 可重新开始。
#. Remove 竞态测试应在 I/O、IRQ、Worker 和用户 fd 活跃时触发，并验证 teardown 顺序。
#. Sanitizer 与 Fault Injection 组合能把错误路径中的 Use-after-free、Double Free 和越界稳定暴露。
#. KCSAN 与并发 Fault Injection 组合可扩大状态竞态，但会显著改变时序，结论要按配置限定。
#. Lockdep 与错误路径压力组合适合验证异常清理中的锁顺序。
#. 修复后应把最低层根因写成 KUnit，把用户可见结果写成 kselftest，并保留 Fuzz Reproducer 或 Fault Scenario。
#. 回归测试必须在修复前能失败或触发旧报告，在修复后稳定通过且不产生新告警。
#. 只在修复后新增一个永远通过的测试，不能证明它覆盖原 Bug。
#. 回归 Case 应尽量最小，但必须保留触发所需的对象状态和并发条件。
#. 测试不应断言易变的内部函数顺序，除非该顺序就是生命周期或同步合同。
#. 回归输出应保存错误类型、对象、触发条件、Kernel Commit 和预期结果。
#. 修复验证还要运行邻接子系统测试、Sanitizer 配置和正常性能基线，防止局部修复引入新回归。
#. 安全修复可能需要私下验证和 Embargo 流程，Reproducer 与报告不能无控制公开。
#. 检测器报告也可能来自测试代码 Bug、错误 Mock 或不受支持配置，必须验证栈和对象归属。
#. 不应把“Known Issue”永久排除；每个 Suppression、Skip 或 Disable 都应有 Owner 和退出条件。
#. CI 配置矩阵不可能覆盖所有组合，应按风险选择 Architecture、Preemption、SMP、Sanitizer、Filesystem 和 Driver 组合。
#. 高开销检测器适合专用 Debug CI，低开销采样检测可补充长时间真实负载。
#. 生产开启检测器前要评估性能、内存、信息泄漏、Panic Policy 和告警处理能力。
#. 稳定缺陷处理顺序是：首个报告 → 错误分类 → 对象生命周期/同步 → 稳定注入或复现 → 修复 → 最小回归 → 相关矩阵验证。

必背路径
--------

检测与修复：

::

   KASAN / UBSAN / KCSAN / KFENCE / Lockdep 报告
   → 找第一个违规访问或依赖
   → 识别对象、锁、引用与 Context
   → 用 Reproducer 或 Fault Injection 稳定触发
   → 修复生命周期、同步或输入合同
   → 增加 KUnit / kselftest / Fuzz Regression
   → 在相关检测配置中持续运行

故障注入：

::

   选择真实可失败点
   → 限制 Task / Callsite / Device
   → 保存原配置
   → 强制一次或概率失败
   → 验证返回、回滚、异步收束与重复恢复
   → 清除注入状态
   → 检查 Kernel Log 和资源残留

必须区分
--------

* KASAN 内存安全，与 KCSAN 数据竞争。
* KASAN 高覆盖调试，与 KFENCE 低开销采样。
* Lockdep 依赖图告警，与已经发生的真实死锁。
* Refcount 保护对象存储，与硬件仍在线。
* RCU Grace Period，与取消所有异步活动。
* 故障注入的真实失败点，与人为制造的不可能状态。
* 报告消失，与根因已修复。
* 修复后测试通过，与测试确实能触发旧 Bug。

一句话结论
----------

Sanitizer 和检查器把违规变成证据，Fault Injection 把低概率错误路径变成稳定输入，Regression Test 再把修复后的对象与同步合同永久固定下来。
