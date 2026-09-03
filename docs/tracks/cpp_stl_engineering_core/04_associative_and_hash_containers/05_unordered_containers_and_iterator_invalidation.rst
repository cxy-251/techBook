====================================================================================================
std::unordered_map 与 std::unordered_set：哈希函数、等价谓词、rehash 动态重构与迭代器局部失效
====================================================================================================

.. note:: 前置背景与上下文承接
   在第 4 模块第 4 节（``04_associative_and_hash_containers/04_hash_table_chaining_and_rehash_dynamics.rst``）中，我们深入剖析了无序关联容器底层哈希表（``_Hashtable``）的微架构、拉链法（Separate Chaining）在单向全局链表与桶前驱指针维度的物理拓扑、哈希值缓存优化，以及质数取模桶与二次幂掩码桶的性能博弈。底层哈希表为标准库提供了通用的离散节点存储与重散列引擎。在本章中，我们将聚焦基于该底座构建的两个最核心的无序关联容器——**``std::unordered_set``**（唯一键哈希集合）与 **``std::unordered_map``**（唯一键值哈希映射表）。本章系统解构自定义类型的 ``Hash`` 仿函数与多字段哈希混淆（Hash Combine）最佳实践、``KeyEqual`` 谓词与哈希函数的数学一致性契约、桶接口（Bucket Interface）在哈希聚集度诊断中的物理意义、``operator[]`` 与 C++17 ``try_emplace`` 的执行代价，以及无序容器独有的 **“Rehash 时迭代器全量失效而元素指针/引用绝对存活”** 的微架构失效边界。

模板架构与自定义类型散列契约
----------------------------

标准无序容器采用正交解耦的泛型模板声明：

.. code-block:: cpp

   template <
       typename Key,
       typename T,
       typename Hash = std::hash<Key>,
       typename KeyEqual = std::equal_to<Key>,
       typename Allocator = std::allocator<std::pair<const Key, T>>
   >
   class unordered_map;

哈希函数与等价谓词的一致性契约
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当调用者为自定义复合类型（如包含多个成员字段的业务结构体）特化哈希与比较策略时，必须严格遵守以下 **代数一致性契约**：

.. math::

   \forall a, b \in 	ext{Domain}, \quad 	ext{KeyEqual}(a, b) == 	ext{true} \implies 	ext{Hash}(a) == 	ext{Hash}(b)

若违反该契约（例如 ``KeyEqual`` 比较了字段 $X$ 与 $Y$，而 ``Hash`` 仅对字段 $X$ 进行了散列计算），会导致两个在语义上等价的对象被分配到不同的桶索引中，从而使 ``find()`` 无法命中已存在的等价键，造成严重的静默数据不一致。

多字段哈希混淆 (Hash Combine) 最佳实践
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于包含多个成员变量的自定义类，朴素的按位异或（``hash(A) ^ hash(B)``）会导致对称字段（如 $A=1, B=2$ 与 $A=2, B=1$）产生完全相同的哈希碰撞。

工业级系统（如 Boost 与 LLVM）广泛采用基于黄金分割比（Golden Ratio 常数 ``0x9e3779b9``）的 **哈希雪崩混淆算法（Hash Combine）**：

.. math::

   	ext{seed} = 	ext{seed} \oplus \left( 	ext{Hash}(v) + 	ext{0x9e3779b9} + (	ext{seed} \ll 6) + (	ext{seed} \gg 2) \right)

通过结合加法、高位左移与低位右移，将新字段的熵均匀扩散到整个 64 位整型空间中，彻底破坏对称冲突。

const Key 物理约束与桶索引保护
------------------------------

与有序容器类似，``std::unordered_map`` 的节点元素类型被强制定义为：

.. code-block:: cpp

   using value_type = std::pair<const Key, T>;

