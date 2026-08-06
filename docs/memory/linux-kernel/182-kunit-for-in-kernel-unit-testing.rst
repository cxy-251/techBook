第182章：KUnit 内核内部单元测试
===============================

核心知识点
----------

KUnit 是内核白盒测试框架
   测试代码运行在内核上下文，可直接调用内部函数、构造内部对象并检查局部状态，不需要先经过用户态 ABI。

KUnit 适合小而稳定的边界
   纯逻辑、解析器、边界条件、数据结构和局部状态机最适合 KUnit；完整启动、真实设备和用户态合同应交给更高层测试。

Suite、Case 与 ``struct kunit`` 构成测试模型
   ``KUNIT_CASE`` 注册测试函数，``struct kunit_suite`` 组织 Case 和 Fixture，``struct kunit`` 保存当前 Case 的状态、诊断、私有数据与测试资源。

Expectation 与 Assertion 用途不同
   ``KUNIT_EXPECT_*`` 失败后继续执行，用于并列检查；``KUNIT_ASSERT_*`` 在必要前提失败时终止 Case，防止后续操作失去安全基础。

Fixture 和 Resource 必须正确清理
   初始化可能只完成一部分。清理逻辑必须识别已取得资源，KUnit Resource 可绑定自动释放回调，确保中止和失败时仍能回收测试资源。

Mock 只隔离外部依赖
   Fake Ops、Clock、Allocator 或 Bus 用于控制输入和错误路径，不应复制被测实现，也不应把可重构的内部调用顺序固定成测试合同。

异步与环境边界仍然存在
   Workqueue、Timer、RCU 等测试必须等待正式同步事件，不能依赖固定 Sleep。UML、QEMU 与真实硬件覆盖范围不同，KTAP 结果也必须与完整 Kernel Log 一起判断。

关键路径
--------

KUnit 注册与执行：

::

   Test Function
   → KUNIT_CASE
   → struct kunit_case[]
   → struct kunit_suite
   → 执行器运行
   → KTAP 输出

单个 Case：

::

   Fixture Init
   → Arrange
   → Assert 前提
   → Act
   → Expect 状态
   → Resource / Fixture Cleanup

概念辨析
--------

* **KUnit 与 kselftest**：KUnit 验证内核内部逻辑；kselftest 从用户态入口验证稳定接口。
* **Expectation 与 Assertion**：Expectation 收集更多失败信息；Assertion 保护后续执行所需的必要条件。
* **测试 Resource 与生产生命周期**：Resource 管理测试夹具；生产对象仍需验证真实引用、注册、取消和释放协议。
* **UML 与真实硬件**：UML 适合快速测试纯逻辑；DMA、IRQ、Firmware 和缓存行为仍需真实环境。
* **KTAP ``ok`` 与内核健康**：Case 通过不代表没有 KASAN、Lockdep、WARN 或 Oops，完整日志仍是判定依据。

本章结论
--------

KUnit 通过白盒调用、明确断言和自动清理，把内核局部逻辑与错误路径拆成可重复验证的最小测试单元。
