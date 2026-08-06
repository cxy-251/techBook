第183章：kselftest 与用户态驱动的内核测试
=========================================

本章必须记住
------------

#. kselftest 是随 Linux 内核源码共同维护、由用户态程序或脚本驱动目标内核行为的测试体系。
#. kselftest 的主要对象是用户态可见契约：Syscall、Ioctl、Netlink、Socket、Procfs、Sysfs、BPF、Cgroup、Namespace、Signal、Timer 和权限语义。
#. kselftest 通常在目标内核已经构建、安装并启动后运行。
#. 测试源码属于一个内核树，测试结果属于实际运行的目标内核，两者版本必须记录并尽量匹配。
#. kselftest 不能直接替代 KUnit；前者从用户入口验证契约，后者直接验证内核内部逻辑。
#. kselftest 失败通常表示用户态可观察行为异常、测试环境不满足、权限不足或工具/内核版本不匹配。
#. 读一个 Selftest 时应先问用户态输入是什么，再问预期返回值、Errno、事件顺序、文件内容或权限结果是什么。
#. 内核内部结构可以重构，只要用户态稳定契约不变，Selftest 应继续通过。
#. ``tools/testing/selftests/`` 是 kselftest 的源码组织根目录。
#. 测试集合通常按子系统或能力组织，例如 BPF、Net、Timers、VM、Cgroup、Seccomp、Ptrace、Filesystems 和 Architecture。
#. 精确目录集合随内核版本变化，必须以目标源码树为准。
#. 顶层 ``tools/testing/selftests/Makefile`` 描述可选 Target 集合和公共构建入口。
#. 每个集合的本地 ``Makefile`` 决定哪些程序、脚本、辅助文件和生成物参与测试。
#. ``TEST_PROGS`` 常表示要直接运行的脚本或程序。
#. ``TEST_GEN_PROGS`` 常表示需要编译生成并运行的程序。
#. ``TEST_FILES``、``TEST_GEN_FILES``、``TEST_INCLUDES`` 等变量表示辅助材料，精确语义按目标 ``lib.mk`` 读取。
#. ``tools/testing/selftests/lib.mk`` 提供公共构建、安装和运行规则。
#. ``kselftest.h`` 与 ``kselftest_harness.h`` 提供用户态结果输出和测试 Harness。
#. ``TEST()``、``FIXTURE()``、``ASSERT_*``、``EXPECT_*`` 属于用户态 Harness，不是 KUnit 宏。
#. Selftest 的 Fixture 应隔离临时文件、Namespace、Cgroup、Socket、Mount、BPF Object 或设备状态。
#. 测试结束后必须恢复 Host 环境，不能留下 Mount、Netns、Sysctl、Cgroup、Module 或网络规则。
#. 测试集合中的 ``config`` 文件可声明建议的 Kconfig 前提，但它不保证当前运行内核已经启用这些配置。
#. 测试前必须核对目标 Kernel Config、Architecture、Capability、LSM、Seccomp、Namespace 和硬件能力。
#. 缺少前提应输出 ``SKIP``，不能把环境缺失伪装成 ``PASS``。
#. 真正的行为不符合契约应输出失败，不能因为环境复杂而无条件跳过。
#. 构建、安装、运行和解析是四个不同阶段。
#. 构建成功只说明测试二进制生成，不说明目标内核行为正确。
#. 安装成功只说明测试包和辅助文件被复制到目标目录。
#. 测试运行成功需要当前内核、权限、设备、文件系统和用户空间工具共同满足前提。
#. 结果解析必须保留每个 Case 的输出、退出码、Timeout、Skip Reason 和 Kernel Log。
#. ``make -C tools/testing/selftests TARGETS=<set> run_tests`` 可选择性构建并运行集合，精确目标按当前树确认。
#. ``TARGETS`` 用于选择测试集合；``SKIP_TARGETS`` 可排除集合，精确接口随构建规则演进。
#. 选择性运行适合补丁开发，但合入前还应按影响范围运行相关邻接集合和更高层回归。
#. ``make ... install INSTALL_PATH=...`` 可导出独立测试包，适合构建机和目标机分离。
#. 安装后的 ``run_kselftest.sh`` 可列出、按集合或按具体测试执行，参数随版本变化。
#. 测试包和目标内核不匹配可能导致编译头文件、UAPI、Feature 探测和结果解释错误。
#. 用户态测试程序可能链接系统 C Library；Library 封装、VDSO 和直接 Syscall 路径应按测试目标区分。
#. 验证 Syscall 精确 Errno 时，应避免 Library 自动回退或转换掩盖内核返回。
#. 验证时间和调度行为时，测试应考虑 Clock、CPU Affinity、Load、Preemption、Virtualization 和 Timer Resolution。
#. 固定 Sleep 不是可靠同步；测试应使用 Poll、Eventfd、Signal、Pipe、Waitpid、Futex 或明确状态接口。
#. Timeout 必须有上限，并输出测试卡在哪个阶段。
#. Selftest 涉及多进程或多线程时，应记录 PID/TID、角色和同步点，避免把子进程异常丢失为父进程普通失败。
#. TAP/KTAP 用结构化文本表达 Plan、Case 编号、``ok``、``not ok``、Directive 和 Diagnostic。
#. TAP/KTAP 输出的 Plan 应与实际 Case 数一致，提前退出和 Crash 会造成不完整计划。
#. ``ok`` 表示该测试项达到自身断言，不证明整个 Kernel Log 无错误。
#. ``not ok`` 表示行为断言失败或测试基础设施失败，需要结合 Diagnostic 和退出状态分类。
#. ``SKIP`` 表示前提不满足，测试没有验证目标行为。
#. ``TODO`` 或 Expected Failure 语义必须谨慎使用，不能长期隐藏真实回归。
#. ``TIMEOUT`` 不是普通失败，它可能对应死锁、等待条件丢失、性能退化或环境失联。
#. Runner 应区分测试程序退出、Signal、Kernel Panic、SSH 断开和目标机重启。
#. Selftest 运行时产生 KASAN、KCSAN、Lockdep、WARN、Oops 或 Refcount 报告，应使 CI 失败或进入明确人工审查。
#. 一些测试需要 Root 或具体 Capability；Root 运行通过不能证明非特权访问控制正确。
#. 权限测试应分别验证允许主体和拒绝主体，并记录 User Namespace、Credential 和 LSM 环境。
#. 容器内运行 Selftest 只覆盖容器暴露的 Namespace、Capability、Mount 和设备视图。
#. Host 级网络、Perf、BPF、Kexec、Mount 和设备测试通常需要更高权限和宿主环境。
#. 网络 Selftest 应为接口、地址、Route、Netns、qdisc 和 Netfilter 使用唯一临时对象，避免污染真实网络。
#. 文件系统 Selftest 应使用专用临时目录、Loop Device 或测试文件系统，并定义 Crash/Unmount 清理。
#. BPF Selftest 的 Loader、Verifier Log、Program Type、Attach Point 和 Kernel Config 都属于结果上下文。
#. Cgroup Selftest 应确认使用 v1 还是 v2、目标挂载点、Controller 启用状态和父层限制。
#. Architecture Selftest 可能依赖 CPU Feature、Page Size、Instruction、Signal Frame 和 ABI，不能跨平台机械比较。
#. kselftest 适合回归用户态合同，不保证内部实现没有内存泄漏、数据竞争或锁问题。
#. 将 Selftest 与 Sanitizer Kernel 组合，可同时验证功能结果和运行时安全。
#. 将 Selftest 与 Fault Injection 组合，可从用户入口稳定触发错误路径和恢复行为。
#. LTP 与 kselftest 都可验证系统调用和系统行为，但项目范围、组织方式和维护边界不同。
#. kselftest 与内核源码同树演进，更适合贴近具体子系统补丁的官方回归。
#. LTP 提供更广的系统级、兼容性和长期回归覆盖，具体套件与结果需按 LTP 版本解释。
#. 不能用一个 kselftest Case 通过推导整个子系统、所有配置和硬件组合均正确。
#. Flaky Selftest 应调查时钟、负载、竞态、共享环境、清理和测试自身 Bug，而不是无限重试。
#. 重试可以收集概率和证据，不能把第一次失败自动改写成通过。
#. 测试日志必须保存目标 Kernel Commit、``uname``、Config、Boot ID、工具 Commit、命令行和环境前提。
#. 修复用户态可见回归时，应把最小可观察失败写成 Selftest，避免断言易变内部实现。
#. 稳定阅读顺序是：Target 目录 → Makefile → 默认运行项 → Harness/Fixture → 用户态入口 → 预期合同 → TAP/KTAP → Cleanup。

