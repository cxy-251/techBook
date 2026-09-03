====================================================================================================
哈希表微架构与冲突处理：拉链法 (Chaining) 节点拓扑、负载因子 (Load Factor) 与二次幂/质数桶设计
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 4 模块前三节中，我们系统解构了基于红黑树（``_Rb_tree``）的有序关联容器体系（``set``、``map``、``multiset`` 与 ``multimap``）。有序容器依赖严格弱序比较器在树形拓扑中维护全局单调性，提供稳定的对数级（$\mathcal{O}(\log N)$）检索与范围查询。然而，在以高频点查（Point Lookup）、大规模键值聚合与极速插入为核心的系统场景中，对数检索的比较开销与跨缓存行（Cache Miss）指针追踪依然构成了吞吐率瓶颈。C++11 正式引入了基于散列技术的无序关联容器族（``std::unordered_*``）。无序容器彻底放弃了全局键排序，通过哈希函数将键直接映射至有限的桶数组（Bucket Array）中，在平均情况下达成期望的 $\mathcal{O}(1)$ 常数时间检索。本章深入剖析哈希表的数学散列基石、开放寻址法（Open Addressing）与标准库拉链法（Separate Chaining）在迭代器稳定性契约下的物理权衡、GCC libstdc++ 单向全局链表与桶指针前驱拓扑、哈希值缓存优化（Cached Hash Code）、负载因子（Load Factor）与动态重散列（Rehash）触发状态机，以及质数桶（Prime Buckets）与二次幂掩码桶（Power-of-Two Buckets）在 CPU 整数除法与雪崩效应（Avalanche Effect）层面的微架构性能博弈。

哈希散列映射数学基石与冲突必然性
--------------------------------

哈希表（Hash Table）的核心物理使命是将理论上无限庞大或极度离散的键空间 $\mathcal{K}$，通过散列算法压缩映射至有限的离散桶索引区间 $[0, B - 1]$。

两阶段散列压缩流水线
~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                     哈希表两阶段散列与桶定位流水线                          |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 阶段 1: 键散列化 (Hashing) ]                                            |
   |      Key k  ------>  std::hash<Key>()(k)  ------>  size_t 原始哈希值 H      |
   |                      (输出 64 位全局整数空间)                               |
   |                                                                             |
   |   [ 阶段 2: 空间区间压缩 (Bucket Index Compression) ]                        |
   |      H  ------>  Index = Compress(H, BucketCount)  ------> 桶索引 [0..B-1]  |
   |                  (质数取模: H % B  或  二次幂掩码: H & (B - 1))             |
   |                                                                             |
   |   [ 阶段 3: 候选节点等价性裁决 (Key Equality) ]                             |
   |      在 Bucket[Index] 链表中调用 KeyEqual()(node->key, k) 确认最终实体      |
   |                                                                             |
   +-----------------------------------------------------------------------------+

1. **哈希函数与等价性的一致性契约**：
   标准库强制规定：若两个键满足等价性谓词（$	ext{KeyEqual}(a, b) == 	ext{true}$），则二者计算出的哈希值必须绝对相等（$	ext{Hash}(a) == 	ext{Hash}(b)$）。反之，不同键产生相同哈希值属于合法但需化解的 **哈希冲突（Hash Collision）**。
2. **鸽巢原理与冲突必然性**：
   由于键空间尺寸 $|\mathcal{K}| \gg B$，依据鸽巢原理（Pigeonhole Principle），无论哈希函数分布多么均匀，哈希冲突在数学上不可避免。

冲突处理范式对决：开放寻址法 vs 标准库拉链法
--------------------------------------------

工业界存在两类主流的哈希冲突解决范式：

