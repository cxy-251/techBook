第010章：属性查找系统
====================

核心知识点
----------

属性访问是一条有序决策链
   ``obj.name`` 不等于直接读取实例字典。默认读取会同时考虑对象类型的 MRO、descriptor、实例字典、普通类属性和访问钩子，再按优先级决定结果来源。

``__getattribute__`` 是实例读取入口
   普通实例属性读取都会先进入 ``object.__getattribute__`` 或其覆盖实现。自定义版本必须显式委托基类实现，否则容易绕过默认规则或因内部再次读取 ``self.attr`` 形成无限递归。

默认实例读取优先级固定
   先在类及 MRO 中寻找同名 data descriptor；再检查实例 ``__dict__``；随后处理 non-data descriptor；再返回普通类属性；全部失败后抛出 ``AttributeError``，外层点号表达式或 ``getattr`` 才会触发 ``__getattr__``。

类侧候选沿 MRO 查找
   查找类属性时不是只看 ``type(obj).__dict__``，而是沿 ``type(obj).__mro__`` 依次寻找第一个同名绑定。子类覆盖父类，本质上是同名键在 MRO 中更早命中。

实例字典可以遮蔽普通类属性
   类侧同名对象既不是 data descriptor，也没有更高优先级时，实例 ``__dict__`` 中的键会成为结果。直接读取 ``Class.attr`` 的接收者变成类对象，不再经过该实例字典。

Descriptor 决定实例与类属性的竞争关系
   data descriptor 优先于实例字典，non-data descriptor 低于实例字典。``property`` 常作为 data descriptor 接管读取和写入；普通函数是 non-data descriptor，会在实例没有同名键时绑定成 method。

``__getattr__`` 只负责失败兜底
   它不会参与已经成功的常规查找，适合延迟字段、代理对象和兼容层。其返回值会成为属性结果；再次抛出 ``AttributeError`` 才表示属性最终不存在。

写入和删除有独立入口
   ``obj.name = value`` 进入 ``__setattr__``，``del obj.name`` 进入 ``__delattr__``。默认路径会先考虑 data descriptor 的 ``__set__`` 或 ``__delete__``，否则再更新或删除实例状态。

方法绑定属于属性系统
   类字典中的函数被实例读取时，函数 descriptor 返回保存 ``__func__`` 与 ``__self__`` 的 bound method；通过类读取时通常返回原函数，调用方需要显式传入实例。

隐式特殊方法查找另走类型路径
   ``len(obj)``、运算符和迭代语法通常绕过实例普通属性链。自定义 ``__getattribute__`` 能观察 ``obj.__len__``，不代表能接管 ``len(obj)`` 的协议分发。

CPython 会缓存高频属性读取
   ``LOAD_ATTR`` 等执行路径可以依据类型、字典形态、descriptor 和版本状态专门化。类结构、实例字典或 descriptor 行为变化后，缓存必须失效或退化，最终语义仍服从完整查找顺序。

关键路径
--------

普通实例属性读取：

::

   obj.name
   → 调用 type(obj) 提供的 getattribute 入口
   → 沿 type(obj).__mro__ 查找类侧候选
   → 若为 data descriptor，调用 __get__ 并返回
   → 否则检查实例 __dict__
   → 若命中实例键，返回实例值
   → 否则若为 non-data descriptor，调用 __get__
   → 否则返回普通类属性
   → 全部失败时抛出 AttributeError
   → 外层触发 __getattr__ 兜底

属性写入：

::

   obj.name = value
   → 调用 __setattr__
   → 沿类 MRO 查找同名 data descriptor
   → 若存在 __set__，交给 descriptor
   → 否则更新实例存储
   → 更新相关字典版本与运行时缓存状态

概念辨析
--------

* **实例属性与类属性**：实例属性属于单个对象；类属性沿 MRO 共享。实例键只能遮蔽优先级较低的类侧候选。
* **``__getattribute__`` 与 ``__getattr__``**：前者是所有普通读取的入口；后者只在前者以 ``AttributeError`` 失败后兜底。
* **data descriptor 与 non-data descriptor**：前者提供 ``__set__`` 或 ``__delete__``，优先于实例字典；后者通常只有 ``__get__``，可被实例键遮蔽。
* **函数与 bound method**：类字典保存 function object；实例读取后得到绑定实例的 method object。
* **shadowing 与 mutation**：shadowing 只改变查找结果来源，不会删除被遮蔽的类属性；修改类字典则会改变整个类族后续查找。
* **普通属性与隐式协议**：``obj.method`` 走完整属性链；语法和内置函数触发的 special method 常直接从类型层查找。
* **缓存与查找规则**：缓存是查找结果的加速层，不是新的语义来源；任何失配都必须回退到通用路径。

本章结论
--------

定位属性问题时，应先确认接收者是实例还是类对象，再沿 MRO 找到类侧候选，判断 descriptor 类型，随后检查实例字典和访问钩子；只有把查找优先级、绑定行为和缓存失效分开，才能准确解释同名属性为何来自不同对象层级。
