第六十九章：Linux 怎样唤醒 AP，并让 workqueue 与 SMP scheduler 正式运行？
======================================================================

第六十八章结束后，PID 0 已进入 CPU0 的 idle loop。Linux 初始化主线转移到 PID 1 的 ``kernel_init()``。PID 2 ``kthreadd`` 已创建，因此 PID 1 可以开始执行会产生内核线程、worker 和异步任务的初始化路径。

PID 1 首先执行：

.. code-block:: c

   wait_for_completion(&kthreadd_done);
   kernel_init_freeable();

completion 已由 PID 0 在 ``rest_init()`` 中完成。PID 1 通过该屏障后进入 ``kernel_init_freeable()``。

本章追踪到 ``page_alloc_init_late()`` 返回，停在 ``do_basic_setup()`` 之前。自然边界是：AP、正式 workqueue、SMP scheduler topology 和依赖 SMP 的内存分配收尾已经具备，下一阶段将进入设备模型和全部 initcall。

PID 1 此时仍在内核态
-------------------

``kernel_init()`` 虽然属于未来的用户态 init task，当前仍运行内核 C 函数。它尚未调用 ``kernel_execve()``，没有装入 ``/init`` 或 ``/sbin/init``。

当前任务身份是：

.. code-block:: text

   current = PID 1
   entry   = kernel_init_freeable()
   mode    = kernel mode
   CPU     = initially CPU0

PID 0 已成为 idle task，PID 2 在 kthreadd 循环中等待创建请求。

允许完整 GFP 分配
----------------

``kernel_init_freeable()`` 首先执行：

.. code-block:: c

   gfp_allowed_mask = __GFP_BITS_MASK;

启动早期会限制部分 GFP flag，避免代码请求尚不能安全完成的 reclaim、I/O 或 filesystem 行为。scheduler 和基本内存管理已经运行后，PID 1 放开完整 GFP mask，使后续初始化可以使用正常 blocking allocation、reclaim 和 I/O 语义。

这不表示所有分配都一定成功，也不表示 swap、块设备和文件系统已经可用。它只取消 early-boot 对 GFP flag 的全局限制；具体路径仍受当前 subsystem 状态约束。

PID 1 获得全部 memory node 的分配资格
----------------------------------

接下来：

.. code-block:: c

   set_mems_allowed(node_states[N_MEMORY]);

第六十八章曾把 PID 1 的 CPU affinity 暂时限制在 CPU0。这里处理的是另一件事：memory-node policy。

``set_mems_allowed()`` 允许 init task 从所有具有内存的 node 分配页面。它不改变 CPU affinity，也不会启动 AP。CPU 可运行集合要等后面的 ``sched_init_smp()`` 调整。

``cad_pid`` 暂时指向 PID 1
------------------------

源码执行：

.. code-block:: c

   cad_pid = get_pid(task_pid(current));

``cad_pid`` 是 Ctrl-Alt-Del 相关动作默认发送信号的目标。当前 ``current`` 是 PID 1，因此初始目标保存为 init task 的 ``struct pid``。

这只是登记 signal target，不会发送信号，也不会触发 reboot。

``smp_prepare_cpus()`` 只准备 AP 启动环境
-------------------------------------

下一步是：

.. code-block:: c

   smp_prepare_cpus(setup_max_cpus);

在 x86 普通 APIC 路径中，它进入 ``native_smp_prepare_cpus()``，主要完成：

* 为 possible CPU 分配 topology sibling/core/die/LLC mask；
* 建立 CPU0 的 sibling topology 基线；
* 检查当前 APIC interrupt mode 是否支持 SMP；
* 为 boot CPU 建立 per-CPU clock-event 路径；
* 准备 AP startup delay、SMT 和平台 wake-up 策略。

这里必须保持边界：

.. code-block:: text

   smp_prepare_cpus()
   = 准备 AP 启动数据和平台方法
   ≠ 已向 AP 发送 INIT/SIPI
   ≠ AP 已 online

真正唤醒 secondary CPU 发生在后面的 ``smp_init()``。

``workqueue_init()`` 让 early work 真正可以执行
-------------------------------------------

第五十八章中的 ``workqueue_init_early()`` 只允许创建 workqueue，并允许 work item 排队或取消；当时没有 kthreadd，也没有正式 worker pool。

现在 PID 1 调用：

