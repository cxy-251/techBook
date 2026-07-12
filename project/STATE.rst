项目状态
========

最后更新
--------

2026-07-13

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成 ``LK-BOOT-001`` 至 ``LK-BOOT-040``。最新三章：

#. ``LK-BOOT-038``：Linux common_startup_64 怎样建立 boot CPU 的最早运行上下文？
#. ``LK-BOOT-039``：x86_64_start_kernel 怎样清理临时环境并保存启动数据？
#. ``LK-BOOT-040``：Linux 怎样进入 start_kernel 并建立最早的通用内核状态？

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

第三十八至四十章已经完成：

::

   arch/x86/kernel/head_64.S:common_startup_64
   → sanitize CR4 and flush stale global identity translations through PGE toggle
   → identify BSP as Linux CPU 0
   → load CPU0 per-cpu offset
   → switch to init_task stack
   → load per-cpu GDT and GSBASE
   → install early IDT
   → enable EFER.SCE and conditional NXE
   → call initial_code = x86_64_start_kernel
   → reset early identity page tables
   → clear formal kernel BSS and brk
   → initialize conditional SME, KASAN and TDX early state
   → copy boot_params and kernel command line
   → load BSP microcode
   → x86_64_start_reservations
   → initialize PC legacy platform quirks
   → start_kernel
   → stack-end magic, processor id, debug objects and build id
   → early cgroup relation for init_task
   → force local IRQs disabled
   → mark CPU0 possible/present/online/active
   → print linux_banner
   → immediately before setup_arch(&command_line)

此刻机器状态：

* 当前执行者：Linux 6.12.95 ``init/main.c:start_kernel()``；
* 当前停点：``setup_arch(&command_line)`` 尚未调用；
* CPU：BSP / Linux CPU 0；
* CPU mode：64 位 long mode；
* RIP：正式内核高半区；
* current task：``init_task``；
* stack：``init_task`` 启动栈，栈底 magic 已写入；
* per-CPU GSBASE：CPU 0；
* early IDT：已安装；
* ``boot_params``：已复制到内核全局对象；
* command line：已复制为 ``root=/dev/sda1 ro console=ttyS0``；
* BSP microcode：早期加载已执行；
* temporary identity mapping：已从 ``early_top_pgt`` 清除；
* CPU 0 masks：possible、present、online、active；
* interrupts：关闭；
* architecture setup：尚未执行；
* memblock：尚未完成 x86 初始化；
* initramfs：尚未展开；
* scheduler、VFS、initcall：尚未初始化。

完成状态
--------

``complete`` 表示章节到达自然终点，关键技术事实已依据固定源码或规范核对。读者不承担技术审稿。

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。

当前下一步
----------

从 ``arch/x86/kernel/setup.c:setup_arch(&command_line)`` 第一条真实调用开始，追踪 boot command line 接管、``boot_params``/setup_data、E820 内存图导入、BIOS 与内核映像保留区、memblock 建立和 early page-table/direct-map 初始化。不要用“完成架构初始化”一句跨过该大型阶段。