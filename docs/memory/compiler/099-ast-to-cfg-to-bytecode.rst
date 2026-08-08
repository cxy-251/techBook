第099章：AST to CFG to Bytecode
================================

核心知识点
----------

* CPython bytecode 不是 AST 的直接文本替换，而是经过作用域事实、AST code generation、pseudo instructions、CFG 组织和 assembler 装配形成的执行表示。
* Symbol table 已经完成名字分类，因此 AST codegen 处理 ``Name`` 节点时可以选择 local/global/closure 等不同访问策略。
* AST 保留源语言结构，例如 ``If``、``For``、``While``、``Try``、``Match``、``Return``；codegen 会把这些节点转换成更接近 VM 的 load、compare、jump、call、return 等动作。
* Pseudo instruction 阶段可以暂时使用逻辑 labels/basic-block references，跳转距离和最终指令布局尚未固定，因此更容易表达控制结构。
* CFG 把执行路径显式化为 basic blocks 和 edges。它位于线性 bytecode 之前，使 compiler 可以先处理控制关系，再决定最终线性排列。
* Basic block 是单入口的顺序指令区域，通常以条件跳转、无条件跳转、return 或其它控制转移结束。
* ``if`` 形成真假分支，``while``/``for`` 形成回边，``try`` 还包含异常 handler 关系，``match`` 则形成多条 case 测试/失败路径。
* CFG 使编译器可以在装配前分析 dead blocks、jump targets、stack depth 和路径一致性，而不必直接在字节 offset 上工作。
* CPython 的异常处理信息可以在中间阶段以结构关系保存，最终再装配成 code object 的 exception table；异常路径并不要求源码中存在显式跳转。
* Assembler 把 CFG/instruction sequence 线性化，解析逻辑 jump target，计算最终参数，并生成 bytecode 与相关元数据。
* Jump offset、opcode 名称、inline cache 和 ``dis`` 显示方式属于 CPython 版本相关实现细节；稳定关系是“控制流目标必须在最终指令布局中被正确解析”。
* 最终 code object 不只包含 bytecode，还包含 constants、names、locals、stack size、line/position tables、exception metadata 等执行与可观察性信息。
* Source location 会从 AST/pseudo instruction 一路传播到最终位置表，使 traceback、debugger、coverage 和 ``dis`` 能把执行位置重新映回源码。
* Bytecode 可以被 ``dis`` 观察，但 ``dis`` 输出是当前 CPython 实现证据，不是 Python 语言规范承诺。
* 排查编译结果时，稳定顺序是 ``AST node → generated actions → CFG blocks/edges → assembled bytecode → code-object metadata``。

关键路径
--------

编译主链：

::

   AST + symbol-table facts
   → walk AST nodes
   → emit bytecode-like pseudo instructions
   → create basic blocks and logical jump targets
   → build/optimize CFG
   → compute stack/control metadata
   → linearize blocks
   → resolve jump targets/offsets
   → emit bytecode + exception/position tables
   → code object

条件分支：

::

   If.test AST
   → evaluate condition
   → conditional jump
   → true basic block
   → false/fallthrough basic block
   → each path reaches return/merge
   → assembler assigns final positions

概念辨析
--------

* **AST control structure 与 CFG**：AST 表达 ``if/for/try`` 等语言结构，CFG 表达实际执行时哪些 basic blocks 可以互相转移。
* **Pseudo instruction 与 final bytecode**：前者可以保留逻辑目标和未决布局，后者已经拥有可执行的最终指令顺序与参数。
* **Basic block 与 source block**：basic block 按控制流边界切分，不与 Python 缩进块一一对应。
* **Jump target 与 byte offset**：前者是逻辑控制目标，最终布局阶段才会被编码成当前版本要求的位置参数。
* **Bytecode 与 code object**：bytecode 是指令序列；code object 还封装常量、名字、局部槽位、栈需求、异常和源码位置等元数据。

本章结论
--------

CPython 的后端主线是 ``AST → Pseudo Instructions → CFG → Assembler → Bytecode/Code Object``。源码中的结构化控制流会先被转换成图，再被装配成线性 VM 指令；因此分析 bytecode 时，应先恢复 basic blocks 和 jumps，而不是把每条 opcode 当作孤立翻译。