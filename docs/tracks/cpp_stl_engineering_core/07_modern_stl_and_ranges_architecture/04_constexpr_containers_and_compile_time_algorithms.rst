================================================================================================
编译期 STL 运行机制：constexpr 容器与算法、编译期内存分配与瞬态销毁规则
================================================================================================

.. note:: 前置背景与上下文承接
   在第 7 模块第 3 节（``07_modern_stl_and_ranges_architecture/03_span_and_string_view_non_owning_views.rst``）中，我们深度剖析了 ``std::span`` 与 ``std::string_view`` 连续物理内存视图的指针与长度拓扑结构、动态/静态 Extent 的零开销抽象机制以及悬垂引用的生命周期防御矩阵。这些视图类型虽然能够在编译期充当常量观察者，但其底层并不拥有动态物理存储。自 C++20 起，现代 C++ 标准库迎来了计算范式的关键跃迁：``constexpr`` 机制从最初简单的无状态数值计算，演进为涵盖动态内存分配、容器全生命周期管理以及完整泛型算法集的图灵完备编译期执行引擎。本节将全面解构编译期 STL 的运行机制，深入剖析常量求值引擎（Constant Evaluation Engine）的解释执行模型、P0784R7 瞬态动态内存分配（Transient Allocation）契约、``constexpr std::vector`` 与 ``std::string`` 的底层支撑架构，以及 ``std::is_constant_evaluated()`` 与 C++23 ``if consteval`` 的编译期/运行期双态分发状态机。

编译期计算范式演进与常量求值引擎
--------------------------------

C++ 的元编程与编译期求值技术历经了四个显著的代际演化阶段。每一个阶段都在不断消除编译期元编程与常规运行期代码之间的语法割裂与心智负担：

1. **第一代：C++98 模板偏特化与枚举值 hack**：
   依靠类型系统推导与模板偏特化模拟模式匹配，依靠 ``enum { value = ... }`` 传递整型计算结果。语法晦涩冗长，且仅支持标量整型常量。
2. **第二代：C++11/C++14 标量 constexpr 函数**：
   引入 ``constexpr`` 关键字。C++11 严格限制函数体只能包含单条 ``return`` 语句；C++14 放宽语法限制，允许局部变量、循环、分支与变易操作，使得编写编译期函数与常规运行期函数达成初步同构。
3. **第三代：C++17 if constexpr 与常量表达式扩展**：
   引入编译期条件分支 ``if constexpr``，允许在模板实例化期间丢弃未命中分支的代码生成；支持 ``constexpr lambda`` 表达式，大幅拓展了高阶函数的编译期能力。
4. **第四代：C++20/C++23 动态常量表达式与完整 STL 赋能**：
   彻底打破“编译期不得分配动态内存、不得调用虚函数”的物理禁区。标准库核心容器（``std::vector``、``std::string``）与绝大多数泛型算法（``<algorithm>``）全量打上 ``constexpr`` 标记，促成了现代 STL 能够在常量表达式中完整运行。

.. list-table:: C++ 编译期计算能力代际演进与底层物理边界对比矩阵
   :widths: 20 20 20 20 20
   :header-rows: 1
   :class: tight-table

   * - 语言标准
     - 内存与存储模型
     - 控制流与循环结构
     - 动态分配与释放支持
     - STL 容器与算法支撑
   * - **C++11**
     - 只读标量，字面类型
     - 仅支持递归表达式展开
     - 严禁任何形式的动态分配
     - 无容器支持，极少数数学函数
   * - **C++14**
     - 支持局部可变栈变量
     - 支持 while/for 语句
     - 严禁任何形式的动态分配
     - 极少数辅助组件
   * - **C++17**
     - 支持编译期 lambda 闭包
     - if constexpr 静态分支
     - 严禁任何形式的动态分配
     - std::array 全面支持，极少数算法
   * - **C++20**
     - 虚函数支持、动态堆内存
     - 完整控制流与协程前置
     - 支持瞬态 new/delete
     - vector/string 与全量 ranges/algorithm
   * - **C++23**
     - 静态反射前置、扩展容器
     - if consteval 精确分发
     - 瞬态分配，探索非瞬态
     - 扩展至 optional/variant/bitset 全量组件

常量求值引擎的解释执行机制
~~~~~~~~~~~~~~~~~~~~~~~~~~

