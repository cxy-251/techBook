第076章：What the Compiler Leaves to the Runtime
=================================================

核心知识点
----------

* 编译器生成的是可执行路径、静态布局和元数据；runtime 维护的是一次具体执行才出现的对象、堆、栈、线程、动态类型、异常和调度状态。
* 判断一项语言能力属于编译期还是运行时，关键看它是否依赖当前对象图、当前调用栈、当前线程、当前模块表或动态输入。
* 编译器可以提前决定 CFG、调用点、闭包环境布局、异常 landing path、GC safepoint、类型描述等结构，却无法提前决定某次分配返回什么地址、哪个动态类型真正出现、异常最终被哪个 handler 捕获。
* Runtime helper 是编译器把复杂语言语义交给运行时的显式边界。对象分配、动态加法、闭包创建、类型检查、异常抛出、写屏障、宽整数/浮点 helper 都可能表现为自动插入的调用。
* Helper 并不只存在于动态语言。目标 ISA 缺少某种运算、sanitizer 插桩、栈保护、异常支持等都可能让 C/C++/Rust 一类静态语言产生运行时依赖。
* Helper 的语义属性会直接限制优化。分配、写屏障、异常、I/O、未知调用都可能修改内存或控制流，不能被当成普通纯函数随意移动或删除。
* 动态类型需要运行时类型证据，例如 tag、shape、type descriptor 或 method table；编译器可以生成 fast path，但 guard 失败后仍需进入通用 runtime path。
* 闭包把捕获关系从源码作用域转成环境对象布局。编译器决定“捕获哪些值”，runtime 维护“这个闭包实例当前指向哪个环境”。
* 异常语义依赖当前调用栈，编译器生成 unwind/landing metadata，runtime 再按真实栈状态查找 handler、执行 cleanup 并恢复控制流。
* GC 依赖对象图和 live references。编译器负责在 safepoint 提供栈/寄存器中的引用位置和对象布局，collector 再据此追踪、移动或回收对象。
* 协程/async 常被编译器 lower 成状态机，但恢复时机、线程、事件循环和调度顺序由 runtime 决定。
* Runtime metadata 包括 type descriptors、vtables/interface tables、exception tables、GC maps、stack maps、module tables 等，它们是生成代码和运行时共享的协议数据。
* 编译期与运行时错误要按边界定位：IR/lowering 错误、链接缺 helper、ABI 不匹配、运行时状态错误分别属于不同层级。

关键路径
--------

运行时边界：

::

   source language feature
   → determine static structure
   → lower dynamic responsibility to helper / metadata
   → emit code + binary metadata
   → runtime consumes current execution state
   → helper/VM/GC/EH returns or transfers control
   → generated code continues

动态语义：

::

   runtime value
   → inspect tag / type / shape
   → fast-path guard succeeds? use specialized code
   → otherwise enter generic helper
   → compute result / throw / allocate
   → return updated runtime state

概念辨析
--------

* **Compile-time structure 与 runtime state**：前者在所有执行中共享，后者随这一次执行的对象、栈、线程和输入变化。
* **Runtime helper 与用户函数**：helper 常由编译器隐式插入，属于语言/目标实现协议；用户函数来自程序显式逻辑。
* **Metadata 与 executable code**：metadata 本身不一定被 CPU 直接执行，但 runtime 会用它解释类型、异常、GC 和调用状态。
* **Static language 与 no runtime**：静态类型减少动态检查，不代表没有 allocator、unwinder、compiler runtime、startup code 等运行时依赖。
* **Lowering 与 runtime execution**：lowering 决定“运行时要做什么入口和协议”，真正结果仍由执行时状态决定。

本章结论
--------

编译器并不会把语言全部压成孤立机器指令，而是为一个持续变化的 runtime world 生成代码和协议。稳定理解路径是 ``Static Structure → Helper/Metadata Boundary → Runtime State → Runtime Action → Generated Code``；分析任何高级语言能力时，都应先定位哪些事实已经固化在编译产物中，哪些事实必须等运行时才能完成。