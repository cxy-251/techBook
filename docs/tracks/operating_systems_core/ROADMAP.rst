========================================================================================
全书施工路线图与源码深度架构全景 (Roadmap & Deep Architecture Blueprint)
========================================================================================

《从裸机通电到 Linux 7.2 内核运行全景实战》立足于真实物理硬件、时钟时序状态机与 4 大开源工业级源码库：
* **物理硬件虚拟化**：``/Volumes/LinuxKernel/qemu``
* **主板 BIOS 固件**：``/Volumes/LinuxKernel/seabios``
* **引导加载程序**：``/Volumes/LinuxKernel/grub``
* **操作系统内核**：``/Volumes/LinuxKernel/linux-7.2-rc1``

本技术专著由 12 大核心实战模块、共计 60 个深度长篇章节构成，全链路贯穿从按下电源键第一纳秒到用户态 PID 1 (systemd) 运行的全景微观世界。

.. note::
   **状态机驱动与自校准规则 (State Machine Execution Rules)**
   * **[x] 已完工**：代表该章节已完成深度推导并在本地磁盘生成高质量 `.rst` 专著文件；
   * **[ ] 待施工**：后台定时调度任务将按序自动锁定第一个 `[ ]` 章节进行撰写与落盘；
   * **自动翻转**：每次定时任务完成落盘后，会自动将对应章节标记从 `[ ]` 翻转为 `[x]`，并挂载到对应模块的 `index.rst`。

----------------------------------------------------------------------------------------

模块 01：x86_64 处理器微架构与物理执行环境基石 (CPU Mechanics & Traps)
-----------------------------------------------------------------------
* [x] `01_cpu_execution_and_traps/01_registers_and_context.rst` - 晶体管速度鸿沟、片上通用与控制寄存器（GPR/PC/SP/FLAGS）物理时钟时序
* [x] `01_cpu_execution_and_traps/02_interrupts_and_traps.rst` - 物理中断引脚（INTR/NMI）、APIC 局部中断控制器与中断向量硬件分发机制
* [x] `01_cpu_execution_and_traps/03_privilege_and_syscall.rst` - CPU 硬件特权级状态机（Ring 0 vs Ring 3）与 SYSENTER / SYSCALL 硬件切栈机制

模块 02：QEMU 硬件级虚拟化与平台芯片组模拟 (QEMU Platform Emulation)
----------------------------------------------------------------------
* [x] `02_qemu_hardware_emulation/01_qemu_architecture_tcg_kvm.rst` - QEMU 核心架构：TCG 动态二进制翻译状态机与 KVM 内核虚拟机硬件加速原理
* [x] `02_qemu_hardware_emulation/02_q35_i440fx_chipset_bus.rst` - Q35 / I440FX 芯片组模拟：Host Bridge、PCIe Root Complex 与 LPC 总线拓扑
* [x] `02_qemu_hardware_emulation/03_memory_region_flatview.rst` - 内存虚拟化拓扑：MemoryRegion 树状分层、FlatView 展平算法与 RAMBlock 物理页映射
* [x] `02_qemu_hardware_emulation/04_apic_ioapic_pit_pic_emulation.rst` - 中断与定时系统模拟：PIT 8254、PIC 8259A、IOAPIC 与 Local APIC MMIO 寄存器映射

模块 03：SeaBIOS 固件启动、POST 自检与硬件建制 (SeaBIOS Firmware & POST)
-------------------------------------------------------------------------
* [x] `03_seabios_firmware_and_post/01_reset_vector_romlayout.rst` - CPU 上电复位向量 `0xFFFFFFF0`、Shadow ROM 映射与 SeaBIOS `romlayout.S` 汇编入口
* [x] `03_seabios_firmware_and_post/02_real_mode_to_32bit_transition.rst` - 16 位实模式与早期 32 位保护模式来回跃迁机制与堆栈切换
* [x] `03_seabios_firmware_and_post/03_pam_registers_shadow_ram.rst` - PAM (Programmable Attribute Map) 寄存器与 ROM 区域可读写/只读硬件状态切换
* [x] `03_seabios_firmware_and_post/04_post_sequence_bda_ebda.rst` - POST (Power-On Self-Test) 加电自检时序、BDA (0x400) 与 EBDA 内存拓扑建立
* [x] `03_seabios_firmware_and_post/05_pci_bus_scan_option_rom.rst` - PCI 总线递归扫描、BAR 空间物理地址分配与 Option ROM 扩展卡固件调用
* [x] `03_seabios_firmware_and_post/06_acpi_smbios_e820_generation.rst` - ACPI (RSDP/MADT/DSDT) 表与 SMBIOS 结构体动态生成及 E820 内存图构建
* [x] `03_seabios_firmware_and_post/07_bios_interrupts_and_mbr_load.rst` - BIOS 中断服务（INT 10h/13h/15h/19h）安装与 MBR 引导扇区 (0x7C00) 加载

