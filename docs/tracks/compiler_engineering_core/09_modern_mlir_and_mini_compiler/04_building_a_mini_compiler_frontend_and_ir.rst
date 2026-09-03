====================================================================================================
从零构建微型编译器（前端与 IR）：手写词法分析、递归下降 Parser、类型检查与三地址码 IR 生成
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 9 模块第 3 节（``03_domain_specific_compilers_gpu_and_ai_graphs``）中，我们系统解构了领域特定编译器（DSC）在 GPU 着色器（SPIR-V）与深度学习 AI 计算图算子融合（Operator Fusion）中的微架构映射与消除内存物化（Materialization）的物理本质。至此，从词法分析、抽象语法树、语义符号分析、中间表示与 SSA 形式、数据流优化 Pass、目标机指令选择与调度、寄存器分配、目标文件链接加载，到现代多层 MLIR 与领域加速编译器的全景理论体系已全部完备。
   作为全书最终篇章的综合实践，本节与下一节将融会贯通前序全部模块的核心原理，从零开始完整手工构建一个自包含、高内聚、无任何外部依赖的工业级微型编译器（Mini-Compiler）。本节聚焦编译器前端与中间表示生成：确立静态强类型教学语言 ``MiniLang`` 的形式文法与阶段契约，手写单字符前瞻词法分析器与行列位置追踪器，推导基于 Pratt 算子结合力（Binding Power）的递归下降解析器，建立作用域链与双遍扫描静态类型检查器，最终实现 AST 向三地址码（3AC Linear IR）的受控平坦化降级（Lowering），为后端指令选择与目标机器码发射交付干净完备的中间表示底座。

MiniLang 语言形式规范与编译阶段契约
----------------------------------

设计一门教学级微型编译器语言，核心在于以最小的正交语法空间覆盖真实工业级编译器前端所面临的完整技术挑战：Token 物理边界识别、双字符操作符贪婪匹配、表达式优先级与结合性消除、词法作用域嵌套与变量遮蔽、严格静态类型检查、控制流分支与循环的线性化展开，以及过程调用约定契约。

MiniLang 语法设计与 EBNF 形式文法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``MiniLang`` 采用显式类型声明、静态块作用域与过程式函数模型。程序由一系列顶层函数声明构成，原生支持 64 位有符号整型（``int``）与布尔型（``bool``）。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                       MiniLang 扩展巴科斯范式 (EBNF) 规范                   |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   Program         ::= FunctionDecl* EOF                                     |
   |                                                                             |
   |   FunctionDecl    ::= "fn" Identifier "(" [ ParameterList ] ")"             |
   |                       [ "->" Type ] BlockStmt                               |
   |                                                                             |
   |   ParameterList   ::= Parameter ( "," Parameter )*                          |
   |   Parameter       ::= Identifier ":" Type                                   |
   |   Type            ::= "int" | "bool"                                        |
   |                                                                             |
   |   BlockStmt       ::= "{" Statement* "}"                                    |
   |                                                                             |
   |   Statement       ::= LetStmt                                               |
   |                     | AssignStmt                                            |
   |                     | IfStmt                                                |
   |                     | WhileStmt                                             |
   |                     | ReturnStmt                                            |
   |                     | ExprStmt                                              |
   |                                                                             |
   |   LetStmt         ::= "let" Identifier ":" Type "=" Expression ";"          |
   |   AssignStmt      ::= Identifier "=" Expression ";"                         |
   |   IfStmt          ::= "if" Expression BlockStmt [ "else" BlockStmt ]        |
   |   WhileStmt       ::= "while" Expression BlockStmt                          |
   |   ReturnStmt      ::= "return" [ Expression ] ";"                           |
   |   ExprStmt        ::= Expression ";"                                        |
   |                                                                             |
   |   Expression      ::= BinaryExpr | PrimaryExpr                              |
   |   BinaryExpr      ::= Expression BinaryOp Expression                        |
   |   PrimaryExpr     ::= IntLiteral                                            |
   |                     | BoolLiteral                                           |
   |                     | Identifier                                            |
   |                     | CallExpr                                              |
   |                     | "(" Expression ")"                                    |
   |                                                                             |
   |   CallExpr        ::= Identifier "(" [ ArgumentList ] ")"                   |
   |   ArgumentList    ::= Expression ( "," Expression )*                        |
   |                                                                             |
   |   BinaryOp        ::= "+" | "-" | "*" | "/"                                 |
   |                     | "==" | "!=" | "<" | "<=" | ">" | ">="                 |
   |                                                                             |
   +-----------------------------------------------------------------------------+

四层表示流转序列与语义守恒契约
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

从原始文本到中间表示，编译器前端划分为四个明确的物理转换阶段，每个阶段守卫一组绝对的不变性公理：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        编译器前端四阶段表示流转流水线                       |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 源码文本 Source Text ]                                                  |
   |         |                                                                   |
   |         |  Lexer 扫描 (正则词法状态机)                                      |
   |         v                                                                   |
   |   [ Token 线性词流 + SourceLocation ]                                       |
   |         |                                                                   |
   |         |  Parser 递归下降 + Pratt 结合力解析                               |
   |         v                                                                   |
   |   [ 抽象语法树 (AST) ]                                                      |
   |         |                                                                   |
   |         |  TypeChecker 作用域解析 + 符号表绑定 + 静态类型推导               |
   |         v                                                                   |
   |   [ 语义注解语法树 (Annotated AST) ]                                        |
   |         |                                                                   |
   |         |  IRGenerator 受控降级 (Lowering)                                  |
   |         v                                                                   |
   |   [ 三地址码 (3AC Linear IR) / 控制流显式化序列 ]                           |
   |                                                                             |
   +-----------------------------------------------------------------------------+

1. **阶段 1：SourceText $	o$ Token Stream（词法阶段）**：
   输入为无结构的连续 UTF-8 字符流。词法分析器剥离无语法意义的空白字符与单行注释（``//``），根据最长匹配原则识别词素（Lexeme），将每个 Token 紧密绑定行号与列号（``SourceLocation``），保留用于错误诊断的物理源信息。
2. **阶段 2：Token Stream $	o$ AST（语法阶段）**：
   解析器按语法规则验证语句结构合法性。消解标点符号（如括号、分号、冒号、花括号），构建树形语法结构。表达式解析采用 Pratt 结合力算法，将中缀序列转换为严格体现算子优先级的多态节点树。
3. **阶段 3：AST $	o$ Annotated AST（语义分析阶段）**：
   遍历 AST 树形拓扑。建立嵌套符号表（``Scope``），执行名字解析（Name Resolution）将符号引用绑定至唯一的形参或局部变量定义点；执行静态类型推导与一致性检查，拦截非法赋值、条件非布尔、参数数量/类型不匹配等语义错误。
4. **阶段 4：Annotated AST $	o$ 3AC IR（中间表示降级阶段）**：
   将树形嵌套结构平坦化展开为线性的三地址码（Three-Address Code, 3AC）四元式序列。控制流结构（``if-else``、``while``）拆解为显式跳转指令（``JUMP``、``BR_FALSE``）与基础块标签（``LABEL``）；复合嵌套表达式拆解为单操作码指令与无限虚拟临时寄存器（``%t0, %t1, ...``）。

手写词法状态机与物理源码位置追踪
--------------------------------

词法分析器（Lexer）是编译器的第一道物理屏障。工业级编译器通常避免使用通用的生成器工具（如 Flex/Lex），而是采用手写状态机以达成确定性的错误定位、极低内存开销与高吞吐字符扫描。

源码定位元数据（SourceLocation）系统
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了在语法解析与语义检查发生故障时向开发者提供精确到字符级的报错提示，每个 Token 和 AST 节点均内嵌位置对象：

.. code-block:: cpp

   struct SourceLocation {
       size_t Line = 1;      // 1-based 物理文本物理行号
       size_t Column = 1;    // 1-based 物理字符列偏移

       std::string toString() const {
           return std::to_string(Line) + ":" + std::to_string(Column);
       }
   };

