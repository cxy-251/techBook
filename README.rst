techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 入口 <docs/tracks/linux-kernel/index.rst>`_
* `第一章：按下电源键后，CPU 从哪里取得第一条指令？ <docs/tracks/linux-kernel/01-power-on-first-instruction.rst>`_
* `第二章：SeaBIOS 怎样从 16 位入口进入 32 位 C 代码？ <docs/tracks/linux-kernel/02-seabios-entry-to-32bit-c.rst>`_
* `第三章：SeaBIOS 怎样识别内存并把初始化代码搬到 RAM？ <docs/tracks/linux-kernel/03-seabios-memory-map-and-relocation.rst>`_
* `第四章：SeaBIOS 怎样在低端内存建立 IVT、BDA 和 EBDA？ <docs/tracks/linux-kernel/04-seabios-ivt-bda-ebda.rst>`_
* `第五章：SeaBIOS 怎样把自己变成可供启动软件调用的 BIOS？ <docs/tracks/linux-kernel/05-seabios-software-interfaces.rst>`_
* `第六章：SeaBIOS 怎样建立中断基础并启动内部线程？ <docs/tracks/linux-kernel/06-seabios-dma-pic-threads.rst>`_
* `第七章：SeaBIOS 怎样为 q35 编号 PCI 总线并发现设备？ <docs/tracks/linux-kernel/07-seabios-pci-bus-and-device-discovery.rst>`_
* `第八章：SeaBIOS 怎样启用 q35 MMCONFIG 并为 PCI 设备分配地址？ <docs/tracks/linux-kernel/08-seabios-q35-mmconfig-and-pci-bar-allocation.rst>`_
* `第九章：SeaBIOS 怎样接通 q35 PCI 中断并打开设备地址解码？ <docs/tracks/linux-kernel/09-seabios-pci-interrupt-routing-and-device-enable.rst>`_
* `第十章：SeaBIOS 怎样进入 SMM 并把处理入口藏进 SMRAM？ <docs/tracks/linux-kernel/10-seabios-smm-and-smbase-relocation.rst>`_
* `第十一章：SeaBIOS 怎样规定物理地址的缓存类型并准备每个 CPU 的 MSR？ <docs/tracks/linux-kernel/11-seabios-mtrr-and-feature-control.rst>`_
* `第十二章：SeaBIOS 怎样用 INIT/SIPI 唤醒其他 CPU？ <docs/tracks/linux-kernel/12-seabios-smp-init-sipi-and-ap-startup.rst>`_
* `第十三章：SeaBIOS 怎样把 CPU、IRQ 和内存信息写成固件表？ <docs/tracks/linux-kernel/13-seabios-pirq-mp-and-smbios-tables.rst>`_
* `第十四章：SeaBIOS 怎样执行 QEMU 的 ACPI table-loader 并找到 RSDP？ <docs/tracks/linux-kernel/14-seabios-acpi-table-loader-and-rsdp.rst>`_
* `第十五章：SeaBIOS 怎样沿 RSDP 读懂 ACPI 表图并解析 DSDT？ <docs/tracks/linux-kernel/15-seabios-acpi-table-graph-and-dsdt-parse.rst>`_
* `第十六章：SeaBIOS 怎样建立时间基准、18.2 Hz BIOS 时钟并初始化 TPM？ <docs/tracks/linux-kernel/16-seabios-timers-clock-and-tpm.rst>`_
* `第十七章：SeaBIOS 为什么先运行 VGA Option ROM 再初始化其他设备？ <docs/tracks/linux-kernel/17-seabios-vga-option-rom-and-console.rst>`_
* `第十八章：SeaBIOS 怎样枚举 USB 设备并初始化 PS/2 键盘？ <docs/tracks/linux-kernel/18-seabios-usb-and-ps2-input.rst>`_
* `第十九章：SeaBIOS 怎样发现 q35 的 AHCI 磁盘并把它加入启动列表？ <docs/tracks/linux-kernel/19-seabios-ahci-disk-and-bootlist.rst>`_
* `第二十章：SeaBIOS 怎样扫描普通 Option ROM 并把 BCV、BEV 加入启动列表？ <docs/tracks/linux-kernel/20-seabios-option-rom-bcv-bev.rst>`_
* `第二十一章：SeaBIOS 怎样执行 BCV 并把启动盘映射成 BIOS 0x80？ <docs/tracks/linux-kernel/21-seabios-bcv-drive-mapping-and-prepareboot.rst>`_
* `第二十二章：SeaBIOS 怎样把硬盘第一扇区读到 0x7c00 并交给 GRUB？ <docs/tracks/linux-kernel/22-seabios-int19-mbr-handoff.rst>`_
* `第二十三章：GRUB boot.img 怎样从 0x7c00 读出 core.img 的第一扇区？ <docs/tracks/linux-kernel/23-grub-boot-img-loads-diskboot.rst>`_
* `第二十四章：GRUB diskboot.img 怎样按 blocklist 读完 core.img？ <docs/tracks/linux-kernel/24-grub-diskboot-blocklist-loads-core.rst>`_
* `第二十五章：GRUB startup_raw 怎样进入保护模式并调用 grub_main？ <docs/tracks/linux-kernel/25-grub-startup-raw-protected-mode-and-grub-main.rst>`_
* `第二十六章：GRUB 怎样通过 BIOS E820 建立自己的堆？ <docs/tracks/linux-kernel/26-grub-machine-init-e820-and-heap.rst>`_
* `第二十七章：GRUB 怎样加载内建模块并建立 hd0、root 和 prefix？ <docs/tracks/linux-kernel/27-grub-built-in-modules-root-prefix-and-hd0.rst>`_
* `第二十八章：GRUB normal 怎样找到并打开 grub.cfg？ <docs/tracks/linux-kernel/28-grub-normal-opens-grub-cfg.rst>`_
* `第二十九章：GRUB 怎样解析 grub.cfg 并建立第一个 Linux 菜单项？ <docs/tracks/linux-kernel/29-grub-parses-config-and-builds-menuentry.rst>`_
* `第三十章：GRUB 怎样自动选择菜单项并装入 linux 命令模块？ <docs/tracks/linux-kernel/30-grub-autoboots-entry-and-loads-linux-module.rst>`_
* `第三十一章：GRUB linux 命令怎样检查并装载 Linux bzImage？ <docs/tracks/linux-kernel/31-grub-linux-command-loads-bzimage.rst>`_
* `第三十二章：GRUB 怎样把 initramfs 放到内核允许的高地址？ <docs/tracks/linux-kernel/32-grub-initrd-placement-and-boot-parameters.rst>`_
* `第三十三章：GRUB 怎样准备 boot_params 并把控制权交给 Linux？ <docs/tracks/linux-kernel/33-grub-boot-params-and-linux-handoff.rst>`_
* `第三十四章：Linux startup_32 怎样建立 4 GiB 映射并进入 64 位模式？ <docs/tracks/linux-kernel/34-linux-startup32-enters-long-mode.rst>`_
* `第三十五章：Linux startup_64 怎样把压缩内核搬到安全解压位置？ <docs/tracks/linux-kernel/35-linux-startup64-relocates-compressed-image.rst>`_
* `第三十六章：Linux 怎样建立解压映射并选择正式内核的位置？ <docs/tracks/linux-kernel/36-linux-builds-identity-maps-and-chooses-output.rst>`_
* `第三十七章：Linux 怎样解压 ELF 内核并进入正式 startup_64？ <docs/tracks/linux-kernel/37-linux-decompresses-elf-and-enters-kernel-startup64.rst>`_
* `第三十八章：Linux common_startup_64 怎样建立 boot CPU 的最早运行上下文？ <docs/tracks/linux-kernel/38-linux-common-startup64-builds-boot-cpu-context.rst>`_
* `第三十九章：x86_64_start_kernel 怎样清理临时环境并保存启动数据？ <docs/tracks/linux-kernel/39-linux-x86-64-start-kernel-cleans-early-environment.rst>`_
* `第四十章：Linux 怎样进入 start_kernel 并建立最早的通用内核状态？ <docs/tracks/linux-kernel/40-linux-start-kernel-establishes-earliest-generic-state.rst>`_
* `第四十一章：Linux setup_arch 怎样接管命令行并导入 E820 内存图？ <docs/tracks/linux-kernel/41-linux-setup-arch-imports-command-line-and-e820.rst>`_
* `第四十二章：Linux 怎样修正 E820 并计算自己真正能管理的物理页？ <docs/tracks/linux-kernel/42-linux-fixes-e820-and-computes-max-pfn.rst>`_
* `第四十三章：Linux 怎样把 E820 RAM 变成 memblock 并建立 early direct map？ <docs/tracks/linux-kernel/43-linux-builds-memblock-and-early-direct-map.rst>`_
* `第四十四章：Linux 怎样扩大启动日志并确认 initramfs 与 ACPI 表可以安全访问？ <docs/tracks/linux-kernel/44-linux-expands-log-buffer-and-reserves-initramfs-acpi.rst>`_
* `第四十五章：Linux 怎样从 MADT、MP table 和 SRAT 建立 CPU 拓扑与 NUMA node？ <docs/tracks/linux-kernel/45-linux-parses-early-acpi-and-builds-numa-nodes.rst>`_
* `第四十六章：Linux 怎样完成 x86-64 paging 收尾并建立 KASAN shadow？ <docs/tracks/linux-kernel/46-linux-finalizes-paging-and-kasan-shadow.rst>`_
* `第四十七章：Linux 怎样探测 tboot、映射 vsyscall 并在固件枚举前限制 CPU？ <docs/tracks/linux-kernel/47-linux-probes-tboot-maps-vsyscall-and-applies-early-limits.rst>`_
* `第四十八章：Linux 怎样完成 ACPI、Local APIC、IOAPIC 与 possible CPU 拓扑？ <docs/tracks/linux-kernel/48-linux-completes-acpi-apic-and-possible-cpu-topology.rst>`_
* `第四十九章：Linux 怎样登记物理资源并完成 setup_arch？ <docs/tracks/linux-kernel/49-linux-registers-resources-and-finishes-setup-arch.rst>`_
* `第五十章：Linux 怎样把 memblock 物理内存变成 node、zone 和 struct page？ <docs/tracks/linux-kernel/50-linux-builds-zones-and-struct-page-map.rst>`_
* `第五十一章：Linux 为什么再次检查 static key/static call，并怎样生成正式命令行？ <docs/tracks/linux-kernel/51-linux-rechecks-static-patching-and-builds-command-lines.rst>`_
* `第五十二章：Linux 怎样确定 CPU 编号上限并把 CPU0 迁入正式 per-CPU area？ <docs/tracks/linux-kernel/52-linux-builds-percpu-area-and-migrates-cpu0.rst>`_
* `第五十三章：Linux 为什么再次确认 CPU NUMA node，并把 CPU0 放入 hotplug ONLINE 状态？ <docs/tracks/linux-kernel/53-linux-initializes-boot-cpu-numa-and-hotplug-state.rst>`_
* `第五十四章：Linux 怎样把 GRUB 命令行分发给内核参数和 init？ <docs/tracks/linux-kernel/54-linux-dispatches-kernel-command-line-and-init-arguments.rst>`_
* `第五十五章：Linux 怎样把 memblock 空闲页交给 buddy，并建立 slab 与 vmalloc？ <docs/tracks/linux-kernel/55-linux-releases-memblock-to-buddy-and-starts-slab-vmalloc.rst>`_
* `第五十六章：Linux 怎样准备 Maple Tree、文本热补丁和 ftrace？ <docs/tracks/linux-kernel/56-linux-prepares-maple-tree-text-poking-and-ftrace.rst>`_
* `第五十七章：Linux 怎样建立 runqueue，并把 init_task 变成 CPU0 的 idle task？ <docs/tracks/linux-kernel/57-linux-initializes-runqueues-and-boot-idle-task.rst>`_
* `第五十八章：Linux 怎样建立 early workqueue、RCU 和 trace event 基础？ <docs/tracks/linux-kernel/58-linux-builds-workqueue-rcu-and-trace-foundations.rst>`_

当前主线
--------

::

   x86-64
   → QEMU q35
   → SeaBIOS
   → GNU GRUB 2.14 i386-pc
   → bzImage
   → Linux 6.12.95

当前 ``start_kernel()`` 已建立 scheduler runqueue、CPU0 idle task、early workqueue、RCU、trace event 和 context tracking 基础。

下一入口是 ``early_irq_init()``，随后进入 x86 IRQ、tick、timer、softirq 与 timekeeping。CPU0 仍是唯一 online CPU，硬件中断仍关闭，initramfs 尚未解包。

开始工作
--------

新的对话或助手先阅读：

#. ``AGENTS.md``；
#. `当前状态 <project/STATE.rst>`_；
#. `Linux Kernel 入口 <docs/tracks/linux-kernel/index.rst>`_；
#. 已完成章节。