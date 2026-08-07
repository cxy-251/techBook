第011章：描述符协议
==================

核心知识点
----------

Descriptor 是类属性参与访问的协议
   一个对象作为 owner class 的类属性出现，并且其类型实现 ``__get__``、``__set__`` 或 ``__delete__`` 中至少一个方法时，它会在属性读取、写入或删除过程中接管结果生成。

协议入口对应三种属性动作
   ``__get__(self, instance, owner)`` 处理读取，``__set__(self, instance, value)`` 处理写入，``__delete__(self, instance)`` 处理删除。这里的 ``self`` 是 descriptor 对象，``instance`` 是访问实例，``owner`` 是拥有该属性的类。

Descriptor 必须位于类及其 MRO 中
   把实现 ``__get__`` 的对象放入实例 ``__dict__`` 不会自动触发协议。解释器先从类型的 MRO 找到类侧对象，再判断其类型是否实现 descriptor 方法。

类访问与实例访问参数不同
   ``obj.attr`` 调用 descriptor 时传入真实实例；``Class.attr`` 通常传入 ``instance=None``。Descriptor 可以在类访问时返回自身、配置对象或其它类级视图。

``__set_name__`` 提供声明位置
   类创建时，``type.__new__`` 会把 owner class 和类字典中的属性名通知给定义了 ``__set_name__`` 的对象。它不是 descriptor 判定条件，但适合生成私有存储名和记录字段元数据。

Data descriptor 优先于实例字典
   只要 descriptor 类型提供 ``__set__`` 或 ``__delete__``，它就是 data descriptor。实例读取同名属性时，即使实例 ``__dict__`` 中已有同名键，data descriptor 仍先执行。

Non-data descriptor 可被实例键遮蔽
   只实现 ``__get__`` 的对象属于 non-data descriptor。实例字典中的同名键优先返回，因此它适合提供默认计算行为，同时允许单个实例覆盖。

只读属性仍可设计为 data descriptor
   Descriptor 可以实现 ``__set__`` 并主动抛出 ``AttributeError``。这样既阻止写入，又保持高于实例字典的读取优先级；没有 setter 的 ``property`` 就体现了这一设计。

普通函数是 non-data descriptor
   函数存入类字典后，实例读取会调用函数的 ``__get__``，生成保存原函数和实例的 bound method。``method.__func__`` 指向函数，``method.__self__`` 指向实例，调用时实例被自动放到第一个实参位置。

``property`` 管理实例属性协议
   ``property`` 用 ``fget``、``fset`` 和 ``fdel`` 把读取、写入、删除映射到函数，通常属于 data descriptor。它适合校验、计算、兼容迁移和受控存储。

``classmethod`` 与 ``staticmethod`` 改变函数绑定
   ``classmethod`` 返回绑定 owner class 的 method，实例和类访问都把类作为第一个参数；``staticmethod`` 返回原始可调用对象，不自动绑定实例或类。

直接读取类字典会绕过协议
   ``vars(Class)["attr"]`` 或 ``Class.__dict__["attr"]`` 取得存放在类 namespace 中的原始 descriptor 对象，不会执行 ``__get__``，适合调试协议本体。

关键路径
--------

Descriptor 读取优先级：

::

   obj.attr
   → 沿 type(obj).__mro__ 查找 attr
   → 若候选为 data descriptor，调用 desc.__get__(obj, type(obj))
   → 否则检查 obj.__dict__
   → 若实例键存在，返回实例值
   → 否则若候选为 non-data descriptor，调用 desc.__get__(obj, type(obj))
   → 否则返回普通类属性
   → 未命中时进入 AttributeError 与 __getattr__ 路径

方法绑定：

::

   实例读取类中的 function object
   → function.__get__(instance, owner)
   → 生成 bound method
   → method 保存 __func__ 与 __self__
   → 调用 method(args)
   → 等价调用 function(instance, args)

概念辨析
--------

* **Descriptor 对象与实例字段值**：descriptor 通常存放在类字典中，真实业务值可以存放在实例字典的另一私有键中。
* **data 与 non-data descriptor**：分类依据是 descriptor 类型是否提供 ``__set__`` 或 ``__delete__``，不是当前对象是否实际允许写入。
* **类访问与实例访问**：类访问的 ``instance`` 为 ``None``；实例访问会传入具体对象并可能执行绑定或读取实例状态。
* **函数与方法**：函数是类 namespace 中的 descriptor；bound method 是一次实例属性读取生成的绑定对象。
* **``property`` 与手写访问钩子**：``property`` 只管理指定类属性；``__getattribute__`` 和 ``__setattr__`` 会影响更广泛的对象访问路径。
* **``classmethod`` 与 ``staticmethod``**：前者绑定类，后者不绑定任何接收者；二者都不是普通实例方法。
* **``__set_name__`` 与动态赋值**：类创建时自动调用；类创建后再赋值 descriptor 时不会自动补调，必须显式处理。

本章结论
--------

设计或排查托管属性时，应先确认 descriptor 存放在哪个类、实现了哪些协议方法、真实数据存放在哪里，再按 data descriptor、实例字典、non-data descriptor 的顺序判断；Python 的方法、property 和多种类级包装器，本质上都建立在同一套属性协议之上。
