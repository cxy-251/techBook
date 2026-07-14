第一百一十五章：scheduler 怎样恢复 parent，并让 clock_nanosleep() 返回 0？
================================================================================

第一百一十四章结束时，10 ms hrtimer已经自然到期，``hrtimer_wakeup()`` 已把parent重新enqueue到CPU0 runqueue。``current`` 仍是idle task的interrupt-return路径，parent尚未恢复原来的kernel stack。

本章从CPU0重新进入scheduler开始，结束在parent回到CPL 3，``clock_nanosleep()`` 返回0。

idle 为什么必须重新进入 scheduler
---------------------------------

parent被 ``try_to_wake_up()`` 激活后：

.. code-block:: text

   parent state = TASK_RUNNING
   parent.on_rq = 1
   rq->curr     = idle/0

wakeup逻辑为CPU0建立reschedule条件。hardirq退出后，idle return/loop路径观察到runqueue不再为空，于是进入scheduler。

核心选择路径是：

.. code-block:: text

   schedule_idle / reschedule path
   → __schedule
   → pick_next_task
   → parent

idle task始终保持 ``TASK_RUNNING``，它不是以blocking state离开CPU。scheduler只是因为CPU0 runqueue上出现了优先于idle class的fair task，而选择parent。

context switch 怎样回到原来的 schedule() 调用
---------------------------------------------

``__schedule()`` 更新：

.. code-block:: text

   prev       = idle/0
   next       = parent
   rq->curr   = parent
   parent.on_cpu = 1

随后：

.. code-block:: text

   context_switch
   → switch_mm_irqs_off(idle active_mm, parent->mm)
   → switch_to(idle, parent)
   → finish_task_switch

parent恢复的不是userspace call site，而是它在第一百一十三章调用 ``schedule()`` 时保存的kernel stack context。

因此控制流从：

.. code-block:: text

   schedule()

内部继续返回，回到：

.. code-block:: text

   do_nanosleep()

这正是sleep/wakeup的核心：waker只让task runnable；真正恢复函数调用栈依赖scheduler context switch。

``do_nanosleep`` 怎样区分自然到期与 signal
-----------------------------------------

parent从 ``schedule()`` 返回后，接着执行：

.. code-block:: c

   hrtimer_cancel(&t.timer);

第一百一十四章已经从timerqueue移除timer并完成callback，所以cancel看到timer inactive，不需要等待running callback，也不会重新编程本次deadline。

随后loop检查：

.. code-block:: c

   while (t.task && !signal_pending(current));

固定状态是：

.. code-block:: text

   t.task = NULL
   signal_pending(parent) = false

因此立即退出loop，并执行：

.. code-block:: c

   __set_current_state(TASK_RUNNING);

parent此时本来已经由wakeup路径设为 ``TASK_RUNNING``；这里再次明确恢复正常task state。

为什么返回值是 0
----------------

``do_nanosleep()`` 的完成判断是：

.. code-block:: c

   if (!t.task)
       return 0;

``t.task`` 由 ``hrtimer_wakeup()`` 在自然expiry callback中清空，所以不会进入：

.. code-block:: text

   remaining-time copyout
   restart_block
   -ERESTART_RESTARTBLOCK
   -ERESTARTNOHAND

``hrtimer_nanosleep()`` 收到0后执行：

.. code-block:: text

   destroy_hrtimer_on_stack(&t.timer)
   → return 0

on-stack hrtimer debug state被销毁；parent kernel stack上的 ``struct hrtimer_sleeper`` 随函数返回自然失效，不需要slab free。

syscall 怎样回到原 userspace call site
------------------------------------

返回链是：

.. code-block:: text

   do_nanosleep
   → hrtimer_nanosleep
   → common_nsleep_timens
   → __x64_sys_clock_nanosleep
   → do_syscall_64
   → syscall_exit_to_user_mode

与successful ``execve`` 不同，本次syscall没有改写userspace RIP。x86 syscall exit恢复原程序在 ``SYSCALL`` 后的下一条指令，并把：

.. code-block:: text

   RAX = 0

返回给userspace。

``rmtp`` 是NULL，且没有signal interruption，因此没有remaining time需要写回。

实际睡眠时间等于 10 ms 吗
-------------------------

kernel建立的保证是：timer callback不会早于absolute expiry ``E``。实际恢复userspace还需要：

.. code-block:: text

   APIC interrupt latency
   + hrtimer callback execution
   + scheduler selection
   + context switch
   + syscall exit

固定场景排除了额外runnable tasks和虚拟化停顿，所以parent在第一个可运行机会恢复；仍应把语义写成：

.. code-block:: text

   monotonic elapsed >= 10 ms

不能把POSIX sleep解释成精确占用10,000,000 ns后在同一纳秒返回。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* parent scheduling class：``SCHED_NORMAL``；
* parent state：``TASK_RUNNING``；
* parent ``on_rq``：1，作为CPU0 current task运行；
* parent ``on_cpu``：1；
* syscall result/RAX：0；
* userspace RIP：原 ``clock_nanosleep`` 调用后的下一条指令；
* monotonic requested interval：10 ms；
* monotonic elapsed：不早于10 ms；
* hrtimer object：已destroy on stack；
* hrtimer queue：无本次timer；
* local APIC deadline：本次event已消费；
* signal/restart：未发生；
* remaining-time copyout：未发生；
* next runtime scenario：unselected。

关键边界
--------

#. wakeup恢复的是task的runnable状态，不是直接恢复函数调用栈。
#. parent从原 ``schedule()`` 调用点继续执行。
#. ``t.task=NULL`` 是自然expiry的完成条件。
#. inactive timer上的 ``hrtimer_cancel()`` 只完成清理确认。
#. on-stack hrtimer不需要slab释放。
#. relative nanosleep保证不早于期限，不保证精确在期限瞬间返回。
#. 无signal时不会进入restart block或remaining-time copyout。

资料
----

* `Linux 7.2-rc1 kernel/time/hrtimer.c：do_nanosleep完成判断、cancel与hrtimer_nanosleep返回 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/hrtimer.c>`_
* `Linux 7.2-rc1 kernel/sched/core.c：__schedule、pick_next_task与context switch <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/core.c>`_
* `Linux 7.2-rc1 kernel/time/posix-timers.c：clock_nanosleep syscall返回路径 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/posix-timers.c>`_
