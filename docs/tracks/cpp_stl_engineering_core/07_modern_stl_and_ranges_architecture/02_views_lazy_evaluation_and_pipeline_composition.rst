==============================================================================================================
std::views 惰性求值视图：filter/transform/take 组合管线、零拷贝变换与悬垂视图防范
==============================================================================================================

.. note:: 前置背景与上下文承接
   在第 7 模块第 1 节（``07_modern_stl_and_ranges_architecture/01_ranges_concepts_and_iterator_sentinel_split.rst``）中，我们系统推导了 C++20 Ranges 核心概念层级、Iterator-Sentinel 异构分离物理拓扑、定制点对象（CPO）的防 ADL 劫持分发机制，以及 Projection 投影解耦。Ranges 体系确立了“序列”作为一等公民的表达范式，而将这一范式推向工业级应用的核心支柱是 **Views（视图）与惰性求值管线**。本章深度剖析 ``std::ranges::view`` 概念的形式化公理约束、惰性求值（Lazy Evaluation）状态机的微架构流转、``operator|`` 管道闭包（Range Adaptor Closure Object）的元编程重载体系、核心适配器（``filter_view``、``transform_view``、``take_view``）的内存与缓存拓扑，以及针对悬垂引用（Dangling Reference）的生命周期全流程防范体系。

Views 概念公理系统与常数级复杂度契约
-------------------------------------

在 STL 架构演进中，容器（Container）与视图（View）代表了两种完全不同的资源与数据访问哲学。容器拥有其承载的物理元素，负责内存的分配、扩容、构造与析构，其拷贝操作具有与元素数量呈正比的 $\mathcal{O}(N)$ 线性时间与空间复杂度。视图则建立在现有底层序列之上，仅持有对原始数据的轻量级访问拓扑描述。

view 概念的形式化定义
~~~~~~~~~~~~~~~~~~~~~

在 C++20 ``<ranges>`` 标准体系中，``std::ranges::view`` 概念被严格定义为满足轻量级移动与析构语义的 Range 实体：

.. code-block:: cpp

   namespace std::ranges {

   template <typename T>
   inline constexpr bool enable_view =
       std::derived_from<T, view_base> ||
       /* 或者是满足 view_interface 继承与启发式判断的类型 */;

   template <typename T>
   concept view =
       range<T> &&
       std::movable<T> &&
       std::default_initializable<T> &&
       enable_view<T>;

   } // namespace std::ranges

语义层面的常数级复杂度（$\mathcal{O}(1)$ Complexity）公理
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

标准不仅对 ``view`` 施加语法签名约束，更施加了严格的物理复杂度公理：
1. **移动构造与移动赋值**：必须在 $\mathcal{O}(1)$ 常数时间内完成。
2. **析构操作**：必须在 $\mathcal{O}(1)$ 常数时间内完成（无论底层序列包含多少元素，View 的销毁仅释放自身持有的指针或句柄，绝不触发对底层元素的逐个析构）。
3. **拷贝构造与拷贝赋值**（若支持）：必须满足 $\mathcal{O}(1)$ 常数时间约束。

.. list-table:: Container 容器与 View 视图物理维度对比矩阵
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 观察维度
     - Owning Container（如 std::vector）
     - Non-Owning View（如 std::ranges::filter_view）
   * - **存储所有权**
     - 独占拥有底层堆内存与元素生命周期
     - 借用或引用底层序列，不拥有深层元素存储
   * - **拷贝/移动开销**
     - 拷贝为 $\mathcal{O}(N)$ 深拷贝，移动为 $\mathcal{O}(1)$ 指针置换
     - 拷贝与移动皆严格保持 $\mathcal{O}(1)$ 浅层指针/状态转移
   * - **析构行为**
     - 逐一析构全部 $N$ 个对象并回收堆内存块
     - 仅重置内部指针与状态，析构开销恒定为 $\mathcal{O}(1)$
   * - **求值时机**
     - 立即构造并物化全量物理元素
     - 惰性延迟至外部迭代器解引用或递增时触发
   * - **生命周期依赖**
     - 自包含完整生命周期，独立存活
     - 强依赖底层数据源，数据源销毁后立即失效

惰性求值（Lazy Evaluation）执行状态机与流水线编织
-------------------------------------------------

视图管线的核心特征是“构造期仅保存规则拓扑，消费期按需驱动状态流转”。当书写如下表达式时：