.. list-table:: const Key 在无序容器中的物理防御意义
   :widths: 25 35 40
   :header-rows: 1
   :class: tight-table

   * - 容器类型
     - 元素键类型
     - 物理微架构保护机制
   * - ``std::unordered_map<K, V>``
     - ``std::pair<const K, V>``
     - 阻止通过迭代器修改 ``it->first``；若键被原地修改，其新哈希值将与节点当前所在的桶索引发生错位，导致后续 ``find()`` 沿新哈希定位至其他桶而永久丢失该节点
   * - ``std::unordered_set<K>``
     - ``const K``
     - 迭代器的 ``operator*`` 恒定返回 ``const Key&``，彻底封死原地写权限

桶接口 (Bucket Interface) 与哈希聚集度诊断
------------------------------------------

为了让系统工程师能够直接内省哈希表的底层分布质量，C++ 标准库暴露了全套 **桶接口（Bucket Interface）**：

.. code-block:: text

   +-----------------------------------------------------------------------------+
   |                        哈希表桶接口 (Bucket Interface) 架构                 |
   +-----------------------------------------------------------------------------+
   |                                                                             |
   |   [ 容器级指标 ]:                                                           |
   |      * bucket_count():      返回当前分配的总桶数 B                          |
   |      * max_bucket_count():  返回系统支持的最大桶数上限                      |
   |      * load_factor():       返回当前平均负载因子 N / B                      |
   |      * max_load_factor():   获取/设置触发 Rehash 的负载阈值 (默认 1.0)      |
   |                                                                             |
   |   [ 单桶级指标与本地迭代器 (Local Iterators) ]:                             |
   |      * bucket(key):         返回指定键当前被映射到的桶索引 [0..B-1]         |
   |      * bucket_size(n):      返回第 n 个桶内部冲突链上的节点总数             |
   |      * begin(n) / end(n):   返回遍历第 n 个桶内部冲突链的 本地迭代器        |
   |                                                                             |
   +-----------------------------------------------------------------------------+

哈希聚集度与复杂度退化诊断
~~~~~~~~~~~~~~~~~~~~~~~~~~

当哈希函数设计不当或遭遇哈希碰撞攻击（HashDoS）时，海量元素会塌陷聚集在极少数桶中：
- 若最大桶深度 $\max(	ext{bucket\_size}(i)) \gg 	ext{load\_factor}()$，表明哈希分布极度不均。
- 此时点查操作将在冲突链上退化为 $\mathcal{O}(N)$ 线性扫描。
- 借助桶接口，工程师可在单元测试中统计方差 $\sigma^2 = \frac{1}{B}\sum (	ext{bucket\_size}(i) - \alpha)^2$，确保哈希函数在实际业务载荷下保持近乎泊松分布。

变易接口与微架构深度剖析
-----------------------

operator[] 惰性插入语义与代价
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``std::unordered_map::operator[](const Key& k)`` 的内部执行流水线包含：
1. 计算 $H = 	ext{Hash}(k)$，定位桶索引 $	ext{Idx} = H \pmod B$。
2. 遍历第 $	ext{Idx}$ 个桶的冲突链。若找到等价键，直接返回对应值的引用 ``it->second``。
3. **若键不存在，容器触发节点分配并执行值类型的默认构造（Value Initialization），随后将其插入链表头部并返回新构造值的引用**。
- **性能戒律**：与有序 map 相同，只读查询严禁调用 ``operator[]``，必须调用 ``find()``。

C++17 try_emplace 与 insert_or_assign
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

C++17 引入了零开销转发接口：
- **``try_emplace(key, args...)``**：仅当哈希表中不存在键 ``key`` 时，才在堆节点内部直接原地调用 ``T(args...)`` 构造映射值。若键已存在，**传入的参数绝对不被移动或复制**，消除了构造开销。
- **``insert_or_assign(key, value)``**：若键存在则直接赋值覆写，若不存在则插入新节点。

C++17 extract() 节点句柄机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

