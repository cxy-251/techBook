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

第十二章结束在：

::

   qemu_platform_setup()
   → smp_setup()
   → smp_scan()
   → 0x10000 AP trampoline
   → INIT/SIPI 广播
   → AP 进入 entry_smp
   → AP 重放 MTRR 与 feature-control MSR
   → APIC ID 与 CountCPUs 更新
   → AP HLT
   → BSP 等待全部当前 CPU 报到
   → 恢复 0x10000
   → smp_setup() 返回

``qemu_platform_setup()`` 接下来执行：

.. code-block:: c

   if (MaxCountCPUs <= 255) {
       pirtable_setup();
       mptable_setup();
   }
   smbios_setup();

此刻机器状态：

* 当前执行者：SeaBIOS ``qemu_platform_setup()``；
* 当前主流程 CPU：BSP；
* 模式：32 位保护模式；
* 分页：关闭；
* 当前存在 CPU 数：已经由 AP 实际报到确认；
* APIC ID：已经发现；
* BSP 与 AP 的 MTRR、条件 feature-control：已经一致；
* BSP local APIC：已经开启；
* AP：已经执行过 SeaBIOS AP 路径，当前停在 ``HLT``；
* ``0x10000`` 临时 AP trampoline：已经恢复；
* ``CountCPUs``：保存实际报到数；
* ``MaxCountCPUs``：保存固件表需要覆盖的最大 CPU/APIC ID 范围；
* PIRQ table、MP table、SMBIOS：尚未建立；
* ACPI：尚未装载或生成；
* 存储、USB 与网络驱动：尚未开始介质探测；
* ``BootList``：尚无具体启动设备；
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

* Intel x86 APIC、INIT/SIPI 与多处理器启动资料；
* SeaBIOS 提交 ``c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf``；
* SeaBIOS ``src/fw/smp.c``、``src/romlayout.S``、``src/config.h`` 和 ``src/fw/paravirt.c``。

当前下一步
----------

收到继续指令后，从 ``qemu_platform_setup()`` 中的 ``pirtable_setup()``、``mptable_setup()`` 与
``smbios_setup()`` 开始，继续追踪 legacy PCI IRQ、CPU/APIC 与系统内存信息怎样交给后续软件。