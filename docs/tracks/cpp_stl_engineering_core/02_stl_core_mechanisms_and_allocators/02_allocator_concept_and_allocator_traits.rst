==================================================================================================================================
内存分配器体系：allocator 接口契约、allocator_traits 统一抽象、未初始化内存批量构造算法
==================================================================================================================================

.. note:: 前置背景与上下文承接
   在第二模块首章《迭代器核心体系与能力分层》中，系统建立了 STL 的游标模型、六级迭代器分类学、``std::iterator_traits`` 编译期萃取及 Tag Dispatching / Concepts 路由机制，完成了算法与容器内部寻址拓扑的解耦。然而，容器除了维护元素逻辑拓扑外，还必须管理底层的物理内存存储与元素生命周期。本章深入剖析 STL 内存子系统的核心枢纽 —— 内存分配器（Allocator）体系：从原始内存申请与对象生命周期的物理分离哲学，到 C++98 至 C++20 分配器接口契约的演进历程；从 ``std::allocator_traits`` 代理中枢的关联类型补齐、节点类型改绑（Rebind）机制与容器状态传播策略，到未初始化内存区域（Raw Memory）上的异常安全批量构造算法与事务回滚屏障，最终通过工业级带状态追踪分配器与 RAII 回滚构造器实现，奠定后续各类 STL 容器物理内存管理的理论与工程基石。

内存分配器核心哲学与对象生命周期的物理分离
------------------------------------------

在 C++ 底层对象模型中，内建的 ``new`` 表达式执行复合操作：首先调用底层的全局内存分配函数（``operator new(sizeof(T))``）在堆上取得指定大小的未初始化虚拟地址空间，随后在所获得的起始地址处执行目标类型的构造函数完成对象初始化。相应地，``delete`` 表达式首先调用对象的析构函数释放资源，随后调用全局内存释放函数（``operator delete(p)``）归还物理内存。

对于通用标准容器（如 ``std::vector``、``std::list``、``std::map``），这种将“内存存储分配”与“对象构造初始化”强行绑定的机制会导致严重的性能损耗与语义冲突：

1. **容量预分配与惰性构造需求**：``std::vector`` 在执行预留空间（``reserve(N)``）或按几何倍数扩容时，必须预先从操作系统或堆管理器取得足以容纳 $N$ 个元素的连续物理存储，但在元素实际插入（如 ``push_back``、``emplace_back``）之前，该内存区域内严禁存在已构造的对象实例。若直接使用 ``new T[N]``，将强制要求 $N$ 个对象全部执行默认构造函数，带来 $O(N)$ 的无效计算开销，且强制约束类型 $T$ 必须具备默认构造能力。
2. **多态内存源隔离需求**：不同容器实例或不同业务子系统对物理内存的来源存在差异化约束。部分模块需要从操作系统全局堆（``glibc malloc`` / ``jemalloc``）分配内存，部分高频节点容器需要从单线程专用的内存池（Memory Pool）或栈上固定缓冲区（Arena）中切分内存，还有部分嵌入式或共享内存系统需要将对象直接映射至特定硬件地址段。容器的数据结构逻辑必须与具体的物理内存获取策略彻底解耦。

STL 分配器（Allocator）子系统通过在架构层面将单一的 ``new`` / ``delete`` 拆解为四个独立的正交原语，建立了严格的内存状态机：

.. code-block:: text

   +-------------------------------------------------------------------------------------------------------+
   |                             STL 物理内存与对象生命周期四阶段状态机                                    |
   +-------------------------------------------------------------------------------------------------------+
   |                                                                                                       |
   |   [ 阶段 0: 无存储状态 ]                                                                              |
   |          |                                                                                            |
   |          | allocate(n): 向底层内存源请求 n * sizeof(T) 字节，满足 alignof(T) 字节对齐                 |
   |          v                                                                                            |
   |   [ 阶段 1: 原始未初始化存储 (Raw Memory) ]                                                          |
   |          |   - 地址有效且已对齐，属于合法虚拟内存页                                                   |
   |          |   - 物理字节处于未定义状态 (Indeterminate Values)                                          |
   |          |   - 严禁执行读取、赋值或普通指针解引用                                                     |
   |          |                                                                                            |
   |          | construct(p, args...): 定位放置构造 (Placement New / construct_at)                          |
   |          v                                                                                            |
   |   [ 阶段 2: 有效对象存活期 (Active Object Lifetime) ]                                                |
   |          |   - 对象生命周期正式确立，虚表指针及成员变量初始化完成                                     |
   |          |   - 支持正常的成员访问、拷贝、移动与赋值运算                                               |
   |          |                                                                                            |
   |          | destroy(p): 显式调用析构函数 p->~T()                                                       |
   |          v                                                                                            |
   |   [ 阶段 3: 归还为原始存储 (Raw Memory Reversion) ]                                                   |
   |          |   - 对象生命周期终结，内部持有的外部资源被释放                                             |
   |          |   - 占用的物理字节空间仍然保留，可重新用于构造新对象                                       |
   |          |                                                                                            |
   |          | deallocate(p, n): 将首地址为 p、大小为 n 的内存块归还给底层内存源                          |
   |          v                                                                                            |
   |   [ 阶段 0: 存储已释放 (Deallocated) ]                                                                |
   |                                                                                                       |
   +-------------------------------------------------------------------------------------------------------+

