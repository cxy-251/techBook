第054章：时间维护、jiffies、Clocksource 与 Clockevents
====================================================

核心知识点
----------

时间读取与事件触发是两个问题
   内核既要回答当前时间是多少，也要安排未来何时产生执行入口。Clocksource 解决前者，clockevents 解决后者。

jiffies 提供低成本 tick 语义
   ``jiffies`` 是按 ``CONFIG_HZ`` 推进的传统时间刻度，适合粗粒度超时和热路径比较。其单位不是固定毫秒，必须根据目标内核的 ``HZ`` 解释。

jiffies 比较必须处理绕回
   有限宽度计数器会自然回绕，截止时间判断应使用 ``time_after()``、``time_before()`` 等宏，时间单位转换应使用标准 helper。

Clocksource 把硬件 cycle 转换成时间
   Clocksource 提供单调递增 counter；timekeeping 层利用 ``mask``、``mult`` 和 ``shift`` 处理绕回并转换为纳秒，再维护不同时间域的基准。

时间接口必须匹配时钟域
   Monotonic 适合间隔和超时，boottime 包含 suspend 时间，realtime 表示可被校正的墙钟时间，raw 更接近原始硬件速率。不同时间域不能混合相减或替代。

Clockevents 是可编程时间闹钟
   Clockevent 设备通过 periodic 或 one-shot 模式产生未来中断，为调度 tick、hrtimer 和 CPU 唤醒提供执行入口。精确读时钟本身不能唤醒 CPU。

高精度 timer 依赖 one-shot 能力
   时间系统根据最近截止事件编程本 CPU 的 clockevent。硬件中断到来后，内核才进入 tick 或 hrtimer 处理路径。

NO_HZ 减少无效周期 tick
   空闲 CPU 没有周期工作时，可以停止固定 tick，并只为最近必要事件设置 one-shot 中断。Tickless 表示减少无用周期事件，不表示系统不存在 timer 或时钟中断。

时间精度与交付延迟彼此独立
   Clocksource 可以准确记录时间，timer 仍可能因关中断、IRQ 拥塞、softirq 或调度等待而晚到。时间源错误和事件处理延迟必须分别判断。

时间选择是语义选择
   调用者必须先确定是否需要 UTC、是否允许时间跳变、是否包含 suspend、是否要求原始速率或低读取成本，再选择对应接口。

关键路径
--------

读取单调时间：

::

   调用 ktime_get 类接口
   → timekeeping 读取 clocksource cycle
   → 计算相对基准的 cycle 差值
   → 使用 mask 处理硬件 counter 绕回
   → 使用 mult / shift 转为纳秒
   → 应用 monotonic 时间域基准
   → 返回时间值

安排下一次时间事件：

::

   tick、timer 或 hrtimer 计算最近截止时间
   → clockevents 层选择本 CPU 事件设备
   → 把截止时间转换成硬件 delta
   → 编程 periodic 或 one-shot 事件
   → 硬件到期产生中断
   → event handler 进入时间处理路径
   → 处理到期对象并安排下一事件

空闲 CPU 进入 tickless：

::

   CPU 即将进入 idle
   → 判断是否仍需周期 tick
   → 计算最近 timer、hrtimer 与调度事件
   → 停止固定周期 tick
   → 用 one-shot clockevent 编程最近事件
   → CPU 休眠并由事件唤醒
   → 更新 timekeeping 与统计状态
   → 决定恢复周期 tick 或继续 tickless

概念辨析
--------

jiffies 与高分辨率时间
   ``jiffies`` 是低成本 tick 计数；``ktime_get*()`` 返回由 clocksource 支撑的高分辨率时间。

Clocksource 与 clockevents
   Clocksource 读取当前时间；clockevents 在未来时刻产生中断。

Monotonic 与 realtime
   Monotonic 适合计算间隔且不受普通墙钟修改影响；realtime 表示日历时间并可能跳变。

Monotonic 与 boottime
   Monotonic 通常不计 suspend 期间经过时间；boottime 把 suspend 包含在总时长中。

Tickless 与无定时事件
   Tickless 省去没有用途的固定 tick；最近 timer、调度事件和外部 IRQ 仍会唤醒 CPU。

时钟精度与 timer 延迟
   时间读取准确不代表回调准时执行，事件交付还受中断和执行路径约束。

本章结论
--------

Linux 用 clocksource 建立时间基准，用 clockevents 触发未来事件，用 jiffies 保留低成本 tick 语义，并通过 NO_HZ 在无周期工作时减少不必要的中断。