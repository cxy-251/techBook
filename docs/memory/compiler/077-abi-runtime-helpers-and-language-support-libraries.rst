第077章：ABI, Runtime Helpers, and Language Support Libraries
==============================================================

核心知识点
----------

* ABI 是已经编译完成的组件之间共享的二进制契约，覆盖参数/返回值位置、寄存器保存责任、stack alignment、symbol naming、对象布局、异常展开和动态链接等规则。
* API 主要约束源码层接口；ABI 约束 object file、library 和 runtime 在没有源码上下文时如何互相理解。
* 跨组件结构体必须在字段顺序、大小、alignment、padding、pointer width 和 calling convention 上一致，否则源码声明相同也会在机器边界错位。
* ``extern "C"`` 一类机制可以稳定 linkage/name mangling，但它只解决“符号如何被找到”的一部分问题，参数布局、对象布局和异常协议仍需 ABI 一致。
* Runtime library 把语言或目标机器无法全部内联表达的语义实现为可链接二进制，例如 startup code、allocator、memcpy/memset、异常/RTTI、unwinder、sanitizer runtime 和低级算术 helper。
* Compiler runtime 与普通标准库职责不同。前者常由编译器自动生成调用，用于目标缺失操作、栈保护、异常、插桩等；标准库更多提供语言/API 层可见功能。
* 编译器可以把 ``memcpy`` 识别成 intrinsic-like memory semantics，再选择内联 load/store、目标向量指令或外部库调用；同一源码调用不保证最终保留同名函数调用。
* 程序入口通常不是直接从 ``main`` 开始。loader 与 startup/crt code 会准备参数、环境、TLS、全局初始化，再进入用户入口；退出时还要处理析构、I/O flush 和 exit status。
* C++ 异常、RTTI、vtable、guard variable、name mangling 等会形成更复杂的 ABI 依赖；跨编译器或跨版本库互操作必须确认对象模型和异常协议兼容。
* Compiler-inserted calls 是隐藏依赖。源码未出现 ``__stack_chk_fail``、``__asan_*``、``_Unwind_*``、低级除法 helper 等符号，object file 仍可能引用它们。
* 链接错误应先按符号类别判断依赖来自 libc、compiler runtime、C++ ABI runtime、unwinder、sanitizer、startup object 还是用户库，而不是只在源代码中找显式调用。
* 跨语言 FFI 能工作，依赖的是双方最终共享 calling convention、layout、ownership、exception/panic boundary 和 symbol/linkage 约定。
* ABI 稳定性是二进制复用前提。源码兼容不等于二进制兼容，结构体布局、vtable 形状、标准库实现或 calling convention 改变都可能破坏已有二进制。

关键路径
--------

二进制调用边界：

::

   source declaration
   → lower to platform ABI
   → classify arguments / return value
   → place values in registers / stack
   → resolve symbol and call target
   → callee reads same ABI state
   → restore preserved registers / stack
   → return result

隐藏运行时依赖：

::

   source operation
   → compiler decides direct code or helper
   → emit helper symbol reference
   → object file relocation
   → linker selects runtime library implementation
   → loader maps dependency
   → runtime helper executes semantics

跨语言互操作：

::

   shared external interface
   → stabilize linkage/name
   → match type width/layout/alignment
   → match calling convention
   → match ownership/error/unwind rules
   → link and execute boundary test

概念辨析
--------

* **API 与 ABI**：API 面向源码使用方式，ABI 面向编译后机器状态和二进制布局。
* **Runtime library 与 compiler runtime**：前者范围更广；compiler runtime 特别承接编译器自动生成的低级语义和工具插桩。
* **Symbol compatibility 与 ABI compatibility**：名字能链接上只说明入口找到，不保证参数、布局和异常语义一致。
* **Standard library call 与 intrinsic/helper lowering**：源码写成库调用，编译器可能把它内联、替换或 lower 到不同 helper。
* **Cross-language interoperability 与 source-language similarity**：语言语法无关紧要，最终二进制契约一致才是关键。

本章结论
--------

ABI、runtime helper 和 language support library 共同把独立编译出的机器代码组织成一个系统。稳定理解路径是 ``Source Interface → ABI Classification → Object/Symbol Dependency → Runtime Library → Binary Execution``；一旦跨组件出现参数错位、未定义符号、异常失败或布局错误，应优先检查二进制契约，而不是只看源码表面。