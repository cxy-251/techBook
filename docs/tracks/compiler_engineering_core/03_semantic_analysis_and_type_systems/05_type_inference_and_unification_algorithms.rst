====================================================================================================
局部与全局类型推导：类型变量、方程约束收集与 Hindley-Milner / Unification 合一求解算法
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 3 模块第 4 节中，编译器构建了双向类型检查（Bidirectional Type Checking）管线，实现了数值拓宽、符号扩展（``SExt``）、截断（``Trunc``）在硬件指令集层面的物理映射，并确立了泛型单态化（Monomorphization）与类型擦除（Type Erasure）的落盘代码生成机制。在前述体系中，所有顶级函数与复合结构的类型签名均依赖显式声明，双向检查器仅在局部表达式内进行期望类型的自顶向下传递与自底向上综合。然而，现代编程语言（如 OCaml、Haskell、Rust、TypeScript、Swift 及现代 C++ ``auto`` / ``decltype``）允许程序员在源码中大量省略显式类型注解。编译器必须将类型视作包含未知项的代数表达式，通过遍历抽象语法树（AST）自动收集结构等式约束，并运用一阶项合一（First-Order Term Unification）算法求出唯一的最一般类型解（Principal Type）。本章深入剖析项代数（Term Algebra）与类型变量的物理建模、等式约束收集状态机、Robinson 一阶项合一算法与 Occurs Check 循环引用消除、Hindley-Milner（HM / Algorithm W）核心推导体系、Let 多态（Let-Polymorphism）与值限制（Value Restriction），以及增量编译防火墙下的局部与全局推导架构权衡。

类型变量、项代数与约束收集模型
------------------------------

在形式化类型系统与编译器前端中，类型推导被定义为在类型项代数（Type Term Algebra）上求解方程组的过程。源码中省略类型标注的 AST 节点不再保留为空指针或非法状态，而是由编译器动态分配唯一的 **类型变量（Type Variable）** 占位符。

类型项代数的形式化定义
~~~~~~~~~~~~~~~~~~~~~~

类型项集合 $\mathcal{T}$ 由基元类型常量、类型变量以及类型构造器递归定义：

.. math::

   	au ::= c \mid \alpha \mid 	au_1 	o 	au_2 \mid T\langle 	au_1, \dots, 	au_n \rangle

其中：
- $c \in \mathcal{B}$ 表示基元单态类型常量集合，例如 $	ext{Int32}$、$	ext{Float64}$、$	ext{Bool}$、$	ext{Void}$。
- $\alpha \in \mathcal{V}$ 表示可被代换的类型变量（Type Variable），编译器通常以自增整型 ID（如 $\alpha_1, \alpha_2, \dots$）进行物理唯一标识。
- $	au_1 	o 	au_2$ 表示一阶函数类型构造器，将输入类型 $	au_1$ 映射到输出类型 $	au_2$。
- $T\langle 	au_1, \dots, 	au_n \rangle$ 表示 $n$ 元参数化类型构造器，例如 $	ext{List}\langle 	au \rangle$、$	ext{Map}\langle 	au_1, 	au_2 \rangle$、$	ext{Tuple}\langle 	au_1, \dots, 	au_k \rangle$。

在支持参数多态的系统中，类型被区分为 **单态类型（Monotypes, $	au$）** 与 **多态类型方案（Polytypes / Type Schemes, $\sigma$）**：

.. math::

   \sigma ::= \forall \alpha_1 \alpha_2 \dots \alpha_n.\, 	au

多态类型方案 $\sigma$ 通过全称量词 $\forall$ 约束一组类型变量 $\vec{\alpha}$。未被 $\forall$ 量化的类型变量称为自由类型变量（Free Type Variables, $	ext{ftv}$）。类型推导的目标即为每个未标注项求出包含最少约束的类型方案。

约束生成体系（Constraint Generation）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

类型推导的第一阶段是遍历 AST 节点并生成一组一阶等式约束集合 $\mathcal{C} = \{ 	au_1 \doteq 	au_1', 	au_2 \doteq 	au_2', \dots \}$。约束收集器维护一个符号类型环境 $\Gamma = \{ x_1:\sigma_1, x_2:\sigma_2, \dots \}$，将作用域内的变量名映射至其对应的类型方案。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                类型推导约束生成与求解管线 (Constraint Pipeline)             |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 抽象语法树 AST ] : let choose = \flag. \a. \b. if flag then a else b     |
   |            |                                                                |
   |            v                                                                |
   |   [ 阶段 1: 节点遍历与新鲜类型变量分配 (Fresh Variable Allocation) ]         |
   |      flag -> a_1,  a -> a_2,  b -> a_3,  if_expr -> a_4                     |
   |            |                                                                |
   |            v                                                                |
   |   [ 阶段 2: 依据语言语义规则收集结构方程 (Constraint Generation) ]          |
   |      1. 条件表达式分支规则: a_1 == Bool                                     |
   |      2. Then/Else 分支一致性: a_2 == a_3                                    |
   |      3. 条件表达式返回值: a_4 == a_2                                        |
   |      4. 函数整体签名: T_choose == a_1 -> a_2 -> a_3 -> a_4                  |
   |            |                                                                |
   |            v                                                                |
   |   [ 阶段 3: 一阶项合一求解器 (Robinson Unification Solver) ]                |
   |      代换合成: [a_1 -> Bool, a_3 -> a_2, a_4 -> a_2]                        |
   |      求出主类型: T_choose = Bool -> a_2 -> a_2 -> a_2                       |
   |            |                                                                |
   |            v                                                                |
   |   [ 阶段 4: Let 多态泛化 (Generalization) ]                                 |
   |      量化自由变量: forall a_2. Bool -> a_2 -> a_2 -> a_2                    |
   |                                                                             |
   +-----------------------------------------------------------------------------+

