第007章：Allocator System
=========================

核心知识点
----------

Allocator 把“容器如何取得和归还存储”从容器结构逻辑中拆出来。``vector``、``list``、``map`` 都需要创建和销毁元素，但连续块、链表节点和树节点的分配单位不同；allocator 提供统一策略入口，容器继续负责结构不变量、元素生命周期、异常安全和 iterator 规则。

``allocate(n)`` 取得足以容纳 ``n`` 个目标对象的原始存储；它不代表这些对象已经构造。对象生命周期由 ``allocator_traits::construct``、``std::construct_at`` 等路径开始，由 ``destroy`` / ``destroy_at`` 结束，最后再 ``deallocate`` 归还存储。

``std::allocator_traits<Alloc>`` 是标准库访问 allocator 的统一入口。它提供 pointer、size_type、difference_type 等类型查询，统一 allocate/deallocate/construct/destroy，并通过 ``rebind_alloc`` 把用户元素 allocator 改绑到容器内部节点类型。

节点式容器通常真正分配的是内部 node，而非裸 ``T``。例如 ``list<T, Alloc>`` 会把 ``Alloc`` rebind 成 ``NodeAlloc``，节点中同时保存链接字段和 ``T`` 对象。

Allocator 可以带状态。容器复制、移动和 swap 时，allocator 状态是否跟随容器传播由 ``propagate_on_container_copy_assignment``、``propagate_on_container_move_assignment``、``propagate_on_container_swap`` 等 traits 决定；allocator 是否相等也会影响能否直接接管底层存储。

``std::pmr`` 将分配策略进一步推到运行时。``polymorphic_allocator`` 持有 ``memory_resource``，容器静态类型可以保持统一，而实际存储来源由 resource 对象决定。resource 的生命周期必须覆盖所有使用它分配存储的容器。

关键路径
--------

单个对象位置的 allocator 路径是：

``allocate → 原始存储 → construct → 活对象 → destroy → 原始存储 → deallocate``。

Vector 扩容时：

``allocator_traits::allocate(new_cap) → 在新块逐个 construct → 失败时 destroy 已构造前缀并 deallocate 新块 → 成功后 destroy 旧元素 → deallocate 旧块 → 提交新状态``。

节点容器创建节点的路径通常是：

``Alloc<T> → rebind_alloc<Node> → NodeTraits::allocate(1) → construct Node(links + T) → 接入链/树结构``。

删除则反向执行：

``先从结构摘除节点 → destroy Node/元素 → deallocate Node``。

Allocator propagation 判断路径是：

``发生 copy/move assignment 或 swap → 查询 propagate trait → 若不传播则比较 allocator → 判断能否直接转移存储 → 否则按目标 allocator 重新分配并迁移元素``。

PMR 路径是：

``pmr 容器 → polymorphic_allocator → memory_resource::allocate/deallocate → monotonic/pool/custom resource``。

它把内存策略从模板参数的具体 allocator 类型转成一个运行时多态资源接口。

概念辨析
--------

Allocator 不等于对象构造器。它首先是存储策略；构造/销毁属于对象生命周期层，标准库通过 allocator_traits 把两层协调起来。

``allocate(n)`` 不等于创建 ``n`` 个对象。它只取得 ``n`` 个槽位的原始存储。

``rebind`` 不等于类型转换。它是从“为 T 分配”的 allocator 家族得到“为内部 Node 分配”的对应 allocator 类型。

自定义 allocator 不只影响性能。它会进入容器类型、移动/复制语义、swap 合法性、资源生命周期和 ABI 设计。

PMR 不等于自动内存池。``memory_resource`` 是运行时策略接口；是否使用池、arena、单调增长还是其它机制由具体 resource 决定。

容器 allocator 相等不代表两个容器内容相等。它只表示两边存储策略是否被视为可互换/兼容，具体意义由 allocator 定义与标准要求决定。

本章结论
--------

读 allocator 相关源码时，先确认当前分配单位是元素还是内部节点，再区分原始存储与活对象，然后追踪 allocator_traits、rebind 与 propagation，最后判断具体内存资源策略。容器结构和 allocator 策略相互协作，但元素数量、异常回滚和结构提交始终由容器负责。