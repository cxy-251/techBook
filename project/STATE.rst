项目状态
========

最后更新
--------

2026-07-13

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成 ``LK-BOOT-001`` 至 ``LK-BOOT-058``。最新三章：

#. ``LK-BOOT-056``：Linux 怎样准备 Maple Tree、文本热补丁和 ftrace？
#. ``LK-BOOT-057``：Linux 怎样建立 runqueue，并把 init_task 变成 CPU0 的 idle task？
#. ``LK-BOOT-058``：Linux 怎样建立 early workqueue、RCU 和 trace event 基础？

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

第五十六至五十八章已经完成：

::

   maple_tree_init()
   → create Maple Tree node slab cache
   → poking_init()
   → prepare controlled x86 runtime text patching
   → ftrace_init()
   → build dynamic function call-site records
   → early_trace_init()
   → sched_init()
   → initialize per-possible-CPU runqueues and scheduling classes
   → bind init_task as CPU0 idle/current task
   → select dynamic preemption model
   → verify IRQs remain disabled
   → radix_tree_init()
   → create radix-tree/XArray node cache and CPU-hotplug cleanup
   → housekeeping_init()
   → workqueue_init_early()
   → allow workqueue creation and queueing without worker execution
   → rcu_init()
   → build RCU core/per-CPU/hierarchy state
   → kvfree_rcu_init()
   → trace_init()
   → make trace-event infrastructure available
   → context_tracking_init()

此刻机器状态：

* 当前执行者：Linux 6.12.95 ``init/main.c:start_kernel()``；
* 精确位置：``context_tracking_init()`` 已返回，``early_irq_init()`` 尚未调用；
* CPU：只有 BSP / Linux CPU0 online；
* mode：64 位 long mode；
* current task：``init_task`` / ``swapper/0`` / PID 0；
* CPU0 runqueue：已建立，``rq->curr`` 与 ``rq->idle`` 指向 boot idle task；
* possible CPU runqueue：均已初始化；
* scheduler：核心数据结构和 scheduling class 已可用；
* scheduler tick：尚未启动；
* interrupts：关闭，``early_boot_irqs_disabled = true``；
* IRQ descriptors：尚未执行 ``early_irq_init()``；
* AP：尚未收到 INIT/SIPI；
* buddy/slab/vmalloc：可用；
* Maple Tree/radix tree：节点 cache 已建立；
* text poking/ftrace：运行期补丁和函数 call-site 基础已建立；
* housekeeping：固定命令行未设置 CPU isolation；
* workqueue：可创建、排队和取消 work，worker kthread 尚未运行；
* RCU：核心/per-CPU/hierarchy 状态已建立，nohz、softirq 和 kthread 环境仍待补齐；
* trace event：基础设施已可用；
* context tracking：已初始化，CPU0 当前处于 kernel context；
* 正式 console：尚未初始化；
* initramfs：尚未解包；
* PID 1 / PID 2：尚未创建。

完成状态
--------

``complete`` 表示章节到达自然终点，关键技术事实已依据固定源码或规范核对。读者不承担技术审稿。

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。

当前下一步
----------

从 ``start_kernel():early_irq_init()`` 开始，追踪通用 IRQ descriptor 分配、x86 ``init_IRQ()`` 与 IDT/interrupt-gate 接管，随后继续 ``tick_init()``、timer wheel、hrtimer、softirq、timekeeping 和架构时钟初始化。保持三个状态边界清晰：IRQ 数据结构已建立、硬件中断入口已安装、``local_irq_enable()`` 真正打开 IF 位发生在不同位置。