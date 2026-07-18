第五十七章：Linux 怎样建立 runqueue 并把 init_task 登记为 CPU0 idle？
=======================================================================

第五十六章结束时，runtime MM与early tracing可用，CPU0仍沿 ``start_kernel`` 执行、IF=0；所有possible
CPU有per-CPU storage，但scheduler尚未初始化。当前入口是：

.. code-block:: c

   sched_init();

本章追踪该函数及return后的very-early IRQ sanity repair，停在 ``radix_tree_init`` call前。它为每个
possible CPU初始化runqueue/class state，把当前静态 ``init_task`` 变成CPU0的PID 0 idle task并发布
``scheduler_running=1``；没有调用 ``schedule``，PID 1/PID 2仍不存在。

linker scheduling-class次序是启动硬门
-----------------------------------

``sched_init`` 先以 ``BUG_ON`` 验证stop > deadline > RT > fair > idle的linker order；
``CONFIG_SCHED_CLASS_EXT`` 还验证fair > ext > idle。错误会终止而不能用runtime排序补救。随后
``wait_bit_init`` 初始化global hashed waitqueue table；这只准备bit-wait primitive，没有waiter或睡眠。

root groups/domain先于每CPU runqueue
--------------------------------

按group scheduling configs，函数为 ``root_task_group`` 建CFS bandwidth、可选sched-ext group与RT
entity/runqueue pointer arrays； ``init_defrootdomain`` 初始化默认root domain并置refcount 1。RT bandwidth
随后按global period/runtime建立。

``CONFIG_CGROUP_SCHED`` 时创建 ``task_group`` SLUB cache，把root group加入global list并
``autogroup_init(&init_task)``。这不是挂载cgroupfs，也没有child cgroup；只是让所有初始tasks有合法
scheduler root ownership。

每个possible CPU获得独立但尚未投入运行的rq
-------------------------------------------

``for_each_possible_cpu`` 取得052 first chunk中的 ``cpu_rq(i)``，依次初始化raw lock、running/load
counts、CFS/RT/DL queues、可选group entries，并把 ``next_class`` 置idle。它清scheduler-domain/root-
domain pointers、设置capacity/default balance fields、CPU ID与 ``rq->online=0``，再将rq attach到
``def_root_domain``。

NO_HZ、CPU-hotplug、hrtick、I/O wait、fair server、sched-ext/core/cache fields都按build初始化；最后按
CPU node分配scratch cpumask。这个loop准备的是future executor containers：CPU1 rq存在不表示CPU1
online，也不表示rq已有normal runnable tasks。

``init_task`` 先取得load、lazy-TLB与kthread外形
-------------------------------------------

loop后为 ``init_task`` 设置load weight与fair slice。 ``mmgrab_lazy_tlb(&init_mm)`` 增加lazy-TLB reference，
``enter_lazy_tlb`` 让当前kernel thread使用 ``init_mm`` active context；它没有user ``mm_struct``。

``set_kthread_struct(current)`` 为当前task补kthread metadata，failure只WARN。随后 ``__sched_fork(0,
current)`` 以fork-like helper重置scheduler entity state；这没有复制task、分配PID或创建child。

``init_idle`` 在两把raw lock下把CPU0与current绑定
---------------------------------------------

当前 ``smp_processor_id`` 是0， ``init_idle(current,0)`` 在task ``pi_lock`` 与CPU0 rq lock下把state置
``TASK_RUNNING``、记录exec start，确保 ``PF_KTHREAD|PF_NO_SETAFFINITY`` 并标成per-CPU kthread；allowed
mask收为CPU0并写task CPU。

随后发布：

.. code-block:: text

   rq0.idle = init_task
   rq0.curr = init_task
   init_task.on_rq = TASK_ON_RQ_QUEUED
   init_task.on_cpu = 1

