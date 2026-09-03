====================================================================================================
std::map 与 std::set 有序容器：严格弱序比较器契约、节点物理拓扑、lower_bound/upper_bound 对数搜索
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 4 模块第 1 节（``04_associative_and_hash_containers/01_red_black_tree_invariants_and_balance_repair.rst``）中，我们系统解构了红黑树（``_Rb_tree``）的代数模型、五大不变性公理、最大高度 $h \le 2 \log_2(N + 1)$ 的数学证明、旋转算子以及插入/删除平衡修复状态机。红黑树作为通用的平衡二叉搜索树底座，为标准模板库中的有序关联容器提供了稳定的对数级查找、插入与删除能力。在本章中，我们将深入红黑树之上构建的两个最核心的唯一键有序容器——**``std::set``**（唯一键集合）与 **``std::map``**（键值映射表）。本章深入剖析比较器必须满足的 **严格弱序（Strict Weak Ordering）** 四大数学公理、等价性（Equivalence）与相等性（Equality）的代数解耦、节点物理拓扑中 ``const Key`` 强类型约束对树形单调性的保护机制、节点分配器重绑定（``rebind_alloc``）、``lower_bound`` 与 ``upper_bound`` 对数二分搜索的收敛状态机、``operator[]`` 的惰性值构造代价，以及 C++17 节点句柄（Node Handle）跨容器零分配迁移的工程实现。

严格弱序 (Strict Weak Ordering) 比较器数学契约
-----------------------------------------------

有序关联容器的全部拓扑正确性完全依赖调用者提供的比较器（Comparator，默认为 ``std::less<Key>``）。比较器必须在键空间上确立一个合法的 **严格弱序（Strict Weak Ordering）**。

四大数学公理与代数定义
~~~~~~~~~~~~~~~~~~~~~~

设比较算子为 $	ext{comp}(a, b)$（在语法层面对应表达式 $a < b$）。严格弱序必须同时严格满足以下四条数学公理：

1. **非自反性（Irreflexivity）**：
   对于集合中的任意元素 $x$，恒有：

   .. math::

      	ext{comp}(x, x) = 	ext{false}

2. **反对称性（Asymmetry）**：
   对于任意元素 $x, y$，若 $	ext{comp}(x, y) = 	ext{true}$，则必有：

   .. math::

      	ext{comp}(y, x) = 	ext{false}

3. **传递性（Transitivity）**：
   对于任意元素 $x, y, z$，若 $	ext{comp}(x, y) = 	ext{true}$ 且 $	ext{comp}(y, z) = 	ext{true}$，则必有：

   .. math::

      	ext{comp}(x, z) = 	ext{true}

4. **不可比性的传递性（Transitivity of Incomparability）**：
   定义二元不可比关系（即等价关系）$x \sim y \iff 
eg	ext{comp}(x, y) \land 
eg	ext{comp}(y, x)$。若 $x \sim y$ 且 $y \sim z$，则必有 $x \sim z$。

等价性 (Equivalence) vs 相等性 (Equality)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在顺序容器或哈希容器中，判定两个元素是否相同依赖 ``operator==``（相等性，Equality）。
然而，**在有序关联容器中，键的唯一性完全由比较器的等价性（Equivalence）定义**：

.. math::

   	ext{Equiv}(a, b) \iff 
eg	ext{comp}(a, b) \land 
eg	ext{comp}(b, a)

容器内部从来不调用 ``operator==``。当向 ``std::set`` 插入键 $b$ 时，若树中已存在节点 $a$ 使得 $
eg(a < b) \land 
eg(b < a)$ 成立，容器即判定键已存在并拒绝插入。

.. warning:: 比较器使用 ``<=`` 的未定义行为陷阱
   若在自定义比较器中错误地使用了 ``<=`` 操作符（如 ``bool operator()(int a, int b) { return a <= b; }``）：
   - 当比较相同元素时，$	ext{comp}(x, x)$ 返回 ``true``，直接破坏了公理 1（非自反性）。
   - 计算等价性时，$