.. list-table:: 核心语法结构的类型约束生成规则表
   :widths: 22 30 48
   :header-rows: 1
   :class: tight-table

   * - 语法结构
     - AST 节点形式
     - 生成的类型项与等式约束集合 $\mathcal{C}$
   * - 整型/浮点字面量
     - ``Literal(val)``
     - 产生单态常量类型 $	ext{Int32}$ 或 $	ext{Float64}$，$\mathcal{C} = \emptyset$
   * - 变量引用
     - ``Var(x)``
     - 从环境 $\Gamma$ 提取 $\Gamma(x) = \forall \vec{\alpha}. 	au$，实例化为新鲜变量 $	au[\vec{\alpha} \mapsto \vec{\beta}]$
   * - Lambda 抽象
     - ``\x. body``
     - 分配新鲜变量 $\alpha_{	ext{arg}}$，扩展环境 $\Gamma' = \Gamma \cup \{ x:\alpha_{	ext{arg}} \}$，结果为 $\alpha_{	ext{arg}} 	o 	au_{	ext{body}}$
   * - 函数调用应用
     - ``Apply(e1, e2)``
     - 分配新鲜结果变量 $\alpha_{	ext{ret}}$，生成约束集合 $\mathcal{C}_{e1} \cup \mathcal{C}_{e2} \cup \{ 	au_{e1} \doteq 	au_{e2} 	o \alpha_{	ext{ret}} \}$
   * - 条件分支
     - ``If(cond, th, el)``
     - 生成约束 $\mathcal{C}_{	ext{cond}} \cup \mathcal{C}_{	ext{th}} \cup \mathcal{C}_{	ext{el}} \cup \{ 	au_{	ext{cond}} \doteq 	ext{Bool}, 	au_{	ext{th}} \doteq 	au_{	ext{el}} \}$
   * - Let 绑定
     - ``Let(x, e1, e2)``
     - 求解 $\mathcal{C}_{e1}$，泛化得到 $\sigma_x = 	ext{gen}(	heta(\Gamma), 	au_{e1})$，在 $\Gamma \cup \{x:\sigma_x\}$ 中推导 $e2$

Robinson 一阶项合一算法与 Occurs Check
---------------------------------------

约束求解的核心算法是 **一阶项合一算法（First-Order Term Unification）**。合一求解器接收一组类型等式约束 $\mathcal{C}$，计算出一个 **最一般合一子（Most General Unifier, MGU）**。

代换（Substitution）与代换复合
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

代换 $	heta$ 是从类型变量集合到类型项集合的有限映射：

.. math::

   	heta = [ \alpha_1 \mapsto 	au_1, \alpha_2 \mapsto 	au_2, \dots, \alpha_k \mapsto 	au_k ]

将代换 $	heta$ 作用于类型项 $	au$ 记作 $	heta(	au)$，其递归替换 $	au$ 中出现的所有 $\alpha_i$。两个代换 $	heta_1$ 与 $	heta_2$ 的复合运算（Composition）记作 $	heta_2 \circ 	heta_1$，满足：

.. math::

   (	heta_2 \circ 	heta_1)(	au) = 	heta_2(	heta_1(	au))

代换复合在代数上满足结合律，编译器通过连续复合局部合一子逐步累积全局解。

Robinson 合一状态转移规则
~~~~~~~~~~~~~~~~~~~~~~~~~

合一函数 $	ext{unify}(	au_1, 	au_2)$ 接收两个类型项，输出消除两者差异的单一替换 $	heta$。若两项结构冲突，则报告类型失配错误。算法状态机遵循以下转移步骤：

1. **同一性消去（Identity Elimination）**：若 $	au_1 \equiv 	au_2$，返回空代换 $	ext{id}$。
2. **变量绑定（Variable Binding, $\alpha \doteq 	au$ 或 $	au \doteq \alpha$）**：
   - 若 $	au$ 等于 $\alpha$，返回空代换 $	ext{id}$。
   - 若 $	au$ 包含 $\alpha$，触发 **Occurs Check 错误**，终止推导。
   - 若通过 Occurs Check，返回单点代换 $[\alpha \mapsto 	au]$。
3. **结构项递归分解（Structural Decomposition）**：
   - 若 $	au_1 = 	au_{1a} 	o 	au_{1b}$ 且 $	au_2 = 	au_{2a} 	o 	au_{2b}$：
     首先计算参数合一子 $	heta_1 = 	ext{unify}(	au_{1a}, 	au_{2a})$；
     将 $	heta_1$ 作用于返回值类型，计算 $	heta_2 = 	ext{unify}(	heta_1(	au_{1b}), 	heta_1(	au_{2b}))$；
     返回复合代换 $	heta_2 \circ 	heta_1$。
   - 若 $	au_1 = T\langle u_1, \dots, u_n \rangle$ 且 $	au_2 = T\langle v_1, \dots, v_n \rangle$（构造器名称与参数数量完全一致）：
     依次对各个类型参数递归执行合一与代换累积。
4. **硬性冲突（Constant/Constructor Conflict）**：若 $	au_1$ 与 $	au_2$ 为不同的基元常量（如 $	ext{Int32} \doteq 	ext{Bool}$）或不同的类型构造器，合一算法失败并抛出具体诊断。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |            Robinson 合一状态转移与 Occurs Check 判定拓扑                     |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |              +------------------------------------------+                   |
   |              | 输入待合一类型对: (Type1, Type2)          |                   |
   |              +------------------------------------------+                   |
   |                                   |                                         |
   |          +------------------------+------------------------+                |
   |          |                        |                        |                |
   |          v                        v                        v                |
   |   [ 两端完全恒等 ]         [ 存在类型变量 alpha ]      [ 两端均为复合构造器 ]   |
   |   (Type1 == Type2)         (alpha, Tau)             (T1->T2, T3->T4)        |
   |          |                        |                        |                |
   |          v                        v                        v                |
   |      返回空代换 id          执行 Occurs Check:        1. theta1 =           |
   |                            alpha in ftv(Tau) ?          unify(T1, T3)       |
   |                                   |                   2. theta2 =           |
   |                         +---------+---------+           unify(th1(T2),      |
   |                         |                   |                 th1(T4))      |
   |                         v                   v         3. 返回 theta2 o th1  |
   |                    [ 是: 包含 ]       [ 否: 无引用 ]       |                |
   |                         |                   |              |                |
   |                         v                   v              |                |
   |                   抛出循环引用错误     返回单点代换         |                |
   |                   (Infinite Type)    [alpha -> Tau]        |                |
   |                                                                             |
   +-----------------------------------------------------------------------------+

