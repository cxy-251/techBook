第060章：中断风暴、延迟与调试策略
=================================

本章必须记住
------------

#. 中断问题常先表现为 CPU 使用率高、交互延迟、网络或块层抖动和实时任务超期。
#. 中断风暴是某个 IRQ 源在短时间内产生异常高事件率，并持续占用 hardirq、softirq 或 IRQ thread 时间。
#. 高 IRQ 事件率可能来自真实高负载，也可能来自设备 pending 位未清除、触发类型错误、共享 IRQ 误判、固件路由或控制器异常。
#. 判断风暴必须比较固定时间窗口内同一 IRQ 的计数增量，单次累计值不能表示速率。
#. ``/proc/interrupts`` 提供 Linux IRQ、每 CPU 累计计数、设备名和部分控制器信息，是硬中断事件率的第一证据。
#. 某个空闲或低速设备的 IRQ 在无业务时高速增长，比高流量网卡压测时计数增长更可疑。
#. 电平中断的设备 pending 条件未清除时，handler 返回后中断线仍有效，会立即再次进入。
#. Shared IRQ 中，handler 若不能准确判断事件来源，可能频繁返回 ``IRQ_NONE`` 或误处理其它设备状态。
#. 中断控制器触发类型与设备实际信号不匹配，会造成丢边沿、重复进入或长期 pending。
#. Hardirq 只表示设备事件已进入内核；大量后续处理通常继续进入 softirq、NAPI、IRQ thread 或 workqueue。
#. ``/proc/softirqs`` 按 CPU 提供 NET_RX、NET_TX、TIMER、BLOCK、SCHED、RCU 等累计计数。
#. 某设备 IRQ 增长与对应 softirq 类型同步增长，说明压力已从硬中断扩展到下半部。
#. ``ksoftirqd/N`` 长时间占用某 CPU，表示该 CPU 的 softirq 工作无法在普通处理窗口内及时完成。
#. ``ksoftirqd`` 高占用会减少该 CPU 上用户 task、worker 和实时 task 的可运行时间。
#. Threaded IRQ 压力通常表现为 ``irq/<n>-<name>`` 线程占用 CPU，应检查 primary handler、thread_fn 和线程优先级。
#. IRQ affinity 决定某个 IRQ 允许投递到哪些 CPU，接口常位于 ``/proc/irq/<irq>/smp_affinity`` 和 ``smp_affinity_list``。
#. Affinity 是允许集合，``/proc/interrupts`` 的每 CPU 增量才是实际分布。
#. 允许集合很宽但计数集中，可能来自设备队列、控制器、RSS、irqbalance 或实际流量方向。
#. 允许集合过窄会让 hardirq、softirq 和同 CPU 应用线程形成局部竞争，即使其它 CPU 空闲。
#. 多队列网卡通常使用多个 MSI-X vector；IRQ、队列、RSS/RPS/XPS 和应用 affinity 需要统一分析。
#. 把 IRQ 移到其它 CPU 可能降低当前 CPU 延迟，也可能破坏缓存局部性、NUMA 关系或隔离策略。
#. 修改 IRQ affinity 前应保存原值、记录业务基线，并确认控制器支持 set_affinity。
#. ``irq_handler_entry`` 与 ``irq_handler_exit`` tracepoint 能测量 handler 调用次数和执行区间。
#. ``softirq_raise``、``softirq_entry`` 与 ``softirq_exit`` 能说明 softirq 何时排队、进入和退出。
#. ``sched_wakeup`` 与 ``sched_switch`` 能说明中断或下半部唤醒 task 后，它还等待了多久才获得 CPU。
#. Perf 可以显示 CPU 样本落在 hardirq、softirq、驱动 handler、协议栈还是 worker 中。
#. Ftrace 和 perf 本身会增加开销；必须限制 IRQ、CPU、事件类型和采集时间，并检查 trace 丢失。
#. 风暴排查不能只看 CPU 百分比，要建立“设备事件率 → IRQ 分布 → softirq 类型 → CPU 执行者 → task 调度延迟”证据链。
#. IRQ count 高但 handler 很短，主要成本可能在 softirq；IRQ count 不高但 handler 很长，问题可能在 top half 设计。
#. Softirq 次数不等于处理对象数量，一个 softirq invocation 可能批量处理多个 packet、timer 或 completion。
#. Interrupt coalescing 可以降低 IRQ 频率但增加单次批量和延迟；参数选择是吞吐与尾延迟权衡。
#. NAPI budget 或队列处理过大可能提高吞吐，同时让 softirq 长时间占据 CPU。
#. 中断风暴会覆盖日志并改变调度时序，日志应限速，诊断优先使用计数和 tracepoint。
#. 修复顺序应优先处理设备状态和驱动确认错误，再考虑 affinity、coalescing 和调度参数。
#. 生产系统调参必须同时验证吞吐、P99 延迟、丢包或错误、CPU 分布和故障恢复。
#. 最终结论应明确：哪个 IRQ 在什么负载下以多高事件率落到哪些 CPU，后续工作进入哪种上下文，以及谁因此延迟。

