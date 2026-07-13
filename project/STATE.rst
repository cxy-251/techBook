项目状态
========

最后更新
--------

2026-07-13

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成 ``LK-BOOT-001`` 至 ``LK-BOOT-064``。最新三章：

#. ``LK-BOOT-062``：Linux 怎样完成启动期随机数并第一次打开外部中断？
#. ``LK-BOOT-063``：Linux 怎样启用正式 console、锁依赖检查并完成 early ACPI？
#. ``LK-BOOT-064``：x86 怎样启动真实定时器、校准延时并完成 boot CPU 收尾？

完整章节列表见 ``docs/tracks/linux-kernel/index.rst``，机器可读接续信息见 ``manifests/tracks/linux-kernel.toml``。

当前主线
--------

::

   x86-64
   → QEMU q35
   → SeaBIOS
   → GNU GRUB 2.14 i386-pc
   → bzImage
   → Linux 7.2-rc1

固定来源
--------

::

   SeaBIOS commit    = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   QEMU commit       = a759542a2c62f0fd3b65f5a66ad9868201014669
   GNU GRUB release  = 2.14
   GRUB commit       = d38d6a1a9b79427848976f53d474392cd29c2a71
   Linux release     = 7.2-rc1
   Linux repository  = gregkh/linux
   Linux commit      = 7404ce51637231382873d0b55edabc2f3b841a9d

源码版本纠正
------------

固定 Linux commit ``7404ce51637231382873d0b55edabc2f3b841a9d`` 的 ``Makefile`` 标识为 ``7.2-rc1``。此前状态文件把它误写成 ``v6.12.95``；真正的 ``v6.12.95`` 是另一提交，且 ``start_kernel()`` 顺序不同。

第三十四章之后的技术调查和源码链接一直指向固定 commit，因此后续继续以该 commit 为权威来源。旧章节正文中残留的 ``Linux 6.12.95`` 仅是显示标签错误，不能据此更换源码路径。

当前控制流位置
--------------

第六十二至六十四章已经完成：

::

   random_init()
   → mix time/cycle data and finalize available CRNG state
   → kfence_init()
   → initialize boot task stack canary
   → initialize perf/profile and SMP call-function foundations
   → early_boot_irqs_disabled = false
   → local_irq_enable()
   → CPU0 IF becomes 1
   → kmem_cache_init_late()
   → console_init()
   → lockdep_init() / locking_selftest()
   → validate initrd placement
   → setup_per_cpu_pageset()
   → numa_policy_init()
   → acpi_early_init()
   → x86_late_time_init()
   → select interrupt mode
   → try HPET, fall back to PIT where required
   → initialize final APIC/PIC interrupt mode
   → tsc_init()
   → sched_clock_init()
   → calibrate_delay()
   → arch_cpu_finalize_init()
   → identify/finalize boot CPU, mitigations, FPU and alternatives

此刻机器状态：

* 当前执行者：Linux 7.2-rc1 ``init/main.c:start_kernel()``；
* 精确位置：``arch_cpu_finalize_init()`` 已返回，``pid_idr_init()`` 尚未调用；
* CPU：只有 BSP / Linux CPU0 online；
* mode：64 位 long mode；
* current task：``init_task`` / ``swapper/0`` / PID 0；
* interrupts：CPU0 IF=1，``early_boot_irqs_disabled = false``；
* IRQ：descriptor、vector、IDT gate 和最终 x86 interrupt mode 已建立；
* timer：HPET/PIT 路径已按运行时能力选择，legacy timer action 已按路径登记；
* TSC：已初始化和评估，最终 clocksource 仍由运行时选择与 watchdog 决定；
* sched clock：正式初始化完成；
* delay：``loops_per_jiffy`` 已校准或确认；
* scheduler：runqueue 与 idle task 已建立，PID 0 仍在同步执行 ``start_kernel()``；
* console：正式 console initcalls 已执行，具体 backend 取决于构建配置；
* lockdep：按配置完成初始化和启动 selftest；
* buddy/slab/vmalloc：可用，per-CPU pageset 已建立；
* NUMA policy：基础已建立；
* ACPI：early ACPICA/table 基础已建立，完整 bus/device scan 尚未执行；
* boot CPU：feature、idle routine、SMT、mitigation、FPU、alternatives 与 memory-encryption 收尾已完成；
* AP：尚未收到 INIT/SIPI；
* initramfs：尚未解包；
* PID allocator：尚未初始化；
* PID 1 / PID 2：尚未创建。

完成状态
--------

``complete`` 表示章节到达自然终点，关键技术事实已依据固定源码或规范核对。读者不承担技术审稿。

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。

当前下一步
----------

从 ``start_kernel():pid_idr_init()`` 开始，继续 ``anon_vma_init()``、``thread_stack_cache_init()``、``cred_init()``、``fork_init()``、``proc_caches_init()``、UTS/time namespace、key/security、network namespace、VFS/page cache、signal、proc/nsfs/pidfs、cpuset、memcg 与 cgroup 基础。保持边界清晰：这些调用是在创建 PID 1 前准备进程和文件系统对象，不代表用户进程已经存在。