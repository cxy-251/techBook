第五十八章：Linux 怎样建立 early workqueue、RCU 和 trace event 基础？
====================================================================

第五十七章结束时，Linux 已经为每个 possible CPU 建立 runqueue，并把当前 ``init_task`` 确认为 CPU0 的 boot idle task。

``start_kernel()`` 接下来执行：

.. code-block:: c

   radix_tree_init();
   housekeeping_init();
   workqueue_init_early();
   rcu_init();
   kvfree_rcu_init();
   trace_init();
   context_tracking_init();

本章追踪到 ``context_tracking_init()`` 返回，停在 ``early_irq_init()`` 之前。

这段控制流的共同目标是：在硬件中断和时间系统启动前，先准备那些会被后续所有异步子系统依赖的通用对象管理、延迟执行、并发回收和事件记录基础。

为什么 Maple Tree 后面仍要初始化 radix tree
------------------------------------------

第五十六章已经初始化 Maple Tree。当前第一条调用仍是：

.. code-block:: c

   radix_tree_init();

现代 radix-tree API 的底层已经与 XArray 紧密关联，但大量内核代码仍通过 radix tree、XArray、IDR/IDA 等接口按整数索引保存对象。

典型用途包括：

* page cache 中的 page/folio index；
* inode、设备号或对象 ID 映射；
* IDR 中的整数 ID 分配；
* 某些驱动和文件系统的稀疏对象表。

Maple Tree 更擅长保存连续范围，radix tree/XArray 更适合离散整数索引。两种结构在内核中并存。

``radix_tree_init()`` 建立节点 slab cache
---------------------------------------

radix tree 会随着最高索引和对象数量增长出不同高度的节点。

函数创建：

.. code-block:: c

   radix_tree_node_cachep =
       kmem_cache_create("radix_tree_node", ...);

每个 ``struct radix_tree_node`` 包含：

* 多个 child/object slot；
* tag bitmap；
* parent、shift、offset；
* RCU 回收节点；
* XArray/radix-tree 根关联信息。

第五十五章 slab 已可用，所以现在可以建立这个专用 cache。

当前没有把磁盘页面装入 page cache
--------------------------------

建立 ``radix_tree_node_cachep`` 只表示后续索引树能够分配节点。

当前尚未发生：

* AHCI 驱动读取磁盘；
* ext4 创建 inode/page cache；
* 根文件系统挂载；
* 用户进程读取文件。

所以 page cache 的核心索引对象已具备分配条件，实际文件页面还没有进入其中。

为什么 radix tree 有 per-CPU preload pool
----------------------------------------

某些调用者在持锁、禁抢占或不能睡眠的区域中插入对象。

若树在插入时必须增长，临时申请节点可能失败或不能阻塞。radix tree 因此维护：

.. code-block:: c

   DEFINE_PER_CPU(struct radix_tree_preload,
                  radix_tree_preloads);

调用者可以在进入临界区前预先分配足够节点，再从当前 CPU 的 preload pool 中取用。

``radix_tree_init()`` 还登记 CPU hotplug teardown callback：CPU 下线时，清理该 CPU 尚未使用的 preload nodes，避免 per-CPU 缓存泄漏。

当前 CPU0 不会在此处下线，AP 也尚未上线。这里先把未来 hotplug 生命周期接入通用状态机。

housekeeping 解决“后台工作应该在哪些 CPU 上运行”
------------------------------------------------

下一条调用：

.. code-block:: c

   housekeeping_init();

Linux 支持通过：

.. code-block:: text

   isolcpus=
   nohz_full=

把部分 CPU 尽量留给低抖动、实时或专用 workload。

日常内核活动仍必须有 CPU 承担，例如：

* unbound workqueue；
* timer；
* 普通 kthread；
* scheduler domain；
* managed IRQ；
* 可卸载的内核噪声。

housekeeping mask 描述哪些 CPU 可以承担这些工作。

固定命令行为什么通常直接返回
----------------------------

本书固定命令行只有：

.. code-block:: text

   root=/dev/sda1 ro console=ttyS0

没有 ``isolcpus=`` 或 ``nohz_full=``，因此 ``housekeeping.flags`` 通常为零，``housekeeping_init()`` 直接返回。

这种情况下查询 housekeeping CPU mask 时会使用 ``cpu_possible_mask``，后续普通内核工作可以在允许的 CPU 上运行。

