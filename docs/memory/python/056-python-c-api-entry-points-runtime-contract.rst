第056章：Python C API Entry Points and Runtime Contract
=====================================================

核心知识点
----------

* Python C API 的根对象是 ``PyObject *``：C 层先拿到统一对象指针，再通过类型、协议或具体类型 API 决定怎样操作。
* ``PyTypeObject`` 描述类型对象及其行为入口；对象能力最终由类型、slot、协议和方法表共同决定。
* C API 函数同时遵守四类契约：对象类型、引用所有权、异常状态、返回值约定。
* 入口参数通常是 borrowed reference；创建对象的 API 常返回 new reference。new reference 必须释放、转移给容器，或作为返回值交给调用方。
* borrowed reference 只在提供者保证的生命周期内有效；若需要跨越可能释放原对象、修改容器或执行 Python 代码的路径，应建立自己的 strong reference。
* 指针返回 API 通常以 ``NULL`` 表示失败；整数返回 API 常以 ``-1`` 表示失败；``PyArg_*`` 系列常用 0 表示失败。
* C 返回值只表达“成功/失败形状”，真正的 Python 异常保存在当前线程的 exception indicator 中。
* 错误返回必须与异常状态一致：失败时返回错误值并保留已设置异常；成功时不能留下未处理异常。
* ``PyArg_ParseTuple`` 等入口把动态 Python 对象转换为 C 值；解析失败后应立即停止正常路径。
* 抽象 API 如 ``PyObject_*``、``PyNumber_*``、``PySequence_*`` 更接近 Python 语义；``PyList_*``、``PyLong_*`` 更接近具体内置类型。
* 具体类型宏和快速 API 通常要求调用方已经建立类型前置条件；错误的类型假设可能直接变成 C 层未定义行为。
* 一个可靠的 C API 函数必须让所有成功出口和失败出口都能解释：当前拥有哪些引用、异常是否存在、返回约定是什么。

关键路径
--------

Python 调用进入 C 扩展：

::

    Python call
      -> C extension function
      -> PyObject * arguments
      -> 参数解析 / 类型检查
      -> C 局部值或具体对象操作
      -> 创建返回对象
      -> 成功：返回 new reference
      -> 失败：保留 exception indicator，返回 NULL/-1

典型对象入口：

::

    PyObject *obj
      -> 类型检查 / 协议判断
      -> 具体 API 或抽象 API
      -> 成功结果
      -> ownership 归属判断

引用路径：

::

    borrowed reference
      -> 只在保证期内使用
      -> 若需延长生命周期：Py_INCREF / Py_NewRef
      -> strong reference
      -> Py_DECREF / 转移 / return

错误路径：

::

    C API call
      -> success ?
         yes -> 继续
         no  -> exception indicator 已设置
                -> 清理当前拥有资源
                -> return NULL / -1

概念辨析
--------

* ``PyObject *`` 是统一对象入口，不代表对象已经是某个具体内置类型。
* new reference 指“当前代码拥有一次释放责任”，不是“对象只能由当前代码使用”。
* borrowed reference 不是弱引用；它仍指向真实对象，只是当前代码没有独立的生命周期所有权。
* ``NULL`` 不是异常对象，只是 C 层错误返回标记；异常原因存放在 exception indicator 中。
* GIL 不替代 ownership 规则；持有 GIL 也不能让已经失效的 borrowed reference 自动安全。
* 类型检查和错误处理是两层问题：类型错误通常通过设置 Python 异常并走正常错误返回路径表达。
* 宏形式的快速 API 不等于更高级语义；它们往往减少检查并暴露更多实现耦合。

本章结论
--------

Python C API 的稳定阅读模型是：先确认 ``PyObject *`` 的真实类型和协议，再确认每个引用的 ownership，随后检查失败 API 是否设置异常，最后核对所有返回出口是否满足约定。任何 C 扩展函数都应被看成一条“对象 -> 所有权 -> 异常 -> 返回值”的 runtime contract，而不是普通 C 函数调用。
