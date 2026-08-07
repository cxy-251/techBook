第052章：Mini Deque
===================

核心知识点
----------

* deque 通过“控制数组 ``map_`` + 多个固定大小 block”实现分段连续存储，在两端增长和随机访问之间折中。
* ``map_`` 的元素是 block 指针；block 才保存元素槽位。控制数组扩展通常只搬 block 指针，不搬已有元素对象。
* 有效元素仍由半开区间 ``[begin_, end_)`` 描述；block 中区间外槽位只是原始存储。
* deque iterator 不能只保存一个元素指针，通常还需要当前 block 的 ``first/last`` 与 ``map_`` 中对应控制槽 ``node``。
* iterator 跨 block 时通过 ``node±1`` 切换 block，再更新 ``first/last/cur``。
* ``push_front/push_back`` 优先使用边界 block 的空槽；没有空槽时才申请新 block；控制数组端部不足时再扩展 ``map_``。
* 随机访问通过逻辑偏移计算目标 block 与块内 offset，复杂度仍为 O(1)，但常数通常高于 vector。
* 控制数组重分配可能使 iterator 中保存的 ``node`` 失效，即使元素本身没有搬迁。

关键路径
--------

1. 空 deque 初始化一块 block，并把 ``begin_`` 与 ``end_`` 放在合适的块内位置。
2. ``push_back`` 检查 ``end_`` 当前 block 是否有空槽；有则构造元素并推进 end。
3. 当前 block 满时，先确保 ``map_`` 后方有控制槽，再分配新 block，接入控制数组后构造元素。
4. ``push_front`` 对称地检查前端空槽或申请前置 block，再提交新的 begin。
5. ``pop`` 先销毁边界元素，再移动 begin/end；某块完全空闲且不再承担边界时可以释放。
6. ``operator[]`` 根据距 begin 的逻辑偏移计算目标 block 编号和块内位置，直接定位元素。

概念辨析
--------

* **deque vs vector**：vector 是单段连续存储；deque 是分段连续，元素整体通常无需因两端扩容而迁移。
* **deque vs list**：deque 仍支持 O(1) 随机访问；list 依赖节点逐步遍历。
* **map_ vs std::map**：deque 实现中的 map 是 block 指针控制数组，与有序关联容器 ``std::map`` 无关。
* **元素地址稳定 vs iterator 稳定**：map 扩展时元素可留在原 block，但 iterator 内部控制槽地址可能失效。
* **block 分配 vs 元素构造**：申请 block 只得到 raw storage，push 时才在具体槽位启动对象生命周期。

本章结论
--------

理解 deque 要始终分两级看位置：先定位 block，再定位块内槽位。两端操作的成本来自边界 block、block 分配和控制数组扩展三层状态；随机访问保持常数时间，是因为这两级定位都能用算术和固定次数指针访问完成。