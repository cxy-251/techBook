========================================================================================================================
物理内存管理体系与 RAII 哲学：malloc/free 与 new/delete 表达式解构、placement new、未初始化内存与缓存局部性
========================================================================================================================

.. note:: 前置背景与上下文承接
   在前一章《右值引用与移动语义深度解析：值类别 (lvalue/xvalue/prvalue)、std::move、完美转发折叠与 moved-from 状态》中，系统剖析了 C++11 资源所有权流转的类型系统规则与寄存器级句柄置换机制。移动语义的高效执行依赖于底层内存边界的精准控制。本章将视野下沉至操作系统内核与物理硬件层级，深入解构 C++ 内存管理基础设施：从 Linux 虚拟内存系统调用（``brk`` / ``mmap``）、C 运行时堆分配器（ptmalloc/jemalloc）的 Chunk 状态机，到 C++ ``new`` / ``delete`` 表达式的双阶段机器码生成；从 Placement New 与未初始化内存批量算法的异常安全屏障，到 CPU 多级缓存局部性（Cache Locality）、内存对齐与高吞吐内存池（Arena）架构，最终确立现代 C++ RAII（Resource Acquisition Is Initialization）资源确定性绑定的物理基石。

物理内存分配体系与系统调用底座：brk、mmap 与堆分配器状态机
--------------------------------------------------------

应用程序进程在 Linux 操作系统中运行于虚拟地址空间（Virtual Address Space）。在 64 位 x86_64 体系架构下，用户态虚拟地址空间通常占用低 47 位（128 TB 空间，Canonical Address 范围为 ``0x0000000000000000`` 至 ``0x00007FFFFFFFFFFF``）。物理内存由操作系统内存管理单元（MMU）以 4KB 物理页（Page Frame）为粒度进行分页映射。

当程序请求动态内存时，用户态运行时库必须通过操作系统内核系统调用向虚拟内存子系统索取内存区域（VMA, Virtual Memory Area）。Linux 内核提供两条底层分配系统调用路径：

1. **``brk`` / ``sbrk`` 系统调用**：
   通过移动进程堆顶指针（Program Break Point）扩展或收缩数据段（Heap Segment）。堆内存连续向上线性增长。分配较小内存块（glibc 默认阈值低于 128KB）时，C 运行时通过调整 ``brk`` 扩充堆顶，减少陷入内核态执行缺页异常（Page Fault）的处理开销。
2. **``mmap`` / ``munmap`` 系统调用**：
   在进程的内存映射区（Memory Mapping Segment）开辟独立且页对齐的匿名虚拟内存映射区（Anonymous VMA）。分配大内存块（glibc 默认阈值大于等于 128KB）时，C 运行时直接调用 ``mmap``。调用 ``free`` 时，该映射区直接通过 ``munmap`` 归还操作系统内核，物理页帧被立即解映射。

.. code-block:: text

   +-----------------------------------------------------------------------------------+
   |                    Linux x86_64 进程虚拟地址空间与内存分配系统调用拓扑             |
   +-----------------------------------------------------------------------------------+
   | 0x7FFF_FFFF_FFFF  +-------------------------------------------------------------+ |
   |                   | 内核保留空间 (Kernel Space, 8-byte canonical limit)          | |
   | 0x7FFF_7FFF_FFFF  +-------------------------------------------------------------+ |
   |                   | 用户栈 (User Stack, 高地址向下增长)                          | |
   |                   |    |                                                        | |
   |                   |    v                                                        | |
   |                   | [ 动态内存映射区 (mmap Anonymous Allocation, >= 128KB) ]      | |
   |                   |    ^                                                        | |
   |                   |    | (brk 堆顶指针扩展方向)                                  | |
   |                   | [ 堆空间 (Heap, 经由 brk 连续向上增长, < 128KB) ]            | |
   |                   +-------------------------------------------------------------+ |
   |                   | BSS 段 (未初始化全局/静态数据)                              | |
   |                   +-------------------------------------------------------------+ |
   |                   | Data 段 (已初始化全局/静态数据)                             | |
   |                   +-------------------------------------------------------------+ |
   | 0x0000_0040_0000  | Text 段 (可执行机器指令)                                    | |
   | 0x0000_0000_0000  +-------------------------------------------------------------+ |
   +-----------------------------------------------------------------------------------+

