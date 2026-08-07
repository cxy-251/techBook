第074章：Immortal Objects, Memory Model, and Free-Threaded Python
=================================================================

核心知识点
----------

* free-threaded CPython 把并发问题从“是否持有一把全局 GIL”下沉到对象生命周期、引用计数、容器内部同步、GC、allocator 和 C API 边界。
* PEP 683 的 immortal objects 用于极少量进程级常驻对象。它们被运行时视为不会通过普通引用计数归零析构，因此 ``INCREF/DECREF`` 可跳过实际计数字段写入。
* immortalization 的主要收益不是改变 Python 对象语义，而是减少多个 CPU core 围绕 ``None``、布尔值、小整数、部分 interned string、静态类型等热点对象头部的写竞争。
* free-threaded 构建不能简单把所有引用计数操作都变成重型原子操作，否则会把高频临时引用成本放大。运行时因此结合 immortalization、biased/local/shared reference counting、deferred 策略等降低共享写入。
* 生命周期安全、容器结构安全和业务一致性是三层不同问题：引用计数保证对象不被过早释放；容器内部同步保证 list/dict 等结构不损坏；应用层锁保护跨多个步骤或对象的业务不变量。
* free-threaded CPython 需要在对象附近保存更多并发状态，例如 owner/thread 信息、局部与共享引用计数、锁或状态位、GC 相关信息。具体字段是版本敏感实现细节。
* 内建容器的内部保护不等于“多步 Python 逻辑原子”。例如“检查 key 是否存在 → 计算 → 写入”仍需显式同步或状态分区。
* borrowed reference 在真正并行修改下风险更高。需要跨越可能修改容器或执行用户代码的边界时，应优先获取 strong reference；新 C API 也逐步提供返回强引用的替代入口。
* free-threaded 模式下，C 扩展必须重新审视所有依赖 GIL 的隐式前提：静态全局状态、直接结构体字段访问、borrowed reference、非线程安全 native 库、跨对象复合操作都需要显式边界。
* 性能瓶颈会从“一把全局 GIL”迁移到局部锁、原子引用计数、cache-line 竞争和共享对象热点。减少共享写入、线程局部分区再合并通常比让所有线程争抢同一对象更重要。

关键路径
--------

.. code-block:: text

   thread accesses PyObject
          ↓
   lifetime strategy
      ├─ immortal object → skip ordinary refcount mutation
      ├─ owning/local path → low-cost local accounting
      └─ shared path → synchronized/shared accounting
          ↓
   mutable object access ?
      ├─ no  → read/use object
      └─ yes → object/container synchronization
          ↓
   multi-step business invariant ?
      ├─ no  → operation completes
      └─ yes → application lock / ownership partition

读一段 free-threaded C 扩展时，按下面顺序检查：

#. 当前 ``PyObject *`` 的 strong/borrowed ownership 是什么。
#. 对象是否可能被其它线程同时访问或修改。
#. 当前 API 是否只保证对象存活，还是同时保证结构状态。
#. 是否直接读取 CPython 内部字段或依赖历史 GIL 保护。
#. 多步操作是否需要扩展自己的锁、critical section 或线程局部分区。

概念辨析
--------

**immortal object 与永久业务对象**
   immortal 是 CPython 运行时内部生命周期策略，不是用户代码给普通对象设置的“永不释放”属性。

**atomic refcount 与线程安全对象**
   引用计数同步只保护生命周期。对象内部字段、业务状态和多步逻辑仍可能发生竞态。

**容器内部锁与事务原子性**
   list/dict 内部锁的目标是保证结构完整；它不自动把多个容器操作组合成业务事务。

**free-threaded 与完全无锁**
   free-threaded 去掉的是单一全局序列化闸口，运行时反而需要更多局部锁、原子状态和所有权规则。

**borrowed reference 与 strong reference**
   borrowed reference 的有效期依赖提供方；strong reference 显式延长对象生命周期，更适合跨越并发修改或可重入调用边界。

本章结论
--------

free-threaded CPython 的核心不是“删除 GIL”四个字，而是把过去由 GIL 隐式承担的安全责任拆到对象生命周期、引用计数、容器锁、GC、allocator 和扩展边界。正确分析顺序应始终是：对象是否活着 → 内部结构是否安全 → 业务状态是否一致。并行能力提高的同时，同步责任变得更局部、更显式。
