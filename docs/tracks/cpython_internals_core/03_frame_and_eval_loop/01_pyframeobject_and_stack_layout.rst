=============================================================================
_PyInterpreterFrame 物理栈帧结构、局部变量与值栈布局
=============================================================================

.. note:: 前置背景与上下文承接
   在前两个模块中，我们先后解构了 CPython 的对象与内存基石（``PyObject`` 头部、``PyTypeObject`` 槽位、``pymalloc`` / ``mimalloc`` 以及分代 GC）以及前端编译管线（PEG 文法、AST 构建、符号表求解、CFG 控制流优化与字节码生成）。编译器最终输出的不可变 ``PyCodeObject`` 封装了机器指令、常量表与栈深上限 ``co_stacksize``。
   
   从本章开始，我们将正式进入全书最核心的引擎腹地——**模块三【虚拟机栈帧与 CEval 解释器核心】**。当 Python 函数被调用时，虚拟机如何在物理内存中建立执行上下文？为什么 Python 3.11+ 的栈帧性能相较旧版实现了质的飞跃？本章将深入 CPython 核心源码 ``Include/internal/pycore_frame.h``、``Include/internal/pycore_interpframe_structs.h``、``Include/internal/pycore_interpframe.h`` 以及 ``Include/cpython/pystate.h``，深度解构 ``_PyInterpreterFrame`` 的内存连续布局、数据栈块（Data Stack Chunk）无锁 Bump 分配算法、``localsplus`` 混合存储阵列、惰性 ``PyFrameObject`` 具象化机制，以及基于 ``_PyStackRef`` 的求值栈拓扑。

-----------------------------------------------------------------------------
1. 栈帧体系的范式革命：从堆分配到连续数据栈
-----------------------------------------------------------------------------

在 Python 3.11 之前，CPython 的函数调用开销极其高昂。每一次 Python 函数调用，虚拟机都会调用 ``PyObject_GC_NewVar`` 在系统堆上分配一个完整的 **``PyFrameObject``**。

旧版堆栈帧的性能痛点
~~~~~~~~~~~~~~~~~~~~

- **高昂的堆分配损耗**：每个栈帧都是一个全功能的 Python GC 对象，包含 GC 链表头、引用计数、实例字典引用等数十个字段，单次调用仅内存分配与初始化就耗费数百个 CPU 周期；
- **极其糟糕的缓存局部性**：栈帧在堆上离散分布，导致深层调用栈无法命中 CPU L1/L2 数据缓存；
- **紧耦合 C 调用栈**：旧版解释器通过递归调用 C 函数 ``PyEval_EvalFrameEx`` 来执行子函数，极易引发 C 机器栈溢出（Segmentation Fault）。

现代 CPython 的轻量级 ``_PyInterpreterFrame`` 架构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

自 Python 3.11+ 起（作为 Faster CPython 项目的核心里程碑），解释器对栈帧体系进行了彻底的解耦与重构：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                  现代 CPython 栈帧双层解耦架构                          |
   +=========================================================================+
   | 物理运行实体：_PyInterpreterFrame                                       |
   | ├── 非 PyObject 结构体，无需 GC 追踪与引用计数                          |
   | ├── 分配于线程私有的连续数据栈块 (_PyStackChunk, 16KB)                   |
   | └── 使用极速 Bump Pointer 指针平移分配，彻底摆脱 malloc / free          |
   +-------------------------------------------------------------------------+
                                     │ (仅当被用户探测时惰性绑定)
                                     ▼
   +-------------------------------------------------------------------------+
   | 用户层兼容实体：PyFrameObject                                           |
   | ├── 仅当调用 sys._getframe()、引发异常回溯或挂载调试器时惰性实例化      |
   | └── 作为 _PyInterpreterFrame 的轻量外壳包装 (Wrapper)                   |
   +-------------------------------------------------------------------------+

-----------------------------------------------------------------------------
2. _PyInterpreterFrame 核心数据结构与内存拓扑
-----------------------------------------------------------------------------

在 ``Include/internal/pycore_interpframe_structs.h`` 中，``_PyInterpreterFrame`` 结构体定义如下：

.. code-block:: c

   struct _PyInterpreterFrame {
       _PyStackRef f_executable;        /* 强引用或延迟引用的 CodeObject (PyCodeObject*) */
       struct _PyInterpreterFrame *previous; /* 指向调用方 (Caller) 栈帧的物理指针 */
       _PyStackRef f_funcobj;           /* 正在执行的函数对象 (PyFunctionObject*) */
       PyObject *f_globals;             /* 全局命名空间字典 (Borrowed Reference) */
       PyObject *f_builtins;            /* 内建命名空间字典 (Borrowed Reference) */
       PyObject *f_locals;              /* 局部变量字典 (惰性分配，通常为 NULL) */
       PyFrameObject *frame_obj;        /* 关联的堆 PyFrameObject (惰性生成) */
       _Py_CODEUNIT *instr_ptr;         /* 当前正在执行的字节码指令指针 */
       _PyStackRef *stackpointer;       /* 当前值栈顶指针 (TOS Pointer) */
   #ifdef Py_GIL_DISABLED
       int32_t tlbc_index;              /* 线程局部字节码 (TLBC) 索引 */
   #endif
       uint16_t return_offset;          /* 函数调用返回时的跳转偏移 */
       char owner;                      /* 栈帧所有权标志 (FRAME_OWNED_BY_THREAD 等) */
       uint8_t visited;                 /* GC 栈回溯遍历标记 */
       
       /* 局部变量与求值栈的物理连续伸展阵列 */
       _PyStackRef localsplus[1];
   };

