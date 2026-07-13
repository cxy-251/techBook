项目状态
========

最后更新
--------

2026-07-13

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成 ``LK-BOOT-001`` 至 ``LK-BOOT-070``。最新三章：

#. ``LK-BOOT-068``：Linux 怎样创建 PID 1、PID 2，并让 PID 0 进入 idle loop？
#. ``LK-BOOT-069``：Linux 怎样唤醒 AP，并让 workqueue 与 SMP scheduler 正式运行？
#. ``LK-BOOT-070``：Linux 怎样运行全部 built-in initcall，并准备 initramfs 与 root filesystem？

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

固定 Linux commit ``7404ce51637231382873d0b55edabc2f3b841a9d`` 的 ``Makefile`` 标识为 ``7.2-rc1``。旧章节中残留的 ``Linux 6.12.95`` 只是历史显示标签错误；后续技术事实继续以固定 commit 为权威来源。

当前控制流位置
--------------

第六十八至七十章已经完成：

::

   rest_init()
   → rcu_scheduler_starting()
   → user_mode_thread(kernel_init)
   → create PID 1
   → pin PID 1 temporarily to CPU0
   → kernel_thread(kthreadd)
   → create PID 2
   → system_state = SYSTEM_SCHEDULING
   → complete(kthreadd_done)
   → schedule_preempt_disabled()
   → PID 0 enters cpu_startup_entry()/idle loop

   PID 1 kernel_init()
   → wait_for_completion(kthreadd_done)
   → kernel_init_freeable()
   → enable full GFP mask and memory-node access
   → smp_prepare_cpus()
   → workqueue_init()
   → init_mm_internals()
   → do_pre_smp_initcalls()
   → lockup_detector_init()
   → smp_init()
   → bring permitted APs online through x86 startup trampoline
   → sched_init_smp()
   → workqueue_init_topology()
   → async_init() / padata_init()
   → page_alloc_init_late()

   → do_basic_setup()
   → cpuset_init_smp()
   → ksysfs_init()
   → driver_init()
   → init_irq_proc()
   → do_ctors()
   → do_initcalls()
   → pure/core/postcore/arch/subsys/fs/device/late
   → kunit_run_all_tests()
   → wait_for_initramfs()
   → console_on_rootfs()
   → check executable /init
   → keep initramfs root when /init is executable
     or prepare_namespace() mounts root=/dev/sda1 and pivots
   → integrity_load_keys()
   → kernel_init_freeable() returns

此刻机器状态：

* 当前主线执行者：Linux 7.2-rc1 PID 1 ``init/main.c:kernel_init()``；
* 精确位置：``kernel_init_freeable()`` 已返回，``async_synchronize_full()`` 尚未调用；
* mode：PID 1 仍在 64 位 kernel mode，尚未 exec 用户程序；
* PID 0：``swapper/0`` 已进入 CPU0 idle loop；
* PID 1：未来的 init task，当前继续内核收尾；
* PID 2：``kthreadd`` 已运行并可创建内核线程；
* CPU：CPU0 online；配置允许且成功启动的 AP 已进入各自 online/idle 状态，数量由实际 QEMU ``-smp``、命令行与启动结果决定；
* interrupts：online CPU 的普通中断已启用；
* scheduler：SMP domains、topology 和 load-balancing 基础已建立；
* workqueue：正式 worker pool 与 topology 已建立；
* driver model：device、bus、class、firmware、platform 等 core 已建立；
* initcalls：pure 至 late 的 built-in initcall 已全部调用；
* asynchronous work：仍可能存在，下一步由 ``async_synchronize_full()`` 汇合；
* ACPI/PCI/device：已按配置运行相应 initcall 和 probe，具体设备成功状态依赖 ``.config`` 与运行时；
* initramfs：专用 async 解包已经完成；
* console：PID 1 已尝试把 fd 0、1、2 连接到 ``/dev/console``；
* root branch：若 rootfs 中存在可执行 ``/init``，当前保留 initramfs root 给 early userspace；否则 ``prepare_namespace()`` 已尝试挂载 ``root=/dev/sda1`` 并 pivot；
* integrity：key loading 已按配置执行；
* ``__init`` memory：尚未释放；
* kernel rodata：尚未执行最终只读标记；
* PTI：最终 userspace page-table 收尾尚未执行；
* system state：仍未进入 ``SYSTEM_RUNNING``；
* user-space init：尚未 ``kernel_execve()``。

关键边界
--------

必须继续分开以下事实：

#. ``user_mode_thread(kernel_init)`` 创建 PID 1，不代表 PID 1 已进入用户态；
#. ``smp_prepare_cpus()`` 准备 AP 启动，不代表 AP 已 online；真正 bring-up 在 ``smp_init()``；
#. ``do_initcalls()`` 返回表示同步 built-in initcall 已调用完，不代表所有 async probe/work 已完成；
#. initramfs 解包完成不等于内核一定已经挂载 ``/dev/sda1``；可执行 ``/init`` 会让 early userspace 接管 root 切换；
#. driver model 建立不等于所有硬件 driver 均已成功 probe；
#. 当前 PID 1 仍是内核函数执行者，成功 ``kernel_execve()`` 后才成为真正用户态 init。

完成状态
--------

``complete`` 表示章节到达自然终点，关键技术事实已依据固定源码或规范核对。读者不承担技术审稿。

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。

当前下一步
----------

从 PID 1 ``kernel_init():async_synchronize_full()`` 开始，继续等待全部异步初始化，设置 ``SYSTEM_FREEING_INITMEM``，释放 kprobe/ftrace/kgdb/bootconfig 与 ``__init`` memory，标记 kernel rodata 只读，执行 ``pti_finalize()``，切换到 ``SYSTEM_RUNNING``，结束 in-kernel boot RCU 状态并处理 sysctl 参数。随后按顺序尝试 ``/init``、``init=``、``CONFIG_DEFAULT_INIT``、``/sbin/init``、``/etc/init``、``/bin/init``、``/bin/sh``，成功 ``kernel_execve()`` 后 PID 1 才进入用户态。