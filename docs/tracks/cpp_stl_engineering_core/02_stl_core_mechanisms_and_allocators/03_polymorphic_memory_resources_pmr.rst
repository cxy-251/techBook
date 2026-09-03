==================================================================================================================================
std::pmr 多态内存资源：std::pmr::memory_resource、单调内存池 (monotonic_buffer_resource) 与池化分配器
==================================================================================================================================

.. note:: 前置背景与上下文承接
   在第二模块前两章《迭代器核心体系与能力分层》与《内存分配器体系：allocator 接口契约、allocator_traits 统一抽象、未初始化内存批量构造算法》中，系统建立了 STL 的游标拓扑、抽象代理中枢以及未初始化内存上的生命周期四阶段状态机。然而，C++98 至 C++14 的经典分配器模型将内存分配策略直接编码为容器模板类型的核心参数（例如 ``std::vector<T, AllocA>`` 与 ``std::vector<T, AllocB>`` 属于完全不同的具现化类型）。这种静态参数化设计导致了函数接口签名泛滥、跨模块二进制接口（ABI）割裂以及代码体积膨胀。C++17 正式引入多态内存资源体系（Polymorphic Memory Resources, PMR），将内存分配策略的定制点从编译期模板类型转移至运行时虚表分发机制。本章深入剖析 ``std::pmr`` 架构体系：解构 ``std::pmr::memory_resource`` 抽象基类的物理虚表拓扑与 NVI 设计模式；分析全局与链式上游委托内存资源；解密基于栈上固定缓冲与 Bump Pointer 快速推进的单调内存池（``monotonic_buffer_resource``）；探究大小分箱（Size-Class Bins）池化资源（``unsynchronized_pool_resource`` / ``synchronized_pool_resource``）的高并发无锁与分流机制；阐明 Uses-Allocator Construction 在多层嵌套容器中的资源穿透传播模型，最终通过高吞吐请求处理管道与带观测遥测的自定义内存资源完成工业级落地。

PMR 架构起源与运行时多态内存解耦
--------------------------------

在传统 STL 架构中，分配器是容器类模板的形参之一：

.. code-block:: cpp

   template <typename T, typename Allocator = std::allocator<T>>
   class vector;

这种设计在带来静态单态化与内联优化的同时，对大型工程系统的模块化架构构成了物理约束：

1. **类型传染与接口膨胀（Type Infection）**：若底层网络模块定义了专用内存池分配器 ``PoolAlloc<Packet>``，则其产出的容器类型为 ``std::vector<Packet, PoolAlloc<Packet>>``。当该容器需要传递给上层业务处理函数时，业务函数的形参必须声明为完全匹配的模板类型或写成函数模板。函数模板的引入导致业务层头文件必须包含底层分配器的具体定义，引发物理编译依赖倒置。
2. **二进制接口（ABI）割裂**：动态链接库（Dynamic Shared Library, ``.so`` / ``.dylib`` / ``.dll``）导出的 C++ 接口若包含标准容器，必须锁定分配器类型。如果外部调用者使用不同的分配策略，两者无法直接传递容器对象，强制依赖深拷贝转换。
3. **异构内存池在运行时的动态切换受限**：同一数据结构在不同运行阶段（例如解析阶段使用栈上瞬态内存，归档阶段转移至持久堆内存）无法共用同一容器实例变量。

C++17 ``std::pmr`` 体系通过引入抽象基类 ``std::pmr::memory_resource`` 与统一包装器 ``std::pmr::polymorphic_allocator<T>``，将物理内存的申请与归还动作收敛为运行时指针分发。

.. code-block:: text

   +-------------------------------------------------------------------------------------------------------+
   |                             经典 Allocator 与 PMR 多态内存资源物理拓扑对比                            |
   +-------------------------------------------------------------------------------------------------------+
   |                                                                                                       |
   |   [ 经典模板 Allocator 拓扑: 编译期类型绑定 ]                                                         |
   |                                                                                                       |
   |     std::vector<int, AllocatorA>  ----> 静态绑定 AllocatorA 实例 (编译期具现化类型 1)                 |
   |     std::vector<int, AllocatorB>  ----> 静态绑定 AllocatorB 实例 (编译期具现化类型 2, 两者类型不兼容) |
   |                                                                                                       |
   |   -------------------------------------------------------------------------------------------------   |
   |                                                                                                       |
   |   [ std::pmr 多态 Allocator 拓扑: 运行时虚表指针解耦 ]                                                |
   |                                                                                                       |
   |     std::pmr::vector<int> (即 std::vector<int, std::pmr::polymorphic_allocator<int>>)                 |
   |          |                                                                                            |
   |          |-- 内部持有 polymorphic_allocator<int>                                                      |
   |                   |                                                                                   |
   |                   +--> 持有单个指针: std::pmr::memory_resource* res_ (8 字节)                          |
   |                                      |                                                                |
   |                 +--------------------+---------------------+                                          |
   |                 |                                          |                                          |
   |                 v                                          v                                          |
   |       monotonic_buffer_resource                  synchronized_pool_resource                           |
   |       (单调栈上高速缓冲)                         (并发无锁线程安全内存池)                             |
   |                                                                                                       |
   +-------------------------------------------------------------------------------------------------------+

