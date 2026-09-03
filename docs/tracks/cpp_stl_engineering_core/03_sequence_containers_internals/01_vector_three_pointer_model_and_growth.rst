====================================================================================================
std::vector 连续内存动态数组：三指针状态模型、几何级扩容迁移、异常安全强保证与 vector<bool> 特化边界
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 2 模块（``02_stl_core_mechanisms_and_allocators``）中，我们系统解构了 STL 迭代器五层能力拓扑与 Traits 萃取机制、内存分配器的原始空间管理与对象生命周期解耦、PMR 多态内存资源池化、强异常安全事务回滚保证，以及半开区间 ``[first, last)`` 泛型算法正交架构。这些基础机制共同构成了 STL 容器运行的底层基石。从本章开始，我们将正式进入全书第 3 模块（``03_sequence_containers_internals``），深度剖析标准模板库中各类顺序容器的物理内存拓扑与工程实现细节。作为现代 C++ 中使用最为广泛、微架构亲和度最高的连续序列容器，``std::vector`` 在物理内存上维护了一段严格连续的元素存储空间，提供 $\mathcal{O}(1)$ 常数时间随机访问与尾部均摊常数时间追加。本章将深入剖析 ``std::vector`` 的三指针内部状态拓扑、1.5 倍与 2.0 倍几何级扩容动力学及历史内存重用方程、基于 ``std::move_if_noexcept`` 的强异常安全提交回滚状态机、精准的迭代器失效判定边界，以及 ``std::vector<bool>`` 位压缩特化所引入的代理引用（Proxy Reference）架构边界。

三指针状态模型与连续内存物理拓扑
--------------------------------

``std::vector`` 的物理实现建立在连续单向线性地址空间之上。工业级标准库（如 GCC libstdc++、LLVM libc++ 与 MSVC STL）均采用 **三指针状态模型（Three-Pointer Model）** 表达容器的内部布局。

三指针数据结构与内存二元切分
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 64 位寻址架构下，一个未包含自定义有状态分配器的 ``std::vector<T>`` 实例仅占用固定的 24 字节栈内存，其内部由三个原始指针构成：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                  std::vector<T> 24 字节栈布局与堆内存连续拓扑                |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 栈内存 (Stack Frame) : 24 Bytes ]                                       |
   |   +-----------------------+-----------------------+---------------------+   |
   |   |   _M_start (8B)       |   _M_finish (8B)      | _M_end_of_storage   |   |
   |   +-----------+-----------+-----------+-----------+----------+----------+   |
   |               |                       |                      |              |
   |               \-----------------\     |     /----------------/              |
   |                                 |     |     |                               |
   |   [ 堆内存 (Heap Allocation) : Capacity * sizeof(T) ]                       |
   |   +---------------+---------------+---------------+---------------------+   |
   |   |  Element[0]   |  Element[1]   |  Element[2]   | (Uninitialized Mem) |   |
   |   +---------------+---------------+---------------+---------------------+   |
   |   ^                               ^               ^                         |
   |   |                               |               |                         |
   |   _M_start                        _M_finish       _M_end_of_storage         |
   |                                                                             |
   |   |<------- size() (已构造对象区间) ------->|                               |
   |   |<-------------------- capacity() (已分配物理容量) ------------------->|   |
   |                                                                             |
   +-----------------------------------------------------------------------------+

三指针的具体物理语义定义如下：

1. **``_M_start``**（或 libc++ 中的 ``__begin_``）：指向当前已分配连续堆内存空间的起始字节地址，亦即容器首个有效元素 ``Element[0]`` 的物理存储位置。
2. **``_M_finish``**（或 libc++ 中的 ``__end_``）：指向当前已构造有效元素区间的尾后边界（Past-the-end）。区间 ``[_M_start, _M_finish)`` 内部的所有槽位均已完成对象构造函数的执行，处于合法生命周期内。
3. **``_M_end_of_storage``**（或 libc++ 中的 ``__end_cap_``）：指向当前已分配堆内存块的物理截止地址。区间 ``[_M_finish, _M_end_of_storage)`` 属于已通过分配器申请但尚未构造对象的原始未初始化内存（Uninitialized Memory）。

容器的核心状态查询接口直接映射至简单的指针算术运算，具有零运行时开销：

.. math::

   	ext{size}() = 	ext{\_M\_finish} - 	ext{\_M\_start}

.. math::

   	ext{capacity}() = 	ext{\_M\_end\_of\_storage} - 	ext{\_M\_start}

.. math::

   	ext{empty}() = (	ext{\_M\_start} == 	ext{\_M\_finish})

.. math::

   	ext{data}() = 	ext{\_M\_start}

连续内存特性与 C 接口零开销兼容
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

C++ 标准严格规定 ``std::vector``（除 ``vector<bool>`` 特化外）的元素必须在物理内存中紧凑且连续排列，满足：

