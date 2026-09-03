==================================================================================================================================
泛型模板底层基石：实例化机制、参数推导、变长参数包展开、依赖类型 typename 与二阶段名字查找
==================================================================================================================================

.. note:: 前置背景与上下文承接
   在前一章《物理内存管理体系与 RAII 哲学：malloc/free 与 new/delete 表达式解构、placement new、未初始化内存与缓存局部性》中，系统剖析了 C++ 物理内存分配、构造析构解耦与 RAII 确定性生命周期绑定。C++ 标准模板库（STL）的高性能基石在于将通用数据结构与泛型算法建立在零运行时抽象开销的类型系统之上。本章将视野转向编译期计算核心，深入解构 C++ 模板系统的底层工程机制：从抽象语法树（AST）模板模式与实例化状态机，到函数模板实参推导（Deduction）与类模板实参推导（CTAD）；从变长参数包（Variadic Pack）的 AST 展开与 C++17 折叠表达式机器码生成，到偏特化 Traits 编译期路由分发；从二阶段名字查找（Two-Phase Lookup）、依赖名（Dependent Name）解析与 ``typename`` / ``template`` 消歧义符的语法分析器语义，到 ``constexpr`` 与 ``if constexpr`` 的编译期分支剪枝，建立支撑后续 STL 容器、迭代器与泛型算法的编译期类型系统基础。

模板 AST 蓝图与编译期实例化状态机：隐式实例化、显式特化与链接去重
-------------------------------------------------------------------

C++ 模板本质上是编译期代码生成的参数化抽象语法树蓝图（AST Blueprint）。在编译器前端词法分析与语法分析阶段，模板声明或定义并不直接分配机器指令内存，也不生成目标文件（``.o`` / ``.obj``）中的符号定义，而是作为一种参数化的模板模式（Template Pattern）常驻于编译器的符号表与 AST 内存池中。

当编译单元中出现具体的模板特化请求时，编译器启动实例化状态机（Instantiation State Machine）。实例化流程遵循严格的时机划分：

1. **隐式实例化（Implicit Instantiation）**：
   当代码中需要完整的类类型定义（例如声明对象实体、使用 ``sizeof(T)``、访问类成员）或调用模板函数时，编译器自动以具体模板实参替换形参，生成对应的特化 AST 节点并进行语义检查与机器指令发射。
2. **成员函数体的延迟实例化（Lazy Instantiation of Member Functions）**：
   类模板被隐式实例化时，编译器仅实例化该类的声明结构、虚函数表布局以及非静态数据成员的内存偏移量；其普通的非虚成员函数体保持未实例化状态，直到该特定成员函数在代码中被显式调用或取得函数指针。
3. **显式实例化声明与定义（Explicit Instantiation Declaration / Definition）**：
   - 显式实例化定义语法：``template class StaticBuffer<int, 64>;``。通知编译器在此编译单元无条件生成该特化的全部代码与符号定义。
   - 显式实例化声明语法（C++11 外部模板）：``extern template class StaticBuffer<int, 64>;``。通知编译器该特化已在其他编译单元完成实例化，当前编译单元仅引用外部符号，抑制本地重复代码生成，降低编译耗时与峰值内存。
4. **显式全特化（Explicit Specialization）**：
   语法为 ``template<> class Container<bool> { ... };``。全特化版本是具体类型的独立实现，完全覆盖主模板模式。

