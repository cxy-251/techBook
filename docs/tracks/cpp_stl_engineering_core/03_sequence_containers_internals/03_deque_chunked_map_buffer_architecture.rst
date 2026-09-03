====================================================================================================
std::deque 分段连续双端队列：中控 map 指针数组、固定块缓冲 (block)、复合迭代器寻址与两端常数扩容
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 3 模块前两节中，我们分别解构了动态连续数组 ``std::vector``（基于三指针状态模型与单向尾部几何扩容，具有极高的 CPU 缓存局部性但头部插入需搬动全量元素）与静态连续数组 ``std::array``（基于栈/对象内嵌存储与编译期固定尺寸，零堆分配但容量无法运行期变易）。在高性能任务调度、广度优先搜索（BFS）队列、滑动窗口以及 I/O 缓冲区等工业场景中，程序要求容器在支持 $\mathcal{O}(1)$ 常数时间随机下标访问（``operator[]``）的同时，支持在 **头部（Front）与尾部（Back）双端进行 $\mathcal{O}(1)$ 的高效插入与删除**，且严禁触发类似 ``std::vector`` 扩容时昂贵的全量元素重分配与深拷贝。标准链表 ``std::list`` 虽然支持双向常数时间插入，但每个节点伴随独立的堆分配开销与前后驱指针内存浪费，且彻底丧失了常数时间随机寻址能力。为了在连续内存的随机寻址能力与链表的双端动态扩张能力之间取得工程折衷，C++ 标准库设计了分段连续容器——**``std::deque``（Double-ended Queue）**。本章深入剖析 ``std::deque`` 的中控 Map 指针数组与固定块缓冲区（Chunk Buffer）二级寻址拓扑、由 ``cur``/``first``/``last``/``node`` 四指针构成的复合随机访问迭代器状态机、双端常数扩容与 Map 浅拷贝重分配机制、中间插入元素的双向最小迁移优化策略，以及其独特的迭代器与引用分离失效边界。

中控 Map 与固定尺寸缓冲区 (Block) 二级拓扑
-------------------------------------------

``std::deque`` 在物理内存上放弃了全局单向严格连续，转而采用 **分段连续内存（Chunked Contiguous Memory）** 架构。其底层结构由一组定长数据块（Buffer / Block）以及一个管理这组数据块首地址的指针数组——**中控 Map（Control Array / Map）** 构成。

二级寻址物理内存模型
~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                  std::deque 二级中控 Map 与分段缓冲区物理拓扑               |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ std::deque 容器主体对象 ]                                               |
   |   * _M_map: 指向中控指针数组首地址 (T**)                                     |
   |   * _M_map_size: 中控指针数组槽位总容量                                      |
   |   * _M_start: 指向首个有效元素的复合迭代器 (4 指针)                          |
   |   * _M_finish: 指向末尾有效元素后继位置的复合迭代器 (4 指针)                 |
   |                                                                             |
   |   [ 中控指针数组 Map (T**) ]                                                |
   |   +----------+----------+----------+----------+----------+----------+       |
   |   | Slot 0   | Slot 1   | Slot 2   | Slot 3   | Slot 4   | Slot 5   |       |
   |   | (null)   | (null)   |  Node A  |  Node B  |  Node C  | (null)   |       |
   |   +----------+----------+----+-----+----+-----+----+-----+----------+       |
   |                              |          |          |                        |
   |            /-----------------/          |          \------------------\     |
   |            v                            v                             v     |
   |   [ Block 0 (Node A) ]         [ Block 1 (Node B) ]          [ Block 2 ]    |
   |   +--------------------+       +--------------------+        +------------+ |
   |   | (unused) | Elem 0  |  -->  | Elem 1   | Elem 2  |   -->  | Elem 3     | |
   |   +--------------------+       +--------------------+        +------------+ |
   |              ^                                                        ^     |
   |              |                                                        |     |
   |          _M_start.cur                                           _M_finish.cur|
   |                                                                             |
   |   |<------------------- 逻辑连续序列: Elem[0..3] ------------------------->| |
   |                                                                             |
   +-----------------------------------------------------------------------------+

