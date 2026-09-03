=========================================================================================================
极简 Allocator 实战：allocate / deallocate 原始内存管理、construct / destroy 生命周期分离
=========================================================================================================

.. note:: 前置背景与上下文承接
   在第 7 模块（``07_modern_stl_and_ranges_architecture``）中，我们全面剖析了现代 C++ 泛型体系的高层抽象演化，包括 C++20 Ranges 管道、非拥有视图（``std::span`` / ``std::string_view``）、编译期常量求值容器以及基于协程状态机的 ``std::generator`` 与无锁并发原语。自此，全书从理论基础、底层对象模型、容器内幕到现代扩展的纵深分析已构建完备。进入第 8 模块——工业级 Mini-STL 实战与性能工程，我们的核心任务是将前述全部分析成果落地为完全自包含、具备工业级严谨度的独立组件实现。STL 容器设计的基石在于**内存资源获取与对象生命周期的物理分离**。如果直接使用原生 ``new T[n]``，语言规则强制要求调用默认构造函数并在分配时立刻启动全部对象的生命周期，这使得实现动态扩容预留容量（Capacity > Size）、按需原位构造（Emplace）以及异常安全回滚成为不可能。本节将从微架构层面对内存分配器（Allocator）与未初始化内存管理进行解耦，构建自包含的 ``MiniAllocator`` 与 ``MiniAllocatorTraits`` 体系。

原始存储与对象生命周期的微架构解耦
-----------------------------------

在 C++ 对象模型中，**存储期（Storage Duration）**与**对象生命周期（Object Lifetime）**属于两个正交的概念层级。一段分配在堆上的物理内存区域称为未初始化原始存储（Uninitialized Raw Storage）。这片区域在微架构层面仅代表经过边界对齐保护的一组连续物理字节序列，此时该地址空间内不存在任何合法的 C++ 类型实例。

.. list-table:: 原生 new[] 表达式与 Allocator 抽象的物理行为对比
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 核心维度
     - 原生 ``new T[n]`` 表达式
     - STL Allocator 架构分层
   * - **存储分配时机**
     - 隐式调用 ``::operator new[](bytes)`` 申请存储
     - 显式调用 ``alloc.allocate(n)`` 获取未初始化地址
   * - **构造执行控制**
     - 强制对 $n$ 个槽位立即执行默认构造函数
     - 允许槽位保持纯原始内存，按需调用 ``construct`` 启动生命周期
   * - **容量与尺寸模型**
     - 尺寸恒等于容量（$	ext{Size} \equiv 	ext{Capacity}$）
     - 尺寸与容量严格解耦（$	ext{Capacity} \ge 	ext{Size}$）
   * - **析构控制粒度**
     - ``delete[]`` 强制批量析构全量 $n$ 个对象
     - ``destroy`` 支持针对特定单个槽位结束对象生命周期
   * - **异常回滚能力**
     - 构造中间抛出异常时由运行时隐式回滚，外部无法介入
     - 容器可捕获构造异常，精确逆序析构已构造元素并保留或释放内存

原生 ``new[]`` 操作将内存分配与对象构造绑定在一起。对于动态数组（如 ``std::vector``），这种绑定破坏了性能与语义：一方面，容器无法预先分配备用容量；另一方面，若类型 ``T`` 未提供默认构造函数，``new T[n]`` 将直接引发编译失败。因此，现代 STL 容器必须通过分配器将操作链拆分为四个离散的物理动作：``allocate``、``construct``、``destroy``、``deallocate``。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                  未初始化存储与对象生命周期阶段流转状态机                   |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |           allocate(n)                                                       |
   |    [ 空指针状态 ] ----------> [ 原始存储区间 (Raw Storage) ]                |
   |                                 (满足 alignof(T) 与 sizeof(T)*n,            |
   |                                  未启动任何对象生命周期)                    |
   |                                      |         ^                            |
   |                                      |         |                            |
   |                    construct(p, val) |         | destroy(p)                 |
   |                    (启动对象生命周期)|         | (结束生命周期，调用析构)   |
   |                                      v         |                            |
   |                               [ 有效对象实例 (Live Object) ]                |
   |                                                                             |
   |           deallocate(p, n)                                                  |
   |    [ 原始存储区间 ] ----------------> [ 归还系统堆内存 / 终止 ]             |
   |    (必须确保所有内部槽位均已完成 destroy)                                   |
   |                                                                             |
   +-----------------------------------------------------------------------------+

