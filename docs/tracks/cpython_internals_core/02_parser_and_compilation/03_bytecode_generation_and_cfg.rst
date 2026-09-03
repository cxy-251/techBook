=============================================================================
控制流图 CFG 构建、Basicblock 划分与字节码编译器 CodeGen 流程
=============================================================================

.. note:: 前置背景与上下文承接
   在前一章中，我们剖析了具象语法树（CST）到抽象语法树（AST）的内联折叠原理，以及符号表系统（``symtable.c``）如何通过两阶段遍历在编译期静态判定变量的五大作用域（``LOCAL``、``GLOBAL_EXPLICIT``、``GLOBAL_IMPLICIT``、``CELL``、``FREE``）。至此，AST 上的每一个节点均已具备了完备的语义与作用域元数据。
   
   然而，树状的 AST 无法直接在基于栈式虚拟机的线性执行引擎（CEval）上运行。编译器必须将分层的 AST 树“展平”为线性的控制流序列。本章将深入 CPython 核心源码文件 ``Python/compile.c``、``Python/codegen.c``、``Python/flowgraph.c`` 以及 ``Python/assemble.c``，深度解构从 AST 访问者模式生成中间伪指令序列（Instruction Sequence）、控制流图（Control Flow Graph, CFG）与基本块（Basicblock）的物理切分算法、基于抽象解释（Abstract Interpretation）求解栈深度 ``co_stacksize`` 的数学过程、CFG 拓扑与冷热块重排优化，以及汇编器最终打包生成 ``PyCodeObject`` 物理实体的完整流水线。

-----------------------------------------------------------------------------
1. CPython 编译管线全景拓扑
-----------------------------------------------------------------------------

从 AST 到最终可执行的 ``PyCodeObject``，CPython 经历了 4 个严格解耦的子阶段：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                  CPython 字节码编译器 4 阶段物理流水线                  |
   +=========================================================================+
   | 阶段 1：CodeGen 代码生成 (Python/codegen.c)                             |
   | └─ 遍历 AST，发射带有符号标签与伪指令的线性序列 _PyInstructionSequence   |
   +-------------------------------------------------------------------------+
                                     │
                                     ▼
   +-------------------------------------------------------------------------+
   | 阶段 2：控制流图构建与基本块切分 (Python/flowgraph.c)                   |
   | └─ 识别跳转目标与终结符，切分 basicblock 结构体，建立有向图拓扑网络     |
   +-------------------------------------------------------------------------+
                                     │
                                     ▼
   +-------------------------------------------------------------------------+
   | 阶段 3：CFG 拓扑优化与栈深抽象求解 (Python/flowgraph.c)                 |
   | └─ 死块消除、跳转穿透、常量折叠、冷块后置重排、计算精确 co_stacksize     |
   +-------------------------------------------------------------------------+
                                     │
                                     ▼
   +-------------------------------------------------------------------------+
   | 阶段 4：汇编器与 CodeObject 打包 (Python/assemble.c)                    |
   | └─ 展开 EXTENDED_ARG、编码 16 位 Code Units、生成 linetable/exception   |
   |    打包产出不可变的 PyCodeObject 内存实体                               |
   +-------------------------------------------------------------------------+

-----------------------------------------------------------------------------
2. CodeGen 阶段：AST 遍历与伪指令序列生成
-----------------------------------------------------------------------------

代码生成器 ``Python/codegen.c`` 本质上是一个遵循访问者模式（Visitor Pattern）的 AST 遍历器。对于 AST 中的每一个语句和表达式节点，CodeGen 会调用相应的发射宏将中间指令推入 ``_PyInstructionSequence`` 缓冲区：

.. code-block:: c

   typedef struct {
       int i_opcode;                    /* 字节码操作码或伪指令 */
       int i_oparg;                     /* 指令操作数或跳转标签 ID */
       _Py_SourceLocation i_loc;        /* 源代码精确行列位置 (lineno, col_offset...) */
       _PyExceptHandlerInfo i_except;   /* 关联的异常处理块元数据 */
   } _PyInstruction;

   typedef struct {
       _PyInstruction *s_instrs;        /* 动态扩容的中间指令数组 */
       int s_allocated;                 /* 分配容量 */
       int s_used;                      /* 已使用条目数 */
   } _PyInstructionSequence;

伪指令（Pseudo-Instructions）与符号标签（Jump Target Labels）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 AST 遍历期间，由于后续代码尚未生成，许多分支跳转的绝对/相对字节码偏移量是未知的。为此，CodeGen 引入了**虚拟标签（Labels）**与**高级伪指令（Pseudo-instructions）**：

1. **符号标签（``_PyJumpTargetLabel``）**：
   在遇到 ``if-else`` 或 ``while`` 循环时，编译器生成唯一的抽象标签（如 ``lbl_else``, ``lbl_end``），发射跳转指令 ``POP_JUMP_IF_FALSE lbl_else``，而无需计算真实的字节偏移。
