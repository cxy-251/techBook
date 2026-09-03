======================================================
模块 03：SeaBIOS 固件启动、POST 自检与硬件建制
======================================================

本模块深入主板固件底层，结合 SeaBIOS 源码系统化解构计算机从按下电源键第一纳秒的 CPU 上电复位向量 (0xFFFFFFF0)、Shadow ROM 物理映射、16/32 位实模式与保护模式来回跃迁、PAM 寄存器可写/只读硬件切换、POST 加电自检时序与 BDA/EBDA 内存拓扑建立、PCI 总线递归扫描与 Option ROM 固件执行，以及 ACPI/SMBIOS 表与 E820 内存图生成全流程。

.. toctree::
   :maxdepth: 2

   01_reset_vector_romlayout
   02_real_mode_to_32bit_transition
   03_pam_registers_shadow_ram
   04_post_sequence_bda_ebda
   05_pci_bus_scan_option_rom
   06_acpi_smbios_e820_generation
   07_bios_interrupts_and_mbr_load
