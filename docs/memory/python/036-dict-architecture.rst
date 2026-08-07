第036章：Dict Architecture
===========================

核心知识点
----------

* ``dict`` 是 CPython 中最核心的映射结构之一，模块全局变量、类与实例属性、关键字参数等大量机制都建立在字典或字典化结构之上。
* ``dict`` 的稳定运行模型是“hash table + compact entry storage”：索引区负责哈希定位，entry 区保存真实条目并维持插入顺序。
* Python 3.7 起，普通 ``dict`` 的插入顺序属于语言保证。更新已有 key 不改变位置；删除后重新插入会进入末尾。
* 一次 key 查找通常经历 ``hash(key) → 起始槽位 → probe → hash 比较 → equality 比较 → value``。hash 负责缩小候选范围，``__eq__`` 负责确认真正相等。
* 哈希碰撞不会破坏正确性，只会增加 probe 和 equality 成本。开放寻址结构需要 dummy 状态维持删除后的探测链。
* resize 会重建索引结构、清理无效槽位并恢复较短 probe 路径，因此普通查找平均接近常数时间，扩容本身仍是阶段性批量成本。
* ``str``、``bytes`` 等常见 key 使用进程级 hash randomization，主要用于降低可预测碰撞攻击风险；它不会改变 ``dict`` 的插入顺序语义。
* 普通字典通常使用 combined table：key 与 value 属于同一字典的条目结构。
* 实例属性字典可使用 PEP 412 key-sharing 设计：同类多个实例共享属性名 keys 结构，各实例分别保存自己的 values，降低大量同构实例的内存开销。
* namespace dict、普通业务 dict、实例属性 dict 的底层思路相似，上层语义不同：名字解析、属性访问和普通映射不能混为同一层。
* 字典 key 必须满足哈希不变量：对象相等时 hash 必须相等；作为 key 期间，参与 ``__hash__`` / ``__eq__`` 的状态应保持稳定。

关键路径
--------

普通查找路径：

::

   key
     ↓
   hash(key)
     ↓
   map hash to index slot
     ↓
   inspect slot state
     ↓
   empty → miss
   entry → compare stored hash
     ↓
   hash match → key equality
     ↓
   equal → return value
   unequal / collision → continue probe

插入与维护路径：

::

   new key/value
       ↓
   lookup existing key
       ↓
   exists → update value, keep order
   missing → choose insertion slot
       ↓
   append logical entry
       ↓
   update index table
       ↓
   load/dummy pressure reaches threshold
       ↓
   resize / rebuild indices

实例属性 key-sharing 路径：

::

   class instances share attribute-name layout
       ↓
   shared keys table
       ↓
   per-instance values array
       ↓
   attribute lookup locates shared key position
       ↓
   read value from current instance storage

概念辨析
--------

* **hash 与 equality**：hash 决定查找候选路径；equality 决定两个 key 是否真正相同。
* **ordered dict 与 hash table**：有序指迭代保持插入顺序；哈希表描述查找算法，两者同时成立。
* **index table 与 entry table**：index table 稀疏、服务定位；entry table 紧凑、保存真实条目和插入顺序。
* **combined table 与 split table**：combined 让单个字典自己保存 keys/values；split/key-sharing 让多个实例共享 keys、各自持有 values。
* **dummy 与 empty**：empty 表示探测可以结束；dummy 表示该位置曾有元素，查找仍需继续。
* **namespace 与普通 dict**：module globals 在实现上是字典，但名字解析还受编译器和执行器规则约束；不能把 namespace 语义简化成普通 ``d[key]``。
* **平均 O(1) 与绝对 O(1)**：正常 hash 分布下 lookup 平均接近常数；恶劣碰撞、昂贵 equality 和 resize 都会增加成本。

本章结论
--------

``dict`` 可以压缩为“hash 决定候选位置，probe 解决冲突，equality 确认 key，compact entries 保存真实条目并维持插入顺序”。排查字典行为时，先确认 key 的 hash/equality 契约，再追踪索引槽、碰撞和扩容；分析实例属性时，再加入 key-sharing 与 per-instance values。这样可以同时解释普通映射、namespace 和对象属性存储。
