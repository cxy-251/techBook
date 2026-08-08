第075章：Debug Information and Source-Level Observability
=========================================================

核心知识点
----------

* Debug information 是编译器为“从机器世界返回源码世界”保留的元数据。它让 debugger 能把 program counter、寄存器、stack frame 和地址范围解释成源码文件、行列、函数、类型和变量。
* 机器码本身只需要保证程序执行，不必保留源码变量名、语句边界、循环形状或内联调用关系；debug info 专门补回这些可观察证据。
* Symbol table 与 debug info 不是同一层。普通 symbol table 主要记录函数/全局名字与地址，debug info 还要描述局部变量、词法作用域、类型、源码位置、内联和变量位置变化。
* DWARF 是 Unix-like/Apple 工具链常见的结构化调试格式。其核心对象包括 DIE、line table、range/location lists、字符串表和 frame/unwind 信息。
* DIE（Debugging Information Entry）用 tag + attributes 描述 compilation unit、subprogram、parameter、variable、type、lexical block、inlined subroutine 等源码对象，并通过引用构成结构化关系。
* Line table 回答“某个机器地址对应哪个源码文件/行列”；它不负责说明变量当前存在哪里。
* Variable location 回答“在某个机器地址范围内，怎样取得这个源码变量的值”。位置可以是寄存器、stack slot、常量、地址表达式或多个 fragments 的组合。
* 同一个变量在不同地址范围内可以位于不同位置，因此 optimized debug info 常使用 location list，而不是“一个变量永远在同一个栈偏移”。
* Type information 决定 debugger 如何解释底层位模式。没有类型描述，寄存器或内存只是一串 bytes，无法稳定显示结构体、枚举、指针、泛型实例等源码对象。
* Inline debug records 可以在没有真实机器 call/frame 的情况下恢复源码级内联调用链，因此 debugger 展示的“inline frame”不等于真实 stack frame。
* Optimization 会引起 source-level drift：指令移动、DCE、CSE、inlining、register allocation、tail duplication 等都会破坏源码与机器指令的一一对应。
* ``optimized out``/``unavailable`` 往往表示当前 PC 对应的 debug location record 无法再恢复该变量，而不是程序运行时一定不存在这个概念值。
* 同一源码行可以对应多段机器地址，一条源码语句也可能完全没有独立指令；单步跳行、断点偏移和变量值突然变化都可能是合法优化结果。
* Unwind information 与普通变量 debug info 职责不同：前者帮助恢复 caller frame/寄存器状态，后者帮助解释源码变量和类型。异常展开、profiler 和 debugger 都可能消费 unwind 数据。
* Stripping 可以移除部分符号/debug sections 而不影响程序执行；生产环境也可以把完整调试信息拆到独立 debug file/PDB/dSYM 中，通过 build ID、UUID 等机制重新关联。
* 调试信息提高 observability，不改变程序语义。若程序运行结果正确但 debugger 显示失真，应先判断是 debug metadata 漂移，还是机器代码本身真的 wrong-code。

关键路径
--------

地址回到源码：

::

   program counter
   → locate binary / compilation unit range
   → query line table
   → obtain source file + line/column
   → query lexical scope / inline chain
   → construct source-level frame view

变量恢复：

::

   current PC + source variable
   → find variable DIE / debug record
   → select matching location range
   → evaluate register/stack/location expression
   → read runtime bits
   → interpret through type information
   → display source-level value

优化后调试：

::

   source variable / statement
   → optimization moves/merges/removes computations
   → update debug ranges and locations
   → register allocation changes value locations
   → emit final debug records
   → debugger shows best recoverable source view

概念辨析
--------

* **Symbol table 与 debug info**：symbol table 足以给函数/全局地址命名，debug info 负责更细的局部变量、类型、行号和作用域映射。
* **Line table 与 variable location**：前者把地址映射到源码位置，后者说明变量当前在哪里或如何计算。
* **Source frame 与 machine stack frame**：内联函数可以有源码级 frame 却没有独立物理栈帧。
* **Optimized out 与 dead value**：debugger 无法恢复变量位置不等于所有机器层等价值都已消失；只是缺少可靠源码映射。
* **Debug correctness 与 program correctness**：debug metadata 可以有 bug 或不完整，而程序机器语义仍然正确；两类问题应分别定位。

本章结论
--------

Debug info 是编译器在优化和代码生成破坏源码形状之后保留下来的“反向地图”。稳定理解路径是 ``PC/Registers/Stack → Address Range → Line/Scope → Variable Location → Type → Source View``；优化越强，源码和机器的一一对应越弱，因此高质量调试依赖编译器持续维护这些映射，而不是要求机器码继续长得像源码。