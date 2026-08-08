第070章：Calling Conventions as Binary-Level Contracts
=======================================================

核心知识点
----------

* Calling convention 是 caller 与 callee 对函数边界机器状态的共同协议，属于 ABI 的核心组成部分。
* 协议至少规定参数位置、返回值位置、caller/callee-saved 寄存器责任、stack alignment、stack cleanup、aggregate/varargs 规则和必要的 unwind 状态。
* 源码函数签名必须经过 ABI classification 才能变成寄存器和栈位置。参数序号本身不足以决定位置，还要看参数类型、目标平台和聚合分类规则。
* 小整数、指针和浮点值通常优先走寄存器，但不同 ABI 对整数类和浮点类参数的编号方式可能完全不同。
* 参数超过寄存器容量、类型需要间接传递、对齐特殊或 ABI 明确要求时，caller 会使用栈参数区或临时内存。
* Caller-saved registers 在调用后不保证保留，因此 caller 若仍需要其中的值，必须在调用前保存、移到安全寄存器或重新计算。
* Callee-saved registers 由 callee 使用后恢复。它们适合保存跨调用长生命周期值，但会增加函数自身 prologue/epilogue 成本。
* 标量返回值通常使用固定返回寄存器；小聚合可能拆到多个寄存器，大聚合常使用 caller 提供的 result buffer/sret hidden pointer。
* Hidden return pointer 会让源码中的 ``f(args) -> Struct`` 在二进制边界上变成“额外结果地址 + 显式参数”，后端 call lowering 必须同时重写 caller 和 callee 视角。
* Varargs 需要额外 ABI 规则，因为 callee 缺少匿名参数的完整静态类型信息；浮点参数复制、register save area、默认提升等都可能参与。
* Stack pointer 在公共调用边界必须满足 ABI 对齐。即使函数内部允许临时改变 SP，执行 call 前也必须恢复到被调用者假定的状态。
* Cross-language interoperability 依赖共享 ABI，而不是共享源语言。C、C++、Rust、Swift、Python extension 等能互调，是因为符号、布局和 calling convention 最终达成一致。
* ``extern "C"``、calling-convention attributes、``repr(C)`` 等机制主要是在控制 name mangling、layout 或 ABI 边界；不同语言仍需逐项确认类型宽度、alignment、ownership 和异常规则。
* Caller 与 callee 对签名或 ABI 的解释只要有一处不一致，就可能表现为参数乱码、返回值错误、保存寄存器损坏、stack imbalance 或 unwind 崩坏。
* Calling convention 是二进制层隐形协议：单个函数体内部完全正确，也可能因边界协议错误而整体失败。

关键路径
--------

参数传递：

::

   source function signature
   → ABI classify each argument
   → assign integer / FP / vector registers
   → overflow or indirect arguments to stack/memory
   → preserve stack alignment
   → emit call
   → callee reads same locations

返回值：

::

   return type
   → ABI classify result
   → scalar/small aggregate: return register(s)
   → large aggregate: caller allocates result buffer
   → pass hidden result pointer
   → callee writes result
   → caller consumes returned value/memory

跨语言边界：

::

   exported symbol + shared ABI
   → match name/linkage
   → match type width/layout/alignment
   → match calling convention and unwind rules
   → caller/callee exchange machine state
   → verify boundary with assembly/runtime tests

概念辨析
--------

* **Calling convention 与 ABI**：calling convention 主要描述函数调用协议；ABI 还包含数据布局、符号、对象格式等更广规则。
* **Parameter order 与 register order**：源码第几个参数不一定对应第几个通用寄存器，类型分类会改变分配路径。
* **Caller-saved 与 callee-saved**：这是保存责任划分，不是寄存器永久属于 caller 或 callee。
* **Aggregate return 与普通返回值**：大型聚合常通过隐藏结果地址返回，机器边界可能比源码签名多一个参数。
* **Cross-language call 与 source compatibility**：语言语法可以完全不同，只要二进制布局和调用协议一致就能互操作。

本章结论
--------

函数调用之所以能跨编译单元甚至跨语言工作，是因为双方遵守同一套二进制协议。稳定理解路径是 ``Signature → ABI Classification → Argument/Return Locations → Saved-Register Responsibility → Stack Contract → Call/Return``；任何函数边界 bug，都应优先检查 caller 与 callee 是否对这些机器状态做出了完全一致的解释。