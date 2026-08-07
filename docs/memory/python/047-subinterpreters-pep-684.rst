第047章：Subinterpreters（PEP 684）
=================================

核心知识点
----------

* subinterpreter 是同一 CPython 进程中的独立 ``PyInterpreterState``，不是线程的别名，也不是独立进程。
* 一个进程可以同时拥有主解释器和多个 subinterpreter；每个解释器拥有自己的 module state、``sys.modules``、builtins、GC 状态、线程状态列表和其它解释器级 runtime state。
* OS thread 是调度实体，``PyThreadState`` 是线程进入某个解释器后的执行现场，``PyInterpreterState`` 是该解释器的共享运行环境。并行执行仍需要线程承载。
* PEP 684 的核心是 per-interpreter GIL：足够隔离的解释器可以拥有自己的 GIL，使不同解释器中的 Python bytecode 能由不同 OS thread 在多个 CPU core 上同时推进。
* per-interpreter GIL 提升的是解释器之间的并行潜力；它没有让单个解释器内部的任意线程天然无锁并行。
* subinterpreter 隔离的是 Python runtime state，不是整个进程。文件描述符、环境变量、地址空间、native library 全局变量等进程资源仍可能共享。
* 同一个纯 Python 模块在不同解释器中导入，会得到各自的 module object 和模块级全局状态；一个解释器修改模块变量不会自动同步到另一个解释器。
* 普通 Python 对象不应把“同一个对象引用”直接跨解释器共享。对象头、引用计数、GC、内部可变字段与解释器归属存在运行时约束。
* 跨解释器传递应优先使用序列化副本、明确支持的不可变数据或 runtime 提供的 cross-interpreter 通道，使所有权边界显式化。
* ``InterpreterPoolExecutor`` 使用 worker thread + 独立 interpreter 的组合提供并行执行；函数、参数和返回值跨解释器传输会产生序列化与调度成本。
* C 扩展是 subinterpreter 兼容性的关键边界。使用多阶段初始化并把状态放入 per-module state 的扩展更适合隔离；依赖 C 全局变量或单阶段初始化的扩展可能泄漏共享状态。
* own-GIL interpreter 需要配合隔离配置。只有把 allocator、扩展模块、fork/exec、thread 等边界纳入配置，per-interpreter GIL 才有稳定意义。
* subinterpreter 适合需要同进程内 Python 状态隔离、又希望获得 CPU 并行的任务；若需要强安全隔离、独立崩溃边界或独立系统资源，进程仍是更清晰的边界。

关键路径
--------

解释器与线程关系：

::

   OS process
       ├─ main PyInterpreterState
       │    └─ PyThreadState(main worker)
       ├─ subinterpreter A
       │    └─ PyThreadState(worker A)
       └─ subinterpreter B
            └─ PyThreadState(worker B)

   each interpreter
       ↓
   own sys.modules / builtins / module state
       ↓
   optionally own GIL
       ↓
   worker thread executes Python code

跨解释器任务链：

::

   caller in interpreter A
       ↓
   prepare callable + arguments
       ↓
   serialize / convert to supported transfer form
       ↓
   submit to worker thread bound to interpreter B
       ↓
   deserialize / reconstruct objects in B
       ↓
   execute using B's modules, globals and GIL
       ↓
   produce result / exception
       ↓
   serialize transfer payload
       ↓
   return reconstructed result to A

扩展模块兼容性检查：

::

   import extension in subinterpreter
       ↓
   inspect initialization/state model
       ↓
   per-module state / multi-phase init
       → can isolate interpreter-local state

   process-global C state / incompatible single-phase assumptions
       → shared-state risk
       → reject, re-enable shared protection, or redesign extension

概念辨析
--------

* **subinterpreter 与 thread**：thread 是 OS 调度单位；subinterpreter 是 Python runtime state 容器。解释器要并行运行仍需线程承载。
* **subinterpreter 与 process**：subinterpreter 共享进程地址空间和 OS 资源；process 提供更强的内存、崩溃与权限隔离。
* **per-interpreter GIL 与 no-GIL**：前者仍保留 GIL，只是每个解释器一把；free-threaded/no-GIL 则允许同一解释器中的多个线程并行执行 Python 代码。
* **模块隔离与对象共享**：模块表按解释器分离不意味着任意 Python object 可以安全跨解释器共享。
* **复制数据与共享引用**：序列化/重建形成解释器本地对象；直接共享对象引用会把所有权、引用计数和同步责任跨越解释器边界。
* **Python 模块与 C 扩展**：纯 Python module 通常自然形成解释器本地 module object；C 扩展还要检查 native 全局状态和初始化模型。
* **并行收益与通信成本**：CPU-heavy 独立任务更容易覆盖解释器通信成本；频繁传递大对象或细粒度任务可能让序列化成为瓶颈。

本章结论
--------

Subinterpreter 的稳定模型是“同一进程内建立多个独立 ``PyInterpreterState``，再用线程承载执行，并通过 per-interpreter GIL 获得解释器之间的 Python 并行”。判断是否适用时，应先画出模块状态、对象所有权和 native 状态的共享边界，再估算跨解释器传输成本。它是线程共享模型与多进程隔离模型之间的一层 runtime 方案，而不是自动安全、自动零成本的并行开关。