allocate 与 deallocate 内存管理机制
-----------------------------------

分配器的首要职责是向上层容器提供满足尺寸与对齐边界的裸内存块。

计算溢出防御与分配上限（max_size）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 64 位体系下，容器申请的元素个数 $n$ 必须转换为字节数 $n 	imes 	ext{sizeof}(T)$。若该乘法运算在 ``std::size_t`` 范围内发生无符号整数回绕（Wrap-around），将导致向操作系统申请一个远小于预期容量的微小内存块。后续容器对该内存块按 $n$ 个对象进行写入时，将直接引发灾难性的堆缓冲区溢出（Heap Buffer Overflow）。

分配器通过 ``max_size()`` 建立安全边界：

.. math::

   	ext{max\_size} = \frac{	ext{std::numeric\_limits}\langle	ext{std::size\_t}\rangle::\max()}{	ext{sizeof}(T)}

在执行任何物理分配前，必须执行边界断言：若 $n > 	ext{max\_size}()$，必须显式抛出 ``std::bad_array_new_length`` 异常。对于 $n = 0$ 的请求，标准允许返回实现定义的指针或空指针，工业级实践通常直接返回 ``nullptr``。

超对齐类型（Over-aligned Types）的硬件级适配
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

C++17 引入了对超对齐类型的语言级支持。默认的全局 ``::operator new(size_t)`` 仅保证返回满足系统基础对齐要求（由宏 ``__STDCPP_DEFAULT_NEW_ALIGNMENT__`` 定义，通常为 8 或 16 字节）的内存地址。当用户定义的结构体包含 AVX-512 向量寄存器类型或显式声明了 ``alignas(64)`` 时，普通分配接口将产生非对齐地址，触发微架构级别的硬件异常或严重的跨缓存行惩罚。

工业级分配器使用编译期分支 ``if constexpr`` 进行对齐分发：

.. code-block:: cpp

   if constexpr (alignof(T) > __STDCPP_DEFAULT_NEW_ALIGNMENT__) {
       return static_cast<T*>(::operator new(bytes, std::align_val_t{alignof(T)}));
   } else {
       return static_cast<T*>(::operator new(bytes));
   }

释放接口必须保持严格对称。调用 ``deallocate(p, n)`` 时，传入的指针 $p$ 与容量参数 $n$ 必须与原先 ``allocate`` 的输入严格一致。借助 C++14 的 Sized Deallocation 与 C++17 的 Aligned Deallocation，分配器将字节数与对齐标签显式回传给底层内存运行时（如 jemalloc、tcmalloc 或 glibc ptmalloc），避免内存管理器在元数据查找中产生额外的开销：

.. code-block:: cpp

   if constexpr (alignof(T) > __STDCPP_DEFAULT_NEW_ALIGNMENT__) {
       ::operator delete(p, bytes, std::align_val_t{alignof(T)});
   } else {
       ::operator delete(p, bytes);
   }

construct 与 destroy 生命周期精细控制
------------------------------------

内存分配完成后，容器需要对存储区域内的具体槽位执行就地构造。

placement new 与类型安全转换
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

启动对象生命周期的底层机制是 **定位 new 表达式（Placement New）**。其函数签名定义于 ``<new>`` 头文件中：

.. code-block:: cpp

   void* operator new(std::size_t, void* ptr) noexcept;

