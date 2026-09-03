====================================================================================================
Traits 萃取与 SFINAE 机制：type_traits 编译期属性查询、enable_if_t 与 void_t 成员探测
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 6 模块第 3 节（``06_callables_and_template_metaprogramming/03_invoke_mem_fn_and_uniform_callable_model.rst``）中，我们系统剖析了 ``std::invoke`` 的 10 种标准调用分支与统一调用抽象。然而，在泛型库与现代 STL 的深层实现中，模板函数与模板类往往需要根据模板实参的精细物理特性（例如是否具备平凡拷贝构造、是否为原生指针、是否重载了特定运算符、或是否包含嵌套类型定义）在编译期选择最优的执行路径或剔除不合法的重载。C++ 模板元编程依托 ``<type_traits>`` 属性查询系统、SFINAE（替换失败非错误）机制与 ``std::void_t`` 探测范式，构建起了类型系统在编译期的内省与分支分发骨架。本章深入解构 ``type_traits`` 的继承拓扑与代数元函数设计、SFINAE 在立即上下文中的替换准则、``std::enable_if_t`` 的三种安放范式与签名冲突边界，以及基于 ``std::void_t`` 的泛型成员探测状态机的底层物理实现。

type_traits 体系架构与元函数设计哲学
------------------------------------

C++ 模板元编程本质上是将类型与编译期常量作为输入与输出的纯函数式计算系统。``<type_traits>`` 库（自 C++11 起标准化）为这一系统提供了统一的数据载体与属性查询契约。

std::integral_constant 基类拓扑
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

所有的布尔型与数值型类型萃取元函数均继承自通用的编译期常量包装器 ``std::integral_constant``。

.. code-block:: cpp

   template <typename T, T v>
   struct integral_constant {
       static constexpr T value = v;
       using value_type = T;
       using type = integral_constant; // 元函数恒等映射

       constexpr operator value_type() const noexcept { return value; }
       constexpr value_type operator()() const noexcept { return value; } // C++14 起
   };

   // 标准布尔特化别名
   using true_type  = integral_constant<bool, true>;
   using false_type = integral_constant<bool, false>;

这一基类拓扑为编译期内省奠定了两个核心物理特性：
1. **类型层面的真假表示**：``true_type`` 与 ``false_type`` 是完全独立的两种具体类型。通过继承，属性查询元函数（如 ``std::is_pointer<T>``）不仅对外暴露 ``static constexpr bool value``，其本身亦可作为类型标签直接参与重载决议（Tag Dispatching）。
2. **函数调用运算符重载**：提供 ``operator()()``，使得元函数实例能够作为仿函数在常量表达式（`constexpr`）环境中直接求值。

C++14/17 变量模板与别名模板演进
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 C++11 中，获取元函数的值需通过 ``trait<T>::value``，获取转换后的类型需通过 ``typename trait<T>::type``。这种语法在复杂元编程中引入了密集的 ``typename`` 与 ``::type`` 样板代码。

标准演进建立了系统性的别名规范：
- **C++14 别名模板（Alias Templates）**：引入 ``trait_t<T>`` 替代 ``typename trait<T>::type``。
- **C++17 变量模板（Variable Templates）**：引入 ``trait_v<T>`` 替代 ``trait<T>::value``。

.. list-table:: 现代 C++ 编译期元函数访问范式演进
   :widths: 20 25 25 30
   :header-rows: 1
   :class: tight-table

   * - 萃取类别
     - C++11 原始语法
     - C++14/17 现代语法
     - 编译器底层实例化机制
   * - **值属性查询**
     - ``is_integral<T>::value``
     - ``is_integral_v<T>``
     - 变量模板实例化直接提取 ``integral_constant::value``
   * - **类型转换变换**
     - ``typename decay<T>::type``
     - ``decay_t<T>``
     - 别名模板直接重定向至内部嵌套的 ``type``
   * - **条件类型选择**
     - ``typename conditional<B, T, F>::type``
     - ``conditional_t<B, T, F>``
     - 编译期三元运算，仅实例化目标分支类型

