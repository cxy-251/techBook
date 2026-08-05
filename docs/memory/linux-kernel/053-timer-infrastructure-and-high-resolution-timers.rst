第053章：定时器基础设施与高精度定时器
=====================================

本章必须记住
------------

#. 内核定时器把“未来某个时间执行”编码成一个延迟执行对象，使当前路径不必占用 CPU 忙等。
#. 定时器通常嵌入业务对象中；timer 只是到期入口，真正状态和生命周期属于外层对象。
#. 普通 timer 的核心对象是 ``struct timer_list``，常用 ``timer_setup()`` 初始化。
#. ``mod_timer()`` 设置或更新普通 timer 的绝对 ``jiffies`` 到期点，并在需要时重新入队。
#. 普通 timer 适合设备请求超时、连接超时、缓存维护和粗粒度周期任务。
#. 普通 timer 到期回调通常运行在 timer softirq 上下文，不能睡眠。
#. 回调中不能使用可能阻塞的 mutex、普通用户内存访问、同步 I/O 或 ``GFP_KERNEL`` 分配。
#. timer 回调应只完成短小动作：修改状态、记录到期、唤醒等待者或排入 workqueue。
#. 需要睡眠或执行复杂恢复时，应把工作转移到线程型 workqueue 或专用内核线程。
#. ``from_timer()`` 用 timer 成员反向取得宿主对象，说明回调安全依赖宿主对象仍然存活。
#. 对象释放前必须停止 timer，并同步可能正在执行的回调，否则会产生 use-after-free。
#. ``del_timer_sync()``、``timer_delete_sync()``、``timer_shutdown_sync()`` 等具体 API 名称和语义随版本演进，应以目标内核为准。
#. teardown 不仅要删除当前 timer，还要防止回调、work 或其它路径再次重新 arm timer。
#. timer 与 workqueue 互相重新排队时，必须建立明确 stopping 状态并按顺序同步两者。
#. 普通 timer 使用 timer wheel 和 per-CPU timer base 管理大量到期对象，强调低成本而非最高精度。
#. ``jiffies`` 精度受 ``CONFIG_HZ`` 影响，普通 timer 的实际回调时间还会被中断、softirq 和 CPU 负载推迟。
#. timer 到期时间通常表示最早可处理边界，不保证回调在该时刻精确开始。
#. 高精度定时器的核心对象是 ``struct hrtimer``，使用 ``ktime_t`` 表达时间。
#. hrtimer 适合纳秒级时间表达、精细睡眠、POSIX timer 和时间敏感唤醒。
#. hrtimer 按到期顺序维护活动对象，并以最早到期项驱动下一次事件编程。
#. 现代 hrtimer 实现细节可能结合红黑树和额外队列状态；应依赖接口语义而非死记单一内部结构。
#. ``hrtimer_start()`` 可以按绝对或相对时间启动 timer；模式还可能包含 pinned 等 CPU 约束。
#. 周期性 hrtimer 应使用 ``hrtimer_forward()`` 或 ``hrtimer_forward_now()`` 推进下一截止时间，避免简单地按回调完成时刻累积漂移。
#. hrtimer 的高精度依赖可用的 clocksource、one-shot clockevents、内核配置和平台硬件。
#. 只有 clocksource 能读时间还不够；未来时刻要产生执行入口，还需要 clockevents 设备触发中断。
#. clockevents 是时间闹钟，能把硬件编程为在下一目标时间产生事件。
#. high-resolution 模式下，最早到期 hrtimer 变化时，内核可能重新编程本 CPU 的 clockevent。
#. clockevent 中断到来后，时间路径处理到期 hrtimer，并按配置和模式执行或延后回调。
#. hrtimer 回调也不能默认睡眠；具体执行上下文受模式、PREEMPT_RT 和实现影响，必须按 API 文档确认。
#. 高精度表示不等于零延迟交付；关中断、长回调、锁竞争和调度延迟仍会让实际执行晚于目标时间。
#. 普通 timer 与 hrtimer 的选择应依据业务时间精度，而不是“hrtimer 看起来更先进”。
#. 对不敏感的后台维护可以使用 ``round_jiffies()`` 一类聚合接口，减少零散唤醒和功耗。
#. pinned timer 限制 timer 留在指定 CPU，减少迁移语义，但会让 CPU hotplug 和局部延迟更复杂。
#. timer 重复启动、取消和回调并发时，需要锁或原子状态保证“完成”和“超时”只能赢一次。
#. 取消 timer 成功不自动取消已经由回调排入的 work，二者必须分别同步。
#. 调试 timer 时应记录计划到期时间、实际回调时间、回调 CPU、是否迁移和回调执行时长。
#. ``timer_start``、``timer_expire_entry``、``timer_expire_exit``、hrtimer 事件和 IRQ tracepoint 可用于建立运行时间线。

必背路径
--------

普通请求超时：

::

   初始化宿主请求对象
   → timer_setup 绑定回调
   → 提交设备请求
   → mod_timer 设置 jiffies 截止点
   → 设备完成时同步取消 timer
   或 timer 到期进入 softirq 回调
   → 回调原子地标记 timed_out
   → queue_work 执行可睡眠恢复
   → teardown 阻止重新 arm
   → 同步 timer 与 work
   → 最后释放请求对象

高精度定时器：

::

   选择合适 clock id 和绝对/相对模式
   → 初始化 hrtimer
   → hrtimer_start 按 ktime 入队
   → 若成为最早事件则重编程 clockevent
   → 硬件在目标时间触发中断
   → 时间路径处理到期 hrtimer
   → 执行短回调或延后处理
   → 周期任务 forward 到下一截止点

选择 timer 类型：

::

   判断时间误差是否影响正确性
   → 粗粒度超时优先普通 timer
   → 精细截止和唤醒考虑 hrtimer
   → 检查平台 high-res 能力
   → 检查回调上下文与生命周期
   → 评估中断频率、功耗与重编程成本

必须区分
--------

线程睡眠与 timer
   线程睡眠将当前 task 交给调度器；timer 将回调对象交给时间系统。

普通 timer 与 hrtimer
   普通 timer 强调低成本粗粒度超时；hrtimer 强调精确时间表达和最早到期排序。

逻辑到期与实际回调
   到期表示时间条件已满足；中断和执行延迟决定回调真正开始时间。

Clocksource 与 clockevents
   clocksource 读取现在；clockevents 安排未来中断。

取消 timer 与对象可释放
   还要同步正在执行的回调、已排队 work 和可能重新 arm 的路径。

一句话结论
----------

定时器是时间驱动的异步控制流：普通 timer 适合低成本超时，hrtimer 适合精细截止，而安全性取决于回调上下文和宿主对象 teardown 是否完整同步。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 11，Context Switching, Preemption, Timers, and Timekeeping；
* AIBook 章节：Chapter 53，Timer Infrastructure and High-Resolution Timers；
* 源文件：``docs/LinuxK/Part_11_Context_Switching_Preemption_Timers_and_Timekeeping/Chapter_053_Timer_Infrastructure_and_High_Resolution_Timers.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_11_Context_Switching_Preemption_Timers_and_Timekeeping/Chapter_053_Timer_Infrastructure_and_High_Resolution_Timers.md>`_。