1. **固定块缓冲区（Buffer / Block）**：
   每个缓冲区是一段独立的连续堆内存数组，容纳固定数量 $B$（Buffer Size）个元素。
   - 在 GCC libstdc++ 中，单个 Block 的字节容量默认为 512 字节。单块容纳元素个数计算公式为：

     .. math::

        B = 	ext{__deque_buf_size}(	ext{sizeof}(T)) = \begin{cases} \lfloor 512 / 	ext{sizeof}(T) \rfloor & 	ext{if } 	ext{sizeof}(T) < 512 \ 1 & 	ext{if } 	ext{sizeof}(T) \ge 512 \end{cases}

   - 在 MSVC STL 中，若 $	ext{sizeof}(T) \le 1$ 则单块容纳 16 个元素；若 $	ext{sizeof}(T) \le 2$ 则容纳 8 个；若 $	ext{sizeof}(T) \le 4$ 则容纳 4 个；若 $	ext{sizeof}(T) \le 8$ 则容纳 2 个；其余情况每块固定容纳 1 个元素（或固定 4096 字节分页）。
2. **中控指针数组（Map）**：
   中控数组是一个元素类型为指针的连续数组 ``T** _M_map``。每个槽位（Slot）存储一个指向具体 Block 首地址的裸指针。
   - 活跃节点集中分布在中控 Map 的中心区域。
   - 当在头部（``push_front``）插入且当前首块已满时，容器在前一个可用槽位分配并挂载一个新 Block；当在尾部（``push_back``）插入且末块已满时，在后一个槽位分配并挂载新 Block。

四指针复合随机访问迭代器架构
----------------------------

由于 ``std::deque`` 的物理内存在跨越 Block 边界时不连续，普通的裸指针无法直接作为其迭代器。标准库设计了包含 **4 个原始指针的复合迭代器（Composite Iterator）**。

迭代器内部指针拓扑与状态空间
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 64 位系统下，一个 ``std::deque<T>::iterator`` 占用 32 字节内存（4 个 8 字节指针）：

.. code-block:: cpp

   template <typename T, typename Ref, typename Ptr>
   struct _Deque_iterator {
       using iterator_category = std::random_access_iterator_tag;
       using value_type        = T;
       using pointer           = Ptr;
       using reference         = Ref;

       T*  _M_cur;   // 指向当前正在引用的元素物理地址
       T*  _M_first; // 指向当前元素所在 Block 的起始物理地址
       T*  _M_last;  // 指向当前元素所在 Block 的截止物理边界 (尾后边界)
       T** _M_node;  // 指向中控 Map 中对应当前 Block 的槽位指针 (T**)
   };

四指针的具体职责为：
- **``_M_cur``**：当前迭代器指向的具体元素物理位置。解引用操作 ``*it`` 直接展开为 ``*_M_cur``，开销与裸指针完全一致。
- **``_M_first`` 与 ``_M_last``**：定义了当前 Block 的有效地址闭开区间 ``[_M_first, _M_last)``，用于在迭代器前进或后退时快速判定是否跨越了当前 Block 边界。
- **``_M_node``**：建立了从当前 Block 回溯到中控 Map 的直接连接。当 ``_M_cur`` 越过当前 Block 边界时，通过 ``_M_node`` 的增减可立即定位相邻的新 Block。

迭代器步进与跨块切换 (set_node) 状态机
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当迭代器执行递增操作（``++it``）时，状态机按以下分支流转：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     Deque 迭代器跨块步进 (operator++) 状态机                |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |                       [ 执行 ++_M_cur ]                                     |
   |                               |                                             |
   |                               v                                             |
   |               _M_cur == _M_last (达到块边界?)                               |
   |                               |                                             |
   |                +--------------+--------------+                              |
   |                |                             |                              |
   |          (否: 块内步进)                 (是: 跨块跃迁)                      |
   |                |                             |                              |
   |                v                             v                              |
   |           完成递增操作                  1. ++_M_node (切至下一个槽位)        |
   |                                         2. _M_first = *_M_node              |
   |                                         3. _M_last = _M_first + BufferSize  |
   |                                         4. _M_cur = _M_first                |
   |                                                                             |
   +-----------------------------------------------------------------------------+

随机访问算术运算 (operator+= / operator[])
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``std::deque::iterator`` 满足随机访问迭代器（Random Access Iterator）契约，支持常数时间跳跃任意偏移量 $n$（``it += n``）：

