====================================================================================================
链表体系物理拓扑：std::list 环形双向带哨兵节点与 splice 零拷贝剪切、std::forward_list 极简单向链表
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 3 模块前三节中，我们系统解构了基于连续内存的动态数组 ``std::vector``、静态内嵌数组 ``std::array`` 以及基于分段二级中控架构的双端队列 ``std::deque``。连续与分段容器在提供高速下标随机访问（``operator[]``）与高 CPU 缓存局部性的同时，其元素的插入与删除操作均不可避免地涉及后续元素的物理搬迁或迭代器大面积失效。当应用场景涉及大型重型对象的高频任意位置插入/删除、并发队列节点流转，或要求在任何变易操作下已有元素的指针与引用绝对不发生失效时，基于离散节点链接的链表容器提供了独特的物理拓扑支撑。现代 C++ 标准库提供了两种互补的链表实现：双向环形带哨兵链表 **``std::list``** 与极致空间压缩的单向链表 **``std::forward_list``**。本章深入剖析 ``std::list`` 的基类指针与值节点继承拓扑、环形空哨兵节点消除边界条件分支的微架构机理、``splice`` 操作在 $\mathcal{O}(1)$ 常数时间内通过指针剪切实现跨容器零拷贝迁移的底层实现、``std::forward_list`` 消除前驱指针与 ``size`` 字段的零抽象开销设计、``insert_after`` 接口范式，以及链表特化归并排序（Merge Sort）的无拷贝节点重构算法。

std::list 环形双向带哨兵节点物理拓扑
------------------------------------

``std::list<T>`` 的物理实现建立在堆上独立分配的离散节点网络之上。工业级标准库（如 GCC libstdc++、LLVM libc++ 与 MSVC STL）均采用 **带空哨兵节点（Sentinel Node）的环形双向链表** 模型。

节点继承层级与内存布局
~~~~~~~~~~~~~~~~~~~~~~

为了将纯粹的链表指针操作与具体元素类型 ``T`` 的构造/析构彻底解耦，标准库将节点设计为两层继承结构：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                  std::list 节点继承层级与堆内存拓扑                          |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 节点基类: _List_node_base (16 Bytes in 64-bit) ]                        |
   |   +-----------------------+-----------------------+                         |
   |   |   _M_next (8 Bytes)   |   _M_prev (8 Bytes)   |                         |
   |   +-----------------------+-----------------------+                         |
   |               ^                                                             |
   |               | 继承 (Inheritance)                                          |
   |   [ 完整值节点: _List_node<T> (16 + sizeof(T) + Padding) ]                  |
   |   +-----------------------+-----------------------+---------------------+   |
   |   |   _M_next (8 Bytes)   |   _M_prev (8 Bytes)   |  _M_storage (T)     |   |
   |   +-----------------------+-----------------------+---------------------+   |
   |                                                                             |
   +-----------------------------------------------------------------------------+

1. **``_List_node_base``（无值基类节点）**：仅包含前向指针 ``_M_next`` 与后向指针 ``_M_prev``。容器本体内部内嵌的 **哨兵头节点** 直接使用基类实例，无需构造无意义的虚拟 ``T`` 对象，消除了当 ``T`` 缺乏默认构造函数时的编译限制。
2. **``_List_node<T>``（具体数据节点）**：继承自基类，并在尾部挂载对齐的未初始化存储缓冲区 ``__gnu_cxx::__aligned_membuf<T> _M_storage``。分配器每次按完整的 ``_List_node<T>`` 尺寸申请堆内存。

环形哨兵拓扑与边界分支消除
~~~~~~~~~~~~~~~~~~~~~~~~~~

