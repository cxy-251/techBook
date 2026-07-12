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

当前主线
--------

::

   x86-64
   → QEMU q35
   → SeaBIOS
   → GRUB i386-pc
   → bzImage
   → Linux 6.12.95

开头从设备上电后的故事进入，最终主题仍然是 Linux 内核。正文按真实发生顺序连续讲述；达到适合一次
阅读的篇幅，并遇到自然控制权交接点时换章。

当前控制流回到 SeaBIOS ``qemu_platform_setup()``。AP 已通过 INIT/SIPI 从 ``0x10000`` 启动，重放 MSR、
报告 APIC ID 后停在 ``HLT``。下一步建立 PIRQ table、MP table 与 SMBIOS，GRUB 尚未被读取或执行。

开始工作
--------

新的对话或助手先阅读：

#. ``AGENTS.md``；
#. `当前状态 <project/STATE.rst>`_；
#. `Linux Kernel 入口 <docs/tracks/linux-kernel/index.rst>`_；
#. 已完成章节。