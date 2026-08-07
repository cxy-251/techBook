第038章：Iterator Traits
=======================

核心知识点
----------

* ``std::iterator_traits<Iter>`` 把 iterator 的关联类型统一暴露给泛型算法，避免算法直接依赖某个具体容器或 iterator 实现。
* 传统关联类型包括 ``value_type``、``difference_type``、``pointer``、``reference`` 和 ``iterator_category``；C++20 体系还引入 ``iterator_concept`` 与 ``iter_value_t``、``iter_reference_t`` 等入口。
* ``value_type`` 表示逻辑元素值类型，适合创建独立临时值；它与 ``decltype(*it)`` 或 ``reference`` 不一定相同。
* ``reference`` 表示解引用结果类型，可能是真实 ``T&``，也可能是 proxy reference；``std::vector<bool>`` 是典型代理访问场景。
* ``difference_type`` 表示两个位置之间的有符号距离；它与容器通常无符号的 ``size_type`` 语义不同。
* ``iterator_category`` 表达传统 iterator 能力层级，算法可据此选择线性推进、双向推进或随机访问路径。
* 原生指针没有嵌套类型，但 ``iterator_traits<T*>`` 为其补齐关联类型，因此数组和裸指针能直接进入 STL iterator 算法。
* Iterator 能力标签既是语义承诺，也影响复杂度。错误宣称随机访问会让算法使用不存在或成本不符的操作。
* Proxy iterator 要求算法区分“元素逻辑值”和“解引用访问对象”，不能默认 ``reference == value_type&``。

关键路径
--------

1. 泛型算法只接收 ``first``、``last`` 或某个 ``Iter`` 类型。
2. 通过 ``iterator_traits`` 获取元素值类型、距离类型、解引用类型与能力标签。
3. 需要独立保存元素时使用 ``value_type``；需要直接读写当前位置时按 ``reference`` / ``*it`` 的真实语义处理。
4. 需要移动位置或计算距离时使用 ``difference_type``，再根据 iterator category 判断允许的操作和复杂度。
5. 遇到原生指针或代理 iterator 时，优先检查 traits 特化和解引用语义，不从表面语法推断对象模型。

概念辨析
--------

* **value_type 与 reference**：前者是逻辑值对象类型；后者是解引用结果，可能是真实引用也可能是代理类型。
* **difference_type 与 size_type**：前者表达有方向的位置差，通常有符号；后者表达容器元素数量，通常无符号。
* **iterator_category 与 iterator_concept**：前者服务传统 LegacyIterator/tag-dispatch 模型；后者在 C++20 ranges 中表达更现代的能力约束。
* **random access 与 contiguous**：随机访问只保证常数时间位置跳转；contiguous 还要求元素地址具有连续存储关系。
* **原生指针与类 iterator**：接口形态不同，但 traits 把它们统一成可查询的 iterator 关联类型。

本章结论
--------

Iterator traits 的核心模型是“位置对象 → 关联类型 → 算法能力”。阅读 iterator 算法时，先区分值类型、解引用类型和距离类型，再看能力标签控制了哪些操作与复杂度；不要把真实引用、随机访问和连续存储混为一谈。