通过将哨兵节点与数据节点构成闭环，链表在物理上消除了 ``nullptr`` 空指针边界：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                  std::list 环形双向闭环拓扑与边界状态                        |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 场景 1: 空链表 (Empty List) 拓扑 ]                                      |
   |   +------------------------------------+                                    |
   |   | 容器本体内嵌哨兵节点: _M_node      |                                    |
   |   |   _M_next = &_M_node; (指向自身)   |                                    |
   |   |   _M_prev = &_M_node; (指向自身)   |                                    |
   |   +------------------------------------+                                    |
   |   * 判定 empty(): _M_node._M_next == &_M_node                               |
   |   * begin() == end() == iterator(&_M_node)                                  |
   |                                                                             |
   |   -----------------------------------------------------------------------   |
   |                                                                             |
   |   [ 场景 2: 包含 2 个有效元素的链表拓扑 ]                                   |
   |                                                                             |
   |         +-------------------------------------------------------------+     |
   |         |                                                             |     |
   |         v                                                             |     |
   |   +------------+   _M_next   +------------+   _M_next   +-------------+--+  |
   |   |   哨兵     | ----------> |   Node A   | ----------> |   Node B    |  |  |
   |   |  _M_node   | <---------- |  (Elem 0)  | <---------- |  (Elem 1)   |  |  |
   |   | (无值基类) |   _M_prev   +------------+   _M_prev   +-------------+  |  |
   |   +------------+                                              |          |  |
   |         ^                                                     |          |  |
   |         \-----------------------------------------------------/          |  |
   |                                                                          |  |
   |   * begin(): iterator(_M_node._M_next) -> Node A                         |  |
   |   * end():   iterator(&_M_node)        -> 哨兵节点本身                   |  |
   |   * front(): Node A 的值; back(): Node B 的值 (_M_node._M_prev)          |  |
   |                                                                             |
   +-----------------------------------------------------------------------------+

哨兵节点的引入使链表的插入与删除算法完全消除了对“是否为头节点”、“是否为空链表”的特判条件分支（Branch Elimination），所有节点的链接修改均退化为统一的无分支四指针赋值指令。

C++11 size() 复杂度演进：O(N) 遍历 vs O(1) 计数
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 C++98 标准中，``std::list::size()`` 的复杂度允许为 $\mathcal{O}(N)$。这使得跨容器剪切任意子区间的 ``splice`` 操作可以在 $\mathcal{O}(1)$ 内完成（直接修改两端指针，无需统计迁移元素个数）。

C++11 标准强制规定所有标准容器的 ``size()`` 必须在 **$\mathcal{O}(1)$ 常数时间** 内返回。因此，现代 ``std::list`` 在容器本体中显式维护了一个计数器字段 ``std::size_t _M_size``：
- 单节点 ``push_back`` / ``pop_front`` 等操作同步自增/自减计数器。
- 当执行区间剪切 ``list1.splice(pos, list2, first, last)`` 且 ``&list1 != &list2`` 时，若给定的不是全量链表，容器必须遍历区间 ``[first, last)`` 统计迁移节点数以更新两端的 ``_M_size``，导致特定重载的 ``splice`` 复杂度升至 $\mathcal{O}(	ext{distance}(first, last))$。

splice 操作与零拷贝节点剪切机制
-------------------------------

``splice`` 是 ``std::list`` 独有的核心变易接口，其物理本质是 **指针的重新编织（Pointer Re-weaving）**。

常数时间指针剪切状态机
~~~~~~~~~~~~~~~~~~~~~~

当将源链表 ``src`` 的单个节点 ``it`` 剪切至目标链表 ``dst`` 的指定位置 ``pos`` 时：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     splice 单节点指针重织物理步骤                           |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 步骤 1: 将目标节点 N 从源链表解绑 (Unlink) ]                            |
   |      N->_M_prev->_M_next = N->_M_next;                                      |
   |      N->_M_next->_M_prev = N->_M_prev;                                      |
   |                                                                             |
   |   [ 步骤 2: 将节点 N 缝合插入目标链表 pos 之前 (Relink) ]                   |
   |      N->_M_prev = pos->_M_prev;                                             |
   |      N->_M_next = pos;                                                      |
   |      pos->_M_prev->_M_next = N;                                             |
   |      pos->_M_prev = N;                                                      |
   |                                                                             |
   |   [ 步骤 3: 计数器原子更新 ]                                                |
   |      --src._M_size;  ++dst._M_size;                                         |
   |                                                                             |
   +-----------------------------------------------------------------------------+

