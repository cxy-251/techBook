================================================================================
词法状态机与 Token 流：Lexeme 词素、最长匹配原则、二义性裁决与 Whitespace/Comment 附着
================================================================================

.. note:: 前置背景与上下文承接
   在第 2 模块第 1 节中，编译器前端完成了源码字符流的物理载入、UTF-8 编码解码校验、紧凑 SourceLocation/Span 线性坐标体系构建以及行表（Line Table）双向决议。源码此时在内存中表现为一个由末尾双空字符（``\0\0``）哨兵保护的连续只读字节序列。本章作为词法分析的核心实现篇，深入解构如何将无结构的连续物理字符流切分为结构化的 Token 序列。内容涵盖 Token 物理内存拓扑与字符串驻留、有限状态自动机（NFA/DFA）与 Hopcroft 状态最小化、工业级手写扫描器与 SIMD 向量化加速、最长匹配原则（Maximal Munch）与二义性裁决、完美哈希关键字判定、现代 IDE 无损语法树中的 Trivia 附着架构，以及词法错误恢复机制。

Token 物理拓扑与 Lexeme 内存切片
--------------------------------

词法分析器（Lexer / Scanner）是编译器中唯一直接逐字节消费原始源码文本的流水线阶段。其核心物理任务是将字符流归纳为具备离散语法范畴的最小语义单元——Token。在数据结构设计上，必须严格解耦词素（Lexeme）与记号（Token）。

Lexeme 与 Token 的数据解耦契约
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 词法分析核心概念物理定义与职责划分
   :widths: 20 25 25 30
   :header-rows: 1
   :class: tight-table

   * - 概念实体
     - 物理表现形式
     - 存在生命周期
     - 编译器消费阶段
   * - 词素 (Lexeme)
     - 源码缓冲区中的连续原始字节切片 (指针 + 长度)
     - 词法扫描期间即时形成，随源码缓冲区释放
     - 供词法器分类，供诊断系统提取原始拼写
   * - 模式 (Pattern)
     - 描述词法单元形态的形式文法/正则表达式规则
     - 编译器设计期确立，硬编码至状态机转移表
     - 驱动词法状态机进行字符分支转移判定
   * - 记号 (Token)
     - 包含枚举类别、位置与载荷的固定尺寸结构体
     - 贯穿语法分析、AST 构建与语义分析初期
     - 语法分析器驱动递归下降或 LR 状态转移的核心输入

Token 紧凑内存布局（16 字节对齐设计）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Token 在语法解析阶段会被大量实例化并高频传递。工业级编译器（如 Clang、Rustc）将 Token 尺寸严格限制在 16 到 24 字节以内，使其能够适配 CPU L1 数据缓存行（Cache Line，通常为 64 字节，单个缓存行可容纳 4 个 Token），并支持寄存器直接传递。

.. code-block:: cpp

   // 工业级紧凑 Token 内存布局设计 (对齐至 16 字节)
   enum class TokenKind : uint16_t {
       // 基础终止符
       Eof = 0,
       Invalid,
       
       // 标识符与字面量
       Identifier,
       IntegerLiteral,
       FloatingLiteral,
       StringLiteral,
       
       // 关键字
       KwIf,
       KwElse,
       KwWhile,
       KwReturn,
       
       // 运算符与分隔符
       Plus,           // +
       PlusPlus,       // ++
       PlusEqual,      // +=
       Greater,        // >
       GreaterGreater, // >>
       GreaterEqual,   // >=
       Semi,           // ;
       LBrace,         // {
       RBrace,         // }
   };

   enum class TokenFlags : uint16_t {
       None            = 0x0000,
       LeadingSpace    = 0x0001, // 前方存在空白字符
       StartOfLine     = 0x0002, // 位于物理行首 (首个非空白 Token)
       NeedsCleaning   = 0x0004, // 包含转义字符或折行，需二次规范化
       HasTrivia       = 0x0008, // 携带附着注释或格式化信息
   };

   struct alignas(8) Token {
       uint32_t Location;     // 4 字节: 全局压缩 SourceLocation 偏移
       uint32_t Length;       // 4 字节: 词素物理字节长度 (或行内绝对偏移)
       TokenKind Kind;        // 2 字节: 语法分类枚举
       TokenFlags Flags;      // 2 字节: 词法状态标志位
       union {
           const char *RawDataPtr;         // 8 字节: 直接指向源码缓冲区的词素起始指针
           const IdentifierInfo *IdentInfo; // 8 字节: 指向驻留符号表条目的唯一指针
           uint64_t SmallLiteralPayload;   // 8 字节: 存储紧凑字面量数值 (如小整数)
       } Payload;
   };
   static_assert(sizeof(Token) == 16, "Token must be exactly 16 bytes for optimal cache throughput");