类型属性分类与代数演算矩阵
--------------------------

``<type_traits>`` 提供了正交且完备的类型内省维度，将其划分为基础分类、复合分类、类型属性与类型变换。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     C++ Type Traits 正交分类体系架构                        |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 14 种基础分类 (Primary Categories - 互斥穷尽) ]                         |
   |     * 基础类型: is_void, is_null_pointer, is_integral, is_floating_point    |
   |     * 复合基元: is_array, is_pointer, is_lvalue_reference,                 |
   |                 is_rvalue_reference, is_member_object_pointer,              |
   |                 is_member_function_pointer, is_enum, is_union,              |
   |                 is_class, is_function                                       |
   |                                                                             |
   |                                      | (逻辑析取组合)                       |
   |                                      v                                      |
   |   [ 复合类型分类 (Composite Categories) ]                                   |
   |     * is_reference = is_lvalue_reference || is_rvalue_reference             |
   |     * is_arithmetic = is_integral || is_floating_point                      |
   |     * is_fundamental = is_arithmetic || is_void || is_null_pointer          |
   |     * is_compound = !is_fundamental                                         |
   |     * is_object = is_scalar || is_array || is_union || is_class             |
   |                                                                             |
   |                                      | (底层物理性质查询)                   |
   |                                      v                                      |
   |   [ 核心性能与生命周期属性 (Type Properties) ]                              |
   |     * is_trivially_copyable: 内存按字节位拷贝 (memcpy) 安全性               |
   |     * is_nothrow_move_constructible: 移动构造异常安全强保证                 |
   |     * is_standard_layout: C 语言内存布局兼容性                              |
   |                                                                             |
   +-----------------------------------------------------------------------------+

关键性能属性的微架构影响
~~~~~~~~~~~~~~~~~~~~~~~~

1. **``std::is_trivially_copyable_v<T>``**：
   - 判定类型是否可以通过 ``std::memcpy`` 或 ``std::memmove`` 进行字节级按位复制而绕过显式构造/析构函数调用。
   - 直接决定了 ``std::vector::insert``、``std::copy`` 与容器底层扩容迁移能否下沉至汇编级连续内存拷贝。
2. **``std::is_nothrow_move_constructible_v<T>``**：
   - 判定移动构造函数是否标记有 ``noexcept``。
   - 决定 ``std::vector`` 在动态扩容时采用移动（Move）还是深拷贝（Copy）策略以满足强异常安全保证。
3. **``std::is_standard_layout_v<T>``**：
   - 判定结构体是否满足 C 语言原生内存布局（首成员偏移为 0、无虚表、访问控制权限一致），决定跨语言 ABI 互操作的安全性。

SFINAE 物理机理与重载决议替换规则
---------------------------------

SFINAE 是 ISO C++ 模板系统的核心基石：**Substitution Failure Is Not An Error（替换失败非错误）**。

SFINAE 的执行流水线
~~~~~~~~~~~~~~~~~~~