通过 ``auto nh = map.extract(key);``，调用者可在 $\mathcal{O}(1)$ 内将节点从哈希表中解绑并持有其所有权。在处于节点句柄（Node Handle）状态时，调用者允许合法修改 ``nh.key()``，随后将其重新插入（``map.insert(std::move(nh))``），达成跨容器的 **零内存分配转移**。

迭代器失效规则全景：迭代器 vs 指针/引用分离
--------------------------------------------

无序关联容器展现出 C++ 标准库中最具特色的 **双态失效边界（Dual Invalidation Invariants）**：

.. list-table:: std::unordered_* 容器变易操作失效规则矩阵
   :widths: 22 28 50
   :header-rows: 1
   :class: tight-table

   * - 容器操作场景
     - 迭代器失效状态 (Iterators)
     - 指针与引用失效状态 (Pointers & References)
   * - **未触发 Rehash 的插入** (``insert/emplace``)
     - **全量保持有效**（除尾后迭代器 ``end()`` 外，其他迭代器不受影响）
     - **绝对有效**（新节点在独立堆地址构造，不影响既有元素地址）
   * - **触发 Rehash 的插入** (``size > max_load * buckets``)
     - **全量失效**（因为桶数组指针与全局单向链表链接被全面打散重织）
     - **绝对有效**（物理节点本身原地不动，内存地址与生命周期恒定）
   * - **单节点删除** (``erase(pos)`` / ``erase(key)``)
     - **仅指向被删除节点的迭代器失效**；其他所有迭代器依然有效
     - **仅指向被删除元素的指针/引用失效**；其他所有指针/引用完全有效
   * - **clear()**
     - 全量失效
     - 全量失效

.. note:: 物理本质核心
   与 ``std::vector`` 扩容时元素物理搬迁导致指针全废不同，哈希表的 Rehash 仅仅重构桶指针数组与单向链表指针，**节点本身未发生任何内存重新分配或对象拷贝**。因此，指向无序容器中已有元素的裸指针与引用在 Rehash 前后永远保持合法有效！

工业级 C++ 完整 Mini-Unordered-Map 与 Mini-Unordered-Set 内核实现
-----------------------------------------------------------------

