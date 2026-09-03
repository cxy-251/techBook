=============================================================================
PyTypeObject 元类型、tp_* 槽位分发机制与 MRO 继承拓扑
=============================================================================

.. note:: 前置背景与上下文承接
   在前一章中，我们解构了 CPython 最底层的物理单元—— ``PyObject`` 与 ``PyVarObject`` 的对象头布局、引用计数与内存对齐。每一个 Python 对象头部的 ``ob_type`` 指针均指向一个全局或堆分配的类型对象。在 CPython 中，**类型本身也是一等公民对象**。本章将深入 CPython 核心源码文件 ``Objects/typeobject.c``、``Include/cpython/object.h`` 与 ``Include/internal/pycore_typeobject.h``，全景剖析 ``PyTypeObject`` 与 ``PyHeapTypeObject`` 的物理内存拓扑、``PyType_Ready()`` 初始化状态机、C3 线性化算法（MRO）的 C 语言实现、``tp_*`` 物理槽位与 Python 魔术方法的双向映射分发机制，以及多线程环境下的类型版本标签与槽位更新同步策略。

-----------------------------------------------------------------------------
1. PyTypeObject 与 PyHeapTypeObject 的物理内存拓扑
-----------------------------------------------------------------------------

在 C 语言层面，类型对象分为两类：
1. **静态内置类型（Static Builtin Types）**：如 ``PyType_Type``（元类 ``type``）、``PyBaseObject_Type``（基类 ``object``）、``PyLong_Type``、``PyList_Type`` 等，直接在 C 源码中通过全局结构体静态初始化，生命周期为进程全局不朽。
2. **堆分配动态类型（Heap Types）**：通过 Python 代码中的 ``class`` 关键字或 C API 中的 ``PyType_FromSpec()`` 动态创建的类。为了容纳类名、方法解析顺序、模块名及额外属性，它们使用扩展结构体 ``PyHeapTypeObject``。

静态类型 ``PyTypeObject`` 与动态类型 ``PyHeapTypeObject`` 的内存拓扑对比如下：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |             PyTypeObject (静态类型内存布局，约 400+ 字节)               |
   +===================+=====================================================+
   | PyObject_VAR_HEAD | ob_refcnt / ob_type / ob_size (变长对象头)          |
   +-------------------+-----------------------------------------------------+
   | 基础元数据        | tp_name, tp_basicsize, tp_itemsize                  |
   +-------------------+-----------------------------------------------------+
   | 核心方法槽位      | tp_dealloc, tp_repr, tp_hash, tp_call, tp_str       |
   |                   | tp_getattro, tp_setattro, tp_richcompare            |
   +-------------------+-----------------------------------------------------+
   | 子协议族指针      | tp_as_number   -> 指向 PyNumberMethods 结构体       |
   |                   | tp_as_sequence -> 指向 PySequenceMethods 结构体     |
   |                   | tp_as_mapping  -> 指向 PyMappingMethods 结构体      |
   |                   | tp_as_async    -> 指向 PyAsyncMethods 结构体        |
   |                   | tp_as_buffer   -> 指向 PyBufferProcs 结构体         |
   +-------------------+-----------------------------------------------------+
   | 继承与类型关系    | tp_base, tp_bases (基类元组), tp_mro (线性化元组)   |
   |                   | tp_subclasses (子类弱引用字典), tp_dict (属性字典)  |
   +-------------------+-----------------------------------------------------+
   | 虚拟机加速与缓存  | tp_version_tag (类型缓存版本号), tp_vectorcall      |
   +-------------------+-----------------------------------------------------+

   +-------------------------------------------------------------------------+
   |             PyHeapTypeObject (动态堆类型内存布局)                       |
   +===================+=====================================================+
   | ht_type           | 完整的 PyTypeObject 嵌入结构体                      |
   +-------------------+-----------------------------------------------------+
   | 嵌入子协议实体    | as_async, as_number, as_sequence, as_mapping        |
   |                   | (动态类不再外部分配结构，而是内嵌于尾部)            |
   +-------------------+-----------------------------------------------------+
   | 动态元数据字段    | ht_name, ht_qualname, ht_slots, ht_module           |
   +-------------------+-----------------------------------------------------+
   | 性能与特化缓存    | _spec_cache (PEP 659 特化自适应缓存)                |
   |                   | unique_id (Free-Threading 模式下的线程私有计数 ID)  |
   +-------------------+-----------------------------------------------------+

