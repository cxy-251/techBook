Linux Kernel
============

这本书讲 Linux 内核。开头从设备上电后的真实执行过程进入，先交代内核取得控制权之前发生的必要故事。

当前正文
--------

#. `第一章：按下电源键后，CPU 从哪里取得第一条指令？ <01-power-on-first-instruction.rst>`_
#. `第二章：SeaBIOS 怎样从 16 位入口进入 32 位 C 代码？ <02-seabios-entry-to-32bit-c.rst>`_
#. `第三章：SeaBIOS 怎样识别内存并把初始化代码搬到 RAM？ <03-seabios-memory-map-and-relocation.rst>`_
#. `第四章：SeaBIOS 怎样在低端内存建立 IVT、BDA 和 EBDA？ <04-seabios-ivt-bda-ebda.rst>`_
#. `第五章：SeaBIOS 怎样把自己变成可供启动软件调用的 BIOS？ <05-seabios-software-interfaces.rst>`_
#. `第六章：SeaBIOS 怎样建立中断基础并启动内部线程？ <06-seabios-dma-pic-threads.rst>`_
#. `第七章：SeaBIOS 怎样为 q35 编号 PCI 总线并发现设备？ <07-seabios-pci-bus-and-device-discovery.rst>`_
#. `第八章：SeaBIOS 怎样启用 q35 MMCONFIG 并为 PCI 设备分配地址？ <08-seabios-q35-mmconfig-and-pci-bar-allocation.rst>`_
#. `第九章：SeaBIOS 怎样接通 q35 PCI 中断并打开设备地址解码？ <09-seabios-pci-interrupt-routing-and-device-enable.rst>`_
#. `第十章：SeaBIOS 怎样进入 SMM 并把处理入口藏进 SMRAM？ <10-seabios-smm-and-smbase-relocation.rst>`_
#. `第十一章：SeaBIOS 怎样规定物理地址的缓存类型并准备每个 CPU 的 MSR？ <11-seabios-mtrr-and-feature-control.rst>`_
#. `第十二章：SeaBIOS 怎样用 INIT/SIPI 唤醒其他 CPU？ <12-seabios-smp-init-sipi-and-ap-startup.rst>`_
#. `第十三章：SeaBIOS 怎样把 CPU、IRQ 和内存信息写成固件表？ <13-seabios-pirq-mp-and-smbios-tables.rst>`_
#. `第十四章：SeaBIOS 怎样执行 QEMU 的 ACPI table-loader 并找到 RSDP？ <14-seabios-acpi-table-loader-and-rsdp.rst>`_
#. `第十五章：SeaBIOS 怎样沿 RSDP 读懂 ACPI 表图并解析 DSDT？ <15-seabios-acpi-table-graph-and-dsdt-parse.rst>`_
#. `第十六章：SeaBIOS 怎样建立时间基准、18.2 Hz BIOS 时钟并初始化 TPM？ <16-seabios-timers-clock-and-tpm.rst>`_
#. `第十七章：SeaBIOS 为什么先运行 VGA Option ROM 再初始化其他设备？ <17-seabios-vga-option-rom-and-console.rst>`_
#. `第十八章：SeaBIOS 怎样枚举 USB 设备并初始化 PS/2 键盘？ <18-seabios-usb-and-ps2-input.rst>`_

当前主线
--------

::

   x86-64
   → QEMU q35
   → SeaBIOS
   → GRUB i386-pc
   → bzImage
   → Linux 6.12.95

正文已经进入同步 ``device_hardware_setup()``：q35 EHCI/UHCI、USB port/class 枚举和 i8042 PS/2 keyboard 初始化已经启动。下一步从 ``block_setup()`` 进入 q35 内置 ICH9 AHCI SATA 启动磁盘探测。

章节组织
--------

正文沿时间线连续讲述。故事达到适合一次阅读的篇幅，并遇到执行者、CPU 模式、运行环境或控制入口的
自然交接点时换章。每章末尾记录当前执行者、当前状态和下一入口。

章节完成状态由固定源码和规范核对决定。读者反馈用于指出哪里难懂、希望展开或阅读不连续，不承担技术审稿。