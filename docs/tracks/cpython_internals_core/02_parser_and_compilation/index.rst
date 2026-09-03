======================================================
第 2 模块：前端编译与 AST 生成
======================================================

.. toctree::
   :maxdepth: 2
   :caption: 模块章节导航

   01_peg_parser_and_grammar
   02_cst_to_ast_transformation
   03_bytecode_generation_and_cfg
   04_peephole_and_bytecode_optimization

模块概述
========

本模块深入剖析 Python 源码从文本字符流到字节码序列的完整编译管线。

内容涵盖 PEG（Parsing Expression Grammar）解析器理论与 CPython 生成器状态机、词法分析器 Tokenizer 与缓冲流、具象语法树（CST）向抽象语法树（AST）的构建与属性折叠、符号表（Symbol Table）的作用域判定算法、控制流图（CFG）与基本块（Basicblock）划分、以及字节码生成与窥孔优化器（Peephole Optimizer）的指令特化与常量折叠。
