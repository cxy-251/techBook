第018章：核心协议
=================

核心知识点
----------

协议把语法动作转换成对象能力
   ``for obj``、``obj[key]``、``obj + other``、``obj()``、``with obj``、``await obj`` 和 ``memoryview(obj)`` 都会请求对象类型提供特定协议。语法只决定入口，类型上的 special method 或 CPython slot 决定实际行为。

隐式协议查找以类型为中心
   许多 special method 的隐式调用不会把实例字典作为主要入口。给单个实例赋值 ``obj.__len__``、``obj.__call__`` 或 ``obj.__add__``，通常不能改变 ``len(obj)``、``obj()`` 或 ``obj + x`` 的结果；稳定协议必须定义在类型上。

容器能力由多组协议共同组成
   ``__len__`` 表示规模并参与 truth testing；``__iter__`` 返回 iterator；``__getitem__`` 定义索引或键读取；``__contains__`` 定义成员测试。缺少直接入口时，运行时可能使用迭代或旧式序列 fallback。

sequence 与 mapping 使用相同语法但语义不同
   ``obj[key]`` 都进入 subscription 协议。sequence 通常接受整数和 ``slice``，越界使用 ``IndexError``；mapping 接受 hashable key，缺失使用 ``KeyError``。类型作者必须明确 key 范围、异常类型和遍历含义。

二元运算需要正向、反向和原地分发
   ``__add__`` 等正向方法先获得处理机会；返回 ``NotImplemented`` 后，解释器可以尝试 ``__radd__`` 等反向方法；``__iadd__`` 等原地方法优先用于增强赋值，失败后再回退普通二元运算。

``NotImplemented`` 是协议协商值
   它表示当前方法无法处理这组操作数，允许解释器继续尝试另一侧或 fallback。它不是异常、``None`` 或布尔假值；双方均无法处理时，运行时才形成 ``TypeError``。

调用协议让对象表现为行为入口
   类型定义 ``__call__`` 后，实例可使用括号调用。CPython 可通过 ``tp_call`` 或 vectorcall 进入执行路径；语义层仍要完成参数求值、参数绑定、函数体执行和异常传播。

descriptor 协议改变属性读取结果
   类属性对象定义 ``__get__``、``__set__`` 或 ``__delete__`` 后，可以接管实例属性访问。普通函数就是 non-data descriptor，实例读取类函数时先生成 bound method，再由调用协议执行。

context manager 把资源生命周期绑定到代码块
   ``__enter__`` 与 ``__exit__`` 管理同步进入和退出，``__aenter__`` 与 ``__aexit__`` 管理异步进入和退出。退出方法接收异常信息，并通过返回值决定异常是否继续传播。

异步协议围绕可挂起状态推进
   ``__await__`` 返回 iterator，``__aiter__`` 返回 async iterator，``__anext__`` 返回 awaitable，并以 ``StopAsyncIteration`` 表示耗尽。协议只规定暂停、恢复和结束表面，调度顺序由事件循环或异步框架负责。

buffer 协议暴露二进制内存视图
   ``memoryview(obj)`` 请求对象提供 buffer，使消费者可在减少复制的情况下读取或修改底层内存。shape、format、itemsize、readonly 和生命周期属于协议的一部分，不能把任意 bytes-like 对象都当作无约束的字节数组。

关键路径
--------

通用协议分发路径：

::

   求值语法中的对象
   → 取得对象实际类型
   → 定位对应 special method 或类型 slot
   → 调用协议实现
   → 校验返回对象与异常是否符合契约
   → 返回结果、执行 fallback 或结束控制流

方法调用路径：

::

   obj.method
   → 属性查找定位类中的函数 descriptor
   → descriptor 生成 bound method
   → 括号触发 callable protocol
   → 绑定 self 与显式参数
   → 执行函数并返回结果

概念辨析
--------

* **协议与继承**：协议关心类型是否提供约定行为；继承只描述类型关系，二者可以重合，也可以通过 duck typing 分离。
* **显式 special method 调用与隐式语法调用**：``obj.__len__()`` 是普通属性访问后的调用，``len(obj)`` 是类型级协议分发。
* **sequence 与 mapping**：前者强调位置和顺序，后者强调 key 到 value 的映射；相同下标语法不代表相同契约。
* **``NotImplemented`` 与 ``TypeError``**：前者把决定权交还给解释器继续分发，后者表示当前操作已经失败。
* **callable 与函数**：函数是 callable 的一种；类、bound method 和实现 ``__call__`` 的实例同样可参与调用协议。
* **descriptor 与普通类属性**：descriptor 在属性查找时主动生成结果，普通类属性只作为值参与查找顺序。
* **context manager 与析构**：context manager 通过控制流保证确定性退出，析构和垃圾回收只处理对象生命周期，时机不稳定。
* **awaitable 与 task**：awaitable 描述可被 ``await`` 驱动的对象，task 是调度框架用于管理协程执行和结果的更高层对象。
* **buffer 与序列协议**：buffer 描述内存布局和共享访问，序列协议描述逻辑元素访问；二者不等价。

本章结论
--------

阅读 Python 运行时行为时，应先把语法还原成协议请求，再沿对象类型、special method、slot、返回值和 fallback 检查完整路径。一个可靠类型不是“实现了许多双下划线方法”就足够，而是每个方法的状态、返回值、异常和彼此关系共同组成一致契约，使对象在容器、运算、调用、资源、异步和内存场景中都保持可预测行为。