当前仍只有 CPU0 online，所以即使 mask 含有其他 possible CPU，实际早期工作仍只能落在 CPU0。

配置了 CPU isolation 时发生什么
------------------------------

若 early 参数已经建立 housekeeping masks，``housekeeping_init()`` 会：

#. 启用 ``housekeeping_overridden`` static key；
#. 必要时建立 tick offload；
#. 确认每种工作至少保留一个 housekeeping CPU；
#. 把 early memblock cpumask 复制到正式 ``kmalloc`` 内存；
#. 释放旧的 memblock backing。

把它放在 workqueue 初始化前，可以让 unbound workqueue 从一开始就遵守 CPU isolation，而不是先绑定到全部 CPU 再返工。

``workqueue_init_early()`` 建立什么
---------------------------------

workqueue 用于把工作封装成 ``work_struct``，稍后由 worker 执行。

它适合：

* 当前路径不应长时间阻塞；
* 工作需要进程上下文，可以睡眠；
* 设备或子系统希望延迟执行；
* 多个事件需要合并或串行处理。

``workqueue_init_early()`` 建立 workqueue 核心对象、worker-pool 描述、属性和系统 workqueue，使后续代码能够：

.. code-block:: text

   create workqueue
   queue work
   cancel work
   flush bookkeeping structures

它也会使用前一步确定的 unbound housekeeping mask。

early workqueue 还不能真正执行 work item
--------------------------------------

源码在这里明确区分两个阶段：

.. code-block:: text

   workqueue_init_early()
       → 可以创建、排队和取消 work

   workqueue_init()
       → 创建/接通 worker kthread，开始真正执行 work

当前 ``kthreadd`` 尚未创建，worker thread 不存在。

所以若某个启动代码此刻 queue work，该 work 可以进入队列，执行必须等待后面的 ``workqueue_init()``。

为什么 RCU 要等 scheduler 基础完成
---------------------------------

接下来：

.. code-block:: c

   rcu_init();

RCU（Read-Copy Update）允许读者以很低开销读取共享数据，更新者发布新版本后，等待所有旧读者离开临界区，再回收旧对象。

抽象过程是：

.. code-block:: text

   reader enters RCU read-side section
   → updater replaces pointer
   → old readers finish
   → grace period completes
   → callback frees old object

RCU 要识别 CPU、任务、抢占、idle、context switch 和后续 tick 中的 quiescent state。

因此 per-CPU area 和 scheduler 基础必须先存在。

``rcu_init()`` 此时准备哪些结构
------------------------------

具体实现取决于构建配置。常见 SMP 内核使用 Tree RCU。

这一阶段会建立或整理：

* per-CPU RCU data；
* RCU node hierarchy；
* grace-period sequence；
* callback list；
* CPU 与 RCU leaf node 的对应；
* scheduler/context-switch 相关接口；
* boot CPU 的初始 RCU 状态。

这使后续内核代码可以使用基本 ``rcu_read_lock()``、``rcu_assign_pointer()`` 和 ``call_rcu()`` 语义。

RCU 尚未拥有完整运行环境
----------------------

此刻仍没有：

* scheduler tick；
* 完整 timekeeping；
* AP online；
* RCU kthread 全部运行；
* softirq 初始化；
* 普通中断。

后面的 ``rcu_init_nohz()``、timer/softirq、SMP bring-up 和 kthread 创建还会继续补齐 RCU 环境。

因此当前应称为“RCU 核心状态已经建立”，不能称为所有 grace-period 推进机制已经完全进入稳定运行期。

``kvfree_rcu_init()`` 为何单独出现
--------------------------------

``kvfree_rcu()`` 允许调用者在 RCU grace period 后释放 ``kmalloc`` 或 ``vmalloc`` 对象。

它需要批处理和延迟回收基础，以避免每个对象都立即创建昂贵的独立回调工作。

``kvfree_rcu_init()`` 初始化相关 per-CPU 队列、批处理状态和回收基础。

当前 workqueue worker 还不能运行，实际延迟回收会随着 RCU、softirq、timer 和 worker 环境逐步投入工作。

``trace_init()`` 与前面的 ``ftrace_init()`` 有什么区别
--------------------------------------------------

第五十六章的 ``ftrace_init()`` 主要建立可动态 patch 的函数 call-site 记录。

当前：

.. code-block:: c

   trace_init();

建立更广泛的 tracing 核心与 trace event 基础，使源码注释所说的状态成立：

.. code-block:: text

   Trace events are available after this

