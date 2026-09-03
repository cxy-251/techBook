=============================================================================
具象语法树 CST 到抽象语法树 AST 的构建与符号表 Symbol Table 生成
=============================================================================

.. note:: 前置背景与上下文承接
   在前一章中，我们剖析了 Python 现代化 PEG 解析器（PEP 617）的文法规则、词法分析器（Tokenizer）的状态机拓扑以及 Packrat 记忆化回溯机制。通过 PEG 文法与词法符号流的协同，源代码文本已经被成功识别并匹配为符合 Python 语法的结构序列。然而，仅有词法与文法结构尚不足以直接生成虚拟机字节码——解释器必须首先建立起结构精纯的**抽象语法树（Abstract Syntax Tree, AST）**，并在 AST 之上完成两阶段**符号表（Symbol Table）分析**，精准判定每个变量究竟是局部变量、全局变量、还是跨栈帧的闭包自由变量。
   
   本章将深入 CPython 核心源码文件 ``Parser/Python.asdl``、``Include/internal/pycore_ast.h``、``Python/symtable.c`` 以及 ``Include/internal/pycore_symtable.h``，自底向上解构 ASDL 元语言描述规范、AST 节点的微观内存拓扑与上下文（``expr_context``）机制、PEG 时代下的“零中间 CST”内联折叠原理，以及核心符号表系统的两阶段作用域推导与闭包变量（Cell / Free）求解算法。

-----------------------------------------------------------------------------
1. ASDL 元语言与 AST 节点的物理内存拓扑
-----------------------------------------------------------------------------

在编译器理论中，AST 必须具备高度正规化与严格类型化的树形数据结构。为了避免手写数百个极其繁琐且易出错的 C 语言结构体与构造函数，CPython 采用了 **ASDL（Abstract Syntax Description Language，抽象语法描述语言）** 作为单一定义源（位于 ``Parser/Python.asdl``）。

在构建 CPython 时，脚本 ``Parser/asdl_c.py`` 会读取 ``Python.asdl`` 并全自动生成 C 语言头文件 ``Include/internal/pycore_ast.h`` 和构造函数集 ``Python/Python-ast.c``。

ASDL 四大核心节点分类
~~~~~~~~~~~~~~~~~~~~~

ASDL 定义了四大核心语法实体类型：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                        ASDL 核心顶层节点族分类                          |
   +====================+==========================+=========================+
   | 节点类别 (Kind)    | 对应 C 语言结构体指针    | 语义描述与典型代表      |
   +--------------------+--------------------------+-------------------------+
   | 模块级 (mod)       | mod_ty                   | Module, Interactive,    |
   |                    |                          | Expression, FunctionType|
   +--------------------+--------------------------+-------------------------+
   | 语句 (stmt)        | stmt_ty                  | FunctionDef, ClassDef,  |
   |                    |                          | Assign, If, For, Return |
   +--------------------+--------------------------+-------------------------+
   | 表达式 (expr)      | expr_ty                  | BinOp, Call, Attribute, |
   |                    |                          | Constant, Name, Tuple   |
   +--------------------+--------------------------+-------------------------+
   | 模式匹配 (pattern) | pattern_ty               | MatchValue, MatchAs,    |
   |                    |                          | MatchClass, MatchStar   |
   +--------------------+--------------------------+-------------------------+

表达式上下文：``expr_context`` 的物理意义
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 AST 节点设计中，同一个标识符（如变量名 ``a``）在不同语法位置所代表的物理语义完全不同。CPython 通过 ``expr_context`` 枚举对其进行严格标注：

.. code-block:: c

   typedef enum _expr_context { Load=1, Store=2, Del=3 } expr_context_ty;

.. code-block:: text

   1. a = 1      ──► Name(id="a", ctx=Store)  (作为赋值左值，表示写入变量)
   2. b = a + 2  ──► Name(id="a", ctx=Load)   (作为运算操作数，表示读取变量)
   3. del a      ──► Name(id="a", ctx=Del)    (作为删除目标，表示销毁变量)

这种上下文区分使得后续的代码生成器（Code Generator）能够在单次遍历中直接映射至不同的字节码指令（如 ``STORE_FAST``、``LOAD_FAST``、``DELETE_FAST``），无需在编译期反复回溯父节点类型。

AST 节点的物理连续排布
~~~~~~~~~~~~~~~~~~~~~~

所有 AST 节点均由 ``_PyObject_MallocWithType`` 在编译期专用的连续内存池 ``PyArena`` 中分配。每个 AST 节点实体均附带源码溯源元数据：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       AST 节点通用物理内存结构                          |
   +====================+====================================================+
   | 变体枚举类型       | enum _expr_kind / enum _stmt_kind (4 Bytes)        |
   +--------------------+----------------------------------------------------+
   | 联合体数据 (union) | 存放具体子节点的指针与属性 (8 ~ 64 Bytes)          |
   +--------------------+----------------------------------------------------+
   | 源码位置元数据     | int lineno, col_offset, end_lineno, end_col_offset |
   | (Source Location)  | (精确记录该节点在 Python 源码文件中的行列边界)     |
   +--------------------+----------------------------------------------------+