字符串驻留（String Interning）与标识符池拓扑
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当源码中频繁出现重复标识符（如变量名 ``index``、类型名 ``int32_t``）时，若在每个 Token 中均分配堆内存存储字符串副本，会导致堆内存分配器锁竞争以及大量冗余的小对象内存开销。

编译器引入全局 **字符串驻留池（String Interning Pool / IdentifierTable）**：
1. 词法器扫描出标识符词素 ``[start_ptr, length]``。
2. 计算该内存切片的快速哈希值（如 xxHash3 或 MurmurHash3）。
3. 查询全局哈希表。若已存在，返回指向唯一 ``IdentifierInfo`` 实例的只读指针；若不存在，在专用连续内存池（Bump Allocator / Arena）中分配单份持久化副本并插入哈希表。
4. 语法解析器与语义分析器在比较两个标识符是否相同时，直接执行 CPU 指针比较（``token1.IdentInfo == token2.IdentInfo``），将原本 $O(N)$ 的字符串逐字节比较降低为 $O(1)$ 的单周期寄存器指令。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                  字符串驻留池 (Identifier Table) 物理拓扑               |
   +-------------------------------------------------------------------------+
   |  源码字符流: "... total_count ... total_count ... total_count ..."      |
   |                    |                  |                  |              |
   |                    | (哈希定位)       | (哈希定位)       | (哈希定位)   |
   |                    +------------------+------------------+              |
   |                                       |                                 |
   |                                       v                                 |
   |                    +--------------------------------------+             |
   |                    |   全局唯一 IdentifierInfo 实例       |             |
   |                    |   - Length: 11                       |             |
   |                    |   - Hash: 0xA4F89C21                 |             |
   |                    |   - TokenKind: TokenKind::Identifier |             |
   |                    |   - Spelling: "total_count\0"        |             |
   |                    +--------------------------------------+             |
   |                                       ^                                 |
   |         +-----------------------------+-----------------------------+   |
   |         |                             |                             |   |
   |   [ Token 1 (Line 1) ]          [ Token 2 (Line 4) ]          [ Token 3 ]
   |   Payload.IdentInfo             Payload.IdentInfo             Payload.IdentInfo
   +-------------------------------------------------------------------------+

有限状态自动机与词法生成数学模型
--------------------------------

词法规则的形式化基础是正则语言（Regular Language）。从字符序列到 Token 的转换过程遵循严格的自动机转换流水线。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     形式词法分析器数学模型构建链路                      |
   +-------------------------------------------------------------------------+
   |  [ 正则表达式集合 (Regex) ]                                             |
   |         |                                                               |
   |         | Thompson 构造法 (引入 ε 转移)                                 |
   |         v                                                               |
   |  [ 不确定有限状态自动机 (NFA) ]                                         |
   |         |                                                               |
   |         | 子集构造法 (Subset Construction / Powerset)                   |
   |         v                                                               |
   |  [ 确定有限状态自动机 (DFA) ]                                           |
   |         |                                                               |
   |         | Hopcroft 状态划分算法                                         |
   |         v                                                               |
   |  [ 最小化确定有限状态自动机 (Minimized DFA) ]                           |
   |         |                                                               |
   |         | 行位移压缩 (Row-Displacement Compression)                     |
   |         v                                                               |
   |  [ 紧凑转移矩阵驱动代码 (Driver Table / Switch-Case ASM) ]               |
   +-------------------------------------------------------------------------+

Thompson 构造法：正则表达式向 NFA 映射
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Thompson 算法通过结构归纳法为正则表达式的基础算子构建对应的 NFA 状态子图：
- **基本字符 $a$**：建立起点 $s_0$ 与终点 $s_1$，存在转移边 $s_0 \xrightarrow{a} s_1$。
- **连接算子 $AB$**：将 $A$ 的接受状态通过 $\epsilon$ 边直接连接到 $B$ 的起始状态。
- **选择算子 $A \mid B$**：新建起始状态 $s_{start}$，发射两条 $\epsilon$ 转移边分别指向 $A$ 与 $B$ 的起点；$A$ 与 $B$ 的接受状态各发射一条 $\epsilon$ 转移边汇聚至新的唯一接受状态 $s_{end}$。
- **Kleene 闭包 $A^*$**：新建 $s_{start}$ 与 $s_{end}$。$s_{start} \xrightarrow{\epsilon} s_{end}$ 匹配空串；$s_{start} \xrightarrow{\epsilon} A_{start}$ 匹配进入；$A_{end} \xrightarrow{\epsilon} A_{start}$ 形成循环回边；$A_{end} \xrightarrow{\epsilon} s_{end}$ 跳出循环。

