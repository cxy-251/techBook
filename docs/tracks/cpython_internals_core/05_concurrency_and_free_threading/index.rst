======================================================
第 5 模块：并发、GIL 与 3.13+ Free-Threading
======================================================

.. toctree::
   :maxdepth: 2
   :caption: 模块章节导航

   01_gil_internals_and_mutex_mechanisms
   02_pep_703_free_threaded_cpython
   03_biased_reference_counting
   04_thread_safe_stop_the_world_and_gc

模块概述
========

本模块深入现代 CPython 并发体系的底层实现与架构演进。

剖析传统 GIL（Global Interpreter Lock）互斥锁与条件变量机制、线程切换周期与竞争损耗；全方位拆解 PEP 703（Free-Threaded CPython）在完全移除 GIL 后保持内存安全与高性能的核心技术，包括偏向引用计数（Biased Reference Counting, BRC）、基于 Mimalloc 线程私有堆的无锁隔离、线程局部唯一 ID 映射、以及多线程并发垃圾回收的 Stop-the-World 安全点（Safe Point）同步机制。
