第055章：Concurrency Abstraction
================================

核心知识点
----------

* concurrency 表示多个任务可以交错推进；parallelism 表示多个执行单元同时占用多个 CPU core。两者不是同一个概念。
* 在默认 CPython GIL build 中，多个线程可以并发等待，但同一 interpreter 内纯 Python bytecode 通常不能靠线程获得多核并行。
* ``threading`` 适合 I/O-bound 或会释放 GIL 的 native 工作；线程共享进程内对象，因此通信便宜，同时需要显式同步共享状态。
* ``Thread`` 生命周期是 create → start → run → terminate → join；后台线程必须有 owner、停止信号、异常处理和 join 责任。
* ``threading.Lock``、``RLock``、``Condition``、``Event``、``Semaphore``、``Barrier`` 表达不同同步关系；它们保护的是业务不变量，不是“让代码自动线程安全”。
* ``queue.Queue`` 把共享状态封装成线程安全 producer/consumer 通道，``maxsize`` 还能形成 backpressure。
* ``threading.local`` 给不同线程提供同名但独立的线程私有状态，适合连接、临时上下文和每线程缓存。
* ``multiprocessing`` 把边界提升到进程：每个进程有独立地址空间、解释器和 GIL，因此纯 Python CPU-bound 工作可以真正多核并行。
* 进程间 Queue/Pipe 传递的是序列化后的内容，不是同一 Python object reference；pickleability、复制成本和对象身份都成为边界。
* ``spawn``、``fork``、``forkserver`` 的启动语义不同；可移植代码应避免依赖 fork 继承复杂线程/锁状态，并把 worker callable 放在可导入位置。
* ``asyncio`` 使用单线程 event loop + coroutine/Task/Future 的 cooperative scheduling；并发发生在 ``await`` 等 suspension boundary。
* coroutine 中直接执行阻塞 I/O 或长 CPU 循环会卡住 event loop；阻塞函数应移交线程，CPU-heavy 工作常移交进程或 native executor。
* ``asyncio.Queue``、Lock、Semaphore 等原语只服务 event-loop task，不是线程同步原语。
* ``concurrent.futures`` 用统一 Future/Executor API 封装线程池与进程池；``submit`` 返回 Future，结果、异常和取消通过同一对象传播。
* ``ThreadPoolExecutor`` 适合隐藏阻塞等待；``ProcessPoolExecutor`` 适合可序列化的 CPU-bound callable；池化减少重复创建 worker 的成本。
* Future 的 completion、result、exception、cancelled 是任务状态接口；取消只对尚未开始或支持协作取消的工作有明确效果，不能假设任意运行中线程会被强制终止。
* 并发设计必须同时闭合任务提交、结果回收、异常传播、取消、backpressure、shutdown 和资源释放；只“启动更多 worker”不是完整架构。
* free-threaded Python、per-interpreter GIL 和 native code 会改变具体并行边界，因此选择前要先确认解释器 build 和热点代码真实执行位置。

关键路径
--------

线程路径：

::

   main thread
       ↓
   create Thread / ThreadPool task
       ↓
   OS thread runs callable
       ↓
   blocking I/O releases/waits
       ↓
   shared Python objects
       ↓
   Lock / Queue / Event synchronize
       ↓
   callable returns / raises
       ↓
   join / Future.result

进程路径：

::

   parent process
       ↓
   submit serializable callable + args
       ↓
   pickle / IPC boundary
       ↓
   worker process + independent interpreter
       ↓
   execute CPU work on another core
       ↓
   serialize result / exception
       ↓
   parent Future / Queue receives value
       ↓
   shutdown / join workers

asyncio 路径：

::

   coroutine object
       ↓
   create Task
       ↓
   event loop drives Task
       ↓
   await pending I/O / Future / Queue
       ↓
   Task suspended
       ↓
   loop advances other ready work
       ↓
   awaited condition completes
       ↓
   Task resumes
       ↓
   result / exception / cancellation

Executor 选择路径：

::

   identify workload
       ↓
   mostly blocking wait? ── yes ──> ThreadPoolExecutor
       │
       no
       ↓
   mostly Python CPU? ── yes ──> ProcessPoolExecutor / subinterpreter / free-threaded strategy
       │
       no
       ↓
   async-native I/O? ── yes ──> asyncio
       ↓
   inspect native library GIL behavior and data-sharing cost

概念辨析
--------

* **thread 与 process**：thread 共享对象和地址空间；process 通过 IPC 传递数据并拥有独立 interpreter 状态。
* **threading 与 asyncio**：thread 由 OS 调度；asyncio Task 在一个 event loop 内协作切换。
* **并发与并行**：大量任务同时进行不代表同时执行 Python CPU 指令。
* **GIL 与业务锁**：GIL 是 CPython runtime 约束；业务共享状态仍需要 Lock/Queue 等明确协议。
* **线程 Queue 与进程 Queue**：前者传对象引用，后者通常经过序列化边界。
* **coroutine 与 Task**：coroutine 是可暂停执行体；Task 是 event loop 对 coroutine 的调度和完成状态包装。
* **Future 与 worker**：Future 是结果/异常状态句柄，不是线程或进程本身。
* **取消与强杀**：Task cancel、Future cancel 多为请求/状态转换，不等于安全地强制终止任意运行中代码。
* **backpressure 与限流**：backpressure 让下游容量限制上游提交；Semaphore 主要限制并发数量，两者目标相关但不完全相同。

本章结论
--------

Concurrency abstraction 可以压缩为“先识别等待还是计算，再决定共享内存、进程隔离或 event-loop 协作，最后用 Future/Queue/同步原语闭合状态传播”。I/O-bound 优先考虑线程或 async-native I/O，纯 Python CPU-bound 在默认 GIL build 下优先考虑进程等真正并行边界。任何方案都必须同时设计结果、异常、取消、backpressure 和 shutdown，才能形成完整的并发运行时模型。