物理内存排布全景
~~~~~~~~~~~~~~~~

每个 ``_PyInterpreterFrame`` 在物理内存中是一个严格连续的扁平内存块，其尾部的 ``localsplus`` 柔性数组承载了该函数运行所需的所有动态变量与操作数：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                _PyInterpreterFrame 连续内存物理排布                     |
   +=========================================================================+
   | 栈帧控制元数据 (Frame Header, 约 72~80 字节)                            |
   | ├── f_executable, previous, f_funcobj, f_globals, f_builtins           |
   | └── instr_ptr, stackpointer, return_offset, owner, visited              |
   +-------------------------------------------------------------------------+
   | localsplus[0 ... co_nlocals-1] : Fast Locals (普通局部变量)            |
   +-------------------------------------------------------------------------+
   | localsplus[co_nlocals ... +ncellvars-1] : Cell Vars (闭包引出变量)      |
   +-------------------------------------------------------------------------+
   | localsplus[... +nfreevars-1] : Free Vars (闭包引用外层变量)             |
   +-------------------------------------------------------------------------+
   ▲
   │ _PyFrame_Stackbase(f) = localsplus + co_nlocalsplus
   ▼
   | localsplus[co_nlocalsplus ... +co_stacksize-1] : Evaluation Value Stack |
   | (操作数求值栈，stackpointer 随 PUSH/POP 在此区间高速上下移动)           |
   +-------------------------------------------------------------------------+

