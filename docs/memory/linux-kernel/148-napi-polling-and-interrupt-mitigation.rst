第148章：NAPI Polling 与中断缓解
================================

本章必须记住
------------

#. NAPI 把“每个 Packet 立即用硬中断处理”转换成“中断触发一次、随后按 Budget 批量 Poll”。
#. NAPI 的核心目标是降低中断率、提高批处理局部性，并给单次网络处理设置 CPU 占用边界。
#. ``struct napi_struct`` 表示一个可调度的网络事件处理实例，通常关联一组 RX/TX Queue。
#. 一个 ``net_device`` 可以有多个 NAPI Instance；一个 NAPI 也可能处理一个 Queue Pair 或一组硬件事件。
#. IRQ Vector、Hardware Queue 与 NAPI Instance 不要求严格一一对应，映射由驱动和硬件决定。
#. 驱动通常在 Probe/Open 阶段用 ``netif_napi_add()`` 一类接口注册 Poll 回调。
#. 注册 NAPI 不表示它已允许运行；数据面启动时还需 ``napi_enable()``。
#. ``napi_disable()`` 等待该 NAPI 不再运行并阻止新 Poll，但不自动停止硬件 IRQ 或 DMA。
#. IRQ Handler 的职责应保持轻量：确认来源、屏蔽或缓解 Queue IRQ、调度 NAPI，然后退出。
#. ``napi_schedule()`` 只发布未来 Poll 工作，不会在调用点直接完整处理 Ring。
#. 已经 Scheduled 的 NAPI 不应被并发重复执行，状态位和 Missed 机制负责合并事件。
#. ``napi_schedule_prep()``、``__napi_schedule()``、``napi_schedule_irqoff()`` 的适用上下文与组合具有版本和驱动差异。
#. 若驱动需要显式 Mask IRQ，稳定原则是先取得 NAPI 调度所有权，再 Mask/发布，避免事件丢失窗口。
#. 部分设备在读 Completion 或写 Doorbell 后自动 Mask/Unmask，不能把软件模板机械套用。
#. NAPI 被调度后通常进入当前 CPU 的 ``softnet_data`` Poll List，并触发 ``NET_RX_SOFTIRQ``。
#. ``net_rx_action()`` 一类核心路径从 Poll List 取出 NAPI 并调用驱动 ``poll(napi, budget)``。
#. 网络 Softirq 可以在中断返回路径执行，也可在压力下由 ``ksoftirqd/<cpu>`` 执行。
#. PREEMPT_RT、Threaded NAPI 和内核版本会改变具体执行上下文，驱动不能只靠函数名假设原子性。
#. Poll 回调通常同时清理 RX Packet 和 TX Completion。
#. Budget 主要按 RX Packet 计数；TX Completion 通常不消耗 RX Budget，具体驱动应遵守 NAPI API 合同。
#. Budget 不是字节数，也不是 Descriptor 数；一个 GRO Packet、Multi-buffer Packet 或特殊路径的计数规则需按实现验证。
#. ``budget == 0`` 可能表示只允许处理 TX Completion 等非 RX 工作，驱动不能无条件进入依赖 RX Budget 的路径。
#. Poll 处理完所有工作且 ``work_done < budget`` 时，驱动通常调用 ``napi_complete_done()``。
#. ``napi_complete_done()`` 成功后，驱动才可按硬件协议重新 Enable/Unmask 对应 IRQ。
#. Poll 用尽 Budget 并返回 ``budget`` 时，NAPI 保持 Scheduled，核心会在后续继续 Poll。
#. 若恰好处理 ``budget`` 个 Packet 同时 Ring 已空，驱动必须按 NAPI 合同解决“完成与 Budget Exhausted 无法同时表达”的边界。
#. 常见策略是保持 Scheduled 等下一轮确认，或在安全条件下按 API 建议调整返回值，具体实现应参考目标版本文档。
#. 在未成功 Complete 前重新打开 IRQ，可能产生重复中断、并发处理或状态机破坏。
#. Complete 后再 Unmask 也存在“判空与新事件到达”的竞态，硬件和驱动必须提供不会 Lost Interrupt 的协议。
#. 某些驱动在 Unmask 后检查 Ring，若发现新工作则重新 Mask 并 Schedule。
#. NAPI Weight 是单个 Instance 的默认批量尺度之一；全局处理还受 ``netdev_budget`` 和时间窗口限制。
#. ``netdev_budget`` 限制一次网络 Softirq 可处理的总 Packet 工作量。
#. ``netdev_budget_usecs`` 一类参数限制一次 Softirq 的时间窗口，具体存在和单位依内核版本。
#. 单 NAPI Budget、全局 Budget 和 Softirq 时间限制是三个不同层级。
#. Budget 太小会增加 Re-schedule、Softirq 和 Cache 重载成本；太大会延长同 CPU 上其它任务等待。
#. 提高 Budget 不能修复 Ring、IRQ Affinity、CPU 频率、内存分配或协议处理的根本瓶颈。
#. NAPI 的收益来自 Batch：一次取多个 Descriptor、一次触碰 Ring Cacheline、批量构造 skb、批量 GRO 与 TX Reclaim。
#. 批处理提高吞吐，也会增加 Packet 等待到 Poll 的时间和单轮占用。
#. Interrupt Coalescing 是 NIC 侧控制何时触发 IRQ；NAPI 是主机侧控制 IRQ 后怎样批量处理。
#. Coalescing 与 NAPI 互补，但不是同一种机制。
#. Coalescing 可按 Packet 数、时间或自适应策略触发，参数通常通过 ``ethtool -c/-C`` 暴露。
#. 更强 Coalescing 可降低 IRQ/Packet，却增加首包延迟和 Burst Size。
#. NAPI Budget 再大也无法消除设备在 Coalescing Timer 中等待的时间。
#. IRQ Affinity 决定 Vector 首先在哪个 CPU 处理；NAPI 默认通常跟随调度它的 CPU。
#. RSS Queue、IRQ Vector、NAPI、RPS、Application CPU 与 NUMA 的组合决定数据局部性。
#. RPS 可以把协议处理转移到其它 CPU，它不会改变 NIC 原始 RX Queue 或 DMA 位置。
#. RFS 试图把 Flow 处理靠近消费 Socket 的 CPU，具体启用和效果依系统配置。
#. 当 Softirq 在硬中断返回路径无法及时处理完，剩余工作可由 ``ksoftirqd`` 继续执行。
#. ``ksoftirqd`` CPU 高表示 Softirq 工作积压或被推迟，不自动证明 NIC 硬件已满载。
#. 单个 ``ksoftirqd`` 高可能来自 Queue/Affinity 集中、GRO 关闭、XDP/Netfilter 成本或其它 Softirq。
#. 高优先级用户任务、长时间关中断/关抢占和 CPU 频率限制都会推迟 NAPI。
#. ``/proc/net/softnet_stat`` 提供 Per-CPU 网络处理与丢弃聚合证据，字段格式随内核版本变化。
#. Softnet Drop 表示 Packet 未能在某个软件接收队列继续处理，不等同于 NIC RX Ring Drop。
#. ``/proc/interrupts`` 可观察 IRQ 分布；IRQ 均衡不代表 NAPI 和应用处理也均衡。
#. ``/proc/softirqs`` 可观察 NET_RX/NET_TX 次数，次数不直接等于 Packet 数或 CPU 时间。
#. Perf 用于定位 CPU 花在 IRQ、NAPI、GRO、协议、Netfilter 还是 Copy 上。
#. Ftrace/eBPF 可连接 IRQ → NAPI Schedule → Poll → Complete，事件名和字段随版本演进。
#. Driver/EtHTool Queue Stats 用于补充 Ring Miss、No Buffer、IRQ 与 Completion 证据。
#. Busy Polling 让应用线程主动轮询 NAPI/Socket 路径，以 CPU 时间换取更少调度与唤醒延迟。
#. ``SO_BUSY_POLL``、系统 Busy Poll 参数和 NAPI ID 机制的支持范围具有内核、驱动与 Socket 类型边界。
#. Busy Poll 不等于设备完全关闭 IRQ，也不自动绕过协议栈。
#. Busy Poll 只在工作负载、CPU 隔离和 Queue Locality 匹配时可能改善尾延迟。
#. 在共享 CPU 上无界 Busy Poll 会抢占其它任务、增加功耗并恶化整机延迟。
#. Threaded NAPI 把 Poll 放到内核线程上下文，调度策略和延迟模型与 Softirq NAPI 不同。
#. Threaded NAPI 是否可用、如何启用和是否适合目标驱动属于版本与部署策略。
#. GRO 通常在 NAPI 批处理中聚合 Packet，因此 NAPI 批量大小会间接影响 GRO 机会。
#. GRO Flush、Timer 与 NAPI Complete 会影响 Packet 何时向上交付，具体实现随版本变化。
#. XDP 可在 NAPI Poll 中先于普通 skb 路径运行，XDP_DROP/TX/REDIRECT 不进入常规协议栈。
#. XDP 工作仍消耗 Poll 时间和 Ring Budget，不能因没有 skb 就忽略其 CPU 成本。
#. NAPI Poll 不能无限等待内存或硬件；高频路径应避免不必要睡眠与不可控长操作。
#. Poll 回调的锁和同步设计必须允许同 Queue 的 IRQ、Reset、Stop 与 Remove 安全协作。
#. ``napi_disable()`` 前应阻止新的 IRQ Schedule，通常先 Mask IRQ 或停止硬件事件源。
#. 设备 Stop 的稳定顺序是停止新 TX、Mask IRQ、停止 DMA/Queue、Disable NAPI，再释放 Ring。
#. 若先释放 Ring 再 Disable NAPI，正在运行的 Poll 可访问已释放 Descriptor。
#. 若只 Disable NAPI 而未停 DMA，设备仍可能覆盖即将释放的 RX Buffer。
#. Reset 后旧 Completion 可能迟到，NAPI Poll 必须结合 Generation/Queue State 拒绝旧结果。
#. NAPI Complete Lost Wakeup 常表现为 Queue 有 Packet、IRQ 不再增长、Poll 也不再运行。
#. NAPI 永久 Scheduled 常表现为 IRQ 很少、Poll 持续返回 Budget、CPU 高且其它任务饥饿。
#. Poll 返回值错误会导致虚假 Busy Loop、事件丢失或重复 IRQ。
#. RX 延迟高但吞吐正常时，应检查 Coalescing、Budget、GRO Flush、CPU 调度和应用唤醒。
#. RX Drop 高时，应分别检查 Hardware Ring、Refill、NAPI/Softnet、协议和 Socket Queue。
#. 调优应一次改变一个变量：Coalescing、Queue 数、IRQ Affinity、Budget、RPS、Busy Poll。
#. 增加 Queue 数可能分散负载，也可能因 Flow 太少、IRQ/NUMA 错配而无收益。
#. 增加 Ring Size 可缓冲短时 Burst，也可能增加排队和内存占用。
#. NAPI 的稳定理解不是“轮询替代中断”，而是“中断负责发现，Poll 负责受控批处理”。
#. 精确 Softirq 函数、NAPI State Bit、Sysctl 和 Tracepoint 具有版本差异。
#. 稳定源码阅读顺序是：NAPI 注册 → IRQ 映射 → Schedule → Softirq Poll → Budget 返回 → Complete → IRQ Rearm → Disable/Teardown。