词法分析器在消费字符时维护单调递增的指针与行列计数器：遇到常规字符时 ``Column`` 自增 1；遇到换行符（``
``）时 ``Line`` 自增 1 且 ``Column`` 归零重置。

双字符前瞻与词法分类矩阵
~~~~~~~~~~~~~~~~~~~~~~~~

词法分析器核心为单字符滑动窗口与前瞻探测器（Lookahead）：
- 当遇到字母或下划线（``[a-zA-Z_]``）时，进入标识符累加状态，并在扫描终止后通过静态哈希表判断是否命中系统保留关键字（如 ``fn``, ``let``, ``while`` 等）。
- 当遇到数字（``[0-9]``）时，进入连续整数解析状态，并直接调用整数字面量转换。
- 当遇到双字符前缀（如 ``=``, ``!``, ``<``, ``>``, ``-``）时，必须前瞻探查紧随其后的下一字符（``peekNext()``），以便贪婪区隔单字符与双字符操作符：

.. list-table:: MiniLang 词法 Token 分类体系与正规式规则
   :widths: 20 22 28 30
   :header-rows: 1
   :class: tight-table

   * - Token 类别枚举
     - 语法形态 / 示例
     - 正规式与判定边界
     - 语义属性与元数据载荷
   * - **KwFn / KwLet**
     - ``fn``, ``let``
     - 保留字精确匹配
     - 声明起始标识；不可作为变量名。
   * - **KwIf / KwElse**
     - ``if``, ``else``
     - 保留字精确匹配
     - 条件分支控制流引导符。
   * - **KwWhile / KwReturn**
     - ``while``, ``return``
     - 保留字精确匹配
     - 循环控制与函数返回值发射符。
   * - **TypeInt / TypeBool**
     - ``int``, ``bool``
     - 保留字精确匹配
     - 标量基元类型符号。
   * - **Identifier**
     - ``factorial``, ``count_val``
     - ``[a-zA-Z_][a-zA-Z0-9_]*``
     - 符号名称字符串（Lexeme）。
   * - **IntLiteral**
     - ``0``, ``120``, ``42``
     - ``[0-9]+``
     - 64 位整型数值载荷（IntValue）。
   * - **True / False**
     - ``true``, ``false``
     - 保留字精确匹配
     - 布尔常量字面量（1 位逻辑值）。
   * - **RelationalOps**
     - ``==``, ``!=``, ``<=``, ``>=``
     - 双字符贪婪前瞻匹配
     - 关系比较算子枚举。
   * - **ArithmeticOps**
     - ``+``, ``-``, ``*``, ``/``
     - 单字符匹配（区分 ``->``）
     - 四则运算算子枚举。
   * - **Punctuation**
     - ``(``, ``)``, ``{``, ``}``, ``;``, ``->``
     - 分隔与箭头符号匹配
     - 作用域边界、参数列表与返回值引导。

递归下降解析与 Pratt 表达式结合力解耦
-------------------------------------

语法分析器（Parser）接收由 Lexer 生产的有序 Token 流，将其重构为树形抽象语法树（AST）。MiniLang 采用经典的递归下降技术处理高层语句，并引入 Pratt 算法统一解析算子表达式。

语句级递归下降预测分析
~~~~~~~~~~~~~~~~~~~~~~

语句解析基于 LL(1) 前瞻选择分发。由于各语句具有明确的起始引导 Token（``KwFn``, ``KwLet``, ``KwIf``, ``KwWhile``, ``KwReturn``），解析器只需通过单 Token 预测即可无回溯地准确分发至对应的分支产生式处理函数：
- **函数解析（parseFunction）**：消费 ``fn`` 引导符，捕获函数名，循环提取以逗号隔开的形式参数（``name: type``），提取可选的箭头返回值类型，最后递归进入 ``BlockStmt`` 解析函数体。
- **变量声明（parseLetStatement）**：消费 ``let``，提取标识符、冒号与类型声明，消费赋值号 ``=``，调用表达式解析器求出初值表达式，以分号 ``;`` 结尾。
- **分支结构（parseIfStatement）**：消费 ``if``，解析条件表达式，递归解析必选的 ``ThenBranch`` 块，探测后续是否存在 ``else`` 关键字以挂载可选的 ``ElseBranch`` 块。
- **循环结构（parseWhileStatement）**：消费 ``while``，解析循环守卫条件表达式，递归解析循环体语句块。

Pratt 结合力（Binding Power）算法数学推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在传统的递归下降语法分析中，处理带有不同优先级和结合性的二元表达式通常需要层层嵌套产生式（例如 ``Expression`` 调用 ``LogicalOr``，调用 ``Relational``，调用 ``Additive``，调用 ``Multiplicative``，最后到达 ``Unary`` 和 ``Primary``）。这种方法会导致解析器源码冗长、调用栈急剧加深且新增操作符时修改成本高昂。

Pratt 解析算法（Top-Down Operator Precedence）通过为每个二元操作符分配数值化的 **结合力（Binding Power, BP）**，以紧凑的扁平循环彻底化解优先级嵌套问题。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        Pratt 算子结合力驱动模型                             |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   表达式:   a   +   b   *   c   ==   d                                      |
   |                                                                             |
   |   结合力:       +       *       ==                                          |
   |             [BP=20] [BP=30] [BP=10]                                         |
   |                                                                             |
   |   解析调用推导栈:                                                           |
   |   1. parseExpression(minBp = 0):                                            |
   |      消费 Primary 'a' 作为 lhs                                              |
   |      探查 '+' (bp=20 >= 0): 消费 '+', 递归调用 parseExpression(minBp = 21)   |
   |                                                                             |
   |   2. parseExpression(minBp = 21):                                           |
   |      消费 Primary 'b' 作为当前层 lhs                                        |
   |      探查 '*' (bp=30 >= 21): 消费 '*', 递归调用 parseExpression(minBp = 31) |
   |                                                                             |
   |   3. parseExpression(minBp = 31):                                           |
   |      消费 Primary 'c' 作为当前层 lhs                                        |
   |      探查 '==' (bp=10 < 31): 结合力低于当前门槛，返回 'c'                   |
   |                                                                             |
   |   4. 回溯收割:                                                              |
   |      乘法层构筑:  (b * c)                                                   |
   |      加法层探查 '==' (bp=10 < 21): 结合力低于门槛，返回 (a + (b * c))       |
   |      根调用探查 '==' (bp=10 >= 0): 消费 '==', 递归右侧解析 'd'              |
   |      最终产出 AST 根节点: (a + (b * c)) == d                                |
   |                                                                             |
   +-----------------------------------------------------------------------------+

结合力算法核心递推公式如下：

.. math::

   	ext{parseExpression}(	ext{minBp}) = 	ext{LoopWhile}(	ext{BP}(	ext{Op}) \ge 	ext{minBp}) \implies 	ext{LHS} \leftarrow 	ext{BinaryExpr}(	ext{Op}, 	ext{LHS}, 	ext{parseExpression}(	ext{BP}(	ext{Op}) + 1))

当操作符为左结合时，右子树递归参数设为 $	ext{BP}(	ext{Op}) + 1$，迫使后续同级操作符在右侧探测时因结合力不足而立即返回，从而使同级操作符归入左侧父节点。

作用域链、符号表与静态类型系统
------------------------------

AST 仅表达了程序的语法层次，并未界定具体符号的声明与使用约束。语义分析阶段（Semantic Analysis）负责将非上下文相关的表面结构映射至严格的语义模型。

作用域链（Scope Chain）树形拓扑
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

