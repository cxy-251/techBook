====================================================================================================================
工业级 Mini-RBTree 与 Mini-HashTable 实战：旋转平衡修复、拉链法桶数组与动态 rehash 迁移
====================================================================================================================

.. note:: 前置背景与上下文承接
   在上一节（``02_mini_vector_and_mini_deque.rst``）中，我们完成了连续内存动态数组（``MiniVector``）与双端分段中控队列（``MiniDeque``）的工程落地，掌握了序列容器在物理连续内存与分段扩容维度的底层实现。在处理基于键（Key）的高频检索、去重与关联映射场景中，序列结构的线性扫描时间开销随数据规模膨胀呈 $\mathcal{O}(N)$ 增长。STL 标准库为此提供了基于有序树结构的关联容器（``std::map`` / ``std::set``）与基于哈希散列的无序容器（``std::unordered_map`` / ``std::unordered_set``）。本节作为工业级关联容器实战篇章，直击非线性数据结构的核心物理实现，分别构建自包含、无外部依赖且具备工业级严谨性的 ``MiniRBTree`` 与 ``MiniHashTable``。

Mini-RBTree 底层平衡核心微架构
------------------------------

红黑树（Red-Black Tree）是一种在每个节点存储着色位（Red 或 Black）的自平衡二叉搜索树。它通过对任意一条从根到叶子路径上的节点着色方式施加约束，确保最长路径不超过最短路径的两倍，达成渐进平衡。

五大不变性公理与黑高上界约束
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

工业级红黑树的全部插入、删除与查找逻辑均建立在以下五条绝对不变性公理之上：

1. **节点颜色公理**：每个节点必须明确标识为红色（Red）或黑色（Black）。
2. **根节点公理**：树的根节点（Root）必须为黑色。
3. **叶子节点公理**：全部外部叶子（NIL 哨兵节点）强制标识为黑色。
4. **红节点独立公理**：红色节点的两个直接子节点必须均为黑色。由此公理推导，整棵树内部绝对禁止出现连续的红色节点。
5. **黑高一致公理（Black-Height Invariant）**：对于任意节点 $x$，从该节点出发到达其子树中任意一个 NIL 叶子节点的全部简单路径上，所包含的黑色节点数目必须完全相同，记作黑高 $bh(x)$。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        红黑树黑高平衡约束与路径长度界定                     |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |                             [ 20 (B) ]  bh = 2                              |
   |                             /        \                                      |
   |                       [ 10 (R) ]    [ 30 (B) ]  bh = 1                      |
   |                       /        \            \                               |
   |                   [ 5 (B) ]  [ 15 (B) ]   [ 40 (R) ]                        |
   |                   /       \               /        \                        |
   |                [NIL]     [NIL]         [NIL]      [NIL]                     |
   |                                                                             |
   |   最短路径（全黑节点）:   Len = bh = 2                                      |
   |   最长路径（黑红交替）:   Len <= 2 * bh = 4                                 |
   |   最大树高数学上界:       h <= 2 * log2(N + 1)                              |
   |                                                                             |
   +-----------------------------------------------------------------------------+

根据数学归纳法证明，一棵包含 $N$ 个内部节点的红黑树，其高度 $h$ 满足严格上界：

.. math::

   h \le 2 \log_2(N + 1)

这一性质保障了搜索、插入与删除操作的最坏时间复杂度始终稳定在 $\mathcal{O}(\log N)$。

Header 哨兵拓扑物理设计
~~~~~~~~~~~~~~~~~~~~~~~

在 GCC libstdc++ 的 ``_Rb_tree`` 实现中，树结构引入了一个特殊的空头节点（Header Sentinel Node），以常数时间复杂度支持双向迭代器的首尾寻址与边界闭环：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                       Header 哨兵节点物理拓扑结构                           |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |                   header_ (color = Red, 独立辅助节点)                       |
   |                   +------------------------------------+                    |
   |                   | parent: 指向真正的根节点 (Root)    |                    |
   |                   | left:   指向全树最小节点 (Leftmost)|                    |
   |                   | right:  指向全树最大节点(Rightmost)|                    |
   |                   +------------------------------------+                    |
   |                             |             |           |                     |
   |               +-------------+             |           +--------------+      |
   |               | (parent)                  | (left)                   | (rt) |
   |               v                           v                          v      |
   |           [ Root (B) ] -------------> [ Min (B) ]                [ Max (B) ]|
   |                                                                             |
   |   - begin()  返回 iterator(header_->left)  [全树最小节点，O(1)]             |
   |   - end()    返回 iterator(header_)        [以 header_ 作为尾后哨兵]        |
   |   - rbegin() 返回 iterator(header_->right) [全树最大节点，O(1)]             |
   |                                                                             |
   +-----------------------------------------------------------------------------+