子集构造法（Subset Construction）：NFA 向 DFA 确定化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

NFA 包含 $\epsilon$ 转移且对于同一输入字符可能存在多个候选转移目标，无法在单次遍历中确定性推进。子集构造法通过跟踪 NFA 状态集合的幂集构造等价的 DFA。

核心算子数学定义：
1. **$\epsilon	ext{-closure}(s)$**：从 NFA 状态 $s$ 出发，仅通过 $\epsilon$ 转移边所能到达的所有 NFA 状态的闭包集合。
2. **$	ext{move}(T, a)$**：从状态集合 $T$ 中的任意状态出发，经过字符 $a$ 转移边所到达的所有 NFA 状态的直接后继集合。

算法执行步骤：
1. 计算初态 $D_0 = \epsilon	ext{-closure}(s_{start})$，将其压入待标记状态集队列。
2. 当队列非空，弹出未标记 DFA 状态子集 $U$。
3. 针对字符表 $\Sigma$ 中的每个输入符号 $a$，计算 $V = \epsilon	ext{-closure}(	ext{move}(U, a))$。
4. 若 $V$ 非空且未在全局 DFA 状态集合中出现，将 $V$ 注册为新的 DFA 状态并入队；在转移函数中记录 $DFA\_Transition(U, a) = V$。
5. 若子集 $U$ 中包含任意 NFA 接受状态，则判定 $U$ 为 DFA 接受状态，并关联对应优先级最高的 Token 类别。

Hopcroft 状态最小化算法
~~~~~~~~~~~~~~~~~~~~~~~

子集构造法生成的 DFA 往往包含等价状态。Hopcroft 算法通过逐步细分状态等价类，生成具备最小状态数的唯一确定性状态机。

.. code-block:: cpp

   // Hopcroft DFA 状态最小化核心算法逻辑
   struct HopcroftMinimizer {
       using StateSet = std::unordered_set<uint32_t>;
       
       // P 为当前状态等价类划分集合 (Partition)
       // W 为待处理的切分候选工作集 (Worklist)
       std::vector<StateSet> Partition;
       std::vector<StateSet> Worklist;
       
       void minimize(const std::vector<uint32_t>& AllStates, 
                      const StateSet& AcceptingStates,
                      const std::vector<char>& Alphabet,
                      const auto& TransitionFunc,
                      const auto& InverseTransitionFunc) {
           
           // 初始划分: 将所有状态划分为两组: [非接受状态集 F_non, 接受状态集 F_acc]
           StateSet NonAccepting;
           for (auto s : AllStates) {
               if (AcceptingStates.find(s) == AcceptingStates.end()) {
                   NonAccepting.insert(s);
               }
           }
           
           Partition.push_back(AcceptingStates);
           if (!NonAccepting.empty()) {
               Partition.push_back(NonAccepting);
           }
           
           Worklist.push_back(AcceptingStates);
           if (!NonAccepting.empty()) {
               Worklist.push_back(NonAccepting);
           }
           
           while (!Worklist.empty()) {
               StateSet A = Worklist.back();
               Worklist.pop_back();
               
               for (char c : Alphabet) {
                   // X 为所有能够在输入字符 c 下转移进入集合 A 的前驱状态集合: X = InvTrans(A, c)
                   StateSet X = InverseTransitionFunc(A, c);
                   if (X.empty()) continue;
                   
                   // 遍历当前划分 P 中的每一个等价类 Y
                   for (size_t i = 0; i < Partition.size(); ++i) {
                       StateSet Y = Partition[i];
                       StateSet Intersection; // Y ∩ X
                       StateSet Difference;   // Y \ X
                       
                       for (auto s : Y) {
                           if (X.count(s)) Intersection.insert(s);
                           else Difference.insert(s);
                       }
                       
                       // 当且仅当 Y 被 X 切分为两个非空子集时，执行划分细化
                       if (!Intersection.empty() && !Difference.empty()) {
                           Partition[i] = Intersection;
                           Partition.push_back(Difference);
                           
                           // 更新 Worklist
                           auto it = std::find(Worklist.begin(), Worklist.end(), Y);
                           if (it != Worklist.end()) {
                               *it = Intersection;
                               Worklist.push_back(Difference);
                           } else {
                               if (Intersection.size() <= Difference.size()) {
                                   Worklist.push_back(Intersection);
                               } else {
                                   Worklist.push_back(Difference);
                               }
                           }
                       }
                   }
               }
           }
       }
   };

