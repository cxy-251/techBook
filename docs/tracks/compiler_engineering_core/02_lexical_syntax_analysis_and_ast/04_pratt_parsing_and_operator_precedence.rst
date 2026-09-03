================================================================================
表达式优先级与 Pratt 算法：Binding Power 结合力、前缀/中缀/后缀统一解析与二义性消除
================================================================================

.. note:: 前置背景与上下文承接
   在第 2 模块第 3 节中，编译器前端确立了形式文法四元组、上下文无关文法（CFG）最左/最右推导、FIRST/FOLLOW/PREDICT 预测集不动点迭代计算，以及递归下降解析器的调用栈拓扑与左递归消除。然而，在处理包含数十种运算符优先级、结合性以及多种语法形态（前缀、中缀、后缀、定界包围）的表达式时，传统递归下降文法分层会导致产生式规则过度膨胀，产生多达数十层的嵌套函数调用栈开销。本章系统解构由 Vaughan Pratt 提出的自顶向下运算符优先级（Top-Down Operator Precedence, TDOP / Pratt Parsing）算法。内容涵盖表达式二义性与运算符结合性的形式化数学模型、基于结合力（Binding Power, $LBP$ 与 $RBP$）的递归截断机制、Null Denotation（Nud）与 Left Denotation（Led）统一解析调度状态机、前缀/二元/后缀/三元及紧致下标调用的统一降解，以及消除运算符多重歧义的高性能工业级 C++ 工程实现。

表达式文法二义性、优先级与结合性的拓扑本质
-----------------------------------------

表达式解析的核心工程目标是将一维线性的 Token 序列转换为拓扑唯一的抽象语法树（AST）。由于人类常用的中缀数学记号（Infix Notation）省略了显式的嵌套定界符，操作符与操作数之间的从属结构必须依赖语法层面的优先级与结合性规则确定。

二义性文法与经典递归下降分层的工程缺陷
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

若直接使用朴素上下文无关文法表达二元运算：

$$E 	o E 	ext{ op } E \mid ( E ) \mid 	ext{Identifier} \mid 	ext{Literal}$$

该文法对于输入序列 ``a - b * c - d`` 存在多个不同的最左推导，可生成多种形状各异的推导树。

.. code-block:: text

   输入序列: a - b * c - d

   候选拓扑 A (符合数学语义):               候选拓扑 B (右结合乘法优先失真):
             Sub                                     Sub
            /   \                                   /   \
          Sub    d                                 a     Sub
         /   \                                          /   \
        a     Mul                                     Mul    d
             /   \                                   /   \
            b     c                                 b     c

为了消除歧义，传统递归下降解析器采用 **分层文法（Stratified Grammar）**。每一种优先级对应一个独立的非终结符与解析函数：

.. code-block:: text

   parseExpression()
     -> parseAssignment()
       -> parseConditional()
         -> parseLogicalOr()
           -> parseLogicalAnd()
             -> parseBitwiseOr()
               -> parseBitwiseXor()
                 -> parseBitwiseAnd()
                   -> parseEquality()
                     -> parseRelational()
                       -> parseShift()
                         -> parseAdditive()
                           -> parseMultiplicative()
                             -> parseUnary()
                               -> parsePostfix()
                                 -> parsePrimary()

分层文法在工业级编译器实现中暴露出两个核心缺陷：
1. **调用栈深度与指令开销**：解析一个基础原子项（如整数字面量 ``42``）时，解析器必须连续执行 15 层以上的函数压栈与跳转，产生大量栈帧分配、寄存器溢出与分支预测未命中。
2. **代码维护与扩展刚性**：新增一个运算符层级（如引入指数运算符 ``**`` 或空值合并运算符 ``??``）需要重写整条调用链上下游的所有函数签名与转发逻辑。

结合性对 AST 拓扑结构与求值依赖的约束
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

结合性（Associativity）决定同优先级运算符连续出现时的子树归属方向：

- **左结合（Left-Associativity）**：操作符从左至右组合操作数。表达式 ``a - b - c`` 构建为 ``Sub(Sub(a, b), c)``，左侧子树深度大于右侧。
- **右结合（Right-Associativity）**：操作符从右至左组合操作数。表达式 ``a = b = c`` 构建为 ``Assign(a, Assign(b, c))``，右侧子树深度大于左侧。

