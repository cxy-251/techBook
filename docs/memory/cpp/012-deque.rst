第012章：Deque
===============

核心知识点
----------

``std::deque`` 用分段连续存储解决“两端高效增长 + O(1) 随机访问”的组合需求。它的逻辑序列连续，物理内存通常由多个 block 组成，外层控制数组保存 block 指针。

常见实现可抽象成四层：deque 容器对象、控制数组、多个 block、iterator。block 内元素连续，block 之间地址可以分散；控制数组负责把逻辑相邻 block 组织起来。

deque iterator 通常比 vector iterator 更复杂，需要同时知道当前元素位置、当前 block 边界以及当前 block 在控制数组中的槽位。``++it`` 在 block 内只移动当前指针，跨 block 时需要切换控制数组槽位并刷新边界。

随机访问仍为 O(1)，因为逻辑下标可以拆成“目标 block + block 内偏移”。但这不等于物理连续，不能把整个 deque 当成一个 C 数组交给要求连续 buffer 的接口。

``push_front``、``push_back`` 通常不搬移已有元素。端点 block 有空位时只在槽位构造对象并移动边界；block 满时新增 block；控制数组槽位不够时才需要扩展控制数组。

端点插入通常保持已有元素 reference/pointer 的有效性，但 iterator 失效规则更严格；中间插入删除会移动一侧元素，位置稳定性和复杂度都需要按具体操作判断。

deque 的局部性介于 vector 与 list 之间：block 内连续、跨 block 有一次额外间接访问。它适合频繁两端操作且仍需下标访问、不要求单块连续内存的场景。

关键路径
--------

尾部追加的普通路径：

``end 所在 block 有空槽 → 在 end 构造元素 → end 前进``。

尾部 block 已满时：

``检查控制数组尾侧槽位 → 必要时扩展控制数组 → allocate 新 block → 把 block 指针挂入控制数组 → 在新 block 构造元素 → 更新 end``。

头部追加与之对称：

``begin 前有空槽 → begin 回退 → 构造元素；否则新增头部 block → 更新 begin → 构造元素``。

随机访问路径：

``逻辑 index + begin 当前偏移 → 计算目标 block 编号 → 从控制数组取 block 地址 → 加 block 内偏移 → 定位元素``。

iterator 跨 block 前进：

``current++ → 若未到 block_end 则结束；若到边界 → block_slot++ → 读取下一个 block → 刷新 block_begin/block_end/current``。

中间插入删除通常选择移动距离较短的一侧，以减少元素移动数量，但整体复杂度仍为 O(n)。

概念辨析
--------

``deque`` 不等于“双向链表”。它是分段数组式容器，支持随机访问；list 才是节点双向链表。

``随机访问`` 不等于 ``contiguous``。deque 可以 O(1) 下标访问，但整个元素序列不保证单块地址连续。

``两端 O(1)`` 不等于绝对没有分配。端点 block 用完时需要新 block，控制数组用完时还可能扩展 block 指针表。

``元素地址稳定`` 不等于 iterator 稳定。deque 的 iterator 携带控制数组相关状态，端点操作可能让 iterator 失效，即使元素对象本身没有搬迁。

``deque`` 不等于 vector 的低性能替代。若主要是连续扫描和尾部追加，vector 通常更有缓存优势；若频繁头尾修改同时需要下标，deque 的结构更匹配。

本章结论
--------

分析 deque 时固定按“控制数组 → block → iterator → 操作发生在端点还是中间 → 是否新增 block/重排控制数组 → iterator/reference 失效”判断。它的本质是用一层索引和分段存储换取两端扩展能力，同时保留常数时间随机访问。