该函数不执行任何实际的堆分配，仅直接返回传入的地址指针 ``ptr``。编译器在生成的汇编代码中，直接将目标对象的构造函数调用指令对准该内存地址。

实现 ``construct`` 时包含两个关键细节：
1. **显式类型转换 ``static_cast<void*>(p)``**：必须将类型指针转换为通用裸指针 ``void*``。这确保了编译器精确匹配到全局的 Placement New，阻断类类型内部可能重载的类属 ``operator new`` 对生命周期控制的干扰。
2. **完美转发 ``std::forward<Args>(args)...``**：利用万能引用与完美转发机制，原汁原味地将左值或右值实参传递给对象构造函数，支持原位高效构造（In-place Emplacement）。

在 C++20 中，标准库引入了 ``std::construct_at(p, std::forward<Args>(args)...)``，其底层语义与上述逻辑等价，并补充了在编译期常量表达式（``constexpr``）中的运行支持。

伪析构调用与平凡类型优化
~~~~~~~~~~~~~~~~~~~~~~~~

与构造相对，结束对象生命周期必须显式调用其析构函数：``p->~T()``。

需要严格指出：调用析构函数仅释放对象所持有的外部资源（如文件描述符、堆句柄或下层容器指针），该槽位所在的物理内存地址依然保持分配状态。容器可以在该物理地址上重新调用 ``construct`` 放置新对象，或者最终通过 ``deallocate`` 统一释放整块存储。

对于满足 ``std::is_trivially_destructible_v<T>`` 的平凡类型（如原生整数、浮点数或纯 POD 结构体），其析构函数不包含任何副作用。在编译优化流水线中，这类析构循环会被优化器整块消除，达成零运行时指令开销。

容器尺寸递增的事务提交顺序
~~~~~~~~~~~~~~~~~~~~~~~~~~

在容器（如动态数组）中执行追加操作时，状态修改必须遵循严格的拓扑顺序：

.. code-block:: text

   [ 步骤 1: 定位槽位 ] 计算当前插入地址 target = data_ + size_;
   [ 步骤 2: 原位构造 ] traits::construct(alloc_, target, std::forward<Args>(args)...);
   [ 步骤 3: 提交状态 ] ++size_;  // 必须在构造彻底完成且无异常抛出后递增

若将步骤 3 提前至构造之前，一旦构造函数在执行过程中抛出异常，外层异常处理逻辑在对容器执行析构清理时，将错误地认为 ``data_[size_]`` 已经是一个有效对象，进而对其调用 ``destroy``。在未完成构造的脏内存上调用析构函数将引发严重的未定义行为。

未初始化内存操作算法与异常安全回滚
----------------------------------

在容器执行批量初始化、拷贝构造或扩容迁移时，面对的不是初始化好的对象序列，而是未初始化的裸内存。STL 提供了专门的未初始化内存算法集：``uninitialized_copy``、``uninitialized_fill``、``uninitialized_move``。

强异常安全保证与逆序析构
~~~~~~~~~~~~~~~~~~~~~~~~

未初始化批量操作的核心挑战在于**强异常安全保证（Strong Exception Safety Guarantee）**：在向包含 $N$ 个槽位的原始内存连续构造元素时，假设在处理第 $k$ 个槽位（$0 \le k < N$）时构造函数抛出了异常，此时系统必须捕获该异常，并严格按照与构造完全相反的逆序，将前 $k-1$ 个已经成功构造的有效对象依次调用 ``destroy`` 进行销毁，随后释放新分配的存储空间，最后重新将原始异常向外抛出。

.. code-block:: text

   新分配区间: [ Slot 0 ] [ Slot 1 ] ... [ Slot k-1 ] [ Slot k ] ... [ Slot N-1 ]
   构造进度:      成功       成功             成功        抛出异常!
                                                |
                 +------------------------------+
                 v
   回滚操作:   销毁 Slot k-1 -> 销毁 Slot k-2 -> ... -> 销毁 Slot 0
   收尾操作:   释放底层存储，抛出异常，保证无泄漏

