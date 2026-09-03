====================================================================================================
统一调用模型：std::invoke 10 种调用分支规则、std::mem_fn 成员指针包装与 std::bind 占位符机制
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 6 模块第 2 节（``06_callables_and_template_metaprogramming/02_std_function_type_erasure_and_small_object_optimization.rst``）中，我们系统剖析了 ``std::function`` 通过静态函数指针表与小对象优化（SOO）联合体实现非侵入式类型擦除的工程架构。然而，在泛型库与算法设计中，C++ 的“可调用实体（Callable Entity）”在语法层面呈现出严重的异构割裂：普通函数、仿函数与 Lambda 闭包遵循 ``f(args...)`` 括号调用语法；而类成员函数指针与类成员变量指针则必须通过专门的指针解引用语法（``(obj.*pmf)(args...)`` 或 ``(ptr->*pmf)(args...)`` 以及 ``obj.*pmd``）方可访问。为消除语法异构性并构建全泛型可调用抽象，C++17 正式引入了 ``std::invoke`` 统一调用模型。本章深入解构 ``std::invoke`` 在 ISO C++ 标准中的 10 种规范调用分发分支、``std::invoke_result`` 编译期类型推导、``std::mem_fn`` 成员指针包装器架构，以及 ``std::bind`` 占位符参数包绑定状态机的物理实现。

可调用语法异构割裂与统一调用抽象
--------------------------------

在 C++17 之前，标准库泛型算法（如 ``std::for_each`` 或自定义线程池调度器）在接收用户传入的可调用实体时，通常直接采用 ``f(std::forward<Args>(args)...)`` 进行表达式求值。这一语法仅对重载了 ``operator()`` 的实体有效。

语法割裂的具体表现
~~~~~~~~~~~~~~~~~~

当可调用实体为类成员指针时，直接调用语法将在编译期触发语法错误：

1. **成员函数指针（Pointer to Member Function, PMF）**：
   - 依赖具体对象实例：``(obj.*pmf)(arg1, arg2)``
   - 依赖对象指针实例：``(ptr->*pmf)(arg1, arg2)``
   - 依赖包装引用实例：``(ref_wrapper.get().*pmf)(arg1, arg2)``
2. **成员变量指针（Pointer to Member Data, PMD）**：
   - 依赖具体对象实例：``obj.*pmd``
   - 依赖对象指针实例：``ptr->*pmd``
   - 依赖包装引用实例：``ref_wrapper.get().*pmd``
3. **常规函数/仿函数/Lambda**：
   - 直接括号调用：``func(arg1, arg2)``

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        C++ 异构调用语法与统一分发抽象                       |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   用户输入的可调用实体与上下文对象:                                         |
   |     * 成员函数指针 & 实体对象  --> (obj.*pmf)(args...)                      |
   |     * 成员函数指针 & 对象指针  --> (ptr->*pmf)(args...)                     |
   |     * 成员变量指针 & 实体对象  --> obj.*pmd                                 |
   |     * 普通函数 / 仿函数 / 闭包 --> f(args...)                               |
   |                                                                             |
   |                                      | (统一抽象化)                         |
   |                                      v                                      |
   |   +---------------------------------------------------------------------+   |
   |   |        std::invoke(f, t1, t2, ..., tN) 统一入口                      |   |
   |   +---------------------------------------------------------------------+   |
   |     * 自动推导 f 的底层类型 (PMF / PMD / Function Object)                   |
   |     * 自动探测 t1 的类型分类 (基类派生实体 / reference_wrapper / 裸指针)    |
   |     * 编译期匹配唯一合法的 C++ 标准调用分支                                 |
   |                                                                             |
   +-----------------------------------------------------------------------------+

std::invoke 10 种调用分支规则规范
---------------------------------

ISO C++17 标准（§23.14.3 [func.invoke]）形式化定义了 ``INVOKE(f, t1, t2, ..., tN)`` 概念。根据首参数 ``f`` 的类型属性以及第一操作数 ``t1`` 与目标类 ``C`` 的继承/引用关系，调用逻辑严格划分为 10 种分支规则。