std::pmr::polymorphic_allocator 的物理内存模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``std::pmr::polymorphic_allocator<T>`` 满足 C++ Allocator 概念的所有规范约束。在 64 位体系结构下，其对象实例的内存布局仅包含一个指向底层多态内存资源的裸指针：

.. code-block:: cpp

   template <typename T>
   class polymorphic_allocator {
   public:
       using value_type = T;

       // 默认构造：绑定至当前全局默认 memory_resource
       polymorphic_allocator() noexcept
           : res_(std::pmr::get_default_resource()) {}

       // 显式指针绑定构造
       polymorphic_allocator(std::pmr::memory_resource* r) noexcept
           : res_(r ? r : std::pmr::get_default_resource()) {}

       template <typename U>
       polymorphic_allocator(const polymorphic_allocator<U>& other) noexcept
           : res_(other.resource()) {}

       [[nodiscard]] T* allocate(std::size_t n) {
           if (n > std::numeric_limits<std::size_t>::max() / sizeof(T)) {
               throw std::bad_array_new_length();
           }
           void* p = res_->allocate(n * sizeof(T), alignof(T));
           return static_cast<T*>(p);
       }

       void deallocate(T* p, std::size_t n) noexcept {
           res_->deallocate(p, n * sizeof(T), alignof(T));
       }

       [[nodiscard]] std::pmr::memory_resource* resource() const noexcept {
           return res_;
       }

       // 等价性比较：判断底层多态资源是否相同
       friend bool operator==(const polymorphic_allocator& a,
                              const polymorphic_allocator& b) noexcept {
           return *a.res_ == *b.res_;
       }

   private:
       std::pmr::memory_resource* res_; // 8 字节指针，指向具体的派生内存资源实例
   };

类型别名 ``std::pmr::vector<T>`` 是 ``std::vector<T, std::pmr::polymorphic_allocator<T>>`` 的完整等价别名。不论底层使用的是全局堆、单调栈缓冲还是多线程内存池，其在函数签名中的类型严格恒定为 ``std::pmr::vector<T>``。

std::pmr::memory_resource 的虚表拓扑与 NVI 模式
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``std::pmr::memory_resource`` 是所有具体内存管理策略的抽象基类。它在架构上严格遵循 **非虚接口模式（Non-Virtual Interface, NVI）**：

- **公有非虚接口（Public Non-Virtual Methods）**：暴露 ``allocate()``、``deallocate()`` 与 ``is_equal()``，负责执行对齐参数的断言检查、边界归一化与统一调用入口。
- **私有/保护纯虚接口（Private/Protected Pure Virtual Methods）**：派生类通过重写 ``do_allocate()``、``do_deallocate()`` 与 ``do_is_equal()`` 实现具体的物理存储分配、回收与等价性判定逻辑。

.. code-block:: cpp

   class memory_resource {
   public:
       virtual ~memory_resource() = default;

       [[nodiscard]] void* allocate(std::size_t bytes, std::size_t alignment = alignof(std::max_align_t)) {
           // 确保对齐值为 2 的整数次幂
           assert((alignment & (alignment - 1)) == 0);
           return do_allocate(bytes, alignment);
       }

       void deallocate(void* p, std::size_t bytes, std::size_t alignment = alignof(std::max_align_t)) noexcept {
           assert((alignment & (alignment - 1)) == 0);
           do_deallocate(p, bytes, alignment);
       }

       bool is_equal(const memory_resource& other) const noexcept {
           return do_is_equal(other);
       }

   private:
       virtual void* do_allocate(std::size_t bytes, std::size_t alignment) = 0;
       virtual void  do_deallocate(void* p, std::size_t bytes, std::size_t alignment) noexcept = 0;
       virtual bool  do_is_equal(const memory_resource& other) const noexcept = 0;
   };

   inline bool operator==(const memory_resource& a, const memory_resource& b) noexcept {
       return &a == &b || a.is_equal(b);
   }

在 64 位 Linux/SysV ABI 下，``memory_resource`` 对象的首部包含一个 8 字节的虚表指针（``_vptr``），指向包含析构函数、``do_allocate``、``do_deallocate`` 与 ``do_is_equal`` 函数指针的虚函数表（vtable）。