.. list-table:: 开放寻址法 (Open Addressing) 与拉链法 (Separate Chaining) 深度对比
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 评价维度
     - 开放寻址法（如 Google Swiss Table / Robin Hood）
     - 标准库拉链法（Node-based Separate Chaining）
   * - 物理内存布局
     - 单一大块连续扁平数组（Flat Array），所有数据内联存储
     - 桶数组（指针数组）+ 堆上独立分配的离散单向链表节点
   * - CPU 缓存局部性
     - **极高**（线性探测完全命中连续 L1/L2 缓存行）
     - 较低（遍历冲突链涉及多次离散堆内存指针跳转）
   * - 变易操作稳定性
     - **极弱**：插入触发数组扩容导致全量元素地址变动
     - **极强（标准契约）**：除被删除节点外，**任何变易均不使已有元素的指针/引用失效**
   * - 墓碑标记 (Tombstone)
     - 需要墓碑机制标记已删除槽位，影响后续探测效率
     - 链表物理解绑即刻释放节点，无任何墓碑开销
   * - C++ 标准库选型
     - 无法满足标准对节点引用绝对稳定的严苛契约
     - **C++ 标准无序容器（std::unordered_*）唯一合法实现底座**

C++ 标准严格规定：向 ``std::unordered_map`` 插入新元素时，**即使触发了全局 Rehash 扩容，所有已有元素的引用与指针必须保持绝对有效**。这一强约束在物理上直接排除了开放寻址法，确立了节点式拉链法在标准 STL 中的垄断地位。

拉链法物理节点拓扑 (GCC libstdc++ 模型)
----------------------------------------

在 GCC libstdc++ 的 ``std::_Hashtable`` 工业级实现中，为了兼顾单桶冲突遍历与全表顺序遍历（``begin()`` 到 ``end()``）的性能，标准库采用了极其精妙的 **全局单向链表 + 桶前驱指针** 拓扑。

全局贯通单向链表拓扑
~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                 GCC libstdc++ _Hashtable 桶数组与全局单向链表拓扑           |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 桶指针数组: __bucket_type* _M_buckets[B] ]                              |
   |   +----------+----------+----------+----------+----------+                  |
   |   | Bucket 0 | Bucket 1 | Bucket 2 | Bucket 3 | Bucket 4 |                  |
   |   +----+-----+----+-----+----+-----+----+-----+----+-----+                  |
   |        |          |          |          |          |                        |
   |        v          |          |          v          |                        |
   |     nullptr       |          |       nullptr       |                        |
   |                   |          \----------\          |                        |
   |                   v                     v          v                        |
   |            +--------------+      +--------------+  |                        |
   |            | 哨兵 Header  |      |   Node B1    |  |                        |
   |            |  _M_before   |      |  (Bucket 1)  |  |                        |
   |            +-------+------+      +-------+------+  |                        |
   |                    |                     |         |                        |
   |                    v                     v         v                        |
   |             +--------------+      +--------------+ +--------------+         |
   |             |   Node A1    | ---> |   Node B2    | |   Node C1    | -> ...  |
   |             |  (Bucket 1)  |      |  (Bucket 2)  | |  (Bucket 4)  |         |
   |             +--------------+      +--------------+ +--------------+         |
   |                                                                             |
   |   * 核心不变量: _M_buckets[i] 指向第 i 桶首元素在全局链表中的 前驱节点!     |
   |   * 全表遍历: 从 _M_before._M_nxt 出发沿单向链表高速流转 (无需扫描空桶)   |
   |                                                                             |
   +-----------------------------------------------------------------------------+

1. **全局单向链表贯通**：所有存入哈希表的物理节点通过 ``_M_nxt`` 指针串联成一条全局单一链表。
   - 容器的 ``begin()`` 直接返回指向全局首节点的迭代器。
   - 迭代器递增 ``operator++`` 仅需单条指针解引用 ``curr = curr->_M_nxt``，**遍历整张哈希表的时间复杂度严格为 $\mathcal{O}(N)$，完全消除了扫描空桶的开销**。