2. **高级伪指令（Pseudo-opcodes）**：
   在 CodeGen 阶段，编译器允许发射更高层级的伪指令，例如：
   - ``LOAD_CLOSURE``：后续在汇编阶段被规约转换为真实的 ``LOAD_FAST`` 或 ``LOAD_DEREF``；
   - ``STORE_FAST_MAYBE_NULL``：允许向未初始化的局部变量槽位写入；
   - ``JUMP_IF_FALSE``：后续被展开为 ``COPY 1`` + ``TO_BOOL`` + ``POP_JUMP_IF_FALSE`` 组合指令。

-----------------------------------------------------------------------------
3. 控制流图（CFG）与基本块（Basicblock）划分算法
-----------------------------------------------------------------------------

在 ``Python/flowgraph.c`` 中，线性指令流被重构成真正的有向图（Directed Graph）—— 控制流图（CFG）。CFG 的基础节点是 **基本块（Basicblock）**。

基本块（Basicblock）的图论定义
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. warning:: 基本块的两大物理不变量
   1. **单入口（Single Entry）**：除基本块的第一条指令外，图中的任何其他边绝对不允许跳转进入该块的中间；
   2. **单出口（Single Exit）**：控制流一旦从第一条指令进入，必须严格顺序执行至该块的最后一条指令，中间绝不发生任何分支或退出。

``basicblock`` 结构体内存拓扑
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: c

   typedef struct _PyCfgBasicblock {
       struct _PyCfgBasicblock *b_list;    /* 内存分配逆序单向链表 (供内存追踪与销毁) */
       _PyJumpTargetLabel b_label;         /* 该基本块关联的标签 ID (若为跳转目标) */
       cfg_instr *b_instr;                 /* 该块所包含的指令动态数组 */
       struct _PyCfgBasicblock *b_next;    /* 控制流正常 Fallthrough 的下一个基本块 */
       int b_iused;                        /* 已使用的指令数量 */
       int b_ialloc;                       /* 指令数组容量 */
       int b_predecessors;                 /* 前驱节点计数 (指向该块的有向边数量) */
       int b_startdepth;                   /* 进入该基本块时的操作数栈深度 */
       unsigned b_cold : 1;                /* 冷块标记 (如异常处理代码，需后置重排) */
       unsigned b_warm : 1;                /* 热块标记 */
       unsigned b_except_handler : 1;      /* 标记该块是否为异常捕获入口 */
   } basicblock;

基本块切分判定状态机
~~~~~~~~~~~~~~~~~~~~

``flowgraph.c`` 在扫描指令流时，一旦遇到以下条件之一，立即闭合当前基本块并开启新的基本块：
1. **遇到终结符指令（``IS_TERMINATOR_OPCODE``）**：
   包括无条件跳转（``JUMP``）、作用域退出（``RETURN_VALUE``、``RAISE_VARARGS``）等。这些指令之后紧随的代码无法通过自然下落（Fallthrough）到达，必须切断。
2. **遇到跳转目标标签（``UseLabel``）**：
   标签意味着外部存在指向此处的跳转边，为满足“单入口”约束，必须将此标签作为新基本块的起始第一条指令。

-----------------------------------------------------------------------------
4. CFG 核心优化与拓扑重排
-----------------------------------------------------------------------------

在 CFG 构建完成后，CPython 执行一系列强大的图论优化通道（Passes）：

.. code-block:: text

   [CFG 优化通道流水线]
            │
            ├─► 1. 死代码消除 (remove_unreachable)
            │     └─ 遍历前驱计数，剔除 b_predecessors == 0 的孤立无用块
            │
            ├─► 2. 跳转穿透 (Jump Threading / Jump to Jump)
            │     └─ 若 Block A 跳转至 Block B，而 Block B 仅包含跳转至 Block C，
            │        直接重写 A 的跳转目标为 Block C！
            │
            ├─► 3. 基本块常量折叠 (fold_const_binop / fold_tuple)
            │     └─ 编译期静态计算 1 + 2 ──► LOAD_CONST 3
            │     └─ 将连续 LOAD_CONST 构造列表/元组优化为单个常量元组
            │
            ├─► 4. 冗余指令对消除 (remove_redundant_nops_and_pairs)
            │     └─ 消除 LOAD_CONST + POP_TOP, COPY 1 + POP_TOP 等无用组合
            │
            ├─► 5. 超级指令合成 (insert_superinstructions)
            │     └─ LOAD_FAST + LOAD_FAST ──► LOAD_FAST_LOAD_FAST
            │     └─ STORE_FAST + LOAD_FAST ──► STORE_FAST_LOAD_FAST
            │
            └─► 6. 冷热块分离重排 (push_cold_blocks_to_end)
                  └─ 将异常处理等 cold 块整体迁移至函数末尾，最大化 CPU I-Cache 命中率

冷热块分离（Cold-Block Separation）的硬件意义
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在现代 CPU（如 Apple Silicon ARM64、Intel x86-64）中，L1 指令缓存（I-Cache）通常仅有 32KB~64KB。
大部分 Python 函数中的 ``try...except`` 异常处理代码在 99% 的运行场景下都不会被触发。如果将异常处理块内联插在主干逻辑中间，会导致高频执行的正常分支被异常代码割裂，破坏 CPU 硬件预取器（Instruction Prefetcher）与分支预测器的连续性。