.. math::

   \&v[i] == \&v[0] + i, \quad \forall i \in [0, 	ext{size}())

该物理不变性确保了 ``std::vector<T>`` 可以直接将底层首地址 ``v.data()`` 传递给接受原生 C 数组指针与长度的底层系统调用或硬件驱动接口（如 POSIX ``read/write``、OpenGL 缓冲区加载及高性能 BLAS 计算库），无需进行中间内存物化或格式转换。

空基类优化 (EBO) 与分配器内存压缩
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在引入泛型分配器模板参数 ``template <typename T, typename Allocator = std::allocator<T>>`` 后，若分配器属于无状态空类（如标准默认分配器 ``std::allocator<T>``，其 ``sizeof(Allocator) == 1`` 字节），直接将其作为普通成员变量会导致 ``std::vector`` 因内存对齐膨胀至 32 字节。

标准库实现广泛利用 **空基类优化（Empty Base Optimization, EBO）** 或 C++20 ``[[no_unique_address]]`` 特性，将分配器作为内部向量数据结构的基类进行继承（如 GCC libstdc++ 的 ``_Vector_base::_Vector_impl``），使无状态分配器不占用独立物理字节，确保容器在 64 位系统下严格维持 24 字节的极简栈空间占用。

几何级扩容动力学与内存重分配开销
--------------------------------

当向 ``std::vector`` 追加新元素（执行 ``push_back`` 或 ``emplace_back``）且当前处于满载状态（即 ``_M_finish == _M_end_of_storage``）时，容器必须触发物理内存重分配（Reallocation）。扩容算法的设计直接决定了容器操作的时间复杂度与系统内存碎片率。

算术级扩容与几何级扩容的平摊复杂度证明
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **算术级扩容（固定增量 $C$）**：
   若每次满载时仅分配额外固定大小 $C$ 的内存空间。向初始为空的容器连续追加 $N$ 个元素，将触发 $\frac{N}{C}$ 次内存重分配。第 $k$ 次重分配需拷贝 $k 	imes C$ 个旧元素。总元素拷贝次数为：

   .. math::

      T_{	ext{arithmetic}}(N) = \sum_{k=1}^{N/C} (k \cdot C) = C \cdot \frac{(1 + N/C)(N/C)}{2} = \mathcal{O}(N^2)

   单次追加操作的平摊时间复杂度退化为 $\mathcal{O}(N)$，在高频写入场景下引发严重的性能停顿。

2. **几何级扩容（乘法因子 $k > 1$）**：
   若每次满载时分配当前容量的 $k$ 倍空间（即 $	ext{NewCap} = k 	imes 	ext{OldCap}$）。向容器连续追加 $N$ 个元素，重分配次数为 $M = \lceil \log_k N \rceil$。总元素拷贝次数满足等比数列求和：

   .. math::

      T_{	ext{geometric}}(N) = \sum_{j=0}^{M-1} k^j = \frac{k^M - 1}{k - 1} \approx \frac{N}{k - 1} = \mathcal{O}(N)

   单次追加操作的平摊时间复杂度（Amortized Time Complexity）收敛为严格的 $\mathcal{O}(1)$：

   .. math::

      	ext{Amortized Cost} = \frac{T_{	ext{geometric}}(N)}{N} \approx \frac{1}{k - 1} = \mathcal{O}(1)

扩容因子权衡：2.0 倍 (GCC/Clang) vs 1.5 倍 (MSVC)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

各主流 C++ 标准库实现对扩容因子 $k$ 的选取存在不同的工程哲学：

.. list-table:: 扩容因子微架构与内存分配特性对比
   :widths: 18 25 25 32
   :header-rows: 1
   :class: tight-table

   * - 评价维度
     - GCC libstdc++ / LLVM libc++
     - MSVC STL / Facebook folly
     - 底层物理机理分析
   * - 扩容系数 $k$
     - $k = 2.0$（翻倍扩容）
     - $k = 1.5$（MSVC）/ $k = 1.5 \sim 1.6$
     - 扩容增速与重分配频率的权衡
   * - 重分配次数
     - 极低（$\log_2 N$ 步）
     - 略高（$\log_{1.5} N \approx 1.7 \log_2 N$）
     - 2.0 倍减少了系统调用与内存申请频率
   * - 内存峰值浪费
     - 最高可达 $50\%$
     - 最高约为 $33.3\%$
     - 1.5 倍显著降低了未初始化内存的冗余预留
   * - 历史内存块重用性
     - 无法重用此前释放的所有旧内存块
     - 可在后续重分配中复用连续旧内存碎片
     - 取决于历史内存累加和与新申请容量的几何关系

