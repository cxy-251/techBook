第049章：Mini Iterator
======================

核心知识点
----------

* iterator 同时承载三类信息：当前位置状态、可执行操作集合、供泛型算法读取的关联类型。
* ``iterator_traits`` 统一暴露 ``value_type``、``difference_type``、``pointer``、``reference`` 与 ``iterator_category``；原生指针依靠特化进入同一算法体系。
* 连续存储上的随机访问 iterator 可以压缩成一个 ``T*``，解引用、递增、偏移、相减与比较都映射为指针运算。
* ``iterator_category`` 必须真实反映实现能力；错误标成 random access 会让算法选择不存在或复杂度不成立的路径。
* ``reverse_iterator`` 保存底层 iterator，但 ``*r`` 对应 ``*(r.base()-1)``；``rbegin`` 通常由 ``end`` 构造，``rend`` 由 ``begin`` 构造。
* ``distance``、``advance`` 等基础算法可以读取 iterator category，通过 tag dispatch 选择线性推进或常数时间跳转。
* iterator 有效性依赖底层存储和结构；对象仍保存非空地址并不代表该位置仍有效。

关键路径
--------

1. 算法拿到 ``It`` 后通过 ``iterator_traits<It>`` 取得距离类型和能力标签。
2. 普通 ``vector_iterator`` 用当前指针实现 ``*``、``++``、``--``、``+=``、``[]`` 和 iterator 差值。
3. ``distance`` 对 random-access iterator 直接执行 ``last-first``，对低能力 iterator 逐步推进计数。
4. ``reverse_iterator`` 自增时让底层 iterator 递减；解引用时先复制 ``base``，再递减一格后解引用。
5. 容器发生重新分配或节点删除后，必须重新判断旧 iterator 是否仍指向有效位置。

概念辨析
--------

* **iterator vs pointer**：pointer 可以天然充当某些 iterator；iterator 是更广义的位置抽象，可以包装节点、分段存储或生成序列。
* **value_type vs reference**：前者表示元素值类型，后者表示解引用结果，代理 iterator 中二者可能完全不同。
* **iterator_category vs iterator_concept**：前者是传统 STL 分发入口；C++20 iterator concepts 能表达更精细的能力要求。
* **reverse ``base()`` vs 当前元素**：``base()`` 指向当前反向元素的后一位置，二者天然相差一格。
* **可比较 vs 可解引用**：``end`` 是合法位置，可比较和移动，但不能解引用。

本章结论
--------

iterator 的本质是“位置语义 + 能力契约”。实现时必须让运行时操作和编译期能力标签一致；算法只依赖 iterator 与 traits，不应读取容器内部结构。反向迭代和 tag dispatch 都是在这一抽象层上继续组合。