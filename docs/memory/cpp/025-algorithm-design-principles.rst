第025章：Algorithm Design Principles
====================================

核心知识点
----------

* STL algorithm 的核心抽象是 iterator range，传统接口通常使用半开区间 ``[first, last)``；``last`` 只表示停止位置，不能解引用。
* algorithm 不拥有容器存储。容器负责容量、对象生命周期与 iterator 失效；algorithm 通过 iterator 读取、写入、交换或移动元素。
* 算法能力由 iterator 能力决定：线性查询通常只需 input/forward iterator，双端重排需要 bidirectional iterator，``sort`` 与 heap algorithms 需要 random access iterator。
* predicate、operation、comparator 把用户语义注入通用循环；C++20 ranges 的 projection 进一步把“先取字段，再比较或判断”显式分离。
* output iterator 的语义必须单独检查：普通 iterator 表示覆盖已有对象，``back_inserter`` 等适配器把赋值转换成容器插入。
* 复杂度应按区间长度、比较次数、predicate 调用次数、移动/交换次数和 iterator 步进成本分别理解，而不只看一个 ``O(N)`` 标签。
* 修改型 algorithm 通常只改变 iterator 可见的元素值或顺序；容器长度、节点数量和存储结构仍由容器成员函数负责。

关键路径
--------

1. 先确定输入区间或 range，以及 ``first``、``last`` 是否属于同一合法范围。
2. 判断 algorithm 是只读查询、原地修改，还是生成输出；若有输出，确认目标 iterator 的写入语义与空间是否足够。
3. 根据算法内部需要的 ``*it``、``++it``、``--it``、``it + n``、交换等操作，确认 iterator category 满足要求。
4. 定位 predicate、comparator、operation、projection 的输入输出关系，确认它们满足算法要求并保持稳定语义。
5. 估算区间长度和用户可调用对象成本，再叠加容器分配、移动和 iterator 步进成本。
6. 算法返回后，根据容器规则重新判断 iterator、pointer、reference 的有效性；需要改变容器长度时再进入 ``erase``、``resize`` 等成员路径。

概念辨析
--------

* **algorithm 与 container**：algorithm 操作位置和值；container 管理存储、生命周期和结构。
* **range 与 container**：range 是可遍历边界，不等于拥有元素的容器；同一容器可以切出多个子 range。
* **iterator category 与容器类型**：算法依赖的是位置能力；容器类型只是产生这些 iterator 的一种来源。
* **predicate 与 projection**：predicate/comparator 决定判断关系；projection 先把元素映射到参与判断的键。
* **普通输出 iterator 与 inserter**：前者要求目标位置已有对象，后者可通过容器接口创建新对象。
* **值修改与结构修改**：``remove_if`` 可以压缩值却不缩短 vector；真正结束尾部对象生命周期的是后续 ``erase``。

本章结论
--------

阅读或选择 STL algorithm 时，固定按“区间 → 读写形态 → iterator 能力 → 可调用对象 → 复杂度 → 容器失效边界”分析。algorithm 的泛型能力来自它只依赖位置协议和操作契约；所有权、容量与对象生命周期始终留在容器一侧。