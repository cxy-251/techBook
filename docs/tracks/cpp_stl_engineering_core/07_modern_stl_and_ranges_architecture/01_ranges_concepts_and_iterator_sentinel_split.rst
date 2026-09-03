==============================================================================================================
C++20 Ranges 体系：Range Concept、Iterator-Sentinel 分离拓扑与统一操作管道
==============================================================================================================

.. note:: 前置背景与上下文承接
   在第 6 模块第 5 节（``06_callables_and_template_metaprogramming/05_cpp20_concepts_constraints_and_requires_clauses.rst``）中，我们系统剖析了 C++20 Concepts 形式化语义、``requires`` 语法体系、约束归一化与基于 Subsumption 蕴含关系的重载决议机制。Concepts 将泛型编程的隐式接口要求提升为编译器一等公民级别的显式类型契约。C++20 基于此核心语言特性，对标准模板库（STL）的基础抽象层进行了彻底重构，确立了 **Ranges（范围）体系**。本章全面解构 Ranges 体系的抽象本质、Range Concepts 能力分层拓扑、迭代器与哨兵（Iterator-Sentinel）的异构分离物理模型、定制点对象（CPO）的调用分发机制，以及 Projection（投影）在泛型算法中的解耦实现。

传统 STL 迭代器对缺陷与 Ranges 抽象重塑
---------------------------------------

自 C++98 起，经典 STL 算法体系以迭代器对（Iterator Pair, 即 ``[first, last)``）作为描述序列的统一接口范式。这种设计将算法逻辑与容器内部存储结构解耦，但在类型系统与工程安全层面存在三项基础性缺陷：

1. **类型同构强制假设与终止条件表达僵化**：
   传统迭代器对强制要求 ``first`` 与 ``last`` 具有完全相同的静态类型 ``Iter``。对于已知确切物理边界的容器（如 ``std::vector`` 或 ``std::list``），``last`` 是一个真实的尾后迭代器（Past-the-end Iterator）。然而，对于以特定条件终止的序列（例如以 ``'\0'`` 结尾的 C 风格字符串、无界数学发生器序列或 ``std::istream_iterator`` 输入流），计算终止并不依赖于预先确知的位置指针，而是取决于遍历过程中元素状态的动态判定。为了适配传统算法，开发者必须构造一个人为的、携带冗余状态的同型结束标记对象，增加了内存开销与条件判断分支。

2. **边界所有权分裂与跨容器误传安全隐患**：
   传统算法接口接收两个独立参数 ``(first, last)``。编译器在类型检查时仅能验证两者的类型匹配，无法检验它们是否指向同一容器实例的有效连续内存区间。传递来自不同容器的迭代器（如 ``std::sort(v1.begin(), v2.end())``）在语法层面完全合法，但在运行时会引发不可预测的跨段内存越界访问与段错误。

3. **临时对象悬垂引用与返回值安全性缺失**：
   当向传统算法传递临时右值容器并返回迭代器时（如 ``auto it = std::find(make_vector().begin(), make_vector().end(), 42);``），迭代器在语句结束后立即指向已被销毁的堆内存，形成悬垂指针（Dangling Pointer），编译器无法在编译期拦截该未定义行为。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                       传统 STL 迭代器对 vs C++20 Ranges                      |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 传统 STL 迭代器对范式 ]:                                                |
   |     template <typename InputIt, typename T>                                 |
   |     InputIt find(InputIt first, InputIt last, const T& value);              |
   |     * 缺陷: 强制 InputIt 同型; 易跨容器错配; 无法约束临时容器返回值生命周期 |
   |                                                                             |
   |                                      |                                      |
   |                                      v (C++20 重构与抽象提升)               |
   |                                                                             |
   |   [ C++20 Ranges 概念化范式 ]:                                              |
   |     template <std::ranges::input_range R, typename T>                       |
   |     std::ranges::borrowed_iterator_t<R>                                     |
   |     ranges::find(R&& r, const T& value, Proj proj = {});                    |
   |     * 优势: 单一 Range 对象作为入口; Iterator 与 Sentinel 异构解耦;        |
   |             内置 Projection 投影; 编译期借用生命周期追踪 (dangling 防御)     |
   |                                                                             |
   +-----------------------------------------------------------------------------+

C++20 Ranges 将“序列”本身抽象为一个独立的对象实体。一个对象只要能够通过定制点提取出起始迭代器与终止标记，即满足 Range 语义。算法直接接收完整的 Range 实体，将区间有效性保证收拢于对象边界内部。

Range Concepts 概念层级拓扑与能力约束
-------------------------------------

C++20 在 ``<ranges>`` 头文件中定义了一套基于 Concepts 的严格概念拓扑。该拓扑以核心 ``range`` 概念为基石，向上衍生出正交的能力维度与分层精化模型。

