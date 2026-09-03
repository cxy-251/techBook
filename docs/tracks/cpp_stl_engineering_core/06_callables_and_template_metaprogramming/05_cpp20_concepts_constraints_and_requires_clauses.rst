==============================================================================================================
C++20 Concepts 概念约束：requires 子句与表达式、约束归一化、编译器可读诊断与重载决议
==============================================================================================================

.. note:: 前置背景与上下文承接
   在第 6 模块第 4 节（``06_callables_and_template_metaprogramming/04_type_traits_sfinae_and_compile_time_branching.rst``）中，我们系统探讨了 ``<type_traits>`` 属性查询系统、SFINAE 机制与 ``std::void_t`` 探测范式。SFINAE 通过将实参替换失败转化为静默候选淘汰，实现了模板重载的编译期分流。然而，SFINAE 机制将接口契约分散在默认模板参数、返回类型装饰与深层元函数展开中，当调用者传入不匹配实参时，编译器往往在模板实例化深处抛出数十层嵌套的冗长诊断。C++20 正式引入了 **Concepts 与 Constraints（概念与约束）** 核心语言特性，将模板实参的能力要求显式提升至函数与类模板的接口声明层。本章全面解构 Concepts 的形式化语义、``requires-clause`` 与 ``requires-expression`` 的双态拓扑、约束归一化（Constraint Normalization）与基于蕴含关系（Subsumption）的重载偏序规则，以及标准概念库的核心分类与微架构性能表现。

Concepts 形式化定义与接口契约化模型
-----------------------------------

C++20 Concepts 将泛型编程范式确立为基于显式契约的类型系统抽象。在传统模板中，函数模板对类型参数的操作属于隐式假设；在 Concepts 体系中，操作能力被形式化定义为命名约束集合。

Concept 的语法定义与常量表达式本质
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Concept 是用于对模板参数施加约束的命名谓词，其基本定义语法如下：

.. code-block:: cpp

   template <parameter-list>
   concept concept-name = constraint-expression;

Concept 具备以下核心语言属性：
1. **纯编译期布尔常量求值**：Concept 在编译期对给定模板实参进行代数演算，求值结果严格为 ``bool`` 类型的纯右值（prvalue）常量表达式。
2. **不可特化与不可赋值**：Concept 本身属于语言一等公民级别的约束命名，禁止对其进行显式特化（Explicit Specialization）或偏特化（Partial Specialization），亦不可作为运行时左值变量进行赋值或寻址。
3. **短路求值（Short-circuit Evaluation）**：由逻辑与（``&&``）和逻辑或（``||``）组合的约束表达式在求值过程中严格遵循短路规则。若左侧约束已确定最终真值，编译器停止对右侧表达式的实例化与语义检查。

.. code-block:: cpp

   #include <concepts>
   #include <type_traits>

   // 基础概念定义：检查类型是否为标量且满足特定大小
   template <typename T>
   concept CompactScalar = std::is_scalar_v<T> && (sizeof(T) <= 8);

   // 复合概念定义：通过逻辑运算组合已有概念
   template <typename T>
   concept NumericIdentifier = (std::integral<T> || std::floating_point<T>) && CompactScalar<T>;

接口约束的三种安放范式
~~~~~~~~~~~~~~~~~~~~~~

在函数模板与类模板中，Concepts 可以通过三种不同的语法形态约束模板参数：

.. list-table:: C++20 Concepts 接口约束的三种语法形态
   :widths: 22 38 40
   :header-rows: 1
   :class: tight-table

   * - 语法范式
     - 代码形态示例
     - 语法适用场景与工程特性
   * - **类型受约束参数**
       (Type-constraint)
     - ``template <std::integral T>``
       ``T add(T a, T b);``
     - 语法最为精炼，直接在模板形参列表中取代 ``typename``，适合针对单个类型参数施加单一命名概念。
   * - **前置 requires 子句**
       (Leading requires-clause)
     - ``template <typename T>``
       ``requires std::integral<T>``
       ``T add(T a, T b);``
     - 紧跟模板形参列表之后，清晰展示多个类型参数之间的复杂关联约束（如 ``requires std::same_as<T, U>``）。
   * - **尾置 requires 子句**
       (Trailing requires-clause)
     - ``template <typename T>``
       ``T add(T a, T b) requires std::integral<T>;``
     - 位于函数签名末尾，适合成员函数基于类模板参数施加额外约束，或约束条件依赖返回类型推导。
   * - **受约束 auto 简写**
       (Constrained auto)
     - ``auto add(std::integral auto a, std::integral auto b);``
     - C++20 泛型函数简写语法，底层自动展开为独立类型参数的受约束函数模板。