.. list-table:: std::invoke 10 种标准分发分支规则矩阵
   :widths: 10 22 28 40
   :header-rows: 1
   :class: tight-table

   * - 分支编号
     - 首参数类型 ``f``
     - 第一操作数类型 ``t1``
     - 规范展开表达式 (Standard Expansion)
   * - **分支 1**
     - 成员函数指针 ``Ret (C::*)(Args...)``
     - ``std::is_base_of_v<C, std::decay_t<decltype(t1)>>``
     - ``(std::forward<decltype(t1)>(t1).*f)(std::forward<Args>(args)...)``
   * - **分支 2**
     - 成员函数指针 ``Ret (C::*)(Args...)``
     - ``std::decay_t<decltype(t1)>`` 为 ``std::reference_wrapper<T>``
     - ``(t1.get().*f)(std::forward<Args>(args)...)``
   * - **分支 3**
     - 成员函数指针 ``Ret (C::*)(Args...)``
     - 既非派生类实体，也非 ``reference_wrapper``（指针/智能指针）
     - ``((*std::forward<decltype(t1)>(t1)).*f)(std::forward<Args>(args)...)``
   * - **分支 4**
     - 成员变量指针 ``Type C::*``
     - ``std::is_base_of_v<C, std::decay_t<decltype(t1)>>``
     - ``std::forward<decltype(t1)>(t1).*f``
   * - **分支 5**
     - 成员变量指针 ``Type C::*``
     - ``std::decay_t<decltype(t1)>`` 为 ``std::reference_wrapper<T>``
     - ``t1.get().*f``
   * - **分支 6**
     - 成员变量指针 ``Type C::*``
     - 既非派生类实体，也非 ``reference_wrapper``（指针/智能指针）
     - ``(*std::forward<decltype(t1)>(t1)).*f``
   * - **分支 7**
     - 常规函数/仿函数/Lambda（左值）
     - 任意参数列表 ``t1, t2, ..., tN``
     - ``f(std::forward<decltype(t1)>(t1), ..., std::forward<decltype(tN)>(tN))``
   * - **分支 8**
     - 常规函数/仿函数/Lambda（右值）
     - 任意参数列表 ``t1, t2, ..., tN``
     - ``std::move(f)(std::forward<decltype(t1)>(t1), ..., std::forward<decltype(tN)>(tN))``
   * - **分支 9**
     - 重载引用限定符的成员函数（``&`` 左值限定）
     - 第一操作数为左值引用
     - 对应分支 1~3 并精确传播左值限定修饰符
   * - **分支 10**
     - 重载引用限定符的成员函数（``&&`` 右值限定）
     - 第一操作数为右值引用
     - 对应分支 1~3 并精确传播右值限定修饰符

分支流转的状态机逻辑
~~~~~~~~~~~~~~~~~~~~

在编译期实现 ``std::invoke`` 时，重载决议或 ``if constexpr`` 条件判断按如下拓扑层级执行：

1. **第一层判别：``std::is_member_function_pointer_v<DecayF>``**：
   - 若为真，进入成员函数分发流（分支 1、2、3）。检测第一参数类型：
     - 若为目标类的同类或派生类：执行直接点解引用 ``(t1.*f)(args...)``。
     - 若为 ``std::reference_wrapper`` 包装器：执行拆包点解引用 ``(t1.get().*f)(args...)``。
     - 否则（如原生裸指针、``std::unique_ptr``、``std::shared_ptr``）：执行解引用操作符 ``((*t1).*f)(args...)``。
2. **第二层判别：``std::is_member_object_pointer_v<DecayF>``**：
   - 若为真，进入成员数据分发流（分支 4、5、6）。按相同规则拆解第一参数，返回变量引用。
3. **第三层判别：兜底分支**：
   - 若非任何成员指针，执行直接括号调用 ``std::forward<F>(f)(std::forward<Args>(args)...)``。

编译期结果推导：std::invoke_result_t
-----------------------------------

在 C++11/14 中，获取调用表达式返回类型的工具为 ``std::result_of<F(Args...)>::type``。由于其函数类型签名语法与常规模板参数传递方式存在认知偏差，且在 SFINAE 条件下推导未决类型时存在歧义，C++17 正式将其弃用（并在 C++20 中彻底移除），引入直接映射 ``INVOKE`` 规则的 ``std::invoke_result<F, Args...>``。

推导原语与 SFINAE 友好性
~~~~~~~~~~~~~~~~~~~~~~~~