.. code-block:: cpp

   auto pipeline = source
       | std::views::filter(pred)
       | std::views::transform(func)
       | std::views::take(n);

编译器仅仅在栈上组装了一个由嵌套模板类型表达的复合视图对象。在此阶段，未对 ``source`` 中的任何一个元素执行读取、判断或映射操作。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                  Views 惰性组合管线嵌套类型与调用驱动模型                   |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ pipeline 对象物理结构 ]:                                                |
   |     take_view<                                                              |
   |       transform_view<                                                       |
   |         filter_view<                                                        |
   |           ref_view<std::vector<int>>,                                       |
   |           PredicateType                                                     |
   |         >,                                                                  |
   |         TransformFuncType                                                   |
   |       >,                                                                    |
   |       std::ptrdiff_t                                                        |
   |     >                                                                       |
   |                                                                             |
   |   [ 消费期拉取驱动 (Pull-Based Pipeline Execution) ]:                       |
   |                                                                             |
   |   for (auto&& x : pipeline)                                                 |
   |        |                                                                    |
   |        v (1. 检查 take 计数未耗尽)                                          |
   |     take_iterator::operator++                                               |
   |        |                                                                    |
   |        v (2. 触发底层迭代器前进)                                            |
   |     transform_iterator::operator++                                          |
   |        |                                                                    |
   |        v (3. 循环推进底层迭代器直至满足谓词)                                |
   |     filter_iterator::operator++                                             |
   |        |                                                                    |
   |        +---> source_iterator::operator++ (访问实际物理内存元素)             |
   |                                                                             |
   |   * 元素解引用路径:                                                         |
   |     *it 触发 transform_func(*filter_it) 并将变换结果直接交付消费循环        |
   |                                                                             |
   +-----------------------------------------------------------------------------+

核心适配器状态机与微架构特征
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **filter_view：条件谓词筛选与 begin() 缓存机制**
   ``filter_view`` 保存底层 Range 与一元谓词。其核心挑战在于实现 ``begin()`` 的 $\mathcal{O}(1)$ 复杂度契约。为了确定首个有效元素，必须从底层起点开始顺序扫描直到谓词为 ``true``。若每次调用 ``begin()`` 均从头扫描，在非随机访问序列中将退化为 $\mathcal{O}(N)$。
   为此，标准库实现中引入了 **第一有效位置缓存（Cached Begin）**。在首次执行 ``begin()`` 时将计算出的首个有效迭代器持久化在 ``filter_view`` 内部成员（如 ``std::optional<iterator_t<V>>``）中，后续调用直接返回缓存副本。
   该设计引发了关键的物理推论：**对包含缓存的 ``filter_view`` 调用 ``begin()`` 会修改视图自身状态**。因此，当底层范围满足前向遍历但不支持特定常态分发时，``const filter_view`` 将无法提供 ``begin()`` 成员函数，强制要求使用非常量对象进行迭代。

2. **transform_view：纯投影变换与多重求值边界**
   ``transform_view`` 在解引用操作符 ``operator*()`` 内部调用转换函数 ``std::invoke(*func_, *current_)``。
   物理特征在于：``transform_view`` 默认不进行结果缓存。当同一个迭代器位置被连续执行多次 ``*it`` 时，映射函数将被重复执行对应次数。若映射函数内部包含较重开销或有外部依赖，需在外部消费侧使用临时变量承接计算结果。

3. **take_view：定长截断哨兵与计数分发**
   ``take_view`` 依据元素计数与终止边界约束序列长度。当底层序列满足 ``sized_range`` 与 ``random_access_range`` 时，``take_view`` 的尾后位置通过简单的指针算术 ``begin() + std::min(size(), count)`` 产生同型迭代器；当底层序列为非定长输入流时，``take_view`` 采用携带递减计数器的异构哨兵（``sentinel``），在迭代器递增至指定次数或底层遭遇结束哨兵时激活停机。

Range Adaptor Closure 与管道操作符 operator| 内部重载机制
-----------------------------------------------------------

Ranges 优雅链式表达的底层技术是 **范围适配器闭包对象（Range Adaptor Closure Object, RACO）** 与柯里化（Currying）元编程。

管道语法转换法则
~~~~~~~~~~~~~~~~

表达式 ``range | views::adaptor(args...)`` 在编译阶段由重载的自由操作符 ``operator|`` 转换为函数调用：