requires 体系：子句与表达式的双态拓扑
-------------------------------------

``requires`` 关键字在 C++20 中承担两类正交但协同的角色：**requires 子句（requires-clause）** 与 **requires 表达式（requires-expression）**。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                       C++20 requires 双态体系拓扑架构                        |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 1. requires-clause (约束子句) ]                                         |
   |     * 语法位置: template<...> requires C<T> 或 func(...) requires C<T>      |
   |     * 物理语义: 接收 compile-time bool 表达式，作为关联约束参与候选过滤     |
   |                                                                             |
   |                                      ^                                      |
   |                                      | (消费布尔结果)                       |
   |                                      |                                      |
   |   [ 2. requires-expression (约束表达式) ]                                   |
   |     * 语法位置: requires (parameter-list) { requirement-seq }               |
   |     * 物理语义: 编译期探测表达式合法性与类型存在性，产出 bool 纯右值        |
   |                                                                             |
   |         +-------------------------------------------------------------+     |
   |         | 四种内部 Requirement 语法结构                               |     |
   |         +-------------------------------------------------------------+     |
   |         | 1. 简单要求 (Simple): 验证表达式能否合法形成                |     |
   |         | 2. 类型要求 (Type): 验证嵌套类型或特化是否存在              |     |
   |         | 3. 复合要求 (Compound): { expr } noexcept -> Concept;       |     |
   |         | 4. 嵌套要求 (Nested): requires Predicate<T>;                |     |
   |         +-------------------------------------------------------------+     |
   |                                                                             |
   +-----------------------------------------------------------------------------+

requires 表达式的四种要求构造
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

requires 表达式是在编译期验证语法与语义构造合法性的核心工具：

1. **简单要求（Simple Requirements）**：
   断言任意表达式在给定类型实参下能够成功通过语法与类型检查。表达式本身仅在编译期被分析，不产生运行时求值。

   .. code-block:: cpp

      template <typename T>
      concept HasAddition = requires(T a, T b) {
          a + b; // 检查 a + b 是否为合法表达式
      };

2. **类型要求（Type Requirements）**：
   以 ``typename`` 关键字开头，验证特定命名类型、嵌套类型别名或类模板特化是否存在且合法。

   .. code-block:: cpp

      template <typename T>
      concept HasContainerTraits = requires {
          typename T::value_type;      // 检查嵌套别名 value_type
          typename T::iterator;        // 检查嵌套迭代器类型
          typename std::allocator<T>;  // 检查类模板特化合法性
      };

3. **复合要求（Compound Requirements）**：
   使用花括号包覆表达式 ``{ expression } [noexcept] [-> return-type-requirement];``，同时施加三重约束：
   - 表达式 ``expression`` 语法良构；
   - 若标记 ``noexcept``，则 ``noexcept(expression)`` 判定严格为 ``true``；
   - 表达式的实际返回类型 ``decltype((expression))`` 必须满足指定的类型约束或概念。

   .. code-block:: cpp

      template <typename T>
      concept AllocatorLike = requires(T& alloc, std::size_t n) {
          { alloc.allocate(n) } -> std::same_as<typename T::value_type*>;
          { alloc.deallocate(alloc.allocate(n), n) } noexcept;
      };

4. **嵌套要求（Nested Requirements）**：
   在 requires 表达式内部使用 ``requires bool-constexpr;``，用于引入附加的编译期常量谓词约束。

   .. code-block:: cpp

      template <typename T>
      concept ValidBuffer = requires(T val) {
          typename T::element_type;
          val.data();
          requires sizeof(typename T::element_type) <= 64; // 嵌套常量布尔要求
      };

requires requires 双重关键字机制解构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在工程实践中常出现形如 ``template <typename T> requires requires(T x) { ... }`` 的语法结构。其本质是外层 ``requires`` 代表 **requires-clause**（用于承接布尔约束并附着到函数声明），内层 ``requires`` 代表 **requires-expression**（即时构造一个临时的匿名语法探测块）。

