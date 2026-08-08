第074章：Immortal Objects, Memory Model, and Free-Threaded Python
=================================================================

核心知识点
----------

* free-threaded CPython 把并发问题从“是否持有一把全局 GIL”下沉到对象生命周期、引用计数、容器内部同步、GC、allocator 和 C API 边界。
* PEP 683 定义的是 **immortal object 机制**：被运行时标记为 immortal 的对象不会通过普通引用计数归零进入析构路径，因此常规 ``INCREF/DECREF`` 可以避免真实计数字段写入。
* “哪些对象是 immortal”属于具体 CPython 版本与构建模式的实现策略，不能从 PEP 683 直接推导出一个跨版本固定对象集合。
* Python 3.13 的实验性 free-threaded build 为降低共享引用计数竞争，曾额外 immortalize module-level function、module、module dict、class/type 等较大范围对象，同时数字/字符串字面量和 interned string 也会进入 immortal 路径。
* Python 3.14 已显著收窄 **free-threaded 额外 immortalization**：官方文档当前把范围限制为 code constants（数字、字符串及由常量构成的 tuple）和 ``sys.intern()`` 得到的字符串。不能继续把 3.13 的 function/module/type 集合写成 3.14 现状。
* 这项 3.14 收窄不等于 ``None``、``True``、``False`` 或其它运行时对象一定变成 mortal；普通 CPython 自身仍可以因为 PEP 683 或静态对象策略让某些对象 immortal。判断具体对象应以当前 runtime 为准，而不是依赖固定名单。
* Python 3.14 提供 ``sys._is_immortal()`` 作为 CPython 专用观测入口，但官方明确不保证某对象在未来版本仍保持相同 immortal 状态。
* immortalization 的收益不是改变 Python 语义，而是减少多个 CPU core 对热门共享对象头部的写竞争和 cache-coherency 成本。
* free-threaded 构建不能简单把所有引用计数操作都变成重型原子操作，否则会放大高频临时引用成本；运行时因此结合 local/shared/biased reference counting、deferred counting、immortalization 与安全内存回收等机制。
* 生命周期安全、容器结构安全和业务一致性是三层不同问题：引用管理保证对象不被过早释放；容器内部同步保证 list/dict 等结构不损坏；应用层锁保护跨多个步骤或对象的业务不变量。
* free-threaded CPython 需要在对象附近保存更多并发状态，例如 owner/thread 信息、局部与共享引用计数、锁或状态位、GC 相关信息。具体字段是版本敏感实现细节。
* 内建容器的内部保护不等于“多步 Python 逻辑原子”。例如“检查 key 是否存在 → 计算 → 写入”仍需显式同步或状态分区。
* borrowed reference 在真正并行修改下风险更高。需要跨越可能修改容器或执行用户代码的边界时，应优先获取 strong reference；新 C API 逐步提供返回强引用的替代入口。
* free-threaded 模式下，C 扩展必须重新审视所有依赖 GIL 的隐式前提：静态全局状态、直接结构体字段访问、borrowed reference、非线程安全 native 库、跨对象复合操作都需要显式边界。
* 性能瓶颈会从“一把全局 GIL”迁移到局部锁、引用计数同步、cache-line 竞争和共享对象热点。减少共享写入、线程局部分区再合并通常比让所有线程争抢同一对象更重要。

关键路径
--------

判断 immortal 状态：

.. code-block:: text

   identify CPython version + build mode
          ↓
   distinguish PEP 683 mechanism
   from version-specific immortalization policy
          ↓
   need concrete answer for this object ?
      ├─ no  → treat immortality as implementation detail
      └─ yes → inspect current runtime / sys._is_immortal where available

Free-threaded 对象访问：

.. code-block:: text

   thread accesses PyObject
          ↓
   lifetime strategy
      ├─ immortal object → skip ordinary refcount mutation
      ├─ owning/local path → lower-cost local accounting
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
#. 是否错误依赖“某类对象一定 immortal”的版本假设。
#. 多步操作是否需要扩展自己的锁、critical section 或线程局部分区。

概念辨析
--------

**PEP 683 与 free-threaded immortalization policy**
   PEP 683 定义 immortal object 机制；free-threaded 3.13/3.14 决定额外把哪些对象放进该机制，两者不是同一层级。

**3.13 与 3.14 free-threaded policy**
   3.13 曾扩大 immortalization 以换取早期并行可行性；3.14 已把额外范围收窄，不能沿用 3.13 名单描述当前版本。

**immortal object 与永久业务对象**
   immortal 是 CPython 运行时内部生命周期策略，不是用户代码给普通对象设置的“永不释放”属性。

**immortal 与 immutable**
   immutable 描述 Python 层值是否能原地修改；immortal 描述 CPython 是否通过普通引用计数释放对象。

**atomic/shared refcount 与线程安全对象**
   引用计数同步只保护生命周期。对象内部字段、业务状态和多步逻辑仍可能发生竞态。

**容器内部锁与事务原子性**
   list/dict 内部锁的目标是保证结构完整；它不自动把多个容器操作组合成业务事务。

**borrowed reference 与 strong reference**
   borrowed reference 的有效期依赖提供方；strong reference 显式延长对象生命周期，更适合跨越并发修改或可重入调用边界。

本章结论
--------

Immortal object 必须分成“机制”和“版本策略”两层理解。PEP 683 提供避免普通 refcount 写入与归零析构的机制；free-threaded CPython 决定哪些对象在当前版本额外采用它。Python 3.14 已收窄 3.13 的额外 immortalization 范围，因此教材不能维护一个跨版本固定对象名单。分析并发对象时仍应依次检查生命周期、结构同步与业务一致性，而不是把 immortality 当成线程安全保证。