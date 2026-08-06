第054章：时间维护、jiffies、Clocksource 与 Clockevents
====================================================

本章必须记住
------------

#. 内核时间管理必须分开回答两个问题：当前时间是多少，未来事件何时触发。
#. Clocksource 负责读取时间线当前位置，clockevents 负责在未来指定时间产生事件中断。
#. ``jiffies`` 是传统 tick 视角下的全局时间刻度，单位由 ``CONFIG_HZ`` 决定。
#. ``HZ=250`` 时一个名义 tick 为 4ms；不同内核配置不能把同一 jiffies 数量直接当成固定毫秒数。
#. ``jiffies`` 适合粗粒度超时、热路径低成本比较和传统周期性维护。
#. ``jiffies`` 是有限宽度计数器，会发生绕回；比较先后必须使用 ``time_after()``、``time_before()`` 等宏。
#. 直接使用 ``jiffies > deadline`` 可能在绕回附近产生错误结论。
#. 毫秒和 jiffies 之间应使用 ``msecs_to_jiffies()``、``jiffies_to_msecs()`` 等 helper 转换。
#. Tick 中断传统上同时推进 jiffies、调度记账、进程时间统计、timer wheel 和系统维护。
#. ``jiffies`` 是 tick 处理的一个结果，不是高精度物理时钟本身。
#. Clocksource 抽象一个可读取、单调递增的硬件 counter，例如架构计数器、TSC 或 SoC counter。
#. Clocksource 的读取函数通常返回 cycle，timekeeping 层使用 ``mult``、``shift`` 和 ``mask`` 转换为纳秒时间。
#. ``mask`` 用于处理有限位宽硬件 counter 的自然绕回。
#. Clocksource 的 rating、稳定性、持续运行能力和读取成本影响内核选择哪个硬件时间源。
#. ``kernel/time/timekeeping.c`` 一类通用代码维护时间基准，并把硬件 cycle 转换为不同 clock domain。
#. ``ktime_get()`` 对应单调时间，适合测量运行期间的时间间隔，不受普通墙钟设置跳变影响。
#. ``ktime_get_boottime()`` 包含系统 suspend 时间，适合需要跨休眠统计经过时长的场景。
#. ``ktime_get_real()`` 表示墙钟/UTC 时间，可能受用户设置、NTP 和时间校正影响，不适合计算内部超时。
#. ``ktime_get_raw()`` 更接近原始硬件速率，通常不应用普通 NTP 频率校正。
#. 选择时间接口必须先决定是否允许跳变、是否包含 suspend、是否需要 UTC、是否只是测量短间隔。
#. ``sched_clock()`` 服务调度、trace 和日志等高频时间戳，不能无条件替代普通 ``ktime_get*()`` 接口。
#. Clockevents 是可编程的硬件时间闹钟，负责安排下一次 tick、hrtimer 或 CPU 唤醒事件。
#. Clockevent 设备可以支持 periodic 模式、one-shot 模式或二者之一，具体能力由平台硬件决定。
#. Periodic 模式以固定间隔产生 tick；one-shot 模式由内核为最近的下一事件单独编程。
#. High-resolution timer 和动态 tick 需要可用的 one-shot clockevent 支撑。
#. Clocksource 只负责读“现在”，即使非常精确，也不能自己在未来把 CPU 唤醒。
#. Clockevents 只负责发出事件，时间值和时钟域仍来自 timekeeping 与 clocksource。
#. NO_HZ_IDLE 允许空闲 CPU 停止固定周期 tick，减少功耗和不必要中断。
#. 空闲 CPU 停止 tick 后，内核仍通过 clocksource 读取当前时间，并用 clockevent 安排最近必要事件。
#. NO_HZ_FULL 可以减少指定运行 CPU 上的调度 tick，但需要满足任务数量、RCU、内务工作和配置条件。
#. Tickless 不等于没有 timer 中断；它表示没有工作时不保持固定周期 tick，最近事件仍会唤醒 CPU。
#. 停止周期 tick 后，内核必须在恢复时补齐时间与统计状态，不能简单停止时间推进。
#. NO_HZ 会降低周期性干扰，但增加 tick 停止、重启、CPU housekeeping 和远端维护复杂度。
#. ``CLOCK_MONOTONIC`` 不在 suspend 期间推进，``CLOCK_BOOTTIME`` 会包含 suspend；二者不能混用。
#. 墙钟时间可以向前或向后调整，绝对超时和时间戳协议必须明确时钟域。
#. 测量耗时时应在开始和结束使用同一种 clock accessor，不能混合 clock domain 相减。
#. 粗粒度 accessor 读取更快但精度更低，适合对精度不敏感的热路径。
#. 调试时间异常时，应记录当前 clocksource、clockevent、HZ、NO_HZ 配置、CPU 和 suspend 状态。
#. ``/sys/devices/system/clocksource/clocksource0`` 常可观察当前可用和选中的 clocksource，具体路径依赖系统。
#. Timer 晚到可能来自 clockevent、中断关闭、softirq、CPU 负载或回调排队，不能只归因于 clocksource 不准。
#. 时钟漂移、墙钟跳变、timer 延迟和调度延迟是不同问题，需要不同证据。

必背路径
--------

读取单调时间：

::

   调用 ktime_get 或相关 accessor
   → timekeeping 读取当前 clocksource cycle
   → 计算相对基准的 cycle delta
   → 使用 mask 处理 counter 绕回
   → 使用 mult / shift 转为纳秒
   → 应用对应 clock domain 语义
   → 返回稳定时间值

安排下一事件：

::

   timer、hrtimer 或 tick 计算最近截止时间
   → clockevents 层选择本 CPU 事件设备
   → 把截止时间转换为硬件 delta
   → 编程 one-shot 或 periodic 事件
   → 硬件到期产生中断
   → event handler 进入 tick / hrtimer 路径
   → 处理到期事件并安排下一事件

空闲 CPU 停止 tick：

::

   CPU 即将进入 idle
   → 判断近期是否需要周期 tick
   → 计算最近 timer、hrtimer 和调度事件
   → 停止 periodic tick
   → 用 one-shot clockevent 编程最近事件
   → CPU 休眠
   → 事件或 IRQ 唤醒 CPU
   → 更新 timekeeping 与统计
   → 恢复或继续保持 tickless

选择时钟接口：

::

   是否需要 UTC 墙钟
   → 是否允许时间跳变
   → 是否需要包含 suspend
   → 是否需要原始硬件速率
   → 是否处于极热读取路径
   → 选择 real、monotonic、boottime、raw 或 coarse 接口

必须区分
--------

* ``jiffies`` 与高精度时间：``jiffies`` 是 tick 单位的粗粒度计数；``ktime_get*`` 返回由 clocksource 支撑的高分辨率时间。
* Clocksource 与 clockevents：Clocksource 读取现在；clockevents 安排未来中断。
* Monotonic 与 realtime：Monotonic 适合间隔和超时；realtime 适合日历时间并可能跳变。
* Monotonic 与 boottime：Monotonic 通常排除 suspend；boottime 包含 suspend 经过时间。
* Tickless 与无定时事件：Tickless 省去无用周期 tick，必要的 timer 和 IRQ 仍会发生。
* 时钟精度与事件交付延迟：时间源可以准确，但关中断和执行拥塞仍会让回调晚到。

一句话结论
----------

Linux 用 clocksource 测量时间、用 clockevents 安排未来中断、用 jiffies 保留低成本 tick 语义，并通过 NO_HZ 在没有周期工作时减少无用 tick。