在 ``PyHeapTypeObject`` 中，四大操作协议结构（``as_number``、``as_sequence`` 等）被直接内联分配在同一个连续堆内存块中，使得 ``type->tp_as_number = &et->as_number`` 可以直接完成指针内联绑定，显著降低了堆分配碎片。

-----------------------------------------------------------------------------
2. PyType_Ready 状态机：类型的物理初始化流水线
-----------------------------------------------------------------------------

任何类型对象在使用前，必须经过 ``PyType_Ready(PyTypeObject *type)`` 的初始化。它是 CPython 类型系统的“固化流水线”，其核心执行步骤如下：

.. code-block:: text

   [PyType_Ready 入口]
           │
           ▼
   1. 参数校验与基类填充 (type_ready_set_base)
      └─ 若 tp_base 为 NULL 且非 object，默认绑定为 &PyBaseObject_Type
           │
           ▼
   2. 属性字典初始化 (type_ready_set_dict)
      └─ 为 tp_dict 分配 PyDictObject
           │
           ▼
   3. MRO 拓扑计算 (type_ready_mro)
      └─ 调用 mro_internal() 执行 C3 算法，填充 tp_mro 元组
           │
           ▼
   4. 继承槽位与协议族 (type_ready_inherit)
      └─ 沿着 tp_mro 逆向回溯，继承父类的 tp_* 函数指针与 tp_as_* 协议
           │
           ▼
   5. 填充描述符与方法 (type_ready_fill_dict)
      └─ 将 tp_methods、tp_members、tp_getset 转换为描述符注入 tp_dict
           │
           ▼
   6. 注册子类弱引用 (type_ready_add_subclasses)
      └─ 将自身注册至所有直接基类的 tp_subclasses 字典中
           │
           ▼
   7. 设置状态标志位 (Py_TPFLAGS_READY)
      └─ 完成类型就绪宣告

-----------------------------------------------------------------------------
3. C3 线性化算法（MRO）的 C 语言底层实现
-----------------------------------------------------------------------------

Python 的多重继承采用 **C3 线性化算法（C3 Superclass Linearization）**，该算法保证了三大核心数学性质：
1. **子类优先于父类（Subclass Order）**；
2. **基类列表局部优先级保持（Local Precedence Order）**；
3. **单调性（Monotonicity）**：在子类 MRO 中，父类间的相对先后顺序与在父类各自的 MRO 中完全一致。

C3 线性化递归公式
~~~~~~~~~~~~~~~~~

设类 $C$ 继承自基类列表 $B_1, B_2, \dots, B_n$，则 $C$ 的 MRO 线性化序列定义为：

$$L[C] = C + 	ext{merge}(L[B_1], L[B_2], \dots, L[B_n], (B_1, B_2, \dots, B_n))$$

CPython 中 ``pmerge()`` 的核心实现逻辑
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``Objects/typeobject.c`` 中，合并逻辑由 C 函数 ``pmerge()`` 驱动：