C 运行时分配器（如 glibc 的 ptmalloc2）在系统调用之上维护内存池管理结构（Arena、Chunks 与 Bins）。分配器将取得的连续内存划分为带元数据的物理 Chunk：

- **Chunk 头部结构（Chunk Header）**：每个 Chunk 包含 ``prev_size``（前一个相邻 Chunk 的大小）和 ``size``（当前 Chunk 大小）。由于 x86_64 架构要求内存按 16 字节对齐，``size`` 字段的低 3 位恒为 0，分配器将其用作标志位：
  
  - ``A`` 位 (``0x4``, ``NON_MAIN_ARENA``)：指示该 Chunk 来自非主线程 Arena。
  - ``M`` 位 (``0x2``, ``IS_MMAPPED``)：指示该 Chunk 由 ``mmap`` 直接映射。
  - ``P`` 位 (``0x1``, ``PREV_INUSE``)：指示物理相邻的前一个 Chunk 正处于使用状态。

.. code-block:: text

   +-------------------------------------------------------------------------------+
   |                      ptmalloc Chunk 内存布局与元数据存储拓扑                  |
   +-------------------------------------------------------------------------------+
   | 偏移量 (Bytes)  | 字段名称                      | 作用与状态说明               |
   +-----------------+-------------------------------+-------------------------------+
   | [ptr - 16]      | size_t prev_size              | 前一 Chunk 物理大小 (若空闲) |
   | [ptr - 8]       | size_t size_and_flags (A|M|P) | 当前 Chunk 大小及 3 位状态位  |
   | ptr (0x00)      | User Data Payload             | 用户可用存储起始地址 (16B对齐)|
   | ...             | ...                           | 连续可用字节空间              |
   +-------------------------------------------------------------------------------+

当程序调用 ``malloc(size)`` 时，分配器计算包含头部与对齐填充后的实际 Chunk 大小，在 Fastbins、Smallbins、Unsorted bins 或 Largebins 中检索最合适的空闲块。当调用 ``free(ptr)`` 时，分配器通过指针算术读取 ``*(size_t*)((char*)ptr - 8)`` 获取当前 Chunk 的大小及 ``P`` 位标志。若相邻 Chunk 均处于空闲状态，分配器执行双向双链表合并，消除外部内存碎片。

.. list-table:: 操作系统系统调用与 C/C++ 内存接口关键属性对比
   :widths: 15 20 20 20 25
   :header-rows: 1
   :class: tight-table

   * - 抽象层级
     - 分配接口 / 系统调用
     - 释放接口 / 系统调用
     - 内存粒度与对齐契约
     - 对象生命周期责任
   * - 操作系统内核
     - ``brk`` / ``mmap``
     - ``brk`` / ``munmap``
     - 4KB 页帧粒度；页边界对齐
     - 仅提供裸物理页帧映射；无对象概念
   * - C 运行时
     - ``malloc`` / ``calloc`` / ``realloc``
     - ``free``
     - 字节粒度；``alignof(max_align_t)`` (16B)
     - 仅管理字节缓冲区与 Chunk 元数据；不调用构造/析构
   * - C++ 分配函数
     - ``operator new`` / ``operator new[]``
     - ``operator delete`` / ``operator delete[]``
     - 字节粒度；支持 C++17 ``std::align_val_t``
     - 仅负责原始内存获取；抛出 ``std::bad_alloc``
   * - C++ 组合表达式
     - ``new`` / ``new[]``
     - ``delete`` / ``delete[]``
     - 类型感知；由目标类型确定对齐
     - 自动执行“内存分配 + 原地构造”与“析构 + 内存归还”

new / delete 表达式的机器级解构与编译器代码生成
------------------------------------------------

C++ 中的 ``new`` 与 ``delete`` 是语言级内建表达式（Language Expressions），编译器将其编译降解为两条独立的正交流水线：**原始存储分配/释放** 与 **对象生命周期构造/析构**。

单对象表达式 ``new T(args...)`` 的降解全流程：

1. **第一阶段（分配存储）**：计算对象大小 ``sizeof(T)`` 与对齐要求 ``alignof(T)``，调用分配函数 ``operator new(sizeof(T))`` 获取 ``void*`` 原始内存指针。
2. **第二阶段（就地构造）**：在获得的内存首地址上，传入参数包 ``args...`` 调用构造函数 ``T::T(args...)``。
3. **异常清理分支（Exception Cleanup）**：若构造函数在执行期间抛出异常，编译器生成的 Landing Pad 异常捕获块将自动调用与 ``operator new`` 签名的 ``operator delete(raw_mem)`` 释放第一阶段取得的裸存储，防止内存泄漏，随后向外层重新抛出该异常。