历史内存重用（Memory Reuse）的数学几何证明
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当底层堆内存管理器（如 ptmalloc、jemalloc）采用连续内存地址分配策略时，容器重分配会释放旧内存块。新申请的内存空间大小若小于或等于历史释放内存块的总和，内存分配器即可在原地址后续空间直接复用旧内存碎片，显著提升 CPU L1/L2 数据缓存命中率并遏制虚拟内存碎片。

设初始容量为 $C_0$。第 $n$ 次扩容申请的容量为 $C_n = C_0 \cdot k^n$。前 $n-1$ 次扩容所释放的内存总和为：

.. math::

   S_{n-1} = \sum_{j=0}^{n-1} C_j = C_0 \sum_{j=0}^{n-1} k^j = C_0 \frac{k^n - 1}{k - 1}

为了使第 $n$ 次申请的内存 $C_n$ 能够复用历史释放的所有内存空间，必须满足不等式：

.. math::

   C_n \le S_{n-1} \implies C_0 \cdot k^n \le C_0 \frac{k^n - 1}{k - 1}

忽略常数项 $-1$，两边同除以 $C_0 \cdot k^n$ 可得：

.. math::

   1 \le \frac{1}{k - 1} \implies k - 1 \le 1 \implies k \le 2

若考虑第 $n-1$ 次旧内存块在重分配瞬间仍被占用（尚未释放，必须在数据迁移完成后方可释放），则实际可复用的历史内存为前 $n-2$ 次释放的块：

.. math::

   C_n \le S_{n-2} \implies k^n \le \frac{k^{n-1} - 1}{k - 1} \implies k^2 - k - 1 \le 0 \implies k \le \frac{1 + \sqrt{5}}{2} \approx 1.618

当扩容因子 $k = 2.0$ 时，$C_n > S_{n-1}$ 恒成立，新内存申请量永远严格大于此前释放的所有内存之和，导致分配器必须持续向高地址寻找全新的内存空洞；而当 $k = 1.5$ 时，从第 3 次扩容开始，$C_n \le S_{n-2}$ 条件逐步得到满足，使得长期运行的进程能够有效利用内存碎片。

强异常安全保证与 move_if_noexcept 迁移策略
------------------------------------------

在动态扩容或在容器中部插入元素时，``std::vector`` 必须向调用者提供 **强异常安全保证（Strong Exception Safety Guarantee）**：若操作过程中抛出异常，容器的状态必须保持完全回滚至操作触发前的初始状态，杜绝元素丢失、重复析构或内存泄漏。

事务性扩容迁移三步曲
~~~~~~~~~~~~~~~~~~~~

``std::vector`` 内部通过严格的事务性分步控制实现状态回滚：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                  std::vector 扩容迁移与强异常安全回滚状态机                  |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 步骤 1: 独立申请全新内存块 ]                                            |
   |      new_storage = Alloc::allocate(new_capacity)                            |
   |      * 若抛出 std::bad_alloc，原 vector 内部指针完全未变，强保证成立        |
   |            |                                                                |
   |            v                                                                |
   |   [ 步骤 2: 条件式元素迁移与新元素构造 ]                                    |
   |      * 在新内存块中使用 std::move_if_noexcept 批量构造新对象                |
   |      * 若某一元素构造函数抛出异常:                                          |
   |        1. 逆序析构已在新内存中构造的部分新对象                              |
   |        2. 释放 new_storage 内存块                                           |
   |        3. 原 vector 中对象未被破坏（因采用只读拷贝），强保证成立            |
   |            |                                                                |
   |            v                                                                |
   |   [ 步骤 3: 事务原子提交与旧内存销毁 ]                                      |
   |      * 析构原内存中的所有旧元素: std::_Destroy(_M_start, _M_finish)         |
   |      * 释放原内存块: Alloc::deallocate(_M_start, _M_end_of_storage-_M_start)|
   |      * 原子重定向指针:                                                      |
   |        _M_start = new_start;                                                |
   |        _M_finish = new_finish;                                              |
   |        _M_end_of_storage = new_end_of_storage;                              |
   |                                                                             |
   +-----------------------------------------------------------------------------+

std::move_if_noexcept 的编译期条件分发机理
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在步骤 2 中，若元素类型 $T$ 的移动构造函数未声明为 ``noexcept``（即可能在移动过程中抛出异常），使用移动语义将导致原内存中的源对象处于被修改或部分转移的未知状态（Moved-from State）。一旦后续对象的构造抛出异常，容器将无法恢复已被破坏的旧元素。

为了在极致移动性能与强异常安全之间取得严格平衡，标准库引入了 ``std::move_if_noexcept``：

.. code-block:: cpp

   template <typename T>
   constexpr std::conditional_t<
       !std::is_nothrow_move_constructible_v<T> && std::is_copy_constructible_v<T>,
       const T&,
       T&&
   > move_if_noexcept(T& x) noexcept {
       return std::move(x);
   }

