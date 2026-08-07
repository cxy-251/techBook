第029章：Callable Runtime
=========================

核心知识点
----------

* 一次 Python 调用的完整路径是：求值 callable → 求值实参 → 准备参数布局 → 调用协议 → 参数绑定 → frame/执行状态创建 → fast locals 初始化 → 执行目标代码。
* call expression 的 primary 必须先求值得到 callable object；函数、bound method、class、内建函数、实现 ``__call__`` 的实例都能进入调用协议。
* CPython 的传统 ``tp_call`` 使用 ``args`` tuple 和 ``kwargs`` dict；vectorcall 使用连续参数数组、位置参数数量和关键字名 tuple，减少调用路径中的临时容器分配。
* vectorcall 来自 PEP 590，属于 CPython 调用优化协议；优化的是参数传递表示，不改变 Python 层调用语义。
* bound method 调用包含两个阶段：属性访问先完成函数与实例绑定，调用协议随后把隐式 ``self`` 和显式实参一起传给函数。
* 参数绑定的本质是把调用处已经求值完成的对象引用填入函数签名的参数槽。
* 绑定顺序要区分 positional-only、positional-or-keyword、``*args``、keyword-only、``**kwargs`` 与默认参数。
* 默认参数对象在函数定义时求值并保存在 function object 上；调用时只是复用对象引用。
* 调用处的 ``*iterable`` / ``**mapping`` 是实参展开；函数定义里的 ``*args`` / ``**kwargs`` 是剩余参数收集，发生阶段不同。
* 用户定义 Python 函数完成参数绑定后，会准备新的执行 frame；C callable 可能直接进入 C 实现而不创建普通 Python 函数 frame。
* recursion 是同一调用机制的重复嵌套：每一层调用拥有独立参数绑定和局部状态，共享 function/code object。
* 调用错误要按阶段定位：属性读取失败、不可调用、参数绑定 ``TypeError``、frame/递归限制、函数体异常分别属于不同边界。

关键路径
--------

方法调用 ``service.quote(...)`` 的运行时路径：

::

   evaluate service.quote
       ↓
   attribute lookup + descriptor binding
       ↓
   obtain bound callable
       ↓
   evaluate every argument expression
       ↓
   expand *args / **kwargs at call site
       ↓
   vectorcall or tp_call
       ↓
   bind objects to formal-parameter slots
       ↓
   apply defaults / collect varargs / varkw
       ↓
   create callee frame when target is Python code
       ↓
   initialize fast locals
       ↓
   execute code object
       ↓
   return object or propagate exception

参数绑定检查顺序：

#. 先放入隐含接收者，例如 bound method 的 ``self``。
#. 位置参数按顺序填槽。
#. 关键字参数按名字填入未占用槽位。
#. 多余位置参数进入 ``*args``。
#. 多余关键字进入 ``**kwargs``。
#. 未填充槽位尝试使用默认对象。
#. 仍有缺失、重复或非法关键字则抛出 ``TypeError``。

概念辨析
--------

* **callable protocol 与 argument binding**：前者回答“这个对象怎样被调用”；后者回答“传入的对象怎样进入函数参数槽”。
* **``tp_call`` 与 vectorcall**：都是 CPython C 级调用入口；vectorcall 主要减少 tuple/dict 打包成本。
* **bound method 与普通 function**：bound method 已保存接收者关系；普通 function 调用时所有参数都需要调用方显式或协议隐式提供。
* **调用处 ``*``/``**`` 与定义处 ``*args``/``**kwargs``**：前者展开实参，后者收集绑定后的剩余实参。
* **默认参数与每次调用局部变量**：默认对象属于 function object 的长期状态；参数名属于每次新 frame 的局部绑定。
* **call stack 与 value stack**：call stack 连接多个调用 frame；value stack 处理一个 frame 内的表达式与调用参数临时对象。
* **递归与共享局部变量**：递归层共享代码，不共享同一组 fast-local 槽；每层 frame 都有自己的参数和局部状态。

本章结论
--------

Python 调用不是单一的“跳进函数体”，而是对象分派、参数表示、签名绑定和 frame 执行的组合路径。排查一次调用时，应先确认 callable 怎样产生，再看实参怎样求值与展开，随后确认 ``tp_call``/vectorcall 如何把对象送入被调用者，最后检查参数怎样落入 fast locals 以及目标是否进入新的 Python frame。