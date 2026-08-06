第144章：Routing、Neighbor Table 与 Netfilter Hook
=================================================

核心知识点
----------

Routing、Neighbor 与 Netfilter 分工独立
   Routing 决定三层去向和输出设备，Neighbor table 把下一跳 IP 解析为链路层地址，Netfilter 在固定路径点过滤、修改和跟踪 packet。

所有决策都属于 Network Namespace
   路由表、策略规则、邻居表、conntrack 和 Netfilter 规则集都按网络命名空间隔离。同一 packet 在容器与宿主机中可能经历两组不同状态。

路由查找输入不只有目的地址
   源地址、输入接口、mark、TOS、UID、VRF 和 policy rule 都可能决定使用哪张 FIB 表及最终 next hop。

Hook 位置定义 Packet 所处阶段
   本地接收通常经过 PRE_ROUTING 与 LOCAL_IN，转发经过 PRE_ROUTING、FORWARD、POST_ROUTING，本地发送经过 LOCAL_OUT 与 POST_ROUTING。

路由结果包含完整输出合同
   Lookup 不只返回设备，还包含 route type、next hop、源地址选择、MTU、错误和后续 ``dst`` 操作。黑洞、禁止、本地和单播不是同一结果。

Neighbor 是可达性状态机
   INCOMPLETE、REACHABLE、STALE、DELAY、PROBE、FAILED 等状态表达地址解析与可达性确认。STALE 不等于立即失败，FAILED 才表示当前解析已失败。

邻居未解析时 Packet 可能排队
   内核可暂存有限 packet 并发出 ARP/NDISC 请求。解析成功后继续输出，失败或队列超限时丢弃并可能向上层报告错误。

Conntrack 记录 Flow 状态
   Conntrack 用双向 tuple、方向、协议状态和 timeout 组织 packet 流。它不是用户 socket，也不等同于 TCP 内部连接状态。

NAT 依赖 Conntrack 保持映射
   DNAT 通常在路由决策前改变目的，SNAT 通常在输出路径后部改变源。首个建立映射的 packet 决定 flow 的后续转换关系。

Mark 与策略必须按时间线解释
   ``skb->mark`` 可以由应用、tc、Netfilter 或隧道设置；只有明确“先修改、后查表”的顺序，才能解释 policy routing 结果。

可观测点不能代表完整路径
   路由查询、规则计数、conntrack 条目和抓包分别证明不同阶段。更早的 XDP/tc drop、后续 qdisc/driver drop 或非对称回程都可能改变结论。

关键路径
--------

本机接收：

::

   RX skb 进入 IP
   → PRE_ROUTING
   → Conntrack / 可选 DNAT
   → Policy rule 与 FIB lookup
   → Route type = LOCAL
   → LOCAL_IN
   → TCP/UDP/ICMP
   → Socket lookup

转发：

::

   Packet 从入口设备进入
   → PRE_ROUTING
   → Conntrack / DNAT
   → Route lookup
   → 检查 forwarding、TTL、MTU
   → FORWARD
   → POST_ROUTING / SNAT
   → Neighbor lookup
   → qdisc 与出口设备

本机发送：

::

   Socket 生成 skb
   → 本地 route lookup
   → LOCAL_OUT
   → 可选 mark / DNAT / reroute
   → POST_ROUTING / SNAT
   → Neighbor resolution
   → qdisc
   → Netdev TX

路径故障定位：

::

   确认 packet 所在 namespace
   → 检查 ip rule 与 route result
   → 检查 Hook counter/verdict
   → 检查 conntrack/NAT tuple
   → 检查 neighbor 状态
   → 检查 qdisc、driver 与回程路径

概念辨析
--------

* Routing 与 Neighbor：Routing 选择三层 next hop；Neighbor 把 next hop 转换成二层地址。
* Hook 与规则工具：Hook 是内核执行位置；nftables/iptables 是配置这些位置的用户接口。
* Conntrack State 与 TCP State：前者是防火墙/NAT 的 flow 视图；后者是 TCP socket 协议状态。
* ACCEPT 与成功交付：ACCEPT 只允许继续当前路径；后续路由、邻居、qdisc 和设备仍可能失败。
* DNAT 与 SNAT：DNAT 改变目的并影响后续路由；SNAT 改变输出 packet 的源身份。
* Route Entry 与实际发送：路由存在不证明邻居解析完成或 packet 已进入硬件。

本章结论
--------

Packet 能否继续前进，取决于路由去向、邻居可达性和 Netfilter/Conntrack 状态连续成立。诊断必须在正确 namespace 中按 Hook、route、neighbor 和设备顺序还原时间线。