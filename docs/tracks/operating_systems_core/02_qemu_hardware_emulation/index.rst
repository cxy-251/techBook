======================================================
模块 02：QEMU 硬件级虚拟化与平台芯片组模拟
======================================================

本模块深入 QEMU 模拟器与 KVM 虚拟化底层，系统化剖析 CPU 虚拟化实现（TCG 动态二进制翻译与 KVM 硬件加速）、Q35/I440FX 主板芯片组与 PCI 总线拓扑、MemoryRegion 内存虚拟化分层模型，以及传统 PIT/PIC 与现代 APIC/IOAPIC 模拟时钟与中断系统的实现。

.. toctree::
   :maxdepth: 2

   01_qemu_architecture_tcg_kvm
   02_q35_i440fx_chipset_bus
   03_memory_region_flatview
   04_apic_ioapic_pit_pic_emulation