核心 range 概念与访问机制
~~~~~~~~~~~~~~~~~~~~~~~~~

``std::ranges::range`` 概念的形式化定义如下：

.. code-block:: cpp

   template <typename T>
   concept range = requires(T& t) {
       std::ranges::begin(t); // 产出起始迭代器
       std::ranges::end(t);   // 产出终止哨兵
   };

该定义表明，``range`` 的充要条件是类型 ``T`` 的左值能够成功接受定制点对象 ``std::ranges::begin`` 与 ``std::ranges::end`` 的调用，产出描述半开区间的两个位置对象。

Range 能力精化层级拓扑
~~~~~~~~~~~~~~~~~~~~~~

依据底层迭代器的遍历与访问能力，Ranges 建立了与传统迭代器分类严格对齐的概念精化体系（Refinement Hierarchy）：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     C++20 Ranges 概念精化拓扑继承架构                       |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |                           [ std::ranges::range ]                            |
   |                                     ^                                       |
   |                                     |                                       |
   |                        [ std::ranges::input_range ]                         |
   |                                     ^                                       |
   |                                     |                                       |
   |                       [ std::ranges::forward_range ]                        |
   |                                     ^                                       |
   |                                     |                                       |
   |                    [ std::ranges::bidirectional_range ]                     |
   |                                     ^                                       |
   |                                     |                                       |
   |                    [ std::ranges::random_access_range ]                     |
   |                                     ^                                       |
   |                                     |                                       |
   |                     [ std::ranges::contiguous_range ]                       |
   |                                                                             |
   |   [ 正交辅助概念体系 ]:                                                     |
   |     * std::ranges::sized_range      : 支持 O(1) 获取元素总数 ranges::size   |
   |     * std::ranges::common_range     : Iterator 与 Sentinel 严格同型         |
   |     * std::ranges::borrowed_range   : 允许右值传入且解引用结果不受生命周期影响 |
   |     * std::ranges::view             : 具备 O(1) 移动/拷贝/析构开销的轻量视图 |
   |                                                                             |
   +-----------------------------------------------------------------------------+

.. list-table:: C++20 Ranges 核心概念体系特征矩阵
   :widths: 22 28 50
   :header-rows: 1
   :class: tight-table

   * - 概念名称 (Concept)
     - 依赖的核心概念
     - 核心约束语义与物理不变性
   * - **``range``**
     - 无
     - 满足 ``std::ranges::begin(t)`` 与 ``std::ranges::end(t)`` 合法性。
   * - **``input_range``**
     - ``range``
     - 迭代器满足 ``std::input_iterator``，支持单遍读取扫描。
   * - **``output_range<R, T>``**
     - ``range``
     - 迭代器满足 ``std::output_iterator<T>``，支持向序列写入类型为 ``T`` 的值。
   * - **``forward_range``**
     - ``input_range``
     - 迭代器满足 ``std::forward_iterator``，支持多遍扫描与保存迭代状态。
   * - **``bidirectional_range``**
     - ``forward_range``
     - 迭代器满足 ``std::bidirectional_iterator``，支持 ``--it`` 双向回退。
   * - **``random_access_range``**
     - ``bidirectional_range``
     - 迭代器满足 ``std::random_access_iterator``，支持 $\mathcal{O}(1)$ 指针加减算术与下标访问。
   * - **``contiguous_range``**
     - ``random_access_range``
     - 元素在物理内存中连续存储，满足 ``to_address(it) == to_address(begin) + index``。
   * - **``common_range``**
     - ``range``
     - ``std::same_as<iterator_t<R>, sentinel_t<R>>``，起始迭代器与哨兵类型完全同构。
   * - **``sized_range``**
     - ``range``
     - 满足 ``std::ranges::size(t)``，能够在 $\mathcal{O}(1)$ 常数时间内获取序列元素总长度。
   * - **``borrowed_range``**
     - ``range``
     - 右值 Range 销毁后，从其提取出的迭代器依然保持合法可用（如 ``std::string_view`` 与 ``std::span``）。
   * - **``view``**
     - ``range``, ``movable``
     - 满足 ``std::ranges::enable_view<T>``，拷贝/移动/析构复杂度严格为 $\mathcal{O}(1)$，不拥有深层元素存储。

borrowed_range 与悬垂指针防御机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Ranges 算法全面引入了生命周期追踪机制。当向泛型算法传入 Range 实体时，算法的返回类型通过 ``std::ranges::borrowed_iterator_t<R>`` 进行推导：

.. code-block:: cpp

   template <typename R>
   using borrowed_iterator_t = std::conditional_t<
       std::ranges::borrowed_range<R>,
       std::ranges::iterator_t<R>,
       std::ranges::dangling
   >;