1. 若 $T$ 显式标记了 ``noexcept`` 移动构造函数（``std::is_nothrow_move_constructible_v<T> == true``），或者 $T$ 不可拷贝，函数返回右值引用 ``T&&``，触发高效的就地资源所有权转移（如内部指针窃取），零拷贝开销。
2. 若 $T$ 的移动构造函数可能抛出异常且 $T$ 支持拷贝构造，函数主动降级为返回常量左值引用 ``const T&``，强制触发深拷贝构造。即使拷贝抛出异常，原容器中的对象依然完好无损，使异常回滚得以平稳完成。

迭代器失效（Iterator Invalidation）拓扑边界
--------------------------------------------

``std::vector`` 内部存储的物理连续性导致其在进行插入、删除或扩容操作时，既有迭代器、指针与引用的有效性呈现严格的拓扑分界。

.. list-table:: std::vector 变易操作对迭代器与引用的失效规则
   :widths: 22 28 50
   :header-rows: 1
   :class: tight-table

   * - 容器操作类型
     - 物理容量前置状态
     - 迭代器、指针与引用失效范围
   * - ``push_back`` / ``emplace_back``
     - ``size() < capacity()``（未扩容）
     - 仅尾后迭代器（``end()``）失效；所有指向既有元素的迭代器/引用依然有效
   * - ``push_back`` / ``emplace_back``
     - ``size() == capacity()``（触发扩容）
     - **全量失效**：底层堆地址整体迁移，所有迭代器、指针和引用全部失效
   * - ``insert(pos, val)``
     - ``size() < capacity()``（未扩容）
     - ``pos`` 及其之后的所有迭代器/引用失效；``pos`` 之前的迭代器/引用依然有效
   * - ``insert(pos, val)``
     - ``size() == capacity()``（触发扩容）
     - **全量失效**：所有迭代器、指针和引用全部失效
   * - ``erase(pos)``
     - 不涉及内存释放
     - ``pos`` 及其之后的所有迭代器/引用失效（含 ``end()``）；``pos`` 之前依然有效
   * - ``clear()``
     - 仅析构对象，不释放物理容量
     - 指向容器元素的所有迭代器、指针与引用全部失效；物理容量 ``capacity()`` 保持不变
   * - ``reserve(new_cap)``
     - ``new_cap > capacity()``
     - **全量失效**：底层存储强制重分配
   * - ``shrink_to_fit()``
     - ``size() < capacity()``
     - 若实际发生了缩容重分配，则所有迭代器、指针和引用全部失效

std::vector<bool> 特化机制与代理引用边界
----------------------------------------

C++98 标准中引入了针对布尔类型的完全特化版本 ``std::vector<bool>``。该特化旨在通过位压缩（Bit-packing）节省物理内存空间，但在面向通用容器概念时引入了深刻的类型系统间隙。

位压缩物理拓扑与代理引用设计
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

标准要求 ``std::vector<bool>`` 将每个布尔值压缩为单一比特（1 bit）进行存储。在底层实现中，容器以字长单元（如 ``uint64_t`` 或 ``unsigned long``）为基本分配单元，一个 64 位整数容纳 64 个连续布尔元素。

由于现代 CPU 体系结构不支持对小于 1 字节（8 bits）的单一比特位进行直接内存寻址（不存在 ``bool*`` 指向某个 bit 的物理硬件机制），``std::vector<bool>`` 无法满足标准连续容器中 ``value_type& reference`` 的基本契约。

为了支持类似于数组的读写语法，标准库引入了 **代理引用类（Proxy Reference）**：

.. code-block:: cpp

   // 标准库 std::vector<bool> 内部代理引用模型示意
   template <typename Allocator>
   class vector<bool, Allocator> {
   public:
       class reference {
           uint64_t* _M_word; // 指向存储该 bit 的 64 位整数字段
           uint64_t  _M_mask; // 用于屏蔽其他 bit 的掩码 (1ULL << offset)
       public:
           reference(uint64_t* w, uint64_t m) : _M_word(w), _M_mask(m) {}

           // 隐式转换为 bool 用于读取
           operator bool() const noexcept {
               return (*_M_word & _M_mask) != 0;
           }

           // 重载赋值运算符用于按位写入
           reference& operator=(bool val) noexcept {
               if (val) *_M_word |= _M_mask;
               else     *_M_word &= ~_M_mask;
               return *this;
           }

           reference& operator=(const reference& other) noexcept {
               return *this = static_cast<bool>(other);
           }
       };

       reference operator[](size_type n) {
           return reference(_M_start + n / 64, 1ULL << (n % 64));
       }
   };

类型推导陷阱与接口断裂边界
~~~~~~~~~~~~~~~~~~~~~~~~~~

代理引用模型的存在使得 ``std::vector<bool>`` 呈现出偏离常规容器的行为：

