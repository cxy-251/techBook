项目状态
========

最后更新
--------

2026-07-12

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成：

#. ``LK-BOOT-001``：按下电源键后，CPU 从哪里取得第一条指令？
#. ``LK-BOOT-002``：SeaBIOS 怎样从 16 位入口进入 32 位 C 代码？
#. ``LK-BOOT-003``：SeaBIOS 怎样识别内存并把初始化代码搬到 RAM？
#. ``LK-BOOT-004``：SeaBIOS 怎样在低端内存建立 IVT、BDA 和 EBDA？
#. ``LK-BOOT-005``：SeaBIOS 怎样把自己变成可供启动软件调用的 BIOS？
#. ``LK-BOOT-006``：SeaBIOS 怎样建立中断基础并启动内部线程？
#. ``LK-BOOT-007``：SeaBIOS 怎样为 q35 编号 PCI 总线并发现设备？
#. ``LK-BOOT-008``：SeaBIOS 怎样启用 q35 MMCONFIG 并为 PCI 设备分配地址？
#. ``LK-BOOT-009``：SeaBIOS 怎样接通 q35 PCI 中断并打开设备地址解码？
#. ``LK-BOOT-010``：SeaBIOS 怎样进入 SMM 并把处理入口藏进 SMRAM？
#. ``LK-BOOT-011``：SeaBIOS 怎样规定物理地址的缓存类型并准备每个 CPU 的 MSR？
#. ``LK-BOOT-012``：SeaBIOS 怎样用 INIT/SIPI 唤醒其他 CPU？
#. ``LK-BOOT-013``：SeaBIOS 怎样把 CPU、IRQ 和内存信息写成固件表？
#. ``LK-BOOT-014``：SeaBIOS 怎样执行 QEMU 的 ACPI table-loader 并找到 RSDP？
#. ``LK-BOOT-015``：SeaBIOS 怎样沿 RSDP 读懂 ACPI 表图并解析 DSDT？
#. ``LK-BOOT-016``：SeaBIOS 怎样建立时间基准、18.2 Hz BIOS 时钟并初始化 TPM？
#. ``LK-BOOT-017``：SeaBIOS 为什么先运行 VGA Option ROM 再初始化其他设备？
#. ``LK-BOOT-018``：SeaBIOS 怎样枚举 USB 设备并初始化 PS/2 键盘？

当前主线
--------

::

   x86-64
   → QEMU q35
   → SeaBIOS
   → GRUB i386-pc
   → bzImage
   → Linux 6.12.95

当前控制流位置
--------------

第十八章结束在：

::

   maininit()
   → synchronous device_hardware_setup()
   → usb_setup()
   → q35 EHCI/UHCI controller threads
   → USB root-port / hub threads
   → address / descriptors / class dispatch
   → conditional USB HID or mass storage
   → ps2port_setup()
   → DSDT PNP0303 check
   → IRQ1 / INT09h and IRQ12 / INT74h
   → PS/2 keyboard setup thread
   → 即将进入 block_setup()

USB 和 PS/2 初始化任务可能仍在协作式线程中运行；``wait_threads()`` 尚未执行。

此刻机器状态：

* 当前主流程执行者：SeaBIOS ``device_hardware_setup()``；
* 主流程 CPU：BSP；
* 模式：32 位保护模式；
* 分页：关闭；
* EHCI/UHCI：已经开始配置并按 companion routing 枚举端口；
* USB HID：条件建立 boot keyboard/mouse pipe；
* USB mass storage：条件建立 drive 并加入启动候选；
* i8042 IRQ1/IRQ12：已经接通；
* PS/2 keyboard：正在或已经完成 controller test、BAT、scan set 2 与 translation；
* USB/PS2 输入：汇合到 ``process_key()``、BDA ring 和 ``INT 16h``；
* q35 内置 ICH9 AHCI：PCI function 已存在，SeaBIOS block driver 尚未开始探测；
* 普通非 VGA Option ROM：尚未扫描；
* ``BootList``：可能已有条件 USB 设备，尚未形成最终集合；
* GRUB：尚未被读取或执行；
* Linux：尚未装入内存。

完成状态
--------

``complete`` 表示章节已经到达自然终点，关键技术事实已依据固定源码或规范核对。读者不承担技术审稿。
读者反馈只用于指出哪里难懂、希望展开或阅读不连续。

资料格式
--------

章节末尾的资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航；章节列表集中放在 Linux
Kernel 目录页。

固定事实来源
------------

* USB 2.0、HID boot protocol、i8042 与 AT keyboard 资料；
* SeaBIOS 提交 ``c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf``；
* SeaBIOS ``src/hw/usb*.c``、``src/hw/ps2port.c``、``src/kbd.c`` 和 ``src/stacks.c``；
* QEMU 提交 ``a759542a2c62f0fd3b65f5a66ad9868201014669`` 的 ``hw/i386/pc_q35.c``。

当前下一步
----------

从 ``device_hardware_setup():block_setup()`` 开始。为保持可复现，启动磁盘固定走 QEMU q35 内置 ICH9 AHCI SATA 路径；追踪 HBA reset、BAR5、port link、IDENTIFY、LBA 容量、transfer mode、``boot_add_hd()``，并在 ``wait_threads()`` 完成后停止。