1. **左值容器或借用范围**：当传入左值容器（如 ``std::vector<int> v``）或本身不拥有数据的轻量视图（如 ``std::string_view``，已被标准库显式特化标记为 ``std::ranges::enable_borrowed_range<std::string_view> = true``）时，算法返回真实的迭代器类型 ``std::ranges::iterator_t<R>``。
2. **非借用右值临时容器**：当传入临时对象（如 ``std::vector<int>{1, 2, 3}``）时，``std::ranges::borrowed_range`` 判定为 ``false``，算法返回值类型退化为 ``std::ranges::dangling``。``dangling`` 是一个没有任何解引用操作符的空结构体，任何尝试对 ``dangling`` 对象执行 ``*it`` 或访问成员的操作都将在编译期直接报错，从类型系统层面彻底消除了悬垂引用。

.. code-block:: cpp

   #include <algorithm>
   #include <vector>
   #include <string_view>
   #include <ranges>

   // 场景 1: 左值容器，返回真实迭代器
   std::vector<int> vec = {10, 20, 30, 40};
   auto it1 = std::ranges::find(vec, 20); // decltype(it1) 为 std::vector<int>::iterator

   // 场景 2: 右值 borrowed_range，返回真实迭代器
   auto it2 = std::ranges::find(std::string_view("12345"), '3'); // 允许从右值 view 返回指针

   // 场景 3: 右值拥有型容器，编译期拦截
   auto it3 = std::ranges::find(std::vector<int>{1, 2, 3}, 2);
   // decltype(it3) 为 std::ranges::dangling
   // int val = *it3; // 编译错误: 无法对 std::ranges::dangling 执行解引用操作

Iterator-Sentinel 分离拓扑与异构终止模型
---------------------------------------

Ranges 架构在底层对迭代终点进行了核心语义解耦：将“指向当前元素的游标（Iterator）”与“判断遍历何时终止的哨兵（Sentinel）”分离为两个独立类型。

sentinel_for 概念的形式化公理
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 C++20 中，类型 ``S`` 成为迭代器 ``I`` 的哨兵，其概念形式化约束如下：

.. code-block:: cpp

   template <typename S, typename I>
   concept sentinel_for =
       std::input_or_output_iterator<I> &&
       std::equality_comparable_with<I, S>;

该公理要求：
1. ``I`` 满足基本迭代器遍历要求；
2. ``I`` 与 ``S`` 支持跨类型等价比较操作符（``i == s`` 与 ``i != s``），且比较语义在数学上满足一致性。

微架构级物理模型对比：同构模型 vs 异构哨兵模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了直观展示 Sentinel 分离带来的底层汇编与硬件收益，我们对比遍历以 ``'\0'`` 结尾的字符串时的两种实现模型：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                同构迭代器模型 vs 异构哨兵模型内存与寄存器映射                |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 方案 A: 传统同构迭代器对模型 (Homogeneous) ]                            |
   |     * 必须预先全量扫描计算 strlen(str) 以构建 const char* last 指针          |
   |     * 寄存器占用: RSI (cur_ptr), RDI (end_ptr)                               |
   |     * 循环比较: cmpq %rdi, %rsi  (双指针数值比对)                            |
   |     * 性能开销: 遍历发生前存在 O(N) 的预扫描，且占用 2 个通用寄存器          |
   |                                                                             |
   |   [ 方案 B: C++20 异构哨兵模型 (Heterogeneous Sentinel) ]                   |
   |     * 定义空结构体 struct NullSentinel {};                                  |
   |     * 重载 operator==(const char* it, NullSentinel) { return *it == '\0'; } |
   |     * 寄存器占用: RSI (cur_ptr)                                              |
   |     * 循环比较: cmpb $0, (%rsi)  (单指针内存值探针比对)                      |
   |     * 物理优势: 零预先扫描开销; 减少 1 个寄存器占用; 消除冗余指令            |
   |                                                                             |
   +-----------------------------------------------------------------------------+

在异构哨兵模型下，终止标记 ``NullSentinel`` 是一个尺寸为 1 字节（作为空类参数传递时被编译器完全优化消除）的无状态类型。编译器在生成循环汇编时，无需在寄存器中维护虚拟的尾后指针，而是直接发射单指令字节比对（``testb`` 或 ``cmpb``），显著降低了寄存器分配压力（Register Pressure）并提升了指令缓存局部性。

异构哨兵与无限序列（Unbounded Ranges）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Sentinel 分离使得表达潜在无限序列成为可能。例如，构造一个自增生成器，配合按条件判停的 Sentinel，算法可以在无需构造物化容器的前提下执行安全的受限遍历：

