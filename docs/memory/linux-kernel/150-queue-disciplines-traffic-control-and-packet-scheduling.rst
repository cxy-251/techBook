第150章：Queue Discipline、Traffic Control 与 Packet Scheduling
==============================================================

核心知识点
----------

qdisc 是驱动前的软件调度层
   qdisc 位于协议栈输出与 ``ndo_start_xmit`` 之间，决定 skb 怎样排队、何时出队、超限时怎样 Drop 或 Mark。

qdisc 与 Driver Ring 是不同队列
   qdisc 理解 Flow、Class、速率、公平性和排队时间；Ring 理解 Descriptor、DMA 和硬件所有权。两层可同时积压。

``Qdisc`` 表示算法实例
   ``struct Qdisc`` 保存运行状态、队列和统计；``struct Qdisc_ops`` 定义 Enqueue、Dequeue、Reset、Drop 等算法操作。

多队列接口具有层级结构
   根 qdisc 可把流量分到多个 TX Queue，每个 Queue 再拥有叶子 qdisc。Root、Class、Leaf 与硬件 Queue 不能混为同一层。

Classless 与 Classful 解决不同问题
   FIFO、FQ、fq_codel 等通常直接组织 Packet；HTB 等 Classful qdisc 先按 Class 分配带宽，再由叶子 qdisc 管理具体排队。

FQ 关注 Flow 公平与节奏
   FQ 将不同 Flow 分开调度，减少单个大流独占队列，并可配合 Socket Pacing 平滑发送。

AQM 主动控制持续排队
   CoDel/fq_codel 依据排队时间等状态在队列填满前 Drop 或 ECN Mark，为发送端提供更早拥塞反馈。主动 Drop 不等同于故障。

HTB 用 Token 表达带宽合同
   Rate、Ceil、Priority 与层级决定 Class 的保证和上限。Token 不足时 Packet 等待；叶子 qdisc 仍决定 Class 内部顺序。

Shaping 与 Policing 不同
   Shaping 通过排队延迟发送以限制平均速率；Policing 通常对超限 Packet 立即 Drop 或 Remark，不维护长等待队列。

TC 由分类与动作组成
   Filter 根据 Header、Mark、Priority、Cgroup、Flower 或 BPF 选择 Class；Action 可以 Drop、Police、Redirect、Mirror 或修改 skb。

配置位置决定是否生效
   Namespace、设备、方向、Parent、Chain 与 Hook 任一错误，都可能造成规则存在却无流量命中。Tunnel、Veth、Bridge 路径可能经过多个 TC/qdisc 边界。

统计字段属于算法语义
   Backlog 表示当前排队量，Drop 表示丢弃，Overlimit 表示策略边界被触发，Requeue 表示下层暂时未接收。它们不能互相替代。

Bufferbloat 是排队时间问题
   吞吐维持而 RTT/P99 显著升高，通常说明瓶颈前积压过深。只追求零 Drop 容易用更长队列换取更差延迟。

GSO/TSO 改变统计粒度
   qdisc 中一个大 skb 可代表多个 Wire Segment，因此 Packet、Byte、Pacing 与最终帧数的关系必须结合 Offload 解释。

关键路径
--------

普通 Egress：

::

   Socket/TCP/IP 生成 skb
   → Route 与 Neighbor 选择输出设备
   → 选择 TX Queue
   → dev_queue_xmit
   → Root/Leaf qdisc Enqueue
   → 算法 Dequeue
   → ndo_start_xmit
   → Driver Ring 与 NIC

HTB 分类：

::

   skb 进入 HTB Root
   → Filter 选择 Class
   → 检查 Rate、Ceil、Priority 与 Token
   → 进入 Class 的 Leaf qdisc
   → Leaf Dequeue
   → 交给驱动

Bufferbloat：

::

   发送速率超过瓶颈
   → Socket/qdisc/Ring Backlog 增长
   → Sojourn Time 上升
   → RTT 与 P99 增大
   → AQM Drop/ECN 或 Limit 触发
   → 发送端降低速率

分层诊断：

::

   ss 查看 Socket Send-Q 与 Pacing
   → tc -s qdisc 查看 Backlog/Drop/Overlimit
   → tc -s class/filter 确认分类命中
   → ip -s link 查看接口聚合统计
   → ethtool -S 查看 Queue/Ring/Hardware
   → 抓包对齐实际发送时刻

概念辨析
--------

* qdisc 与 Driver Ring：qdisc 负责策略排队；Ring 负责 DMA Descriptor 执行。
* Shaping 与 Policing：Shaping 延迟发送；Policing 通常超限即处理或丢弃。
* Drop 与 Overlimit：Drop 是 Packet 消失；Overlimit 只是策略边界被触发。
* FQ 与 HTB：FQ 主要提供 Flow 公平和 Pacing；HTB 表达层级带宽保证与上限。
* 配置存在与实际执行：规则可能未命中、位于错误路径，或已下沉硬件执行。

本章结论
--------

qdisc 是发送路径的时间与顺序控制器：它在驱动前组织 Flow、公平性、带宽和主动拥塞反馈，而端到端延迟必须继续把 Socket、qdisc、Ring 与硬件队列分层测量。
