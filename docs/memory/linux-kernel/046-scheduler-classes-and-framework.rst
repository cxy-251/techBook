第046章：调度类与调度框架
=========================

核心知识点
----------

调度器由核心框架与调度类共同组成
   核心框架维护 task 状态、每 CPU 运行队列和上下文切换；调度类负责不同策略下的入队、记账、抢占判断与选择规则。

调度策略决定 task 所属调度类
   ``SCHED_NORMAL`` 等普通策略进入公平类，``SCHED_FIFO`` 与 ``SCHED_RR`` 进入实时类，``SCHED_DEADLINE`` 进入 deadline 类。用户设置的是策略，内核执行的是对应 ``sched_class`` 的回调。

每个 CPU 都有独立运行队列
   ``struct rq`` 是单个 CPU 调度状态的根对象，保存当前 task、idle task、可运行数量、队列时钟，以及 fair、RT、deadline 等类的子队列。

可运行不等于正在运行
   runnable task 已具备获得 CPU 的资格，但可能仍在运行队列中等待；running task 才是当前 CPU 的实际执行者。

唤醒路径决定重新加入竞争的位置
   task 的等待条件满足后，唤醒路径会检查状态、选择合法 CPU、把 task 放入目标 ``rq``，并判断它是否应请求抢占当前 task。

调度选择依赖此前维护的队列状态
   权重、优先级、预算、虚拟时间和队列位置在唤醒、睡眠、tick、优先级变化等路径中持续更新。选择 next 时使用的是这些既有状态，不会重新扫描并计算全系统全部 task。

调度类具有优先顺序
   概念上的顺序是 stop、deadline、实时、公平和 idle。高层调度类存在可运行实体时，较低调度类通常不会在该 CPU 上被选择。

选择 task 与切换执行者是两个阶段
   ``pick_next_task`` 决定 next，``context_switch`` 才真正切换地址空间、内核栈和寄存器上下文。``need_resched`` 只记录重新调度需求，不表示切换已经发生。

关键路径
--------

task 被唤醒：

::

   等待条件满足
   → 检查 task 是否处于可唤醒状态
   → 在允许 CPU 集合中选择目标 CPU
   → 锁定目标 rq
   → 调用所属 sched_class 的 enqueue_task
   → 更新可运行统计与类内队列
   → 判断是否需要抢占当前 task
   → 在允许调度的边界进入调度器

CPU 选择下一个 task：

::

   schedule
   → __schedule 读取当前 CPU 的 rq
   → 处理 prev 的状态与队列关系
   → put_prev_task 结算前一个实体
   → 按调度类顺序寻找可运行实体
   → 得到 next
   → set_next_task 建立运行状态
   → context_switch 完成执行上下文切换

阅读调度问题：

::

   确认 task 的 policy 与 sched_class
   → 确认 task 是 runnable 还是 sleeping
   → 确认它位于哪个 CPU 的 rq
   → 检查类内优先级、权重、预算或队列位置
   → 找最近的 wakeup、dequeue、tick 或迁移事件
   → 再分析 pick_next_task 与 context_switch

概念辨析
--------

调度框架与调度策略
   框架负责统一状态和切换；调度类负责具体竞争规则。

可运行与正在运行
   runnable 表示有资格竞争 CPU；running 表示已经获得 CPU。

入队与上下文切换
   入队把 task 放入竞争集合；上下文切换才把 CPU 交给它。

重新调度请求与立即切换
   ``need_resched`` 表示应尽快重新选择；真正切换仍要等待合法调度边界。

每 CPU 队列与多核协调
   单次选择发生在本 CPU 的 ``rq``；迁移和负载均衡负责协调多个 ``rq``。

选择 next 与完成切换
   选择只确定候选执行者；架构相关上下文切换完成后，新 task 才真正运行。

本章结论
--------

Linux 调度器以每 CPU ``rq`` 保存运行状态，以 ``sched_class`` 实现不同策略；一次调度选择只是此前唤醒、入队、记账、迁移和抢占判断共同形成的结果。