.. code-block:: cpp

   _Deque_iterator& operator+=(difference_type n) {
       difference_type offset = n + (_M_cur - _M_first);
       if (offset >= 0 && offset < static_cast<difference_type>(BufferSize)) {
           // 目标仍落在当前 Block 内部
           _M_cur += n;
       } else {
           // 目标跨越了多个 Block
           difference_type node_offset =
               offset > 0 ? offset / static_cast<difference_type>(BufferSize)
                          : -static_cast<difference_type>((-offset - 1) / BufferSize) - 1;
           set_node(_M_node + node_offset);
           _M_cur = _M_first + (offset - node_offset * static_cast<difference_type>(BufferSize));
       }
       return *this;
   }

通过整数除法与取模，迭代器可以在 $\mathcal{O}(1)$ 常数时间内计算出目标 Block 索引与块内偏移量，抹平了多数据块离散分布的抽象断层。

双端常数扩容与 Map 浅拷贝重分配机制
------------------------------------

当在 ``std::deque`` 的两端调用 ``push_front`` 或 ``push_back`` 时，容器展现出优于 ``std::vector`` 的扩容性能特征。

双端扩张动力学
~~~~~~~~~~~~~~

1. **块内空闲槽位填充**：若端点迭代器所在的 Block 尚有可用空间，元素直接在未初始化的裸内存槽位就地构造，指针向前/向后步进 1 格，耗时为严格的 $\mathcal{O}(1)$。
2. **挂载新 Block**：若端点 Block 已被填满，容器向分配器仅申请单个固定大小的 Block 内存，并将其指针挂载到中控 Map 的相邻空闲槽位（Slot），原有的所有数据块及其存储的对象绝对不需要发生任何移动或拷贝。

中控 Map 满载时的浅拷贝重分配 (Reallocate Map)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

只有当中控 Map 自身的槽位数组被全部占满时，容器才会触发 Map 数组的重分配：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     中控 Map 重分配与浅拷贝指针居中重排                      |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 旧 Map 状态 (两端槽位耗尽) ]                                            |
   |   +----------+----------+----------+----------+                             |
   |   |  Node 0  |  Node 1  |  Node 2  |  Node 3  |  (容量: 4)                  |
   |   +----+-----+----+-----+----+-----+----+-----+                             |
   |        |          |          |          |                                   |
   |        v          v          v          v                                   |
   |     [Blk 0]    [Blk 1]    [Blk 2]    [Blk 3]                                |
   |                                                                             |
   |   [ 申请 2 倍新 Map 并执行指针浅拷贝居中 ]                                  |
   |   +--------+--------+--------+--------+--------+--------+--------+--------+   |
   |   | (null) | (null) | Node 0 | Node 1 | Node 2 | Node 3 | (null) | (null) |   |
   |   +--------+--------+---+----+---+----+---+----+---+----+--------+--------+   |
   |                         |        |        |        |                        |
   |                         \--------+--------+--------/                        |
   |                                  |                                          |
   |                                  v (底层真实元素 Block 完全保持不动)        |
   |                               [Blk 0..3]                                    |
   |                                                                             |
   +-----------------------------------------------------------------------------+

Map 重分配具有以下微架构优势：
- **仅拷贝指针（Shallow Pointer Copy）**：Map 数组内部仅存储裸指针（每个槽位 8 字节）。即使 deque 中存储了数百万个复杂重型对象，重分配时仅需使用 ``memcpy`` 迁移数千个指针地址，开销极低。
- **指针居中对齐**：新 Map 申请原容量的 2 倍至 3 倍大小，将旧指针复制到新数组的正中央。这确保了后续在头部与尾部继续插入时，均能拥有充裕的空闲槽位向两侧延伸。
- **元素物理地址绝对恒定**：元素对象本身始终驻留在其专属的 Block 堆内存块中，其物理地址在整个扩容周期中保持绝对不变。

中间插入/删除的双向最小迁移优化
-------------------------------

当在 ``std::deque`` 的中间位置调用 ``insert(pos, val)`` 或 ``erase(pos)`` 时，容器无法维持 $\mathcal{O}(1)$ 复杂度。为了最小化元素拷贝次数，标准库实现了 **双向距离判定与最小迁移策略**。

.. math::

   	ext{dist\_front} = 	ext{pos} - 	ext{begin}()

.. math::

   	ext{dist\_back} = 	ext{end}() - 	ext{pos}