四阶段原语的物理职责边界：

- **``allocate(n)``**：负责向底层虚拟内存系统或堆管理器请求一段长度严格满足 $n 	imes 	ext{sizeof}(T)$ 字节且起始地址严格按 $	ext{alignof}(T)$ 对齐的连续平坦内存块。此阶段仅建立虚拟内存映射，不触发任何构造函数。
- **``construct(p, args...)``**：在已分配的原始内存地址 ``p`` 上执行 ``::new (static_cast<void*>(p)) T(std::forward<Args>(args)...)``，正式确立对象的生命周期，建立对象的类型不变量、虚表指针（若存在）及成员初始状态。
- **``destroy(p)``**：显式调用析构函数 ``p->~T()``（或 C++20 ``std::destroy_at(p)``），结束该地址处对象的生命周期，执行成员析构与外部资源释放，但保留该处的物理内存占用。
- **``deallocate(p, n)``**：接收先前由 ``allocate`` 返回的起始指针 ``p`` 与分配时的元素个数 $n$，将对应的物理字节块归还给底层分配器或操作系统，解除内存映射。

C++98 至 C++20 Allocator 概念契约演进与接口规范
-----------------------------------------------

Allocator 的接口规范在 C++ 标准库演进过程中经历了从重型全功能类到轻量化纯策略类的架构收敛。

C++98 时代的原始 Allocator 模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 C++98 标准中，每一个符合标准的分配器类必须在其内部直接提供一整套冗长的类型定义与成员函数：

.. code-block:: cpp

   // C++98 标准分配器概念示意（高度冗余）
   template <typename T>
   class Allocator98 {
   public:
       typedef T              value_type;
       typedef T*             pointer;
       typedef const T*       const_pointer;
       typedef T&             reference;
       typedef const T&       const_reference;
       typedef std::size_t    size_type;
       typedef std::ptrdiff_t difference_type;

       template <typename U>
       struct rebind {
           typedef Allocator98<U> other;
       };

       pointer address(reference x) const { return &x; }
       const_pointer address(const_reference x) const { return &x; }

       pointer allocate(size_type n, const void* hint = 0);
       void deallocate(pointer p, size_type n);

       size_type max_size() const throw();

       void construct(pointer p, const T& val) {
           new (static_cast<void*>(p)) T(val);
       }
       void destroy(pointer p) {
           p->~T();
       }
   };

C++98 模型存在三个结构性缺陷：

1. **类型绑定硬编码**：容器直接调用 ``Alloc::allocate`` 与 ``Alloc::construct``，导致分配器必须显式提供 ``pointer``、``reference``、``address`` 以及 ``rebind`` 模板结构体。编写自定义分配器需要书写大量毫无实际逻辑的模板样板代码（Boilerplate）。
2. **完美转发缺失**：``construct`` 函数仅接收 ``const T& val``，无法支持就地完美转发构造（Emplace 机制），亦无法支持移动语义，导致大对象在构造时产生多余的临时对象与拷贝开销。
3. **无状态假设与等价性僵化**：C++98 标准库曾预设所有同类型分配器实例均完全等价且无状态（Stateless），即任意实例分配的内存可由同类型另一个实例合法释放。这直接阻碍了基于局部 Arena、线程专属池或特定设备句柄的有状态分配器（Stateful Allocators）的工业级应用。

现代 C++ 标准对 Allocator 契约的精简与重构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

C++11 引入了分配器中枢代理类 ``std::allocator_traits``，将标准容器对分配器的访问全面重定向至 traits 代理层。由此，自定义 Allocator 本身的接口契约被极度简化。在 C++17 与 C++20 中，现代 Allocator 仅需提供极简的物理存储分配与归还接口：