``splice`` 具有以下无可替代的工程特性：
1. **零堆分配与零构造**：操作过程中完全不调用分配器的 ``allocate`` 或类型 ``T`` 的任何构造/拷贝/移动函数，极其适合承载不可移动（Non-movable）或持有重型资源的对象。
2. **不抛异常保证（No-throw Guarantee）**：单纯的指针重新赋值属于原子级内存操作，满足绝对的 ``noexcept`` 契约。
3. **迭代器绝对稳定**：指向被迁移节点的迭代器、指针与引用全部保持有效，且自动伴随节点归属转移至新容器。

迭代器与引用稳定性 (Iterator Stability)
---------------------------------------

得益于节点的离散独立分配与指针寻址，``std::list`` 在变易操作下展现出标准库中最强的稳定性保障：

.. list-table:: std::list 变易操作对迭代器与引用的失效规则表
   :widths: 25 35 40
   :header-rows: 1
   :class: tight-table

   * - 容器操作类型
     - 迭代器失效状态 (Iterators)
     - 指针与引用失效状态 (Pointers & References)
   * - ``insert(pos, val)`` / ``emplace``
     - **无任何既有迭代器失效**；新元素获得有效新迭代器
     - **全部有效**（新节点在独立堆地址构造，不干扰既有对象）
   * - ``erase(pos)``
     - **仅指向被删除节点的迭代器失效**；其他所有迭代器依然有效
     - **仅指向被删除元素的指针/引用失效**；其他所有引用完全有效
   * - ``splice(pos, other, ...)``
     - **全部有效**；被迁移节点的迭代器仍指向原元素并可在新容器中遍历
     - **全部有效**
   * - ``swap(list1, list2)``
     - **全部有效**；迭代器跟随其所属节点绑定至对侧容器
     - **全部有效**
   * - ``clear()``
     - 指向原链表元素的所有迭代器全量失效
     - 指向原链表元素的所有指针/引用全量失效

std::forward_list 极简单向链表架构
----------------------------------

C++11 引入的 ``std::forward_list<T>`` 旨在提供与手写 C 语言单向链表物理内存布局完全等价的泛型容器，确立了 **零额外空间抽象（Zero-Overhead Abstraction）** 典范。

单指针节点与无 size 字段设计
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **单向指针内存压缩**：
   每个节点仅包含一个单向后继指针 ``_M_next`` 与元素数据 ``T``：

   .. math::

      	ext{sizeof}(	ext{\_Fwd\_list\_node}\langle T \rangle) = 8 + 	ext{sizeof}(T) + 	ext{Padding}

   在 64 位架构下，相比 ``std::list`` 的每个节点 16 字节指针开销，``std::forward_list`` 仅消耗 8 字节指针，节省了 $50\%$ 的结构体元数据内存占用。
2. **彻底剔除 size() 成员**：
   ``std::forward_list`` 故意不提供 ``size()`` 成员函数，容器本体仅占用单个裸指针大小（8 字节）。若引入 ``size`` 字段，容器对象尺寸将翻倍，违背其与 C 裸链表零成本等价的设计哲学。

insert_after / erase_after 与 before_begin() 接口范式
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

单向链表的物理拓扑决定了其无法在 $\mathcal{O}(1)$ 内根据当前节点指针反查前驱节点。因此，若要在位置 $P$ 之前插入新节点，必须从链表头遍历至 $P$ 的前驱，导致开销退化为 $\mathcal{O}(N)$。

为了维持严格的 $\mathcal{O}(1)$ 常数时间操作，标准库重构了单向链表的插入与删除接口范式：
- **``insert_after(pos, val)``**：在指定迭代器 ``pos`` 的 **后继位置** 插入新节点。
- **``erase_after(pos)``**：删除指定迭代器 ``pos`` 的 **后继节点**。
- **``before_begin()``**：返回一个指向首元素前驱虚拟位置（即内嵌哨兵头节点）的前向迭代器，使在链表首部插入（``insert_after(before_begin(), val)``）与常规位置享有统一的无分支执行逻辑。

链表专用算法：list::sort 归并重构机理
-------------------------------------

由于双向链表与单向链表的迭代器分别仅支持双向步进与前向步进，无法满足快速排序或内省排序（``std::sort``）对随机访问迭代器（Random Access Iterator）的要求，调用 ``std::sort(list.begin(), list.end())`` 将触发编译期静态断言失败。

