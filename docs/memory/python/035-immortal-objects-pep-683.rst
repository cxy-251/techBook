第035章：Immortal Objects（PEP 683）
====================================

核心知识点
----------

* PEP 683 为部分长期存活、高频共享对象引入 **immortal object** 状态，使它们不再按普通对象方式反复修改引用计数。
* immortal object 仍然是普通 Python 对象：有 identity、type、对象头和正常语言语义；变化只发生在 CPython 的生命周期管理策略。
* 普通对象依赖 ``INCREF → DECREF → refcount == 0 → deallocate``；immortal object 使用特殊 refcount 状态，普通 ``Py_INCREF()`` / ``Py_DECREF()`` 路径识别后基本不再改写该计数。
* ``None``、``True``、``False``、部分静态类型和运行时长期共享对象适合这种策略，因为它们语义稳定、访问频率高、生命周期通常与解释器或进程接近。
* immortal refcount 是状态标记，不是“真实有这么多引用”。看到极大的 ``sys.getrefcount()`` 或内部 refcount 值时，不应把它解释为真实持有者数量。
* 引用计数本质上是对象头部写操作。热门共享对象被多个执行上下文频繁 ``INCREF`` / ``DECREF`` 时，会产生 cache line 写入与一致性成本。
* 让 immortal object 的引用计数更新变成 no-op，可以减少共享 cache line 的失效和多核之间的写流量。
* pre-fork 服务依赖 copy-on-write 共享父进程内存页；若子进程只因为 refcount 更新就写共享对象页，会触发额外页面复制。immortal object 可以减少这类无业务数据变化的写入。
* immortal object 并不让所有 Python 对象绕过 GC。普通 heap object 仍按 refcount 和 cyclic GC 工作；对象是否 GC-tracked、是否 static、是否 immortal，需要分别判断。
* intentional immortality 与内存泄漏是两类问题。前者是 runtime 明确选择的长期生命周期；后者是本应释放的对象仍被错误 strong reference 或分配路径保留。
* PEP 683 也为多解释器共享和 free-threaded/no-GIL 方向提供基础：长期共享对象若无需频繁原子更新 refcount，可以减少共享写热点和同步成本。
* free-threaded Python 仍需要处理大量普通对象的并发生命周期；immortal object 只移除一小类“已知永远不会按普通路径销毁”的 refcount 竞争。
* 这项机制属于 CPython implementation detail。Python 用户代码不应依赖某个具体对象在某个版本中一定是 immortal。
* C 扩展应通过公开引用计数 API 管理对象；直接修改 ``ob_refcnt`` 会绕开运行时对 immortal 状态、free-threaded 构建和未来实现变化的处理。

关键路径
--------

普通对象与 immortal object 的生命周期差异：

::

   ordinary heap object
       ↓
   INCREF / DECREF update ob_refcnt
       ↓
   last strong reference released
       ↓
   refcount == 0
       ↓
   deallocation

   immortal object
       ↓
   special immortal refcount state
       ↓
   ordinary INCREF / DECREF recognized
       ↓
   no normal refcount write
       ↓
   no ordinary refcount-to-zero deallocation
       ↓
   lifetime controlled by runtime/static finalization policy

缓存与 copy-on-write 优化链：

::

   hot shared singleton/type
       ↓
   frequent reference transfers
       ↓
   ordinary model writes refcount cache line
       ↓
   cache coherence / fork COW pressure
       ↓
   mark object immortal
       ↓
   refcount updates become no-op
       ↓
   fewer shared writes

概念辨析
--------

* **immortal 与 immutable**：immutable 表示 Python 层值不能原地修改；immortal 表示 CPython 不按普通 refcount 生命周期释放。两个概念处在不同层级。
* **immortal 与 singleton**：singleton 表示只有一个语义实例；是否 immortal 是 CPython 内部优化选择。两者经常重叠但不等价。
* **immortal 与 GC untracked**：immortal 描述生命周期/refcount 策略；GC tracking 描述对象是否进入循环引用扫描，两者需要独立判断。
* **immortal 与 leak**：immortal 是有意设计的长期对象；leak 是无意中让本应结束生命周期的对象继续被持有。
* **cache line 优化与语言语义**：减少 refcount 写入只改变性能和共享成本，不改变 ``is``、属性访问、参数传递等 Python 语义。
* **PEP 683 与 no-GIL**：PEP 683 不是完整的 no-GIL 方案，它只是减少一类高频共享对象的引用计数同步压力。

本章结论
--------

Immortal object 的核心是把“runtime 已经知道会长期存在的对象”从普通引用计数写入路径中移出。它减少热门共享对象的 cache line 修改、pre-fork copy-on-write 成本，并为多解释器和 free-threaded 方向降低一部分共享 refcount 压力。阅读源码时，应把 immortal 状态视为 CPython 的生命周期与性能优化，而不是 Python 语言层的新对象语义。