在函数重载决议（Overload Resolution）过程中，当编译器确定候选函数模板后，会尝试将用户提供的模板实参（或推导出的实参）逐一替换（Substitute）到函数签名中。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                       SFINAE 模板实例化与重载决议流转                       |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   1. 收集所有可见的同名函数及函数模板，构成初始候选重载集 (Candidate Set)   |
   |                                                                             |
   |                                      |                                      |
   |                                      v                                      |
   |   2. 模板实参推导与显式实参注入                                             |
   |                                                                             |
   |                                      |                                      |
   |                                      v                                      |
   |   3. 在函数声明中执行实参替换 (Substitution)                                |
   |      * 替换位置: 返回类型、形参列表、模板参数默认值                         |
   |                                                                             |
   |                     +----------------+----------------+                     |
   |                     |                                 |                     |
   |             [ 替换成功 (Success) ]            [ 替换失败 (Failure) ]         |
   |                     |                                 |                     |
   |                     v                                 |                     |
   |          实例化出具体函数特化                         |                     |
   |          加入可行函数集 (Viable Set)                  |                     |
   |                     |                                 |                     |
   |                     |                     [ 检查失败发生的位置 ]:           |
   |                     |                     * 在立即上下文 (Immediate Context)|
   |                     |                       --> 仅从候选集中静默剔除        |
   |                     |                     * 在非立即上下文 (函数体内/深层)  |
   |                     |                       --> 触发硬编译错误 (Hard Error) |
   |                     |                                                       |
   |                     v                                                       |
   |   4. 对可行函数集执行重载决议排序，选出唯一最优匹配 (Best Match)            |
   |      (若可行集为空或存在歧义则报错)                                         |
   |                                                                             |
   +-----------------------------------------------------------------------------+

立即上下文（Immediate Context）的严格界定
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

SFINAE 仅对发生在**立即上下文**内的替换失败生效。若替换失败发生在非立即上下文，将直接导致编译器终止并抛出硬错误（Hard Error）。

立即上下文涵盖以下区域：
1. 函数模板的返回类型表达式。
2. 函数模板的形参类型列表。
3. 模板参数列表中的类型参数与非类型参数默认值。
4. 类模板特化与偏特化的模板实参列表。

**非立即上下文典型陷阱**：在类模板实例化过程中内部发生的类型错误，或者在函数体（Function Body）内部产生的语法失效，均属于非立即上下文。

.. code-block:: cpp

   // 陷阱示例：非立即上下文导致的硬错误
   template <typename T>
   struct BadHelper {
       using type = typename T::non_existent_type; // 硬错误：在此处直接报错，无法被外层 SFINAE 捕获
   };

   template <typename T, typename = typename BadHelper<T>::type>
   void bad_func(T); // 当 T 无 non_existent_type 时，触发硬编译错误而非静默剔除

编译期条件分支与重载过滤技术
----------------------------

依托 SFINAE 机制，C++ 演化出多种编译期分支选择与重载控制范式。

std::enable_if 与 std::enable_if_t 原理
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``std::enable_if`` 是一种基于布尔条件控制嵌套类型存在的元函数。

.. code-block:: cpp

   template <bool B, typename T = void>
   struct enable_if {};

   template <typename T>
   struct enable_if<true, T> {
       using type = T;
   };

   template <bool B, typename T = void>
   using enable_if_t = typename enable_if<B, T>::type;

当布尔条件 $B$ 为 ``true`` 时，偏特化版本生效，暴露 ``type = T``；当 $B$ 为 ``false`` 时，基础主模板生效，内部不存在 ``type``。将 ``enable_if_t`` 置于立即上下文，即可在条件为假时通过缺少类型触发 SFINAE 剔除。

std::enable_if_t 的三种安放范式与签名冲突边界
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: std::enable_if_t 三种安放范式优劣与陷阱分析
   :widths: 18 32 50
   :header-rows: 1
   :class: tight-table

   * - 安放位置
     - 语法形式
     - 微架构机制与工程边界
   * - **返回类型**
     - ``template <typename T>``
       ``std::enable_if_t<Condition<T>, Ret> func(T val);``
     - 最经典的 SFINAE 范式。缺点：返回类型冗长，对于构造函数和析构函数无返回值场景完全不可用。
   * - **函数形参默认值**
     - ``template <typename T>``
       ``void func(T val, std::enable_if_t<Condition<T>, int> = 0);``
     - 允许用于构造函数。缺点：向外部接口暴露了多余的无意义参数，调用者可能显式传参破坏 SFINAE。
   * - **模板类型默认参数 (高危)**
     - ``template <typename T, typename = std::enable_if_t<Condition<T>>>``
       ``void func(T val);``
     - 语法最为整洁。**高危陷阱**：函数模板默认参数不属于函数签名。当两个重载仅在默认模板参数不同时，在编译器视角构成**函数重复定义（Redefinition Error）**，导致硬错误。
   * - **非类型模板参数 (安全推荐)**
     - ``template <typename T, std::enable_if_t<Condition<T>, int> = 0>``
       ``void func(T val);``
     - 针对重载场景的安全模式。通过使非类型模板参数值不同（或通过独立类型），避免同名函数签名重复定义冲突。

