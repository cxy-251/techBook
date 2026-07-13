项目状态
========

最后更新
--------

2026-07-13

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成 ``LK-BOOT-001`` 至 ``LK-BOOT-051``。最新三章：

#. ``LK-BOOT-049``：Linux 怎样登记物理资源并完成 setup_arch？
#. ``LK-BOOT-050``：Linux 怎样把 memblock 物理内存变成 node、zone 和 struct page？
#. ``LK-BOOT-051``：Linux 为什么再次检查 static key/static call，并怎样生成正式命令行？

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

第四十九至五十一章已经完成：

::

   finish setup_arch() and return to start_kernel()
   → mm_core_init_early()
   → establish nodes, zones, sparse memory and struct page metadata
   → jump_label_init() idempotent check on fixed x86 path
   → static_call_init() idempotent check on fixed x86 path
   → early_security_init()
   → prepare early LSM blob offsets and hooks
   → setup_boot_config()
   → conditionally detach bootconfig trailer from initramfs
   → conditionally convert kernel.* and init.* bootconfig keys
   → setup_command_line(command_line)
   → allocate saved_command_line and static_command_line from memblock

此刻机器状态：

* 当前执行者：Linux 6.12.95 ``init/main.c:start_kernel()``；
* 精确位置：``setup_command_line(command_line)`` 已返回，``setup_nr_cpu_ids()`` 尚未调用；
* CPU：BSP / Linux CPU 0；
* mode：64 位 long mode；
* current task：``init_task``；
* interrupts：关闭，``early_boot_irqs_disabled = true``；
* node/zone/``struct page``：已建立；
* memblock：仍活动；
* buddy：尚未接收全部可分配 RAM；
* static key/static call：固定 x86 路径此前已初始化，本阶段完成幂等确认；
* early LSM：已初始化并可安装 static-call hook；
* 普通 LSM 和 policy：尚未完成；
* bootconfig：已完成尾部识别、条件解析和从 initramfs 逻辑范围裁剪；
* ``saved_command_line``：已建立完整持久副本；
* ``static_command_line``：已建立可原地解析副本；
* ``nr_cpu_ids``：尚未按 possible mask 最终收缩；
* per-CPU area：尚未建立；
* CPU0：仍使用早期 per-CPU/GDT 基础；
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

从 ``start_kernel():setup_nr_cpu_ids()`` 开始，追踪 possible/present/online/active CPU mask 区别、x86-64 per-CPU first chunk、``__per_cpu_offset``、早期 APIC/ACPI/NUMA 映射迁移、CPU0 的 GDT/GS per-CPU base 切换，以及 boot CPU hotplug state 初始化。