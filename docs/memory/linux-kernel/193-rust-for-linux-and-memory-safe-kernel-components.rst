第193章：Rust for Linux 与内存安全内核组件
=========================================

核心知识点
----------

Rust 是选择性第二语言
   Rust for Linux 的目标是在新驱动和边界清晰的组件中，用类型系统表达更多内存与生命周期不变量，而不是重写整个 C 内核。

Safe Abstraction 是关键边界
   Rust 组件应优先通过 ``kernel`` Crate 的安全抽象访问内核能力。Generated Bindings 只暴露 C 类型和符号，不能证明锁、上下文和生命周期前提成立。

``unsafe`` 集中人工证明责任
   Safe API 的正确性依赖内部 ``unsafe`` 代码维护底层合同。审查应沿 Safe Caller、Abstraction Invariant、Unsafe Block、Binding 和 C API 逐层检查。

所有权不能替代内核生命周期协议
   所有权和 ``Drop`` 能减少重复释放与遗漏清理，仍必须先撤销外部入口并同步 Work、Timer、IRQ、DMA 和 C Callback，之后才能释放对象。

Pin 与受控初始化保护地址敏感对象
   ``Pin`` 适合包含锁、链表、Timer、Work 或 C 自引用的对象，保证对象不再移动。Fallible Initialization 还必须阻止半初始化对象发布，并在失败时清理已完成字段。

并发与 FFI 仍需运行时约束
   ``Send``、``Sync``、引用计数和借用不能自动证明硬件在线、数据竞争不存在或 C 侧隐藏指针安全。锁、RCU、原子操作和设备协议仍是必要基础。

工具链和测试属于安全合同
   Rust Compiler、Bindgen、Kconfig 和目标内核版本必须匹配。编译通过只证明静态约束成立，还需错误注入、并发压力、动态检测和真实设备测试。

关键路径
--------

Rust 内核调用：

::

   Rust Driver
   → Safe Abstraction
   → 所有权 / 生命周期 / Pin / Result
   → 受审查的 unsafe Block
   → Generated Bindings 或 C Helper
   → 既有 C Kernel API
   → 子系统与设备状态

对象生命周期：

::

   受控原地初始化
   → 完成底层 C 对象初始化
   → 注册到子系统
   → 对外提供 Safe Handle
   → 阻止新入口
   → 注销并同步异步活动
   → Drop / Put / Free

概念辨析
--------

* **Safe 调用面与内部实现已正确**：Safe API 降低调用者责任，仍依赖 Wrapper 正确维护全部底层不变量。
* **所有权与设备有效性**：所有权保护对象存储生命周期，不保证硬件、Firmware 和业务状态仍有效。
* **``Pin`` 与完整初始化**：``Pin`` 只保证地址稳定；初始化完成、注册成功和并发同步需要其它协议证明。
* **Binding 可调用与调用合法**：Binding 暴露函数形状，指针、长度、锁和上下文前提仍由调用者保证。
* **Rust 编译通过与设备行为正确**：编译器验证可表达的类型约束，FFI、并发和硬件协议仍需 Review 与运行测试。
* **Rust 与不再需要 Sanitizer**：Rust 减少部分内存错误，``unsafe``、C 回调和设备边界仍需 KASAN、KCSAN、Lockdep 与 Fault Injection。

本章结论
--------

Rust for Linux 通过安全抽象、所有权、生命周期和 Pin 把部分内核不变量前移到编译期，并把剩余的 C、并发和硬件风险集中到更小、更明确的 ``unsafe`` 边界。