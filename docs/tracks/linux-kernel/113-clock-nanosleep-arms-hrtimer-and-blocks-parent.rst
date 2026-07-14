第一百一十三章：clock_nanosleep() 怎样建立 hrtimer 并让 parent 阻塞？
================================================================================

上一场景已经结束：``/work/demo.txt`` 的 pathname、open file 与 inode 均不再可访问。现在开始一个独立的运行期实验，parent 调用：

.. code-block:: c

   struct timespec req = {
       .tv_sec = 0,
       .tv_nsec = 10 * 1000 * 1000,
   };

   clock_nanosleep(CLOCK_MONOTONIC, 0, &req, NULL);

固定条件：

* 系统只有 CPU0 online；
* parent 是普通 ``SCHED_NORMAL`` task，当前运行在 CPU0；
* parent 的 ``timer_slack_ns`` 固定为 0；
* high-resolution timers 已启用，CPU0 的 hrtimer base 处于 hres active；
* CPU0 使用 local APIC TSC-deadline clockevent；
* parent 之外没有其他 runnable user task，CPU0 的下一执行者只能是 idle task；
* 请求期间没有 signal、freezer、CPU hotplug、timer migration 或 spurious wakeup；
* userspace timespec 可读且合法；
* local APIC interrupt 在第一个不早于 expiry 的时刻送达。

本章从 native x86-64 syscall 入口开始，结束在 parent 已从 runqueue 移除、CPU0 切换到 idle task，而 10 ms hrtimer 仍在等待到期。

syscall 入口怎样选择 CLOCK_MONOTONIC 的实现
-------------------------------------------

native x86-64 ``clock_nanosleep`` 的 syscall number 是 230。用户态执行 ``SYSCALL`` 时：

.. code-block:: text

   RAX = 230
   RDI = CLOCK_MONOTONIC
   RSI = 0
   RDX = &req
   R10 = NULL

控制流进入：

.. code-block:: text

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_clock_nanosleep

``SYSCALL_DEFINE4(clock_nanosleep)`` 先执行：

.. code-block:: text

   clockid_to_kclock(CLOCK_MONOTONIC)
   → clock_monotonic
   → get_timespec64(&t, req)
   → timespec64_valid(&t)

固定 ``t`` 是：

.. code-block:: text

   tv_sec  = 0
   tv_nsec = 10,000,000

``flags`` 没有 ``TIMER_ABSTIME``，因此这是 relative sleep。``rmtp`` 为 ``NULL``，restart block记录 ``TT_NONE``；固定场景没有 signal，所以后续不会进入restart路径。

CLOCK_MONOTONIC 怎样进入 hrtimer_nanosleep
-----------------------------------------

``clock_monotonic.nsleep`` 指向：

.. code-block:: c

   common_nsleep_timens

relative timer不需要time namespace的absolute-time换算。调用链是：

.. code-block:: text

   common_nsleep_timens
   → timespec64_to_ktime
   → hrtimer_nanosleep(10 ms,
                       HRTIMER_MODE_REL,
                       CLOCK_MONOTONIC)

``hrtimer_nanosleep()`` 在当前kernel stack上创建：

.. code-block:: c

   struct hrtimer_sleeper t;

随后：

.. code-block:: text

   hrtimer_setup_sleeper_on_stack
   → __hrtimer_setup_sleeper
   → __hrtimer_setup

关键字段变成：

.. code-block:: text

   t.task             = current parent
   t.timer.function   = hrtimer_wakeup
   t.timer.base       = CPU0 monotonic hrtimer clock base
   timer mode         = relative, hard hrtimer on non-RT kernel

这是一个位于parent syscall kernel stack上的临时timer object。它不会创建kernel thread，也不是普通timer wheel中的 ``struct timer_list``。

expiry 怎样从 relative 10 ms 变成 absolute time
-----------------------------------------------

``hrtimer_set_expires_range_ns()`` 先保存requested interval。由于固定：

.. code-block:: text

   current->timer_slack_ns = 0

soft expiry与hard expiry相同，不允许kernel为了合并wakeups而向后移动期限。

``do_nanosleep()`` 首先执行：

.. code-block:: c

   set_current_state(TASK_INTERRUPTIBLE | TASK_FREEZABLE);
   hrtimer_sleeper_start_expires(&t, HRTIMER_MODE_REL);

start路径最终进入：

.. code-block:: text

   hrtimer_start_expires_user
   → hrtimer_start_range_ns
   → __hrtimer_start_range_ns

relative expiry在CPU0 monotonic base上换算为：