.. code-block:: cpp

   // 表达式 A: 管道后置写法
   auto r1 = source | std::views::filter(pred);

   // 语义完全等价于表达式 B: 直接调用适配器
   auto r2 = std::views::filter(source, pred);

   // 以及表达式 C: 闭包对象接受参数
   auto r3 = std::views::filter(pred)(source);

闭包柯里化与元编程组合状态机
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了支撑该语法，标准库在内部将 ``std::views::filter(pred)`` 构造为一个派生自 ``std::ranges::range_adaptor_closure`` 的轻量闭包对象。该对象仅打包捕获传入的参数（如一元谓词），并延迟等待 Range 输入：

.. code-block:: cpp

   // 概念化实现：闭包对象的管道重载
   template <typename Derived>
   struct range_adaptor_closure {
       template <std::ranges::range R>
       requires /* 检查 Derived 能否作用于 R */
       constexpr auto operator()(R&& r) const {
           return static_cast<const Derived&>(*this)(std::forward<R>(r));
       }

       // 重载: Range | Closure
       template <std::ranges::range R>
       friend constexpr auto operator|(R&& r, const Derived& closure) {
           return closure(std::forward<R>(r));
       }

       // 重载: Closure_A | Closure_B (闭包合成流水线)
       template <typename OtherClosure>
       friend constexpr auto operator|(const Derived& a, const OtherClosure& b) {
           return /* 返回组合后的新闭包对象: b(a(range)) */;
       }
   };

这一设计不仅允许 ``range | adaptor``，还支持将多个适配器闭包先行融合成一个高阶复合管道组件：

.. code-block:: cpp

   // 先行组合变换管线逻辑，不依赖具体数据实体
   auto process_pipeline = std::views::filter([](int x) { return x % 2 == 0; })
                         | std::views::transform([](int x) { return x * 10; })
                         | std::views::take(5);

   // 随后将复合闭包施加于不同数据源
   auto res1 = vec1 | process_pipeline;
   auto res2 = vec2 | process_pipeline;

视图悬垂（Dangling Views）生命周期陷阱与防御体系
-------------------------------------------------

由于视图具有非拥有与惰性求值的核心特性，其内部普遍持有指向底层存储、容器或闭包环境的引用或原始指针。若数据所有权管理不当，视图管线极易诱发致命的悬垂引用（Dangling Reference）未定义行为。

右值容器传递与 views::all 的所有权推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当 Range 实体进入视图管线时，首先经由 ``std::views::all`` 进行归一化封装：
1. **左值容器**（``Container&``）：被封装为 ``std::ranges::ref_view<Container>``，内部持有指向左值容器的单指针 ``std::addressof(container)``。
2. **已存在的视图**（``View``）：直接按原类型完美转发移动或拷贝。
3. **右值临时容器**（``Container&&``）：在 C++20 早期曾被完全禁止，后经由标准缺陷报告引入了 ``std::ranges::owning_view<Container>``。``owning_view`` 通过移动语义直接将整个临时容器转移至视图内部持久存储，使得诸如返回临时变换序列的场景获得安全支持。

然而，若在自定义函数中违规混合引用与临时对象，仍会引发严重灾难：

.. code-block:: cpp

   // 危险代码范式 1: 返回引用局部变量的视图
   auto create_dangling_view() {
       std::vector<int> temp_data = {1, 2, 3, 4, 5};
       // 错误: filter_view 内部封装了指向局部变量 temp_data 的 ref_view
       return temp_data | std::views::filter([](int x) { return x > 2; });
       // 函数退出，temp_data 物理析构，调用侧解引用该视图将触发 Use-After-Free
   }

闭包捕获引用的生命周期脱节
~~~~~~~~~~~~~~~~~~~~~~~~~~

当向 ``filter`` 或 ``transform`` 传递的 Lambda 表达式捕获了局部作用域的引用时，视图的有效生命周期被隐式绑定至被捕获变量的存活期：

.. code-block:: cpp

   // 危险代码范式 2: Lambda 按引用捕获短期局部变量
   auto build_threshold_pipeline(std::vector<int>& data) {
       int threshold = 100;
       // 错误: Lambda 内部按引用捕获 [&threshold]
       return data | std::views::filter([&threshold](int x) { return x > threshold; });
       // 函数退出后 threshold 栈帧回收，管线迭代时访问该捕获引用诱发内存越界
   }