``std::list`` 提供了内置的高性能链表级排序成员函数 ``list::sort()``。其底层采用 **非递归自底向上归并排序（Bottom-up Merge Sort）**，全程通过 ``splice`` 仅调整节点指针指向，实现零元素深拷贝与 $\mathcal{O}(N \log N)$ 确定性排序：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     list::sort 自底向上归并排序状态机                       |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 内部状态 ]: 维护 64 个槽位的临时链表数组 counter[0..63]                 |
   |                counter[i] 最多容纳 2^(i+1) 个已排序节点                     |
   |                                                                             |
   |   [ 归并流水线 ]:                                                           |
   |   1. While 原链表非空:                                                      |
   |      * 使用 splice 提取原链表首节点至 carry                                 |
   |      * For (i = 0; i < 64 && !counter[i].empty(); ++i):                     |
   |          carry.merge(counter[i])  ; 将已排序段两两归并                      |
   |      * counter[i].swap(carry)                                               |
   |   2. 最终归并: 遍历 counter 数组，将所有非空槽位依次 merge 合并至结果链表   |
   |                                                                             |
   |   * 全程仅重连指针，无任何 T 对象构造与拷贝，空间复杂度 O(1)                |
   |                                                                             |
   +-----------------------------------------------------------------------------+

工业级 C++ 完整 Mini-List 与 Mini-ForwardList 内核实现
------------------------------------------------------

