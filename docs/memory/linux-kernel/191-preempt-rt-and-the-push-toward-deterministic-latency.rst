第191章：PREEMPT_RT 与确定性延迟
================================

核心知识点
----------

确定性延迟关注最坏情况
   PREEMPT_RT 的目标是缩短并约束高优先级任务的最大等待时间。平均延迟和平均吞吐不能证明实时任务满足 Deadline。

延迟必须分解到具体阶段
   一次事件响应包含中断到达、事件处理、任务唤醒、Runqueue 等待、锁等待、上下文切换和任务执行。只有找到最早不能继续推进的阶段，才能定位根因。

PREEMPT_RT 改变中断与锁的执行语义
   设备中断主体尽量在线程化 IRQ 中运行，普通 ``spinlock_t`` 在 RT 配置下可具有睡眠与优先级继承语义，从而减少长 Hardirq 和不可抢占区间。

低级原子路径仍不可抢占
   NMI、部分架构路径、``raw_spinlock_t``、IRQ-off 和 Preempt-off 区间仍会阻止高优先级任务运行。实时内核并不意味着所有代码都可抢占。

优先级继承只解决锁反转
   ``rt_mutex`` 可临时提升锁持有者优先级，缩短受支持锁上的优先级反转。它不能消除 Raw Lock、Firmware、设备等待和过长算法路径。

优先级必须按依赖关系设计
   实时任务、IRQ Thread、Worker 和控制线程的优先级应匹配真实生产者—消费者关系。业务线程高于其依赖的 IRQ Thread，可能反而阻塞数据到达。

实时性必须以目标环境验证
   ``cyclictest``、调度 Tracepoint、IRQ Trace 和延迟 Tracer 应在目标硬件、Firmware、驱动和真实压力下联合使用，并记录最大值、直方图、运行时长和负载条件。

关键路径
--------

实时任务唤醒：

::

   Timer / Device Event
   → Hardirq 最小处理
   → IRQ Thread 或 Timer Path
   → 唤醒实时任务
   → 进入 Runqueue
   → 检查 IRQ-off / Preempt-off / Lock / 更高优先级实体
   → sched_switch
   → 实时任务执行

延迟调查：

::

   发现最大延迟样本
   → 对齐 sched_wakeup 与 sched_switch
   → 检查 Hardirq、Threaded IRQ 和 Softirq
   → 检查 Raw Lock 与不可抢占区间
   → 检查 rt_mutex 与 PI 链
   → 定位最早阻塞点
   → 修改后在相同条件复测

概念辨析
--------

* **平均延迟与最坏延迟**：平均值描述总体水平；实时合同由最大值、长尾和 Deadline Miss 决定。
* **高调度优先级与立即运行**：高优先级只在可调度点获得选择权，不能穿透 Hardirq、Raw Lock 和不可抢占区间。
* **Threaded IRQ 与 Hardirq Primary Handler**：Primary Handler 只完成最小确认和唤醒；设备主体工作在线程上下文执行。
* **``spinlock_t`` 与 ``raw_spinlock_t``**：前者在 RT 下可转换为支持 PI 的锁；后者始终保持严格原子语义。
* **Priority Inheritance 与全部延迟消除**：PI 只处理支持锁上的优先级反转，不能解决设备、Firmware 和长执行路径。
* **CPU Isolation 与完全无干扰**：Isolation 减少调度、Tick、IRQ 和 RCU 干扰，NMI、SMI 和硬件事件仍可能发生。

本章结论
--------

PREEMPT_RT 通过线程化中断、缩短不可抢占区间和优先级继承，把实时任务的等待路径变成可分解、可追踪和可验证的最坏延迟问题。