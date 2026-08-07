第045章：GIL Internals
======================

核心知识点
----------

* 本章默认讨论 CPython 的 GIL-enabled 构建。GIL 是解释器运行时的互斥入口，用来保护大量 Python 对象访问、引用计数和解释器内部状态；它不是业务数据一致性的替代品。
* OS thread、``PyThreadState`` 与 ``PyInterpreterState`` 是三个不同层级：OS thread 由操作系统调度；``PyThreadState`` 保存线程进入 Python runtime 后的执行现场；``PyInterpreterState`` 保存一个解释器实例的共享状态。
* 默认 GIL 构建中，线程要执行 Python bytecode 或使用大多数 Python C API，通常必须拥有 attached thread state 并持有对应 GIL。
* 多个线程可以同时存在、阻塞、运行 native code，但同一解释器中的纯 Python bytecode 在默认构建下仍由 GIL 串行推进。
* GIL 不是“每条 bytecode 一把锁”。线程取得 GIL 后会连续执行一段指令，解释器在安全检查点处理线程切换请求、signal、pending call、异步异常等事件。
* eval breaker 是求值循环中的快速检查机制。无待处理事件时继续快路径；有事件时进入慢路径，可能处理调度、信号或释放 GIL。
* ``sys.setswitchinterval()`` 调整的是解释器线程切换的时间倾向，不会让 CPU-bound Python 线程变成真正的多核并行。
* CPU-bound 纯 Python 线程主要竞争 GIL，因此增加线程通常不能按 CPU core 数线性加速。
* I/O-bound 线程可以获得并发收益，因为 ``sleep``、socket、文件 I/O 等底层阻塞操作常在等待期间释放 GIL，让其它线程执行 Python 代码。
* C 扩展是否释放 GIL决定了并发表现。native 函数长时间持有 GIL 会阻塞其它 Python 线程；不访问 Python 对象的长计算可以在明确边界释放 GIL。
* GIL 只维护解释器内部安全，不保证 ``counter += 1``、检查后写入、跨多个字段更新等业务复合操作具有原子语义；这类不变量仍应使用 Lock、Queue 或单所有者设计。
* 在 free-threaded 构建中，多个线程可以同时执行 Python 代码；此时保护责任转移到对象内部锁、引用计数策略、GC 暂停、allocator 与扩展模块同步机制。

关键路径
--------

默认 CPython 线程执行链：

::

   OS thread
       ↓
   attach / obtain PyThreadState
       ↓
   PyThreadState points to PyInterpreterState
       ↓
   acquire GIL
       ↓
   enter current frame / bytecode evaluator
       ↓
   execute a run of Python instructions
       ↓
   eval-breaker / safe-point check
       ↓
   no pending work → continue evaluation
       or
   switch/signal/pending work → slow path
       ↓
   possibly release GIL
       ↓
   another waiting thread acquires GIL
       ↓
   original thread later reacquires and resumes frame

阻塞 I/O 的典型路径：

::

   Python thread holds GIL
       ↓
   call blocking native I/O
       ↓
   native wrapper releases GIL
       ↓
   OS thread waits for I/O
       ↓
   another Python thread acquires GIL and runs
       ↓
   I/O completes
       ↓
   waiting thread reacquires GIL
       ↓
   convert native result to Python objects
       ↓
   continue Python frame

概念辨析
--------

* **GIL 与 OS 调度**：OS 可以同时调度多个线程；GIL 额外限制默认 CPython 中哪些线程能进入 Python 对象与 bytecode 执行路径。
* **GIL 与 ``PyThreadState``**：thread state 是执行现场和解释器归属；GIL 是默认构建中的互斥入口。二者不是同一个对象。
* **GIL 与用户锁**：GIL 保护 runtime 内部结构；``threading.Lock`` 保护应用自己的跨语句、跨对象业务不变量。
* **线程并发与 CPU 并行**：I/O 等待可以重叠，因此线程很适合 I/O-bound；默认 GIL 构建中的纯 Python CPU 工作仍主要串行执行。
* **Python bytecode 与 native code**：native code 若释放 GIL，可以和其它 Python 线程并行；若持续持有 GIL，即使工作发生在 C/C++ 中也会阻塞其它 Python 线程。
* **切换间隔与原子性**：调整 switch interval 只改变调度倾向，不应作为保证某段 Python 操作不被交错执行的正确性机制。
* **GIL build 与 free-threaded build**：前者依赖全局解释器锁形成大粒度保护；后者移除这层全局串行点，把同步拆到更细粒度的 runtime 对象与业务代码中。

本章结论
--------

GIL 的稳定模型是“默认 CPython 用解释器级互斥入口串行化 Python runtime 的关键访问路径”。分析多线程问题时，应先确认构建模式，再沿 ``OS thread → PyThreadState → interpreter → GIL → frame/evaluator`` 追踪执行；随后区分热点究竟位于纯 Python CPU、阻塞 I/O、持有 GIL 的 native 扩展，还是业务锁。只要把 runtime 安全与业务原子性分开，GIL 对性能和正确性的边界就能稳定判断。