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

当前主线
--------

::

   x86-64
   → QEMU q35
   → SeaBIOS
   → GRUB i386-pc
   → bzImage
   → Linux 6.12.95

正文已经从平台释放处理器复位，追踪到 SeaBIOS 为 PCI bridge 分配 bus number，并把所有已发现 function
缓存进 ``PCIDevices``。当前仍在 ``pci_setup()`` 内，下一步从 q35 MMCONFIG 和 PCI BAR 资源分配继续。

章节组织
--------

正文沿时间线连续讲述。故事达到适合一次阅读的篇幅，并遇到执行者、CPU 模式、运行环境或控制入口的
自然交接点时换章。每章末尾记录当前执行者、当前状态和下一入口。

章节完成状态由固定源码和规范核对决定。读者反馈用于指出哪里难懂、希望展开或阅读不连续，不承担技术审稿。