====================================================================================================================
工业级 Mini-Vector 与 Mini-Deque 实战：三指针模型、几何扩容、move_if_noexcept 迁移与中控 map 缓冲区
====================================================================================================================

.. note:: 前置背景与上下文承接
   在上一节（``01_mini_allocator_and_uninitialized_memory.rst``）中，我们完成了原始堆内存管理与对象生命周期的微架构解耦，确立了 ``allocate`` / ``deallocate`` 与 ``construct`` / ``destroy`` 的四阶段分流模型，并构建了具备强异常安全回滚能力的未初始化内存算法。本节正式进入 STL 核心顺序容器的工程落地阶段。动态连续数组（``std::vector``）与双端分段队列（``std::deque``）是现代系统级编程中最高频使用的序列存储结构。两者代表了截然不同的物理布局哲学：前者追求绝对的连续内存以榨干 CPU 缓存行（Cache Line）与 SIMD 预取吞吐，代价是扩容时的整体搬迁与首部插入的线性移动；后者通过两级指针中控架构（Map-and-Chunks）达成首尾两端的均摊常数级插入与删除，化解了大块连续虚存分配的压力。本节将深入两者的微架构核心，完整实现自包含、工业级严谨的 ``MiniVector`` 与 ``MiniDeque``。

Mini-Vector 连续内存动态数组核心微架构
--------------------------------------

``std::vector`` 的物理实现建立在一段严格连续的线性地址空间之上。为了以极低的元数据开销精确维护容器状态，工业级实现普遍采用经典的三指针模型。

三指针状态模型与寻址映射
~~~~~~~~~~~~~~~~~~~~~~~~

在 64 位体系结构下，``MiniVector`` 内部仅维护三个同类型的原生指针，对象本体尺寸固定为 24 字节：

.. code-block:: cpp

   T* start_;          // 指向首个有效元素的起始物理地址
   T* finish_;         // 指向最后一个有效元素之后的下一个未构造槽位
   T* end_of_storage_; // 指向当前已分配原始内存空间的尾后边界

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        Mini-Vector 三指针内存物理拓扑                       |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   start_                                finish_          end_of_storage_    |
   |     |                                      |                    |           |
   |     v                                      v                    v           |
   |   +----------+----------+----------+-----+----+----+-----+----+----+         |
   |   | Object 0 | Object 1 | Object 2 | ... | Uninitialized Memory |         |
   |   +----------+----------+----------+-----+----+----+-----+----+----+         |
   |   <----------- size() = finish_ - start_ ----><- spare capacity ->          |
   |   <------------------ capacity() = end_of_storage_ - start_ ------>          |
   |                                                                             |
   +-----------------------------------------------------------------------------+

基于指针算术，全部核心维度查询均在 $\mathcal{O}(1)$ 常数时间内完成：

1. **尺寸计算**：``size() = static_cast<size_type>(finish_ - start_)``。
2. **容量计算**：``capacity() = static_cast<size_type>(end_of_storage_ - start_)``。
3. **空判定**：``empty() = (start_ == finish_)``。
4. **随机访问**：``operator[](n)`` 编译为单指令基址变址寻址 ``*(start_ + n)``，与原生数组性能完全等价。

几何级扩容数学推导与重分配事务
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当调用 ``push_back`` 或 ``emplace_back`` 且满足 ``finish_ == end_of_storage_`` 时，必须触发底层存储重分配。动态数组保持 $\mathcal{O}(1)$ 均摊复杂度的核心在于**按几何级数增长容量**。

设初始容量为 $C_0$，扩容增长因子为 $k$。连续追加 $N$ 个元素时触发 $\approx \log_k N$ 次扩容。搬迁元素的总操作次数为：

.. math::

   T(N) = \sum_{i=1}^{\lfloor \log_k N \rfloor} C_0 \cdot k^i = C_0 \cdot \frac{k^{\lfloor \log_k N \rfloor + 1} - k}{k - 1} \approx \frac{k}{k - 1} N

单次插入操作的均摊时间复杂度为常数阶：

.. math::

   T_{	ext{amortized}} = \frac{T(N)}{N} \approx \frac{k}{k - 1} = \mathcal{O}(1)

对于增长因子的工程选取：
- **$k = 2.0$（GCC libstdc++ / Clang libc++）**：推导与位移指令映射简单，单次重分配后提供充足的富余槽位；
- **$k = 1.5$（MSVC STL）**：满足黄金分割方程 $k \le \frac{1 + \sqrt{5}}{2} \approx 1.618$，使得第 $j$ 次扩容申请的新空间能够复用前 $j-1$ 次释放归还操作系统的内存碎片，显著提升虚拟内存页的重用率。

在我们的 ``MiniVector`` 中，选取 $k = 2.0$ 作为基准几何增长律，空容器扩容初始容量设置为 1。

move_if_noexcept 条件迁移与强异常安全保证
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

