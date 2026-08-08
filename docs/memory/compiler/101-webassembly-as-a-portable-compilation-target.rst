第101章：WebAssembly as a Portable Compilation Target
======================================================

核心知识点
----------

* WebAssembly（Wasm）是面向编译器的低层、可移植、可验证目标格式。它不是源语言，也不是某个真实 CPU ISA，而是一台由 runtime 实现的抽象目标机器。
* 编译到 Wasm 时，源语言的语法、泛型、类层级、模板、所有权等高层语义通常已经被前端和中端处理；Wasm 主要承载函数、数值类型、控制流、局部值、内存、表、globals、imports 和 exports。
* Wasm 的可移植性来自稳定的目标语义，而不是“自动拥有相同操作系统环境”。核心指令可以跨 runtime 执行，文件、网络、时钟、随机数等外部能力仍取决于 imports、WASI 或宿主自定义接口。
* 多语言前端可以把 C/C++、Rust、AssemblyScript、TinyGo 等程序降低到同一种 Wasm module；Wasm 不需要理解各语言的全部高层规则，只接收已经 lower 后的执行语义。
* Wasm module 是 compiler 与 runtime 的关键交界点。编译器负责生成合法 module，runtime 负责 decode、validate、instantiate，并选择解释、JIT 或 AOT 方式执行。
* Wasm 的安全性与可移植性强依赖 validation。模块进入实际执行前，需要证明函数签名、operand stack、控制结构、索引空间等满足规范约束。
* ``.wat`` 是面向人的文本表示，``.wasm`` 是面向传输和执行的二进制表示；二者描述同一类 module 语义，文本名与调试信息可以在二进制中被弱化或剥离。
* WAT 中的 ``func``、``param``、``result``、``local.get``、``i32.add`` 等已经非常接近执行模型；源码中的语句块、变量声明方式和大部分表面结构已经消失。
* Imports/exports 定义 module 与宿主之间的接口边界。Export 让宿主调用模块能力，import 让模块显式请求外部函数、内存、表或其它资源。
* Browser、server、edge、embedded 和 plugin 场景共享同一个核心原则：Wasm 提供可验证计算模块，宿主决定外部资源、权限、生命周期和调用方式。
* 同一个 ``.wasm`` 是否能在不同环境运行，要同时检查核心 Wasm feature set 和宿主接口依赖。只兼容指令集并不等于兼容完整运行环境。
* Wasm 是“portable compilation target”，不是“portable source runtime”。语言 runtime、libc、allocator、异常、线程或系统 API 仍可能作为额外依赖进入最终产物。

关键路径
--------

编译与执行：

::

   source language
   → frontend / semantic analysis
   → language-neutral or target IR
   → Wasm backend
   → .wasm module
   → decode + validate
   → instantiate imports/exports/memory/table
   → interpreter / JIT / AOT execution
   → host CPU

可移植性判断：

::

   Wasm module
   → inspect core feature requirements
   → inspect imports
   → inspect runtime/WASI support
   → inspect host capabilities
   → determine whether module is actually portable to target environment

概念辨析
--------

* **Wasm 与 machine code**：Wasm 是抽象目标 ISA/代码格式，仍需 runtime 解释或编译成真实 CPU 指令。
* **Wasm portability 与 environment portability**：核心代码格式可以移植，宿主 API、WASI 版本和语言运行库仍可能绑定环境。
* **WAT 与 Wasm binary**：前者便于阅读和调试，后者用于紧凑传输、加载和执行。
* **Module 与 process**：module 是可实例化的代码与资源定义，不等同于传统操作系统进程。
* **Import/export 与 syscall**：imports/exports 是模块边界机制；系统调用只是宿主可能通过这些接口提供的一类能力。

本章结论
--------

WebAssembly 的稳定模型是 ``Source/IR → Wasm Module → Validation → Instantiation → Runtime Execution``。它的价值不在于替代真实 CPU，而在于为多语言编译器提供一台可移植、可验证、可嵌入的低层目标机器；真正的运行环境能力则通过显式宿主边界补齐。