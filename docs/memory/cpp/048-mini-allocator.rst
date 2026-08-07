第048章：Mini Allocator
=======================

核心知识点
----------

* allocator 把“原始存储管理”和“对象生命周期”拆开：``allocate/deallocate`` 管存储，``construct/destroy`` 管对象。
* ``allocate(n)`` 得到的是足以容纳 ``n`` 个 ``T`` 的未初始化存储，不代表其中已经存在 ``T`` 对象。
* ``deallocate`` 前必须先结束所有有效对象生命周期；未构造槽位不能执行析构。
* ``construct`` 在指定地址启动对象生命周期，现代实现可通过 ``std::construct_at``；``destroy`` 结束对象生命周期但不释放整块存储。
* 容器必须记录“已构造数量”，异常恢复时只能销毁已经成功构造的前缀。
* ``allocator_traits`` 是容器访问 allocator 的统一入口，负责类型萃取、allocate/deallocate、construct/destroy、rebind 与传播属性。
* 对齐、元素数量溢出、申请与释放协议匹配属于 allocator 自身必须维护的不变量。

关键路径
--------

1. 容器需要容量 ``n``，先通过 traits 调用 ``allocate`` 得到 raw storage。
2. 从首槽开始逐个 ``construct`` 元素，并推进“已构造尾指针”。
3. 若第 ``i`` 个构造失败，只逆序 ``destroy`` 前 ``i`` 个有效对象，再 ``deallocate`` 整块新存储。
4. 若全部构造成功，再销毁旧对象并释放旧存储，最后提交新指针和容量。
5. 容器析构时先销毁 ``[first,last)``，再释放 ``[first,cap)`` 对应的原始存储。

概念辨析
--------

* **存储 vs 对象**：有地址和空间不等于对象已存在；对象生命周期必须由构造动作启动。
* **destroy vs deallocate**：前者结束 ``T`` 的生命周期，后者归还字节存储，两者不能互相替代。
* **capacity vs size**：capacity 表示可放对象的槽位数，size 表示当前有效对象数。
* **allocator vs allocator_traits**：allocator 提供策略，traits 给容器提供稳定统一接口并补齐默认行为。
* **rebind**：节点容器拿到 ``Alloc<T>`` 后通常需要把同一分配策略重新绑定到内部 node 类型。

本章结论
--------

实现 allocator 时必须始终按“申请原始存储 → 构造对象 → 销毁对象 → 释放存储”理解生命周期。容器异常安全的基础不是某个特殊语法，而是准确记录哪些槽位已经成为有效对象，并在最终成功之前不提前提交新状态。