项目状态
========

最后更新
--------

2026-07-13

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成 ``LK-BOOT-001`` 至 ``LK-BOOT-049``。最新三章：

#. ``LK-BOOT-047``：Linux 怎样探测 tboot、映射 vsyscall 并在固件枚举前限制 CPU？
#. ``LK-BOOT-048``：Linux 怎样完成 ACPI、Local APIC、IOAPIC 与 possible CPU 拓扑？
#. ``LK-BOOT-049``：Linux 怎样登记物理资源并完成 setup_arch？

完整章节列表见 ``docs/tracks/linux-kernel/index.rst``，机器可读接续信息见 ``manifests/tracks/linux-kernel.toml``。

当前主线
--------

::

   x86-64
   → QEMU q35
   → SeaBIOS
   → GNU GRUB 2.14 i386-pc
   → bzImage
   → Linux 6.12.95

固定来源
--------

::

   SeaBIOS commit    = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   QEMU commit       = a759542a2c62f0fd3b65f5a66ad9868201014669
   GNU GRUB release  = 2.14
   GRUB commit       = d38d6a1a9b79427848976f53d474392cd29c2a71
   Linux release     = 6.12.95
   Linux source tag  = gregkh/linux v6.12.95
   Linux commit      = 7404ce51637231382873d0b55edabc2f3b841a9d

当前控制流位置
--------------

第四十七至四十九章已经完成：

::

   tboot_probe()
   → map_vsyscall()
   → early_quirks()
   → topology_apply_cmdline_limits_early()
   → acpi_boot_init()
   → parse FADT / full MADT / HPET / BGRT / SPCR
   → MP table fallback
   → init_apic_mappings()
   → topology_init_possible_cpus()
   → init_cpu_to_node()
   → init_gi_nodes()
   → io_apic_init_mappings()
   → x86_init.hyper.guest_late_init()
   → e820__reserve_resources()
   → e820__register_nosave_regions(max_pfn)
   → reserve_standard_io_resources()
   → e820__setup_pci_gap()
   → conditional VGA screen registration
   → x86_init.oem.banner()
   → x86_init.timers.wallclock_init()
   → therm_lvt_init()
   → mcheck_init()
   → register_refined_jiffies(CLOCK_TICK_RATE)
   → conditional EFI memmap quirks
   → unwind_init()
   → return from setup_arch()

此刻机器状态：

* 当前执行者：Linux 6.12.95 ``init/main.c:start_kernel()``；
* 精确位置：``setup_arch(&command_line)`` 已返回，``mm_core_init_early()`` 尚未调用；
* CPU：BSP / Linux CPU 0；
* mode：64 位 long mode；
* current task：``init_task``；
* interrupts：关闭，``early_boot_irqs_disabled = true``；
* E820 与标准 PC I/O ranges：已登记进 resource tree；
* hibernation nosave holes：已登记；
* PCI 32 位 MMIO gap：已选择并写入 ``pci_mem_start``；
* ACPI/APIC/IOAPIC/possible CPU/NUMA 拓扑：已完成启动期建立；
* wallclock backend：已完成条件选择，尚未在该调用中读取 RTC；
* thermal LVT：BSP firmware 初值已条件保存；
* MCE software decode/work framework：已初始化；
* refined-jiffies：已登记为后备 clocksource 候选；
* unwinder：已按构建配置初始化；
* ``setup_arch()``：已返回；
* buddy allocator：尚未建立；
* per-CPU area：尚未建立；
* scheduler：尚未初始化；
* AP：尚未唤醒；
* initramfs：尚未解包。

完成状态
--------

``complete`` 表示章节到达自然终点，关键技术事实已依据固定源码或规范核对。读者不承担技术审稿。

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。

当前下一步
----------

从 ``start_kernel():mm_core_init_early()`` 开始，沿真实调用顺序追踪通用内存管理早期核心、static key/static call、early security、boot config、正式命令行保存、CPU 数量与 per-CPU area。不要跳到 scheduler、AP 启动或 initramfs 解包。