Header 节点的工程价值体现在三个维度：
1. **常数阶边界定位**：通过 ``header_->left`` 与 ``header_->right``，容器能够在 $\mathcal{O}(1)$ 时间内交付 ``begin()`` 与 ``rbegin()``，无需每次自根节点向下遍历查找极值。
2. **统一尾后哨兵**：``end()`` 迭代器直接封装指向 ``header_`` 的指针。当迭代器从中序极大值自增时，逻辑自动指向 ``header_``，完美契合 STL 尾后半开区间契约。
3. **根节点父指针安全化**：根节点的父指针指向 ``header_``，使得树内任意节点的父指针遍历均具备合法目标，消除了空指针解引用保护分支。

旋转算子与局部拓扑变换
~~~~~~~~~~~~~~~~~~~~~~

当插入新节点破坏了红黑树的不变性时，必须依靠树旋转（Tree Rotation）调整局部拓扑结构。旋转操作在维持二叉搜索树中序有序性的前提下，精确改变子树的高度分布。

左旋算子（Left Rotate）
^^^^^^^^^^^^^^^^^^^^^^^

设节点 $X$ 的右孩子为 $Y$，$Y$ 的左子树为 $\beta$。以 $X-Y$ 边执行左旋的操作步骤如下：
1. 将 $Y$ 的左子树 $\beta$ 移接为 $X$ 的右子树；
2. 若 $\beta$ 存在，更新 $\beta$ 的父指针指向 $X$；
3. 将 $X$ 的父节点移接给 $Y$；
4. 更新原 $X$ 的父节点的对应孩子指针（左孩子或右孩子）指向 $Y$；若 $X$ 原为根节点，则更新根节点为 $Y$；
5. 将 $X$ 挂载为 $Y$ 的左孩子，同时更新 $X$ 的父指针指向 $Y$。

.. code-block:: text

        X                         Y
       / \       左旋 (X)        / \
      alpha Y    =======>       X   gamma
           / \                 / \
        beta gamma          alpha beta

右旋算子（Right Rotate）
^^^^^^^^^^^^^^^^^^^^^^^^

右旋算子是左旋的完全镜像操作。设节点 $Y$ 的左孩子为 $X$，$X$ 的右子树为 $\beta$。以 $Y-X$ 边执行右旋：
1. 将 $X$ 的右子树 $\beta$ 移接为 $Y$ 的左子树；
2. 若 $\beta$ 存在，更新 $\beta$ 的父指针指向 $Y$；
3. 将 $Y$ 的父节点移接给 $X$；
4. 更新原 $Y$ 的父节点的对应孩子指针指向 $X$；若 $Y$ 原为根节点，则更新根节点为 $X$；
5. 将 $Y$ 挂载为 $X$ 的右孩子，同时更新 $Y$ 的父指针指向 $X$。

.. code-block:: text

          Y                       X
         / \     右旋 (Y)        / \
        X  gamma =======>     alpha  Y
       / \                          / \
    alpha beta                   beta gamma

插入重新着色与平衡修复状态机
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

新节点插入时统一着为**红色**。若插入为根节点，直接涂黑；若插入节点的父节点为黑色，树的五大不变性完全保持，无需修复。当且仅当父节点亦为红色时，破坏了“红节点独立公理”，触发再平衡状态机。

设当前破坏节点为 $Z$，父节点为 $P$，祖父节点为 $G$，叔节点为 $U$（$G$ 的另一侧孩子）。以父节点 $P$ 为祖父 $G$ 的左孩子为例（对称分支同理），状态机分为以下三类场景：

- **Case 1：叔节点 $U$ 为红色**
  - **处理策略**：将父节点 $P$ 与叔节点 $U$ 均涂为黑色，祖父节点 $G$ 涂为红色。随后将当前节点指针 $Z$ 上移至祖父 $G$（$Z \leftarrow G$），进入下一轮迭代检查。
  - **物理意义**：将多余的一层红色上推至祖父层级，子树黑高保持不变。

- **Case 2：叔节点 $U$ 为黑色，且 $Z$ 是父节点 $P$ 的右孩子（折线型拓扑）**
  - **处理策略**：以父节点 $P$ 为轴执行左旋，将指针 $Z$ 更新为原父节点 $P$（$Z \leftarrow P$），状态无缝转换为 Case 3。
  - **物理意义**：通过局部旋转将内侧折线拓扑规整为同向直线拓扑。