.. code-block:: cpp

   struct IntGenerator {
       int value = 0;
       int operator*() const { return value; }
       IntGenerator& operator++() { ++value; return *this; }
       IntGenerator operator++(int) { auto tmp = *this; ++value; return tmp; }
       using difference_type = std::ptrdiff_t;
       using value_type = int;
       using iterator_concept = std::input_iterator_tag;
   };

   // 定义哨兵：当生成器的值达到上限或满足特定条件时触发终止
   struct ThresholdSentinel {
       int limit;
       friend bool operator==(const IntGenerator& it, const ThresholdSentinel& s) {
           return *it >= s.limit;
       }
       friend bool operator==(const ThresholdSentinel& s, const IntGenerator& it) {
           return it == s;
       }
   };

   // 组合形成 Range
   struct CustomBoundedRange {
       int start_val;
       int max_val;
       IntGenerator begin() const { return IntGenerator{start_val}; }
       ThresholdSentinel end() const { return ThresholdSentinel{max_val}; }
   };

定制点对象（Customization Point Objects, CPO）微架构实现
--------------------------------------------------------

在泛型编程中，为了获取任意对象的起始与结束位置，传统代码常采用 ``using std::begin; begin(t);`` 的 ADL（Argument-Dependent Lookup，参数相关查找）两步分发手法。ADL 机制存在两项严重的工程缺陷：
1. **命名空间意外捕获与语义劫持**：若用户命名空间内存在同名但语义不符的非标准 ``begin`` 函数，ADL 会因最佳匹配规则而错误调用该函数。
2. **全局作用域污染**：未受限的 ADL 查找使得模板实例化深处的符号决议高度依赖包含顺序与外部声明环境。

CPO 的核心物理定义与防劫持设计
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

C++20 Ranges 通过 **定制点对象（CPO）** 彻底终结了 ADL 缺陷。CPO 是定义在特定私有内联命名空间中的 **全局 ``inline constexpr`` 函数对象实例**。

以 ``std::ranges::begin`` 为例，其标准库核心实现机制如下：

.. code-block:: cpp

   namespace std::ranges {
   namespace __begin_impl {

       // 毒丸技术 (Poison Pills): 在私有命名空间内声明被禁用的重载，阻断不合规的全局 ADL
       void begin(auto&) = delete;
       void begin(const auto&) = delete;

       struct _BeginCpo {
           // 优先级 1: 原生数组类型，返回数组首元素指针
           template <typename T, std::size_t N>
           constexpr T* operator()(T (&arr)[N]) const noexcept {
               return arr;
           }

           // 优先级 2: 拥有成员函数 t.begin()，且返回值满足 input_or_output_iterator
           template <typename T>
           requires requires(T& t) {
               { t.begin() } -> std::input_or_output_iterator;
           }
           constexpr auto operator()(T& t) const noexcept(noexcept(t.begin())) {
               return t.begin();
           }

           // 优先级 3: 经过受控 ADL 查找自由函数 begin(t)
           template <typename T>
           requires requires(T& t) {
               { begin(t) } -> std::input_or_output_iterator;
           }
           constexpr auto operator()(T& t) const noexcept(noexcept(begin(t))) {
               return begin(t);
           }
       };

   } // namespace __begin_impl

   // 导出单例函数对象
   inline namespace _Cpos {
       inline constexpr __begin_impl::_BeginCpo begin{};
   }

   } // namespace std::ranges

CPO 具有以下刚性物理特征：
1. **完全封死外部 ADL 寻址**：由于 ``std::ranges::begin`` 本身是一个实体对象名称而非未限定函数名，调用 ``std::ranges::begin(x)`` 严格执行对象成员操作符 ``operator()`` 解析，绝不触发对 ``begin`` 的全局 ADL 搜索。
2. **确定性分发流水线**：CPO 内部通过 Concepts ``requires`` 约束建立了严格互斥的分发优先级阶梯：原生数组 $	o$ 成员函数 $	o$ 受限 ADL 自由函数。
3. **完美转发与 noexcept 保持**：CPO 精确计算表达式的异常规范，并在编译期传递其 noexcept 契约。

Projection（投影）机制与算法解耦
--------------------------------

在传统 STL 算法中，当需要依据复合对象的某个特定字段或成员函数进行计算（如按员工年龄排序、按订单编号查找）时，开发者必须在谓词（Predicate）或比较器（Comparator）内部混杂字段提取逻辑：

.. code-block:: cpp

   struct Employee {
       int id;
       std::string name;
       double salary;
   };

   // 传统写法: 比较器中内嵌字段访问
   std::sort(employees.begin(), employees.end(), [](const Employee& a, const Employee& b) {
       return a.salary < b.salary;
   });

这种模式导致通用比较器（如 ``std::less<>``）无法直接复用，且当比较逻辑较为复杂（如多级排序或非对称比较）时，代码冗余度显著上升。