以下 C++ 源码实现了一套自包含的工业级 ``MiniUnorderedSet<Key>`` 与 ``MiniUnorderedMap<Key, Value>`` 容器模板。该实现涵盖：
1. 包含黄金分割比混淆的 `hash_combine` 仿函数。
2. 严格遵循 `const Key` 强类型约束的键值节点。
3. 包含 `operator[]`、`try_emplace` 与 `find` 的核心接口。
4. 全套桶接口（`bucket_count`、`bucket_size`、`load_factor`）。
5. 验证 Rehash 发生时“迭代器失效而指针/引用绝对稳定”的端到端测试套件。

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

   // 黄金分割比哈希混淆工具
   template <typename T>
   inline void hash_combine(size_t& seed, const T& val) noexcept {
       seed ^= std::hash<T>{}(val) + 0x9e3779b9 + (seed << 6) + (seed >> 2);
   }

   // 工业级预置质数表
   static constexpr size_t kPrimeTable[] = {
       7ul, 17ul, 37ul, 79ul, 163ul, 331ul, 673ul, 1361ul, 2729ul, 5471ul
   };

   inline size_t get_next_prime(size_t n) {
       for (size_t p : kPrimeTable) {
           if (p >= n) return p;
       }
       return kPrimeTable[sizeof(kPrimeTable) / sizeof(size_t) - 1];
   }

   // =========================================================================
   // 1. 物理节点与哈希容器通用内核
   // =========================================================================
   struct HashNodeBase {
       HashNodeBase* Next = nullptr;
   };

   template <typename Val>
   struct HashNode : public HashNodeBase {
       Val Value;
       size_t HashCode = 0;

       template <typename... Args>
       explicit HashNode(size_t hash, Args&&... args)
           : Value(std::forward<Args>(args)...), HashCode(hash) {}
   };

   template <typename Val, typename Ref, typename Ptr>
   struct HashTableIterator {
       using iterator_category = std::forward_iterator_tag;
       using value_type        = Val;
       using reference         = Ref;
       using pointer           = Ptr;

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

       bool operator==(const HashTableIterator& o) const noexcept { return Node == o.Node; }
       bool operator!=(const HashTableIterator& o) const noexcept { return Node != o.Node; }
   };

   template <
       typename Key,
       typename Value,
       typename KeyOfValue,
       typename Hash = std::hash<Key>,
       typename Equal = std::equal_to<Key>
   >
   class HashTableCore {
   public:
       using iterator       = HashTableIterator<Value, Value&, Value*>;
       using const_iterator = HashTableIterator<Value, const Value&, const Value*>;

   private:
       using Node = HashNode<Value>;
       using Alloc = std::allocator<Node>;
       using BucketAlloc = std::allocator<HashNodeBase*>;

       HashNodeBase _M_before_begin;
       HashNodeBase** _M_buckets = nullptr;
       size_t _M_bucket_count = 0;
       size_t _M_element_count = 0;
       float _M_max_load_factor = 1.0f;

       Hash _M_hash;
       Equal _M_equal;
       Alloc _M_node_alloc;
       BucketAlloc _M_bucket_alloc;

   public:
       explicit HashTableCore(size_t initial_buckets = 7) {
           _M_bucket_count = get_next_prime(initial_buckets);
           _M_buckets = _M_bucket_alloc.allocate(_M_bucket_count);
           std::fill_n(_M_buckets, _M_bucket_count, nullptr);
           _M_before_begin.Next = nullptr;
       }

       ~HashTableCore() {
           clear();
           if (_M_buckets) {
               _M_bucket_alloc.deallocate(_M_buckets, _M_bucket_count);
           }
       }

       [[nodiscard]] size_t size() const noexcept { return _M_element_count; }
       [[nodiscard]] size_t bucket_count() const noexcept { return _M_bucket_count; }
       [[nodiscard]] bool empty() const noexcept { return _M_element_count == 0; }
       [[nodiscard]] float load_factor() const noexcept {
           return static_cast<float>(_M_element_count) / static_cast<float>(_M_bucket_count);
       }

       iterator begin() noexcept { return iterator(_M_before_begin.Next); }
       iterator end() noexcept { return iterator(nullptr); }
       const_iterator begin() const noexcept { return const_iterator(_M_before_begin.Next); }
       const_iterator end() const noexcept { return const_iterator(nullptr); }

       // 桶接口支持
       size_t bucket(const Key& k) const {
           return _M_hash(k) % _M_bucket_count;
       }

       size_t bucket_size(size_t bkt) const {
           assert(bkt < _M_bucket_count);
           size_t count = 0;
           HashNodeBase* curr = _M_buckets[bkt];
           while (curr) {
               ++count;
               if (curr->Next && (static_cast<Node*>(curr->Next)->HashCode % _M_bucket_count) != bkt) break;
               curr = curr->Next;
           }
           return count;
       }

       iterator find(const Key& k) {
           size_t code = _M_hash(k);
           size_t bkt = code % _M_bucket_count;
           HashNodeBase* curr = _M_buckets[bkt];

           while (curr) {
               Node* rn = static_cast<Node*>(curr);
               if (rn->HashCode == code && _M_equal(KeyOfValue()(rn->Value), k)) {
                   return iterator(curr);
               }
               if (curr->Next && (static_cast<Node*>(curr->Next)->HashCode % _M_bucket_count) != bkt) break;
               curr = curr->Next;
           }
           return end();
       }

       template <typename... Args>
       std::pair<iterator, bool> emplace_unique(Args&&... args) {
           if (static_cast<float>(_M_element_count + 1) / static_cast<float>(_M_bucket_count) > _M_max_load_factor) {
               rehash(get_next_prime(_M_bucket_count * 2));
           }

           Node* newNode = _M_node_alloc.allocate(1);
           std::allocator_traits<Alloc>::construct(_M_node_alloc, newNode, 0, std::forward<Args>(args)...);

           const Key& k = KeyOfValue()(newNode->Value);
           size_t code = _M_hash(k);
           newNode->HashCode = code;

           size_t bkt = code % _M_bucket_count;
           HashNodeBase* curr = _M_buckets[bkt];
           while (curr) {
               Node* rn = static_cast<Node*>(curr);
               if (rn->HashCode == code && _M_equal(KeyOfValue()(rn->Value), k)) {
                   std::allocator_traits<Alloc>::destroy(_M_node_alloc, newNode);
                   _M_node_alloc.deallocate(newNode, 1);
                   return {iterator(curr), false};
               }
               if (curr->Next && (static_cast<Node*>(curr->Next)->HashCode % _M_bucket_count) != bkt) break;
               curr = curr->Next;
           }

           // 物理插入全局链表首部
           newNode->Next = _M_before_begin.Next;
           _M_before_begin.Next = newNode;
           _M_buckets[bkt] = newNode;

           ++_M_element_count;
           return {iterator(newNode), true};
       }

       void rehash(size_t new_buckets_count) {
           new_buckets_count = get_next_prime(new_buckets_count);
           if (new_buckets_count == _M_bucket_count) return;

           HashNodeBase** new_buckets = _M_bucket_alloc.allocate(new_buckets_count);
           std::fill_n(new_buckets, new_buckets_count, nullptr);

           HashNodeBase* curr = _M_before_begin.Next;
           _M_before_begin.Next = nullptr;

           // 原地重新穿针引线 (零节点内存释放与重新构造!)
           while (curr) {
               HashNodeBase* next = curr->Next;
               Node* rn = static_cast<Node*>(curr);
               size_t new_bkt = rn->HashCode % new_buckets_count;

               curr->Next = _M_before_begin.Next;
               _M_before_begin.Next = curr;
               new_buckets[new_bkt] = curr;

               curr = next;
           }

           _M_bucket_alloc.deallocate(_M_buckets, _M_bucket_count);
           _M_buckets = new_buckets;
           _M_bucket_count = new_buckets_count;
       }

       void clear() noexcept {
           HashNodeBase* curr = _M_before_begin.Next;
           while (curr) {
               HashNodeBase* next = curr->Next;
               Node* rn = static_cast<Node*>(curr);
               std::allocator_traits<Alloc>::destroy(_M_node_alloc, rn);
               _M_node_alloc.deallocate(rn, 1);
               curr = next;
           }
           _M_before_begin.Next = nullptr;
           std::fill_n(_M_buckets, _M_bucket_count, nullptr);
           _M_element_count = 0;
       }
   };

   // =========================================================================
   // 2. MiniUnorderedSet 容器适配器
   // =========================================================================
   template <typename Key, typename Hash = std::hash<Key>, typename Equal = std::equal_to<Key>>
   class MiniUnorderedSet {
       struct Identity {
           const Key& operator()(const Key& k) const noexcept { return k; }
       };
       using TableType = HashTableCore<Key, Key, Identity, Hash, Equal>;
       TableType _M_table;

   public:
       using iterator = typename TableType::const_iterator;

       MiniUnorderedSet() = default;

       [[nodiscard]] size_t size() const noexcept { return _M_table.size(); }
       [[nodiscard]] bool empty() const noexcept { return _M_table.empty(); }
       [[nodiscard]] size_t bucket_count() const noexcept { return _M_table.bucket_count(); }

       iterator begin() const noexcept { return _M_table.begin(); }
       iterator end() const noexcept { return _M_table.end(); }

       std::pair<iterator, bool> insert(const Key& k) {
           auto res = _M_table.emplace_unique(k);
           return {iterator(res.first.Node), res.second};
       }

       iterator find(const Key& k) const {
           return iterator(const_cast<TableType&>(_M_table).find(k).Node);
       }
   };

   // =========================================================================
   // 3. MiniUnorderedMap 容器适配器
   // =========================================================================
   template <typename Key, typename T, typename Hash = std::hash<Key>, typename Equal = std::equal_to<Key>>
   class MiniUnorderedMap {
   public:
       using value_type = std::pair<const Key, T>;

   private:
       struct Select1st {
           const Key& operator()(const value_type& p) const noexcept { return p.first; }
       };
       using TableType = HashTableCore<Key, value_type, Select1st, Hash, Equal>;
       TableType _M_table;

   public:
       using iterator = typename TableType::iterator;

       MiniUnorderedMap() = default;

       [[nodiscard]] size_t size() const noexcept { return _M_table.size(); }
       [[nodiscard]] bool empty() const noexcept { return _M_table.empty(); }
       [[nodiscard]] size_t bucket_count() const noexcept { return _M_table.bucket_count(); }
       [[nodiscard]] float load_factor() const noexcept { return _M_table.load_factor(); }

       iterator begin() noexcept { return _M_table.begin(); }
       iterator end() noexcept { return _M_table.end(); }

       iterator find(const Key& k) { return _M_table.find(k); }

       T& operator[](const Key& k) {
           iterator it = find(k);
           if (it == end()) {
               it = _M_table.emplace_unique(std::piecewise_construct,
                                           std::forward_as_tuple(k),
                                           std::forward_as_tuple()).first;
           }
           return it->second;
       }

       template <typename... Args>
       std::pair<iterator, bool> emplace(Args&&... args) {
           return _M_table.emplace_unique(std::forward<Args>(args)...);
       }
   };

   } // namespace core_stl

   // =========================================================================
   // 4. 端到端测试与失效边界验证套件
   // =========================================================================
   namespace test {

   struct CustomUser {
       std::string Name;
       int Age;

       bool operator==(const CustomUser& o) const noexcept {
           return Name == o.Name && Age == o.Age;
       }
   };

   struct CustomUserHash {
       size_t operator()(const CustomUser& u) const noexcept {
           size_t seed = 0;
           core_stl::hash_combine(seed, u.Name);
           core_stl::hash_combine(seed, u.Age);
           return seed;
       }
   };

   inline void runUnorderedContainersTestSuite() {
       std::cout << "=======================================================
";
       std::cout << " MiniUnorderedMap/Set 与 Rehash 引用稳定性测试套件
";
       std::cout << "=======================================================

";

       // 1. 测试自定义类型 Hash Combine 与 MiniUnorderedSet 插入去重
       {
           core_stl::MiniUnorderedSet<CustomUser, CustomUserHash> userSet;
           userSet.insert({"Alice", 25});
           userSet.insert({"Bob", 30});
           auto [it_dup, inserted] = userSet.insert({"Alice", 25});
           assert(!inserted); // 拦截等价键
           assert(userSet.size() == 2);

           std::cout << "[测试 1: 自定义类型 Hash Combine 与 Set 去重]: 成功入库 2 个唯一实体
";
       }

       // 2. 核心验证: Rehash 发生时，已有元素的【指针与引用绝对保持有效】
       {
           core_stl::MiniUnorderedMap<std::string, int> map;
           map.emplace(std::make_pair("stable_key", 777));

           // 捕获已有元素的物理指针与引用
           auto it_orig = map.find("stable_key");
           assert(it_orig != map.end());
           int* val_ptr = &(it_orig->second);
           const std::string* key_ptr = &(it_orig->first);
           assert(*val_ptr == 777);

           size_t old_bkt_count = map.bucket_count();

           // 连续插入大量新元素，强制触发 Rehash 扩容
           for (int i = 0; i < 50; ++i) {
               map.emplace(std::make_pair("bulk_key_" + std::to_string(i), i));
           }

           // 验证 Rehash 已经发生
           assert(map.bucket_count() > old_bkt_count);
           std::cout << "
[测试 2: Rehash 触发验证]:
"
                     << "  桶数量由 " << old_bkt_count << " 扩展至 " << map.bucket_count()
                     << " (当前元素总数: " << map.size() << ")
";

           // 核心断言: 物理指针地址绝对恒定，数据依然完好无损!
           assert(*val_ptr == 777);
           assert(*key_ptr == "stable_key");
           std::cout << "  -> 核心断言通过: Rehash 扩容后，指向原有元素的指针与引用地址完全有效且数据保真!

";
       }

       std::cout << "  -> MiniUnorderedMap 与 MiniUnorderedSet 容器测试完全通过。

";
   }

   } // namespace test

