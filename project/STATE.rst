项目状态
========

最后更新
--------

2026-07-13

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成 ``LK-BOOT-001`` 至 ``LK-BOOT-055``。最新三章：

#. ``LK-BOOT-053``：Linux 为什么再次确认 CPU NUMA node，并把 CPU0 放入 hotplug ONLINE 状态？
#. ``LK-BOOT-054``：Linux 怎样把 GRUB 命令行分发给内核参数和 init？
#. ``LK-BOOT-055``：Linux 怎样把 memblock 空闲页交给 buddy，并建立 slab 与 vmalloc？

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

第五十三至五十五章已经完成：

::

   early_numa_node_init()
   → ensure formal per-CPU CPU-to-node data is available
   → boot_cpu_hotplug_init()
   → mark CPU0 hotplug state/target as CPUHP_ONLINE
   → mark CPU0 booted once and AP sync ONLINE
   → print_kernel_cmdline(saved_command_line)
   → parse_early_param() idempotent checkpoint
   → parse_args("Booting kernel", static_command_line, ...)
   → dispatch __param and __setup options
   → collect unknown options for PID 1
   → split init arguments after -- and bootconfig init.*
   → random_init_early(command_line)
   → setup_log_buf(0)
   → vfs_caches_init_early()
   → sort_main_extable()
   → trap_init()
   → mm_core_init()
   → build zonelists and page allocator CPU-hotplug hooks
   → decide memory debugging/hardening static keys
   → memblock_free_all()
   → release free RAM into buddy
   → x86 mem_init() and after_bootmem transition
   → kmem_cache_init()
   → vmalloc_init(), espfix/PTI, mm and execmem caches

此刻机器状态：

* 当前执行者：Linux 6.12.95 ``init/main.c:start_kernel()``；
* 精确位置：``mm_core_init()`` 已返回，``maple_tree_init()`` 尚未调用；
* CPU：只有 BSP / Linux CPU0 online；
* mode：64 位 long mode；
* current task：``init_task``；
* interrupts：关闭，``early_boot_irqs_disabled = true``；
* CPU0 hotplug state：``state = target = CPUHP_ONLINE``；
* GRUB command line：已打印并完成内核参数、``__setup`` 参数和 init 参数分发；
* ``root=/dev/sda1 ro console=ttyS0``：已转换为后续根挂载与控制台策略，尚未执行实际挂载/console 初始化；
* node/zone/``struct page``：已建立；
* memblock free RAM：已交给 buddy；
* buddy allocator：可用；
* slab：``kmem_cache_init()`` 已完成，late 阶段尚未执行；
* vmalloc：可用；
* scheduler：尚未初始化；
* AP：尚未收到 INIT/SIPI；
* external IRQ：尚未启用；
* console：正式初始化尚未执行；
* initramfs：尚未解包；
* PID 1：尚未创建。

完成状态
--------

``complete`` 表示章节到达自然终点，关键技术事实已依据固定源码或规范核对。读者不承担技术审稿。

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。

当前下一步
----------

从 ``start_kernel():maple_tree_init()`` 开始，继续 ``poking_init()``、``ftrace_init()``、``early_trace_init()``，随后进入 ``sched_init()``。需要区分“scheduler 数据结构可用”“中断已开启”“AP 已启动”三个不同时间点；当前只有第一项即将发生。