转移矩阵的行位移压缩（Row-Displacement Compression）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

朴素 DFA 驱动引擎使用二维数组 ``uint16_t TransitionTable[NumStates][256]``。若状态数为 500，表尺寸达到 $500 	imes 256 	imes 2 = 256	ext{ KB}$，将挤占宝贵的 CPU L2 缓存。

现代词法生成器采用 **行位移压缩技术（Row-Displacement Table）**，将稀疏的二维转移表交错平移重叠，压缩至两个一维数组 ``Check[]`` 与 ``Next[]`` 中：
1. 对于状态 $S$，在全局一维数组中寻找一个偏移基址 $	ext{Base}[S]$。
2. 使得对于该状态支持的所有输入字符 $c$，位置 $	ext{Base}[S] + c$ 在数组中均未被其他状态占用。
3. 运行时寻址逻辑：
   - 检查 ``Check[Base[S] + c] == S``。
   - 若匹配成功，下一个状态为 ``Next[Base[S] + c]``；若匹配失败，跳转至错误或默认恢复状态。

手写扫描器工程实现与 SIMD 向量化加速
------------------------------------

尽管自动生成工具（Flex、Ragel）在理论上具备完备的形式化证明，现代工业级编译器（Clang、Rustc、GCC、Swift）几乎全量采用 **手写递归与 Switch 驱动扫描器（Hand-written Scanner）**。

手写词法分析器的工业优势
~~~~~~~~~~~~~~~~~~~~~~~~

1. **精准的错误恢复与诊断控制**：手写扫描器可在发生拼写错误时即时修改内部状态，输出附带 Fix-it 建议的诊断信息，而非直接陷入自动生成器的通用语法陷阱。
2. **多模式平滑交织（Lexer Modes）**：处理插值字符串（如 Python f-string、JS 模板字面量）时，需在代码模式与字符串模式间进行栈式切换，手写扫描器能够直接复用主语言的数据结构。
3. **极佳的局部性与编译器内联**：手写循环与特定语言的快速字符跳转紧密结合，易于触发编译器后端循环展开（Loop Unrolling）与向量化生成。

无分支字符分类表（Character Classification Table）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在扫描循环内部，频繁调用标准库函数（如 ``isalpha()``、``isspace()``）会引入额外的函数调用开销与区域设置（Locale）判断成本。手写词法器预先构建一个 256 字节的静态位掩码属性表：

.. code-block:: cpp

   // 256 字节静态无分支字符分类表
   struct CharInfo {
       enum Mask : uint8_t {
           None       = 0x00,
           IdentifierStart = 0x01, // [a-zA-Z_]
           IdentifierBody  = 0x02, // [a-zA-Z0-9_]
           DecDigit        = 0x04, // [0-9]
           HexDigit        = 0x08, // [0-9a-fA-F]
           Whitespace      = 0x10, // [' ', '	', '\f', '\v']
           Newline         = 0x20, // ['\r', '
']
           Punctuation     = 0x40, // 基础符号
       };
   };

   alignas(64) static const uint8_t CharClassTable[256] = {
       // 0x00 .. 0xFF 静态初始化掩码
       /* 0x00 - '\0' */ CharInfo::None,
       /* 0x20 - ' '  */ CharInfo::Whitespace,
       /* 0x0A - '
' */ CharInfo::Newline,
       /* 0x30 - '0'  */ CharInfo::DecDigit | CharInfo::HexDigit | CharInfo::IdentifierBody,
       /* 0x41 - 'A'  */ CharInfo::IdentifierStart | CharInfo::IdentifierBody | CharInfo::HexDigit,
       /* 0x5F - '_'  */ CharInfo::IdentifierStart | CharInfo::IdentifierBody,
       // 其余条目严格依位填充...
   };

   // 快速判定内联函数 (零分支，单次内存寻址)
   inline bool isIdentStart(uint8_t c) {
       return (CharClassTable[c] & CharInfo::IdentifierStart) != 0;
   }
   inline bool isIdentBody(uint8_t c) {
       return (CharClassTable[c] & CharInfo::IdentifierBody) != 0;
   }