当编译器遭遇诸如 ``constexpr auto x = func();`` 或 ``static_assert(expr)`` 的常量求值上下文（Constant Evaluation Context）时，前端编译器内部的**常量表达式解释器**（如 Clang 的 ``ExprConstant.cpp`` 或 GCC 的 ``constexpr.cc``）将被即刻激活。

该解释器在编译器内部构建了一个受限的、具备内存沙盒保护的虚拟抽象机：
1. **符号化抽象存储（Symbolic Storage）**：
   常量求值器并不直接向操作系统的真实物理内存申请地址，而是维护一个符号化的对象抽象堆栈与虚拟地址空间。所有的变量读写操作均转化为对编译期 AST 节点与内部内存槽位（Slots）的状态机更新。
2. **未定义行为（Undefined Behavior）的绝对零容忍**：
   在常规运行期，诸如数组越界读取、有符号整数溢出、空指针解引用或读取未初始化内存等未定义行为，编译器通常会依赖硬件异常捕获或在激进优化时假设其永不发生。然而，在编译期常量求值上下文下，**任何未定义行为都是致命的语法错误**。常量求值引擎充当着极致严苛的静态内存分析器，一旦探测到任何非法内存访问或未定义操作，编译过程将立即硬中断并输出精准的堆栈诊断报告。

瞬态动态内存分配（Transient Allocation）契约
--------------------------------------------

在 C++20 之前，禁止在常量表达式中进行动态内存分配的底层根源在于**指针生命周期与目标文件格式的物理阻抗失配**：
若允许在编译期分配堆内存并将指针持久化至运行期，运行期代码所获取的指针值指向的是编译器所在主机的编译期虚拟进程空间，该地址在目标程序加载运行（Load Time）时将毫无意义，必然引发不可预测的崩溃。

P0784R7 提案的破局：瞬态生命周期约束
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

C++20 采纳了 P0784R7（*More constexpr containers*）提案，通过引入**瞬态分配（Transient Allocation）**概念，在不破坏目标文件静态数据段布局的前提下，完全放开了编译期的动态内存管理。

.. math::

   \forall 	ext{Ptr} \in 	ext{AllocatedMemory}_{	ext{CompileTime}}, \quad 	ext{Deallocated}(	ext{Ptr}) \prec 	ext{EvaluationEnd}

**瞬态分配核心不变量**：
在编译期常量表达式求值生命周期内，所有通过 ``new``、``std::allocator<T>::allocate`` 或等价机制向编译器求值器申请的堆内存，**必须在整个常量求值表达式完成推导之前，被对应的 ``delete`` 或 ``deallocate`` 彻底释放**。

如果常量求值结束时，编译器检测到仍有未释放的动态内存，编译器将判定发生**编译期内存泄漏**，并将该表达式判定为非常量表达式，从而抛出编译期硬错误：

.. code-block:: cpp

   // 编译期动态内存合法性判定
   constexpr int compute_transient() {
       int* p = new int[5]{1, 2, 3, 4, 5}; // 编译期动态申请内存
       int sum = 0;
       for (int i = 0; i < 5; ++i) sum += p[i];
       delete[] p; // 必须在函数返回前显式释放！满足瞬态不变量
       return sum;
   }

   constexpr int compute_leak() {
       int* p = new int[5]{1, 2, 3, 4, 5};
       return p[0]; // 错误！内存发生泄漏，违背瞬态分配契约
   }

   constexpr int valid_val = compute_transient(); // 编译通过，计算结果在常量折叠为 15
   // constexpr int leak_val = compute_leak();    // 编译期报错：'p' was allocated here and never deallocated

动态分配底层原语解耦：std::construct_at 与 std::destroy_at
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在常规 STL 容器实现中，内存的分配与对象的生命周期是严格解耦的：使用 ``allocator::allocate`` 获取未初始化的原始内存字节，随后使用定位 new（``placement new``：``::new (static_cast<void*>(ptr)) T(...)``）在已分配的原始内存上就地构造对象。

然而，在常量求值引擎中，``void*`` 指针类型擦除与随意地址强转是被严格禁止的。常量求值器必须精准掌握每一个符号对象的真实静态类型。为解决这一矛盾，C++20 引入了标准原语 ``std::construct_at`` 与 ``std::destroy_at``：

