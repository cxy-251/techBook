第一百四十七章：local APIC定时器中断怎样让timerfd callback唤醒epoll_wait？
================================================================================

上一章结束时，parent阻塞在eventpoll自己的wait queue：

::

   parent TASK_INTERRUPTIBLE on EP.wq
   T.t.tmr queued on CPU0 monotonic hrtimer base
   T.ticks = 0
   T.expired = 0
   EP.rdllist = empty

CPU0正在运行idle task。20ms deadline到达后，QEMU的local APIC向CPU0投递local timer vector。

本章固定条件继续保持：

* CPU0是唯一online CPU；
* high-resolution timer mode已经启用；
* local APIC clock-event的event handler是 ``hrtimer_interrupt``；
* timerfd hrtimer运行在hardirq expiry base，非PREEMPT_RT；
* 本次中断没有更早的其他hard hrtimer callback；
* one-shot timer只到期一次；
* ``T.wqh`` 上只有epoll callback ``P``；
* ``EP.wq`` 上只有parent waiter ``W``；
* 没有close、DEL、signal、migration或callback竞态。

本章结束在timerfd callback已经把 ``T.ticks`` 增加到1，epitem已经进入ready list，parent已经重新变成runnable；parent尚未恢复原来的 ``epoll_wait`` kernel stack。

x86怎样进入local APIC timer vector
---------------------------------

CPU从idle状态进入interrupt gate，对应入口：

::

   sysvec_apic_timer_interrupt

``DEFINE_IDTENTRY_SYSVEC`` 建立的入口保存register frame并切换到内核interrupt上下文。当前task identity仍是CPU0 idle task，但执行上下文已经是hardirq。

入口首先：

::

   set_irq_regs(regs)
   apic_eoi()
   trace_local_timer_entry(LOCAL_TIMER_VECTOR)
   local_apic_timer_interrupt()

``apic_eoi`` 告诉local APIC当前vector已经被CPU接受，允许APIC继续处理后续interrupt priority状态。它不代表hrtimer callback已经完成。

local_apic_timer_interrupt怎样进入hrtimer core
---------------------------------------------

``local_apic_timer_interrupt`` 取得CPU0 per-CPU clock-event device：

::

   evt = this_cpu_ptr(&lapic_events)

固定设备已经初始化，所以 ``evt->event_handler`` 非NULL。函数增加APIC timer interrupt统计后调用：

::

   evt->event_handler(evt)
   → hrtimer_interrupt(evt)

这里需要区分两层对象：

* local APIC clock-event负责在硬件deadline时产生一次CPU interrupt；
* hrtimer core维护多个软件hrtimer，并决定本次interrupt应运行哪些callback。

APIC并不知道 ``timerfd_ctx``，也不直接修改 ``T.ticks``。

hrtimer_interrupt怎样找到到期timer
---------------------------------

``hrtimer_interrupt`` 在interrupts disabled状态进入，取得CPU0的：

::

   struct hrtimer_cpu_base *B

随后锁住：

::

   B->lock

并更新当前monotonic time。为了在扫描期间避免错误的remote reprogram，core暂时把：

::

   B->expires_next = KTIME_MAX

然后调用：

::

   __hrtimer_run_queues(B, now, flags, HRTIMER_ACTIVE_HARD)

monotonic hard base的最左侧timer是 ``T.t.tmr``。固定 ``now`` 已经到达或超过soft expiry，因此进入：

::

   __run_hrtimer(B, monotonic_base, &T.t.tmr, now, flags)

callback运行前，core完成这些状态变化：

::

   base->running = &T.t.tmr
   remove T.t.tmr from active timer tree
   T.t.tmr.is_queued = inactive

因此callback开始时，one-shot timer已经不在RB tree里，但 ``base->running`` 明确指出它正在执行。

为什么callback运行时暂时释放cpu-base lock
---------------------------------------

``__run_hrtimer`` 保存callback指针后释放 ``B->lock``，再调用：

::

   timerfd_tmrproc(&T.t.tmr)

hrtimer core不能在持有raw CPU-base lock时调用任意timer callback，否则callback内部需要其他锁或重新arm timer时容易形成锁嵌套与死锁。

当前仍处于CPU0 hardirq上下文；释放的是hrtimer CPU-base raw lock，不是开启一次普通task调度点。

timerfd_tmrproc怎样修改ctx
--------------------------

``timerfd_tmrproc`` 通过 ``container_of`` 从内嵌hrtimer找到：

::

   timerfd_ctx T

然后调用：

::

   timerfd_triggered(T)

``timerfd_triggered`` 获取 ``T.wqh.lock``，并执行核心函数：

.. code-block:: c

   T.expired = 1;
   T.ticks++;
   wake_up_locked_poll(&T.wqh, EPOLLIN);

固定状态变化：

::

   T.expired: 0 → 1
   T.ticks:   0 → 1

``ticks`` 是尚未被用户read消费的expiration数量。``expired`` 用于标记底层timer发生过callback，特别服务于periodic timer的lazy restart逻辑。本场景 ``tintv=0``，后续不会周期restart。

EPOLLIN wake怎样到达epoll callback
---------------------------------

``wake_up_locked_poll`` 已经在 ``T.wqh.lock`` 下运行。queue中唯一entry是non-exclusive callback ``P``：

::

   P.wait.func = ep_poll_callback
   P.epi       = I

wake key包含 ``EPOLLIN``。``ep_poll_callback`` 检查该key与 ``I.event.events``：

