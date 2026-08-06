第193章：Rust for Linux 与内存安全内核组件
=========================================

本章必须记住
------------

#. Rust for Linux 的目标不是重写整个内核，而是在选择性新代码中把部分内存安全和生命周期不变量移入类型系统。
#. Linux 内核仍以 C 为主体，Rust 组件通过内核 Rust Abstraction、Generated Bindings 和现有 C API 协作。
#. Rust 能减少部分 Use-after-free、越界、Double Free、未初始化和错误释放路径，不能自动证明硬件协议、并发设计和业务逻辑正确。
#. Rust 内核代码运行在 ``no_std`` 环境，不能直接使用普通用户态 ``std`` 运行时和系统 API。
#. ``kernel`` Crate 提供内核可用的分配、同步、设备、工作队列、用户访问和其它封装。
#. Rust Driver 理想上只使用经过审查的 Safe Abstraction，不直接依赖 Raw Generated Binding。
#. Generated C Bindings 只描述 C 类型和函数形状，不证明调用时机、锁状态和对象生命周期正确。
#. Rust Abstraction 的职责是把 C API 的前置条件转写成类型、构造、方法接收者、Drop 和错误语义。
#. 一个 Safe API 的安全性来自内部 ``unsafe`` 实现正确维护不变量，而不是来自函数没有 ``unsafe`` 关键字。
#. ``unsafe`` 表示编译器无法验证全部条件，调用者或实现者必须人工证明安全合同。
#. 稳定审查顺序是：Safe Caller → Abstraction Invariant → Unsafe Block → Binding → C API → Hardware/Subsystem State。
#. 所有权用于表达谁负责最终释放资源、注销对象、递减引用和执行错误回滚。
#. 单一 Owner 能减少同一资源在正常 Teardown 和错误路径中重复释放。
#. ``Drop`` 可自动执行资源释放，释放顺序仍必须符合底层 C 子系统协议。
#. Rust 值离开作用域自动 Drop，不等于底层异步 Callback、IRQ、Work 或 DMA 已经停止。
#. Drop 实现必须先撤销外部入口、同步异步活动，再释放底层对象。
#. Rust 借用和生命周期能约束普通引用有效期，不能直接替代 RCU、Refcount、Lock 和设备生命周期协议。
#. 跨 Workqueue、Timer、File Descriptor 或 C Callback 保存对象时，通常需要 Owned Handle、Reference Count 或注册句柄。
#. ``Arc`` 类引用计数封装保护对象存储生命周期，不自动保证硬件仍在线或业务状态仍有效。
#. Rust 的 ``Send`` 表示值可跨线程移动，``Sync`` 表示共享引用可跨线程访问；实现它们必须符合真实同步语义。
#. 对包含 Raw Pointer、FFI Object 或硬件状态的 Wrapper，``Send``/``Sync`` 不能机械自动实现。
#. 数据竞争安全仍依赖 Mutex、Spinlock、Atomic、RCU 或其它内核同步机制。
#. Rust 借用规则减少同一作用域内的可变别名，不覆盖 C 侧保存的隐藏指针和设备 DMA。
#. Slice 把 Pointer 与 Length 绑定，可减少分离传递导致的越界访问。
#. Slice 长度正确不证明设备实际写入长度、DMA Ownership 和协议字段可信。
#. 用户态、网络、固件和设备输入仍必须进行普通范围与语义校验。
#. 未初始化内核对象应使用受控初始化协议，不能在字段尚未完成时发布到 C 子系统。
#. ``MaybeUninit`` 允许表示未初始化存储，它本身不会自动完成初始化证明。
#. ``Pin`` 表达对象在被 Pin 后地址保持稳定，适合包含 C Self-reference、List、Lock、Timer、Work 等地址敏感对象。
#. Pin 只保证地址稳定，不保证对象已注册、没有并发访问或底层资源仍有效。
#. ``PinInit``、``pin_init!``、``try_pin_init!`` 等机制用于构造必须原地初始化的内核对象，精确 API 随版本演进。
#. Fallible Initializer 必须在失败时清理已经初始化的字段，并阻止半初始化对象被当作完整对象使用。
#. ``Opaque<T>`` 用于包装 Rust 不解释布局和内部不变量的 C/FFI 对象。
#. ``Opaque<bindings::mutex>`` 一类对象允许 C 侧初始化和修改，Rust 侧通过受控 Raw Pointer 访问。
#. Opaque 只隐藏内部表示，不自动提供锁、生命周期和线程安全。
#. Wrapper 必须说明 FFI 对象何时初始化、何时可调用、何时销毁以及是否要求 Pin。
#. Rust Abstraction 应尽量把错误返回映射为 ``Result``，保留内核 Errno 语义。
#. ``Result`` 强制调用者处理成功和失败分支，仍可能被错误传播或不完整 Cleanup 误用。
#. ``?`` 传播错误不会自动撤销已经发布到外部系统的对象；发布后的回滚仍需显式协议。
#. RAII 适合管理局部资源，跨注册表、Callback 和异步系统的 Ownership Transfer 必须明确。
#. 注册成功后，资源可能由 C 子系统持有；Rust 对象不能在仍被 C 侧引用时 Drop。
#. C API 若保存回调函数和 Context Pointer，Wrapper 必须保证 Context 在注销和同步完成前存活。
#. FFI 函数参数的 Pointer、Alignment、Lifetime、Mutability 和 Lock 前提均属于 ``unsafe`` 合同。
#. C 宏和 Inline Function 可能通过 ``rust/helpers/`` 等 Wrapper 暴露给 Rust，具体结构随内核版本变化。
#. Helper 只是跨语言桥接，不应绕过已有 Rust Abstraction 的安全边界。
#. Rust Driver 直接调用 Binding 会把底层 ``unsafe`` 条件扩散到叶子代码，增加审查成本。
#. 高质量 Abstraction 应服务多个真实调用者，并与子系统维护者共同定义稳定不变量。
#. 为单个驱动过度抽象会增加 API 和维护负担。
#. Rust 类型系统可以防止一部分非法状态被构造，不能表达所有硬件、时序和跨子系统状态。
#. MMIO、DMA、IRQ、Firmware、Power Management 和热插拔仍需要底层内核对象模型和顺序保证。
#. Volatile MMIO 访问安全不等于寄存器访问顺序、位语义和设备状态正确。
#. DMA Buffer 的 Rust 所有权必须与 CPU/Device Ownership、Mapping 和 Completion 对齐。
#. IOMMU 和设备隔离不由 Rust 自动提供。
#. Rust 内核模块仍需遵守 Kconfig、Kbuild、Module 生命周期、License 和符号可见性规则。
#. 是否编译 Rust 代码取决于架构支持、工具链、Kconfig、Makefile 和目标配置。
#. 源码树存在 Rust 文件不表示当前内核包含该功能。
#. Rust 编译器、Bindgen 和内核支持版本组成受控工具链，不能任意混用用户态最新工具版本。
#. Toolchain 要求随内核版本演进，应以目标内核文档和构建检查为准。
#. Rust 组件必须同时接受 Rust 编译器检查、内核 Coding Guideline、Clippy/Formatter 边界和子系统 Review。
#. 编译通过只证明类型与语法条件满足，不证明 FFI 不变量和硬件行为正确。
#. 测试应包含 KUnit 或 Rust 单元测试、kselftest、错误注入、并发压力和真实设备验证。
#. Safe Abstraction 的测试应覆盖正常构造、初始化失败、注册失败、Drop 和重复操作。
#. 对 Async Object 应验证 Work/Timer/IRQ 在对象释放前真正收束。
#. 对引用对象应验证 Clone/Get/Put 和最后 Release 路径。
#. 对用户输入和 Buffer 应验证边界、长度、空值、并发和错误码。
#. Sanitizer、KCSAN、Lockdep 和 Fault Injection 仍然适用于 Rust 内核组件及其 C 边界。
#. Rust 减少某些内存安全 Bug，不应因此关闭动态检测和错误路径测试。
#. Bug 可能集中到 ``unsafe`` Wrapper、错误 ``Send``/``Sync``、C 回调生命周期和硬件协议边界。
#. 审查 ``unsafe`` 时必须写出被假设的不变量，以及 Safe Caller 如何被类型阻止违反它。
#. 一个 ``unsafe`` Block 很短不代表风险小；关键是它能触达的对象和长期状态。
#. Safe Wrapper 若遗漏一个 C 前提，会把错误承诺传播给所有调用者。
#. 修改 Abstraction 时应运行全部调用者测试，因为安全合同是共享接口。
#. Rust 与 C 共存意味着最终对象生命周期可能跨语言；调查 Bug 时不能只看 Rust Stack 或 C Stack 一侧。
#. Panic 策略、分配失败和错误传播必须符合内核约束，不能套用普通用户态 Rust 假设。
#. 内核代码通常避免不可控 Unwind，具体 Panic 和 Allocation 行为按目标内核 Rust 规则确认。
#. Rust 不改变 Linux 的稳定 UAPI 原则；用户态接口兼容仍由子系统设计保证。
#. Rust Abstraction 本身也形成长期维护面，命名、可见性和安全合同应谨慎扩展。
#. Rust 的主要工程收益是改变 Bug 形态：把部分非法生命周期和访问提前变成编译错误，将剩余风险集中到更小的 ``unsafe`` 边界。
#. 稳定阅读顺序是：Kconfig/Kbuild → Rust Driver → Safe Abstraction → Ownership/Pin/Drop → Unsafe → Bindings → C 实现 → Teardown。

