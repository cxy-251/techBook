第003章：Compilation as a Sequence of Representations
====================================================

核心知识点
----------

* 编译过程不是源码直接变机器码，而是一串表示连续改写：token stream → AST → IR → Machine IR → object file / executable。
* 每层表示只保留后续阶段需要的信息，同时丢弃已经不重要的源码形态，并增加本层必须满足的新约束。
* AST 偏语言结构；IR 偏控制流、数据流和可优化事实；Machine IR 偏目标指令、寄存器、栈帧和 ABI；object file 偏 section、symbol、relocation 和 debug info。
* lowering 是向执行环境移动的过程：高层语言关系逐步变成显式的值、控制流、内存、寄存器、指令和文件格式约束。
* analysis pass 只读取当前表示并产生事实；transformation pass 改写表示。表示被修改后，旧 analysis fact 必须失效、更新或重新计算。

关键路径
--------

* lexer 将源码字符组织为 token；parser 将 token 组织成 AST；semantic analysis 为 AST 补充类型、绑定和作用域事实。
* AST lowering 到 IR 后，源码变量和语句被压缩成 value definition/use、basic block、branch、load/store 等关系。
* middle-end analysis 产生控制流、数据流、alias、loop 等事实，transform pass 根据这些事实改写 IR。
* backend lowering 将 IR 变成目标相关表示，并依次处理 instruction selection、register allocation、prologue/epilogue、encoding 等问题。
* 最终 object file 保存代码、数据、符号、重定位和可选调试信息，再由 linker / loader 继续完成执行前构造。

概念辨析
--------

* **AST vs IR**：AST 尽量保留语言结构；IR 更关注分析和执行关系，不要求保持源码语句形状。
* **IR vs Machine IR**：前者通常相对 target-independent；后者已经承担 ISA、寄存器和 ABI 约束。
* **lowering vs optimization**：lowering 主要改变抽象层级；optimization 主要在保持语义下改善某种成本，两者可以交织。
* **analysis fact vs program representation**：analysis 是从当前表示推导出的附加事实，不等于程序本体；表示变化可能让事实失效。
* **object file vs executable**：object file 通常仍含未解析符号和 relocation；链接后才形成更完整的可执行映像。

本章结论
--------

理解编译器首先要理解表示。每次遇到编译现象，都应问：当前处在哪一层表示、这一层保留了什么、丢弃了什么、新增了什么约束，以及哪些分析事实仍然有效。编译管线的绝大多数复杂度，都可以还原成这些表示之间的转换关系。