.. code-block:: cpp

   #include <new>
   #include <utility>
   #include <iostream>

   struct TransactionNode {
       int node_id;
       explicit TransactionNode(int id) : node_id(id) {
           if (id < 0) {
               throw std::runtime_error("Invalid node id");
           }
       }
       ~TransactionNode() = default;
   };

   // 编译器处理 auto p = new TransactionNode(42); 的伪代码等价展开模型
   TransactionNode* manual_lowered_new(int id) {
       // 1. 调用分配函数取得存储
       void* raw_storage = ::operator new(sizeof(TransactionNode));
       TransactionNode* obj_ptr = nullptr;

       try {
           // 2. 在裸存储地址上调用构造函数
           obj_ptr = ::new (raw_storage) TransactionNode(id);
       } catch (...) {
           // 3. 构造函数抛出异常时的自动存储回收
           ::operator delete(raw_storage);
           throw; // 保持异常继续传播
       }

       return obj_ptr;
   }

   // 编译器处理 delete p; 的伪代码等价展开模型
   void manual_lowered_delete(TransactionNode* p) noexcept {
       if (p == nullptr) {
           return;
       }
       // 1. 调用析构函数结束对象生命周期
       p->~TransactionNode();
       // 2. 调用释放函数归还原始存储
       ::operator delete(static_cast<void*>(p));
   }

数组表达式 ``new T[N]`` 与 ``delete[] p`` 涉及数组 Cookie（Array Cookie）元数据管理机制：

当类型 ``T`` 拥有非平凡析构函数（Non-Trivial Destructor）时，运行时必须获知数组元素的具体数量 $N$，以便在 ``delete[]`` 时逐个调用每个元素的析构函数。

x86_64 体系下 Itanium C++ ABI 规范规定：编译器在分配数组内存时，额外多申请 8 字节空间用于保存元素个数 $N$。实际分配大小为 ``sizeof(T) * N + sizeof(size_t)``。首部 8 字节写入数值 $N$，返回给用户的指针则偏移至 ``raw_storage + 8``。

.. code-block:: text

   +-------------------------------------------------------------------------------+
   |              new T[N] 数组 Cookie 与物理内存偏移拓扑 (x86_64 ABI)             |
   +-------------------------------------------------------------------------------+
   | 物理内存地址   | 字段内容                      | 访问者与生命周期职责         |
   +----------------+-------------------------------+-------------------------------+
   | raw_ptr (0x00) | size_t element_count (N)      | 运行时数组元数据 (Cookie)     |
   | ret_ptr (0x08) | T[0] 对象存储起始             | 用户返回指针；首个元素构造点 |
   | (0x08 + 1*sz)  | T[1] 对象存储                 | 第二个元素构造点              |
   | ...            | ...                           | ...                           |
   | (0x08 + N*sz)  | 数组内存终点 (raw_ptr + Total)| 分配边界                      |
   +-------------------------------------------------------------------------------+

执行 ``delete[] user_ptr`` 时，编译器生成的代码向前回退 8 字节读取 ``size_t count = *(size_t*)((char*)user_ptr - 8)``，随后以逆序执行 ``for (size_t i = count; i > 0; --i) user_ptr[i - 1].~T();``，最后调用 ``operator delete[]((char*)user_ptr - 8)`` 释放整段连续内存。

混用分配与释放接口将直接导致系统崩溃或内存损坏：

- 对 ``new T[N]`` 取得的指针调用 ``delete p``：析构函数仅被调用一次，且传入释放函数的地址为 ``user_ptr`` 而非真实分配起始地址 ``raw_ptr``，破坏堆分配器的 Chunk 内部元数据。
- 对 ``malloc`` 取得的指针调用 ``delete p``：将未构造的内存当做有效对象执行析构，引发未定义行为。

原位构造 (Placement New)、未初始化内存与批量生命周期算法
--------------------------------------------------------

在 STL 工业级容器（如 ``std::vector``、``std::deque``）的实现中，核心原则是将**内存分配策略**与**对象生命周期管理**完全解耦。容器在初始化或扩容时，预先申请能够容纳指定容量的未初始化原始存储（Raw Memory），仅在元素实际插入时才在指定内存槽位上执行就地构造。

