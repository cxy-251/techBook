第132章：IRQ 请求、处理、亲和性与退出
=====================================

本章必须记住
------------

#. IRQ 路径把硬件事件转换成内核回调，但“设备产生事件”“中断控制器投递”“驱动确认事件”是三个不同阶段。
#. 驱动通常从 platform resource、PCI MSI/MSI-X、ACPI/DT 或子系统接口取得 Linux IRQ number。
#. Linux IRQ number 是内核抽象编号，不等于硬件中断线、GSI、MSI vector 或控制器 hwirq。
#. ``request_irq()`` 把 IRQ、primary handler、flags、name 和 ``dev_id`` 绑定成一个 ``irqaction``。
#. ``request_threaded_irq()`` 额外提供 ``thread_fn``，把可睡眠或耗时工作放入 IRQ thread。
#. ``devm_request_irq*()`` 只托管 action 的释放，不会自动停止设备中断源或排空异步工作。
#. Handler 的 ``dev_id`` 应唯一对应设备实例；共享 IRQ 的 ``free_irq()`` 也靠它删除正确 action。
#. ``request_irq`` 成功后硬件可能立即产生中断，因此设备状态、锁和 handler 所需对象必须已初始化。
#. 常见安全顺序是：先建立 handler 与软件状态，再清 pending，最后在设备侧 unmask/enable 中断。
#. 若设备在申请 IRQ 前已经能触发，必须先保持设备侧中断屏蔽，避免 handler 访问半初始化对象。
#. Primary handler 在硬中断上下文运行，不能睡眠，不能获取可能睡眠的 mutex，也不能执行阻塞 I/O。
#. Handler 应快速读取必要状态、确认归属、mask/ack 事件并安排后续处理。
#. ``IRQ_NONE`` 表示事件不属于当前 action；``IRQ_HANDLED`` 表示本 action 已处理。
#. ``IRQ_WAKE_THREAD`` 表示 primary handler 已确认事件归属，并请求运行 ``thread_fn``。
#. Threaded handler 在内核线程上下文运行，可以睡眠，但仍必须遵守设备状态、锁和 teardown 协议。
#. ``IRQF_ONESHOT`` 常用于 threaded IRQ，使 thread 处理期间对应 IRQ 保持 mask，避免重复进入。
#. Oneshot 不是所有设备的通用答案；若 primary handler 已能彻底清源和重新 arm，具体策略可不同。
#. 共享 IRQ 需要 ``IRQF_SHARED``，并要求每个 handler 先检查本设备 pending 状态。
#. Shared handler 不能无条件返回 ``IRQ_HANDLED``，否则会掩盖 spurious interrupt 和其它设备故障。
#. MSI/MSI-X 通常不采用传统共享线语义，但一个 vector 内仍可能汇总多个设备内部事件源。
#. 边沿触发记录状态变化；水平触发在设备保持有效电平时会持续成立。
#. 水平触发路径中，若设备 pending 未清就 unmask，IRQ 会立即再次触发并形成风暴。
#. 边沿触发路径中，若在 mask 期间没有可靠设备状态锁存，可能丢失后续边沿。
#. 触发类型通常应来自固件、irqdomain 或总线配置，驱动不应与真实布线冲突。
#. 设备侧 ACK 与中断控制器 ACK/EOI 必须区分。
#. 驱动处理设备寄存器 pending/status；generic IRQ flow 与 irqchip 处理 mask、ack、eoi 和路由。
#. 读取状态寄存器可能 clear-on-read；写状态寄存器可能是 W1C，必须按设备手册设计 handler。
#. Handler 中清中断的顺序必须与读取完成队列、DMA 可见性和重新开中断相匹配。
#. 设备写 completion ring 后触发 IRQ 时，驱动还需使用 DMA API/屏障保证 CPU 能看到完成数据。
#. IRQ 到达只证明设备发出通知，不自动证明所有 DMA 数据已按 CPU 需要的顺序可见。
#. 中断风暴可能来自 pending 未清、触发类型错误、设备 reset、共享 handler 误判或硬件持续报错。
#. IRQ affinity 指定某个 IRQ 可投递到哪些 CPU，最终受在线 CPU、中断控制器和系统策略限制。
#. ``/proc/interrupts`` 显示各 CPU 计数；``/proc/irq/<n>/smp_affinity*`` 显示或设置 affinity。
#. Affinity hint 是调度建议，不保证用户空间 irqbalance 或平台一定维持该分布。
#. 多队列设备常尝试建立 queue → MSI-X vector → CPU 的局部关系。
#. IRQ 数、硬件队列数、软件队列数和 CPU 数不必一一相等。
#. 好的 affinity 需要同时考虑提交 CPU、completion CPU、NUMA、cache、NAPI/softirq 和业务线程位置。
#. 把所有 vector 固定到同一 CPU 会形成热点；过度分散也会增加跨 NUMA 和共享状态成本。
#. CPU hotplug 会改变可用 affinity，驱动和子系统必须允许 IRQ 重新路由。
#. 禁用 IRQ 有同步和非同步语义，不能只从函数名推断 handler 已全部退出。
#. ``disable_irq()`` 通常等待正在执行的 handler 结束，并增加 disable depth；调用上下文需允许等待。
#. ``disable_irq_nosync()`` 不等待当前 handler，调用者必须另行保证并发安全。
#. ``synchronize_irq()`` 等待指定 IRQ 上正在执行的 action/线程到达安全边界，精确语义依 IRQ 类型与版本。
#. ``free_irq()`` 删除 action，并需要处理正在执行的 handler；共享 IRQ 只移除匹配 ``dev_id`` 的 action。
#. 仅 ``free_irq`` 不足以安全移除设备，因为硬件可能在 action 删除后继续触发该中断。
#. 安全 teardown 的第一步是设置 stopping/disconnected，阻止新业务请求和重新使能中断。
#. 然后在设备侧 mask 中断源，并通过 read-back 或设备规定方式确认 mask 已生效。
#. 若 IRQ 由 DMA completion 产生，还应停止新 DMA、等待设备不再写 ring/buffer。
#. 之后调用 ``synchronize_irq()`` 或等价同步，确认 handler/thread 不再访问私有对象。
#. Handler 可能安排 tasklet、workqueue、NAPI、timer 或唤醒等待者，这些后续路径也必须分别取消或排空。
#. ``synchronize_irq()`` 不会自动等待普通 work、timer、RCU reader、用户 fd 或设备 DMA。
#. Managed IRQ 在 devres 释放时调用 free，但若驱动未提前停止硬件，仍可能发生 use-after-free。
#. Remove 与 suspend 的目标不同：remove 永久撤销对象，suspend 需要保留可恢复状态。
#. Suspend 期间可以暂时禁用 IRQ；resume 必须按设备状态恢复、清 pending、再 unmask。
#. Wake IRQ 是系统睡眠中的特殊事件源，与运行期数据 IRQ 的 enable/affinity 规则可能不同。
#. IRQ handler 不能假设设备一直存在；热拔插和 reset 路径应检查 generation/stopping 状态。
#. Reset 后旧 IRQ 或旧 completion 可能迟到，驱动应防止它命中新队列对象。
#. 统计 IRQ 次数只能证明入口发生，不能证明 handler 做了有效工作或 completion 被业务消费。
#. ``/proc/interrupts`` 中计数不增长时，应先查设备侧 enable、pending、MSI/BAR、irqdomain 和 affinity。
#. 计数增长但业务不前进时，应查 handler 返回、ACK、DMA 可见性、下半部和队列状态。
#. Spurious IRQ 诊断需要对齐共享 action、触发类型、设备 pending 和控制器状态。
#. Tracepoint、ftrace、perf 和 eBPF 可观测 IRQ entry/exit、handler 时长和 CPU 分布，事件名依版本。
#. 长 handler 会延迟同 CPU 上其它 IRQ 和调度；应把可延后工作移到 threaded IRQ、NAPI 或 workqueue。
#. 盲目把所有工作线程化会增加调度延迟和上下文切换，仍需按事件频率和实时约束评估。
#. 精确 ``irq_desc``、flow handler、irqchip 回调和线程同步实现具有架构与版本差异。
#. 稳定源码阅读顺序是：IRQ 来源 → request 参数 → handler 归属/ACK → 下半部 → affinity → disable/sync/free → 后续异步收束。