::

   EPOLLIN matches EPOLLIN|EPOLLERR|EPOLLHUP

callback随后锁住 ``EP.lock``。``I`` 当前不在任何ready list，因此：

::

   add I to tail of EP.rdllist

固定没有scan正在进行，所以不会使用 ``EP.ovflist``。

callback还会检查 ``EP.wq``。parent的exclusive waiter ``W`` 仍在queue中，于是通过wake function进入scheduler wake path：

::

   parent TASK_INTERRUPTIBLE → TASK_RUNNING
   enqueue parent on CPU0 runqueue

``W.func`` 是 ``ep_autoremove_wake_function``，所以wake尝试后 ``W`` 从 ``EP.wq`` 自动摘除。这个自动摘除只处理parent的stack waiter，不会移除 ``P`` 或 ``I``。

两级wake链可以压缩为：

::

   timerfd callback
   → wake T.wqh
   → run callback P
   → queue epitem I on EP.rdllist
   → wake EP.wq
   → parent becomes runnable

hrtimer callback为什么返回NORESTART
---------------------------------

``timerfd_tmrproc`` 固定返回：

::

   HRTIMER_NORESTART

``__run_hrtimer`` 重新获取 ``B->lock`` 后，不会把 ``T.t.tmr`` 再次排入active tree。随后清除：

::

   base->running = NULL

这与one-shot ``T.tintv=0`` 一致。即使timerfd是periodic，timerfd也不会在callback中直接周期重arm；它延迟到read或gettime访问时调用 ``timerfd_restart``，避免极短周期造成callback DoS。

hrtimer_interrupt怎样完成硬件重编程
----------------------------------

callback结束后， ``hrtimer_interrupt`` 重新更新当前时间，计算CPU0所有hrtimer base中的下一到期时间：

::

   expires_next = hrtimer_update_next_event(B)

本场景不固定系统中其他timer，所以 ``expires_next`` 可能是另一个内核timer的deadline或 ``KTIME_MAX``。hrtimer core据此重新编程local APIC clock-event，随后释放 ``B->lock``。

x86入口继续：

::

   trace_local_timer_exit
   set_irq_regs(old_regs)
   return from interrupt

interrupt exit看到parent已经runnable。固定scheduler顺序要求CPU0离开idle并选择parent；parent将在下一章恢复原 ``epoll_wait`` 调用栈。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：CPU0处于interrupt-exit/scheduler交接；
* CPU mode：x86-64 CPL 0；
* interrupted task：CPU0 idle task；
* parent：``TASK_RUNNING``，已在CPU0 runqueue；
* parent ``on_rq=1``、 ``on_cpu=0``；
* helper：阻塞在timerfd/epoll之外；
* fd 6：open timerfd ``F6``；
* timerfd ctx ``T``：active；
* ``T.t.tmr``：inactive、not queued、not running；
* ``T.tintv``：0；
* ``T.expired``：1；
* ``T.ticks``：1；
* ``T.wqh``：仍包含callback ``P``；
* callback ``P``：仍active；
* fd 7：open eventpoll ``F7``；
* eventpoll ``EP``：active， ``refcount=2``；
* ``EP.rbr``：包含 ``I``；
* ``EP.rdllist``：包含ready ``I``；
* ``EP.ovflist``：``EP_UNACTIVE_PTR``；
* parent waiter ``W``：已从 ``EP.wq`` 自动移除；
* filesystem/block I/O：none；
* next control entry：scheduler恢复parent的 ``ep_poll`` stack。

关键边界
--------

#. local APIC clock-event只产生硬件interrupt，不理解timerfd对象。
#. ``hrtimer_interrupt`` 在CPU0 per-CPU bases中选择真正到期的软件timer。
#. callback前timer已从active tree移除，并由 ``base->running`` 标记执行中。
#. hrtimer core释放CPU-base lock后才调用 ``timerfd_tmrproc``。
#. timerfd callback在 ``T.wqh.lock`` 下把 ``ticks`` 从0增到1。
#. wake key是 ``EPOLLIN``，因此匹配epitem interest。
#. ``P`` 把target wait queue事件转换成eventpoll ready-list membership。
#. ``W`` 把eventpoll readiness转换成parent task runnable状态。
#. ``P`` 与 ``W`` 属于不同wait queue，生命周期也不同。
#. wake后 ``W`` 自动移除； ``P`` 继续挂在 ``T.wqh``。
#. one-shot callback返回 ``HRTIMER_NORESTART``，timer保持inactive。
#. parent被唤醒不等于event已经复制到用户空间；交付要等恢复后重新poll。

下一任务
--------

下一章恢复parent：

::

   epoll_wait resumes
   → ep_send_events
   → timerfd_poll sees T.ticks=1
   → copy {EPOLLIN, data=0x71FD6}
   → epoll_wait returns 1
   → read(6, &expirations, 8)
   → T.ticks 1 → 0
   → expirations=1
   → read returns 8

资料
----

* `Linux 7.2-rc1 arch/x86/kernel/apic/apic.c：local APIC timer vector <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/apic/apic.c>`_
* `Linux 7.2-rc1 kernel/time/hrtimer.c：hrtimer_interrupt与callback执行 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/hrtimer.c>`_
* `Linux 7.2-rc1 fs/timerfd.c：timerfd_tmrproc、ticks与wait queue wake <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/timerfd.c>`_
* `Linux 7.2-rc1 fs/eventpoll.c：ep_poll_callback与eventpoll waiter wake <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