约束归一化与重载偏序决议
------------------------

当多个受约束的函数模板形成重载候选集时，C++20 编译器依托 **约束归一化（Constraint Normalization）** 与 **蕴含关系（Subsumption）** 确立候选之间的偏序优先级。

约束归一化流水线
~~~~~~~~~~~~~~~~

为了比较不同约束的强弱，编译器首先将顶层约束表达式递归展开为由 **原子约束（Atomic Constraints）** 通过合取（$\land$, ``&&``）与析取（$\lor$, ``||``）构成的逻辑范式。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                       约束归一化与原子约束映射流水线                         |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 顶层命名概念定义 ]:                                                     |
   |     template <typename T> concept SortableRange = Range<T> && Sortable<T>;  |
   |                                                                             |
   |                                      |                                      |
   |                                      v                                      |
   |   [ 递归展开 Concept 引用 ]:                                                |
   |     Range<T>    ==> (InputRange<T> && HasBeginEnd<T>)                       |
   |     Sortable<T> ==> (Permutable<T> && LessComparable<T>)                    |
   |                                                                             |
   |                                      |                                      |
   |                                      v                                      |
   |   [ 形成合取范式 (Conjunctive Normal Form - CNF) ]:                         |
   |     InputRange<T>  /\  HasBeginEnd<T>  /\  Permutable<T>  /\  LessComp<T>   |
   |                                                                             |
   |                                      |                                      |
   |                                      v                                      |
   |   [ 提取原子约束集合 (Atomic Constraint Set) ]:                             |
   |     每个叶子节点表达式及其映射的模板参数形成唯一原子约束标识 ID              |
   |                                                                             |
   +-----------------------------------------------------------------------------+

原子约束的同一性判定
~~~~~~~~~~~~~~~~~~~~

两个原子约束 $E_1$ 与 $E_2$ 被判定为等价（Identical），当且仅当满足以下两条准则：
1. 它们的表达式在抽象语法树（AST）层面具有完全相同的程序源码结构；
2. 表达式中引用的所有模板形参在映射替换后指向相同的实参来源。

若两个概念采用不同的写法（即便在数学逻辑上等价），如果其源码形式不相同，编译器将视其为两个独立的原子约束，无法建立直接的蕴含偏序。

蕴含关系（Subsumption Rule）与重载排序
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

设有两个函数模板重载 $F_1$ 与 $F_2$，其归一化后的关联约束分别为 $P$ 与 $Q$：
- 若 $P$ 在合取逻辑上能够证明蕴含 $Q$（即 $P \implies Q$ 恒成立），且 $Q$ 不能证明蕴含 $P$（即 $Q 
ot\implies P$），则称 **$P$ 严格强于（More Constrained than）$Q$**。
- 在函数重载决议中，**更强约束的模板候选相较于较弱约束的模板候选具有更高的优先级**。

.. code-block:: cpp

   template <typename T> concept Incrementable = requires(T a) { ++a; };
   template <typename T> concept Decrementable = requires(T a) { --a; };
   template <typename T> concept Bidirectional = Incrementable<T> && Decrementable<T>;

   // 重载 1：弱约束
   template <Incrementable T>
   void step(T& val) {
       ++val;
   }

   // 重载 2：强约束 (Bidirectional 蕴含 Incrementable)
   template <Bidirectional T>
   void step(T& val) {
       ++val; // 双向类型优先进入此重载
   }

当调用 ``step(x)`` 且 ``x`` 同时支持自增与自减时，重载 1 的约束为 $\{ 	ext{Incrementable} \}$，重载 2 的约束为 $\{ 	ext{Incrementable} \land 	ext{Decrementable} \}$。由于 $\{ 	ext{Incrementable} \land 	ext{Decrementable} \} \implies \{ 	ext{Incrementable} \}$，重载 2 更加特化，编译器确定性选择重载 2，不产生歧义。

标准概念库核心分类与能力分层
----------------------------

C++20 ``<concepts>`` 标准头文件建立了一套标准化的概念层级体系，为现代泛型库提供了统一的接口约束词汇。