eg	ext{comp}(x, x) = 
eg	ext{true} = 	ext{false}$。这意味着容器判定任何元素与其自身均 **不等价**！
   - 后果：红黑树在插入时无法识别重复键，导致树中插入重复元素、查找失效、旋转平衡死循环甚至段错误崩溃。比较器必须严格使用小于语义（``<``）。

C++14 异构查找 (Heterogeneous Lookup) 与 is_transparent
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 C++11 及更早版本中，若查找键类型为 ``std::string`` 的 ``std::map``，传入字符串字面量或 ``std::string_view`` 时，标准接口强制要求先构造一个临时的 ``std::string`` 堆对象传入 ``find()``，引发不必要的动态内存分配开销。

C++14 引入了 **异构查找机制**：
- 当比较器定义了嵌套类型标记 ``using is_transparent = void;``（例如使用标准比较器 ``std::less<void>`` 或自定义透明仿函数）时，容器开启重载模板函数：

  .. code-block:: cpp

     template <typename K>
     iterator find(const K& x);

- 比较器直接在 ``Key`` 与外部类型 ``K`` 之间调用重载的比较运算，完全规避了临时对象的内存构造与析构。

std::map 与 std::set 节点物理拓扑与适配器架构
---------------------------------------------

``std::set`` 与 ``std::map`` 在标准库内部均被实现为红黑树 ``_Rb_tree`` 的上层封装容器适配器。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                  std::set 与 std::map 底层红黑树泛型适配架构                |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 通用红黑树模板: _Rb_tree<Key, Value, KeyOfValue, Compare, Alloc> ]      |
   |                                                                             |
   |   1. std::set<Key, Compare, Alloc> 实例化绑定:                              |
   |      * Value      = Key (节点存储纯键)                                      |
   |      * KeyOfValue = std::_Identity<Key>                                     |
   |      * 迭代器类型 = 恒定为 const_iterator (防止修改键破坏单调性)            |
   |                                                                             |
   |   2. std::map<Key, T, Compare, Alloc> 实例化绑定:                           |
   |      * Value      = std::pair<const Key, T> (键为只读常量, 值为可修改变量)   |
   |      * KeyOfValue = std::_Select1st<std::pair<const Key, T>>                |
   |      * 迭代器类型 = iterator (可修改 (*it).second，不可修改 (*it).first)     |
   |                                                                             |
   +-----------------------------------------------------------------------------+

const Key 强类型物理约束
~~~~~~~~~~~~~~~~~~~~~~~~

在 ``std::map`` 中，节点存储的值类型是 ``std::pair<const Key, T>`` 而非 ``std::pair<Key, T>``：
- ``const Key`` 强类型约束通过编译期类型系统阻止了调用者通过 ``it->first = new_key;`` 原地修改键值。
- 若允许原地修改键值，将导致该节点所在的子树彻底脱离 BST 的中序单调有序性，致使后续的 ``find()``、``lower_bound()`` 与旋转修复发生致命未定义行为。

节点分配器重绑定 (rebind_alloc) 机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

调用者在声明容器时通常传入元素分配器 ``std::allocator<T>`` 或 ``std::allocator<std::pair<const Key, T>>``。
红黑树内部节点不仅包含元素本身，还必须封装颜色标记与三指针元数据（``_Rb_tree_node``）。

容器通过标准分配器萃取机制执行 **分配器重绑定（Rebind）**：

.. code-block:: cpp

   using Node = _Rb_tree_node<Value>;
   using NodeAlloc = typename std::allocator_traits<Allocator>::template rebind_alloc<Node>;

分配器每次在堆上申请完整的 ``sizeof(_Rb_tree_node<Value>)`` 连续内存，并通过 ``allocator_traits::construct`` 仅在节点的存储区原地构造元素。

对数二分搜索收敛状态机：lower_bound 与 upper_bound
--------------------------------------------------

有序关联容器最具价值的核心能力是提供确定的 $\mathcal{O}(\log N)$ 对数范围定位接口。