.. code-block:: text

   +---------------------------------------------------------------------------------------+
   |                       C++ 模板编译期 AST 实例化与符号生成状态机                         |
   +---------------------------------------------------------------------------------------+
   | 模板源码定义 (Template Blueprint)                                                     |
   |   template <typename T, size_t N> struct StaticBuffer { ... };                        |
   |                                                                                       |
   | 阶段 1：词法/语法解析 -> 模板 AST 模式 (TemplateDecl, 符号表中记录形参列表)            |
   |                                                                                       |
   | 阶段 2：使用点触发实例化请求 (Point of Instantiation, POI)                           |
   |   - 声明指针: StaticBuffer<int, 32>* p; --------> 仅前置声明特化 (Incomplete Type)    |
   |   - 实例化对象: StaticBuffer<int, 32> buf; ------> 实例化类布局与数据成员 (Complete)  |
   |   - 调用成员: buf.write(0, 42); -----------------> 触发 StaticBuffer<int, 32>::write  |
   |                                                    成员函数体 AST 实例化与代码生成   |
   |                                                                                       |
   | 阶段 3：中间代码生成 (IR Lowering) 与符号修饰 (Name Mangling)                          |
   |   - 生成符号: _ZN12StaticBufferIiLm32EE5writeEmi                                      |
   |   - 归入目标文件 ELF 段: .text._ZN12StaticBufferIiLm32EE5writeEmi                     |
   |                                                                                       |
   | 阶段 4：链接期 COMDAT / linkonce 消除重复指令段                                        |
   |   - 链接器识别多目标文件中相同的 COMDAT Key，保留一份唯一定义，合并多余副本          |
   +---------------------------------------------------------------------------------------+

在多翻译单元（Multi-Translation Unit）编译模型中，由于模板定义通常放置于公共头文件中，多个独立的 ``.cpp`` 编译单元可能同时实例化相同的模板特化（例如 ``std::vector<int>``）。这会导致每个编译单元的目标文件中均包含一份完全相同的函数符号与机器指令。

为了解决单一定义规则（ODR, One Definition Rule）与多重定义符号冲突，现代编译工具链（GCC/Clang/MSVC）与 ELF/PE 链接器采用 **COMDAT（Common Data）/ linkonce 节** 机制：

- 编译器将每个模板特化的函数机器指令放入具有独立段名称的 COMDAT 节中（例如 ELF 的 ``.text._ZN12StaticBufferIiLm32EE5writeEmi``）。
- 链接器（Linker）在合并多个 ``.o`` 目标文件生成最终可执行文件或动态链接库时，比对所有 COMDAT 节的特征签名，仅保留其中一份指令数据，将其他目标文件中的同名节完全丢弃，并将所有交叉调用跳转指令重定位至保留的唯一起始物理地址。

.. list-table:: 模板实例化方式与编译器/链接器动作对照
   :widths: 18 22 30 30
   :header-rows: 1
   :class: tight-table

   * - 实例化类别
     - 语法形式
     - 编译器生成行为
     - 链接器符号处理
   * - 隐式类实例化
     - ``Vector<T> v;``
     - 实例化类骨架与已调用成员函数；未调用成员保持未编译
     - 生成 COMDAT 符号，参与链接去重
   * - 外部模板声明
     - ``extern template class Vector<int>;``
     - 抑制当前编译单元的代码生成；仅生成外部未解析符号引用
     - 链接至其他编译单元生成的实例化实体
   * - 显式模板定义
     - ``template class Vector<int>;``
     - 强制实例化该类的所有成员函数与静态成员定义
     - 导出全局弱符号（Weak Symbol）或 COMDAT 符号
   * - 显式全特化
     - ``template<> class Vector<bool>;``
     - 作为独立具体类进行完整编译；必须遵循普通类的 ODR 约束
     - 若定义在头文件中需加 ``inline``，否则引发重复定义错误

函数模板实参推导与非类型模板参数 (NTTP)
---------------------------------------

函数模板实参推导（Template Argument Deduction）是编译器在函数调用点自动将实参表达式的类型映射至模板形参模式（Pattern Matching）的核心过程。

推导系统按以下三类形参声明模式进行规则分发：

1. **值传递形参（``template <typename T> void f(T param)``）**：
   - 实参类型的顶层 ``const`` 与 ``volatile`` 限定符被自动忽略。
   - 数组类型与函数类型退化（Decay）为对应的原生指针类型（如 ``int[10]`` 退化为 ``int*``）。