-----------------------------------------------------------------------------
2. CST 到 AST 的折叠与“零中间解析树”架构
-----------------------------------------------------------------------------

在传统的编译器前端（如 GCC 早期架构或 Python 3.8 之前的旧语法系统）中，编译过程分为两个阶段：
1. **源码字符流 $	o$ 具象语法树（Concrete Syntax Tree, CST）**：CST（又称 Parse Tree）严格映射文法中的每一个终结符与非终结符，树中充斥着大量的逗号、冒号、括号、单子产生式等冗余无意义节点。
2. **CST $	o$ 抽象语法树（AST）**：通过专门的转化函数（如旧版 ``ast_for_stmt()``）递归遍历整个庞大的 CST，剥除冗余标点并重构为 AST。

PEG 时代的“零中间 CST”内联折叠
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

自 Python 3.9 引入现代 PEG 解析器后，CPython 彻底废弃了中间 CST 阶段。

在 ``Grammar/python.gram`` 中，每个文法匹配分支的末尾直接绑定了 C 语言内联语义动作代码（Action Codes）。解析器在自底向上规约的同时，**直接调用 AST 构造函数将 Token 流现场折叠为 AST 节点**：

.. code-block:: text

   [Token 流: NAME "x" | EQUAL "=" | NUMBER "42"]
                          │
                          ▼ (PEG 文法规则: assignment)
   [内联 C 动作: _PyAST_Assign(targets, value, NULL, EXTRA)]
                          │
                          ▼
   [直接产出 AST: Assign(targets=[Name('x', Store)], value=Constant(42))]

这种架构使编译前端的内存分配次数减少了 60% 以上，并利用 ``PyArena`` 实现了 AST 构建完毕后的常数级一键释放。

-----------------------------------------------------------------------------
3. 符号表（Symbol Table）的两阶段作用域分析系统
-----------------------------------------------------------------------------

当 AST 构建完成后，编译器面临一个核心问题：**Python 是一门词法作用域（Lexical Scoping）的动态语言，变量不需要预先声明类型，但必须在编译期静态确定其访问作用域（Scope）**。

例如，在函数体内访问变量 ``x``，它究竟是读取局部变量（``LOAD_FAST``）、全局变量（``LOAD_GLOBAL``），还是跨越闭包层级的自由变量（``LOAD_DEREF``）？

CPython 在 ``Python/symtable.c`` 中实现了一套精密的 **两阶段符号分析器（Two-Pass Symbol Table Analyzer）**。

核心数据结构：``symtable`` 与 ``PySTEntryObject``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: c

   struct symtable {
       PyObject *st_filename;          /* 源文件名 */
       struct _symtable_entry *st_cur; /* 当前正在遍历的作用域符号表节点 */
       struct _symtable_entry *st_top; /* 顶层模块作用域节点 */
       PyObject *st_blocks;            /* 字典: AST 节点指针 -> 对应 PySTEntryObject */
       PyObject *st_stack;             /* 嵌套命名空间栈 */
       PyObject *st_global;            /* 顶层模块全局符号字典 */
       _PyFutureFeatures *st_future;   /* future 特性标志 */
   };

   typedef struct _symtable_entry {
       PyObject_HEAD
       PyObject *ste_id;        /* 该作用域的唯一整数 ID */
       PyObject *ste_symbols;   /* 核心字典: 变量名 (str) -> 标志位 (long) */
       PyObject *ste_name;      /* 作用域名称 (如 "foo", "<listcomp>") */
       PyObject *ste_varnames;  /* 函数形参列表 */
       PyObject *ste_children;  /* 嵌套子作用域列表 */
       _Py_block_ty ste_type;   /* FunctionBlock, ClassBlock, ModuleBlock 等 */
       int ste_nested;          /* 是否处于嵌套作用域 */
       ...
   } PySTEntryObject;

第一阶段：原始事实收集（Pass 1 - Raw Collection）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在第一阶段，函数 ``_PySymtable_Build()`` 深度优先递归遍历整棵 AST（通过 ``symtable_visit_stmt`` 与 ``symtable_visit_expr``）：

1. **遇到变量绑定或使用**：根据 AST 上下文调用 ``symtable_add_def()`` 在当前作用域的 ``ste_symbols`` 中记录原始事实标志位：
   - ``DEF_LOCAL``：在当前代码块中发生了赋值（如 ``x = 1``）；
   - ``DEF_PARAM``：作为函数形参出现；
   - ``DEF_GLOBAL``：显式声明了 ``global x``；
   - ``DEF_NONLOCAL``：显式声明了 ``nonlocal x``；
   - ``USE``：变量被读取使用（如 ``print(x)``）；
   - ``DEF_ANNOT``：变量带有类型注解（如 ``x: int``）。
2. **遇到函数、类、推导式或类型形参**：调用 ``symtable_enter_block()`` 压栈创建新的子作用域节点 ``PySTEntryObject``，并将子节点链接至父节点的 ``ste_children`` 列表中。