必背路径
--------

IRQ 注册：

::

   总线/固件解析硬件中断
   → irqdomain 映射为 Linux IRQ
   → 初始化设备状态与锁
   → 清旧 pending 并保持设备侧 mask
   → request_irq / request_threaded_irq
   → 建立 irqaction
   → 设备侧 unmask/enable
   → 硬件事件可进入 handler

Threaded IRQ：

::

   设备触发 IRQ
   → generic IRQ flow
   → primary handler 检查本设备 pending
   → mask / ack 必要状态
   → 返回 IRQ_WAKE_THREAD
   → IRQ thread 执行可睡眠处理
   → 更新队列和业务状态
   → 重新允许设备中断

多队列 Affinity：

::

   分配 MSI-X vectors
   → 每个 vector 绑定队列或队列组
   → 设置允许 CPU mask
   → 设备 completion 触发对应 vector
   → 目标 CPU 运行 handler/NAPI
   → 本地消费队列和唤醒业务
   → 用 /proc/interrupts 验证实际分布

安全 Teardown：

::

   设置 stopping 并阻止新提交
   → 注销上层入口
   → 设备侧 mask IRQ 并 read-back
   → 停止 DMA / 队列 / 事件源
   → synchronize_irq
   → cancel/flush NAPI、work、timer、tasklet
   → free_irq 或等待 devres 释放
   → 释放 ring、MMIO 和私有对象

必须区分
--------

* Linux IRQ 与 Hardware IRQ：Linux IRQ 是内核映射编号；hwirq/vector/中断线属于控制器或总线语义。
* 设备 ACK 与 Controller EOI：驱动清设备事件源；irqchip/flow handler 完成控制器侧协议。
* Primary Handler 与 Threaded Handler：Primary 在硬中断上下文快速确认事件；thread 可睡眠并执行较长处理。
* Disable 与 Synchronize：Disable 阻止后续投递；synchronize 等待已经进入的处理路径到达安全终点。
* Free IRQ 与停止设备：Free 撤销内核 action；设备侧仍必须先停止产生事件和 DMA。
* IRQ Affinity 与业务局部性：Affinity 决定通知 CPU；完整局部性还取决于队列、软中断、NUMA 和应用线程。

一句话结论
----------

IRQ 正确性不止是注册 handler，而是让设备事件、控制器投递、归属确认、下半部和退出同步形成闭合状态机；teardown 必须先让硬件沉默，再等待所有软件路径结束。
