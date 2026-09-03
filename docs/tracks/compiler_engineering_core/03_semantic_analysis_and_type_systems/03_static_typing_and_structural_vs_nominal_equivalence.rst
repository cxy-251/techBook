====================================================================================================
静态类型系统基石：名义类型 vs 结构类型等价性、子类型多态与类型规则健全性
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 3 模块第 2 节中，编译器完成了多遍扫描架构、基于 Pareto 支配性原则的函数重载决议以及模块依赖有向无环图（DAG）的拓扑定序，将源码中的每一个标识符精确绑定至符号表中的声明条目。然而，符号绑定仅确认了实体的物理存在性与可见性边界。为了确保程序在执行时不会触发非法的内存解引用、指令与操作数位宽失配或未定义行为，编译器前端必须对所有语法树节点施加静态类型系统约束。本章深入剖析名义类型（Nominal Typing）与结构类型（Structural Typing）在编译器内部表示与内存布局上的本质差异、带环递归类型的余归纳（Coinductive）等价性判定算法、基于偏序集与格理论（Lattice）的子类型多态模型、函数参数逆变与返回值协变的数学证明，以及 Wright-Felleisen 框架下类型系统健全性（Soundness = Progress + Preservation）的形式化约束与工程实现。

类型系统的物理本质与编译期程序事实
----------------------------------

在目标机器的硬件物理层面上，CPU 寄存器与物理内存仅处理固定宽度的无类型二进制位序列（如 8-bit、16-bit、32-bit、64-bit 机器字）。硬件算术逻辑单元（ALU）依靠操作码（Opcode）决定如何解释这些位模式，例如 x86-64 架构中的 ``ADD`` 指令执行二进制补码加法，而 ``ADDSS`` 指令执行单精度 IEEE 754 浮点加法。

静态类型系统是编译器在编译期构建的抽象逻辑层，其核心功能是为源码中的每个表达式、变量与函数调用赋予形式化类型事实（Type Facts），并建立一套机械化推导规则，在代码生成之前验证全部操作在语义和物理上的合法性。

类型系统在编译器中的数据流向与职责边界
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在现代编译器前端中，类型系统贯穿语义分析与中端中间表示（IR）生成的全流程：

1. **操作合法性过滤**：验证特定操作符或函数调用是否在给定的操作数类型集合上存在良定义（Well-Defined）的行为。例如，禁止对函数指针执行浮点乘法操作。
2. **内存几何尺寸推导**：依据类型定义计算变量在栈帧（Stack Slot）或全局数据段中占用的精确字节数（Size）与内存对齐边界（Alignment），生成结构体字段访问的基址偏移量（Offset）。
3. **指令选择指导**：在将 AST 降级为中间表示（如 LLVM IR / 三地址码）时，根据类型事实映射到底层物理数据类型（如将源码级整数映射为 ``i32`` 或 ``i64``，将对象引用映射为目标平台指针类型 ``ptr``）。
4. **别名分析与优化假设**：基于强类型语言的基于类型别名分析（Type-Based Alias Analysis, TBAA）规则，向优化器提供内存访问无冲突的证明，使编译器能够合法地重排内存加载与存储指令。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                  类型事实从 AST 到目标机器码的编译期演进流转                |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 源码 AST 表达式 ] : BinaryExpr( '+', Var(a), Var(b) )                   |
   |            |                                                                |
   |            v                                                                |
   |   [ 语义类型检查器 (Type Checker) ]                                         |
   |     - 查询符号表: Type(a) = i32, Type(b) = i32                              |
   |     - 匹配类型规则: (i32, i32) -> i32                                       |
   |     - 产出类型事实: ExprType = i32                                          |
   |            |                                                                |
   |            v                                                                |
   |   [ 中间表示生成 (IR Lowering) ]                                            |
   |     - 选择强类型 IR 指令: %sum = add i32 %a, %b                             |
   |     - 附加 TBAA 元数据标签: !tbaa !int_type_tag                             |
   |            |                                                                |
   |            v                                                                |
   |   [ 后端指令选择 (Instruction Selection) ]                                  |
   |     - 映射物理寄存器: %a -> %edi, %b -> %esi                                |
   |     - 发射目标机器汇编: addl %esi, %edi                                     |
   |                                                                             |
   +-----------------------------------------------------------------------------+

名义类型等价性 vs 结构类型等价性
--------------------------------

类型等价性（Type Equivalence）回答编译器的核心判定问题：在给定的类型环境 $\Gamma$ 下，类型表达式 $	au_1$ 与 $	au_2$ 是否代表同一个类型（即 $	au_1 \equiv 	au_2$）。编译器设计领域存在两种截然不同的等价性判定范式：名义类型（Nominal Typing）与结构类型（Structural Typing）。

名义类型等价性（Nominal Equivalence）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

名义类型系统将类型的唯一标识绑定至类型声明语句的显式名字（Identifier）及其命名空间全限定路径。即使两个类型在内存几何布局、成员字段名称、字段类型及其声明顺序上完全相同，只要它们由不同的声明语句引入，编译器即判定二者为完全不同的互不兼容类型。

- **代表语言**：C++、Java、Rust、C#、Swift。
- **编译器内部表示**：每个名义类型在类型池（Type Pool）中具有唯一的内存地址（``NominalTypeEntry*``）或全局唯一的数值 ID（``TypeId``）。
- **等价性判定时间复杂度**：$O(1)$。编译器仅需比对两个类型对象的内存指针值是否相等：

.. code-block:: cpp

   bool isNominalEquivalent(const Type *t1, const Type *t2) {
       return t1 == t2; // 指针全局唯一化 (Type Interning)
   }

