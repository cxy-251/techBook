================================================================================
AST 节点拓扑与语法错误恢复：CST 向 AST 简化、Panic Mode 恐慌恢复与同步 Token 探测
================================================================================

.. note:: 前置背景与上下文承接
   在第 2 模块第 4 节中，编译器前端确立了基于 Vaughan Pratt 算法的自顶向下运算符优先级解析体系，通过左结合力（$LBP$）与右结合力（$RBP$）数值约束及 Nud/Led 状态机消除了复杂表达式的二义性文法嵌套调用开销。然而，解析器在处理整段源码文本时，不仅需要将线性的 Token 流转换为具备明确层级关系的内存语法树，还必须应对现实场景中频繁出现的语法残缺与非法输入。本章系统解构具体语法树（Concrete Syntax Tree, CST）向抽象语法树（Abstract Syntax Tree, AST）的拓扑映射与有损/无损压缩折叠机制、高缓存局部性的 Arena 扁平内存布局、语法错误的结构断点状态机建模、单 Token 缺失合成与冗余剔除的局部恢复策略、基于多级同步 Token 集合（Resynchronization Sets）与括号平衡跟踪的 Panic Mode 恐慌恢复算法，以及工业级 C++ 语法容错解析引擎的完整实现。

CST 与 AST 的拓扑映射与有损/无损压缩折叠
---------------------------------------

词法分析器产生的 Token 序列是一维平铺的物理字节切片，语法分析器的首要任务是将这种时序关系转换为反映计算依赖的树状拓扑。在编译器理论与前端工程中，存在两种形态各异的语法树：具体语法树（CST，亦称 Parse Tree）与抽象语法树（AST）。

具体语法树（CST）的文法推导全貌
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

CST 是形式文法推导过程的严格物理映射。CST 中的每一个内部节点对应文法产生式中的一个非终结符（Non-terminal），每一个叶子节点对应输入的终结符 Token（包括括号、逗号、分号及空白注释等物理痕迹）。

以表达式文法规则推导算式 ``(base + tax) * rate`` 为例：

.. code-block:: text

   文法产生式规则:
   E  -> T (("+" | "-") T)*
   T  -> F (("*" | "/") F)*
   F  -> IDENT | NUMBER | "(" E ")"

其在 CST 中的完整推导展开拓扑呈现如下形态：

.. code-block:: text

                     [ Expression (E) ]
                             |
                      [ Term (T) ]
                      /    |    \
                     /     |     \
          [ Factor (F) ] Token[*] [ Factor (F) ]
            /   |    \                   |
      Token[(] [E]   Token[)]       Token[IDENT: rate]
              / | \
             /  |  \
           [T] Token[+] [T]
            |            |
           [F]          [F]
            |            |
     Token[IDENT: base] Token[IDENT: tax]

CST 的核心属性在于其保留了文法推导的完整证明链条。在语法调试、代码格式化工具（Code Formatter）以及需要对源码进行像素级还原的重构引擎中，CST 提供了完整的语法证据。但在中端类型检查、数据流分析与 IR 生成阶段，CST 存在大量结构冗余：
1. **纯推导过渡节点膨胀**：节点链条 ``E -> T -> F -> IDENT`` 仅用于表达运算优先级，在内存中引入了 4 次指针间接寻址与 4 个独立的堆内存分配开销。
2. **表面标点冗余**：分组括号 ``(`` 与 ``)`` 仅用于干预解析优先级，其从属关系在树形分支连接后已完全确定，保留独立的括号节点增加了后续遍历的匹配负担。

抽象语法树（AST）的结构提炼与语义聚焦
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

AST 抽离了仅服务于解析算法的分层细节与无语义表面标点，直接将节点映射为语言规范中的核心语义实体（表达式、语句、声明、类型描述）。

将上述 CST 经结构折叠转换为 AST 后的拓扑形态如下：

.. code-block:: text

             [ ASTBinaryExpr (Op: Mul) ]
                     /         \
                    /           \
     [ ASTBinaryExpr (Op: Add) ] [ ASTDeclRefExpr (Name: rate) ]
             /          \
            /            \
   [ ASTDeclRefExpr ]  [ ASTDeclRefExpr ]
     (Name: base)        (Name: tax)

.. list-table:: 具体语法树 (CST) 与抽象语法树 (AST) 的物理特征对比
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 架构维度
     - 具体语法树 (CST / Parse Tree)
     - 抽象语法树 (AST)
   * - 节点类型构成
     - 文法非终结符 + 所有终结符 Token（含标点与空白）
     - 强类型语言结构（BinaryExpr, CallExpr, IfStmt 等）
   * - 内存占用规模
     - 极大（通常达到源码体积的 15~30 倍）
     - 紧凑（通常为源码体积的 3~8 倍）
     - 拓扑层级深度
     - 深度大，受文法分层产生式链条直接拉长
     - 扁平，仅反映真实的运算与控制从属关系
   * - 下游消费场景
     - 源码精准格式化、IDE 语法高亮、增量重构
     - 符号表解析、类型检查、常量折叠、IR 降解
   * - 语法糖呈现
     - 保留原始编写形态（如 ``a += 1``）
     - 保留特化节点或直接归一化展开（Normalization）

