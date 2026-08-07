第029章：Binary Search Algorithms
=================================

核心知识点
----------

* 二分算法依赖的是“相对当前比较表达式已经形成单调分区”的区间；通常来自按同一 comparator 排序的区间。
* ``binary_search`` 只回答是否存在比较等价元素，不返回位置；需要位置、插入点或重复范围时应直接使用边界算法。
* ``lower_bound`` 返回第一个“不排在目标之前”的位置，既是等价组左边界，也是保持有序时的最早插入点。
* ``upper_bound`` 返回第一个“排在目标之后”的位置，是等价组右边界后的 one-past 位置。
* ``equal_range`` 返回 ``[lower_bound, upper_bound)``；目标不存在时两个 iterator 相等并共同指向合法插入点。
* ``partition_point`` 是更一般的“true 前缀 / false 后缀”边界查找；二分搜索可以视为特定比较谓词上的分区点定位。
* comparator 定义等价关系：``!comp(a,b) && !comp(b,a)``。排序和查找阶段必须使用兼容的 comparator。
* 比较次数可以是对数级，但 forward/bidirectional iterator 寻找中点可能产生线性步进；复杂度不能只看比较次数。
* 对 ``map``、``set`` 等树形有序容器，应优先使用成员 ``lower_bound`` / ``upper_bound`` / ``equal_range``，因为成员函数能利用树结构完成对数级节点跳转。

关键路径
--------

1. 先验证区间是否对当前 comparator/谓词形成正确分区；排序阶段和查询阶段的比较规则必须一致。
2. 只需要存在性时用 ``binary_search``；需要左边界/插入点用 ``lower_bound``；需要右边界用 ``upper_bound``；需要完整重复组用 ``equal_range``。
3. ``lower_bound`` 追踪 ``comp(element, value)`` 的 true→false 边界；``upper_bound`` 追踪 ``comp(value, element)`` 的 false→true 边界。
4. 得到 ``[first,last)`` 后，可用距离计算重复数量；随机访问 iterator 的减法为常数时间，其他 iterator 需额外遍历。
5. 对树形容器先检查是否有等价成员函数，避免通用算法在节点迭代器上产生线性步进。

概念辨析
--------

* **binary_search 与 lower_bound**：前者只交付 bool；后者保留位置，通常信息量更高。
* **lower_bound 与 upper_bound**：左边界关注 ``element < value`` 何时停止；右边界关注 ``value < element`` 何时开始。
* **equal_range 与 find**：前者交付整个等价组；后者只定位一个元素。
* **有序与分区**：二分算法真正需要的是相对查询表达式的分区前提；完整排序是最常见的建立方式。
* **比较等价与对象相等**：二分算法使用 comparator 等价类，未参与 comparator 的字段不影响命中结果。
* **对数比较与对数总成本**：非随机访问 iterator 可能仍需要线性步进，因此要把比较和移动 iterator 分开估算。

本章结论
--------

二分算法的稳定判断顺序是“验证分区前提 → 选择存在性或边界结果 → 检查 comparator 方向 → 估算 iterator 步进成本 → 优先利用容器成员索引”。任何二分调用的正确性首先来自前置顺序关系，而不是函数名本身。