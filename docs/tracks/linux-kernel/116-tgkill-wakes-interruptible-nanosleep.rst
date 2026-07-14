第一百一十六章：tgkill() 怎样排入 SIGUSR1 并唤醒 nanosleep 中的 parent？
================================================================================

上一场景的10 ms monotonic sleep已经自然到期并返回。现在开始一个独立实验，parent再次调用：

.. code-block:: c

   struct timespec req = {
       .tv_sec = 0,
       .tv_nsec = 10 * 1000 * 1000,
   };
   struct timespec remaining;

   clock_nanosleep(CLOCK_MONOTONIC, 0, &req, &remaining);

本次sleep不会自然结束。固定条件如下：

* 系统只有CPU0 online；
* parent是单线程 ``SCHED_NORMAL`` task，TGID与TID均为 ``P``；
* helper是另一个同UID进程，PID为 ``H``；
* parent已经为 ``SIGUSR1`` 安装 ``SA_SIGINFO | SA_RESTORER`` handler；
* handler没有 ``SA_RESTART``、``SA_NODEFER`` 或 ``SA_ONSTACK``；
* ``SIGUSR1`` 未屏蔽，也没有其他pending signal；
* parent的 ``timer_slack_ns`` 为0；
* hrtimer high-resolution模式已启用，CPU0使用local APIC TSC-deadline clockevent；
* parent在monotonic时间 ``T0`` arm timer，hard expiry为 ``E = T0 + 10 ms``；
* parent阻塞后，helper成为CPU0唯一runnable user task；
* helper在 ``Ts = T0 + 4 ms`` 执行 ``tgkill(P, P, SIGUSR1)``，随后立即阻塞；
* parent会在 ``E`` 之前恢复执行；
* ``remaining`` 指针有效且可写；
* 没有ptrace、seccomp、freezer、CPU migration、其他signal或失败路径。

本章从parent已经阻塞、helper正在CPU0运行开始，结束在parent被放回CPU0 runqueue，而原sleep hrtimer仍然queued、尚未取消。

开始时有哪些对象仍然存在
------------------------

parent先前已经沿以下路径进入睡眠：

.. code-block:: text

   clock_nanosleep
   → common_nsleep_timens
   → hrtimer_nanosleep
   → do_nanosleep
   → set_current_state(TASK_INTERRUPTIBLE | TASK_FREEZABLE)
   → enqueue hrtimer
   → schedule
   → context_switch(parent, helper)

此刻CPU0的执行者是helper，parent的状态是：

.. code-block:: text

   parent.__state = TASK_INTERRUPTIBLE | TASK_FREEZABLE
   parent.on_rq   = 0
   parent.on_cpu  = 0

parent的kernel stack仍保留未完成的 ``do_nanosleep()`` 调用链，以及位于该stack上的：

.. code-block:: c

   struct hrtimer_sleeper t;

关键timer状态为：

.. code-block:: text

   t.task           = parent
   t.timer.function = hrtimer_wakeup
   t.timer.base     = CPU0 monotonic hard hrtimer base
   t.timer expiry   = E
   t.timer queued   = true

``t.task`` 尚未被callback清空，因为 ``E`` 尚未到达。

helper 怎样进入 tgkill syscall
-----------------------------

在 ``Ts = T0 + 4 ms``，helper执行：

.. code-block:: c

   tgkill(P, P, SIGUSR1);

native x86-64 ABI寄存器是：

.. code-block:: text

   RAX = __NR_tgkill
   RDI = P              # target TGID
   RSI = P              # target TID
   RDX = SIGUSR1

控制流进入：

.. code-block:: text

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_tgkill
   → do_tkill
   → do_send_specific

``tgkill`` 同时检查TGID和TID。``find_task_by_vpid(P)`` 找到parent后，还必须满足：

.. code-block:: text

   task_tgid_vnr(parent) == P

这避免target TID已经退出并被其他进程复用时，把signal错误地发给新task。

SIGUSR1 的 siginfo 怎样形成
---------------------------

``do_tkill()`` 调用 ``prepare_kill_siginfo()``，固定生成：

.. code-block:: text

   si_signo = SIGUSR1
   si_errno = 0
   si_code  = SI_TKILL
   si_pid   = H
   si_uid   = helper UID

由于helper与parent具有允许发送signal的凭据，``check_kill_permission()`` 返回0。控制继续进入：

.. code-block:: text

   do_send_sig_info
   → send_signal_locked
   → __send_signal_locked

这是thread-directed signal，因此 ``PIDTYPE_PID`` 选择parent自己的pending queue，而不是thread group共享queue：

.. code-block:: text

   pending = &parent->pending

``SIGUSR1`` 是传统非实时signal。固定它此前不在pending set中，所以本次可以记录完整 ``sigqueue`` 信息，不会发生legacy signal合并。

pending signal 怎样发布
-----------------------

持有parent ``sighand->siglock`` 时，``__send_signal_locked()`` 完成：

