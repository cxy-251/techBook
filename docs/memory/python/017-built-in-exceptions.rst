第017章：内置异常
=================

核心知识点
----------

异常是运行时失败的类型化接口
   Python 抛出的对象必须派生自 ``BaseException``。异常对象拥有类型、参数、traceback、上下文和直接原因；``except`` 通过类型及其子类关系匹配处理器，因此异常设计本质上属于对象系统与控制流系统的交叉点。

``BaseException`` 与 ``Exception`` 划分控制信号和普通错误
   ``SystemExit``、``KeyboardInterrupt``、``GeneratorExit`` 直接位于 ``BaseException`` 分支，用于进程退出、用户中断和生成器关闭。业务代码通常捕获 ``Exception`` 或更具体类型，让这些控制信号继续传播。

异常类型应对应失败契约
   ``TypeError`` 表示对象类型、协议能力或参数形状不适合当前操作；``ValueError`` 表示类型可接受但具体值超出契约；``AttributeError`` 表示属性协议失败；``IndexError`` 与 ``KeyError`` 分别表示序列位置和映射键查找失败，并共同派生自 ``LookupError``。

资源和名字失败有独立异常族
   ``OSError`` 连接文件、socket、权限和路径等系统资源错误；``NameError`` 表示名字解析失败；``SyntaxError`` 发生在解析或编译阶段；``RuntimeError`` 用于没有更具体类别的运行时失败。选择异常类型时，应从失败操作而不是错误消息措辞出发。

迭代结束是一种协议信号
   iterator 通过 ``StopIteration`` 表示同步耗尽，async iterator 通过 ``StopAsyncIteration`` 表示异步耗尽。``for`` 与 ``async for`` 会把它们转换为循环正常结束；当它们穿出协议驱动层进入业务代码时，应判断是否需要翻译成领域错误。

生成器返回值通过结束异常传递
   generator 执行 ``return value`` 时，驱动方会在 ``StopIteration.value`` 中收到该值；``yield from`` 使用此机制收束子迭代器。生成器函数体意外抛出的 ``StopIteration`` 会依据 PEP 479 转换为 ``RuntimeError``，避免把内部错误误判为正常结束。

异常传播会形成 traceback
   异常沿调用栈向上查找匹配的 handler，每经过一个 frame 都会形成 traceback 节点。traceback 描述异常传播路径，异常消息只描述局部状态；排错时应优先读取最底层触发点和完整调用链。

异常链保留抽象层之间的因果关系
   处理一个异常时抛出另一个异常，会通过 ``__context__`` 保存隐式上下文；``raise NewError(...) from exc`` 通过 ``__cause__`` 指定直接原因；``raise ... from None`` 只隐藏展示链，不删除底层异常对象和真实因果。

重新抛出应保留原 traceback
   在 ``except`` 中使用裸 ``raise`` 会继续传播当前异常并保留原始 traceback。重新执行 ``raise exc`` 会增加新的抛出位置，改变可见路径。需要翻译异常时，应创建新异常并使用 ``from`` 连接原因。

异常组表达并发或聚合失败
   ``ExceptionGroup`` 与 ``BaseExceptionGroup`` 可以携带多个异常，``except*`` 按类型拆分匹配子异常。处理后未被消费的部分会重新组合并继续传播，适合任务组和批量操作同时失败的场景。

关键路径
--------

普通异常传播路径：

::

   操作破坏运行时契约
   → 创建或取得异常对象
   → 连接当前 traceback
   → 沿 frame 栈向上查找 except
   → 按异常类型和子类关系匹配
   → handler 恢复、翻译、重新抛出或结束传播

异常翻译路径：

::

   捕获底层具体异常
   → 判断当前抽象层能否恢复
   → 创建面向调用方的新异常
   → raise NewError(...) from original
   → 保留直接 cause 和原始 traceback
   → 上层只依赖稳定的领域异常接口

概念辨析
--------

* **``BaseException`` 与 ``Exception``**：前者覆盖全部异常和控制信号；后者是普通应用错误的公共根。
* **``TypeError`` 与 ``ValueError``**：前者表示对象或参数形状不适用，后者表示对象类型合适但值域不合法。
* **``KeyError`` 与 ``AttributeError``**：分别来自 mapping key lookup 和 attribute lookup，不能因名字相同而混用。
* **``StopIteration`` 与业务失败**：在 iterator 驱动层是正常结束信号，穿出协议边界后可能需要翻译成更明确的领域错误。
* **``__context__`` 与 ``__cause__``**：前者记录处理期间自动形成的上下文，后者由 ``raise ... from ...`` 显式指定。
* **裸 ``raise`` 与 ``raise exc``**：裸 ``raise`` 保留当前异常的原传播路径；后者从当前行再次抛出并改变 traceback。
* **异常抑制与异常恢复**：隐藏异常输出不等于系统恢复；恢复必须保证后续状态仍满足调用方契约。
* **异常类型与错误消息**：调用方应依赖稳定的类型层级和结构化属性，避免通过消息字符串做控制分支。

本章结论
--------

异常处理的核心不是“把错误抓住”，而是让失败类型、传播路径和恢复边界保持一致。评审代码时，应先确定失败属于哪种操作契约，再检查捕获范围、控制信号、traceback、异常链和状态恢复；只有当前层真正能够恢复或提供更稳定抽象时才处理异常，否则应保留完整因果继续传播。
