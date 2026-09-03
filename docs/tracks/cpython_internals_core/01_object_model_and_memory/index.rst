======================================================
第 1 模块：对象模型与内存基石
======================================================

.. toctree::
   :maxdepth: 2
   :caption: 模块章节导航

   01_pyobject_header_and_ob_refcnt
   02_type_object_and_slot_dispatch
   03_pyarena_and_mimalloc_allocator
   04_gc_and_cyclic_references

模块概述
========

本模块自底向上解构 CPython 运行时的核心内存对象模型。

从最基础的 `PyObject` 和 `PyVarObject` 内存头布局出发，剖析 64 位体系结构下的内存对齐、结构体填充、定长与变长对象的物理区分；深入探讨 Python 3.13+ Free-Threading（PEP 703 自由线程）模式下基于 `ob_tid`、`ob_ref_local` 与 `ob_ref_shared` 的偏向引用计数（Biased Reference Counting）底层实现机制；进而剖析 `PyTypeObject` 的元类型与槽位分发状态机、CPython 核心内存分配体系（PyMem/PyObject 内存池与 Mimalloc 架构）以及分代垃圾回收器打破循环引用的三色标记与双向链表迁移算法。