扩容重分配涉及三个逻辑步骤：
1. 分配容量为原先 2 倍的新原始存储块；
2. 在新空间对应位置构造待插入的新元素；
3. 将旧空间内的已有有效对象搬迁至新空间。

在第 3 步搬迁过程中，若直接使用移动构造函数（``std::move``），一旦某个对象的移动构造函数抛出异常，旧空间中的部分对象已被破坏性挪走（处于 moved-from 状态），新空间未完全构造成功，容器将陷入不可逆的中间破坏状态，破坏了强异常安全保证（Strong Exception Safety Guarantee）。

标准库确立了基于 ``std::move_if_noexcept`` 的安全契约：
- 若元素类型 ``T`` 声明了不抛出异常的移动构造函数（``std::is_nothrow_move_constructible_v<T> == true``），或者该类型不可拷贝（``std::is_copy_constructible_v<T> == false``），系统采用右值移动迁移，达成零资源拷贝的高吞吐；
- 若类型的移动构造函数可能抛出异常且其具备拷贝构造函数，系统强制回退采用左值拷贝构造。一旦构造过程中断抛出异常，新内存空间执行已构造元素的逆序析构并释放，旧空间中的所有对象保持完好无损，容器恢复到调用前的状态。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                  Mini-Vector 扩容与强异常安全迁移状态机                     |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 旧缓冲区: N 个有效元素 ]                                                |
   |         |                                                                   |
   |         | 1. allocate(2 * N)                                                |
   |         v                                                                   |
   |   [ 新原始内存空间 ]                                                        |
   |         |                                                                   |
   |         | 2. 在新空间索引 N 处原位构造新元素 (emplace_back 目标)            |
   |         v                                                                   |
   |         +-- 抛出异常? --> 析构新元素，deallocate 新空间，原 vector 保持不变 |
   |         | (成功)                                                            |
   |         v                                                                   |
   |   [ 3. 元素条件迁移: uninitialized_move_if_noexcept ]                       |
   |         |                                                                   |
   |         +-- 抛出异常? (仅发生在拷贝回退路径)                                |
   |         |       |                                                           |
   |         |       v                                                           |
   |         |   逆序销毁新空间已构造项 -> deallocate 新空间 -> 旧空间完全未受损 |
   |         | (完全成功)                                                        |
   |         v                                                                   |
   |   [ 4. 提交指针切换 ]                                                       |
   |         - 析构旧空间全部 N 个对象 (p->~T())                                 |
   |         - deallocate 旧空间                                                 |
   |         - start_ = new_start; finish_ = new_finish; end_of_storage_ = ...   |
   |                                                                             |
   +-----------------------------------------------------------------------------+

Mini-Deque 双端队列分段中控架构核心微架构
-----------------------------------------

与 ``std::vector`` 的连续空间不同，``std::deque`` 采用**分段连续（Piecewise Continuous）**架构。它通过二级间接寻址，在逻辑上向用户暴露线性随机访问接口，而在物理上由多块定长缓冲区（Chunk / Block Buffer）离散分布构成。

中控指针数组（Map）与定长数据缓冲区（Chunk）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``MiniDeque`` 的核心控制结构由两层组成：
1. **中控数组（Map）**：一段连续存储的指针数组（类型为 ``T**``），其每个槽位存储一个指向固定尺寸数据缓冲区的原生指针；
2. **数据块缓冲区（Chunk）**：一段分配在堆上的连续数组（尺寸固定为 ``CHUNK_SIZE``，如 512 字节或固定元素个数，例如 8 个槽位），容纳实际元素。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        Mini-Deque 内存物理拓扑架构                          |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   map_ (中控指针数组, T**)                                                  |
   |     |                                                                       |
   |     +---> [ Node 0 (nullptr) ]                                              |
   |     |                                                                       |
   |     +---> [ Node 1 ] ------> [ Chunk 1: [e0] [e1] [e2] [e3] ]               |
   |     |                                    ^                                  |
   |     |                                    | start_                           |
   |     +---> [ Node 2 ] ------> [ Chunk 2: [e4] [e5] [e6] [e7] ]               |
   |     |                                                                       |
   |     +---> [ Node 3 ] ------> [ Chunk 3: [e8] [e9] [  ] [  ] ]               |
   |     |                                              ^                        |
   |     |                                              | finish_                |
   |     +---> [ Node 4 (nullptr) ]                                              |
   |                                                                             |
   +-----------------------------------------------------------------------------+

四指针复合随机访问迭代器拓扑
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了让离散分段的物理空间支持全局指针算术与随机访问，``MiniDeque`` 的迭代器内部必须封装四个定位指针：

.. code-block:: cpp

   template <typename T>
   struct DequeIterator {
       T* cur;      // 指向当前正在访问的具体元素
       T* first;    // 指向当前 Chunk 的起始物理边界
       T* last;     // 指向当前 Chunk 的尾后物理边界（first + CHUNK_SIZE）
       T** node;    // 指向中控数组中记录本 Chunk 指针的槽位地址
   };

