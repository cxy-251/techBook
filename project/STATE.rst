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

第十一章结束在：

::

   qemu_platform_setup()
   → mtrr_setup()
   → fixed-range MTRR
   → q35 PCI hole variable MTRR
   → IA32_MTRR_DEF_TYPE 重新启用
   → msr_feature_control_setup()
   → 条件写 IA32_FEATURE_CONTROL
   → 返回

``qemu_platform_setup()`` 接下来执行：

.. code-block:: c

   smp_setup();

此刻机器状态：

* 当前执行者：SeaBIOS ``qemu_platform_setup()``；
* CPU：BSP；
* 模式：32 位保护模式；
* 分页：关闭；
* BSP MTRR：已经配置；
* 普通 RAM 默认缓存类型：WB；
* ``0xa0000-0xbffff``：UC；
* ``0xc0000-0xfffff``：WP；
* q35 ``0xc0000000-0xffffffff`` PCI hole：UC；
* ``IA32_FEATURE_CONTROL``：QEMU提供非零策略时已写入；
* ``smp_msr``：保存了 AP 需要重放的 MTRR 与 feature-control 写入序列；
* local APIC 的 SMP 启动配置：尚未执行；
* AP：尚未由 SeaBIOS 唤醒；
* ACPI、SMBIOS、MP table：尚未建立；
* 设备驱动与启动介质探测：尚未开始；
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

* Intel x86 MTRR、MSR、IA32_FEATURE_CONTROL 与 APIC/SMP 资料；
* SeaBIOS 提交 ``c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf``；
* SeaBIOS ``src/fw/mtrr.c``、``src/fw/smp.c``、``src/fw/paravirt.c`` 和 ``src/x86.h``；
* QEMU 提交 ``a759542a2c62f0fd3b65f5a66ad9868201014669`` 的 ``hw/i386/fw_cfg.c``。

当前下一步
----------

收到继续指令后，从 ``qemu_platform_setup():smp_setup()`` 开始，继续追踪 local APIC、INIT/SIPI、
``0x10000`` AP 启动跳板、共享栈锁、APIC ID 与 AP 重放 MSR。