模块 04：GRUB2 引导加载器与内核协议握手 (GRUB2 Bootloader & Protocol)
------------------------------------------------------------------------
* [x] `04_grub2_bootloader_and_protocol/01_mbr_boot_s_diskboot.rst` - MBR Stage 1 (`boot.S`) 446 字节机器码极限空间与跳转 `diskboot.S`
* [x] `04_grub2_bootloader_and_protocol/02_core_img_dynamic_modules.rst` - `core.img` (Stage 1.5/2) 架构：压缩自解压、动态模块加载器 (`dl.c`) 与符号解析
* [x] `04_grub2_bootloader_and_protocol/03_fs_drivers_and_grub_cfg.rst` - 最小文件系统驱动实现（ext2/4, FAT, Btrfs）与 `/boot/grub/grub.cfg` 语法解析引擎
* [x] `04_grub2_bootloader_and_protocol/04_a20_line_and_gdt_mode_switch.rst` - 打开 A20 地址线、加载 GDT 并完成 16 位实模式向 32 位保护模式跃迁
* [x] `04_grub2_bootloader_and_protocol/05_linux_boot_protocol_structs.rst` - Linux Boot Protocol 规范：`setup_header`、`struct boot_params` 内存布局与参数装配
* [x] `04_grub2_bootloader_and_protocol/06_vmlinuz_elf_initrd_loading.rst` - `vmlinuz` 容器结构解构、`vmlinux.bin` 与 initramfs/initrd 物理内存装载

模块 05：Linux 7.2 内核解压缩与 64 位长模式穿越 (Decompressor & Mode Switch)
------------------------------------------------------------------------------
* [x] `05_kernel_decompressor_and_long_mode/01_head_64_pic_relocation.rst` - 解压器入口 `arch/x86/boot/compressed/head_64.S` 与位置无关代码 (PIC) 物理重定位
* [x] `05_kernel_decompressor_and_long_mode/02_early_paging_and_long_mode.rst` - 早期页表构建：1GB/2MB 大页恒等映射与开启 64 位长模式 (IA-32e)
* [x] `05_kernel_decompressor_and_long_mode/03_decompression_zstd_kaslr.rst` - 内核解压引擎（misc.c、Zstandard 算法）与 KASLR (内核地址空间布局随机化)
* [x] `05_kernel_decompressor_and_long_mode/04_elf64_parsing_kernel_jump.rst` - ELF64 头部解析、程序段物理重定位与跳转真正内核入口 `startup_64`

模块 06：Linux 7.2 内核汇编入口与早期平台建制 (Kernel Early Assembly Boot)
---------------------------------------------------------------------------
* [x] `06_kernel_early_assembly_bootstrap/01_startup_64_bss_early_pgt.rst` - `arch/x86/kernel/head_64.S`：清除 BSS、设置初始栈与挂载 `init_top_pgt` 早期页表
* [x] `06_kernel_early_assembly_bootstrap/02_la57_paging_cpuid_features.rst` - 5 级分页 (LA57) 与 4 级分页动态检测、CR4 寄存器配置与 CPUID 特性拓扑嗅探
* [x] `06_kernel_early_assembly_bootstrap/03_x86_64_start_kernel_transition.rst` - `x86_64_start_kernel()`：物理到虚拟地址映射与首个 C 语言运行时建立
* [x] `06_kernel_early_assembly_bootstrap/04_early_idt_and_exception_table.rst` - `early_idt_handler_array`：早期中断描述符表挂载与双重错误保护