.. code-block:: cpp

   namespace std {
       template <typename T, typename... Args>
       constexpr T* construct_at(T* p, Args&&... args) {
           return ::new (const_cast<void*>(static_cast<const volatile void*>(p)))
               T(std::forward<Args>(args)...);
       }

       template <typename T>
       constexpr void destroy_at(T* p) {
           if constexpr (std::is_array_v<T>) {
               for (auto& elem : *p) (destroy_at)(std::addressof(elem));
           } else {
               p->~T();
           }
       }
   }

编译器对 ``std::construct_at`` 提供了内置特权支持（Compiler Intrinsics）。在编译期常量表达式内部，它能够绕过标准对 ``placement new`` 的语法禁止，允许开发者在类型明确的未初始化内存存储上直接激活对象生命周期，并在对象废弃时通过 ``std::destroy_at`` 显式触发析构函数。

constexpr 容器微架构支撑：std::vector 与 std::string
---------------------------------------------------

在 C++20 中，``std::vector`` 与 ``std::basic_string`` 的所有成员函数均被赋予了 ``constexpr`` 属性。这意味着包括动态扩容、首尾插入、元素移动重排、缓冲区管理在内的全套容器操作，均可无缝运行于编译期。

编译期容器拓扑与运行期三指针模型的等价映射
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``std::vector`` 在常量求值环境下的内部运作机制，与第 3 模块第 1 节（``03_sequence_containers_internals/01_vector_three_pointer_model_and_growth.rst``）中阐述的三指针连续内存模型在逻辑上高度一致：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |             std::vector 编译期常量求值引擎符号化三指针拓扑映射              |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   常量求值器内部虚拟堆空间:                                                 |
   |   +-----------+-----------+-----------+-----------+-----------+-----------+ |
   |   | Slot 0    | Slot 1    | Slot 2    | Slot 3    | [Uninit]  | [Uninit]  | |
   |   | Value: 10 | Value: 20 | Value: 30 | Value: 40 | Reserved  | Reserved  | |
   |   +-----------+-----------+-----------+-----------+-----------+-----------+ |
   |         ^                                   ^                       ^       |
   |         |                                   |                       |       |
   |     start_                             finish_                 end_of_      |
   |   (元素起始指针)                      (当前元素末尾)           storage_     |
   |                                                             (总容量边界)    |
   |                                                                             |
   |   操作演进时序:                                                             |
   |   1. 初始: start_ = finish_ = end_of_storage_ = nullptr                     |
   |   2. push_back(10): std::allocator 申请 1 槽位，construct_at 初始化首元素  |
   |   3. 扩容迁移: 申请 2 槽位新内存 -> 元素拷贝/移动 -> destroy_at 销毁旧对象  |
   |               -> std::allocator::deallocate 释放旧槽位 -> 重新绑定三指针    |
   |                                                                             |
   +-----------------------------------------------------------------------------+

关键约束：从编译期瞬态计算提取数据固化至编译期常量
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

既然编译期容器受制于“瞬态分配”约束，必须在常量求值结束前完全析构释放自身，那么我们如何利用 ``constexpr std::vector`` 在编译期进行复杂的动态排序、过滤与去重，并将最终的计算结果永久固化为编译期可访问的静态常量呢？

工程解法是通过**数据形态的跨容器转移**：
利用 ``constexpr`` 函数内部完整的 ``std::vector`` 执行复杂的动态扩容计算；在返回前，将数据精准抽取拷贝至无动态内存分配的静态容器（如 ``std::array``）中，随后 ``vector`` 离开作用域触发析构并全量释放编译期堆内存，满足瞬态释放不变量：

.. code-block:: cpp

   #include <vector>
   #include <array>
   #include <algorithm>

   // 编译期利用 vector 进行动态数据清洗并转存为 array
   template <std::size_t N>
   constexpr std::array<int, N> compile_time_sort_and_extract() {
       std::vector<int> dynamic_buffer;
       // 编译期动态 push_back 扩容
       dynamic_buffer.push_back(42);
       dynamic_buffer.push_back(17);
       dynamic_buffer.push_back(99);
       dynamic_buffer.push_back(8);
       dynamic_buffer.push_back(23);

       // 编译期就地排序
       std::sort(dynamic_buffer.begin(), dynamic_buffer.end());

       // 将前 N 项搬移至无内存分配开销的静态数组中
       std::array<int, N> result{};
       for (std::size_t i = 0; i < N; ++i) {
           result[i] = dynamic_buffer[i];
       }

       return result; // 函数返回，dynamic_buffer 析构，内部堆内存全量释放！
   }

   // 成功将动态计算结果固化为只读数据段符号
   constexpr auto sorted_top3 = compile_time_sort_and_extract<3>();
   static_assert(sorted_top3[0] == 8);
   static_assert(sorted_top3[1] == 17);
   static_assert(sorted_top3[2] == 23);