Projection 的形式化定义与执行模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Projection（投影）** 是一个一元可调用对象，它在算法将元素传递给比较器、谓词或目标值比对之前，先行对元素执行一次只读变换或属性提取。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                       Projection 内部数据流执行模型                          |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 原始元素输入 ]: Element A, Element B                                    |
   |                           |            |                                    |
   |                           v            v                                    |
   |   [ 投影变换流水线 ]: std::invoke(proj, A)   std::invoke(proj, B)           |
   |                           |            |                                    |
   |                           +-----+  +---+                                    |
   |                                 |  |                                        |
   |                                 v  v                                        |
   |   [ 通用比较器判定 ]: std::invoke(comp, Projected_A, Projected_B)           |
   |                                 |                                           |
   |                                 v                                           |
   |   [ 算法控制决策 ]:  true / false (用于划分、排序或查找分支)                |
   |                                                                             |
   +-----------------------------------------------------------------------------+

在 C++20 Ranges 算法中，每个接收谓词或比较器的算法均增设了一个默认值为 ``std::identity`` 的 Projection 模板参数：

.. code-block:: cpp

   namespace std::ranges {

   template <
       random_access_iterator I,
       sentinel_for<I> S,
       typename Comp = ranges::less,
       typename Proj = std::identity
   >
   requires sortable<I, Comp, Proj>
   constexpr I sort(I first, S last, Comp comp = {}, Proj proj = {});

   template <
       random_access_range R,
       typename Comp = ranges::less,
       typename Proj = std::identity
   >
   requires sortable<iterator_t<R>, Comp, Proj>
   constexpr borrowed_iterator_t<R> sort(R&& r, Comp comp = {}, Proj proj = {});

   } // namespace std::ranges

借助 Projection 与成员指针的 ``std::invoke`` 支持，对复合对象的排序与查找代码得到极致解耦：

.. code-block:: cpp

   // C++20 Ranges 写法: 比较器保持通用 ranges::less，投影指定提取成员
   std::ranges::sort(employees, std::ranges::less{}, &Employee::salary);

   // 按姓名查找员工
   auto it = std::ranges::find(employees, "Alice", &Employee::name);

Projection 的微架构优势与约束
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **零运行时开销**：当 Projection 为成员指针（如 ``&Employee::salary``）或空 Lambda 时，编译器通过内联展开直接生成结构体基地址偏移寻址指令（如 ``movsd 0x10(%rdi), %xmm0``），没有任何函数指针间接跳转开销。
2. **纯函数契约约束**：Projection 仅用于提取比较键，其执行过程必须保持只读无副作用。若 Projection 试图修改被引用的底层对象，将破坏算法的不变量保证。

工业级 C++20 Mini-Ranges 核心引擎实现
-------------------------------------

