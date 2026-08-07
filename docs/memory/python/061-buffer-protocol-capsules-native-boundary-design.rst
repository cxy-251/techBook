第061章：Buffer Protocol, Capsules, and Native Boundary Design
==============================================================

核心知识点
----------

* Buffer protocol 是 Python object 与 native memory 之间的二进制共享契约：producer 暴露内存，consumer 请求并解释该内存。
* ``PyObject_GetBuffer()`` 成功后得到 ``Py_buffer``；``Py_buffer`` 不是 Python object，而是一次内存借用的 C 描述结构。
* ``Py_buffer`` 的关键字段包括 ``buf``、``len``、``readonly``、``itemsize``、``format``、``ndim``、``shape``、``strides``、``suboffsets`` 和 ``obj``。
* ``view.buf`` 只有在当前 buffer view 的借用期内有效；借用结束后不能继续保存并使用该 pointer。
* 每次成功的 ``PyObject_GetBuffer()`` 都必须对应一次 ``PyBuffer_Release()``。
* ``view.obj`` 会帮助维持 exporter 生命周期；``PyBuffer_Release()`` 会结束这份借用关系并释放对应强引用。
* consumer 必须明确自己能处理哪类布局：连续字节、可写内存、结构化元素、多维 shape、stride 或间接布局。
* 只会线性扫描的 native 代码应请求简单/连续 buffer；支持非连续数据时必须按 ``shape`` 与 ``strides`` 计算元素位置。
* 写入 consumer 必须请求可写 buffer；没有取得写权限就修改 ``view.buf`` 会破坏协议边界。
* ``memoryview`` 是 Python 层对 buffer interface 的对象化包装；切片通常可以继续共享底层 exporter，而不是复制数据。
* 跨调用保留 buffer 有两条稳定路线：复制到 native 自有内存，或把 ``Py_buffer`` 连同 release 责任交给明确 owner。
* ``PyCapsule`` 用于把 opaque ``void *``、native handle 或函数表包装成 Python object，在扩展模块之间通过 import 边界传递。
* Capsule name 是契约的一部分；producer 与 consumer 应使用精确匹配的名称，并可额外携带 API version 字段。
* Capsule 只保存 pointer、name、context 和 destructor，不自动保证 pointer 类型或 ABI 兼容。
* Capsule destructor 适合表达 native 资源 ownership；静态函数表通常无需析构，动态 handle 则应由明确 owner 释放。
* Native boundary 的成本不仅是调用开销，还包括对象转换、引用计数、布局检查、异常转换、线程状态、buffer lifetime 和资源 cleanup。
* 设计 native API 时，应优先让边界表达能力和生命周期，而不是依赖某个具体 Python 容器类型。

关键路径
--------

Buffer consumer：

::

    Python object
      -> PyObject_GetBuffer(obj, &view, flags)
      -> validate readonly / format / ndim / shape / strides
      -> use view.buf within borrow lifetime
      -> create Python/native result
      -> PyBuffer_Release(&view)
      -> return

失败路径：

::

    GetBuffer success
      -> later validation/call fails
      -> preserve exception
      -> release other owned resources
      -> PyBuffer_Release
      -> return NULL / -1

共享与复制选择：

::

    incoming binary data
      -> need data after current borrow?
         no  -> use Py_buffer directly
         yes -> copy to native-owned memory
               or transfer Py_buffer + release duty to owner

Capsule producer/consumer：

::

    producer native pointer/function table
      -> PyCapsule_New(pointer, "module._C_API", destructor)
      -> expose as module attribute
      -> consumer imports capsule
      -> PyCapsule_Import / GetPointer
      -> validate name + api_version
      -> call native API

Native boundary checklist：

::

    object kind/protocol
      -> ownership
      -> buffer layout + lifetime
      -> thread/GIL state
      -> native call
      -> error -> Python exception
      -> cleanup
      -> return ownership

概念辨析
--------

* ``Py_buffer`` 是一次借用描述，不是底层内存 owner。
* ``memoryview`` 是 Python object，但它通常仍然共享 exporter 的内存，不等于复制后的 ``bytes``。
* zero-copy 不等于零成本；布局检查、引用维护、同步和 cache behavior 仍然存在。
* ``len`` 不意味着任意 buffer 都可从 ``buf`` 连续读取；strided/multidimensional 数据必须按请求语义解释。
* Capsule 是 pointer 运输容器，不是类型系统，也不是自动 ABI 层。
* Capsule name 校验能阻止一部分错误入口，无法证明结构体布局、函数签名或版本完全兼容。
* Buffer protocol 适合共享数据，Capsule 适合共享 native 能力，两者解决的是不同边界问题。

本章结论
--------

Native boundary 的稳定设计应把“数据共享”和“native 能力共享”分开：二进制数据通过 buffer protocol 与 ``Py_buffer`` 建立受控借用期，C pointer/函数表通过 capsule 建立命名和版本契约。无论选择哪种路径，都必须明确 owner、lifetime、布局、线程状态、异常转换和 cleanup，zero-copy 或直接 pointer 传递都不能绕过这些责任。
