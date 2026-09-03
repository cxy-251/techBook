=============================================================================
PyObject 物理头布局、定长/变长对象与引用计数机制
=============================================================================

.. note:: 前置背景与上下文承接
   在现代操作系统与 64 位体系结构（如 x86-64 与 ARM64）中，CPU 执行指令与访问内存的核心物理单元是字节地址与寄存器。对于高级动态语言 Python 而言，其在操作系统视角下本质上是一个运行在用户态的 C 语言原生进程。无论是简单的整数 ``42``、字符串 ``"Hello"`` 还是复杂的函数、模块与类，在物理堆内存中都必须映射为一个严格遵守 C 语言内存对齐与结构体布局规则的二进制内存块。本章作为全书第一章，将直接深入 CPython 核心头文件 ``Include/object.h`` 与 ``Include/internal/pycore_object.h``，自底向上剖析 Python 对象的最小物理基石—— ``PyObject`` 与 ``PyVarObject`` 的内存拓扑、现代 64 位内存对齐优化、静态不朽对象（Immortal Objects）机制以及 Python 3.13+ Free-Threading（PEP 703 自由线程）下的偏向引用计数（Biased Reference Counting）物理实现。

-----------------------------------------------------------------------------
1. 物理内存视角下的 Python 对象
-----------------------------------------------------------------------------

在 Python 语言层，“一切皆为对象”是一句广为人知的抽象描述。然而在 CPython 虚拟机的 C 源码实现中，这一抽象概念被精确固化为一条铁律：

.. warning:: 核心物理约束
   **所有 Python 对象在物理堆内存中分配后，其首地址在生命周期内绝对不可改变，且所有指向该对象的指针均统一强制转换为 ``PyObject*`` 类型。**

为了实现面向对象的多态性与统一管理，CPython 没有依赖 C++ 的虚函数表指针（vptr），而是通过在所有对象的最起始物理地址处放置一个标准化的“对象头（Object Header）”结构来固化类型信息与生命周期状态。

标准构建（Standard Build with GIL）下的 PyObject 内存结构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在传统的带 GIL 构建中，所有定长对象的基础结构 ``struct _object`` 定义于 ``Include/object.h``：

.. code-block:: c

   struct _object {
       _Py_ANONYMOUS union {
   #if SIZEOF_VOID_P > 4
           int64_t ob_refcnt_full;
           struct {
   #  if PY_BIG_ENDIAN
               uint16_t ob_flags;
               uint16_t ob_overflow;
               uint32_t ob_refcnt;
   #  else
               uint32_t ob_refcnt;
               uint16_t ob_overflow;
               uint16_t ob_flags;
   #  endif
           };
   #else
           Py_ssize_t ob_refcnt;
   #endif
           _Py_ALIGNED_DEF(_PyObject_MIN_ALIGNMENT, char) _aligner;
       };
       PyTypeObject *ob_type;
   };

在 64 位架构（``SIZEOF_VOID_P == 8``）下，该结构体在物理内存中严格占用 **16 字节**，其字节拓扑分布如下：

.. code-block:: text

   +------------------------------------+------------------------------------+
   | 偏移量 (Offset)                    | 物理字段名称与含义                 |
   +====================================+====================================+
   | 0x00 ~ 0x03 (4 Bytes)              | uint32_t ob_refcnt (本地引用计数)  |
   +------------------------------------+------------------------------------+
   | 0x04 ~ 0x05 (2 Bytes)              | uint16_t ob_overflow (溢出标记)    |
   +------------------------------------+------------------------------------+
   | 0x06 ~ 0x07 (2 Bytes)              | uint16_t ob_flags (不朽/静态标记)  |
   +------------------------------------+------------------------------------+
   | 0x08 ~ 0x0F (8 Bytes)              | PyTypeObject *ob_type (类型指针)   |
   +------------------------------------+------------------------------------+

1. **``ob_refcnt``（引用计数）**：记录当前引用该内存块的指针总数。当且仅当该计数降至 0 时，对象触发析构并由内存分配器回收。
2. **``ob_flags`` 与 ``ob_overflow``**：用于支持 Python 3.12+ 引入的不朽对象（Immortal Objects）与溢出保护。
3. **``ob_type``（类型指针）**：指向描述该对象行为的元类型对象（如 ``&PyLong_Type``、``&PyUnicode_Type``）。通过该指针，虚拟机可在运行时分发加减法、属性查找、字符串化等所有魔术方法。

-----------------------------------------------------------------------------
2. 变长对象头：PyVarObject 与连续内存布局
-----------------------------------------------------------------------------

并非所有 Python 对象在创建时大小都是固定的。例如，整数 ``42`` 占用的字节数是固定的，而列表 ``[1, 2, 3]``、元组 ``("a", "b")`` 和字符串 ``"cpython"`` 所包含的元素个数在运行时各不相同。

