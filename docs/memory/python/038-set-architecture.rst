第038章：Set Architecture
==========================

核心知识点
----------

* ``set`` / ``frozenset`` 用哈希表表达“唯一元素集合”，核心能力是 membership、去重和集合运算。
* set 槽位保存元素引用和相关 hash，不保存 value；因此它可以看作只有 key 的哈希结构。
* 一次 ``x in s`` 通常经历 ``hash(x) → 初始槽位 → probe → hash 比较 → equality 比较``。命中必须满足 hash 候选一致并由 equality 确认相等。
* set 元素必须 hashable；相等对象必须具有相同 hash，且对象在集合存活期间参与 ``__hash__`` / ``__eq__`` 的状态应保持稳定。
* 哈希碰撞不影响集合正确性，只会延长 probe 链并增加 equality 调用。极端坏 hash 可以让 membership 退化到接近线性成本。
* CPython set 使用开放寻址类探测结构，删除后需要保留 dummy 状态，使已有 collision chain 的查找不会提前终止。
* resize 会在表过密或 dummy 过多时重新构建槽位，恢复足够空闲空间和较短 probe 路径；因此单次修改成本可能出现阶段性峰值。
* 并集、交集、差集、对称差集的底层稳定模型是“遍历元素 + 对另一集合做哈希 membership + 构造或更新结果”。
* ``set`` 是可变容器，自身不可哈希；``frozenset`` 内容固定，可以作为 dict key 或另一个 set 的元素。
* ``set`` 的语言语义不保证插入顺序，也不支持 indexing 和 slicing。当前某次运行观察到的迭代顺序不能作为协议依赖。
* hash randomization、表大小、插入删除历史、resize 都可能影响 set 的实际槽位和迭代顺序。
* list 适合保留顺序和重复元素；set 适合唯一性与高频 membership；dict 适合 key→value 映射。

关键路径
--------

Membership / insertion：

::

   element
      ↓
   hash(element)
      ↓
   compute initial slot
      ↓
   inspect slot
      ↓
   empty → miss / insertion point
   active entry → compare stored hash
      ↓
   hash match → equality
      ↓
   equal → hit / duplicate
   unequal → continue probing
      ↓
   dummy / collision → continue probe

删除与重建：

::

   remove element
       ↓
   locate active slot
       ↓
   mark slot as dummy
       ↓
   used decreases, historical probe path preserved
       ↓
   fill/dummy pressure grows
       ↓
   resize / rebuild table
       ↓
   reinsert active elements

集合运算：

::

   choose source elements
       ↓
   iterate source
       ↓
   hash membership test in other set
       ↓
   keep / discard according to union-intersection-difference rule
       ↓
   build result set

概念辨析
--------

* **唯一性与 hash**：hash 负责定位候选位置，equality 才决定“是不是同一个集合元素”。
* **collision 与 equality**：hash 相同不代表对象相等；collision 只是需要继续比较和探测。
* **set 与 dict**：两者都依赖 hash table；dict 保存 key-value，set 只关心元素是否存在。
* **set 与 frozenset**：set 可修改所以自身不具备稳定 hash；frozenset 内容固定，可以进入其它哈希容器。
* **unordered 与随机**：set 没有语言层顺序保证；具体顺序由当前实现状态决定，不等于每次迭代都会主动随机洗牌。
* **平均 O(1) 与最坏退化**：正常 hash 分布下 membership 平均接近常数；大量碰撞或昂贵 equality 会显著增加成本。
* **元素可变与容器可变**：set 本身可变不意味着元素可随意改变 hash 相关状态；元素的哈希身份必须稳定。

本章结论
--------

``set`` 可以压缩为“用 hash table 保存唯一 key，用 probe 处理冲突，用 equality 最终确认成员关系”。使用 set 时最重要的正确性约束不是“元素不可变”这个表面规则，而是元素在集合生命周期中保持稳定的 hash/equality 身份。性能判断则围绕 hash 分布、probe 长度、resize 和批量 membership 展开；顺序需求应交给 list、tuple 或有序映射处理。