.. code-block:: text

   add sigqueue carrying SI_TKILL info
   → sigaddset(&parent->pending.signal, SIGUSR1)
   → complete_signal(SIGUSR1, parent, PIDTYPE_PID)

parent没有屏蔽 ``SIGUSR1``，也没有退出、停止或被ptrace控制，因此 ``wants_signal()`` 对parent返回true。

``complete_signal()`` 最终调用：

.. code-block:: text

   signal_wake_up(parent, false)
   → signal_wake_up_state(parent, 0)

``signal_wake_up_state()`` 先设置thread flag：

.. code-block:: text

   parent.TIF_SIGPENDING = 1

随后执行：

.. code-block:: c

   wake_up_state(parent, TASK_INTERRUPTIBLE);

这里的 ``TASK_INTERRUPTIBLE`` 正好匹配parent在 ``do_nanosleep()`` 中设置的state。

try_to_wake_up 怎样让 parent 重新 runnable
------------------------------------------

``wake_up_state()`` 进入scheduler的：

.. code-block:: text

   try_to_wake_up
   → ttwu_state_match
   → select_task_rq
   → ttwu_queue
   → ttwu_do_activate

固定系统只有CPU0，因此没有CPU选择和migration。scheduler把parent重新加入CPU0 runqueue：

.. code-block:: text

   parent.__state = TASK_RUNNING
   parent.on_rq   = 1
   parent.on_cpu  = 0
   parent CPU     = CPU0

wakeup保证signal发布发生在parent观察task state之前，相关 ``pi_lock``、runqueue lock与memory barrier防止“signal已经pending，但sleeping task永久错过wakeup”的竞态。

wakeup 为什么没有立刻运行 signal handler
----------------------------------------

``signal_wake_up_state()`` 只完成两件核心事情：

#. 设置 ``TIF_SIGPENDING``；
#. 把parent从sleeping变为runnable。

当前CPU仍在helper的 ``tgkill`` syscall中。signal handler不会在helper上下文运行，也不会由 ``try_to_wake_up()`` 直接调用。

固定helper的 ``tgkill`` 返回0后立即进入阻塞，因此scheduler将选择刚被唤醒的parent。parent将从自己原先的kernel stack继续执行，先完成 ``do_nanosleep()`` 的收尾，之后才会在返回用户态前处理pending signal。

为什么 hrtimer 此时仍然 queued
-----------------------------

本次wakeup来自signal，不是timer expiry。当前monotonic时间约为 ``T0 + 4 ms``，仍早于：

.. code-block:: text

   E = T0 + 10 ms

因此没有发生：

.. code-block:: text

   LOCAL_TIMER_VECTOR
   → hrtimer_interrupt
   → hrtimer_wakeup callback

关键结果是：

.. code-block:: text

   t.task             = parent
   t.timer.is_queued  = true
   timer expiry       = E
   remaining interval > 0

signal wakeup不会自动操作hrtimer tree。timer取消必须由恢复执行的parent调用 ``hrtimer_cancel()`` 完成。

当前精确状态
------------

* current executor：helper，准备阻塞并让出CPU0；
* CPU mode：x86-64 CPL 0，位于helper syscall/schedule路径；
* helper ``tgkill`` result：0；
* parent state：``TASK_RUNNING``；
* parent ``on_rq``：1；
* parent ``on_cpu``：0；
* parent target CPU：CPU0；
* parent ``TIF_SIGPENDING``：已设置；
* parent private pending：包含一个 ``SIGUSR1``；
* siginfo：``SI_TKILL``，``si_pid=H``；
* parent kernel stack：仍停在原 ``schedule()`` 调用；
* sleeper ``t.task``：仍指向parent；
* sleep hrtimer：仍在CPU0 monotonic base中queued；
* timer hard expiry：``E = T0 + 10 ms``；
* current time：约 ``T0 + 4 ms``，早于E；
* signal handler：尚未建立frame，也尚未运行；
* next control transfer：scheduler从helper切换到parent。

关键边界
--------

#. ``tgkill`` 用TGID和TID共同锁定一个thread，并生成 ``SI_TKILL`` siginfo。
#. thread-directed signal进入target task自己的pending queue。
#. ``signal_wake_up_state`` 先设置 ``TIF_SIGPENDING``，再唤醒 ``TASK_INTERRUPTIBLE`` task。
#. wakeup只让parent runnable，不直接运行handler。
#. signal wakeup不会自动取消sleep hrtimer。
#. hrtimer callback尚未执行，所以 ``t.task`` 仍指向parent。
#. parent必须恢复自己的kernel stack，才能取消timer并计算remaining time。

资料
----

* `Linux 7.2-rc1 kernel/signal.c：tgkill、signal queue与signal_wake_up_state <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/signal.c>`_
* `Linux 7.2-rc1 kernel/sched/core.c：try_to_wake_up与runqueue activation <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/core.c>`_
* `Linux 7.2-rc1 kernel/time/hrtimer.c：sleeping hrtimer的task pointer与取消边界 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/hrtimer.c>`_
