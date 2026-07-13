项目状态
========

最后更新
--------

2026-07-13

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成 ``LK-BOOT-001`` 至 ``LK-BOOT-052``。最新三章：

#. ``LK-BOOT-050``：Linux 怎样把 memblock 物理内存变成 node、zone 和 struct page？
#. ``LK-BOOT-051``：Linux 为什么再次检查 static key/static call，并怎样生成正式命令行？
#. ``LK-BOOT-052``：Linux 怎样确定 CPU 编号上限并把 CPU0 迁入正式 per-CPU area？

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

第五十至五十二章已经完成：

::

   mm_core_init_early()
   → establish node / zone / sparse memory / struct page metadata
   → jump_label_init() and static_call_init() idempotent checks
   → early_security_init()
   → setup_boot_config()
   → setup_command_line(command_line)
   → setup_nr_cpu_ids()
   → derive runtime CPU-ID upper bound from cpu_possible_mask
   → setup_per_cpu_areas()
   → allocate embedded or page-backed per-CPU first chunk
   → establish __per_cpu_offset for every possible CPU
   → migrate early APIC / ACPI / NUMA maps
   → switch CPU0 to formal GDT and GS-relative per-CPU base
   → set node-to-cpumask and x86 SMP local masks
   → smp_prepare_boot_cpu()
   → native_pv_lock_init()

此刻机器状态：

* 当前执行者：Linux 6.12.95 ``init/main.c:start_kernel()``；
* 精确位置：``smp_prepare_boot_cpu()`` 已返回，``early_numa_node_init()`` 尚未调用；
* CPU：只有 BSP / Linux CPU 0 online；
* mode：64 位 long mode；
* current task：``init_task``；
* interrupts：关闭，``early_boot_irqs_disabled = true``；
* ``nr_cpu_ids``：已按 possible mask 最终收缩；
* per-CPU first chunk：已建立；
* possible CPU units：均已有 offset、CPU 编号和早期拓扑副本；
* CPU0：已切换到正式 per-CPU unit 和 GDT/GS base；
* early APIC/ACPI/NUMA arrays：数据已迁移，early pointers 已撤销；
* node-to-cpumask / x86 SMP masks：已建立；
* boot CPU SMP hook：已执行；
* AP：尚未收到 INIT/SIPI；
* boot CPU hotplug state：尚未完成下一阶段初始化；
* 正式命令行：已保存，尚未通用解析；
* buddy：尚未接收全部可分配 RAM；
* slab/scheduler：尚未初始化；
* initramfs：尚未解包。

完成状态
--------

``complete`` 表示章节到达自然终点，关键技术事实已依据固定源码或规范核对。读者不承担技术审稿。

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。

当前下一步
----------

从 ``start_kernel():early_numa_node_init()`` 开始，继续 ``boot_cpu_hotplug_init()``，随后打印 ``saved_command_line``、完成 early parameter 幂等入口和通用 ``parse_args()``，把内核参数与 ``init`` 参数真正分发。