必背路径
--------

确认是否存在中断风暴：

::

   保存 /proc/interrupts 第一次快照
   → 等待固定时间窗口
   → 保存第二次快照
   → 计算每个 IRQ、每个 CPU 的增量
   → 按设备名和业务负载判断速率是否合理
   → 异常时检查触发类型、pending 清除和共享 IRQ

追踪硬中断到软中断：

::

   找到异常增长的 Linux IRQ
   → 确认设备和 handler
   → 对照 /proc/softirqs 的类型与 CPU 增量
   → 观察 ksoftirqd 或 IRQ thread CPU 使用
   → 使用 irq/softirq tracepoint 建立时间线
   → 判断成本落在 top half、bottom half 还是调度等待

分析 CPU 分布：

::

   读取 smp_affinity_list
   → 读取 /proc/interrupts 实际每 CPU 计数
   → 检查设备队列和 MSI-X vector
   → 检查 irqbalance、RSS/RPS/XPS 和应用 affinity
   → 判断局部性、NUMA 与隔离要求
   → 一次只修改一个 affinity 或队列参数
   → 重复相同负载验证

建立完整延迟证据：

::

   记录设备事件和 IRQ 到达
   → 测量 irq_handler_entry 到 exit
   → 跟踪 softirq_raise 到 entry/exit
   → 找到目标 task 的 sched_wakeup
   → 找到 task 作为 sched_switch next
   → 分别计算 handler、softirq 和 wakeup-to-run 延迟
   → 对齐 CPU、时间基准和业务日志

必须区分
--------

高事件率与错误风暴
   高负载设备可能正常产生大量 IRQ；空闲状态下持续高速 IRQ 更指向设备或驱动错误。

Hardirq 压力与 softirq 压力
   前者来自入口和 top half；后者来自延迟批处理、协议栈和 timer 等下半部。

Affinity 允许集合与实际落点
   ``smp_affinity`` 表示允许 CPU；实际计数分布由控制器、队列和运行负载决定。

IRQ 次数与处理对象数量
   一次 IRQ 或 softirq 可以批量处理多个对象，不能把计数直接当作 packet 或请求数。

吞吐优化与延迟优化
   Coalescing 和大 budget 可能提高吞吐，却增加单批处理时间和尾延迟。

一句话结论
----------

中断风暴诊断必须先量化 IRQ 事件率，再沿 softirq 和 CPU 分布追踪实际工作，最后用调度时间线证明事件压力怎样转化成系统延迟。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 12，Interrupts, Exceptions, Softirq, Tasklet, and Workqueue；
* AIBook 章节：Chapter 60，Interrupt Storms, Latency, and Debugging Strategies；
* 源文件：``docs/LinuxK/Part_12_Interrupts_Exceptions_Softirq_Tasklet_and_Workqueue/Chapter_060_Interrupt_Storms_Latency_and_Debugging_Strategies.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_12_Interrupts_Exceptions_Softirq_Tasklet_and_Workqueue/Chapter_060_Interrupt_Storms_Latency_and_Debugging_Strategies.md>`_。