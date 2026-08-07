第006章：Iterator System
========================

核心知识点
----------

Iterator 是容器与算法之间的位置抽象。算法不需要知道元素存放在连续数组、链表节点、分段缓冲还是输入流中，只依赖 iterator 暴露的比较、递增、解引用、回退或随机跳转能力。

STL 传统算法普遍使用半开区间 ``[first, last)``。``first`` 指向第一个候选元素，``last`` 是尾后位置；空区间自然表示为 ``first == last``。尾后位置可比较、可作为停止条件，不能解引用。

Iterator 能力按可用操作逐级增强：output 负责写入；input 支持单趟读取；forward 支持多趟前向遍历；bidirectional 增加 ``--``；random access 增加常数级 ``+n``、``-n``、下标与距离计算；contiguous 再增加元素地址连续承诺。

Random access 与 contiguous 是不同概念。``deque`` 可随机访问，但常见实现使用分段存储；``vector`` 的 iterator 同时具备随机访问与连续存储语义。

``std::iterator_traits`` 为算法提供统一的 ``value_type``、``difference_type``、``reference``、``pointer`` 与 iterator category 查询入口。原生指针也通过 traits 特化进入同一套泛型算法体系。

Tag dispatch 是传统 STL 的编译期分派机制：算法从 traits 取得 category tag，再通过重载选择不同实现。C++20 之后 iterator concepts 用约束直接表达能力，但核心思想仍是“根据 iterator 能力选择合法且更高效的路径”。

Iterator adapter 改变位置操作的语义。``reverse_iterator`` 把正向区间映射成反向遍历；``back_insert_iterator`` 把 ``*out = value`` 转换为容器 ``push_back``；move iterator 把解引用结果转成可移动值类别。

关键路径
--------

普通顺序算法的最小路径是：

``取得 first/last → 检查 first != last → 解引用 *first → 使用元素 → ++first → 重复直到 first == last``。

判断算法需要什么 iterator 时直接看源码表达式：

``++it + *it`` 对应 input/forward 级能力；``--it`` 要求 bidirectional；``it + n``、``last - first``、``it[n]`` 要求 random access；地址连续算法还需要 contiguous 承诺。

Traits 分派路径是：

``Iterator 类型 → iterator_traits<Iterator> → iterator_category / concept → 编译期选择实现 → 生成针对该 iterator 的代码``。

``std::advance`` 是典型例子：输入 iterator 只能循环 ``++``；双向 iterator 可以根据正负距离 ``++/--``；随机访问 iterator 可以直接 ``it += n``。

``reverse_iterator`` 的关键关系是 ``r.base()`` 指向反向 iterator 当前元素的“正向后一位置”，因此反向区间 ``[rbegin, rend)`` 通常来自正向 ``[begin, end)`` 的 ``end`` 与 ``begin``。

Iterator 有效性必须与容器修改路径一起判断：容器结构修改 → 查看是否重分配、节点删除或位置移动 → 决定旧 iterator/reference/pointer 是否仍指向同一活对象。

概念辨析
--------

Iterator 不等于裸指针。指针是 contiguous iterator 的重要实例，但链表 iterator、流 iterator、插入 adapter 都可以表达位置而没有简单地址步进模型。

``end()`` 不等于最后一个元素。它是尾后位置；最后一个元素在非空双向/随机访问区间中通常由 ``--end()`` 或等价操作获得。

Random access 不等于连续存储。能常数时间跳转只说明位置运算能力；连续存储额外承诺相邻元素在地址上连续。

Output iterator 不一定指向已有元素。``back_inserter`` 的赋值操作会创建新元素，它更像“写入动作适配器”。

Iterator category/concept 不只是标签。它决定哪些表达式合法、算法复杂度能否成立，以及实现能否选择更高效路径。

Iterator 失效不等于 iterator 对象本身被销毁。旧 iterator 变量仍存在，但它所描述的位置关系已经失去合法语义。

本章结论
--------

读 STL iterator 代码时，先确认区间是否有效，再按源码实际使用的表达式判断能力层级，然后看 traits/concept 如何分派实现，最后结合容器修改规则判断 iterator 是否失效。算法只依赖位置接口，容器负责位置语义，这正是 STL 容器与算法能够解耦的核心。