必背路径
--------

IRQ 触发 NAPI：

::

   NIC Queue 产生 Completion
   → MSI-X / IRQ 到达 CPU
   → Driver Handler 确认事件
   → 取得 NAPI Schedule 所有权
   → Mask / 缓解 Queue IRQ
   → 把 napi_struct 加入 Poll List
   → Raise NET_RX_SOFTIRQ
   → Handler 返回

NAPI Poll：

::

   net_rx_action 取得 napi_struct
   → 调用 driver poll(napi, budget)
   → 清理 TX Completion
   → 处理最多 budget 个 RX Packet
   → 构造 skb / XDP / GRO
   → 更新 Ring Consumer 并 Refill
   → 返回 work_done

Poll 完成：

::

   Ring 已排空且 work_done < budget
   → napi_complete_done
   → 处理 Missed / GRO Flush 等核心状态
   → Complete 成功
   → 按设备顺序重新 Unmask IRQ
   → 再检查是否有新事件
   → 必要时重新 Schedule

Softirq 过载：

::

   Packet 持续进入
   → Poll 反复用尽 Budget
   → 全局 Budget / 时间窗口耗尽
   → 重新 Raise NET_RX_SOFTIRQ
   → 剩余工作由后续 Softirq 或 ksoftirqd 执行
   → Queue 延迟与 Softnet Drop 可能上升

