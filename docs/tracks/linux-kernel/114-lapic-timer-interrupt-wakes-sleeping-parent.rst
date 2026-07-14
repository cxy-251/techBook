第一百一十四章：local APIC timer interrupt 怎样运行 hrtimer callback 并唤醒 parent？
========================================================================================

第一百一十三章结束时，CPU0正在执行idle task；parent已经从runqueue移除，停在 ``schedule()`` 内；CPU0 monotonic hrtimer base中只有一个最早到期timer，其expiry为 ``E``，callback是 ``hrtimer_wakeup``。

本章从TSC达到deadline开始，结束在parent已经重新进入CPU0 runqueue并被标记为runnable，但尚未恢复 ``do_nanosleep()`` 的kernel stack。

TSC deadline 怎样变成 x86 interrupt
-----------------------------------

固定CPU0使用local APIC TSC-deadline mode。硬件比较当前TSC与：

.. code-block:: text

   MSR_IA32_TSC_DEADLINE

在第一个不早于 ``E`` 的时刻，local APIC向CPU0投递 ``LOCAL_TIMER_VECTOR``。CPU当时运行idle task，进入interrupt gate后：

.. code-block:: text

   current = idle/0
   CPU mode = CPL 0 hardirq context
   interrupts = disabled by interrupt entry

x86入口保存idle execution context并进入：

.. code-block:: text

   sysvec_apic_timer_interrupt

handler先执行：

.. code-block:: text

   set_irq_regs
   → apic_eoi
   → trace_local_timer_entry
   → local_apic_timer_interrupt

``apic_eoi()`` 向local APIC确认当前vector已被CPU接受。它不代表hrtimer已经执行完成。

clockevent 怎样进入 hrtimer_interrupt
------------------------------------

``local_apic_timer_interrupt()`` 取得CPU0的per-CPU clockevent：

.. code-block:: c

   struct clock_event_device *evt = this_cpu_ptr(&lapic_events);

固定device已经由high-resolution timer framework设置：

.. code-block:: text

   evt->event_handler = hrtimer_interrupt

因此调用链继续：

.. code-block:: text

   local_apic_timer_interrupt
   → evt->event_handler(evt)
   → hrtimer_interrupt(evt)

``hrtimer_interrupt()`` 在interrupts disabled状态下操作CPU0自己的 ``struct hrtimer_cpu_base``。它首先：

.. code-block:: text

   cpu_base.nr_events++
   dev->next_event = KTIME_MAX
   raw_spin_lock(cpu_base->lock)
   now = hrtimer_update_base(cpu_base)

固定 ``now >= E``，因此monotonic base最左侧timer已经到期。

到期timer怎样从queue切换到callback状态
-------------------------------------

``__hrtimer_run_queues()`` 遍历active hard bases，找到parent sleeper timer。``__run_hrtimer()`` 在 ``cpu_base->lock`` 保护下完成：

.. code-block:: text

   base->running = &t.timer
   → remove timer from timerqueue
   → timer.is_queued = inactive
   → update active_bases / base next expiry

随后临时释放 ``cpu_base->lock``，调用：

.. code-block:: c

   hrtimer_wakeup(&t.timer);

timer从queue中消失不等于parent已经运行；callback下一步只负责把sleeping task重新变成runnable。

``hrtimer_wakeup`` 为什么先清空 task pointer
------------------------------------------

callback从 ``struct hrtimer`` 找回：

.. code-block:: c

   struct hrtimer_sleeper *t;
   struct task_struct *task = t->task;

然后严格按顺序执行：

.. code-block:: c

   t->task = NULL;
   if (task)
       wake_up_process(task);

``t->task = NULL`` 是sleep completion标志。之后parent从 ``schedule()`` 返回时，``do_nanosleep()`` 看到NULL，就知道timer自然到期，而不是signal或spurious wakeup。

``wake_up_process`` 怎样让 parent 再次 runnable
---------------------------------------------

``wake_up_process(parent)`` 进入：

.. code-block:: text

   try_to_wake_up(parent, TASK_NORMAL, 0)

