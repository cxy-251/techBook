======================================================
模块 07：Linux 7.2 内存子系统全景初始化
======================================================

本模块深入 Linux 7.2-rc1 内存管理子系统（Memory Management, MM），系统化解构从物理内存探测到微观对象分配的全景架构：`start_kernel()` 启动总控时序与 `setup_arch()` 架构级初始化、`memblock` 早期物理内存分配器、物理内存直接映射区 (`PAGE_OFFSET`) 与页表构建、伙伴系统 (Buddy System) `struct page` / Zone / 阶数拆分与合并、SLUB 细粒度对象分配器快速/慢速路径、`vmalloc` 与 Fixmap 固定映射，以及 Per-CPU 变量物理存储机制。

.. toctree::
   :maxdepth: 2

   01_start_kernel_setup_arch
   02_memblock_allocator
   03_init_mem_mapping_pagetables
   04_buddy_system_page_alloc
   05_slub_allocator_internals
   06_vmalloc_and_fixmaps
   07_per_cpu_storage_mechanics