.. code-block:: cpp

   // C++20 极简 Allocator 契约标准模型
   template <typename T>
   struct ModernAllocator {
       using value_type = T;

       constexpr ModernAllocator() noexcept = default;
       template <typename U>
       constexpr ModernAllocator(const ModernAllocator<U>&) noexcept {}

       [[nodiscard]] T* allocate(std::size_t n) {
           if (n > std::numeric_limits<std::size_t>::max() / sizeof(T)) {
               throw std::bad_array_new_length();
           }
           void* p = ::operator new(n * sizeof(T));
           return static_cast<T*>(p);
       }

       void deallocate(T* p, std::size_t n) noexcept {
           ::operator delete(p);
       }

       // 等价性比较：判断两分配器实例管理的存储是否互通
       friend constexpr bool operator==(const ModernAllocator&, const ModernAllocator&) noexcept {
           return true;
       }
       friend constexpr bool operator!=(const ModernAllocator&, const ModernAllocator&) noexcept {
           return false;
       }
   };

.. list-table:: C++ 各代标准 Allocator 规范与核心职责演进矩阵
   :widths: 14 20 22 20 24
   :header-rows: 1
   :class: tight-table

   * - 标准版本
     - 分配器核心职责
     - 构造与析构接口
     - 有状态分配器支持
     - 代理层介入机制
   * - C++98
     - 内存管理 + 构造/析构 + 繁琐类型别名
     - ``construct(p, val)`` / ``destroy(p)`` 成员函数
     - 规范预设无状态，跨实例释放未定义
     - 无代理层，容器直连 Allocator
   * - C++11
     - 聚焦原始内存分配，类型别名可选
     - 引入可变参数模板与完美转发
     - 完善支持，引入传播标志 (POCCA/POCMA/POCS)
     - 引入 ``std::allocator_traits`` 作为统一分发中枢
   * - C++17
     - 废弃 ``construct`` / ``destroy`` / ``rebind`` 等成员
     - 移入 ``allocator_traits`` 统一默认实现
     - 引入 ``std::pmr`` 多态内存资源体系
     - 全面强制通过 ``allocator_traits`` 路由
   * - C++20
     - 移除已废弃成员，支持 ``constexpr`` 分配
     - 推广 ``std::construct_at`` / ``std::destroy_at``
     - 容器支持编译期常量求值阶段动态分配
     - 基于 Concepts 强化 ``allocator_traits`` 约束

std::allocator_traits 代理中枢架构与类型改绑机制
-------------------------------------------------

在标准库架构中，``std::allocator_traits<Alloc>`` 承担着类似 ``std::iterator_traits`` 的类型萃取与接口统一转换职责。标准容器（如 ``std::vector<T, Alloc>``、``std::list<T, Alloc>``）内部严禁直接调用 ``Alloc::allocate`` 或 ``Alloc::construct``，必须严格通过 ``std::allocator_traits<Alloc>::allocate(...)`` 与 ``std::allocator_traits<Alloc>::construct(...)`` 进行中转调用。

.. code-block:: text

   +-------------------------------------------------------------------------------------------------------+
   |                             std::allocator_traits 代理中枢体系架构                                    |
   +-------------------------------------------------------------------------------------------------------+
   |  标准容器层 (std::vector, std::list, std::map, std::deque)                                            |
   +---------------------------------------------------+---------------------------------------------------+
                                                       | 统一标准调用: Traits::allocate / construct / ...
                                                       v
   +-------------------------------------------------------------------------------------------------------+
   |  std::allocator_traits<Alloc> 萃取与补齐中枢 (Type & Policy Synthesis Engine)                         |
   |    - 自动补齐缺省类型: pointer -> Alloc::value_type*, size_type -> size_t                         |
   |    - 自动改绑节点类型: rebind_alloc<Node> -> Alloc<Node>                                              |
   |    - 自动降级构造/析构: 若 Alloc 无 construct 则降级为 ::new ((void*)p) T(args...)                    |
   |    - 传播策略决策矩阵: propagate_on_container_copy/move/swap, is_always_equal                         |
   +---------------------------------------------------+---------------------------------------------------+
                                                       | 静态分发 / 默认实现降级
                                                       v
   +-------------------------------------------------------------------------------------------------------+
   |  底层分配器实现 (std::allocator, std::pmr::polymorphic_allocator, Custom Arena/Pool Allocator)        |
   +-------------------------------------------------------------------------------------------------------+

关联类型自动推导与补齐机制
~~~~~~~~~~~~~~~~~~~~~~~~~~

当自定义分配器未定义特定的类型别名时，``std::allocator_traits`` 基于 SFINAE 与条件编译提供标准默认推导规则：