为了高效支持变长容器，CPython 定义了 ``PyVarObject`` 结构：

.. code-block:: c

   struct PyVarObject {
       PyObject ob_base;
       Py_ssize_t ob_size; /* 变长部分容纳的元素数量 (非字节数) */
   };

.. code-block:: text

   +-------------------+--------------------+--------------------+
   | 0x00 ~ 0x07       | 0x08 ~ 0x0F        | 0x10 ~ 0x17        |
   +===================+====================+====================+
   | ob_refcnt / flags | PyTypeObject* type | Py_ssize_t ob_size |
   +-------------------+--------------------+--------------------+
   |<-------------- PyObject -------------->|                    |
   |<--------------------------- PyVarObject ------------------->|

- **``ob_size`` 的物理含义**：记录容器中有效逻辑元素的数量（例如列表中的元素指针数，字符串中的字符数）。注意它不是分配的内存总字节数。
- **结构体尾部数组（Flexible Array Member）**：变长对象在内存中通常采用连续分配策略。例如元组 ``PyTupleObject`` 定义为：

.. code-block:: c

   struct _tupleobject {
       PyObject_VAR_HEAD
       PyObject *ob_item[1]; /* 实际分配时扩展为 ob_size 个元素指针 */
   };

这种“单次分配、头部固定、尾部变长”的物理布局极大减少了内存碎片的产生，并提升了 CPU L1/L2 Cache 的缓存行命中率。

-----------------------------------------------------------------------------
3. Python 3.13+ Free-Threading 架构下的 PyObject 内存革命
-----------------------------------------------------------------------------

在 PEP 703（Free-Threaded CPython，即禁用全局解释器锁 GIL 的构建版本 ``Py_GIL_DISABLED``）中，多个线程可以真正并行执行 Python 字节码。如果多个线程同时对同一个对象的引用计数执行传统的非原子自增/自减，将导致严重的并发数据竞争（Data Race）；而如果对每一次引用计数修改都使用原子指令（如 x86 的 ``LOCK XADD`` 或 ARM 的 ``LDADDAL``），高频的跨核心缓存行失效（Cache Line Bouncing）将导致吞吐量急剧下滑。

为了兼顾内存安全与超高执行性能，CPython 3.13+ 重构了 Free-Threading 模式下的 ``PyObject`` 物理布局：

.. code-block:: c

   #if defined(Py_GIL_DISABLED)
   struct _object {
       _Py_ALIGNED_DEF(_PyObject_MIN_ALIGNMENT, uintptr_t) ob_tid;
       uint16_t ob_flags;
       PyMutex ob_mutex;           // 单对象细粒度轻量锁 (1 Byte)
       uint8_t ob_gc_bits;         // 垃圾回收状态位 (1 Byte)
       uint32_t ob_ref_local;      // 拥有者线程私有本地引用计数 (4 Bytes)
       Py_ssize_t ob_ref_shared;   // 跨线程共享原子引用计数 (8 Bytes)
       PyTypeObject *ob_type;      // 类型对象指针 (8 Bytes)
   };
   #endif

在 Free-Threading 模式下，``PyObject`` 扩展为 **32 字节**：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                    Free-Threaded PyObject 物理内存拓扑                  |
   +==================+======================================================+
   | 0x00 ~ 0x07      | uintptr_t ob_tid (所属线程 ID 或 0，亦充当 GC 链表指针)|
   +------------------+------------------------------------------------------+
   | 0x08 ~ 0x09      | uint16_t ob_flags (静态/不朽状态标志)                |
   +------------------+------------------------------------------------------+
   | 0x0A             | PyMutex ob_mutex (1字节原子轻量锁，用于属性修改同步) |
   +------------------+------------------------------------------------------+
   | 0x0B             | uint8_t ob_gc_bits (GC 追踪与遍历标记位)             |
   +------------------+------------------------------------------------------+
   | 0x0C ~ 0x0F      | uint32_t ob_ref_local (线程私有本地计数器)           |
   +------------------+------------------------------------------------------+
   | 0x10 ~ 0x17      | Py_ssize_t ob_ref_shared (跨线程原子计数与状态掩码)  |
   +------------------+------------------------------------------------------+
   | 0x18 ~ 0x1F      | PyTypeObject *ob_type (元类型指针)                   |
   +------------------+------------------------------------------------------+

偏向引用计数（Biased Reference Counting, BRC）机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

偏向引用计数的物理核心逻辑如下：

1. **线程归属判断**：每个对象在创建时，其 ``ob_tid`` 会记录创建该对象的线程 ID。在 ARM64 macOS 上，线程 ID 可直接通过系统寄存器指令 ``mrs %0, tpidrro_el0`` 以 1 个时钟周期的极低开销读取：

   .. code-block:: c

      static inline Py_ALWAYS_INLINE int
      _Py_IsOwnedByCurrentThread(PyObject *ob) {
          return ob->ob_tid == _Py_ThreadId();
      }