.. code-block:: text

   左结合 AST 拓扑 (如 a - b - c)         右结合 AST 拓扑 (如 a = b = c)
             [-]                                   [=]
            /   \                                 /   \
          [-]    c                               a    [=]
         /   \                                       /   \
        a     b                                     b     c

AST 拓扑决定了后续类型检查的中间值类型推导链与 IR 降低阶段的值依赖关系。必须明确：**AST 拓扑结构与运行时求值顺序（Evaluation Order）属于两层正交的语言规范约束**。AST 结构表达操作数的逻辑归属，而操作数求值的先后顺序（例如 C/C++ 中的未指定求值顺序，或 Java/Rust 中的严格从左到右求值）由中端 IR 生成阶段发射的具体指令序列强制保证。

Pratt 解析算法数学模型与结合力（Binding Power）
-----------------------------------------------

Vaughan Pratt 于 1973 年提出的自顶向下运算符优先级算法（Pratt Parsing / TDOP）通过将优先级与结合性映射为标量 **结合力（Binding Power）**，在一个扁平的单层主循环中完成了所有复杂表达式的解析。

结合力（Binding Power）形式化定义与数值序
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Pratt 算法为每个运算符分配两个结合力数值：
1. **左结合力 $LBP$（Left Binding Power）**：定义运算符争夺其左侧已解析表达式的吸引强度。
2. **右结合力 $RBP$（Right Binding Power）**：定义运算符争夺其右侧待解析表达式的吸引强度。

设优先级为正整数 $P \in \mathbb{N}^+$，数值越大代表绑定强度越高。结合力数值对结合性的表达形式如下：

.. list-table:: 运算符结合性与结合力二元组 $(LBP, RBP)$ 映射模型
   :widths: 20 22 28 30
   :header-rows: 1
   :class: tight-table

   * - 运算符类别
     - 结合性
     - 结合力配置规则
     - 算法行为特征
   * - 算术加减二元
     - 左结合 (Left)
     - $LBP = P, \quad RBP = P + 1$
     - 右侧递归阈值提升，阻止同优先级右侧运算符抢夺操作数
   * - 算术乘除二元
     - 左结合 (Left)
     - $LBP = P_{mul}, \quad RBP = P_{mul} + 1$
     - $P_{mul} > P_{add}$，自然跨越低优先级运算符边界
   * - 赋值运算符
     - 右结合 (Right)
     - $LBP = P_{assign}, \quad RBP = P_{assign}$
     - 右侧递归维持同级阈值，允许同优先级右侧运算符并入右子树
   * - 指数运算符 ``**``
     - 右结合 (Right)
     - $LBP = P_{pow}, \quad RBP = P_{pow}$
     - 连续指数运算 ``a ** b ** c`` 自然构造成 ``Pow(a, Pow(b, c))``
   * - 前缀单目运算符
     - 无前置左操作数
     - $RBP = P_{unary}$
     - 仅向下约束其右侧操作数的最低结合力
   * - 后缀单目运算符
     - 仅绑定左操作数
     - $LBP = P_{postfix}, \quad RBP = \infty$
     - 直接将左侧已有 AST 节点封装，不消耗右侧表达式

Nud 与 Led 概念抽象与职责划分
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Pratt 算法将 Token 在表达式中所处的位置及其语义动作严格划分为两类分发函数：