- **Case 3：叔节点 $U$ 为黑色，且 $Z$ 是父节点 $P$ 的左孩子（直线型拓扑）**
  - **处理策略**：将父节点 $P$ 涂为黑色，祖父节点 $G$ 涂为红色，随后以祖父节点 $G$ 为轴执行右旋。
  - **物理意义**：旋转使黑色父节点接替祖父成为新子树根，原祖父成为右侧红色兄弟，全路径黑高平衡修复完成，循环终止。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                       Mini-RBTree 插入修复状态机流转                        |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |    [ 插入新节点 Z (Red) ]                                                   |
   |              |                                                              |
   |              v                                                              |
   |    [ 父节点 P 是否为 Red? ] --- (否) ---> [ 插入完成, 不变性自洽 ]          |
   |              |                                                              |
   |             (是)                                                            |
   |              v                                                              |
   |    [ 检查叔节点 U 的颜色 ]                                                  |
   |        |                 |                                                  |
   |     (Red)             (Black)                                               |
   |        |                 |                                                  |
   |        v                 v                                                  |
   |    [ Case 1 ]    [ Z 是否为内侧孩子? ]                                      |
   |    - P 涂黑              |                                                  |
   |    - U 涂黑             (是, Case 2)                                        |
   |    - G 涂红              v                                                  |
   |    - Z = G        [ 对 P 做单旋, 转为直线型 ]                               |
   |    - 继续向上迭代        |                                                  |
   |                          v                                                  |
   |                      [ Case 3 (直线型) ]                                    |
   |                      - P 涂黑, G 涂红                                       |
   |                      - 对 G 做反向旋转                                      |
   |                      - 修复完成, 退出循环                                   |
   |                                                                             |
   +-----------------------------------------------------------------------------+

双向中序迭代器步进拓扑
~~~~~~~~~~~~~~~~~~~~~~

红黑树的元素按键严格弱序排列，其中序遍历序列即为严格单调升序序列。双向迭代器的 ``operator++()`` 实现遵循中序遍历的后继节点检索算法：

1. **若当前节点存在右子树**：后继节点必然是其右子树中的最左节点（自右孩子开始，持续沿左指针向下遍历至尽头）；
2. **若当前节点不存在右子树**：后继节点为当前节点的最低祖先，且该祖先的左子树包含当前节点。沿着父指针向上回溯，直到当前节点不再是其父节点的右孩子；
3. **边界处理**：当从全树最大节点递增时，指针回溯至 ``header_`` 节点，表示到达 ``end()``。

Mini-HashTable 拉链法微架构与动态重散列
---------------------------------------

``MiniHashTable`` 采用分离链接法（Separate Chaining）解决哈希碰撞。为了达成极高的遍历性能与常数阶插入删除，工业级实现对节点拓扑与桶数组结构进行了高度协同优化。

单向贯通链表与桶前驱指针拓扑
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在传统的拉链法实现中，每个桶独立维护一个链表头节点，全表遍历必须以双重循环逐一检查每个桶，导致遍历开销受制于桶数组总尺寸 $B$。

GCC libstdc++ ``_Hashtable`` 采用了突破性的**单向贯通链表**拓扑：
1. **全局单向贯通链表**：全表中存储的所有有效元素节点（``HashNode``）被串联在一条全局单向链表上；
2. **首元素伪哨兵（before_begin）**：容器维护一个空节点 ``before_begin_``，其 ``next`` 指向全局链表中的第一个有效数据节点；
3. **桶数组存储前驱指针（Bucket of Predecessors）**：桶数组 ``buckets_`` 的每个槽位存储的不再是数据节点本身，而是指向**该桶内首个元素在全局链表中的前驱节点指针**（``HashNode*``）。若桶为空，槽位填充 ``nullptr``。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                  Mini-HashTable 全局单向链表与桶前驱指针拓扑                |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   before_begin_ (Node*)                                                     |
   |        |                                                                    |
   |        v                                                                    |
   |     [ Node A (Bkt 1) ] ---> [ Node B (Bkt 1) ] ---> [ Node C (Bkt 3) ] --->|
   |        ^                         ^                       ^                  |
   |        |                         |                       |                  |
   |   buckets_[1] -------------------+                       |                  |
   |   buckets_[2] = nullptr                                  |                  |
   |   buckets_[3] -------------------------------------------+                  |
   |                                                                             |
   |   - begin() 直接返回 before_begin_->next，全表遍历为纯单向链表推进 O(N)     |
   |   - 桶定位与节点插入通过修改前驱节点的 next 指针完成，实现严格 O(1) 插入    |
   |                                                                             |
   +-----------------------------------------------------------------------------+