必背路径
--------

kselftest 执行链：

::

   内核源码中的 tools/testing/selftests
   → Target Makefile
   → 构建测试程序与脚本
   → 可选安装到独立目录
   → 在已启动目标内核上运行
   → 用户态接口触发内核路径
   → TAP / KTAP 与退出状态
   → CI 关联 Kernel Log

用户契约验证：

::

   构造用户态输入
   → Syscall / Ioctl / Netlink / Procfs / Sysfs / Socket
   → 内核执行
   → 返回值 / Errno / Event / File State / Permission
   → Assert 稳定 UAPI 行为
   → 清理 Namespace、Cgroup、Mount 与临时对象

必须区分
--------

* kselftest 与 KUnit：kselftest 从用户态入口验证内核对外合同；KUnit 在内核内部直接验证函数、结构体和局部状态机。
* 测试源码版本与当前运行内核版本：编译测试的源码版本决定测试期望；真正被验证的是当前启动内核，二者不匹配会产生假失败或假通过。
* 构建成功与行为验证成功：构建成功只证明测试程序和依赖可生成；运行断言通过才证明目标内核行为符合合同。
* ``SKIP`` 与 ``PASS``：``SKIP`` 表示功能、配置、权限或环境前提缺失；``PASS`` 表示目标路径已执行且断言成立。
* TAP/KTAP 测试结果与完整 Kernel Log 健康：协议结果描述测试项状态；Kernel Log 还可能包含测试框架未捕获的 Sanitizer、Lockdep、WARN 或 Oops。
* Root 环境通过与非特权安全合同正确：Root 通过只证明高权限路径；必须以普通 Credential、Namespace 和 Capability 再验证拒绝与授权边界。
* 用户态稳定行为与内核内部实现细节：返回值、Errno、事件和文件语义属于可测试合同；内部函数顺序和私有结构布局通常不应被测试固化。

一句话结论
----------

kselftest 从普通用户进程能够触达的接口出发，把 Linux 内核对用户态承诺的返回值、事件、权限和状态语义固定成可持续运行的回归测试。