模块 07：Linux 7.2 内存子系统全景初始化 (Memory Subsystem Boot)
----------------------------------------------------------------
* [x] `07_linux_memory_subsystem_boot/01_start_kernel_setup_arch.rst` - `start_kernel()` 启动总控时序与 `setup_arch()` 架构级初始化
* [x] `07_linux_memory_subsystem_boot/02_memblock_allocator.rst` - `memblock` 早期物理内存分配器：内存块探测、保留区管理与物理地址分配
* [x] `07_linux_memory_subsystem_boot/03_init_mem_mapping_pagetables.rst` - 物理内存恒等映射与直接映射区 (`PAGE_OFFSET`) 构建：PGD/P4D/PUD/PMD/PTE 层次
* [x] `07_linux_memory_subsystem_boot/04_buddy_system_page_alloc.rst` - 伙伴系统 (Buddy System)：struct page、Zone (DMA/Normal/HighMem)、阶数拆分与合并
* [x] `07_linux_memory_subsystem_boot/05_slub_allocator_internals.rst` - SLUB 细粒度对象分配器：kmem_cache 拓扑、cpu_slab 无锁快速路径与 node_slab 慢速路径
* [x] `07_linux_memory_subsystem_boot/06_vmalloc_and_fixmaps.rst` - `vmalloc` 虚拟地址连续空间管理、Fixmap 固定映射与临时内核映射 (kmap)
* [x] `07_linux_memory_subsystem_boot/07_per_cpu_storage_mechanics.rst` - Per-CPU 变量物理存储机制：`setup_per_cpu_areas()` 与 GS 寄存器段基址硬件寻址

模块 08：Linux 7.2 中断体系、时钟源与多核 SMP 引导 (Interrupts, Timers & SMP)
------------------------------------------------------------------------------
* [x] `08_linux_interrupts_timers_and_smp/01_trap_init_and_idt_gates.rst` - `trap_init()` 与 IDT 中断描述符表全量初始化：中断门/陷阱门与 IST 独立异常栈
* [x] `08_linux_interrupts_timers_and_smp/02_ioapic_lapic_msi_routing.rst` - 中断控制器驱动拓扑：IO-APIC、Local APIC 与 MSI/MSI-X 消息中断硬件分发
* [x] `08_linux_interrupts_timers_and_smp/03_irq_domains_softirq_workqueues.rst` - 硬件 IRQ Domain 映射机制、中断上下半部与 Softirq / Tasklet / Workqueue
* [x] `08_linux_interrupts_timers_and_smp/04_clocksource_clockevents_nohz.rst` - 硬件高精度定时器 (HPET/TSC)、Clocksource、Clockevents 与 Tickless (NO_HZ) 机制
* [x] `08_linux_interrupts_timers_and_smp/05_smp_init_sipi_bus_sequence.rst` - 多核 SMP 上电启动：BSP (引导核) 向 AP (应用核) 发送 INIT-SIPI-SIPI 硬件唤醒总线时序
* [x] `08_linux_interrupts_timers_and_smp/06_secondary_startup_64_hotplug.rst` - `smpboot.c` 与 `secondary_startup_64`：从核微码加载、独立页表挂载与 CPU 热插拔

模块 09：Linux 7.2 任务管理与 EEVDF 调度器 (Tasks & EEVDF Scheduler)
---------------------------------------------------------------------
* [x] `09_linux_task_and_eevdf_scheduler/01_task_struct_and_thread_info.rst` - `struct task_struct` 核心拓扑解构：线程描述符、调度实体与内核栈内存布局
* [x] `09_linux_task_and_eevdf_scheduler/02_init_task_idle_thread.rst` - 初始 0 号任务 (`init_task` / Idle Thread) 静态编译诞生与每 CPU 运行队列绑定
* [x] `09_linux_task_and_eevdf_scheduler/03_kernel_clone_copy_process_cow.rst` - 进程创建核心机制：`kernel_clone()`、`copy_process()` 与写时复制 (COW) 机制
* [x] `09_linux_task_and_eevdf_scheduler/04_context_switch_switch_to.rst` - 上下文切换微观过程：`__switch_to()` 与 `__switch_to_asm()` 寄存器与栈指针原子切换
* [x] `09_linux_task_and_eevdf_scheduler/05_eevdf_scheduler_mathematics.rst` - EEVDF (Earliest Eligible Virtual Deadline First) 调度算法数学模型与 `cfs_rq` 运行队列
* [x] `09_linux_task_and_eevdf_scheduler/06_realtime_deadline_and_preemption.rst` - 实时调度策略 (FIFO/RR)、SCHED_DEADLINE 与 Linux 内核抢占机制 (PREEMPT_DYNAMIC)

