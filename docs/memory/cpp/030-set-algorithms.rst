第030章：Set Algorithms
=======================

核心知识点
----------

* STL set algorithms 处理两个按同一比较规则排序的区间，输入不要求来自 ``std::set``；vector、array、list 或其他有序 range 都可以参与。
* ``set_union`` 对每个等价组输出 ``max(count1, count2)`` 个元素；STL 的集合算法保留 multiset 式重复计数语义。
* ``set_intersection`` 输出两个区间共同元素，并按等价组取 ``min(count1, count2)``。
* ``set_difference(first1, first2)`` 有方向性，对每个等价组输出 ``max(count1-count2, 0)``。
* ``set_symmetric_difference`` 输出两侧出现次数差的绝对值，表达只存在于一侧的部分。
* ``includes`` 判断第二个有序区间是否被第一个区间覆盖，重复元素数量同样参与包含关系。
* ``merge`` 把两个有序区间合并成一个有序输出，同时保留所有输入元素；它和 ``set_union`` 的重复计数规则不同。
* 所有算法都依赖同一个 comparator 的顺序和等价定义；输入未排序或比较规则不一致会破坏算法前提。
* 输出 iterator 由调用者提供，目标容量和对象构造仍由输出策略负责；使用 ``back_inserter`` 可以把结果增长交给容器。
* 双指针同步扫描时每轮至少推进一个输入 iterator，因此核心比较/推进总量受 ``N1 + N2`` 约束。

关键路径
--------

1. 先验证两个输入区间都按同一 comparator 排序，并明确 comparator 定义的等价关系。
2. 根据业务需要选择并集、交集、左差集、对称差、包含判断或完整有序合并。
3. 对重复值先计算两侧等价组出现次数，再套用对应的 max/min/差值规则预测输出。
4. 准备输出位置：``set_union``、``symmetric_difference``、``merge`` 的安全上界可到 ``N1 + N2``；intersection 上界为 ``min(N1,N2)``；difference 上界为 ``N1``。
5. 扫描时只比较当前左右元素：左小推进左，右小推进右，等价时按具体算法决定输出与推进方式。
6. 返回后使用算法返回的输出尾 iterator 确定真实结果边界，并检查输出是否与输入发生危险重叠。

概念辨析
--------

* **set algorithm 与 std::set**：前者是对有序 range 的非成员算法，后者是维护有序唯一键的容器。
* **set_union 与 merge**：union 对重复组取较大次数；merge 保留两边全部次数。
* **difference 与 symmetric_difference**：difference 有左右方向；symmetric difference 对称保留两侧不共同的部分。
* **数学集合与 STL multiset 语义**：STL 算法不会自动把重复值压成一个，重复次数参与结果。
* **operator== 与比较等价**：集合算法的“相同”来自 comparator 等价类，不要求对象完整相等。
* **输出空间与算法本身**：算法负责写值，目标容器是否扩容、分配和构造由 output iterator 语义决定。

本章结论
--------

使用集合算法时固定按“排序与 comparator → 重复计数语义 → 输出容量 → 输入输出重叠 → 返回尾位置”分析。它们本质上是两个有序区间的线性同步扫描，正确性完全建立在统一的顺序前提上。