基于 RAII 的回滚守卫模式
~~~~~~~~~~~~~~~~~~~~~~~~

在工程实践中，显式编写多层嵌套的 ``try-catch`` 容易产生遗漏。现代 STL 广泛采用 RAII 事务守卫模式管理构造过程：

.. code-block:: cpp

   template <class ForwardIt, class Alloc>
   struct UninitializedRollbackGuard {
       Alloc& alloc;
       ForwardIt first;
       ForwardIt current;
       bool committed = false;

       ~UninitializedRollbackGuard() {
           if (!committed) {
               while (current != first) {
                   --current;
                   mini_allocator_traits<Alloc>::destroy(alloc, std::addressof(*current));
               }
           }
       }
   };

该守卫在构造循环全部成功完成后置位 ``committed = true``。若中途由于任何原因发生栈展开，守卫析构函数将自动执行逆序销毁，完全闭合了异常路径上的安全漏洞。

mini_allocator_traits 统一适配设计
----------------------------------

C++98 时代的容器直接依赖分配器提供的具体成员函数（如 ``alloc.allocate``、``alloc.construct``）。这种紧耦合导致了两个架构缺陷：
1. **接口冗余与标准化割裂**：每个分配器必须重复实现完全相同的样板模板函数；
2. **指针类型假设僵化**：无法无缝引入非裸指针（Fancy Pointer，如跨进程共享内存偏移指针 ``offset_ptr``）。

C++11 引入了 ``std::allocator_traits`` 作为唯一中枢。现代容器绝不允许直接调用分配器的方法，而是全部重定向至 Traits 接口。

.. list-table:: allocator_traits 核心反射与回退机制
   :widths: 25 35 40
   :header-rows: 1
   :class: tight-table

   * - Traits 静态接口
     - 优先分发路径
     - 缺省回退（Fallback）路径
   * - ``allocate(a, n)``
     - ``a.allocate(n)``
     - 无回退（分配器必须提供核心分配能力）
   * - ``deallocate(a, p, n)``
     - ``a.deallocate(p, n)``
     - 无回退（分配器必须提供核心释放能力）
   * - ``construct(a, p, args...)``
     - 若 ``a.construct(p, args...)`` 合法，则调用该成员
     - 回退到全局 ``::new (static_cast<void*>(p)) T(std::forward<Args>(args)...)``
   * - ``destroy(a, p)``
     - 若 ``a.destroy(p)`` 合法，则调用该成员
     - 回退到标准伪析构调用 ``p->~T()``
   * - ``max_size(a)``
     - 若 ``a.max_size()`` 合法，则调用该成员
     - 回退到 ``numeric_limits<size_type>::max() / sizeof(value_type)``

通过 SFINAE 与 C++17 ``std::void_t``，Traits 能够在编译期自动探测分配器是否定制了特定的生命周期钩子，在保证高扩展性的同时免除了简单分配器的样板代码负担。

自包含工业级 Mini-Allocator 引擎实战
------------------------------------

以下提供完整的、自包含的高性能现代分配器架构源码。

