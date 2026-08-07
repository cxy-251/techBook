第019章：Hash Table Foundations
===============================

核心知识点
----------

- 哈希表把 ``key`` 先映射成 hash value，再压缩到 bucket index；bucket 只是候选集合入口，真正的键等价仍由 ``key_equal`` 判断。
- 正确性约束是：若 ``key_equal(a, b)`` 为真，则 ``hash(a) == hash(b)`` 必须成立；hash 分布质量影响性能，hash/equality 不一致会破坏查找语义。
- STL ``unordered_*`` 的常见实现模型是 ``bucket array + node chain``：bucket 数组负责一级定位，节点链负责处理冲突；标准只规定接口与复杂度，不强制内部布局。
- collision 表示多个 key 落入同一 bucket。chaining 通过节点链处理冲突；open addressing 通过探测槽位处理冲突，两者在局部性、删除、扩容和位置稳定性上不同。
- ``load_factor = size / bucket_count`` 表示平均 bucket 负载；``max_load_factor`` 控制容器希望维持的负载上界。
- ``reserve(n)`` 面向“预期元素数量”，``rehash(n)`` 面向“bucket 数量下限”。二者最终都会影响 bucket array，并可能触发已有元素重新分桶。
- rehash 通常只重建 bucket 组织和节点链接，不必重新构造元素对象；但所有依赖 bucket 遍历状态的 iterator 会失效。
- 哈希表查找、插入、删除的平均复杂度接近 ``O(1)``，前提是 hash 分布合理且负载受控；大量碰撞时最坏可退化到 ``O(n)``。
- ``std::hash`` 提供标准 hash 入口，但普通标准无序容器没有针对敌意输入的抗碰撞安全保证；外部不可信 key 需要单独评估 hash-flooding 风险。

关键路径
--------

1. 查找 ``key``：调用 ``Hash(key)`` 得到 hash value。
2. 根据当前 ``bucket_count`` 将 hash value 映射到 bucket index。
3. 进入对应 bucket 的候选节点集合。
4. 对候选节点逐个调用 ``KeyEqual(node_key, key)``。
5. 命中则返回元素位置；扫描结束仍未命中则返回 ``end()``。
6. 插入新 key 时，在未命中路径上分配并构造新节点，再链接到目标 bucket。
7. 插入后更新 ``size`` 与负载状态；若超过策略边界，则分配新的 bucket array。
8. rehash 遍历已有节点，按新的 bucket 数重新计算或使用缓存 hash 重新定位 bucket，再重建 bucket 链接。
9. 删除元素时，先在 bucket 链中摘除节点，再结束元素生命周期并释放节点存储。
10. 批量构建哈希表时，先 ``reserve``，可以减少中间 rehash 次数和 iterator 失效窗口。

概念辨析
--------

- **hash value 与 bucket index**：hash value 是 ``Hash`` 的输出；bucket index 是结合当前 bucket 数量后的定位结果。bucket 数变化后，同一 hash value 可以落入不同 bucket。
- **hash 与 equality**：hash 用于缩小候选范围，equality 用于确认语义等价；hash 相同不代表 key 相等。
- **collision 与错误**：不同 key 发生 collision 是正常现象，只会增加候选扫描；等价 key 得到不同 hash 才属于设计错误。
- **chaining 与 open addressing**：chaining 使用独立节点和链；open addressing 把元素放在槽位中并使用 probe sequence。标准 ``unordered_*`` 的源码阅读通常更接近前者。
- **reserve 与 rehash**：``reserve`` 以元素规模表达容量意图；``rehash`` 直接对 bucket 数量提出要求。
- **iterator 与 reference/pointer**：rehash 会使 iterator 失效；节点式实现下，未被删除元素的 reference 和 pointer 通常保持有效。
- **平均 O(1) 与最坏 O(n)**：平均复杂度来自负载和分布假设，不是无条件保证。高碰撞、热点 key 或恶意输入都可能破坏平均路径。

本章结论
--------

哈希表的稳定模型是 ``key -> hash value -> bucket -> key_equal -> node``。容量管理围绕 ``bucket_count``、``load_factor``、``max_load_factor``、``reserve`` 和 ``rehash`` 展开；性能判断必须同时观察 hash 质量与 bucket 负载。源码阅读时先找 bucket array、node、Hash、KeyEqual 和 rehash 路径，再判断 iterator 失效与最坏复杂度，能够覆盖绝大多数 ``unordered_*`` 实现问题。