1. ``pointer``：优先采用 ``Alloc::pointer``；若不存在，推导为 ``Alloc::value_type*``。
2. ``const_pointer``：优先采用 ``Alloc::const_pointer``；若不存在，推导为 ``std::pointer_traits<pointer>::rebind<const value_type>``（即 ``const Alloc::value_type*``）。
3. ``void_pointer``：优先采用 ``Alloc::void_pointer``；若不存在，推导为 ``std::pointer_traits<pointer>::rebind<void>``（即 ``void*``）。
4. ``difference_type``：优先采用 ``Alloc::difference_type``；若不存在，推导为 ``std::pointer_traits<pointer>::difference_type``（即 ``std::ptrdiff_t``）。
5. ``size_type``：优先采用 ``Alloc::size_type``；若不存在，推导为 ``std::make_unsigned_t<difference_type>``（即 ``std::size_t``）。

这种推导机制允许高阶分配器定义 **花式指针（Fancy Pointer）**，例如用于跨进程共享内存的相对偏移指针（Offset Pointer）或分段地址指针，而普通分配器仅需声明 ``value_type`` 即可满足全部类型要求。

Rebind 类型改绑机制的物理必然性
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当程序员声明一个双向链表 ``std::list<int, MyAlloc<int>>`` 时，模板形参中提供的分配器类型为针对用户数据类型 ``int`` 的 ``MyAlloc<int>``。

然而，在 ``std::list`` 的物理内存模型中，链表绝不单独为每个 ``int`` 分配 4 字节的孤立存储。链表的物理存储单元是包含前后向指针与数据字段的复合节点结构体：

.. code-block:: cpp

   // std::list 内部物理节点结构体拓扑
   template <typename T>
   struct __list_node {
       __list_node* prev;  // 8 字节前向指针
       __list_node* next;  // 8 字节后向指针
       T            value; // 用户数据载荷 (sizeof(T))
   };

``std::list`` 每次执行插入操作时，必须分配的是完整节点 ``__list_node<int>``（在 64 位系统上占用 $8 + 8 + 4 = 20 \rightarrow 24$ 字节，经对齐补齐），而非单纯的 4 字节 ``int``。

容器必须具备从用户提供的元素分配器 ``Alloc<T>`` 动态衍生出节点分配器 ``Alloc<Node>`` 的编译期推导能力。这一能力即为 **Rebind 机制**。

``std::allocator_traits`` 提供统一的改绑模板类型定义：

.. code-block:: cpp

   template <typename Alloc, typename U>
   struct rebind_alloc_helper {
       // 优先检测 Alloc 是否显式定义了 rebind<U>::other
       template <typename A, typename = typename A::template rebind<U>::other>
       static typename A::template rebind<U>::other test(int);

       // 若未定义，则自动将 Alloc<T, Args...> 模式匹配替换为 Alloc<U, Args...>
       template <typename A>
       static auto test(...) -> typename replace_first_arg<A, U>::type;

       using type = decltype(test<Alloc>(0));
   };

   template <typename Alloc>
   struct allocator_traits {
       template <typename U>
       using rebind_alloc = typename rebind_alloc_helper<Alloc, U>::type;

       template <typename U>
       using rebind_traits = std::allocator_traits<rebind_alloc<U>>;
   };

在容器实现中，节点分配器的构造与内存获取模式严格遵循以下规范：

.. code-block:: cpp

   template <typename T, typename Alloc = std::allocator<T>>
   class MiniList {
       using Node = __list_node<T>;
       // 利用 allocator_traits 将用户分配器改绑为内部节点分配器
       using NodeAlloc  = typename std::allocator_traits<Alloc>::template rebind_alloc<Node>;
       using NodeTraits = std::allocator_traits<NodeAlloc>;

       NodeAlloc node_allocator_;

   public:
       template <typename... Args>
       Node* create_node(Args&&... args) {
           // 1. 分配单个完整节点的物理存储
           Node* p = NodeTraits::allocate(node_allocator_, 1);
           try {
               // 2. 在未初始化节点存储上构造用户数据与指针
               NodeTraits::construct(node_allocator_, p, std::forward<Args>(args)...);
               return p;
           } catch (...) {
               NodeTraits::deallocate(node_allocator_, p, 1);
               throw;
           }
       }
   };

容器赋值、移动与交换中的 Allocator 传播策略矩阵
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于带有状态（成员变量、内存池句柄、Arena 指针）的分配器，当容器发生拷贝赋值、移动赋值或 ``swap`` 交换操作时，容器所持有的分配器实例是否随之复制或转移，直接决定了底层物理内存的所有权归属与释放合法性。

``std::allocator_traits`` 定义了四个核心传播类型标签（Propagation Traits），均为布尔类型的编译期常量：

1. **``propagate_on_container_copy_assignment`` (POCCA)**：
   在容器执行拷贝赋值运算（``c1 = c2``）时，若该 trait 为 ``std::true_type``，则目标容器 ``c1`` 将首先获取源容器 ``c2`` 的分配器副本 ``c1.alloc = c2.alloc``。若目标容器原有容量不足需要重新分配，将使用新赋予的分配器；若为 ``std::false_type``，则 ``c1`` 始终保留自身的分配器，仅使用自身的分配器分配新内存并拷贝元素值。