MiniLang 遵循词法作用域（Lexical Scoping）。作用域以树形链表组织：每个语句块（``BlockStmt``）与函数体均对应一个独立的 ``Scope`` 实例，内含一个局部符号映射表与指向外层父作用域的 ``Parent`` 指针：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                       词法作用域树与符号回溯解析拓扑                        |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 全局作用域 Global Scope ]                                               |
   |     Symbols: { "factorial": Func(int -> int), "main": Func(void -> int) }   |
   |                            ^                                                |
   |                            | (Parent 指针)                                  |
   |   [ 函数作用域 fn factorial ]                                               |
   |     Symbols: { "n": Param(int) }                                            |
   |            ^               ^                                                |
   |            |               | (Parent 指针)                                  |
   |   [ 函数体外层 Block ]    [ While 循环内部 Block ]                          |
   |     Symbols: {            Symbols: {                                        |
   |       "res": Var(int),      "shadowed_var": Var(int)                        |
   |       "i":   Var(int)     }                                                 |
   |     }                                                                       |
   |                                                                             |
   +-----------------------------------------------------------------------------+

符号解析过程（Name Resolution）遵循向上寻根规则：在当前作用域内查找目标标识符，命中则直接返回；若未命中且 ``Parent`` 非空，则递归向外层回溯查找；直至根作用域仍未找到时，报告未定义符号错误。该机制天然支持变量遮蔽（Variable Shadowing），内层块声明的同名变量可安全遮蔽外层变量。

双遍扫描（Two-Pass）名字决议
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了支持函数间的相互调用而无需类似 C 语言的前向声明（Forward Declaration），类型检查器采用双遍扫描设计：
- **Pass 1（函数签名收集）**：快速遍历所有顶层函数声明，提取函数名、形参类型列表与返回值类型，以函数符号注入全局作用域。此阶段若探测到重复同名函数，立即报告重定义错误。
- **Pass 2（函数体深度检查）**：深入每个函数的代码块执行语句与表达式类型推导。此时，任意函数体内发起的函数调用均能在全局作用域中精准解析到被调者的类型签名。

静态类型推导与语义检查矩阵
~~~~~~~~~~~~~~~~~~~~~~~~~~

类型系统确保程序在运行时绝对不会发生数据类型错位。类型推导以自底向上的方式递归推导每个表达式节点的 ``InferredType``：

.. list-table:: MiniLang 语义检查规则与静态安全约束
   :widths: 24 28 48
   :header-rows: 1
   :class: tight-table

   * - 语法结构 / 检查项目
     - 静态判定与类型一致性公理
     - 语义违规判定与错误报告策略
   * - **变量声明 (LetStmt)**
     - $	ext{Type}(	ext{Initializer}) == 	ext{DeclType}$
     - 初值表达式类型与显式声明类型冲突时，拒绝声明。
   * - **变量赋值 (AssignStmt)**
     - $	ext{Type}(	ext{Value}) == 	ext{Symbol.Type}$
     - 目标必须为已声明可变符号（不可为函数名）；类型必须完全相等。
   * - **算术二元运算 (+, -, \*, /)**
     - $	ext{LHS} == 	ext{int} \land 	ext{RHS} == 	ext{int} \implies 	ext{Result} = 	ext{int}$
     - 任一操作数非 ``int`` 时，报告非法算术操作数错误。
   * - **相等比较运算 (==, !=)**
     - $	ext{LHS} == 	ext{RHS} \implies 	ext{Result} = 	ext{bool}$
     - 仅允许同类型比较（整型比整型，布尔比布尔）；跨类型比较触发拦截。
   * - **关系比较运算 (<, <=, >, >=)**
     - $	ext{LHS} == 	ext{int} \land 	ext{RHS} == 	ext{int} \implies 	ext{Result} = 	ext{bool}$
     - 布尔值不支持大小序比较；操作数必须严格为 ``int``。
   * - **条件分支与循环守卫 (if / while)**
     - $	ext{Type}(	ext{Condition}) == 	ext{bool}$
     - 守卫条件必须为布尔标量；严禁整型隐式真值转换。
   * - **函数调用 (CallExpr)**
     - $N_{	ext{args}} == N_{	ext{params}} \land \forall i, 	ext{Type}(A_i) == P_i$
     - 实参个数不符或对应位置类型不相容时，精准报告实参违规槽位。
   * - **函数返回 (ReturnStmt)**
     - $	ext{Type}(	ext{Expr}) == 	ext{CurrentFunction.ReturnType}$
     - 返回值类型必须严格吻合函数原型签名（无值返回对应 ``void``）。

三地址码 (3AC) 线性中间表示设计与受控降级
-----------------------------------------

三地址码（Three-Address Code, 3AC）是连接高层语法抽象与底层物理机器码的关键纽带。在 3AC 中，复杂的嵌套语法树被彻底解构为由基本线性指令构成的序列，每条指令至多包含一个目标变量和两个源操作数。

四元式指令拓扑模型
~~~~~~~~~~~~~~~~~~

MiniLang 3AC 采用规整的四元式结构：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        3AC 四元式指令物理结构模型                           |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   struct IRInstruction {                                                    |
   |       IROp Op;           // 指令操作码枚举 (ADD, SUB, LOAD, BR_FALSE ...)   |
   |       std::string Dest;  // 结果赋值目标 (虚拟寄存器 %t 或内存变量名)       |
   |       std::string Src1;  // 第一源操作数 (操作数、常量或跳转目标)           |
   |       std::string Src2;  // 第二源操作数 (可选操作数或参数个数)             |
   |   };                                                                        |
   |                                                                             |
   |   核心操作码语义分类:                                                       |
   |     1. 存储与传输:  LOAD (加载常量/变量), STORE (写回命名变量)              |
   |     2. 算术运算:    ADD, SUB, MUL, DIV                                      |
   |     3. 条件比较:    EQ, NE, LT, LE, GT, GE                                  |
   |     4. 控制流流转:  LABEL (锚点), JUMP (无条件跳转), BR_FALSE (假跳转)      |
   |     5. 过程调用:    PARAM (实参压入), CALL (调用执行), RET (函数返回)       |
   |                                                                             |
   +-----------------------------------------------------------------------------+

虚拟寄存器与跳转标签生成机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

IR 生成器维护两个单调自增的状态计数器：
- **临时变量分配器**：调用 ``newTemp()`` 分配全局唯一的虚拟寄存器符号（如 ``%t0``, ``%t1``, ``%t2`` ...），代表单次计算产出的临时值槽位。
- **控制流标签分配器**：调用 ``newLabel(prefix)`` 分配唯一的跳转目标锚点（如 ``.else_0``, ``.exit_1``, ``.loop_header_0`` ...）。

控制流降级算法：分支与循环的线性平坦化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

高层语言的嵌套控制流（``if-else`` 与 ``while``）在 3AC 降级过程中被重写为基于条件跳转与反向回跳的平坦基本块拓扑：

1. **If-Else 降级模式**：
   - 首先求值条件表达式，得到结果临时变量 ``condTemp``。
   - 分配标签 ``elseLabel`` 与 ``exitLabel``。若无 else 分支，则直接以 ``exitLabel`` 作为条件假跳转目标。
   - 发射 ``BR_FALSE condTemp, elseLabel``。
   - 降级 ``ThenBranch`` 内部的所有语句。
   - 在 then 块末尾发射无条件跳转 ``JUMP exitLabel``，越过 else 块。
   - 发射标签指令 ``elseLabel:``，紧随其后降级 ``ElseBranch`` 语句。
   - 发射收敛出口标签 ``exitLabel:``。

2. **While 循环降级模式**：
   - 分配标签 ``loopHeader`` 与 ``loopExit``。
   - 发射循环头锚点 ``loopHeader:``。
   - 求值循环守卫条件表达式，生成 ``condTemp``。
   - 发射条件假跳转 ``BR_FALSE condTemp, loopExit``，当条件不满足时跳出循环。
   - 降级循环体 ``Body`` 中的所有语句。
   - 在循环体末尾发射反向回跳 ``JUMP loopHeader``，维系循环迭代。
   - 发射循环退出锚点 ``loopExit:``。

C++ 工业级自包含微型编译器前端与 IR 生成引擎实战
------------------------------------------------

