=============================================================================
PEG 解析器架构、Grammar 规则与词法分析 Tokenizer 状态机
=============================================================================

.. note:: 前置背景与上下文承接
   在模块一【对象模型与内存基石】中，我们完整剖析了 CPython 运行时的底层物理世界——从 ``PyObject`` / ``PyVarObject`` 的内存布局与引用计数、``PyTypeObject`` 的元类型分发网络、三层内存分配器体系（``pymalloc`` 与 ``mimalloc``），到分代循环垃圾回收器（GC）。从本章开始，我们将正式进入模块二【前端编译与 AST 生成】。
   
   任何 Python 程序在进入虚拟机执行之前，必须首先将纯文本字符流编译为抽象语法树（AST），进而转化为虚拟机可执行的字节码序列。本章聚焦 Python 编译管线的第一道物理大门，深入 CPython 核心源码 ``Grammar/python.gram``、``Parser/pegen.h``、``Parser/pegen.c`` 以及 ``Parser/tokenizer/``，深度解构从传统 LL(1) 到现代化 PEG 解析器（PEP 617）的技术演进、词法分析器（Tokenizer）的状态机与缩进栈处理、Packrat 记忆化回溯机制、Grammar 元文法规则，以及软关键字与两阶段精准语法错误诊断系统。

-----------------------------------------------------------------------------
1. 从 LL(1) 到 PEG：Python 语法分析器的架构革命
-----------------------------------------------------------------------------

在 Python 3.9 之前，CPython 一直使用由 Guido van Rossum 早期手写的 **LL(1) 预测分析器**（结合 pgen 状态机）。

LL(1) 分析器的局限性
~~~~~~~~~~~~~~~~~~~~

LL(1) 意味着解析器从左到右扫描输入（Left-to-right），推导最左句型（Leftmost derivation），且**仅向前看 1 个 Token（k=1）**。这种理论模型存在严苛的表达力瓶颈：
- **无法解析带有括号的复杂上下文**：例如多行 ``with (open("a"), open("b")) as (f1, f2):`` 在 LL(1) 语法中与函数调用存在多重歧义。
- **无法自然支持模式匹配（Pattern Matching）**：PEP 634 引入的 ``match/case`` 语句包含复杂的软关键字与嵌套结构，LL(1) 无法在仅看 1 个 Token 的前提下断定后续结构。
- **被迫在语法层打补丁**：为了规避冲突，旧版 Python 不得不将某些非法语法先放行到 AST 构建阶段，再通过后置遍历手动抛出语法错误。

PEG（Parsing Expression Grammar，解析表达式文法）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了彻底解放 Python 的语法表达力，PEP 617 在 Python 3.9+ 引入了基于 **PEG 的 Packrat 解析器生成器（pegen）**。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                        LL(1) vs PEG 核心差异对比                        |
   +====================+==========================+=========================+
   | 核心特性           | 传统 LL(1) 分析器        | 现代化 PEG 分析器       |
   +--------------------+--------------------------+-------------------------+
   | 选择算子语义       | 无序并集（存在歧义冲突） | **有序选择（Ordered）** |
   |                    | $A 	o B \mid C$         | 先匹配分支 1，失败才试 2|
   +--------------------+--------------------------+-------------------------+
   | 前瞻能力           | 严格固定 1 个 Token      | **任意深度无限前瞻**    |
   +--------------------+--------------------------+-------------------------+
   | 回溯与时间复杂度   | 不允许回溯               | 带 Packrat 记忆化回溯   |
   |                    |                          | 严格保证 $O(N)$ 复杂度  |
   +--------------------+--------------------------+-------------------------+
   | AST 生成模式       | 产生冗余 CST 中间树      | **内联语义动作直接产出**|
   +--------------------+--------------------------+-------------------------+

在 PEG 中，分支规则 ``e1 | e2`` 具备严格的**确定性优先级（Ordered Choice）**：解析器永远优先尝试 ``e1``，若 ``e1`` 匹配成功则直接提交该分支，绝对不会再去评估 ``e2``；只有当 ``e1`` 彻底匹配失败时，解析器才回溯游标并尝试 ``e2``。

-----------------------------------------------------------------------------
2. 词法分析器状态机（Tokenizer）与 Token 流生成
-----------------------------------------------------------------------------

文本源代码首先通过词法分析器被切分为一系列离散的 **Token 符号流**。在 CPython 中，词法状态机由 ``struct tok_state``（定义于 ``Parser/lexer/state.h``）统一维护：

.. code-block:: c

   struct tok_state {
       /* 字符输入缓冲区游标 */
       char *buf;                    /* 物理行缓冲区起始指针 */
       char *cur;                    /* 当前正扫描的字符指针 */
       char *inp;                    /* 缓冲区中已读取数据的末尾 */
       char *end;                    /* 物理缓冲区的最大界限 */
       
       /* 缩进栈状态机 (处理 Python 的语义缩进) */
       int indents[MAXINDENT];       /* 记录各层级缩进列偏移的递增栈 */
       int indent;                   /* 当前栈顶的缩进索引 */
       int atbol;                    /* 标记当前是否处于行首 (At Beginning Of Line) */
       int pendin;                   /* 待发出的连续 DEDENT Token 计数 */
       
       /* 括号层级状态 (隐式行连接) */
       int level;                    /* 处于 (), [], {} 内部时的嵌套深度 */
       
       /* 现代 F-string / T-string 模态嵌套栈 */
       tokenizer_mode tok_mode_stack[MAX_MODE_STACK_SIZE];
       int tok_mode_stack_index;
   };

