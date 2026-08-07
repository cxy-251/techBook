第037章：List and Tuple Architecture
=====================================

核心知识点
----------

* CPython ``list`` 可以理解为“对象头 + 连续的 ``PyObject*`` 引用数组 + 当前长度 + 已分配容量”。连续的是元素引用槽位，元素对象本身通常分散在堆上。
* list 的索引读取可以直接按槽位偏移定位，因此随机索引访问成本低；中间插入、删除会移动后续引用槽位，成本随序列长度增长。
* ``append`` 依赖 over-allocation：扩容时申请略多于当前长度的容量，让后续若干次追加直接写入空槽位。
* 容量足够时 ``append`` 接近常数成本；容量不足时需要重新分配引用数组并搬移旧引用。多次追加综合来看是摊销常数成本，单次 append 仍可能很贵。
* ``tuple`` 是固定长度、固定槽位的序列。不可变约束作用于外层引用槽位，不会递归冻结槽位指向的对象。
* ``tuple(records)`` 或 tuple 切片创建新的外层容器并复制元素引用，因此属于浅层复制；元素对象仍可以被多个容器共享。
* tuple 只有在所有元素都可哈希时才可哈希。包含可变、不可哈希元素的 tuple 不能作为 dict key 或 set element。
* CPython 会对部分小 tuple 等高频对象使用 freelist 或专门复用策略。对象销毁后地址可能被新对象复用，所以历史 ``id()`` 不能作为长期唯一标识。
* list 与 tuple 的普通切片都会创建新容器并复制选中范围的引用，时间与空间成本随切片长度增长。
* list/tuple 的 memory locality 主要来自连续引用数组；对于 ``list[int]``，真正整数对象仍独立存在，因此它和原始连续数值数组的缓存行为不同。
* 选择 list 还是 tuple，首先看外层结构是否需要修改：需要增长、插入、删除、替换槽位用 list；固定记录、稳定返回值、可哈希复合 key 更适合 tuple。

关键路径
--------

List append：

::

   append(item)
       ↓
   inspect logical length and capacity
       ↓
   capacity available?
      ├─ yes → store item reference in next slot
      └─ no  → allocate larger reference array
                    ↓
                move old references
                    ↓
                store new item
       ↓
   update length

List / tuple slicing：

::

   source sequence[start:stop]
       ↓
   calculate slice range
       ↓
   allocate new outer container
       ↓
   copy selected object references
       ↓
   return new list / tuple

Tuple snapshot：

::

   source references
       ↓
   allocate fixed-size tuple
       ↓
   copy references into fixed slots
       ↓
   outer slots cannot be rebound
       ↓
   referenced mutable objects may still change

概念辨析
--------

* **length 与 capacity**：length 是 Python 可见元素数量；capacity 是 list 内部已申请槽位数量，属于 CPython 实现细节。
* **append O(1) 与 resize O(n)**：append 的摊销成本接近常数；触发扩容的具体一次操作需要搬移旧引用。
* **tuple 不可变与深度不可变**：tuple 固定的是外层槽位；元素对象若可变，其内部状态仍可变化。
* **切片与视图**：list/tuple 普通切片复制外层引用，不是共享槽位的 view；``memoryview`` 等二进制视图属于另一套模型。
* **浅复制与深复制**：切片、``list(x)``、``tuple(x)`` 通常创建新外层容器并共享元素；``copy.deepcopy`` 才尝试递归复制对象图。
* **连续数组与连续对象**：list 连续保存对象指针，不等于元素数据本身连续。
* **freelist 与对象存活**：freelist 复用的是已经销毁对象的内存，不表示旧对象仍然存在。

本章结论
--------

list 与 tuple 的共同底层模型是“连续对象引用槽位”，主要区别是 list 允许改变长度和槽位并通过 over-allocation 支撑增长，tuple 在创建后固定外层槽位。分析性能时先看是否发生扩容、槽位移动或切片复制；分析共享状态时先区分外层容器是否独立，再检查元素对象是否仍被多个容器共同引用。