parent当前：

.. code-block:: text

   state  = TASK_INTERRUPTIBLE | TASK_FREEZABLE
   on_rq  = 0
   on_cpu = 0
   cpu    = CPU0

``try_to_wake_up()`` 取得 ``parent->pi_lock``，确认state与 ``TASK_NORMAL`` 匹配，然后执行wakeup状态转换：

.. code-block:: text

   parent state → TASK_WAKING
   → select_task_rq(parent)
   → CPU0
   → ttwu_queue
   → rq_lock(CPU0)
   → ttwu_do_activate
   → enqueue parent into CPU0 runqueue
   → parent state → TASK_RUNNING

固定只有CPU0，不发生task migration或remote wake-list。parent重新成为CPU0 runqueue上的fair task。

为什么唤醒不等于立刻继续 syscall
--------------------------------

callback仍在idle task被interrupt打断后的hardirq context中。此刻：

.. code-block:: text

   current        = idle/0
   parent.on_rq   = 1
   parent state   = TASK_RUNNING
   parent.on_cpu  = 0

scheduler wakeup逻辑发现idle正在占用CPU，设置reschedule条件。parent尚未恢复kernel stack，也尚未执行 ``hrtimer_cancel()``。

callback返回：

.. code-block:: text

   hrtimer_wakeup
   → HRTIMER_NORESTART

``__run_hrtimer()`` 重新取得 ``cpu_base->lock``，清除：

.. code-block:: text

   base->running = NULL

timer不会重新enqueue。

hrtimer interrupt 怎样结束本次硬件事件
--------------------------------------

``hrtimer_interrupt()`` 重新读取monotonic time，计算下一个timer expiry。固定场景没有其他pending hrtimer，因此next expiry是 ``KTIME_MAX``；clockevent被重新arm或停止，不再保留本次10 ms deadline。

随后：

.. code-block:: text

   raw_spin_unlock(cpu_base->lock)
   → local_apic_timer_interrupt returns
   → trace_local_timer_exit
   → restore irq_regs pointer

interrupt exit离开hardirq状态。CPU0已经存在可运行的parent，idle task不能继续长期占用CPU；reschedule路径将在离开interrupt或idle loop的最近调度点进入scheduler。

当前精确状态
------------

* current executor：仍是CPU0 idle task的interrupt-return路径；
* CPU mode：x86-64 CPL 0，正在退出hardirq；
* local APIC EOI：已完成；
* parent state：``TASK_RUNNING``；
* parent ``on_rq``：1，位于CPU0 runqueue；
* parent ``on_cpu``：0；
* parent kernel stack：仍停在第一百一十三章的 ``schedule()``；
* sleeper ``t.task``：NULL；
* hrtimer queue state：inactive，不再queued；
* hrtimer callback：已返回 ``HRTIMER_NORESTART``；
* ``base->running``：NULL；
* 10 ms clockevent：已消费；
* pending signal：无；
* scheduler reschedule：需要选择parent替换idle；
* ``clock_nanosleep``：尚未返回用户态。

关键边界
--------

#. local APIC产生硬件interrupt，hrtimer framework决定具体callback。
#. APIC EOI发生在timer callback之前。
#. hrtimer先从timerqueue移除，再运行callback。
#. ``t.task=NULL`` 表示timer自然到期。
#. ``wake_up_process`` 只把parent放回runqueue，不直接跳到parent的kernel stack。
#. callback运行时 ``current`` 仍是被interrupt打断的idle task。
#. fixed single-CPU场景没有remote wake-list或task migration。

资料
----

* `Linux 7.2-rc1 arch/x86/kernel/apic/apic.c：sysvec_apic_timer_interrupt与local_apic_timer_interrupt <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/apic/apic.c>`_
* `Linux 7.2-rc1 kernel/time/hrtimer.c：hrtimer_interrupt、__run_hrtimer与hrtimer_wakeup <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/hrtimer.c>`_
* `Linux 7.2-rc1 kernel/sched/core.c：wake_up_process与try_to_wake_up <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/core.c>`_
