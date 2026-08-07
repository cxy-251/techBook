第048章：Free-Threaded Python
=============================

核心知识点
----------

* Free-threaded Python 指 CPython 在可选 no-GIL 模式下允许多个线程同时执行 Python code 的运行时形态。Python 3.13 起开始提供这一路线，核心设计来自 PEP 703。
* build 是否支持 free threading 与当前进程是否启用 GIL 是两个不同状态；兼容性原因可能让 free-threaded build 在运行时重新启用 GIL。
* GIL 移除后，``PyThreadState`` 仍然存在。线程仍要 attach 到 Python runtime；变化在于多个线程可以同时处于可执行 Python 对象的状态。
* 原来由单个 GIL 承担的大粒度保护被拆成多个局部机制：对象生命周期、容器内部锁、allocator、GC、thread state 和扩展模块同步。
* free-threaded runtime 的目标首先是解释器内部安全，即防止 Python 对象和容器结构被并发访问破坏；它不自动保证应用业务操作的原子性。
* ``dict``、``list``、``set`` 等内置可变容器在 free-threaded CPython 中使用内部同步保护自身结构，但多个操作组成的业务事务仍需 ``threading.Lock`` 或其它同步原语。
* ``counts[key] += 1`` 是读取旧对象、计算新值、写回容器的复合操作。容器内部锁能保证 dict 不损坏，不能保证两个线程的业务累加不会丢失更新。
* free-threaded 设计需要更复杂的引用计数策略，包括 atomic、biased、deferred 等思路，以减少每次对象引用变化都成为跨核热点。
* 对共享容器的锁粒度尽量局部化；无关对象可以并行，真正共享同一容器或同一缓存行的线程仍会竞争。
* 部分读取路径可以采用 optimistic locking 或延迟内存复用等策略降低锁开销，但这些属于 CPython 实现细节，不应写入业务正确性假设。
* GC 仍要获得稳定对象图，因此 free-threaded runtime 需要 stop-the-world 或其它协调阶段；no-GIL 不代表 runtime 完全没有全局暂停。
* C 扩展是迁移重点。历史代码可能依赖 GIL 隐式保护 C 全局变量、borrowed reference、直接结构体字段访问和无锁缓存，这些假设在 free-threaded 模式下必须显式修正。
* 返回 borrowed reference 的旧式快速宏或直接字段读取，在共享对象可被并发修改时风险更高；扩展应优先使用带锁或返回 strong reference 的安全 API，并在需要时使用 critical section。
* free-threaded 能扩大 CPU-bound Python 多线程的并行空间，但同步、atomic refcount、GC、allocator 与扩展兼容性都会引入额外成本，单线程性能不一定更快。
* 最容易获得收益的设计通常减少共享热点：线程先处理本地状态，最后合并；频繁修改同一个全局 dict、counter 或 registry 会把瓶颈从 GIL 转移到对象锁和缓存一致性竞争。

关键路径
--------

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
       ├─ atomic / biased / deferred refcount path
       └─ safe memory reclamation
       ↓
   mutable container access
       ├─ internal object/container lock
       └─ optimistic read path where supported
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

C 扩展迁移检查：

::

   extension touches shared Python/native state
       ↓
   does API acquire needed object lock?
       ↓
   does returned reference remain valid concurrently?
       ↓
   are C globals/caches protected?
       ↓
   use strong-reference API / critical section / extension lock
       ↓
   declare and test free-threading compatibility

概念辨析
--------

* **no-GIL 与无锁**：移除全局 GIL 不代表 runtime 没有锁；保护被拆到对象、容器、allocator、GC 和扩展等更小粒度。
* **runtime 安全与业务正确性**：内部锁保证解释器数据结构不损坏；应用锁保证跨多个操作的业务不变量。
* **容器线程安全与复合原子性**：单次 ``append``、``setitem`` 的结构安全不等于“读取后修改再写回”整体原子。
* **free-threaded 与 per-interpreter GIL**：free-threaded 允许同一解释器中的多个线程并行；per-interpreter GIL 让不同解释器各自持有 GIL 并行。
* **并行能力与实际加速**：线程能同时执行只是前提；共享热点、对象锁、atomic refcount、缓存行竞争和 GC 都可能限制扩展性。
* **Python 内置对象与 C 扩展**：CPython 可以改造自己的容器和对象协议；第三方扩展必须自行检查曾经依赖 GIL 的隐式假设。
* **线程本地状态与共享状态**：线程私有对象几乎没有同步竞争；跨线程频繁共享可变对象会迅速放大锁和 cache-coherency 成本。
* **build 能力与当前运行状态**：二进制支持 free threading，不等于当前进程一定关闭 GIL；诊断性能前必须确认实际运行模式。

本章结论
--------

Free-threaded Python 的核心不是简单“删除一把锁”，而是把 CPython 的并发保护从全局 GIL 拆到对象生命周期、容器、GC、allocator 和扩展边界。迁移和性能分析时，应先确认当前 GIL 状态，再画出跨线程共享对象图，区分解释器内部安全与业务级原子性，最后检查 C 扩展兼容。共享越少、任务越独立，free-threaded 越容易释放多核收益；共享热点越集中，瓶颈越可能从 GIL 转移到更细粒度的同步上。