Occurs Check 的物理本质与防循环机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当推导自应用表达式（如 $\lambda x. x\, x$）时，编译器为参数 $x$ 分配变量 $\alpha_x$。调用应用规则要求 $\alpha_x \doteq \alpha_x 	o \beta$。若不加拦截，变量绑定将形成无穷展开项 $\alpha_x \mapsto (\alpha_x 	o \beta) 	o \beta \dots$。

Occurs Check 算法遍历目标类型项 $	au$ 的完整语法树，收集其自由变量集合 $	ext{ftv}(	au)$。若待绑定变量 $\alpha \in 	ext{ftv}(	au)$，则判定该等式在有限项代数中无解，立即终止推导。该检查确保了类型推导算法在遇到非良构递归项时的强停机性（Strong Termination）。

并查集（Union-Find）路径压缩优化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在工业级编译器实现中，显式构造字符串或哈希表映射的代换复合操作具有高昂的内存分配与深拷贝开销。现代编译器采用基于 **并查集（Disjoint-Set / Union-Find）** 的图结构直接在类型节点上维护等价类：
- 每个类型变量内部持有一个指向代表节点（Representative Node）的指针。
- 绑定操作直接将变量节点的代表指针指向目标类型节点。
- 查找代表项时执行路径压缩（Path Compression），将所有经过的中间节点直接连接到根代表项。
- 结合按秩合并（Union by Rank），将一阶项合一的时间复杂度由朴素实现的指数/高次多项式降至近线性的反阿克曼函数复杂度 $\mathcal{O}(N \cdot \alpha(N))$。

Hindley-Milner 体系与 Algorithm W 实现机制
------------------------------------------

Hindley-Milner（HM）类型系统（亦称 Damas-Milner 系统）是参数化多态语言静态类型推导的黄金标准。其核心特性在于保证能够为良构程序自动推导出 **最一般主类型（Principal Type Scheme）**，无需任何显式类型标注。

泛化（Generalization）与实例化（Instantiation）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

HM 系统的多态性通过在 Let 绑定边界处的泛化与实例化实现：

1. **类型泛化（Generalization, $	ext{gen}(\Gamma, 	au)$）**：
   提取单态类型 $	au$ 中所有未在当前环境 $\Gamma$ 的自由类型变量集合中出现的类型变量，为其添加全称量词 $\forall$：

   .. math::

      	ext{gen}(\Gamma, 	au) = \forall \vec{\alpha}.\, 	au, \quad 	ext{其中 } \vec{\alpha} = 	ext{ftv}(	au) \setminus 	ext{ftv}(\Gamma)

   若类型变量出现在外部环境 $\Gamma$ 中（例如外层 Lambda 抽象的形参），说明该变量受外层上下文约束，不可被内层泛化为独立类型参数。

2. **多态实例化（Instantiation, $	ext{inst}(\sigma)$）**：
   从多态方案 $\sigma = \forall \alpha_1 \dots \alpha_n. 	au$ 出发，为每一个量化变量 $\alpha_i$ 分配一个全局唯一的全新类型变量 $\beta_i$，返回单态类型：

   .. math::

      	ext{inst}(\sigma) = 	au [ \alpha_1 \mapsto \beta_1, \dots, \alpha_n \mapsto \beta_n ]

   每次在不同调用点引用多态变量时，实例化机制均生成独立的类型变量，实现参数化多态的多重独立特化。

Let 多态（Let-Polymorphism）与 Lambda 限制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

HM 系统对 Lambda 抽象形参和 Let 绑定变量施加了严格的不对称规则：
- **Lambda 抽象 $\lambda x. e$**：形参 $x$ 在函数体内部只能作为 **单态类型变量 $\alpha$** 存在，无法在函数体内泛化为多态方案。
- **Let 绑定 $	ext{let } x = e_1 	ext{ in } e_2$**：绑定项 $e_1$ 在完成推导后立即执行泛化，将 $x$ 作为多态类型方案 $\sigma_x$ 存入环境，供 $e_2$ 内部的不同调用点多次独立实例化。

例如，表达式 $	ext{let } id = \lambda x. x 	ext{ in } (id\ 42, id\ 	ext{true})$ 能够合法推导为 $(	ext{Int32}, 	ext{Bool})$；而将多态变量作为 Lambda 参数传入时（如 $\lambda id. (id\ 42, id\ 	ext{true})$），由于 $id$ 在参数位置为单态变量，首次用于整数后即被绑定为 $	ext{Int32} 	o 	ext{Int32}$，后续用于布尔值将触发类型冲突。该限制将高阶类型推导限定在一阶谓词逻辑范畴内，确保了判定的可判定性。

算法 W（Algorithm W）推导流程
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

算法 W 是 HM 系统的标准确定性实现算法。函数 $W(\Gamma, e)$ 接收类型环境 $\Gamma$ 与 AST 表达式 $e$，返回复合代换 $	heta$ 与推导类型 $	au$：