Python 独特词法机制的微观状态转移
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   源代码字符流 ──► [词法状态机 tok_state]
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   【缩进与行首判定】   【括号隐式续行】    【F-string 模态栈】
   - atbol = 1          - level > 0         - 遇到 f" / t"
   - 计算空格/Tab 列数  - 忽略物理换行      - 压入 TOK_FSTRING 模式
   - 对比 indents[] 栈  - 仅产出普通空格    - 遇到 { 切换回代码模式
   - 产出 INDENT/DEDENT                     - 遇到 } 切换回字符串模式

1. **INDENT 与 DEDENT 栈状态机**：
   当扫描到行首（``atbol == 1``）且遇到非空行时，计算其物理缩进空格数 $C$：
   - 若 $C > 	ext{indents}[	ext{indent}]$：将 $C$ 压入缩进栈，词法分析器产出一个 ``INDENT`` Token。
   - 若 $C < 	ext{indents}[	ext{indent}]$：依次弹出栈顶直到找到匹配的缩进层级 $C$。每弹出一层，``pendin`` 计数加 1，并在后续调用中连续产出相应数量的 ``DEDENT`` Token。若在栈中找不到相等的 $C$，直接抛出 ``IndentationError``。
2. **隐式行连接（Implicit Line Joining）**：
   当 ``level > 0``（即游标处于未闭合的括号内）时，换行符 ``
`` 不会被转化为语义换行 ``NEWLINE``，而是作为普通空白丢弃，从而原生支持多行表达式书写。

-----------------------------------------------------------------------------
3. PEG 解析器核心：Packrat 记忆化与回溯机制
-----------------------------------------------------------------------------

在 ``Parser/pegen.h`` 中，解析器核心由 ``Parser`` 与 ``Token`` 结构体驱动：

.. code-block:: c

   typedef struct _memo {
       int type;                     /* 文法规则类型 ID */
       void *node;                   /* 已经成功解析出的 AST 节点指针 */
       int mark;                     /* 成功解析后 Token 流游标所在的新位置 */
       struct _memo *next;           /* 冲突链表指针 */
   } Memo;

   typedef struct {
       int type;                     /* Token 类型 (如 NAME, NUMBER, NEWLINE) */
       PyObject *bytes;              /* 词法单元原始字节数据 */
       int lineno, col_offset;       /* 源代码绝对行号与列偏移 */
       Memo *memo;                   /* 该 Token 上挂载的记忆化条目链表 */
       uint64_t memo_mask;           /* 64位位图过滤器 (用于快速过滤未命中) */
   } Token;

   typedef struct {
       struct tok_state *tok;        /* 绑定的词法分析器 */
       Token **tokens;               /* 已缓冲的 Token 指针环形数组 */
       int mark;                     /* 当前解析游标所在的 Token 索引 */
       int fill, size;               /* Token 缓冲区的填充深度与容量 */
       PyArena *arena;               /* 编译期 AST 内存池 */
   } Parser;

Packrat 记忆化加速原理解析
~~~~~~~~~~~~~~~~~~~~~~~~~~

当解析器尝试在一个位置匹配某条复杂规则（例如 ``expression``）但最终在更深层失败时，解析器必须执行 **回溯（Backtracking）**（通过将 ``p->mark`` 重置回进入规则前的游标位置）。

如果不加优化，频繁的回溯会导致相同子树被重复解析数千次，使最坏时间复杂度急剧爆炸至指数级 $O(2^N)$。

CPython 采用 **Packrat 记忆化算法** 消除重复计算：

.. code-block:: c

   int _PyPegen_is_memoized(Parser *p, int type, void *pres)
   {
       Token *t = p->tokens[p->mark];
       /* 1. 快速位图检查：若该规则对应的 bit 位为 0，绝对未被缓存，直接以 1 个周期返回！ */
       if ((t->memo_mask & (1ULL << (type & 63))) == 0) {
           return 0;
       }
       /* 2. 命中候选：遍历链表获取已缓存的 AST 节点与游标位置 */
       for (Memo *m = t->memo; m != NULL; m = m->next) {
           if (m->type == type) {
               p->mark = m->mark;       /* 游标直接瞬间跳跃至该规则结束处！ */
               *(void **)pres = m->node;/* 直接复用已生成的 AST 节点！ */
               return 1;
           }
       }
       return 0;
   }

通过将每个位置的规则推导结果缓存于 ``Token.memo`` 中，任何非终结符在同一个 Token 位置最多只被评估一次，从而将 PEG 回溯解析的最坏时间复杂度在数学上严格压制为 **线性时间 $O(N)$**。

