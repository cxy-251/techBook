第180章：网络吞吐、丢包、锁争用与可扩展性
==========================================

核心知识点
----------

网络瓶颈必须按层定位
   接收路径应拆成 NIC Queue、IRQ、NAPI、协议栈、Socket Queue 和应用；发送路径应拆成 Socket、TCP/Pacing、qdisc、Netdev Queue、Driver Ring 和 NIC。

每层都有独立 Queue 与 Drop
   NIC Ring Overflow、Softnet Backlog、qdisc Drop、Socket Queue 满和应用消费慢属于不同位置。第一问题是 Packet 最后出现在哪一层，而不是先扩大所有 Buffer。

整机 CPU 余量会隐藏单队列饱和
   单 RX Queue、单 IRQ CPU、单 Flow、单 Socket Lock 或单应用 Worker可以先达到极限，其它 CPU 空闲并不代表该路径还有服务能力。

RSS、RPS、RFS 与 XPS 作用不同
   RSS 在硬件侧把 Flow 分到 RX Queue；RPS 在软件侧转移接收处理；RFS尝试靠近消费 Task；XPS影响发送 Queue 选择。它们都需要与 IRQ、Worker 和 NUMA 对齐。

增加 Queue 不保证线性扩展
   并行度还受 MSI-X Vector、CPU、设备 Engine、Flow Hash、应用分片和共享状态限制。单大 Flow通常不会因增加 RSS Queue 自动拆分。

吞吐必须同时看 Byte、Packet 与 Connection
   小包高 PPS 的每包固定成本可先耗尽 CPU，而 Bit/s 仍不高。GRO/GSO/TSO 等 Offload 还会改变抓包和计数粒度。

TCP 重传不是本机丢包证明
   Retransmit 可来自本机、远端、中间网络、ACK 丢失、乱序或超时。需要结合双端抓包、Sequence/ACK、设备 Counter 和 Queue 状态缩小位置。

Socket Queue 反映端点压力
   Recv-Q 长期增长通常表示应用读取或调度不足；Send-Q 增长还需结合接收窗口、拥塞窗口、RTT、Loss、Pacing 和 qdisc 解释。

锁争用会把多核路径重新串行化
   Spinlock Slowpath 只说明 CPU 在等待，必须通过 Call Graph 找到具体锁对象、持有者、等待者和临界区。睡眠锁还需要 Off-CPU 证据。

False Sharing 不一定出现显式锁
   多 CPU 修改同一 Cacheline 上的不同字段会形成 Coherence Traffic，表现为 Cycles 增长、IPC 下降和扩展性停滞，需要 Cacheline 与 NUMA 证据验证。

Buffer 增长只改变排队位置
   扩大 Ring、Backlog、qdisc 或 Socket Buffer 可减少短时 Drop，也会提高内存占用与尾延迟。它不能创造 NIC、CPU、网络或应用的服务率。

关键路径
--------

接收路径：

::

   Packet 到达 NIC RX Queue
   → DMA 写入 RX Buffer
   → MSI-X / IRQ
   → NAPI Poll
   → Driver 交付 skb
   → GRO / IP / Netfilter / TCP/UDP
   → Socket Receive Queue
   → Application recv
   → Buffer Refill 与所有权回收

发送路径：

::

   Application send
   → Socket Send Buffer
   → TCP Segmentation / Pacing / Congestion
   → Routing / Netfilter / Neighbor
   → qdisc
   → Netdev TX Queue
   → Driver Descriptor / DMA
   → NIC Queue / Wire
   → TX Completion 与 skb 释放

扩展性调查：

::

   逐步增加 Flow、Queue、Worker 或 CPU
   → 记录 Throughput、PPS、CPU/Packet 和 p99
   → 检查 Per-queue 与 Per-CPU 分布
   → 展开 Lock Slowpath 调用链
   → 检查 Cacheline、NUMA 与单 Flow 热点
   → 找到吞吐停止增长时最先饱和的共享对象
   → 分片、对齐或减少共享写

概念辨析
--------

* NIC Drop 与 TCP Retransmit：设备局部丢弃和端到端恢复事件不同。
* NAPI Budget Exhaustion 与 Drop：达到处理预算不表示 Packet 已经丢失。
* Softnet Backlog 与 Socket Queue：CPU 网络处理排队和应用接收排队不同。
* qdisc 与 Driver Ring：软件发送调度和硬件执行队列不同。
* RSS、RPS、RFS 与 XPS：硬件接收分流、软件接收分流、应用局部性和发送选择不同。
* Bit Throughput 与 Packet Rate：大包带宽和小包 PPS 的 CPU 成本模型不同。
* Lock Contention 与 False Sharing：显式同步等待和隐式 Cacheline 争用不同。
* Buffer 深度与服务能力：更深队列只延后溢出，不提高处理速率。

本章结论
--------

网络可扩展性调查必须先找到 Packet 停在哪个 Queue，再判断该层是服务率不足、应用消费慢，还是共享锁与 Cacheline 把并行路径重新串行化。