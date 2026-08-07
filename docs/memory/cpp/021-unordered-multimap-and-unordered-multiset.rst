第021章：Unordered Multimap and Unordered Multiset
==================================================

核心知识点
----------

- ``std::unordered_multimap<Key, T>`` 允许同一等价 key 对应多份 mapped value；``std::unordered_multiset<Key>`` 允许同一等价 key 出现多次。
- multi 容器与 unique unordered 容器共享 ``Hash -> bucket -> KeyEqual`` 定位模型，差别在于等价 key 已存在时仍然插入新节点。
- duplicate key 的“重复”由 ``key_equal`` 定义，不由对象地址、插入顺序或单独的 ``operator==`` 之外规则决定；``Hash`` 必须与这套等价关系一致。
- ``unordered_multimap`` 的元素类型仍是 ``pair<const Key, T>``；key 参与 bucket 身份，mapped value 不参与定位，因此同 key 组内可以保存不同业务值。
- 等价 key 的元素在容器迭代顺序中形成连续子范围，``equal_range(key)`` 返回这组元素的半开区间 ``[first, last)``。
- ``find(key)`` 只需要返回某个等价元素，``count(key)`` 返回数量，``equal_range(key)`` 才是完整读取或批量处理重复键组的主要接口。
- ``erase(key)`` 会删除该 key 的全部等价元素；只删除组内某一条记录时，应拿到 ``equal_range`` 后按 iterator 精确擦除。
- multi 容器插入返回新元素 iterator，不需要 unique 容器中的 ``bool inserted``，因为等价 key 的存在不会让插入失败。
- 性能仍取决于 bucket 分布和负载，同时要额外观察“热点 key 的组长度”：即使 hash 定位是平均常数，消费某个有 ``K`` 条记录的等价组也至少需要 ``O(K)``。
- 纯频次统计通常使用 ``unordered_map<Key, std::size_t>`` 更直接；需要保留每次重复事件本身时，``unordered_multiset`` 才表达真实数据模型。

关键路径
--------

1. 插入 ``(key, value)`` 时计算 ``Hash(key)`` 并定位 bucket。
2. 在 bucket 中通过 ``KeyEqual`` 查找已有等价 key 组。
3. 无论等价组是否存在，multi 容器都构造新的独立 node。
4. 将新 node 链接到对应 bucket，并保证等价 key 在迭代语义上构成连续子范围。
5. 更新 ``size``，必要时根据 load policy 触发 rehash。
6. ``equal_range(key)`` 先完成 hash/bucket 定位，再找到该等价组的起点和组后第一个位置。
7. 遍历 ``[first, last)`` 即可读取该 key 的所有记录；成本与组内元素数量成正比。
8. ``count(key)`` 本质上需要确定并统计等价组长度。
9. ``erase(key)`` 定位等价组后删除其中全部节点；``erase(iterator)`` 只删除指定节点。
10. rehash 会重建 bucket 组织并使 iterator 失效，但未被删除元素的 reference/pointer 仍按节点式稳定性规则判断。

概念辨析
--------

- **unordered_multimap 与 unordered_map<Key, vector<T>>**：前者每个重复值是独立节点，天然支持逐元素插入/删除；后者一个 key 对应一个聚合 value，更适合整组一起管理、排序或紧凑存储。
- **unordered_multiset 与频次表**：multiset 保存每次重复元素；``unordered_map<Key, count>`` 只保存聚合计数，空间和语义都不同。
- **find 与 equal_range**：``find`` 只保证给出一个命中位置；``equal_range`` 给出完整等价组边界。
- **count 与遍历成本**：定位 bucket 可以接近 ``O(1)``，但返回/统计 ``K`` 个重复元素不可避免地与 ``K`` 相关。
- **duplicate key 与 collision**：duplicate key 是 ``KeyEqual`` 判定等价的多个元素；collision 是不同 key 落在同一 bucket，两者不是同一概念。
- **组内连续与全局有序**：等价 key 组可连续遍历，不代表整个 unordered 容器存在业务顺序；rehash 后全局遍历顺序可以变化。
- **unique 与 multi 插入语义**：unique 容器需要报告“是否插入”；multi 容器允许重复，每次成功插入都新增元素。

本章结论
--------

unordered multi 容器的稳定模型是“哈希定位不变，唯一性约束取消”。同一 ``key_equal`` 等价类可以保存多份独立节点，完整读取依赖 ``equal_range``，精确删除依赖 iterator，整组删除可用 ``erase(key)``。选型时先确认业务是否真的需要保留每一份重复记录，再检查 hash/equality 一致性、热点 key 组长度、rehash 失效边界和内存形状。
