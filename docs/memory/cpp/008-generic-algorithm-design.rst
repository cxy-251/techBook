第008章：Generic Algorithm Design
==================================

核心知识点
----------

STL 泛型算法通过 iterator/range 接口与容器解耦。算法只要求调用方提供一个合法区间和满足能力约束的位置对象，不直接依赖 ``vector``、``list`` 或其它容器内部结构。

半开区间 ``[first, last)`` 是传统 STL 算法的基础契约。调用方负责保证 ``first`` 与 ``last`` 描述同一序列中的合法范围，并保证算法执行期间这些 iterator 不被容器修改操作失效。

算法需求可以直接从其内部表达式反推：只使用 ``!=``、``++``、``*`` 的算法只需输入遍历能力；使用 ``--`` 需要双向能力；使用 ``+n``、``last-first``、``it[n]`` 需要随机访问能力。

Iterator 把算法的通用位置操作翻译为容器具体访问：vector iterator 常接近连续地址位置，list iterator 通常保存节点位置，输入流 iterator 将递增翻译为读取下一输入单元。算法源码无需知道这些差异。

``iterator_traits``、tag dispatch、concepts 和 policy object 都服务于编译期路径选择。Traits 读取类型能力，tag/concept 选择不同算法实现，predicate/comparator/projection 把用户行为注入算法骨架。

算法复杂度由两部分共同决定：算法执行多少次逻辑操作，以及 iterator 的单次位置移动成本。``lower_bound`` 的比较次数可以保持对数级，但若 iterator 只能线性前进，移动到各个中点仍可能累计为线性级 iterator 增量。

比较器和谓词不仅是可调用对象，还必须满足相应语义约束。排序比较器需要建立严格弱序；二分查找要求区间已经按对应规则分区/排序；破坏这些前提会使算法结果失去规范保证。

关键路径
--------

一个最小 ``find_if`` 路径是：

``first/last → first != last → pred(*first) → 命中则返回 first → 否则 ++first → 到 last 返回 last``。

容器与算法的解耦路径是：

``container.begin/end → iterator 表达位置 → algorithm 只调用 iterator 操作 → iterator 把操作翻译到底层数组/节点/流 → 返回位置给调用方``。

Traits 分派路径是：

``算法模板获得 It → iterator_traits/iterator concept → 获得 category/capability → 编译期选择实现 → 针对 It 实例化代码``。

例如 distance/advance 对随机访问 iterator 可直接使用减法或 ``+=``，对输入 iterator 只能逐步遍历。

用户策略注入路径是：

``algorithm skeleton → 调用 pred/comp/projection → 用户类型的 operator()/lambda → 返回判断结果 → 算法继续控制流``。

因此用户回调的异常、状态修改、比较一致性都会成为算法整体语义的一部分。

复杂度检查应按：

``算法规定的比较/赋值次数 → iterator 每次操作复杂度 → 元素操作复杂度 → 用户回调成本``。

不能只看算法名称就断言真实运行成本。

概念辨析
--------

泛型算法独立于容器，不代表独立于数据结构能力。iterator 所能提供的操作仍由底层结构决定。

``std::sort`` 与 ``list::sort`` 的区别不只是 API 风格。前者需要 random access iterator；链表缺少这种能力，所以成员 sort 利用节点重连完成排序。

算法复杂度中的 ``O(log N) comparisons`` 不一定等于整体 ``O(log N)`` 时间。若位置移动为线性成本，真实路径还要计入 iterator increments。

Predicate/comparator 不等于任意返回 bool 的函数。算法常对其稳定性、纯度或序关系有更强语义要求。

Iterator 失效是调用方与容器共同产生的边界，算法一般不会动态检查。算法执行期间修改容器导致失效后继续使用旧 iterator，会破坏区间契约。

C++20 ranges 改变接口形状，但没有改变核心模型：range 仍提供起点/终点，iterator/sentinel 仍定义位置能力，concept 仍决定算法合法路径。

本章结论
--------

读 STL 算法时，先确认区间合法性，再从源码操作反推 iterator 能力，然后看 traits/concepts 如何选择实现，再检查 comparator/predicate 的语义前提，最后把 iterator 成本与元素操作成本合并评估复杂度。STL 泛型算法的本质是静态多态下的“位置协议 + 用户策略 + 编译期分派”。