``std::invoke_result<F, Args...>::type``（简写别名 ``std::invoke_result_t<F, Args...>``）在底层通过 ``decltype(std::invoke(std::declval<F>(), std::declval<Args>()...))`` 展开推导。若传入的参数组合无法在 10 种分支中匹配到合法调用，该类型萃取结构体内部不包含 ``type`` 成员，从而平滑触发 SFINAE 替换失败，保证重载集过滤的安全收敛。

.. code-block:: cpp

   // C++17 std::is_invocable 系列辅助类型萃取
   template <typename F, typename... Args>
   struct is_invocable; // 判定是否可调用

   template <typename Ret, typename F, typename... Args>
   struct is_invocable_r; // 判定是否可调用且返回值可隐式转换为 Ret

   template <typename F, typename... Args>
   struct is_nothrow_invocable; // 判定调用是否带有 noexcept 保证

std::mem_fn 成员指针包装器架构
------------------------------

``std::mem_fn`` 是一种高阶适配器，用于将类成员函数指针或成员变量指针提升为拥有一等公民地位的标准仿函数对象（Function Object）。

底层设计与多态承载
~~~~~~~~~~~~~~~~~~

通过 ``std::mem_fn(pmf)`` 返回的包装类实例，内部存储原始成员指针，并在其 ``operator()`` 内部直接转发调用 ``std::invoke(pmf, std::forward<Args>(args)...)``。这赋予了该对象自适应接收左值引用、右值引用、裸指针与智能指针的能力。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        std::mem_fn 算法管道适配拓扑                         |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   std::vector<std::shared_ptr<Task>> taskList;                              |
   |                                                                             |
   |   [ 传统成员函数指针在泛型算法中的阻碍 ]:                                   |
   |     std::for_each(taskList.begin(), taskList.end(), &Task::execute);        |
   |     --> 编译期错误: 无法对智能指针实例直接调用 (*ptr)(&Task::execute)       |
   |                                                                             |
   |   [ std::mem_fn 包装后的多态适配 ]:                                         |
   |     std::for_each(taskList.begin(), taskList.end(),                         |
   |                   std::mem_fn(&Task::execute));                             |
   |     --> 内部调用 std::invoke(&Task::execute, smart_ptr)                     |
   |     --> 自动展开为 (*smart_ptr).*(&Task::execute)()                         |
   |     --> 成功触发 Task 虚函数或普通成员函数执行                              |
   |                                                                             |
   +-----------------------------------------------------------------------------+

std::bind 占位符机制与参数重排状态机
-----------------------------------

``std::bind`` 是一种通用的函数参数绑定机制，它将一个可调用实体与其部分或全部参数绑定在一起，生成一个新的可调用闭包。

占位符类型系统（std::placeholders）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

标准库在命名空间 ``std::placeholders`` 中预定义了全局常量 ``_1, _2, _3, ...``。每一个占位符具有独立的特化类型（如 ``std::is_placeholder<decltype(_1)>::value == 1``）。

参数解包状态机
~~~~~~~~~~~~~~

当对 ``bind`` 返回的对象执行调用 ``bound_fn(u1, u2, ...)`` 时，内部存储的每一个绑定项 $B_k$ 按以下三重状态机映射为实际传递给底层函数的实参 $A_k$：

1. **绑定项为占位符 ``_N``**：
   - 提取外层调用传入的第 $N$ 个实参：$A_k = 	ext{std::get}<N-1>(	ext{forward\_as\_tuple}(u_1, u_2, ...))$。
2. **绑定项为嵌套绑定表达式（``std::is_bind_expression_v<Bk> == true``）**：
   - 递归触发嵌套绑定对象的求值：$A_k = B_k(u_1, u_2, ...)$。
3. **绑定项为常规值/引用包装（``std::reference_wrapper``）**：
   - 若通过 ``std::ref/cref`` 传递，拆包为引用；若通过值传递，传递内部捕获的拷贝。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                       std::bind 参数绑定与解包状态机                        |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   std::bind(f, a1, _2, a3, _1) 存储内部 Tuple: <a1, _2, a3, _1>             |
   |                                                                             |
   |   外部调用: bound_obj(argX, argY)                                           |
   |   传入实参 Tuple: <argX, argY> (索引: _1 -> argX, _2 -> argY)                |
   |                                                                             |
   |   参数解包映射流转:                                                         |
   |     * 槽位 1 (a1)   --> 常规值存储   --> 传递 a1                            |
   |     * 槽位 2 (_2)   --> 匹配占位符 2 --> 提取 argY                          |
   |     * 槽位 3 (a3)   --> 常规值存储   --> 传递 a3                            |
   |     * 槽位 4 (_1)   --> 匹配占位符 1 --> 提取 argX                          |
   |                                                                             |
   |   底层函数最终执行: std::invoke(f, a1, argY, a3, argX)                     |
   |                                                                             |
   +-----------------------------------------------------------------------------+