所有局部变量（``co_varnames``）、闭包单元（``co_cellvars``）、自由变量（``co_freevars``）以及求值栈（Value Stack）被整合在同一个连续的单调地址空间中。
- ``LOAD_FAST 0``：直接通过基址寻址 ``frame->localsplus[0]``，在汇编层面仅为一条单周期寄存器变址寻址指令（如 ARM64 下的 ``ldr x0, [x19, #80]``）；
- ``_PyFrame_StackPush(f, v)``：执行 ``*f->stackpointer++ = v``，零开销自增。

-----------------------------------------------------------------------------
3. 线程级数据栈块（Data Stack Chunk）与 Bump 分配
-----------------------------------------------------------------------------

为了承载这些连续的 ``_PyInterpreterFrame``，每个线程状态结构体 ``PyThreadState`` 维护了一条私有的 **数据栈块链表（``_PyStackChunk``）**：

.. code-block:: c

   typedef struct _stack_chunk {
       struct _stack_chunk *previous;   /* 前一个 16KB 数据栈块 */
       size_t size;                     /* 栈块总容量 (字节) */
       size_t top;                      /* 当前已分配游标 */
       PyObject *data[1];               /* 连续内存缓冲区 */
   } _PyStackChunk;

   #define _PY_DATA_STACK_CHUNK_SIZE (16 * 1024) /* 默认单块 16KB */

极速入栈与出栈算法
~~~~~~~~~~~~~~~~~~

当发生 Python 函数调用时，解释器调用 ``_PyFrame_PushUnchecked()`` 进行无锁分配：

.. code-block:: c

   static inline _PyInterpreterFrame *
   _PyFrame_PushUnchecked(PyThreadState *tstate, _PyStackRef func,
                          int null_locals_from, _PyInterpreterFrame *previous)
   {
       PyFunctionObject *func_obj = (PyFunctionObject *)PyStackRef_AsPyObjectBorrow(func);
       PyCodeObject *code = (PyCodeObject *)func_obj->func_code;
       
       /* 1. 直接以当前 datastack_top 作为新栈帧的物理首地址 */
       _PyInterpreterFrame *new_frame = (_PyInterpreterFrame *)tstate->datastack_top;
       
       /* 2. 指针单调前移该 CodeObject 所需的完整帧大小 co_framesize */
       tstate->datastack_top += code->co_framesize;
       
       /* 3. 初始化元数据并链接 previous 指针 */
       _PyFrame_Initialize(tstate, new_frame, func, NULL, code, null_locals_from, previous);
       return new_frame;
   }

- **入栈耗时**：仅需 **3 次指针加法与赋值**，完全无需调用 OS 内核或通用堆内存分配器；
- **出栈耗时（``_PyThreadState_PopFrame``）**：函数返回时，直接执行 ``tstate->datastack_top = (PyObject **)frame;`` 将游标回退，内存瞬间完成重置与回收！
- **扩容与缩容**：当当前 16KB Chunk 剩余空间不足以容纳 ``co_framesize`` 时，自动分配新的 Chunk 串联入链表；当调用链回退时，多余的 Chunk 会被缓存（``datastack_cached_chunk``）以供下次调用复用，彻底消除了频繁的系统调用。

-----------------------------------------------------------------------------
4. 栈帧所有权模型（Frame Ownership）与生成器挂起
-----------------------------------------------------------------------------

每个栈帧的 ``owner`` 字段精准记录了其生命周期宿主状态：

.. code-block:: c

   enum _frameowner {
       FRAME_OWNED_BY_THREAD = 0,       /* 归属于线程数据栈 (常规函数调用) */
       FRAME_OWNED_BY_GENERATOR = 1,    /* 归属于生成器/协程堆对象 */
       FRAME_OWNED_BY_FRAME_OBJECT = 2, /* 归属于逃逸至堆上的 PyFrameObject */
       FRAME_OWNED_BY_INTERPRETER = 3,  /* 解释器内部顶层哨兵帧 */
   };

生成器（Generator）与异步协程（Coroutine）零拷贝挂起
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在常规线程栈上执行的函数，在返回后其栈帧内存立即被覆盖。但生成器在执行 ``yield`` 时必须保留全部局部变量与执行游标。

CPython 在 ``_PyGenObject`` 头部直接内联嵌入了 ``_PyInterpreterFrame``：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                 _PyGenObject / _PyCoroObject 内存布局                   |
   +=========================================================================+
   | PyObject_HEAD (引用计数与类型)                                          |
   | ├── gi_name, gi_qualname, gi_exc_state                                  |
   | └── gi_frame_state (FRAME_CREATED / FRAME_SUSPENDED / FRAME_EXECUTING)  |
   +-------------------------------------------------------------------------+
   | _PyInterpreterFrame gi_iframe (直接内联在生成器堆内存尾部！)             |
   | ├── owner = FRAME_OWNED_BY_GENERATOR                                    |
   | ├── instr_ptr = 停在 YIELD_VALUE 指令处                                 |
   | └── localsplus[] = 完整保留上次挂起时的所有局部变量与求值栈状态         |
   +-------------------------------------------------------------------------+

当生成器被 ``next()`` 激活时，解释器直接将 ``gi_iframe`` 压入当前线程的调用链中执行；当触发 ``yield`` 时，无需任何内存深拷贝，仅需将其 ``previous`` 指针断开并标记为 ``FRAME_SUSPENDED``，即可实现微秒级的极速协程切换。

-----------------------------------------------------------------------------
5. 惰性 PyFrameObject 具象化机制
-----------------------------------------------------------------------------

为了维持 Python 强大的内省能力（如 ``sys._getframe()``、``inspect.currentframe()`` 或 ``traceback`` 打印），CPython 实现了精密的**惰性具象化（Lazy Materialization）机制**：

.. code-block:: text

   常规高速运行态:
     _PyInterpreterFrame (运行在 16KB Data Stack 上)
     frame->frame_obj == NULL (零 Python 对象开销)

   当用户执行 f = sys._getframe():
     1. 调用 _PyFrame_MakeAndSetFrameObject(frame);
     2. 在堆上分配一个真正的 PyFrameObject;
     3. 将 PyFrameObject->f_frame 指向数据栈上的 _PyInterpreterFrame;
     4. 将 _PyInterpreterFrame->frame_obj 指向该 PyFrameObject;
     5. 返回包装后的 PyFrameObject 给用户 Python 代码。

当包含 ``PyFrameObject`` 的外层函数执行完毕时，为了防止数据栈回退导致悬空指针，解释器会调用 ``_PyFrame_Copy()`` 将栈帧数据从线程数据栈物理迁移至 ``PyFrameObject->_f_frame_data`` 堆存储中，并将所有权修改为 ``FRAME_OWNED_BY_FRAME_OBJECT``，从而天衣无缝地兼顾了**极限运行速度**与**完全向后兼容的内省语义**。

-----------------------------------------------------------------------------
小结与下章导读
-----------------------------------------------------------------------------

本章系统解构了 CPython 3.13+ 虚拟机栈帧与运行时内存拓扑：
1. 从旧版全堆分配向轻量级 ``_PyInterpreterFrame`` 与惰性 ``PyFrameObject`` 的架构进化；
2. ``_PyInterpreterFrame`` 头部元数据与尾部 ``localsplus``（局部变量、Cell/Free 闭包与求值栈）连续一体化内存布局；
3. 线程级 16KB 数据栈块（``_PyStackChunk``）基于 Bump Pointer 的极速入栈与出栈算法；
4. 栈帧所有权模型（``_frameowner``）与生成器/协程内联帧的零拷贝挂起机制；
5. 惰性 ``PyFrameObject`` 具象化与栈帧数据向堆逃逸迁移的兼容性保障。

在掌握了栈帧的物理拓扑后，下一章我们将正式启动虚拟机的核心执行引擎—— **03_frame_and_eval_loop/02_ceval_interpreter_loop.rst（_PyEval_EvalFrameDefault 执行状态机、Direct Threaded Code 与指令分发）**。
