第182章：KUnit 内核内部单元测试
===============================

本章必须记住
------------

#. KUnit 是 Linux 内核内部的白盒单元测试框架，测试代码与被测代码都运行在内核上下文。
#. KUnit 适合直接调用内部函数、访问内部结构体、构造局部状态和验证错误路径。
#. KUnit 最适合纯逻辑、解析器、小状态机、数据结构、边界条件、局部资源管理和不依赖真实硬件的代码。
#. KUnit 不是完整系统测试，不能单独证明真实设备、用户 ABI、Boot、Suspend/Resume 或多机行为正确。
#. KUnit 的基本对象链是 Test Function → ``struct kunit_case`` → Case Array → ``struct kunit_suite`` → Registration Macro → Executor。
#. Test Case 函数签名通常是 ``void test_case(struct kunit *test)``。
#. ``struct kunit`` 表示当前测试上下文，承载状态、失败记录、日志、资源和私有数据。
#. ``KUNIT_CASE()`` 把一个测试函数包装成可枚举的 Case。
#. ``struct kunit_suite`` 组织 Suite 名称、Case 数组、Fixture 初始化与清理。
#. ``kunit_test_suite()`` 或相关宏负责注册 Suite，精确宏随内核版本演进。
#. 读一个 KUnit 文件时先找 Suite，再找 Case 数组，再找每个 Case 调用的被测函数。
#. 一个 Case 应只验证一个明确行为或一组高度相关的不变量。
#. Case 名称应表达输入条件与预期行为，不能只写 ``test1``、``basic`` 或 ``works``。
#. 测试结构应按 Arrange、Act、Assert 阅读和编写。
#. Arrange 构造输入、Fixture、Mock、错误状态和对象关系。
#. Act 只触发一个明确函数、回调或状态转换。
#. Assert 验证返回值、对象状态、引用、列表、资源和错误语义。
#. ``KUNIT_EXPECT_*`` 失败后通常记录失败并继续当前 Case。
#. ``KUNIT_ASSERT_*`` 失败后终止当前 Case，用于保护后续代码的安全前提。
#. 对象创建、内存分配、指针合法性等后续解引用前提应使用 Assertion。
#. 多个相互独立的输出属性适合使用 Expectation，以保留更多失败信息。
#. 把普通行为比较全部写成 Assertion 会降低一次运行的诊断密度。
#. 把必要前置条件写成 Expectation 可能让测试继续执行到 NULL Dereference 或无效状态。
#. ``*_MSG`` 变体应包含输入值、状态名、索引或对象 ID，避免失败日志只有宏行号。
#. 表驱动测试适合大量边界输入，但失败信息必须能标识具体 Case 参数。
#. 参数化测试 API 与注册细节具有版本差异，稳定思想是输入集合与行为断言分离。
#. Fixture ``init`` 通常在每个 Case 前运行，``exit`` 在每个 Case 后运行。
#. Suite 级初始化和清理围绕整个 Suite，精确字段和支持依目标内核版本确认。
#. ``test->priv`` 可保存当前 Case 的私有 Fixture 对象，其生命周期必须由测试框架或清理路径管理。
#. Fixture 初始化失败必须阻止 Case 使用半初始化对象。
#. 清理函数必须处理部分初始化，不能假设 Arrange 全部成功。
#. KUnit Resource API 用测试上下文管理资源，在 Case 结束、Assertion 中止或失败时自动执行 Cleanup。
#. ``kunit_kmalloc()``、``kunit_kzalloc()`` 等资源与当前测试绑定，适合测试期内存。
#. 自动资源管理减少测试代码泄漏，不替代被测生产代码自身的所有权测试。
#. 被测函数应仍然使用真实生产分配、引用和释放协议；测试 Resource 只管理测试夹具。
#. KUnit Resource 可以绑定自定义 Init/Free 回调，适合临时对象、Fake Device 或注册状态。
#. Resource 名称和匹配接口属于内部 API，精确用法需按目标源码确认。
#. 测试局部对象时，应验证正常释放和错误中止两条路径均无残留。
#. Mock 的目标是隔离真正的外部依赖，不是复制被测实现。
#. 可测试代码应将纯逻辑从硬件访问、全局注册和异步回调中拆出。
#. 依赖注入、Ops Table、Fake Clock、Fake Allocator 或 Fake Bus 可提高局部测试可控性。
#. Mock 返回值应覆盖成功、边界、失败和重复调用，不应永远返回理想结果。
#. Mock 调用次数和顺序只有在它们属于稳定合同或资源协议时才应被断言。
#. 对内部实现顺序过度断言会让正常重构产生无价值测试失败。
#. KUnit 可以验证私有函数，但测试可访问性设计应避免把内部符号错误暴露成外部 ABI。
#. 测试文件可与被测源码位于同一编译单元、使用 Internal Header，或通过受控接口访问。
#. 选择方式应平衡封装、构建结构和测试价值。
#. 内建 KUnit 测试编译进 ``vmlinux``，通常由 KUnit Executor 在启动阶段发现并运行。
#. 模块形式的 KUnit Suite 可在测试模块加载时运行，适合已启动系统中的选择性测试。
#. UML 把 Linux 内核作为用户态进程运行，适合快速构建和纯逻辑测试循环。
#. UML 不能代表所有架构、MMU、IRQ、DMA、Cache、Firmware 和真实设备语义。
#. QEMU 可提供目标架构虚拟环境，比 UML 更接近架构路径，仍不等同于真实硬件。
#. ``tools/testing/kunit/kunit.py`` 负责配置、构建、运行和解析结果，默认工作流常使用 UML。
#. ``kunit.py run`` 是工具工作流，不是内核内部执行机制本身。
#. ``.kunitconfig`` 描述测试构建所需 Kconfig 片段；测试是否实际编译还取决于依赖和配置合并结果。
#. KUnit 测试常使用独立 Kconfig Symbol，使生产构建可以关闭测试代码。
#. 测试配置启用不应意外改变被测功能的正常生产语义。
#. 内建测试在 Boot 中运行可能影响启动时间、日志和内存，不能无评估部署到生产。
#. KUnit 结果通常以 KTAP 形式输出，包含 Suite、Case、``ok``、``not ok``、Plan 和 Diagnostic。
#. KTAP 输出是结构化测试协议，不只是普通 Printk 文本。
#. CI 解析 KTAP 时必须保留 Kernel Log，因为 Sanitizer、Lockdep 或 Panic 可能发生在测试结果行之外。
#. Case 输出 ``ok`` 但同时触发 KASAN、KCSAN、Lockdep、WARN 或 Refcount 报告，不应判为整体成功。
#. Test Case 被跳过必须说明原因，例如 Config、Architecture、Feature 或 Fixture 条件不满足。
#. ``KUNIT_SKIP()`` 表示当前 Case 未验证，不等同于通过。
#. KUnit Case 不应使用无上限等待；异步测试需要 Completion、明确 Timeout 和 Cleanup。
#. 固定 ``msleep()`` 不能证明异步路径完成，只会引入 Flaky Timing。
#. 测试 Workqueue、Timer 或 RCU 时，应等待真实同步边界并验证对象在同步前后的状态。
#. KUnit 在内核地址空间运行，测试 Bug 自身也可能 Panic、死锁或破坏全局状态。
#. 测试代码必须像生产内核代码一样遵守 Context、Locking、GFP 和生命周期规则。
#. KUnit 运行环境应尽量隔离，特别是使用 Sanitizer、Fault Injection 和高风险并发测试时。
#. 测试完成后必须恢复全局参数、Static Key、Hook、注册对象和故障注入状态。
#. Case 间共享全局状态会造成顺序依赖和 Flaky Failure，应尽量消除。
#. 若必须共享，Suite Fixture 要定义清晰的初始化、串行化和恢复协议。
#. KUnit 能快速验证局部错误路径，但真实用户入口仍需要 kselftest 或系统测试覆盖。
#. 一个修复可以同时包含 KUnit：固定根因逻辑；kselftest：固定用户态可见行为。
#. KUnit Coverage 只能说明测试执行到代码，不能证明边界输入、生命周期和并发状态均被断言。
#. KUnit 测试的稳定阅读顺序是：Kconfig/Makefile → Suite → Fixture → Cases → 被测接口 → Expect/Assert → Resource Cleanup → KTAP。