2. **``propagate_on_container_move_assignment`` (POCMA)**：
   在容器执行移动赋值运算（``c1 = std::move(c2)``）时：
   - 若 POCMA 为 ``std::true_type``：``c1`` 直接接管 ``c2`` 的分配器实例及底层的内部指针数组（$O(1)$ 指针窃取），随后将 ``c2`` 置空。
   - 若 POCMA 为 ``std::false_type``：
     - 若 ``c1.get_allocator() == c2.get_allocator()``，两容器分配器等价，仍可执行 $O(1)$ 内部指针与容量窃取。
     - 若 ``c1.get_allocator() != c2.get_allocator()``，由于 ``c1`` 无法使用自身的分配器释放由 ``c2`` 分配的物理存储，容器严禁窃取指针，必须退化为逐元素移动构造到新分配的存储空间中（时间复杂度退化为 $O(N)$），随后析构并释放 ``c2`` 的元素。
3. **``propagate_on_container_swap`` (POCS)**：
   在容器执行交换操作（``std::swap(c1, c2)``）时：
   - 若 POCS 为 ``std::true_type``：两容器在交换内部指针与容量的同时，直接调用 ``std::swap(c1.alloc, c2.alloc)`` 交换分配器实例，操作始终安全且为 $O(1)$。
   - 若 POCS 为 ``std::false_type``：要求 ``c1.get_allocator() == c2.get_allocator()`` 必须成立。若两个有状态分配器不相等，执行 ``swap`` 构成未定义行为（Undefined Behavior），因为交换后容器在析构时将使用不匹配的分配器释放对方的原存储。
4. **``is_always_equal``**：
   标识该类型的所有分配器实例是否在运行时永远等价（无状态分配器或全局共享单例池）。若为 ``std::true_type``，编译器在生成移动构造、移动赋值与交换代码时可完全静态消除分配器比较分支，生成纯粹的寄存器指针交换指令。

.. list-table:: std::allocator_traits 四大传播策略与状态判定矩阵
   :widths: 22 14 18 46
   :header-rows: 1
   :class: tight-table

   * - 传播类型标识
     - 默认推导值
     - 推荐自定义设定
     - 物理操作与内存管理约束
   * - ``propagate_on_container_copy_assignment``
     - ``false_type``
     - 状态独占时设为 ``true_type``
     - 拷贝赋值时决定是否复制分配器；若为 false，必须用原分配器重新分配
   * - ``propagate_on_container_move_assignment``
     - ``false_type``
     - 允许转移时设为 ``true_type``
     - 移动赋值时决定是否接管分配器；若为 false 且分配器不等，引发 $O(N)$ 元素重构
   * - ``propagate_on_container_swap``
     - ``false_type``
     - 允许交换时设为 ``true_type``
     - 交换时决定是否交换分配器；若为 false 且分配器不等，直接触发未定义行为 (UB)
   * - ``is_always_equal``
     - ``is_empty<Alloc>::type``
     - 有状态分配器显式设为 ``false_type``
     - 标识任意两实例是否可互相释放存储；指导编译器消除运行时等价性判定分支

未初始化内存批量构造算法与异常安全屏障
--------------------------------------

STL 在 `<memory>` 头文件中提供了一组底层未初始化内存操作算法（Raw Memory Algorithms）。这组算法是容器实现内部批量扩容、范围构造与区间插入的核心构件。

标准算法（如 ``std::copy``、``std::fill``）与未初始化内存算法（如 ``std::uninitialized_copy``、``std::uninitialized_fill``）的根本区别在于操作的目标物理内存状态：

- **``std::copy(first, last, d_first)``**：假定目标区间 ``[d_first, d_first + (last - first))`` 已经存在存活的有效对象，内部循环通过赋值操作符 ``*d_first = *first`` 修改对象状态。
- **``std::uninitialized_copy(first, last, d_first)``**：假定目标区间仅为通过 ``allocate`` 取得的纯原始未初始化存储，内部循环通过定位放置构造（Placement New / ``construct_at``）在每个原始地址上正式确立新对象的生命周期。

核心未初始化算法概览
~~~~~~~~~~~~~~~~~~~~

