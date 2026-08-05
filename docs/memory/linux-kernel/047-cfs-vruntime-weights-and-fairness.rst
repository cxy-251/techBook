第047章：CFS、vruntime、权重与公平性
====================================

本章必须记住
------------

#. Linux 公平调度类服务普通任务，核心对象是 ``sched_entity``、``cfs_rq``、权重和虚拟时间记账。
#. 公平调度不是简单平均分配 CPU；它根据当前可运行集合、实体权重和历史 CPU 消耗计算相对份额。
#. 普通 task 在 ``task_struct`` 中内嵌 ``struct sched_entity``，组调度也可以用调度实体代表一个任务组。
#. ``sum_exec_runtime`` 记录实体实际获得的 CPU 运行时间，``vruntime`` 记录按权重归一化后的虚拟运行时间。
#. 经典近似关系是 ``delta_vruntime = delta_exec * NICE_0_LOAD / weight``。
#. 权重越大，同样实际运行时间带来的 ``vruntime`` 增量越小，实体长期获得的 CPU 份额越大。
#. 权重越小，``vruntime`` 增长越快，实体会更快消耗自己的公平份额。
#. nice 值是用户态调整普通任务相对 CPU 份额的接口，调度器内部把 nice 映射为权重。
#. nice 值越低，权重越大；nice 值越高，权重越小。
#. nice 0 使用基准权重 ``NICE_0_LOAD``；在常见主线实现中该基准值为 1024。
#. 多个持续可运行普通实体的长期份额近似按各自权重占总权重的比例分配。
#. 份额关系只对同一竞争层级中的可运行实体成立；睡眠实体、其它 CPU 上的实体和更高调度类任务不在同一直接比较集合中。
#. task 睡眠时暂时离开运行队列，不再消耗 CPU，也不会继续增加 ``vruntime``。
#. task 被唤醒时需要放置到合理的虚拟时间位置，既避免永久落后，也避免通过长时间睡眠取得无限不公平优势。
#. ``cfs_rq->min_vruntime`` 为当前公平队列提供推进中的虚拟时间基准，帮助新实体和唤醒实体保持可比较位置。
#. 经典 CFS 模型倾向于选择相对较小 ``vruntime`` 的实体，因为它相对自己的权重获得了较少 CPU。
#. 现代主线公平类已经引入 EEVDF 选择逻辑；``vruntime`` 和权重仍负责公平记账，具体选择还会考虑 eligibility、lag、slice 和 virtual deadline。
#. 因此不能把所有当前内核版本的公平选择无条件简化成“永远取红黑树中最小 vruntime”。
#. EEVDF 的稳定读法是：先判断实体是否有资格运行，再在有资格实体中倾向选择虚拟截止时间更早者。
#. ``vruntime`` 是相对公平标尺，不是墙钟时间，也不是任务下次一定运行的绝对时间。
#. ``min_vruntime`` 是队列内部基准，不是系统全局统一时间。
#. 任务刚刚运行后会增加实际运行时间和虚拟运行时间；其公平位置随记账向后推进。
#. 当前实体运行期间，``update_curr()`` 一类路径负责结算实际执行时间并更新公平类状态。
#. ``calc_delta_fair()`` 一类逻辑按权重把实际时间折算为虚拟时间；精确函数和内部结构会随版本演进。
#. 公平性是长期目标，不保证每个极短时间窗口内所有任务获得完全相同或精确比例的 CPU。
#. 调度粒度、唤醒抢占、CPU 数量、迁移、缓存局部性和睡眠行为会影响短期延迟。
#. 开启 cgroup CPU 组调度后，公平竞争具有层级性：任务先在组内竞争，组实体再和其它组竞争。
#. cgroup 权重和 task nice 属于不同层级的份额控制，最终结果由层级权重共同决定。
#. ``SCHED_IDLE`` 策略和 nice 19 不是同一个含义；前者属于更弱的普通策略语义，不能只按 nice 权重解释。
#. nice 只影响普通公平类内部相对份额，不能压过 ``SCHED_FIFO``、``SCHED_RR`` 或 ``SCHED_DEADLINE``。
#. 排查普通任务 CPU 份额时，应同时观察 runnable 时间、实际运行时间、队列等待、nice、cgroup 权重和 CPU 亲和性。

必背路径
--------

公平类运行记账：

::

   普通 task 被调度到 CPU
   → sched_entity 成为当前实体
   → 运行一段 delta_exec
   → update_curr 结算实际运行时间
   → 按 weight 计算 delta_vruntime
   → 更新 sum_exec_runtime 和 vruntime
   → 更新队列基准、lag 或 deadline 状态
   → 在下一次调度中重新比较

普通任务的长期份额：

::

   nice 值映射为 weight
   → 所有持续 runnable 实体形成总权重
   → 每个实体按自身权重取得近似比例
   → weight 大的实体 vruntime 增长较慢
   → weight 小的实体 vruntime 增长较快
   → 长期运行逐步接近权重比例

现代公平类选择：

::

   更新当前实体运行记账
   → 维护 cfs_rq 的虚拟时间基准
   → 判断候选实体的 eligibility 与 lag
   → 比较虚拟 deadline 等选择键
   → 选择下一个公平类实体
   → 实际结果仍受更高调度类和 CPU placement 约束

排查公平性异常：

::

   确认任务属于 fair class
   → 确认任务是否持续 runnable
   → 读取 nice 与调度权重
   → 检查 cgroup CPU weight 和 quota
   → 检查 affinity 与实际运行 CPU
   → 比较运行时间和 runqueue 等待时间
   → 结合 sched trace 验证唤醒与切入时间

必须区分
--------

实际运行时间与 ``vruntime``
   实际运行时间是 task 真正占用 CPU 的时间；``vruntime`` 是按权重归一化后的公平记账。

nice 与实时优先级
   nice 只调整公平类份额；实时优先级属于更高调度类的固定优先级规则。

长期公平与短期延迟
   权重比例描述长期趋势；一次唤醒能否迅速上 CPU 还受队列、抢占和拓扑影响。

经典 CFS 选择与现代 EEVDF
   经典模型强调较小 ``vruntime``；现代主线在保留虚拟时间记账的同时使用 eligibility 和虚拟 deadline。

单 task 权重与 cgroup 组权重
   task 权重控制组内实体关系；组权重控制不同 cgroup 之间的层级份额。

睡眠时间与 CPU 消耗
   睡眠任务不占 CPU；唤醒放置规则决定它重新加入竞争时的位置。

一句话结论
----------

公平调度通过权重和虚拟时间连续记录“谁已经获得多少 CPU”；现代实现再用 eligibility 与虚拟 deadline 决定当前应运行的实体。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 10，Scheduler Architecture, CFS, Real-Time Classes, and CPU Time；
* AIBook 章节：Chapter 47，CFS, vruntime, Weights, and Fairness；
* 源文件：``docs/LinuxK/Part_10_Scheduler_Architecture_CFS_Real_Time_Classes_and_CPU_Time/Chapter_047_CFS_vruntime_Weights_and_Fairness.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_10_Scheduler_Architecture_CFS_Real_Time_Classes_and_CPU_Time/Chapter_047_CFS_vruntime_Weights_and_Fairness.md>`_。