现代无损语法树架构（Green/Red Tree）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在兼顾编译器高性能编译与 IDE 语言服务器协议（LSP）无损源码重构的需求下，现代编译器基础设施（如 C# Roslyn、Swift libSyntax、Rust rust-analyzer）引入了分层的 Green/Red Tree 架构。

.. code-block:: text

   +-----------------------------------------------------------------------+
   |                       Green/Red Tree 分层双模架构                     |
   +-----------------------------------------------------------------------+
   |                                                                       |
   |   [ Green Tree (底层不可变纯值拓扑) ]                                 |
   |   - 纯粹不可变数据结构 (Immutable)                                    |
   |   - 仅记录自身相对宽度 (TextLength) 与 TokenKind                      |
   |   - 无父节点指针，相同子树全局共享缓存 (Structural Sharing)           |
   |                                                                       |
   |   [ Red Tree (上层门面代理拓扑) ]                                     |
   |   - 按需延迟计算生成的轻量包装门面 (Facade Proxy)                     |
   |   - 持有指向 Green Node 的指针 + 父节点指针 + 绝对 SourceOffset       |
   |   - 为语义分析与 IDE 提供便捷的双向遍历视图                           |
   |                                                                       |
   +-----------------------------------------------------------------------+

Green Tree 作为底层不可变节点，仅记录节点的相对宽度与子节点列表，完全剥离绝对位置偏移，使得相同的语法子树可以在内存中跨文件共享。Red Tree 作为只读包装层，在遍历过程中按需派生绝对物理坐标与父节点引用，消除了增量重新解析时全树内存重建的性能损耗。

AST 节点内存物理拓扑与高性能存储架构
-----------------------------------

在工业级编译器（如 Clang、Rustc）中，大型源码工程可能产生数百万甚至上千万个 AST 节点。AST 内存布局的设计直接决定了编译器的内存峰值与 Cache 命中率。

经典面向对象指针树的物理缺陷
~~~~~~~~~~~~~~~~~~~~~~~~~~~

朴素的 AST 实现通常采用 C++ 虚函数继承体系：

.. code-block:: cpp

   // 传统反模式: 离散堆分配虚函数多态节点
   class ASTNode {
   public:
       virtual ~ASTNode() = default;
       virtual void accept(ASTVisitor &visitor) = 0;
       SourceLocation Loc;
   };

   class BinaryExpr : public ASTNode {
       std::unique_ptr<ASTNode> Left;
       std::unique_ptr<ASTNode> Right;
       OperatorKind Op;
   };

该设计在硬件执行层面存在三大瓶颈：
1. **虚表指针（vptr）内存膨胀**：每个 64 位平台上的对象头部均包含 8 字节的虚表指针。在大量微小节点（如字面量、变量引用）中，元数据开销超过有效载荷。
2. **堆碎片与动态分配延迟**：通过标准 ``malloc`` / ``new`` 逐个分配节点导致内存空间高度离散，系统调用开销显著。
3. **缓存行颠簸（Cache Thrashing）**：遍历树时，子节点指针指向不连续的堆地址，导致 CPU L1/L2 Data Cache 频繁发生 Cache Miss。

Arena 线性连续内存池（Bump Allocator）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

现代编译器全面采用基于单调指针递增的 Arena 内存池管理 AST 对象的生命周期。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                        Arena 线性块分配拓扑                             |
   +-------------------------------------------------------------------------+
   |                                                                         |
   |   Chunk 0 (4MB Page)                                                    |
   |   [ Node 1 ][ Node 2 ][ Node 3 ][ Node 4 ] -> [ Free Space... ]         |
   |   ^                                       ^                   ^         |
   |   ChunkBase                               AllocPtr            ChunkEnd  |
   |                                                                         |
   |   分配操作: ptr = AllocPtr; AllocPtr += sizeof(T); return ptr;          |
   |   析构操作: 编译单元解析完毕后直接释放整块 Chunk 链表，析构开销为 O(1)   |
   |                                                                         |
   +-------------------------------------------------------------------------+

Arena 分配机制将单个节点的分配时间复杂度压降至 $O(1)$ 指针加法，同时确保在时序上相邻创建的父子 AST 节点在物理内存地址上保持连续，最大化利用 CPU 缓存行（Cache Line）预取。

