第014章：Operator Precedence, Associativity, and Ambiguity
=========================================================

核心知识点
----------

* 表达式 parser 的目标是把线性 token stream 收敛成唯一 AST；优先级与结合性是消除结构歧义的核心规则。
* Precedence 表示绑定强度：高优先级操作符先形成更深的子树，例如 ``a - b * c`` 必须先得到 ``Mul(b, c)``。
* Associativity 决定同优先级操作符连续出现时的分组方向；减法通常左结合，赋值和部分指数运算通常右结合。
* 括号通过提前形成一个完整 operand 覆盖默认绑定关系；括号本身可在 AST 中消失，但其分组效果必须保留。
* 优先级只决定 AST 结构，不等同于求值顺序、短路语义、溢出规则或副作用顺序。
* Pratt parsing 用 prefix/infix/postfix 处理器与 binding power 控制递归；operator-precedence parser 或 parser generator 也可用表格和 precedence 声明解决相同问题。

关键路径
--------

``token stream → 解析 operand → 读取 operator → 比较 precedence/binding power → 处理 associativity → 递归形成子表达式 → 返回唯一 AST``。

对 ``a - b * c - d``，先因 ``*`` 优先级更高形成 ``Mul(b, c)``；随后两个 ``-`` 优先级相同，左结合使第一个减法先形成 ``Sub(a, Mul(b, c))``，最终得到 ``Sub(Sub(a, Mul(b, c)), d)``。Pratt parser 中，这一过程表现为不同 operator 的 binding power 和解析右操作数时使用的递归阈值。

概念辨析
--------

* **Precedence vs associativity**：precedence 处理不同优先级操作符竞争；associativity 处理同优先级连续操作符。
* **Precedence vs evaluation order**：AST 的父子关系不自动决定函数调用或副作用的实际先后，求值顺序由语言语义另行规定。
* **Associativity vs mathematical associativity**：语言记号的左/右结合是语法规则；数学或机器运算是否满足结合律是另一问题。
* **普通二元树 vs 比较链**：``x < y <= z`` 在某些语言中是专门 comparison-chain 结构，不能机械按左结合或右结合二元树处理。
* **Pratt parsing vs 分层 grammar**：Pratt 用 binding power 编码关系；分层 grammar 用 ``AddExpr/MulExpr/UnaryExpr`` 等非终结符编码关系，目标相同。

本章结论
--------

表达式 parser 必须把优先级、结合性和特殊链式规则落实成唯一 AST。阅读实现时，应先确认 operand 与 delimiter，再看操作符表或 grammar 层级，随后检查 associativity 和特殊语法，最后核对生成的 AST 是否与语言定义一致。