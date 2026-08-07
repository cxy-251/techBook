第057章：Extension Type System
=============================

核心知识点
----------

* 扩展类型把 C 结构体注册成 Python type object，让 Python 代码按普通对象语义创建实例、访问属性、调用方法并参与协议分发。
* 实例布局通常以 ``PyObject_HEAD`` 开头，后面才是扩展自己的 C 字段；对象头让 CPython 能管理引用计数和类型关系。
* 扩展类型可通过 static type 或 heap type 定义；现代扩展通常更适合 heap type，因为它更容易结合 module state、多解释器、Limited API 和 ABI 演进。
* ``PyType_Spec`` 描述类型名、实例大小、flag 和 slot；``PyType_Slot`` 把 Python 语义入口映射到 C 函数或表。
* ``tp_new``/``Py_tp_new`` 负责分配对象，``tp_init``/``Py_tp_init`` 负责根据 Python 参数初始化已有实例，``tp_dealloc`` 负责实例释放。
* slot 接入 Python 运行时协议；method table 暴露普通点号方法；member table 暴露简单 C 字段；getset table 暴露需要计算或校验的属性。
* 普通方法存在不代表运算符自动可用；运算符、迭代、repr 等语义需要相应 type slot。
* member table 与 getset table 最终会形成 descriptor，所以扩展属性仍参与 Python 的统一属性查找模型。
* 扩展模块初始化负责创建模块对象、创建类型对象，并把类型绑定到模块 namespace。
* PEP 489 multi-phase initialization 把模块创建与执行拆开，使扩展模块更接近普通 Python 模块的导入生命周期。
* ``PyModule_AddObjectRef`` 等 API 会让模块持有类型对象引用；本地临时引用仍需按 ownership 规则释放。
* module state 用于保存每模块/每解释器状态；把状态放在 C 全局变量中会破坏 subinterpreter 隔离。
* ``PyCapsule`` 可把 opaque C pointer 或函数表包装成 Python object，供另一个扩展模块通过 import 路径取得。
* 扩展类型的失败诊断要同时看：类型创建、slot 函数返回约定、引用所有权、模块初始化和对象析构路径。

关键路径
--------

扩展类型创建：

::

    C struct + PyObject_HEAD
      -> PyType_Spec / PyTypeObject
      -> type slots / method tables / member tables
      -> PyType_FromModuleAndSpec / PyType_Ready
      -> type object
      -> add to module namespace
      -> Python: from native import Type

实例生命周期：

::

    Type(...)
      -> tp_new / Py_tp_new
      -> allocate instance
      -> tp_init / Py_tp_init
      -> Python object in use
      -> refcount reaches zero
      -> tp_dealloc
      -> release owned Python/native resources

属性与方法：

::

    obj.method(...)
      -> attribute lookup
      -> method descriptor from method table
      -> C function

    obj.value
      -> attribute lookup
      -> member/getset descriptor
      -> C field read/write or getter/setter

模块初始化：

::

    import native
      -> PyInit_native
      -> create module
      -> Py_mod_exec
      -> create heap type
      -> bind type to module
      -> module ready

概念辨析
--------

* 扩展类型不是“绕过 Python 对象模型”，而是把 C 数据接入同一套 Python 类型、descriptor 和协议系统。
* heap type 是 Python object；static type 通常位于静态存储区，两者生命周期和多解释器适配方式不同。
* method table 负责普通方法，slot 负责 Python 协议入口，两者不能互相替代。
* member table 适合简单字段映射；需要校验、派生值或资源逻辑时应使用 getset。
* module state 是解释器级状态隔离工具，不等于进程级隔离；底层 OS 资源仍可能跨解释器共享。
* capsule 只封装 ``void *`` 及名称/析构约定，不自动提供 C 类型安全或 ABI 兼容。

本章结论
--------

扩展类型的核心模型是“C 实例布局 + Python type object + slot/descriptor 表 + 模块初始化”。阅读或设计扩展类型时，应从类型对象在哪里创建开始，沿实例分配、属性/协议分发、模块 state 和析构路径检查，确保每一层都符合 Python 对象系统和引用所有权规则。