尾部平铺变长节点（Trailing Objects 模式）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于包含可变数量子节点的结构（如函数调用实参列表 ``CallExpr``、复合语句块 ``CompoundStmt``），传统做法是在节点内部持有 ``std::vector<ASTNode*>``，这引入了二次指针跳转与额外的控制块开销。

Clang 采用的 Trailing Objects 模式在单一连续内存块中同时分配节点头结构与其子对象数组：

.. code-block:: cpp

   // 内存物理布局: [ CallExpr 头部结构体 ] [ Arg0 指针 ] [ Arg1 指针 ] ... [ ArgN 指针 ]
   class alignas(void*) CallExpr final : public ASTExpr {
       ASTExpr *Callee;
       unsigned NumArgs;
       SourceLocation RParenLoc;

       CallExpr(ASTExpr *callee, std::span<ASTExpr*> args, SourceLocation rParenLoc)
           : ASTExpr(NodeKind::CallExpr), Callee(callee), NumArgs(args.size()), RParenLoc(rParenLoc) {
           // 将变长参数直接拷贝至结构体尾部连续内存中
           ASTExpr **trailingArgs = getTrailingArgs();
           std::copy(args.begin(), args.end(), trailingArgs);
       }

   public:
       static CallExpr* create(BumpAllocator &arena, ASTExpr *callee, std::span<ASTExpr*> args, SourceLocation rParenLoc) {
           size_t totalBytes = sizeof(CallExpr) + sizeof(ASTExpr*) * args.size();
           void *mem = arena.allocate(totalBytes, alignof(CallExpr));
           return new (mem) CallExpr(callee, args, rParenLoc);
       }

       ASTExpr** getTrailingArgs() {
           return reinterpret_cast<ASTExpr**>(reinterpret_cast<char*>(this) + sizeof(CallExpr));
       }
   };

该布局使得整个调用表达式节点及其所有参数指针位于同一个物理内存切片内，减少了分配次数并提升了遍历吞吐量。

语法错误作为结构断点与状态机建模
--------------------------------

语法错误（Syntax Error）发生在解析器所处的当前文法状态下，下一个输入的 Lookahead Token 无法命中任何合法的产生式转换规则。解析器必须将语法错误视为语法构建流程中的 **结构断点（Structural Breakpoint）**。

结构断点的四维事实证据元组
~~~~~~~~~~~~~~~~~~~~~~~~~

为了构建精确的编译器前端诊断与恢复系统，发生语法断点时必须捕获四维事实元组：

$$\mathcal{D} = \langle \mathcal{P}_{	ext{prefix}}, \mathcal{S}_{	ext{grammar}}, \mathcal{T}_{	ext{expected}}, 	au_{	ext{actual}} \rangle$$

.. list-table:: 语法断点四维事实元组构成与工程职责
   :widths: 20 25 25 30
   :header-rows: 1
   :class: tight-table

   * - 证据要素
     - 物理取值含义
     - 提取来源
     - 诊断与恢复职责
   * - 已确认前缀 $\mathcal{P}_{	ext{prefix}}$
     - 已成功构建的语法节点链
     - 解析器调用栈与 AST 临时树
     - 确定当前断点所处的语法作用域上下文
   * - 文法状态 $\mathcal{S}_{	ext{grammar}}$
     - 正在执行的产生式与匹配点
     - 当前正在执行的递归下降解析函数
     - 决定当前位置所需闭合的结构层级
   * - 预期符号集 $\mathcal{T}_{	ext{expected}}$
     - 当前规则允许出现的合法 Token 集合
     - 文法规则的 $FIRST$ 与 $FOLLOW$ 集
     - 生成人类可读的高质量错误提示信息
   * - 实际符号 $	au_{	ext{actual}}$
     - 词法扫描器返回的非法 Token
     - 解析器当前的 Lookahead 缓冲区
     - 提供直接出错物理行、列、偏移量坐标

错误恢复的核心工程目标
~~~~~~~~~~~~~~~~~~~~~

当语法断点触发时，解析器禁止直接崩溃退出（如调用 ``exit()``），必须执行受控恢复算法，达成以下工程目标：
1. **AST 全局拓扑健全性**：产出一棵结构闭合、指针非空的语法树，确保类型检查、作用域分析与 IDE 语法索引能够无异常遍历整棵树。
2. **级联误报抑制（Cascade Suppression）**：一次孤立的源码书写错误（如漏写一个分号）仅触发 1 条精准错误报告，禁止产生因状态机失步导致的成百上千条次生衍生伪错误。
3. **最大化有效结构保留**：尽可能多地解析源码中的合法函数、类与语句块，不因局部错误抛弃整文件或大作用域的分析价值。

局部错误恢复与合成节点策略
--------------------------

局部错误恢复（Local Error Recovery）在不改变外层解析状态的前提下，通过对当前 Token 流执行单步微调使当前产生式顺利闭合。