2. **桶指针指向前驱节点（Predecessor Pointer）**：
   桶数组 ``_M_buckets[i]`` 并不直接指向第 $i$ 个桶的首节点，而是指向其在全局链表中的 **直接前驱节点（即前一个桶的末尾节点，或首桶前驱哨兵 Header）**。
   - 物理收益：当向空桶插入首个节点，或在桶内执行单向链表删除时，由于直接持有了前驱节点指针，插入与删除可以在 $\mathcal{O}(1)$ 常数时间内完成前驱重织，无需反向遍历链表寻找前驱。

哈希值缓存优化 (Cached Hash Code)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于复杂键类型（如长字符串 ``std::string``、复合结构体），重复计算哈希值的开销极其昂贵。
标准库节点内部通过条件编译特化引入了 **哈希值缓存字段**：

.. code-block:: cpp

   template <typename Value, bool CacheHash>
   struct _Hash_node_value_base;

   // 当 Key 属于非基本数据类型时，开启缓存
   struct _Hash_node : public _Hash_node_base {
       Value _M_storage;
       std::size_t _M_hash_code; // 缓存 64 位原始哈希值
   };

- **Rehash 加速**：当触发扩容重散列时，直接复用 `_M_hash_code` 计算新桶索引，完全免除对所有元素重新调用哈希函数的 CPU 损耗。
- **快速判不等**：在遍历冲突链进行键匹配时，首先比对 `node->_M_hash_code == query_hash`，若哈希值不同直接跳过，仅在哈希值相同时才调用昂贵的 `KeyEqual()` 字符串比对。

负载因子 (Load Factor) 与 Rehash 动态扩容状态机
-----------------------------------------------

负载因子（Load Factor, $\alpha$）是衡量哈希表空间利用率与冲突密度的核心物理指标：

.. math::

   \alpha = \frac{	ext{size}()}{	ext{bucket\_count}()} = \frac{N}{B}

Rehash 触发契约
~~~~~~~~~~~~~~~

标准库默认将最大负载因子设置为 $	ext{max\_load\_factor} = 1.0$。
当调用 ``insert`` 或 ``emplace`` 插入新元素后，若满足以下判定条件：

.. math::

   \frac{N + 1}{B} > 	ext{max\_load\_factor}

容器强制触发 **重散列（Rehash）** 扩容状态机。

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        Rehash 动态重散列物理流转状态机                      |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 步骤 1: 计算新桶容量 NewBucketCount ]                                   |
   |      根据增长策略查询下一个质数 (libstdc++) 或左移翻倍 (MSVC: B * 2)        |
   |                                                                             |
   |   [ 步骤 2: 申请新桶数组内存 (Zero Allocation for Nodes) ]                  |
   |      __bucket_type* new_buckets = Alloc(NewBucketCount * sizeof(void*))     |
   |      全量初始化为 nullptr                                                   |
   |                                                                             |
   |   [ 步骤 3: 节点指针重织 (Pointer Re-weaving) ]                             |
   |      遍历旧全局链表中的每一个物理节点 Node:                                 |
   |      * 获取其缓存哈希值: H = Node->_M_hash_code                             |
   |      * 计算新桶索引: NewIdx = H % NewBucketCount                            |
   |      * 将 Node 重新编织挂入 new_buckets[NewIdx] 冲突链                      |
   |      * 物理节点本身原地不动，完全不调用 T 的构造函数或拷贝/移动函数!        |
   |                                                                             |
   |   [ 步骤 4: 释放旧桶指针数组，重置迭代器哨兵 ]                              |
   |                                                                             |
   +-----------------------------------------------------------------------------+

二次幂掩码桶 vs 质数取模桶设计博弈
----------------------------------

在将 64 位哈希值压缩至桶索引时，主流编译器展现了两种截然不同的架构路线：