-----------------------------------------------------------------------------
4. Grammar 规则语法糖与 AST 动作代码（Action Codes）
-----------------------------------------------------------------------------

CPython 的核心语法规则统一定义在 ``Grammar/python.gram`` 中。``pegen`` 工具会读取该文件并自动生成高效的 C 解析代码 ``Parser/parser.c``。

``python.gram`` 中的核心操作符
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **截断回溯 / 提交操作符（Cut Operator, ``~``）**：
   一旦匹配了 ``~`` 之前的符号，解析器即对当前分支做出绝对承诺（Commit）。如果 ``~`` 后续符号解析失败，解析器**绝不发生回溯**，而是直接终止并抛出致命语法错误。
   
   .. code-block:: text
   
      for_stmt[stmt_ty]:
          | 'for' t=star_targets 'in' ~ ex=star_expressions ':' b=block { ... }

   *(一旦看到 ``for targets in``，语法结构已被唯一锚定，后续若缺少冒号则无需尝试其他备选语句，直接精准报错)*

2. **强制匹配操作符（Forced Match, ``&&``）**：
   强制要求后续 Token 必须存在（如 ``'try' &&':'``），若缺失立即抛出语法异常。

3. **直接内联语义动作（C Action Codes）**：
   每条文法规则后面使用花括号 ``{ ... }`` 直接嵌入 C 语言 AST 构造函数。例如：

   .. code-block:: text

      if_stmt[stmt_ty]:
          | 'if' a=named_expression ':' b=block c=elif_stmt {
              _PyAST_If(a, b, CHECK(asdl_stmt_seq*, _PyPegen_singleton_seq(p, c)), EXTRA) }
          | 'if' a=named_expression ':' b=block c=[else_block] {
              _PyAST_If(a, b, c, EXTRA) }

   这种“即扫即建”的设计使 CPython 完全摆脱了构建巨型 Concrete Syntax Tree（CST，具象语法树）的中间阶段，直接将 Token 流实时折叠为精简的 AST。

-----------------------------------------------------------------------------
5. 软关键字与两阶段精准错误诊断系统
-----------------------------------------------------------------------------

软关键字（Soft Keywords）
~~~~~~~~~~~~~~~~~~~~~~~~~

Python 3.10+ 引入的 ``match``、``case`` 以及 Python 3.12+ 引入的 ``type`` 均为**软关键字（Soft Keywords）**。这意味着它们在模式匹配或类型别名语句中充当关键字，但在其他任意普通代码中仍然可以被自由用作变量名或函数名（如 ``match = 42``）。

PEG 解析器通过 ``_PyPegen_expect_soft_keyword()`` 实现了完全基于文法位置的动态判定：

.. code-block:: text

   match_stmt[stmt_ty]:
       | "match" subject=subject_expr ':' NEWLINE INDENT cases[asdl_match_case_seq*]=case_block+ DEDENT { ... }

*(使用双引号 ``"match"`` 声明软关键字匹配，词法阶段按普通 NAME 产出，语法阶段按位置上下文仲裁)*

两阶段精准错误诊断（Two-Phase Error Handling）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了给开发者提供极其清晰、符合人类心理预期的错误提示，CPython 采取了**两阶段解析策略**：

.. code-block:: text

   [输入源代码]
        │
        ▼
   【第一阶段：标准文法解析 (Fast Normal Pass)】
   - 仅匹配合法文法规则
   - 若解析成功 ──► 直接返回生成的 AST！
        │
        ├─► 解析失败
        ▼
   【第二阶段：错误特化重解析 (Error Specialization Pass)】
   - 激活 Grammar 中所有以 invalid_* 命名的异常规则
   - 重放解析过程，精准捕获常见手误：
     * invalid_assignment: "cannot assign to literal"
     * invalid_kwarg: "expression cannot contain assignment, perhaps you meant '=='?"
     * missing_parentheses: "Missing parentheses in call to 'print'. Did you mean print(...)?"
   - 提取精确的源码行号与列范围 (lineno, col_offset, end_col_offset)，生成优美的代码下划线提示

-----------------------------------------------------------------------------
小结与下章导读
-----------------------------------------------------------------------------

本章系统解构了 CPython 3.13+ 前端解析管线的底层物理机制：
1. 从传统单 Token 前瞻的 LL(1) 向支持无限前瞻与确定性选择的 PEG（PEP 617）的理论升级；
2. 词法分析器 ``struct tok_state`` 的状态迁移、缩进栈（``indents[]``）与 F-string 模态栈；
3. Packrat 记忆化算法通过 64 位 ``memo_mask`` 与节点缓存将回溯开销压制在严格的 $O(N)$ 线性时间；
4. ``python.gram`` 元语法规则中的提交操作符 ``~`` 与直接生成 AST 的内联语义动作；
5. 软关键字上下文隔离与两阶段精准错误诊断架构。

通过 PEG 解析器与内联语义动作，字符流已经被成功转化为内存中的 AST 节点。在下一章中，我们将继续深入—— **02_parser_and_compilation/02_cst_to_ast_transformation.rst（具象语法树 CST 到抽象语法树 AST 的构建与符号表 Symbol Table 生成）**。
