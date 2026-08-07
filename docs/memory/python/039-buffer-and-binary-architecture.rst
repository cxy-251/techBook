第039章：Buffer and Binary Architecture
=========================================

核心知识点
----------

* Python 二进制数据路径的核心问题是“谁拥有内存、谁只持有视图、当前操作是否复制、consumer 需要什么格式与连续性”。
* Buffer protocol 把对象分成 exporter/producer 和 consumer。exporter 暴露底层内存与元数据，consumer 声明自己需要只读/可写、format、shape、strides、连续性等条件。
* C API 中 ``PyObject_GetBuffer()`` 获取 ``Py_buffer``，``PyBuffer_Release()`` 结束视图持有；release 不等于释放底层 owner 对象。
* ``memoryview`` 是 Python 层通用 buffer view。它通常不拥有数据，只保存对 exporter 的引用和 offset、长度、format、itemsize、shape、strides 等视图信息。
* ``bytearray`` 适合可修改、可复用缓冲区；``bytes`` 适合稳定不可变快照；``memoryview`` 适合在多个处理阶段之间传递共享窗口。
* ``memoryview`` 切片通常继续得到子 view；``bytes`` / ``bytearray`` 的普通切片会创建新的容器并复制内容。
* zero-copy 指当前处理步骤没有为数据内容创建新的等长存储。它不是全链路永久属性：后续 ``bytes(view)``、``tobytes()``、复制切片等仍会 materialize 新数据。
* 零拷贝成立需要 exporter 生命周期有效、consumer 支持 buffer protocol、可变性/格式/连续性要求兼容，并且代码没有显式物化副本。
* 连续视图和带 stride 的视图都可以共享底层内存；只接受 C-contiguous 数据的 consumer 遇到非连续 view 时可能拒绝或要求复制。
* ``Py_buffer`` 中最关键的概念字段是 ``buf``、``obj``、``len``、``readonly``、``itemsize``、``format``、``ndim``、``shape``、``strides``。
* ``struct.unpack_from`` 等 API 可以直接消费 buffer，在给定 offset 上解析数据，避免先做 ``data[:n]`` 这样的中间 bytes 复制。
* 活动 view 会约束可变 exporter 的 resize，因为调整底层存储可能让 consumer 保存的指针失效。
* ``bytes-like object`` 不是一个足够精确的工程契约。接口还应说明只读/可写、连续/strided、是否长期持有 view、是否允许复制。
* Python 3.12 起 PEP 688 让 Python 层也能显式参与 buffer protocol；底层 C buffer 模型仍是理解高性能 I/O 和扩展边界的主线。

关键路径
--------

Buffer 获取与释放：

::

   owner/exporter object
       ↓
   consumer requests buffer
       ↓
   PyObject_GetBuffer(flags)
       ↓
   exporter validates writable / format / shape / contiguity request
       ↓
   fill Py_buffer
       ↓
   consumer reads or writes shared memory
       ↓
   PyBuffer_Release
       ↓
   exporter resize/lifecycle constraints may be lifted

Python 零拷贝切片：

::

   bytearray / array / mmap owner
       ↓
   memoryview(owner)
       ↓
   subview = view[start:stop]
       ↓
   same underlying storage, new logical window
       ↓
   consumer accepts view
       ↓
   no data copy

物化副本路径：

::

   view / bytes-like input
       ↓
   bytes(view) / view.tobytes() / copying slice
       ↓
   allocate new storage
       ↓
   copy selected bytes
       ↓
   independent immutable or mutable result

二进制解析：

::

   reusable mutable buffer
       ↓
   memoryview
       ↓
   struct.unpack_from(view, offset)
       ↓
   parse header without intermediate slice copy
       ↓
   payload subview
       ↓
   copy only at boundary that requires stable bytes

概念辨析
--------

* **owner 与 view**：owner 负责底层存储；view 负责描述如何看这段存储，并通常延长 exporter 生命周期。
* **zero-copy 与无成本**：零拷贝省掉数据复制，仍有 view 创建、协议检查、解析和 Python/C 调用成本。
* **bytes 与 bytearray**：bytes 不可变、适合快照；bytearray 可原地修改、适合缓冲区复用。
* **bytearray slice 与 memoryview slice**：前者通常复制出新 bytearray，后者通常建立共享子视图。
* **连续与共享**：非连续 stride view 也能共享内存；consumer 是否能直接处理由其接口契约决定。
* **readonly 与 memoryview**：view 的可写能力来自 exporter；对 ``bytes`` 的 view 是只读，对可写 exporter 才能得到可写路径。
* **release 与 free**：释放 buffer view 只结束 consumer 的持有关系；底层内存何时真正释放仍由 owner 生命周期决定。
* **binary view 与 Python object sequence**：list/tuple 保存对象引用；buffer 描述的是可按字节/元素格式访问的底层连续或带 stride 内存。

本章结论
--------

Buffer architecture 可以压缩为“owner 管内存，buffer protocol 描述内存，memoryview 暴露共享视图，consumer 决定能否直接消费”。分析二进制性能时先标出所有权和复制点，再检查 readonly、format、shape、strides 与 contiguity；需要稳定快照时再显式 materialize。这样才能判断一条 I/O、解析或 C 扩展路径究竟是真正零拷贝，还是只把复制推迟到了后面的边界。