单 Token 缺失合成（Single Token Insertion）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当解析器期待终结符 $	au_{	ext{wanted}}$，而当前读入的实际 Token $	au_{	ext{actual}}$ 无法匹配该终结符，但 $	au_{	ext{actual}}$ 属于 $	au_{	ext{wanted}}$ 紧随其后的后续产生式合法起始符（$FIRST$ 集合）时，解析器采用合成插入策略。

典型场景：函数参数列表缺少右括号 ``)``，紧随其后直接出现函数体起始花括号 ``{``：

.. code-block:: rust

   // 源码输入: 缺少闭合右括号
   fn calculate(x: i32, y: i32 {
       return x + y;
   }

.. code-block:: text

   解析器执行链路:
   1. 解析 ParamList -> 匹配 "x: i32, y: i32"
   2. 期待 TokenKind::RParen -> 当前 Lookahead 为 TokenKind::LBrace
   3. 判定 LBrace 为 Block 的起始终结符
   4. 触发局部恢复:
      - 向诊断引擎注册 Error: "expected ')' after parameter list, found '{'"
      - 附带 Fix-it Hint: 在列偏移处建议插入 ')'
      - 构造 SyntheticToken(TokenKind::RParen) 并挂入 AST
   5. 解析器直接进入 parseBlock() 正常解析函数体

单 Token 冗余剔除（Single Token Deletion）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当当前 Token $	au_{	ext{actual}}$ 非法，但前瞻一位的 Token $	au_{	ext{next}}$ 正好等于预期的 $	au_{	ext{wanted}}$ 时，解析器判定当前 Token 为用户误输入的噪音字符，直接将其消耗丢弃。

典型场景：表达式中误输入多余的分号或操作符 ``let x = a +; b;``：

.. code-block:: cpp

   // 单 Token 判定与消耗算法
   Token Parser::expectOrRecover(TokenKind expected) {
       if (peek().Kind == expected) {
           return advance();
       }

       // 策略 A: 单 Token 冗余剔除 (Single Token Deletion)
       if (peekAhead(1).Kind == expected) {
           diagnoseUnexpectedToken(peek());
           advance(); // 吞掉并丢弃当前非法 Token
           return advance(); // 消费原本期待的 Token
       }

       // 策略 B: 单 Token 缺失合成 (Single Token Insertion)
       if (isFollowsExpected(expected, peek().Kind)) {
           diagnoseMissingToken(expected, peek().Location);
           return SyntheticToken(expected, peek().Location);
       }

       // 局部恢复失败，触发深层 Panic Mode 恢复
       return triggerPanicMode(expected);
   }

合成错误节点与 Poison 机制
~~~~~~~~~~~~~~~~~~~~~~~~~

在无法完成简单 Token 补齐的表达式内部，解析器必须在 AST 中插入显式的合成错误节点（如 ``ASTErrorExpr`` 或 ``ASTErrorStmt``），并将其数据类型标记为 Poison/Error 类型。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                        Poison 错误类型静默抑制拓扑                      |
   +-------------------------------------------------------------------------+
   |                                                                         |
   |   源码输入:  let z = x + ;                                              |
   |                                                                         |
   |   AST 结构:                                                             |
   |             [ ASTVarDecl: z ]                                           |
   |                     |                                                   |
   |          [ ASTBinaryExpr (Op: +) ]                                      |
   |                 /         \                                             |
   |     [ ASTDeclRefExpr: x ] [ ASTErrorExpr (PoisonType) ]                 |
   |                                                                         |
   |   类型检查阶段执行逻辑:                                                 |
   |   - TypeCheck(BinaryExpr):                                              |
   |       LeftType = Type(x) -> i32                                         |
   |       RightType = Type(ASTErrorExpr) -> PoisonType                      |
   |       判定: 存在操作数为 PoisonType 时，直接返回 PoisonType，不输出类型报错  |
   |                                                                         |
   +-------------------------------------------------------------------------+

Poison 机制确保了语法阶段已经报错的碎片不会在后续的语义分析、重载决议与类型推导中引发二次雪崩式报错。

Panic Mode 恐慌模式与同步 Token 集合
------------------------------------

当语法错乱跨越多个 Token，局部插入或删除无法使解析器恢复稳定状态时，解析器进入 **恐慌模式（Panic Mode）**。

Panic Mode 的运行机制包括：丢弃当前输入流中的 Token，直到遇到具有明确结构定界意义的 **同步 Token（Synchronization Token）**，随后强行平复调用栈，重新启动解析。

同步 Token 集合（Resynchronization Sets）的层次化构建
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

同步 Token 集合不是全编译器固定的单一集合，而是随解析器调用栈深度动态变化的拓扑集合：

$$\mathcal{S}_{	ext{sync}} = \mathcal{S}_{	ext{current\_rule}} \cup \mathcal{S}_{	ext{enclosing\_scopes}}$$

.. list-table:: 编译器各文法层级的同步 Token 集合设计规范
   :widths: 22 28 50
   :header-rows: 1
   :class: tight-table

   * - 语法分析层级
     - 核心同步 Token 集合
     - 恢复动作与结构裁决
   * - 表达式层级 (Expression)
     - ``;``, ``)``, ``]``, ``}``, ``,``
     - 截断当前表达式并返回 ``ASTErrorExpr``，将控制权交还给包含该表达式的语句
   * - 语句层级 (Statement)
     - ``;``, ``}``, ``let``, ``if``, ``while``, ``return``
     - 消耗至 ``;`` 之后，或停在下一条语句的起始关键字前，重新开始解析下一语句
   * - 结构体/类体 (Class/Struct)
     - ``}``, ``pub``, ``fn``, ``var``, ``type``
     - 消耗至下一个成员声明引导词，保持外层类结构的完整性
   * - 顶层编译单元 (Translation Unit)
     - ``fn``, ``struct``, ``enum``, ``import``, ``EOF``
     - 跳过损坏的整段声明，同步至下一个顶级定义项起点