.. list-table:: 经典模板分配器与 std::pmr 多态分配器架构多维对比矩阵
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 评估维度
     - 经典模板 Allocator (std::allocator / Custom)
     - 多态 Allocator (std::pmr::polymorphic_allocator)
   * - 容器类型绑定
     - 静态绑定：策略不同则类型互异，无法隐式转换
     - 动态解耦：所有策略共享统一容器类型别名
   * - 分配分发机制
     - 编译期静态单态化（Static Monomorphization），可全内联
     - 运行时虚表间接调用（Virtual Call via vtable）
   * - 对象内存占用
     - 无状态分配器占用 0 字节（经由空基类优化 EBO）
     - 严格占用 8 字节（存储单个 ``memory_resource*`` 指针）
   * - 跨模块与 ABI 兼容性
     - 极差：库接口暴露模板实现，引发头文件依赖蔓延
     - 优异：导出统一标准类型，运行时多态注入策略
   * - 嵌套容器分配传播
     - 依赖复杂的 ``scoped_allocator_adaptor`` 手工适配
     - 原生集成 Uses-Allocator Construction 自动深度渗透
   * - 容器移动/交换语义
     - 由静态 traits 标签（POCMA/POCS）编译期决定
     - 传播标志固定为 false，运行时动态比对资源指针

虚函数间接调用的性能权衡
~~~~~~~~~~~~~~~~~~~~~~~~

PMR 引入的虚函数调用会带来微观层面的指令间接寻址开销（1 次解引用获取虚表地址，1 次偏移寻址获取函数指针，共约 2~5 个 CPU 时钟周期）以及潜在的硬件分支目标缓冲（BTB）间接分支预测未命中。

然而在工业级高频物理内存分配场景中，该间接调用开销相比于直接调用操作系统全局堆（如 ``glibc malloc`` 内部的自旋锁竞争、全局 Arena 查找以及缺页中断）所耗费的数十至数百个时钟周期，影响微乎其微。当配合单调内存池或固定块分箱内存池时，本地连续内存的高命中率所带来的 L1/L2 数据缓存加速，能大幅压制虚表跳转的微观成本。

标准内存资源层级与链式上游委托拓扑
----------------------------------

标准库在 `<memory_resource>` 中定义了完整的内存资源层级，并支持基于装饰器模式（Decorator Pattern）的链式上游委托（Upstream Chaining）。

.. code-block:: text

   +-------------------------------------------------------------------------------------------------------+
   |                             std::pmr 内存资源拓扑结构与链式委托体系                                   |
   +-------------------------------------------------------------------------------------------------------+
   |                                                                                                       |
   |   [ 顶层容器使用层 ]                                                                                  |
   |        std::pmr::vector<T> / std::pmr::string / std::pmr::map<K, V>                                   |
   |                                       |                                                               |
   |                                       v                                                               |
   |   [ 多态适配层 ]            polymorphic_allocator<T>                                                  |
   |                                       |                                                               |
   |                                       v                                                               |
   |   [ 策略聚合层 ]         +---------------------------+                                                |
   |                          | monotonic_buffer_resource |  (负责小对象极速线性分配)                      |
   |                          | unsync_pool_resource      |  (负责固定大小块分箱复用)                      |
   |                          +-------------+-------------+                                                |
   |                                        |                                                              |
   |                                        | 当本地 Buffer 耗尽或块尺寸超限时，向上游申请 Chunk           |
   |                                        v                                                              |
   |   [ 上游委托层 ]         +---------------------------+                                                |
   |                          |   new_delete_resource()   |  (下发给全局堆 ::operator new)                 |
   |                          |   null_memory_resource()  |  (严格封顶，抛出 std::bad_alloc)               |
   |                          +---------------------------+                                                |
   |                                                                                                       |
   +-------------------------------------------------------------------------------------------------------+

全局基石资源
~~~~~~~~~~~~

1. **``std::pmr::new_delete_resource()``**：
   - 返回指向全局单例资源的指针。
   - 其 ``do_allocate`` 内部直接调用全局的 ``::operator new(bytes, std::align_val_t(alignment))``。
   - 其 ``do_deallocate`` 内部直接调用全局的 ``::operator delete(p, bytes, std::align_val_t(alignment))``。
   - 处于整个资源委托链条的最底层叶子节点。
2. **``std::pmr::null_memory_resource()``**：
   - 返回一个特殊的边界单例资源。
   - 其 ``do_allocate`` 在被调用时无条件直接抛出 ``std::bad_alloc`` 异常。
   - 其 ``do_deallocate`` 为无操作空函数。
   - 工程意义：作为上游资源传入内存池时，可用于建立 **硬性内存隔离屏障**。确保某个内存池仅在预分配的固定物理空间内工作，完全阻断意外的全局堆分配逃逸。