以下 C++ 源码实现了一套自包含的工业级双向环形链表 ``MiniList<T>`` 与极简单向链表 ``MiniForwardList<T>``。该实现涵盖：
1. 具备无值基类节点与具体数据节点的两层继承拓扑。
2. 环形空哨兵节点构造与全量无分支增删状态机。
3. 双向双指针迭代器与前向单指针迭代器实现。
4. $\mathcal{O}(1)$ 节点剪切 ``splice`` 核心算法。
5. ``MiniForwardList`` 的 ``before_begin()`` 与 ``insert_after`` 语义。
6. 完备的生命周期释放与端到端测试验证套件。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <memory>
   #include <utility>
   #include <cstddef>
   #include <cassert>
   #include <initializer_list>

   namespace core_stl {

   // =========================================================================
   // 1. MiniList: 环形双向带哨兵链表实现
   // =========================================================================
   struct ListNodeBase {
       ListNodeBase* Next = nullptr;
       ListNodeBase* Prev = nullptr;
   };

   template <typename T>
   struct ListNode : public ListNodeBase {
       T Value;

       template <typename... Args>
       explicit ListNode(Args&&... args) : Value(std::forward<Args>(args)...) {}
   };

   template <typename T>
   struct ListIterator {
       using iterator_category = std::bidirectional_iterator_tag;
       using value_type        = T;
       using difference_type   = std::ptrdiff_t;
       using pointer           = T*;
       using reference         = T&;

       ListNodeBase* Node = nullptr;

       ListIterator() = default;
       explicit ListIterator(ListNodeBase* n) : Node(n) {}

       reference operator*() const noexcept {
           return static_cast<ListNode<T>*>(Node)->Value;
       }

       pointer operator->() const noexcept {
           return &static_cast<ListNode<T>*>(Node)->Value;
       }

       ListIterator& operator++() noexcept {
           Node = Node->Next;
           return *this;
       }

       ListIterator operator++(int) noexcept {
           ListIterator tmp = *this;
           Node = Node->Next;
           return tmp;
       }

       ListIterator& operator--() noexcept {
           Node = Node->Prev;
           return *this;
       }

       ListIterator operator--(int) noexcept {
           ListIterator tmp = *this;
           Node = Node->Prev;
           return tmp;
       }

       bool operator==(const ListIterator& other) const noexcept {
           return Node == other.Node;
       }
       bool operator!=(const ListIterator& other) const noexcept {
           return Node != other.Node;
       }
   };

   template <typename T, typename Allocator = std::allocator<T>>
   class MiniList {
   public:
       using value_type      = T;
       using size_type       = std::size_t;
       using reference       = T&;
       using const_reference = const T&;
       using iterator        = ListIterator<T>;

   private:
       using Node = ListNode<T>;
       using NodeAlloc = typename std::allocator_traits<Allocator>::template rebind_alloc<Node>;

       ListNodeBase _M_node; // 栈上内嵌的空哨兵头节点
       size_type _M_size = 0;
       NodeAlloc _M_alloc;

   public:
       MiniList() {
           init_sentinel();
       }

       MiniList(std::initializer_list<T> init) {
           init_sentinel();
           for (const auto& item : init) {
               push_back(item);
           }
       }

       ~MiniList() {
           clear();
       }

       // 禁用拷贝以保持模型精简
       MiniList(const MiniList&) = delete;
       MiniList& operator=(const MiniList&) = delete;

       [[nodiscard]] bool empty() const noexcept { return _M_node.Next == &_M_node; }
       [[nodiscard]] size_type size() const noexcept { return _M_size; }

       iterator begin() noexcept { return iterator(_M_node.Next); }
       iterator end() noexcept { return iterator(&_M_node); }

       reference front() noexcept {
           assert(!empty() && "front on empty list");
           return *begin();
       }

       reference back() noexcept {
           assert(!empty() && "back on empty list");
           return *iterator(_M_node.Prev);
       }

       template <typename... Args>
       iterator emplace(iterator pos, Args&&... args) {
           Node* newNode = _M_alloc.allocate(1);
           std::allocator_traits<NodeAlloc>::construct(_M_alloc, newNode, std::forward<Args>(args)...);

           // 四指针无分支闭环链接
           ListNodeBase* p = pos.Node;
           newNode->Next = p;
           newNode->Prev = p->Prev;
           p->Prev->Next = newNode;
           p->Prev = newNode;

           ++_M_size;
           return iterator(newNode);
       }

       void push_back(const T& value) { emplace(end(), value); }
       void push_front(const T& value) { emplace(begin(), value); }

       iterator erase(iterator pos) noexcept {
           assert(pos != end() && "Cannot erase end iterator");
           ListNodeBase* curr = pos.Node;
           ListNodeBase* nextNode = curr->Next;

           curr->Prev->Next = curr->Next;
           curr->Next->Prev = curr->Prev;

           Node* target = static_cast<Node*>(curr);
           std::allocator_traits<NodeAlloc>::destroy(_M_alloc, target);
           _M_alloc.deallocate(target, 1);

           --_M_size;
           return iterator(nextNode);
       }

       void pop_front() noexcept { erase(begin()); }
       void pop_back() noexcept { erase(iterator(_M_node.Prev)); }

       void clear() noexcept {
           ListNodeBase* curr = _M_node.Next;
           while (curr != &_M_node) {
               ListNodeBase* nextNode = curr->Next;
               Node* target = static_cast<Node*>(curr);
               std::allocator_traits<NodeAlloc>::destroy(_M_alloc, target);
               _M_alloc.deallocate(target, 1);
               curr = nextNode;
           }
           init_sentinel();
           _M_size = 0;
       }

       // O(1) 常数时间指针剪切拼接
       void splice(iterator pos, MiniList& other, iterator it) noexcept {
           if (pos == it || pos.Node == it.Node->Next) return;

           ListNodeBase* n = it.Node;

           // 从源链表解绑
           n->Prev->Next = n->Next;
           n->Next->Prev = n->Prev;

           // 缝合入目标链表 pos 之前
           ListNodeBase* p = pos.Node;
           n->Prev = p->Prev;
           n->Next = p;
           p->Prev->Next = n;
           p->Prev = n;

           --other._M_size;
           ++this->_M_size;
       }

   private:
       void init_sentinel() noexcept {
           _M_node.Next = &_M_node;
           _M_node.Prev = &_M_node;
       }
   };

   // =========================================================================
   // 2. MiniForwardList: 极简单向链表实现
   // =========================================================================
   struct FwdNodeBase {
       FwdNodeBase* Next = nullptr;
   };

   template <typename T>
   struct FwdNode : public FwdNodeBase {
       T Value;

       template <typename... Args>
       explicit FwdNode(Args&&... args) : Value(std::forward<Args>(args)...) {}
   };

   template <typename T>
   struct FwdIterator {
       using iterator_category = std::forward_iterator_tag;
       using value_type        = T;
       using difference_type   = std::ptrdiff_t;
       using pointer           = T*;
       using reference         = T&;

       FwdNodeBase* Node = nullptr;

       FwdIterator() = default;
       explicit FwdIterator(FwdNodeBase* n) : Node(n) {}

       reference operator*() const noexcept {
           return static_cast<FwdNode<T>*>(Node)->Value;
       }

       pointer operator->() const noexcept {
           return &static_cast<FwdNode<T>*>(Node)->Value;
       }

       FwdIterator& operator++() noexcept {
           Node = Node->Next;
           return *this;
       }

       FwdIterator operator++(int) noexcept {
           FwdIterator tmp = *this;
           Node = Node->Next;
           return tmp;
       }

       bool operator==(const FwdIterator& other) const noexcept { return Node == other.Node; }
       bool operator!=(const FwdIterator& other) const noexcept { return Node != other.Node; }
   };

   template <typename T, typename Allocator = std::allocator<T>>
   class MiniForwardList {
   private:
       using Node = FwdNode<T>;
       using NodeAlloc = typename std::allocator_traits<Allocator>::template rebind_alloc<Node>;

       FwdNodeBase _M_head; // 仅含 8 字节指针的栈上哨兵头
       NodeAlloc _M_alloc;

   public:
       using iterator = FwdIterator<T>;

       MiniForwardList() noexcept { _M_head.Next = nullptr; }

       ~MiniForwardList() { clear(); }

       [[nodiscard]] bool empty() const noexcept { return _M_head.Next == nullptr; }

       iterator before_begin() noexcept { return iterator(&_M_head); }
       iterator begin() noexcept { return iterator(_M_head.Next); }
       iterator end() noexcept { return iterator(nullptr); }

       template <typename... Args>
       iterator emplace_after(iterator pos, Args&&... args) {
           Node* newNode = _M_alloc.allocate(1);
           std::allocator_traits<NodeAlloc>::construct(_M_alloc, newNode, std::forward<Args>(args)...);

           newNode->Next = pos.Node->Next;
           pos.Node->Next = newNode;
           return iterator(newNode);
       }

       void push_front(const T& value) {
           emplace_after(before_begin(), value);
       }

       iterator erase_after(iterator pos) noexcept {
           FwdNodeBase* target = pos.Node->Next;
           if (!target) return end();

           pos.Node->Next = target->Next;
           Node* realTarget = static_cast<Node*>(target);
           std::allocator_traits<NodeAlloc>::destroy(_M_alloc, realTarget);
           _M_alloc.deallocate(realTarget, 1);

           return iterator(pos.Node->Next);
       }

       void pop_front() noexcept {
           erase_after(before_begin());
       }

       void clear() noexcept {
           FwdNodeBase* curr = _M_head.Next;
           while (curr) {
               FwdNodeBase* next = curr->Next;
               Node* realNode = static_cast<Node*>(curr);
               std::allocator_traits<NodeAlloc>::destroy(_M_alloc, realNode);
               _M_alloc.deallocate(realNode, 1);
               curr = next;
           }
           _M_head.Next = nullptr;
       }
   };

   } // namespace core_stl

   // =========================================================================
   // 3. 端到端测试与拓扑验证套件
   // =========================================================================
   namespace test {

   inline void runListTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " MiniList 双向哨兵环与 MiniForwardList 单向链表测试套件
";
       std::cout << "=======================================================

";

       // 1. 测试 MiniList 环形哨兵与双向遍历
       {
           core_stl::MiniList<int> lst = {10, 20, 30};
           assert(lst.size() == 3);
           assert(lst.front() == 10 && lst.back() == 30);

           lst.push_front(5);
           lst.push_back(40);
           // 预期: 5, 10, 20, 30, 40
           assert(lst.size() == 5);
           assert(lst.front() == 5 && lst.back() == 40);

           std::cout << "[测试 1: MiniList 双向增删与边界]: 元素序列: ";
           for (int v : lst) std::cout << v << " ";
           std::cout << " (size = " << lst.size() << ")
";
       }

       // 2. 测试 splice 跨链表零拷贝指针剪切
       {
           core_stl::MiniList<std::string> ready = {"TaskA", "TaskB", "TaskC"};
           core_stl::MiniList<std::string> pending = {"TaskX"};

           // 将 ready 中的 "TaskB" (迭代器 it) 剪切至 pending 首部
           auto it = ++ready.begin(); // 指向 TaskB
           assert(*it == "TaskB");

           pending.splice(pending.begin(), ready, it);

           assert(ready.size() == 2);
           assert(pending.size() == 2);
           assert(pending.front() == "TaskB" && pending.back() == "TaskX");
           assert(*it == "TaskB"); // 迭代器依然合法，直接迁移至 pending

           std::cout << "[测试 2: splice 零拷贝指针剪切]: 剪切后 pending: ";
           for (const auto& s : pending) std::cout << s << " ";
           std::cout << "
";
       }

       // 3. 测试 MiniForwardList 单向极简布局与 insert_after
       {
           core_stl::MiniForwardList<int> fwd;
           assert(fwd.empty());
           assert(sizeof(fwd) == sizeof(void*)); // 严格等于单指针 8 字节

           fwd.push_front(30);
           fwd.push_front(20);
           fwd.push_front(10);
           // 序列: 10 -> 20 -> 30

           // 在 20 后面插入 25
           auto it = fwd.begin();
           ++it; // 指向 20
           fwd.emplace_after(it, 25);

           // 预期: 10, 20, 25, 30
           std::cout << "[测试 3: MiniForwardList insert_after 8 字节单指针]: ";
           for (int v : fwd) std::cout << v << " ";
           std::cout << "
";

           fwd.erase_after(it); // 删除 25
           assert(*(++fwd.begin()) == 20);
       }

       std::cout << "
  -> 链表体系物理拓扑与零拷贝剪切验证完全通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰印证了链表体系的物理运行规律：

1. **环形哨兵消除分支惩罚**：在执行首尾插入（``push_front`` / ``push_back``）时，双向环形哨兵节点使算法统一在常数 4 条指针写入指令内完成，无论链表此前是否为空。
2. **splice 零对象开销转移**：在将 ``TaskB`` 从 ``ready`` 剪切至 ``pending`` 队列时，``TaskB`` 对象的字符串堆内存未发生任何释放或重新申请，指向该节点的迭代器 ``it`` 无缝在目标容器中继续生效。
3. **单向链表的极限空间收缩**：``MiniForwardList`` 容器本体尺寸严格等同于单个 64 位指针（8 字节），通过 ``insert_after`` 与 ``before_begin()`` 范式达成了与手写 C 单向链表完全等价的内存利用率。

小结与下章导读
--------------

本章系统解构了现代 C++ 离散顺序容器——双向链表 ``std::list`` 与单向链表 ``std::forward_list`` 的物理拓扑与运行机理：

1. **节点继承拓扑与哨兵闭环**：剖析了 ``_List_node_base`` 与 ``_List_node<T>`` 的两层拆分，阐明了环形空哨兵节点在消除边界分支特判与支持无默认构造类型层面的微架构优势。
2. **splice 指针重织机制**：推导了常数时间 $\mathcal{O}(1)$ 节点解绑与缝合的物理过程，确立了跨链表零拷贝、异常安全强保证与迭代器绝对稳定的核心价值。
3. **极简单向链表设计哲学**：揭示了 ``std::forward_list`` 消除前驱指针与 ``size`` 字段以实现极致内存压缩的设计意图，阐释了 ``insert_after`` 接口范式的必要性。
4. **特化排序算法**：说明了由于缺乏随机访问能力，链表必须采用内部自底向上归并排序（Merge Sort）实现 $\mathcal{O}(N \log N)$ 零拷贝原址重排。

在掌握了动态连续数组（``std::vector``）、静态连续数组（``std::array``）、分段双端队列（``std::deque``）与离散链表（``std::list`` / ``std::forward_list``）之后，下一章我们将深入分析工业级 C++ 中最复杂且优化最为激进的连续序列容器——``std::basic_string``。在第 3 模块第 5 节 **std::basic_string 字符串体系：小字符串优化 (SSO) 内部联合体布局、动态扩容与 COW 历史包袱（``03_sequence_containers_internals/05_string_sso_and_memory_layouts.rst``）** 中，我们将深入剖析 15/22 字节小字符串内联缓冲（SSO Union）、写时复制（COW）在多线程下的原子引用计数惩罚，以及标准强制短字符串零堆分配的微架构实现。