- **内存排布与 ABI 契约**：名义类型要求在编译期确定其完整的内存物理布局。编译器通过固定的字段偏移量生成直接的基址加变址寻址指令（如 ``MOVQ 8(%rax), %rbx``），字段访问零运行时查找开销。

结构类型等价性（Structural Equivalence）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

结构类型系统将类型的等价性建立在其组成结构的同构性之上。如果两个类型包含相同名称、相同类型的成员字段集合，且字段满足相同的访问约束，编译器即判定二者等价，无论其在源码中被赋予何种类型别名或声明名称。

- **代表语言**：TypeScript、Go（接口实现判定）、OCaml（对象系统）、Zig（匿名结构体）。
- **编译器内部表示**：结构类型表现为一棵类型结构树或有向图（Directed Graph）。结构节点（``RecordType``）包含一个按字典序排序或哈希映射的成员列表 ``{ field_name: Type* }``。
- **等价性判定算法**：递归遍历两棵类型结构图，验证所有对应字段的名称与类型是否一一等价。
- **内存排布与 ABI 挑战**：在结构类型系统中，两个在源码中结构兼容的对象可能在内存中具有不同的字段偏移排列。例如对象 $A$ 的字段顺序为 ``{x: i32, y: f64}``，而对象 $B$ 的字段顺序为 ``{y: f64, x: i32}``。若允许结构等价直接互相赋值，直接按偏移寻址将导致内存解释错乱。因此，结构类型语言在后端通常采用以下三种工程策略之一：
  1. **字段对齐规范化（Canonical Field Ordering）**：强制所有结构类型在前端按字段名 ASCII 字典序重排内存偏移。
  2. **胖指针与接口方法表（Fat Pointers & Itables）**：如 Go 语言的 ``interface``，由数据指针与类型元数据字典组成双字结构（16 字节），通过运行时元数据查找字段偏移或方法分发地址。
  3. **单态化生成特化代码（Monomorphization / Dictionary Passing）**：在调用点针对具体内存布局生成特化的访问代码。

.. list-table:: 名义类型与结构类型核心机制全方位对比
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 维度
     - 名义类型系统 (Nominal Typing)
     - 结构类型系统 (Structural Typing)
   * - 等价判定基准
     - 显式声明的符号名称与声明路径 (TypeId)
     - 成员字段的名称、类型、修饰符拓扑结构
   * - 编译期检查复杂度
     - $O(1)$ 指针/ID 比对，开销极低
     - $O(|V| + |E|)$ 图遍历与余归纳比对
   * - 重构安全性
     - 极高，意外同构的类型不会发生隐式赋值混淆
     - 较高，但可能由于字段命名巧合导致非预期类型匹配
   * - 内存寻址模型
     - 编译期硬编码固定字段偏移量 (Fixed Offset)
     - 依赖字典序规范排布、胖指针虚表或字典传递
   * - 循环引用处理
     - 基于类型声明的不完整指针天然解耦
     - 必须采用带记忆化集合的余归纳定点算法
   * - 典型代表实现
     - Clang (C/C++), Rustc, HotSpot JVM
     - TypeScript Compiler (tsc), Go gc (interface)

带环递归结构类型的余归纳 (Coinductive) 等价性判定
-------------------------------------------------

在实际编程语言中，数据类型经常包含自引用或相互引用的环状拓扑（如链表节点、抽象语法树节点或图数据结构）：

.. code-block:: text

   type NodeA = { value: i32, next: Pointer(NodeA) }
   type NodeB = { value: i32, next: Pointer(NodeB) }

若采用朴素的递归算法判定 ``NodeA`` 与 ``NodeB`` 是否结构等价，算法在展开 ``next`` 字段时将陷入无限递归并导致编译器调用栈溢出（Stack Overflow）。

余归纳（Coinduction）判定模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

编译器通过构造余归纳假设集合（Coinductive Hypothesis Set）解决环状类型判定问题。余归纳的基本数学原理是：**在未能证明两个类型不等价之前，先假设它们等价**。

算法维护一个正在验证的类型对假设集合 $\mathcal{H} = \{ (	au_i, 	au_j) \}$：
1. 当进入判定函数 ``isEqual(	au_1, 	au_2)`` 时，首先检查对 $(	au_1, 	au_2)$ 是否已经存在于集合 $\mathcal{H}$ 中。
2. 若 $(	au_1, 	au_2) \in \mathcal{H}$，说明当前遍历路径已经形成闭环且在此环路上尚未发现任何结构冲突，直接返回 ``true``。
3. 若 $(	au_1, 	au_2) 
otin \mathcal{H}$，将 $(	au_1, 	au_2)$ 加入 $\mathcal{H}$ 中。
4. 逐项递归检查 $	au_1$ 与 $	au_2$ 的各子成分类型（如所有字段的类型与返回值类型）：
   - 若所有子成分均递归返回 ``true``，则判定 $	au_1 \equiv 	au_2$ 成立。
   - 若任意子成分返回 ``false``，将 $(	au_1, 	au_2)$ 从 $\mathcal{H}$ 中移除（或标记为不兼容），返回 ``false``。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |               余归纳带环结构类型等价性判定状态机 (Coinductive Trace)         |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   待判定: NodeA == NodeB                                                    |
   |     NodeA = { val: i32, next: Ptr(NodeA) }                                  |
   |     NodeB = { val: i32, next: Ptr(NodeB) }                                  |
   |                                                                             |
   |   [ 步 1 ]: 检查 (NodeA, NodeB) 是否在假设集 H 中 -> 否                      |
   |             将 (NodeA, NodeB) 加入 H = { (NodeA, NodeB) }                   |
   |                                                                             |
   |   [ 步 2 ]: 比较字段 "val": Type(i32) == Type(i32) -> 成立                  |
   |                                                                             |
   |   [ 步 3 ]: 比较字段 "next": Ptr(NodeA) == Ptr(NodeB)                       |
   |             解引用进入目标类型比较: NodeA == NodeB                          |
   |                                                                             |
   |   [ 步 4 ]: 再次检查 (NodeA, NodeB) 是否在假设集 H 中                        |
   |             命中已存在假设 (NodeA, NodeB) in H -> 判定成立, 返回 true        |
   |                                                                             |
   |   [ 步 5 ]: 所有字段验证通过 -> 算法收敛, 结论: NodeA 结构等价于 NodeB       |
   |                                                                             |
   +-----------------------------------------------------------------------------+