.. code-block:: text

   absolute expiry E = ktime_get() + 10 ms

固定CPU只有CPU0，timer不迁移。``enqueue_hrtimer()`` 把timer按expiry顺序插入CPU0 monotonic base的timerqueue linked red-black tree，并设置：

.. code-block:: text

   timer.is_queued              = HRTIMER_STATE_ENQUEUED
   cpu_base.active_bases       |= monotonic-base bit
   base.expires_next            = E
   cpu_base.next_timer          = &t.timer

为什么 local APIC 会被重新编程
-----------------------------

固定timer是CPU0当前最早到期的timer，因此enqueue结果要求更新clockevent deadline。high-resolution路径最终把next event交给CPU0的clockevent device。

固定clockevent是：

.. code-block:: text

   name           = lapic-deadline
   feature        = CLOCK_EVT_FEAT_ONESHOT
   set_next_event = lapic_next_deadline

``lapic_next_deadline()`` 读取当前TSC，并写：

.. code-block:: c

   MSR_IA32_TSC_DEADLINE = current_tsc + converted_delta;

local APIC现在承担一次性硬件唤醒：当TSC到达deadline时，向CPU0投递 ``LOCAL_TIMER_VECTOR``。

parent 怎样真正离开 runqueue
----------------------------

``do_nanosleep()`` 检查 ``t.task`` 仍指向parent，说明timer尚未在start过程中到期，于是调用：

.. code-block:: c

   schedule();

当前parent state不是 ``TASK_RUNNING``。scheduler路径是：

.. code-block:: text

   schedule
   → __schedule_loop(SM_NONE)
   → __schedule
   → try_to_block_task
   → block_task
   → pick_next_task

没有pending signal，``try_to_block_task()`` 保留 ``TASK_INTERRUPTIBLE | TASK_FREEZABLE``，并把parent从CPU0 runqueue中dequeue：

.. code-block:: text

   parent.on_rq   = 0
   parent state   = TASK_INTERRUPTIBLE | TASK_FREEZABLE
   parent.on_cpu  = 1 until context switch completes

CPU0没有其他runnable普通task，``pick_next_task()`` 选择per-CPU idle task。``context_switch()`` 完成：

.. code-block:: text

   prev = parent
   next = idle/0
   rq->curr = idle/0
   parent.on_cpu = 0 after switch completion

parent的kernel stack、``struct hrtimer_sleeper t`` 和未完成的syscall调用链都保留下来；只是暂时不再占用CPU。

当前精确状态
------------

* current executor：CPU0 idle task；
* CPU mode：x86-64 CPL 0，idle loop；
* parent：sleeping，``on_rq=0``、``on_cpu=0``；
* parent state：``TASK_INTERRUPTIBLE | TASK_FREEZABLE``；
* parent syscall stack：停在 ``schedule()`` 内；
* hrtimer object：位于parent kernel stack；
* hrtimer callback：``hrtimer_wakeup``；
* hrtimer task pointer：仍指向parent；
* timer base：CPU0 monotonic hard hrtimer base；
* absolute expiry：``E = arm_time + 10 ms``；
* timerqueue state：queued且为next timer；
* CPU0 clockevent：local APIC TSC-deadline one-shot；
* signal/restart：没有发生；
* ``clock_nanosleep``：尚未返回；
* next hardware event：``LOCAL_TIMER_VECTOR``。

关键边界
--------

#. ``clock_nanosleep`` 使用hrtimer，不使用jiffies timer wheel。
#. relative 10 ms在enqueue时转换成monotonic absolute expiry。
#. timer slack为0时soft expiry与hard expiry相同。
#. hrtimer object位于sleeping task自己的kernel stack。
#. 设置 ``TASK_INTERRUPTIBLE`` 不等于已经睡眠；真正离开CPU发生在 ``schedule()``。
#. timer callback尚未执行，parent也尚未被wakeup。

资料
----

* `Linux 7.2-rc1 kernel/time/posix-timers.c：clock_nanosleep 与 CLOCK_MONOTONIC nsleep选择 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/posix-timers.c>`_
* `Linux 7.2-rc1 kernel/time/hrtimer.c：hrtimer_nanosleep、do_nanosleep与timer enqueue <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/hrtimer.c>`_
* `Linux 7.2-rc1 kernel/sched/core.c：schedule、__schedule与blocking dequeue <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/core.c>`_
* `Linux 7.2-rc1 arch/x86/kernel/apic/apic.c：lapic-deadline clockevent编程 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/apic/apic.c>`_
