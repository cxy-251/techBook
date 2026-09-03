=======================================================
从裸机通电到 Linux 7.2 内核运行全景实战
=======================================================

本技术专著立足于真实物理硬件、时钟时序状态机与 4 大开源工业级源码库：
* **物理硬件虚拟化**：``/Volumes/LinuxKernel/qemu``
* **主板 BIOS 固件**：``/Volumes/LinuxKernel/seabios``
* **引导加载程序**：``/Volumes/LinuxKernel/grub``
* **操作系统内核**：``/Volumes/LinuxKernel/linux-7.2-rc1``

系统化解构从计算机按下电源键第一纳秒到多任务调度的全部微观物理与代码实现。

.. toctree::
   :maxdepth: 2
   :caption: 全书 12 大核心实战模块目录:
   :numbered:

   ROADMAP
   01_cpu_execution_and_traps/index
   02_qemu_hardware_emulation/index
   03_seabios_firmware_and_post/index
   04_grub2_bootloader_and_protocol/index
   05_kernel_decompressor_and_long_mode/index
   06_kernel_early_assembly_bootstrap/index
   07_linux_memory_subsystem_boot/index
   08_linux_interrupts_timers_and_smp/index
   09_linux_task_and_eevdf_scheduler/index
   10_linux_vfs_and_block_storage/index
   11_linux_syscalls_and_modern_io/index
   12_linux_isolation_and_pid1_init/index

索引与搜索
==========

* :ref:`genindex`
* :ref:`search`