.. list-table:: C++20 ``<concepts>`` 核心标准概念拓扑矩阵
   :widths: 20 30 50
   :header-rows: 1
   :class: tight-table

   * - 概念分类
     - 标准概念名称
     - 核心约束语义与物理不变性
   * - **核心语言概念**
       (Core Language)
     - ``std::same_as<T, U>``
       ``std::derived_from<Derived, Base>``
       ``std::convertible_to<From, To>``
       ``std::integral<T>``
     - 验证精确类型一致性、公有继承层级关系、隐式与显式类型转换合法性、以及整数类型族。
   * - **比较概念**
       (Comparison)
     - ``std::equality_comparable<T>``
       ``std::totally_ordered<T>``
       ``std::three_way_comparable<T>``
     - 约束类型支持 ``==``、``!=`` 以及全序比较运算符（``<``, ``<=``, ``>``, ``>=``），或支持 C++20 三路比较（``<=>``）。
   * - **对象与生命周期**
       (Object & Lifetime)
     - ``std::destructible<T>``
       ``std::constructible_from<T, Args...>``
       ``std::movable<T>``
       ``std::copyable<T>``
       ``std::regular<T>``
     - 约束析构、就地构造、移动语义、深拷贝语义，以及满足默认构造与可复制的正则对象语义（Regular Object）。
   * - **可调用概念**
       (Callable)
     - ``std::invocable<F, Args...>``
       ``std::regular_invocable<F, Args...>``
       ``std::predicate<F, Args...>``
       ``std::strict_weak_order<R, T, U>``
     - 约束可调用对象支持 ``std::invoke`` 调度、无副作用正则调用、返回布尔判定值、以及满足严格弱序关系的二元比较谓词。

精确类型约束（std::same_as）与转换约束（std::convertible_to）的选型准则
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **``std::same_as<T, U>``**：
   要求类型 $T$ 与 $U$ 经过去除顶层引用与 cv 限定后完全同构，并在语言层面满足双向一致性（``std::same_as<T, U> && std::same_as<U, T>``）。用于封死任何隐式转换、阻止派生类向上转型、以及精确约束成员函数返回类型。
2. **``std::convertible_to<From, To>``**：
   允许从 ``From`` 到 ``To`` 存在隐式转换与显式 ``static_cast``。用于设计宽口径泛型接口（例如接受任意能够转换为 ``std::string_view`` 或 ``double`` 的实参）。

编译器诊断信息与 SFINAE 性能对比
--------------------------------

Concepts 相比传统 SFINAE 带来了两项维度的微架构级提升：**编译期可读诊断** 与 **编译器符号解析吞吐量**。

.. list-table:: SFINAE 与 C++20 Concepts 全景对比矩阵
   :widths: 18 41 41
   :header-rows: 1
   :class: tight-table

   * - 评估维度
     - 经典 SFINAE (enable_if_t / void_t)
     - C++20 Concepts & Constraints
   * - **接口声明可读性**
     - 差：约束混杂在返回类型、默认形参或深层偏特化中
     - 优：在函数模板头部以命名概念显式声明输入契约
   * - **错误诊断定位**
     - 差：数十层实例化调用栈，报错指向函数体深层代码
     - 优：单层直接报错，准确定位未满足的具体 concept 与原子要求
   * - **重载偏序判定**
     - 繁琐：需手动设计互斥条件（``!Condition``）防止签名重叠
     - 自然：基于归一化蕴含关系自动确立特化偏序优先级
   * - **编译器内存与耗时**
     - 较重：尝试实例化每一个潜在候选并生成废弃 AST
     - 极轻：短路求值与约束结果 AST 级哈希缓存，编译加速明显

工业级 C++ Mini-Concepts 约束与泛型重载调度引擎
------------------------------------------------