1. **``auto&`` 编译硬性失败**：
   表达式 ``auto& bit = v[0];`` 试图将一个非 const 左值引用绑定至临时生成的代理对象 ``vector<bool>::reference``，直接触发编译器类型匹配错误。
2. **``auto`` 悬垂引用隐式陷阱**：
   在 C++11 中，代码 ``auto bit = v[0];`` 推导出的类型是 ``std::vector<bool>::reference`` 而非 ``bool``。若原容器 ``v`` 后续发生析构或扩容，该代理对象内部持有的原始指针 ``_M_word`` 将成为悬垂指针（Dangling Pointer），后续对 ``bit`` 的读写将导致未定义行为（UB）。正确写法必须显式声明类型：``bool bit = v[0];``。
3. **缺少连续内存首地址接口**：
   ``std::vector<bool>`` 不提供返回 ``bool*`` 的 ``data()`` 成员函数，无法直接对接原生 C API。
4. **多线程并发写入数据竞争（Data Race）**：
   当两个独立线程分别并发修改同一个字节内的不同 bit（例如线程 A 写入 ``v[0]``，线程 B 写入 ``v[1]``）时，由于底层操作涉及对同一个 64 位整数的读-改-写（Read-Modify-Write）周期，将引发非线程安全的数据竞争破坏。

.. list-table:: 替代方案选型指南
   :widths: 25 35 40
   :header-rows: 1
   :class: tight-table

   * - 替代方案
     - 适用场景与核心特性
     - 相比 vector<bool> 的优势
   * - ``std::vector<uint8_t>`` / ``std::vector<char>``
     - 需要标准动态数组语义、原生字节对齐与 C 接口互操作
     - 每个元素占用 1 字节，支持真正的 ``uint8_t&`` 引用与 ``data()`` 指针
   * - ``std::bitset<N>``
     - 编译期已知固定位宽的高性能位掩码运算
     - 栈上紧凑分配，支持超快速位运算（AND/OR/XOR/Shift）与硬件指令加速（POPCNT）
   * - ``boost::dynamic_bitset``
     - 运行期动态位宽的纯位图集合处理
     - 专为位图设计的完备数学集合接口，明确暴露位图语义而非伪装成标准序列容器

工业级 C++ 完整 Mini-Vector 内核实现
------------------------------------