模块 10：Linux 7.2 虚拟文件系统 (VFS) 与块设备存储架构 (VFS & Block Storage)
-----------------------------------------------------------------------------
* [x] `10_linux_vfs_and_block_storage/01_vfs_objects_sb_inode_dentry_file.rst` - VFS 四大核心对象：`super_block`、`inode`、`dentry` 与 `file` 拓扑与函数指针分发
* [x] `10_linux_vfs_and_block_storage/02_path_lookup_dcache_rcu.rst` - 路径查找与目录项缓存 (Dcache)：RCU 无锁并发路径遍历与哈希快速查找
* [x] `10_linux_vfs_and_block_storage/03_rootfs_and_initramfs_unpacking.rst` - `rootfs` 内存文件系统挂载与 `initramfs` (cpio 归档) 内核态解包全流程
* [x] `10_linux_vfs_and_block_storage/04_page_cache_address_space_writeback.rst` - 页缓存 (Page Cache) 机制：`address_space` 结构、XArray 检索与脏页异步回写
* [x] `10_linux_vfs_and_block_storage/05_blk_mq_architecture_and_bio.rst` - 通用块层与 `struct bio` 结构流转：多队列架构 (blk-mq) 软件暂存队列与硬件派发队列
* [x] `10_linux_vfs_and_block_storage/06_ext4_f2fs_disk_layout_journal.rst` - ext4 / F2FS 物理磁盘布局、元数据日志事务 (JBD2) 与闪存写入优化

模块 11：Linux 7.2 现代 I/O 引擎、系统调用与内核基础设施 (Syscalls & Modern I/O)
---------------------------------------------------------------------------------
* [x] `11_linux_syscalls_and_modern_io/01_syscall_entry_msr_lstar_pt_regs.rst` - 系统调用微观全链路：`entry_SYSCALL_64` 汇编入口、MSR_LSTAR 硬件跳转与 pt_regs 保存
* [x] `11_linux_syscalls_and_modern_io/02_vdso_vgetcpu_gettimeofday.rst` - vDSO (Virtual Dynamic Shared Object) 与用户态无系统调用直读硬件计时器
* [x] `11_linux_syscalls_and_modern_io/03_io_uring_sq_cq_ring_buffers.rst` - 现代异步 I/O 核心引擎：`io_uring` 提交队列 (SQ) 与完成队列 (CQ) 共享内存环形缓冲区设计
* [x] `11_linux_syscalls_and_modern_io/04_epoll_rbtree_and_readylist.rst` - 事件多路复用机制：`epoll` 红黑树结构、就绪链表与回调挂载
* [x] `11_linux_syscalls_and_modern_io/05_signals_generation_delivery_sigreturn.rst` - 信号处理机制 (Signals)：信号生成、悬挂队列、内核向用户态栈帧注入与 `sigreturn`

模块 12：Linux 7.2 运行时资源隔离与 1 号进程 (PID 1) 诞生 (Namespaces, Cgroups & PID 1)
----------------------------------------------------------------------------------------
* [x] `12_linux_isolation_and_pid1_init/01_namespaces_subsystem_topology.rst` - Linux Namespaces 隔离机制：PID、Mount、Network、IPC、UTS、User 命名空间数据结构
* [x] `12_linux_isolation_and_pid1_init/02_cgroups_v2_unified_hierarchy.rst` - Cgroups v2 统一层次结构：内存/CPU/IO 控制器拓扑与资源限制计算
* [x] `12_linux_isolation_and_pid1_init/03_kernel_init_thread_free_initmem.rst` - `kernel_init()` 内核线程启动与释放早期引导初始化内存 (`free_initmem()`)
* [x] `12_linux_isolation_and_pid1_init/04_kernel_execve_systemd_ring3.rst` - 用户空间大门开启：`kernel_execve()` 加载 `/sbin/init` (systemd) 并向 Ring 3 用户态跃迁
