第059章：Softirq、Tasklet、Workqueue 与 Threaded IRQ
==================================================

本章必须记住
------------

#. Softirq、tasklet、workqueue 和 threaded IRQ 都用于延后处理，但它们的执行上下文、并发模型和睡眠能力不同。
#. Softirq 是固定编号的底层延迟执行机制，核心对象包括 softirq vector、pending 位和处理函数。
#. ``open_softirq()`` 把编号与处理函数关联，``raise_softirq()`` 设置 pending，处理路径消费 pending 并调用对应 action。
#. 网络接收、网络发送、timer、RCU 和块层等高频核心路径会使用 softirq。
#. Softirq handler 运行时按 atomic context 规则处理，不能睡眠，也不能使用阻塞 mutex 或 ``GFP_KERNEL``。
#. 同一种 softirq 可以在多个 CPU 上并发执行，共享对象必须使用 per-CPU 设计、锁、状态位或队列协议保护。
#. Softirq 处理有时间和重启次数限制；持续 pending 时，剩余工作会交给每 CPU 的 ``ksoftirqd/N``。
#. ``ksoftirqd`` 是内核线程，但它处理 softirq 时仍执行 softirq 语义，不能因此把 handler 当成普通可睡眠 work。
#. ``/proc/softirqs`` 按 CPU 展示各 softirq 类型的累计执行次数，适合观察类型和分布。
#. Tasklet 建立在 softirq 之上，把固定 vector 包装成可动态调度的回调对象。
#. 同一个 tasklet 实例通常不会并发执行，但不同 tasklet 可以在不同 CPU 上并发运行。
#. Tasklet 串行化只覆盖该 tasklet 回调，不自动保护 IRQ、设备关闭路径和其它对象访问者。
#. Tasklet 仍不能睡眠，不能用于需要 mutex、阻塞 I/O 或复杂资源等待的路径。
#. 设备拆除前必须停止新调度并等待已调度 tasklet 结束，避免宿主对象释放后回调继续访问。
#. Workqueue 把 ``work_struct`` 交给 worker pool 和 kworker 执行，属于进程上下文延迟工作。
#. Workqueue 回调通常允许睡眠、使用 mutex、等待 completion 和执行 ``GFP_KERNEL`` 分配。
#. Workqueue 回调没有原始用户调用者的用户地址空间语义；用户数据必须在原进程上下文先复制为内核对象。
#. ``system_wq`` 等系统 workqueue 适合普通异步工作；专用 workqueue 用于控制并发、优先级、CPU 绑定和回收语义。
#. Bound workqueue 与特定 CPU worker pool 相关，利于局部性；unbound workqueue 允许更灵活地选择执行 CPU。
#. ``WQ_HIGHPRI``、``WQ_MEM_RECLAIM``、``WQ_CPU_INTENSIVE`` 等属性表达不同调度和资源保证，不能随意添加。
#. ``WQ_MEM_RECLAIM`` 用于可能参与内存回收路径的 workqueue，确保回收压力下仍有执行进展。
#. 同一个 work item 已处于 pending 状态时，重复 ``queue_work()`` 不会简单产生多个并发实例；具体重排和重新排队仍要按 API 契约判断。
#. ``flush_work()``、``cancel_work_sync()``、``flush_workqueue()`` 等接口用于等待或取消工作，是对象拆除协议的重要部分。
#. Work 回调可能重新排队自己、timer 或其它 work，teardown 必须先阻止重新排队，再执行同步取消。
#. Threaded IRQ 使用 ``request_threaded_irq()`` 将硬中断 primary handler 和可调度 ``thread_fn`` 绑定起来。
#. Primary handler 仍在 hardirq 中，只做确认、屏蔽、保存状态和返回 ``IRQ_WAKE_THREAD``。
#. ``thread_fn`` 在 ``irq/<n>-<name>`` 一类内核线程中运行，通常允许睡眠并受调度器 policy/priority 管理。
#. ``IRQF_ONESHOT`` 常用于在线程处理完成前保持 IRQ 屏蔽，防止共享状态尚未收束时再次进入。
#. PREEMPT_RT 会线程化许多普通 IRQ，并改变部分锁语义，但 NMI、raw spinlock 和底层不可线程化区间仍保留硬实时约束。
#. Threaded IRQ 适合主体处理和 IRQ 生命周期强相关的设备路径；普通 workqueue 更适合与单次 IRQ 解耦的通用异步任务。
#. 机制选择不能只看“快慢”，必须同时判断上下文、并发、可睡眠性、CPU 局部性、取消和对象生命周期。

必背路径
--------

Softirq 路径：

::

   硬中断或内核路径 raise_softirq
   → 设置当前 CPU pending 位
   → 在 IRQ 退出或其它允许点处理 pending
   → 调用对应 softirq action
   → 达到时间或重启限制时唤醒 ksoftirqd
   → ksoftirqd 继续处理剩余 pending

Tasklet 路径：

::

   初始化宿主对象中的 tasklet
   → IRQ 或其它路径调用 tasklet_schedule
   → 挂入 per-CPU tasklet 队列
   → raise TASKLET_SOFTIRQ
   → softirq 路径取得 tasklet
   → 同一实例串行执行回调
   → teardown 前 kill 或同步等待

Workqueue 路径：

::

   INIT_WORK 绑定内核对象与回调
   → queue_work 放入 workqueue
   → worker pool 选择 kworker
   → work 回调在进程上下文执行
   → 可以睡眠并完成复杂处理
   → 更新对象状态或重新排队
   → teardown 阻止新排队
   → cancel/flush 等待旧工作结束

Threaded IRQ 路径：

::

   request_threaded_irq 注册 handler 与 thread_fn
   → IRQ 到达并调用 primary handler
   → 确认来源、保存状态、必要时 mask
   → 返回 IRQ_WAKE_THREAD
   → IRQ core 唤醒 irq thread
   → thread_fn 完成可睡眠主体处理
   → 恢复设备与 IRQ

必须区分
--------

* Softirq 与 ``ksoftirqd``：``ksoftirqd`` 提供可调度执行容器；softirq handler 本身仍遵守不可睡眠语义。
* Tasklet 串行化与对象互斥：同一 tasklet 实例不并发，不代表整个设备对象没有其它并发访问者。
* Workqueue 与 IRQ thread：Workqueue 是通用异步执行框架；IRQ thread 与具体 IRQ 的屏蔽、唤醒和优先级协议直接绑定。
* Bound 与 unbound workqueue：Bound 强调 per-CPU 局部性；unbound 强调跨 CPU 执行弹性。
* 排队成功与工作完成：``queue_work()`` 只说明工作进入或已经处于 pending 状态，不说明回调已经运行完毕。

一句话结论
----------

Softirq 和 tasklet 适合不可睡眠的低层延迟工作，workqueue 和 threaded IRQ 提供可调度线程上下文；正确选择取决于上下文、并发和生命周期，而不是机制名称。