Placement New 是 C++ 提供的底层原语，用于在调用方指定的物理地址上就地构造对象，语法形式为：

.. code-block:: cpp

   ::new (static_cast<void*>(address)) T(args...);

标准库头文件 ``<new>`` 中定义的内置 Placement ``operator new`` 实现为内联空操作：

.. code-block:: cpp

   [[nodiscard]] inline void* operator new(std::size_t, void* ptr) noexcept {
       return ptr;
   }

C++20 引入了标准化工具 ``std::construct_at`` 与 ``std::destroy_at``，统一了原位构造与就地析构的形式，并在编译期支持 ``constexpr`` 表达式求值：

.. code-block:: cpp

   #include <memory>

   template <typename T, typename... Args>
   constexpr T* construct_at(T* location, Args&&... args) {
       return ::new (static_cast<void*>(location)) T(std::forward<Args>(args)...);
   }

   template <typename T>
   constexpr void destroy_at(T* location) noexcept {
       location->~T();
   }

在未初始化内存（Uninitialized Memory）区域进行批量元素初始化与迁移时，必须严格处理**部分构造（Partial Construction）**异常边界：若在初始化第 $K$ 个元素时构造函数抛出异常，算法必须回滚销毁前 $0 \dots K-1$ 个已构造的有效对象，随后释放原始内存，严禁对尚未构造的 $K \dots N-1$ 槽位执行析构。

标准库提供了四个核心底层未初始化内存算法，其内部均内置了基于 RAII 或指针标记的强异常安全回滚机制：

1. ``std::uninitialized_copy(InputIt first, InputIt last, ForwardIt d_first)``
2. ``std::uninitialized_fill(ForwardIt first, ForwardIt last, const T& value)``
3. ``std::uninitialized_move(InputIt first, InputIt last, ForwardIt d_first)``
4. ``std::destroy(ForwardIt first, ForwardIt last)``

.. code-block:: cpp

   #include <cstddef>
   #include <memory>
   #include <new>
   #include <utility>
   #include <iostream>

   template <typename T>
   class RawMemoryTransactionEngine {
   public:
       // 批量异常安全原位迁移引擎
       static T* uninitialized_move_commit(T* src_first, T* src_last, T* dest_buffer) {
           T* current_constructed = dest_buffer;
           try {
               for (; src_first != src_last; ++src_first, ++current_constructed) {
                   // 在目标原始存储槽位上就地执行移动构造
                   std::construct_at(current_constructed, std::move(*src_first));
               }
               return current_constructed;
           } catch (...) {
               // 事务失败回滚：仅析构已在目标区域成功构造的元素 [dest_buffer, current_constructed)
               for (T* p = dest_buffer; p != current_constructed; ++p) {
                   std::destroy_at(p);
               }
               // 未构造的 [current_constructed, dest_buffer + N) 区域保持原始内存状态，绝不触发析构
               throw;
           }
       }

       // 批量安全销毁已构造对象序列
       static void destroy_range(T* first, T* last) noexcept {
           for (; first != last; ++first) {
               std::destroy_at(first);
           }
       }
   };

硬件级缓存局部性 (Cache Locality)、内存对齐与内存池设计
------------------------------------------------------

现代多核 CPU 的计算核心与主存（DRAM）之间存在巨大的访问延迟鸿沟。CPU 采用多级高速缓存架构缓解内存墙限制：

- **L1 数据缓存 (L1D Cache)**：延迟约为 4~5 个时钟周期（~1.0 ns），容量通常为 32KB~48KB / 核心。
- **L2 缓存 (L2 Cache)**：延迟约为 12~14 个时钟周期（~3.5 ns），容量通常为 512KB~1.25MB / 核心。
- **L3 共享缓存 (L3 Cache)**：延迟约为 40~60 个时钟周期（~12 ns），容量通常为 16MB~96MB 共享。
- **主内存 (Main Memory, DRAM)**：延迟约为 150~250 个时钟周期（~60~80 ns）。

CPU 缓存与主存间的数据交换以**缓存行（Cache Line，主流架构固定为 64 字节）**为物理基本单元。

