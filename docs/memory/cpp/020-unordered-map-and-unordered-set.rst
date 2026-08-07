第020章：Unordered Map and Unordered Set
========================================

核心知识点
----------

- ``std::unordered_map<Key, T>`` 保存唯一 ``Key -> T`` 映射；``std::unordered_set<Key>`` 只保存唯一 key。两者共享同一套 hash table 定位与容量模型。
- ``unordered_map`` 的元素类型是 ``std::pair<const Key, T>``，``unordered_set`` 的元素本身就是 const key 语义；进入容器后不能通过普通元素访问修改 key，因为 bucket 定位依赖 key 的 hash/equality。
- 常见实现对象图是：容器对象保存 bucket array、size、hasher、key_equal、load policy；node 保存元素和冲突链链接。
- 查找路径固定为 ``Hash -> bucket -> KeyEqual``。hash 只把搜索缩小到 bucket，bucket 内仍要逐项比较等价性。
- unique 容器插入时必须先判断是否已有等价 key；存在则不新增元素，不存在才构造并链接新节点。
- ``operator[]`` 只存在于 map 类容器。key 缺席时它会插入新元素，并对 mapped value 做 value-initialize，因此它既是访问接口，也是潜在的结构修改接口。
- 只读存在性查询优先用 ``find`` / ``contains``；要求存在并希望缺失时报错时用 ``at``；写入或计数场景才适合 ``operator[]``。
- ``reserve`` / ``rehash`` 可能使 iterator 全部失效；普通插入只有在触发 rehash 时才导致全局 iterator 失效；erase 只使被删元素的位置对象失效。
- 节点式哈希表中，rehash 通常重组 bucket 关系而不移动元素对象，因此未被 erase 元素的 reference/pointer 通常比 iterator 更稳定。
- unordered 容器不提供 key 顺序、范围有序查询或稳定遍历顺序；需要 ``lower_bound``、按 key 排序遍历、前驱后继时，应回到 ordered associative containers。

关键路径
--------

1. ``find(key)`` 先计算 ``Hash(key)``。
2. 将 hash value 映射到目标 bucket。
3. 扫描 bucket 中的节点，并用 ``KeyEqual`` 判断是否等价。
4. 命中则返回 node iterator；未命中返回 ``end()``。
5. ``insert`` / ``emplace`` 在 unique 容器中先完成重复键判断；缺席时才新增节点并增加 ``size``。
6. ``unordered_map::operator[](key)`` 先走查找路径；命中则返回 ``mapped value`` 引用。
7. 若 key 缺席，``operator[]`` 构造 ``pair<const Key, T>``，其中 ``T`` 被 value-initialize，再返回 ``second`` 引用。
8. 插入后检查负载因子；若需要扩容，创建新的 bucket array 并执行 rehash。
9. rehash 后必须重新获取 iterator；保存的 reference/pointer 仍需按元素是否被 erase 判断。
10. ``erase(key)`` 先定位 bucket 和等价节点，再从链中摘除并销毁该唯一元素。

概念辨析
--------

- **unordered_map 与 unordered_set**：前者回答“key 对应什么值”，后者回答“key 是否存在”。
- **唯一性与 hash 相同**：唯一性由 ``KeyEqual`` 定义；两个不同 key 可以 hash 相同并同时存在，只要 equality 判定不等价。
- **key 不可修改与 mapped value 可修改**：key 决定节点 bucket 身份，mapped value 不参与定位，因此 ``it->second`` 可改，``it->first`` 不可原地改。
- **operator[] 与 find**：``find`` 不改变容器；``operator[]`` 在 key 缺席时会插入默认 mapped value，读路径误用会产生隐式状态变化。
- **reserve 与元素个数**：``reserve(n)`` 表示准备容纳约 ``n`` 个元素，并不保证 bucket_count 精确等于 ``n``。
- **unordered 与 ordered**：unordered 强调平均等值查询成本；ordered 强调顺序、范围和稳定的比较器序列。
- **iterator 稳定与对象稳定**：rehash 改变遍历结构，iterator 失效；元素节点本身通常保持，reference/pointer 更稳定。

本章结论
--------

``unordered_map`` / ``unordered_set`` 的核心是“唯一 key + hash bucket”。分析一次操作时，先确认 ``Hash`` 与 ``KeyEqual`` 是否一致，再沿 ``hash -> bucket -> equality`` 路径判断命中与插入；随后检查本次操作是否可能 rehash，以及手里保存的是 iterator 还是元素 reference/pointer。选型时，只做等值查询且不依赖 key 顺序时使用 unordered；需要排序、范围和前驱后继时使用 ordered 容器。