2. **左值引用与常引用形参（``template <typename T> void f(T& param)`` 与 ``void f(const T& param)``）**：
   - 保持实参类型的顶层 ``const`` 属性。
   - 数组与函数类型不发生退化，精准保留数组长度与类型签名（如 ``int[10]`` 推导为 ``int(&)[10]``，使得通过引用推导固定数组长度成为可能）。
3. **通用引用/转发引用形参（``template <typename T> void f(T&& param)``）**：
   - 传入左值时，``T`` 被推导为左值引用类型 ``U&``；经由引用折叠规则 ``U& && -> U&``，最终形参类型为 ``U&``。
   - 传入右值时，``T`` 被推导为具体类型 ``U``，最终形参类型为右值引用 ``U&&``。

.. code-block:: cpp

   #include <cstddef>
   #include <type_traits>

   // 基于引用传递推导原生数组长度的非退化模式
   template <typename T, std::size_t N>
   constexpr std::size_t query_array_extent(T (&)[N]) noexcept {
       return N;
   }

   // 包含不可推导上下文的模板设计
   template <typename T>
   struct TypeIdentity {
       using type = T;
   };

   // 第二个参数位于不可推导上下文（Nested Name Specifier）中
   template <typename T>
   void configure_threshold(T value, typename TypeIdentity<T>::type default_value) {
       // 仅由 value 参数推导 T；default_value 允许进行隐式类型转换
   }

当模板参数出现在作用域解析运算符 ``::`` 左侧（嵌套名字说明符，Nested Name Specifier）时，该位置构成 **不可推导上下文（Non-deduced Context）**。编译器无法根据该位置的实参逆向推导外层模板参数，必须依赖其他显式参数或调用点显式指定的模板实参。

C++17 引入了 **类模板实参推导（CTAD, Class Template Argument Deduction）**。编译器根据类模板的构造函数形参列表自动合成隐式推导指引（Implicit Deduction Guides），或根据库开发者提供的显式推导指引（Explicit Deduction Guides）进行重载决议：

.. code-block:: cpp

   template <typename T, std::size_t N>
   struct FixedBuffer {
       T elements[N];
   };

   // 用户显式推导指引：将原生数组初始化推导为 FixedBuffer<T, N>
   template <typename T, std::size_t N>
   FixedBuffer(const T (&)[N]) -> FixedBuffer<T, N>;

   // 调用点无需显式写出模板实参
   const int sample_data[4] = {1, 2, 3, 4};
   FixedBuffer buffer{sample_data}; // 经由推导指引自动推导为 FixedBuffer<int, 4>

**非类型模板参数（NTTP, Non-Type Template Parameter）** 将具体数值作为类型签名的组成部分。

在 C++20 之前，NTTP 支持的类型限于整型、枚举、指针、左值引用以及 ``std::nullptr_t``。C++20 放宽了限制，支持满足结构化类型（Structural Type）约束的字面量类类型（Literal Class Type）。所有非静态数据成员必须为公共且非可变的结构化类型，并在编译期支持 ``constexpr`` 构造与比较。

NTTP 使得固定长度内存容器（如 ``std::array<T, N>``）、位掩码配置与维度计算能够在编译期完成常量传播（Constant Propagation）与循环完全展开（Loop Unrolling），生成扁平高效的 SIMD 向量化汇编。

变长参数包 (Variadic Templates) 与 C++17 折叠表达式深度展开
------------------------------------------------------------

C++11 可变参数模板引入了参数包（Parameter Pack）机制，允许模板接收任意数量的类型或数值实参。参数包分为两类：

1. **类型参数包（Template Parameter Pack）**：``typename... Args``，表示零个或多个类型形参。
2. **函数参数包（Function Parameter Pack）**：``Args... args``，表示对应类型的零个或多个函数形参。

编译器在 AST 中将参数包表征为紧凑的序列节点。在实例化阶段，编译器根据传入实参的元数（Arity）将参数包模式进行克隆展开。