这种拓扑结构带来了显著的工业性能优势：
- **全局遍历极速化**：``begin()`` 到 ``end()`` 的遍历完全沿着单向链表指针单重循环推进，耗时仅与有效元素数量 $N$ 成正比（$\mathcal{O}(N)$），彻底规避了对空桶的无谓检查；
- **常数时间单向插入**：向目标桶插入新节点时，将其挂接在目标桶首节点之后，直接复用前驱节点的指向，保持 $\mathcal{O}(1)$ 插入开销。

负载因子与质数扩容序列
~~~~~~~~~~~~~~~~~~~~~~

哈希表平均查找长度直接取决于负载因子 $\alpha$：

.. math::

   \alpha = \frac{N}{B}

其中 $N$ 为元素总数，$B$ 为当前桶总数。标准库默认设置最大负载因子 $\alpha_{\max} = 1.0$。当新插入元素导致 $\alpha > \alpha_{\max}$ 时，容器必须触发重散列（Rehash）。

为了消除低阶位散列不均引发的碰撞聚集，``MiniHashTable`` 采用离散质数增长序列：

.. code-block:: cpp

   #include <iostream>
   #include <cstddef>
   #include <new>
   #include <utility>
   #include <functional>
   #include <type_traits>
   #include <cassert>
   #include <algorithm>

   namespace mini_stl {

   enum class RBColor : bool { Red = false, Black = true };

   template <typename T>
   struct RBTreeNode {
       using NodePtr = RBTreeNode<T>*;

       RBColor color{RBColor::Red};
       NodePtr parent{nullptr};
       NodePtr left{nullptr};
       NodePtr right{nullptr};
       T value{};

       RBTreeNode() = default;
       explicit RBTreeNode(const T& v) : color(RBColor::Red), value(v) {}
       explicit RBTreeNode(T&& v) : color(RBColor::Red), value(std::move(v)) {}
   };

   template <typename T, typename Compare = std::less<T>>
   class MiniRBTree {
   public:
       using value_type = T;
       using size_type = std::size_t;
       using Node = RBTreeNode<T>;
       using NodePtr = Node*;

       struct Iterator {
           NodePtr node{nullptr};

           Iterator() noexcept = default;
           explicit Iterator(NodePtr n) noexcept : node(n) {}

           T& operator*() const noexcept { return node->value; }
           T* operator->() const noexcept { return &(node->value); }

           Iterator& operator++() noexcept {
               if (node->right != nullptr) {
                   node = node->right;
                   while (node->left != nullptr) {
                       node = node->left;
                   }
               } else {
                   NodePtr p = node->parent;
                   while (node == p->right) {
                       node = p;
                       p = p->parent;
                   }
                   if (node->right != p) {
                       node = p;
                   }
               }
               return *this;
           }

           Iterator operator++(int) noexcept {
               Iterator tmp = *this;
               ++(*this);
               return tmp;
           }

           Iterator& operator--() noexcept {
               if (node->color == RBColor::Red && node->parent != nullptr && node->parent->parent == node) {
                   node = node->right;
               } else if (node->left != nullptr) {
                   node = node->left;
                   while (node->right != nullptr) {
                       node = node->right;
                   }
               } else {
                   NodePtr p = node->parent;
                   while (node == p->left) {
                       node = p;
                       p = p->parent;
                   }
                   node = p;
               }
               return *this;
           }

           Iterator operator--(int) noexcept {
               Iterator tmp = *this;
               --(*this);
               return tmp;
           }

           bool operator==(const Iterator& other) const noexcept { return node == other.node; }
           bool operator!=(const Iterator& other) const noexcept { return node != other.node; }
       };

       using iterator = Iterator;

   private:
       NodePtr header_{nullptr};
       size_type node_count_{0};
       Compare comp_{};

       NodePtr& root() noexcept { return header_->parent; }
       NodePtr root() const noexcept { return header_->parent; }
       NodePtr& leftmost() noexcept { return header_->left; }
       NodePtr leftmost() const noexcept { return header_->left; }
       NodePtr& rightmost() noexcept { return header_->right; }
       NodePtr rightmost() const noexcept { return header_->right; }

       void init_header() {
           header_ = new Node();
           header_->color = RBColor::Red;
           header_->parent = nullptr;
           header_->left = header_;
           header_->right = header_;
           node_count_ = 0;
       }

       void destroy_subtree(NodePtr x) noexcept {
           if (x != nullptr) {
               destroy_subtree(x->left);
               destroy_subtree(x->right);
               delete x;
           }
       }

       void rotate_left(NodePtr x) noexcept {
           NodePtr y = x->right;
           x->right = y->left;
           if (y->left != nullptr) {
               y->left->parent = x;
           }
           y->parent = x->parent;

           if (x == root()) {
               root() = y;
           } else if (x == x->parent->left) {
               x->parent->left = y;
           } else {
               x->parent->right = y;
           }

           y->left = x;
           x->parent = y;
       }

       void rotate_right(NodePtr y) noexcept {
           NodePtr x = y->left;
           y->left = x->right;
           if (x->right != nullptr) {
               x->right->parent = y;
           }
           x->parent = y->parent;

           if (y == root()) {
               root() = x;
           } else if (y == y->parent->right) {
               y->parent->right = x;
           } else {
               y->parent->left = x;
           }

           x->right = y;
           y->parent = x;
       }

       void rebalance_after_insert(NodePtr z) noexcept {
           z->color = RBColor::Red;
           while (z != root() && z->parent->color == RBColor::Red) {
               if (z->parent == z->parent->parent->left) {
                   NodePtr u = z->parent->parent->right;
                   if (u != nullptr && u->color == RBColor::Red) {
                       z->parent->color = RBColor::Black;
                       u->color = RBColor::Black;
                       z->parent->parent->color = RBColor::Red;
                       z = z->parent->parent;
                   } else {
                       if (z == z->parent->right) {
                           z = z->parent;
                           rotate_left(z);
                       }
                       z->parent->color = RBColor::Black;
                       z->parent->parent->color = RBColor::Red;
                       rotate_right(z->parent->parent);
                   }
               } else {
                   NodePtr u = z->parent->parent->left;
                   if (u != nullptr && u->color == RBColor::Red) {
                       z->parent->color = RBColor::Black;
                       u->color = RBColor::Black;
                       z->parent->parent->color = RBColor::Red;
                       z = z->parent->parent;
                   } else {
                       if (z == z->parent->left) {
                           z = z->parent;
                           rotate_right(z);
                       }
                       z->parent->color = RBColor::Black;
                       z->parent->parent->color = RBColor::Red;
                       rotate_left(z->parent->parent);
                   }
               }
           }
           root()->color = RBColor::Black;
       }

   public:
       MiniRBTree() {
           init_header();
       }

       ~MiniRBTree() noexcept {
           clear();
           delete header_;
       }

       MiniRBTree(const MiniRBTree&) = delete;
       MiniRBTree& operator=(const MiniRBTree&) = delete;

       MiniRBTree(MiniRBTree&& other) noexcept
           : header_(other.header_), node_count_(other.node_count_), comp_(other.comp_) {
           other.init_header();
       }

       MiniRBTree& operator=(MiniRBTree&& other) noexcept {
           if (this != &other) {
               clear();
               delete header_;
               header_ = other.header_;
               node_count_ = other.node_count_;
               comp_ = other.comp_;
               other.init_header();
           }
           return *this;
       }

       [[nodiscard]] size_type size() const noexcept { return node_count_; }
       [[nodiscard]] bool empty() const noexcept { return node_count_ == 0; }

       iterator begin() noexcept { return iterator(leftmost()); }
       iterator end() noexcept { return iterator(header_); }

       void clear() noexcept {
           if (root() != nullptr) {
               destroy_subtree(root());
               root() = nullptr;
               leftmost() = header_;
               rightmost() = header_;
               node_count_ = 0;
           }
       }

       std::pair<iterator, bool> insert_unique(const T& value) {
           NodePtr y = header_;
           NodePtr x = root();
           bool comp_val = true;

           while (x != nullptr) {
               y = x;
               comp_val = comp_(value, x->value);
               x = comp_val ? x->left : x->right;
           }

           iterator j = iterator(y);
           if (comp_val) {
               if (j == begin()) {
                   return {insert_node_at(x, y, value), true};
               } else {
                   --j;
               }
           }

           if (comp_(j.node->value, value)) {
               return {insert_node_at(x, y, value), true};
           }

           return {j, false};
       }

       iterator find(const T& key) noexcept {
           NodePtr x = root();
           NodePtr y = header_;

           while (x != nullptr) {
               if (!comp_(x->value, key)) {
                   y = x;
                   x = x->left;
               } else {
                   x = x->right;
               }
           }

           iterator j = iterator(y);
           return (j == end() || comp_(key, j.node->value)) ? end() : j;
       }

   private:
       iterator insert_node_at(NodePtr, NodePtr y, const T& v) {
           NodePtr z = new Node(v);
           if (y == header_ || comp_(v, y->value)) {
               y->left = z;
               if (y == header_) {
                   root() = z;
                   rightmost() = z;
               } else if (y == leftmost()) {
                   leftmost() = z;
               }
           } else {
               y->right = z;
               if (y == rightmost()) {
                   rightmost() = z;
               }
           }

           z->parent = y;
           z->left = nullptr;
           z->right = nullptr;

           rebalance_after_insert(z);
           ++node_count_;
           return iterator(z);
       }
   };

   struct HashNodeBase {
       HashNodeBase* next{nullptr};
       HashNodeBase() noexcept = default;
   };

   template <typename T>
   struct HashNode : public HashNodeBase {
       std::size_t hash_code{0};
       T value{};

       explicit HashNode(const T& v, std::size_t h, HashNodeBase* n = nullptr)
           : hash_code(h), value(v) {
           next = n;
       }
       explicit HashNode(T&& v, std::size_t h, HashNodeBase* n = nullptr)
           : hash_code(h), value(std::move(v)) {
           next = n;
       }
   };

   template <
       typename T,
       typename Hash = std::hash<T>,
       typename KeyEqual = std::equal_to<T>
   >
   class MiniHashTable {
   public:
       using value_type = T;
       using size_type = std::size_t;
       using NodeBase = HashNodeBase;
       using Node = HashNode<T>;
       using NodePtr = Node*;
       using BasePtr = NodeBase*;

       static constexpr std::size_t PRIME_TABLE[] = {
           11ul, 23ul, 53ul, 97ul, 193ul, 389ul, 769ul, 1543ul, 3079ul, 6151ul
       };
       static constexpr std::size_t NUM_PRIMES = sizeof(PRIME_TABLE) / sizeof(PRIME_TABLE[0]);

       struct Iterator {
           NodePtr cur{nullptr};

           Iterator() noexcept = default;
           explicit Iterator(NodePtr n) noexcept : cur(n) {}

           T& operator*() const noexcept { return cur->value; }
           T* operator->() const noexcept { return &(cur->value); }

           Iterator& operator++() noexcept {
               cur = static_cast<NodePtr>(cur->next);
               return *this;
           }

           Iterator operator++(int) noexcept {
               Iterator tmp = *this;
               cur = static_cast<NodePtr>(cur->next);
               return tmp;
           }

           bool operator==(const Iterator& other) const noexcept { return cur == other.cur; }
           bool operator!=(const Iterator& other) const noexcept { return cur != other.cur; }
       };

       using iterator = Iterator;

   private:
       BasePtr* buckets_{nullptr};
       size_type bucket_count_{0};
       NodeBase before_begin_{};
       size_type element_count_{0};
       float max_load_factor_{1.0f};
       Hash hasher_{};
       KeyEqual eq_{};

       [[nodiscard]] size_type bucket_index(std::size_t code) const noexcept {
           return code % bucket_count_;
       }

   public:
       MiniHashTable() {
           bucket_count_ = PRIME_TABLE[0];
           buckets_ = new BasePtr[bucket_count_]();
           before_begin_.next = nullptr;
       }

       ~MiniHashTable() noexcept {
           clear();
           delete[] buckets_;
       }

       MiniHashTable(const MiniHashTable&) = delete;
       MiniHashTable& operator=(const MiniHashTable&) = delete;

       MiniHashTable(MiniHashTable&& other) noexcept
           : buckets_(other.buckets_),
             bucket_count_(other.bucket_count_),
             element_count_(other.element_count_),
             max_load_factor_(other.max_load_factor_),
             hasher_(std::move(other.hasher_)),
             eq_(std::move(other.eq_)) {
           before_begin_.next = other.before_begin_.next;
           other.buckets_ = nullptr;
           other.bucket_count_ = 0;
           other.element_count_ = 0;
           other.before_begin_.next = nullptr;
       }

       MiniHashTable& operator=(MiniHashTable&& other) noexcept {
           if (this != &other) {
               clear();
               delete[] buckets_;

               buckets_ = other.buckets_;
               bucket_count_ = other.bucket_count_;
               element_count_ = other.element_count_;
               max_load_factor_ = other.max_load_factor_;
               hasher_ = std::move(other.hasher_);
               eq_ = std::move(other.eq_);
               before_begin_.next = other.before_begin_.next;

               other.buckets_ = nullptr;
               other.bucket_count_ = 0;
               other.element_count_ = 0;
               other.before_begin_.next = nullptr;
           }
           return *this;
       }

       [[nodiscard]] size_type size() const noexcept { return element_count_; }
       [[nodiscard]] bool empty() const noexcept { return element_count_ == 0; }
       [[nodiscard]] size_type bucket_count() const noexcept { return bucket_count_; }
       [[nodiscard]] float load_factor() const noexcept {
           return static_cast<float>(element_count_) / static_cast<float>(bucket_count_);
       }

       iterator begin() noexcept { return iterator(static_cast<NodePtr>(before_begin_.next)); }
       iterator end() noexcept { return iterator(nullptr); }

       void clear() noexcept {
           BasePtr curr = before_begin_.next;
           while (curr != nullptr) {
               BasePtr next = curr->next;
               delete static_cast<NodePtr>(curr);
               curr = next;
           }
           before_begin_.next = nullptr;
           element_count_ = 0;
           if (buckets_ != nullptr) {
               std::fill(buckets_, buckets_ + bucket_count_, nullptr);
           }
       }

       iterator find(const T& value) noexcept {
           const std::size_t code = hasher_(value);
           const size_type bkt = bucket_index(code);
           BasePtr curr = buckets_[bkt];
           while (curr != nullptr) {
               NodePtr node = static_cast<NodePtr>(curr);
               if (node->hash_code == code && eq_(node->value, value)) {
                   return iterator(node);
               }
               curr = curr->next;
               if (curr != nullptr && bucket_index(static_cast<NodePtr>(curr)->hash_code) != bkt) {
                   break;
               }
           }
           return end();
       }

       std::pair<iterator, bool> insert_unique(const T& value) {
           const std::size_t code = hasher_(value);
           const size_type bkt = bucket_index(code);

           BasePtr curr = buckets_[bkt];
           while (curr != nullptr) {
               NodePtr node = static_cast<NodePtr>(curr);
               if (node->hash_code == code && eq_(node->value, value)) {
                   return {iterator(node), false};
               }
               curr = curr->next;
               if (curr != nullptr && bucket_index(static_cast<NodePtr>(curr)->hash_code) != bkt) {
                   break;
               }
           }

           if (static_cast<float>(element_count_ + 1) > static_cast<float>(bucket_count_) * max_load_factor_) {
               rehash_growth();
           }

           return {insert_node_at_bucket(value, code), true};
       }

   private:
       iterator insert_node_at_bucket(const T& value, std::size_t code) {
           const size_type bkt = bucket_index(code);
           NodePtr new_node = new Node(value, code);

           if (buckets_[bkt] == nullptr) {
               new_node->next = before_begin_.next;
               before_begin_.next = new_node;
               buckets_[bkt] = new_node;
           } else {
               new_node->next = buckets_[bkt]->next;
               buckets_[bkt]->next = new_node;
           }

           ++element_count_;
           return iterator(new_node);
       }

       void rehash_growth() {
           size_type next_prime = bucket_count_ * 2;
           for (size_type i = 0; i < NUM_PRIMES; ++i) {
               if (PRIME_TABLE[i] > bucket_count_) {
                   next_prime = PRIME_TABLE[i];
                   break;
               }
           }

           BasePtr* new_buckets = new BasePtr[next_prime]();
           BasePtr curr = before_begin_.next;
           before_begin_.next = nullptr;

           while (curr != nullptr) {
               BasePtr next = curr->next;
               NodePtr node = static_cast<NodePtr>(curr);
               const size_type new_bkt = node->hash_code % next_prime;

               curr->next = new_buckets[new_bkt];
               new_buckets[new_bkt] = curr;

               curr = next;
           }

           BasePtr tail = &before_begin_;
           for (size_type b = 0; b < next_prime; ++b) {
               if (new_buckets[b] != nullptr) {
                   BasePtr bkt_head = new_buckets[b];
                   tail->next = bkt_head;
                   while (tail->next != nullptr) {
                       tail = tail->next;
                   }
               }
           }

           delete[] buckets_;
           buckets_ = new_buckets;
           bucket_count_ = next_prime;
       }
   };

   struct TrackedItem {
       int key{0};
       static inline int active_instances{0};
       static inline int copy_count{0};
       static inline int move_count{0};

       TrackedItem() noexcept { ++active_instances; }
       explicit TrackedItem(int k) noexcept : key(k) { ++active_instances; }
       TrackedItem(const TrackedItem& o) noexcept : key(o.key) {
           ++active_instances;
           ++copy_count;
       }
       TrackedItem(TrackedItem&& o) noexcept : key(o.key) {
           ++active_instances;
           ++move_count;
       }
       ~TrackedItem() noexcept { --active_instances; }

       bool operator<(const TrackedItem& o) const noexcept { return key < o.key; }
       bool operator==(const TrackedItem& o) const noexcept { return key == o.key; }

       static void reset_stats() noexcept {
           active_instances = 0;
           copy_count = 0;
           move_count = 0;
       }
   };

   struct TrackedHash {
       std::size_t operator()(const TrackedItem& item) const noexcept {
           return std::hash<int>{}(item.key);
       }
   };

   inline void test_mini_rb_tree() {
       std::cout << "[Test MiniRBTree] 启动红黑树微架构与平衡状态机检验..." << std::endl;
       MiniRBTree<int> tree;
       assert(tree.empty());
       assert(tree.size() == 0);

       const int keys[] = {10, 20, 30, 15, 25, 5, 1, 8};
       for (int k : keys) {
           auto [it, inserted] = tree.insert_unique(k);
           assert(inserted);
           assert(*it == k);
       }
       assert(tree.size() == 8);

       auto [dup_it, dup_inserted] = tree.insert_unique(20);
       assert(!dup_inserted);
       assert(*dup_it == 20);
       assert(tree.size() == 8);

       int expected_sorted[] = {1, 5, 8, 10, 15, 20, 25, 30};
       std::size_t idx = 0;
       for (auto it = tree.begin(); it != tree.end(); ++it) {
           assert(*it == expected_sorted[idx]);
           ++idx;
       }
       assert(idx == 8);

       assert(tree.find(15) != tree.end());
       assert(*tree.find(15) == 15);
       assert(tree.find(999) == tree.end());

       tree.clear();
       assert(tree.empty());
       assert(tree.size() == 0);
       std::cout << "[Test MiniRBTree] 验证通过：中序单调性与平衡修复正常。" << std::endl;
   }

   inline void test_mini_hash_table() {
       std::cout << "[Test MiniHashTable] 启动哈希表拉链法与动态重散列检验..." << std::endl;
       MiniHashTable<int> ht;
       assert(ht.empty());
       assert(ht.size() == 0);
       assert(ht.bucket_count() == 11);

       for (int i = 1; i <= 10; ++i) {
           auto [it, ins] = ht.insert_unique(i * 10);
           assert(ins);
           assert(*it == i * 10);
       }
       assert(ht.size() == 10);
       assert(ht.bucket_count() == 11);

       ht.insert_unique(110);
       ht.insert_unique(120);
       assert(ht.size() == 12);
       assert(ht.bucket_count() == 23);

       std::size_t traversed = 0;
       for (auto it = ht.begin(); it != ht.end(); ++it) {
           assert(*it % 10 == 0);
           ++traversed;
       }
       assert(traversed == 12);

       assert(ht.find(50) != ht.end());
       assert(*ht.find(50) == 50);
       assert(ht.find(999) == ht.end());

       auto [dup_it, dup_ins] = ht.insert_unique(50);
       assert(!dup_ins);
       assert(*dup_it == 50);
       assert(ht.size() == 12);

       MiniHashTable<TrackedItem, TrackedHash> tracked_ht;
       TrackedItem::reset_stats();

       for (int i = 1; i <= 5; ++i) {
           tracked_ht.insert_unique(TrackedItem(i));
       }
       assert(TrackedItem::active_instances == 5);

       auto target_it = tracked_ht.find(TrackedItem(3));
       assert(target_it != tracked_ht.end());
       const TrackedItem* target_addr = &(*target_it);

       for (int i = 6; i <= 30; ++i) {
           tracked_ht.insert_unique(TrackedItem(i));
       }
       assert(tracked_ht.size() == 30);
       assert(tracked_ht.bucket_count() >= 53);

       auto refound_it = tracked_ht.find(TrackedItem(3));
       assert(refound_it != tracked_ht.end());
       assert(&(*refound_it) == target_addr);
       assert(refound_it->key == 3);

       tracked_ht.clear();
       assert(TrackedItem::active_instances == 0);

       std::cout << "[Test MiniHashTable] 验证通过：Rehash 扩容与节点地址稳定性正常。" << std::endl;
   }

   } // namespace mini_stl

   int main() {
       mini_stl::test_mini_rb_tree();
       mini_stl::test_mini_hash_table();
       std::cout << "全部 Mini-RBTree 与 Mini-HashTable 工业级实战断言测试顺利通过！" << std::endl;
       return 0;
   }