SIMD 向量化分词加速（AVX2 / NEON）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在真实工业代码库中，源码存在大段连续的空白缩进、普通 ASCII 标识符以及大块注释。逐字节遍历会在 CPU 指令流水线中产生大量迭代周期间接开销。现代高性能词法器利用 SIMD 寄存器（256 位 AVX2 或 128 位 ARM NEON）单周期并行扫描 16 到 32 个字节。

.. code-block:: cpp

   #include <immintrin.h>

   // 使用 x86-64 AVX2 向量化跳过连续空格与制表符 (单周期消费 32 字节)
   inline const char* skipWhitespaceAVX2(const char *ptr, const char *end) {
       // 预置 32 字节的空白向量
       __m256i spaceVec = _mm256_set1_epi8(' ');
       __m256i tabVec   = _mm256_set1_epi8('	');

       while (ptr + 32 <= end) {
           // 1. 无对齐载入 32 字节源码数据
           __m256i chunk = _mm256_loadu_si256(reinterpret_cast<const __m256i*>(ptr));

           // 2. 并行比对是否为 ' ' 或 '	'
           __m256i matchSpace = _mm256_cmpeq_epi8(chunk, spaceVec);
           __m256i matchTab   = _mm256_cmpeq_epi8(chunk, tabVec);
           __m256i isWhite    = _mm256_or_si256(matchSpace, matchTab);

           // 3. 提取比对结果的高位掩码 (生成 32 位整数，每位对应一个字节的比对结果)
           uint32_t mask = static_cast<uint32_t>(_mm256_movemask_epi8(isWhite));

           // 若 32 个字节全为空白 (掩码所有位均为 1: 0xFFFFFFFF)
           if (mask == 0xFFFFFFFF) {
               ptr += 32;
           } else {
               // 利用硬件指令计算尾随连续 1 的个数 (即首个非空白字符的偏移量)
               // 在 x86 上使用 ~mask 并执行 Count Trailing Zeros (tzcnt)
               uint32_t nonWhiteOffset = __builtin_ctz(~mask);
               return ptr + nonWhiteOffset;
           }
       }

       // 标量回退处理末尾不足 32 字节的数据
       while (ptr < end && (*ptr == ' ' || *ptr == '	')) {
           ptr++;
       }
       return ptr;
   }

最长匹配原则与词法二义性裁决
----------------------------

词法分析面临的核心问题是：当输入字符流存在多个合法 Token 前缀时，如何建立唯一的边界划分。

最长匹配原则（Maximal Munch Rule）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

最长匹配原则（又称 Maximal Munch）规定：在扫描器当前物理位置，必须优先构造能够满足合法 Token 模式的 **最长连续字符序列**。

- 输入 ``count++``：
  扫描到第一个 ``+`` 时，虽然 ``+``（``TokenKind::Plus``）是合法 Token，但词法器超前扫描下一个字符发现构成更长的合法操作符 ``++``（``TokenKind::PlusPlus``），因此产生单个 ``PlusPlus`` 记号。
- 输入 ``123.456``：
  词法器将识别为一个完整的浮点数字面量，而非整数字面量 ``123``、点运算符 ``.`` 与整数 ``456`` 的拼接。

典型词法二义性场景与硬件级裁决
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

尽管最长匹配能解决大部分边界问题，但在特定语言文法设计中会引发严重的语义级冲突。

.. list-table:: 典型词法二义性冲突场景与工程裁决方案
   :widths: 20 25 25 30
   :header-rows: 1
   :class: tight-table

   * - 冲突场景
     - 源码冲突样例
     - 最长匹配产生的缺陷
     - 现代编译器工程裁决机制
   * - C++ 嵌套模板闭合
     - ``std::vector<std::list<int>>``
     - 词法器将末尾 ``>>`` 贪婪匹配为右移运算符 ``TokenKind::GreaterGreater``
     - 词法器维持输出单个 ``GreaterGreater``，语法分析器在模板参数列表上下文中将其拆解为两个独立的 ``TokenKind::Greater`` 消费
   * - Rust 范围操作符 vs 浮点
     - ``0..10`` 或 ``0.to_string()``
     - 扫描 ``0.`` 时若判定为浮点数前缀，会导致后续连续 ``.`` 无法正确组成范围 ``..``
     - 实施 Lookahead(2)：若发现数字后紧随 ``..``，立即截断整数形态并保留 ``..`` 独立扫描
   * - 预处理数字 (pp-number)
     - C/C++ 中的 ``0xE+1`` 或 ``123e+foo``
     - 在宏展开与词法阶段尚无法确定是否为科学计数法有效浮点
     - 词法阶段全部捕获为宽泛的预处理数字 Token，延迟至语法分析与语义分析期执行严格数值转换