1. **Null Denotation（Nud / 前缀分发器）**：
   当 Token 出现在 **表达式起始位置**（即左侧当前不存在已解析的 AST 节点）时被调用。
   
   - 处理范围：整数字面量、浮点字面量、字符串、标识符变量、前缀一元运算符（``-``, ``+``, ``!``, ``~``, ``*``, ``&``）、定界包围符（分组括号 ``(``）。
   - 行为特征：主动消耗当前 Token，根据需要递归调用表达式解析引擎获取子操作数，最终产出一个基础 AST 节点。

2. **Left Denotation（Led / 中缀与后缀分发器）**：
   当 Token 出现在 **表达式中间或末尾**（即左侧已存在解析完毕的 AST 节点 ``left``）时被调用。
   
   - 处理范围：二元算术与逻辑运算符（``+``, ``-``, ``*``, ``/``, ``&&``, ``||``）、关系比较符（``==``, ``<``, ``>=``）、赋值运算符（``=``, ``+=``）、后缀运算符（``++``, ``--``）、调用与访问定界符（函数调用 ``(``、数组下标 ``[``、成员访问 ``.`` / ``->``）。
   - 行为特征：接收左侧 AST 节点 ``left`` 作为输入参数，消耗操作符 Token，按该操作符的 $RBP$ 递归解析右侧子表达式，最后将 ``left`` 与右侧节点组装为新的父节点返回。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                        Pratt 解析器双相分发拓扑                         |
   +-------------------------------------------------------------------------+
   |                                                                         |
   |   源码 Token 流:  [ - ]   [ a ]   [ * ]   [ b ]   [ + ]   [ c ]         |
   |                     |       |       |                                   |
   |   (起始位置无左节点) v       |       |                                   |
   |   触发 Nud( - ) ------+     |       |                                   |
   |       |               |     |       |                                   |
   |       v               v     |       |                                   |
   |   递归 Nud( a ) -> AST(a)   |       |                                   |
   |       |                     |       |                                   |
   |       +-> 生成 AST(Neg a) <-+       |                                   |
   |                 |                   |                                   |
   |                 | (已有左节点)       v                                   |
   |                 +------------> 触发 Led( * )                            |
   |                                     |                                   |
   |                                     v                                   |
   |                               递归获取右节点 AST(b)                     |
   |                                     |                                   |
   |                                     +-> 生成 AST(Mul (Neg a) b)         |
   +-------------------------------------------------------------------------+

Pratt 解析核心驱动循环与不等式截断定理
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Pratt 解析引擎的完整执行逻辑被提炼为一个带有最低结合力阈值约束的函数 ``parseExpression(min_bp)``。

.. code-block:: cpp

   // Pratt 解析核心驱动算法
   ASTExpr* Parser::parseExpression(uint8_t min_bp) {
       Token token = advance(); // 消费起始 Token
       
       // 1. 前缀阶段: 必须存在有效的 Nud 动作
       NudHandler nud = findNudHandler(token.Kind);
       if (!nud) {
           diagnoseUnexpectedToken(token);
           return createErrorExpr(token.Location);
       }
       
       ASTExpr *left = nud(token); // 构造初始左子树
       
       // 2. 中缀/后缀阶段: 循环检查后续 Token 的左结合力是否超过当前门槛
       while (min_bp < getLeftBindingPower(peek().Kind)) {
           Token opToken = advance(); // 消费中缀/后缀运算符
           
           LedHandler led = findLedHandler(opToken.Kind);
           assert(led && "Token with LBP > 0 must have an associated Led handler");
           
           // 执行 Led 动作并将返回的新节点置为下一次迭代的 left
           left = led(left, opToken);
       }
       
       return left;
   }

**不等式截断定理**：在 ``parseExpression(min_bp)`` 递归树中，当前解析上下文能够吞入右侧运算符 $op_{next}$ 的充要条件是：

$$	ext{LBP}(op_{next}) > 	ext{min\_bp}$$

当遇到 $LBP(op_{next}) \le 	ext{min\_bp}$ 的运算符时，循环条件被破坏，当前递归层级立即返回已构建的 ``left`` 节点，控制权交还给具有更低阈值要求的外层调用栈。

运算符号实例解析轨迹追踪：``a - b * c - d``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

以输入序列 ``a - b * c - d`` 为例，设定优先级常数：
- 减法 ``-``：$LBP = 10, \quad RBP = 11$（左结合）
- 乘法 ``*``：$LBP = 20, \quad RBP = 21$（左结合）

.. code-block:: text

   调用链状态追踪表:
   
   1. 进入 parseExpr(min_bp = 0)
      - 读取 'a' -> 触发 Nud(a) -> left = AST(a)
      - peek() 为 '-' (LBP = 10)。判断 0 < 10 成立，进入循环。
      - 消费 '-'，触发 Led(-, left = AST(a))
        - 计算 '-' 的 RBP = 11
        - 发起递归调用: right = parseExpr(min_bp = 11)
   
   2. 递归进入 parseExpr(min_bp = 11)
      - 读取 'b' -> 触发 Nud(b) -> left = AST(b)
      - peek() 为 '*' (LBP = 20)。判断 11 < 20 成立，进入循环。
      - 消费 '*'，触发 Led(*, left = AST(b))
        - 计算 '*' 的 RBP = 21
        - 发起递归调用: right = parseExpr(min_bp = 21)
   
   3. 递归进入 parseExpr(min_bp = 21)
      - 读取 'c' -> 触发 Nud(c) -> left = AST(c)
      - peek() 为第二个 '-' (LBP = 10)。判断 21 < 10 不成立，循环终止。
      - 返回 AST(c)
   
   4. 回到步骤 2 的 Led(*)
      - right = AST(c)
      - 构建节点: left = Mul(AST(b), AST(c))
      - peek() 为第二个 '-' (LBP = 10)。判断 11 < 10 不成立，循环终止。
      - 返回 Mul(AST(b), AST(c))
   
   5. 回到步骤 1 的 Led(-)
      - right = Mul(AST(b), AST(c))
      - 构建节点: left = Sub(AST(a), Mul(AST(b), AST(c)))
      - peek() 为第二个 '-' (LBP = 10)。判断 0 < 10 成立，继续外层循环！
      - 消费第二个 '-'，触发 Led(-, left = Sub(a, Mul(b, c)))
        - RBP = 11 -> right = parseExpr(11) 解析出 AST(d)
        - 构建节点: left = Sub(Sub(a, Mul(b, c)), d)
   
   6. 遇到 EOF (LBP = 0)，判断 0 < 0 不成立，顶层返回最终 AST。

统一分发架构与复杂语法形态建模
------------------------------

Pratt 算法的优势在于能够将非标准二元运算的各类复杂语法结构无缝收敛至统一的 Nud/Led 状态机中。

.. list-table:: 现代编程语言常见语法形态在 Pratt 模型中的映射规范
   :widths: 22 18 20 40
   :header-rows: 1
   :class: tight-table

   * - 语法形态
     - 触发槽位
     - 绑定阈值配置
     - 内部解析与 AST 构建动作
   * - 标识符 / 字面量
     - Nud
     - 无
     - 直接封装字面量或变量引用叶子节点返回
   * - 前缀单目 (``-x``, ``!x``)
     - Nud
     - $RBP = P_{unary}$
     - 消费单目 Token，递归调用 ``parseExpr(P_unary)`` 获得右操作数
   * - 后缀单目 (``x++``)
     - Led
     - $LBP = P_{post}$
     - 消费后缀 Token，直接组装 ``ASTUnaryExpr(Kind, left)`` 返回
   * - 数组下标 (``a[i]``)
     - Led
     - $LBP = P_{call}$
     - 消费 ``[``，递归执行 ``parseExpr(0)``，消费闭合 ``]``，组装 ``ASTIndexExpr``
   * - 函数调用 (``f(a, b)``)
     - Led
     - $LBP = P_{call}$
     - 消费 ``(``，循环解析逗号分隔实参列表，消费闭合 ``)``，组装 ``ASTCallExpr``
   * - 成员访问 (``a.b``)
     - Led
     - $LBP = P_{member}$
     - 消费 ``.``，强制消费标识符 Token，组装 ``ASTMemberAccessExpr``
   * - 三元条件 (``c ? t : e``)
     - Led
     - $LBP = P_{ternary}$
     - 消费 ``?``，以阈值 0 解析 ``then`` 分支，消费 ``:``，以 $RBP = P_{ternary} - 1$ 解析 ``else`` 分支
   * - 分组括号 (``(a + b)``)
     - Nud
     - 无
     - 消费 ``(``，递归执行 ``parseExpr(0)``，消费匹配的 ``)``，直接返回内部子树

三元条件运算符与嵌套优先级消除
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

三元条件运算符 ``condition ? then_expr : else_expr`` 具有两个运算符定界符及右结合特征：

.. code-block:: cpp

   // 三元条件运算符 Led 实现
   ASTExpr* Parser::parseTernaryLed(ASTExpr *condition, Token questionToken) {
       // 1. 中间 then 表达式处于独立子作用域，允许任意低优先级二元运算（阈值重置为 0）
       ASTExpr *thenExpr = parseExpression(0);
       
       // 2. 强制消费匹配的分隔符 ':'
       consume(TokenKind::Colon);
       
       // 3. 右结合性保障: else 分支采用弱于或等于当前三元优先级的 RBP
       // 确保 a ? b : c ? d : e 正确折叠为 a ? b : (c ? d : e)
       uint8_t rbp = getPrecedence(PrecedenceKind::Conditional) - 1;
       ASTExpr *elseExpr = parseExpression(rbp);
       
       return Arena.alloc<ASTConditionalExpr>(condition, thenExpr, elseExpr, questionToken.Location);
   }

运算符双重身份消除：前缀 vs 二元
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 C/C++/Rust 语法中，符号 ``-``, ``+``, ``*``, ``&`` 具有多义性。例如 ``*`` 既可以表示指针解引用（前缀单目），也可以表示乘法（中缀二元）：

.. code-block:: text

   源码上下文 A:  *ptr = 10;          -> 出现在表达式起始 -> 触发 Nud(Star) -> 指针解引用
   源码上下文 B:  int val = a * b;    -> 出现在左节点后   -> 触发 Led(Star) -> 算术乘法

在 Pratt 解析器中，双重身份的消歧无需回溯或词法 Hack。**分发引擎依据调用时机自动裁决**：
- 在主循环起始处调用，当前上下文必为前缀阶段，直接命中该 TokenKind 注册的 Nud 处理器。
- 在循环内部调用，当前上下文必存在有效 ``left`` 节点，直接命中该 TokenKind 注册的 Led 处理器。

工业级 Pratt 解析器 C++ 物理架构与高性能实现
-------------------------------------------

在工业级编译器（如 Clang、V8、Swift、Rustc）中，Pratt 解析器通常结合查找表（Lookup Table）与 Arena 内存池以达到极致性能。

数据结构拓扑与优先级阶元定义
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: cpp

   #pragma once
   #include <cstdint>
   #include <cassert>
   #include <span>
   #include <vector>

   // 运算符优先级分层定义 (数值单调递增)
   enum class Precedence : uint8_t {
       Lowest = 0,
       Assignment,    // = += -= (右结合)
       Conditional,   // ? :     (右结合)
       LogicalOr,     // ||
       LogicalAnd,    // &&
       BitwiseOr,     // |
       BitwiseXor,    // ^
       BitwiseAnd,    // &
       Equality,      // == !=
       Relational,    // < <= > >=
       Shift,         // << >>
       Additive,      // + -
       Multiplicative,// * / %
       UnaryPrefix,   // ++ -- + - ! ~ * & (前缀)
       Postfix,       // ++ -- (后缀)
       CallIndexMember// () [] . ->
   };

   // 运算符规则描述元数据表项
   struct OperatorRule {
       using NudFunc = ASTExpr* (*)(Parser&, Token);
       using LedFunc = ASTExpr* (*)(Parser&, ASTExpr*, Token);

       NudFunc Nud = nullptr;
       LedFunc Led = nullptr;
       uint8_t LBP = 0; // Left Binding Power
   };

核心解析驱动引擎与表驱动分发
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: cpp

   class Parser {
   public:
       explicit Parser(std::span<const Token> tokens, BumpAllocator &arena)
           : Tokens(tokens), Cursor(0), Arena(arena) {
           initializeOperatorTable();
       }

       // 核心入口: 基于结合力阈值的自顶向下表达式解析
       ASTExpr* parseExpression(uint8_t minBindingPower = 0) {
           if (isAtEnd()) {
               diagnoseUnexpectedEof();
               return nullptr;
           }

           // 1. 前缀 Nud 分发阶段
           Token prefixTok = advance();
           const OperatorRule &prefixRule = Rules[static_cast<size_t>(prefixTok.Kind)];
           
           if (!prefixRule.Nud) {
               diagnoseExpectedExpression(prefixTok);
               return Arena.alloc<ASTErrorExpr>(prefixTok.Location);
           }

           ASTExpr *left = prefixRule.Nud(*this, prefixTok);

           // 2. 中缀/后缀 Led 结合力驱动主循环
           while (!isAtEnd()) {
               Token nextTok = peek();
               const OperatorRule &infixRule = Rules[static_cast<size_t>(nextTok.Kind)];
               
               // 当后续操作符的左结合力不大于当前门槛时，截断递归并收敛当前子树
               if (infixRule.LBP <= minBindingPower) {
                   break;
               }

               Token opTok = advance();
               assert(infixRule.Led && "Grammar error: Token with LBP > 0 must provide a Led handler");
               left = infixRule.Led(*this, left, opTok);
           }

           return left;
       }

       Token advance() { return Tokens[Cursor++]; }
       Token peek() const { return Tokens[Cursor]; }
       bool isAtEnd() const { return Cursor >= Tokens.size() || peek().Kind == TokenKind::Eof; }
       
       Token consume(TokenKind expected) {
           if (peek().Kind == expected) return advance();
           diagnoseMissingToken(expected, peek().Location);
           return Token{expected, peek().Location, {}};
       }

       BumpAllocator& getArena() { return Arena; }

   private:
       std::span<const Token> Tokens;
       size_t Cursor;
       BumpAllocator &Arena;
       static constexpr size_t MaxTokenKinds = 256;
       OperatorRule Rules[MaxTokenKinds];

       void initializeOperatorTable();
       void registerRule(TokenKind kind, OperatorRule::NudFunc nud, OperatorRule::LedFunc led, Precedence prec);
       void diagnoseUnexpectedEof();
       void diagnoseExpectedExpression(Token tok);
       void diagnoseMissingToken(TokenKind expected, SourceLocation loc);
   };

典型 Nud / Led 静态动作函数实现
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: cpp

   // 1. 原子字面量与标识符 (Nud)
   static ASTExpr* parsePrimaryNud(Parser &P, Token tok) {
       switch (tok.Kind) {
           case TokenKind::IntLiteral:
               return P.getArena().alloc<ASTIntLiteral>(tok.Payload.IntValue, tok.Location);
           case TokenKind::Identifier:
               return P.getArena().alloc<ASTIdentifierExpr>(tok.Payload.IdentInfo, tok.Location);
           default:
               return nullptr;
       }
   }

   // 2. 前缀一元运算 (Nud): 如 -a, !flag, *ptr
   static ASTExpr* parseUnaryPrefixNud(Parser &P, Token tok) {
       uint8_t rbp = static_cast<uint8_t>(Precedence::UnaryPrefix);
       ASTExpr *operand = P.parseExpression(rbp);
       return P.getArena().alloc<ASTUnaryExpr>(tok.Kind, operand, UnaryPosition::Prefix, tok.Location);
   }

   // 3. 分组括号 (Nud): (expr)
   static ASTExpr* parseGroupParenNud(Parser &P, Token tok) {
       ASTExpr *inner = P.parseExpression(0);
       P.consume(TokenKind::RParen);
       return inner;
   }

   // 4. 左结合标准二元运算 (Led): 如 a + b, a * b
   static ASTExpr* parseBinaryLeftAssocLed(Parser &P, ASTExpr *left, Token tok) {
       uint8_t lbp = static_cast<uint8_t>(getOperatorPrecedence(tok.Kind));
       // 左结合核心: RBP = LBP + 1, 阻止右侧同级运算符并入当前子树
       uint8_t rbp = lbp + 1;
       ASTExpr *right = P.parseExpression(rbp);
       return P.getArena().alloc<ASTBinaryExpr>(tok.Kind, left, right, tok.Location);
   }

   // 5. 右结合赋值运算 (Led): 如 a = b = c
   static ASTExpr* parseAssignmentLed(Parser &P, ASTExpr *left, Token tok) {
       uint8_t lbp = static_cast<uint8_t>(Precedence::Assignment);
       // 右结合核心: RBP = LBP, 允许右侧同级赋值运算符继续并入右子树
       uint8_t rbp = lbp;
       ASTExpr *right = P.parseExpression(rbp);
       return P.getArena().alloc<ASTAssignmentExpr>(tok.Kind, left, right, tok.Location);
   }

   // 6. 函数调用运算符 (Led): f(x, y)
   static ASTExpr* parseFunctionCallLed(Parser &P, ASTExpr *callee, Token tok) {
       std::vector<ASTExpr*> args;
       if (P.peek().Kind != TokenKind::RParen) {
           do {
               args.push_back(P.parseExpression(0));
           } while (P.peek().Kind == TokenKind::Comma && (P.advance(), true));
       }
       SourceLocation closeLoc = P.consume(TokenKind::RParen).Location;
       return P.getArena().alloc<ASTCallExpr>(callee, std::move(args), tok.Location, closeLoc);
   }

   // 7. 数组下标访问 (Led): arr[index]
   static ASTExpr* parseArrayIndexLed(Parser &P, ASTExpr *base, Token tok) {
       ASTExpr *index = P.parseExpression(0);
       SourceLocation closeLoc = P.consume(TokenKind::RBracket).Location;
       return P.getArena().alloc<ASTIndexExpr>(base, index, tok.Location, closeLoc);
   }

   // 8. 成员访问 (Led): obj.field
   static ASTExpr* parseMemberAccessLed(Parser &P, ASTExpr *base, Token tok) {
       Token fieldTok = P.consume(TokenKind::Identifier);
       return P.getArena().alloc<ASTMemberExpr>(base, fieldTok.Payload.IdentInfo, tok.Location, fieldTok.Location);
   }

调用栈扁平化与性能度量分析
~~~~~~~~~~~~~~~~~~~~~~~~~

Pratt 解析算法在硬件层面的性能优势来源于其将同优先级的左结合嵌套转换为了循环单调步进：

1. **调用栈开销抑制**：在处理连续同级算术链 ``a + b + c + d + ... + z``（长度为 $N$）时，分层递归下降解析器会在 ``parseAdditive()`` 处递归展开产生深度为 $O(N)$ 的函数调用栈。Pratt 解析器在 ``min_bp = 0`` 的主循环内单层迭代运行，调用栈深度恒定为 $O(1)$。
2. **函数内联与分支预测友好**：表驱动将分发收敛至静态数组索引 `Rules[kind]`，现代 CPU 能够高效预测紧凑主循环的跳转边界，极大降低了指令 Cache Miss 率。

.. list-table:: 递归下降分层解析 vs Pratt 结合力解析工程性能对比
   :widths: 22 28 28 22
   :header-rows: 1
   :class: tight-table

   * - 评估指标
     - 经典分层递归下降
     - Pratt TDOP 结合力解析
     - 性能差异成因
   * - 解析单字面量栈深度
     - 15 ~ 25 层栈帧
     - 1 层栈帧
     - 省略无匹配分层的逐级空转调用
   * - 连续长表达式栈消耗
     - $O(N)$ 深度（受左递归写法限制）
     - $O(	ext{嵌套层级})$
     - 主循环迭代扁平化消费同级 Token
   * - 引入新操作符维护成本
     - 修改多层产生式与函数调用链
     - 仅在配置表中增加一行注册项
     - 规则表与解析驱动逻辑完全解耦
   * - 内存碎片与分配开销
     - 节点分配散落在各层解析函数中
     - 统一由 Arena 内存池单调分配
     - 连续线性地址分配提升缓存命中率

语法错误恢复与边界异常收敛
--------------------------

表达式是用户编写代码时语法错误最密集的高发区。Pratt 解析器必须在面对语法残缺时保证算法收敛与诊断精准度。

.. code-block:: text

   典型表达式异常场景:
   1. 连续二元操作符 (缺失中间操作数):   a + * b
   2. 悬挂二元操作符 (结尾缺失操作数):   let x = a + ;
   3. 定界符不匹配或提前截断:           foo(a, b * (c + d);

缺失操作数的同步与合成修复
~~~~~~~~~~~~~~~~~~~~~~~~~

当解析器在操作符后期待操作数时，若后续 Token 无法触发有效的 Nud 动作（如输入 ``a + * b`` 中的 ``*``）：

1. **发射就地诊断**：精确指出 ``*`` 位置缺失合法的左操作数或前缀表达式。
2. **插入合成错误节点（Synthetic Error Node）**：分配一个携带错误标记的 ``ASTErrorExpr`` 作为当前二元运算的右操作数，使父级 ``BinaryExpr(+)`` 结构得以闭合。
3. **禁止级联报错**：将合成错误节点的类型标记为 `Type::Error`，在后续语义分析中静默抑制与该节点相关的类型不匹配告警。

.. code-block:: cpp

   // 缺失操作数容错处理实现
   ASTExpr* Parser::parseBinaryLeftAssocLed(Parser &P, ASTExpr *left, Token tok) {
       uint8_t lbp = static_cast<uint8_t>(getOperatorPrecedence(tok.Kind));
       uint8_t rbp = lbp + 1;
       
       // 检查紧随 Token 是否合法
       if (P.isAtStatementEnd() || P.peek().Kind == TokenKind::RBrace) {
           P.diagnoseExpectedRightOperand(tok);
           ASTExpr *errNode = P.getArena().alloc<ASTErrorExpr>(tok.Location);
           return P.getArena().alloc<ASTBinaryExpr>(tok.Kind, left, errNode, tok.Location);
       }
       
       ASTExpr *right = P.parseExpression(rbp);
       return P.getArena().alloc<ASTBinaryExpr>(tok.Kind, left, right, tok.Location);
   }

未闭合定界符与优先级泄漏隔离
~~~~~~~~~~~~~~~~~~~~~~~~~~~

在解析包含包围定界符的复杂表达式（如 ``(a + b`` 或 ``arr[i + 1``）时，若右侧定界符缺失：

- 定界符 Nud/Led 处理器在进入内部递归时统一将 `min_bp` 强制置为 0，防止外层结合力泄漏至括号内部。
- 内部表达式解析完成后，调用 ``consume()`` 验证闭合符号。若发现后续为分号 ``;`` 或语句结束关键字，立即停止匹配，向诊断引擎注册未闭合范围，并就地返回当前已构建的内部子树，防止解析器越界吞噬后续独立语句。

小结与下章导读
--------------

本章系统解构了现代编译器前端处理表达式优先级与结合性的核心技术：

1. **表达式二义性本质**：阐明了中缀记号缺少定界符导致的文法歧义，剖析了经典分层递归下降解析器在调用栈深度与维护扩展性上的工程缺陷。
2. **Pratt 算法数学模型**：形式化定义了结合力（Binding Power, $LBP$ 与 $RBP$）及其对左结合（$RBP = LBP + 1$）与右结合（$RBP = LBP$）的数值表达，确立了 $LBP \le min\_bp$ 的不等式递归截断定理。
3. **Nud 与 Led 状态机抽象**：解构了前缀分发器 Nud 与中缀/后缀分发器 Led 的统一职责划分，消除了多义性运算符（如一元负号与二元减法、指针解引用与乘法）的判定歧义。
4. **复杂语法结构收敛**：展示了三元条件运算符、数组下标、函数调用与成员访问向 Pratt 模型的无缝映射。
5. **高性能物理实现**：构建了基于表驱动与 Arena 内存池的工业级 C++ Pratt 解析架构，通过循环扁平化将连续运算栈消耗从 $O(N)$ 压降至 $O(1)$。
6. **错误恢复与诊断**：确立了缺失操作数合成节点插入与定界符隔离恢复机制。

在语法分析器成功将复杂的声明、语句与表达式构建为内存中的语法树后，编译器需要对整棵树的拓扑形态进行标准化规范，并在遭遇严重语法错乱时实施系统级恢复。在下一章 **AST 节点拓扑与语法错误恢复：CST 向 AST 简化、Panic Mode 恐慌恢复与同步 Token 探测（05_ast_topology_and_parser_error_recovery.rst）** 中，我们将深入剖析具体语法树（CST）向抽象语法树（AST）的有损/无损压缩折叠、紧凑内存布局设计、Panic Mode 恐慌恢复算法，以及基于同步 Token 集合（Synchronization Set）的数据流恢复策略。