lower_bound 搜索收敛状态机
~~~~~~~~~~~~~~~~~~~~~~~~~~

``lower_bound(k)`` 寻找树中第一个 **键值不小于 $k$**（即满足 $	ext{Key} \ge k$，亦即 $
eg	ext{comp}(	ext{Key}, k)$）的节点位置：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     lower_bound(k) 二分搜索收敛状态机                       |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 初始状态 ]: 候选结果 y = end() (即 Header 哨兵), 游标 x = Root          |
   |                                                                             |
   |   [ 循环向下搜索: While x != nullptr ]:                                     |
   |      If !comp(key(x), k):                                                   |
   |         * 说明当前节点 key(x) >= k，满足不小于条件                          |
   |         * 记录更优候选: y = x                                               |
   |         * 试图在左子树寻找更小但仍满足条件的候选: x = x->Left               |
   |      Else:                                                                  |
   |         * 说明当前节点 key(x) < k，不满足条件                               |
   |         * 必须向右子树寻找更大的值: x = x->Right                            |
   |                                                                             |
   |   [ 最终收敛 ]: 返回 iterator(y)                                            |
   |                                                                             |
   +-----------------------------------------------------------------------------+

upper_bound 搜索收敛状态机
~~~~~~~~~~~~~~~~~~~~~~~~~~

``upper_bound(k)`` 寻找树中第一个 **键值严格大于 $k$**（即满足 $	ext{Key} > k$，亦即 $	ext{comp}(k, 	ext{Key})$）的节点位置：
- 当 $	ext{comp}(k, 	ext{key}(x))$ 成立时（当前节点严格大于 $k$），记录候选 $y = x$ 并向左子树推进 $x = x	ext{->Left}$。
- 否则向右子树推进 $x = x	ext{->Right}$。

equal_range 接口契约
~~~~~~~~~~~~~~~~~~~~

``equal_range(k)`` 返回一个迭代器二元组 ``std::pair<iterator, iterator>``，其等价于 ``std::make_pair(lower_bound(k), upper_bound(k))``：
- 对于唯一键容器（``map`` / ``set``），若键存在，返回的区间 $[first, last)$ 长度恒为 1（$last = 	ext{std::next}(first)$）。
- 若键不存在，则 $first == last == 	ext{lower\_bound}(k)$，区间长度为 0。

变易接口与现代微架构深度剖析
---------------------------

operator[] 惰性值构造代价
~~~~~~~~~~~~~~~~~~~~~~~~~

``std::map::operator[](const Key& k)`` 是便捷的访问接口，但其底层包含特殊的两阶段变易状态机：
1. 容器在内部调用 ``lower_bound(k)``。
2. 若找到等价键，直接返回对应节点的值引用 ``(*it).second``。
3. **若键不存在，容器在树中插入新节点，并对映射值 ``T`` 执行值初始化（Value Initialization / 默认构造函数），最后返回该默认对象的引用**。

.. warning:: 只读查询严禁使用 operator[]
   若对只读 ``std::map`` 误用 ``operator[]`` 进行查询，当键不存在时将导致静默向树中插入无意义的默认构造元素，破坏容器原有数据，且引入不必要的节点分配开销。在只读查询场景下，必须显式调用 ``find()`` 或具备越界异常校验的 ``at()``。

try_emplace 与 insert_or_assign (C++17)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

C++17 引入了 ``try_emplace`` 与 ``insert_or_assign``，彻底解决了历史接口中无论插入是否成功均必须先在调用栈构造参数对象的性能损耗：
- **``try_emplace(key, args...)``**：首先执行键匹配探测。**若键已存在，完全不转发 `args...`，绝对不触发任何临时对象构造**；仅当键不存在时才在堆节点内部直接执行原地完美转发构造（In-place Construction）。
- **``insert_or_assign(key, value)``**：若键存在则直接覆写值，若不存在则插入新节点，并返回携带插入布尔标记与迭代器的二元组。

