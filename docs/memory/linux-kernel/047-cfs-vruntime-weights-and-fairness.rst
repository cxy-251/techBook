第047章：CFS、vruntime、权重与公平性
====================================

核心知识点
----------

公平调度围绕 sched_entity 与 cfs_rq 工作
   普通 task 通过内嵌的 ``sched_entity`` 参与公平调度，``cfs_rq`` 保存同一竞争层级中的公平类实体及其运行状态。

实际运行时间与虚拟运行时间承担不同职责
   ``sum_exec_runtime`` 记录实体真正使用的 CPU 时间，``vruntime`` 把实际时间按权重归一化，用于比较不同权重实体已经获得的相对 CPU 份额。

权重决定虚拟时间增长速度
   经典近似关系为 ``delta_vruntime = delta_exec * NICE_0_LOAD / weight``。权重越大，同样运行时间产生的 ``vruntime`` 增量越小，长期获得的 CPU 份额越大。

nice 是普通任务权重的用户接口
   nice 值越低，调度权重越大；nice 值越高，权重越小。nice 只影响公平类内部份额，不能压过实时类或 deadline 类任务。

公平性是相对且长期的
   多个持续 runnable 的实体，长期 CPU 份额近似按自身权重占总权重的比例分配。短时间窗口仍会受唤醒、粒度、迁移和缓存局部性影响。

min_vruntime 提供队列内比较基准
   ``cfs_rq->min_vruntime`` 随队列执行向前推进，使新实体、唤醒实体和已有实体能够在同一虚拟时间语境中比较。

现代公平选择使用 EEVDF 思路
   ``vruntime`` 和权重继续承担公平记账，选择阶段还会考虑 eligibility、lag、slice 和 virtual deadline。当前实现不能简单概括为“永远选择最小 vruntime”。

组调度形成层级公平
   启用 cgroup CPU 组调度后，task 先在组内竞争，组实体再与其它组竞争。task nice 与 cgroup weight 位于不同层级，最终份额由整棵层级共同决定。

关键路径
--------

公平类运行记账：

::

   sched_entity 获得 CPU
   → 运行 delta_exec
   → update_curr 结算实际运行时间
   → 按 weight 折算 delta_vruntime
   → 更新 sum_exec_runtime 与 vruntime
   → 更新队列基准、lag 和 deadline 状态
   → 下一次调度重新比较实体

长期 CPU 份额形成：

::

   nice 映射为 weight
   → runnable 实体形成当前总权重
   → weight 大的实体 vruntime 增长较慢
   → weight 小的实体 vruntime 增长较快
   → 调度器持续纠正相对运行差额
   → 长期结果接近权重比例

现代公平类选择：

::

   更新当前实体记账
   → 推进 cfs_rq 虚拟时间基准
   → 判断候选实体是否 eligible
   → 比较 lag 与 virtual deadline
   → 选择下一个公平类实体
   → 结果仍受更高调度类和 CPU 放置约束

排查公平性异常：

::

   确认 task 属于 fair class
   → 确认它是否持续 runnable
   → 检查 nice 与实体权重
   → 检查 cgroup weight、quota 与层级
   → 检查 affinity 和实际运行 CPU
   → 比较运行时间与队列等待时间
   → 用 sched 事件验证唤醒、切入与迁移

概念辨析
--------

实际运行时间与 vruntime
   实际运行时间表示真正占用 CPU 的时间；``vruntime`` 是按权重归一化后的公平账本。

nice 与实时优先级
   nice 调整普通任务份额；实时优先级属于更高调度类的固定优先级规则。

长期公平与短期延迟
   权重比例描述长期趋势；一次唤醒多久上 CPU 还受抢占、队列和拓扑影响。

经典 CFS 与现代 EEVDF
   经典模型强调较小 ``vruntime``；现代实现保留虚拟时间记账，并加入资格与虚拟截止时间选择。

task 权重与 cgroup 权重
   task 权重作用于组内竞争；cgroup 权重作用于组之间的层级竞争。

睡眠与 CPU 份额
   睡眠实体不消耗 CPU；唤醒放置规则决定它重新进入公平竞争时的位置。

本章结论
--------

公平调度通过权重和虚拟时间记录“每个实体相对已经获得多少 CPU”，再用 eligibility 与虚拟截止时间决定当前最应运行的实体。
