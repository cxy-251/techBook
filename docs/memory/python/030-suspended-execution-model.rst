第030章：Suspended Execution Model
==================================

核心知识点
----------

* generator 把一次函数执行拆成多次“恢复—运行—挂起”，核心变化是 frame lifetime，而不是对象模型被替换。
* 调用 generator function 时先创建 generator object，函数体尚未执行；第一次 ``next()`` 或 ``send(None)`` 才真正进入 frame。
* ``yield`` 同时是输出点和挂起点：向调用方产出对象，并保存当前 instruction position、locals 与继续执行所需状态。
* generator object 是外部驱动入口；suspended frame 是被保存的执行现场。
* 可观察状态通常包括 created、running、suspended、closed；同一 generator 在 running 状态下不能重入。
* ``next(g)`` 与 ``g.send(None)`` 可以启动新生成器；生成器已经挂起后，``send(value)`` 会让上一次 ``yield`` 表达式求值为该 value。
* ``throw(exc)`` 把异常注入当前挂起点，生成器内部可以捕获、继续 yield，或让异常向外传播。
* ``close()`` 在挂起点注入 ``GeneratorExit``，用于触发 ``finally``、context cleanup 和资源释放；关闭后生成器不能重新恢复。
* generator ``return value`` 会通过 ``StopIteration.value`` 传递给驱动方或 ``yield from`` 委托者。
* ``yield from`` 是完整的迭代/生成器委托协议，不只转发普通 ``yield`` 值，还处理 ``send``、``throw``、``close``、异常与子生成器返回值。
* suspended generator 会继续持有 frame 内局部对象，因此惰性执行也意味着对象生命周期被延长。
* generator 与 coroutine 都属于可暂停执行模型；coroutine 在此基础上增加 awaitable 约束与调度器关系。

关键路径
--------

普通 generator 生命周期：

::

   call generator function
       ↓
   create generator object
       ↓
   state = CREATED
       ↓ next() / send(None)
   enter generator frame
       ↓
   execute until yield
       ↓
   return yielded object to caller
       ↓
   save locals + instruction position + required stack state
       ↓
   state = SUSPENDED
       ↓ next/send/throw
   resume same frame
       ↓
   yield again / return / exception / close
       ↓
   state = CLOSED

``incoming = yield total`` 的双向关系：

#. 第一次执行到 ``yield total`` 时，``total`` 向外成为 ``next()``/``send()`` 的返回值。
#. frame 停在该 ``yield`` 表达式。
#. 下一次 ``send(value)`` 恢复时，刚才的 ``yield total`` 表达式在生成器内部得到 ``value``。
#. 该值再绑定给 ``incoming``，函数继续向下运行。

``yield from child()`` 的委托路径：

::

   caller → parent generator → yield from → child iterator/generator
                              ↑              ↓
                     child return value ← StopIteration.value

概念辨析
--------

* **generator function 与 generator object**：前者是函数定义；后者是某一次可暂停调用的运行时对象。
* **generator object 与 frame**：generator object 提供协议入口并拥有生命周期；frame 保存真正的局部变量、执行位置和求值状态。
* **``yield`` 与 ``return``**：``yield`` 暂停并保留执行现场；``return`` 结束 frame，并把可选返回值包装进 ``StopIteration.value``。
* **``next`` 与 ``send``**：``next(g)`` 等价于“无值恢复”；``send(value)`` 还会给上一个 ``yield`` 表达式注入一个普通值。
* **``throw`` 与普通 raise**：``throw`` 由外部驱动者把异常注入挂起点；普通 ``raise`` 是生成器内部主动触发异常。
* **``close`` 与对象销毁**：``close`` 是显式关闭协议；对象最终被 GC 回收属于生命周期管理，两者不是同一个事件。
* **``yield from`` 与 ``for ... yield``**：后者只转发普通产出；``yield from`` 定义了完整委托协议及子生成器返回值传递。
* **generator 与线程**：generator 是单 frame 的协作式暂停/恢复，不提供线程级并行或抢占执行。

本章结论
--------

生成器的核心不是“一个函数返回很多次”，而是“一个 frame 可以被对象持有并在明确挂起点恢复”。Generator object 负责接收 ``next``、``send``、``throw``、``close``，frame 保存真正的 execution continuation；``yield from`` 再把这套驱动协议完整地委托给子迭代器。理解 generator 时，应始终沿“谁拥有 frame、当前停在哪里、下一次恢复向 frame 注入什么、结束时怎样清理”追踪。