.. code-block:: c

   workqueue_init();

此时 PID 2 已存在，workqueue 可以创建 worker kthread，建立 normal/high-priority/unbound pool，并开始消费此前积压的 work item。

因此两个入口的区别是：

.. code-block:: text

   workqueue_init_early()
   → data structures and queueing are available

   workqueue_init()
   → worker execution environment becomes available

这不表示所有 workqueue 都已完成工作。它表示 work item 从此可以被 worker 并发执行。

``init_mm_internals()`` 接上依赖正常调度的 VM 维护
----------------------------------------------

随后调用：

.. code-block:: c

   init_mm_internals();

该入口建立 VM statistics、per-CPU threshold 和后续内存维护所需基础。某些 vmstat folding、NUMA statistics 和 background maintenance 依赖 timer、workqueue 或 online CPU，因此不能全部放在最早的 ``mm_core_init()`` 阶段。

它不是重新初始化 buddy allocator，也不会创建用户地址空间。PID 1 当前仍共享启动阶段的内核执行环境。

pre-SMP initcall 在 AP 上线前执行
-------------------------------

``do_pre_smp_initcalls()`` 遍历：

.. code-block:: text

   __initcall_start
   → __initcall0_start

这是链接器单独放在 normal initcall level 之前的一组 early initcall。它们被要求在 AP 正式 online 前完成，例如需要建立全局状态、CPU hotplug callback 或 AP 启动依赖的基础。

每个函数仍通过 ``do_one_initcall()`` 执行，内核会检查：

* 返回时 preempt count 是否失衡；
* 函数是否错误地保持 IRQ disabled；
* ``initcall_debug`` 是否需要记录耗时和返回值。

``lockup_detector_init()`` 准备 watchdog
-------------------------------------

lockup detector 在 AP bring-up 前建立 watchdog 基础。后续 CPU online 时，可以按 hotplug callback 为各 CPU 接上 softlockup/hardlockup 检测。

是否真正启用 NMI watchdog、使用 perf event，取决于配置、CPU capability 和命令行。调用该入口不能直接断言每个 QEMU vCPU 都已有硬件 NMI watchdog。

``smp_init()`` 才真正把 AP 唤醒
-----------------------------

PID 1 随后调用：

.. code-block:: c

   smp_init();

generic CPU hotplug 代码会在 ``setup_max_cpus`` 限制内遍历 present CPU，为每个 AP 创建 idle task，并通过 architecture bring-up callback 启动 CPU。

x86 普通路径的关键链条是：

.. code-block:: text

   smp_init()
   → cpu_up()/CPU hotplug state machine
   → native_kick_ap()
   → common_cpu_up()
   → prepare AP idle task, stack and IRQ stack
   → do_boot_cpu()
   → APIC wakeup method
   → startup trampoline
   → start_secondary()

若 APIC driver 没有更专用的 64-bit/32-bit wake-up 方法，``do_boot_cpu()`` 使用 INIT startup sequence，并把 trampoline 地址作为 SIPI vector 交给目标 APIC ID。

这里才是 Linux 内核自己的 AP bring-up。SeaBIOS 第十二章曾临时唤醒 AP 做固件初始化，随后 AP 又被置于等待状态；当前是 Linux 为自己建立每 CPU 内核上下文并让 AP 成为 online Linux CPU。

AP 从 trampoline 进入 ``start_secondary()``
-----------------------------------------

AP 收到启动消息后从 low-memory trampoline 开始，重新建立 Linux 需要的 mode、page table、GDT、per-CPU base 和 stack，随后进入 ``start_secondary()``。

``start_secondary()`` 对 AP 完成：

* CPU identification 与 feature consistency；
* Local APIC 和 per-CPU timer；
* scheduler、RCU、call-function 和 hotplug state；
* topology sibling 关系；
* 标记 CPU online/active；
* 最终进入该 CPU 自己的 ``cpu_startup_entry()`` idle loop。

AP online 后不持续执行 PID 1 的代码。每个 AP 先拥有自己的 idle task，等待 scheduler 给它分配 runnable task。

online CPU 数量取决于 QEMU 运行参数
-------------------------------

固定主线只规定 QEMU q35，没有固定 ``-smp`` 的 vCPU 数量，也没有固定 ``maxcpus=``、``nosmp`` 或 CPU isolation 参数。

因此本章只能确认：