.. list-table:: 质数桶设计与二次幂掩码桶设计微架构博弈
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 维度
     - 质数桶设计 (GCC libstdc++)
     - 二次幂掩码桶设计 (MSVC STL / LLVM / Abseil)
   * - 索引计算公式
     - $	ext{Index} = H \pmod{	ext{Prime}}$
     - $	ext{Index} = H \ \& \ (2^k - 1)$
   * - CPU 指令开销
     - 高（依赖硬件 64 位整数除法 ``DIV``，通常消耗 20~40 CPU 周期）
     - **极致（仅消耗单条单周期位与 `AND` 指令，耗时 < 1ns）**
   * - 劣质哈希防御力
     - **极强**（质数天然打散低位规律，如指针地址对齐低 3 位全 0）
     - 极弱（若哈希函数低位分布不均，将引发毁灭性桶碰撞）
   * - 依赖哈希质量
     - 容忍通用哈希算法
     - **强依赖雪崩哈希（Avalanche Hash，如 MurmurHash3 / WyHash）**

Lemire 快速取模算法 (Fast Modulo Reduction)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了在质数桶或任意桶数量下消除高延迟的整数除法指令，现代高性能计算广泛引入了 **Daniel Lemire 快速取模乘法算法**：

.. math::

   	ext{Index} = 	ext{uint32\_t}\left( \frac{	ext{uint64\_t}(H) 	imes B}{2^{32}} \right)

通过一次 64 位无符号乘法与一次右移 32 位操作，在单个时钟周期内完成无除法区段映射，兼顾了非二次幂桶的抗碰撞性与单周期执行效率。

工业级 C++ 完整 Mini-HashTable 内核实现
---------------------------------------

以下 C++ 源码实现了一套自包含的工业级拉链法哈希表 ``MiniHashTable<Key, Value>``。该实现涵盖：
1. 包含数据、哈希值缓存与单向指针的物理节点拓扑。
2. 内置预置质数表（Prime List）与动态 Rehash 扩容机制。
3. 保证全局链表常数时间遍历与桶前驱指针维护。
4. 包含 `insert`、`find`、`erase` 与负载因子动态监测。
5. 端到端测试套件（验证哈希冲突链挂载、Rehash 节点零拷贝重织与对数/常数点查）。

