第067章：genobject.c and frameobject.c
======================================

核心知识点
----------

* ``Objects/genobject.c`` 组织 generator、native coroutine 和 async generator 的可恢复执行；``Objects/frameobject.c`` 与内部 frame 定义负责把执行现场暴露给 Python introspection。
* generator/coroutine function 调用先创建“可恢复执行对象”，函数体不会像普通函数那样立即完整运行。对象保存 code、执行 frame、状态和异常相关信息。
* 一个可恢复对象的稳定状态模型是 created → executing → suspended → executing → closed/cleared。执行中再次恢复同一个 generator 会触发 reentrancy 错误。
* ``yield`` 的核心是把本轮产出返回给驱动者，同时保留下一条指令位置、locals、value stack 和异常处理状态；下一次 ``send``/``next`` 从原暂停点继续。
* ``send(value)`` 会让前一次 ``yield`` 表达式求值得到 ``value``；生成器 ``return x`` 会结束执行，并把 ``x`` 放入 ``StopIteration.value``。
* ``throw`` 把异常注入暂停点；``close`` 通常注入 ``GeneratorExit``，从而让 ``finally`` 有机会执行。关闭不是简单丢弃 frame。
* coroutine object 与 generator 共用可暂停 frame 模型，但通过 awaitable 协议被驱动。``await`` 让当前 coroutine 暂停，并暴露当前等待对象；上层 Task/Future 在条件满足后恢复它。
* coroutine 完成后再次 await 会报错；创建后从未 await 的 coroutine 在 finalize 时可产生 RuntimeWarning。
* 内部 ``_PyInterpreterFrame`` 是解释器执行使用的轻量 frame；``PyFrameObject`` 是 Python 可见的 introspection 对象。现代 CPython 不要求每次函数调用都立刻物化完整 Python frame object。
* 暂停 frame 会保留 locals、value stack、instruction position、closure/await chain 等恢复材料，因此 generator/coroutine 本身会延长这些对象的生命周期。
* traceback、debugger、``inspect``、``gi_frame``、``cr_frame`` 等都可能让 frame 继续存活；frame 生命周期与函数返回时间不是严格等同关系。

关键路径
--------

generator：

::

    g = generator_function()
        ↓
    generator object + initial frame
        ↓
    state = CREATED
        ↓ next(g) / send(None)
    state = EXECUTING
        ↓
    ceval 执行到 YIELD
        ↓
    保存 instruction pointer + locals + stack
        ↓
    state = SUSPENDED
        ↓ send(value) / next / throw
    再次 EXECUTING
        ↓
    yield / return / exception

``send``：

::

    previous: received = yield output
                     ↓ suspend
    g.send(x)
        ↓
    x 放回暂停 frame
        ↓
    yield expression evaluates to x
        ↓
    received = x

coroutine / Task：

::

    coro = async_fn()
       ↓
    coroutine object
       ↓ create_task
    Task owns/drives coroutine
       ↓ step
    coroutine executes
       ↓ await pending Future
    coroutine suspended
       ↓ Future completes
    callback makes Task ready
       ↓ Task step
    coroutine resumes
       ↓ return / exception
    Task stores result / exception

frame 生命周期：

::

    code + globals + args
       ↓
    interpreter frame
       ↓
    fast locals / value stack / instruction pointer
       ↓
    running or suspended
       ↓
    return / exception / close
       ↓
    execution state cleared
       ↓
    PyFrameObject may still survive via traceback/introspection refs

概念辨析
--------

* generator function 不等于 generator object；前者是 function，调用后才得到后者。
* coroutine object 不等于 Task。Task 是调度和结果状态包装器，coroutine 是可恢复执行体。
* ``yield``/``await`` 暂停的是执行 frame，不是“线程保存了一行代码”。恢复需要完整 locals、栈和异常上下文。
* ``close``/cancel 不等于强制销毁 frame；它们通过异常/控制流让清理代码运行。
* ``gi_frame``/``cr_frame`` 是 introspection 视图，不应假定内部执行永远使用相同的公开 ``PyFrameObject`` 布局。
* frame 已结束不等于立刻释放；traceback、generator、debugger 或用户引用都可能继续持有它。
* ``StopIteration.value`` 是 generator ``return`` 的返回通道，不是一次 ``yield`` 的值。

本章结论
--------

生成器与协程的本质是“frame 可暂停并可恢复”。``genobject.c`` 管理对象状态、resume 输入、yield/return/exception/close，frame 则保存继续执行所需的真实现场。Task 只是把 coroutine 接入事件循环的驱动器。调试暂停执行时，应先看对象状态，再看当前 frame 和等待对象，最后看是谁负责下一次 resume。