安全关闭 NAPI：

::

   Stop 上层 TX Queue
   → Mask 设备 Queue IRQ
   → 停止 RX/TX DMA 或硬件 Queue
   → synchronize_irq
   → napi_disable 等待 Poll 退出
   → 清理 Ring 与 Buffer
   → 删除 NAPI / 释放对象

必须区分
--------

IRQ Coalescing 与 NAPI
   Coalescing 决定设备何时通知；NAPI 决定通知后怎样批量处理。

NAPI Budget 与 Ring Size
   Budget 限制单轮 CPU 工作；Ring Size 决定硬件可缓存多少 Descriptor。

``napi_disable`` 与停止硬件
   Disable 只收束 Poll；DMA 和 IRQ 事件源必须由驱动另行停止。

Softirq 与 ``ksoftirqd``
   同一 NAPI 工作可在中断返回 Softirq 或内核线程中执行，时延和调度条件不同。

Busy Poll 与普通 NAPI
   Busy Poll 让应用主动寻找完成；普通 NAPI 由 IRQ/Softirq 调度，两者仍共享 Queue 和协议语义。

一句话结论
----------

NAPI 用一次 IRQ 换取一个受 Budget 控制的批处理窗口，正确性取决于 Schedule、Poll、Complete、IRQ Rearm 与设备 Queue 所有权形成无丢事件闭环。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 30，Network Device Drivers, NAPI, Queues, Offloads, and Packet Scheduling；
* AIBook 章节：Chapter 148，NAPI Polling and Interrupt Mitigation；
* 源文件：``docs/LinuxK/Part_30_Network_Device_Drivers_NAPI_Queues_Offloads_and_Packet_Scheduling/Chapter_148_NAPI_Polling_and_Interrupt_Mitigation.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_30_Network_Device_Drivers_NAPI_Queues_Offloads_and_Packet_Scheduling/Chapter_148_NAPI_Polling_and_Interrupt_Mitigation.md>`_。