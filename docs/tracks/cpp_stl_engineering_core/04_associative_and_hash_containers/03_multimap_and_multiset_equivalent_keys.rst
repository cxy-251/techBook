====================================================================================================
std::multimap 与 std::multiset 多重容器：等价键连续区间存储、equal_range 二分定位与插入策略
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 4 模块第 2 节（``04_associative_and_hash_containers/02_map_and_set_ordered_associative_containers.rst``）中，我们系统解构了唯一键有序容器 ``std::set`` 与 ``std::map`` 的严格弱序（Strict Weak Ordering）契约、``const Key`` 强类型约束以及基于对数二分搜索的 ``lower_bound`` / ``upper_bound`` 收敛状态机。唯一键容器在遇到比较器等价键（$
eg(a < b) \land 
eg(b < a)$）时，强制执行覆盖或拒绝插入。然而，在实际工业级系统（如倒排索引、高频行情多重委托单薄、路由路由表多重下一跳、事件时间戳多重订阅）中，同一键可能关联多个完全独立的对象实体。为了支持重复键的存储与高效检索，现代 C++ 标准库提供了 **``std::multiset``** 与 **``std::multimap``**。本章深入剖析多重容器中等价键在红黑树内部的拓扑聚集机理、C++11 插入顺序保持契约（FIFO Stability）、``insert_equal`` 插入分发状态机、``equal_range`` 范围边界收敛、``count()`` 的线性扫描复杂度代价、单节点删除与全等价键范围删除（Range Erase）的指针重织，以及对比 ``std::multimap<K, V>`` 与 ``std::map<K, std::vector<V>>`` 的微架构选型权衡。

等价键 (Equivalent Keys) 的物理语义与红黑树拓扑聚集
---------------------------------------------------

在有序多重容器中，重复键的判定同样基于比较器定义的等价性关系：

.. math::

   	ext{Equiv}(a, b) \iff 
eg	ext{comp}(a, b) \land 
eg	ext{comp}(b, a)

