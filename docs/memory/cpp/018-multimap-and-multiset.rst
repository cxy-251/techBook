第018章：Multimap and Multiset
==============================

核心知识点
----------

* ``std::multimap`` 和 ``std::multiset`` 与 ``map`` / ``set`` 使用同一类有序关联模型，区别在于允许多个 key 在 ``Compare`` 意义下等价。
* ``multimap`` 表达一键多值，每个等价 key 对应独立节点和独立 mapped value；``multiset`` 表达可重复的有序元素集合。
* 等价关系仍由 ``!comp(a,b) && !comp(b,a)`` 定义，不依赖 ``operator==``。
* 等价 key 在全局有序遍历中形成连续区间；C++11 起，等价元素之间保持插入顺序。
* ``equal_range(key)`` 是 multi 容器读取完整重复键组的核心接口，返回 ``[lower_bound(key), upper_bound(key))``。
* ``find(key)`` 只返回某个等价元素，适合存在性或任一元素查询；``count(key)`` 给数量；完整分组读取、聚合或条件删除优先使用 ``equal_range``。
* ``multimap::emplace`` / ``multiset::emplace`` 插入等价 key 仍属于成功路径，所以通常直接返回新节点 iterator，而不是 ``iterator + bool``。
* 每个重复元素都是独立节点。按 iterator 删除只删除该节点；按 key 删除会删除该等价类中的全部元素。
* 节点式有序结构继续提供普通插入不使已有 iterator/reference 失效、删除只使被删节点位置失效的稳定性。
* ``multimap<Key,T>`` 与 ``map<Key, vector<T>>`` 表达不同：前者把每个值作为树节点并按 key 统一排序，后者把一个 key 映射到拥有一组值的聚合对象。

关键路径
--------

**重复键插入**

``准备 key/value -> Compare 沿树定位 -> 即使遇到等价 key 也继续确定等价区间插入位置 -> 分配并构造新节点 -> 链接 -> 红黑树修复 -> 返回新节点 iterator``。

multi 容器不会因为“已存在等价 key”拒绝插入；唯一性检查被移除，但全局排序和平衡修复仍保留。

**equal_range**

``lower_bound(key) -> 找到等价组左边界；upper_bound(key) -> 找到等价组右边界；遍历 [first,last) -> 处理全部等价节点``。

完整成本应拆成 ``O(log N)`` 的定位，加上 ``O(K)`` 的组内遍历。重复组很大时，真正成本通常落在 ``K``。

**条件删除组内节点**

``[first,last)=equal_range(key) -> 遍历 -> 命中业务条件时 erase(it) -> 使用返回的下一个 iterator 继续``。

这条路径只删除指定节点，不会误删同 key 下的其他业务值。

**按 key 删除**

``定位等价区间 -> 逐个摘除并销毁区间节点 -> 返回删除数量``。语义上是删除整个等价类。

概念辨析
--------

* **duplicate key vs comparator equivalent**：所谓“重复”以比较器等价为准，不一定等于业务层 ``==``。
* **multimap vs map<Key, vector<T>>**：前者每个 value 是独立树节点；后者一个树节点拥有整个 value 集合，组内结构由 ``vector`` 自己管理。
* **find vs equal_range**：``find`` 给一个位置；``equal_range`` 给完整等价组边界。
* **count vs 遍历**：``count`` 只回答数量；要访问 mapped value 仍要遍历等价区间。
* **erase(iterator) vs erase(key)**：前者删除单节点，后者删除整组等价 key。
* **组内顺序 vs key 顺序**：全局先按 key 排序，等价 key 组内再保持稳定插入顺序；mapped value 不参与 ``multimap`` 的 key 排序。
* **multi ordered vs unordered multi**：multi ordered 保留全局 key 顺序和范围查询；unordered multi 更偏向哈希等值查找。

本章结论
--------

multi 容器可以压缩成：``Compare 定义等价类 -> 所有元素仍作为独立有序树节点 -> 等价节点在遍历结果中形成连续区间 -> equal_range 负责完整分组访问 -> 删除语义按单节点或整组区分``。一键多值且需要全局排序、范围查询或稳定节点位置时，``multimap`` / ``multiset`` 是直接表达；若业务天然以“一个 key 拥有一个值集合”为整体管理单位，应评估 ``map<Key, container<T>>``。