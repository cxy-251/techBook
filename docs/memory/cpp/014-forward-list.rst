第014章：Forward List
======================

核心知识点
----------

``std::forward_list`` 是单向节点链表。每个节点通常只保存元素和一个 ``next`` 指针，容器维护头前位置；它用更小的节点状态换取只能向前遍历的能力。

``before_begin()`` 是第一个真实元素之前的特殊位置。它让“在首元素前插入”和“删除首元素”都能统一成 after 操作：``push_front`` 可理解为在 before_begin 之后插入，``pop_front`` 可理解为删除 before_begin 之后的元素。

单向链表修改需要前驱节点。``insert_after(pos, value)`` 改写 ``pos`` 保存的 next 链接；``erase_after(pos)`` 删除的是 ``pos`` 后面的节点。接口使用“after”语义，是因为被删节点自己无法反向找到谁指向它。

forward_list iterator 满足 forward iterator：可以解引用、比较、递增并多趟遍历，但不能 ``--it``，也不能常数时间随机跳转。定位某个节点或它的前驱通常是 O(n)。

标准 ``forward_list`` 没有成员 ``size()``。需要长度时通常通过遍历计算，体现的是“保持单向链表最小状态，不额外维护长度字段”的设计取舍。

节点式结构使未被删除节点的地址和 iterator/reference 通常保持稳定；插入只增加局部链接，擦除只使目标节点对应位置失效。

相对 ``list``，forward_list 每节点少一个反向指针，空间更省；代价是无法反向遍历、删除当前节点时必须持有前驱、许多操作需要重新从头扫描。

关键路径
--------

最小节点模型：

``before_begin/sentinel → node(value,next) → node(value,next) → ... → null/end``。

插入路径：

``找到前驱 prev → allocate 新节点 → 构造 T → new.next = prev.next → prev.next = new → 提交完成``。

删除路径：

``给定 prev → erased = prev.next → prev.next = erased.next → destroy T → deallocate erased → 返回新的 prev.next``。

删除扫描中的稳定循环不变量是：

``prev 始终指向 cur 的前驱；若删除 cur，则 cur = erase_after(prev)；若保留 cur，则 prev = cur, ++cur``。

长度查询：

``begin → 连续 ++iterator 到 end → 计数``，因此是 O(n)。

若要删除“当前节点”，核心动作不是直接拿 ``cur`` 调 erase，而是确保同时维护 ``prev``，因为链接修改发生在前驱节点内部。

概念辨析
--------

``forward_list`` 不等于 ``list`` 的简化 API。它的节点模型真的少一个反向链接，因此 iterator 能力、删除接口和状态维护都不同。

``erase_after(pos)`` 删除的不是 ``pos``，而是 ``pos`` 后一个节点。

``before_begin`` 不等于 ``begin``。before_begin 是头前哨兵位置，不能当作元素解引用；begin 才指向第一个真实元素。

``没有 size()`` 不等于容器不知道结束位置。结束由链尾 null/end 表达，只是没有额外保存元素计数。

``局部修改 O(1)`` 不等于整体操作 O(1)。若调用前还需要线性寻找前驱，完整业务操作仍然是 O(n)。

``节点稳定`` 不等于缓存友好。独立节点分配和 pointer chasing 仍会牺牲连续访问局部性。

本章结论
--------

读 forward_list 时按“头前位置 → 当前前驱 → next 链接 → 节点生命周期 → iterator 能力 → 是否需要线性定位”判断。它适合单向扫描、已知前驱后的局部插入删除、对每节点空间敏感且不需要随机访问或反向遍历的场景。