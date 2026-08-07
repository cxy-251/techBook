第071章：importlib asyncio and contextlib
========================================

核心知识点
----------

* ``importlib``、``asyncio``、``contextlib`` 是标准库把底层 runtime 协议组织成工程抽象的典型案例：模块加载、可恢复执行和资源生命周期分别由明确的状态对象驱动。
* ``importlib`` 把模块名转换成 module object。核心对象是 ``sys.modules``、finder、``ModuleSpec``、loader、package ``__path__`` 和 module namespace。
* 动态导入先查 ``sys.modules``；miss 后 finder 产生 spec，loader 创建/取得 module，模块在执行前放入 cache，再执行顶层代码。这个顺序保证循环导入能看到同一 module identity。
* ``ModuleSpec`` 表达“如何加载”，module object 表达“加载和执行后的运行时状态”；二者不能混为一个对象。
* ``invalidate_caches()`` 清 finder 的发现缓存，不会清除已加载的 ``sys.modules``；``reload(module)`` 会重执行模块代码，但不会自动替换外部保存的旧函数/类引用。
* ``asyncio`` 的核心链是 coroutine → Task → event loop → Future/等待条件 → ready callback → resume。协作式并发来自 ``await`` 主动交回执行权。
* event loop 管理 ready callbacks、timer、I/O readiness 和 Task/Future 状态。Task 驱动 coroutine；Future 表达“尚未完成、稍后产生结果/异常”的状态槽。
* cancellation 是异常注入/状态传播，不是立即销毁 coroutine。``CancelledError`` 在可恢复点进入 coroutine，``finally``、``async with`` 和退出栈仍应获得 cleanup 机会。
* backpressure 必须有显式等待边界：queue capacity、stream ``drain``、semaphore 或协议 pause/resume 让生产者在下游容量不足时停止继续堆积。
* ``contextlib`` 把 ``__enter__/__exit__``、``__aenter__/__aexit__``、generator-based manager、``ExitStack`` 与 ``AsyncExitStack`` 统一为“获取成功后注册确定性退出动作”的模型。
* ``@contextmanager``/``@asynccontextmanager`` 的 ``yield`` 前是 acquire，``yield`` 后是 cleanup。异常会在退出阶段重新进入 generator，使 ``finally`` 能处理资源释放。
* ``ExitStack``/``AsyncExitStack`` 适合运行时数量不确定的资源。每获取一个资源立即注册 cleanup，退出时按 LIFO 逆序释放。
* 三个模块共同展示同一标准库设计方法：把复杂 runtime 行为封装成 protocol object + explicit state + deterministic lifecycle，而不是隐藏状态所有权。

关键路径
--------

``importlib.import_module``：

::

    fullname string
       ↓
    sys.modules lookup
       ├─ hit → return cached module
       └─ miss
            ↓
         resolve parent/package context
            ↓
         sys.meta_path finders
            ↓
         finder.find_spec(...)
            ↓
         ModuleSpec
            ↓
         loader.create_module / default module
            ↓
         insert sys.modules[fullname]
            ↓
         loader.exec_module(module)
            ↓
         bind child on parent package
            ↓
         return module object

``asyncio``：

::

    async function call
       ↓
    coroutine object
       ↓ create_task
    Task
       ↓ event loop step
    coroutine runs
       ↓ await pending object
    Task records waiter / coroutine suspended
       ↓
    Future / timer / I/O becomes ready
       ↓
    callback puts Task in ready queue
       ↓
    Task resumes coroutine
       ↓
    result / exception / cancellation

异步取消：

::

    task.cancel()
       ↓
    cancellation requested
       ↓ next resume point
    inject CancelledError
       ↓
    finally / async context cleanup
       ↓
    propagate or explicitly handle cancellation

``ExitStack``：

::

    enter resource A → register A.__exit__
        ↓
    enter resource B → register B.__exit__
        ↓
    register cleanup callback C
        ↓
    body
        ↓ normal / exception / cancel
    C cleanup
        ↓
    B.__exit__
        ↓
    A.__exit__

贯穿插件链：

::

    module name
       ↓ importlib
    module object
       ↓ fetch(session)
    coroutine object
       ↓ asyncio Task
    event loop execution
       ↓ await / result
    AsyncExitStack
       ↓
    session cleanup on every exit path

概念辨析
--------

* finder 负责发现，loader 负责创建/执行，``ModuleSpec`` 负责描述加载计划；三者职责不同。
* ``sys.modules`` cache 与 finder cache 不同；``invalidate_caches`` 不能替代 reload 或删除 module cache。
* import 成功不等于所有 API 存在；顶层执行完成后还可能在属性访问阶段失败。
* coroutine 是可恢复执行体，Task 是调度/结果包装器，Future 是异步结果状态；三者不能互换理解。
* ``async def`` 不自动产生并发；只有 coroutine 被驱动并在 ``await`` 处让出执行权，event loop 才能交错推进其它任务。
* cancellation 不是线程级强制终止；它必须走 coroutine 的异常和 cleanup 路径。
* context manager 解决的是确定性生命周期，不是垃圾回收。``with`` 退出与对象何时被 GC 是两种边界。
* ``ExitStack`` 是动态嵌套 ``with`` 的资源所有权结构，不是异常吞噬器；是否抑制异常取决于注册的 exit callback。

本章结论
--------

``importlib`` 用 finder/spec/loader 管理模块身份与加载状态，``asyncio`` 用 Task/Future/event loop 管理暂停和恢复，``contextlib`` 用 context protocol/exit stack 管理资源退出。三者表面是标准库 API，底层都遵循同一原则：显式保存状态、明确谁负责下一步、保证失败路径能收束。阅读复杂框架时，先找这些状态对象和所有者，通常比只看高层函数名更有效。