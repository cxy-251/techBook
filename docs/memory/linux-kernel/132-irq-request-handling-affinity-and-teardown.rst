第132章：IRQ 请求、处理、亲和性与退出
=====================================

核心知识点
----------

IRQ 路径包含三个层级
   设备产生事件、中断控制器投递和驱动确认事件是不同阶段。Linux IRQ number 只是内核映射编号，不等于硬件线、GSI、hwirq 或 MSI vector。

注册发布的是回调入口
   ``request_irq()`` 把 IRQ、handler、flags、name 和 ``dev_id`` 绑定为 ``irqaction``；``request_threaded_irq()`` 还可建立可睡眠的 IRQ thread。

初始化必须早于 unmask
   注册成功后中断可能立即到达，因此锁、状态、队列和 ``dev_id`` 宿主对象必须先就绪。常见顺序是保持设备侧 mask、清 pending、注册 handler，最后启用事件源。

Primary handler 不能睡眠
   硬中断上下文只适合快速确认归属、读取必要状态、mask/ack 设备事件并调度后续处理。

Threaded IRQ 承担可睡眠工作
   Primary handler 返回 ``IRQ_WAKE_THREAD`` 后，``thread_fn`` 在内核线程上下文运行。``IRQF_ONESHOT`` 可在 thread 执行期间保持对应 IRQ masked。

共享 IRQ 必须验证归属
   ``IRQF_SHARED`` 下，每个 handler 都要检查本设备 pending 状态。无条件返回 ``IRQ_HANDLED`` 会掩盖 spurious IRQ 和其它设备故障。

设备 ACK 与控制器 EOI 分离
   驱动负责清设备寄存器中的事件源；generic IRQ flow 和 irqchip 负责控制器侧 mask、ack、eoi 与路由。

触发类型决定清源协议
   水平触发在 pending 未清时会持续有效；边沿触发在 mask 期间若设备不锁存状态可能丢事件。驱动必须服从真实布线与 irqdomain 配置。

IRQ 通知不替代 DMA 可见性
   设备写 completion ring 后触发 IRQ，只说明通知到达。驱动仍需按 DMA API 与描述符协议保证数据和状态字段对 CPU 可见。

Affinity 是通知位置策略
   IRQ affinity 决定事件可投递到哪些 CPU，完整局部性还取决于硬件队列、NAPI/softirq、NUMA、应用线程和 buffer 位置。

多队列不要求一一映射
   IRQ vector、设备队列、软件队列和 CPU 数可以不同。多个队列共享 vector 或多个 CPU 共享队列都可能是正常设计。

Disable、Synchronize、Free 语义不同
   Disable 阻止后续投递，``synchronize_irq()`` 等待已进入的处理路径到达安全点，``free_irq()`` 撤销 action；三者都不会自动停止设备 DMA 或普通 work。

Managed IRQ 不自动正确退出
   ``devm_request_irq*()`` 只托管最终释放。若设备仍能触发或异步路径仍使用私有对象，自动 free 仍会形成 UAF。

Teardown 必须先停止事件源
   先设置 stopping、阻止新请求、在设备侧 mask IRQ 并确认生效，再停止 DMA/队列，然后同步 IRQ thread、NAPI、work、timer 和 tasklet。

关键路径
--------

IRQ 注册：

::

   固件/总线描述硬件中断
   → irqdomain 映射为 Linux IRQ
   → 初始化状态、锁和队列
   → 保持设备侧 mask 并清 pending
   → request_irq / request_threaded_irq
   → 建立 irqaction
   → 设备侧 unmask
   → 事件进入 handler

Threaded IRQ：

::

   设备触发事件
   → generic IRQ flow
   → primary handler 检查归属
   → mask/ack 必要状态
   → 返回 IRQ_WAKE_THREAD
   → IRQ thread 执行可睡眠处理
   → 更新队列与业务状态
   → 重新允许设备中断

安全退出：

::

   设置 stopping 并阻止新提交
   → 注销上层入口
   → 设备侧 mask IRQ 并 read-back
   → 停止 DMA、队列和事件源
   → synchronize_irq
   → cancel/flush NAPI、work、timer、tasklet
   → free_irq 或等待 devres
   → 释放 ring、MMIO 和私有对象

概念辨析
--------

* Linux IRQ 与 hardware IRQ：前者是内核抽象编号；后者属于中断控制器或总线语义。
* Device ACK 与 controller EOI：驱动清设备事件；irqchip 完成控制器协议。
* Primary handler 与 threaded handler：前者不可睡眠并快速确认；后者可睡眠并承担较长处理。
* Disable 与 synchronize：前者阻止新投递；后者等待已经进入的处理路径。
* Free IRQ 与停止设备：Free 只撤销 action；硬件必须先停止产生事件和 DMA。
* IRQ affinity 与完整局部性：Affinity 只选择通知 CPU，队列、NUMA 和业务线程仍需联合设计。

本章结论
--------

IRQ 正确性是一条从设备事件、控制器投递、归属确认到下半部和退出同步的闭环。安全 teardown 必须先让硬件不再产生事件，再等待所有软件路径结束。