跨越缓冲区边界跳转函数 ``set_node``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

当迭代器自增步进触发 ``cur == last`` 时，表示当前数据块已遍历完毕，迭代器必须跃迁至下一个中控节点：

.. code-block:: cpp

   void set_node(T** new_node) noexcept {
       node = new_node;
       first = *new_node;
       last = first + CHUNK_SIZE;
   }

前向步进运算符实现：

.. code-block:: cpp

   DequeIterator& operator++() noexcept {
       ++cur;
       if (cur == last) {
           set_node(node + 1);
           cur = first;
       }
       return *this;
   }

随机访问常数时间寻址计算
~~~~~~~~~~~~~~~~~~~~~~~~

尽管物理存储离散，``MiniDeque`` 的全局随机访问依然保持严格的 $\mathcal{O}(1)$ 复杂度。设当前偏移量为 $k$（从 ``start_`` 起算），寻址公式如下：

.. math::

   	ext{total\_offset} = (start\_.cur - start\_.first) + k

.. math::

   	ext{chunk\_delta} = \frac{	ext{total\_offset}}{	ext{CHUNK\_SIZE}}

.. math::

   	ext{element\_offset} = 	ext{total\_offset} \pmod{	ext{CHUNK\_SIZE}}

目标元素物理地址：

.. math::

   	ext{target\_ptr} = *(start\_.node + 	ext{chunk\_delta}) + 	ext{element\_offset}

整个过程仅涉及一次乘法、一次除法、一次取模与两次内存加载，无任何循环遍历开销。

两端常数插入与中控 Map 浅层重分配
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``MiniDeque`` 支持首尾两端的对称常数时间推入与弹出：
- **尾部推入（push_back）**：当 ``finish_.cur != finish_.last - 1`` 时，直接在 ``finish_.cur`` 原位构造并递增指针；若当前块满，在中控数组下一个节点申请新 Chunk 并重置 ``finish_``；
- **首部推入（push_front）**：当 ``start_.cur != start_.first`` 时，递减 ``start_.cur`` 并在该空闲槽位原位构造；若当前块首无空位，在中控数组前一个节点申请新 Chunk 并重置 ``start_``。

当首端或尾端的中控节点用尽（``start_.node == map_`` 或 ``finish_.node == map_ + map_size_ - 1``）时，中控数组触发扩容。需要特别指出：**中控数组扩容仅重新分配存储 Chunk 指针的连续数组，原有的各个数据 Chunk 物理内存绝不发生任何挪动与重新分配**。新中控数组将已有节点指针整体拷贝至正中央，预留两端对等的空槽，耗时极低且彻底消除了元素移动开销。

.. list-table:: Mini-Vector 与 Mini-Deque 微架构物理特性全方位对比
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 核心维度
     - Mini-Vector（动态连续数组）
     - Mini-Deque（分段中控双端队列）
   * - **物理存储拓扑**
     - 单一线性完全连续内存块
     - 二级映射：连续中控指针数组 + 多块定长缓冲区
   * - **对象尺寸开销**
     - 24 字节（3 个裸指针）
     - 64 字节（2 个迭代器各 32 字节 + 中控指针 + 容量）
   * - **扩容与重分配成本**
     - 高：需申请 2 倍新空间并全量迁移已有元素
     - 极低：仅浅拷贝中控指针，已有数据块物理地址恒定不动
   * - **首端插入（push_front）**
     - 极高：$\mathcal{O}(N)$ 线性全体后移
     - 均摊常数阶：$\mathcal{O}(1)$，仅在块满时分配单个新 Chunk
   * - **尾端插入（push_back）**
     - 均摊常数阶：$\mathcal{O}(1)$，满时触发全量搬迁
     - 均摊常数阶：$\mathcal{O}(1)$，满时仅分配单个新 Chunk
   * - **CPU 缓存与 SIMD 局部性**
     - 最优：内存绝对连续，硬件预取器效率最大化
     - 良好：块内连续，跨块处触发微小的不连续惩罚
   * - **迭代器与引用失效准则**
     - 扩容时全部失效；未扩容插入时插入点之后失效
     - 两端插入仅使迭代器失效，元素指针与引用绝对有效

自包含 MiniVector 与 MiniDeque 工业级实现
----------------------------------------