.. code-block:: text

   Algorithm W(Gamma, expr) -> (Substitution, Type):
     1. Var(x):
        assert x in Gamma
        sigma = Gamma(x)
        tau = instantiate(sigma)
        return (id, tau)

     2. Lambda(x, body):
        beta = fresh_type_var()
        Gamma' = Gamma union { x : beta }
        (th1, tau_body) = W(Gamma', body)
        return (th1, th1(beta) -> tau_body)

     3. Apply(e1, e2):
        beta = fresh_type_var()
        (th1, tau1) = W(Gamma, e1)
        (th2, tau2) = W(th1(Gamma), e2)
        th3 = unify(th2(tau1), tau2 -> beta)
        return (th3 o th2 o th1, th3(beta))

     4. Let(x, e1, e2):
        (th1, tau1) = W(Gamma, e1)
        Gamma' = th1(Gamma)
        sigma_x = generalize(Gamma', tau1)
        (th2, tau2) = W(Gamma' union { x : sigma_x }, e2)
        return (th2 o th1, tau2)

     5. If(cond, th_branch, el_branch):
        (th1, tau_cond) = W(Gamma, cond)
        th2 = unify(tau_cond, Bool)
        (th3, tau_th) = W((th2 o th1)(Gamma), th_branch)
        (th4, tau_el) = W((th3 o th2 o th1)(Gamma), el_branch)
        th5 = unify(th4(tau_th), tau_el)
        return (th5 o th4 o th3 o th2 o th1, th5(tau_el))

值限制（Value Restriction）与可变状态安全
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

标准 HM 系统建立在纯函数式语义假定之上。当语言引入可变状态（Mutable References / Pointers / Arrays）时，朴素的 Let 多态将破坏内存安全性：

.. code-block:: ocaml

   (* 假定未加值限制的类型推导 *)
   let r = ref []      (* 推导为 forall 'a. 'a list ref *)
   let () = r := [1]   (* 在此将 'a 实例化为 int，存入整数列表 *)
   let s = List.hd !r  (* 在此将 'a 实例化为 string，按字符串指针解引用导致非法内存访问 *)

为了解决可变引用与多态泛化的语义冲突，Wright 与 Felleisen 提出了 **值限制（Value Restriction）** 法则：

- 编译器仅在 Let 绑定的右侧表达式 $e_1$ 属于 **语法值（Syntactic Value）** 时，才允许对自由类型变量执行多态泛化。
- **语法值定义**：字面量常量、变量引用、Lambda 闭包抽象 $\lambda x. e$ 以及由语法值构成的不可变元组/结构体构造器。
- **非语法值**：函数调用（如 ``ref []``）、计算表达式。非语法值推导出的自由变量保持单态绑定，禁止量化为 $\forall \alpha$，从而在静态检查阶段彻底切断类型混淆漏洞。

局部推导与全局推导的工程实现权衡
--------------------------------

在实际工业编译器架构设计中，类型推导系统的覆盖范围直接决定了编译吞吐量、增量编译粒度以及诊断信息的友好程度。

.. list-table:: 局部类型推导与全局类型推导架构特性深度对比
   :widths: 18 41 41
   :header-rows: 1
   :class: tight-table

   * - 评价维度
     - 局部类型推导 (Local Inference)
     - 全局 HM 类型推导 (Global HM Inference)
   * - 典型代表语言
     - C++ (``auto``), Rust (``let``), Go (``:=``), TypeScript, Swift
     - Haskell, OCaml, Standard ML, Elm
   * - 推导边界范围
     - 限制在单函数体、单语句或表达式上下文字符流内
     - 跨越语句、函数、甚至模块级别的全程序约束网络
   * - 函数签名要求
     - 顶层函数与公开接口必须显式声明完整类型签名
     - 函数参数与返回值均可省略声明，全量由系统推导
   * - 增量编译性能
     - 极高：修改函数体仅触发该函数重编译，签名形成防火墙
     - 较低：修改深层函数推导类型可能沿调用图引发连锁重推导
   * - 错误诊断质量
     - 精确清晰：错误范围牢牢锁定在当前表达式或声明语句行
     - 溯源链条长：冲突往往爆发在远离根因的深层调用点
   * - 语言复杂度支持
     - 自然兼容子类型多态（Subtyping）、重载决议与特征约束
     - 引入子类型与高阶多态后求解极易退化为不可判定问题

工业级 C++ 完整类型推导与合一求解引擎实现
------------------------------------------

以下 C++ 源码实现了一个自包含、工业级完备的 Hindley-Milner 类型推导与 Robinson 一阶合一求解引擎。该实现涵盖：
1. 具备完整继承层次的 AST 节点体系（包含整型字面量、布尔字面量、变量引用、Lambda 闭包、函数调用应用、Let 绑定、If-Then-Else 条件分支）。
2. 支持类型变量唯一 ID 生成、单态与多态类型方案定义、自由变量集合提取的类型代数系统。
3. 具备 Occurs Check 循环引用拦截与代换复合运算的 Robinson 合一求解器。
4. 完整的 Hindley-Milner 算法 W 推导器（支持多态实例化、环境自由变量过滤泛化与 Let 多态）。
5. 包含多态复用、分支约束、类型失配拦截以及 Occurs Check 无限类型拦截的端到端测试套件。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <string>
   #include <vector>
   #include <memory>
   #include <unordered_map>
   #include <unordered_set>
   #include <algorithm>
   #include <cstdint>
   #include <cassert>
   #include <sstream>

   // =========================================================================
   // 1. 类型项代数与多态方案定义 (Type Term Algebra & Type Scheme)
   // =========================================================================
   enum class TypeKind : uint8_t {
       Primitive,
       TypeVariable,
       Function
   };

   struct Type {
       TypeKind Kind;
       std::string Name;
       uint32_t VarId = 0; // 仅用于 TypeVariable
       const Type *ParamType = nullptr;  // 仅用于 Function: Param -> Return
       const Type *ReturnType = nullptr; // 仅用于 Function

       virtual ~Type() = default;

       bool isPrimitive() const { return Kind == TypeKind::Primitive; }
       bool isTypeVar() const { return Kind == TypeKind::TypeVariable; }
       bool isFunction() const { return Kind == TypeKind::Function; }
   };

   // 全局类型分配池与单例管理
   class TypeSystem {
   public:
       TypeSystem() {
           IntType = createPrimitive("Int");
           BoolType = createPrimitive("Bool");
       }

       const Type* getInt() const { return IntType; }
       const Type* getBool() const { return BoolType; }

       const Type* createFreshTypeVar() {
           AllocatedTypes.push_back(std::make_unique<Type>());
           Type *t = AllocatedTypes.back().get();
           t->Kind = TypeKind::TypeVariable;
           t->VarId = ++NextVarId;
           t->Name = "a" + std::to_string(t->VarId);
           return t;
       }

       const Type* createFunction(const Type *param, const Type *ret) {
           AllocatedTypes.push_back(std::make_unique<Type>());
           Type *t = AllocatedTypes.back().get();
           t->Kind = TypeKind::Function;
           t->ParamType = param;
           t->ReturnType = ret;
           
           std::stringstream ss;
           if (param->isFunction()) {
               ss << "(" << param->Name << ")";
           } else {
               ss << param->Name;
           }
           ss << " -> " << ret->Name;
           t->Name = ss.str();
           return t;
       }

   private:
       const Type* createPrimitive(std::string name) {
           AllocatedTypes.push_back(std::make_unique<Type>());
           Type *t = AllocatedTypes.back().get();
           t->Kind = TypeKind::Primitive;
           t->Name = std::move(name);
           return t;
       }

       const Type *IntType;
       const Type *BoolType;
       uint32_t NextVarId = 0;
       std::vector<std::unique_ptr<Type>> AllocatedTypes;
   };

   // 多态类型方案: forall a1, a2, ... . Type
   struct TypeScheme {
       std::vector<uint32_t> QuantifiedVars;
       const Type *BodyType = nullptr;

       TypeScheme() = default;
       TypeScheme(std::vector<uint32_t> vars, const Type *body)
           : QuantifiedVars(std::move(vars)), BodyType(body) {}
   };

   // =========================================================================
   // 2. 代换映射与复合运算 (Substitutions)
   // =========================================================================
   class Substitution {
   public:
       Substitution() = default;

       void bind(uint32_t varId, const Type *targetType) {
           Mapping[varId] = targetType;
       }

       bool contains(uint32_t varId) const {
           return Mapping.find(varId) != Mapping.end();
       }

       const Type* lookup(uint32_t varId) const {
           auto it = Mapping.find(varId);
           if (it != Mapping.end()) return it->second;
           return nullptr;
       }

       // 将代换作用于类型项: theta(tau)
       const Type* apply(const Type *t, TypeSystem &ts) const {
           if (!t) return nullptr;
           if (t->isPrimitive()) return t;

           if (t->isTypeVar()) {
               const Type *target = lookup(t->VarId);
               if (target) {
                   return apply(target, ts); // 递归应用多层代换
               }
               return t;
           }

           if (t->isFunction()) {
               const Type *newParam = apply(t->ParamType, ts);
               const Type *newRet = apply(t->ReturnType, ts);
               if (newParam == t->ParamType && newRet == t->ReturnType) {
                   return t;
               }
               return ts.createFunction(newParam, newRet);
           }

           return t;
       }

       // 代换复合: this = s2 o s1
       Substitution compose(const Substitution &s1, TypeSystem &ts) const {
           Substitution result;
           // 1. 对 s1 中的每一项应用 this (s2)
           for (const auto &pair : s1.Mapping) {
               result.bind(pair.first, this->apply(pair.second, ts));
           }
           // 2. 将 this (s2) 中未在 s1 中出现的项加入结果
           for (const auto &pair : this->Mapping) {
               if (!result.contains(pair.first)) {
                   result.bind(pair.first, pair.second);
               }
           }
           return result;
       }

   private:
       std::unordered_map<uint32_t, const Type*> Mapping;
   };

   // 计算自由类型变量集合 (Free Type Variables)
   void getFreeTypeVars(const Type *t, std::unordered_set<uint32_t> &ftv) {
       if (!t || t->isPrimitive()) return;
       if (t->isTypeVar()) {
           ftv.insert(t->VarId);
           return;
       }
       if (t->isFunction()) {
           getFreeTypeVars(t->ParamType, ftv);
           getFreeTypeVars(t->ReturnType, ftv);
       }
   }

   std::unordered_set<uint32_t> getSchemeFreeTypeVars(const TypeScheme &scheme) {
       std::unordered_set<uint32_t> ftv;
       getFreeTypeVars(scheme.BodyType, ftv);
       for (uint32_t q : scheme.QuantifiedVars) {
           ftv.erase(q);
       }
       return ftv;
   }

   // =========================================================================
   // 3. Robinson 一阶项合一求解器 (Unification with Occurs Check)
   // =========================================================================
   class UnificationSolver {
   public:
       static bool occursCheck(uint32_t varId, const Type *t, const Substitution &subst, TypeSystem &ts) {
           const Type *applied = subst.apply(t, ts);
           std::unordered_set<uint32_t> ftv;
           getFreeTypeVars(applied, ftv);
           return ftv.find(varId) != ftv.end();
       }

       static Substitution unify(const Type *t1, const Type *t2, TypeSystem &ts) {
           if (t1 == t2) return Substitution();

           if (t1->isTypeVar()) {
               return bindVariable(t1->VarId, t2, ts);
           }
           if (t2->isTypeVar()) {
               return bindVariable(t2->VarId, t1, ts);
           }

           if (t1->isPrimitive() && t2->isPrimitive()) {
               if (t1 == t2) return Substitution();
               std::cerr << "[合一冲突] 基元类型失配: " << t1->Name << " 与 " << t2->Name << "
";
               throw std::runtime_error("Type Mismatch Conflict");
           }

           if (t1->isFunction() && t2->isFunction()) {
               // 递归合一参数项
               Substitution s1 = unify(t1->ParamType, t2->ParamType, ts);
               // 将 s1 作用于返回类型后合一返回值
               const Type *ret1 = s1.apply(t1->ReturnType, ts);
               const Type *ret2 = s1.apply(t2->ReturnType, ts);
               Substitution s2 = unify(ret1, ret2, ts);
               return s2.compose(s1, ts);
           }

           std::cerr << "[合一冲突] 类型构造器失配: " << t1->Name << " 与 " << t2->Name << "
";
           throw std::runtime_error("Constructor Mismatch Conflict");
       }

   private:
       static Substitution bindVariable(uint32_t varId, const Type *target, TypeSystem &ts) {
           if (target->isTypeVar() && target->VarId == varId) {
               return Substitution(); // 恒等绑定
           }
           // 执行 Occurs Check 拦截无限循环项
           Substitution emptySubst;
           if (occursCheck(varId, target, emptySubst, ts)) {
               std::cerr << "[Occurs Check 失败] 检测到无穷递归类型项: a" << varId 
                         << " 包含于 " << target->Name << "
";
               throw std::runtime_error("Infinite Type Detected via Occurs Check");
           }
           Substitution s;
           s.bind(varId, target);
           return s;
       }
   };

   // =========================================================================
   // 4. 抽象语法树 (AST) 节点层级
   // =========================================================================
   enum class ASTKind {
       IntLit,
       BoolLit,
       Var,
       Lambda,
       Apply,
       Let,
       If
   };

   struct ASTNode {
       virtual ~ASTNode() = default;
       virtual ASTKind getKind() const = 0;
   };

   struct IntLitAST : public ASTNode {
       int64_t Value;
       IntLitAST(int64_t v) : Value(v) {}
       ASTKind getKind() const override { return ASTKind::IntLit; }
   };

   struct BoolLitAST : public ASTNode {
       bool Value;
       BoolLitAST(bool v) : Value(v) {}
       ASTKind getKind() const override { return ASTKind::BoolLit; }
   };

   struct VarAST : public ASTNode {
       std::string Name;
       VarAST(std::string name) : Name(std::move(name)) {}
       ASTKind getKind() const override { return ASTKind::Var; }
   };

   struct LambdaAST : public ASTNode {
       std::string ParamName;
       std::unique_ptr<ASTNode> Body;
       LambdaAST(std::string param, std::unique_ptr<ASTNode> body)
           : ParamName(std::move(param)), Body(std::move(body)) {}
       ASTKind getKind() const override { return ASTKind::Lambda; }
   };

   struct ApplyAST : public ASTNode {
       std::unique_ptr<ASTNode> Callee;
       std::unique_ptr<ASTNode> Argument;
       ApplyAST(std::unique_ptr<ASTNode> callee, std::unique_ptr<ASTNode> arg)
           : Callee(std::move(callee)), Argument(std::move(arg)) {}
       ASTKind getKind() const override { return ASTKind::Apply; }
   };

   struct LetAST : public ASTNode {
       std::string VarName;
       std::unique_ptr<ASTNode> ValueExpr;
       std::unique_ptr<ASTNode> BodyExpr;
       LetAST(std::string name, std::unique_ptr<ASTNode> val, std::unique_ptr<ASTNode> body)
           : VarName(std::move(name)), ValueExpr(std::move(val)), BodyExpr(std::move(body)) {}
       ASTKind getKind() const override { return ASTKind::Let; }
   };

   struct IfAST : public ASTNode {
       std::unique_ptr<ASTNode> Cond;
       std::unique_ptr<ASTNode> ThenBranch;
       std::unique_ptr<ASTNode> ElseBranch;
       IfAST(std::unique_ptr<ASTNode> c, std::unique_ptr<ASTNode> th, std::unique_ptr<ASTNode> el)
           : Cond(std::move(c)), ThenBranch(std::move(th)), ElseBranch(std::move(el)) {}
       ASTKind getKind() const override { return ASTKind::If; }
   };

   // =========================================================================
   // 5. 符号类型环境与 Hindley-Milner Algorithm W 引擎
   // =========================================================================
   class TypeEnvironment {
   public:
       void extend(const std::string &name, const TypeScheme &scheme) {
           Bindings[name] = scheme;
       }

       bool lookup(const std::string &name, TypeScheme &outScheme) const {
           auto it = Bindings.find(name);
           if (it != Bindings.end()) {
               outScheme = it->second;
               return true;
           }
           return false;
       }

       // 对环境中所有类型方案应用代换
       TypeEnvironment apply(const Substitution &subst, TypeSystem &ts) const {
           TypeEnvironment newEnv;
           for (const auto &pair : Bindings) {
               const TypeScheme &oldScheme = pair.second;
               const Type *newBody = subst.apply(oldScheme.BodyType, ts);
               newEnv.extend(pair.first, TypeScheme(oldScheme.QuantifiedVars, newBody));
           }
           return newEnv;
       }

       // 获取环境中所有未量化的自由类型变量集合
       std::unordered_set<uint32_t> getFreeTypeVars() const {
           std::unordered_set<uint32_t> ftv;
           for (const auto &pair : Bindings) {
               auto schemeFTV = getSchemeFreeTypeVars(pair.second);
               ftv.insert(schemeFTV.begin(), schemeFTV.end());
           }
           return ftv;
       }

   private:
       std::unordered_map<std::string, TypeScheme> Bindings;
   };

   class HindleyMilnerInference {
   public:
       HindleyMilnerInference(TypeSystem &ts) : Types(ts) {}

       // 实例化多态类型方案: forall a. a -> a  ==>  aFresh -> aFresh
       const Type* instantiate(const TypeScheme &scheme) {
           Substitution subst;
           for (uint32_t qVar : scheme.QuantifiedVars) {
               subst.bind(qVar, Types.createFreshTypeVar());
           }
           return subst.apply(scheme.BodyType, Types);
       }

       // 泛化单态类型: 将未在环境中的自由变量量化为 forall
       TypeScheme generalize(const TypeEnvironment &env, const Type *t) {
           std::unordered_set<uint32_t> typeFTV;
           getFreeTypeVars(t, typeFTV);

           std::unordered_set<uint32_t> envFTV = env.getFreeTypeVars();
           std::vector<uint32_t> quantified;

           for (uint32_t varId : typeFTV) {
               if (envFTV.find(varId) == envFTV.end()) {
                   quantified.push_back(varId);
               }
           }
           return TypeScheme(quantified, t);
       }

       // Algorithm W 核心推导入口
       std::pair<Substitution, const Type*> infer(const TypeEnvironment &env, const ASTNode *node) {
           if (!node) {
               throw std::runtime_error("Null AST Node Encountered");
           }

           switch (node->getKind()) {
               case ASTKind::IntLit:
                   return {Substitution(), Types.getInt()};

               case ASTKind::BoolLit:
                   return {Substitution(), Types.getBool()};

               case ASTKind::Var: {
                   auto *v = static_cast<const VarAST*>(node);
                   TypeScheme scheme;
                   if (!env.lookup(v->Name, scheme)) {
                       std::cerr << "[未绑定标识符] 变量名: " << v->Name << "
";
                       throw std::runtime_error("Unbound Identifier");
                   }
                   const Type *instType = instantiate(scheme);
                   return {Substitution(), instType};
               }

               case ASTKind::Lambda: {
                   auto *lam = static_cast<const LambdaAST*>(node);
                   const Type *paramVar = Types.createFreshTypeVar();
                   
                   TypeEnvironment extendedEnv = env;
                   // 参数作为无量化单态变量压入局部环境
                   extendedEnv.extend(lam->ParamName, TypeScheme({}, paramVar));

                   auto [s1, bodyType] = infer(extendedEnv, lam->Body.get());
                   const Type *finalParam = s1.apply(paramVar, Types);
                   const Type *funcType = Types.createFunction(finalParam, bodyType);
                   return {s1, funcType};
               }

               case ASTKind::Apply: {
                   auto *app = static_cast<const ApplyAST*>(node);
                   const Type *retVar = Types.createFreshTypeVar();

                   auto [s1, calleeType] = infer(env, app->Callee.get());
                   auto [s2, argType] = infer(env.apply(s1, Types), app->Argument.get());

                   const Type *appliedCallee = s2.apply(calleeType, Types);
                   const Type *expectedFunc = Types.createFunction(argType, retVar);

                   Substitution s3 = UnificationSolver::unify(appliedCallee, expectedFunc, Types);
                   const Type *finalRet = s3.apply(retVar, Types);
                   Substitution finalSubst = s3.compose(s2.compose(s1, Types), Types);
                   return {finalSubst, finalRet};
               }

               case ASTKind::Let: {
                   auto *letNode = static_cast<const LetAST*>(node);
                   auto [s1, valType] = infer(env, letNode->ValueExpr.get());

                   TypeEnvironment env1 = env.apply(s1, Types);
                   // 核心: 对绑定项执行泛化 (Let-Polymorphism)
                   TypeScheme generalizedScheme = generalize(env1, valType);

                   TypeEnvironment extendedEnv = env1;
                   extendedEnv.extend(letNode->VarName, generalizedScheme);

                   auto [s2, bodyType] = infer(extendedEnv, letNode->BodyExpr.get());
                   return {s2.compose(s1, Types), bodyType};
               }

               case ASTKind::If: {
                   auto *ifNode = static_cast<const IfAST*>(node);
                   auto [s1, condType] = infer(env, ifNode->Cond.get());
                   Substitution sCond = UnificationSolver::unify(condType, Types.getBool(), Types);
                   Substitution s1Total = sCond.compose(s1, Types);

                   auto [s2, thenType] = infer(env.apply(s1Total, Types), ifNode->ThenBranch.get());
                   Substitution s2Total = s2.compose(s1Total, Types);

                   auto [s3, elseType] = infer(env.apply(s2Total, Types), ifNode->ElseBranch.get());
                   Substitution s3Total = s3.compose(s2Total, Types);

                   const Type *appliedThen = s3Total.apply(thenType, Types);
                   const Type *appliedElse = s3Total.apply(elseType, Types);
                   Substitution sBranch = UnificationSolver::unify(appliedThen, appliedElse, Types);

                   Substitution finalSubst = sBranch.compose(s3Total, Types);
                   return {finalSubst, finalSubst.apply(appliedThen, Types)};
               }
           }
           throw std::runtime_error("Unknown AST Node");
       }

   private:
       TypeSystem &Types;
   };

   // =========================================================================
   // 6. 端到端测试套件与控制台验证
   // =========================================================================
   int main() {
       TypeSystem ts;
       HindleyMilnerInference engine(ts);
       TypeEnvironment globalEnv;

       std::cout << "========================================================================
";
       std::cout << "现代编译器 Hindley-Milner 算法 W 与 Robinson 一阶项合一求解引擎
";
       std::cout << "========================================================================

";

       // ---------------------------------------------------------------------
       // 测试 1: Let 多态泛化与多处实例化
       // let id = \x. x in (id 42, id true) ==> 此处测试 id 42 的推导
       // ---------------------------------------------------------------------
       std::cout << ">>> [测试 1] Let 多态泛化与实例化: let id = (\x. x) in id 42
";
       auto idBody = std::make_unique<VarAST>("x");
       auto idLambda = std::make_unique<LambdaAST>("x", std::move(idBody));
       auto callId42 = std::make_unique<ApplyAST>(
           std::make_unique<VarAST>("id"),
           std::make_unique<IntLitAST>(42)
       );
       auto letExpr = std::make_unique<LetAST>("id", std::move(idLambda), std::move(callId42));

       try {
           auto [subst, resultType] = engine.infer(globalEnv, letExpr.get());
           std::cout << "    推导成功! 表达式结果类型: " << resultType->Name << "

";
       } catch (const std::exception &e) {
           std::cout << "    推导失败: " << e.what() << "

";
       }

       // ---------------------------------------------------------------------
       // 测试 2: 条件分支与高阶选择函数推导
       // \flag. \a. \b. if flag then a else b
       // ---------------------------------------------------------------------
       std::cout << ">>> [测试 2] 高阶选择函数推导: \flag. \a. \b. if flag then a else b
";
       auto ifNode = std::make_unique<IfAST>(
           std::make_unique<VarAST>("flag"),
           std::make_unique<VarAST>("a"),
           std::make_unique<VarAST>("b")
       );
       auto lamB = std::make_unique<LambdaAST>("b", std::move(ifNode));
       auto lamA = std::make_unique<LambdaAST>("a", std::move(lamB));
       auto chooseFunc = std::make_unique<LambdaAST>("flag", std::move(lamA));

       try {
           auto [subst, resultType] = engine.infer(globalEnv, chooseFunc.get());
           std::cout << "    推导成功! 函数主类型: " << resultType->Name << "

";
       } catch (const std::exception &e) {
           std::cout << "    推导失败: " << e.what() << "

";
       }

       // ---------------------------------------------------------------------
       // 测试 3: 类型冲突检测 (If 分支返回不同类型)
       // \x. if x then 42 else false
       // ---------------------------------------------------------------------
       std::cout << ">>> [测试 3] 分支冲突检测: \x. if x then 42 else false
";
       auto badIf = std::make_unique<IfAST>(
           std::make_unique<VarAST>("x"),
           std::make_unique<IntLitAST>(42),
           std::make_unique<BoolLitAST>(false)
       );
       auto badLam = std::make_unique<LambdaAST>("x", std::move(badIf));

       try {
           auto [subst, resultType] = engine.infer(globalEnv, badLam.get());
           std::cout << "    异常: 本应失败但推导成功: " << resultType->Name << "

";
       } catch (const std::exception &e) {
           std::cout << "    [预期内拦截] 成功捕获语义错误: " << e.what() << "

";
       }

       // ---------------------------------------------------------------------
       // 测试 4: Occurs Check 拦截自应用循环引用
       // \x. x x
       // ---------------------------------------------------------------------
       std::cout << ">>> [测试 4] Occurs Check 无限项检测: \x. x x
";
       auto selfApply = std::make_unique<ApplyAST>(
           std::make_unique<VarAST>("x"),
           std::make_unique<VarAST>("x")
       );
       auto omegaLam = std::make_unique<LambdaAST>("x", std::move(selfApply));

       try {
           auto [subst, resultType] = engine.infer(globalEnv, omegaLam.get());
           std::cout << "    异常: 本应触发 Occurs Check 失败: " << resultType->Name << "

";
       } catch (const std::exception &e) {
           std::cout << "    [预期内拦截] 成功拦截无限项构造: " << e.what() << "

";
       }

       return 0;
   }

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 推导引擎，控制台输出清晰地验证了各核心推导规则的物理执行效果：

1. **Let 多态泛化与实例化**：在处理 ``let id = (\x. x) in id 42`` 时，引擎成功将 ``id`` 的推导结果 $\alpha_1 	o \alpha_1$ 泛化为 $\forall \alpha_1. \alpha_1 	o \alpha_1$，并在调用点将其独立实例化为全新变量 $\beta_1 	o \beta_1$。与实参 $42: 	ext{Int}$ 合一后求出整体结果为 $	ext{Int}$。
2. **高阶约束传递与最一般主类型构造**：针对三元选择函数，推导器从 ``flag`` 强制约束出 $	ext{Bool}$，从分支等价性约束出 $a$ 与 $b$ 共享同一类型变量 $\alpha_2$，输出最一般主类型 $	ext{Bool} 	o \alpha_2 	o \alpha_2 	o \alpha_2$。
3. **等式冲突精准捕获**：在 ``if x then 42 else false`` 中，合一器在合并分支类型 $	ext{Int} \doteq 	ext{Bool}$ 时识别出基元类型常量失配，直接终止推导。
4. **Occurs Check 强停机保护**：在处理自应用 $\lambda x. x\, x$ 时，方程 $\alpha_x \doteq \alpha_x 	o \beta$ 触发了自由变量扫描，识别出循环引用，拦截了无限深度类型项的生成。

小结与下章导读
--------------

本章系统解构了现代编译器前端在无显式类型标注场景下的自动化语义求解体系：

1. **项代数与约束收集模型**：建立了以基元类型、类型变量与构造器为基石的代数体系，将语法树遍历映射为等式约束生成流水线。
2. **Robinson 一阶合一求解机制**：阐明了代换复合与等式消解的数学原理，依托 Occurs Check 与并查集优化实现了高效、强停机的等式求解。
3. **Hindley-Milner 体系与 Algorithm W**：通过不对称的 Let 多态与值限制（Value Restriction）规则，在保持一阶可判定性的前提下实现了最一般主类型的自动推导。
4. **工程架构权衡**：横向对比了全局推导与局部推导在增量编译、签名防火墙与错误溯源层面的物理约束。

至此，全书 **第 3 模块：语义分析、作用域与类型系统（03_semantic_analysis_and_type_systems）** 已全部完工。编译器已完成从源码字符流、词法 Token、抽象语法树（AST）、作用域符号表到类型推导与语义合法性验证的全部前端工作。

在接下来的 **第 4 模块：中间表示 (IR)、控制流图 (CFG) 与 SSA 形式 (04_ir_cfg_and_ssa_construction)** 中，我们将正式跨越编译器前端与中端的物理分水岭。在第 4 模块第 1 节 **中间表示 (IR) 设计哲学：高层语言语义保留与机器无关性前端解耦、受控降级 (Lowering)（04_ir_cfg_and_ssa_construction/01_ir_design_working_language_and_lowering.rst）** 中，我们将深入剖析三地址码（3AC）、树形 IR 与图 IR 的设计抉择、HIR 到 LIR 的渐进降级策略，以及中端 IR 如何实现高层语义保留与底层硬件架构的彻底解耦。