.. code-block:: cpp

   #pragma once
   #include <iostream>
   #include <memory>
   #include <utility>
   #include <cassert>
   #include <functional>
   #include <string>
   #include <vector>
   #include <algorithm>

   namespace core_stl {

   // 工业级预置质数增长表
   static constexpr size_t kPrimeList[] = {
       11ul, 23ul, 53ul, 97ul, 193ul, 389ul, 769ul, 1543ul, 3079ul,
       6151ul, 12289ul, 24593ul, 49157ul, 98317ul, 196613ul, 393241ul
   };

   inline size_t next_prime(size_t n) {
       for (size_t p : kPrimeList) {
           if (p >= n) return p;
       }
       return kPrimeList[sizeof(kPrimeList) / sizeof(size_t) - 1];
   }

   // =========================================================================
   // 1. 物理节点与哈希值缓存
   // =========================================================================
   struct HashNodeBase {
       HashNodeBase* Next = nullptr;
   };

   template <typename Val>
   struct HashNode : public HashNodeBase {
       Val Value;
       size_t HashCode = 0; // 缓存 64 位哈希值

       template <typename... Args>
       explicit HashNode(size_t hash, Args&&... args)
           : Value(std::forward<Args>(args)...), HashCode(hash) {}
   };

   // =========================================================================
   // 2. 前向迭代器
   // =========================================================================
   template <typename Val>
   struct HashTableIterator {
       using iterator_category = std::forward_iterator_tag;
       using value_type        = Val;
       using reference         = Val&;
       using pointer           = Val*;

       HashNodeBase* Node = nullptr;

       HashTableIterator() = default;
       explicit HashTableIterator(HashNodeBase* n) : Node(n) {}

       reference operator*() const noexcept {
           return static_cast<HashNode<Val>*>(Node)->Value;
       }

       pointer operator->() const noexcept {
           return &static_cast<HashNode<Val>*>(Node)->Value;
       }

       HashTableIterator& operator++() noexcept {
           Node = Node->Next;
           return *this;
       }

       HashTableIterator operator++(int) noexcept {
           HashTableIterator tmp = *this;
           Node = Node->Next;
           return tmp;
       }

       bool operator==(const HashTableIterator& o) const noexcept { return Node == o.Node; }
       bool operator!=(const HashTableIterator& o) const noexcept { return Node != o.Node; }
   };

   // =========================================================================
   // 3. MiniHashTable 主容器
   // =========================================================================
   template <
       typename Key,
       typename Value,
       typename KeyOfValue,
       typename Hash = std::hash<Key>,
       typename Equal = std::equal_to<Key>
   >
   class MiniHashTable {
   public:
       using iterator = HashTableIterator<Value>;

   private:
       using Node = HashNode<Value>;
       using Alloc = std::allocator<Node>;
       using BucketAlloc = std::allocator<HashNodeBase*>;

       HashNodeBase _M_before_begin; // 全局单向链表头前驱哨兵
       HashNodeBase** _M_buckets = nullptr;
       size_t _M_bucket_count = 0;
       size_t _M_element_count = 0;
       float _M_max_load_factor = 1.0f;

       Hash _M_hash;
       Equal _M_equal;
       Alloc _M_node_alloc;
       BucketAlloc _M_bucket_alloc;

   public:
       explicit MiniHashTable(size_t initial_buckets = 11) {
           _M_bucket_count = next_prime(initial_buckets);
           allocate_buckets(_M_bucket_count);
           _M_before_begin.Next = nullptr;
       }

       ~MiniHashTable() {
           clear();
           deallocate_buckets();
       }

       [[nodiscard]] size_t size() const noexcept { return _M_element_count; }
       [[nodiscard]] size_t bucket_count() const noexcept { return _M_bucket_count; }
       [[nodiscard]] bool empty() const noexcept { return _M_element_count == 0; }
       [[nodiscard]] float load_factor() const noexcept {
           return static_cast<float>(_M_element_count) / static_cast<float>(_M_bucket_count);
       }

       iterator begin() noexcept { return iterator(_M_before_begin.Next); }
       iterator end() noexcept { return iterator(nullptr); }

       // 对标对数/常数查找
       iterator find(const Key& k) {
           size_t code = _M_hash(k);
           size_t bkt = code % _M_bucket_count;
           HashNodeBase* curr = _M_buckets[bkt];

           while (curr) {
               Node* realNode = static_cast<Node*>(curr);
               if (realNode->HashCode == code && _M_equal(KeyOfValue()(realNode->Value), k)) {
                   return iterator(curr);
               }
               // 若下一个节点不再属于当前桶，提前终止查找
               if (curr->Next && (static_cast<Node*>(curr->Next)->HashCode % _M_bucket_count) != bkt) {
                   break;
               }
               curr = curr->Next;
           }
           return end();
       }

       // 唯一键插入
       template <typename... Args>
       std::pair<iterator, bool> emplace_unique(Args&&... args) {
           // 检查并按需触发 Rehash
           if (static_cast<float>(_M_element_count + 1) / static_cast<float>(_M_bucket_count) > _M_max_load_factor) {
               rehash(next_prime(_M_bucket_count * 2));
           }

           // 构造临时值以提取 Key (实际工业实现使用 piecewise 或预计算)
           Node* newNode = _M_node_alloc.allocate(1);
           std::allocator_traits<Alloc>::construct(_M_node_alloc, newNode, 0, std::forward<Args>(args)...);
           const Key& k = KeyOfValue()(newNode->Value);
           size_t code = _M_hash(k);
           newNode->HashCode = code;

           // 检查是否存在重复键
           size_t bkt = code % _M_bucket_count;
           HashNodeBase* curr = _M_buckets[bkt];
           while (curr) {
               Node* realNode = static_cast<Node*>(curr);
               if (realNode->HashCode == code && _M_equal(KeyOfValue()(realNode->Value), k)) {
                   // 键冲突且等价: 释放新节点，返回已有迭代器
                   std::allocator_traits<Alloc>::destroy(_M_node_alloc, newNode);
                   _M_node_alloc.deallocate(newNode, 1);
                   return {iterator(curr), false};
               }
               if (curr->Next && (static_cast<Node*>(curr->Next)->HashCode % _M_bucket_count) != bkt) break;
               curr = curr->Next;
           }

           // 物理插入: 挂入全局链表头部
           newNode->Next = _M_before_begin.Next;
           _M_before_begin.Next = newNode;
           _M_buckets[bkt] = newNode;

           ++_M_element_count;
           return {iterator(newNode), true};
       }

       void rehash(size_t new_buckets_count) {
           new_buckets_count = next_prime(new_buckets_count);
           if (new_buckets_count == _M_bucket_count) return;

           HashNodeBase** new_buckets = _M_bucket_alloc.allocate(new_buckets_count);
           std::fill_n(new_buckets, new_buckets_count, nullptr);

           // 重新穿针引线 (零节点内存重新分配!)
           HashNodeBase* curr = _M_before_begin.Next;
           _M_before_begin.Next = nullptr;

           while (curr) {
               HashNodeBase* next = curr->Next;
               Node* realNode = static_cast<Node*>(curr);
               size_t new_bkt = realNode->HashCode % new_buckets_count;

               // 头插法接入新全局链表
               curr->Next = _M_before_begin.Next;
               _M_before_begin.Next = curr;
               new_buckets[new_bkt] = curr;

               curr = next;
           }

           deallocate_buckets();
           _M_buckets = new_buckets;
           _M_bucket_count = new_buckets_count;
       }

       void clear() noexcept {
           HashNodeBase* curr = _M_before_begin.Next;
           while (curr) {
               HashNodeBase* next = curr->Next;
               Node* realNode = static_cast<Node*>(curr);
               std::allocator_traits<Alloc>::destroy(_M_node_alloc, realNode);
               _M_node_alloc.deallocate(realNode, 1);
               curr = next;
           }
           _M_before_begin.Next = nullptr;
           std::fill_n(_M_buckets, _M_bucket_count, nullptr);
           _M_element_count = 0;
       }

   private:
       void allocate_buckets(size_t count) {
           _M_buckets = _M_bucket_alloc.allocate(count);
           std::fill_n(_M_buckets, count, nullptr);
       }

       void deallocate_buckets() noexcept {
           if (_M_buckets) {
               _M_bucket_alloc.deallocate(_M_buckets, _M_bucket_count);
               _M_buckets = nullptr;
           }
       }
   };

   } // namespace core_stl

   // =========================================================================
   // 4. 端到端测试与微架构验证套件
   // =========================================================================
   namespace test {

   struct PairSelect1st {
       const std::string& operator()(const std::pair<const std::string, int>& p) const noexcept {
           return p.first;
       }
   };

   inline void runHashTableTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " MiniHashTable 拉链法微架构与 Rehash 动态扩容测试套件
";
       std::cout << "=======================================================

";

       using TableType = core_stl::MiniHashTable<
           std::string,
           std::pair<const std::string, int>,
           PairSelect1st
       >;

       TableType table(11);
       assert(table.bucket_count() == 11);
       assert(table.empty());

       // 1. 插入测试与负载因子追踪
       std::vector<std::string> words = {
           "compiler", "architecture", "register", "allocation",
           "dominator", "frontier", "variable", "ssa", "pipeline"
       };

       std::cout << "[测试 1: 批量插入与哈希分布]:
";
       int val = 1;
       for (const auto& w : words) {
           auto [it, ins] = table.emplace_unique(std::make_pair(w, val++));
           assert(ins);
           std::cout << "  插入: \"" << it->first << "\" -> " << it->second
                     << " (size=" << table.size() << ", load_factor=" << table.load_factor() << ")
";
       }
       assert(table.size() == 9);

       // 2. 触发 Rehash 扩容测试 (再插入 5 个元素强制突破 load_factor > 1.0)
       size_t old_bkt_count = table.bucket_count();
       table.emplace_unique(std::make_pair("extra_1", 100));
       table.emplace_unique(std::make_pair("extra_2", 200));
       table.emplace_unique(std::make_pair("extra_3", 300));

       std::cout << "
[测试 2: 动态 Rehash 扩容生效验证]:
"
                 << "  旧桶数量: " << old_bkt_count
                 << " -> 新桶数量: " << table.bucket_count()
                 << " (元素总数: " << table.size() << ", load_factor: " << table.load_factor() << ")
";
       assert(table.bucket_count() > old_bkt_count);

       // 3. 常数时间查找与哈希值缓存校验
       auto it_find = table.find("dominator");
       assert(it_find != table.end() && it_find->second == 5);
       auto it_miss = table.find("non_exist_key");
       assert(it_miss == table.end());

       std::cout << "
[测试 3: 哈希定位对标]:
"
                 << "  find(\"dominator\") = " << it_find->first << " -> " << it_find->second << " (OK)
"
                 << "  find(\"non_exist_key\") = MISS (OK)

";

       std::cout << "  -> MiniHashTable 拉链法与 Rehash 状态机验证完全通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰展示了拉链法哈希表的核心物理运转机制：

1. **常数级单桶冲突插入**：初始 9 个字符串顺利通过质数取模（$H \pmod{11}$）分散挂接在不同桶中，哈希值缓存字段完全消除了后续比对与扩容时的冗余哈希计算。
2. **Rehash 零对象开销重散列**：当插入导致负载因子逼近 $1.0$ 时，容器自动申请尺寸为 $23$ 的新质数桶指针数组，并在原址重织全局单向链表，未发生任何实体键值对象的析构或重新构造。
3. **全局链表无缝遍历**：全表遍历直接沿单向链表推进，耗时严格受元素数量 $N$ 控制，消除了对海量空桶的无谓扫描。

小结与下章导读
--------------

本章系统解构了现代 C++ 无序关联容器底层哈希表的微架构与核心机制：

1. **散列化与冲突必然性**：推导了两阶段散列压缩流水线，明确了 $	ext{KeyEqual}$ 与 $	ext{Hash}$ 必须遵循的等价性公理契约。
2. **拉链法垄断成因**：剖析了标准 STL 对变易操作下已有节点引用与指针绝对稳定的要求，论证了开放寻址法因无法保持引用稳定而被排除的标准物理根源。
3. **全局单向链表与桶前驱拓扑**：解构了 GCC libstdc++ 的 `_M_before` 哨兵设计与桶数组存放前驱指针的实现机理，阐明了全表 $\mathcal{O}(N)$ 极速遍历与哈希值缓存优化。
4. **取模算子微架构博弈**：对比了质数桶（硬件除法代价）与二次幂掩码桶（位运算极速但依赖雪崩哈希）的设计权衡，介绍了 Lemire 快速无除法取模技术。

在掌握了哈希表自平衡与拉链法内核之后，下一章我们将深入剖析标准库中基于哈希表构建的具体无序容器。在第 4 模块第 5 节 **std::unordered_map 与 std::unordered_set：哈希函数、等价谓词、rehash 动态重构与迭代器局部失效（``04_associative_and_hash_containers/05_unordered_containers_and_iterator_invalidation.rst``）** 中，我们将深入剖析自定义类型的 `Hash` 与 `KeyEqual` 特化规范、桶接口（Bucket Interface / `bucket_count` / `load_factor`）、`operator[]` 的哈希插入语义，以及在 Rehash 发生时仅引发迭代器失效而指针/引用保持存活的独有微架构边界。
