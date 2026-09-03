===========================================
Part 4: 移动内核底层机制 (Mobile Kernel)
===========================================

本模块解构移动平台针对能效与交互构建的内核子系统，涵盖 EAS 能效感知调度器、匿名共享内存 (Ashmem/memfd)、Low Memory Killer (LMKD) 进程回收、WakeLock 电源管理与内核安全隔离。

.. toctree::
   :maxdepth: 1
   :caption: 模块章节

   01_eas_energy_aware_scheduler_and_responsiveness
   02_virtual_memory_ashmem_and_low_memory_killer
   03_interrupt_bottom_half_dma_and_drivers
   04_tickless_idle_wakelock_and_power_management
   05_kernel_isolation_dac_mac_and_attack_surface