以下 C++ 源码实现了一个工业级自包含的 ``MiniVector<T>`` 动态数组模板。该实现涵盖：
1. 严格的三指针内存状态模型与内存对齐布局。
2. 1.5 倍几何级扩容算法与内存重分配事务控制。
3. 基于 ``std::move_if_noexcept`` 与 ``noexcept`` 检测的强异常安全回滚机制。
4. 包含移动语义、就地构造（``emplace_back``）、随机访问迭代器与析构安全保障。
5. 完备的测试验证套件（覆盖几何扩容、移动迁移统计、强异常回滚与迭代器有效性）。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <memory>
   #include <utility>
   #include <cstddef>
   #include <cassert>
   #include <stdexcept>
   #include <type_traits>
   #include <initializer_list>

   namespace core_stl {

   template <typename T, typename Allocator = std::allocator<T>>
   class MiniVector {
   public:
       using value_type      = T;
       using allocator_type  = Allocator;
       using size_type       = std::size_t;
       using difference_type = std::ptrdiff_t;
       using reference       = value_type&;
       using const_reference = const value_type&;
       using pointer         = typename std::allocator_traits<Allocator>::pointer;
       using const_pointer   = typename std::allocator_traits<Allocator>::const_pointer;
       using iterator        = pointer;
       using const_iterator  = const_pointer;

   private:
       using AllocTraits = std::allocator_traits<Allocator>;

       // 三指针状态模型
       pointer _M_start           = nullptr;
       pointer _M_finish          = nullptr;
       pointer _M_end_of_storage  = nullptr;
       Allocator _M_alloc;

   public:
       // =====================================================================
       // 构造与析构体系
       // =====================================================================
       MiniVector() noexcept(noexcept(Allocator())) : _M_alloc(Allocator()) {}

       explicit MiniVector(const Allocator& alloc) noexcept : _M_alloc(alloc) {}

       explicit MiniVector(size_type count, const Allocator& alloc = Allocator())
           : _M_alloc(alloc) {
           if (count > 0) {
               _M_start = AllocTraits::allocate(_M_alloc, count);
               _M_finish = _M_start;
               _M_end_of_storage = _M_start + count;
               
               // 默认值构造
               for (; _M_finish != _M_end_of_storage; ++_M_finish) {
                   AllocTraits::construct(_M_alloc, _M_finish);
               }
           }
       }

       MiniVector(std::initializer_list<T> init, const Allocator& alloc = Allocator())
           : _M_alloc(alloc) {
           reserve(init.size());
           for (const auto& item : init) {
               push_back(item);
           }
       }

       ~MiniVector() {
           clear_and_deallocate();
       }

       // 拷贝构造函数 (强异常安全)
       MiniVector(const MiniVector& other)
           : _M_alloc(AllocTraits::select_on_container_copy_construction(other._M_alloc)) {
           size_type n = other.size();
           if (n > 0) {
               _M_start = AllocTraits::allocate(_M_alloc, n);
               _M_finish = _M_start;
               _M_end_of_storage = _M_start + n;

               try {
                   for (pointer p = other._M_start; p != other._M_finish; ++p, ++_M_finish) {
                       AllocTraits::construct(_M_alloc, _M_finish, *p);
                   }
               } catch (...) {
                   clear_and_deallocate();
                   throw;
               }
           }
       }

       // 移动构造函数 (保证 noexcept 窃取所有权)
       MiniVector(MiniVector&& other) noexcept
           : _M_start(other._M_start),
             _M_finish(other._M_finish),
             _M_end_of_storage(other._M_end_of_storage),
             _M_alloc(std::move(other._M_alloc)) {
           other._M_start = nullptr;
           other._M_finish = nullptr;
           other._M_end_of_storage = nullptr;
       }

       // 拷贝赋值重载 (Copy-and-Swap 强保证)
       MiniVector& operator=(const MiniVector& other) {
           if (this != &other) {
               MiniVector temp(other);
               swap(temp);
           }
           return *this;
       }

       // 移动赋值重载
       MiniVector& operator=(MiniVector&& other) noexcept {
           if (this != &other) {
               clear_and_deallocate();
               _M_start = other._M_start;
               _M_finish = other._M_finish;
               _M_end_of_storage = other._M_end_of_storage;
               _M_alloc = std::move(other._M_alloc);

               other._M_start = nullptr;
               other._M_finish = nullptr;
               other._M_end_of_storage = nullptr;
           }
           return *this;
       }

       // =====================================================================
       // 基础容量与元素访问
       // =====================================================================
       size_type size() const noexcept {
           return static_cast<size_type>(_M_finish - _M_start);
       }

       size_type capacity() const noexcept {
           return static_cast<size_type>(_M_end_of_storage - _M_start);
       }

       bool empty() const noexcept {
           return _M_start == _M_finish;
       }

       pointer data() noexcept { return _M_start; }
       const_pointer data() const noexcept { return _M_start; }

       reference operator[](size_type index) noexcept {
           assert(index < size() && "Index out of bounds");
           return _M_start[index];
       }

       const_reference operator[](size_type index) const noexcept {
           assert(index < size() && "Index out of bounds");
           return _M_start[index];
       }

       reference at(size_type index) {
           if (index >= size()) {
               throw std::out_of_range("MiniVector::at: index out of range");
           }
           return _M_start[index];
       }

       iterator begin() noexcept { return _M_start; }
       iterator end() noexcept { return _M_finish; }
       const_iterator begin() const noexcept { return _M_start; }
       const_iterator end() const noexcept { return _M_finish; }

       // =====================================================================
       // 核心扩容与变易操作
       // =====================================================================
       void reserve(size_type new_capacity) {
           if (new_capacity > capacity()) {
               reallocate_and_migrate(new_capacity);
           }
       }

       void push_back(const T& value) {
           emplace_back(value);
       }

       void push_back(T&& value) {
           emplace_back(std::move(value));
       }

       template <typename... Args>
       reference emplace_back(Args&&... args) {
           if (_M_finish == _M_end_of_storage) {
               // 1.5 倍几何级扩容策略 (MSVC 风格, 初始为 1)
               size_type old_cap = capacity();
               size_type new_cap = old_cap == 0 ? 1 : old_cap + (old_cap >> 1);
               if (new_cap <= old_cap) { // 整数溢出保护
                   new_cap = old_cap + 1;
               }
               reallocate_and_migrate(new_cap);
           }

           AllocTraits::construct(_M_alloc, _M_finish, std::forward<Args>(args)...);
           reference ref = *_M_finish;
           ++_M_finish;
           return ref;
       }

       void pop_back() noexcept {
           assert(!empty() && "Cannot pop from empty vector");
           --_M_finish;
           AllocTraits::destroy(_M_alloc, _M_finish);
       }

       void clear() noexcept {
           destroy_elements(_M_start, _M_finish);
           _M_finish = _M_start;
       }

       void swap(MiniVector& other) noexcept {
           std::swap(_M_start, other._M_start);
           std::swap(_M_finish, other._M_finish);
           std::swap(_M_end_of_storage, other._M_end_of_storage);
           std::swap(_M_alloc, other._M_alloc);
       }

   private:
       void destroy_elements(pointer first, pointer last) noexcept {
           for (; first != last; ++first) {
               AllocTraits::destroy(_M_alloc, first);
           }
       }

       void clear_and_deallocate() noexcept {
           if (_M_start) {
               destroy_elements(_M_start, _M_finish);
               AllocTraits::deallocate(_M_alloc, _M_start, capacity());
               _M_start = nullptr;
               _M_finish = nullptr;
               _M_end_of_storage = nullptr;
           }
       }

       // 强异常安全核心: 事务性重分配与迁移
       void reallocate_and_migrate(size_type new_capacity) {
           assert(new_capacity > size());

           // 1. 申请独立新内存块 (若抛出 std::bad_alloc，原状态完全不受影响)
           pointer new_start = AllocTraits::allocate(_M_alloc, new_capacity);
           pointer new_finish = new_start;
           pointer new_end_of_storage = new_start + new_capacity;

           // 2. 将旧元素迁移至新空间 (结合 move_if_noexcept)
           try {
               for (pointer p = _M_start; p != _M_finish; ++p, ++new_finish) {
                   if constexpr (std::is_nothrow_move_constructible_v<T> || !std::is_copy_constructible_v<T>) {
                       AllocTraits::construct(_M_alloc, new_finish, std::move(*p));
                   } else {
                       AllocTraits::construct(_M_alloc, new_finish, *p); // 降级为只读拷贝以保强异常安全
                   }
               }
           } catch (...) {
               // 回滚事务: 逆序销毁已构造的新对象并释放新内存
               destroy_elements(new_start, new_finish);
               AllocTraits::deallocate(_M_alloc, new_start, new_capacity);
               throw; // 重新抛出异常，原 vector 毫发无损
           }

           // 3. 提交事务: 销毁旧对象并切换内部指针
           destroy_elements(_M_start, _M_finish);
           if (_M_start) {
               AllocTraits::deallocate(_M_alloc, _M_start, capacity());
           }

           _M_start = new_start;
           _M_finish = new_finish;
           _M_end_of_storage = new_end_of_storage;
       }
   };

   } // namespace core_stl

   // =========================================================================
   // 端到端测试套件与异常安全验证
   // =========================================================================
   namespace test {

   struct TrackedItem {
       static inline int move_count = 0;
       static inline int copy_count = 0;
       static inline int destruct_count = 0;

       int id;
       explicit TrackedItem(int val = 0) : id(val) {}

       TrackedItem(const TrackedItem& other) : id(other.id) {
           ++copy_count;
       }

       TrackedItem(TrackedItem&& other) noexcept : id(other.id) {
           other.id = -1;
           ++move_count;
       }

       ~TrackedItem() {
           ++destruct_count;
       }

       static void reset_stats() {
           move_count = 0;
           copy_count = 0;
           destruct_count = 0;
       }
   };

   // 模拟可能在第 N 次拷贝/移动时抛出异常的结构体
   struct ThrowingItem {
       static inline int construct_attempts = 0;
       static inline int throw_after_attempts = -1;

       int value;
       explicit ThrowingItem(int v = 0) : value(v) {}

       ThrowingItem(const ThrowingItem& other) : value(other.value) {
           ++construct_attempts;
           if (throw_after_attempts > 0 && construct_attempts >= throw_after_attempts) {
               throw std::runtime_error("Simulated Copy Construction Failure");
           }
       }

       // 未标 noexcept 的移动构造函数 (促使 vector 降级使用拷贝)
       ThrowingItem(ThrowingItem&& other) noexcept(false) : value(other.value) {
           ++construct_attempts;
           if (throw_after_attempts > 0 && construct_attempts >= throw_after_attempts) {
               throw std::runtime_error("Simulated Move Construction Failure");
           }
       }
   };

   inline void runVectorTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " MiniVector 物理拓扑、几何扩容与强异常安全测试套件
";
       std::cout << "=======================================================

";

       // 1. 测试基础三指针状态与 1.5 倍几何扩容
       {
           core_stl::MiniVector<int> vec;
           assert(vec.size() == 0 && vec.capacity() == 0 && vec.empty());

           std::cout << "[测试 1: 1.5 倍几何级扩容轨迹]
";
           size_t last_cap = 0;
           for (int i = 0; i < 20; ++i) {
               vec.push_back(i);
               if (vec.capacity() != last_cap) {
                   last_cap = vec.capacity();
                   std::cout << "  元素数量 size: " << vec.size()
                             << ", 当前容量 capacity: " << vec.capacity() << "
";
               }
           }
           assert(vec.size() == 20);
           for (size_t i = 0; i < vec.size(); ++i) {
               assert(vec[i] == static_cast<int>(i));
           }
           std::cout << "  -> 几何扩容与连续索引访问验证通过。

";
       }

       // 2. 测试 noexcept 移动构造函数的零拷贝优先迁移
       {
           std::cout << "[测试 2: nothrow 移动构造函数在扩容中的优先调度]
";
           TrackedItem::reset_stats();
           core_stl::MiniVector<TrackedItem> vec;
           vec.reserve(2);

           vec.emplace_back(101);
           vec.emplace_back(102);
           assert(TrackedItem::copy_count == 0 && TrackedItem::move_count == 0);

           // 触发扩容迁移
           vec.emplace_back(103);
           std::cout << "  扩容迁移执行完成: copy_count = " << TrackedItem::copy_count
                     << ", move_count = " << TrackedItem::move_count << "
";
           assert(TrackedItem::copy_count == 0);
           assert(TrackedItem::move_count == 2); // 成功通过 std::move 迁移旧对象
           std::cout << "  -> nothrow 移动优先判定机制验证通过。

";
       }

       // 3. 测试强异常安全回滚机制
       {
           std::cout << "[测试 3: 扩容中途异常触发与容器状态事务回滚]
";
           ThrowingItem::construct_attempts = 0;
           ThrowingItem::throw_after_attempts = -1;

           core_stl::MiniVector<ThrowingItem> vec;
           vec.reserve(4);
           vec.push_back(ThrowingItem(1));
           vec.push_back(ThrowingItem(2));
           vec.push_back(ThrowingItem(3));
           vec.push_back(ThrowingItem(4));

           assert(vec.size() == 4 && vec.capacity() == 4);

           // 设置在第 2 次迁移构造时抛出异常
           ThrowingItem::construct_attempts = 0;
           ThrowingItem::throw_after_attempts = 2;

           bool exception_caught = false;
           try {
               // 触发扩容重分配
               vec.push_back(ThrowingItem(5));
           } catch (const std::exception& e) {
               exception_caught = true;
               std::cout << "  [预期内捕获异常]: " << e.what() << "
";
           }

           assert(exception_caught);
           // 验证原 vector 状态保持事务一致性
           assert(vec.size() == 4);
           assert(vec.capacity() == 4);
           assert(vec[0].value == 1 && vec[1].value == 2 && vec[2].value == 3 && vec[3].value == 4);
           std::cout << "  -> 异常后 vector 原内存与元素完全无损，强异常安全保证成立。

";
       }
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰地印证了 ``std::vector`` 的核心微架构机制：

1. **几何级容量阶梯跃迁**：容量从 $0 	o 1 	o 2 	o 3 	o 4 	o 6 	o 9 	o 13 	o 19 	o 28$，严格遵循 $C_{n+1} = \lfloor C_n 	imes 1.5 \rfloor$ 的递推动力学，在均摊常数时间开销与内存冗余度之间达成了平衡。
2. **移动构造函数的无条件特化**：当包含 ``noexcept`` 移动构造函数时，扩容过程中的旧元素拷贝计数维持在 0，迁移操作全部由移动构造接管，避免了昂贵的深拷贝。
3. **强异常安全事务回滚**：当元素因缺少 ``noexcept`` 声明而降级为拷贝构造并在扩容中途抛出异常时，事务状态机精准截获异常、析构新分配的部分对象并释放新内存，使原向量在元素内容与容量指针上均保持与抛出前完全一致的状态。

小结与下章导读
--------------

本章系统解构了现代 C++ 最核心的连续顺序容器 ``std::vector`` 的物理拓扑与运行机制：

1. **三指针状态模型**：剖析了 ``_M_start``、``_M_finish`` 与 ``_M_end_of_storage`` 在 64 位系统下的 24 字节极简栈布局及其对 C 数组的原生零开销互操作支持。
2. **几何级扩容动力学**：通过数学推导证明了几何扩容的均摊 $\mathcal{O}(1)$ 复杂度，对比了 2.0 倍（GCC）与 1.5 倍（MSVC）在内存碎片与历史内存空间复用（$k \le 1.618$）层面的物理权衡。
3. **强异常安全保证**：阐明了独立内存申请、基于 ``std::move_if_noexcept`` 的条件式迁移以及原子提交回滚构成的事务状态机。
4. **vector<bool> 特化边界**：揭示了单比特位压缩带来的代理引用（Proxy Reference）机制，以及其在 ``auto&`` 编译失败、悬垂引用与多线程竞争中的架构局限。

在掌握了动态连续数组的内存管理后，下一章我们将转向其静态对偶容器。在第 3 模块第 2 节 **std::array 固定大小连续内存：聚合初始化、零运行时开销、constexpr 编译期支持与原生数组退化边界（``03_sequence_containers_internals/02_array_fixed_capacity_and_constexpr.rst``）** 中，我们将深入剖析原生数组的面向对象安全包装、结构化绑定（Structured Binding）支持、编译期常量求值以及值语义传递对原生指针退化缺陷的彻底克服。