.. code-block:: text

   +-------------------------------------------------------------------------------+
   |                      CPU 多级缓存层级与内存访问延迟阶梯拓扑                   |
   +-------------------------------------------------------------------------------+
   | 层级           | 典型容量       | 访问延迟 (Cycles / ns) | 物理传输单元         |
   +----------------+----------------+------------------------+---------------------+
   | CPU Registers  | ~1 KB          | 0 cycles (0.2 ns)      | 8-byte / SIMD 寄存器|
   | L1D Cache      | 32 KB - 48 KB  | ~4 cycles (1.0 ns)     | 64-byte Cache Line  |
   | L2 Cache       | 512 KB - 1 MB  | ~14 cycles (3.5 ns)    | 64-byte Cache Line  |
   | L3 Cache (LLC) | 16 MB - 96 MB  | ~50 cycles (12.0 ns)   | 64-byte Cache Line  |
   | Main Memory    | 16 GB - 128 GB | ~200 cycles (60.0 ns)  | 64-byte Burst       |
   +-------------------------------------------------------------------------------+

缓存局部性分为两个物理维度：

1. **空间局部性（Spatial Locality）**：当程序访问某个内存地址时，与其物理相邻的内存地址在短时间内也会被访问。``std::vector`` 与连续原生数组在物理内存中紧密排列，一次 64 字节 Cache Line 加载即可填充多个相邻元素，硬件流式预取器（Hardware Stream Prefetcher）能自动识别线性步进并将后续 Cache Line 预加载至 L1D。
2. **时间局部性（Temporal Locality）**：某个内存地址被访问后，短时间内会被重复访问。

与之对比，基于分散链表节点的容器（如 ``std::list``、``std::map``）中的每个节点通过独立的堆分配取得，内存地址高度离散。遍历链表时，CPU 必须执行**指针追踪（Pointer Chasing）**，每次解引用 ``node->next`` 均会引发一次独立的 Cache Miss，导致流水线停顿数十至上百个时钟周期。

.. list-table:: 连续内存容器与节点式容器的硬件性能与内存开销对照
   :widths: 20 25 25 30
   :header-rows: 1
   :class: tight-table

   * - 维度指标
     - 连续内存容器 (``std::vector<T>``)
     - 节点式容器 (``std::list<T>``)
     - 树形关联容器 (``std::map<K, V>``)
   * - 内存物理拓扑
     - 单一连续虚拟地址块
     - 离散双向链表节点
     - 离散红黑树平衡节点
   * - 单元素额外内存开销
     - 0 字节（仅容量预留损耗）
     - 16 字节（双向指针 ``prev``/``next``）+ Chunk 头部 16B
     - 24 字节（三指针 ``parent``/``left``/``right`` + 颜色）+ Chunk 头部 16B
   * - L1D 缓存命中率
     - 极高（顺序预取流水线满载）
     - 极低（节点离散，频繁 Cache Miss）
     - 极低（树形跳跃寻址）
   * - 内存分配频次
     - $O(\log N)$ 几何级扩容分配
     - $O(N)$ 每次插入均触发系统堆分配
     - $O(N)$ 每次插入均触发系统堆分配

在多核高并发体系下，不当的内存对齐还会引发**伪共享（False Sharing）**。当两个独立线程频繁写入位于同一 64 字节 Cache Line 上的不同独立变量时，CPU 的 MESI 缓存一致性协议将强制在多核心间频繁置无效（Invalidate）并重新传输该 Cache Line，导致吞吐量断崖式下降。C++11 引入 ``alignas`` 与 C++17 引入 ``std::hardware_destructive_interference_size`` 用于隔离跨核心并发变量：

.. code-block:: cpp

   #include <new>

   // 使用 64 字节对齐隔离不同线程的写操作，消除 False Sharing
   struct alignas(64) ThreadWorkerSlot {
       uint64_t sequence_number{0};
       uint64_t processed_counter{0};
   };

为了消除高频小对象分配对全局堆分配器造成的锁竞争（Lock Contention）与内存碎片，高性能系统普遍采用**固定块内存池（Arena / Slab Allocator）**。

下面实现一个基于嵌入式自由链表（Embedded Free-List）的高吞吐 Arena 分配器。该分配器在空闲块内部直接复用存储空间保存 ``next`` 指针，实现零额外元数据开销的 $O(1)$ 分配与释放：