.. code-block:: c

   static int
   pmerge(PyObject *acc, PyObject **to_merge, Py_ssize_t to_merge_size)
   {
       /* to_merge 包含 n 个父类的 MRO 序列以及 1 个显式基类列表 */
       Py_ssize_t *remain = PyMem_New(Py_ssize_t, to_merge_size);
       /* remain[i] 记录第 i 个待合并子列表中当前候选元素的游标位置 */
       ...
     again:
       for (i = 0; i < to_merge_size; i++) {
           PyObject *candidate = PyTuple_GET_ITEM(to_merge[i], remain[i]);
           /* 检查 candidate 是否存在于其它任何子列表的尾部（tail） */
           for (j = 0; j < to_merge_size; j++) {
               if (tail_contains(to_merge[j], remain[j], candidate))
                   goto skip; /* 在尾部出现冲突，跳过该候选者 */
           }
           /* 候选者合法：追加到输出列表 acc 中 */
           PyList_Append(acc, candidate);
           /* 将所有包含该 candidate 的列表头指针推进 */
           for (j = 0; j < to_merge_size; j++) {
               if (remain[j] < PyTuple_GET_SIZE(to_merge[j]) &&
                   PyTuple_GET_ITEM(to_merge[j], remain[j]) == candidate) {
                   remain[j]++;
               }
           }
           goto again;
         skip: ;
       }
       ...
   }

如果遍历所有子列表均无法选出一个“未在任何其他列表尾部出现”的合法候选者，说明存在继承拓扑冲突，CPython 将直接抛出 ``TypeError: Cannot create a consistent method resolution order (MRO)``。

-----------------------------------------------------------------------------
4. 双向槽位分发机制（Slot Dispatch & slotdefs）
-----------------------------------------------------------------------------

CPython 的核心设计之一是：**C 语言底层的函数指针槽位（Slots）与 Python 层面的双下划线魔术方法（Dunder Methods）之间存在双向自动同步机制**。

双向映射矩阵 ``slotdefs``
~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``Objects/typeobject.c`` 中定义了一个静态表 ``slotdefs[]``，它建立了物理槽位偏移与方法名的映射：

.. code-block:: c

   static pytype_slotdef slotdefs[] = {
       TPSLOT(__repr__, tp_repr, slot_tp_repr, wrap_unaryfunc, "..."),
       TPSLOT(__hash__, tp_hash, slot_tp_hash, wrap_hashfunc, "..."),
       FLSLOT(__call__, tp_call, slot_tp_call, wrap_call, "...", PyWrapperFlag_KEYWORDS),
       TPSLOT(__getattribute__, tp_getattro, _Py_slot_tp_getattr_hook, wrap_binaryfunc, "..."),
       TPSLOT(__getitem__, tp_as_mapping.mp_subscript, slot_mp_subscript, wrap_binaryfunc, "..."),
       BINSLOT(__add__, tp_as_number.nb_add, slot_nb_add, "+"),
       ...
   };

双向桥接原理
~~~~~~~~~~~~

1. **正向绑定（C 槽位 -> Python 描述符）**：
   当 C 扩展模块定义了一个原生类型并填充了 ``tp_repr`` 函数指针时，``PyType_Ready()`` 会通过 ``add_operators()`` 自动在 ``tp_dict`` 中生成一个包装描述符 ``wrapper_descriptor``（关联 ``__repr__``）。当 Python 代码调用 ``obj.__repr__()`` 时，将通过包装器直接调用 C 原生函数指针。
2. **反向分发（Python 魔术方法 -> C 槽位）**：
   当 Python 代码中定义了 ``class MyClass: def __add__(self, other): ...`` 时，类的 ``tp_dict`` 中包含了 ``__add__`` 函数对象。``fixup_slot_dispatchers()`` 会通过 ``update_one_slot()``，将 ``type->tp_as_number->nb_add`` 槽位填充为通用的反向分发函数 ``slot_nb_add``。

当虚拟机执行字节码指令 ``BINARY_OP_ADD`` 时，直接通过 C 指针快速调用 ``Py_TYPE(a)->tp_as_number->nb_add(a, b)``，无需进行昂贵的字典查找。

-----------------------------------------------------------------------------
5. 描述符协议与属性查找仲裁拓扑
-----------------------------------------------------------------------------

在 Python 中访问一个属性 ``instance.attr`` 时，CPython 遵循严格的物理仲裁优先级：

