======================================================
模块 06：Linux 7.2 内核汇编入口与早期平台建制
======================================================

本模块深入 Linux 7.2-rc1 内核主体汇编入口（`arch/x86/kernel/head_64.S` 与 `head64.c`），系统化解构内核从 64 位裸机跳转到 C 语言通用内核大门（`x86_64_start_kernel`）的全过程：BSS 段与早期堆清零、0 号空闲进程 (`init_task`) 栈挂载、抹除低端恒等映射并构建 `init_top_pgt` 早期页表、LA57 5 级分页与 4 级分页硬件动态探测、CR4/EFER 架构控制寄存器配置、CPUID 拓扑嗅探，以及早期异常表与 `early_idt_handler_array` 保护机制。

.. toctree::
   :maxdepth: 2

   01_startup_64_bss_early_pgt
   02_la57_paging_cpuid_features
   03_x86_64_start_kernel_transition
   04_early_idt_and_exception_table
