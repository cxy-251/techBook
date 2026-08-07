第064章：dictobject.c
=====================

核心知识点
----------

* ``Objects/dictobject.c`` 实现 CPython ``dict`` 的核心：hash lookup、冲突探测、compact layout、插入顺序、删除标记、resize、split table 与对象属性字典优化。
* 现代 CPython dict 把“稀疏定位”和“紧凑内容”分开：``dk_indices`` 保存 slot → entry index，``dk_entries`` 紧凑保存 active entries。查找走 indices，迭代按 entries 顺序读取。
* 插入顺序是 Python 3.7+ 的语言保证；CPython 的 compact dict 布局让这项语义低成本实现。更新已有 key 不移动顺序，删除再插入会成为新的尾部 entry。
* dict 查找先计算 hash，再用 mask 得到初始 slot；冲突时沿 probe sequence 继续。hash 相同不代表 key 相同，最终仍需 equality 判断。
* empty slot 与 dummy slot 不同。empty 可以终止一次 miss 查找；dummy 表示这里曾经有 entry，探测必须继续，否则会截断冲突链。
* key 必须保持 hash/equality 契约：若 ``a == b``，它们应有相同 hash；已作为 key 的对象如果 hash 依赖可变状态，会破坏稳定查找。
* combined table 将 key/hash/value 放在 entries；split table 将共享 keys 与每实例 values 分离。大量同类实例的 ``__dict__`` 可以通过 key-sharing 减少重复属性名内存。
* key-sharing dict 与 ``__slots__`` 是不同优化：前者仍保留 ``__dict__`` 语义并共享 keys；后者把属性存储迁移到类型定义的 slot。
* resize 不只是“数组变大”。它还会重新建立 index table、缩短 probe chain、清理 dummy，并改变内部 table identity。
* ``LOAD_GLOBAL``、``LOAD_ATTR`` 等高频路径可缓存 dict keys/version/index 等事实。dict 或 namespace 发生相关结构修改时，guard 失败或 version invalidation 让执行器回到通用查找。

关键路径
--------

普通 dict lookup：

::

    d[key]
      ↓
    hash(key)
      ↓
    initial_index = hash & mask
      ↓
    dk_indices[slot]
      ├─ EMPTY → miss
      ├─ DUMMY → continue probe
      └─ entry index
            ↓
         hash match?
            ↓
         key identity/equality?
            ├─ yes → value
            └─ no  → continue probe

compact dict 结构：

::

    PyDictObject
      ├─ ma_keys
      │    ├─ dk_indices   → 稀疏 hash 定位
      │    └─ dk_entries   → 紧凑 entry / 插入顺序
      └─ ma_values         → split-table values（可选）

实例属性共享 keys：

::

    class instances
       ↓
    shared keys table: name / score / ...
       ↓
    instance A values[]
    instance B values[]
    instance C values[]

resize：

::

    insert
      ↓
    usable space insufficient / probe quality degraded
      ↓
    allocate/rebuild keys table
      ↓
    active entries reindexed
      ↓
    dummy 清理
      ↓
    后续查找使用新 mask / indices

概念辨析
--------

* dict 有插入顺序，不等于它是按 key 排序的数据结构；顺序来自插入历史。
* hash table 的 slot 与 entry 不是同一位置；index table 负责定位，entry table 保存内容与顺序。
* hash 相等只是冲突候选，不等于 key 相等。
* 删除 slot 变成 dummy，不等于删除 entry 后所有内部空间立即收缩。
* 平均 O(1) 是算法性质，真实成本还取决于 hash、equality、load factor、dummy 和 cache locality。
* 实例 ``__dict__`` 语义上是 dict，内部可能使用 split/key-sharing 形态；不能仅凭 Python 外观推断 C 布局。
* dict version/cache 是 CPython 优化层，不是 Python 语言可依赖的业务版本号。

本章结论
--------

``dictobject.c`` 的核心模型是“hash probe + compact entries + optional shared keys”。查找依赖 hash 与 equality，插入顺序依赖紧凑 entry 序列，实例属性通过 split table 复用 key 形状，resize 和 version invalidation 负责维持查找效率与缓存正确性。读任何 dict 性能或属性查找问题时，都应先区分 table 形态，再看 probe、删除痕迹和缓存前提。