trace event 可以记录：

* scheduler 事件；
* IRQ/softirq；
* timer；
* workqueue；
* block I/O；
* 文件系统；
* 电源和 CPU hotplug。

两层关系是：

.. code-block:: text

   ftrace_init
       → function-entry patch points

   trace_init
       → tracing instances, event infrastructure and buffers

tracefs 的用户接口和各具体事件注册仍会在后续初始化中继续完善。

``initcall_debug`` 为什么现在接入 tracing
---------------------------------------

若命令行设置 ``initcall_debug``，源码在 ``trace_init()`` 后调用：

.. code-block:: c

   initcall_debug_enable();

这样后面的 initcall 执行可以记录开始、结束、耗时和返回值，帮助定位哪个驱动或子系统拖慢或卡住启动。

固定命令行没有该参数，因此主线通常跳过启用动作。

context tracking 记录 CPU 当前处于什么上下文
-------------------------------------------

本章最后调用：

.. code-block:: c

   context_tracking_init();

内核需要区分 CPU 当前处于：

.. code-block:: text

   kernel context
   user context
   guest context
   idle / extended quiescent state

这影响：

* RCU quiescent-state 判断；
* virtual CPU time accounting；
* NO_HZ_FULL；
* tracing；
* 从用户态进入内核、再返回用户态的边界处理。

当前没有用户进程，因此 CPU0 仍处于 kernel context。初始化只是让后续 entry/exit path 有正式状态可以更新。

为什么这里仍不需要硬件 IRQ
-------------------------

radix tree、housekeeping、early workqueue、RCU 初始结构和 tracing 都在 CPU0 的同步启动调用链中建立。

它们依赖 allocator、per-CPU 和 scheduler 基础，不要求硬件中断已经打开。

反过来，接下来的 IRQ、timer、softirq 与 timekeeping 会依赖：

* RCU 基础；
* scheduler；
* workqueue bookkeeping；
* trace event；
* context tracking。

所以这些设施必须先于 ``early_irq_init()``。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 6.12.95 ``init/main.c:start_kernel()``；
* 精确位置：``context_tracking_init()`` 已返回，``early_irq_init()`` 尚未调用；
* CPU：只有 CPU0 online；
* current：``init_task`` / ``swapper/0`` / PID 0；
* scheduler：runqueue 与核心数据结构已建立；
* interrupts：仍关闭；
* IRQ descriptor：尚未执行正式 early 初始化；
* scheduler tick：尚未启动；
* radix tree/XArray：节点 cache 和 CPU-hotplug cleanup 已登记；
* housekeeping：固定主线未设置 isolation，使用默认 CPU mask；
* workqueue：可创建和排队，worker kthread 尚未运行；
* RCU：核心/per-CPU/hierarchy 状态已建立，后续 nohz、softirq 和 kthread 阶段尚待完成；
* trace event：基础设施已可用；
* context tracking：已初始化，当前仍处于 kernel context；
* AP：尚未收到 INIT/SIPI；
* initramfs：尚未解包；
* PID 1：尚未创建。

下一条控制流是：

.. code-block:: c

   early_irq_init();

下一批将进入 IRQ descriptor、x86 中断控制器入口、tick、timer、softirq 和 timekeeping，使 CPU0 第一次具备接受正常异步硬件事件的完整前提。

资料
----

* `Linux 6.12.95 init/main.c：radix tree、housekeeping、workqueue、RCU、trace 与 IRQ 顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c>`_
* `Linux 6.12.95 lib/radix-tree.c：节点 cache、preload 与 CPU hotplug cleanup <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/lib/radix-tree.c>`_
* `Linux 6.12.95 kernel/sched/isolation.c：housekeeping masks 与 CPU isolation <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/isolation.c>`_
* `Linux 6.12.95 kernel/workqueue.c：early 和正式 workqueue 初始化 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/workqueue.c>`_
* `Linux 6.12.95 kernel/rcu/tree.c：Tree RCU 初始化与 CPU hierarchy <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/rcu/tree.c>`_
* `Linux 6.12.95 kernel/trace/trace.c：trace_init 与 event tracing 基础 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/trace/trace.c>`_
* `Linux 6.12.95 kernel/context_tracking.c：kernel/user/guest context tracking <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/context_tracking.c>`_
* `Linux workqueue 文档 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/core-api/workqueue.rst>`_
* `Linux RCU 概念文档 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/RCU/whatisRCU.rst>`_