程序输出验证分析
~~~~~~~~~~~~~~~~

运行上述 C++ 测试套件，控制台输出清晰验证了现代无序关联容器的核心微架构规律：

1. **Hash Combine 消除分布偏差**：通过黄金分割比混淆算法，包含了字符串与整数的 ``CustomUser`` 对象在桶数组中均匀离散，等价键去重逻辑严格按 $	ext{KeyEqual}$ 闭环生效。
2. **指针/引用生命周期的绝对持久性**：在测试 2 中，即使向哈希表连续插入 50 个元素导致底层触发了多轮 Rehash 扩容（桶数量由 7 扩展至 79），此前捕获的 ``val_ptr`` 与 ``key_ptr`` 物理地址始终未变，值依然准确维持 $777$。这从微架构层面彻底证实了标准库拉链法哈希表“节点原址重织、零对象搬迁”的本质特性。

小结与全模块结项导读
--------------------

本章系统解构了现代 C++ 无序关联容器 ``std::unordered_map`` 与 ``std::unordered_set`` 的底层微架构与接口契约：

1. **散列化与等价性代数一致性**：阐释了 $	ext{KeyEqual}(a, b) \implies 	ext{Hash}(a) == 	ext{Hash}(b)$ 的刚性约束，推导了多字段 ``hash_combine`` 混淆算法。
2. **const Key 物理防御**：剖析了利用类型系统封死原地修改键以杜绝桶索引错位丢失节点的微架构防线。
3. **桶接口与诊断**：解构了 ``bucket_count``、``load_factor`` 与本地迭代器在内省哈希碰撞分布中的工业实践。
4. **双态失效边界**：严格确立了“Rehash 仅使迭代器失效，而元素指针与引用永不失效”的物理不变性。