3. **``std::pmr::get_default_resource()`` 与 ``std::pmr::set_default_resource()``**：
   - 管理程序范围内的默认多态内存资源。
   - 内部维护一个全局原子指针，系统启动时默认指向 ``new_delete_resource()``。
   - ``set_default_resource(r)`` 允许在运行时原子切换全局默认分配策略。未显式指定资源的 ``polymorphic_allocator`` 实例将自动绑定至该默认资源。

单调内存池 (monotonic_buffer_resource) 物理微架构
--------------------------------------------------

``std::pmr::monotonic_buffer_resource`` 专为具有明确阶段性生命周期的业务场景设计（例如网络请求解析、编译器抽象语法树构建、批处理任务与游戏帧临时对象）。

物理工作机制与 Bump Pointer 推进
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``monotonic_buffer_resource`` 内部将物理内存视为一条单向向前推进的线性地址流：

1. **初始缓冲区绑定（Initial Buffer Attachment）**：构造时可接收一段由调用者预先分配的物理存储（通常为栈上的 ``std::byte[]`` 数组），并记录缓冲区的首尾地址与当前游标指针 ``current_ptr_``。
2. **指针碰撞分配（Bump Pointer Allocation）**：
   - 每次调用 ``do_allocate(bytes, alignment)`` 时，计算满足当前对齐要求的起始地址：
     $$	ext{aligned\_addr} = (	ext{current\_ptr} + 	ext{alignment} - 1) \ \& \ \sim(	ext{alignment} - 1)$$
   - 若 $	ext{aligned\_addr} + 	ext{bytes} \le 	ext{buffer\_end}$，则直接将 $	ext{current\_ptr}$ 更新为 $	ext{aligned\_addr} + 	ext{bytes}$，并返回 $	ext{aligned\_addr}$。
   - 整个分配过程仅包含单次加法、位与运算与指针赋值，耗时仅数个纳秒，具有极佳的 CPU L1 指令缓存与数据局部性。
3. **几何级上游扩容（Upstream Geometric Growth）**：
   - 当当前缓冲区剩余空间不足以容纳请求的字节数时，资源向上游资源（Upstream Resource）申请一个新的大型物理块（Chunk）。
   - 新 Chunk 的大小通常按前一次 Chunk 大小的 2 倍几何级数增长（例如 $4	ext{KB} \rightarrow 8	ext{KB} \rightarrow 16	ext{KB}$），并将新 Chunk 作为单向链表节点挂载于资源内部的持有链表头上。
4. **单次释放空操作（No-op Deallocation）**：
   - 其 ``do_deallocate(p, bytes, alignment)`` 实现为空函数，不执行任何释放与空闲链表维护操作。
5. **阶段重置与析构回收（``release()`` & Destruction）**：
   - 调用 ``release()`` 或资源自身析构时，资源遍历其内部单向链表，调用上游资源的 ``deallocate`` 一次性批量归还所有动态申请的 Chunk，并将游标重置回初始缓冲区的起始位置。

.. code-block:: text

   +-------------------------------------------------------------------------------------------------------+
   |                       monotonic_buffer_resource 物理内存布局与 Bump 分配推进                          |
   +-------------------------------------------------------------------------------------------------------+
   |                                                                                                       |
   |   [ 栈上初始缓冲区 (4KB Fixed Buffer) ]                                                               |
   |   buffer_start                                                                           buffer_end   |
   |       |                                                                                      |        |
   |       v                                                                                      v        |
   |     +------------------+------------------+------------------+-----------------------------+          |
   |     | Alloc 1: 128 B   | Alloc 2: 256 B   | Alloc 3: 64 B    | (空闲未分配连续空间)        |          |
   |     +------------------+------------------+------------------+-----------------------------+          |
   |                                                              ^                                        |
   |                                                              |-- current_ptr_ (对齐向前推移)          |
   |                                                                                                       |
   |   -------------------------------------------------------------------------------------------------   |
   |                                                                                                       |
   |   [ 当初始缓冲区溢出时: 向上游申请 2x 几何增长的大块 Chunk 链表 ]                                     |
   |                                                                                                       |
   |   Chunk List Head                                                                                     |
   |         |                                                                                             |
   |         v                                                                                             |
   |     +-----------------------------------------+         +---------------------------------------+     |
   |     | Chunk 2 (8KB from Upstream)             | ------> | Chunk 1 (4KB from Upstream)           |     |
   |     | current_ptr_ ---> [ Alloc 4 ... ]       |         | [ 全部填满的分配数据 ]                |     |
   |     +-----------------------------------------+         +---------------------------------------+     |
   |                                                                                                       |
   |   * 规则：单次 deallocate() 为纯 No-op；release() 时沿单向链表全量归还给 Upstream。                   |
   |                                                                                                       |
   +-------------------------------------------------------------------------------------------------------+

生命周期倒序不变量与安全释放边界
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

由于 ``monotonic_buffer_resource`` 在执行 ``release()`` 或析构时会直接从物理底层抹除所有内存块，使用该资源必须严格遵循 **对象生命周期必须先于物理内存资源终结** 的黄金定律：