以下 C++20 源码实现了一套自包含的工业级概念约束与泛型调度库。实现涵盖：
1. 自定义 Concept 架构：基于 requires 表达式实现嵌套要求、类型要求与复合要求。
2. 约束归一化与 Subsumption 偏序重载状态机：设计基础运算器、双向运算器与随机访问运算器的分级重载。
3. 精确类型约束（``std::same_as``）与范围契约校验。
4. 端到端静态断言与重载决议调度测试套件。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <string>
   #include <vector>
   #include <list>
   #include <concepts>
   #include <type_traits>
   #include <cassert>

   namespace mini_concepts {

   // =========================================================================
   // 1. 自定义概念定义：结合四种 requires 表达式构造
   // =========================================================================

   // 概念 A: 检查类型是否具有嵌套 value_type 及 size() 成员
   template <typename T>
   concept SizedContainer = requires(const T& c) {
       typename T::value_type;                             // 1. 类型要求
       { c.size() } noexcept -> std::same_as<std::size_t>; // 2. 复合要求 (noexcept + 精确返回类型)
       c.empty();                                          // 3. 简单要求
   };

   // 概念 B: 检查类型是否包含可读取的整型 ID 字段
   template <typename T>
   concept HasIntegralId = requires(const T& obj) {
       { obj.id } -> std::integral; // 复合要求：obj.id 必须满足整数概念
       requires sizeof(obj.id) >= 4; // 4. 嵌套要求：ID 字段物理位宽不小于 4 字节
   };

   // =========================================================================
   // 2. 基于 Subsumption 蕴含关系的层次化概念设计
   // =========================================================================

   // 基础层：基本遍历器概念
   template <typename Iter>
   concept SimpleIterator = requires(Iter it) {
       { *it } -> std::same_as<typename std::iterator_traits<Iter>::reference>;
       { ++it } -> std::same_as<Iter&>;
   };

   // 进阶层：双向遍历器概念 (蕴含 SimpleIterator)
   template <typename Iter>
   concept BidirectionalIter = SimpleIterator<Iter> && requires(Iter it) {
       { --it } -> std::same_as<Iter&>;
   };

   // 高级层：随机访问遍历器概念 (蕴含 BidirectionalIter)
   template <typename Iter>
   concept FastRandomAccessIter = BidirectionalIter<Iter> && requires(Iter it, std::ptrdiff_t n) {
       { it + n } -> std::same_as<Iter>;
       { it[n] } -> std::same_as<typename std::iterator_traits<Iter>::reference>;
   };

   // =========================================================================
   // 3. 重载决议状态机：依托约束强度自动特化调度
   // =========================================================================

   // 重载路径 1: 基础遍历器算法 (最低约束)
   template <SimpleIterator Iter>
   std::string advanceAndDescribe(Iter first, std::size_t steps) {
       for (std::size_t i = 0; i < steps; ++i) {
           ++first;
       }
       return "[LinearScan-Mode]: Stepped forward linearly";
   }

   // 重载路径 2: 双向遍历器算法 (中间约束)
   template <BidirectionalIter Iter>
   std::string advanceAndDescribe(Iter first, std::size_t steps) {
       for (std::size_t i = 0; i < steps; ++i) {
           ++first;
       }
       return "[Bidirectional-Mode]: Supports backward step, stepped forward";
   }

   // 重载路径 3: 随机访问遍历器算法 (最强约束 - Subsumes All)
   template <FastRandomAccessIter Iter>
   std::string advanceAndDescribe(Iter first, std::size_t steps) {
       first = first + static_cast<std::ptrdiff_t>(steps); // O(1) 指针算术
       return "[RandomAccess-Mode]: Jumped in O(1) constant time";
   }

   // =========================================================================
   // 4. 业务契约约束函数：使用类型受约束参数与尾置 requires 子句
   // =========================================================================

   struct UserRecord {
       uint32_t id;
       std::string name;
   };

   struct LegacyRecord {
       int16_t id; // 2 字节，不满足 HasIntegralId 中的 sizeof(id) >= 4 约束
       std::string name;
   };

   template <HasIntegralId T>
   uint64_t extractNormalizedId(const T& record) {
       return static_cast<uint64_t>(record.id);
   }

   // 尾置 requires 子句演示
   template <typename T>
   auto processBuffer(const T& buffer) -> std::size_t
       requires SizedContainer<T> && (sizeof(typename T::value_type) > 1)
   {
       return buffer.size() * sizeof(typename T::value_type);
   }

   } // namespace mini_concepts

   // =========================================================================
   // 5. 端到端功能验证测试套件
   // =========================================================================
   namespace test {

   using namespace mini_concepts;

   inline void runConceptsTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " C++20 Concepts 概念约束与重载决议引擎验证
";
       std::cout << "=======================================================

";

       // 1. 概念静态断言验证
       static_assert(SizedContainer<std::vector<int>>, "std::vector must be SizedContainer");
       static_assert(!SizedContainer<int>, "int is not SizedContainer");
       static_assert(HasIntegralId<UserRecord>, "UserRecord has uint32_t id >= 4 bytes");
       static_assert(!HasIntegralId<LegacyRecord>, "LegacyRecord id is only 2 bytes");
       std::cout << "[测试 1: Concept 编译期静态断言]: 全部验证通过。
";

       // 2. 验证基于 Subsumption 蕴含关系的重载自动偏序分发
       std::vector<int> vec = {10, 20, 30, 40, 50};
       std::list<int> lst = {10, 20, 30, 40, 50};

       // vector::iterator 满足 FastRandomAccessIter，必须精准命中重载 3
       std::string vecRes = advanceAndDescribe(vec.begin(), 2);
       // list::iterator 满足 BidirectionalIter，必须精准命中重载 2
       std::string lstRes = advanceAndDescribe(lst.begin(), 2);

       std::cout << "[测试 2.1: vector 迭代器重载分发]: " << vecRes << "
";
       std::cout << "[测试 2.2: list 迭代器重载分发]:   " << lstRes << "
";

       assert(vecRes.find("[RandomAccess-Mode]") != std::string::npos);
       assert(lstRes.find("[Bidirectional-Mode]") != std::string::npos);

       // 3. 验证业务契约与尾置 requires 子句约束
       UserRecord validUser{10001, "Alice"};
       uint64_t normId = extractNormalizedId(validUser);
       std::cout << "[测试 3.1: 受约束 ID 提取结果]: " << normId << "
";
       assert(normId == 10001);

       std::vector<double> doubleBuf(10, 3.14);
       std::size_t totalBytes = processBuffer(doubleBuf);
       std::cout << "[测试 3.2: 尾置 requires 缓冲区字节计算]: " << totalBytes << " bytes
";
       assert(totalBytes == 80);

       std::cout << "
  -> C++20 Concepts 核心引擎测试完全通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述测试套件，其输出体现了 C++20 概念系统对现代泛型编程的核心重塑：

1. **重载偏序无歧义自动裁决**：``advanceAndDescribe`` 接收 ``std::vector::iterator`` 时，尽管其同时满足 ``SimpleIterator``、``BidirectionalIter`` 与 ``FastRandomAccessIter`` 三项概念，编译器通过约束归一化证明了最强概念的蕴含关系，直接将调用路由至 $\mathcal{O}(1)$ 常数时间指针跳跃版本，彻底摆脱了传统 SFINAE 需显式书写互斥逻辑的包袱。
2. **接口契约前置拦截**：若调用者尝试对 ``LegacyRecord`` 调用 ``extractNormalizedId``，编译器在匹配函数签名时直接报告不满足 ``HasIntegralId`` 概念（精确指出嵌套要求 ``sizeof(obj.id) >= 4`` 求值为 ``false``），错误直接停留在调用点，杜绝了函数体内部深层展开报错。

小结与下章导读
--------------

本章深入解构了 C++20 Concepts 体系的设计哲学、物理语义与编译器运作机理：

1. **Concepts 形式化语义**：阐明了概念作为编译期布尔常量谓词的一等公民地位与接口契约化本质。
2. **requires 架构双态拓扑**：剖析了作为约束挂载点的 ``requires-clause`` 与包含四种要求构造的 ``requires-expression``。
3. **约束归一化与 Subsumption 偏序法则**：推导了原子约束提取、同一性判定以及基于逻辑蕴含关系的重载优先级决议算法。
4. **标准概念库能力分层**：解构了核心语言概念、对象生命周期概念与可调用概念在标准库中的正交拓扑。
5. **微架构与诊断优势**：对比了 Concepts 相比传统 SFINAE 在编译耗时缩减与可读诊断信息层面的突破。

至此，本书 **第 6 模块：可调用对象、类型擦除与模板元编程** 已全部完工落盘。

在接下来的 **第 7 模块：现代 STL 体系演进与 Ranges 管道（07_modern_stl_and_ranges_architecture）** 中，我们将跨入现代 C++ STL 的革命性演进领域。在第 7 模块第 1 节 **C++20 Ranges 体系：Range Concept、Iterator-Sentinel 分离拓扑与统一操作管道（``07_modern_stl_and_ranges_architecture/01_ranges_concepts_and_iterator_sentinel_split.rst``）** 中，我们将全面剖析 Ranges 对传统迭代器对架构的彻底解耦，深入 Range 概念体系、迭代器与哨兵（Sentinel）类型分离拓扑，以及基于管道运算符（``|``）的组合式操作模型。