unlock后再设置idle preempt count、 ``idle_sched_class``、ftrace-graph/vtime idle state，并把comm写成
``swapper/0``。此时同一个task既继续运行 ``start_kernel``，又已成为CPU0没有其他runnable task时的
idle/current identity；它尚未进入 ``cpu_startup_entry`` idle loop。

boot idle pointer与剩余scheduler policies最后发布
-----------------------------------------------

``idle_thread_set_boot_cpu`` 在generic SMP-idle-thread build把per-CPU ``idle_threads[0]`` 指向current；
UP/stub path no-op。随后关闭CPU0 balance-push mode，初始化fair与sched-ext class global state、PSI、
utilization clamping与dynamic preemption policy。

``preempt_dynamic_init`` 可按build/default/054 parsed ``preempt=`` 用static calls/keys选择none/voluntary/
full/lazy可用模式；具体mode未固定。最后 ``scheduler_running=1`` 表示core APIs与data structures ready，
不表示timer tick、SMP domains或第一次context switch已经发生。

return后的IRQ check属于本章出口
-----------------------------

``start_kernel`` 紧接着 ``WARN(!irqs_disabled(),...)``；若任何early init错误地打开IF，就warning并
``local_irq_disable``。因此无论054 unknown handler/056 tracer是否破坏预期，本章真实出口都重新固定
IF=0。该repair本身不dispatch pending device IRQ； ``init_IRQ`` 仍在later章节。

本章结束状态
------------

* current executor：CPU0上的 ``start_kernel``，current为 ``init_task/swapper/0``（PID 0）；
* precise next： ``radix_tree_init()`` 尚未调用；
* CPU/mode：CPU0，x86-64 CPL0，post-sched sanity后IF确定为0；
* scheduling classes/root group/default root domain：按build初始化；
* possible CPU runqueues：locks、CFS/RT/DL与conditional fields已建并attach root domain；
* CPU0 rq/current/idle：均已绑定； ``init_task`` on-CPU且idle class；
* other CPU rq：containers存在，CPU仍未运行，idle tasks尚未在此创建；
* ``init_mm``：current持lazy-TLB reference；没有user mm；
* ``scheduler_running``：1；full SMP scheduling topology与tick尚未建立；
* task switch：一次也未由本章执行；PID 1、kthreadd/PID 2均不存在；
* IRQ/AP/initramfs：未启用、未启动、未解包。

关键边界
--------

#. possible CPU有rq不等于online；loop还显式把 ``rq->online`` 初始化为0。
#. class queues ready不等于已有ordinary runnable tasks。
#. root task group/domain与later cgroupfs/SMP scheduling domains不同。
#. ``__sched_fork`` 在current上重置scheduler state，不创建进程。
#. ``init_task`` 是PID 0 boot idle，不是future PID 1 ``kernel_init``。
#. ``init_idle`` 发布rq curr/idle但不进入idle loop，也不调用 ``schedule``。
#. dynamic preemption ready不表示timer IRQ或preemptive switch已发生。
#. ``scheduler_running=1`` 是core-ready flag，不代表full topology/tick/AP ready。
#. post-return sanity repair使下一章入口IF确定为0。

下一入口
--------

第058章从：

.. code-block:: c

   radix_tree_init();

开始，随后是housekeeping、early workqueue、RCU/kvfree-RCU与full trace-event基础。

资料
----

* `Linux 7.2-rc1固定提交：sched_init与post-return IRQ repair顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L1042-L1052>`_；
* `Linux 7.2-rc1固定提交：sched_init class/group/rq与boot idle完整顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/core.c#L8915-L9108>`_；
* `Linux 7.2-rc1固定提交：init_idle locks与rq/task publication <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/core.c#L8243-L8309>`_；
* `Linux 7.2-rc1固定提交：default root domain <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/topology.c#L577-L588>`_；
* `Linux 7.2-rc1固定提交：boot CPU idle-thread pointer <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/smpboot.c#L21-L40>`_。