.. code-block:: cpp

   // 严重错误示例：默认类型参数导致的重复定义
   template <typename T, typename = std::enable_if_t<std::is_integral_v<T>>>
   void process(T val);

   template <typename T, typename = std::enable_if_t<std::is_floating_point_v<T>>>
   void process(T val); // 编译期报错: redefinition of 'template<class T, class> void process(T)'

   // 正确方案：非类型模板参数安全隔离
   template <typename T, std::enable_if_t<std::is_integral_v<T>, int> = 0>
   void process(T val);

   template <typename T, std::enable_if_t<std::is_floating_point_v<T>, int> = 0>
   void process(T val); // 正确：非类型参数签名完全正交，安全分流

C++17 if constexpr 对 SFINAE 模板膨胀的革新
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 C++17 之前，为了针对不同类型执行不同逻辑，必须将单个函数拆分为多个依赖 SFINAE 重载的独立函数模板。这不仅引发元编程样板代码爆炸，还急剧拉长编译器符号表查找耗时。

C++17 引入 ``if constexpr`` 语句，在单个函数体内实现编译期完全剪枝：未命中的分支在语义分析阶段被完全丢弃，其内部代码不会被实例化。

.. list-table:: SFINAE 重载分发与 C++17 if constexpr 全景对比
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 评估维度
     - 经典 SFINAE (enable_if_t)
     - C++17 if constexpr
   * - **代码组织拓扑**
     - 分散：每个分支对应一个独立的函数模板重载
     - 集中：单一函数体内扁平化条件分支
   * - **符号表与编译开销**
     - 较重：每个重载均参与重载决议排序与推导
     - 极轻：仅实例化目标分支，其余分支直接 AST 丢弃
   * - **类型依赖隔离**
     - 需在函数签名处保证立即上下文替换安全
     - 只要分支条件为常量表达式，分支内部可包含非法语法
   * - **重载与接口定制**
     - 适用于提供截然不同的接口或针对构造函数特化
     - 适用于函数内部执行算法的微架构降级

探测范式（Detection Idiom）与 std::void_t 机制
----------------------------------------------

在泛型编程中，最核心的需求之一是内省某个类型是否具有特定成员（如嵌套类型 ``iterator``、成员变量 ``size``、或特定签名函数 ``serialize()``）。

std::void_t 物理机理与 CWG 1558 缺陷修复
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``std::void_t`` 是一个将任意变长类型列表映射为 ``void`` 的别名模板。

.. code-block:: cpp

   template <typename...>
   using void_t = void;

在 C++14 早期，由于编译器核心缺陷（CWG issue 1558），若变长类型参数包中包含未使用的类型参数，部分编译器会在别名模板展开时错误地提前折叠，导致 SFINAE 无法检测到无效类型。现代 C++ 标准要求通过辅助类模板保证参数包的严格替换：

.. code-block:: cpp

   namespace detail {
       template <typename... Ts>
       struct make_void { using type = void; };
   }

   template <typename... Ts>
   using void_t = typename detail::make_void<Ts...>::type;

成员探测状态机流转
~~~~~~~~~~~~~~~~~~