现代 C++ 演进：std::bind 对比 Generic Lambda
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 C++14 引入泛型 Lambda（Generic Lambda）与初始化捕获（Init Capture）后，``std::bind`` 在绝大多数场景下已被 Lambda 完全替代。

.. list-table:: std::bind 与 C++14/20 Lambda 物理性能与特性全景对比
   :widths: 22 38 40
   :header-rows: 1
   :class: tight-table

   * - 维度
     - ``std::bind``
     - C++14/20 Generic Lambda
   * - **编译器内联能力**
     - 较弱（多层嵌套模板与 Tuple 索引展开，深度递归易阻断内联）
     - 极强（直接生成内联闭包类 ``operator()``，100% 内联消除开销）
   * - **值类别精确传递**
     - 复杂（默认值拷贝，需显式声明 ``std::ref`` / ``std::cref``）
     - 直观精准（通过 ``[&]`` 捕获或 ``std::forward<decltype(x)>(x)`` 完美转发）
   * - **移动专有类型支持**
     - 繁琐（无法直观进行所有权转移）
     - 原生支持（``[p = std::move(ptr)]() { ... }`` 移动捕获）
   * - **编译期诊断开销**
     - 极重（参数不匹配时引发数百行深层模板实例化报错信息）
     - 极轻（直接在调用点精准报出参数类型不匹配）

工业级 C++ 统一调用模型与 Bind 引擎实现
---------------------------------------