C++17 之前，解包变长参数必须采用递归模板实例化（Recursive Template Instantiation）或初始化列表解包惯用法（Braced-Init-List Expansion Trick）：

.. code-block:: cpp

   #include <iostream>
   #include <utility>

   // C++11 经典逗号表达式与初始化列表解包模式
   template <typename... Args>
   void print_elements_cpp11(Args&&... args) {
       // 利用数组初始化列表的从左至右求值保证，执行无副作用解包
       int dummy[] = { 0, ((std::cout << args << ' '), 0)... };
       (void)dummy; // 压制未引用变量警告
       std::cout << '
';
   }

C++17 引入了原生的 **折叠表达式（Fold Expressions）**，直接在语法分析器层面将参数包展开为二元运算符树（Binary Operator Tree），消除了递归模板实例化导致的编译器符号表膨胀与编译延迟。

折叠表达式支持 4 种语法形式：

.. list-table:: C++17 折叠表达式 4 种拓扑结构与 AST 展开语义
   :widths: 20 25 30 25
   :header-rows: 1
   :class: tight-table

   * - 折叠类型
     - 语法形式
     - 逻辑展开等价语义 (设包为 $E_1, E_2, \dots, E_N$)
     - 结合方向
   * - 一元右折叠 (Unary Right Fold)
     - ``(args op ...)``
     - ``(E_1 op (E_2 op (... op E_N)))``
     - 右结合
   * - 一元左折叠 (Unary Left Fold)
     - ``(... op args)``
     - ``(((E_1 op E_2) op ...) op E_N)``
     - 左结合
   * - 二元右折叠 (Binary Right Fold)
     - ``(args op ... op init)``
     - ``(E_1 op (E_2 op (... op (E_N op init))))``
     - 右结合
   * - 二元左折叠 (Binary Left Fold)
     - ``(init op ... op args)``
     - ``((((init op E_1) op E_2) op ...) op E_N)``
     - 左结合

折叠表达式支持全部 32 种 C++ 二元运算符（包括算术、位运算、逻辑、赋值以及逗号运算符）。

空参数包处理边界：一元折叠要求参数包必须非空；仅当运算符为 ``&&``（空包求值为 ``true``）、``||``（空包求值为 ``false``）或逗号运算符（空包求值为 ``void()``）时，一元折叠才允许接收空包。对于其他运算符，必须提供初始值 ``init`` 采用二元折叠以确保良构性。

.. code-block:: cpp

   #include <cstddef>
   #include <cstdint>
   #include <type_traits>
   #include <utility>

   // 使用二元左折叠与逗号运算符实现工业级连续内存哈希聚合算法
   template <typename... Args>
   constexpr uint64_t compute_composite_hash(const Args&... args) noexcept {
       uint64_t seed = 0xCBF29CE484222325ULL; // FNV-1a 初始偏移偏置
       auto hash_step = [&seed](const auto& item) noexcept {
           // 提取每个参数的连续内存字节执行编译期 FNV 混合
           const uint8_t* byte_ptr = reinterpret_cast<const uint8_t*>(&item);
           for (size_t i = 0; i < sizeof(item); ++i) {
               seed ^= static_cast<uint64_t>(byte_ptr[i]);
               seed *= 0x100000001B3ULL;
           }
       };

       // 二元左折叠展开：逐个执行 hash_step，无任何递归实例化开销
       (hash_step(args), ...);
       return seed;
   }

   // 编译期所有类型断言判定
   template <typename ExpectedType, typename... Candidates>
   inline constexpr bool all_same_v = (std::is_same_v<ExpectedType, Candidates> && ...);

模板特化、偏特化拓扑与编译期分发架构
------------------------------------

模板特化体系提供了根据模板实参模式切换底层实现的数据驱动机制。特化分为全特化（Full Specialization）与偏特化（Partial Specialization）。

偏特化仅适用于类模板与变量模板（Variable Templates）；**函数模板不支持偏特化**。

