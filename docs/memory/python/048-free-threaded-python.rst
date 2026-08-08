第048章：Free-Threaded Python
=============================

核心知识点
----------

* Free-threaded Python 指 CPython 在可选 no-GIL 构建中允许多个线程同时执行 Python code 的运行时形态，核心设计来自 PEP 703。
* Python 3.13 首次提供实验性 free-threaded build；Python 3.14 进入 PEP 779 的第二阶段：**free-threaded build 已获得官方支持、不再是 experimental，但仍然是可选构建，并非默认 CPython 运行模式**。
* build 是否支持 free threading 与当前进程是否启用 GIL 是两个不同状态；兼容性原因仍可能让 free-threaded build 在运行时重新启用 GIL。
* GIL 移除后，``PyThreadState`` 仍然存在。线程仍要 attach 到 Python runtime；变化在于同一解释器中可以有多个线程同时推进 Python code。
* 原来由单个 GIL 承担的大粒度保护被拆成多个局部机制：对象生命周期、容器内部锁、allocator、GC、thread state 和扩展模块同步。
* free-threaded runtime 的目标首先是解释器内部安全，即防止 Python 对象和容器结构被并发访问破坏；它不自动保证应用业务操作的原子性。
* ``dict``、``list``、``set`` 等内置可变容器使用内部同步保护自身结构，但官方仍建议对业务共享状态优先使用 ``threading.Lock`` 等同步原语，而不是把容器内部锁当成应用并发合同。
* ``counts[key] += 1`` 是读取旧对象、计算新值、写回容器的复合操作。容器结构安全不能保证两个线程的业务累加不会丢失更新。
* free-threaded 设计需要更复杂的引用计数与回收策略，包括 biased/local/shared reference counting、deferred counting、immortalization 和安全内存复用等机制；具体实现会继续随版本演进。
* 对共享容器的锁粒度尽量局部化；无关对象可以并行，真正共享同一容器或同一缓存行的线程仍会竞争。
* GC 仍要获得稳定对象图，因此 free-threaded runtime 仍存在 stop-the-world 或其它全局协调阶段；no-GIL 不等于 runtime 完全没有全局暂停。
* C 扩展是迁移重点。历史代码可能依赖 GIL 隐式保护 C 全局变量、borrowed reference、直接结构体字段访问和无锁缓存，这些假设在 free-threaded 模式下必须显式修正。
* 返回 borrowed reference 的旧接口在共享对象可被并发修改时风险更高；扩展应优先使用返回 strong reference 的安全 API、critical section 或自己的锁，并声明与测试 free-threading compatibility。
* Python 3.14 的 free-threaded build 已恢复 specialization 等关键优化，但仍有额外同步与内存成本；官方基准显示单线程开销已经远低于 3.13，仍不能假设单线程一定更快。
* free-threaded 与 CPython 实验性 JIT 是不同路线。Python 3.14 的 free-threaded build **当前不支持 JIT compilation**，不能把 no-GIL 与 JIT 当成已经组合好的统一执行模式。
* 最容易获得收益的设计通常减少共享热点：线程先处理本地状态，最后合并；频繁修改同一个全局 dict、counter 或 registry 会把瓶颈从 GIL 转移到对象锁和缓存一致性竞争。

关键路径
--------

运行模式判断：

::

   CPython executable
   → default GIL build or free-threaded build ?
   → if free-threaded: is GIL currently disabled ?
   → check extension compatibility / fallback
   → only then interpret concurrency and benchmark result

Free-threaded 对象访问链：

::

   OS thread
       ↓
   attach PyThreadState
       ↓
   enter Python runtime without global GIL serialization
       ↓
   access Python object
       ↓
   lifetime protection
       ├─ local/shared/deferred refcount path
       └─ safe memory reclamation
       ↓
   mutable container access
       ├─ internal object/container synchronization
       └─ optimized read path where supported
       ↓
   perform Python operation
       ↓
   application-level invariant still needs its own synchronization

业务复合更新：

::

   Thread A                     Thread B
      ↓                            ↓
   read counts[key]             read counts[key]
      ↓                            ↓
   compute new value            compute new value
      ↓                            ↓
   write dict entry             write dict entry

   runtime keeps dict structurally valid
   but result may violate "increment exactly twice"

   correct business path:

   acquire application Lock
       ↓
   read → compute → write
       ↓
   release Lock

概念辨析
--------

* **3.13 experimental 与 3.14 supported**：3.13 是实验性引入；3.14 已正式支持这条构建路线，但仍不是默认构建。
* **supported 与 default**：官方支持表示不会按实验功能随意撤回；默认 CPython 仍由 GIL-enabled build 占主导。
* **no-GIL 与无锁**：移除全局 GIL 不代表 runtime 没有锁；保护被拆到对象、容器、allocator、GC 和扩展等更小粒度。
* **runtime 安全与业务正确性**：内部同步保证解释器数据结构不损坏；应用锁保证跨多个操作的业务不变量。
* **容器线程安全与复合原子性**：单次容器操作的内部安全不等于“读取后修改再写回”整体原子。
* **free-threaded 与 per-interpreter GIL**：free-threaded 允许同一解释器中的多个线程并行；per-interpreter GIL 让不同解释器各自持有 GIL 并行。
* **free-threaded 与 JIT**：二者分别解决并行和热点执行优化；Python 3.14 当前不能在 free-threaded build 中使用 JIT。
* **并行能力与实际加速**：线程能同时执行只是前提；共享热点、对象锁、引用计数、缓存行竞争和 GC 都可能限制扩展性。

本章结论
--------

Python 3.14 已把 free-threaded CPython 从实验路线推进到正式支持的可选构建。稳定分析模型仍是：先确认 build 与当前 GIL 状态，再沿对象生命周期、容器同步、GC、allocator 和 C 扩展边界追踪并发责任，最后用应用级同步保护业务不变量。它不是“默认 Python 已经没有 GIL”，也不能与当前实验性 JIT 混为同一执行模式。