第145章：TCP/IP 状态、拥塞与 Packet 诊断
========================================

核心知识点
----------

TCP 是多状态共同推进的字节流协议
   一个连接同时包含 socket state、序列空间、ACK、窗口、重传、定时器和队列；任何单个字段都不能单独解释吞吐或卡顿。

连接状态表达生命周期
   LISTEN、SYN-SENT、SYN-RECV、ESTABLISHED、FIN-WAIT、CLOSE-WAIT、LAST-ACK 和 TIME-WAIT 描述建连与关闭阶段，不直接表示当前 packet 所在位置。

监听队列分成不同阶段
   握手中的请求与已完成等待 accept 的连接属于不同队列。大量 SYN-RECV、accept queue 满和应用 accept 慢需要分别诊断。

Send 返回不表示数据已确认
   用户 send 成功只表示本地 TCP 接受字节。数据还可能停留在 socket 队列、重传队列、qdisc、设备 ring 或网络路径中。

Receive Window 与 Congestion Window 约束不同
   对端 advertised window 保护接收缓存和应用消费能力；cwnd 控制发送端对网络容量与拥塞的估计。实际在途量受二者共同限制。

ACK、SACK 与序列空间描述接收进展
   累计 ACK 确认连续字节，SACK 额外报告不连续已接收区间。发送队列、未确认数据和重传记分不是同一集合。

RTO 与快速恢复是不同丢失机制
   RTO 基于 RTT 估计和方差，是较慢的超时恢复；重复 ACK、SACK、RACK 等机制可在超时前推断丢失并触发恢复。

重传不自动证明物理链路丢包
   抓包工具根据观察到的序列与时间推断 retransmission。重排、抓包缺失、offload、非对称路由和不同抓取点都可能影响判断。

队列增长指向生产与消费失衡
   Send-Q 持续增长表示应用供数快于后续路径推进；Recv-Q 持续增长表示内核接收快于应用读取。它们不等于 qdisc backlog 或驱动 ring 深度。

状态症状具有明确方向
   大量 CLOSE-WAIT 常指向本地应用未关闭；大量 SYN-SENT 指向主动建连未完成；大量 TIME-WAIT 需要结合短连接速率和主动关闭方向解释。

诊断必须连接主机与网络证据
   ``ss`` 提供 socket/TCP 状态，协议计数提供聚合趋势，抓包提供 packet 时间线，trace/perf 提供内核路径与 CPU 成本；这些证据必须按同一 flow 和时间窗口对齐。

关键路径
--------

主动建连：

::

   connect
   → 状态进入 SYN-SENT
   → 发送 SYN
   → 收到 SYN-ACK
   → 校验 ACK 与选项
   → 发送最终 ACK
   → 状态进入 ESTABLISHED
   → 唤醒阻塞或非阻塞调用者

发送与确认：

::

   应用 send 字节
   → TCP 分段并进入发送队列
   → 受 rwnd、cwnd 与 pacing 限制
   → Packet 进入 IP/qdisc/设备
   → 对端返回累计 ACK/SACK
   → 更新在途数据与拥塞状态
   → 释放发送内存并唤醒写者

丢失恢复：

::

   ACK/SACK 暴露序列缺口
   → 快速重传或 RACK 推断丢失
   → 重传缺失 segment
   → 调整 cwnd/ssthresh
   → 若反馈不足则等待 RTO
   → 超时重传并退避
   → 收到新 ACK 后继续推进

吞吐诊断：

::

   绑定同一五元组与时间窗口
   → 检查应用供数和 Recv-Q/Send-Q
   → 检查 rwnd、cwnd、RTT、RTO、pacing
   → 检查重传、SACK 和 zero-window
   → 检查 qdisc、设备和 CPU
   → 检查回程 ACK 与非对称路径
   → 确定真正限制项

概念辨析
--------

* Socket State 与 Conntrack State：前者是 TCP 端点状态；后者是 Netfilter 对 flow 的跟踪状态。
* Receive Window 与 Congestion Window：前者是接收端流控；后者是发送端拥塞控制。
* RTT 与 RTO：RTT 是往返时间样本；RTO 是根据 RTT 统计推导的重传超时。
* Send Queue 与 In-flight Data：发送队列保存尚未完全处理的数据；在途数据只是其中已发送未确认部分。
* FIN 与 RST：FIN 有序关闭一个方向；RST 立即复位连接并报告异常终止。
* TIME-WAIT 与 fd 泄漏：TIME-WAIT 是协议状态；原应用 fd 通常已经关闭。

本章结论
--------

TCP 性能由应用队列、接收窗口、拥塞窗口、ACK/SACK 反馈、重传计时和本机网络队列共同决定。可靠诊断必须把连接状态与双向 packet 时间线放在同一证据链中。