- **合法的阶段析构顺序**：
  1. 容器对象调用自身析构函数，完成内部元素的析构（执行析构函数中的资源清理逻辑，如关闭文件描述符、释放外部堆句柄）。
  2. 容器依赖的 ``monotonic_buffer_resource`` 显式调用 ``release()`` 或退出作用域自动析构，归还物理底层内存。
- **未定义行为破坏场景**：
  若在容器对象尚存活时提前调用 ``arena.release()``，随后容器在其析构函数中试图遍历元素并执行 ``destroy``，将直接访问已经被释放的野指针内存，引发段错误（SIGSEGV）或静默内存破坏。

池化内存资源 (Pool Resources) 拓扑与并发分流
--------------------------------------------

单调内存资源虽然在批量构造和一次性释放场景下性能优异，但其无法复用中间归还的空闲内存。对于存在大量交错创建、销毁且对象大小分布相对固定的长期业务系统，标准库提供了池化内存资源：

- ``std::pmr::unsynchronized_pool_resource``：非线程安全版本，面向单线程独占场景。
- ``std::pmr::synchronized_pool_resource``：线程安全版本，面向多线程并发共享场景。

分箱大小类别（Size-Class Bins）与微架构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

池化内存资源内部将内存划分为一组离散的“分箱”（Bins / Pools），每个分箱专门负责服务特定字节大小区间的分配请求：

.. code-block:: text

   +-------------------------------------------------------------------------------------------------------+
   |                             Pool Resources 内部分箱与空闲链表拓扑                                     |
   +-------------------------------------------------------------------------------------------------------+
   |                                                                                                       |
   |   用户请求: allocate(bytes, align)                                                                    |
   |        |                                                                                              |
   |        +---> bytes <= largest_pool_block?                                                             |
   |                 |                                                                                     |
   |                 |-- [ 是: 命中分箱 ] --> 路由至对应的 Size-Class Bin                                  |
   |                 |                            |                                                        |
   |                 |                            +--> Bin[16 B]  --> [ Free Block ] -> [ Free Block ]     |
   |                 |                            +--> Bin[32 B]  --> [ Free Block ] -> [ Free Block ]     |
   |                 |                            +--> Bin[64 B]  --> (空闲列表耗尽，向上游申请 Chunk 切分) |
   |                 |                            +--> Bin[128 B] --> [ Free Block ]                       |
   |                 |                                                                                     |
   |                 +-- [ 否: 超大对象 ] --> 旁路路由 (Bypass Pool) --> 直接由 Upstream Resource 分配     |
   |                                                                                                       |
   +-------------------------------------------------------------------------------------------------------+

分箱运行逻辑：

1. **侵入式空闲链表（Intrusive Free List）**：每个分箱维护一个单向空闲块链表。由于未分配的内存块处于闲置状态，标准库实现直接将空闲块的前 8 字节用作指向下一个空闲块的指针（``next``），实现零额外元数据内存开销。
2. **分配命中（Allocation Hit）**：从对应分箱的空闲链表头部弹出一个块（$O(1)$ 复杂度）。
3. **分配缺失（Allocation Miss）**：当对应分箱的空闲链表为空时，该分箱向上游资源申请一个较大的 Chunk，将其物理切分为若干固定大小的块，串联至空闲链表中，随后返回首块。
4. **归还复用（Deallocation & Reuse）**：调用 ``do_deallocate`` 时，该块被重新推入对应分箱的空闲链表头部，供后续分配立即复用。
5. **超大分配旁路（Oversized Allocation Bypass）**：当请求的字节数超过最大分箱限制（由 ``pool_options::largest_required_pool_block`` 设定）时，请求直接跨过分箱系统，旁路委托给上游资源。

std::pmr::pool_options 配置参数
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

程序员可以通过配置 ``std::pmr::pool_options`` 结构体精确调优池化资源的行为：

.. code-block:: cpp

   struct pool_options {
       std::size_t max_blocks_per_chunk;        // 单个 Chunk 内部允许切分的最大块数（控制单次向 Upstream 申请的内存上限）
       std::size_t largest_required_pool_block; // 进入分箱管理的最大对象字节数阈值，超过此值的请求直达 Upstream
   };

并发模型与锁竞争消除
~~~~~~~~~~~~~~~~~~~~

- **``unsynchronized_pool_resource``**：内部无任何互斥锁（Mutex）与原子变量同步操作。在单线程、协程上下文或线程局部存储（Thread-Local Storage, TLS）中运行，吞吐量达到极致。
- **``synchronized_pool_resource``**：
  - 保证多线程并发调用 ``allocate`` 与 ``deallocate`` 的线程安全性。
  - 主流标准库（如 GCC libstdc++ 与 LLVM libc++）通常在内部采用细粒度的按分箱独立加锁，或利用 Thread-Local Cache 架构将分配请求分流至各线程专属的无锁缓冲中，显著降低多核并发访问下的全局锁争用（Lock Contention）。