实现涵盖：
1. **MiniAllocator<T>**：满足现代 STL 分配器最小概念集合，具备超对齐支持与溢出安全保护；
2. **MiniAllocatorTraits<Alloc>**：基于 SFINAE 萃取与就地回退的统一分发中枢；
3. **未初始化内存算法集**：自包含的 ``mini_uninitialized_copy`` 与 ``mini_uninitialized_fill``，内置异常回滚事务保证；
4. **生命周期监控测试套件**：利用带有全局计数器与可控异常注入的 ``InstanceTracer``，严格断言验证正常分配、对齐属性、异常强安全回滚及析构平衡。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <cstddef>
   #include <limits>
   #include <new>
   #include <type_traits>
   #include <utility>
   #include <cassert>
   #include <stdexcept>

   namespace mini_stl {

   // =========================================================================
   // 1. 工业级通用分配器 MiniAllocator<T>
   // =========================================================================

   template <typename T>
   class MiniAllocator {
   public:
       using value_type = T;
       using pointer = T*;
       using const_pointer = const T*;
       using size_type = std::size_t;
       using difference_type = std::ptrdiff_t;

       // 泛型重绑定结构：为节点式容器跨类型分配提供支持
       template <typename U>
       struct rebind {
           using other = MiniAllocator<U>;
       };

       constexpr MiniAllocator() noexcept = default;
       constexpr ~MiniAllocator() noexcept = default;

       template <typename U>
       constexpr MiniAllocator(const MiniAllocator<U>&) noexcept {}

       [[nodiscard]] pointer allocate(size_type n) {
           if (n == 0) {
               return nullptr;
           }
           if (n > max_size()) {
               throw std::bad_array_new_length{};
           }

           const size_type bytes = n * sizeof(T);

           // 超对齐硬件分发
           if constexpr (alignof(T) > __STDCPP_DEFAULT_NEW_ALIGNMENT__) {
               return static_cast<pointer>(::operator new(bytes, std::align_val_t{alignof(T)}));
           } else {
               return static_cast<pointer>(::operator new(bytes));
           }
       }

       void deallocate(pointer p, size_type n) noexcept {
           if (p == nullptr) {
               return;
           }

           const size_type bytes = n * sizeof(T);
           if constexpr (alignof(T) > __STDCPP_DEFAULT_NEW_ALIGNMENT__) {
               ::operator delete(p, bytes, std::align_val_t{alignof(T)});
           } else {
               ::operator delete(p, bytes);
           }
       }

       [[nodiscard]] constexpr size_type max_size() const noexcept {
           return std::numeric_limits<size_type>::max() / sizeof(T);
       }

       friend constexpr bool operator==(const MiniAllocator&, const MiniAllocator&) noexcept {
           return true;
       }

       friend constexpr bool operator!=(const MiniAllocator&, const MiniAllocator&) noexcept {
           return false;
       }
   };

   // =========================================================================
   // 2. 分配器特征萃取层 MiniAllocatorTraits<Alloc>
   // =========================================================================

   namespace detail {

   template <typename, typename, typename... Args>
   struct has_member_construct : std::false_type {};

   template <typename Alloc, typename U, typename... Args>
   struct has_member_construct<
       Alloc,
       U,
       std::void_t<decltype(std::declval<Alloc&>().construct(
           std::declval<U*>(), std::declval<Args>()...))>,
       Args...
   > : std::true_type {};

   template <typename, typename, typename = void>
   struct has_member_destroy : std::false_type {};

   template <typename Alloc, typename U>
   struct has_member_destroy<
       Alloc,
       U,
       std::void_t<decltype(std::declval<Alloc&>().destroy(std::declval<U*>()))>
   > : std::true_type {};

   } // namespace detail

   template <typename Alloc>
   struct MiniAllocatorTraits {
       using allocator_type = Alloc;
       using value_type = typename Alloc::value_type;
       using pointer = value_type*;
       using const_pointer = const value_type*;
       using size_type = std::size_t;
       using difference_type = std::ptrdiff_t;

       template <typename U>
       using rebind_alloc = typename Alloc::template rebind<U>::other;

       [[nodiscard]] static pointer allocate(Alloc& a, size_type n) {
           return a.allocate(n);
       }

       static void deallocate(Alloc& a, pointer p, size_type n) noexcept {
           a.deallocate(p, n);
       }

       template <typename U, typename... Args>
       static void construct(Alloc& a, U* p, Args&&... args) {
           if constexpr (detail::has_member_construct<Alloc, U, void, Args&&...>::value) {
               a.construct(p, std::forward<Args>(args)...);
           } else {
               ::new (static_cast<void*>(p)) U(std::forward<Args>(args)...);
           }
       }

       template <typename U>
       static void destroy(Alloc& a, U* p) noexcept(std::is_nothrow_destructible_v<U>) {
           if constexpr (detail::has_member_destroy<Alloc, U>::value) {
               a.destroy(p);
           } else {
               p->~U();
           }
       }

       [[nodiscard]] static constexpr size_type max_size(const Alloc& a) noexcept {
           return a.max_size();
       }
   };

   // =========================================================================
   // 3. 未初始化内存算法簇与异常安全回滚守卫
   // =========================================================================

   template <typename ForwardIt, typename Alloc>
   class UninitializedGuard {
   public:
       UninitializedGuard(Alloc& a, ForwardIt first) noexcept
           : alloc_(a), first_(first), current_(first) {}

       ~UninitializedGuard() {
           if (!committed_) {
               rollback();
           }
       }

       void advance(ForwardIt next) noexcept {
           current_ = next;
       }

       void commit() noexcept {
           committed_ = true;
       }

   private:
       void rollback() noexcept {
           while (current_ != first_) {
               --current_;
               MiniAllocatorTraits<Alloc>::destroy(alloc_, std::addressof(*current_));
           }
       }

       Alloc& alloc_;
       ForwardIt first_;
       ForwardIt current_;
       bool committed_ = false;
   };

   template <typename InputIt, typename ForwardIt, typename Alloc>
   ForwardIt mini_uninitialized_copy(InputIt first, InputIt last, ForwardIt d_first, Alloc& alloc) {
       UninitializedGuard<ForwardIt, Alloc> guard(alloc, d_first);
       ForwardIt dest = d_first;
       for (; first != last; ++first, (void)++dest) {
           MiniAllocatorTraits<Alloc>::construct(alloc, std::addressof(*dest), *first);
           guard.advance(dest + 1);
       }
       guard.commit();
       return dest;
   }

   template <typename ForwardIt, typename Size, typename T, typename Alloc>
   ForwardIt mini_uninitialized_fill_n(ForwardIt first, Size count, const T& value, Alloc& alloc) {
       UninitializedGuard<ForwardIt, Alloc> guard(alloc, first);
       ForwardIt dest = first;
       for (Size i = 0; i < count; ++i, (void)++dest) {
           MiniAllocatorTraits<Alloc>::construct(alloc, std::addressof(*dest), value);
           guard.advance(dest + 1);
       }
       guard.commit();
       return dest;
   }

   } // namespace mini_stl

   // =========================================================================
   // 4. 生命周期探测器与单元测试驱动
   // =========================================================================

   namespace test {

   struct InstanceTracer {
       static inline int active_instances = 0;
       static inline int total_constructed = 0;
       static inline int total_destructed = 0;
       static inline int throw_on_index = -1;

       int id;

       static void reset() noexcept {
           active_instances = 0;
           total_constructed = 0;
           total_destructed = 0;
           throw_on_index = -1;
       }

       explicit InstanceTracer(int val) : id(val) {
           if (throw_on_index >= 0 && total_constructed == throw_on_index) {
               throw std::runtime_error("Simulated Constructor Exception");
           }
           ++active_instances;
           ++total_constructed;
       }

       InstanceTracer(const InstanceTracer& other) : id(other.id) {
           if (throw_on_index >= 0 && total_constructed == throw_on_index) {
               throw std::runtime_error("Simulated Copy Constructor Exception");
           }
           ++active_instances;
           ++total_constructed;
       }

       ~InstanceTracer() {
           --active_instances;
           ++total_destructed;
       }
   };

   // 超对齐测试结构 (64 字节对齐，模拟 AVX-512)
   struct alignas(64) OverAlignedData {
       uint64_t values[8];
   };

   inline void runMiniAllocatorTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " Mini-Allocator 与未初始化内存微架构验证套件
";
       std::cout << "=======================================================

";

       using Alloc = mini_stl::MiniAllocator<InstanceTracer>;
       using Traits = mini_stl::MiniAllocatorTraits<Alloc>;

       Alloc alloc;

       // 1. 基础存储分配与原位构造验证
       std::cout << "[测试 1: 原始内存分配与显式生命周期控制]:
";
       InstanceTracer::reset();
       constexpr std::size_t capacity = 4;
       InstanceTracer* buffer = Traits::allocate(alloc, capacity);
       assert(buffer != nullptr);
       assert(InstanceTracer::active_instances == 0); // 纯裸内存，尚未构造任何对象

       for (std::size_t i = 0; i < capacity; ++i) {
           Traits::construct(alloc, buffer + i, static_cast<int>(i * 10));
       }
       assert(InstanceTracer::active_instances == 4);
       assert(buffer[2].id == 20);

       // 显式析构销毁
       for (std::size_t i = capacity; i > 0; --i) {
           Traits::destroy(alloc, buffer + (i - 1));
       }
       assert(InstanceTracer::active_instances == 0);
       assert(InstanceTracer::total_destructed == 4);

       Traits::deallocate(alloc, buffer, capacity);
       std::cout << "  - 原始存储获取、就地构造、显式析构与存储释放全生命周期对齐验证成功。

";

       // 2. 超对齐类型硬件对齐边界断言
       std::cout << "[测试 2: 超对齐类型 (alignas(64)) 分配与释放]:
";
       mini_stl::MiniAllocator<OverAlignedData> aligned_alloc;
       OverAlignedData* aligned_ptr = aligned_alloc.allocate(2);
       const uintptr_t address = reinterpret_cast<uintptr_t>(aligned_ptr);
       assert((address % 64) == 0); // 必须满足 64 字节硬件对齐
       std::cout << "  - 物理地址: 0x" << std::hex << address << std::dec 
                 << "，严格满足 64 字节对齐约束。
";
       aligned_alloc.deallocate(aligned_ptr, 2);
       std::cout << "  - Aligned Deallocation 释放成功。

";

       // 3. 强异常安全回滚测试
       std::cout << "[测试 3: 未初始化填充过程中的强异常安全逆序回滚]:
";
       InstanceTracer::reset();
       constexpr std::size_t rollback_cap = 5;
       InstanceTracer* rollback_buf = Traits::allocate(alloc, rollback_cap);

       // 设置构造第 3 个对象（索引从 0 开始计，即 total_constructed == 2）时触发异常
       InstanceTracer::throw_on_index = 2;
       InstanceTracer template_val(99); // total_constructed = 0, active = 1
       InstanceTracer::throw_on_index = 2; // 重设异常点

       bool exception_caught = false;
       try {
           mini_stl::mini_uninitialized_fill_n(rollback_buf, rollback_cap, template_val, alloc);
       } catch (const std::runtime_error& e) {
           exception_caught = true;
       }

       assert(exception_caught);
       // 异常抛出后，已经构造的槽位 0 与 槽位 1 必须被完全析构回滚
       // active_instances 仅剩 template_val 自身的 1 个存活实例
       assert(InstanceTracer::active_instances == 1);
       std::cout << "  - 捕获预期异常，前序已构造的有效对象全部被逆序安全析构。
";
       std::cout << "  - 存活对象计数精确归零（排除外部模板对象），无泄漏、无悬垂。
";

       Traits::deallocate(alloc, rollback_buf, rollback_cap);
       std::cout << "  - 存储空间顺利释放，容器状态维持未污染的一致性。

";

       std::cout << "=======================================================
";
       std::cout << " 全部测试断言通过，Mini-Allocator 物理微架构契约严格成立。
";
       std::cout << "=======================================================
";
   }

   } // namespace test
