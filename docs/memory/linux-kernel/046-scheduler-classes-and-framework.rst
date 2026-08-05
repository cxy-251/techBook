第046章：调度类与调度框架
=========================

本章必须记住
------------

#. Linux 调度器由统一核心框架和多个调度类组成；核心框架管理 task 状态、每 CPU 运行队列与上下文切换，调度类实现具体策略。
#. 用户态设置的是 ``SCHED_NORMAL``、``SCHED_FIFO``、``SCHED_RR``、``SCHED_DEADLINE`` 等策略；内核把 task 映射到对应的 ``sched_class``。
#. ``struct sched_class`` 是调度策略操作表，包含入队、出队、唤醒抢占、选择任务、tick 记账、fork 和退出等回调。
#. 调度类不只在 ``pick_next_task`` 时工作；task 的唤醒、睡眠、创建、退出、优先级变化和周期 tick 都会更新后续选择所依赖的状态。
#. 调度类概念上的优先顺序是内部 stop 类、deadline 类、实时类、公平类、idle 类；配置启用的扩展调度类会插入相应框架位置。
#. 高优先级调度类中存在可运行 task 时，低优先级调度类通常不会获得该 CPU。
#. 每个 CPU 都有自己的 ``struct rq``，它是该 CPU 调度状态的根对象。
#. ``rq`` 保存当前 task、idle task、可运行数量、运行队列时钟以及 fair、RT、deadline 等类的子队列。
#. 普通任务进入 ``cfs_rq``，固定优先级实时任务进入 ``rt_rq``，deadline 任务进入 ``dl_rq``。
#. 调度选择首先是每 CPU 决策；跨 CPU 的放置、迁移和负载均衡再把多个 ``rq`` 连接起来。
#. task 的“可运行”状态不等于它正在 CPU 上执行；可运行 task 可能正在对应 ``rq`` 中等待。
#. task 进入睡眠前要从可运行队列移除；条件满足后，唤醒路径再把它放回某个合法 CPU 的队列。
#. ``try_to_wake_up()`` 是常见唤醒入口之一，它负责状态检查、目标 CPU 选择、入队和必要的抢占判断。
#. 一个简化唤醒路径是：睡眠 task → 条件满足 → 选择目标 CPU → 调用所属调度类入队 → 检查是否应抢占当前 task。
#. ``schedule()`` 是主动进入调度器的公开入口之一，核心工作最终落到 ``__schedule()`` 一类内部路径。
#. 调度核心在切换前处理前一个 task 的状态和队列关系，再从当前 CPU 的 ``rq`` 选择下一个 task。
#. ``pick_next_task()`` 使用已经维护好的调度类顺序和类内队列，不会在此刻重新计算全系统所有 task 的完整排序。
#. ``put_prev_task`` 用于让调度类结算前一个 task，``set_next_task`` 用于让调度类建立下一个 task 的运行状态。
#. 真正的 ``context_switch`` 保存前一个 task 的执行上下文，切换地址空间与内核栈，并恢复下一个 task。
#. “选择了 next”与“已经完成上下文切换”是两个步骤；中间还存在锁、状态更新和架构切换工作。
#. tick 可以更新当前 task 的运行时间、预算或时间片，并在需要时设置重新调度标志。
#. 唤醒路径可以设置抢占请求；实际切换通常发生在允许调度的边界。
#. ``need_resched`` 表示当前 CPU 应在合适位置重新进入调度器，不表示 CPU 已经立即切换 task。
#. task 的调度策略、优先级、CPU 亲和性和 cgroup 约束共同决定它能进入哪些队列以及如何竞争。
#. runqueue 锁保护同一 CPU 的调度状态；跨 CPU 唤醒和迁移需要遵守多个 ``rq`` 的锁顺序。
#. 调度器源码必须按状态转换阅读：先看 task 如何变为 runnable，再看如何入队，最后看何时触发选择和切换。
#. 只从 ``schedule()`` 向下阅读会漏掉大量决定，因为权重、优先级、预算和队列位置早已在其它路径中维护。

必背路径
--------

task 被唤醒：

::

   等待条件满足
   → 唤醒方找到目标 task
   → 检查 task 是否仍处于可唤醒状态
   → 在允许 CPU 集合中选择目标 CPU
   → 锁定目标 rq
   → 调用所属 sched_class 的 enqueue_task
   → 更新 runnable 与队列统计
   → 检查是否应抢占当前 task
   → 在合适边界发生重新调度

CPU 选择下一个 task：

::

   当前路径调用 schedule
   → __schedule 读取当前 CPU rq
   → 处理 prev 的睡眠、出队或继续可运行状态
   → 调用 put_prev_task 结算前一个实体
   → 按调度类优先顺序查询可运行实体
   → 得到 next task
   → 调用 set_next_task 建立运行状态
   → context_switch 切换执行上下文
   → 新 task 从调度点继续运行

阅读一个调度问题：

::

   确认目标 task 的 policy 与 sched_class
   → 确认它是否 runnable
   → 确认它位于哪个 CPU 的 rq
   → 确认类内队列位置、优先级或预算
   → 找到最近的 wakeup、dequeue、tick 或优先级变化
   → 再分析 pick_next_task 与 context_switch

必须区分
--------

调度框架与调度策略
   核心框架负责统一状态与切换；调度类负责不同策略的队列和选择规则。

可运行与正在运行
   runnable task 有资格获得 CPU；running task 正在某个 CPU 上执行。

入队与切换
   入队让 task 进入竞争集合；上下文切换才真正把 CPU 交给它。

重新调度请求与立即切换
   ``need_resched`` 记录调度需求；切换要等到允许调度的执行边界。

每 CPU 队列与全局调度
   每次选择基于本 CPU ``rq``；多核迁移和负载均衡在此基础上协调多个队列。

选择 next 与完成切换
   ``pick_next_task`` 决定候选；``context_switch`` 才改变实际执行者。

一句话结论
----------

Linux 调度器以每 CPU ``rq`` 保存状态，以 ``sched_class`` 实现策略；最终选择只是前面一系列唤醒、入队、记账和状态转换的结果。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 10，Scheduler Architecture, CFS, Real-Time Classes, and CPU Time；
* AIBook 章节：Chapter 46，Scheduler Classes and the Scheduling Framework；
* 源文件：``docs/LinuxK/Part_10_Scheduler_Architecture_CFS_Real_Time_Classes_and_CPU_Time/Chapter_046_Scheduler_Classes_and_the_Scheduling_Framework.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_10_Scheduler_Architecture_CFS_Real_Time_Classes_and_CPU_Time/Chapter_046_Scheduler_Classes_and_the_Scheduling_Framework.md>`_。