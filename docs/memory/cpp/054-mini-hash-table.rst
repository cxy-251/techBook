第054章：Mini Hash Table
========================

核心知识点
----------

* 哈希表定位分两层：``Hash`` 把 key 转成哈希值，bucket policy 把哈希值映射到桶，再由 ``KeyEqual`` 在冲突集合中确认真正等价 key。
* separate chaining 的典型结构是 bucket array 保存链头，node 保存 ``value``、可选 cached hash 与 ``next``。
* 等价 key 必须满足相同 hash；hash 相同并不代表 key 等价，最终语义判断仍由 ``KeyEqual`` 完成。
* unique-key 表的 key 通常以 ``const Key`` 存在节点中，防止用户原地修改 key 后破坏 bucket 定位关系。
* ``insert`` 应先检查重复 key，再判断是否需要 rehash；rehash 后 bucket_count 改变，必须重新计算 bucket index。
* ``load_factor = size / bucket_count``；``max_load_factor`` 控制何时扩桶，决定平均冲突链长度与空间占用的折中。
* ``rehash`` 重建 bucket 到 node 的链接关系；节点对象地址可以保持不变，但遍历结构发生变化，因此 iterator 通常失效。
* 平均 O(1) 依赖 hash 分布；极端碰撞下查找、插入、删除可以退化到 O(n)。

关键路径
--------

1. ``find(key)`` 计算 ``hash(key)``，映射到 bucket index，只扫描该桶链表。
2. 扫描节点时可先比较 cached hash，再调用 ``KeyEqual`` 确认 key 等价。
3. ``insert`` 在旧表中先检查是否已有等价 key；随后根据 ``next_size`` 与最大负载因子决定是否 rehash。
4. 若发生 rehash，建立新的 bucket array，并按每个节点哈希值重新挂链。
5. 插入新节点时先完整构造 node，再把 ``node->next`` 指向旧链头，最后提交 ``bucket[index]=node`` 并递增 size。
6. ``erase`` 先找到目标及其前驱，断开链，再销毁节点并递减 size。
7. 析构或 clear 遍历所有 bucket 链，逐节点销毁释放，并清空入口。

概念辨析
--------

* **hash equality vs key equality**：hash 相等只是候选条件，真正等价由 ``KeyEqual`` 决定。
* **bucket_count vs size**：bucket 是索引槽数量，size 是元素节点数量，两者通过 load factor 联系。
* **rehash vs reserve**：rehash 直接要求桶数；reserve 通常根据期望元素数和最大负载因子推导所需桶数。
* **节点地址稳定 vs iterator 稳定**：rehash 可不搬 node 本体，但 iterator 的遍历顺序和 bucket 入口变化，因此 iterator 仍会失效。
* **平均复杂度 vs 最坏复杂度**：O(1) 是良好分布下的平均结果，不是哈希表无条件保证。

本章结论
--------

实现哈希表时应始终沿 ``key → hash → bucket → collision chain → KeyEqual`` 追踪查找路径。正确性取决于 Hash 与 KeyEqual 的一致契约，性能取决于分布质量和负载因子，rehash 则是用额外空间重新缩短冲突链的结构性操作。