必背路径
--------

Rust 内核调用路径：

::

   Rust Driver
   → kernel Crate Safe Abstraction
   → 类型、所有权、Pin 与 Result 约束
   → 受审查的 unsafe Block
   → Generated Bindings / C Helper
   → 既有 C Kernel API
   → Subsystem / Device State

对象生命周期：

::

   Fallible Pin Initialization
   → 完成底层 C Object 初始化
   → 注册到子系统
   → Safe Handle 对外使用
   → 阻止新入口
   → 注销 Callback / Device / Work
   → 同步异步活动
   → Drop / Put / Free

必须区分
--------

* Safe Rust 调用面与内部 ``unsafe`` 条件已经正确：Safe API 只表示调用者无需执行 Unsafe 操作；其安全仍依赖 Wrapper 正确维护全部底层前提。
* 所有权保护存储生命周期与硬件和业务状态仍有效：所有权防止对象内存被错误释放；设备在线、Firmware 状态和业务有效性仍需运行时协议保证。
* ``Pin`` 地址稳定与对象已经初始化和同步：``Pin`` 只保证对象不再移动；初始化完成、注册成功和异步收束必须由其它状态与 API 证明。
* Generated Binding 可调用与调用满足 C API 合同：Binding 只暴露 C 符号和类型；锁、指针、长度、Context 和生命周期前提仍由调用方保证。
* Rust 编译通过与 FFI、并发和设备行为正确：编译器验证类型系统能表达的约束；跨语言合同、同步和硬件协议仍需 Review 与运行测试。
* 减少部分内存安全错误与不再需要 Sanitizer 和故障测试：Rust 能提前阻止部分非法状态；``unsafe``、C 回调和设备边界仍需 KASAN、KCSAN、Lockdep 与 Fault Injection。
* Rust 作为选择性第二语言与重写整个 Linux 内核：Rust 用于边界清晰的新驱动和抽象；C 仍是主体，两种语言会长期通过受控接口共存。

一句话结论
----------

Rust for Linux 通过 Safe Abstraction、所有权、生命周期和 Pin 把部分内核对象不变量移入类型系统，同时把无法静态证明的 C、并发和硬件风险集中到可审查的 ``unsafe`` 边界。
