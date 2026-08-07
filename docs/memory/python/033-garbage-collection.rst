第033章：垃圾回收
=================

核心知识点
----------

* CPython 的循环垃圾回收器是引用计数的补充，主要处理“外部已经不可达，但对象之间仍通过强引用互相支撑”的循环对象组。
* 普通对象最后一份 strong reference 消失时仍由引用计数立即处理；GC 不负责替代这条主路径。
* 只有能够持有其它 Python 对象引用、并支持 GC tracking 的对象才需要进入循环检测；原子对象通常没有参与引用环的必要。
* ``gc.is_tracked(obj)`` 可以观察对象当前是否被 GC 跟踪，但某些容器会根据内容做取消跟踪优化，因此 tracked 状态属于实现层事实。
* 分代策略利用“大多数对象生命周期短”的经验：年轻对象更频繁扫描，存活对象进入更老 generation，从而减少长期对象被重复遍历的成本。
* 循环检测的核心是候选对象图，而不是简单寻找 ``refcount > 0`` 的对象。GC 会区分候选集合内部引用与来自集合外部的强引用入口。
* CPython 可以把候选对象的临时 GC 引用计数初始化为真实引用计数，再通过 ``tp_traverse`` 扣除候选集合内部的边；扣除后仍有外部入口的对象恢复为可达，没有外部入口的对象进入不可达集合。
* C 扩展类型只有正确实现 ``tp_traverse``，GC 才能看见对象内部保存的引用边；需要打断环时通常还要提供 ``tp_clear``。
* finalizer 会让回收路径变复杂，因为 ``__del__`` / ``tp_finalize`` 能执行 Python 代码，甚至重新建立外部 strong reference，使对象发生 resurrection。
* PEP 442 之后，现代 CPython 可以安全处理大量带 ``__del__`` 的循环；判断重点应放在 finalizer 是否复活对象、是否依赖清理顺序，而不是沿用“有 ``__del__`` 就一定无法回收”的旧规则。
* weak reference 默认不延长目标对象生命周期，适合缓存、反向索引和生命周期观察；``weakref.finalize`` 可用于附加清理回调，但外部资源仍应优先显式管理。
* ``gc.collect()`` 适合诊断和测试，可以强制推进 collection；自动 GC 的实际触发仍受 generation、阈值、解释器版本和构建模式影响。
* ``gc.get_referrers()`` 是调试线索，不是完整 root 枚举器；它只能看到 GC 能追踪的部分引用关系，也可能把当前调试过程本身加入对象图。
* 内存持续增长时，应先判断对象是否仍从 globals、frame、缓存、任务队列、异常对象、C 扩展等长寿命 root 可达，再判断是否属于真正的循环回收问题。

关键路径
--------

循环对象组进入 GC 的路径：

::

   objects strongly reference each other
       ↓
   external roots disappear
       ↓
   refcounts remain > 0
       ↓
   objects remain GC-tracked candidates
       ↓
   generation selected for collection
       ↓
   initialize temporary GC reference counts
       ↓
   traverse candidate-internal references
       ↓
   subtract internal edges
       ↓
   still has outside references ?
       ├─ yes → reachable / keep alive
       └─ no  → unreachable set
                    ↓
               finalization / weakref handling
                    ↓
               clear internal references
                    ↓
               ordinary deallocation

对象复活路径：

::

   object judged unreachable
       ↓
   finalizer runs
       ↓
   finalizer stores self into external root
       ↓
   strong reference restored
       ↓
   object becomes reachable again
       ↓
   destruction postponed

概念辨析
--------

* **引用计数与循环 GC**：引用计数处理单对象 strong reference 归零；循环 GC 处理对象组内部引用让计数无法归零的情况。
* **tracked 与 reachable**：tracked 表示对象被纳入 GC 观察范围；reachable 表示当前仍有从外部执行状态进入对象的强引用路径，两者不是同一概念。
* **generation 与对象年龄**：generation 是 GC 扫描策略中的管理层级，不是 Python 语义中的对象属性。
* **weakref 与 strong reference**：weakref 能观察目标却通常不保持其存活；普通容器、属性和局部变量持有的 strong reference 会延长生命周期。
* **finalizer 与确定性资源清理**：finalizer 的触发依赖生命周期和 GC 时机；文件、锁、socket、事务等资源应使用显式上下文边界。
* **``gc.collect`` 与修复泄漏**：强制 collection 只能回收已经不可达的循环对象；仍被缓存、frame 或全局结构强引用的对象不会因此消失。

本章结论
--------

CPython GC 可以压缩为“引用计数负责即时释放，循环 GC 周期性分析可跟踪对象图，扣除候选集合内部引用后识别真正不可达的对象组”。排查 GC 问题时，先确定对象是否仍有外部 strong reference，再确认它是否被跟踪、是否形成环、扫描是否覆盖到对应 generation，最后处理 finalizer、weakref 和 resurrection 等生命周期边界。