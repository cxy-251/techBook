第013章：List
==============

核心知识点
----------

``std::list`` 是节点式双向链表容器。每个元素位于独立节点中，节点通常保存 ``prev``、``next`` 和元素对象；容器本体维护哨兵或边界状态。顺序由链接关系决定，不依赖连续地址。

list iterator 通常只需要保存节点位置，``++it`` 沿 ``next`` 前进，``--it`` 沿 ``prev`` 后退，因此满足 bidirectional iterator；它不支持 O(1) 的 ``it+n`` 或下标访问。

任意已知位置插入和擦除的结构修改是 O(1)，因为只需局部重连指针。插入前先分配并构造新节点，构造成功后再接入链表；擦除先摘链，再销毁元素和释放节点。

节点独立存在，因此插入其他节点通常不会使已有 iterator/reference 失效；erase 只使指向被删除元素的位置对象失效。这个稳定性是 list 的主要能力之一。

``splice`` 是 list 的核心操作：把已有节点从源链表摘下并接入目标链表，不需要拷贝或移动元素对象。被迁移元素的地址、reference 和 iterator 仍指向同一个元素，只是所属容器发生变化；跨容器 splice 还需要满足 allocator 兼容前提。

``sort``、``merge``、``reverse``、``unique`` 等成员算法可以直接重连节点，避免把重对象来回移动。普通 ``std::sort`` 需要 random access iterator，因此不能直接用于 list。

list 的代价是每节点额外指针、频繁独立分配和较差 cache locality。若主要需求是随机访问和连续扫描，vector/deque 通常更合适。

关键路径
--------

节点插入路径：

``rebind allocator 到 node 类型 → allocate 节点存储 → 构造节点中的 T → 构造成功后 link_before(position,node) → 更新 size/边界``。

局部链接提交可以抽象为：

``node.prev = before → node.next = position → before.next = node → position.prev = node``。

擦除路径：

``保存目标节点 → target.prev.next = target.next → target.next.prev = target.prev → destroy T → deallocate node``。

``splice`` 单节点路径：

``从 source 局部摘下 node → 在 destination position 前接入 node → 不构造 T、不销毁 T、不改变元素地址``。

``sort`` 等链表算法的关键不是交换元素值，而是：

``比较节点中的值 → 调整节点顺序/合并链 → 保留元素对象本身``。

因此读 list 源码时，先找到哨兵和 node 基类，再找链接函数、allocator rebind、splice/merge 这类节点迁移路径。

概念辨析
--------

``list 插入 O(1)`` 不等于“按值找到插入点也是 O(1)”。常数复杂度成立的前提是位置 iterator 已经给出；定位位置通常仍需线性遍历。

``节点地址稳定`` 不等于 iterator 永远有效。erase 对应节点后，指向该元素的 iterator/reference 立即失效。

``splice`` 不等于 move assignment。splice 改的是节点所属链表和链接关系，通常不会调用元素的移动构造或移动赋值。

``list`` 不适合随机访问。双向 iterator 只能逐节点移动，距离 ``n`` 个节点通常需要 O(n)。

``节点容器`` 不等于高性能修改。若元素小、访问密集，节点分配与缓存失配的代价可能远高于 vector 搬移成本。

``std::list`` 不等于侵入式链表。标准 list 自己拥有节点并管理元素生命周期；侵入式链表把链接字段放进业务对象，生命周期由外部管理。

本章结论
--------

选择和阅读 list 时，核心顺序是“节点所有权 → prev/next 不变量 → allocator 与元素生命周期 → 局部摘链/插链 → iterator 稳定性 → cache 成本”。list 真正擅长的是已定位节点的稳定修改、splice 和链表级重排，而不是一般意义上的快速容器。