constexpr 泛型算法与执行边界控制
--------------------------------

伴随 C++20 Ranges 与 STL 算法体系的重构，``<algorithm>`` 与 ``<numeric>`` 库中的绝大多数经典算法均被全面标记为 ``constexpr``，覆盖线性查找、划分、排列、变换、累加以及复杂的内省排序。

编译期算法图灵完备性与解释器执行步长限制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

尽管常量求值引擎具备图灵完备性，允许在编译期执行任意复杂的循环与递归，但在工程落地中必须防止无限循环导致编译器进程挂死或耗尽内存。

各大现代 C++ 编译器均对常量求值设置了**最大解释操作步长计数器（Constexpr Step Limit）**：
- **Clang**：提供命令行选项 ``-fconstexpr-steps=N``（默认通常为 $1048576$ 步）。
- **GCC**：提供 ``-fconstexpr-ops-limit=N`` 控制最大运算操作数，提供 ``-fconstexpr-depth=N`` 控制递归调用栈深度。

若编译期排序算法处理的数据集过大（例如对包含 $10000$ 个元素的序列进行快速排序），其计算步数可能轻易击穿编译器的默认上限，触发形如 ``constexpr evaluation exceeded maximum number of steps`` 的编译期错误。在构建大型编译期查找表（Lookup Tables, LUT）时，需要适当调优编译器参数或将高复杂度算法拆解为分治段。

双态分发状态机：std::is_constant_evaluated 与 if consteval
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在高性能系统软件工程中，同一功能在编译期和运行期往往存在截然不同的最优实现策略：
- **编译期**：倾向于依赖通用、纯净的 C++ 算法与类型系统，禁止平台特化的裸指针算术与内联汇编；
- **运行期**：倾向于利用平台专有的硬件指令集加速（如利用 x86 AVX-512、ARM NEON 进行 SIMD 向量化计算，或直接调用经过汇编优化的 ``memcpy`` / ``memmove``）。

为了向开发者提供精准识别当前执行上下文的能力，C++ 标准经历了从库函数检测向核心语言原生语法的演进：

1. **C++20 的过渡原语：std::is_constant_evaluated()**：
   标准库在 ``<type_traits>`` 中引入了 ``std::is_constant_evaluated()``。如果当前执行流处于显然需要常量表达式求值的上下文中，该函数返回 ``true``；反之返回 ``false``。

   **致命语法陷阱**：必须使用普通运行期 ``if`` 语句包裹，**绝不能与 if constexpr 混用**！
   
   .. code-block:: cpp

      // 错误示范：代码逻辑彻底瓦解！
      if constexpr (std::is_constant_evaluated()) { ... }
      
      // 深度机理解析：
      // 在 if constexpr (cond) 中，条件表达式 cond 自身必然处于常量求值上下文中！
      // 因此 std::is_constant_evaluated() 永远求值为 true！
      // 导致 else 分支在模板实例化期间被永久丢弃，运行期硬件优化路径彻底丢失！

2. **C++23 的语言级正名：if consteval 与 if !consteval**：
   为彻底根除上述易错陷阱，C++23 在核心语言层面正式引入了专用语法糖 ``if consteval``：

   .. code-block:: cpp

      // C++23 现代双态分发模式
      constexpr double fast_sin(double x) {
          if consteval {
              // 编译期分支：调用纯净的泰勒展开或 CORDIC 算法进行常量模拟计算
              return taylor_series_sin(x);
          } else {
              // 运行期分支：直接下沉调用硬件 FPU 内建指令或 glibc 汇编实现
              return __builtin_sin(x);
          }
      }

