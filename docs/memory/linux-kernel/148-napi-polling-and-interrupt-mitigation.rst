第148章：NAPI Polling 与中断缓解
================================

核心知识点
----------

NAPI 把中断发现与批量处理分离
   IRQ 只负责确认事件并调度 ``struct napi_struct``；真正的 RX/TX Completion 处理在受 Budget 限制的 Poll 中完成。

NAPI Instance 是调度单位
   一个接口可有多个 NAPI，一个 NAPI 可服务一个 Queue Pair 或一组事件。IRQ Vector、硬件 Queue 与 NAPI 不要求一一对应。

注册与启用是两个阶段
   驱动在 Probe/Open 中注册 Poll 回调，并在数据面可用后 ``napi_enable()``。``napi_disable()`` 收束 Poll，但不会停止设备 IRQ 或 DMA。

Schedule 只发布未来工作
   ``napi_schedule()`` 不在调用点完成 Ring 清理。核心状态位保证同一 NAPI 不被并发重复执行，并合并重复事件。

Poll 受局部与全局预算约束
   驱动 ``poll(napi, budget)`` 通常清理 TX Completion，并处理最多 Budget 个 RX Packet。系统还受全局 Packet Budget 与时间窗口限制。

Budget 用尽表示继续调度
   若 Ring 仍有工作，Poll 返回 Budget，NAPI 保持 Scheduled。Budget 是 Packet 工作量边界，不是 Ring Size 或字节数。

完成条件必须准确
   Ring 已空且 ``work_done < budget`` 时，驱动调用 ``napi_complete_done()``。只有成功 Complete 后，才能按设备协议重新打开 IRQ。

IRQ Rearm 必须避免丢事件
   判空、Complete、Unmask 和新 Completion 到达之间存在竞态。硬件或驱动必须通过状态重检、Missed 机制或可靠触发协议形成闭环。

Coalescing 与 NAPI 位于不同层
   Interrupt Coalescing 决定 NIC 何时通知；NAPI 决定通知后 CPU 怎样批量处理。增强两者都可提高吞吐，也会增加首包和排队延迟。

执行上下文可能变化
   NAPI 常由 NET_RX_SOFTIRQ 执行，压力下可转入 ``ksoftirqd``；PREEMPT_RT、Threaded NAPI 等会改变调度模型，驱动应依 API 约束而非函数名判断上下文。

局部性由完整队列拓扑决定
   RSS、IRQ Affinity、NAPI CPU、RPS/RFS、应用 CPU 与 NUMA 共同决定 Cache Locality。IRQ 均衡不表示协议与应用处理也均衡。

调优必须定位瓶颈层
   Budget、Coalescing、Queue 数、Ring Size、RPS 和 Busy Poll 解决不同问题。提高 Budget 不能修复 Refill、Affinity、CPU 或协议路径过载。

Teardown 先让事件源沉默
   安全顺序是停止新发送、Mask IRQ、停止硬件 Queue/DMA、同步 IRQ、Disable NAPI，最后释放 Ring。只 Disable NAPI 会留下设备 DMA 访问。

关键路径
--------

IRQ 调度 NAPI：

::

   Queue 产生 Completion
   → IRQ 到达 CPU
   → Handler 确认事件
   → 取得 NAPI Schedule 所有权
   → Mask/缓解 Queue IRQ
   → 加入 Poll List
   → Raise NET_RX_SOFTIRQ

NAPI Poll：

::

   网络 Softirq 取得 napi_struct
   → 调用 poll(napi, budget)
   → 清理 TX Completion
   → 处理 RX Descriptor
   → XDP / skb / GRO
   → 更新 Consumer 与 Refill
   → 返回 work_done

Poll 完成：

::

   Ring 已空且 work_done < budget
   → napi_complete_done
   → 处理核心 Missed 状态
   → 按设备协议 Unmask IRQ
   → 重检 Queue
   → 有新工作则重新 Schedule

安全关闭：

::

   Stop 上层 TX Queue
   → Mask 设备 IRQ
   → 停止 RX/TX DMA
   → synchronize_irq
   → napi_disable 等待 Poll 退出
   → 清理 Ring 与 Buffer
   → 删除 NAPI 并释放对象

概念辨析
--------

* IRQ Coalescing 与 NAPI：前者控制通知频率，后者控制通知后的批处理。
* NAPI Budget 与 Ring Size：Budget 限制单轮 CPU 工作；Ring Size 限制设备可缓存的 Descriptor。
* ``napi_disable`` 与硬件停止：Disable 只停止 Poll，DMA 与 IRQ 源需单独关闭。
* Softirq 与 ``ksoftirqd``：它们可执行同一 NAPI 工作，但调度时延不同。
* Busy Poll 与普通 NAPI：Busy Poll 用应用 CPU 主动找完成，仍共享同一 Queue 和协议状态。

本章结论
--------

NAPI 用一次 IRQ 打开一个受 Budget 约束的批处理窗口；正确性取决于 Schedule、Poll、Complete、IRQ Rearm 与硬件 Queue 形成无丢事件闭环。