以下给出一套自包含、完整可编译、无第三方依赖的 C++17 微型编译器前端实现。包含：
1. ``SourceLocation`` 与词法分析器 ``Lexer``；
2. 抽象语法树体系与具备结合力驱动的 ``Parser``；
3. 嵌套 ``Scope`` 符号表与双遍扫描 ``TypeChecker``；
4. 线性三地址码 ``IRGenerator``；
5. 端到端测试套件，驱动一段完整的阶乘与条件分支程序，验证编译全链路。

.. code-block:: cpp

   #include <iostream>
   #include <vector>
   #include <string>
   #include <memory>
   #include <unordered_map>
   #include <cassert>
   #include <sstream>
   #include <cctype>

   namespace minilang {

   // ============================================================================
   // 1. 源码位置与 Token 体系
   // ============================================================================
   struct SourceLocation {
       size_t Line = 1;
       size_t Column = 1;

       std::string toString() const {
           return std::to_string(Line) + ":" + std::to_string(Column);
       }
   };

   enum class TokenType {
       Eof,
       // 关键字
       KwFn, KwLet, KwIf, KwElse, KwWhile, KwReturn,
       // 类型标识
       TypeInt, TypeBool,
       // 字面量与标识符
       Identifier, IntLiteral, True, False,
       // 操作符
       Plus, Minus, Star, Slash,
       Assign,
       EqualEqual, BangEqual, Less, LessEqual, Greater, GreaterEqual,
       // 分隔符
       LParen, RParen, LBrace, RBrace, Colon, Semicolon, Comma, Arrow
   };

   struct Token {
       TokenType Type;
       std::string Lexeme;
       int64_t IntValue = 0;
       SourceLocation Loc;
   };

   // ============================================================================
   // 2. 词法分析器 (Lexer)
   // ============================================================================
   class Lexer {
   public:
       explicit Lexer(std::string source) : Source(std::move(source)) {}

       std::vector<Token> tokenize() {
           std::vector<Token> tokens;
           while (!isAtEnd()) {
               skipWhitespaceAndComments();
               if (isAtEnd()) break;

               char c = peek();
               if (std::isalpha(c) || c == '_') {
                   tokens.push_back(lexIdentifierOrKeyword());
               } else if (std::isdigit(c)) {
                   tokens.push_back(lexInteger());
               } else {
                   tokens.push_back(lexOperatorOrPunctuation());
               }
           }
           tokens.push_back({TokenType::Eof, "<EOF>", 0, {CurrentLine, CurrentCol}});
           return tokens;
       }

   private:
       std::string Source;
       size_t Cursor = 0;
       size_t CurrentLine = 1;
       size_t CurrentCol = 1;

       bool isAtEnd() const { return Cursor >= Source.size(); }
       char peek() const { return Source[Cursor]; }
       char peekNext() const { return (Cursor + 1 < Source.size()) ? Source[Cursor + 1] : '\0'; }

       char advance() {
           char c = Source[Cursor++];
           if (c == '
') {
               CurrentLine++;
               CurrentCol = 1;
           } else {
               CurrentCol++;
           }
           return c;
       }

       void skipWhitespaceAndComments() {
           while (!isAtEnd()) {
               char c = peek();
               if (c == ' ' || c == '	' || c == '\r' || c == '
') {
                   advance();
               } else if (c == '/' && peekNext() == '/') {
                   while (!isAtEnd() && peek() != '
') {
                       advance();
                   }
               } else {
                   break;
               }
           }
       }

       Token lexIdentifierOrKeyword() {
           SourceLocation loc = {CurrentLine, CurrentCol};
           std::string lexeme;
           while (!isAtEnd() && (std::isalnum(peek()) || peek() == '_')) {
               lexeme.push_back(advance());
           }

           static const std::unordered_map<std::string, TokenType> keywords = {
               {"fn", TokenType::KwFn},
               {"let", TokenType::KwLet},
               {"if", TokenType::KwIf},
               {"else", TokenType::KwElse},
               {"while", TokenType::KwWhile},
               {"return", TokenType::KwReturn},
               {"int", TokenType::TypeInt},
               {"bool", TokenType::TypeBool},
               {"true", TokenType::True},
               {"false", TokenType::False}
           };

           auto it = keywords.find(lexeme);
           TokenType type = (it != keywords.end()) ? it->second : TokenType::Identifier;
           return {type, lexeme, 0, loc};
       }

       Token lexInteger() {
           SourceLocation loc = {CurrentLine, CurrentCol};
           std::string lexeme;
           while (!isAtEnd() && std::isdigit(peek())) {
               lexeme.push_back(advance());
           }
           int64_t val = std::stoll(lexeme);
           return {TokenType::IntLiteral, lexeme, val, loc};
       }

       Token lexOperatorOrPunctuation() {
           SourceLocation loc = {CurrentLine, CurrentCol};
           char c = advance();
           switch (c) {
               case '+': return {TokenType::Plus, "+", 0, loc};
               case '-':
                   if (!isAtEnd() && peek() == '>') {
                       advance();
                       return {TokenType::Arrow, "->", 0, loc};
                   }
                   return {TokenType::Minus, "-", 0, loc};
               case '*': return {TokenType::Star, "*", 0, loc};
               case '/': return {TokenType::Slash, "/", 0, loc};
               case '(': return {TokenType::LParen, "(", 0, loc};
               case ')': return {TokenType::RParen, ")", 0, loc};
               case '{': return {TokenType::LBrace, "{", 0, loc};
               case '}': return {TokenType::RBrace, "}", 0, loc};
               case ':': return {TokenType::Colon, ":", 0, loc};
               case ';': return {TokenType::Semicolon, ";", 0, loc};
               case ',': return {TokenType::Comma, ",", 0, loc};
               case '=':
                   if (!isAtEnd() && peek() == '=') {
                       advance();
                       return {TokenType::EqualEqual, "==", 0, loc};
                   }
                   return {TokenType::Assign, "=", 0, loc};
               case '!':
                   if (!isAtEnd() && peek() == '=') {
                       advance();
                       return {TokenType::BangEqual, "!=", 0, loc};
                   }
                   break;
               case '<':
                   if (!isAtEnd() && peek() == '=') {
                       advance();
                       return {TokenType::LessEqual, "<=", 0, loc};
                   }
                   return {TokenType::Less, "<", 0, loc};
               case '>':
                   if (!isAtEnd() && peek() == '=') {
                       advance();
                       return {TokenType::GreaterEqual, ">=", 0, loc};
                   }
                   return {TokenType::Greater, ">", 0, loc};
               default:
                   break;
           }
           std::cerr << "Lexical error: unexpected character '" << c << "' at " << loc.toString() << "
";
           return {TokenType::Eof, "", 0, loc};
       }
   };

   // ============================================================================
   // 3. 抽象语法树 (AST)
   // ============================================================================
   enum class DataType { Void, Int, Bool, Unknown };

   inline std::string dataTypeToString(DataType t) {
       switch (t) {
           case DataType::Void: return "void";
           case DataType::Int: return "int";
           case DataType::Bool: return "bool";
           case DataType::Unknown: return "unknown";
       }
       return "unknown";
   }

   class ASTNode {
   public:
       virtual ~ASTNode() = default;
       SourceLocation Loc;
       explicit ASTNode(SourceLocation loc) : Loc(loc) {}
   };

   class ExprNode : public ASTNode {
   public:
       DataType InferredType = DataType::Unknown;
       using ASTNode::ASTNode;
   };

   class IntLiteralExpr : public ExprNode {
   public:
       int64_t Value;
       IntLiteralExpr(int64_t val, SourceLocation loc) : ExprNode(loc), Value(val) {
           InferredType = DataType::Int;
       }
   };

   class BoolLiteralExpr : public ExprNode {
   public:
       bool Value;
       BoolLiteralExpr(bool val, SourceLocation loc) : ExprNode(loc), Value(val) {
           InferredType = DataType::Bool;
       }
   };

   class VariableExpr : public ExprNode {
   public:
       std::string Name;
       VariableExpr(std::string name, SourceLocation loc) : ExprNode(loc), Name(std::move(name)) {}
   };

   class BinaryExpr : public ExprNode {
   public:
       TokenType Op;
       std::unique_ptr<ExprNode> Left;
       std::unique_ptr<ExprNode> Right;

       BinaryExpr(TokenType op, std::unique_ptr<ExprNode> lhs, std::unique_ptr<ExprNode> rhs, SourceLocation loc)
           : ExprNode(loc), Op(op), Left(std::move(lhs)), Right(std::move(rhs)) {}
   };

   class CallExpr : public ExprNode {
   public:
       std::string Callee;
       std::vector<std::unique_ptr<ExprNode>> Args;

       CallExpr(std::string callee, std::vector<std::unique_ptr<ExprNode>> args, SourceLocation loc)
           : ExprNode(loc), Callee(std::move(callee)), Args(std::move(args)) {}
   };

   class StmtNode : public ASTNode {
   public:
       using ASTNode::ASTNode;
   };

   class BlockStmt : public StmtNode {
   public:
       std::vector<std::unique_ptr<StmtNode>> Statements;
       using StmtNode::StmtNode;
   };

   class LetStmt : public StmtNode {
   public:
       std::string VarName;
       DataType DeclType;
       std::unique_ptr<ExprNode> Initializer;

       LetStmt(std::string name, DataType type, std::unique_ptr<ExprNode> init, SourceLocation loc)
           : StmtNode(loc), VarName(std::move(name)), DeclType(type), Initializer(std::move(init)) {}
   };

   class AssignStmt : public StmtNode {
   public:
       std::string VarName;
       std::unique_ptr<ExprNode> Value;

       AssignStmt(std::string name, std::unique_ptr<ExprNode> val, SourceLocation loc)
           : StmtNode(loc), VarName(std::move(name)), Value(std::move(val)) {}
   };

   class IfStmt : public StmtNode {
   public:
       std::unique_ptr<ExprNode> Condition;
       std::unique_ptr<BlockStmt> ThenBranch;
       std::unique_ptr<BlockStmt> ElseBranch;

       IfStmt(std::unique_ptr<ExprNode> cond, std::unique_ptr<BlockStmt> thenB, std::unique_ptr<BlockStmt> elseB, SourceLocation loc)
           : StmtNode(loc), Condition(std::move(cond)), ThenBranch(std::move(thenB)), ElseBranch(std::move(elseB)) {}
   };

   class WhileStmt : public StmtNode {
   public:
       std::unique_ptr<ExprNode> Condition;
       std::unique_ptr<BlockStmt> Body;

       WhileStmt(std::unique_ptr<ExprNode> cond, std::unique_ptr<BlockStmt> body, SourceLocation loc)
           : StmtNode(loc), Condition(std::move(cond)), Body(std::move(body)) {}
   };

   class ReturnStmt : public StmtNode {
   public:
       std::unique_ptr<ExprNode> Expr;

       ReturnStmt(std::unique_ptr<ExprNode> expr, SourceLocation loc)
           : StmtNode(loc), Expr(std::move(expr)) {}
   };

   struct Parameter {
       std::string Name;
       DataType Type;
       SourceLocation Loc;
   };

   class FunctionDecl : public ASTNode {
   public:
       std::string Name;
       std::vector<Parameter> Params;
       DataType ReturnType;
       std::unique_ptr<BlockStmt> Body;

       FunctionDecl(std::string name, std::vector<Parameter> params, DataType retType, std::unique_ptr<BlockStmt> body, SourceLocation loc)
           : ASTNode(loc), Name(std::move(name)), Params(std::move(params)), ReturnType(retType), Body(std::move(body)) {}
   };

   class ProgramNode : public ASTNode {
   public:
       std::vector<std::unique_ptr<FunctionDecl>> Functions;
       explicit ProgramNode(SourceLocation loc) : ASTNode(loc) {}
   };

   // ============================================================================
   // 4. 递归下降与 Pratt 结合力解析器
   // ============================================================================
   class Parser {
   public:
       explicit Parser(std::vector<Token> tokens) : Tokens(std::move(tokens)) {}

       std::unique_ptr<ProgramNode> parseProgram() {
           auto prog = std::make_unique<ProgramNode>(peek().Loc);
           while (!isAtEnd()) {
               prog->Functions.push_back(parseFunction());
           }
           return prog;
       }

   private:
       std::vector<Token> Tokens;
       size_t Index = 0;

       const Token& peek() const { return Tokens[Index]; }
       bool isAtEnd() const { return Index >= Tokens.size() || peek().Type == TokenType::Eof; }

       const Token& advance() {
           if (!isAtEnd()) Index++;
           return Tokens[Index - 1];
       }

       bool check(TokenType type) const {
           if (Index >= Tokens.size()) return false;
           return Tokens[Index].Type == type;
       }

       bool match(TokenType type) {
           if (check(type)) {
               advance();
               return true;
           }
           return false;
       }

       const Token& consume(TokenType type, const std::string& errMsg) {
           if (check(type)) return advance();
           std::cerr << "Parser error at " << peek().Loc.toString() << ": " << errMsg << ", found '" << peek().Lexeme << "'
";
           assert(false && "Parser error");
           return peek();
       }

       DataType parseType() {
           if (match(TokenType::TypeInt)) return DataType::Int;
           if (match(TokenType::TypeBool)) return DataType::Bool;
           std::cerr << "Unknown type at " << peek().Loc.toString() << "
";
           assert(false);
           return DataType::Unknown;
       }

       std::unique_ptr<FunctionDecl> parseFunction() {
           consume(TokenType::KwFn, "Expected 'fn'");
           const Token& nameTok = consume(TokenType::Identifier, "Expected function name");
           consume(TokenType::LParen, "Expected '(' after function name");

           std::vector<Parameter> params;
           if (!check(TokenType::RParen)) {
               do {
                   const Token& pName = consume(TokenType::Identifier, "Expected parameter name");
                   consume(TokenType::Colon, "Expected ':' after parameter name");
                   DataType pType = parseType();
                   params.push_back({pName.Lexeme, pType, pName.Loc});
               } while (match(TokenType::Comma));
           }
           consume(TokenType::RParen, "Expected ')' after parameters");

           DataType retType = DataType::Void;
           if (match(TokenType::Arrow)) {
               retType = parseType();
           }

           auto body = parseBlock();
           return std::make_unique<FunctionDecl>(nameTok.Lexeme, std::move(params), retType, std::move(body), nameTok.Loc);
       }

       std::unique_ptr<BlockStmt> parseBlock() {
           const Token& brace = consume(TokenType::LBrace, "Expected '{'");
           auto block = std::make_unique<BlockStmt>(brace.Loc);
           while (!check(TokenType::RBrace) && !isAtEnd()) {
               block->Statements.push_back(parseStatement());
           }
           consume(TokenType::RBrace, "Expected '}'");
           return block;
       }

       std::unique_ptr<StmtNode> parseStatement() {
           if (match(TokenType::KwLet)) {
               return parseLetStatement();
           }
           if (match(TokenType::KwIf)) {
               return parseIfStatement();
           }
           if (match(TokenType::KwWhile)) {
               return parseWhileStatement();
           }
           if (match(TokenType::KwReturn)) {
               return parseReturnStatement();
           }
           if (check(TokenType::Identifier)) {
               if (Index + 1 < Tokens.size() && Tokens[Index + 1].Type == TokenType::Assign) {
                   return parseAssignStatement();
               }
           }
           SourceLocation loc = peek().Loc;
           auto expr = parseExpression(0);
           consume(TokenType::Semicolon, "Expected ';' after expression");
           return std::make_unique<AssignStmt>("_discard", std::move(expr), loc);
       }

       std::unique_ptr<LetStmt> parseLetStatement() {
           SourceLocation loc = Tokens[Index - 1].Loc;
           const Token& nameTok = consume(TokenType::Identifier, "Expected variable name");
           consume(TokenType::Colon, "Expected ':' after variable name");
           DataType type = parseType();
           consume(TokenType::Assign, "Expected '=' in let declaration");
           auto init = parseExpression(0);
           consume(TokenType::Semicolon, "Expected ';' after let statement");
           return std::make_unique<LetStmt>(nameTok.Lexeme, type, std::move(init), loc);
       }

       std::unique_ptr<AssignStmt> parseAssignStatement() {
           const Token& nameTok = consume(TokenType::Identifier, "Expected identifier");
           consume(TokenType::Assign, "Expected '='");
           auto val = parseExpression(0);
           consume(TokenType::Semicolon, "Expected ';' after assignment");
           return std::make_unique<AssignStmt>(nameTok.Lexeme, std::move(val), nameTok.Loc);
       }

       std::unique_ptr<IfStmt> parseIfStatement() {
           SourceLocation loc = Tokens[Index - 1].Loc;
           auto cond = parseExpression(0);
           auto thenBranch = parseBlock();
           std::unique_ptr<BlockStmt> elseBranch = nullptr;
           if (match(TokenType::KwElse)) {
               elseBranch = parseBlock();
           }
           return std::make_unique<IfStmt>(std::move(cond), std::move(thenBranch), std::move(elseBranch), loc);
       }

       std::unique_ptr<WhileStmt> parseWhileStatement() {
           SourceLocation loc = Tokens[Index - 1].Loc;
           auto cond = parseExpression(0);
           auto body = parseBlock();
           return std::make_unique<WhileStmt>(std::move(cond), std::move(body), loc);
       }

       std::unique_ptr<ReturnStmt> parseReturnStatement() {
           SourceLocation loc = Tokens[Index - 1].Loc;
           std::unique_ptr<ExprNode> retVal = nullptr;
           if (!check(TokenType::Semicolon)) {
               retVal = parseExpression(0);
           }
           consume(TokenType::Semicolon, "Expected ';' after return");
           return std::make_unique<ReturnStmt>(std::move(retVal), loc);
       }

       int getInfixBindingPower(TokenType op) const {
           switch (op) {
               case TokenType::EqualEqual:
               case TokenType::BangEqual:
               case TokenType::Less:
               case TokenType::LessEqual:
               case TokenType::Greater:
               case TokenType::GreaterEqual:
                   return 10;
               case TokenType::Plus:
               case TokenType::Minus:
                   return 20;
               case TokenType::Star:
               case TokenType::Slash:
                   return 30;
               default:
                   return -1;
           }
       }

       std::unique_ptr<ExprNode> parsePrimary() {
           SourceLocation loc = peek().Loc;
           if (match(TokenType::IntLiteral)) {
               return std::make_unique<IntLiteralExpr>(Tokens[Index - 1].IntValue, loc);
           }
           if (match(TokenType::True)) {
               return std::make_unique<BoolLiteralExpr>(true, loc);
           }
           if (match(TokenType::False)) {
               return std::make_unique<BoolLiteralExpr>(false, loc);
           }
           if (match(TokenType::Identifier)) {
               std::string name = Tokens[Index - 1].Lexeme;
               if (match(TokenType::LParen)) {
                   std::vector<std::unique_ptr<ExprNode>> args;
                   if (!check(TokenType::RParen)) {
                       do {
                           args.push_back(parseExpression(0));
                       } while (match(TokenType::Comma));
                   }
                   consume(TokenType::RParen, "Expected ')' after call args");
                   return std::make_unique<CallExpr>(name, std::move(args), loc);
               }
               return std::make_unique<VariableExpr>(name, loc);
           }
           if (match(TokenType::LParen)) {
               auto inner = parseExpression(0);
               consume(TokenType::RParen, "Expected ')'");
               return inner;
           }
           std::cerr << "Syntax error: Unexpected token '" << peek().Lexeme << "' at " << loc.toString() << "
";
           assert(false);
           return nullptr;
       }

       std::unique_ptr<ExprNode> parseExpression(int minBp) {
           auto lhs = parsePrimary();
           while (true) {
               TokenType op = peek().Type;
               int bp = getInfixBindingPower(op);
               if (bp < minBp) break;

               advance();
               auto rhs = parseExpression(bp + 1);
               lhs = std::make_unique<BinaryExpr>(op, std::move(lhs), std::move(rhs), lhs->Loc);
           }
           return lhs;
       }
   };

   // ============================================================================
   // 5. 符号表与类型检查器 (Semantic Analysis)
   // ============================================================================
   struct Symbol {
       std::string Name;
       DataType Type;
       bool IsFunction = false;
       std::vector<DataType> ParamTypes;
   };

   class Scope {
   public:
       std::shared_ptr<Scope> Parent;
       std::unordered_map<std::string, Symbol> Symbols;

       explicit Scope(std::shared_ptr<Scope> parent = nullptr) : Parent(std::move(parent)) {}

       bool define(const Symbol& sym) {
           if (Symbols.find(sym.Name) != Symbols.end()) {
               return false;
           }
           Symbols[sym.Name] = sym;
           return true;
       }

       const Symbol* lookup(const std::string& name) const {
           auto it = Symbols.find(name);
           if (it != Symbols.end()) return &it->second;
           if (Parent) return Parent->lookup(name);
           return nullptr;
       }
   };

   class TypeChecker {
   public:
       void check(ProgramNode& prog) {
           GlobalScope = std::make_shared<Scope>();

           // 第 1 遍扫描：收集函数原型
           for (const auto& fn : prog.Functions) {
               std::vector<DataType> pTypes;
               for (const auto& p : fn->Params) pTypes.push_back(p.Type);
               Symbol fnSym = {fn->Name, fn->ReturnType, true, pTypes};
               if (!GlobalScope->define(fnSym)) {
                   reportError("Duplicate function definition: " + fn->Name, fn->Loc);
               }
           }

           // 第 2 遍扫描：深入函数体检查
           for (const auto& fn : prog.Functions) {
               CurrentFunction = fn.get();
               auto fnScope = std::make_shared<Scope>(GlobalScope);
               for (const auto& p : fn->Params) {
                   if (!fnScope->define({p.Name, p.Type, false, {}})) {
                       reportError("Duplicate parameter name: " + p.Name, p.Loc);
                   }
               }
               checkBlock(*fn->Body, fnScope);
           }
       }

   private:
       std::shared_ptr<Scope> GlobalScope;
       FunctionDecl* CurrentFunction = nullptr;

       void reportError(const std::string& msg, SourceLocation loc) {
           std::cerr << "Semantic Error at " << loc.toString() << ": " << msg << "
";
           assert(false && "Semantic check failed");
       }

       void checkBlock(BlockStmt& block, std::shared_ptr<Scope> scope) {
           for (auto& stmt : block.Statements) {
               checkStatement(*stmt, scope);
           }
       }

       void checkStatement(StmtNode& stmt, std::shared_ptr<Scope> scope) {
           if (auto letStmt = dynamic_cast<LetStmt*>(&stmt)) {
               DataType initType = checkExpression(*letStmt->Initializer, scope);
               if (initType != letStmt->DeclType) {
                   reportError("Type mismatch in 'let' declaration for '" + letStmt->VarName + 
                               "'. Expected " + dataTypeToString(letStmt->DeclType) + 
                               ", got " + dataTypeToString(initType), letStmt->Loc);
               }
               if (!scope->define({letStmt->VarName, letStmt->DeclType, false, {}})) {
                   reportError("Variable redeclaration: " + letStmt->VarName, letStmt->Loc);
               }
           } else if (auto assignStmt = dynamic_cast<AssignStmt*>(&stmt)) {
               if (assignStmt->VarName == "_discard") {
                   checkExpression(*assignStmt->Value, scope);
                   return;
               }
               const Symbol* sym = scope->lookup(assignStmt->VarName);
               if (!sym || sym->IsFunction) {
                   reportError("Assignment to undeclared variable: " + assignStmt->VarName, assignStmt->Loc);
               }
               DataType valType = checkExpression(*assignStmt->Value, scope);
               if (valType != sym->Type) {
                   reportError("Type mismatch in assignment to '" + assignStmt->VarName + 
                               "'. Expected " + dataTypeToString(sym->Type) + 
                               ", got " + dataTypeToString(valType), assignStmt->Loc);
               }
           } else if (auto ifStmt = dynamic_cast<IfStmt*>(&stmt)) {
               DataType condType = checkExpression(*ifStmt->Condition, scope);
               if (condType != DataType::Bool) {
                   reportError("'if' condition must be bool, got " + dataTypeToString(condType), ifStmt->Condition->Loc);
               }
               auto thenScope = std::make_shared<Scope>(scope);
               checkBlock(*ifStmt->ThenBranch, thenScope);
               if (ifStmt->ElseBranch) {
                   auto elseScope = std::make_shared<Scope>(scope);
                   checkBlock(*ifStmt->ElseBranch, elseScope);
               }
           } else if (auto whileStmt = dynamic_cast<WhileStmt*>(&stmt)) {
               DataType condType = checkExpression(*whileStmt->Condition, scope);
               if (condType != DataType::Bool) {
                   reportError("'while' condition must be bool, got " + dataTypeToString(condType), whileStmt->Condition->Loc);
               }
               auto bodyScope = std::make_shared<Scope>(scope);
               checkBlock(*whileStmt->Body, bodyScope);
           } else if (auto retStmt = dynamic_cast<ReturnStmt*>(&stmt)) {
               DataType actualRet = retStmt->Expr ? checkExpression(*retStmt->Expr, scope) : DataType::Void;
               if (actualRet != CurrentFunction->ReturnType) {
                   reportError("Return type mismatch. Expected " + dataTypeToString(CurrentFunction->ReturnType) + 
                               ", got " + dataTypeToString(actualRet), retStmt->Loc);
               }
           }
       }

       DataType checkExpression(ExprNode& expr, std::shared_ptr<Scope> scope) {
           if (dynamic_cast<IntLiteralExpr*>(&expr)) {
               expr.InferredType = DataType::Int;
               return DataType::Int;
           }
           if (dynamic_cast<BoolLiteralExpr*>(&expr)) {
               expr.InferredType = DataType::Bool;
               return DataType::Bool;
           }
           if (auto varExpr = dynamic_cast<VariableExpr*>(&expr)) {
               const Symbol* sym = scope->lookup(varExpr->Name);
               if (!sym || sym->IsFunction) {
                   reportError("Use of undeclared variable: " + varExpr->Name, varExpr->Loc);
               }
               expr.InferredType = sym->Type;
               return sym->Type;
           }
           if (auto binExpr = dynamic_cast<BinaryExpr*>(&expr)) {
               DataType lhsT = checkExpression(*binExpr->Left, scope);
               DataType rhsT = checkExpression(*binExpr->Right, scope);

               switch (binExpr->Op) {
                   case TokenType::Plus:
                   case TokenType::Minus:
                   case TokenType::Star:
                   case TokenType::Slash:
                       if (lhsT != DataType::Int || rhsT != DataType::Int) {
                           reportError("Arithmetic operator requires int operands", binExpr->Loc);
                       }
                       binExpr->InferredType = DataType::Int;
                       return DataType::Int;
                   case TokenType::EqualEqual:
                   case TokenType::BangEqual:
                       if (lhsT != rhsT) {
                           reportError("Equality comparison requires identical types", binExpr->Loc);
                       }
                       binExpr->InferredType = DataType::Bool;
                       return DataType::Bool;
                   case TokenType::Less:
                   case TokenType::LessEqual:
                   case TokenType::Greater:
                   case TokenType::GreaterEqual:
                       if (lhsT != DataType::Int || rhsT != DataType::Int) {
                           reportError("Relational comparison requires int operands", binExpr->Loc);
                       }
                       binExpr->InferredType = DataType::Bool;
                       return DataType::Bool;
                   default:
                       reportError("Unsupported binary operator", binExpr->Loc);
               }
           }
           if (auto callExpr = dynamic_cast<CallExpr*>(&expr)) {
               const Symbol* sym = GlobalScope->lookup(callExpr->Callee);
               if (!sym || !sym->IsFunction) {
                   reportError("Call to undeclared function: " + callExpr->Callee, callExpr->Loc);
               }
               if (callExpr->Args.size() != sym->ParamTypes.size()) {
                   reportError("Function '" + callExpr->Callee + "' expects " + 
                               std::to_string(sym->ParamTypes.size()) + " arguments, got " + 
                               std::to_string(callExpr->Args.size()), callExpr->Loc);
               }
               for (size_t i = 0; i < callExpr->Args.size(); ++i) {
                   DataType argT = checkExpression(*callExpr->Args[i], scope);
                   if (argT != sym->ParamTypes[i]) {
                       reportError("Argument " + std::to_string(i) + " type mismatch in call to '" + 
                                   callExpr->Callee + "'. Expected " + dataTypeToString(sym->ParamTypes[i]) + 
                                   ", got " + dataTypeToString(argT), callExpr->Args[i]->Loc);
                   }
               }
               callExpr->InferredType = sym->Type;
               return sym->Type;
           }
           reportError("Unknown expression node", expr.Loc);
           return DataType::Unknown;
       }
   };

   // ============================================================================
   // 6. 三地址码 (3AC) 线性中间表示与 Lowering
   // ============================================================================
   enum class IROp {
       Alloca, Store, Load,
       Add, Sub, Mul, Div,
       Equal, NotEqual, Less, LessEqual, Greater, GreaterEqual,
       Jump, BranchIfFalse,
       Label,
       Param, Call, Return
   };

   inline std::string irOpToString(IROp op) {
       switch (op) {
           case IROp::Alloca: return "ALLOCA";
           case IROp::Store: return "STORE";
           case IROp::Load: return "LOAD";
           case IROp::Add: return "ADD";
           case IROp::Sub: return "SUB";
           case IROp::Mul: return "MUL";
           case IROp::Div: return "DIV";
           case IROp::Equal: return "EQ";
           case IROp::NotEqual: return "NE";
           case IROp::Less: return "LT";
           case IROp::LessEqual: return "LE";
           case IROp::Greater: return "GT";
           case IROp::GreaterEqual: return "GE";
           case IROp::Jump: return "JUMP";
           case IROp::BranchIfFalse: return "BR_FALSE";
           case IROp::Label: return "LABEL";
           case IROp::Param: return "PARAM";
           case IROp::Call: return "CALL";
           case IROp::Return: return "RET";
       }
       return "UNKNOWN";
   }

   struct IRInstruction {
       IROp Op;
       std::string Dest;
       std::string Src1;
       std::string Src2;

       std::string toString() const {
           std::ostringstream oss;
           if (Op == IROp::Label) {
               oss << Dest << ":";
               return oss.str();
           }
           oss << "  ";
           if (!Dest.empty()) {
               oss << Dest << " = ";
           }
           oss << irOpToString(Op);
           if (!Src1.empty()) oss << " " << Src1;
           if (!Src2.empty()) oss << ", " << Src2;
           return oss.str();
       }
   };

   struct IRFunction {
       std::string Name;
       std::vector<std::string> Params;
       std::vector<IRInstruction> Instructions;

       std::string toString() const {
           std::ostringstream oss;
           oss << "function @" << Name << "(";
           for (size_t i = 0; i < Params.size(); ++i) {
               oss << Params[i] << (i + 1 < Params.size() ? ", " : "");
           }
           oss << ") {
";
           for (const auto& inst : Instructions) {
               oss << inst.toString() << "
";
           }
           oss << "}
";
           return oss.str();
       }
   };

   class IRGenerator {
   public:
       std::vector<IRFunction> generate(const ProgramNode& prog) {
           std::vector<IRFunction> funcs;
           for (const auto& fn : prog.Functions) {
               funcs.push_back(lowerFunction(*fn));
           }
           return funcs;
       }

   private:
       size_t TempCounter = 0;
       size_t LabelCounter = 0;

       std::string newTemp() {
           return "%t" + std::to_string(TempCounter++);
       }

       std::string newLabel(const std::string& prefix = "L") {
           return "." + prefix + "_" + std::to_string(LabelCounter++);
       }

       IRFunction lowerFunction(const FunctionDecl& fn) {
           TempCounter = 0;
           LabelCounter = 0;
           IRFunction irFn;
           irFn.Name = fn.Name;

           for (const auto& p : fn.Params) {
               irFn.Params.push_back(p.Name);
           }

           lowerBlock(*fn.Body, irFn);

           if (irFn.Instructions.empty() || irFn.Instructions.back().Op != IROp::Return) {
               irFn.Instructions.push_back({IROp::Return, "", "", ""});
           }
           return irFn;
       }

       void lowerBlock(const BlockStmt& block, IRFunction& irFn) {
           for (const auto& stmt : block.Statements) {
               lowerStatement(*stmt, irFn);
           }
       }

       void lowerStatement(const StmtNode& stmt, IRFunction& irFn) {
           if (auto letStmt = dynamic_cast<const LetStmt*>(&stmt)) {
               std::string valTemp = lowerExpression(*letStmt->Initializer, irFn);
               irFn.Instructions.push_back({IROp::Store, letStmt->VarName, valTemp, ""});
           } else if (auto assignStmt = dynamic_cast<const AssignStmt*>(&stmt)) {
               if (assignStmt->VarName == "_discard") {
                   lowerExpression(*assignStmt->Value, irFn);
                   return;
               }
               std::string valTemp = lowerExpression(*assignStmt->Value, irFn);
               irFn.Instructions.push_back({IROp::Store, assignStmt->VarName, valTemp, ""});
           } else if (auto ifStmt = dynamic_cast<const IfStmt*>(&stmt)) {
               std::string condTemp = lowerExpression(*ifStmt->Condition, irFn);
               std::string elseLabel = newLabel("else");
               std::string exitLabel = newLabel("exit");

               std::string falseTarget = ifStmt->ElseBranch ? elseLabel : exitLabel;
               irFn.Instructions.push_back({IROp::BranchIfFalse, "", condTemp, falseTarget});

               lowerBlock(*ifStmt->ThenBranch, irFn);
               if (ifStmt->ElseBranch) {
                   irFn.Instructions.push_back({IROp::Jump, "", exitLabel, ""});
                   irFn.Instructions.push_back({IROp::Label, elseLabel, "", ""});
                   lowerBlock(*ifStmt->ElseBranch, irFn);
               }
               irFn.Instructions.push_back({IROp::Label, exitLabel, "", ""});
           } else if (auto whileStmt = dynamic_cast<const WhileStmt*>(&stmt)) {
               std::string loopHeader = newLabel("loop_header");
               std::string loopExit = newLabel("loop_exit");

               irFn.Instructions.push_back({IROp::Label, loopHeader, "", ""});
               std::string condTemp = lowerExpression(*whileStmt->Condition, irFn);
               irFn.Instructions.push_back({IROp::BranchIfFalse, "", condTemp, loopExit});

               lowerBlock(*whileStmt->Body, irFn);
               irFn.Instructions.push_back({IROp::Jump, "", loopHeader, ""});
               irFn.Instructions.push_back({IROp::Label, loopExit, "", ""});
           } else if (auto retStmt = dynamic_cast<const ReturnStmt*>(&stmt)) {
               std::string retVal = "";
               if (retStmt->Expr) {
                   retVal = lowerExpression(*retStmt->Expr, irFn);
               }
               irFn.Instructions.push_back({IROp::Return, "", retVal, ""});
           }
       }

       std::string lowerExpression(const ExprNode& expr, IRFunction& irFn) {
           if (auto intLit = dynamic_cast<const IntLiteralExpr*>(&expr)) {
               std::string t = newTemp();
               irFn.Instructions.push_back({IROp::Load, t, std::to_string(intLit->Value), ""});
               return t;
           }
           if (auto boolLit = dynamic_cast<const BoolLiteralExpr*>(&expr)) {
               std::string t = newTemp();
               irFn.Instructions.push_back({IROp::Load, t, boolLit->Value ? "1" : "0", ""});
               return t;
           }
           if (auto varExpr = dynamic_cast<const VariableExpr*>(&expr)) {
               std::string t = newTemp();
               irFn.Instructions.push_back({IROp::Load, t, varExpr->Name, ""});
               return t;
           }
           if (auto binExpr = dynamic_cast<const BinaryExpr*>(&expr)) {
               std::string lhs = lowerExpression(*binExpr->Left, irFn);
               std::string rhs = lowerExpression(*binExpr->Right, irFn);
               std::string res = newTemp();
               IROp op;
               switch (binExpr->Op) {
                   case TokenType::Plus: op = IROp::Add; break;
                   case TokenType::Minus: op = IROp::Sub; break;
                   case TokenType::Star: op = IROp::Mul; break;
                   case TokenType::Slash: op = IROp::Div; break;
                   case TokenType::EqualEqual: op = IROp::Equal; break;
                   case TokenType::BangEqual: op = IROp::NotEqual; break;
                   case TokenType::Less: op = IROp::Less; break;
                   case TokenType::LessEqual: op = IROp::LessEqual; break;
                   case TokenType::Greater: op = IROp::Greater; break;
                   case TokenType::GreaterEqual: op = IROp::GreaterEqual; break;
                   default: assert(false && "Unhandled bin op");
               }
               irFn.Instructions.push_back({op, res, lhs, rhs});
               return res;
           }
           if (auto callExpr = dynamic_cast<const CallExpr*>(&expr)) {
               std::vector<std::string> argTemps;
               for (const auto& arg : callExpr->Args) {
                   argTemps.push_back(lowerExpression(*arg, irFn));
               }
               for (const auto& at : argTemps) {
                   irFn.Instructions.push_back({IROp::Param, "", at, ""});
               }
               std::string res = newTemp();
               irFn.Instructions.push_back({IROp::Call, res, "@" + callExpr->Callee, std::to_string(argTemps.size())});
               return res;
           }
           assert(false && "Unhandled expr lowering");
           return "";
       }
   };

   } // namespace minilang

   // ============================================================================
   // 7. 测试驱动套件
   // ============================================================================
   int main() {
       std::string sourceCode = R"(
           // 计算 1 到 n 的阶乘
           fn factorial(n: int) -> int {
               let res: int = 1;
               let i: int = 1;
               while i <= n {
                   res = res * i;
                   i = i + 1;
               }
               return res;
           }

           fn main() -> int {
               let val: int = factorial(5);
               if val == 120 {
                   return 1;
               } else {
                   return 0;
               }
           }
       )";

       std::cout << "[Step 1] 词法分词分析...
";
       minilang::Lexer lexer(sourceCode);
       auto tokens = lexer.tokenize();
       std::cout << "Token 总数: " << tokens.size() << "
";
       assert(tokens.size() > 20);

       std::cout << "[Step 2] 语法树解析 (Recursive Descent + Pratt)...
";
       minilang::Parser parser(tokens);
       auto prog = parser.parseProgram();
       assert(prog->Functions.size() == 2);
       assert(prog->Functions[0]->Name == "factorial");
       assert(prog->Functions[1]->Name == "main");

       std::cout << "[Step 3] 语义分析与静态类型检查...
";
       minilang::TypeChecker checker;
       checker.check(*prog);
       std::cout << "类型检查与名字决议全部通过！
";

       std::cout << "[Step 4] 三地址码 (3AC) 降级生成...
";
       minilang::IRGenerator irGen;
       auto irModule = irGen.generate(*prog);
       assert(irModule.size() == 2);

       std::cout << "
--- 生成的三地址码 (3AC IR) 转储 ---
";
       for (const auto& fn : irModule) {
           std::cout << fn.toString() << "
";
       }

       std::cout << "[MiniCompiler Frontend] 端到端全套断言通过，前端与 IR 生成圆满成功！
";
       return 0;
   }
