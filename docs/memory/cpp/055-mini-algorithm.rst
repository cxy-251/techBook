第055章：Mini Algorithm
=======================

核心知识点
----------

* STL 算法的基本接口是半开区间 ``[first,last)`` 加 iterator；容器提供存储，算法只依赖位置操作和元素表达式。
* ``find`` 只需要 input iterator：比较 ``first!=last``、解引用、递增，并返回首个命中位置或 ``last``。
* ``copy`` 在已有目标对象上执行逐元素拷贝赋值，不负责分配空间，也不负责在 raw storage 上构造对象。
* ``move`` 算法把源元素作为右值交给目标赋值；源对象生命周期仍然存在，只进入 moved-from 状态。
* ``copy/move`` 的重叠方向必须匹配读写顺序；向右搬移应使用 backward 版本，避免覆盖尚未读取的源元素。
* ``lower_bound`` 的前提是区间按 comparator 分区；返回第一个不满足 ``comp(element,value)`` 的位置。
* forward iterator 版本的 lower_bound 比较次数可保持 O(log n)，但 ``distance/advance`` 可能产生 O(n) iterator 推进；随机访问 iterator 才有完整对数级位置移动成本。
* 排序算法需要更强 iterator 和比较器契约；比较器必须形成严格弱序。
* tag dispatch 让 ``iterator_category`` 参与编译期实现选择，使同一个算法接口针对不同 iterator 能力走不同路径。

关键路径
--------

1. 算法先建立半开区间边界，任何循环都在 ``first==last`` 前停止，绝不解引用 ``last``。
2. ``find`` 逐位置测试谓词或相等关系，命中立即返回当前 iterator。
3. ``copy`` 读取 ``*first`` 写入 ``*d_first``，同步推进输入与输出位置；返回最终输出尾位置。
4. ``move`` 与 copy 结构相同，但写入表达式改为 ``*d_first = std::move(*first)``。
5. ``lower_bound`` 用 ``first + count`` 描述剩余候选区间，每轮检查中点并排除一半逻辑区间。
6. 算法需要距离或跳转时读取 iterator category；random access 直接算术跳转，低能力 iterator 逐步推进。
7. 调用算法后若随后修改容器结构，必须重新检查算法返回 iterator 的失效规则。

概念辨析
--------

* **算法 ``move`` vs ``std::move(expr)``**：前者遍历区间并执行移动赋值，后者只是把单个表达式转换为右值类别。
* **copy vs uninitialized_copy**：copy 给已有对象赋值；uninitialized_copy 在原始存储中构造新对象。
* **lower_bound vs binary_search**：lower_bound 返回位置，即使目标不存在也有意义；binary_search 只回答是否存在等价元素。
* **比较次数 vs iterator 移动次数**：forward iterator 上 lower_bound 可以少比较，但寻找中点仍可能线性推进。
* **算法复杂度 vs 容器复杂度**：同一算法在不同 iterator 上的推进成本不同，不能只看算法名判断实际成本。

本章结论
--------

Mini Algorithm 把 STL 的核心模式压缩为“区间 + iterator + callable”。阅读任何算法实现时，先确认区间和 iterator 能力，再看元素读写与比较表达式，最后核对返回位置、复杂度、重叠和失效边界；容器类型本身通常不应进入算法核心。