以下提供了一套自包含、符合 C++20 标准的 Mini-Ranges 核心引擎实现。代码涵盖：
1. 自定义 Concept 架构：实现 ``range``、``sentinel_for``、``sized_range`` 与 ``borrowed_range``。
2. CPO 定制点对象：实现防 ADL 劫持的 ``mini::ranges::begin`` 与 ``mini::ranges::end``。
3. 异构哨兵体系：实现针对 C 风格字符串的 ``NullTerminatedSentinel`` 与定长受限哨兵 ``CountSentinel``。
4. 现代受约束泛型算法：实现支持 Range 容器入口与 Projection 投影的 ``mini::ranges::for_each``、``mini::ranges::find`` 与 ``mini::ranges::sort``。
5. 完整的静态断言与端到端运行测试套件。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <vector>
   #include <string>
   #include <concepts>
   #include <type_traits>
   #include <functional>
   #include <utility>
   #include <cassert>
   #include <algorithm>

   namespace mini {

   // =========================================================================
   // 1. 基础工具与迭代器概念
   // =========================================================================

   template <typename I>
   concept readable = requires(const I& i) {
       { *i } -> std::same_as<decltype(*i)>;
   };

   template <typename I>
   concept weakly_incrementable = requires(I i) {
       typename std::iter_difference_t<I>;
       { ++i } -> std::same_as<I&>;
       i++;
   };

   template <typename I>
   concept input_or_output_iterator = weakly_incrementable<I> && requires(I i) {
       { *i };
   };

   // 哨兵概念：支持与迭代器进行跨类型等价比较
   template <typename S, typename I>
   concept sentinel_for =
       input_or_output_iterator<I> &&
       requires(const I& i, const S& s) {
           { i == s } -> std::convertible_to<bool>;
           { i != s } -> std::convertible_to<bool>;
           { s == i } -> std::convertible_to<bool>;
           { s != i } -> std::convertible_to<bool>;
       };

   // =========================================================================
   // 2. Customization Point Objects (CPO) 实现
   // =========================================================================

   namespace __cpo_detail {

       void begin(auto&) = delete;
       void begin(const auto&) = delete;
       void end(auto&) = delete;
       void end(const auto&) = delete;

       struct _Begin {
           template <typename T, std::size_t N>
           constexpr T* operator()(T (&arr)[N]) const noexcept {
               return arr;
           }

           template <typename T>
           requires requires(T& t) { { t.begin() } -> input_or_output_iterator; }
           constexpr auto operator()(T& t) const noexcept(noexcept(t.begin())) {
               return t.begin();
           }

           template <typename T>
           requires requires(T& t) { { begin(t) } -> input_or_output_iterator; }
           constexpr auto operator()(T& t) const noexcept(noexcept(begin(t))) {
               return begin(t);
           }
       };

       struct _End {
           template <typename T, std::size_t N>
           constexpr T* operator()(T (&arr)[N]) const noexcept {
               return arr + N;
           }

           template <typename T>
           requires requires(T& t) {
               { t.end() } -> sentinel_for<decltype(_Begin{}(t))>;
           }
           constexpr auto operator()(T& t) const noexcept(noexcept(t.end())) {
               return t.end();
           }

           template <typename T>
           requires requires(T& t) {
               { end(t) } -> sentinel_for<decltype(_Begin{}(t))>;
           }
           constexpr auto operator()(T& t) const noexcept(noexcept(end(t))) {
               return end(t);
           }
       };

   } // namespace __cpo_detail

   namespace ranges {
       inline namespace _Cpos {
           inline constexpr __cpo_detail::_Begin begin{};
           inline constexpr __cpo_detail::_End end{};
       }
   }

   // =========================================================================
   // 3. Range 概念体系定义
   // =========================================================================

   template <typename T>
   concept range = requires(T& t) {
       ranges::begin(t);
       ranges::end(t);
   };

   template <range R>
   using iterator_t = decltype(ranges::begin(std::declval<R&>()));

   template <range R>
   using sentinel_t = decltype(ranges::end(std::declval<R&>()));

   template <range R>
   using range_value_t = std::iter_value_t<iterator_t<R>>;

   template <range R>
   using range_reference_t = std::iter_reference_t<iterator_t<R>>;

   // Sized Range 概念
   template <typename T>
   concept sized_range = range<T> && requires(T& t) {
       { t.size() } -> std::integral;
   };

   // Common Range 概念：迭代器与哨兵同型
   template <typename T>
   concept common_range = range<T> && std::same_as<iterator_t<T>, sentinel_t<T>>;

   // Borrowed Range 标记特性
   template <typename T>
   inline constexpr bool enable_borrowed_range = false;

   template <typename T>
   concept borrowed_range = range<T> && (
       std::is_lvalue_reference_v<T> ||
       enable_borrowed_range<std::remove_cvref_t<T>>
   );

   // 悬垂防范占位结构体
   struct dangling {
       constexpr dangling() noexcept = default;
       template <typename... Args>
       constexpr dangling(Args&&...) noexcept {}
   };

   template <range R>
   using borrowed_iterator_t = std::conditional_t<
       borrowed_range<R>,
       iterator_t<R>,
       dangling
   >;

   // =========================================================================
   // 4. 异构哨兵模型实现示例
   // =========================================================================

   // 4.1 C 风格以 '\0' 结尾的字符串哨兵
   struct NullTerminatedSentinel {
       template <std::input_or_output_iterator I>
       requires requires(I it) { { *it == '\0' } -> std::convertible_to<bool>; }
       friend constexpr bool operator==(const I& it, NullTerminatedSentinel) noexcept {
           return *it == '\0';
       }

       template <std::input_or_output_iterator I>
       requires requires(I it) { { *it == '\0' } -> std::convertible_to<bool>; }
       friend constexpr bool operator!=(const I& it, NullTerminatedSentinel s) noexcept {
           return !(it == s);
       }
   };

   // 4.2 计数判定哨兵
   template <std::integral CountType>
   struct CountSentinel {
       CountType target_count;

       template <typename I>
       requires requires(const I& it) { { it.current_count() } -> std::convertible_to<CountType>; }
       friend constexpr bool operator==(const I& it, const CountSentinel& s) noexcept {
           return it.current_count() >= s.target_count;
       }

       template <typename I>
       requires requires(const I& it) { { it.current_count() } -> std::convertible_to<CountType>; }
       friend constexpr bool operator!=(const I& it, const CountSentinel& s) noexcept {
           return !(it == s);
       }
   };

   // 4.3 包装 C 风格字符串的简易 Range
   class CStringRange {
   private:
       const char* m_str;
   public:
       constexpr explicit CStringRange(const char* s) noexcept : m_str(s) {}
       constexpr const char* begin() const noexcept { return m_str; }
       constexpr NullTerminatedSentinel end() const noexcept { return {}; }
   };

   // 显式特化 CStringRange 为 borrowed_range
   template <>
   inline constexpr bool enable_borrowed_range<CStringRange> = true;

   // =========================================================================
   // 5. 受约束与带 Projection 投影的 Ranges 算法
   // =========================================================================

   namespace ranges {

       // 5.1 for_each 算法
       template <
           input_or_output_iterator I,
           sentinel_for<I> S,
           typename Proj = std::identity,
           std::indirectly_unary_invocable<std::projected<I, Proj>> Fun
       >
       constexpr I for_each(I first, S last, Fun f, Proj proj = {}) {
           for (; first != last; ++first) {
               std::invoke(f, std::invoke(proj, *first));
           }
           return first;
       }

       template <
           range R,
           typename Proj = std::identity,
           std::indirectly_unary_invocable<std::projected<iterator_t<R>, Proj>> Fun
       >
       constexpr borrowed_iterator_t<R> for_each(R&& r, Fun f, Proj proj = {}) {
           return for_each(ranges::begin(r), ranges::end(r), std::ref(f), std::ref(proj));
       }

       // 5.2 find 算法
       template <
           input_or_output_iterator I,
           sentinel_for<I> S,
           typename T,
           typename Proj = std::identity
       >
       requires requires(I it, Proj proj, const T& val) {
           { std::invoke(proj, *it) == val } -> std::convertible_to<bool>;
       }
       constexpr I find(I first, S last, const T& value, Proj proj = {}) {
           for (; first != last; ++first) {
               if (std::invoke(proj, *first) == value) {
                   return first;
               }
           }
           return first;
       }

       template <
           range R,
           typename T,
           typename Proj = std::identity
       >
       constexpr borrowed_iterator_t<R> find(R&& r, const T& value, Proj proj = {}) {
           return find(ranges::begin(r), ranges::end(r), value, std::ref(proj));
       }

       // 5.3 简单排序算法 (冒泡排序原型，用于展示 Iterator/Sentinel/Projection 交互)
       template <
           std::random_access_iterator I,
           sentinel_for<I> S,
           typename Comp = std::less<>,
           typename Proj = std::identity
       >
       constexpr I sort(I first, S last, Comp comp = {}, Proj proj = {}) {
           if (first == last) return first;
           // 计算长度以支持随机访问排序
           auto n = last - first;
           for (decltype(n) i = 0; i < n - 1; ++i) {
               for (decltype(n) j = 0; j < n - i - 1; ++j) {
                   auto&& val_a = std::invoke(proj, *(first + j));
                   auto&& val_b = std::invoke(proj, *(first + j + 1));
                   if (std::invoke(comp, val_b, val_a)) {
                       std::iter_swap(first + j, first + j + 1);
                   }
               }
           }
           return first + n;
       }

       template <
           range R,
           typename Comp = std::less<>,
           typename Proj = std::identity
       >
       constexpr borrowed_iterator_t<R> sort(R&& r, Comp comp = {}, Proj proj = {}) {
           return sort(ranges::begin(r), ranges::end(r), std::ref(comp), std::ref(proj));
       }

   } // namespace ranges

   } // namespace mini

   // =========================================================================
   // 6. 端到端功能验证测试套件
   // =========================================================================
   namespace test {

   struct Employee {
       int id;
       std::string name;
       double salary;
   };

   inline void runMiniRangesTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " C++20 Mini-Ranges 体系架构与物理模型验证
";
       std::cout << "=======================================================

";

       // 1. 概念静态检查验证
       static_assert(mini::range<std::vector<int>>, "std::vector must be a range");
       static_assert(mini::sized_range<std::vector<int>>, "std::vector must be a sized_range");
       static_assert(mini::common_range<std::vector<int>>, "std::vector has identical iter/sentinel");
       static_assert(mini::range<mini::CStringRange>, "CStringRange must be a range");
       static_assert(!mini::common_range<mini::CStringRange>, "CStringRange has heterogeneous sentinel");
       static_assert(mini::borrowed_range<mini::CStringRange>, "CStringRange is marked as borrowed_range");
       std::cout << "[测试 1: Range Concepts 静态断言]: 全部验证通过。
";

       // 2. 验证异构哨兵（NullTerminatedSentinel）遍历
       mini::CStringRange str_range("Modern-CPP-Ranges-Core");
       std::size_t char_count = 0;
       mini::ranges::for_each(str_range, [&](char c) {
           ++char_count;
       });
       std::cout << "[测试 2: 异构哨兵单遍遍历字符数]: " << char_count << "
";
       assert(char_count == 22);

       // 3. 验证带 Projection 投影的查找算法
       std::vector<Employee> staff = {
           {101, "Alice", 7500.0},
           {102, "Bob", 6200.0},
           {103, "Charlie", 9800.0},
           {104, "Diana", 8100.0}
       };

       // 3.1 按成员指针投影查找 ID
       auto it_emp = mini::ranges::find(staff, 103, &Employee::id);
       assert(it_emp != staff.end());
       std::cout << "[测试 3.1: 投影查找 ID=103 员工]: " << it_emp->name
                 << ", 薪资: " << it_emp->salary << "
";
       assert(it_emp->name == "Charlie");

       // 3.2 按成员指针投影查找姓名
       auto it_name = mini::ranges::find(staff, std::string("Diana"), &Employee::name);
       assert(it_name != staff.end());
       std::cout << "[测试 3.2: 投影查找 Name='Diana' 员工]: ID=" << it_name->id << "
";
       assert(it_name->id == 104);

       // 4. 验证带 Projection 投影的排序算法
       std::cout << "[测试 4.1: 按薪资升序投影排序前]:
";
       for (const auto& e : staff) {
           std::cout << "  - " << e.name << ": " << e.salary << "
";
       }

       mini::ranges::sort(staff, std::less<>{}, &Employee::salary);

       std::cout << "[测试 4.2: 按薪资升序投影排序后]:
";
       for (const auto& e : staff) {
           std::cout << "  - " << e.name << ": " << e.salary << "
";
       }
       assert(staff.front().name == "Bob");
       assert(staff.back().name == "Charlie");

       // 5. 验证 borrowed_range 与 dangling 生命周期类型判定
       static_assert(std::same_as<
           decltype(mini::ranges::find(staff, 101, &Employee::id)),
           std::vector<Employee>::iterator
       >, "Lvalue range returns real iterator");

       static_assert(std::same_as<
           decltype(mini::ranges::find(std::vector<int>{1, 2, 3}, 2)),
           mini::dangling
       >, "Rvalue non-borrowed container returns mini::dangling");

       static_assert(std::same_as<
           decltype(mini::ranges::find(mini::CStringRange("test"), 'e')),
           const char*
       >, "Rvalue borrowed_range returns real pointer");

       std::cout << "[测试 5: 生命周期悬垂检测 (dangling)]: 全部静态验证通过。
";

       std::cout << "
  -> C++20 Mini-Ranges 体系核心引擎测试完全通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述测试套件，其物理执行结果展示了 Ranges 体系对泛型算法内核的重塑：

1. **异构哨兵零预扫描吞吐**：在对 ``CStringRange`` 执行 ``for_each`` 时，程序没有调用 ``strlen`` 进行线性预扫描，而是利用 ``NullTerminatedSentinel`` 在单遍遍历中直接探测内存值 ``*it == '\0'``，达到了零额外内存分配与最小指令开销。
2. **Projection 与泛型比较器的正交解耦**：在对 ``Employee`` 结构体数组排序时，通用比较器 ``std::less<>`` 无需针对 ``Employee`` 重载 ``operator<`` 或编写专用 Lambda，通过 ``&Employee::salary`` 成员指针直接完成键提取，代码简洁且无运行时虚表或包装器开销。
3. **编译期生命周期安全防护**：静态断言确认了当向算法传入右值 ``std::vector`` 时，返回类型确定性退化为 ``mini::dangling``，彻底封死了任何解引用操作，杜绝了悬垂指针缺陷。

小结与下章导读
--------------

本章系统解构了 C++20 Ranges 体系的设计哲学、物理模型与微架构实现：

1. **Range 抽象提升**：剖析了传统迭代器对在同构假设与安全性上的缺陷，确立了 Range 作为统一序列实体的概念模型。
2. **Range Concepts 拓扑**：梳理了从 ``input_range`` 到 ``contiguous_range`` 的精化层级，以及 ``sized_range``、``common_range`` 与 ``borrowed_range`` 正交维度的约束语义。
3. **Iterator-Sentinel 异构分离**：推导了 ``sentinel_for`` 概念的数学公理，分析了无状态哨兵在降低寄存器压力与消除预扫描上的硬件优势。
4. **定制点对象（CPO）架构**：阐明了通过私有全局函数对象实例封死外部 ADL 劫持、建立确定性分发优先级的微架构机制。
5. **Projection 投影解耦**：解构了算法内部利用 ``std::invoke`` 分离字段提取与业务比较的高性能模型。

在下一节 **std::views 惰性求值视图：filter/transform/take 组合管线、零拷贝变换与悬垂视图防范（``07_modern_stl_and_ranges_architecture/02_views_lazy_evaluation_and_pipeline_composition.rst``）** 中，我们将深入 Ranges 体系的另一大支柱 —— **Views 视图与管道适配器**。我们将全面剖析基于管道操作符（``|``）的复合操作流水线、延迟求值（Lazy Evaluation）迭代驱动机制、零拷贝数据流转换，以及嵌套视图在迭代器缓存与生命周期管理上的关键工程实践。