底层容器扩容与迭代器失效联动
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

即使底层容器本身保持存活，若在视图构建后对其执行了破坏迭代器有效性的变易操作（如 ``std::vector::push_back`` 导致连续内存重新分配）：
1. ``ref_view`` 内的底层指针仍指向旧容器结构，但容器已发生重分配；
2. ``filter_view`` 内部已缓存的 ``begin()`` 迭代器指向已经释放的陈旧堆内存块（Stale Heap Memory）；
3. 随后对视图的任何遍历操作均会产生内存崩溃。

.. list-table:: 视图生命周期陷阱与工业级工程对策
   :widths: 25 35 40
   :header-rows: 1
   :class: tight-table

   * - 故障诱因
     - 底层物理失效机理
     - 工业级标准修复策略
   * - **临时容器逃逸**
     - ``ref_view`` 指向已销毁的栈上临时容器
     - 使用 ``std::ranges::to<std::vector>()`` 物化，或使用 ``owning_view``
   * - **Lambda 引用捕获失效**
     - 闭包捕获的外部变量生命周期先于视图终止
     - 强制采用值捕获 ``[threshold]``，确保 Callable 自包含
   * - **底层容器动态扩容**
     - 容器重分配导致视图内部缓存的迭代器失效
     - 在构建视图与完成遍历之间，严禁对源容器执行变易操作
   * - **多次求值副作用**
     - ``transform_view`` 每次 ``*it`` 均重新触发计算
     - 保持变换函数为无副作用纯函数（Pure Function）

工业级 C++20 Mini-Views 核心引擎与组合管线实现
----------------------------------------------