函数模板通过函数重载决议（Function Overload Resolution）、标签分发（Tag Dispatching）或 SFINAE / Concepts 机制表达特化分支。若允许函数模板偏特化，将与函数重载规则产生多义性冲突，破坏重载决议拓扑的一致性。

.. code-block:: cpp

   #include <cstddef>
   #include <type_traits>

   // 主模板：默认通用内存拷贝策略（字节逐一拷贝）
   template <typename T, typename Enable = void>
   struct MemoryTransferTraits {
       static void transfer(T* dest, const T* src, size_t count) {
           for (size_t i = 0; i < count; ++i) {
               dest[i] = src[i];
           }
       }
   };

   // 偏特化 1：针对指针类型的特化
   template <typename T>
   struct MemoryTransferTraits<T*> {
       static void transfer(T** dest, T* const* src, size_t count) {
           __builtin_memcpy(dest, src, count * sizeof(T*));
       }
   };

   // 偏特化 2：基于 type_traits 条件的平凡类型快速内存拷贝特化
   template <typename T>
   struct MemoryTransferTraits<T, std::enable_if_t<std::is_trivially_copyable_v<T>>> {
       static void transfer(T* dest, const T* src, size_t count) {
           __builtin_memcpy(dest, src, count * sizeof(T));
       }
   };

偏特化匹配遵循 **偏序重载规则（Partial Ordering Rules）**：当存在多个候选特化均能匹配当前实参时，编译器通过构造虚构实参进行双向匹配测试，严格选择“特化程度最高”（Most Specialized）的版本；若不存在唯一定义的最特化版本，编译器立即报告歧义编译错误（Ambiguous Template Specialization）。

.. code-block:: text

   +---------------------------------------------------------------------------------------+
   |                       类模板特化与偏特化选择拓扑层次结构                               |
   +---------------------------------------------------------------------------------------+
   | [ 主模板 Primary Template: template <typename T, typename U> struct Dict ]             |
   |                                 |                                                     |
   |           +---------------------+---------------------+                               |
   |           |                                           |                               |
   |           v                                           v                               |
   | [ 偏特化 1: Dict<T, int> ]                    [ 偏特化 2: Dict<T*, U*> ]              |
   |   (固定第二个参数类型)                            (模式约束为指针类型)                  |
   |           |                                           |                               |
   |           +---------------------+---------------------+                               |
   |                                 |                                                     |
   |                                 v                                                     |
   |                     [ 全特化: Dict<char*, int> ]                                      |
   |                       (完全确定具体类型，最高优先级)                                   |
   +---------------------------------------------------------------------------------------+

依赖名、typename 消歧义与二阶段名字查找 (Two-Phase Name Lookup)
-----------------------------------------------------------------

在模板定义内部，名字按照与模板形参的依赖关系划分为两类：

1. **非依赖名（Non-dependent Names）**：含义与类型在模板定义点即可完全确定，与模板形参无关的名字（例如标准类型 ``int``、未受模板参数影响的全局函数）。
2. **依赖名（Dependent Names）**：类型或含义直接或间接依赖于模板形参的名字（例如 ``T::value_type``、``buffer[i]`` 中 ``buffer`` 为参数化类型）。

现代 C++ 编译器严格执行 **二阶段名字查找（Two-Phase Name Lookup）**：

- **第一阶段（Phase 1: Definition Time）**：
  在解析模板定义的阶段，编译器立即对所有非依赖名执行普通词法与作用域查找（Unqualified / Qualified Name Lookup）并完成早期静态绑定。若非依赖名不存在或存在非依赖语法错误，编译器在定义点立即报错，无需等待实例化。
- **第二阶段（Phase 2: Instantiation Time）**：
  在具体调用或使用触发的实例化点（POI），编译器已知全部模板实参的具体类型。此时对依赖名执行延迟查找，结合实参类型的命名空间执行 **参数依赖查找（ADL, Argument-Dependent Lookup / Koenig Lookup）**，并完成重载决议与类型检查。

