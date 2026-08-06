第155章：高性能 Packet Pipeline 的观测与优化
=============================================

核心知识点
----------

优化目标必须是端到端结果
   高性能网络不能只追求局部 Packet/s，应同时满足吞吐、CPU、P99/P999、Drop、内存、功耗和数据正确性。

先固定实际路径坐标
   观测应明确 NIC Queue、Driver/NAPI、XDP Program、Redirect Target、AF_XDP Ring、User Worker 和 TX/下游，避免把不同层统计混为同一边界。

相邻层必须建立计数守恒
   每层都要记录输入、输出、Drop 和 Backlog。Packet 最后一次出现的位置与下一层的差值，才是待解释的丢失或统计边界。

策略 Drop 与资源 Drop 不同
   预期的 ``XDP_DROP`` 是业务结果；ABORTED、Redirect Error、No Buffer、Ring Full 和 Frame Leak 是错误或容量证据，必须分别计数。

Counter 也具有生命周期
   Program Replace、Map 重建、设备 Reset、CPU Hotplug 和计数溢出会改变基线。监控必须记录 Program/Map Generation 与采样窗口。

CPU Profile 与 Packet 位置互补
   Perf 说明 CPU 在 Driver、NAPI、BPF、Map 或用户逻辑中花费多少；Queue/Ring Counter 才说明 Packet 停在哪里，两类证据不能互相替代。

热路径观测必须低扰动
   高频路径优先使用 Per-CPU Counter、驱动统计和采样事件。逐 Packet Trace、Map 全量 Dump 和 ``bpf_printk`` 会显著改变被测系统。

AF_XDP 需要 Frame 守恒账本
   FILL Produced、RX Consumed、TX Submitted、COMPLETION Reaped 和 User Free Frame 之和应保持稳定；不守恒直接指向 Leak、Double-submit 或未回收完成。

Ring 状态对应不同瓶颈
   FILL 空表示缺少可接收 Frame；RX 满表示用户消费慢；TX 满表示内核/设备消费慢；COMPLETION 积压表示用户回收慢。

Queue Locality 决定扩展效率
   RSS Queue、IRQ、NAPI、XSK Worker、UMEM 和 NIC NUMA Node 应尽量对齐。增加 Queue 数不能拆分单个热 Flow，也可能增加 Ring、IRQ 和 Cache 成本。

Batch 是吞吐与延迟交换
   增大 NAPI、AF_XDP 或用户 Batch 可摊薄同步和系统调用，同时增加首包等待与单轮 CPU 占用，必须用尾延迟验证。

优化应逐层单变量推进
   先建立传统栈基线，再依次验证 Native XDP、Redirect、AF_XDP 和 Zero-copy；每次只改变一个关键变量，并保留可回滚配置。

故障恢复属于性能合同
   Program Replace、Worker Restart、Queue Reset、设备 Down/Up 和 UMEM 重建必须可重复执行，否则峰值数据没有生产价值。

关键路径
--------

端到端计数链：

::

   NIC RX Packets
   → Driver/NAPI Processed
   → XDP PASS + DROP + TX + REDIRECT + ABORTED
   → Redirect Success / Error
   → AF_XDP RX Published
   → User RX Consumed
   → User TX Submitted
   → TX Completion Reaped

   相邻层差值
   → Drop、Backlog、Redirect 失败或统计粒度差异

CPU 定位：

::

   /proc/interrupts 确认 IRQ CPU
   → Softirq/softnet 观察 NAPI 压力
   → perf 定位 Driver/BPF/User 热点
   → Map Counter 解释 Action 分布
   → Ring 指标确认等待位置
   → NUMA 与 Affinity 检查远端访问
   → 只优化占比最大的已证明路径

AF_XDP Ring 诊断：

::

   FILL 持续下降
   → 检查 RX Frame 归还

   RX Ring 接近满
   → 检查 Worker 调度与 Batch

   TX Ring 满
   → 检查 Need-wakeup、驱动和 NIC

   COMPLETION 积压
   → 检查用户回收循环

   Frame 总数不守恒
   → 检查 Leak、Double-submit 和提前复用

受控优化：

::

   固定 Packet Size、Flow、Queue、CPU 与 NUMA
   → 保存配置和对象 Generation
   → 记录吞吐、Cycles/Packet、P99、Drop
   → 每次修改一个变量
   → 验证计数守恒和业务正确
   → 重复覆盖 Reset/Restart
   → 无稳定收益则恢复基线

概念辨析
--------

* CPU 热点与 Drop 位置：Profile 表示计算成本；逐层 Counter 表示 Packet 流失或积压位置。
* Packet/s 与 Gbit/s：小包可在较低带宽下耗尽 CPU，必须同时记录包率、字节率和包长。
* Ring 增大与性能改善：更大容量能吸收 Burst，也可能把 Drop 转化为更高尾延迟。
* Queue 数与可扩展性：多 Queue 只对可分散 Flow 有效，并要求 IRQ、Worker 和 NUMA 正确映射。
* Zero-copy 与低 CPU：Payload 不复制后，Parser、Busy Poll、Cache Miss 和跨 NUMA 仍可能主导 CPU。

本章结论
--------

高性能 Packet Pipeline 必须建立逐层守恒账本：先证明 Packet 在哪里消失、CPU 在哪里消耗、Frame 在哪里停留，再调整程序、Queue、NUMA、Batch 和唤醒策略。