必背路径
--------

KUnit 对象链：

::

   Test Function(struct kunit *test)
   → KUNIT_CASE
   → struct kunit_case[]
   → struct kunit_suite
   → kunit_test_suite
   → Built-in Executor / Module Init / kunit_tool
   → KTAP Result

单个 Case：

::

   Arrange Fixture 与输入
   → Assert 前置对象有效
   → Act 调用被测函数
   → Expect 行为和状态
   → KUnit Resource Cleanup
   → 输出 Case Result

必须区分
--------

* ``KUNIT_EXPECT_*`` 与 ``KUNIT_ASSERT_*``：Expectation 记录失败后继续当前 Case；Assertion 在必要前置条件失败时立即终止当前 Case。
* 测试 Resource 生命周期与生产对象生命周期：KUnit Resource 管理 Fixture 和测试期资源；生产对象仍必须按真实注册、引用、异步收束和释放协议验证。
* UML 快速测试与真实硬件验证：UML 适合快速运行纯逻辑和错误路径；它不能代表真实架构、IRQ、DMA、Firmware 和设备时序。
* 内建执行器与 ``kunit.py`` 用户态工具：内建执行器在内核中发现并运行 Suite；``kunit.py`` 负责配置、构建、启动环境和解析 KTAP。
* KTAP ``ok`` 与没有任何内核运行时警告：``ok`` 只表示 Case 断言通过；KASAN、Lockdep、WARN、Oops 等日志仍会使整次运行失败。
* 内部逻辑正确与用户态接口契约正确：KUnit 能证明内部函数和对象行为；稳定 UAPI、权限和端到端交互仍需 kselftest 或系统测试。

一句话结论
----------

KUnit 把内核内部函数和对象变成可直接构造、断言和自动清理的白盒测试单元，使错误路径在接触完整系统和真实硬件前就能被验证。
