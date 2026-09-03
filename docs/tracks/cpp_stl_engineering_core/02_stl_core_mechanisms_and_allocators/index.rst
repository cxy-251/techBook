========================================================================
第 2 模块：STL 核心机制与内存子系统 (02_stl_core_mechanisms_and_allocators)
========================================================================

本模块深入剖析 C++ 标准模板库（STL）的核心抽象与底层内存子系统：从迭代器游标模型、能力分层拓扑与 traits 编译期萃取分发，到内存分配器（Allocator）接口契约、未初始化内存生命周期分离、std::pmr 多态内存资源池化管理以及异常安全强保证机制。

.. toctree::
   :maxdepth: 1

   01_iterator_taxonomy_and_traits_system
   02_allocator_concept_and_allocator_traits
   03_polymorphic_memory_resources_pmr
   04_exception_safety_guarantees_and_rollbacks
   05_generic_algorithm_decoupling_philosophy
