第047章：Subinterpreters（PEP 684）
=================================

核心知识点
----------

* subinterpreter 是同一 CPython 进程中的独立 ``PyInterpreterState``，不是线程的别名，也不是独立进程。
* 一个进程可以同时拥有主解释器和多个 subinterpreter；每个解释器拥有自己的 module state、``sys.modules``、builtins、GC 状态、线程状态列表和其它解释器级 runtime state。
* OS thread 是调度实体，``PyThreadState`` 是线程进入某个解释器后的执行现场，``PyInterpreterState`` 是该解释器的共享运行环境。解释器本身不自动产生并发，并行执行仍需要线程等执行载体。
* PEP 684 的核心是 per-interpreter GIL：足够隔离的解释器可以拥有自己的 GIL，使不同解释器中的 Python bytecode 能由不同 OS thread 在多个 CPU core 上同时推进。
* Python 3.14 的重要变化是 PEP 734 把 multiple-interpreter 管理正式带入标准库：``concurrent.interpreters`` 提供高层解释器管理与任务执行 API，不再要求普通 Python 代码必须通过 C API 才能创建和使用 subinterpreter。
* ``concurrent.interpreters`` 主要提供解释器隔离与管理，不会凭空产生线程。需要真正并发时仍要把解释器与 thread/executor 等执行模型组合。
* Python 3.14 同时加入 ``concurrent.futures.InterpreterPoolExecutor``，用 worker thread + 独立 interpreter 的组合提供熟悉的 executor 接口和真正的多核 Python 并行。
* per-interpreter GIL 提升的是解释器之间的并行潜力；它没有让单个解释器内部的任意线程天然无锁并行。后者属于 free-threaded/no-GIL 路线。
* subinterpreter 隔离的是 Python runtime state，不是整个进程。文件描述符、环境变量、地址空间、native library 全局变量等进程资源仍可能共享。
* 同一个纯 Python 模块在不同解释器中导入，会得到各自的 module object 和模块级全局状态；一个解释器修改模块变量不会自动同步到另一个解释器。
* 普通 Python 对象不能因为处于同一地址空间就随意以“同一个对象引用”跨解释器共享。对象生命周期、引用计数、GC 和解释器归属都要求明确传输边界。
* 跨解释器数据交换应使用 ``concurrent.interpreters`` 支持的数据机制、明确可共享对象、序列化副本或其它显式 channel/protocol，而不是偷偷复用任意 ``PyObject *``。
* ``InterpreterPoolExecutor`` 的函数、参数、返回值和异常跨解释器传输会产生序列化、复制、调度与初始化成本，因此最适合粒度足够大的独立任务。
* C 扩展仍是 subinterpreter 兼容性的关键边界。使用 multi-phase initialization 并把状态放入 per-module state 的扩展更适合隔离；依赖 C 全局变量或 legacy single-phase assumptions 的扩展可能泄漏共享状态。
* Python 3.14 标准库扩展已适配 multiple interpreters，但第三方 PyPI 扩展并不自动兼容；部署前必须验证具体依赖。
* own-GIL interpreter 需要配合隔离配置。只有把 allocator、扩展模块、fork/exec、thread 等边界纳入配置，per-interpreter GIL 才有稳定意义。
* subinterpreter 适合需要同进程内 Python 状态隔离、又希望获得 CPU 并行的任务；若需要强安全隔离、独立崩溃边界或独立系统资源，process 仍是更清晰的边界。

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

   each isolated interpreter
       ↓
   own sys.modules / builtins / module state
       ↓
   own GIL where configured
       ↓
   worker thread executes Python code

Python 3.14 高层入口：

::

   application
   → concurrent.interpreters
   → create / inspect / run in interpreter
   → explicit data transfer boundary

   or

   application
   → InterpreterPoolExecutor
   → worker thread + isolated interpreter
   → execute callable in parallel
   → transfer result / exception back

跨解释器任务链：

::

   caller in interpreter A
       ↓
   prepare callable + arguments
       ↓
   convert / serialize to supported transfer form
       ↓
   execute in interpreter B
       ↓
   B uses its own modules / globals / interpreter state
       ↓
   produce result / exception
       ↓
   transfer payload
       ↓
   reconstruct result in A

扩展模块兼容性检查：

::

   import extension in subinterpreter
       ↓
   inspect initialization/state model
       ↓
   per-module state / multi-phase init
       → can isolate interpreter-local state

   process-global C state / legacy single-phase assumptions
       → shared-state risk
       → reject, serialize access, or redesign extension

概念辨析
--------

* **PEP 684 与 PEP 734**：PEP 684 解决 per-interpreter GIL 与 runtime isolation；PEP 734 把 multiple interpreters 的管理能力正式暴露到 Python 标准库。
* **``concurrent.interpreters`` 与 ``InterpreterPoolExecutor``**：前者是解释器管理/执行 API，解释器本身不等于并发；后者把线程和独立解释器组合成 executor。
* **subinterpreter 与 thread**：thread 是 OS 调度单位；subinterpreter 是 Python runtime state 容器。解释器要并行运行仍需执行载体。
* **subinterpreter 与 process**：subinterpreter 共享进程地址空间和部分 OS 资源；process 提供更强的内存、崩溃与权限隔离。
* **per-interpreter GIL 与 no-GIL**：前者仍保留 GIL，只是隔离解释器各自拥有；free-threaded/no-GIL 则允许同一解释器中的多个线程并行执行 Python 代码。
* **模块隔离与对象共享**：模块表按解释器分离不意味着任意 Python object 可以安全跨解释器共享。
* **标准库支持与第三方扩展支持**：Python 3.14 提供正式标准库入口，不代表所有 PyPI C 扩展已经满足多解释器隔离要求。
* **并行收益与通信成本**：CPU-heavy 独立任务更容易覆盖解释器创建、序列化和通信成本；细粒度高频交互可能失去优势。

本章结论
--------

Python 3.14 之后，subinterpreter 已从主要面向 C API 的 runtime 机制进入普通 Python 标准库：PEP 684 提供独立解释器与 per-interpreter GIL 的并行基础，PEP 734 的 ``concurrent.interpreters`` 提供高层管理入口，``InterpreterPoolExecutor`` 则把线程与独立解释器组合成可直接使用的并行执行模型。正确判断仍要围绕解释器隔离、数据传输、第三方扩展兼容与通信成本，而不是把“同一进程”误解成“任意对象都能共享”。