CPython 通过 ``push_cold_blocks_to_end()``，将所有被标记为 ``b_cold == 1`` 的基本块整体“搬迁”到整个 CodeObject 字节码的最尾端，使得主干逻辑在物理内存中高度紧凑连续，极大压榨了 CPU 硬件缓存能效。

-----------------------------------------------------------------------------
5. 抽象解释求栈深：calculate_stackdepth()
-----------------------------------------------------------------------------

Python 虚拟机是一个基于栈的求值引擎。在执行任何函数栈帧时，解释器都需要在物理内存中为操作数栈预留足够的空间。

.. warning:: 为什么栈深必须在编译期精确静态确定？
   如果允许栈在运行时动态分配或无界增长，每次执行压栈指令都必须执行边界检查（Bounds Check），产生极大的运行时损耗。通过在编译期计算出函数执行过程中**最坏情况下的最大栈深度（``co_stacksize``）**，虚拟机在创建栈帧时即可一次性分配固定大小的连续内存，运行时无须任何越界检查。

抽象解释遍历推导
~~~~~~~~~~~~~~~~

在 ``Python/flowgraph.c`` 的 ``calculate_stackdepth()`` 中，编译器使用抽象解释器对整个 CFG 进行静态模拟：

1. **栈效应定义**：每条指令 $I$ 根据其操作码与操作数，定义了净推栈效应：

   $$\Delta 	ext{depth} = 	ext{pushed}(I) - 	ext{popped}(I)$$

2. **图遍历传播**：
   - 设入口基本块的初始栈深 $D_{	ext{entry}} = 0$；
   - 沿基本块指令逐条累加 $	ext{depth}_{k+1} = 	ext{depth}_k + \Delta 	ext{depth}$，过程中记录历史最高峰值 $	ext{maxdepth}$；
   - 当遇到分支跳转边时，将目标基本块标记为待访问，并断言：**从所有不同控制流路径汇聚到同一个基本块入口时，其起始栈深度必须绝对一致（Inconsistent Stackdepth Check）**；若不一致则证明字节码存在结构性错误。
   - 最终输出的 $	ext{maxdepth}$ 直接写入 ``PyCodeObject.co_stacksize``。

-----------------------------------------------------------------------------
6. 汇编器（Assembler）与 PyCodeObject 物理产出
-----------------------------------------------------------------------------

编译的最终阶段由 ``Python/assemble.c`` 完成，其核心工作是将优化后的基本块网络序列化为标准的不可变 ``PyCodeObject``：

1. **16 位 Code Unit 编码**：
   自 Python 3.6 起，字节码统一采用标准的 16 位小端序编码（2 字节对齐）：
   - 高 8 位（Byte 1）：``opcode``（操作码）
   - 低 8 位（Byte 0）：``oparg``（操作数）
2. **``EXTENDED_ARG`` 级联扩展**：
   若某指令的操作数超过 255（如访问第 300 个常量），汇编器会自动在其前面插入 ``EXTENDED_ARG`` 前缀指令，每次向上提供 8 位有效载荷：

   .. code-block:: text

      EXTENDED_ARG (300 >> 8 = 1)   ──► 暂存高 8 位
      LOAD_CONST   (300 & 0xFF = 44) ──► 组合得到真实操作数 300

3. **元数据表生成**：
   - ``co_code``：序列化后的原始二进制字节码数组（``PyBytesObject``）；
   - ``co_linetable``：遵循 PEP 626 规范的高压缩行号与列跨度映射表；
   - ``co_exceptiontable``：零开销异常处理表（Exception Table），记录每个受保护字节码区间的起始偏移、结束偏移与目标 Handler 跳转位置；
   - ``co_consts``、``co_varnames``、``co_localsplusnames``：常量与变量名元组。

-----------------------------------------------------------------------------
小结与下章导读
-----------------------------------------------------------------------------

本章系统解构了 CPython 3.13+ 从抽象语法树到字节码与控制流图的底层转换链路：
1. CodeGen 阶段基于访问者模式发射带有符号标签与伪指令的中间序列；
2. 基本块（Basicblock）的“单入口、单出口”物理不变量与 CFG 有向图划分状态机；
3. 死代码剔除、跳转穿透、超级指令合成与冷热块分离（Cold-block Separation）的硬件缓存优化；
4. ``calculate_stackdepth()`` 通过抽象解释在编译期精确推导最大栈深 ``co_stacksize`` 的数学过程；
5. 汇编器（Assembler）编码 16 位 Code Unit、处理 ``EXTENDED_ARG`` 并最终封装生成不可变 ``PyCodeObject``。

在字节码生成之后，解释器还会对指令序列执行最后一轮精密的微观代数优化。在下一章中，我们将深入—— **02_parser_and_compilation/04_peephole_and_bytecode_optimization.rst（窥孔优化器 Peephole Optimizer、常量折叠与指令特化准备）**。
