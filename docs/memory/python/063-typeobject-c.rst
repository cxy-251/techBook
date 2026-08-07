第063章：typeobject.c
=====================

核心知识点
----------

* ``Objects/typeobject.c`` 是 CPython 类型系统的核心落点：类创建、MRO、属性查找、descriptor 分发、slot 更新、特殊方法和类型缓存都在这里汇合。
* 普通实例通过 ``Py_TYPE(obj)`` 指向 ``PyTypeObject``；类型对象保存 ``tp_dict``、``tp_mro``、base、实例布局和各类协议 slot。类本身也是对象，其类型通常是 metaclass。
* Python ``class`` 先执行 class body 得到 namespace，再选择 metaclass，最终由 metaclass 创建 heap type。类型准备阶段建立 MRO、继承 slot、descriptor、缓存状态等。
* 实例属性读取的稳定优先级：data descriptor → instance dict/managed storage → non-data descriptor 或普通类属性 → ``__getattr__`` fallback。
* ``property`` 是 data descriptor，因此能压过实例字典同名键；普通 Python function 是 non-data descriptor，因此实例字典可以覆盖方法名。
* 从实例读取类中的 Python function 会发生 method binding，产生保存 ``__func__`` 与 ``__self__`` 的 bound method；从类读取通常得到原 function object。
* MRO 决定类层级名字查找顺序。多继承的核心不是“深度优先”，而是 C3 linearization 生成的单调线性顺序。
* ``len(obj)``、``obj + other``、``obj()`` 等特殊操作通常直接从类型 slot 获取能力，不按普通 ``obj.__len__`` 实例属性查找路径执行。
* 类字典中定义 ``__len__``、``__add__``、``__call__`` 等特殊方法后，类型准备或类型修改路径会把这些名字同步到对应 slot；运行时协议调用再走 slot。
* CPython 会为类型查找维护 version tag、method cache 和 specialization 前提。修改类属性、bases 或 MRO 时必须让相关缓存失效。

关键路径
--------

类创建主干：

::

    class body code object
        ↓
    执行 class body → namespace
        ↓
    选择 metaclass
        ↓
    metaclass call / type_new
        ↓
    创建 PyTypeObject
        ↓
    bases + C3 MRO
        ↓
    填充 tp_dict / descriptors / slots
        ↓
    ready type object

实例属性读取：

::

    obj.name
      ↓
    type(obj) + tp_mro 中查 name
      ↓
    data descriptor?
      ├─ 是 → descr.__get__(obj, type)
      └─ 否
           ↓
        instance dict / managed storage
           ↓ miss
        non-data descriptor?
           ├─ 是 → __get__（方法绑定等）
           └─ 否 → 返回普通类属性
           ↓ miss
        __getattr__ fallback

特殊方法：

::

    len(obj) / obj + x / obj()
        ↓
    type(obj)
        ↓
    对应 protocol slot
        ↓
    slot wrapper / Python method / C implementation
        ↓
    结果或异常

概念辨析
--------

* 实例 attribute lookup 与类型 attribute lookup 不是同一入口；读取 ``obj.x`` 和 ``Type.x`` 的 metaclass/descriptor 参与者不同。
* ``obj.__len__`` 可见不等于 ``len(obj)`` 一定按普通属性路径调用它；特殊方法由类型 slot 驱动。
* function 是 descriptor，bound method 是属性读取结果；二者不是同一个对象。
* data descriptor 的优先级高于实例字典，non-data descriptor 的优先级低于实例字典。
* MRO 是查找顺序，不是对象复制顺序；继承不会把基类字典内容复制进子类字典。
* ``tp_dict`` 是类型 namespace 的 runtime 表示，slot 是高频协议入口；两者通过特殊方法更新逻辑保持一致，但职责不同。
* 动态修改类语义允许发生，代价包括 slot 重计算、version invalidation 和 inline cache 失效。

本章结论
--------

``typeobject.c`` 的核心模型是“类型对象 + MRO + descriptor + slot”。普通点号访问由 descriptor 优先级和实例存储决定，方法绑定是 non-data descriptor 的结果，特殊语法则通过类型 slot 直接进入协议实现。读类型系统源码时，先确定名字在哪个 namespace，再判断命中的对象是否是 descriptor，最后确认该操作是否绕过普通属性路径走 slot。