.. code-block:: cpp

   #include <iostream>

   void diagnostic_probe(double) {
       std::cout << "Global double probe (Phase 1 Bound)
";
   }

   template <typename T>
   struct PipelineWorker {
       void execute(T value) {
           // 非依赖调用：在 Phase 1 绑定至 diagnostic_probe(double)
           diagnostic_probe(0);

           // 依赖调用：查找延迟至 Phase 2，受 ADL 影响
           process_element(value);
       }
   };

   // 在模板定义之后声明的具体重载
   void diagnostic_probe(int) {
       std::cout << "Late declared int probe
";
   }

   namespace EngineDomain {
       struct CustomTask {};
       // 声明于命名空间内部的 ADL 目标函数
       void process_element(const CustomTask&) {
           std::cout << "EngineDomain ADL process_element executed
";
       }
   }

在上述机制中，``diagnostic_probe(0)`` 是非依赖名，在 Phase 1 阶段已牢固绑定至 ``diagnostic_probe(double)``；即使后续在当前作用域声明了更精准匹配的 ``diagnostic_probe(int)``，实例化阶段也不会重新绑定。

而 ``process_element(value)`` 的实参 ``value`` 为依赖类型，查找推迟至 Phase 2，通过 ADL 在实参类型 ``EngineDomain::CustomTask`` 所属的命名空间中成功定位并调用 ``process_element``。

在处理嵌套依赖名字（Qualified Dependent Names，如 ``T::SubType``）时，C++ 语法分析器面临固有的词法歧义：在模板定义阶段，编译器无法预知模板实参特化版本中 ``T::SubType`` 究竟是一个类型别名、一个静态数据成员还是一组成员函数。

C++ 语法规则规定：**在无任何显式标注的情况下，编译器一律将嵌套依赖名字解析为非类型（值或成员变量）**。

因此，当该名字用作类型声明时，必须在名字前显式前置关键字 ``typename``，告知语法分析器将其解析为类型说明符（Type Specifier）：

.. code-block:: cpp

   template <typename Container>
   struct SequenceInspector {
       // 必须显式使用 typename 消除类型解析歧义
       using element_type = typename Container::value_type;

       void inspect(Container& c) {
           // 若省略 typename，编译器将解析为 static 成员与 variable 的乘法表达式：
           // (Container::value_type) * (variable);
           typename Container::value_type* local_pointer = nullptr;
           (void)local_pointer;
       }
   };

类似地，当访问依赖于模板参数的对象的成员模板函数时，必须使用 ``.template`` 或 ``->template`` 消歧义符，防止编译器将小于号 ``<`` 解析为小于比较运算符：

.. code-block:: cpp

   template <typename AllocatorNode>
   void allocate_node(AllocatorNode& node) {
       // 显式使用 .template 指明 rebind 为成员模板
       using SubAlloc = typename AllocatorNode::template rebind<int>::other;
       (void)node;
   }

.. list-table:: 名字查找分类与消歧义符语义
   :widths: 20 25 30 25
   :header-rows: 1
   :class: tight-table

   * - 名字构造类型
     - 示例表达式
     - 查找时机 (Lookup Phase)
     - 语法歧义消除规则
   * - 非依赖普通名
     - ``std::size_t``, ``memcpy``
     - Phase 1（模板定义点）
     - 立即查找并静态绑定；未声明则报错
   * - 依赖类型名
     - ``typename Alloc::pointer``
     - Phase 2（实参已知实例化点）
     - 必须使用 ``typename`` 声明其为类型
   * - 依赖模板成员名
     - ``obj.template get<0>()``
     - Phase 2（实参已知实例化点）
     - 必须使用 ``template`` 防止 ``<`` 被解析为比较符
   * - 依赖函数调用
     - ``swap(a, b)``
     - Phase 2（实参已知实例化点）
     - 结合普通查找与实参所在命名空间 ADL