.. code-block:: cpp

   #include <cstddef>
   #include <cstdint>
   #include <new>
   #include <utility>
   #include <vector>

   template <typename T, size_t BlockSize = 4096>
   class FixedArenaAllocator {
   public:
       FixedArenaAllocator() = default;

       ~FixedArenaAllocator() noexcept {
           for (void* block : raw_blocks_) {
               ::operator delete(block);
           }
       }

       // 禁用拷贝以保持物理所有权唯一
       FixedArenaAllocator(const FixedArenaAllocator&) = delete;
       FixedArenaAllocator& operator=(const FixedArenaAllocator&) = delete;

       // O(1) 极速分配一个对象大小的未初始化存储
       [[nodiscard]] T* allocate() {
           if (free_list_head_ == nullptr) {
               grow_arena();
           }
           Node* node = free_list_head_;
           free_list_head_ = free_list_head_->next;
           return reinterpret_cast<T*>(node);
       }

       // O(1) 将存储槽位归还至空闲链表首部
       void deallocate(T* ptr) noexcept {
           if (ptr == nullptr) return;
           Node* node = reinterpret_cast<Node*>(ptr);
           node->next = free_list_head_;
           free_list_head_ = node;
       }

   private:
       // 嵌入式空闲节点：空闲时解释为指针，分配后用作对象存储
       union Node {
           Node* next;
           alignas(alignof(T)) std::byte storage[sizeof(T)];
       };

       static_assert(sizeof(Node) >= sizeof(Node*), "Element size must accommodate free list pointer");

       void grow_arena() {
           constexpr size_t elements_per_block = BlockSize / sizeof(Node);
           static_assert(elements_per_block > 0, "BlockSize too small for element type");

           void* new_block = ::operator new(sizeof(Node) * elements_per_block);
           raw_blocks_.push_back(new_block);

           Node* current = static_cast<Node*>(new_block);
           for (size_t i = 0; i < elements_per_block - 1; ++i) {
               current[i].next = &current[i + 1];
           }
           current[elements_per_block - 1].next = free_list_head_;
           free_list_head_ = current;
       }

       Node* free_list_head_{nullptr};
       std::vector<void*> raw_blocks_;
   };

RAII 哲学与现代智能指针内核拓扑
-------------------------------

RAII（Resource Acquisition Is Initialization，资源获取即初始化）是现代 C++ 资源管理的核心哲学。其核心公理为：**将资源的生命周期严格绑定至拥有该资源的栈对象（或宿主对象）的生命周期**。

在 C++ 编译器运行机制中，当控制流离开当前作用域（无论是正常返回、``break``、``goto`` 还是因异常展开 Stack Unwinding）时，编译器在函数尾部生成的清理代码保证以**严格逆序（Reverse Construction Order）**调用当前作用域内所有局部自动对象的析构函数。

.. code-block:: text

   +-------------------------------------------------------------------------------+
   |               RAII 作用域自动清理与 Stack Unwinding 逆序析构拓扑              |
   +-------------------------------------------------------------------------------+
   | 作用域进入 (Scope Enter)                                                      |
   |   1. 构造 ResA: 申请系统文件句柄 fd = open(...)                              |
   |   2. 构造 ResB: 申请互斥锁 mutex.lock()                                       |
   |   3. 构造 ResC: 申请堆内存 ptr = malloc(...)                                  |
   |                                                                               |
   | 业务执行中... 触发异常 throw std::runtime_error(...) 或 return                 |
   |                                                                               |
   | 作用域退出 (栈展开 Stack Unwinding 阶段，编译器注入严格逆序清理代码)           |
   |   3. 析构 ResC: free(ptr) -> 归还堆内存                                       |
   |   2. 析构 ResB: mutex.unlock() -> 释放并发锁                                  |
   |   1. 析构 ResA: close(fd) -> 关闭系统句柄                                     |
   +-------------------------------------------------------------------------------+

现代 C++ 通过标准智能指针将 RAII 哲学形式化为类型系统约束：

1. **``std::unique_ptr<T, Deleter>``**：
   表达**独占所有权（Exclusive Ownership）**。内部仅持有一个原始指针 ``T*``（在自定义无状态 Deleter 时，通过空基类优化 EBO 或 C++20 ``[[no_unique_address]]`` 实现与原生裸指针相同的 8 字节空间占用与零运行时开销）。拷贝构造与拷贝赋值被显式 ``= delete``，仅支持移动构造与移动赋值。
2. **``std::shared_ptr<T>``**：
   表达**共享所有权（Shared Ownership）**。对象物理内存占用为 16 字节（双指针拓扑）：一个指针指向目标资源 ``T*``，另一个指针指向堆上分配的**控制块（Control Block）**。
3. **``std::weak_ptr<T>``**：
   表达**非拥有弱引用（Non-Owning Reference）**。同样占用 16 字节，指向 ``std::shared_ptr`` 所管理的资源及同一控制块，用于解决循环引用死锁问题。