1. **``std::uninitialized_copy(first, last, d_first)``**：将源输入区间 ``[first, last)`` 内的每个元素通过拷贝构造方式初始化至目标未初始化存储区间。
2. **``std::uninitialized_fill(d_first, d_last, value)``**：将特定值 ``value`` 作为拷贝构造实参，批量初始化整个未初始化目标区间 ``[d_first, d_last)``。
3. **``std::uninitialized_fill_n(d_first, n, value)``**：从起始未初始化地址 ``d_first`` 开始，连续构造 $n$ 个相同副本。
4. **``std::uninitialized_move(first, last, d_first)``**：利用 ``std::move(*first)`` 将源区间的元素移动构造至未初始化目标区间。
5. **``std::uninitialized_default_construct(d_first, d_last)``**：在目标区间执行值未确定的默认初始化（Default Initialization，对于非类类型保留物理脏数据）。
6. **``std::uninitialized_value_construct(d_first, d_last)``**：在目标区间执行值初始化（Value Initialization，即 ``new (p) T()``，对基本标量清零）。
7. **``std::destroy(first, last)`` 与 ``std::destroy_n(first, n)``**：连续调用区间内每个对象的析构函数，将有效对象区间恢复为原始未初始化存储。

动态数组扩容中的异常安全回滚状态机
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

以 ``std::vector<T>`` 的几何级扩容（Reallocation）过程为例，未初始化内存算法必须提供严格的 **强异常安全保证（Strong Exception Safety Guarantee）**：如果在迁移过程中，第 $k$ 个元素的构造函数抛出了异常，容器必须确保已经构造完成的前 $k-1$ 个新对象被严格按逆序全部析构，新申请的物理存储空间被完整归还给分配器，同时原缓冲区内的所有旧元素状态保持完好无损。

.. code-block:: text

   +-------------------------------------------------------------------------------------------------------+
   |                       std::vector 扩容未初始化内存迁移与事务回滚状态机                                |
   +-------------------------------------------------------------------------------------------------------+
   |                                                                                                       |
   |   [ 旧缓冲区: 包含有效旧元素 ]                                                                        |
   |   old_start                                     old_finish                 old_end_of_storage          |
   |       |                                             |                              |                   |
   |       v                                             v                              v                   |
   |     +---------------------------------------------+------------------------------+                     |
   |     | Obj 0 | Obj 1 | ... | Obj k-1 | Obj k | ... | (未初始化的剩余空闲存储)      |                     |
   |     +---------------------------------------------+------------------------------+                     |
   |                                                                                                       |
   |   1. 申请新物理存储: new_start = AllocTraits::allocate(alloc, new_capacity)                            |
   |   2. 顺序执行批量构造迁移:                                                                             |
   |                                                                                                       |
   |   [ 新候选缓冲区: Raw Memory -> Active Objects ]                                                      |
   |   new_start                     new_cur (构建指针游标)                                                |
   |       |                            |                                                                  |
   |       v                            v                                                                  |
   |     +----------------------------+-----------------------------------------------+                    |
   |     | Obj 0' | Obj 1' | ...      | (尚未构造的原始未初始化存储空间)              |                    |
   |     +----------------------------+-----------------------------------------------+                    |
   |       \________________________/   \_____________________________________________/                    |
   |            已成功构造的前缀                    仍为原始字节 (严禁执行析构)                            |
   |                                                                                                       |
   |   分支 A: 构造第 k 个元素抛出异常 (Exception Caught)                                                  |
   |     - 事务回滚: 仅对区间 [new_start, new_cur) 逐个执行 destroy                                        |
   |     - 归还存储: AllocTraits::deallocate(alloc, new_start, new_capacity)                                |
   |     - 旧缓冲区完全未被破坏，向外重抛异常 (保持强异常安全)                                             |
   |                                                                                                       |
   |   分支 B: 全量迁移成功 (Transaction Committed)                                                        |
   |     - 析构旧元素: std::destroy(old_start, old_finish)                                                 |
   |     - 释放旧存储: AllocTraits::deallocate(alloc, old_start, old_capacity)                             |
   |     - 提交三指针: start_ = new_start; finish_ = new_cur; end_of_storage_ = new_start + new_cap;       |
   |                                                                                                       |
   +-------------------------------------------------------------------------------------------------------+

异常安全回滚的核心控制变量是动态推进的构造游标 ``new_cur``。由于尚未构造的内存区域不存在对象生命周期，对其执行析构属于严重未定义行为；因此回滚清理循环的边界必须严格限制在 ``[new_start, new_cur)``。

工业级 Mini-Allocator 与异常安全批量构造器完整实现
--------------------------------------------------

为将上述内存分配、``allocator_traits`` 代理中枢、类型改绑、有状态内存管理与异常安全事务回滚落实为完整的工程代码，本节给出一套完整的 C++17/20 工业级实现。

代码包含三个核心组件：