以下提供自包含、无外部依赖的 ``MiniVector`` 与 ``MiniDeque`` 工业级实现，配套完整的生命周期追踪器与自动化单元测试套件。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <cstddef>
   #include <new>
   #include <utility>
   #include <type_traits>
   #include <cassert>
   #include <stdexcept>
   #include <algorithm>
   #include <memory>

   namespace mini_stl {

   // =========================================================================
   // 1. 工业级自包含 MiniVector<T> 实现
   // =========================================================================

   template <typename T>
   class MiniVector {
   public:
       using value_type = T;
       using size_type = std::size_t;
       using difference_type = std::ptrdiff_t;
       using reference = T&;
       using const_reference = const T&;
       using pointer = T*;
       using const_pointer = const T*;
       using iterator = T*;
       using const_iterator = const T*;

   private:
       pointer start_{nullptr};
       pointer finish_{nullptr};
       pointer end_of_storage_{nullptr};

       void deallocate_storage() noexcept {
           if (start_ != nullptr) {
               ::operator delete(static_cast<void*>(start_));
               start_ = finish_ = end_of_storage_ = nullptr;
           }
       }

       void destroy_elements(pointer first, pointer last) noexcept {
           for (; first != last; ++first) {
               first->~T();
           }
       }

   public:
       constexpr MiniVector() noexcept = default;

       explicit MiniVector(size_type count, const T& value = T()) {
           if (count > 0) {
               start_ = static_cast<pointer>(::operator new(count * sizeof(T)));
               finish_ = start_;
               end_of_storage_ = start_ + count;
               try {
                   for (size_type i = 0; i < count; ++i) {
                       ::new (static_cast<void*>(finish_)) T(value);
                       ++finish_;
                   }
               } catch (...) {
                   destroy_elements(start_, finish_);
                   deallocate_storage();
                   throw;
               }
           }
       }

       ~MiniVector() noexcept {
           clear();
           deallocate_storage();
       }

       // 拷贝构造函数
       MiniVector(const MiniVector& other) {
           const size_type count = other.size();
           if (count > 0) {
               start_ = static_cast<pointer>(::operator new(count * sizeof(T)));
               finish_ = start_;
               end_of_storage_ = start_ + count;
               try {
                   for (pointer src = other.start_; src != other.finish_; ++src) {
                       ::new (static_cast<void*>(finish_)) T(*src);
                       ++finish_;
                   }
               } catch (...) {
                   destroy_elements(start_, finish_);
                   deallocate_storage();
                   throw;
               }
           }
       }

       // 移动构造函数：零拷贝接管
       MiniVector(MiniVector&& other) noexcept
           : start_(other.start_), finish_(other.finish_), end_of_storage_(other.end_of_storage_) {
           other.start_ = other.finish_ = other.end_of_storage_ = nullptr;
       }

       // 拷贝赋值运算符
       MiniVector& operator=(const MiniVector& other) {
           if (this != &other) {
               MiniVector temp(other);
               swap(temp);
           }
           return *this;
       }

       // 移动赋值运算符
       MiniVector& operator=(MiniVector&& other) noexcept {
           if (this != &other) {
               clear();
               deallocate_storage();
               start_ = other.start_;
               finish_ = other.finish_;
               end_of_storage_ = other.end_of_storage_;
               other.start_ = other.finish_ = other.end_of_storage_ = nullptr;
           }
           return *this;
       }

       void swap(MiniVector& other) noexcept {
           std::swap(start_, other.start_);
           std::swap(finish_, other.finish_);
           std::swap(end_of_storage_, other.end_of_storage_);
       }

       [[nodiscard]] size_type size() const noexcept {
           return static_cast<size_type>(finish_ - start_);
       }

       [[nodiscard]] size_type capacity() const noexcept {
           return static_cast<size_type>(end_of_storage_ - start_);
       }

       [[nodiscard]] bool empty() const noexcept {
           return start_ == finish_;
       }

       reference operator[](size_type index) noexcept {
           return *(start_ + index);
       }

       const_reference operator[](size_type index) const noexcept {
           return *(start_ + index);
       }

       reference at(size_type index) {
           if (index >= size()) {
               throw std::out_of_range("MiniVector::at out of range");
           }
           return *(start_ + index);
       }

       reference front() noexcept { return *start_; }
       const_reference front() const noexcept { return *start_; }
       reference back() noexcept { return *(finish_ - 1); }
       const_reference back() const noexcept { return *(finish_ - 1); }

       iterator begin() noexcept { return start_; }
       const_iterator begin() const noexcept { return start_; }
       iterator end() noexcept { return finish_; }
       const_iterator end() const noexcept { return finish_; }

       void clear() noexcept {
           destroy_elements(start_, finish_);
           finish_ = start_;
       }

       void reserve(size_type new_cap) {
           if (new_cap <= capacity()) {
               return;
           }
           reallocate(new_cap);
       }

       template <typename... Args>
       reference emplace_back(Args&&... args) {
           if (finish_ == end_of_storage_) {
               const size_type new_cap = (capacity() == 0) ? 1 : capacity() * 2;
               reallocate_and_emplace(new_cap, std::forward<Args>(args)...);
           } else {
               ::new (static_cast<void*>(finish_)) T(std::forward<Args>(args)...);
               ++finish_;
           }
           return back();
       }

       void push_back(const T& value) {
           emplace_back(value);
       }

       void push_back(T&& value) {
           emplace_back(std::move(value));
       }

       void pop_back() noexcept {
           assert(!empty());
           --finish_;
           finish_->~T();
       }

   private:
       void reallocate(size_type new_cap) {
           pointer new_start = static_cast<pointer>(::operator new(new_cap * sizeof(T)));
           pointer new_finish = new_start;

           try {
               for (pointer p = start_; p != finish_; ++p) {
                   if constexpr (std::is_nothrow_move_constructible_v<T> || !std::is_copy_constructible_v<T>) {
                       ::new (static_cast<void*>(new_finish)) T(std::move(*p));
                   } else {
                       ::new (static_cast<void*>(new_finish)) T(*p);
                   }
                   ++new_finish;
               }
           } catch (...) {
               destroy_elements(new_start, new_finish);
               ::operator delete(static_cast<void*>(new_start));
               throw;
           }

           destroy_elements(start_, finish_);
           deallocate_storage();

           start_ = new_start;
           finish_ = new_finish;
           end_of_storage_ = new_start + new_cap;
       }

       template <typename... Args>
       void reallocate_and_emplace(size_type new_cap, Args&&... args) {
           pointer new_start = static_cast<pointer>(::operator new(new_cap * sizeof(T)));
           pointer new_finish = new_start;

           try {
               // 1. 先在新空间尾部构造新元素
               pointer emplace_pos = new_start + size();
               ::new (static_cast<void*>(emplace_pos)) T(std::forward<Args>(args)...);

               // 2. 迁移已有元素
               for (pointer p = start_; p != finish_; ++p) {
                   if constexpr (std::is_nothrow_move_constructible_v<T> || !std::is_copy_constructible_v<T>) {
                       ::new (static_cast<void*>(new_finish)) T(std::move(*p));
                   } else {
                       ::new (static_cast<void*>(new_finish)) T(*p);
                   }
                   ++new_finish;
               }
               // 将指针越过新构造的元素
               ++new_finish;
           } catch (...) {
               destroy_elements(new_start, new_finish);
               ::operator delete(static_cast<void*>(new_start));
               throw;
           }

           destroy_elements(start_, finish_);
           deallocate_storage();

           start_ = new_start;
           finish_ = new_finish;
           end_of_storage_ = new_start + new_cap;
       }
   };

   // =========================================================================
   // 2. 工业级自包含 MiniDeque<T> 实现
   // =========================================================================

   template <typename T>
   class MiniDeque {
   public:
       using value_type = T;
       using size_type = std::size_t;
       using difference_type = std::ptrdiff_t;
       using reference = T&;
       using const_reference = const T&;
       using pointer = T*;
       using const_pointer = const T*;

       // 每个数据块固定包含 4 个元素，便于测试边界跨越与重分配
       static constexpr size_type CHUNK_SIZE = 4;

       // ---------------------------------------------------------------------
       // 复合随机访问迭代器
       // ---------------------------------------------------------------------
       struct Iterator {
           using iterator_category = std::random_access_iterator_tag;
           using value_type = T;
           using difference_type = std::ptrdiff_t;
           using pointer = T*;
           using reference = T&;

           T* cur{nullptr};
           T* first{nullptr};
           T* last{nullptr};
           T** node{nullptr};

           Iterator() noexcept = default;
           Iterator(T* c, T** n) noexcept : cur(c), node(n) {
               if (n != nullptr) {
                   first = *n;
                   last = first + CHUNK_SIZE;
               }
           }

           void set_node(T** new_node) noexcept {
               node = new_node;
               first = *new_node;
               last = first + CHUNK_SIZE;
           }

           reference operator*() const noexcept { return *cur; }
           pointer operator->() const noexcept { return cur; }

           Iterator& operator++() noexcept {
               ++cur;
               if (cur == last) {
                   set_node(node + 1);
                   cur = first;
               }
               return *this;
           }

           Iterator operator++(int) noexcept {
               Iterator tmp = *this;
               ++(*this);
               return tmp;
           }

           Iterator& operator--() noexcept {
               if (cur == first) {
                   set_node(node - 1);
                   cur = last;
               }
               --cur;
               return *this;
           }

           Iterator operator--(int) noexcept {
               Iterator tmp = *this;
               --(*this);
               return tmp;
           }

           Iterator& operator+=(difference_type n) noexcept {
               const difference_type offset = n + (cur - first);
               if (offset >= 0 && offset < static_cast<difference_type>(CHUNK_SIZE)) {
                   cur += n;
               } else {
                   const difference_type node_offset = (offset > 0)
                       ? (offset / static_cast<difference_type>(CHUNK_SIZE))
                       : (-((-offset - 1) / static_cast<difference_type>(CHUNK_SIZE)) - 1);
                   set_node(node + node_offset);
                   cur = first + (offset - node_offset * static_cast<difference_type>(CHUNK_SIZE));
               }
               return *this;
           }

           Iterator operator+(difference_type n) const noexcept {
               Iterator tmp = *this;
               tmp += n;
               return tmp;
           }

           Iterator& operator-=(difference_type n) noexcept {
               return *this += (-n);
           }

           Iterator operator-(difference_type n) const noexcept {
               Iterator tmp = *this;
               tmp -= n;
               return tmp;
           }

           difference_type operator-(const Iterator& other) const noexcept {
               return static_cast<difference_type>(CHUNK_SIZE) * (node - other.node) +
                      (cur - first) - (other.cur - other.first);
           }

           reference operator[](difference_type n) const noexcept {
               return *(*this + n);
           }

           bool operator==(const Iterator& other) const noexcept { return cur == other.cur; }
           bool operator!=(const Iterator& other) const noexcept { return cur != other.cur; }
           bool operator<(const Iterator& other) const noexcept {
               return (node == other.node) ? (cur < other.cur) : (node < other.node);
           }
       };

       using iterator = Iterator;

   private:
       T** map_{nullptr};
       size_type map_size_{0};
       iterator start_;
       iterator finish_;

       pointer allocate_chunk() {
           return static_cast<pointer>(::operator new(CHUNK_SIZE * sizeof(T)));
       }

       void deallocate_chunk(pointer p) noexcept {
           if (p != nullptr) {
               ::operator delete(static_cast<void*>(p));
           }
       }

       void create_map_and_nodes(size_type num_elements) {
           const size_type num_nodes = num_elements / CHUNK_SIZE + 1;
           map_size_ = std::max<size_type>(8, num_nodes + 2);
           map_ = static_cast<T**>(::operator new(map_size_ * sizeof(T*)));
           for (size_type i = 0; i < map_size_; ++i) {
               map_[i] = nullptr;
           }

           T** nstart = map_ + (map_size_ - num_nodes) / 2;
           T** nfinish = nstart + num_nodes;

           for (T** cur = nstart; cur < nfinish; ++cur) {
               *cur = allocate_chunk();
           }

           start_.set_node(nstart);
           start_.cur = start_.first;
           finish_.set_node(nfinish - 1);
           finish_.cur = finish_.first + (num_elements % CHUNK_SIZE);
       }

       void reallocate_map(size_type nodes_to_add, bool add_at_front) {
           const size_type old_num_nodes = finish_.node - start_.node + 1;
           const size_type new_num_nodes = old_num_nodes + nodes_to_add;

           T** new_nstart = nullptr;
           if (map_size_ > 2 * new_num_nodes) {
               // 现有 map 足够大，直接在内部向中部做浅层指针移动
               new_nstart = map_ + (map_size_ - new_num_nodes) / 2 + (add_at_front ? nodes_to_add : 0);
               if (new_nstart < start_.node) {
                   std::copy(start_.node, finish_.node + 1, new_nstart);
               } else {
                   std::copy_backward(start_.node, finish_.node + 1, new_nstart + old_num_nodes);
               }
           } else {
               // 申请 2 倍新 map 空间
               const size_type new_map_size = map_size_ + std::max(map_size_, nodes_to_add) + 2;
               T** new_map = static_cast<T**>(::operator new(new_map_size * sizeof(T*)));
               for (size_type i = 0; i < new_map_size; ++i) {
                   new_map[i] = nullptr;
               }

               new_nstart = new_map + (new_map_size - new_num_nodes) / 2 + (add_at_front ? nodes_to_add : 0);
               std::copy(start_.node, finish_.node + 1, new_nstart);

               ::operator delete(static_cast<void*>(map_));
               map_ = new_map;
               map_size_ = new_map_size;
           }

           start_.set_node(new_nstart);
           finish_.set_node(new_nstart + old_num_nodes - 1);
       }

   public:
       MiniDeque() {
           create_map_and_nodes(0);
       }

       ~MiniDeque() noexcept {
           clear();
           if (start_.node != nullptr) {
               deallocate_chunk(*start_.node);
           }
           if (map_ != nullptr) {
               ::operator delete(static_cast<void*>(map_));
           }
       }

       // 移动构造函数
       MiniDeque(MiniDeque&& other) noexcept
           : map_(other.map_), map_size_(other.map_size_),
             start_(other.start_), finish_(other.finish_) {
           other.map_ = nullptr;
           other.map_size_ = 0;
           other.start_ = iterator();
           other.finish_ = iterator();
       }

       // 移动赋值运算符
       MiniDeque& operator=(MiniDeque&& other) noexcept {
           if (this != &other) {
               clear();
               if (start_.node != nullptr) {
                   deallocate_chunk(*start_.node);
               }
               if (map_ != nullptr) {
                   ::operator delete(static_cast<void*>(map_));
               }

               map_ = other.map_;
               map_size_ = other.map_size_;
               start_ = other.start_;
               finish_ = other.finish_;

               other.map_ = nullptr;
               other.map_size_ = 0;
               other.start_ = iterator();
               other.finish_ = iterator();
           }
           return *this;
       }

       [[nodiscard]] size_type size() const noexcept {
           return static_cast<size_type>(finish_ - start_);
       }

       [[nodiscard]] bool empty() const noexcept {
           return finish_ == start_;
       }

       iterator begin() noexcept { return start_; }
       iterator end() noexcept { return finish_; }

       reference operator[](size_type n) noexcept {
           return start_[static_cast<difference_type>(n)];
       }

       const_reference operator[](size_type n) const noexcept {
           return start_[static_cast<difference_type>(n)];
       }

       reference front() noexcept { return *start_; }
       const_reference front() const noexcept { return *start_; }
       reference back() noexcept { return *(finish_ - 1); }
       const_reference back() const noexcept { return *(finish_ - 1); }

       template <typename... Args>
       reference emplace_back(Args&&... args) {
           if (finish_.cur != finish_.last - 1) {
               ::new (static_cast<void*>(finish_.cur)) T(std::forward<Args>(args)...);
               ++finish_.cur;
           } else {
               // 当前块只剩最后一个槽位，构造后切换到下一个块
               ::new (static_cast<void*>(finish_.cur)) T(std::forward<Args>(args)...);
               if (finish_.node == map_ + map_size_ - 1) {
                   reallocate_map(1, false);
               }
               *(finish_.node + 1) = allocate_chunk();
               finish_.set_node(finish_.node + 1);
               finish_.cur = finish_.first;
           }
           return back();
       }

       void push_back(const T& value) {
           emplace_back(value);
       }

       void push_back(T&& value) {
           emplace_back(std::move(value));
       }

       template <typename... Args>
       reference emplace_front(Args&&... args) {
           if (start_.cur != start_.first) {
               --start_.cur;
               ::new (static_cast<void*>(start_.cur)) T(std::forward<Args>(args)...);
           } else {
               // 当前首块已满，需要往前分配新块
               if (start_.node == map_) {
                   reallocate_map(1, true);
               }
               *(start_.node - 1) = allocate_chunk();
               start_.set_node(start_.node - 1);
               start_.cur = start_.last - 1;
               ::new (static_cast<void*>(start_.cur)) T(std::forward<Args>(args)...);
           }
           return front();
       }

       void push_front(const T& value) {
           emplace_front(value);
       }

       void push_front(T&& value) {
           emplace_front(std::move(value));
       }

       void pop_back() noexcept {
           assert(!empty());
           if (finish_.cur != finish_.first) {
               --finish_.cur;
               finish_.cur->~T();
           } else {
               // 回退到前一个数据块的末尾槽位
               deallocate_chunk(*finish_.node);
               finish_.set_node(finish_.node - 1);
               finish_.cur = finish_.last - 1;
               finish_.cur->~T();
           }
       }

       void pop_front() noexcept {
           assert(!empty());
           start_.cur->~T();
           if (start_.cur != start_.last - 1) {
               ++start_.cur;
           } else {
               // 释放当前空置的数据块并跃迁至下一个块
               pointer old_chunk = *start_.node;
               start_.set_node(start_.node + 1);
               start_.cur = start_.first;
               deallocate_chunk(old_chunk);
           }
       }

       void clear() noexcept {
           for (T** n = start_.node + 1; n < finish_.node; ++n) {
               for (pointer p = *n; p < *n + CHUNK_SIZE; ++p) {
                   p->~T();
               }
               deallocate_chunk(*n);
           }

           if (start_.node != finish_.node) {
               for (pointer p = start_.cur; p < start_.last; ++p) {
                   p->~T();
               }
               for (pointer p = finish_.first; p < finish_.cur; ++p) {
                   p->~T();
               }
               deallocate_chunk(*finish_.node);
           } else {
               for (pointer p = start_.cur; p < finish_.cur; ++p) {
                   p->~T();
               }
           }
           finish_ = start_;
       }
   };

   } // namespace mini_stl

   // =========================================================================
   // 3. 单元测试驱动与微架构验证套件
   // =========================================================================

   namespace test {

   struct TrackedItem {
       static inline int active_count = 0;
       static inline int total_constructs = 0;
       static inline int move_constructs = 0;
       static inline int copy_constructs = 0;
       static inline int destructs = 0;

       int value{0};

       static void reset() noexcept {
           active_count = 0;
           total_constructs = 0;
           move_constructs = 0;
           copy_constructs = 0;
           destructs = 0;
       }

       explicit TrackedItem(int v = 0) noexcept : value(v) {
           ++active_count;
           ++total_constructs;
       }

       TrackedItem(const TrackedItem& other) noexcept : value(other.value) {
           ++active_count;
           ++total_constructs;
           ++copy_constructs;
       }

       TrackedItem(TrackedItem&& other) noexcept : value(other.value) {
           ++active_count;
           ++total_constructs;
           ++move_constructs;
           other.value = -1;
       }

       ~TrackedItem() noexcept {
           --active_count;
           ++destructs;
       }

       TrackedItem& operator=(const TrackedItem& other) noexcept {
           value = other.value;
           return *this;
       }

       TrackedItem& operator=(TrackedItem&& other) noexcept {
           value = other.value;
           other.value = -1;
           return *this;
       }
   };

   inline void runSequenceContainerTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " Mini-Vector 与 Mini-Deque 微架构工程验证套件
";
       std::cout << "=======================================================

";

       // ---------------------------------------------------------------------
       // 1. MiniVector 几何扩容与 move_if_noexcept 验证
       // ---------------------------------------------------------------------
       std::cout << "[测试 1: MiniVector 几何扩容与不抛异常移动迁移验证]:
";
       TrackedItem::reset();
       {
           mini_stl::MiniVector<TrackedItem> vec;
           assert(vec.empty());
           assert(vec.capacity() == 0);

           for (int i = 0; i < 10; ++i) {
               vec.emplace_back(i * 10);
           }

           assert(vec.size() == 10);
           assert(vec.capacity() >= 10);
           assert(vec[0].value == 0);
           assert(vec[9].value == 90);
           assert(TrackedItem::copy_constructs == 0); // 声明为 noexcept 移动构造，绝不触发拷贝
           assert(TrackedItem::move_constructs > 0);   // 扩容迁移均走右值移动

           std::cout << "  - 10 次 emplace_back 后容量: " << vec.capacity() << "
";
           std::cout << "  - 触发的移动构造次数: " << TrackedItem::move_constructs 
                     << "，拷贝构造次数: " << TrackedItem::copy_constructs << " (零拷贝保证)。
";

           // 弹出末尾元素测试
           vec.pop_back();
           assert(vec.size() == 9);
           assert(vec.back().value == 80);
       }
       assert(TrackedItem::active_count == 0); // 退出作用域后对象完全平衡析构
       std::cout << "  - MiniVector 作用域析构完成，内存完全回收，存活对象归零。

";

       // ---------------------------------------------------------------------
       // 2. MiniDeque 两端推入与分段缓冲区跨界验证
       // ---------------------------------------------------------------------
       std::cout << "[测试 2: MiniDeque 双端推入、Chunk 跨界与随机访问验证]:
";
       TrackedItem::reset();
       {
           mini_stl::MiniDeque<TrackedItem> deq;
           assert(deq.empty());
           assert(deq.size() == 0);

           // 尾部插入 6 个元素（CHUNK_SIZE 为 4，跨越至少 2 个 Chunk）
           for (int i = 0; i < 6; ++i) {
               deq.push_back(TrackedItem(i + 1));
           }

           // 首部插入 6 个元素（向前分配新 Chunk）
           for (int i = 0; i < 6; ++i) {
               deq.push_front(TrackedItem(-(i + 1)));
           }

           assert(deq.size() == 12);
           std::cout << "  - 双端混合插入 12 项完成，当前尺寸: " << deq.size() << "
";

           // 验证随机下标寻址是否严格连续单调
           // 预期序列: -6, -5, -4, -3, -2, -1, 1, 2, 3, 4, 5, 6
           int expected[] = {-6, -5, -4, -3, -2, -1, 1, 2, 3, 4, 5, 6};
           for (std::size_t i = 0; i < deq.size(); ++i) {
               assert(deq[i].value == expected[i]);
           }
           std::cout << "  - 二级映射 operator[](n) 全量二分/跨 Chunk 寻址断言通过。
";

           // 验证迭代器遍历与指针算术
           int count = 0;
           for (auto it = deq.begin(); it != deq.end(); ++it) {
               assert(it->value == expected[count]);
               assert(deq.begin()[count].value == expected[count]);
               ++count;
           }
           assert(count == 12);
           std::cout << "  - 复合随机访问迭代器 Forward 步进与跨界跃迁验证成功。
";

           // 双端弹出验证
           deq.pop_front();
           assert(deq.front().value == -5);
           deq.pop_back();
           assert(deq.back().value == 5);
           assert(deq.size() == 10);
           std::cout << "  - pop_front() 与 pop_back() 边界回收断言通过，剩余尺寸: 10。
";
       }
       assert(TrackedItem::active_count == 0); // 验证析构平衡
       std::cout << "  - MiniDeque 作用域析构完成，存活实例数严格归零。

";

       std::cout << "=======================================================
";
       std::cout << " 全部测试断言通过，MiniVector 与 MiniDeque 契约成立。
";
       std::cout << "=======================================================
";
   }

   } // namespace test