* Linux 尝试启动允许范围内的 present AP；
* 成功启动的 AP 进入 online mask；
* 启动失败或被配置限制的 CPU 可能保持 offline。

不能预先写死最终 online CPU 数字。

``sched_init_smp()`` 让调度器理解真实 CPU topology
-----------------------------------------------

AP bring-up 完成后调用：

.. code-block:: c

   sched_init_smp();

此前 scheduler 已有每 CPU runqueue，但系统只能安全使用 boot CPU。现在调度器根据 online CPU、NUMA node、core/SMT/LLC topology、CPU isolation 和 housekeeping mask 建立 scheduling domains 与 load-balancing relationships。

它还解除 PID 1 的启动期 CPU0 pinning，把 init task 的 allowed mask 调整到合适的 non-isolated online CPU 集合。

因此三个阶段要分开：

.. code-block:: text

   sched_init()
   → runqueue and classes exist

   smp_init()
   → APs are brought online

   sched_init_smp()
   → scheduler domains and migration policy use actual SMP topology

``workqueue_init_topology()`` 更新 worker placement
------------------------------------------------

AP 和 scheduler topology 已稳定后，workqueue 根据 CPU affinity、NUMA node、housekeeping/isolation 和 unbound workqueue policy 重建或更新 worker-pool topology。

``workqueue_init()`` 已让 worker 能运行；``workqueue_init_topology()`` 解决这些 worker 在多 CPU 系统上应如何分布。它不是第二次创建整套 workqueue。

async、padata 与 page allocator late init
---------------------------------------

PID 1 继续执行：

.. code-block:: c

   async_init();
   padata_init();
   page_alloc_init_late();

``async_init()`` 建立通用 asynchronous init domain，使设备和 subsystem 可以并行执行允许异步化的初始化工作。

``padata_init()`` 准备 parallel-data framework。crypto 和其他需要“并行处理、按序提交”的 subsystem 可以在 online CPU 上分发任务。

``page_alloc_init_late()`` 完成必须等待 SMP/topology 的 allocator 收尾，例如按最终 CPU/node 状态建立或更新 zonelist、CPU hotplug callback、per-CPU page allocator 关系和 deferred page initialization。具体动作取决于配置。

它不代表所有物理页都空闲，也不代表内存回收线程已经完成全部工作；它把 page allocator 从 boot/SMP 过渡状态推进到正常多 CPU 运行环境。

本章结束时的系统状态
------------------

本章结束时：

* 当前主线执行者：PID 1 ``kernel_init_freeable()``；
* PID 0：CPU0 idle task；
* PID 2：``kthreadd`` 已可创建内核线程；
* workqueue：正式 worker execution 已开始；
* AP：允许且成功启动的 secondary CPU 已进入 online/idle；
* scheduler：SMP topology、domain 和 load balancing 基础已建立；
* PID 1：不再要求永久固定在 CPU0；
* per-CPU timer、RCU、IPI 与 idle task 已随 online CPU 建立；
* async、padata 和 allocator late init 已完成对应入口；
* 设备模型的完整初始化尚未开始；
* normal initcall levels 尚未执行；
* initramfs 尚未等待完成；
* PID 1 仍未 exec 用户态 init。

下一条控制流是：

.. code-block:: c

   do_basic_setup();

它将建立 ksysfs、driver core、``/proc/interrupts`` 支持，并按 pure、core、postcore、arch、subsys、fs、device、late 顺序运行 built-in initcall。

资料
----

* `Linux 7.2-rc1 init/main.c：kernel_init_freeable 的 SMP 与 basic setup 顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c>`_
* `Linux 7.2-rc1 arch/x86/kernel/smpboot.c：native_smp_prepare_cpus、AP trampoline 与 native_kick_ap <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/smpboot.c>`_
* `Linux 7.2-rc1 kernel/cpu.c：CPU hotplug state machine 与 secondary CPU bring-up <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/cpu.c>`_
* `Linux 7.2-rc1 kernel/sched/core.c：sched_init_smp <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/core.c>`_
* `Linux 7.2-rc1 kernel/workqueue.c：workqueue_init 与 topology setup <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/workqueue.c>`_
* `Linux 7.2-rc1 mm/vmstat.c：init_mm_internals <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/vmstat.c>`_
* `Linux 7.2-rc1 mm/page_alloc.c：page_alloc_init_late <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/page_alloc.c>`_