第二阶段：全局约束求解与闭包分析（Pass 2 - Scope Resolution）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

第一阶段仅收集了局部事实，但无法单独判定未声明变量的真正归属。第二阶段由 ``symtable_analyze()`` 驱动，自顶向下进行作用域求解：

.. code-block:: text

   [Pass 2: analyze_block(ste, bound, free, global)]
                          │
       ┌──────────────────┴──────────────────┐
       ▼                                     ▼
   【分析当前作用域内的所有符号】         【递归传递至各子作用域】
   - 遍历 ste_symbols 字典               - 将当前 local 并入 bound 集合
   - 结合父级传入的 bound/global 集合    - 子作用域分析完毕后返回 child_free
   - 仲裁判定五大作用域终态              - 将 child_free 并入当前 newfree 集合
       │                                     │
       └──────────────────┬──────────────────┘
                          │
                          ▼
   【Cell 与 Free 闭包变量终态裁决】
   - 若某变量在当前属于 LOCAL，但在子作用域中被标记为 FREE：
     └─ 该变量在当前作用域被升级标记为 【CELL】！
     └─ 并且从向上返回的 free 集合中剔除（闭包绑定在此闭合）！

变量终态的五大作用域（Scope）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

经过两阶段求解后，每个符号的标志位高 4 位被写入最终的作用域枚举：

1. **``LOCAL``（局部变量）**：仅在当前函数内部定义并使用。运行时存储于栈帧的“快速局部变量数组”中，通过极速指令 ``LOAD_FAST`` / ``STORE_FAST`` 访问。
2. **``GLOBAL_EXPLICIT``（显式全局变量）**：显式使用 ``global x`` 声明，跨越所有层级直达模块全局字典。
3. **``GLOBAL_IMPLICIT``（隐式全局/内建变量）**：在当前函数未绑定，且所有外层作用域中也均未绑定的符号，运行时依次查找全局命名空间（``f_globals``）与内建命名空间（``f_builtins``）。
4. **``CELL``（闭包载体变量）**：当前函数绑定的局部变量，但被内部嵌套函数（闭包）引用。运行时必须为其在堆上分配一个 ``PyCellObject`` 单元。
5. **``FREE``（自由闭包变量）**：内部函数引用的外层函数中的变量。运行时通过 ``LOAD_DEREF`` 指令从栈帧环境中的 Cell 单元间接读取。

-----------------------------------------------------------------------------
4. 私有名称重整（Name Mangling）与 PEP 695 作用域演进
-----------------------------------------------------------------------------

双下划线私有属性重整
~~~~~~~~~~~~~~~~~~~~

在类定义内部（``ClassBlock``），任何以双下划线开头且不以双下划线结尾的标识符（如 ``__private_var``）均会被符号表中的 ``_Py_Mangle()`` 自动重整：

$$	ext{Mangled Name} = 	ext{"\_"} + 	ext{ClassName (去除前导下划线)} + 	ext{OriginalName}$$

例如在类 ``class MyClass:`` 中，``__data`` 被重整为 ``_MyClass__data``，从而在底层物理机制上避免派生类属性命名冲突。

PEP 695 类型参数作用域（Python 3.12+）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Python 3.12 引入了全新的泛型与类型参数语法（如 ``def func[T](x: T) -> T: ...``）。为了确保类型参数 ``T`` 不会污染全局或外层命名空间，符号表新增了三种特化作用域：
- ``TypeParametersBlock``：包围泛型函数/类的类型形参作用域；
- ``TypeAliasBlock``：用于 ``type Alias = int`` 别名作用域；
- ``TypeVariableBlock``：用于类型变量的约束与默认值求解。

这些作用域表现为轻量级的函数式独立作用域，由符号表在 AST 编译期完成严密的词法隔离。

-----------------------------------------------------------------------------
小结与下章导读
-----------------------------------------------------------------------------

本章系统剖析了 Python 源码从抽象语法树到作用域符号网络的物理构建链路：
1. ASDL 元语言如何规范化生成整套 C 语言 AST 数据结构与 ``expr_context``（``Load`` / ``Store`` / ``Del``）机制；
2. PEG 时代“零中间 CST”架构通过内联语义动作（Action Codes）实现 AST 的即时折叠；
3. 符号表系统（``symtable.c``）的“事实收集”与“约束求解”两阶段算法；
4. 变量五大作用域（``LOCAL`` / ``GLOBAL_EXPLICIT`` / ``GLOBAL_IMPLICIT`` / ``CELL`` / ``FREE``）的数学图论判定流程；
5. 私有名称重整（Name Mangling）与 PEP 695 类型参数作用域隔离模型。

在掌握了带有精确作用域标注的 AST 之后，下一章我们将深入字节码生成器的腹地—— **02_parser_and_compilation/03_bytecode_generation_and_cfg.rst（控制流图 CFG 构建、Basicblock 划分与字节码编译器 CodeGen 流程）**。