括号平衡跟踪（Bracket Balance Tracking）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 Panic Mode 消耗 Token 的循环中，若无条件扫描同步 Token，遇到嵌套代码块中的分号或关键字时可能发生提前截断，导致外层作用域的作用域定界符失衡。

现代解析器在执行同步跳过时，必须内置基于物理计数器的括号平衡状态机：

.. code-block:: cpp

   // 带括号平衡状态跟踪的 Panic 模式跳过算法
   void Parser::skipUntil(const TokenSet &syncSet) {
       int parenParenDepth = 0;   // () 深度
       int bracketDepth = 0;      // [] 深度
       int braceDepth = 0;        // {} 深度

       while (!isAtEnd()) {
           Token current = peek();

           // 1. 深度追踪
           switch (current.Kind) {
               case TokenKind::LParen:   parenParenDepth++; break;
               case TokenKind::RParen:   if (parenParenDepth > 0) parenParenDepth--; break;
               case TokenKind::LBracket: bracketDepth++; break;
               case TokenKind::RBracket: if (bracketDepth > 0) bracketDepth--; break;
               case TokenKind::LBrace:   braceDepth++; break;
               case TokenKind::RBrace:
                   if (braceDepth > 0) {
                       braceDepth--;
                   } else {
                       // 遇到当前层级未匹配的外层闭合花括号，必须立即终止跳过，防止吞噬外层作用域
                       return;
                   }
                   break;
               default:
                   break;
           }

           // 2. 仅在同层嵌套深度（所有括号闭合）时，才允许命中同步 Token 退出
           if (parenParenDepth == 0 && bracketDepth == 0 && braceDepth == 0) {
               if (syncSet.contains(current.Kind)) {
                   return;
               }
           }

           advance(); // 丢弃不匹配的噪音 Token
       }
   }

工业级 AST 构建与语法容错解析引擎 C++ 实战
------------------------------------------

以下提供一套完整的工业级 C++ 解析与错误恢复引擎，集成 Arena 内存池、单 Token 缺失合成、Poison 错误抑制及带括号平衡跟踪的 Panic Mode 状态机。

数据结构与 Arena 分配器设计
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <string>
   #include <string_view>
   #include <vector>
   #include <span>
   #include <memory>
   #include <cstdint>
   #include <cassert>

   // 源码物理位置坐标
   struct SourceLocation {
       uint32_t Line = 0;
       uint32_t Column = 0;
       uint32_t Offset = 0;
   };

   // Token 物理类型枚举
   enum class TokenKind : uint8_t {
       Eof,
       Identifier,
       IntLiteral,
       KwFn,
       KwLet,
       KwReturn,
       KwIf,
       KwElse,
       Plus,
       Minus,
       Star,
       Slash,
       Equal,
       Semi,
       Colon,
       Comma,
       LParen,
       RParen,
       LBrace,
       RBrace
   };

   struct Token {
       TokenKind Kind;
       SourceLocation Loc;
       std::string_view Text;
   };

   // 线性 Arena 连续内存池
   class BumpAllocator {
   public:
       explicit BumpAllocator(size_t pageSize = 4096 * 16) : PageSize(pageSize) {
           allocateNewPage();
       }

       ~BumpAllocator() {
           for (char *page : Pages) {
               delete[] page;
           }
       }

       BumpAllocator(const BumpAllocator&) = delete;
       BumpAllocator& operator=(const BumpAllocator&) = delete;

       void* allocate(size_t bytes, size_t alignment) {
           size_t currentAddr = reinterpret_cast<size_t>(CurrentPtr);
           size_t alignedAddr = (currentAddr + (alignment - 1)) & ~(alignment - 1);
           size_t padding = alignedAddr - currentAddr;

           if (CurrentPtr + padding + bytes > CurrentEnd) {
               allocateNewPage();
               return allocate(bytes, alignment);
           }

           CurrentPtr = reinterpret_cast<char*>(alignedAddr) + bytes;
           return reinterpret_cast<void*>(alignedAddr);
       }

       template <typename T, typename... Args>
       T* alloc(Args&&... args) {
           void *mem = allocate(sizeof(T), alignof(T));
           return new (mem) T(std::forward<Args>(args)...);
       }

   private:
       size_t PageSize;
       std::vector<char*> Pages;
       char *CurrentPtr = nullptr;
       char *CurrentEnd = nullptr;

       void allocateNewPage() {
           char *newPage = new char[PageSize];
           Pages.push_back(newPage);
           CurrentPtr = newPage;
           CurrentEnd = newPage + PageSize;
       }
   };

