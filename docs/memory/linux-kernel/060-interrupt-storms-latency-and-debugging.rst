第060章：中断风暴、延迟与调试策略
=================================

核心知识点
----------

中断风暴首先是事件率异常
   某个 IRQ 源在短时间内持续产生大量事件，并占用 hardirq、softirq 或 IRQ thread 时间。判断时必须比较固定时间窗口内的计数增量，单次累计值不能代表速率。

高事件率不一定是错误
   高流量网卡在压测时可能正常产生大量 IRQ；空闲或低速设备在无业务时高速增长，更可能指向 pending 位未清除、触发类型错误、共享 IRQ 误判或固件路由异常。

``/proc/interrupts`` 是第一层证据
   它给出 Linux IRQ、设备名和每 CPU 累计计数。两次同间隔采样可以确定哪个 IRQ 以多高速率落到哪些 CPU。

电平中断必须清除 pending 条件
   若设备状态仍保持有效电平，handler 返回后控制器会立即再次投递。风暴修复应优先检查设备确认和清除顺序，而不是先调整调度参数。

Hardirq 压力会扩散到下半部
   IRQ handler 往往只安排 NAPI、softirq、workqueue 或 IRQ thread。硬中断计数增长与对应 softirq 类型同步增长，说明工作量已经进入后续处理阶段。

``/proc/softirqs`` 显示类型与 CPU 分布
   NET_RX、NET_TX、TIMER、BLOCK、SCHED 和 RCU 等计数能够说明哪类延迟工作正在增长。Softirq 次数表示执行批次，不等于 packet 或请求数量。

``ksoftirqd`` 高占用表示 backlog
   它说明普通 softirq 处理窗口无法及时清空 pending 工作。该 CPU 上的用户 task、worker 和实时 task 都可能因此减少运行机会。

Threaded IRQ 压力落到 IRQ 线程
   ``irq/<n>-<name>`` 长时间占用 CPU 时，应分别检查 primary handler、``thread_fn``、线程优先级和设备事件率。

IRQ affinity 是允许集合
   ``smp_affinity`` 或 ``smp_affinity_list`` 说明 IRQ 可以投递到哪些 CPU；实际分布仍要看 ``/proc/interrupts`` 的每 CPU 增量。

局部拥塞可能由位置约束造成
   过窄 affinity 会让 IRQ、softirq 和应用 task 集中在同一 CPU，即使其它 CPU 空闲。移动 IRQ 又可能影响缓存、NUMA、RSS 队列和隔离策略。

延迟必须按执行阶段测量
   ``irq_handler_entry/exit`` 测量 top half，``softirq_raise/entry/exit`` 测量下半部，``sched_wakeup`` 到 ``sched_switch`` 测量目标 task 的 wakeup-to-run 延迟。

修复顺序应从正确性到调优
   先修复设备 pending、触发类型和共享 IRQ 判断，再考虑 affinity、coalescing、NAPI budget 和调度策略。后者只能重新分配成本，不能修复错误事件源。

关键路径
--------

确认中断风暴：

::

   保存 /proc/interrupts 第一次快照
   → 等待固定时间窗口
   → 保存第二次快照
   → 计算每个 IRQ、每个 CPU 的增量
   → 对照设备业务量判断速率是否合理
   → 异常时检查触发类型、pending 清除与共享 IRQ

追踪硬中断到下半部：

::

   找到异常增长的 Linux IRQ
   → 确认设备与 handler
   → 对照 /proc/softirqs 的类型和 CPU 增量
   → 观察 ksoftirqd 或 IRQ thread CPU 使用
   → 使用 IRQ 与 softirq tracepoint 建立时间线
   → 判断成本位于 top half、bottom half 或调度等待

分析 CPU 分布：

::

   读取 IRQ 的 smp_affinity_list
   → 读取 /proc/interrupts 实际每 CPU 增量
   → 检查 MSI-X vector 与设备队列
   → 检查 irqbalance、RSS/RPS/XPS 和应用 affinity
   → 判断缓存、NUMA 与隔离要求
   → 一次只修改一个位置参数
   → 在相同负载下重新验证

建立完整延迟链：

::

   记录设备事件与 IRQ 到达
   → 测量 irq_handler_entry 到 exit
   → 跟踪 softirq_raise 到 entry/exit
   → 找到目标 task 的 sched_wakeup
   → 找到 task 作为 sched_switch next
   → 分别计算 handler、softirq 与调度等待
   → 对齐 CPU、时间基准和业务日志

概念辨析
--------

高事件率与错误风暴
   高负载设备可能正常产生大量 IRQ；无业务时持续高速 IRQ 更指向设备、驱动或路由错误。

Hardirq 压力与 softirq 压力
   前者来自入口和 top half；后者来自批处理、协议栈、timer 等延迟工作。

Affinity 允许集合与实际落点
   Affinity 规定可用 CPU；控制器、队列、负载和 irqbalance 决定实际分布。

IRQ 次数与处理对象数量
   一次 IRQ 或 softirq 可以批量处理多个对象，计数不能直接换算成 packet 或请求数。

吞吐优化与延迟优化
   Coalescing 和更大 budget 可以减少中断次数并提高吞吐，也可能增加单批执行时间和尾延迟。

本章结论
--------

中断风暴诊断必须先量化 IRQ 事件率，再沿 softirq、IRQ thread 和 CPU 分布追踪实际工作，最后用调度时间线证明这些事件怎样转化为系统延迟。