第059章：Softirq、Tasklet、Workqueue 与 Threaded IRQ
==================================================

核心知识点
----------

延迟执行机制应按执行上下文而不是旧名称分类
   Softirq、tasklet、BH workqueue、threaded workqueue 和 threaded IRQ 都把工作推迟到稍后执行，但真正决定选择的是能否睡眠、并发模型、CPU 局部性、延迟和生命周期协议。

Softirq 是固定类型的底层机制
   ``open_softirq()`` 注册处理函数，``raise_softirq()`` 设置当前 CPU 的 pending 位。网络、timer、RCU 等高频核心路径会直接使用 softirq。

Softirq 仍是 atomic context
   Handler 不能睡眠，也不能使用阻塞 mutex 或 ``GFP_KERNEL``。同一种 softirq 可以在多个 CPU 上并发执行，共享对象必须依靠 per-CPU 数据、锁或状态协议保护。

``ksoftirqd`` 不改变处理语义
   Softirq 超过时间或重启限制后，剩余工作会交给每 CPU 的 ``ksoftirqd/N``。它虽由内核线程承载，softirq handler 仍按不可睡眠规则运行。

Tasklet 是建立在 softirq 上的旧式动态回调包装
   同一 tasklet 实例通常不会并发执行，但不同实例及其它对象访问路径仍可能并发。现代代码不应因为“需要 bottom half”就默认新建 tasklet，应先判断现有子系统机制、BH workqueue 或 threaded workqueue 是否更合适。

BH workqueue 把 workqueue 管理接口带入 softirq context
   使用 ``WQ_BH`` 创建的 workqueue 始终是 per-CPU，并在排队 CPU 的 softirq context 中按队列顺序执行。它可以看作 softirq 的 convenience interface：work item **不能睡眠**，却可以使用 workqueue 的 delayed queueing、flush、cancel 等生命周期管理能力。

``WQ_BH`` 不是普通 kworker workqueue
   BH workqueue 使用 pseudo worker 表示 bottom-half 执行上下文，不由可睡眠 kworker 承载。``max_active`` 必须为 0，除 ``WQ_HIGHPRI`` 外不能随意叠加其它 workqueue flag。

Threaded workqueue 提供可调度执行环境
   普通 ``work_struct`` 进入 worker pool 后由 kworker 执行，通常可以睡眠、使用 mutex、等待 completion 和进行 ``GFP_KERNEL`` 分配。

Threaded workqueue 分为 bound 与 unbound
   Bound workqueue 更强调 per-CPU 局部性；unbound workqueue 允许更灵活的 CPU 调度。``WQ_HIGHPRI``、``WQ_MEM_RECLAIM`` 等属性表达特殊执行保证，不能随意使用。

Work item 具有 pending 状态
   重复 ``queue_work()`` 不会简单创建多个并发实例。排队成功只说明工作已进入或已经处于 pending 状态，不表示回调已完成。

Workqueue 拆除依赖同步接口
   ``cancel_work_sync()``、``flush_work()`` 和 ``flush_workqueue()`` 用于停止或等待旧工作。若回调会重新排队自己、timer 或其它 work，必须先关闭重新排队入口。

Threaded IRQ 与具体中断绑定
   ``request_threaded_irq()`` 注册 primary handler 与 ``thread_fn``。Primary handler 在 hardirq 中完成最小确认并返回 ``IRQ_WAKE_THREAD``，主体工作在线程上下文执行。

``IRQF_ONESHOT`` 维持处理边界
   对需要在线程完成前保持 IRQ 屏蔽的设备，它可避免共享状态尚未收束时重复进入。具体使用仍要符合触发类型和设备协议。

机制选择必须包含生命周期
   除了能否睡眠，还要判断多 CPU 并发、CPU 局部性、延迟要求、取消能力、内存回收保证和宿主对象何时能够释放。

关键路径
--------

Softirq 路径：

::

   硬中断或内核路径 raise_softirq
   → 设置当前 CPU pending 位
   → 在 IRQ 退出或其它允许点处理 pending
   → 调用对应 softirq action
   → 达到时间或重启限制
   → 唤醒 ksoftirqd
   → ksoftirqd 继续处理剩余工作

BH workqueue 路径：

::

   alloc_workqueue(..., WQ_BH, 0)
   → queue work on current / target CPU
   → enter that CPU softirq context
   → BH pseudo worker executes work item
   → callback must not sleep
   → flush / cancel / delayed-work API manages lifecycle

Threaded workqueue 路径：

::

   INIT_WORK 绑定对象与回调
   → queue_work 放入 workqueue
   → worker pool 选择 kworker
   → work function 在进程上下文执行
   → 完成可睡眠复杂处理
   → 更新对象状态或重新排队
   → teardown 阻止新排队
   → cancel 或 flush 等待旧工作结束

Threaded IRQ 路径：

::

   request_threaded_irq 注册 handler 与 thread_fn
   → IRQ 到达并调用 primary handler
   → 确认来源、保存状态、必要时 mask
   → 返回 IRQ_WAKE_THREAD
   → IRQ core 唤醒 IRQ thread
   → thread_fn 完成主体处理
   → 恢复设备与 IRQ

选择机制：

::

   deferred work
   → must sleep ?
      ├─ yes → threaded workqueue / threaded IRQ
      └─ no  → must run as low-level softirq-style bottom half ?
                  ├─ yes → existing softirq / WQ_BH / subsystem mechanism
                  └─ no  → prefer threaded workqueue for clearer lifecycle

概念辨析
--------

Softirq 与 ``ksoftirqd``
   ``ksoftirqd`` 提供可调度承载者；softirq 回调本身仍不能睡眠。

Tasklet 与现代 bottom-half 选择
   Tasklet 仍是 softirq 上的动态包装，但“需要延迟执行”不再等于“应该创建 tasklet”；应优先按上下文和生命周期选择机制。

``WQ_BH`` 与普通 Workqueue
   ``WQ_BH`` work item 在 softirq context 执行、不能睡眠；普通 threaded workqueue 由 kworker 执行并通常可以睡眠。

BH workqueue 与 Softirq
   BH workqueue 复用 softirq 执行上下文，同时提供 workqueue 的排队、取消和 flush 管理接口；它没有把 bottom half 变成进程上下文。

Workqueue 与 IRQ thread
   Workqueue 是通用异步框架；IRQ thread 与具体 IRQ 的唤醒、屏蔽和优先级协议直接绑定。

Bound 与 unbound workqueue
   Bound 强调 CPU 局部性；unbound 强调跨 CPU 调度弹性。

排队成功与执行完成
   排队只建立未来执行资格；对象释放前仍需等待回调真正退出。

本章结论
--------

现代延迟执行不应只背 ``softirq / tasklet / workqueue / threaded IRQ`` 四个名字。应先区分 atomic bottom-half 与可睡眠线程上下文：低层不可睡眠工作可以使用现有 softirq、``WQ_BH`` 或子系统机制；复杂可阻塞工作使用 threaded workqueue；与具体设备中断直接绑定的主体工作使用 threaded IRQ。真正的选择依据始终是执行能力、并发模型和对象生命周期。