1. **若 $	ext{dist\_front} < 	ext{dist\_back}$（插入点靠近头部）**：
   - 容器在头部扩展一个新槽位（类似 ``push_front``）。
   - 将区间 ``[begin(), pos)`` 内部的所有元素整体向前搬移 1 格（调用 ``std::move_backward`` 或前向移动）。
   - 在腾出的 ``pos - 1`` 位置就地构造新元素。
2. **若 $	ext{dist\_front} \ge 	ext{dist\_back}$（插入点靠近尾部）**：
   - 容器在尾部扩展一个新槽位（类似 ``push_back``）。
   - 将区间 ``[pos, end())`` 内部的所有元素整体向后搬移 1 格。
   - 在腾出的 ``pos`` 位置构造新元素。

该优化确保了中间变易操作最多仅需移动 $\min(	ext{dist\_front}, 	ext{dist\_back}) \le \frac{	ext{size}()}{2}$ 个元素，比 ``std::vector`` 固定移动后端全部元素的策略减少了一半的元素构造/赋值开销。

迭代器与引用失效 (Iterator & Reference Invalidation) 拓扑边界
--------------------------------------------------------------

``std::deque`` 的分段连续存储模型导致了其在变易操作下呈现出独特的 **“迭代器失效但引用有效”** 的分离失效特征。

.. list-table:: std::deque 变易操作对迭代器与引用的失效规则表
   :widths: 22 28 50
   :header-rows: 1
   :class: tight-table

   * - 容器操作类型
     - 迭代器失效状态 (Iterators)
     - 指针与引用失效状态 (Pointers & References)
   * - ``push_front`` / ``push_back``
     - **全部迭代器失效**（因为中控 Map 发生槽位变化或重分配，导致迭代器的 ``_M_node`` 失效）
     - **全部指针与引用依然有效**（因为所有元素所在的 Block 物理地址未发生改变）
   * - ``pop_front`` / ``pop_back``
     - 被销毁元素的迭代器及尾后迭代器（``end()``）失效；其他迭代器失效
     - 仅指向被删除元素的指针/引用失效；其他所有元素的指针与引用依然有效
   * - 中间 ``insert(pos, val)``
     - **全部迭代器失效**
     - **全部指针与引用失效**（因为涉及区间内元素对象的批量移动）
   * - 中间 ``erase(pos)``
     - **全部迭代器失效**
     - **全部指针与引用失效**
   * - ``clear()``
     - 全部迭代器失效
     - 全部指针与引用失效

工业级 C++ 完整 Mini-Deque 内核实现
-----------------------------------

