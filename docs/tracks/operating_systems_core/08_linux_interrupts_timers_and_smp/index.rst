========================================================================
模块 08：Linux 7.2 中断体系、时钟源与多核 SMP 引导
========================================================================

本模块深入 Linux 7.2-rc1 中断系统、硬件定时器与多核处理器（SMP）引导拓扑，系统化解构从底层中断门分发到多核上电运行的全景硬件时序：`trap_init()` 与 IDT 中断描述符表全量初始化、中断门/陷阱门与 IST 独立异常栈、IO-APIC / Local APIC 与 MSI/MSI-X 消息中断路由、硬件 IRQ Domain 映射与软中断（Softirq）/ Workqueue 下半部机制、HPET / TSC 高精度时钟源与无滴答（NO_HZ）定时器、多核 SMP INIT-SIPI-SIPI 硬件总线唤醒时序，以及从核 `secondary_startup_64` 汇编建制与 CPU 热插拔。

.. toctree::
   :maxdepth: 2

   01_trap_init_and_idt_gates
   02_ioapic_lapic_msi_routing
   03_irq_domains_softirq_workqueues
   04_clocksource_clockevents_nohz
   05_smp_init_sipi_bus_sequence
   06_secondary_startup_64_hotplug