Uses-Allocator 构造机制与多层容器资源传播
------------------------------------------

在 STL 容器嵌套结构中（例如 ``std::pmr::vector<std::pmr::string>``），外层容器的内存分配与内层元素的内存分配处于不同的层级。

如果不引入特殊传播机制，外层 vector 扩容时会在绑定的 PMR 资源上为 ``std::pmr::string`` 对象本身分配存储；然而，当这些字符串对象被构造并存入长字符串数据时，内层字符串如果仅执行默认构造，将静默绑定至全局默认资源（``std::pmr::get_default_resource()``），导致内层动态内存无法落入外层指定的专用内存池中。

C++17 通过 **Uses-Allocator 构造机制** 彻底解决了多层嵌套对象的分配器自动渗透传播问题。

编译期检测与分发三大协议
~~~~~~~~~~~~~~~~~~~~~~~~

标准库通过模板类型萃取 ``std::uses_allocator<T, Alloc>::value``（在 C++17 中为 ``std::uses_allocator_v<T, Alloc>``）判定目标类型 $T$ 是否支持分配器注入。

当 ``polymorphic_allocator<T>::construct(p, args...)`` 在原始地址 $p$ 上构造对象时，根据类型特征静态分发至以下三种路径之一：

.. list-table:: Uses-Allocator 构造策略分发矩阵
   :widths: 22 30 48
   :header-rows: 1
   :class: tight-table

   * - 匹配类型特征
     - 构造函数调用形式
     - 典型标准库与用户自定义类型
   * - ``!std::uses_allocator_v<T, Alloc>``
     - ``::new (p) T(args...)``
     - 原生标量类型（``int``, ``double``）、传统无分配器类
   * - ``std::is_constructible_v<T, std::allocator_arg_t, Alloc, Args...>``
     - ``::new (p) T(std::allocator_arg, alloc, args...)``
     - 前置分配器标签类：``std::tuple``, ``std::function``, ``std::promise``
   * - ``std::is_constructible_v<T, Args..., Alloc>``
     - ``::new (p) T(args..., alloc)``
     - 后置分配器容器类：``std::pmr::string``, ``std::pmr::vector``, ``std::pmr::map``

.. code-block:: text

   +-------------------------------------------------------------------------------------------------------+
   |                        Uses-Allocator Construction 在嵌套容器中的递归渗透拓扑                         |
   +-------------------------------------------------------------------------------------------------------+
   |                                                                                                       |
   |   std::pmr::vector<std::pmr::string> vec(&custom_arena);                                              |
   |                                                                                                       |
   |   vec.emplace_back("Long string exceeding SSO buffer limit...");                                      |
   |        |                                                                                              |
   |        | 1. vector 使用 custom_arena 分配 string 对象本身的头部空间 (sizeof(string) = 32B)             |
   |        v                                                                                              |
   |   polymorphic_allocator<string>::construct(&vec[0], "Long string...")                                 |
   |        |                                                                                              |
   |        | 2. 检测到 string 满足 std::uses_allocator_v<string, polymorphic_allocator>                   |
   |        | 3. 匹配后置参数构造: string("Long string...", polymorphic_allocator(custom_arena))           |
   |        v                                                                                              |
   |   string 内部字符数组 (超出 SSO 阈值) 动态申请物理存储                                                |
   |        |                                                                                              |
   |        +---> 自动通过传入的 polymorphic_allocator 再次向 custom_arena 请求内存                         |
   |                                                                                                       |
   |   * 结果：外层容器与内层所有嵌套元素的物理内存全部精准收敛在同一个 custom_arena 中，零泄漏，零全局堆逃逸。|
   |                                                                                                       |
   +-------------------------------------------------------------------------------------------------------+

std::pair 与 std::tuple 的分段解包构造
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于关联容器中的键值对 ``std::pair<const Key, Value>``，``std::pmr::polymorphic_allocator::construct`` 会进一步自动解构 Pair 的 ``first`` 与 ``second`` 成员，分别针对这两个成员各自独立执行 Uses-Allocator 判定并递归传入分配器，确保如 ``std::pmr::map<std::pmr::string, std::pmr::vector<int>>`` 中的键和值均能自动继承外层 Map 的内存资源。

PMR 容器在拷贝、移动与交换中的传播屏障
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

根据 C++17 标准规范，``std::pmr::polymorphic_allocator<T>`` 的四大传播标志被强制规定为：

- ``propagate_on_container_copy_assignment`` $\equiv$ ``std::false_type``
- ``propagate_on_container_move_assignment`` $\equiv$ ``std::false_type``
- ``propagate_on_container_swap`` $\equiv$ ``std::false_type``
- ``is_always_equal`` $\equiv$ ``std::false_type``