AST 节点拓扑定义
~~~~~~~~~~~~~~~~

.. code-block:: cpp

   enum class ASTNodeKind : uint8_t {
       ErrorExpr,
       IntLiteralExpr,
       DeclRefExpr,
       BinaryExpr,
       VarDeclStmt,
       ReturnStmt,
       CompoundStmt,
       FunctionDecl
   };

   class ASTNode {
   public:
       ASTNodeKind Kind;
       SourceLocation Loc;
       explicit ASTNode(ASTNodeKind kind, SourceLocation loc) : Kind(kind), Loc(loc) {}
   };

   class ASTExpr : public ASTNode {
   public:
       bool IsPoison = false;
       explicit ASTExpr(ASTNodeKind kind, SourceLocation loc, bool isPoison = false)
           : ASTNode(kind, loc), IsPoison(isPoison) {}
   };

   class ASTErrorExpr final : public ASTExpr {
   public:
       explicit ASTErrorExpr(SourceLocation loc)
           : ASTExpr(ASTNodeKind::ErrorExpr, loc, /*isPoison=*/true) {}
   };

   class ASTIntLiteralExpr final : public ASTExpr {
   public:
       int64_t Value;
       ASTIntLiteralExpr(int64_t val, SourceLocation loc)
           : ASTExpr(ASTNodeKind::IntLiteralExpr, loc), Value(val) {}
   };

   class ASTDeclRefExpr final : public ASTExpr {
   public:
       std::string_view Identifier;
       ASTDeclRefExpr(std::string_view ident, SourceLocation loc)
           : ASTExpr(ASTNodeKind::DeclRefExpr, loc), Identifier(ident) {}
   };

   class ASTBinaryExpr final : public ASTExpr {
   public:
       TokenKind Op;
       ASTExpr *Left;
       ASTExpr *Right;
       ASTBinaryExpr(TokenKind op, ASTExpr *left, ASTExpr *right, SourceLocation loc)
           : ASTExpr(ASTNodeKind::BinaryExpr, loc, (left && left->IsPoison) || (right && right->IsPoison)),
             Op(op), Left(left), Right(right) {}
   };

   class ASTStmt : public ASTNode {
   public:
       using ASTNode::ASTNode;
   };

   class ASTVarDeclStmt final : public ASTStmt {
   public:
       std::string_view Name;
       ASTExpr *Initializer;
       ASTVarDeclStmt(std::string_view name, ASTExpr *init, SourceLocation loc)
           : ASTStmt(ASTNodeKind::VarDeclStmt, loc), Name(name), Initializer(init) {}
   };

   class ASTCompoundStmt final : public ASTStmt {
   public:
       std::span<ASTStmt*> Statements;
       ASTCompoundStmt(std::span<ASTStmt*> stmts, SourceLocation loc)
           : ASTStmt(ASTNodeKind::CompoundStmt, loc), Statements(stmts) {}
   };

   class ASTFunctionDecl final : public ASTNode {
   public:
       std::string_view Name;
       ASTCompoundStmt *Body;
       ASTFunctionDecl(std::string_view name, ASTCompoundStmt *body, SourceLocation loc)
           : ASTNode(ASTNodeKind::FunctionDecl, loc), Name(name), Body(body) {}
   };