子类型多态（Subtyping）与类型格（Type Lattice）
-----------------------------------------------

子类型关系（Subtyping Relation）是面向对象与高级函数式语言中实现多态的核心机制。形式化地，若类型 $S$ 是类型 $T$ 的子类型，记作 $S \le T$，则意味着任何期望接收类型 $T$ 的值的上下文，都可以安全地接收类型 $S$ 的值（Liskov 替换原则在类型系统的形式化表达）。

子类型偏序关系公理
~~~~~~~~~~~~~~~~~~

子类型关系在类型集合上构成一个数学上的偏序关系（Partial Order），必须严格满足以下三条公理：

1. **自反性（Reflexivity）**：
   $$\forall T, \quad T \le T$$
2. **传递性（Transitivity）**：
   $$\forall S, T, U, \quad (S \le T \land T \le U) \implies S \le U$$
3. **反对称性（Antisymmetry）**：
   $$\forall S, T, \quad (S \le T \land T \le S) \implies S \equiv T$$

类型格（Type Lattice）拓扑
~~~~~~~~~~~~~~~~~~~~~~~~~~

现代类型系统通常将整个类型空间组织为一个有界格（Bounded Lattice）：

- **顶类型（Top Type, $	op$）**：格的最顶端元素。所有其他类型均为顶类型的子类型（$\forall T, T \le 	op$）。在 TypeScript 中对应 ``unknown``，在 Java 中对应 ``java.lang.Object``（针对引用类型），在 C# 中对应 ``object``。
- **底类型（Bottom Type, $\bot$）**：格的最底端元素。底类型是所有其他类型的子类型（$\forall T, \bot \le T$）。底类型不包含任何运行时正常值，用于表示不返回的计算（如死循环、必定抛出异常的函数或不可达分支）。在 Rust 中对应 ``!``（Never Type），在 TypeScript 中对应 ``never``，在 LLVM IR 中对应 ``noreturn`` 属性。
- **最小上界（Join / Least Upper Bound, $\sqcup$）**：给定类型 $A$ 和 $B$，$A \sqcup B$ 是同时作为 $A$ 和 $B$ 超类型的最小类型。对应条件表达式 ``cond ? exprA : exprB`` 的公共提升类型。
- **最大下界（Meet / Greatest Lower Bound, $\sqcap$）**：给定类型 $A$ 和 $B$，$A \sqcap B$ 是同时作为 $A$ 和 $B$ 子类型的最大类型。对应交叉类型（Intersection Type） $A \ \& \ B$。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        标准有界类型格 (Bounded Type Lattice)                |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |                             Top Type (Top, unknown)                         |
   |                                  /           \                              |
   |                                 /             \                             |
   |                          Number                String                       |
   |                          /    \                  |                          |
   |                       Float   Integer        ConstString                    |
   |                         \      /                 |                          |
   |                          \    /                  |                          |
   |                         Float & Int              |                          |
   |                                 \               /                           |
   |                                  \             /                            |
   |                            Bottom Type (Bottom, never)                      |
   |                                                                             |
   +-----------------------------------------------------------------------------+

型变（Variance）：协变、逆变与不变性
------------------------------------

当基础类型通过复合构造器（如容器 ``List<T>``、指针 ``Pointer<T>``、引用 ``Ref<T>`` 或函数类型 $T_1 	o T_2$）组合成新类型时，复合类型之间的子类型关系如何随子成分的子类型关系发生迁移，由 **型变（Variance）** 规则严格约束。

设 $F$ 为一个类型构造器，若已知 $S \le T$：
- **协变（Covariance）**：若 $F(S) \le F(T)$，称 $F$ 关于其参数是协变的。
- **逆变（Contravariance）**：若 $F(T) \le F(S)$，称 $F$ 关于其参数是逆变的（子类型方向发生反转）。
- **不变（Invariance）**：若仅在 $S \equiv T$ 时才有 $F(S) \le F(T)$，称 $F$ 关于其参数是不变的。
- **双变（Bivariance）**：若同时存在 $F(S) \le F(T)$ 与 $F(T) \le F(S)$，称 $F$ 为双变的（通常会破坏类型健全性）。

函数类型的子类型定理（Function Subtyping Rule）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

函数类型构造器 $(T_{	ext{arg}} 	o T_{	ext{ret}})$ 是理解型变的核心模型。

.. admonition:: 函数子类型核心定理
   设有两个函数类型 $F_1 = (A 	o B)$ 与 $F_2 = (A' 	o B')$。
   则 $F_1 \le F_2$ 成立，当且仅当满足：
   $$A' \le A \quad (	ext{参数位置逆变}) \quad \land \quad B \le B' \quad (	ext{返回值位置协变})$$

