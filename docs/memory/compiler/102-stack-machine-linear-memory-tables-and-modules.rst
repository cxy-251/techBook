第102章：Stack Machine, Linear Memory, Tables, and Modules
==========================================================

核心知识点
----------

* Wasm 采用 stack-based execution model。指令通过隐式 operand stack 传递临时值，而不是直接暴露真实 CPU 的物理寄存器。
* ``local.get``、常量指令和算术指令通过 stack effect 连接。函数签名定义入口参数和出口结果，验证器据此检查所有执行路径的栈类型是否闭合。
* Operand stack 只保存临时计算值；locals、linear memory、tables、globals 和宿主资源是不同状态空间，分析时不能混在一起。
* Linear memory 是模块可通过整数地址访问的连续字节空间。Wasm 只定义原始 bytes 与 load/store，C/C++/Rust 的 heap、stack、object layout、allocator 元数据由编译器和语言 runtime 在其上构造。
* Linear memory 与 operand stack 完全不同：前者是可寻址持久字节状态，后者是指令之间的临时值通道。
* Data segment 在实例化时把初始 bytes 写入 linear memory；memory 的 initial/max size、growth 和访问宽度共同决定运行时访问是否合法。
* Table 是引用值的索引容器，典型用途是保存函数引用。它让函数指针、虚调用、回调和动态 dispatch 能在 Wasm 中受控表达。
* ``call_indirect`` 通过运行时 table slot 选择函数，同时要求目标 function type 匹配调用点声明；动态选择并没有取消类型约束。
* Linear memory 保存 bytes，table 保存 references。二者虽然都按 index 访问，但语义和验证规则不同。
* Module 是 Wasm 的加载与部署单位，包含 types、imports、functions、tables、memories、globals、data/element segments、exports 等定义。
* Module definition 与 instance 要区分。Module 是静态可复用定义，instance 才拥有具体 memory、table、globals 和已绑定 imports。
* Import 声明模块运行所需的外部依赖；实例化时宿主必须提供名称和类型匹配的实现。Export 则把内部 function/memory/table/global 暴露给宿主。
* 同一个 module 可以实例化多次，每个 instance 可以拥有不同状态和 imports，因此 module reuse 与 runtime isolation 可以同时存在。
* 阅读 Wasm 时，稳定顺序是 ``function signature/stack → memory → table/indirect calls → imports/exports → instance state``。

关键路径
--------

Operand stack：

::

   function locals/parameters
   → local.get / const
   → push typed operands
   → instruction consumes operands
   → push typed result
   → branch/call/return consumes resulting stack shape

Linear memory：

::

   address computation
   → push integer address
   → load/store instruction
   → bounds check against current memory
   → read/write bytes
   → source-language layout interprets those bytes

Indirect call：

::

   arguments + table slot index
   → lookup table entry
   → obtain function reference
   → check expected function type
   → enter target function
   → return typed result

Module lifecycle：

::

   static module
   → validate declarations and bodies
   → resolve imports
   → allocate/init memories, tables, globals
   → apply data/element segments
   → create instance
   → expose exports to host

概念辨析
--------

* **Operand stack 与 linear memory**：前者保存临时 typed values，后者保存模块可寻址原始 bytes。
* **Table 与 memory**：table 保存 reference values，memory 保存 bytes；``call_indirect`` 查 table，``load/store`` 访问 memory。
* **Function index 与 table slot**：前者是模块函数索引空间，后者是运行时 table 中的动态位置。
* **Module 与 instance**：module 是静态定义，instance 是绑定 imports 并拥有具体状态的运行时实体。
* **Import 与 export**：import 表示模块需要宿主提供什么，export 表示模块愿意向宿主提供什么。

本章结论
--------

Wasm 的核心机器模型可以压成 ``Typed Operand Stack + Linear Memory + Reference Tables + Module Boundary``。读一个模块时先追 stack effect，再区分 byte-addressed memory、reference table 和 host imports/exports，就能恢复它如何计算、保存状态、动态调用并与宿主连接。