容错解析器与状态机实现
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: cpp

   class TokenSet {
   public:
       constexpr TokenSet() : Mask(0) {}
       constexpr TokenSet(std::initializer_list<TokenKind> kinds) : Mask(0) {
           for (auto k : kinds) {
               Mask |= (1ULL << static_cast<uint8_t>(k));
           }
       }

       bool contains(TokenKind k) const {
           return (Mask & (1ULL << static_cast<uint8_t>(k))) != 0;
       }

       TokenSet operator|(const TokenSet &other) const {
           TokenSet res;
           res.Mask = this->Mask | other.Mask;
           return res;
       }

   private:
       uint64_t Mask;
   };

   class DiagnosticsEngine {
   public:
       void report(SourceLocation loc, std::string_view message) {
           std::cerr << "error at [" << loc.Line << ":" << loc.Column << "]: " << message << "
";
           ErrorCount++;
       }

       size_t getErrorCount() const { return ErrorCount; }

   private:
       size_t ErrorCount = 0;
   };

   class Parser {
   public:
       Parser(std::span<const Token> tokens, BumpAllocator &arena, DiagnosticsEngine &diags)
           : Tokens(tokens), Cursor(0), Arena(arena), Diags(diags) {}

       // 顶级函数解析入口
       ASTFunctionDecl* parseFunctionDeclaration() {
           Token fnTok = consume(TokenKind::KwFn, "expected 'fn' keyword");
           Token nameTok = consume(TokenKind::Identifier, "expected function name identifier");

           // 解析形参列表定界符
           consume(TokenKind::LParen, "expected '(' after function name");
           // 简化逻辑：忽略形参内部，直接寻找并闭合 ')'
           if (peek().Kind != TokenKind::RParen) {
               skipUntil(TokenSet{TokenKind::RParen, TokenKind::LBrace});
           }
           expectOrRecover(TokenKind::RParen, "expected ')' to close parameter list");

           ASTCompoundStmt *body = parseCompoundStatement();
           return Arena.alloc<ASTFunctionDecl>(nameTok.Text, body, fnTok.Loc);
       }

   private:
       std::span<const Token> Tokens;
       size_t Cursor;
       BumpAllocator &Arena;
       DiagnosticsEngine &Diags;

       Token peek() const {
           if (Cursor < Tokens.size()) return Tokens[Cursor];
           return Token{TokenKind::Eof, {0, 0, 0}, ""};
       }

       Token advance() {
           Token t = peek();
           if (Cursor < Tokens.size()) Cursor++;
           return t;
       }

       bool isAtEnd() const {
           return peek().Kind == TokenKind::Eof;
       }

       Token consume(TokenKind expected, std::string_view errorMsg) {
           if (peek().Kind == expected) return advance();
           Diags.report(peek().Loc, errorMsg);
           return Token{expected, peek().Loc, ""}; // 合成虚拟 Token 返回
       }

       void expectOrRecover(TokenKind expected, std::string_view errorMsg) {
           if (peek().Kind == expected) {
               advance();
               return;
           }

           // 单 Token 缺失合成判定
           Diags.report(peek().Loc, errorMsg);
           if (peek().Kind == TokenKind::LBrace && expected == TokenKind::RParen) {
               // 局部修复: 虚拟插入 RParen，不消耗当前的 LBrace
               return;
           }

           // 触发局部跳过
           skipUntil(TokenSet{expected, TokenKind::Semi, TokenKind::RBrace});
           if (peek().Kind == expected) {
               advance();
           }
       }

       ASTCompoundStmt* parseCompoundStatement() {
           Token lbrace = consume(TokenKind::LBrace, "expected '{' to begin block");
           std::vector<ASTStmt*> statements;

           const TokenSet stmtSyncSet = {
               TokenKind::KwLet, TokenKind::KwReturn, TokenKind::KwIf, TokenKind::RBrace, TokenKind::Semi
           };

           while (!isAtEnd() && peek().Kind != TokenKind::RBrace) {
               try {
                   if (peek().Kind == TokenKind::KwLet) {
                       statements.push_back(parseVarDeclStatement());
                   } else if (peek().Kind == TokenKind::KwReturn) {
                       statements.push_back(parseReturnStatement());
                   } else {
                       Diags.report(peek().Loc, "expected statement keyword ('let', 'return')");
                       skipUntil(stmtSyncSet);
                       if (peek().Kind == TokenKind::Semi) advance();
                   }
               } catch (...) {
                   // 异常边界收敛
                   skipUntil(stmtSyncSet);
               }
           }

           consume(TokenKind::RBrace, "expected '}' to close block");

           // 使用 Arena 分配尾部连续切片
           size_t spanBytes = sizeof(ASTStmt*) * statements.size();
           ASTStmt **stmtArray = reinterpret_cast<ASTStmt**>(Arena.allocate(spanBytes, alignof(ASTStmt*)));
           std::copy(statements.begin(), statements.end(), stmtArray);

           return Arena.alloc<ASTCompoundStmt>(std::span<ASTStmt*>(stmtArray, statements.size()), lbrace.Loc);
       }

       ASTVarDeclStmt* parseVarDeclStatement() {
           Token letTok = advance(); // 消费 'let'
           Token nameTok = consume(TokenKind::Identifier, "expected variable name after 'let'");
           consume(TokenKind::Equal, "expected '=' in variable declaration");

           ASTExpr *initExpr = parseExpression();

           // 语句结尾分号校验与恐慌恢复
           if (peek().Kind != TokenKind::Semi) {
               Diags.report(peek().Loc, "expected ';' after variable declaration");
               // 若下一 Token 是合法的下一语句起点，直接合成分号，保持当前变量声明节点
               if (peek().Kind == TokenKind::KwLet || peek().Kind == TokenKind::KwReturn || peek().Kind == TokenKind::RBrace) {
                   return Arena.alloc<ASTVarDeclStmt>(nameTok.Text, initExpr, letTok.Loc);
               }
               skipUntil(TokenSet{TokenKind::Semi, TokenKind::RBrace, TokenKind::KwLet});
               if (peek().Kind == TokenKind::Semi) advance();
           } else {
               advance(); // 消费 ';'
           }

           return Arena.alloc<ASTVarDeclStmt>(nameTok.Text, initExpr, letTok.Loc);
       }

       ASTStmt* parseReturnStatement() {
           Token retTok = advance(); // 消费 'return'
           ASTExpr *val = parseExpression();
           consume(TokenKind::Semi, "expected ';' after return statement");
           return Arena.alloc<ASTVarDeclStmt>("", val, retTok.Loc); // 简写复用
       }

       ASTExpr* parseExpression() {
           Token tok = peek();
           if (tok.Kind == TokenKind::IntLiteral) {
               advance();
               int64_t val = std::stoll(std::string(tok.Text));
               return Arena.alloc<ASTIntLiteralExpr>(val, tok.Loc);
           }
           if (tok.Kind == TokenKind::Identifier) {
               advance();
               return Arena.alloc<ASTDeclRefExpr>(tok.Text, tok.Loc);
           }

           // 表达式语法断点: 缺失有效操作数
           Diags.report(tok.Loc, "expected expression (identifier or literal)");
           return Arena.alloc<ASTErrorExpr>(tok.Loc);
       }

       void skipUntil(const TokenSet &syncSet) {
           int parenDepth = 0;
           int braceDepth = 0;

           while (!isAtEnd()) {
               Token current = peek();

               if (current.Kind == TokenKind::LParen) parenDepth++;
               else if (current.Kind == TokenKind::RParen && parenDepth > 0) parenDepth--;
               else if (current.Kind == TokenKind::LBrace) braceDepth++;
               else if (current.Kind == TokenKind::RBrace) {
                   if (braceDepth > 0) {
                       braceDepth--;
                   } else {
                       // 保护外层作用域闭合花括号不被吞噬
                       return;
                   }
               }

               if (parenDepth == 0 && braceDepth == 0) {
                   if (syncSet.contains(current.Kind)) {
                       return;
                   }
               }

               advance();
           }
       }
   };

