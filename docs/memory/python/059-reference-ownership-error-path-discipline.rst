第059章：Reference Ownership and Error Path Discipline
=====================================================

核心知识点
----------

* Python/C API 的对象生命周期纪律建立在 reference ownership 上：当前代码是否拥有一次 strong reference，决定它是否负责释放。
* new reference 表示调用方获得一次新的释放责任；borrowed reference 只提供临时访问权；strong reference 保证对象在释放前保持存活。
* stolen reference 表示调用 API 后，当前代码把原有释放责任交给了接收方；之后本地变量不应再按 owned reference 处理。
* ``Py_INCREF`` / ``Py_NewRef`` 用于建立新的 strong reference；``Py_DECREF`` 用于释放已拥有引用。
* ``Py_XDECREF`` 允许指针为 ``NULL``，适合统一 cleanup；``Py_CLEAR`` 先把槽位置空再释放旧引用，适合析构和循环引用路径。
* ``Py_SETREF`` / ``Py_XSETREF`` 适合替换持有的对象引用，让结构先进入新状态，再释放旧对象。
* ``Py_DECREF`` 可能触发对象析构，析构过程又可能执行 Python 代码，因此释放前应先把周围数据结构调整到一致状态。
* ownership 应被当成局部状态机：``NULL -> owned -> transferred/released``，每条控制流都必须闭合。
* 错误处理由“C 错误返回值 + 当前线程 exception indicator”共同表达。
* 返回 ``PyObject *`` 的函数失败时通常返回 ``NULL``；返回整数状态的函数常用 ``-1``；调用者必须知道每个 API 的具体约定。
* 如果某 API 已经设置异常，cleanup 代码应尽量保留原始异常，不要用次生失败无意覆盖它。
* cleanup 本身可能失败或触发 Python 代码，所以错误路径应简短、顺序稳定、所有权清晰。
* 常见写法是初始化所有 owned 指针为 ``NULL``，成功获得引用后赋值，释放或转移后立即置 ``NULL``，最后用统一 ``goto error/done`` 清理。
* 容器 API 的 ownership 规则并不统一：有的取项返回 borrowed reference，有的返回 new reference，有的 set API 会 steal reference，必须逐个确认。
* free-threaded 场景下 borrowed reference 风险更高；能直接取得 strong reference 的新 API 通常更适合跨并发边界使用。

关键路径
--------

单个引用状态机：

::

    NULL
      -> API returns new reference
      -> OWNED
      -> Py_DECREF / Py_CLEAR
         => RELEASED
      or
      -> return / steal / store into owner
         => TRANSFERRED

Borrowed 转 strong：

::

    borrowed reference
      -> Py_NewRef / Py_INCREF
      -> strong reference
      -> safe to retain across wider lifetime
      -> Py_DECREF when done

统一失败路径：

::

    acquire object A
      -> acquire object B
      -> operation C
      -> failure anywhere
      -> goto error
      -> Py_XDECREF(B)
      -> Py_XDECREF(A)
      -> return NULL

异常传播：

::

    C API fails
      -> return sentinel
      -> exception indicator set
      -> cleanup only owned resources
      -> preserve exception
      -> propagate sentinel upward

引用转移：

::

    value = PyLong_FromLong(...)
      -> owned by current function
      -> PyList_SET_ITEM(list, i, value)
      -> ownership transferred to list
      -> value = NULL

概念辨析
--------

* new、borrowed、stolen 描述的是引用责任，不是对象本体的独占关系。
* borrowed reference 不是“引用计数为零边缘对象”，而是当前代码没有独立 ownership。
* ``Py_INCREF`` 的意义是取得 ownership，不应把业务逻辑建立在具体引用计数数值上。
* ``Py_DECREF`` 不是纯粹的整数减一；它可能触发析构和任意 Python 可见副作用。
* cleanup 路径不是“失败后随便释放”，而是只释放当前函数此刻仍拥有的资源。
* 异常 indicator 与返回值必须一致；只有 sentinel 没有异常，或有异常却返回正常值，都会破坏 C API contract。
* 置 ``NULL`` 是所有权状态记录方式，不只是防御性编码风格。

本章结论
--------

C 扩展最重要的工程纪律之一是把每个 ``PyObject *`` 当成显式 ownership 状态机，并让所有失败出口共享清晰的 cleanup 规则。检查代码时，逐个标记 new/borrowed/stolen reference，再沿每条返回路径核对 owned reference 是否恰好释放或转移一次，同时确保原始 exception indicator 被正确传播。