.. code-block:: text

   +---------------------------------------------------------------------------------------+
   |                std::shared_ptr / std::weak_ptr 双指针与控制块物理拓扑                 |
   +---------------------------------------------------------------------------------------+
   | std::shared_ptr<T> 实例 (16 字节栈存储)                                               |
   |   [ 资源指针: T* ptr ] --------------------+                                          |
   |   [ 控制块指针: ControlBlock* cb ] --------|-------------------+                      |
   |                                            |                   |                      |
   |                                            v                   v                      |
   |                                   +-----------------+  +----------------------------+ |
   |                                   | 目标业务对象 T  |  | 控制块 (Control Block)     | |
   |                                   | [ payload data] |  | - atomic<long> strong_refs | |
   |                                   +-----------------+  | - atomic<long> weak_refs   | |
   |                                                        | - Deleter & Allocator      | |
   |                                                        +----------------------------+ |
   |                                                                ^                      |
   | std::weak_ptr<T> 实例 (16 字节栈存储)                          |                      |
   |   [ 资源指针: T* ptr ] ----------------------------------------+ (用于 lock 提升)     |
   |   [ 控制块指针: ControlBlock* cb ] ----------------------------+                      |
   +---------------------------------------------------------------------------------------+

控制块的生命周期状态机由强引用计数（``strong_refs``）与弱引用计数（``weak_refs``）联合驱动：

- 当某个 ``shared_ptr`` 析构时，执行原子递减 ``fetch_sub(1, memory_order_acq_rel)``。当 ``strong_refs`` 归零时，立即就地调用业务对象的析构函数 ``p->~T()``，释放受控资源。
- 当最后一个指向该控制块的 ``weak_ptr`` 析构时，弱引用计数 ``weak_refs`` 归零，控制块自身的物理内存才被真正释放。

工厂函数 ``std::make_shared<T>(args...)`` 与直接构造 ``std::shared_ptr<T>(new T(args...))`` 存在关键的物理内存布局差异：

.. list-table:: make_shared 单块分配与常规构造双块分配的微观对比
   :widths: 20 25 25 30
   :header-rows: 1
   :class: tight-table

   * - 对比维度
     - ``std::make_shared<T>(args...)``
     - ``std::shared_ptr<T>(new T(args...))``
     - 工程决策影响
   * - 堆分配次数
     - **1 次连续内存分配**（对象与控制块合并）
     - **2 次独立堆分配**（对象 1 次，控制块 1 次）
     - ``make_shared`` 分配延迟降低 50%
   * - 缓存局部性
     - 极高（控制块与对象物理相邻）
     - 较低（对象与控制块物理地址随机分散）
     - ``make_shared`` 减少一次 Cache Miss
   * - 异常安全性
     - 绝对安全（单表达式内原子完成）
     - 潜在泄漏风险（C++17 之前参数求值顺序未定）
     - 推荐优先使用 ``make_shared``
   * - 内存释放时机
     - **延迟释放**：对象已析构，但若有 ``weak_ptr`` 存活，整个单块内存无法归还
     - **即时释放**：对象析构后其物理内存立即释放；控制块独立保留至弱引用清零
     - 大对象且存在长生命周期 ``weak_ptr`` 时选用直接构造

小结与下章导读
--------------

本章系统解构了现代 C++ 物理内存管理体系与 RAII 哲学：从 Linux 虚拟地址空间布局与 ``brk`` / ``mmap`` 系统调用，到 C 运行时堆分配器的 Chunk 拓扑与对齐约束；从 ``new`` / ``delete`` 表达式在编译期的两阶段降解与数组 Cookie 机制，到 Placement New 与未初始化内存批量算法的强异常安全回滚保证；从 CPU 多级高速缓存、Cache Line 空间局部性与高性能 Arena 内存池架构，到 RAII 作用域逆序析构保证与现代智能指针的控制块拓扑。

掌握了底层物理内存拓扑与生命周期边界后，下一章我们将正式切入 **泛型模板底层基石：实例化机制、参数推导、变长参数包展开、依赖类型 typename 与二阶段名字查找（05_template_instantiation_and_two_phase_lookup.rst）**，系统解析编译期 AST 实例化流程、模板实参推导（CTAD）、折叠表达式机器指令生成以及 SFINAE 的底层编译期判定准则。