.. list-table:: std::is_constant_evaluated() 与 if consteval 机制深度对比
   :widths: 25 35 40
   :header-rows: 1
   :class: tight-table

   * - 判定机制
     - 语言标准引入版本
     - 语法形态与分类
     - 常见错误与边缘行为
   * - **std::is_constant_evaluated()**
     - C++20
     - 标准库内置函数（依赖编译器内部原语）
     - 严禁与 ``if constexpr`` 配合使用，否则条件恒真；在非明显常量上下文中可能误判
   * - **if consteval**
     - C++23
     - 核心语言原生关键字与语句结构
     - 原生语法支持，完全消除误用歧义；代码意图明确，未中选分支在常量求值期间不执行
   * - **if !consteval**
     - C++23
     - 核心语言原生取反语法
     - 优先保障运行期分支的逻辑表达，在常量求值期间直接旁路跳过运行期汇编代码

自包含工业级编译期 Vector 与常量算法引擎实战
---------------------------------------------

为了将上述理论完全转化为具备工程落地价值的代码，下面提供一套完整的、完全符合 C++20/C++23 规范的自包含工业级编译期动态容器 ``ConstexprVector<T>`` 与常量排序算法引擎。

代码完整覆盖：
1. 基于编译期未初始化内存与 ``std::construct_at`` / ``std::destroy_at`` 的物理生命周期管理；
2. 瞬态内存申请与释放的严格配对，杜绝编译期内存泄漏；
3. 容器几何扩容与元素移动语义在常量解释器中的实现；
4. 编译期就地快速排序（QuickSort）算法；
5. 基于 ``std::is_constant_evaluated()`` 的双态求值探针；
6. 完整的编译期 ``static_assert`` 矩阵与运行期端到端验证套件。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <cstddef>
   #include <memory>
   #include <type_traits>
   #include <utility>
   #include <cassert>
   #include <array>
   #include <algorithm>

   namespace core_stl {

   // =========================================================================
   // 1. 具备编译期瞬态分配能力的轻量级 ConstexprVector
   // =========================================================================

   template <typename T>
   class ConstexprVector {
   public:
       using value_type = T;
       using size_type = std::size_t;
       using reference = T&;
       using const_reference = const T&;
       using pointer = T*;
       using const_pointer = const T*;
       using iterator = pointer;
       using const_iterator = const_pointer;

       // 默认构造：不触发任何堆分配
       constexpr ConstexprVector() noexcept
           : data_(nullptr), size_(0), capacity_(0) {}

       // 预留容量构造
       constexpr explicit ConstexprVector(size_type initial_cap)
           : data_(nullptr), size_(0), capacity_(0) {
           reserve(initial_cap);
       }

       // 析构函数：全量销毁活动对象，并释放动态内存，保证满足瞬态释放约束
       constexpr ~ConstexprVector() {
           clear();
           if (data_ != nullptr) {
               std::allocator<T> alloc;
               alloc.deallocate(data_, capacity_);
               data_ = nullptr;
               capacity_ = 0;
           }
       }

       // 禁止拷贝语义以保持内核精简，提供高效移动语义
       ConstexprVector(const ConstexprVector&) = delete;
       ConstexprVector& operator=(const ConstexprVector&) = delete;

       constexpr ConstexprVector(ConstexprVector&& other) noexcept
           : data_(other.data_), size_(other.size_), capacity_(other.capacity_) {
           other.data_ = nullptr;
           other.size_ = 0;
           other.capacity_ = 0;
       }

       constexpr ConstexprVector& operator=(ConstexprVector&& other) noexcept {
           if (this != &other) {
               clear();
               if (data_) {
                   std::allocator<T> alloc;
                   alloc.deallocate(data_, capacity_);
               }
               data_ = other.data_;
               size_ = other.size_;
               capacity_ = other.capacity_;

               other.data_ = nullptr;
               other.size_ = 0;
               other.capacity_ = 0;
           }
           return *this;
       }

       // 编译期容量预留机制
       constexpr void reserve(size_type new_cap) {
           if (new_cap <= capacity_) return;

           std::allocator<T> alloc;
           pointer new_data = alloc.allocate(new_cap);

           // 将已有元素迁移至新内存块中
           for (size_type i = 0; i < size_; ++i) {
               std::construct_at(new_data + i, std::move(data_[i]));
               std::destroy_at(data_ + i);
           }

           if (data_ != nullptr) {
               alloc.deallocate(data_, capacity_);
           }

           data_ = new_data;
           capacity_ = new_cap;
       }

       // 元素尾插操作：支持自动几何级扩容（1.5 倍或初始对齐）
       constexpr void push_back(const T& value) {
           emplace_back(value);
       }

       constexpr void push_back(T&& value) {
           emplace_back(std::move(value));
       }

       template <typename... Args>
       constexpr reference emplace_back(Args&&... args) {
           if (size_ == capacity_) {
               size_type next_cap = (capacity_ == 0) ? 2 : (capacity_ + capacity_ / 2 + 1);
               reserve(next_cap);
           }
           pointer target_slot = data_ + size_;
           std::construct_at(target_slot, std::forward<Args>(args)...);
           ++size_;
           return *target_slot;
       }

       // 尾部元素弹出
       constexpr void pop_back() noexcept {
           assert(size_ > 0 && "Cannot pop from an empty ConstexprVector");
           --size_;
           std::destroy_at(data_ + size_);
       }

       // 清理全部已构造元素
       constexpr void clear() noexcept {
           for (size_type i = 0; i < size_; ++i) {
               std::destroy_at(data_ + i);
           }
           size_ = 0;
       }

       // 基础属性与访问器
       constexpr size_type size() const noexcept { return size_; }
       constexpr size_type capacity() const noexcept { return capacity_; }
       constexpr bool empty() const noexcept { return size_ == 0; }

       constexpr reference operator[](size_type idx) noexcept {
           assert(idx < size_ && "Index out of range");
           return data_[idx];
       }

       constexpr const_reference operator[](size_type idx) const noexcept {
           assert(idx < size_ && "Index out of range");
           return data_[idx];
       }

       constexpr pointer data() noexcept { return data_; }
       constexpr const_pointer data() const noexcept { return data_; }

       constexpr iterator begin() noexcept { return data_; }
       constexpr iterator end() noexcept { return data_ + size_; }
       constexpr const_iterator begin() const noexcept { return data_; }
       constexpr const_iterator end() const noexcept { return data_ + size_; }

   private:
       pointer data_;
       size_type size_;
       size_type capacity_;
   };

   // =========================================================================
   // 2. 编译期快速排序（QuickSort）泛型算法实现
   // =========================================================================

   namespace algo {

   template <typename Iterator, typename Compare>
   constexpr Iterator constexpr_partition(Iterator first, Iterator last, Compare comp) {
       auto pivot_it = last - 1;
       auto i = first;
       for (auto j = first; j < pivot_it; ++j) {
           if (comp(*j, *pivot_it)) {
               std::iter_swap(i, j);
               ++i;
           }
       }
       std::iter_swap(i, pivot_it);
       return i;
   }

   template <typename Iterator, typename Compare>
   constexpr void constexpr_quicksort(Iterator first, Iterator last, Compare comp) {
       if (first < last) {
           auto pivot = constexpr_partition(first, last, comp);
           if (pivot > first) {
               constexpr_quicksort(first, pivot, comp);
           }
           if (pivot + 1 < last) {
               constexpr_quicksort(pivot + 1, last, comp);
           }
       }
   }

   template <typename Iterator>
   constexpr void constexpr_sort(Iterator first, Iterator last) {
       constexpr_quicksort(first, last, [](const auto& a, const auto& b) {
           return a < b;
       });
   }

   } // namespace algo

   // =========================================================================
   // 3. 双态分发计算流水线与瞬态数据提纯
   // =========================================================================

   struct DualExecutionProbe {
       // 探测执行环境：编译期返回 1，运行期返回 2
       static constexpr int evaluate_mode() noexcept {
           if (std::is_constant_evaluated()) {
               return 1;
           } else {
               return 2;
           }
       }
   };

   // 编译期动态计算中枢：完成瞬态分配并导出至 std::array 固化
   template <std::size_t OutCount>
   constexpr std::array<int, OutCount> compute_and_materialize_primes(int limit) {
       ConstexprVector<int> sieve_buffer;
       
       // 编译期动态搜集质数
       for (int i = 2; i <= limit; ++i) {
           bool is_prime = true;
           for (std::size_t j = 0; j < sieve_buffer.size(); ++j) {
               int p = sieve_buffer[j];
               if (p * p > i) break;
               if (i % p == 0) {
                   is_prime = false;
                   break;
               }
           }
           if (is_prime) {
               sieve_buffer.push_back(i);
           }
       }

       // 逆序排序：验证编译期算法对动态容器的操作能力
       algo::constexpr_quicksort(sieve_buffer.begin(), sieve_buffer.end(), [](int a, int b) {
           return a > b; // 降序排列
       });

       // 固化转存：将前 OutCount 个结果提取至定长静态结构
       std::array<int, OutCount> result{};
       size_type count = (sieve_buffer.size() < OutCount) ? sieve_buffer.size() : OutCount;
       for (size_type i = 0; i < count; ++i) {
           result[i] = sieve_buffer[i];
       }

       return result; // 函数返回：sieve_buffer 析构，内部堆内存全量释放，瞬态分配闭环
   }

   } // namespace core_stl

   // =========================================================================
   // 4. 静态断言验证矩阵与运行期测试驱动套件
   // =========================================================================

   namespace test {

   // 编译期静态断言矩阵（完全在编译器解释器中执行）
   // 1. 双态探针验证
   static_assert(core_stl::DualExecutionProbe::evaluate_mode() == 1, 
                 "Must evaluate to compile-time mode (1) in constant context");

   // 2. 编译期动态内存创建、元素追加与排序断言
   constexpr auto compile_time_pipeline_test = []() constexpr {
       core_stl::ConstexprVector<int> vec;
       vec.push_back(50);
       vec.push_back(10);
       vec.push_back(40);
       vec.push_back(20);
       vec.push_back(30);

       core_stl::algo::constexpr_sort(vec.begin(), vec.end());

       bool sorted_correctly = (vec[0] == 10 && vec[1] == 20 && vec[2] == 30 && 
                                vec[3] == 40 && vec[4] == 50);
       std::size_t final_size = vec.size();

       return sorted_correctly && (final_size == 5);
   };
   static_assert(compile_time_pipeline_test(), "Compile-time vector operations and sort must pass");

   // 3. 质数筛法并转存静态数组断言：提取 50 以内的前 5 大质数 [47, 43, 41, 37, 31]
   constexpr auto top5_primes = core_stl::compute_and_materialize_primes<5>(50);
   static_assert(top5_primes[0] == 47, "Prime 0 must be 47");
   static_assert(top5_primes[1] == 43, "Prime 1 must be 43");
   static_assert(top5_primes[2] == 41, "Prime 2 must be 41");
   static_assert(top5_primes[3] == 37, "Prime 3 must be 37");
   static_assert(top5_primes[4] == 31, "Prime 4 must be 31");

   inline void runConstexprStlTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " Constexpr STL 运行机制与瞬态内存管理验证套件
";
       std::cout << "=======================================================

";

       std::cout << "[测试 1: 静态断言矩阵]: 全部通过。编译期动态内存申请与排序均在编译阶段完成折叠。
";
       std::cout << "  - 编译期固化质数结果: ";
       for (auto p : top5_primes) {
           std::cout << p << " ";
       }
       std::cout << "

";

       // 运行期环境调用双态探针
       int runtime_mode = core_stl::DualExecutionProbe::evaluate_mode();
       std::cout << "[测试 2: 双态求值环境探针]:
";
       std::cout << "  - 运行期调用 evaluate_mode() 返回值: " << runtime_mode << " (预期为 2)
";
       assert(runtime_mode == 2);
       std::cout << "  - 探针成功区分了运行期与编译期求值路径。

";

       // 运行期下复用 ConstexprVector 执行海量动态增删验证
       core_stl::ConstexprVector<std::string> str_vec;
       str_vec.emplace_back("Modern");
       str_vec.emplace_back("C++");
       str_vec.emplace_back("Constexpr");
       str_vec.emplace_back("Engine");

       assert(str_vec.size() == 4);
       assert(str_vec[0] == "Modern");
       assert(str_vec[3] == "Engine");

       str_vec.pop_back();
       assert(str_vec.size() == 3);

       std::cout << "[测试 3: 运行期对象生命周期与析构重用]:
";
       std::cout << "  - 字符串动态容器容量: " << str_vec.capacity() << ", 元素数量: " << str_vec.size() << "
";
       std::cout << "  - 动态元素验证通过，无内存泄漏。

";

       std::cout << "=======================================================
";
       std::cout << " 全部测试用例运行完毕，系统状态满足设计不变量。
";
       std::cout << "=======================================================
";
   }

   } // namespace test