2. **本地路径（Fast Path）**：如果当前执行代码的线程就是该对象的拥有者（``_Py_IsOwnedByCurrentThread(op) == 1``），则增加引用计数只需直接对 ``ob_ref_local`` 进行普通的无锁局部加法，无需任何原子总线锁。
3. **共享路径（Shared Path）**：如果其他线程访问该对象，则将引用计数增量通过原子 CAS 指令累加到 ``ob_ref_shared`` 中。
4. **合并与回收**：当对象所属线程退出或对象触发销毁时，将本地计数与共享计数合并（``_Py_ExplicitMergeRefcount``），当总计数真正归零时安全释放内存。

-----------------------------------------------------------------------------
4. 不朽对象机制（Immortal Objects）
-----------------------------------------------------------------------------

在 Python 3.12 之前，即使是内置单例（如 ``None``, ``True``, ``False``, 小整数池 ``-5~256``, 空元组 ``()``），每当函数调用传入或返回它们时，CPU 依然必须执行 ``Py_INCREF`` 和 ``Py_DECREF``。

这在多解释器（Sub-interpreters）与多核心并发场景下引发了灾难性的“假共享（False Sharing）”：不同核心上的线程为了修改单例对象的引用计数，不断抢占该内存块所在缓存行的独占所有权，使 CPU 缓存一致性总线不堪重负。

为此，CPython 引入了 **静态不朽对象（Immortal Objects）** 机制：

.. code-block:: c

   #define _Py_IMMORTAL_FLAGS (1 << 0)
   #define _Py_STATIC_IMMORTAL_INITIAL_REFCNT 0x7FFFFFFF

- **不朽判定宏**：

  .. code-block:: c

     static inline int _Py_IsImmortal(PyObject *op) {
     #if defined(Py_GIL_DISABLED)
         return (op->ob_flags & _Py_IMMORTAL_FLAGS) != 0;
     #else
         return (op->ob_refcnt == _Py_STATIC_IMMORTAL_INITIAL_REFCNT);
     #endif
     }

- **无操作（No-op）增减**：在 ``_Py_RefcntAdd`` 与 ``Py_DECREF`` 中，一旦检测到 ``_Py_IsImmortal(op)`` 为真，直接跳过内存写入。这使得所有核心只以“只读（Shared Read）”模式共享这些单例，彻底消除了缓存行颠簸。

-----------------------------------------------------------------------------
5. 核心生命周期宏：Py_INCREF、Py_DECREF 与 Py_SETREF
-----------------------------------------------------------------------------

在 C 扩展与解释器内核中，对象的引用计数必须严格遵循 CPython 内存管理规约：

.. code-block:: c

   /* 增加引用计数 */
   static inline void _Py_INCREF(PyObject *op) {
       _Py_RefcntAdd(op, 1);
   }

   /* 释放引用并安全防止重入 */
   #define Py_SETREF(dst, src) \
       do { \
           PyObject **_tmp_dst_ptr = _Py_CAST(PyObject**, &(dst)); \
           PyObject *_tmp_old_dst = (*_tmp_dst_ptr); \
           *_tmp_dst_ptr = (src); \
           Py_DECREF(_tmp_old_dst); \
       } while (0)

.. seealso:: 为什么必须使用 Py_SETREF 而非 Py_DECREF(dst); dst = src;
   在复杂的 Python 对象析构过程中，``Py_DECREF(_tmp_old_dst)`` 可能会触发目标对象的 ``tp_dealloc`` 析构器。析构器内部可能执行任意用户级 Python 代码（如 ``__del__`` 钩子）。如果先执行 ``Py_DECREF``，在析构器执行期间 ``dst`` 仍指向已悬空的野指针；而 ``Py_SETREF`` 先将新对象指针赋给 ``dst``，然后再析构旧对象，从而物理杜绝了重入破坏。

-----------------------------------------------------------------------------
小结与下章导读
-----------------------------------------------------------------------------

本章系统剖析了 CPython 3.13+ 对象模型在物理内存层面的核心表示，厘清了：
1. ``PyObject`` 与 ``PyVarObject`` 的 16 字节 / 24 字节内存布局；
2. 64 位体系结构下通过联合体与位字段实现的对齐优化与不朽标记；
3. Free-Threading 构建下偏向引用计数（BRC）与硬件线程寄存器的加速机制；
4. 不朽对象消除 CPU 缓存行颠簸的物理原理。

在下一章中，我们将继续向上攀升，深入剖析 Python 类型系统的灵魂—— ``PyTypeObject`` 元类型、``tp_*`` 槽位分发状态机以及方法解析顺序（MRO）的 C 语言底层实现机制。