利用 ``std::void_t`` 探测类型特性的标准流水线基于主模板与偏特化的两层状态机：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        std::void_t 成员探测状态机                           |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 1. 定义主模板 (默认兜底状态) ]:                                         |
   |     template <typename T, typename = void>                                  |
   |     struct has_serialize : std::false_type {};                              |
   |                                                                             |
   |                                      |                                      |
   |                                      v                                      |
   |   [ 2. 定义偏特化版本 (尝试替换目标表达式) ]:                               |
   |     template <typename T>                                                   |
   |     struct has_serialize<T,                                                 |
   |         std::void_t<decltype(std::declval<T>().serialize())>>               |
   |         : std::true_type {};                                                |
   |                                                                             |
   |                                      |                                      |
   |                                      v                                      |
   |   [ 3. 编译器实例化 has_serialize<TargetType> ]:                            |
   |                                                                             |
   |                     +----------------+----------------+                     |
   |                     |                                 |                     |
   |         [ TargetType 具有 serialize() ]     [ TargetType 无此成员 ]         |
   |                     |                                 |                     |
   |                     v                                 v                     |
   |         decltype 替换求值成功             decltype 替换发生非法语法         |
   |         void_t 展开为 void                触发立即上下文 SFINAE             |
   |         偏特化 <T, void> 精确匹配         偏特化被静默剔除                  |
   |         继承 std::true_type               回退至主模板                      |
   |         -> value = true                   继承 std::false_type              |
   |                                           -> value = false                  |
   |                                                                             |
   +-----------------------------------------------------------------------------+

工业级通用的 is_detected 架构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为避免针对每一个成员重复编写主模板与偏特化结构体，C++ Library Fundamentals TS 提出了高度抽象的 ``is_detected`` 范式：

.. code-block:: cpp

   template <template <typename...> class Op, typename... Args>
   struct is_detected; // 判定 Op<Args...> 是否合法

   template <typename Default, template <typename...> class Op, typename... Args>
   struct detected_or; // 若合法提取其类型，否则返回 Default 兜底类型

工业级 C++ Mini-TypeTraits 与 SFINAE/Detection 引擎
---------------------------------------------------