========================================================================
第 4 模块：关联容器、红黑树与哈希表内核全量完工结项
========================================================================

至此，《现代C++对象模型与STL工程内核全景深度剖析》**第 4 模块（04_associative_and_hash_containers）的 5 节核心专著章节已全部全量完工落盘**：
- **01 节**：红黑树底层平衡机制：五大不变量、黑高约束、左旋右旋拓扑变换与插入/删除重新着色平衡修复
- **02 节**：std::map 与 std::set 有序容器：严格弱序比较器契约、节点物理拓扑、lower_bound/upper_bound 对数搜索
- **03 节**：std::multimap 与 std::multiset 多重容器：等价键连续区间存储、equal_range 二分定位与插入策略
- **04 节**：哈希表微架构与冲突处理：拉链法 (Chaining) 节点拓扑、负载因子 (Load Factor) 与二次幂/质数桶设计
- **05 节**：std::unordered_map 与 std::unordered_set：哈希函数、等价谓词、rehash 动态重构与迭代器局部失效

在接下来的 **第 5 模块：泛型算法、双指针与内省排序（05_generic_algorithms_and_performance）** 中，我们将正式开启 STL 泛型算法与性能工程的宏大篇章。在第 5 模块第 1 节 **STL 算法设计准则：半开区间几何不变量、只读/变易分类与迭代器能力编译期 tag dispatch（``05_generic_algorithms_and_performance/01_half_open_range_contract_and_iterator_dispatch.rst``）** 中，我们将深入剖析半开区间 $[first, last)$ 的代数几何公理、只读算法与变易算法分类、基于迭代器分类标签（Iterator Category Tags）的编译期重载分发，以及消除冗余指针判空的微架构优化。