**数学与物理证明**：
1. **返回值协变证明 ($B \le B'$)**：调用点期望获取一个类型为 $B'$ 的计算结果。如果函数 $F_1$ 产生的是 $B$ 类型的对象，由于 $B \le B'$，根据 Liskov 替换原则，调用点可以安全地将 $B$ 当作 $B'$ 使用。因此返回值方向保持一致的子类型关系（协变）。
2. **参数位置逆变证明 ($A' \le A$)**：调用点持有的实参类型为 $A'$。当调用点将该实参传递给函数 $F_1$ 时，$F_1$ 的函数体实现要求入参必须满足类型 $A$ 的所有约束。为了确保传递的实参合法，传入的实际对象 $A'$ 必须能够满足 $A$ 的要求，即必须有 $A' \le A$。因此，函数类型在形参位置上的子类型方向与整体函数子类型方向严格相反（逆变）。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                    函数参数逆变与返回值协变的物理数据流                     |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   调用点期待的函数契约 F2: (Animal) -> Object                                |
   |   实际提供的函数实现 F1: (Object) -> Dog                                    |
   |                                                                             |
   |   已知子类型继承关系: Dog <= Animal <= Object                                |
   |                                                                             |
   |   数据流 1 (实参传入):                                                      |
   |     调用点传入实参: x = new Animal()                                         |
   |     函数 F1 形参接收: param: Object                                         |
   |     合法性验证: Animal <= Object (实参 Dog/Animal 均可作为 Object 传入)       |
   |     -> 形参位置要求 F1 形参类型比 F2 形参类型更宽 (Object >= Animal, 逆变)   |
   |                                                                             |
   |   数据流 2 (结果返回):                                                      |
   |     函数 F1 内部执行产出: return new Dog()                                   |
   |     调用点接收返回值: res: Object                                           |
   |     合法性验证: Dog <= Object (产出的 Dog 满足接收方 Object 约束)            |
   |     -> 返回值位置要求 F1 返回类型比 F2 返回类型更窄 (Dog <= Object, 协变)    |
   |                                                                             |
   |   结论: (Object -> Dog) <= (Animal -> Object)                               |
   |                                                                             |
   +-----------------------------------------------------------------------------+

可变引用（Mutable References）的不变性定理
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在包含可变状态的内存模型中，指针或可变引用类型 ``Ref<T>`` 必须强制规定为 **不变（Invariant）**。

假设允许可变引用协变（即若 $	ext{Dog} \le 	ext{Animal}$，则允许 $	ext{Ref}\langle	ext{Dog}\rangle \le 	ext{Ref}\langle	ext{Animal}\rangle$）：
1. 声明变量 ``dogRef: Ref<Dog>``，指向真实的堆分配 ``Dog`` 内存空间。
2. 协变赋值：令 ``animalRef: Ref<Animal> = dogRef``。此时两个引用指向同一块物理内存。
3. 写入操作：执行 ``*animalRef = new Cat()``（因为 ``Cat`` 是 ``Animal`` 的子类型，写入合法）。
4. 读取操作：原代码继续通过 ``dogRef->bark()`` 访问该对象。
5. **硬件后果**：CPU 执行至 ``dogRef->bark()`` 时，将内存中的 ``Cat`` 虚表指针解释为 ``Dog`` 虚表，调用错误的内存偏移地址，引发非法内存越界访问或进程崩溃（SIGSEGV）。

.. list-table:: 复合类型构造器的型变属性及其物理安全性边界
   :widths: 20 20 60
   :header-rows: 1
   :class: tight-table

   * - 复合类型构造器
     - 型变特征
     - 物理安全性保证与约束成因
   * - 只读容器 / 迭代器 ``ReadOnlyList<T>``
     - 协变 (Covariant)
     - 仅提供读取接口（输出数据），元素类型向上收窄满足使用方约束
   * - 只写通道 / 消费者 ``Consumer<T>``
     - 逆变 (Contravariant)
     - 仅提供写入接口（输入数据），要求接收方具备更宽泛的处理能力
   * - 可读写引用 / 数组 ``Array<T>`` / ``Ref<T>``
     - 不变 (Invariant)
     - 同时支持读取（要求协变）与写入（要求逆变），数学交集仅允许严格等价
   * - 函数类型 ``(Arg) -> Ret``
     - 参数逆变，返回协变
     - 保证调用点实参传递与函数体返回值解引用的双向安全契约

类型系统的健全性证明框架：Progress 与 Preservation
---------------------------------------------------

编译器静态类型系统的核心理论基石是 **健全性（Soundness）**。1994 年，Wright 与 Felleisen 提出了基于操作语义（Operational Semantics）的经典证明框架，将类型健全性等价于两个核心定理：**进展定理（Progress）** 与 **保持定理（Preservation / Subject Reduction）**。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |             Wright-Felleisen 静态类型系统健全性证明核心模型                 |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 进展定理 (Progress) ]                                                   |
   |   良类型表达式不会卡住:                                                     |
   |   若 |- e : T, 则 e 已经是一个值 (Value), 或者存在 e' 使得 e -> e'          |
   |                                                                             |
   |   [ 保持定理 (Preservation / Subject Reduction) ]                           |
   |   表达式小步规约保持类型不变:                                               |
   |   若 |- e : T 且 e -> e', 则必然有 |- e' : T                                |
   |                                                                             |
   |   [ 联合推论: 类型健全性 (Type Soundness) ]                                 |
   |   Well-typed programs cannot go wrong!                                      |
   |   良类型程序绝不会陷入未定义的卡住状态 (Stuck State / Trap / Memory Fault)  |
   |                                                                             |
   +-----------------------------------------------------------------------------+

进展定理（Progress Theorem）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

形式化定义：设 $e$ 是一个在空类型环境 $\emptyset$ 下良类型的闭合表达式（Closed Term），即 $\vdash e : 	au$。则 $e$ 必然满足以下两个条件之一：
1. $e$ 已经是一个终态值（Value，如字面量或已完成构造的 lambda 抽象）。
2. 存在合法的单步操作语义转换（Step Transition），使得 $e 	o e'$。

**物理含义**：通过静态类型检查的代码，在运行期间的每一步求值过程中，操作数均满足当前指令所期望的形态，绝不会出现“尝试将整数作为函数进行调用”或“对空指针解引用”等陷入无法继续执行的死锁/非法硬件陷阱状态（Stuck State）。

保持定理（Preservation / Subject Reduction）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

形式化定义：设在类型环境 $\Gamma$ 下，表达式 $e$ 具有类型 $	au$（即 $\Gamma \vdash e : 	au$）。若 $e$ 经过单步求值规约转换为 $e'$（即 $e 	o e'$），则在相同的类型环境 $\Gamma$ 下，$e'$ 依然具有完全相同的类型 $	au$：
$$\Gamma \vdash e : 	au \quad \land \quad e 	o e' \implies \Gamma \vdash e' : 	au$$

**物理含义**：程序在运行执行过程中的状态突变（State Transition）与表达式化简，不会破坏编译期推导出的类型事实。中间状态生成的值始终处于预期的内存空间与寄存器边界内。

类型系统非健全性漏洞（Unsoundness Holes）与工程代价
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当类型系统的规则设计存在漏洞导致 Progress 或 Preservation 被破坏时，该类型系统即被称为非健全的（Unsound）。非健全性将导致编译器中端优化的假设崩溃：

1. **C/C++ 的任意指针类型强转（Unchecked Pointer Cast）**：允许将任意整数强转为指针或在互不相关的类型指针间强转（破坏 Preservation）。优化器依据 TBAA 假设两指针不发生别名，将其加载指令重排，最终产生脏读错误。
2. **Java 早期数组协变（Array Covariance）**：Java 允许 ``String[]`` 隐式转换为 ``Object[]``。为防止写入非法对象，JVM 必须在每一次数组存储指令（``AASTORE``）中插入昂贵的运行时动态类型检查（``ArrayStoreException``），以运行时性能惩罚弥补静态类型系统的不健全。
3. **TypeScript 的 ``any`` 与方法参数双变（Bivariant Method Parameters）**：为适配 JavaScript 历史遗留生态主动放弃了严格健全性，导致编译通过的代码在运行时依然可能抛出 ``TypeError: undefined is not a function``。

工业级 C++ 静态类型检查与等价性判定引擎实现
--------------------------------------------

以下提供一套完整的工业级 C++ 静态类型分析核心引擎。代码涵盖：
1. 类型池管理与名义类型指针唯一化（Interning）。
2. 结构类型（Record Type）的规范化与带假设集的余归纳（Coinductive）等价性判定。
3. 遵循参数逆变、返回值协变规则的函数子类型（Function Subtyping）验证器。
4. 类型格（Type Lattice）最小上界（Join）计算与全量类型规则检查。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <string>
   #include <string_view>
   #include <vector>
   #include <unordered_map>
   #include <unordered_set>
   #include <memory>
   #include <algorithm>
   #include <cstdint>
   #include <cassert>
   #include <sstream>

   // 类型类别枚举
   enum class TypeKind : uint8_t {
       Top,          // 顶类型 (unknown / Object)
       Bottom,       // 底类型 (never / noreturn)
       Primitive,    // 基础标量类型 (i32, f64, bool)
       Nominal,      // 名义类型 (class / struct by name)
       Structural,   // 结构类型 (record / anonymous struct)
       Pointer,      // 指针类型 (Pointer<T>)
       Function      // 函数类型 ((Args...) -> Ret)
   };

   struct Type;

   // 结构体成员字段描述
   struct StructField {
       std::string Name;
       const Type *FieldType = nullptr;
       uint32_t Offset = 0; // 内存偏移字节

       bool operator==(const StructField &o) const {
           return Name == o.Name && FieldType == o.FieldType;
       }
   };

   // 核心类型节点结构
   struct Type {
       TypeKind Kind;
       std::string Name; // 用于名义类型唯一标识或基础类型名称
       uint32_t Size = 0;
       uint32_t Alignment = 0;

       // 复合类型特化字段
       const Type *Pointee = nullptr;                     // 用于 Pointer
       std::vector<StructField> Fields;                  // 用于 Structural / Nominal
       std::vector<const Type*> ParamTypes;              // 用于 Function
       const Type *ReturnType = nullptr;                 // 用于 Function

       bool isTop() const { return Kind == TypeKind::Top; }
       bool isBottom() const { return Kind == TypeKind::Bottom; }
       bool isPrimitive() const { return Kind == TypeKind::Primitive; }
       bool isStructural() const { return Kind == TypeKind::Structural; }
       bool isNominal() const { return Kind == TypeKind::Nominal; }
       bool isFunction() const { return Kind == TypeKind::Function; }
   };

   // 类型对哈希，用于余归纳假设集
   struct TypePairHash {
       size_t operator()(const std::pair<const Type*, const Type*> &p) const noexcept {
           auto h1 = std::hash<const void*>()(p.first);
           auto h2 = std::hash<const void*>()(p.second);
           return h1 ^ (h2 << 1);
       }
   };

   // 类型池与类型系统核心引擎
   class TypeSystem {
   public:
       TypeSystem() {
           // 初始化全系统单例特殊类型
           TopType = allocateType(TypeKind::Top, "Top", 0, 0);
           BottomType = allocateType(TypeKind::Bottom, "Bottom", 0, 0);
           Int32Type = allocateType(TypeKind::Primitive, "i32", 4, 4);
           Float64Type = allocateType(TypeKind::Primitive, "f64", 8, 8);
           BoolType = allocateType(TypeKind::Primitive, "bool", 1, 1);
       }

       const Type* getTop() const { return TopType; }
       const Type* getBottom() const { return BottomType; }
       const Type* getInt32() const { return Int32Type; }
       const Type* getFloat64() const { return Float64Type; }
       const Type* getBool() const { return BoolType; }

       // 创建名义类型 (Nominal Type)
       const Type* createNominalType(const std::string &uniqueName, uint32_t size, uint32_t align) {
           return allocateType(TypeKind::Nominal, uniqueName, size, align);
       }

       // 创建结构类型 (Structural Record Type, 自动按字段名字典序规范化)
       const Type* createStructuralType(std::vector<StructField> fields) {
           std::sort(fields.begin(), fields.end(), [](const StructField &a, const StructField &b) {
               return a.Name < b.Name;
           });

           // 计算内存对齐与布局
           uint32_t currentOffset = 0;
           uint32_t maxAlign = 1;
           for (auto &f : fields) {
               assert(f.FieldType != nullptr);
               uint32_t fieldAlign = f.FieldType->Alignment > 0 ? f.FieldType->Alignment : 1;
               maxAlign = std::max(maxAlign, fieldAlign);
               // 填充对齐空隙
               if (currentOffset % fieldAlign != 0) {
                   currentOffset += (fieldAlign - (currentOffset % fieldAlign));
               }
               f.Offset = currentOffset;
               currentOffset += f.FieldType->Size;
           }
           // 尾部结构体对齐补齐
           if (maxAlign > 0 && currentOffset % maxAlign != 0) {
               currentOffset += (maxAlign - (currentOffset % maxAlign));
           }

           auto *t = allocateType(TypeKind::Structural, "{...}", currentOffset, maxAlign);
           t->Fields = std::move(fields);
           return t;
       }

       // 创建指针类型
       const Type* createPointerType(const Type *pointee) {
           assert(pointee != nullptr);
           auto *t = allocateType(TypeKind::Pointer, "Ptr", 8, 8);
           t->Pointee = pointee;
           return t;
       }

       // 创建函数类型
       const Type* createFunctionType(std::vector<const Type*> params, const Type *ret) {
           assert(ret != nullptr);
           auto *t = allocateType(TypeKind::Function, "Fn", 8, 8);
           t->ParamTypes = std::move(params);
           t->ReturnType = ret;
           return t;
       }

       // =====================================================================
       // 1. 类型等价性判定 (Type Equivalence)
       // =====================================================================
       bool isEquivalent(const Type *t1, const Type *t2) {
           std::unordered_set<std::pair<const Type*, const Type*>, TypePairHash> coinductiveHypotheses;
           return checkEquivalenceCoinductive(t1, t2, coinductiveHypotheses);
       }

       // =====================================================================
       // 2. 子类型判定: S <= T (Subtyping with Variance & Coinduction)
       // =====================================================================
       bool isSubtypeOf(const Type *sub, const Type *super) {
           std::unordered_set<std::pair<const Type*, const Type*>, TypePairHash> coinductiveHypotheses;
           return checkSubtypeCoinductive(sub, super, coinductiveHypotheses);
       }

       // =====================================================================
       // 3. 最小上界计算: A Join B (Least Upper Bound in Type Lattice)
       // =====================================================================
       const Type* computeJoin(const Type *t1, const Type *t2) {
           if (isSubtypeOf(t1, t2)) return t2;
           if (isSubtypeOf(t2, t1)) return t1;
           return TopType; // 无法收敛时提升至顶类型
       }

   private:
       Type* allocateType(TypeKind kind, const std::string &name, uint32_t size, uint32_t align) {
           AllocatedTypes.push_back(std::make_unique<Type>());
           Type *t = AllocatedTypes.back().get();
           t->Kind = kind;
           t->Name = name;
           t->Size = size;
           t->Alignment = align;
           return t;
       }

       // 余归纳结构等价性核心递归实现
       bool checkEquivalenceCoinductive(const Type *t1, const Type *t2,
                                        std::unordered_set<std::pair<const Type*, const Type*>, TypePairHash> &hypotheses) {
           if (t1 == t2) return true;
           if (!t1 || !t2) return false;
           if (t1->Kind != t2->Kind) return false;

           // 检查余归纳假设缓存，防止带环结构无限递归
           auto pair = std::make_pair(t1, t2);
           if (hypotheses.count(pair)) return true;
           hypotheses.insert(pair);

           switch (t1->Kind) {
               case TypeKind::Top:
               case TypeKind::Bottom:
               case TypeKind::Primitive:
                   return t1->Name == t2->Name;

               case TypeKind::Nominal:
                   // 名义类型强制严格比对全局唯一声明标识符
                   return t1->Name == t2->Name;

               case TypeKind::Pointer:
                   return checkEquivalenceCoinductive(t1->Pointee, t2->Pointee, hypotheses);

               case TypeKind::Structural: {
                   // 结构类型要求所有字段数量、名称及类型一一对应
                   if (t1->Fields.size() != t2->Fields.size()) return false;
                   for (size_t i = 0; i < t1->Fields.size(); ++i) {
                       if (t1->Fields[i].Name != t2->Fields[i].Name) return false;
                       if (!checkEquivalenceCoinductive(t1->Fields[i].FieldType, t2->Fields[i].FieldType, hypotheses)) {
                           return false;
                       }
                   }
                   return true;
               }

               case TypeKind::Function: {
                   if (t1->ParamTypes.size() != t2->ParamTypes.size()) return false;
                   for (size_t i = 0; i < t1->ParamTypes.size(); ++i) {
                       if (!checkEquivalenceCoinductive(t1->ParamTypes[i], t2->ParamTypes[i], hypotheses)) {
                           return false;
                       }
                   }
                   return checkEquivalenceCoinductive(t1->ReturnType, t2->ReturnType, hypotheses);
               }
           }
           return false;
       }

       // 余归纳子类型判定实现
       bool checkSubtypeCoinductive(const Type *sub, const Type *super,
                                    std::unordered_set<std::pair<const Type*, const Type*>, TypePairHash> &hypotheses) {
           if (sub == super) return true;
           if (!sub || !super) return false;

           // 格理论公理: 任何类型都是 Top 的子类型，Bottom 是任何类型的子类型
           if (super->isTop()) return true;
           if (sub->isBottom()) return true;
           if (sub->isTop() && !super->isTop()) return false;
           if (super->isBottom() && !sub->isBottom()) return false;

           auto pair = std::make_pair(sub, super);
           if (hypotheses.count(pair)) return true;
           hypotheses.insert(pair);

           // 基础标量类型仅在完全等价时成立子类型关系
           if (sub->isPrimitive() && super->isPrimitive()) {
               return sub->Name == super->Name;
           }

           // 名义类型需显式等价 (本实现未扩展继承链，故等价于名字一致)
           if (sub->isNominal() && super->isNominal()) {
               return sub->Name == super->Name;
           }

           // 指针类型子类型关系 (指针默认保持不变性 Invariant 以保证内存安全)
           if (sub->Kind == TypeKind::Pointer && super->Kind == TypeKind::Pointer) {
               return checkEquivalenceCoinductive(sub->Pointee, super->Pointee, hypotheses);
           }

           // 结构类型宽度子类型 (Width Subtyping): sub 必须包含 super 的所有字段，且字段类型协变
           if (sub->isStructural() && super->isStructural()) {
               for (const auto &superField : super->Fields) {
                   auto it = std::find_if(sub->Fields.begin(), sub->Fields.end(),
                                          [&](const StructField &sf) { return sf.Name == superField.Name; });
                   if (it == sub->Fields.end()) return false; // 缺少必需字段
                   // 深度子类型检查
                   if (!checkSubtypeCoinductive(it->FieldType, superField.FieldType, hypotheses)) {
                       return false;
                   }
               }
               return true;
           }

           // 函数子类型: 参数位置逆变 (Contravariant), 返回值位置协变 (Covariant)
           if (sub->isFunction() && super->isFunction()) {
               if (sub->ParamTypes.size() != super->ParamTypes.size()) return false;
               for (size_t i = 0; i < sub->ParamTypes.size(); ++i) {
                   // 逆变验证: superParam <= subParam
                   if (!checkSubtypeCoinductive(super->ParamTypes[i], sub->ParamTypes[i], hypotheses)) {
                       return false;
                   }
               }
               // 协变验证: subRet <= superRet
               return checkSubtypeCoinductive(sub->ReturnType, super->ReturnType, hypotheses);
           }

           return false;
       }

       const Type *TopType;
       const Type *BottomType;
       const Type *Int32Type;
       const Type *Float64Type;
       const Type *BoolType;
       std::vector<std::unique_ptr<Type>> AllocatedTypes;
   };

   // =========================================================================
   // 端到端验证主程序
   // =========================================================================
   int main() {
       TypeSystem ts;

       std::cout << "========================================================================
";
       std::cout << "现代编译器静态类型系统、结构/名义等价性与型变规则验证引擎
";
       std::cout << "========================================================================

";

       // 1. 测试名义类型等价性 (Nominal Typing)
       std::cout << ">>> [测试 1] 名义类型等价性验证 (Nominal Typing)
";
       const Type *userId = ts.createNominalType("UserId", 4, 4);
       const Type *orderId = ts.createNominalType("OrderId", 4, 4);
       const Type *userIdAlias = userId; // 指向同一内存条目

       std::cout << "UserId == UserIdAlias: " << (ts.isEquivalent(userId, userIdAlias) ? "true (等价)" : "false") << "
";
       std::cout << "UserId == OrderId (内存布局相同但名称不同): " 
                 << (ts.isEquivalent(userId, orderId) ? "true" : "false (名义隔离拦截成功)") << "

";

       // 2. 测试结构类型与余归纳带环递归等价性 (Structural Typing & Coinduction)
       std::cout << ">>> [测试 2] 结构类型等价性与余归纳自引用环路验证
";
       // 构造类型 NodeA = { val: i32, next: Ptr(NodeA) }
       auto *nodeAType = const_cast<Type*>(ts.createStructuralType({{"val", ts.getInt32()}}));
       const Type *ptrNodeA = ts.createPointerType(nodeAType);
       nodeAType->Fields.push_back({"next", ptrNodeA, 8});
       nodeAType->Size = 16;

       // 构造类型 NodeB = { val: i32, next: Ptr(NodeB) }
       auto *nodeBType = const_cast<Type*>(ts.createStructuralType({{"val", ts.getInt32()}}));
       const Type *ptrNodeB = ts.createPointerType(nodeBType);
       nodeBType->Fields.push_back({"next", ptrNodeB, 8});
       nodeBType->Size = 16;

       bool structEq = ts.isEquivalent(nodeAType, nodeBType);
       std::cout << "递归自引用结构体 NodeA == NodeB 余归纳等价性判定: " 
                 << (structEq ? "true (判定成功收敛)" : "false") << "

";

       // 3. 测试结构类型宽度子类型 (Width Subtyping)
       std::cout << ">>> [测试 3] 结构类型宽度子类型多态判定 (Width Subtyping)
";
       // Point2D = { x: i32, y: i32 }
       const Type *point2D = ts.createStructuralType({
           {"x", ts.getInt32()},
           {"y", ts.getInt32()}
       });
       // Point3D = { x: i32, y: i32, z: i32 }
       const Type *point3D = ts.createStructuralType({
           {"x", ts.getInt32()},
           {"y", ts.getInt32()},
           {"z", ts.getInt32()}
       });

       std::cout << "Point3D <= Point2D (多字段类型作为少字段类型的子类型): " 
                 << (ts.isSubtypeOf(point3D, point2D) ? "true (满足替换原则)" : "false") << "
";
       std::cout << "Point2D <= Point3D: " 
                 << (ts.isSubtypeOf(point2D, point3D) ? "true" : "false (正确拦截字段缺失)") << "

";

       // 4. 测试函数类型的型变规则: 参数逆变 (Contravariant) 与 返回值协变 (Covariant)
       std::cout << ">>> [测试 4] 函数子类型型变定理验证 (参数逆变 & 返回值协变)
";
       // 函数 F1: (Point2D) -> Point3D
       const Type *funcF1 = ts.createFunctionType({point2D}, point3D);
       // 函数 F2: (Point3D) -> Point2D
       const Type *funcF2 = ts.createFunctionType({point3D}, point2D);

       // 理论推导:
       // 要证 F1 <= F2，需满足:
       //   1. 形参逆变: F2.param (Point3D) <= F1.param (Point2D) -> 成立 (测试3已证)
       //   2. 返回值协变: F1.ret (Point3D) <= F2.ret (Point2D) -> 成立 (测试3已证)
       // 因此 F1 是 F2 的合法子类型！
       bool funcSubtype = ts.isSubtypeOf(funcF1, funcF2);
       std::cout << "((Point2D) -> Point3D) <= ((Point3D) -> Point2D): " 
                 << (funcSubtype ? "true (型变定理数学验证成立)" : "false") << "
";

       bool funcReverseSubtype = ts.isSubtypeOf(funcF2, funcF1);
       std::cout << "((Point3D) -> Point2D) <= ((Point2D) -> Point3D): " 
                 << (funcReverseSubtype ? "true" : "false (正确拦截型变反向违规)") << "

";

       // 5. 测试类型格 Top / Bottom 与 Join 运算
       std::cout << ">>> [测试 5] 类型格 (Type Lattice) 最小上界 Join 计算
";
       const Type *joinPoint = ts.computeJoin(point3D, point2D);
       std::cout << "Join(Point3D, Point2D) 计算结果: " << joinPoint->Name 
                 << " (成功提升至公共超类型 Point2D 结构)
";

       const Type *joinDisjoint = ts.computeJoin(point2D, ts.getInt32());
       std::cout << "Join(Point2D, i32) 计算结果: " << joinDisjoint->Name 
                 << " (无公共基类时提升至 Top 类型)
";

       return 0;
   }

程序输出验证分析
~~~~~~~~~~~~~~~~

执行上述 C++ 引擎，输出结果严格验证了类型系统的核心数学推导与工程实现：

1. **名义隔离机制**：``UserId`` 与 ``OrderId`` 虽具备相同的物理位宽与对齐尺寸，但指针地址不同，引擎直接在 $O(1)$ 时间内拦截非法赋值。
2. **余归纳带环收敛**：对于自引用的递归结构体 ``NodeA`` 与 ``NodeB``，假设缓存集合精准截断无限递归，成功判定结构同构性。
3. **宽度子类型替换**：具备 3 个字段的 ``Point3D`` 被成功判定为 ``Point2D`` 的子类型，保证内存读操作的超集兼容。
4. **函数双向型变裁决**：引擎严格遵循参数位置逆变（$	ext{Point3D} \le 	ext{Point2D}$）与返回值位置协变（$	ext{Point3D} \le 	ext{Point2D}$），成功证明了 $((Point2D) 	o Point3D) \le ((Point3D) 	o Point2D)$ 的定理成立。

小结与下章导读
--------------

本章系统解构了现代编译器在语义分析阶段构建的静态类型系统理论基石与工程实现：

1. **类型的物理与语义本质**：类型不仅是编译期约束事实，更是内存几何尺寸计算、字段偏移寻址与指令选择的物理依据。
2. **名义类型 vs 结构类型**：名义类型依靠全局唯一标识符实现 $O(1)$ 等价性判定与固定偏移硬编码寻址；结构类型通过图同构性与规范化实现高表达力，依赖胖指针或单态化解决布局失配。
3. **带环递归类型的余归纳判定**：利用假设集合截断自引用递归路径，实现了循环类型的定点等价性判定。
4. **子类型多态与类型格**：建立了由 $	op$（Top）与 $\bot$（Bottom）构成的有界偏序格，明确了 Join 与 Meet 的集合边界。
5. **型变公理与内存安全**：推导了函数类型在参数位置逆变、返回值位置协变的数学证明，剖析了可变引用强制不变性的硬件内存安全根源。
6. **Wright-Felleisen 健全性体系**：形式化阐述了进展定理（Progress）与保持定理（Preservation）对杜绝未定义行为的理论保障。

在完成类型等价性与子类型基础规则的确立后，编译器需要对由各种算术运算符、类型转换表达式与泛型多态函数构成的复杂 AST 节点执行端到端的类型检查与特化。在第 3 模块第 4 节 **表达式类型检查与泛型实例化：隐式转换截断、单态化 (Monomorphization) 与类型擦除（03_semantic_analysis_and_type_systems/04_type_checking_conversions_and_generics.rst）** 中，我们将深入剖析表达式类型推导流水线、隐式数值提升截断插入、基于 AST 克隆的 C++/Rust 泛型单态化生成算法与 Java/Go 类型擦除与装箱拆箱开销。