传播标志全为 ``false_type`` 构成了 PMR 容器的物理传播屏障，对工程代码产生了明确的操作约束：

1. **拷贝赋值（Copy Assignment）**：目标容器始终保留其原有的 ``memory_resource*``，仅将源容器的数据元素复制到由目标分配器申请的新存储中。
2. **移动赋值（Move Assignment）**：
   - 若 ``left.get_allocator() == right.get_allocator()``（即底层绑定同一内存资源），直接执行 $O(1)$ 指针窃取并置空源容器。
   - 若 ``left.get_allocator() != right.get_allocator()``，由于左侧容器严禁使用自身的分配器释放右侧容器的物理块，必须退化为逐个元素的移动构造与旧元素析构（时间复杂度退化为 $O(N)$）。
3. **容器交换（Swap）**：
   - 必须满足 ``left.get_allocator() == right.get_allocator()``。
   - 若两个绑定了不同内存资源的 PMR 容器执行 ``std::swap(c1, c2)``，直接触发 **未定义行为（Undefined Behavior）**。

工业级高吞吐 PMR 请求处理引擎完整实现
--------------------------------------

本节给出一个完整的工业级 C++17/20 架构实战：实现一个带原子指标遥测的自定义内存资源 ``TrackedMetricsResource``，并结合栈上单调内存池与非同步池化资源，构建一个高吞吐零堆碎片的 HTTP 请求解析与路由上下文引擎。

.. code-block:: cpp

   #include <array>
   #include <atomic>
   #include <cassert>
   #include <cstddef>
   #include <iostream>
   #include <memory_resource>
   #include <string>
   #include <string_view>
   #include <utility>
   #include <vector>

   namespace engine::pmr {

   // =========================================================================
   // 1. 工业级带原子统计与水位监测的多态内存资源：TrackedMetricsResource
   // =========================================================================
   class TrackedMetricsResource : public std::pmr::memory_resource {
   public:
       explicit TrackedMetricsResource(std::pmr::memory_resource* upstream = std::pmr::new_delete_resource()) noexcept
           : upstream_(upstream),
             allocated_bytes_(0),
             deallocated_bytes_(0),
             allocation_count_(0),
             peak_bytes_(0) {}

       [[nodiscard]] std::size_t current_allocated_bytes() const noexcept {
           return allocated_bytes_.load(std::memory_order_relaxed) -
                  deallocated_bytes_.load(std::memory_order_relaxed);
       }

       [[nodiscard]] std::size_t peak_allocated_bytes() const noexcept {
           return peak_bytes_.load(std::memory_order_relaxed);
       }

       [[nodiscard]] std::size_t allocation_count() const noexcept {
           return allocation_count_.load(std::memory_order_relaxed);
       }

   private:
       void* do_allocate(std::size_t bytes, std::size_t alignment) override {
           void* p = upstream_->allocate(bytes, alignment);
           std::size_t current = allocated_bytes_.fetch_add(bytes, std::memory_order_relaxed) + bytes;
           allocation_count_.fetch_add(1, std::memory_order_relaxed);

           std::size_t dealloc = deallocated_bytes_.load(std::memory_order_relaxed);
           std::size_t live = (current >= dealloc) ? (current - dealloc) : 0;

           // 更新峰值内存水位
           std::size_t prev_peak = peak_bytes_.load(std::memory_order_relaxed);
           while (live > prev_peak &&
                  !peak_bytes_.compare_exchange_weak(prev_peak, live, std::memory_order_relaxed)) {
               // 自旋更新 CAS
           }

           return p;
       }

       void do_deallocate(void* p, std::size_t bytes, std::size_t alignment) noexcept override {
           upstream_->deallocate(p, bytes, alignment);
           deallocated_bytes_.fetch_add(bytes, std::memory_order_relaxed);
       }

       bool do_is_equal(const std::pmr::memory_resource& other) const noexcept override {
           return this == &other;
       }

       std::pmr::memory_resource* upstream_;
       std::atomic<std::size_t>   allocated_bytes_;
       std::atomic<std::size_t>   deallocated_bytes_;
       std::atomic<std::size_t>   allocation_count_;
       std::atomic<std::size_t>   peak_bytes_;
   };

   // =========================================================================
   // 2. HTTP 请求报文上下文数据结构（深度嵌套 PMR 容器）
   // =========================================================================
   struct HttpHeader {
       std::pmr::string name;
       std::pmr::string value;

       // 支持 Uses-Allocator 构造传播
       HttpHeader(std::string_view n, std::string_view v,
                  const std::pmr::polymorphic_allocator<std::byte>& alloc)
           : name(n, alloc), value(v, alloc) {}
   };

   class HttpRequestContext {
   public:
       using AllocatorType = std::pmr::polymorphic_allocator<std::byte>;

       explicit HttpRequestContext(AllocatorType alloc)
           : method_(alloc),
             uri_(alloc),
             body_(alloc),
             headers_(alloc) {}

       void set_method(std::string_view m) { method_ = m; }
       void set_uri(std::string_view u) { uri_ = u; }
       void set_body(std::string_view b) { body_ = b; }

       void add_header(std::string_view name, std::string_view value) {
           // emplace_back 自动将外层 vector 的 allocator 传播给 HttpHeader 及其内部的两个 pmr::string
           headers_.emplace_back(name, value, headers_.get_allocator());
       }

       [[nodiscard]] std::string_view method() const noexcept { return method_; }
       [[nodiscard]] std::string_view uri() const noexcept { return uri_; }
       [[nodiscard]] std::string_view body() const noexcept { return body_; }
       [[nodiscard]] const std::pmr::vector<HttpHeader>& headers() const noexcept { return headers_; }

   private:
       std::pmr::string              method_;
       std::pmr::string              uri_;
       std::pmr::string              body_;
       std::pmr::vector<HttpHeader>  headers_;
   };

   // =========================================================================
   // 3. 高吞吐请求处理管道：单调栈缓冲 + 池化复合架构
   // =========================================================================
   class FastPipelineProcessor {
   public:
       explicit FastPipelineProcessor(std::pmr::memory_resource* metrics_res)
           : root_metrics_res_(metrics_res) {}

       void process_single_request(std::string_view raw_method,
                                   std::string_view raw_uri,
                                   std::string_view raw_body) {
           // 1. 栈上预分配 8KB 物理热内存
           alignas(std::max_align_t) std::array<std::byte, 8192> stack_buffer{};

           // 2. 建立单调缓冲区，指定 root_metrics_res_ 作为溢出上游
           std::pmr::monotonic_buffer_resource arena(
               stack_buffer.data(),
               stack_buffer.size(),
               root_metrics_res_
           );

           // 3. 基于 Arena 创建多态分配器
           std::pmr::polymorphic_allocator<std::byte> alloc(&arena);

           // 4. 构建业务上下文（所有容器及嵌套字符串完全由栈上 Arena 承接）
           {
               HttpRequestContext req(alloc);
               req.set_method(raw_method);
               req.set_uri(raw_uri);
               req.set_body(raw_body);

               req.add_header("Host", "api.internal.service");
               req.add_header("User-Agent", "HighThroughputClient/2.0");
               req.add_header("X-Trace-ID", "e9b21f3a-8c4d-4b71-9f6e-12879a6d450b");
               req.add_header("Content-Type", "application/json");

               // 执行业务逻辑...
               assert(req.headers().size() == 4);
           }
           // 5. 作用域结束：HttpRequestContext 正常析构，随后 arena 自动析构释放，零堆碎片，零全局锁
       }

   private:
       std::pmr::memory_resource* root_metrics_res_;
   };

   } // namespace engine::pmr