小结与下章导读
--------------

本章系统解构了具体语法树（CST）向抽象语法树（AST）的拓扑转换规律与编译器前端错误恢复机制：

1. **CST 与 AST 物理边界**：阐明了 CST 记录产生式推导证明痕迹与 AST 承载计算语义的本质差异，剖析了括号折叠、冗余层级压缩以及现代 Green/Red Tree 双模架构的设计取舍。
2. **高性能内存存储**：建立了基于 Bump Allocator（Arena）的线性连续物理内存分配模型，运用 Trailing Objects 模式消除了可变长子节点数组的二次寻址，消除了虚析构开销。
3. **语法断点四维建模**：形式化定义了由已确认前缀、当前文法状态、预期符号集与实际符号构成的错误状态证据元组。
4. **局部精准恢复与 Poison 机制**：确立了单 Token 缺失合成与冗余剔除的就地恢复规则，运用 Poison 错误类型在 AST 中短路级联类型报错。
5. **Panic Mode 恐慌恢复引擎**：设计了层次化同步 Token 集合（Resynchronization Sets）与嵌套括号平衡跟踪算法，确保解析器在遭遇严重语法溃散时平稳收敛至可信边界。

至此，第 2 模块关于源码物理编码、词法状态机、递归下降分析、Pratt 优先级解析与 AST 容错构建的全部前端语法技术已全量建立。解析器生成的 AST 仅表达了静态语法层次，尚未确定标识符所绑定的物理内存槽位与类型合法性。在第 3 模块第 1 节 **符号表物理拓扑与嵌套作用域链：声明/使用绑定、变量遮蔽 (Shadowing) 与自由变量/闭包捕获（03_semantic_analysis_and_type_systems/01_symbol_tables_and_nested_scope_chains.rst）** 中，我们将全面进入语义分析阶段，深入解构符号表的作用域树拓扑、哈希桶链表查找机制、Lexical Scope 遮蔽规则以及闭包环境的逃逸分析。