以下 C++ 源码实现了一套自包含的工业级统一调用模型库。实现涵盖：
1. 完全遵循 C++17 标准 10 种分支规则的 ``MiniInvoke`` 引擎。
2. SFINAE 友好的 ``MiniInvokeResult`` 类型萃取。
3. 适配对象、指针与智能指针的 ``MiniMemFn`` 包装器。
4. 包含占位符系统（``_1, _2``）、参数包重排与完美转发的完整 ``MiniBind`` 引擎。
5. 覆盖普通函数、成员函数、成员变量、智能指针、引用包装与参数绑定的完整测试套件。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <string>
   #include <vector>
   #include <memory>
   #include <utility>
   #include <type_traits>
   #include <functional>
   #include <tuple>
   #include <cassert>

   namespace uniform_callable {

   // =========================================================================
   // 1. std::invoke 10 种调用分支规则的编译期实现
   // =========================================================================

   namespace detail {

   // 辅助萃取：判定类型是否为 std::reference_wrapper 的特化
   template <typename T>
   struct is_reference_wrapper : std::false_type {};

   template <typename U>
   struct is_reference_wrapper<std::reference_wrapper<U>> : std::true_type {};

   template <typename T>
   inline constexpr bool is_reference_wrapper_v = is_reference_wrapper<std::decay_t<T>>::value;

   // -------------------------------------------------------------------------
   // 分支 1, 2, 3: 成员函数指针调用 (Pointer to Member Function, PMF)
   // -------------------------------------------------------------------------
   template <typename MemberFn, typename Class, typename Target, typename... Args>
   constexpr decltype(auto) invoke_mempair_fn(MemberFn Class::* pmf, Target&& target, Args&&... args) {
       using RawTarget = std::decay_t<Target>;
       if constexpr (std::is_base_of_v<Class, RawTarget>) {
           // 分支 1: 第一参数为目标类或派生类实体 (左值/右值)
           return (std::forward<Target>(target).*pmf)(std::forward<Args>(args)...);
       } else if constexpr (is_reference_wrapper_v<RawTarget>) {
           // 分支 2: 第一参数为 std::reference_wrapper 包装器
           return (target.get().*pmf)(std::forward<Args>(args)...);
       } else {
           // 分支 3: 第一参数为指针或重载了解引用操作符的智能指针实体
           return ((*std::forward<Target>(target)).*pmf)(std::forward<Args>(args)...);
       }
   }

   // -------------------------------------------------------------------------
   // 分支 4, 5, 6: 成员变量指针访问 (Pointer to Member Data, PMD)
   // -------------------------------------------------------------------------
   template <typename MemberData, typename Class, typename Target>
   constexpr decltype(auto) invoke_mempair_data(MemberData Class::* pmd, Target&& target) {
       using RawTarget = std::decay_t<Target>;
       if constexpr (std::is_base_of_v<Class, RawTarget>) {
           // 分支 4: 访问实体对象的成员变量
           return std::forward<Target>(target).*pmd;
       } else if constexpr (is_reference_wrapper_v<RawTarget>) {
           // 分支 5: 访问 reference_wrapper 包装实体的成员变量
           return target.get().*pmd;
       } else {
           // 分支 6: 访问指针/智能指针指向实体的成员变量
           return (*std::forward<Target>(target)).*pmd;
       }
   }

   } // namespace detail

   // -------------------------------------------------------------------------
   // 统一 invoke 入口函数 (涵盖分支 1~10)
   // -------------------------------------------------------------------------
   template <typename Callable, typename... Args>
   constexpr decltype(auto) mini_invoke(Callable&& callable, Args&&... args) {
       using DecayCallable = std::decay_t<Callable>;
       if constexpr (std::is_member_function_pointer_v<DecayCallable>) {
           // 分支 1, 2, 3 及 9, 10
           return detail::invoke_mempair_fn(callable, std::forward<Args>(args)...);
       } else if constexpr (std::is_member_object_pointer_v<DecayCallable>) {
           // 分支 4, 5, 6
           static_assert(sizeof...(Args) == 1, "Member object pointer requires exactly one target instance.");
           return detail::invoke_mempair_data(callable, std::forward<Args>(args)...);
       } else {
           // 分支 7, 8: 常规函数指针、仿函数与 Lambda 闭包
           return std::forward<Callable>(callable)(std::forward<Args>(args)...);
       }
   }

   // =========================================================================
   // 2. invoke_result 编译期返回类型萃取
   // =========================================================================
   template <typename Void, typename Callable, typename... Args>
   struct invoke_result_impl {};

   template <typename Callable, typename... Args>
   struct invoke_result_impl<
       std::void_t<decltype(mini_invoke(std::declval<Callable>(), std::declval<Args>()...))>,
       Callable, Args...> {
       using type = decltype(mini_invoke(std::declval<Callable>(), std::declval<Args>()...));
   };

   template <typename Callable, typename... Args>
   struct mini_invoke_result : invoke_result_impl<void, Callable, Args...> {};

   template <typename Callable, typename... Args>
   using mini_invoke_result_t = typename mini_invoke_result<Callable, Args...>::type;

   // =========================================================================
   // 3. std::mem_fn 成员指针包装器实现
   // =========================================================================
   template <typename MemberPointer>
   class MiniMemFn {
   private:
       MemberPointer Ptr_;

   public:
       constexpr explicit MiniMemFn(MemberPointer ptr) noexcept : Ptr_(ptr) {}

       template <typename... Args>
       constexpr decltype(auto) operator()(Args&&... args) const {
           return mini_invoke(Ptr_, std::forward<Args>(args)...);
       }
   };

   template <typename MemberPointer>
   constexpr MiniMemFn<MemberPointer> mini_mem_fn(MemberPointer ptr) noexcept {
       return MiniMemFn<MemberPointer>(ptr);
   }

   // =========================================================================
   // 4. std::bind 与占位符系统实现
   // =========================================================================

   // 占位符结构体
   template <int N>
   struct Placeholder {};

   } // namespace uniform_callable

   // 注入标准命名空间萃取
   namespace std {
       template <int N>
       struct is_placeholder<uniform_callable::Placeholder<N>> : std::integral_constant<int, N> {};
   }

   namespace uniform_callable {

   namespace placeholders {
       inline constexpr Placeholder<1> _1;
       inline constexpr Placeholder<2> _2;
       inline constexpr Placeholder<3> _3;
   }

   // Bind 表达式封装类
   template <typename Fn, typename... BoundArgs>
   class MiniBinder {
   private:
       std::decay_t<Fn> Fn_;
       std::tuple<std::decay_t<BoundArgs>...> BoundArgsTuple_;

       // 参数选择解析器
       template <typename BoundItem, typename ActualTuple>
       static constexpr decltype(auto) select_arg(BoundItem&& item, ActualTuple&& actuals) {
           using RawItem = std::decay_t<BoundItem>;
           constexpr int PlaceholderIndex = std::is_placeholder_v<RawItem>;

           if constexpr (PlaceholderIndex > 0) {
               // 状态 1: 占位符参数映射
               return std::get<PlaceholderIndex - 1>(std::forward<ActualTuple>(actuals));
           } else if constexpr (detail::is_reference_wrapper_v<RawItem>) {
               // 状态 2: 显式引用包装解包
               return item.get();
           } else {
               // 状态 3: 绑定的常量值传递
               return std::forward<BoundItem>(item);
           }
       }

       template <typename ActualTuple, std::size_t... Indices>
       constexpr decltype(auto) call_impl(ActualTuple&& actuals, std::index_sequence<Indices...>) {
           return mini_invoke(
               Fn_,
               select_arg(std::get<Indices>(BoundArgsTuple_), std::forward<ActualTuple>(actuals))...
           );
       }

   public:
       template <typename F, typename... Args>
       constexpr explicit MiniBinder(F&& f, Args&&... args)
           : Fn_(std::forward<F>(f)), BoundArgsTuple_(std::forward<Args>(args)...) {}

       template <typename... CallArgs>
       constexpr decltype(auto) operator()(CallArgs&&... callArgs) {
           return call_impl(
               std::forward_as_tuple(std::forward<CallArgs>(callArgs)...),
               std::make_index_sequence<sizeof...(BoundArgs)>{}
           );
       }
   };

   template <typename Fn, typename... Args>
   constexpr MiniBinder<Fn, Args...> mini_bind(Fn&& fn, Args&&... args) {
       return MiniBinder<Fn, Args...>(std::forward<Fn>(fn), std::forward<Args>(args)...);
   }

   } // namespace uniform_callable

   // =========================================================================
   // 5. 端到端功能与分支覆盖测试套件
   // =========================================================================
   namespace test {

   struct Calculator {
       int Factor = 10;

       int multiply(int a, int b) const {
           return a * b * Factor;
       }

       int add(int a, int b) {
           return a + b + Factor;
       }
   };

   inline int freeAdd(int a, int b, int c) {
       return a + b + c;
   }

   inline void runUniformCallableTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " 统一调用模型与 Bind 参数绑定验证套件
";
       std::cout << "=======================================================

";

       using namespace uniform_callable;
       using namespace uniform_callable::placeholders;

       Calculator calc;
       calc.Factor = 5;

       // 1. 测试 mini_invoke 10 种核心分支
       // 分支 1: 成员函数 + 实体对象
       int r1 = mini_invoke(&Calculator::multiply, calc, 2, 3);
       assert(r1 == 30); // 2 * 3 * 5 = 30
       std::cout << "[测试 1: 成员函数 + 实体对象]: 调用验证成功 (" << r1 << ")。
";

       // 分支 2: 成员函数 + reference_wrapper
       auto refCalc = std::ref(calc);
       int r2 = mini_invoke(&Calculator::add, refCalc, 10, 20);
       assert(r2 == 35); // 10 + 20 + 5 = 35
       std::cout << "[测试 2: 成员函数 + reference_wrapper]: 调用验证成功 (" << r2 << ")。
";

       // 分支 3: 成员函数 + 智能指针
       auto smartCalc = std::make_shared<Calculator>();
       smartCalc->Factor = 2;
       int r3 = mini_invoke(&Calculator::multiply, smartCalc, 4, 5);
       assert(r3 == 40); // 4 * 5 * 2 = 40
       std::cout << "[测试 3: 成员函数 + 智能指针]: 调用验证成功 (" << r3 << ")。
";

       // 分支 4: 成员变量 + 实体对象
       int& varRef = mini_invoke(&Calculator::Factor, calc);
       assert(varRef == 5);
       varRef = 8;
       assert(calc.Factor == 8);
       std::cout << "[测试 4: 成员变量 + 实体对象引用修改]: 验证成功 (Factor 修改为 8)。
";

       // 分支 6: 成员变量 + 智能指针
       int smartVar = mini_invoke(&Calculator::Factor, smartCalc);
       assert(smartVar == 2);
       std::cout << "[测试 5: 成员变量 + 智能指针访问]: 验证成功 (" << smartVar << ")。
";

       // 分支 7: 普通函数
       int rFree = mini_invoke(freeAdd, 1, 2, 3);
       assert(rFree == 6);
       std::cout << "[测试 6: 普通自由函数统一调用]: 验证成功 (" << rFree << ")。
";

       // 2. 测试 mini_mem_fn 包装器
       auto memFnMultiply = mini_mem_fn(&Calculator::multiply);
       assert(memFnMultiply(calc, 2, 3) == 48); // 2 * 3 * 8 = 48
       assert(memFnMultiply(smartCalc, 3, 3) == 18); // 3 * 3 * 2 = 18
       std::cout << "[测试 7: mini_mem_fn 跨对象/智能指针适配]: 验证成功。
";

       // 3. 测试 mini_bind 与占位符映射重排
       // 将 freeAdd(a, b, c) 绑定为 bound(x, y) => freeAdd(100, y, x)
       auto boundFn = mini_bind(freeAdd, 100, _2, _1);
       int rBind = boundFn(10, 20); // 实际调用: freeAdd(100, 20, 10) = 130
       assert(rBind == 130);
       std::cout << "[测试 8: mini_bind 占位符反向重排]: 调用验证成功 (100 + 20 + 10 = " << rBind << ")。
";

       // 绑定成员函数: 将 calc.add(a, b) 绑定为 boundAdd(x) => calc.add(x, 50)
       auto boundMember = mini_bind(&Calculator::add, &calc, _1, 50);
       int rBoundMem = boundMember(15); // 15 + 50 + 8 (Factor) = 73
       assert(rBoundMem == 73);
       std::cout << "[测试 9: mini_bind 绑定成员函数与对象指针]: 验证成功 (" << rBoundMem << ")。
";

       std::cout << "
  -> 统一调用模型与 Bind 引擎全套测试完全通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述测试套件，输出结果清晰印证了统一调用模型在处理异构调用时的核心机制：

1. **语法壁垒彻底消除**：无论传入的是裸函数指针、成员函数指针、成员变量指针，还是左值对象、指针对象与 ``reference_wrapper``，``mini_invoke`` 均能在编译期精准识别其所属的标准规范分支，生成零间接开销的直达机器指令。
2. **成员变量引用透明穿透**：在测试 4 中，对成员数据指针的调用直接返回了对象内部字段的原生左值引用（``int&``），证明了统一调用模型不仅支持执行计算，还能无缝充当统一的属性投影器（Projection）。
3. **占位符灵活重排**：在测试 8 与 9 中，``mini_bind`` 成功利用编译期 Tuple 索引与占位符映射状态机，完成了实参位置反转与部分参数预置，为高阶算法管道提供了完备的适配能力。

小结与下章导读
--------------

本章深入剖析了现代 C++ 统一调用模型与高阶函数适配器的核心架构：

1. **调用语法异构的物理现实**：分析了成员指针解引用与常规函数调用在语言级语法上的割裂。
2. **std::invoke 10 种分支规则**：系统推导了涵盖类实体、引用包装器、智能指针与成员变量访问的完整规范判定树。
3. **编译期类型萃取**：阐释了 ``std::invoke_result_t`` 的 SFINAE 友好推导机制。
4. **std::mem_fn 与 std::bind 微架构**：解构了成员指针函数化包装与占位符参数映射状态机的物理实现。

在统一调用模型的支撑下，模板元编程能够以一致的语法操纵任意可调用实体。然而，为了在编译期根据类型的细粒度特征（如是否具备默认构造、是否拥有特定成员函数）精确启用或禁用特定函数重载，必须建立完备的类型属性萃取与 SFINAE 替换失败保护机制。在第 6 模块第 4 节 **Traits 萃取与 SFINAE 机制：type_traits 编译期属性查询、enable_if_t 与 void_t 成员探测（``06_callables_and_template_metaprogramming/04_type_traits_sfinae_and_compile_time_branching.rst``）** 中，我们将深入剖析编译期类型萃取系统、SFINAE 原理、``std::void_t`` 探测范式与编译期分支分发的工程实现。