小结与下章导读
--------------

本章系统解构了现代 C++17 ``std::pmr`` 多态内存资源体系：从经典模板 Allocator 引发的类型传染与 ABI 割裂物理缺陷，到 ``polymorphic_allocator`` 依托 8 字节虚表指针将物理内存分配策略推迟至运行时的解耦架构；从 ``memory_resource`` 抽象基类的 NVI 设计模式、全局单例基石（``new_delete_resource``、``null_memory_resource``）到链式上游委托拓扑；从 ``monotonic_buffer_resource`` 基于栈上固定缓冲与 Bump Pointer 线性推进的极速 $O(1)$ 分配与阶段统一释放，到 ``unsynchronized_pool_resource`` 与 ``synchronized_pool_resource`` 的大小分箱（Size-Class Bins）、侵入式空闲链表与多线程锁竞争消除机制；从 Uses-Allocator Construction 在多层嵌套容器中的三向协议推导与 pair/tuple 深度渗透，到 PMR 容器因传播标志全部锁定为 false 所形成的物理移动/交换屏障；最终通过带原子指标遥测的自定义内存资源与零堆碎片高吞吐请求处理管道，实现了现代 C++ 内存子系统的高效闭环。

在彻底掌握了静态 Allocator 与动态 PMR 内存资源的物理分配与生命周期控制后，下一章我们将深入 STL 容器的核心防御屏障 —— **异常安全保证与回滚机制：基本保证/强保证/不抛保证、noexcept 移动判定与 vector 扩容事务一致性（``02_stl_core_mechanisms_and_allocators/04_exception_safety_guarantees_and_rollbacks.rst``）**，剖析栈展开（Stack Unwinding）过程中的 RAII 资源守卫、``std::move_if_noexcept`` 条件移动降级判定以及容器状态原子提交的底层状态机。