以下展示一套自包含、符合 C++20 标准的 Mini-Views 核心引擎。代码涵盖：
1. **基础适配器闭包基类**：实现基于 CRTP 的 ``RangeAdaptorClosure``，支持 ``range | closure`` 与 ``closure1 | closure2`` 两种管道运算；
2. **零拷贝引用视图**：实现轻量包裹左值序列的 ``RefView``；
3. **带 begin() 缓存的过滤视图**：实现工业级 ``MiniFilterView`` 与迭代器推进状态机；
4. **延迟解引用转换视图**：实现具备零内存开销投影变换的 ``MiniTransformView``；
5. **计数截断视图**：实现支持安全受限遍历的 ``MiniTakeView``；
6. **适配器单例与工厂**：实现与标准库语法一致的 ``mini::views::filter``、``mini::views::transform``、``mini::views::take``；
7. **完整验证套件**：涵盖多级管道链接、惰性求值时机探针断言与闭包独立预合成测试。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <vector>
   #include <concepts>
   #include <type_traits>
   #include <functional>
   #include <utility>
   #include <cassert>
   #include <optional>
   #include <algorithm>

   namespace mini {

   // =========================================================================
   // 1. View 核心概念与基础设施
   // =========================================================================

   struct view_base {};

   template <typename T>
   inline constexpr bool enable_view = std::derived_from<T, view_base>;

   template <typename T>
   concept range = requires(T& t) {
       std::begin(t);
       std::end(t);
   };

   template <range R>
   using iterator_t = decltype(std::begin(std::declval<R&>()));

   template <range R>
   using sentinel_t = decltype(std::end(std::declval<R&>()));

   template <range R>
   using range_reference_t = decltype(*std::declval<iterator_t<R>&>());

   template <typename T>
   concept view = range<T> && std::movable<T> && enable_view<T>;

   // =========================================================================
   // 2. 管道闭包基类 (Range Adaptor Closure Object)
   // =========================================================================

   template <typename Derived>
   struct RangeAdaptorClosure {
       template <range R>
       requires requires(const Derived& closure, R&& r) {
           closure(std::forward<R>(r));
       }
       friend constexpr auto operator|(R&& r, const Derived& closure) {
           return closure(std::forward<R>(r));
       }

       // 闭包间合成: (Closure_A | Closure_B)(Range) == Closure_B(Closure_A(Range))
       template <typename OtherClosure>
       friend constexpr auto operator|(const Derived& first, const OtherClosure& second) {
           return [first, second](range auto&& r) {
               return second(first(std::forward<decltype(r)>(r)));
           };
       }
   };

   // =========================================================================
   // 3. RefView：轻量引用包装器
   // =========================================================================

   template <range R>
   requires std::is_object_v<R>
   class RefView : public view_base {
   private:
       R* m_ptr = nullptr;
   public:
       constexpr RefView() noexcept = default;
       constexpr explicit RefView(R& r) noexcept : m_ptr(std::addressof(r)) {}

       constexpr auto begin() const noexcept { return std::begin(*m_ptr); }
       constexpr auto end() const noexcept { return std::end(*m_ptr); }
   };

   template <typename R>
   constexpr auto all(R&& r) {
       if constexpr (view<std::decay_t<R>>) {
           return std::forward<R>(r);
       } else {
           return RefView{r};
       }
   }

   // =========================================================================
   // 4. MiniFilterView 实现 (携带 begin 缓存机制)
   // =========================================================================

   template <view V, typename Pred>
   requires std::is_object_v<Pred> && std::indirect_unary_predicate<Pred, iterator_t<V>>
   class MiniFilterView : public view_base {
   private:
       V m_base;
       Pred m_pred;
       mutable std::optional<iterator_t<V>> m_cached_begin;

   public:
       class Sentinel;

       class Iterator {
       private:
           iterator_t<V> m_curr;
           sentinel_t<V> m_end;
           const Pred* m_pred_ptr = nullptr;

           constexpr void satisfy_predicate() {
               while (m_curr != m_end && !std::invoke(*m_pred_ptr, *m_curr)) {
                   ++m_curr;
               }
           }

       public:
           using iterator_category = std::forward_iterator_tag;
           using value_type = std::iter_value_t<iterator_t<V>>;
           using difference_type = std::iter_difference_t<iterator_t<V>>;
           using reference = range_reference_t<V>;

           constexpr Iterator() = default;
           constexpr Iterator(iterator_t<V> curr, sentinel_t<V> end, const Pred& pred)
               : m_curr(curr), m_end(end), m_pred_ptr(std::addressof(pred)) {
               satisfy_predicate();
           }

           constexpr reference operator*() const { return *m_curr; }

           constexpr Iterator& operator++() {
               ++m_curr;
               satisfy_predicate();
               return *this;
           }

           constexpr Iterator operator++(int) {
               auto tmp = *this;
               ++(*this);
               return tmp;
           }

           friend constexpr bool operator==(const Iterator& x, const Iterator& y) {
               return x.m_curr == y.m_curr;
           }

           friend constexpr bool operator==(const Iterator& x, const Sentinel& y) {
               return x.m_curr == y.m_end;
           }
       };

       class Sentinel {
       public:
           sentinel_t<V> m_end;
           constexpr Sentinel() = default;
           constexpr explicit Sentinel(sentinel_t<V> end) : m_end(end) {}
       };

       constexpr MiniFilterView() = default;
       constexpr MiniFilterView(V base, Pred pred)
           : m_base(std::move(base)), m_pred(std::move(pred)) {}

       constexpr auto begin() const {
           if (!m_cached_begin.has_value()) {
               m_cached_begin = Iterator(std::begin(m_base), std::end(m_base), m_pred);
           }
           return *m_cached_begin;
       }

       constexpr auto end() const {
           return Sentinel(std::end(m_base));
       }
   };

   // =========================================================================
   // 5. MiniTransformView 实现 (解引用时计算映射)
   // =========================================================================

   template <view V, typename Func>
   requires std::is_object_v<Func> && std::regular_invocable<Func&, range_reference_t<V>>
   class MiniTransformView : public view_base {
   private:
       V m_base;
       Func m_func;

   public:
       class Iterator {
       private:
           iterator_t<V> m_curr;
           const Func* m_func_ptr = nullptr;

       public:
           using iterator_category = std::forward_iterator_tag;
           using value_type = std::remove_cvref_t<std::invoke_result_t<Func&, range_reference_t<V>>>;
           using difference_type = std::iter_difference_t<iterator_t<V>>;

           constexpr Iterator() = default;
           constexpr Iterator(iterator_t<V> curr, const Func& func)
               : m_curr(curr), m_func_ptr(std::addressof(func)) {}

           constexpr decltype(auto) operator*() const {
               return std::invoke(*m_func_ptr, *m_curr);
           }

           constexpr Iterator& operator++() {
               ++m_curr;
               return *this;
           }

           constexpr Iterator operator++(int) {
               auto tmp = *this;
               ++(*this);
               return tmp;
           }

           friend constexpr bool operator==(const Iterator& x, const Iterator& y) {
               return x.m_curr == y.m_curr;
           }

           template <typename S>
           friend constexpr bool operator==(const Iterator& x, const S& s) {
               return x.m_curr == s;
           }
       };

       constexpr MiniTransformView() = default;
       constexpr MiniTransformView(V base, Func func)
           : m_base(std::move(base)), m_func(std::move(func)) {}

       constexpr auto begin() const {
           return Iterator(std::begin(m_base), m_func);
       }

       constexpr auto end() const {
           return std::end(m_base);
       }
   };

   // =========================================================================
   // 6. MiniTakeView 实现 (计数截断)
   // =========================================================================

   template <view V>
   class MiniTakeView : public view_base {
   private:
       V m_base;
       std::ptrdiff_t m_count = 0;

   public:
       class Sentinel {
       private:
           sentinel_t<V> m_end;
       public:
           constexpr Sentinel() = default;
           constexpr explicit Sentinel(sentinel_t<V> end) : m_end(end) {}

           template <typename I>
           friend constexpr bool operator==(const I& it, const Sentinel& s) {
               return it.current_count() <= 0 || it.base() == s.m_end;
           }
       };

       class Iterator {
       private:
           iterator_t<V> m_curr;
           std::ptrdiff_t m_remaining = 0;

       public:
           using iterator_category = std::forward_iterator_tag;
           using value_type = std::iter_value_t<iterator_t<V>>;
           using difference_type = std::iter_difference_t<iterator_t<V>>;
           using reference = range_reference_t<V>;

           constexpr Iterator() = default;
           constexpr Iterator(iterator_t<V> curr, std::ptrdiff_t count)
               : m_curr(curr), m_remaining(count) {}

           constexpr reference operator*() const { return *m_curr; }

           constexpr Iterator& operator++() {
               ++m_curr;
               --m_remaining;
               return *this;
           }

           constexpr Iterator operator++(int) {
               auto tmp = *this;
               ++(*this);
               return tmp;
           }

           constexpr iterator_t<V> base() const { return m_curr; }
           constexpr std::ptrdiff_t current_count() const { return m_remaining; }

           friend constexpr bool operator==(const Iterator& x, const Iterator& y) {
               return x.m_curr == y.m_curr;
           }
       };

       constexpr MiniTakeView() = default;
       constexpr MiniTakeView(V base, std::ptrdiff_t count)
           : m_base(std::move(base)), m_count(count) {}

       constexpr auto begin() const {
           return Iterator(std::begin(m_base), m_count);
       }

       constexpr auto end() const {
           return Sentinel(std::end(m_base));
       }
   };

   // =========================================================================
   // 7. Adaptor 闭包生成器与全局命名空间导出
   // =========================================================================

   namespace views {

       // Filter Adaptor
       template <typename Pred>
       struct FilterClosure : RangeAdaptorClosure<FilterClosure<Pred>> {
           Pred m_pred;
           constexpr explicit FilterClosure(Pred p) : m_pred(std::move(p)) {}

           template <range R>
           constexpr auto operator()(R&& r) const {
               return MiniFilterView(all(std::forward<R>(r)), m_pred);
           }
       };

       struct _Filter {
           template <typename Pred>
           constexpr auto operator()(Pred pred) const {
               return FilterClosure<Pred>(std::move(pred));
           }

           template <range R, typename Pred>
           constexpr auto operator()(R&& r, Pred pred) const {
               return MiniFilterView(all(std::forward<R>(r)), std::move(pred));
           }
       };

       // Transform Adaptor
       template <typename Func>
       struct TransformClosure : RangeAdaptorClosure<TransformClosure<Func>> {
           Func m_func;
           constexpr explicit TransformClosure(Func f) : m_func(std::move(f)) {}

           template <range R>
           constexpr auto operator()(R&& r) const {
               return MiniTransformView(all(std::forward<R>(r)), m_func);
           }
       };

       struct _Transform {
           template <typename Func>
           constexpr auto operator()(Func func) const {
               return TransformClosure<Func>(std::move(func));
           }

           template <range R, typename Func>
           constexpr auto operator()(R&& r, Func func) const {
               return MiniTransformView(all(std::forward<R>(r)), std::move(func));
           }
       };

       // Take Adaptor
       struct TakeClosure : RangeAdaptorClosure<TakeClosure> {
           std::ptrdiff_t m_count;
           constexpr explicit TakeClosure(std::ptrdiff_t n) : m_count(n) {}

           template <range R>
           constexpr auto operator()(R&& r) const {
               return MiniTakeView(all(std::forward<R>(r)), m_count);
           }
       };

       struct _Take {
           constexpr auto operator()(std::ptrdiff_t n) const {
               return TakeClosure(n);
           }

           template <range R>
           constexpr auto operator()(R&& r, std::ptrdiff_t n) const {
               return MiniTakeView(all(std::forward<R>(r)), n);
           }
       };

       inline constexpr _Filter filter{};
       inline constexpr _Transform transform{};
       inline constexpr _Take take{};

   } // namespace views

   } // namespace mini

   // =========================================================================
   // 8. 工业级功能与状态机验证测试套件
   // =========================================================================

   namespace test {

   inline void runViewsPipelineTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " C++20 Mini-Views 惰性组合管线与状态机验证
";
       std::cout << "=======================================================

";

       // 1. 概念静态断言检查
       static_assert(mini::view<mini::RefView<std::vector<int>>>, "RefView must satisfy view concept");
       static_assert(mini::view<mini::MiniFilterView<mini::RefView<std::vector<int>>, bool(*)(int)>>,
                     "MiniFilterView must satisfy view concept");
       std::cout << "[测试 1: View Concepts 静态约束]: 断言全部验证通过。
";

       // 2. 惰性求值时机与调用探针验证
       std::vector<int> raw_events = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};
       std::size_t filter_invocations = 0;
       std::size_t transform_invocations = 0;

       auto probe_filter = [&filter_invocations](int x) {
           ++filter_invocations;
           return x % 2 == 0;
       };

       auto probe_transform = [&transform_invocations](int x) {
           ++transform_invocations;
           return x * 100;
       };

       // 构建管道阶段：断言不触发任何计算操作
       auto lazy_pipe = raw_events
           | mini::views::filter(std::ref(probe_filter))
           | mini::views::transform(std::ref(probe_transform))
           | mini::views::take(3);

       std::cout << "[测试 2.1: 管道组装期探测]:
";
       std::cout << "  - 谓词过滤调用计数: " << filter_invocations << "
";
       std::cout << "  - 映射转换调用计数: " << transform_invocations << "
";
       assert(filter_invocations == 0);
       assert(transform_invocations == 0);

       // 消费遍历阶段：按需流式计算
       std::vector<int> collected_results;
       for (int val : lazy_pipe) {
           collected_results.push_back(val);
       }

       std::cout << "[测试 2.2: 管道消费完成探测]:
";
       std::cout << "  - 产出元素集合大小: " << collected_results.size() << "
";
       std::cout << "  - 产出元素值: ";
       for (int v : collected_results) std::cout << v << " ";
       std::cout << "
";
       std::cout << "  - 消费后过滤调用计数: " << filter_invocations << "
";
       std::cout << "  - 消费后映射调用计数: " << transform_invocations << "
";

       // 物理推导验证:
       // 偶数 2, 4, 6 构成前 3 项。
       // 遍历扫描至元素 6 时已集齐 3 项，take 截断终止，元素 7~10 从未被触碰。
       assert(collected_results.size() == 3);
       assert(collected_results[0] == 200);
       assert(collected_results[1] == 400);
       assert(collected_results[2] == 600);
       assert(filter_invocations == 6);      // 依次探测 1(F), 2(T), 3(F), 4(T), 5(F), 6(T)
       assert(transform_invocations == 3);   // 仅对通过过滤的前 3 个偶数调用变换

       // 3. 闭包独立预合成与复用验证
       auto reusable_pipeline = mini::views::filter([](int x) { return x > 5; })
                              | mini::views::take(2);

       std::vector<int> dataset_a = {2, 4, 6, 8, 10};
       std::vector<int> dataset_b = {1, 3, 7, 9, 11};

       auto out_a = dataset_a | reusable_pipeline;
       auto out_b = dataset_b | reusable_pipeline;

       std::vector<int> res_a(out_a.begin(), out_a.end());
       std::vector<int> res_b(out_b.begin(), out_b.end());

       assert(res_a.size() == 2 && res_a[0] == 6 && res_a[1] == 8);
       assert(res_b.size() == 2 && res_b[0] == 7 && res_b[1] == 9);
       std::cout << "[测试 3: 独立闭包组合与多源复用]: 全部断言通过。

";
   }

   } // namespace test