以下 C++ 源码实现了一个工业级自包含的 ``MiniDeque<T>`` 分段双端队列模板。该实现涵盖：
1. 具备 ``_M_cur``、``_M_first``、``_M_last``、``_M_node`` 四指针的随机访问复合迭代器，支持精确跨块跳转与解引用。
2. 包含中控 Map 与固定尺寸 Block 缓冲区的二级内存分配与管理。
3. 双端常数时间 ``push_back`` / ``push_front`` / ``pop_back`` / ``pop_front`` 与中控 Map 浅拷贝动态扩容居中。
4. 常数时间随机下标寻址 ``operator[]`` 与 ``size()`` 距离计算。
5. 完整的生命周期清理与端到端测试套件。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <memory>
   #include <utility>
   #include <cstddef>
   #include <cassert>
   #include <algorithm>
   #include <stdexcept>

   namespace core_stl {

   // 固定单块缓冲区容纳元素数量 (教学与验证设为 4 个，工业级一般为 512 字节/sizeof(T))
   template <typename T>
   struct DequeBufferConfig {
       static constexpr std::size_t BufferSize = sizeof(T) < 512 ? (512 / sizeof(T) > 0 ? 512 / sizeof(T) : 1) : 1;
   };

   // 自定义小型 Block 配置便于高频测试跨块逻辑
   template <typename T, std::size_t CustomBufSize = 4>
   class MiniDeque;

   // =========================================================================
   // 1. 四指针复合随机访问迭代器 (Composite Random Access Iterator)
   // =========================================================================
   template <typename T, std::size_t BufSize = 4>
   struct MiniDequeIterator {
       using iterator_category = std::random_access_iterator_tag;
       using value_type        = T;
       using difference_type   = std::ptrdiff_t;
       using pointer           = T*;
       using reference         = T&;

       pointer  _M_cur   = nullptr;
       pointer  _M_first = nullptr;
       pointer  _M_last  = nullptr;
       T**      _M_node  = nullptr;

       MiniDequeIterator() = default;
       MiniDequeIterator(pointer cur, T** node)
           : _M_cur(cur), _M_first(*node), _M_last(*node + BufSize), _M_node(node) {}

       void set_node(T** new_node) noexcept {
           _M_node = new_node;
           _M_first = *new_node;
           _M_last = _M_first + BufSize;
       }

       reference operator*() const noexcept { return *_M_cur; }
       pointer operator->() const noexcept { return _M_cur; }

       MiniDequeIterator& operator++() noexcept {
           ++_M_cur;
           if (_M_cur == _M_last) {
               set_node(_M_node + 1);
               _M_cur = _M_first;
           }
           return *this;
       }

       MiniDequeIterator operator++(int) noexcept {
           MiniDequeIterator tmp = *this;
           ++(*this);
           return tmp;
       }

       MiniDequeIterator& operator--() noexcept {
           if (_M_cur == _M_first) {
               set_node(_M_node - 1);
               _M_cur = _M_last;
           }
           --_M_cur;
           return *this;
       }

       MiniDequeIterator operator--(int) noexcept {
           MiniDequeIterator tmp = *this;
           --(*this);
           return tmp;
       }

       MiniDequeIterator& operator+=(difference_type n) noexcept {
           difference_type offset = n + (_M_cur - _M_first);
           if (offset >= 0 && offset < static_cast<difference_type>(BufSize)) {
               _M_cur += n;
           } else {
               difference_type node_offset =
                   offset > 0 ? offset / static_cast<difference_type>(BufSize)
                              : -static_cast<difference_type>((-offset - 1) / BufSize) - 1;
               set_node(_M_node + node_offset);
               _M_cur = _M_first + (offset - node_offset * static_cast<difference_type>(BufSize));
           }
           return *this;
       }

       MiniDequeIterator operator+(difference_type n) const noexcept {
           MiniDequeIterator tmp = *this;
           return tmp += n;
       }

       MiniDequeIterator& operator-=(difference_type n) noexcept {
           return *this += -n;
       }

       MiniDequeIterator operator-(difference_type n) const noexcept {
           MiniDequeIterator tmp = *this;
           return tmp -= n;
       }

       difference_type operator-(const MiniDequeIterator& other) const noexcept {
           return static_cast<difference_type>(BufSize) * (_M_node - other._M_node - 1) +
                  (_M_cur - _M_first) + (other._M_last - other._M_cur);
       }

       reference operator[](difference_type n) const noexcept {
           return *(*this + n);
       }

       bool operator==(const MiniDequeIterator& other) const noexcept {
           return _M_cur == other._M_cur;
       }
       bool operator!=(const MiniDequeIterator& other) const noexcept {
           return !(*this == other);
       }
       bool operator<(const MiniDequeIterator& other) const noexcept {
           return (_M_node == other._M_node) ? (_M_cur < other._M_cur) : (_M_node < other._M_node);
       }
   };

   // =========================================================================
   // 2. MiniDeque 双端队列容器主体
   // =========================================================================
   template <typename T, std::size_t CustomBufSize>
   class MiniDeque {
   public:
       using value_type      = T;
       using size_type       = std::size_t;
       using difference_type = std::ptrdiff_t;
       using reference       = T&;
       using const_reference = const T&;
       using iterator        = MiniDequeIterator<T, CustomBufSize>;
       using const_iterator  = MiniDequeIterator<const T, CustomBufSize>;

       static constexpr std::size_t BufSize = CustomBufSize;

   private:
       using NodeAlloc = std::allocator<T*>;
       using ElemAlloc = std::allocator<T>;

       T** _M_map             = nullptr;
       size_type _M_map_size  = 0;
       iterator _M_start;
       iterator _M_finish;

       ElemAlloc _M_elem_alloc;
       NodeAlloc _M_map_alloc;

       static constexpr size_type InitialMapSize = 8;

   public:
       MiniDeque() {
           initialize_map(0);
       }

       ~MiniDeque() {
           clear();
           // 释放初始空 Block
           if (_M_start._M_first) {
               _M_elem_alloc.deallocate(_M_start._M_first, BufSize);
           }
           if (_M_map) {
               _M_map_alloc.deallocate(_M_map, _M_map_size);
           }
       }

       // 禁用拷贝以保持模型精简
       MiniDeque(const MiniDeque&) = delete;
       MiniDeque& operator=(const MiniDeque&) = delete;

       // =====================================================================
       // 基础状态查询
       // =====================================================================
       [[nodiscard]] size_type size() const noexcept {
           if (!_M_map) return 0;
           return static_cast<size_type>(_M_finish - _M_start);
       }

       [[nodiscard]] bool empty() const noexcept {
           return _M_start == _M_finish;
       }

       iterator begin() noexcept { return _M_start; }
       iterator end() noexcept { return _M_finish; }

       reference front() noexcept {
           assert(!empty() && "front() on empty deque");
           return *_M_start;
       }

       reference back() noexcept {
           assert(!empty() && "back() on empty deque");
           iterator tmp = _M_finish;
           --tmp;
           return *tmp;
       }

       reference operator[](size_type n) noexcept {
           assert(n < size() && "Index out of bounds");
           return _M_start[static_cast<difference_type>(n)];
       }

       const_reference operator[](size_type n) const noexcept {
           assert(n < size() && "Index out of bounds");
           return _M_start[static_cast<difference_type>(n)];
       }

       // =====================================================================
       // 双端压入与弹出
       // =====================================================================
       void push_back(const T& value) {
           if (_M_finish._M_cur != _M_finish._M_last - 1) {
               // 当前尾块尚有空槽位 (留 1 个尾后哨兵)
               std::allocator_traits<ElemAlloc>::construct(_M_elem_alloc, _M_finish._M_cur, value);
               ++_M_finish._M_cur;
           } else {
               // 尾块已满，挂载新块
               reserve_map_at_back();
               *(_M_finish._M_node + 1) = _M_elem_alloc.allocate(BufSize);
               std::allocator_traits<ElemAlloc>::construct(_M_elem_alloc, _M_finish._M_cur, value);
               _M_finish.set_node(_M_finish._M_node + 1);
               _M_finish._M_cur = _M_finish._M_first;
           }
       }

       void push_front(const T& value) {
           if (_M_start._M_cur != _M_start._M_first) {
               // 当前首块前方有空位
               --_M_start._M_cur;
               std::allocator_traits<ElemAlloc>::construct(_M_elem_alloc, _M_start._M_cur, value);
           } else {
               // 首块前方已满，挂载新块
               reserve_map_at_front();
               *(_M_start._M_node - 1) = _M_elem_alloc.allocate(BufSize);
               _M_start.set_node(_M_start._M_node - 1);
               _M_start._M_cur = _M_start._M_last - 1;
               std::allocator_traits<ElemAlloc>::construct(_M_elem_alloc, _M_start._M_cur, value);
           }
       }

       void pop_back() noexcept {
           assert(!empty() && "pop_back on empty deque");
           if (_M_finish._M_cur != _M_finish._M_first) {
               --_M_finish._M_cur;
               std::allocator_traits<ElemAlloc>::destroy(_M_elem_alloc, _M_finish._M_cur);
           } else {
               // 跨回前一个块并释放当前尾块
               _M_elem_alloc.deallocate(_M_finish._M_first, BufSize);
               _M_finish.set_node(_M_finish._M_node - 1);
               _M_finish._M_cur = _M_finish._M_last - 1;
               std::allocator_traits<ElemAlloc>::destroy(_M_elem_alloc, _M_finish._M_cur);
           }
       }

       void pop_front() noexcept {
           assert(!empty() && "pop_front on empty deque");
           std::allocator_traits<ElemAlloc>::destroy(_M_elem_alloc, _M_start._M_cur);
           if (_M_start._M_cur != _M_start._M_last - 1) {
               ++_M_start._M_cur;
           } else {
               // 跨至下一个块并释放当前首块
               T* old_first = _M_start._M_first;
               _M_start.set_node(_M_start._M_node + 1);
               _M_start._M_cur = _M_start._M_first;
               _M_elem_alloc.deallocate(old_first, BufSize);
           }
       }

       void clear() noexcept {
           for (T** node = _M_start._M_node + 1; node < _M_finish._M_node; ++node) {
               destroy_buffer(*node, *node + BufSize);
               _M_elem_alloc.deallocate(*node, BufSize);
           }
           if (_M_start._M_node != _M_finish._M_node) {
               destroy_buffer(_M_start._M_cur, _M_start._M_last);
               destroy_buffer(_M_finish._M_first, _M_finish._M_cur);
               _M_elem_alloc.deallocate(_M_finish._M_first, BufSize);
           } else {
               destroy_buffer(_M_start._M_cur, _M_finish._M_cur);
           }
           _M_finish = _M_start;
       }

   private:
       void destroy_buffer(T* first, T* last) noexcept {
           for (; first != last; ++first) {
               std::allocator_traits<ElemAlloc>::destroy(_M_elem_alloc, first);
           }
       }

       void initialize_map(size_type num_elements) {
           size_type num_nodes = num_elements / BufSize + 1;
           _M_map_size = std::max(InitialMapSize, num_nodes + 2);
           _M_map = _M_map_alloc.allocate(_M_map_size);

           // 让节点指针挂载在新 Map 的正中央
           T** start_node = _M_map + (_M_map_size - num_nodes) / 2;
           T** finish_node = start_node + num_nodes - 1;

           for (T** cur_node = start_node; cur_node <= finish_node; ++cur_node) {
               *cur_node = _M_elem_alloc.allocate(BufSize);
           }

           _M_start.set_node(start_node);
           _M_start._M_cur = _M_start._M_first;

           _M_finish.set_node(finish_node);
           _M_finish._M_cur = _M_finish._M_first + (num_elements % BufSize);
       }

       void reserve_map_at_back(size_type nodes_to_add = 1) {
           if (nodes_to_add + 1 > _M_map_size - (_M_finish._M_node - _M_map)) {
               reallocate_map(nodes_to_add, false);
           }
       }

       void reserve_map_at_front(size_type nodes_to_add = 1) {
           if (nodes_to_add > static_cast<size_type>(_M_start._M_node - _M_map)) {
               reallocate_map(nodes_to_add, true);
           }
       }

       // 中控 Map 浅拷贝重分配与居中
       void reallocate_map(size_type nodes_to_add, bool add_at_front) {
           size_type old_num_nodes = _M_finish._M_node - _M_start._M_node + 1;
           size_type new_num_nodes = old_num_nodes + nodes_to_add;

           T** new_start_node = nullptr;
           if (_M_map_size > 2 * new_num_nodes) {
               // 现有 Map 空间充足，仅需在内部平移指针居中
               new_start_node = _M_map + (_M_map_size - new_num_nodes) / 2 + (add_at_front ? nodes_to_add : 0);
               if (new_start_node < _M_start._M_node) {
                   std::copy(_M_start._M_node, _M_finish._M_node + 1, new_start_node);
               } else {
                   std::copy_backward(_M_start._M_node, _M_finish._M_node + 1, new_start_node + old_num_nodes);
               }
           } else {
               // 申请 2 倍大的新 Map
               size_type new_map_size = _M_map_size + std::max(_M_map_size, nodes_to_add) + 2;
               T** new_map = _M_map_alloc.allocate(new_map_size);
               new_start_node = new_map + (new_map_size - new_num_nodes) / 2 + (add_at_front ? nodes_to_add : 0);

               // 浅拷贝迁移既有 Block 指针
               std::copy(_M_start._M_node, _M_finish._M_node + 1, new_start_node);

               _M_map_alloc.deallocate(_M_map, _M_map_size);
               _M_map = new_map;
               _M_map_size = new_map_size;
           }

           // 重新挂载迭代器的 Node 指针
           _M_start.set_node(new_start_node);
           _M_finish.set_node(new_start_node + old_num_nodes - 1);
       }
   };

   } // namespace core_stl

   // =========================================================================
   // 3. 端到端测试与内存状态验证套件
   // =========================================================================
   namespace test {

   inline void runDequeTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " MiniDeque 中控 Map 二级拓扑与双端扩容测试套件
";
       std::cout << "=======================================================

";

       // 使用单块容纳 4 个元素的 MiniDeque
       core_stl::MiniDeque<int, 4> dq;

       // 1. 双端高频追加测试 (触发多块分配与跨块跃迁)
       std::cout << "[测试 1: push_back 与 push_front 跨块扩容]
";
       // 尾部追加 10, 20, 30, 40, 50, 60
       for (int v : {10, 20, 30, 40, 50, 60}) {
           dq.push_back(v);
       }
       // 头部追加 0, -10, -20, -30
       for (int v : {0, -10, -20, -30}) {
           dq.push_front(v);
       }

       // 期望序列: -30, -20, -10, 0, 10, 20, 30, 40, 50, 60 (总计 10 个元素)
       assert(dq.size() == 10);
       assert(dq.front() == -30);
       assert(dq.back() == 60);

       std::cout << "  当前 deque 元素序列 (逻辑连续): ";
       for (size_t i = 0; i < dq.size(); ++i) {
           std::cout << dq[i] << " ";
       }
       std::cout << "
  -> 双端跨块插入与随机下标访问验证通过。

";

       // 2. 随机访问迭代器算术运算测试
       std::cout << "[测试 2: 四指针复合迭代器跨块步进与距离计算]
";
       auto it = dq.begin();
       assert(*it == -30);

       it += 5; // 跨块前进 5 个位置 -> 应该命中 20
       assert(*it == 20);

       it -= 2; // 跨块后退 2 个位置 -> 应该命中 0
       assert(*it == 0);

       auto it_end = dq.end();
       assert(it_end - dq.begin() == 10);
       std::cout << "  -> 迭代器 operator+=, operator-=, operator- 跨块寻址通过。

";

       // 3. 双端弹出与块内存动态释放
       std::cout << "[测试 3: 双端弹出 pop_front / pop_back 边界释放]
";
       dq.pop_front(); // 弹出 -30
       assert(dq.front() == -20);
       assert(dq.size() == 9);

       dq.pop_back();  // 弹出 60
       assert(dq.back() == 50);
       assert(dq.size() == 8);

       std::cout << "  弹出后首尾值: front = " << dq.front() << ", back = " << dq.back() << "
";
       std::cout << "  -> 双端弹出与 Block 边界收缩验证通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰验证了 ``std::deque`` 的分段二级架构：

1. **逻辑连续与物理分段解耦**：通过在单块容纳 4 个元素的配置下交替执行 ``push_back`` 与 ``push_front``，容器成功将 10 个元素离散分布在多个 Block 之中，同时对外维持严格的单调逻辑序列 ``[-30, -20, -10, 0, 10, 20, 30, 40, 50, 60]``。
2. **复合迭代器跨块无缝寻址**：``it += 5`` 与 ``it_end - dq.begin()`` 准确完成了中控 Map 节点跳转与块内偏移量换算，消除了数据块物理地址不连续对标准随机访问算法的影响。
3. **两端零重分配开销**：在双端连续插入 10 个元素的过程中，已存在的元素地址始终保持稳定，未发生类似 ``std::vector`` 的全量深拷贝迁移。

小结与下章导读
--------------

本章系统解构了现代 C++ 分段序列容器 ``std::deque`` 的二级核心拓扑与微架构特性：

1. **中控 Map 与 Block 二级拓扑**：剖析了通过中控指针数组管理多个定长数据块的物理布局，确立了双端 $\mathcal{O}(1)$ 扩展无需全量元素拷贝的机制。
2. **四指针复合迭代器模型**：解构了 ``_M_cur``/``_M_first``/``_M_last``/``_M_node`` 状态机在块内高速访问与跨块跃迁（``set_node``）中的协同机理。
3. **Map 浅拷贝扩容与双向最小迁移**：推导了 Map 满载时仅复制裸指针数组的极低开销，以及中间插入时基于 $\min(	ext{dist\_front}, 	ext{dist\_back})$ 的迁移减半优化。
4. **引用/迭代器分离失效**：阐明了双端压入导致迭代器失效而既有元素指针/引用保持绝对有效的底层物理成因。

在掌握了动态连续数组（``std::vector``）、静态连续数组（``std::array``）与分段连续双端队列（``std::deque``）之后，下一章我们将转向基于离散节点链接的经典链表体系。在第 3 模块第 4 节 **链表体系物理拓扑：std::list 环形双向带哨兵节点与 splice 零拷贝剪切、std::forward_list 极简单向链表（``03_sequence_containers_internals/04_list_and_forward_list_node_topologies.rst``）** 中，我们将深入剖析带空哨兵节点的环形双向链表拓扑、``splice`` 节点指针剪切的常数时间拼接机理，以及单向链表 ``std::forward_list`` 消除前驱指针达成极致内存压缩的工程设计。