.. code-block:: text

   [访问 instance.attr]
           │
           ▼
   1. 在 Py_TYPE(instance) 及其 MRO 中查找 attr (获取 descr)
           │
           ├─► 若 descr 是【数据描述符】(Data Descriptor, 实现了 tp_descr_set):
           │     └─► 立即调用 descr->tp_descr_get(descr, instance, type) 并返回！
           │
           ├─► 若 descr 非数据描述符（或未找到）:
           │     │
           │     ▼
           │   2. 检查 instance 自身的 __dict__ (或 Managed Dict)
           │     │
           │     ├─► 若在实例字典中找到 attr:
           │     │     └─► 直接返回实例属性值！
           │     │
           │     ▼
           │   3. 若实例字典未找到:
           │     │
           │     ├─► 若类中找到了【非数据描述符】(Non-data Descriptor, 仅实现 tp_descr_get):
           │     │     └─► 调用 descr->tp_descr_get(descr, instance, type) 并返回！
           │     │
           │     ├─► 若类中找到了普通属性（如类变量）:
           │     │     └─► 直接返回该类属性！
           │     │
           │     ▼
           │   4. 所有字典均未找到:
           │     └─► 回退调用 __getattr__ 钩子；若无则抛出 AttributeError

这一仲裁机制在 ``Objects/typeobject.c`` 的 ``_Py_type_getattro_impl()`` 与 ``Objects/object.c`` 的 ``PyObject_GenericGetAttr()`` 中严格固化。

-----------------------------------------------------------------------------
6. Free-Threading 自由线程下的类型锁与安全点槽位更新
-----------------------------------------------------------------------------

在 Python 3.13+ Free-Threading 模式（``Py_GIL_DISABLED``）下，多个并发线程可能在运行时动态修改类属性（例如通过 ``setattr(cls, '__getitem__', new_func)``）。

由于 CEval 虚拟机循环在执行字节码时是以**无锁、非原子方式直接读取 ``tp_*`` 槽位指针**以保证极致性能，CPython 采取了精密的**两阶段安全点同步机制（Two-Phase Safe Point Update）**：

.. code-block:: c

   static void
   apply_type_slot_updates(slot_update_t *updates)
   {
       pinned_mutexes_t pinned;
       /* 1. 锁定当前关键区互斥锁，防止死锁 */
       type_lock_prevent_release(&pinned);
       /* 2. 触发全局 Stop-the-World 安全点停顿，暂停所有执行 Python 字节码的线程 */
       types_stop_world();
       /* 3. 在完全无并发竞争的静止世界中，直接批量覆写所有子类的 C 槽位指针 */
       apply_slot_updates(updates);
       /* 4. 恢复所有工作线程运行 */
       types_start_world();
       type_lock_allow_release(&pinned);
   }

此外，每个类都维护一个 ``tp_version_tag``（类型版本标签）。一旦类属性被修改，``_PyType_Modified_Unlocked()`` 会递归清除该类及其所有派生类的版本标签，使得 Tier 1 / Tier 2 JIT 优化器中的内联缓存（Inline Cache）立即失效并重新特化。

-----------------------------------------------------------------------------
小结与下章导读
-----------------------------------------------------------------------------

本章系统拆解了 CPython 3.13+ 元类型系统与分发引擎的核心实现：
1. ``PyTypeObject`` 与 ``PyHeapTypeObject`` 的内存拓扑与内联协议结构；
2. ``PyType_Ready()`` 初始化流水线的状态变迁与属性固化；
3. C3 算法在 ``pmerge()`` 中的单调性保证与冲突检测；
4. ``slotdefs`` 驱动的 C 槽位与 Python 魔术方法双向同步网络；
5. 描述符协议的四级物理仲裁链；
6. 自由线程（Free-Threading）下结合 Stop-the-World 的类型修改安全性模型。

在建立了对象头（Chapter 1）与类型元模型（Chapter 2）的认知后，下一章我们将深入 CPython 的底层内存基础设施—— **内存分配器架构：从 PyMem/PyObject 内存池到 Python 3.13+ 引入的 Mimalloc 深度剖析**。