1. **``TrackingArenaAllocator<T>``**：带物理内存池指针与实时分配遥测的有状态分配器，支持对齐检查与类型改绑。
2. **``MiniAllocatorTraits<Alloc>``**：模拟标准库 ``std::allocator_traits`` 的完整萃取中枢，包含 SFINAE 缺省类型补齐与接口路由。
3. **``UninitializedMemoryEngine``**：带 RAII 自动事务回滚守卫的未初始化内存批量迁移与构造引擎。

.. code-block:: cpp

   #include <cstddef>
   #include <cstdlib>
   #include <iostream>
   #include <limits>
   #include <memory>
   #include <new>
   #include <stdexcept>
   #include <type_traits>
   #include <utility>

   namespace core_memory {

   // =========================================================================
   // 1. 物理 Arena 内存存储池 (用于支撑有状态分配器)
   // =========================================================================
   class MemoryArena {
   public:
       explicit MemoryArena(std::size_t capacity_bytes)
           : capacity_(capacity_bytes), used_bytes_(0), allocations_count_(0) {
           buffer_ = static_cast<std::byte*>(std::malloc(capacity_));
           if (!buffer_) {
               throw std::bad_alloc();
           }
       }

       ~MemoryArena() noexcept {
           std::free(buffer_);
       }

       MemoryArena(const MemoryArena&) = delete;
       MemoryArena& operator=(const MemoryArena&) = delete;

       void* allocate(std::size_t bytes, std::size_t alignment) {
           std::size_t current_addr = reinterpret_cast<std::size_t>(buffer_ + used_bytes_);
           std::size_t aligned_addr = (current_addr + alignment - 1) & ~(alignment - 1);
           std::size_t padding = aligned_addr - current_addr;

           if (used_bytes_ + padding + bytes > capacity_) {
               throw std::bad_alloc();
           }

           used_bytes_ += padding + bytes;
           ++allocations_count_;
           return reinterpret_cast<void*>(aligned_addr);
       }

       void deallocate(void* p, std::size_t bytes) noexcept {
           // Arena 采用整体回收策略，单次 deallocate 仅更新遥测计数
           if (allocations_count_ > 0) {
               --allocations_count_;
           }
       }

       [[nodiscard]] std::size_t used_bytes() const noexcept { return used_bytes_; }
       [[nodiscard]] std::size_t active_allocations() const noexcept { return allocations_count_; }

   private:
       std::byte*  buffer_;
       std::size_t capacity_;
       std::size_t used_bytes_;
       std::size_t allocations_count_;
   };

   // =========================================================================
   // 2. 有状态物理追踪分配器：TrackingArenaAllocator
   // =========================================================================
   template <typename T>
   class TrackingArenaAllocator {
   public:
       using value_type = T;

       explicit TrackingArenaAllocator(MemoryArena* arena = nullptr) noexcept
           : arena_(arena) {}

       template <typename U>
       TrackingArenaAllocator(const TrackingArenaAllocator<U>& other) noexcept
           : arena_(other.arena_) {}

       [[nodiscard]] T* allocate(std::size_t n) {
           if (n > std::numeric_limits<std::size_t>::max() / sizeof(T)) {
               throw std::bad_array_new_length();
           }
           std::size_t bytes = n * sizeof(T);
           if (arena_) {
               return static_cast<T*>(arena_->allocate(bytes, alignof(T)));
           }
           void* p = ::operator new(bytes, std::align_val_t{alignof(T)});
           return static_cast<T*>(p);
       }

       void deallocate(T* p, std::size_t n) noexcept {
           if (arena_) {
               arena_->deallocate(static_cast<void*>(p), n * sizeof(T));
               return;
           }
           ::operator delete(static_cast<void*>(p), std::align_val_t{alignof(T)});
       }

       // 显式定义传播标志 (有状态分配器)
       using propagate_on_container_copy_assignment = std::false_type;
       using propagate_on_container_move_assignment = std::true_type;
       using propagate_on_container_swap            = std::false_type;
       using is_always_equal                        = std::false_type;

       template <typename U>
       bool operator==(const TrackingArenaAllocator<U>& rhs) const noexcept {
           return arena_ == rhs.arena_;
       }

       template <typename U>
       bool operator!=(const TrackingArenaAllocator<U>& rhs) const noexcept {
           return arena_ != rhs.arena_;
       }

       template <typename> friend class TrackingArenaAllocator;

   private:
       MemoryArena* arena_;
   };

   // =========================================================================
   // 3. Mini Allocator Traits 代理中枢实现
   // =========================================================================
   template <typename Alloc>
   struct MiniAllocatorTraits {
       using allocator_type = Alloc;
       using value_type     = typename Alloc::value_type;
       using pointer        = value_type*;
       using const_pointer  = const value_type*;
       using size_type      = std::size_t;
       using difference_type = std::ptrdiff_t;

       // 自动 Rebind 改绑机制
       template <typename U>
       using rebind_alloc = TrackingArenaAllocator<U>;

       [[nodiscard]] static pointer allocate(Alloc& a, size_type n) {
           return a.allocate(n);
       }

       static void deallocate(Alloc& a, pointer p, size_type n) noexcept {
           a.deallocate(p, n);
       }

       template <typename T, typename... Args>
       static void construct(Alloc&, T* p, Args&&... args) {
           ::new (static_cast<void*>(p)) T(std::forward<Args>(args)...);
       }

       template <typename T>
       static void destroy(Alloc&, T* p) noexcept {
           p->~T();
       }
   };

   // =========================================================================
   // 4. 异常安全事务回滚守卫与未初始化内存算法引擎
   // =========================================================================
   template <typename Alloc, typename T>
   class UninitializedTransactionGuard {
   public:
       UninitializedTransactionGuard(Alloc& alloc, T* storage, std::size_t capacity) noexcept
           : alloc_(alloc), storage_(storage), capacity_(capacity), current_(storage), committed_(false) {}

       ~UninitializedTransactionGuard() noexcept {
           if (!committed_ && storage_) {
               // 事务未提交：对已构造的前缀严格执行逆序析构
               while (current_ > storage_) {
                   --current_;
                   MiniAllocatorTraits<Alloc>::destroy(alloc_, current_);
               }
               // 释放已申请的未初始化存储
               MiniAllocatorTraits<Alloc>::deallocate(alloc_, storage_, capacity_);
           }
       }

       void advance() noexcept {
           ++current_;
       }

       T* current() const noexcept {
           return current_;
       }

       void commit() noexcept {
           committed_ = true;
       }

   private:
       Alloc&      alloc_;
       T*          storage_;
       std::size_t capacity_;
       T*          current_;
       bool        committed_;
   };

   template <typename Alloc, typename InputIt, typename T>
   T* uninitialized_move_with_rollback(Alloc& alloc, InputIt first, InputIt last, std::size_t new_cap) {
       using Traits = MiniAllocatorTraits<Alloc>;
       T* new_storage = Traits::allocate(alloc, new_cap);

       UninitializedTransactionGuard<Alloc, T> guard(alloc, new_storage, new_cap);

       for (InputIt it = first; it != last; ++it) {
           Traits::construct(alloc, guard.current(), std::move_if_noexcept(*it));
           guard.advance();
       }

       guard.commit(); // 全部迁移成功，提交事务，解除析构与存储释放守卫
       return new_storage;
   }

   } // namespace core_memory