constexpr、inline 变量与 if constexpr 编译期分支剪枝
------------------------------------------------------

现代 C++ 模板编程将大量计算与静态策略路由前移至编译期。

- **``constexpr`` 函数与常量求值引擎**：
  ``constexpr`` 关键字修饰函数表明：当所有调用实参均为编译期常量表达式且函数体内部未执行未定义行为（如越界、非受控类型双写 reinterpret_cast）时，编译器在编译期常量求值引擎中直接计算其返回值，生成字面量常量；当实参包含运行时变量时，平滑退化为普通运行时机器指令函数。
- **C++17 ``inline`` 变量**：
  解决了头文件中定义模板常量与 traits 的 ODR 冲突问题。``inline constexpr bool is_fast_path_v = ...;`` 允许头文件被包含至数百个编译单元，链接器保证全局符号唯一合并。
- **C++17 ``if constexpr`` 编译期分支剪枝（Compile-time Branch Pruning）**：
  在模板函数内部，``if constexpr (condition)`` 的条件表达式必须为编译期布尔常量。编译器根据求值结果，仅对选中的分支生成 AST 并进行语义检查与机器指令发射；未选中的分支代码被直接**丢弃（Discarded Statement）**。

未被选中的 ``if constexpr`` 分支即使包含针对当前特化类型不合法的操作（例如对无解引用操作符的类型执行 ``*ptr``），只要该语法在词法层面良构，编译器就不会产生编译错误。这彻底淘汰了复杂的重载 SFINAE 技术，构建出高内聚、易维护的泛型内核代码。

.. code-block:: cpp

   #include <cstddef>
   #include <cstring>
   #include <type_traits>
   #include <utility>

   template <typename T>
   struct BufferSerializer {
       static void serialize_payload(uint8_t* output_stream, const T& value) {
           if constexpr (std::is_trivially_copyable_v<T>) {
               // 分支 A：平凡可复制类型直接发射高效 memcpy 机器指令
               std::memcpy(output_stream, &value, sizeof(T));
           } else if constexpr (std::is_member_function_pointer_v<decltype(&T::custom_serialize)>) {
               // 分支 B：具备自定义序列化成员函数时调用业务接口
               // 若 T 为平凡类型，此分支直接被丢弃，绝不触发对 &T::custom_serialize 的实例化检查
               value.custom_serialize(output_stream);
           } else {
               // 分支 C：编译期静态断言拦截非法类型
               static_assert(sizeof(T) == 0, "Target type does not satisfy serialization constraints");
           }
       }
   };

小结与下章导读
--------------

本章系统解构了现代 C++ 泛型模板系统的底层编译期机制：从抽象语法树（AST）模板模式与隐式/显式实例化状态机，到多目标文件编译下的 COMDAT / linkonce 符号链接去重；从函数模板实参推导模式与 C++20 结构化非类型模板参数（NTTP），到 C++17 折叠表达式的二元操作符展开与机器码生成；从基于偏特化机制的 Traits 静态分发架构，到二阶段名字查找（Two-Phase Lookup）、参数依赖查找（ADL）与 ``typename`` / ``template`` 语法消歧义符；最终结合 ``constexpr`` 与 ``if constexpr`` 确立了编译期分支剪枝的高效模型。

至此，第一模块《C++ 底层基石与对象模型》的 5 个核心基础章节已全部完工。下一章我们将正式跨入 **第 2 模块：STL 核心机制与内存子系统** 的首篇 —— **迭代器核心体系与能力分层：输入/输出/前向/双向/随机/连续迭代器拓扑、traits 萃取与适配器模型（``02_stl_core_mechanisms_and_allocators/01_iterator_taxonomy_and_traits_system.rst``）**，深入剖析 STL 迭代器五级与六级能力拓扑契约、指针与对象迭代器的统一萃取模型以及逆向/流/插入适配器的底层物理结构。
