第021章：调用、上下文、异步与缓冲区协议
========================================

核心知识点
----------

协议把语法位置变成运行时能力请求
   ``obj(...)``、``with obj``、``await obj``、``async for item in obj`` 和 ``memoryview(obj)`` 分别请求调用、资源管理、可等待、异步迭代和缓冲区能力。判断失败时，应先定位具体语法入口，再检查对象类型提供了哪个协议。

调用表达式面向对象类型
   函数、类、bound method、C 扩展 callable 和定义 ``__call__`` 的实例都能参与调用协议。给单个实例添加 ``__call__`` 属性通常只能改变 ``obj.__call__()``，不能让缺少类型级调用入口的 ``obj()`` 成功。

调用前先完成参数求值
   解释器先求值被调用对象、位置参数和关键字参数，再进入 callable 的参数绑定和执行路径。参数求值期间出现的异常发生在被调用函数体之前，不能归因于 callee 内部逻辑。

bound method 包含绑定与调用两个阶段
   ``obj.method(arg)`` 先通过属性查找和函数 descriptor 生成绑定了 ``obj`` 的 method，再把显式参数提交给调用协议。调试时应区分属性定位、方法绑定、参数绑定和函数体执行。

vectorcall 是 CPython 的调用优化表面
   传统 ``tp_call`` 常使用 tuple 和 dict 表达参数，vectorcall 使用数组和关键字名结构减少临时对象。它改变内部传参成本，不改变 Python 层的求值顺序、绑定规则、返回值和异常语义。

context manager 管理成对状态变化
   ``with`` 使用 ``__enter__`` 和 ``__exit__``，把资源建立、body 使用、退出清理和异常策略绑定到同一作用域。``__enter__`` 的返回值决定 ``as`` 目标，manager 与 body 使用的资源对象不必相同。

退出方法决定异常是否继续传播
   body 正常结束时，``__exit__`` 接收三个 ``None``；异常退出时接收异常类型、对象和 traceback。返回真值表示异常已在边界内处理，返回假值表示异常继续向外传播。清理职责与异常抑制职责应分开设计。

async context manager 允许进入和退出挂起
   ``async with`` 使用 ``await __aenter__()`` 和 ``await __aexit__()``，适合连接、异步锁和远程 session。body 中的异常与取消都会进入异步退出路径，退出逻辑必须考虑自身再次被取消的边界。

awaitable 描述可被驱动的暂停对象
   coroutine object 天然可等待，自定义对象可通过 ``__await__`` 返回 iterator。调用 ``async def`` 只创建 coroutine object，函数体在被 await、封装为 task 或底层驱动后才开始执行。

coroutine 是一次性执行对象
   同一个 coroutine object 完成后不能再次 await；需要重复异步操作，应再次调用 async function 创建新 coroutine，或使用可重复产生结果的更高层对象。

async iterator 分离取得迭代器和推进元素
   ``__aiter__`` 返回 async iterator，``__anext__`` 返回 awaitable；awaitable 完成后给出元素，耗尽时抛出 ``StopAsyncIteration``。``async for`` 会消费该信号并正常结束。

buffer 协议暴露结构化内存
   ``memoryview(obj)`` 请求 exporter 提供底层内存描述，包括元素格式、维度、shape、strides、itemsize、只读状态和连续性。consumer 获得的是视图，不必复制整块数据。

零复制依赖生命周期与布局契约
   view 存活期间，exporter 必须保持底层内存有效；可写 view 还要求双方遵守修改规则。非连续、多维或带格式的 buffer 不能总被当作普通 ``bytes`` 使用，consumer 应检查布局能力。

关键路径
--------

异步流处理路径：

::

   调用 factory(...) 创建资源管理对象
   → async with 请求 __aenter__
   → await 进入操作并绑定 stream
   → async for 请求 __aiter__
   → 重复 await __anext__
   → 得到 chunk 或 StopAsyncIteration
   → memoryview(chunk) 请求 buffer
   → 调用 sink(view)
   → await __aexit__ 完成异步收束

同步 context manager 路径：

::

   求值 manager
   → 取得 enter 与 exit 能力
   → 调用 __enter__ 并绑定 as 目标
   → 执行 body
   → 调用 __exit__ 接收正常或异常状态
   → 根据返回值继续或抑制异常
   → 完成资源退出

概念辨析
--------

* **callable object 与 function object**：函数只是 callable 的一种；类和携带状态的实例同样可以通过统一括号语法执行。
* **``obj.__call__()`` 与 ``obj()``**：前者是显式属性访问后的普通调用，后者使用类型级特殊调用协议。
* **manager 与 ``as`` 目标**：manager 控制生命周期，进入方法返回给 body 的对象可以是资源、代理或其它句柄。
* **清理与异常抑制**：退出方法应可靠清理；只有明确恢复了系统状态时才返回真值抑制异常。
* **coroutine 与 task**：coroutine 是可等待的执行对象，task 是事件循环对 coroutine 的调度、状态和结果管理包装。
* **awaitable 与 async iterator**：前者表示一次可暂停计算，后者通过多次 ``__anext__`` 产生元素序列。
* **``StopIteration`` 与 ``StopAsyncIteration``**：分别结束同步和异步迭代，不能交叉使用。
* **buffer exporter 与 consumer**：exporter 提供内存和布局，consumer 通过 view 读取或修改；双方共享生命周期和格式约束。
* **``memoryview`` 与数据复制**：view 通常避免完整复制，但切片、转换、强制连续化或格式变换仍可能创建新数据。
* **vectorcall 与语言调用语义**：vectorcall 优化 CPython 内部参数传递，不是新的 Python 调用规则。

本章结论
--------

调用、上下文、异步和 buffer 协议共同体现了 Python 的对象能力模型：语法只发出请求，类型负责交付可验证的对象、状态和结束信号。评审这类代码时，应逐层确认调用参数、资源所有权、暂停点、取消路径、迭代耗尽、异常传播以及内存视图生命周期；任何一层协议返回错误对象或模糊状态，都会在下一层以难以定位的方式失败。