```

性能与汇编级特性分析：

1. **内联消除与零开销分派**：在现代编译器（GCC/Clang ``-O2`` / ``-O3``）下，``MiniAllocatorTraits::construct`` 内部的 Placement New 表达式直接退化为对目标结构体字段的原生写入指令（如 ``mov [rax], rdx``），Traits 代理层的间接包装被编译期全量内联剥离，无函数调用跳转开销。
2. **RAII 事务守卫的静态开销优化**：``UninitializedTransactionGuard`` 在编译后的代码中，正常提交路径仅执行简单的布尔变量设置操作 ``committed_ = true``。异常回滚路径则完全交由编译器生成的 Landing Pad（异常处理展开表）管理，确保正常执行路径（Happy Path）的指令缓存命中率与流水线执行效率达到最优。

小结与下章导读
--------------

本章系统解构了现代 C++ STL 内存分配器体系：从原始内存分配与对象生命周期的物理分离哲学，到 C++98、C++11、C++17 至 C++20 分配器接口契约的精简收敛；从 ``std::allocator_traits`` 代理中枢的关联类型推导、针对节点容器的 ``rebind_alloc`` 改绑机制，到容器拷贝、移动、交换中的四大传播策略矩阵（POCCA、POCMA、POCS、``is_always_equal``）；从未初始化内存操作算法与普通赋值算法的物理状态界限，到动态扩容过程中的异常安全事务回滚状态机；最终通过带物理 Arena 的追踪分配器与 RAII 回滚构造器，实现了底层内存管理机制的完整闭环。

掌握了基于模板的静态分配器与 traits 代理体系后，下一章我们将深入现代 C++17 的重大内存架构演进 —— **std::pmr 多态内存资源体系：std::pmr::memory_resource、单调内存池 (monotonic_buffer_resource) 与无锁分配器（``02_stl_core_mechanisms_and_allocators/03_polymorphic_memory_resources_pmr.rst``）**，剖析多态虚函数分发消除模板类型扩散的底层机制、单调缓冲区生命周期模型以及嵌套容器的 Uses-Allocator Construction 传播规范。
