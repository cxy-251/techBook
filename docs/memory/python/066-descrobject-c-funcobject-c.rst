第066章：descrobject.c and funcobject.c
=======================================

核心知识点
----------

* ``Objects/descrobject.c`` 实现多类 descriptor，``Objects/funcobject.c`` 实现 Python function object。二者共同解释一次 ``obj.name(...)`` 怎样从属性读取进入调用。
* descriptor 的 C 层核心入口是类型上的 ``tp_descr_get`` 与 ``tp_descr_set``。属性查找先找到类字典中的对象，再依据该对象是否具有 descriptor 能力决定下一步。
* 常见 descriptor 包括 ``property``、member descriptor、getset descriptor、wrapper descriptor、method descriptor。它们来源不同，但都接入统一属性协议。
* ``property`` 是 data descriptor，持有 fget/fset/fdel；实例读取会调用 getter，写入会进入 setter 或报错。实例字典同名项不能覆盖 data descriptor 的读取。
* 普通 Python function 放入 class dict 后是 non-data descriptor。实例读取时 function ``__get__`` 产生 bound method；实例字典同名值可以压过它。
* function object 保存 code object、globals、defaults、kwdefaults、closure、annotations、name/qualname、函数字典和调用入口。它保存的是“可复用定义材料”，不是某次调用的 locals。
* 一次 Python function 调用会使用 function 保存的 code/globals/defaults/closure 创建执行 frame，再将实参绑定到 locals/localsplus。frame 结束后 function object 仍可被下一次调用复用。
* bound method 保存 ``__func__`` 与 ``__self__``。``obj.method(x)`` 的语义等价于调用原 function 并把 ``obj`` 作为第一个参数。
* 内建类型方法通常不是 Python function，而是 method descriptor/C callable；它们没有 ``__code__``，绑定和调用仍遵守 descriptor + call protocol。
* vectorcall 用连续 ``PyObject *`` 参数数组、参数数量与关键字名元组表示调用，避免传统 ``args tuple + kwargs dict`` 的部分临时分配。它改变调用成本，不改变参数绑定语义。

关键路径
--------

``property`` 读取：

::

    profile.score
        ↓
    type(profile) MRO 查找 "score"
        ↓
    命中 property object
        ↓
    data descriptor
        ↓
    property.__get__ / fget(profile)
        ↓
    返回计算结果

普通方法绑定：

::

    profile.scale
        ↓
    class dict 命中 function object
        ↓
    function.tp_descr_get(profile, Profile)
        ↓
    bound method
       ├─ __func__ = function
       └─ __self__ = profile

方法调用：

::

    profile.scale(10)
        ↓
    属性查找 / method-load optimization
        ↓
    callable + bound self + 10
        ↓
    vectorcall / Python function call
        ↓
    创建/推入执行 frame
        ↓
    参数绑定 self, factor
        ↓
    ceval 执行 code object

function object：

::

    def scale(...)
       ↓ compile
    code object
       ↓ class body executes
    PyFunctionObject
       ├─ code
       ├─ globals
       ├─ defaults / kwdefaults
       ├─ closure
       ├─ annotations
       └─ vectorcall entry

概念辨析
--------

* descriptor 是“类字典中的行为对象”，attribute lookup 是“决定何时调用 descriptor 的算法”；两者职责不同。
* function object 与 frame 不同。function 跨多次调用存在，frame 表示一次具体执行现场。
* function 与 bound method 不同。bound method 只是把接收者绑定到原 callable 的包装对象。
* ``Profile.scale`` 与 ``profile.scale`` 不是同一属性读取结果：前者通常是 function，后者通常是 method。
* ``property`` 与普通 method 都使用 descriptor 协议，但前者是 data descriptor，后者的 Python function 是 non-data descriptor。
* method descriptor 与 Python function descriptor 语义相似，但 C 对象种类和调用入口不同。
* vectorcall 是调用 ABI/优化层，不是新的 Python 调用语义。

本章结论
--------

``descrobject.c`` 负责把类字典中的对象变成可接管属性访问的 descriptor，``funcobject.c`` 负责保存 Python 函数的 code、定义环境和调用入口。实例方法本质上是“function descriptor 读取 → bound receiver → callable dispatch”；``property`` 则是 data descriptor 直接在读取阶段求值。先区分 descriptor 类型，再区分 function、method 和 frame，调用路径就会变得清晰。