上下文敏感词法分析（Context-Sensitive Lexing / Lexer Hack）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在特定语言（如 C++ 与 JavaScript）中，单纯依靠无状态词法器无法完成正确的切分：
1. **C++ "Lexer Hack" 符号消歧**：
   在 C 语言中，语句 ``T * p;`` 存在双重歧义：若 ``T`` 为类型名，该语句为指针变量声明；若 ``T`` 为变量名，该语句为乘法表达式。现代编译器通过在语义分析器中将已识别的类型符号反向注入词法器的标识符表，动态修改 Token 的 ``Kind``。
2. **JavaScript 正则字面量 vs 除法运算符**：
   斜杠 ``/`` 既可代表除法运算符（``a / b``），也可代表正则表达式字面量的起始定界符（``/abc/g.test(s)``）。词法器必须与语法分析器协同维护一个布尔标志位 ``AllowRegExp``。当且仅当前一个 Token 属于表达式起始上下文（如 ``(``、``=``、``return``、``,``）时，斜杠才会被词法器解析为正则表达式。

关键字与标识符决议机制
----------------------

源码中绝大多数标识符与关键字共享相同的词法正则模式（``[a-zA-Z_][a-zA-Z0-9_]*``）。将二者高效分离是词法器的核心职责。

完美哈希函数（Perfect Hashing）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于固定的关键字集合（如 C++ 的 90 余个关键字、Rust 的 40 余个关键字），通过静态构建工具（如 GNU ``gperf``）在编译期计算出无冲突的 **完美哈希函数（Perfect Hash Function）**。

.. code-block:: cpp

   // 编译期生成的高效关键字完美哈希识别器
   struct KeywordLookup {
       static inline TokenKind classify(const char *str, unsigned int len) {
           // 极小语言关键字完美哈希表
           static const unsigned char asso_values[] = {
               16, 16, 16, 16, 16, 16, 16, 16, 16, 16,
               // ... 针对 ASCII 字符映射的散列偏置权值 ...
               4,  0,  1,  16, 2,  16, 16, 0,  16, 16, // 'a'..'j'
           };

           if (len <= 8 && len >= 2) {
               // 通过字符串首尾字符与长度计算无冲突槽位
               unsigned int key = len + asso_values[static_cast<uint8_t>(str[0])] + 
                                        asso_values[static_cast<uint8_t>(str[len - 1])];
               
               // 单次内存比对确认识别结果
               if (key == 6 && memcmp(str, "return", 6) == 0) return TokenKind::KwReturn;
               if (key == 2 && memcmp(str, "if", 2) == 0)     return TokenKind::KwIf;
               if (key == 5 && memcmp(str, "while", 5) == 0)  return TokenKind::KwWhile;
           }
           return TokenKind::Identifier;
       }
   };

硬关键字与软关键字（Contextual Keywords）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 现代编程语言关键字类型与裁决策略
   :widths: 20 25 25 30
   :header-rows: 1
   :class: tight-table

   * - 分类范畴
     - 典型代表
     - 词法分析器行为
     - 语法分析器职责
   * - 硬关键字 (Hard Keywords)
     - ``if``, ``return``, ``while``, ``class``
     - 词法器直接赋予专属的 ``TokenKind::Kw*``，禁止作为普通变量名
     - 直接驱动语法产生式分支选择
   * - 软关键字 (Contextual / Soft)
     - C# 中的 ``get``, ``set``, ``yield``；Rust 中的 ``union``, ``dyn``
     - 词法器统一输出为普通的 ``TokenKind::Identifier``
     - 仅当其出现在特定语法树节点槽位时，语法器动态将其提升为具有关键字控制效力的结构

Unicode 标识符与 UAX #31 规范
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

支持多语言命名的现代语言遵循 Unicode Standard Annex #31（UAX #31）规范。标识符的有效性由字符的 Unicode 属性决定：
- **起始字符集合**：满足 ``XID_Start`` 属性（包含全球各类语言文字字母及具有字母特性的表意符号）。
- **继续字符集合**：满足 ``XID_Continue`` 属性（在起始集合基础上增加非间断间距标记、组合标记、十进制数字及连接标点）。
- **规范化过滤**：词法器在驻留 Unicode 标识符前，强制执行 Unicode 规范化形式 NFKC（兼容等价性组合）转换，消除视觉形似字符带来的安全风险。

无损语法树与 Trivia（空白/注释）附着拓扑
----------------------------------------

经典编译器架构在词法分析阶段将空白字符与注释直接丢弃。这一处理模式完全能够支撑语法分析与后端代码生成，但在现代语言服务器（IDE / Language Server）环境下会导致严重的结构退化：IDE 无法实现高保真源码重构（Refactoring）、自动格式化（Formatting）以及精确的代码修复（Quick-Fix）。

现代编译器前端（如 .NET Roslyn、SwiftSyntax、rust-analyzer）全量引入 **无损语法树（Lossless Syntax Tree / Concrete Syntax Tree）** 架构。

Trivia 物理模型与切分原则
~~~~~~~~~~~~~~~~~~~~~~~~~

在无损语法体系中，文本中的所有字符必须实现 100% 的信息守恒。任何非语法 Token 的字符（空格、制表符、行注释、块注释、文档注释、条件编译指令）均被抽象为 **Trivia（附着物）**。

Trivia 自身不作为独立的语法节点进入 AST，而是按严格的几何拓扑规则附着于其相邻的主 Token 之上：
1. **前置附着物（Leading Trivia）**：位于当前 Token 物理起始位置之前的所有空白与注释。
2. **后置附着物（Trailing Trivia）**：紧随当前 Token 结束位置之后、且直至当前物理行行尾换行符之间的所有空白与单行注释。

.. code-block:: text

   源码文本行: "    let score = 100; // 记录初始分值
"
   -----------------------------------------------------------------------------
   Token 1: 'let'
     - Leading Trivia : [ Whitespace("    ") ]
     - Main Token     : TokenKind::KwLet (spelling: "let")
     - Trailing Trivia: [ Whitespace(" ") ]
   Token 2: 'score'
     - Leading Trivia : []
     - Main Token     : TokenKind::Identifier (spelling: "score")
     - Trailing Trivia: [ Whitespace(" ") ]
   Token 3: '='
     - Leading Trivia : []
     - Main Token     : TokenKind::Equal (spelling: "=")
     - Trailing Trivia: [ Whitespace(" ") ]
   Token 4: '100'
     - Leading Trivia : []
     - Main Token     : TokenKind::IntegerLiteral (spelling: "100")
     - Trailing Trivia: []
   Token 5: ';'
     - Leading Trivia : []
     - Main Token     : TokenKind::Semi (spelling: ";")
     - Trailing Trivia: [ Whitespace(" "), Comment("// 记录初始分值"), Newline("
") ]
   -----------------------------------------------------------------------------
   * 拓扑不变性: 遍历整棵语法树所有 Token 的 (LeadingTrivia + Token + TrailingTrivia)，
     能够逐字节无损还原（Bit-for-bit Roundtrip）原始磁盘文件。

Green-Red 树中的 Trivia 内存表征
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Roslyn 与 rust-analyzer 采用 Green-Red 树分层架构：
- **Green Node（不可变内部物理节点）**：完全基于相对偏移量存储，不包含绝对源码位置，可跨线程与跨编辑版本高效共享。每个 Green Token 内部直接内联存储其 Leading/Trailing Trivia 数组。
- **Red Node（面向公共 API 的瞬态包装器）**：在访问时按需计算绝对物理偏移量与父子指针。

.. code-block:: rust

   // Rust-Analyzer 风格的紧凑无损 Token 与 Trivia 拓扑
   #[derive(Clone, Copy, PartialEq, Eq, Hash)]
   pub enum SyntaxKind {
       // Token
       Ident,
       Whitespace,
       Comment,
       Plus,
       Semi,
       // 复合语法结构
       BinaryExpr,
   }

   #[derive(Clone, Debug)]
   pub struct GreenToken {
       kind: SyntaxKind,
       text: String, // 纯文本或驻留切片
   }

   #[derive(Clone, Debug)]
   pub struct GreenElement {
       // 统一容纳主 Token 与作为 Trivia 的 Whitespace/Comment
       children: Vec<GreenToken>,
   }

文档注释与 Lint 指令的语义提升
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

特定注释（如 Doxygen/Rustdoc 的 ``///`` 或 ``/** ... */`` 以及 Lint 控制属性 ``// nolint``）携带强语法约束。词法器在识别到特定前缀时，会生成专属的文档记号（``TokenKind::DocComment``），并在 AST 构建阶段将其直接提升为附加在声明节点上的元数据属性（Attribute / Annotation），供后续类型检查器与 API 文档提取系统直接消费。

词法错误恢复与非法 Token 遏制
------------------------------

词法分析器处于编译流程最外层，必须具备极高的容错性，严禁因单个非法字节或异常状态导致词法进程崩溃。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     词法错误快速拦截与局部恢复机制                      |
   +-------------------------------------------------------------------------+
   |  [ 异常输入源 ]                                                         |
   |         |                                                               |
   |         +---> [ 未闭合字符串字面量: "hello world
 ]                    |
   |         |            |                                                  |
   |         |            v                                                  |
   |         |     (触发物理行逃生) -> 强制在 '
' 前闭合，发射 InvalidToken |
   |         |                                                               |
   |         +---> [ 非法控制字符/乱码字节: 0x1B ]                           |
   |         |            |                                                  |
   |         |            v                                                  |
   |         |     (单字节隔离) -> 产生单个 InvalidToken，指针递增 1 字节    |
   |         |                                                               |
   |         +---> [ 未闭合多行块注释: /* code... EOF ]                      |
   |                      |                                                  |
   |                      v                                                  |
   |               (EOF 哨兵拦截) -> 报告未闭合错误，状态机回归基态          |
   +-------------------------------------------------------------------------+

未闭合字符串字面量的物理行逃生（Line Escape）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当程序员遗漏右双引号时（如 ``let s = "unterminated string;``），若词法器盲目扫描至文件末尾，会导致后续整篇代码均被误判为字符串内容。

工业级词法器设立 **物理行边界硬约束**：
1. 扫描普通单行字符串时，一旦遇到 ``
``、``\r`` 或 ``\0`` 哨兵，立即强行终止字符串扫描状态。
2. 构造一个携带 ``TokenFlags::NeedsCleaning`` 的 ``TokenKind::StringLiteral`` 或 ``TokenKind::Invalid``。
3. 发射明确诊断：``error: missing terminating '"' character``。
4. 扫描指针保持在换行符前，使词法器在下一行能够以完全正常的初始状态继续分词，将错误严格局部化。

非法字符与不可识别字节的单字节隔离
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当源码中出现非法字符（如随机乱码二进制、不支持的 Unicode 特殊符号）：
1. 词法器不直接中断流程，而是将当前不可识别的单个物理字节包装为 ``TokenKind::Invalid``。
2. 记录当前精确的 SourceLocation。
3. 指针仅递增 1 个字节，继续驱动状态机。
4. 语法解析器在消费到 ``TokenKind::Invalid`` 时执行同步点丢弃，确保编译器能一次性报告文件中所有的非法字符错误。

小结与下章导读
--------------

本章系统解构了现代编译器词法分析阶段的工程物理实现：

1. **Token 物理拓扑**：确立了 Lexeme 切片与 Token 分类实体的解耦契约，构建了 16 字节对齐的紧凑内存结构，并通过全局字符串驻留池将标识符比较加速至 $O(1)$ 指针比对。
2. **状态机理论与压缩**：剖析了从正则表达式经过 Thompson 构造、子集构造法到 Hopcroft 最小化 DFA 的完整数学模型，并引入行位移表压缩技术消除了稀疏矩阵的内存开销。
3. **工业级手写扫描**：解析了手写词法分析器在复杂错误恢复与多模式切换中的工程优势，结合无分支静态位掩码分类表与 AVX2 向量化跳步，实现了极高的分词吞吐率。
4. **最长匹配与二义性消除**：深入探讨了 Maximal Munch 贪心匹配原则在嵌套模板、浮点范围及预处理数字中的冲突场景与消歧策略，解构了上下文感知词法器的状态机协作机制。
5. **Trivia 体系与无损语法树**：剖析了现代语言服务器架构中 Leading/Trailing Trivia 的物理切分拓扑，支撑了代码 100% 字节级无损重构能力。
6. **局部错误恢复**：构建了针对未闭合字面量与非法控制字符的行逃生与单字节隔离防线。

在词法分析器将连续字符流稳定转化为离散的 Token 序列之后，编译前端将进入语法结构的组织与层次化构建阶段。在下一章 **形式文法与递归下降解析：产生式规则、左递归消除、回溯抑制与上下文相关文法处理（03_grammars_and_recursive_descent_parsing.rst）** 中，我们将深入剖析上下文无关文法（CFG）、BNF 范式、递归下降解析器的高性能手工编写、LL(k) 预测集构建以及消除文法左递归与回溯的工业实践。
