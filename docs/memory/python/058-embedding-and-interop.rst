第058章：Embedding and Interop
==============================

核心知识点
----------

* Embedding 指宿主 C/C++ 程序拥有进程入口，并主动初始化、驱动和结束 CPython runtime。
* 普通扩展模块是 Python 调 C；embedding 是宿主程序主动进入 Python。二者共用引用计数、异常、类型转换和调用约定。
* 现代初始化应把 ``PyConfig`` 视为解释器配置入口；路径、环境变量、site 导入、isolated 模式等都会影响嵌入后的运行时环境。
* 解释器初始化后，宿主可通过导入模块、取得属性、检查 callable、构造参数并调用 Python 函数。
* 每个进入 Python C API 的 native 线程都必须附着到合适的 interpreter/thread state。
* 单解释器、短时回调常可使用 ``PyGILState_Ensure`` / ``PyGILState_Release``；多解释器场景需要显式管理目标 ``PyInterpreterState`` 与 ``PyThreadState``。
* thread state 比“有没有拿到 GIL”更基础；free-threaded build 中 GIL 语义变化，但线程状态仍是访问 runtime 的入口。
* Python exception indicator 属于当前线程状态；C API 调用失败后应立即读取、格式化或转换错误。
* Native interop 的数据路径有两种：复制为 Python object，或共享底层 native memory 并用 buffer/memoryview 暴露。
* 复制路径生命周期清晰但有复制成本；共享路径减少复制，却要求明确底层内存的 owner、可写性、并发和释放时机。
* ``PyObject_Call*`` 成功返回 new reference，失败返回 ``NULL`` 并设置异常；参数容器本身也是 Python object，也要管理引用。
* 将宿主内存包装成 ``memoryview`` 不会自动取得宿主内存所有权；Python 对象仍可能在调用结束后继续持有该视图。
* 若 Python 结果、回调或 view 可能逃逸当前调用，宿主必须保证其引用和底层内存生命周期覆盖逃逸期。
* Finalization 是独立风险区：解释器进入结束阶段后，不应再允许线程随意进入 Python。
* 宿主应把 Python 异常转换为自己的错误模型，例如错误码、日志、任务失败或 UI diagnostic，而不是让异常状态长期悬挂。

关键路径
--------

解释器生命周期：

::

    host process starts
      -> configure PyConfig
      -> Py_InitializeFromConfig
      -> CPython runtime ready
      -> import/call Python code
      -> release all owned PyObject references
      -> stop native callbacks into Python
      -> Py_FinalizeEx

Native 线程进入 Python：

::

    OS/native thread
      -> attach PyThreadState to target interpreter
      -> acquire required runtime execution state
      -> call Python/C API
      -> handle exception immediately
      -> detach/release thread state

数据互操作：

::

    native value/memory
      -> copy conversion: PyLong/PyBytes/PyUnicode/...
         or
      -> shared view: buffer/memoryview
      -> construct Python args
      -> PyObject_Call*
      -> Python result or exception
      -> convert result back to host representation

共享内存路径：

::

    host owns memory
      -> expose memoryview/buffer
      -> Python plugin consumes it
      -> ensure no escaped view outlives host memory
      -> release Python wrapper
      -> host may free/reuse memory

概念辨析
--------

* Embedding 不等于扩展模块：谁拥有进程入口和解释器生命周期不同。
* ``PyGILState_Ensure`` 适合简单单解释器模型，不是多解释器线程管理的通用答案。
* GIL 与 thread state 不同；进入 runtime 的正确解释器上下文比单纯“拿锁”更重要。
* memoryview 是 Python object 包装，不代表 Python 拥有宿主内存。
* zero-copy 只减少数据复制，不会消除 lifetime、同步、异常和 ownership 成本。
* ``PyErr_Print`` 适合简单宿主；大型系统更应显式获取并映射异常，而不是直接输出到 stderr。
* ``Py_FinalizeEx`` 不是普通资源析构函数；解释器结束阶段需要先停止所有可能再次进入 Python 的宿主活动。

本章结论
--------

Embedding 的稳定模型是：宿主拥有解释器生命周期，线程通过正确的 interpreter/thread state 进入 runtime，native 值通过复制或共享边界变成 Python object，调用结果再通过引用和异常契约返回宿主。设计时必须把初始化、线程入口、对象所有权、共享内存和 finalization 放在同一张生命周期图中。