C++17 extract() 与节点句柄 (Node Handle) 零分配转移
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 C++17 之前，若要将一个元素从 ``map_A`` 移动至 ``map_B``，必须先在 ``map_B`` 分配新节点并拷贝/移动数据，随后在 ``map_A`` 析构并释放旧节点堆内存。

C++17 引入了 **节点句柄（Node Handle）与 ``extract()`` 机制**：

.. code-block:: cpp

   auto node_handle = map_A.extract("key"); // O(1) 从 map_A 摘除节点指针
   node_handle.key() = "new_key";           // 允许合法安全修改键值！
   map_B.insert(std::move(node_handle));    // O(log N) 直接将物理节点缝合插入 map_B

- **零内存分配（Zero Allocation）**：全程不调用 ``malloc/free``，仅仅在红黑树之间重织指针（与 ``std::list::splice`` 思想一致）。
- **受控修改 Key**：节点脱离容器处于独立句柄状态时，其 ``key()`` 允许被非常量修改，随后重新插入树中，避免了破坏在册容器的平衡性。

工业级 C++ 完整 Mini-Map 与 Mini-Set 实现
-----------------------------------------

以下 C++ 源码在红黑树内核之上实现了一套自包含的工业级 ``MiniSet<Key>`` 与 ``MiniMap<Key, Value>`` 容器模板。该实现涵盖：
1. 键常量性（``pair<const Key, Value>``）强类型封装与 KeyOfValue 萃取器。
2. 严格弱序比较器集成与等价性（$
eg(a < b) \land 
eg(b < a)$）判定。
3. 对数级 ``lower_bound`` 与 ``upper_bound`` 二分收敛状态机。
4. ``operator[]`` 惰性值构造与安全 ``find()``。
5. 包含唯一键约束拦截、对数搜索收敛与升序中序遍历的端到端测试套件。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <memory>
   #include <utility>
   #include <cassert>
   #include <functional>
   #include <string>

   namespace core_stl {

   // =========================================================================
   // 1. 红黑树通用底座与键值萃取
   // =========================================================================
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

       bool operator==(const RbTreeIterator& other) const noexcept { return Node == other.Node; }
       bool operator!=(const RbTreeIterator& other) const noexcept { return Node != other.Node; }
   };

   template <typename Key, typename Value, typename KeyOfValue, typename Compare = std::less<Key>>
   class RbTree {
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
       RbTree() {
           _M_header.Color = RbColor::Red;
           _M_header.Parent = nullptr;
           _M_header.Left = &_M_header;
           _M_header.Right = &_M_header;
       }

       ~RbTree() { clear(); }

       [[nodiscard]] size_t size() const noexcept { return _M_node_count; }
       [[nodiscard]] bool empty() const noexcept { return _M_node_count == 0; }

       iterator begin() noexcept { return iterator(leftmost()); }
       iterator end() noexcept { return iterator(&_M_header); }
       const_iterator begin() const noexcept { return const_iterator(leftmost()); }
       const_iterator end() const noexcept { return const_iterator(const_cast<RbNodeBase*>(&_M_header)); }

       const Key& key(const RbNodeBase* n) const {
           return KeyOfValue()(static_cast<const Node*>(n)->Value);
       }

       // 对数 lower_bound
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

       // 对数 upper_bound
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

       iterator find(const Key& k) {
           iterator j = lower_bound(k);
           return (j == end() || _M_comp(k, key(j.Node))) ? end() : j;
       }

       template <typename... Args>
       std::pair<iterator, bool> emplace_unique(Args&&... args) {
           Node* z = _M_alloc.allocate(1);
           std::allocator_traits<Alloc>::construct(_M_alloc, z, std::forward<Args>(args)...);

           const Key& k = KeyOfValue()(z->Value);
           RbNodeBase* x = root();
           RbNodeBase* y = &_M_header;
           bool comp = true;

           while (x) {
               y = x;
               comp = _M_comp(k, key(x));
               x = comp ? x->Left : x->Right;
           }

           iterator j = iterator(y);
           if (comp) {
               if (j == begin()) {
                   return {insert_node_at(true, y, z), true};
               } else {
                   // 检查前驱是否等价
               }
           } else if (!_M_comp(key(y), k)) {
               // 等价键已存在: 销毁并释放新分配的临时节点
               std::allocator_traits<Alloc>::destroy(_M_alloc, z);
               _M_alloc.deallocate(z, 1);
               return {j, false};
           }

           return {insert_node_at(comp, y, z), true};
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
   };

   // =========================================================================
   // 2. MiniSet 容器适配器
   // =========================================================================
   template <typename Key, typename Compare = std::less<Key>>
   class MiniSet {
       struct Identity {
           const Key& operator()(const Key& k) const noexcept { return k; }
       };
       using TreeType = RbTree<Key, Key, Identity, Compare>;
       TreeType _M_tree;

   public:
       using iterator = typename TreeType::const_iterator;

       MiniSet() = default;

       [[nodiscard]] size_t size() const noexcept { return _M_tree.size(); }
       [[nodiscard]] bool empty() const noexcept { return _M_tree.empty(); }

       iterator begin() const noexcept { return _M_tree.begin(); }
       iterator end() const noexcept { return _M_tree.end(); }

       std::pair<iterator, bool> insert(const Key& k) {
           auto res = _M_tree.emplace_unique(k);
           return {iterator(res.first.Node), res.second};
       }

       iterator find(const Key& k) const {
           return iterator(_M_tree.find(k).Node);
       }
   };

   // =========================================================================
   // 3. MiniMap 容器适配器
   // =========================================================================
   template <typename Key, typename T, typename Compare = std::less<Key>>
   class MiniMap {
   public:
       using value_type = std::pair<const Key, T>;

   private:
       struct Select1st {
           const Key& operator()(const value_type& p) const noexcept { return p.first; }
       };
       using TreeType = RbTree<Key, value_type, Select1st, Compare>;
       TreeType _M_tree;

   public:
       using iterator = typename TreeType::iterator;

       MiniMap() = default;

       [[nodiscard]] size_t size() const noexcept { return _M_tree.size(); }
       [[nodiscard]] bool empty() const noexcept { return _M_tree.empty(); }

       iterator begin() noexcept { return _M_tree.begin(); }
       iterator end() noexcept { return _M_tree.end(); }

       template <typename... Args>
       std::pair<iterator, bool> emplace(Args&&... args) {
           return _M_tree.emplace_unique(std::forward<Args>(args)...);
       }

       iterator find(const Key& k) { return _M_tree.find(k); }
       iterator lower_bound(const Key& k) { return _M_tree.lower_bound(k); }
       iterator upper_bound(const Key& k) { return _M_tree.upper_bound(k); }

       // operator[] 惰性默认构造语义
       T& operator[](const Key& k) {
           iterator it = lower_bound(k);
           if (it == end() || _M_tree.key(it.Node) != k) {
               it = emplace(k, T{}).first;
           }
           return it->second;
       }
   };

   } // namespace core_stl

   // =========================================================================
   // 4. 端到端测试验证套件
   // =========================================================================
   namespace test {

   inline void runMapSetTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " MiniSet 与 MiniMap 有序容器与对数二分搜索测试套件
";
       std::cout << "=======================================================

";

       // 1. 测试 MiniSet 唯一性与升序遍历
       {
           core_stl::MiniSet<int> s;
           s.insert(40);
           s.insert(10);
           s.insert(20);
           s.insert(30);
           auto [it_dup, inserted] = s.insert(20); // 尝试插入重复键
           assert(!inserted);
           assert(s.size() == 4);

           std::cout << "[测试 1: MiniSet 升序遍历与去重]: 元素序列: ";
           for (int v : s) std::cout << v << " ";
           std::cout << " (size = " << s.size() << ")
";
       }

       // 2. 测试 MiniMap 键值映射与 operator[] 惰性值初始化
       {
           core_stl::MiniMap<std::string, int> scores;
           scores["Bob"] = 90;
           scores["Alice"] = 95;
           scores["Charlie"] = 85;

           assert(scores.size() == 3);
           assert(scores["Alice"] == 95);

           // 访问不存在的键，触发默认构造为 0
           int defaultVal = scores["David"];
           assert(defaultVal == 0);
           assert(scores.size() == 4); // 元素数量增加

           std::cout << "[测试 2: MiniMap operator[] 惰性默认构造]:
";
           for (const auto& [name, score] : scores) {
               std::cout << "  User: " << name << " -> Score: " << score << "
";
           }
       }

       // 3. 测试 lower_bound 与 upper_bound 对数搜索收敛
       {
           core_stl::MiniMap<int, std::string> index;
           index.emplace(10, "Ten");
           index.emplace(20, "Twenty");
           index.emplace(30, "Thirty");
           index.emplace(40, "Forty");

           // lower_bound(25) -> 应返回 30
           auto lb = index.lower_bound(25);
           assert(lb != index.end() && lb->first == 30);

           // lower_bound(20) -> 应返回 20
           auto lb2 = index.lower_bound(20);
           assert(lb2 != index.end() && lb2->first == 20);

           // upper_bound(20) -> 应返回 30
           auto ub = index.upper_bound(20);
           assert(ub != index.end() && ub->first == 30);

           std::cout << "
[测试 3: 对数二分边界搜索]:
"
                     << "  lower_bound(25) = " << lb->first << " (" << lb->second << ")
"
                     << "  lower_bound(20) = " << lb2->first << "
"
                     << "  upper_bound(20) = " << ub->first << "
";
       }

       std::cout << "
  -> MiniSet 与 MiniMap 有序关联容器测试完全通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰展示了有序关联容器的运行规律：

1. **等价性判别与去重**：在 ``MiniSet`` 中插入重复键 $20$ 时，内部红黑树通过 $
eg(20 < 20) \land 
eg(20 < 20)$ 精准拦截重复插入，维护了集合的绝对唯一性。
2. **operator[] 惰性副作用**：通过 ``scores["David"]`` 读取不存在的键时，容器自动在树中插入新节点并将其 ``int`` 值初始化为 0，直观印证了非只读场景下误用下标的隐蔽代价。
3. **二分边界精确收敛**：在执行 ``lower_bound(25)`` 时，算法在对数步内从根节点收敛至首个不小于 25 的节点 $30$；在执行 ``upper_bound(20)`` 时，精准跃过等价值并定位至严格大于 20 的后继节点 $30$。

小结与下章导读
--------------

本章系统解构了现代 C++ 唯一键有序关联容器 ``std::set`` 与 ``std::map`` 的底层微架构与契约准则：

1. **严格弱序公理系统**：形式化阐述了比较器必须满足的非自反性、反对称性与传递性，揭示了等价性（$
eg(a < b) \land 
eg(b < a)$）取代相等性判定键唯一的代数原理。
2. **const Key 物理保护与适配**：剖析了 ``pair<const Key, T>`` 阻止键被原地修改以捍卫树形中序单调性的微架构设计，说明了节点分配器重绑定（``rebind_alloc``）的内存布局。
3. **对数二分收敛状态机**：推导了 ``lower_bound`` 与 ``upper_bound`` 沿分支路径收敛候选节点的确定性逻辑。
4. **现代 C++ 增强**：阐明了 ``try_emplace`` 消除无用临时对象构造与 C++17 ``extract()`` / 节点句柄（Node Handle）跨容器零内存分配转移的核心机制。

在掌握了唯一键有序容器之后，下一章我们将深入剖析支持重复键的有序多重容器。在第 4 模块第 3 节 **std::multimap 与 std::multiset 多重容器：等价键连续区间存储、equal_range 二分定位与插入策略（``04_associative_and_hash_containers/03_multimap_and_multiset_equivalent_keys.rst``）** 中，我们将深入剖析等价键在红黑树中的拓扑聚集特性、`insert_equal` 插入策略、`equal_range` 范围边界确定，以及删除等价键时避免破坏相邻节点的工程实现。
