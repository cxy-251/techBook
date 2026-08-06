第182章：KUnit 内核内部单元测试
===============================

核心知识点
----------

KUnit 是内核白盒单元测试框架
   测试代码与被测代码都运行在内核上下文，可直接调用内部函数、构造内部结构体并验证局部状态机，不需要先经过用户态 ABI。

KUnit 适合小而稳定的对象边界
   解析器、纯逻辑、边界条件、局部数据结构、错误转换和不依赖真实硬件的小状态机最适合 KUnit。完整启动、真实设备和用户契约仍需更高层测试。

测试对象由 Suite 与 Case 组织
   测试函数经 ``KUNIT_CASE`` 进入 Case 数组，再由 ``struct kunit_suite`` 组织 Fixture 和注册信息，最终由内建执行器、模块加载或测试工具运行。

``struct kunit`` 是当前 Case 上下文
   它承载失败状态、诊断输出、私有 Fixture 和测试资源。Case 内的断言、分配和清理都围绕该对象建立生命周期。

Expectation 与 Assertion 作用不同
   ``KUNIT_EXPECT_*`` 记录失败后继续执行，适合并列检查多个结果；``KUNIT_ASSERT_*`` 在必要前置条件失败时立即终止，防止后续解引用或状态操作失去安全基础。

Fixture 必须支持部分初始化
   Case 前置初始化可能在任一步失败，清理函数必须识别哪些资源已经建立，不能假设 Arrange 阶段全部成功。

Resource API 管理测试资源
   KUnit Resource 将内存和自定义清理回调绑定到测试上下文，使 Assertion 中止或 Case 失败时仍能清理 Fixture。它不能替代生产对象自身的引用和释放协议测试。

Mock 应隔离外部依赖
   Ops Table、Fake Clock、Fake Allocator、Fake Bus 和受控返回值可把硬件或全局环境移出测试。Mock 不应复制被测实现，也不应固化无关内部调用顺序。

运行环境决定覆盖边界
   UML 适合快速执行纯逻辑；QEMU 可覆盖更多目标架构路径；真实硬件才能验证 DMA、IRQ、Firmware、缓存一致性和设备时序。

KTAP 是结构化结果协议
   Suite、Case、Plan、``ok``、``not ok`` 和诊断信息组成 KTAP 输出。CI 仍需同时检查完整 Kernel Log，避免遗漏断言之外的 Sanitizer、Lockdep 或 Oops。

异步测试必须使用真实同步边界
   Workqueue、Timer、RCU 和 Completion 测试应等待明确事件并设置上限，不能用固定 ``msleep`` 代替状态确认。

测试代码也必须遵守内核规则
   KUnit 运行在内核地址空间，错误的锁、GFP、Context 或全局状态恢复同样会导致 Panic、死锁和后续 Case 污染。

关键路径
--------

KUnit 对象链：

::

   Test Function(struct kunit *test)
   → KUNIT_CASE
   → struct kunit_case[]
   → struct kunit_suite
   → 注册 Suite
   → 内建执行器 / 模块 / kunit_tool
   → KTAP 结果

单个 Case 生命周期：

::

   Fixture Init
   → Arrange 输入和依赖
   → Assert 必要前置条件
   → Act 调用被测接口
   → Expect 输出与对象状态
   → Resource / Fixture Cleanup
   → 输出 Case Result

局部错误路径测试：

::

   注入依赖返回错误
   → 调用生产接口
   → 验证返回值
   → 验证未发布半对象
   → 验证引用、列表和资源恢复
   → 再次调用并确认可重复

概念辨析
--------

* **KUnit 与 kselftest**：KUnit 直接验证内核内部函数和对象；kselftest 从用户态入口验证返回值、事件、权限和稳定 ABI。
* **Expectation 与 Assertion**：Expectation 保留更多失败信息；Assertion 用于保护后续执行必须成立的安全前提。
* **测试 Resource 与生产生命周期**：Resource 管理测试夹具；生产对象仍需按真实 Get/Put、注册、异步取消和释放协议验证。
* **UML 与真实硬件**：UML 提供快速内核执行环境；它不能覆盖真实 DMA、IRQ、Firmware 和物理缓存行为。
* **KTAP ``ok`` 与内核健康**：Case 断言通过不代表没有 KASAN、Lockdep、WARN 或 Oops，完整日志仍是判定依据。
* **Mock 合同与实现细节**：应断言稳定输入输出和所有权合同，不应把可重构的内部调用顺序固定成测试目标。

本章结论
--------

KUnit 将内核内部逻辑拆成可构造、可断言、可自动清理的白盒测试单元，使局部状态机和错误路径在进入完整系统前就能被稳定验证。