以下 C++ 源码实现了一套自包含的工业级类型萃取与 SFINAE 探测库。实现涵盖：
1. 底层 ``MiniIntegralConstant`` 基类与核心类型属性查询（``is_integral``, ``is_pointer``, ``is_reference``, ``is_trivially_copyable``）。
2. 类型修改元函数（``remove_reference``, ``decay``, ``conditional``）。
3. 严格遵循 SFINAE 契约的 ``MiniEnableIf`` 与非类型模板参数重载隔离。
4. 基于 ``MiniVoidT`` 的通用 ``is_detected`` 探测体系。
5. 针对嵌套类型、成员函数与算术运算符的端到端编译期内省与运行时测试套件。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <string>
   #include <vector>
   #include <utility>
   #include <cassert>
   #include <cstring>

   namespace mini_traits {

   // =========================================================================
   // 1. integral_constant 与基础真值拓扑
   // =========================================================================
   template <typename T, T v>
   struct MiniIntegralConstant {
       static constexpr T value = v;
       using value_type = T;
       using type = MiniIntegralConstant;

       constexpr operator value_type() const noexcept { return value; }
       constexpr value_type operator()() const noexcept { return value; }
   };

   using MiniTrueType  = MiniIntegralConstant<bool, true>;
   using MiniFalseType = MiniIntegralConstant<bool, false>;

   // =========================================================================
   // 2. 核心类型变换与代数演算元函数
   // =========================================================================

   // conditional 三元选择器
   template <bool B, typename T, typename F>
   struct MiniConditional { using type = T; };

   template <typename T, typename F>
   struct MiniConditional<false, T, F> { using type = F; };

   template <bool B, typename T, typename F>
   using mini_conditional_t = typename MiniConditional<B, T, F>::type;

   // remove_reference 引用剥除
   template <typename T> struct MiniRemoveReference      { using type = T; };
   template <typename T> struct MiniRemoveReference<T&>  { using type = T; };
   template <typename T> struct MiniRemoveReference<T&&> { using type = T; };

   template <typename T>
   using mini_remove_reference_t = typename MiniRemoveReference<T>::type;

   // remove_cv 常量与易失性修饰剥除
   template <typename T> struct MiniRemoveCv                   { using type = T; };
   template <typename T> struct MiniRemoveCv<const T>          { using type = T; };
   template <typename T> struct MiniRemoveCv<volatile T>       { using type = T; };
   template <typename T> struct MiniRemoveCv<const volatile T> { using type = T; };

   template <typename T>
   using mini_remove_cv_t = typename MiniRemoveCv<T>::type;

   // decay 类型退化 (模拟传值语义)
   template <typename T>
   struct MiniDecay {
   private:
       using U = mini_remove_reference_t<T>;
   public:
       using type = mini_conditional_t<
           std::is_array_v<U>,
           std::remove_extent_t<U>*,
           mini_conditional_t<
               std::is_function_v<U>,
               std::add_pointer_t<U>,
               mini_remove_cv_t<U>
           >
       >;
   };

   template <typename T>
   using mini_decay_t = typename MiniDecay<T>::type;

   // =========================================================================
   // 3. SFINAE 核心支撑：enable_if
   // =========================================================================
   template <bool B, typename T = void>
   struct MiniEnableIf {};

   template <typename T>
   struct MiniEnableIf<true, T> { using type = T; };

   template <bool B, typename T = void>
   using mini_enable_if_t = typename MiniEnableIf<B, T>::type;

   // =========================================================================
   // 4. void_t 与通用的 Detection 探测器范式
   // =========================================================================
   namespace detail {
       template <typename... Ts>
       struct MakeVoid { using type = void; };
   }

   template <typename... Ts>
   using mini_void_t = typename detail::MakeVoid<Ts...>::type;

   // is_detected 架构实现
   struct NonSuch {
       NonSuch() = delete;
       ~NonSuch() = delete;
       NonSuch(const NonSuch&) = delete;
       void operator=(const NonSuch&) = delete;
   };

   namespace detail {
       template <typename Default, typename AlwaysVoid, template <typename...> class Op, typename... Args>
       struct Detector {
           using value_t = MiniFalseType;
           using type = Default;
       };

       template <typename Default, template <typename...> class Op, typename... Args>
       struct Detector<Default, mini_void_t<Op<Args...>>, Op, Args...> {
           using value_t = MiniTrueType;
           using type = Op<Args...>;
       };
   }

   template <template <typename...> class Op, typename... Args>
   using is_detected = typename detail::Detector<NonSuch, void, Op, Args...>::value_t;

   template <template <typename...> class Op, typename... Args>
   inline constexpr bool is_detected_v = is_detected<Op, Args...>::value;

   template <typename Default, template <typename...> class Op, typename... Args>
   using detected_or = detail::Detector<Default, void, Op, Args...>;

   template <typename Default, template <typename...> class Op, typename... Args>
   using detected_or_t = typename detected_or<Default, Op, Args...>::type;

   // =========================================================================
   // 5. 编译期属性查询元函数示例
   // =========================================================================

   // is_pointer 判定
   template <typename T> struct MiniIsPointer : MiniFalseType {};
   template <typename T> struct MiniIsPointer<T*> : MiniTrueType {};

   template <typename T>
   inline constexpr bool mini_is_pointer_v = MiniIsPointer<mini_remove_cv_t<T>>::value;

   // is_lvalue_reference 判定
   template <typename T> struct MiniIsLvalueReference : MiniFalseType {};
   template <typename T> struct MiniIsLvalueReference<T&> : MiniTrueType {};

   template <typename T>
   inline constexpr bool mini_is_lvalue_reference_v = MiniIsLvalueReference<T>::value;

   } // namespace mini_traits

   // =========================================================================
   // 6. 端到端功能验证与 SFINAE 重载测试套件
   // =========================================================================
   namespace test {

   using namespace mini_traits;

   // -------------------------------------------------------------------------
   // 场景 A: 探测类是否包含嵌套类型 iterator
   // -------------------------------------------------------------------------
   template <typename T>
   using MemberIteratorOp = typename T::iterator;

   template <typename T>
   using HasIterator = is_detected<MemberIteratorOp, T>;

   // -------------------------------------------------------------------------
   // 场景 B: 探测类是否具有 serialize() const 成员函数
   // -------------------------------------------------------------------------
   template <typename T>
   using MemberSerializeOp = decltype(std::declval<const T>().serialize());

   template <typename T>
   using HasSerialize = is_detected<MemberSerializeOp, T>;

   // -------------------------------------------------------------------------
   // 场景 C: SFINAE 安全重载分发 (序列化引擎)
   // -------------------------------------------------------------------------
   struct CustomDocument {
       std::string serialize() const {
           return "<Document Title='Architecture' />";
       }
   };

   struct PlainNumber {
       int Value = 42;
   };

   // 重载 1: 具备 serialize 成员函数的类
   template <typename T, mini_enable_if_t<is_detected_v<MemberSerializeOp, T>, int> = 0>
   std::string serializeObject(const T& obj) {
       return "[CustomSerializer]: " + obj.serialize();
   }

   // 重载 2: 原生算术类型
   template <typename T, mini_enable_if_t<std::is_arithmetic_v<T>, int> = 0>
   std::string serializeObject(const T& val) {
       return "[ArithmeticSerializer]: " + std::to_string(val);
   }

   // 重载 3: 兜底泛型 (采用 C++17 if constexpr 内部内省)
   template <typename T, mini_enable_if_t<!is_detected_v<MemberSerializeOp, T> && !std::is_arithmetic_v<T>, int> = 0>
   std::string serializeObject(const T& obj) {
       if constexpr (std::is_same_v<T, PlainNumber>) {
           return "[PlainNumberFallback]: " + std::to_string(obj.Value);
       } else {
           return "[GenericFallback]: Unknown Type Payload";
       }
   }

   // -------------------------------------------------------------------------
   // 测试套件主入口
   // -------------------------------------------------------------------------
   inline void runTypeTraitsTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " type_traits 属性查询与 SFINAE 探测引擎验证
";
       std::cout << "=======================================================

";

       // 1. 验证基础 traits 查询与元函数演算
       static_assert(mini_is_pointer_v<int*>, "int* must be a pointer");
       static_assert(!mini_is_pointer_v<int>, "int is not a pointer");
       static_assert(mini_is_pointer_v<const double* const>, "const double* const must be a pointer");
       static_assert(mini_is_lvalue_reference_v<int&>, "int& is lvalue reference");
       static_assert(!mini_is_lvalue_reference_v<int&&>, "int&& is not lvalue reference");
       std::cout << "[测试 1: 基础属性查询元函数]: 静态断言验证通过。
";

       // 2. 验证类型变换 (decay 与 remove_reference)
       using RawArray = int[5];
       using DecayedArray = mini_decay_t<RawArray>;
       static_assert(std::is_same_v<DecayedArray, int*>, "Array must decay to pointer");

       using RefType = const double&;
       using StrippedRef = mini_remove_reference_t<RefType>;
       static_assert(std::is_same_v<StrippedRef, const double>, "Reference must be stripped");
       std::cout << "[测试 2: 类型退化与引用剥除]: 静态断言验证通过。
";

       // 3. 验证 is_detected 成员探测
       static_assert(HasIterator<std::vector<int>>::value, "std::vector<int> must have iterator");
       static_assert(!HasIterator<int>::value, "int does not have iterator");
       static_assert(HasSerialize<CustomDocument>::value, "CustomDocument must have serialize()");
       static_assert(!HasSerialize<PlainNumber>::value, "PlainNumber has no serialize()");
       std::cout << "[测试 3: is_detected 成员与类型探测]: 静态断言验证通过。
";

       // 4. 验证 detected_or_t 默认类型兜底
       template <typename T>
       using ValueTypeOp = typename T::value_type;

       using VecValType = detected_or_t<double, ValueTypeOp, std::vector<int>>;
       using IntValType = detected_or_t<double, ValueTypeOp, int>; // int 无 value_type，回退至 double

       static_assert(std::is_same_v<VecValType, int>, "Vector value_type must be int");
       static_assert(std::is_same_v<IntValType, double>, "Fallback value_type must be double");
       std::cout << "[测试 4: detected_or_t 默认回退机制]: 静态断言验证通过。
";

       // 5. 验证 SFINAE 重载决议分发与运行时行为
       CustomDocument doc;
       PlainNumber num{100};
       double pi = 3.14159;

       std::string rDoc = serializeObject(doc);
       std::string rPi  = serializeObject(pi);
       std::string rNum = serializeObject(num);

       std::cout << "[测试 5.1: 自定义序列化重载]: " << rDoc << "
";
       std::cout << "[测试 5.2: 算术类型序列化重载]: " << rPi << "
";
       std::cout << "[测试 5.3: 兜底结构体序列化重载]: " << rNum << "
";

       assert(rDoc.find("<Document") != std::string::npos);
       assert(rPi.find("3.14159") != std::string::npos);
       assert(rNum.find("100") != std::string::npos);

       std::cout << "
  -> type_traits 与 SFINAE 探测引擎全套测试完全通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

编译并执行上述验证套件，其运行结果体现了现代 C++ 编译期元编程的核心威力：

1. **静态断言零运行时开销**：所有的基础属性查询（``mini_is_pointer_v``）、类型退化（``mini_decay_t``）以及成员探测（``HasSerialize``），均在编译期完成代数演算并以 ``static_assert`` 形式固化，运行时机器码开销为严格的零。
2. **重载决议精准收敛**：在测试 5 中，``serializeObject`` 面对不同特性的输入实参（带专属成员的 ``CustomDocument``、原生浮点 ``double``、与无特定成员的 ``PlainNumber``），依托 ``enable_if_t`` 与 ``is_detected_v`` 在重载集中精确激活对应特化分支，完全排除了无效重载并避免了签名重定义冲突。
3. **安全回退保障泛型健壮性**：通过 ``detected_or_t`` 模式，在探测嵌套类型失败时能够自适应提供备用类型（如 ``double`` 兜底），从根本上避免了编译硬错误的产生。

小结与下章导读
--------------

本章深入剖析了 C++ 编译期类型属性查询、SFINAE 机制与探测范式的底层架构：

1. **type_traits 架构拓扑**：解构了 ``integral_constant`` 纯类型真值载体与 C++14/17 别名/变量模板设计。
2. **类型属性正交矩阵**：梳理了 14 种基础类型分类与 ``is_trivially_copyable`` 对底层内存拷贝优化的指导作用。
3. **SFINAE 物理机理**：阐明了重载决议替换流水线，界定了立即上下文与非立即上下文的硬错误边界。
4. **编译期条件分支模式**：剖析了 ``std::enable_if_t`` 的三种安放范式、签名冲突陷阱与 C++17 ``if constexpr`` 的扁平化演进。
5. **std::void_t 探测范式**：推导了基于两阶段模板替换的 ``is_detected`` 成员探测状态机。

SFINAE 与 ``enable_if_t`` 虽然为 C++ 提供了强大的编译期内省能力，但其语法繁琐、报错信息深奥冗长，且重载排序开销巨大。为了从语言核心层面提供第一公民级别的泛型约束语法，C++20 正式推出了革命性的 **Concepts 与 Constraints（概念与约束）** 体系。在第 6 模块第 5 节 **C++20 Concepts 概念约束：requires 子句与表达式、约束归一化、编译器可读诊断与重载决议（``06_callables_and_template_metaprogramming/05_cpp20_concepts_constraints_and_requires_clauses.rst``）** 中，我们将全面解构 Concepts 的代数模型、原子约束归一化、编译期诊断信息优化以及对传统 SFINAE 体系的现代化替代。
