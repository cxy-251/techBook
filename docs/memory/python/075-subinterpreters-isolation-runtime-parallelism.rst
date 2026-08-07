第075章：Subinterpreters, Isolation, and Runtime Parallelism
============================================================

核心知识点
----------

* subinterpreter 在同一 OS process 内创建另一套 Python runtime state。它主要隔离 Python 级模块、builtins、import state、异常状态和对象图，不等同于进程级安全隔离。
* CPython 中 interpreter 的核心对象是 ``PyInterpreterState``，执行线程通过 ``PyThreadState`` 绑定到某个 interpreter。
* process 级资源仍然共享，包括地址空间、文件描述符、环境变量、当前工作目录、动态库和 native 全局状态。
* per-interpreter GIL 把锁的保护范围从进程级收缩到 interpreter 级。多个 OS thread 分别运行不同 interpreter，才有机会真正并行执行 Python bytecode。
* “创建多个 interpreter”本身只建立隔离；并行执行仍需要多个 thread 或其它执行单元。
* 大多数普通 Python 对象不应直接跨 interpreter 共享。跨边界时优先传递简单不可变值、复制/序列化数据，或使用专门支持的 cross-interpreter communication primitive。
* 跨 interpreter 传递时要区分 value 与 identity。接收端通常得到一份可使用的数据表示，不会自动获得发送端原对象的 identity、引用图和可变状态。
* C 扩展是多解释器兼容性的关键风险。使用 C ``static`` 全局变量会把状态放到 process 级；更稳妥的方向是 multi-phase initialization、per-module state、heap type，以及明确的 process-global 锁。
* per-interpreter GIL 破坏了“进程内所有 Python 对象都由同一把 GIL 保护”的历史假设。扩展模块要明确对象属于哪个 interpreter、状态属于哪个 module instance、锁属于哪个层级。
* message passing 是默认更清晰的设计：输入输出使用小而明确的数据协议，资源句柄和复杂共享状态留在宿主侧，通过 queue/channel/host callback 协调。
* subinterpreter 适合 CPU 工作足够粗粒度、通信面较小、隔离有价值且依赖库兼容的场景；不应把它当成进程级崩溃隔离或安全沙箱。

关键路径
--------

.. code-block:: text

   OS process
      ├─ process resources
      ├─ thread A → PyThreadState A → Interpreter 0
      └─ thread B → PyThreadState B → Interpreter 1

   Interpreter 0
      ├─ sys.modules
      ├─ builtins
      ├─ import state
      └─ Python object graph

   Interpreter 1
      ├─ independent sys.modules
      ├─ independent builtins
      ├─ independent import state
      └─ independent Python object graph

两个 interpreter 之间的数据路径应显式化：

.. code-block:: text

   sender object/value
        ↓
   supported shared value
      or serialization/copy
      or cross-interpreter queue
        ↓
   transfer boundary
        ↓
   receiver-side value/object

判断能否获得并行收益时，按下面顺序：

#. 确认任务运行在不同 interpreter。
#. 确认它们由不同 OS thread 同时推进。
#. 确认 interpreter 使用各自的 GIL/执行保护。
#. 计算任务粒度是否覆盖数据传输成本。
#. 检查 C 扩展、多解释器状态和 process-global native 状态是否兼容。

概念辨析
--------

**subinterpreter 与 process**
   subinterpreter 共享进程地址空间和 OS 资源；process 拥有独立地址空间和更强故障/安全隔离。

**subinterpreter 与 thread**
   interpreter 是 Python runtime state 边界；thread 是 OS 调度执行单元。二者通常组合使用。

**per-interpreter GIL 与 no-GIL**
   per-interpreter GIL 表示每个 interpreter 仍有自己的 GIL；free-threaded 则允许同一 interpreter 内多个线程并行执行 Python 代码。

**数据复制与对象共享**
   复制保留值语义而失去 identity；真正共享需要运行时专门支持同步与生命周期。

**Python 模块隔离与 native 全局状态**
   ``sys.modules`` 可以按 interpreter 隔离，C 静态变量默认仍属于整个进程。

本章结论
--------

Subinterpreter 的稳定模型是“同进程、独立 Python runtime state、显式通信”。隔离边界主要落在 ``PyInterpreterState`` 和对象图，进程资源仍共享；并行来自不同 OS thread 驱动不同 interpreter。工程设计应优先缩小跨 interpreter 数据面，并把 C 扩展状态、对象 ownership 和通信协议写成明确边界。
