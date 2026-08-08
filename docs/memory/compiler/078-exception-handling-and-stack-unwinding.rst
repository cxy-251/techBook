第078章：Exception Handling and Stack Unwinding
================================================

核心知识点
----------

* Exception 是跨函数栈帧传播的 non-local control flow。普通 CFG 只能描述当前函数的一部分异常边，完整目标取决于动态调用栈和运行时 handler 匹配。
* 一个可抛异常调用通常同时有 normal continuation 和 unwind continuation。LLVM IR 中的 ``invoke`` 正是这种双后继表示。
* 异常路径必须保持资源语义。C++ 析构、``finally``、``defer`` 等 cleanup 在异常离开当前帧时仍要执行，不能因为控制流不是普通 ``return`` 就被跳过。
* Zero-cost EH 的目标是让未抛异常的正常路径尽量不增加显式检查，把大部分成本放到异常表、unwind metadata 和真正抛异常后的运行时处理。
* “Zero-cost” 不代表异常免费。代价仍存在于二进制元数据、编译器复杂度、异常对象创建、查表、stack unwinding 和 handler dispatch。
* Stack unwinding 同时需要机器层与语言层信息：机器层恢复 SP、FP、return address 和寄存器；语言层判断本帧是否有 cleanup 或 matching handler。
* Personality function 是 unwinder 与语言特定异常语义之间的接口。它根据异常类型和当前帧的语言相关表决定继续 unwind、执行 cleanup 还是进入 handler。
* 表驱动 EH 常采用两阶段过程：search phase 先寻找真正能处理异常的 handler；cleanup phase 再重新展开栈，执行中间帧 cleanup，最后转入目标 handler。
* Landing pad 是异常进入某个函数时的代码入口，可以执行析构/cleanup、匹配 catch，或在清理后继续 ``resume`` 同一个异常。
* Unwind metadata 把“某段机器地址对应什么栈恢复规则、什么异常动作”写入二进制。运行时依赖这些元数据重建源码看不到的异常控制流。
* ``nothrow``/``nounwind`` 一类属性会影响优化和 CFG。能证明调用不会 unwind 时，编译器可以删除异常边；证据不足时必须保留潜在异常路径。
* 异常处理会限制 code motion、DCE、inlining 和寄存器活跃性，因为对象状态必须在可能抛异常的程序点满足 cleanup 所需语义。
* 跨语言/跨库异常需要兼容的 exception ABI、object representation、personality/unwinder 协议；否则异常可能无法安全穿过边界。

关键路径
--------

异常传播：

::

   call may throw
   → exception object created / raised
   → search dynamic stack frames
   → personality checks current frame
   → find matching handler
   → unwind again through intermediate frames
   → run cleanup / destructors
   → install handler context
   → continue at catch/handler

函数内异常边：

::

   invoke-like call
   → normal edge: continue computation
   → unwind edge: enter landing pad
   → execute cleanup
   → handle locally or resume outward

概念辨析
--------

* **Exception edge 与 ordinary branch**：异常目标由动态调用栈和异常类型决定，不只是当前函数内固定条件分支。
* **Zero-cost EH 与 no-cost exceptions**：前者强调正常路径少检查，抛异常本身仍然昂贵。
* **Unwinder 与 personality function**：unwinder 负责机器级走栈和恢复，personality 负责语言特定 handler/cleanup 决策。
* **Landing pad 与 catch block**：landing pad 是机器/IR 异常入口，可以只做 cleanup；真正 catch handler 只是其中一种结果。
* **Cleanup 与 handler**：cleanup 保证资源释放后继续传播，handler 则真正消费异常并恢复普通执行。

本章结论
--------

异常处理本质上是“由元数据和 runtime 重建的跨栈控制流”。稳定理解路径是 ``Throw → Search → Unwind → Cleanup → Handler``；编译器负责把调用点、landing pad、资源清理和 unwind 表写进产物，runtime 再根据真实调用栈把异常安全送到正确处理点。