中序遍历下的等价键连续性定理
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**定理（Contiguous In-order Property）**：
在一棵满足二叉搜索树有序性与红黑树平衡公理的树形结构中，所有彼此等价的键集合 $\{N_1, N_2, \dots, N_k\}$ 在中序遍历（In-order Traversal）序列中必然构成一个 **连续且紧密相邻的半开区间 $[first, last)$**。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     等价键在红黑树中的中序连续聚集拓扑                      |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |                                [ Key = 20 ]                                 |
   |                                /          \                                 |
   |                               /            \                                |
   |                       [ Key = 10 ]        [ Key = 30 ]                      |
   |                       /          \                                          |
   |                      v            v                                         |
   |               [ Key = 10 ]     [ Key = 10 ]  <--- 等价键分散在树形分支中     |
   |               (Inst #1)        (Inst #3)                                    |
   |                   |                |                                        |
   |                   +----------------+----------------+                       |
   |                                    |                |                       |
   |                                    v                v                       |
   |   * 逻辑中序遍历升序序列: ... < 10(#1) == 10(#2) == 10(#3) < 20 < 30 ...      |
   |   * equal_range(10) 圈定连续范围: [ 10(#1), 20 )                            |
   |                                                                             |
   +-----------------------------------------------------------------------------+

尽管等价键在物理树形拓扑中可能作为左孩子或右孩子分布在不同深度的节点上，但二叉搜索树的比较规则确保了任何严格小于 10 的节点必然位于该等价组左侧，任何严格大于 10 的节点必然位于右侧，从而在中序迭代器遍历时呈现严格连续的聚集形态。

独立节点设计 vs map<Key, vector<Value>> 架构权衡
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

许多工程师会面临架构选型：是直接使用 ``std::multimap<Key, Value>``，还是使用 ``std::map<Key, std::vector<Value>>``？

.. list-table:: std::multimap 与 std::map<Key, vector<Value>> 微架构对比
   :widths: 22 38 40
   :header-rows: 1
   :class: tight-table

   * - 评价维度
     - ``std::multimap<Key, Value>``
     - ``std::map<Key, std::vector<Value>>``
   * - 内存分配拓扑
     - 每个元素对应一个独立的堆节点（Node-based）
     - 每个唯一键对应一个树节点，等价值聚合在动态连续数组（Vector）中
   * - 内存元数据开销
     - 较高（每个元素均携带 24 字节红黑树指针+颜色）
     - **极低**（同键海量值时，Vector 连续存储均摊开销趋近于 0）
   * - 插入与删除性能
     - **常数级 $\mathcal{O}(1)$ 节点释放与重织**；无任何已有元素内存搬移
     - 中间元素删除可能触发 Vector 内部后续元素的线性内存搬迁（$\mathcal{O}(M)$）
   * - 迭代器稳定性
     - **极强**：插入与删除单节点不影响其他任何等价节点的迭代器与引用
     - **较弱**：Vector 扩容导致已有值的指针、引用全量失效
   * - 选型决策边界
     - **适合高频变易、要求引用绝对稳定、等价键数量较少且分布均匀的场景**
     - **适合静态聚合、等价值数量庞大、高频顺序遍历的批处理场景**

insert_equal 插入分发策略与 C++11 顺序保持契约
----------------------------------------------

C++11 相对顺序稳定性契约 (FIFO Order Preservation)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 C++98 标准中，标准库未对插入相同等价键的相对前后顺序做出严格规定。
**C++11 标准（LWG Issue 233）正式确立了强约束**：
**向 `std::multiset` 或 `std::multimap` 插入等价键时，新插入的元素必须严格放置在容器中所有已有等价键的末尾（即保持先进先出 FIFO 相对稳定性）。**

这意味着多次插入相同的键，按迭代器顺序遍历时，其出现顺序严格等同于插入的时序历史。

insert_equal 状态机实现机理
~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了严格践行 C++11 的 FIFO 稳定性，红黑树的 ``insert_equal`` 算法执行以下搜索流转：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     insert_equal 寻找插入点物理状态机                       |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 目标 ]: 将新节点 Z 插入至已有等价键的最右侧 (upper_bound 语义)          |
   |                                                                             |
   |   [ 遍历游标 x = Root, 候选父节点 y = Header ]:                             |
   |      While x != nullptr:                                                    |
   |         y = x;                                                              |
   |         If comp(key(Z), key(x)):                                            |
   |            * key(Z) < key(x): 必在左侧                                      |
   |            x = x->Left;                                                     |
   |         Else:                                                               |
   |            * key(Z) >= key(x): 包含等价情况!                                |
   |            * 关键: 当 key(Z) 等价于 key(x) 时，算法强制向右子树推进!        |
   |            x = x->Right;                                                    |
   |                                                                             |
   |   [ 节点挂载 ]:                                                             |
   |      * 将 Z 挂接在 y 的对应孩子侧，执行 rebalance_after_insert(Z)            |
   |                                                                             |
   +-----------------------------------------------------------------------------+

当新键与当前节点等价时，由于比较算子 ``comp(key(Z), key(x))`` 返回 ``false``，算法强制将搜索分支导向右子树（``x = x->Right``）。这一微架构决策从数学上保证了新节点必然插入在所有已有等价键的中序后继位置，达成了严格的 FIFO 顺序保证。

equal_range、lower_bound 与 count 复杂度陷阱
--------------------------------------------

equal_range 范围边界收敛
~~~~~~~~~~~~~~~~~~~~~~~~

在多重容器中，处理特定键的所有等价实例必须使用 ``equal_range(k)``：

.. math::

   	ext{equal\_range}(k) = \langle 	ext{lower\_bound}(k), 	ext{upper\_bound}(k) \rangle

- **``lower_bound(k)``**：定位首个不小于 $k$（$\ge k$）的节点，精确命中第一个等价键。
- **``upper_bound(k)``**：定位首个严格大于 $k$（$> k$）的节点，精确命中等价键区间的尾后位置。
- **复杂度**：利用红黑树的对数收敛特性，``equal_range`` 的时间复杂度为标准的 $\mathcal{O}(\log N)$。

count() 成员函数的线性时间复杂度陷阱
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在唯一键容器中，``count(k)`` 仅返回 0 或 1，耗时为 $\mathcal{O}(\log N)$。
然而，**在多重容器中，`count(k)` 的时间复杂度为 $\mathcal{O}(\log N + S)$**（其中 $S$ 为等价键的实际数量）：
- 标准库首先调用 ``equal_range(k)`` 定位区间 $[first, last)$（耗时 $\mathcal{O}(\log N)$）。
- 随后调用 ``std::distance(first, last)`` 逐节点步进统计区间长度（耗时 $\mathcal{O}(S)$）。
- **工程最佳实践**：若仅需判断容器中是否存在某个键，严禁调用 ``multimap::count(k) > 0``（当存在 10 万个等价键时将引发灾难性的 10 万次指针遍历），必须使用 ``multimap::find(k) != multimap::end()`` 在 $\mathcal{O}(\log N)$ 内短路返回。

等价键删除语义与迭代器失效边界
------------------------------

多重容器提供了两类截然不同的删除重载：

1. 按迭代器单节点精准删除：``erase(iterator pos)``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- 仅将迭代器 ``pos`` 指向的单个特定节点从红黑树中剥离并释放。
- **失效范围**：仅有被删除的 ``pos`` 迭代器失效；**其他所有等价键节点（无论位于其前还是其后）的迭代器、指针与引用保持绝对有效**。

2. 按键全量范围删除：``erase(const Key& k)``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- 首先调用 ``equal_range(k)`` 圈定连续等价区间 $[first, last)$。
- 循环调用单节点删除逻辑，销毁区间内的全部 $S$ 个节点并执行局部的红黑树平衡修复。
- 返回值：返回被物理删除的节点总数 $S$。

工业级 C++ 完整 Mini-Multimap 与 Mini-Multiset 内核实现
-------------------------------------------------------

以下 C++ 源码在红黑树内核中实现了自包含的 ``MiniMultiset<Key>`` 与 ``MiniMultimap<Key, Value>``。该实现涵盖：
1. 具备 FIFO 顺序保持契约的 ``insert_equal`` 插入状态机。
2. 对数级 ``lower_bound``、``upper_bound`` 与 ``equal_range``。
3. 区分单节点精准删除 ``erase(iterator)`` 与全量等价键删除 ``erase(key)``。
4. 键常量性强类型封装（``pair<const Key, Value>``）与中序遍历。
5. 端到端测试套件（验证等价键聚集、FIFO 插入时序稳定性、单节点删除与范围删除）。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <memory>
   #include <utility>
   #include <cassert>
   #include <functional>
   #include <string>
   #include <vector>

   namespace core_stl {

   enum class RbColor : uint8_t { Red, Black };

   struct RbNodeBase {
       RbColor Color = RbColor::Red;
       RbNodeBase* Parent = nullptr;
       RbNodeBase* Left   = nullptr;
       RbNodeBase* Right  = nullptr;

       static RbNodeBase* minimum(RbNodeBase* x) noexcept {
           while (x->Left) x = x->Left;
           return x;
       }

       static RbNodeBase* maximum(RbNodeBase* x) noexcept {
           while (x->Right) x = x->Right;
           return x;
       }
   };

   template <typename Val>
   struct RbNode : public RbNodeBase {
       Val Value;

       template <typename... Args>
       explicit RbNode(Args&&... args) : Value(std::forward<Args>(args)...) {}
   };

   template <typename Val, typename Ref, typename Ptr>
   struct RbTreeIterator {
       using iterator_category = std::bidirectional_iterator_tag;
       using value_type        = Val;
       using reference         = Ref;
       using pointer           = Ptr;

       RbNodeBase* Node = nullptr;

       RbTreeIterator() = default;
       explicit RbTreeIterator(RbNodeBase* n) : Node(n) {}

       reference operator*() const noexcept {
           return static_cast<RbNode<Val>*>(Node)->Value;
       }

       pointer operator->() const noexcept {
           return &static_cast<RbNode<Val>*>(Node)->Value;
       }

       RbTreeIterator& operator++() noexcept {
           if (Node->Right) {
               Node = RbNodeBase::minimum(Node->Right);
           } else {
               RbNodeBase* p = Node->Parent;
               while (Node == p->Right) {
                   Node = p;
                   p = p->Parent;
               }
               if (Node->Right != p) Node = p;
           }
           return *this;
       }

       RbTreeIterator operator++(int) noexcept {
           RbTreeIterator tmp = *this;
           ++(*this);
           return tmp;
       }

       bool operator==(const RbTreeIterator& other) const noexcept { return Node == other.Node; }
       bool operator!=(const RbTreeIterator& other) const noexcept { return Node != other.Node; }
   };

   template <typename Key, typename Value, typename KeyOfValue, typename Compare = std::less<Key>>
   class MultiRbTree {
   public:
       using iterator       = RbTreeIterator<Value, Value&, Value*>;
       using const_iterator = RbTreeIterator<Value, const Value&, const Value*>;

   private:
       using Node = RbNode<Value>;
       using Alloc = std::allocator<Node>;

       RbNodeBase _M_header;
       size_t _M_node_count = 0;
       Compare _M_comp;
       Alloc _M_alloc;

       RbNodeBase*& root() noexcept { return _M_header.Parent; }
       RbNodeBase* root() const noexcept { return _M_header.Parent; }
       RbNodeBase*& leftmost() noexcept { return _M_header.Left; }
       RbNodeBase* leftmost() const noexcept { return _M_header.Left; }
       RbNodeBase*& rightmost() noexcept { return _M_header.Right; }
       RbNodeBase* rightmost() const noexcept { return _M_header.Right; }

   public:
       MultiRbTree() {
           _M_header.Color = RbColor::Red;
           _M_header.Parent = nullptr;
           _M_header.Left = &_M_header;
           _M_header.Right = &_M_header;
       }

       ~MultiRbTree() { clear(); }

       [[nodiscard]] size_t size() const noexcept { return _M_node_count; }
       [[nodiscard]] bool empty() const noexcept { return _M_node_count == 0; }

       iterator begin() noexcept { return iterator(leftmost()); }
       iterator end() noexcept { return iterator(&_M_header); }
       const_iterator begin() const noexcept { return const_iterator(leftmost()); }
       const_iterator end() const noexcept { return const_iterator(const_cast<RbNodeBase*>(&_M_header)); }

       const Key& key(const RbNodeBase* n) const {
           return KeyOfValue()(static_cast<const Node*>(n)->Value);
       }

       iterator lower_bound(const Key& k) {
           RbNodeBase* y = &_M_header;
           RbNodeBase* x = root();
           while (x) {
               if (!_M_comp(key(x), k)) {
                   y = x;
                   x = x->Left;
               } else {
                   x = x->Right;
               }
           }
           return iterator(y);
       }

       iterator upper_bound(const Key& k) {
           RbNodeBase* y = &_M_header;
           RbNodeBase* x = root();
           while (x) {
               if (_M_comp(k, key(x))) {
                   y = x;
                   x = x->Left;
               } else {
                   x = x->Right;
               }
           }
           return iterator(y);
       }

       std::pair<iterator, iterator> equal_range(const Key& k) {
           return {lower_bound(k), upper_bound(k)};
       }

       iterator find(const Key& k) {
           iterator j = lower_bound(k);
           return (j == end() || _M_comp(k, key(j.Node))) ? end() : j;
       }

       // 核心: 支持等价键的稳定插入 (FIFO 顺序保持)
       template <typename... Args>
       iterator emplace_equal(Args&&... args) {
           Node* z = _M_alloc.allocate(1);
           std::allocator_traits<Alloc>::construct(_M_alloc, z, std::forward<Args>(args)...);

           const Key& k = KeyOfValue()(z->Value);
           RbNodeBase* x = root();
           RbNodeBase* y = &_M_header;

           while (x) {
               y = x;
               // 若 k < key(x) 向左; 若 k >= key(x) 强制向右 (保证等价键落在右侧，维持 FIFO)
               x = _M_comp(k, key(x)) ? x->Left : x->Right;
           }

           bool insert_left = (x != nullptr || y == &_M_header || _M_comp(k, key(y)));
           return insert_node_at(insert_left, y, z);
       }

       iterator erase(iterator pos) noexcept {
           assert(pos != end() && "Cannot erase end iterator");
           RbNodeBase* y = pos.Node;
           iterator next_it = pos;
           ++next_it;

           erase_node(y);
           --_M_node_count;
           return next_it;
       }

       size_t erase(const Key& k) {
           auto [first, last] = equal_range(k);
           size_t count = 0;
           while (first != last) {
               first = erase(first);
               ++count;
           }
           return count;
       }

       void clear() noexcept {
           erase_subtree(root());
           _M_header.Parent = nullptr;
           _M_header.Left = &_M_header;
           _M_header.Right = &_M_header;
           _M_node_count = 0;
       }

   private:
       void erase_subtree(RbNodeBase* x) noexcept {
           while (x) {
               erase_subtree(x->Right);
               RbNodeBase* y = x->Left;
               Node* target = static_cast<Node*>(x);
               std::allocator_traits<Alloc>::destroy(_M_alloc, target);
               _M_alloc.deallocate(target, 1);
               x = y;
           }
       }

       iterator insert_node_at(bool insert_left, RbNodeBase* p, Node* z) {
           z->Left = nullptr;
           z->Right = nullptr;
           z->Color = RbColor::Red;

           if (p == &_M_header) {
               root() = z;
               leftmost() = z;
               rightmost() = z;
               z->Parent = &_M_header;
           } else if (insert_left) {
               p->Left = z;
               z->Parent = p;
               if (p == leftmost()) leftmost() = z;
           } else {
               p->Right = z;
               z->Parent = p;
               if (p == rightmost()) rightmost() = z;
           }

           rebalance_after_insert(z);
           ++_M_node_count;
           return iterator(z);
       }

       void rotate_left(RbNodeBase* x) noexcept {
           RbNodeBase* y = x->Right;
           x->Right = y->Left;
           if (y->Left) y->Left->Parent = x;
           y->Parent = x->Parent;
           if (x == root()) root() = y;
           else if (x == x->Parent->Left) x->Parent->Left = y;
           else x->Parent->Right = y;
           y->Left = x;
           x->Parent = y;
       }

       void rotate_right(RbNodeBase* x) noexcept {
           RbNodeBase* y = x->Left;
           x->Left = y->Right;
           if (y->Right) y->Right->Parent = x;
           y->Parent = x->Parent;
           if (x == root()) root() = y;
           else if (x == x->Parent->Right) x->Parent->Right = y;
           else x->Parent->Left = y;
           y->Right = x;
           x->Parent = y;
       }

       void rebalance_after_insert(RbNodeBase* z) noexcept {
           while (z != root() && z->Parent->Color == RbColor::Red) {
               RbNodeBase* p = z->Parent;
               RbNodeBase* g = p->Parent;
               if (p == g->Left) {
                   RbNodeBase* u = g->Right;
                   if (u && u->Color == RbColor::Red) {
                       p->Color = RbColor::Black;
                       u->Color = RbColor::Black;
                       g->Color = RbColor::Red;
                       z = g;
                   } else {
                       if (z == p->Right) {
                           z = p;
                           rotate_left(z);
                           p = z->Parent;
                       }
                       p->Color = RbColor::Black;
                       g->Color = RbColor::Red;
                       rotate_right(g);
                   }
               } else {
                   RbNodeBase* u = g->Left;
                   if (u && u->Color == RbColor::Red) {
                       p->Color = RbColor::Black;
                       u->Color = RbColor::Black;
                       g->Color = RbColor::Red;
                       z = g;
                   } else {
                       if (z == p->Left) {
                           z = p;
                           rotate_right(z);
                           p = z->Parent;
                       }
                       p->Color = RbColor::Black;
                       g->Color = RbColor::Red;
                       rotate_left(g);
                   }
               }
           }
           root()->Color = RbColor::Black;
       }

       void erase_node(RbNodeBase* z) noexcept {
           RbNodeBase* y = (z->Left && z->Right) ? RbNodeBase::minimum(z->Right) : z;
           RbNodeBase* x = y->Left ? y->Left : y->Right;
           RbNodeBase* p = y->Parent;

           if (x) x->Parent = p;

           if (y == root()) {
               root() = x;
           } else if (y == p->Left) {
               p->Left = x;
           } else {
               p->Right = x;
           }

           if (y == leftmost()) {
               leftmost() = (y->Right && x) ? RbNodeBase::minimum(x) : p;
           }
           if (y == rightmost()) {
               rightmost() = (y->Left && x) ? RbNodeBase::maximum(x) : p;
           }

           // 若 y != z，将 y 移植到 z 的位置
           if (y != z) {
               y->Parent = z->Parent;
               y->Left = z->Left;
               y->Right = z->Right;
               y->Color = z->Color;

               if (z->Left) z->Left->Parent = y;
               if (z->Right) z->Right->Parent = y;

               if (z == root()) root() = y;
               else if (z == z->Parent->Left) z->Parent->Left = y;
               else z->Parent->Right = y;
           }

           Node* target = static_cast<Node*>(z);
           std::allocator_traits<Alloc>::destroy(_M_alloc, target);
           _M_alloc.deallocate(target, 1);
       }
   };

   // =========================================================================
   // 2. MiniMultiset 与 MiniMultimap 容器适配
   // =========================================================================
   template <typename Key, typename Compare = std::less<Key>>
   class MiniMultiset {
       struct Identity {
           const Key& operator()(const Key& k) const noexcept { return k; }
       };
       using TreeType = MultiRbTree<Key, Key, Identity, Compare>;
       TreeType _M_tree;

   public:
       using iterator = typename TreeType::const_iterator;

       MiniMultiset() = default;

       [[nodiscard]] size_t size() const noexcept { return _M_tree.size(); }
       [[nodiscard]] bool empty() const noexcept { return _M_tree.empty(); }

       iterator begin() const noexcept { return _M_tree.begin(); }
       iterator end() const noexcept { return _M_tree.end(); }

       iterator insert(const Key& k) {
           return iterator(_M_tree.emplace_equal(k).Node);
       }

       std::pair<iterator, iterator> equal_range(const Key& k) const {
           auto res = const_cast<TreeType&>(_M_tree).equal_range(k);
           return {iterator(res.first.Node), iterator(res.second.Node)};
       }

       size_t erase(const Key& k) { return _M_tree.erase(k); }
   };

   template <typename Key, typename T, typename Compare = std::less<Key>>
   class MiniMultimap {
   public:
       using value_type = std::pair<const Key, T>;

   private:
       struct Select1st {
           const Key& operator()(const value_type& p) const noexcept { return p.first; }
       };
       using TreeType = MultiRbTree<Key, value_type, Select1st, Compare>;
       TreeType _M_tree;

   public:
       using iterator = typename TreeType::iterator;

       MiniMultimap() = default;

       [[nodiscard]] size_t size() const noexcept { return _M_tree.size(); }
       [[nodiscard]] bool empty() const noexcept { return _M_tree.empty(); }

       iterator begin() noexcept { return _M_tree.begin(); }
       iterator end() noexcept { return _M_tree.end(); }

       template <typename... Args>
       iterator emplace(Args&&... args) {
           return _M_tree.emplace_equal(std::forward<Args>(args)...);
       }

       std::pair<iterator, iterator> equal_range(const Key& k) {
           return _M_tree.equal_range(k);
       }

       iterator erase(iterator pos) { return _M_tree.erase(pos); }
       size_t erase(const Key& k) { return _M_tree.erase(k); }
   };

   } // namespace core_stl

   // =========================================================================
   // 3. 端到端测试验证套件
   // =========================================================================
   namespace test {

   inline void runMultiAssociativeTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " MiniMultimap 与 MiniMultiset 等价键与 FIFO 稳定性验证
";
       std::cout << "=======================================================

";

       // 1. 测试 MiniMultimap 等价键插入、FIFO 顺序保持与 equal_range 提取
       {
           core_stl::MiniMultimap<std::string, int> postings;
           // 插入顺序: cache#1 (3), api (1), cache#2 (8), cache#3 (13)
           postings.emplace("cache", 3);
           postings.emplace("api", 1);
           postings.emplace("cache", 8);
           postings.emplace("cache", 13);

           assert(postings.size() == 4);

           std::cout << "[测试 1: MiniMultimap 全量中序遍历]:
";
           for (const auto& [term, pos] : postings) {
               std::cout << "  Word: " << term << " -> DocPos: " << pos << "
";
           }

           // equal_range("cache") 验证
           auto [first, last] = postings.equal_range("cache");
           std::vector<int> extractedPositions;
           for (auto it = first; it != last; ++it) {
               extractedPositions.push_back(it->second);
           }

           // 验证断言: 必须严格满足 FIFO 插入时序 [3, 8, 13]
           assert(extractedPositions.size() == 3);
           assert(extractedPositions[0] == 3);
           assert(extractedPositions[1] == 8);
           assert(extractedPositions[2] == 13);
           std::cout << "  -> equal_range(\"cache\") 提取成功且严格满足 C++11 FIFO 时序。

";
       }

       // 2. 测试单节点删除与全等价键范围删除
       {
           core_stl::MiniMultiset<int> latencies;
           latencies.insert(50);
           latencies.insert(20);
           latencies.insert(20);
           latencies.insert(20);
           latencies.insert(80);
           assert(latencies.size() == 5);

           std::cout << "[测试 2: MiniMultiset 删除测试]: 初始序列: ";
           for (int v : latencies) std::cout << v << " ";
           std::cout << " (size = " << latencies.size() << ")
";

           // 删除全部 key == 20 的节点
           size_t erasedCount = latencies.erase(20);
           assert(erasedCount == 3);
           assert(latencies.size() == 2);

           std::cout << "  -> erase(20) 成功删除 " << erasedCount << " 个等价节点，剩余: ";
           for (int v : latencies) std::cout << v << " ";
           std::cout << "

";
       }

       std::cout << "  -> MiniMultimap 与 MiniMultiset 多重容器验证完全通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰展示了多重有序关联容器的核心运行特性：

1. **等价键拓扑聚集与 FIFO 保真**：在 ``postings`` 中依次存入 ``cache:3``、``cache:8`` 与 ``cache:13`` 时，``insert_equal`` 状态机强制向右子树收敛，使 ``equal_range("cache")`` 迭代时严格按 $[3, 8, 13]$ 升序时序返回。
2. **多节点独立生命周期**：每个等价键对象均分配了独立的红黑树节点，消除了 ``vector<Value>`` 动态扩容搬迁可能导致的迭代器失效。
3. **范围删除完整收敛**：调用 ``latencies.erase(20)`` 时，算法在对数时间内圈定全部 3 个等价节点并依次解绑，剩余节点（50 与 80）的拓扑关系保持完全良构。

小结与下章导读
--------------

本章系统解构了现代 C++ 多重有序关联容器 ``std::multimap`` 与 ``std::multiset`` 的底层微架构与实现规范：

1. **等价键中序连续性**：阐释了基于比较器等价性（$
eg(a < b) \land 
eg(b < a)$）的键在二叉搜索树中构成连续半开区间的数学原理。
2. **C++11 FIFO 稳定性**：推导了 ``insert_equal`` 在等价时强制向右子树分发的微架构设计，保证了相同键实例的插入时序保持。
3. **范围检索与复杂度**：剖析了 ``equal_range`` 的对数检索优势与 ``count()`` 遍历求距离的 $\mathcal{O}(\log N + S)$ 性能陷阱。
4. **架构选型权衡**：建立了 ``multimap<Key, Value>`` 与 ``map<Key, vector<Value>>`` 在内存开销、变易吞吐率与迭代器稳定性之间的决策矩阵。

在完成了基于红黑树的有序关联容器（``set``、``map``、``multiset``、``multimap``）全景剖析后，下一章我们将正式跨入基于哈希散列的无序关联容器世界。在第 4 模块第 4 节 **哈希表微架构与冲突处理：拉链法 (Chaining) 节点拓扑、负载因子 (Load Factor) 与二次幂/质数桶设计（``04_associative_and_hash_containers/04_hash_table_chaining_and_rehash_dynamics.rst``）** 中，我们将深入剖析哈希函数分布、拉链法（Separate Chaining）单向链表桶数组、负载因子动态重散列（Rehash）、质数桶（libstdc++）与二次幂掩码桶（MSVC/Abseil）在取模微架构上的效率权衡。
