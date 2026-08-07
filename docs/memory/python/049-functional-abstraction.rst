第049章：Functional Abstraction
==============================

核心知识点
----------

* ``itertools`` 的核心产物是 iterator：工具对象保存最小推进状态，由下游 ``next()`` 请求驱动上游逐项生产。
* ``chain``、``islice``、``takewhile``、``dropwhile`` 等通常保持惰性，不会先把全部输入复制成新列表。
* ``groupby`` 只按**相邻**且 key 相同的元素分组；如果目标是按全局 key 聚合，通常必须先排序或保证输入本身已经按 key 聚集。
* ``sorted()``、``list()``、``tuple()``、``set()`` 等是典型 materialization boundary：进入后需要消费输入，并改变内存峰值、异常触发时机和资源持有时间。
* ``functools.partial`` 创建携带预绑定参数的 callable object；它保存原 callable 和绑定状态，不复制函数体。
* decorator 本质上通常是“外部名字重新绑定到 wrapper”；wrapper 通过 closure、默认参数或对象字段持有原 callable 和额外状态。
* ``functools.wraps`` 通过复制元数据并设置 ``__wrapped__``，让 introspection、文档和调试仍能追踪原 callable。
* ``lru_cache`` 在 callable 外增加 key 构造、缓存查找和结果保存层；缓存的是结果对象引用，可变结果会被后续命中者共享。
* ``cached_property`` 是 descriptor 层的惰性缓存：第一次读取执行计算并把结果写入实例存储，之后通常直接读取已缓存值。
* ``singledispatch`` 按第一个参数的 runtime type/MRO 选择实现，是动态分发表，不是静态重载系统。
* generator expression、generator function、``map``、``filter`` 和多数 ``itertools`` 工具都遵循 pull-based lazy evaluation。
* 惰性流水线降低中间数据内存占用，同时会推迟异常和副作用，并可能延长文件、游标、连接等上游资源的生命周期。
* iterator 通常是单次消费状态机；把同一个 iterator 交给多个消费者会共享推进位置，而 iterable 往往可以重新创建 iterator。
* 函数式抽象的主要收益是组合与按需消费，主要代价是动态调用层、隐藏状态、共享 iterator、缓存和延迟资源释放。

关键路径
--------

典型惰性流水线：

::

   input iterable
       ↓
   iter(input)
       ↓
   chain / map / generator / filter
       ↓
   downstream next()
       ↓
   current layer requests next(upstream)
       ↓
   transform / predicate / callable
       ↓
   yield one object
       ↓
   next request repeats
       ↓
   StopIteration closes normal iteration

``partial`` 调用链：

::

   partial(original, bound_args, bound_kwargs)
       ↓
   partial object stores callable + bound state
       ↓
   partial(new_args, new_kwargs)
       ↓
   merge bound and current arguments
       ↓
   call original callable
       ↓
   return / raise

缓存调用链：

::

   call cached wrapper
       ↓
   build cache key
       ↓
   cache hit? ── yes ──> return stored object
       │
       no
       ↓
   call original function
       ↓
   store result
       ↓
   return result

概念辨析
--------

* **iterable 与 iterator**：iterable 能提供 iterator；iterator 自身保存当前消费位置并实现 ``__next__``。
* **惰性与异步**：惰性只表示按需计算，不表示并发，也不自动产生 ``await`` 或线程调度。
* **惰性与零内存**：惰性减少中间物化，某些工具仍需缓存输入池、复制状态或保存历史。
* **``groupby`` 与数据库 GROUP BY**：``itertools.groupby`` 只合并相邻同 key 项，不会自动扫描并聚合全部同 key 元素。
* **``partial`` 与 closure**：二者都能保存调用状态；``partial`` 专注参数预绑定，closure 能表达任意额外逻辑和局部状态。
* **decorator 与原函数**：装饰后外部名字通常指向 wrapper；原函数可能由 ``__wrapped__``、closure 或对象字段继续持有。
* **缓存与纯函数**：缓存最适合参数可哈希、结果稳定且重复调用高的函数；副作用函数和可变返回对象需要额外约束。
* **iterator 与 snapshot**：iterator 表达未来消费路径，``list(iterator)`` 才把当时剩余元素物化成独立容器。

本章结论
--------

Functional abstraction 可以压缩为“iterator 把数据处理改成按需推进，callable wrapper 把调用行为改造成可组合对象”。阅读 ``itertools`` / ``functools`` 代码时，先找真实 iterator 和 callable，再确认谁驱动消费、何处物化、包装层保存什么状态、异常何时发生、资源由谁关闭。掌握这条路径后，惰性、缓存、partial、decorator、groupby 与 iterator 生命周期可以统一到同一个 runtime 模型中。