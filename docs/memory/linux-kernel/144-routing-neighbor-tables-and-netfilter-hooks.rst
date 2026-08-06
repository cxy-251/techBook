第144章：Routing、Neighbor Table 与 Netfilter Hook
=================================================

本章必须记住
------------

#. IP 层发送一个 packet 前必须连续回答：去哪里、由哪个接口离开、下一跳二层地址是什么、路径上的规则是否允许或修改它。
#. Routing 决定三层去向；Neighbor table 把下一跳 IP 转换为链路层地址；Netfilter 在固定路径点过滤、修改和跟踪 packet。
#. 三者是连续但独立的状态机，路由正确不表示邻居可达，也不表示 Netfilter 放行。
#. 所有判断都属于某个 network namespace；不同 namespace 拥有独立路由、规则、邻居表、conntrack 和 Netfilter 规则集。
#. Route lookup 的输入不只有目的地址，还可包括源地址、输入接口、mark、TOS、uid、VRF/l3mdev 和策略规则。
#. FIB 保存路由信息；策略路由先通过 rule 选择表，再在相应表中查找。
#. Route lookup 的结果通常包含 route type、输出设备、下一跳、源地址选择、MTU、错误和后续 ``dst`` 操作。
#. Route type 可以表示本地、单播、不可达、禁止、黑洞、广播或其它语义，不能只看设备名。
#. 本机接收 packet 通常先经过 PRE_ROUTING，再根据路由结果进入 LOCAL_IN 或 FORWARD。
#. 本机产生 packet 通常没有 PRE_ROUTING，而是经过 LOCAL_OUT，再进入 POST_ROUTING。
#. 转发 packet 的稳定主线是 PRE_ROUTING → route decision → FORWARD → POST_ROUTING。
#. 本机目标的稳定主线是 PRE_ROUTING → route decision → LOCAL_IN → local protocol/socket。
#. 本机发送的稳定主线是 local route/output → LOCAL_OUT → POST_ROUTING → neighbor/output。
#. 精确 route lookup 和 hook 相对位置会受 IPv4/IPv6、reroute、xfrm、bridge 和版本实现影响，稳定结论是路径角色。
#. ``ip_forward`` 是 IPv4 转发的必要策略入口之一，不代表所有 namespace、接口和规则都允许转发。
#. IPv6 转发有独立 sysctl 与协议行为，不能直接套用 IPv4 配置。
#. TTL/Hop Limit、MTU、source validation、policy 和 route type 都可能在转发路径拒绝 packet。
#. ECMP 可在多个 next hop 中选择一条路径，选择通常受 flow hash、policy 和邻居状态影响。
#. 同一 flow 通常应保持稳定路径，以避免乱序；精确哈希字段和策略可配置且具有版本差异。
#. VRF 把接口放入独立三层路由域，并通过 l3mdev 规则影响 lookup。
#. ``skb->mark`` 可由应用、tc、Netfilter 或隧道设置，并参与策略路由和规则选择。
#. Mark 本身没有全局固定含义，必须结合当前 namespace 的 rule 和规则配置解释。
#. ``ip route get`` 显示的是指定输入条件下的路由决策，不证明 packet 已通过 Netfilter 或真正到达设备。
#. Route 选择直连目的时，neighbor lookup 的 key 通常是目的 IP；选择网关时，key 是网关 IP。
#. 邻居表是 IP 下一跳到链路层地址的缓存与可达性状态机。
#. IPv4 典型使用 ARP，IPv6 典型使用 Neighbor Discovery；通用逻辑由邻居子系统管理。
#. ``struct neighbour`` 表示一个邻居对象，``struct neigh_table`` 表示协议/namespace 对应的邻居表。
#. Neighbor entry 通常同时包含设备、协议地址、链路层地址、状态、计时器、输出函数和未解析队列。
#. 常见 NUD 状态包括 INCOMPLETE、REACHABLE、STALE、DELAY、PROBE、FAILED、PERMANENT、NOARP。
#. REACHABLE 表示近期确认可达；STALE 表示有地址但需要按策略重新确认，不等同于立即失败。
#. INCOMPLETE 表示正在解析链路地址，packet 可能进入 unresolved queue。
#. DELAY/PROBE 表示内核正在进行可达性确认；FAILED 表示解析或探测失败。
#. PERMANENT/NOARP 等状态具有静态或协议特殊语义，不能按动态 ARP 老化模型解释。
#. 路由到网关时，ARP/NDISC 查询的是下一跳网关，不是最终互联网目的地址。
#. 邻居项可用时，链路层可以立即构造 header 并交给设备发送。
#. 邻居项不可用时，内核通常排队有限数量 packet，并发送 ARP Request 或 Neighbor Solicitation。
#. 解析成功后，未解析队列中的 packet 继续输出；解析失败后，packet 被丢弃并可能向上层报告错误。
#. unresolved queue 有长度/字节限制，邻居解析慢时会形成局部排队和 drop。
#. 邻居表也受容量、GC 阈值和老化策略约束，大量 peer/扫描/容器地址会放大资源压力。
#. ``ip neigh`` 是状态快照；短暂 STALE 不自动等于网络故障，FAILED/反复 INCOMPLETE 才需结合探测分析。
#. ARP flux、proxy ARP、IPv6 proxy NDP 和 bridge/VRF 会改变邻居解析位置与回答者。
#. 邻居解析完成不表示物理链路可靠，驱动 ring、交换网络和远端仍可能丢包。
#. Netfilter 提供协议族相关 Hook 框架，允许模块按 priority 在 packet 路径中执行回调。
#. 常见 IPv4/IPv6 Hook 名称为 PRE_ROUTING、LOCAL_IN、FORWARD、LOCAL_OUT、POST_ROUTING。
#. Hook 是内核路径位置；iptables/nftables 是在这些位置组织规则的用户态配置体系。
#. nftables 和 iptables frontend 最终可使用 Netfilter 基础设施，但规则表示、兼容层和功能不同。
#. 一个 Hook 点可以注册多个回调，执行顺序由 priority 和注册顺序规则决定。
#. Hook verdict 常见为 ACCEPT、DROP、STOLEN、QUEUE、REPEAT 等，具体可用值依协议和接口。
#. ACCEPT 表示继续执行后续 Hook/路径，不表示 packet 已成功交付最终目的。
#. DROP 表示当前规则路径丢弃；抓包在更早位置看到 packet 仍与此结果兼容。
#. STOLEN 表示回调接管 packet 生命周期，调用者不能继续按普通路径使用 skb。
#. QUEUE 可把 packet 交给用户态队列程序决定，带来额外排队、复制和故障依赖。
#. Netfilter 回调可以读取或修改 skb、mark、地址、端口和 conntrack 状态，但修改后必须维护 checksum、routing 和 header 合同。
#. 在 LOCAL_OUT 或 DNAT 后改变目的地址，可能要求重新执行路由查找。
#. 在 SNAT 后改变源地址，必须使后续 checksum 和 conntrack/NAT 状态一致。
#. Conntrack 把双向 packet 流组织成连接对象，并跟踪 ORIGINAL 与 REPLY 方向的 tuple 和协议状态。
#. Conntrack 的“连接”是内核状态对象，不等同于用户态 socket，也不只服务 TCP。
#. UDP 没有 TCP 握手，conntrack 仍可根据双向 tuple 和 timeout 建立状态。
#. ICMP、隧道和相关连接具有各自 tuple/expectation 规则，具体 helper 具有版本与安全边界。
#. 常见 conntrack 状态 NEW、ESTABLISHED、RELATED、INVALID 是规则视图，不等同于 TCP 内部 socket state。
#. ESTABLISHED conntrack 表示已观察到符合跟踪模型的双向/后续流量，不表示 TCP 应用已完成握手的所有业务条件。
#. INVALID 表示 packet 无法按当前 conntrack 状态解释，原因可包括截断、超时、乱序、资源或协议异常。
#. Conntrack table 是有限资源；条目数量、bucket、timeout 和 GC 会影响新流建立。
#. 表满时新流可能无法建立 conntrack，进而被 stateful firewall/NAT 丢弃。
#. Conntrack entry 的生命周期可能长于某个 packet，短于用户应用连接，必须按 timeout 与协议事件判断。
#. NAT 通常依赖 conntrack 为一个 flow 保存地址/端口映射。
#. NAT 规则主要在连接的首个需建立映射的 packet 上决定转换，后续 packet 根据 conntrack NAT 状态应用一致映射。
#. 因此修改 NAT 规则不保证已存在 conntrack flow 立即改用新映射。
#. DNAT 改变目的地址/端口，常用于把流量导向内部服务；SNAT/MASQUERADE 改变源地址/端口，常用于出站共享地址。
#. DNAT 常在路由决策前的 PRE_ROUTING 或本机 LOCAL_OUT 路径生效，以便新目的参与 route lookup。
#. SNAT 常在 POST_ROUTING 生效，因为此时通常已知道输出路径与源地址需求。
#. REDIRECT、NETMAP、MASQUERADE 等 target/expression 具有各自动态地址和接口语义。
#. NAT 不自动允许 packet；filter 规则仍可在其它 Hook 丢弃同一 flow。
#. Firewall ACCEPT 也不自动证明路由、邻居、qdisc 和设备发送成功。
#. Conntrack/NAT 与 network namespace 绑定，容器与宿主机可有不同表和规则。
#. veth packet 可能先在容器 namespace 经过一组路径，再在宿主 namespace 作为新入口经过另一组路径。
#. Bridge Netfilter 可让二层 bridge packet 进入部分 Netfilter 处理，精确行为受配置和内核版本影响。
#. XDP、tc ingress/egress 与 Netfilter 是不同 Hook 体系，执行位置和 skb 是否存在都可能不同。
#. XDP 在普通 skb 创建前，Netfilter 通常在 skb 网络层路径中；tc 可位于设备 ingress/egress 等位置。
#. Packet 被 XDP DROP 时，iptables/nftables 计数不会增加，因为 packet 尚未进入相应 Hook。
#. Policy routing、Netfilter mark 和 NAT 组合时，必须按“谁先修改字段、谁随后查表”建立精确时间线。
#. Reverse path filtering 可根据源地址反向路由判断丢弃 packet，尤其影响非对称路由与多宿主系统。
#. rp_filter 的模式、接口范围和 policy lookup 具有配置差异，不能只看主路由表猜测。
#. PMTU/ICMP 错误可能在 route/dst 与 socket error queue 中反馈，防火墙错误丢弃 ICMP 会造成黑洞。
#. 邻居失败可向本地 socket 报告 host unreachable，也可能只表现为超时，取决于协议与排队状态。
#. ``ip route``, ``ip rule``, ``ip neigh`` 应在 packet 所在 namespace 中执行。
#. ``nft list ruleset``/iptables-save 显示配置，不保证每条规则被命中；需结合 counter 与 trace。
#. Conntrack 工具显示跟踪表状态，字段和可用性依内核模块、权限与 namespace。
#. ``tcpdump -i any`` 会在多个接口/方向看到相同逻辑 packet，可能出现重复观察，不能当成重复发送结论。
#. 在入口设备抓到 packet、出口未抓到时，应按 PRE_ROUTING → route → FORWARD/INPUT → POST_ROUTING → neighbor 顺序定位。
#. 在出口抓到 packet但对端未收到时，应继续检查 qdisc、driver、链路与对端，而不是继续修改路由。
#. 在 conntrack 中有 flow 不表示 packet 已被 filter ACCEPT 或邻居发送。
#. Netfilter counter 不增加可能因为 packet 在更早 XDP/tc/route/namespace 被处理，或规则匹配条件错误。
#. NAT 地址正确但连接失败时，应继续检查 reply route、reverse NAT、conntrack、filter 和对端服务。
#. 非对称路由会让 reply packet 进入不同防火墙/conntrack 实例，导致状态和 NAT 不匹配。
#. Flow offload、hardware offload 和 eBPF datapath 可绕过部分传统慢路径，诊断时要确认实际加速状态。
#. Offload 后规则语义仍需保持，但计数、抓包点和 trace 可见性可能变化。
#. 路由和规则更新与在途 packet 并发，旧 ``dst``/conntrack 对象可因引用继续存在一段时间。
#. RCU 允许读路径高效查表，更新后的立即可见边界和对象释放由具体子系统管理。
#. 精确函数名、Hook priority、route cache 实现和 conntrack internals 属于版本敏感细节。
#. 稳定源码阅读顺序是：namespace/入口 → Hook 前状态 → route rule/FIB → local/forward 分支 → conntrack/NAT → Hook verdict → neighbor → qdisc/device。

必背路径
--------

本机接收：

::

   RX skb 进入 IP
   → PRE_ROUTING
   → Conntrack / DNAT 等处理
   → Route lookup
   → 结果为 LOCAL
   → LOCAL_IN
   → TCP/UDP/ICMP
   → Socket lookup 与接收队列

转发：

::

   Packet 从入口设备进入
   → PRE_ROUTING
   → Conntrack / 可选 DNAT
   → Policy rule + FIB lookup
   → 检查 forwarding、TTL、MTU
   → FORWARD
   → POST_ROUTING
   → 可选 SNAT
   → Neighbor lookup
   → qdisc / 出口设备

本机发送：

::

   Socket 构造 IP packet
   → 输出 route lookup
   → LOCAL_OUT
   → 可选 mark/DNAT 并 reroute
   → POST_ROUTING
   → 可选 SNAT
   → Neighbor lookup
   → 链路层与设备发送

Neighbor 解析：

::

   Route 得到输出设备与 next hop
   → 查找 struct neighbour
   → REACHABLE/可用则直接构造 L2 header
   → INCOMPLETE 则排队 packet
   → 发送 ARP Request / Neighbor Solicitation
   → 收到应答并更新状态
   → 释放 unresolved queue 继续发送
   → 超时则 FAILED 并丢弃/报错

定位“入口有包、出口无包”：

::

   确认 network namespace 与入口设备
   → 检查 PRE_ROUTING counter/trace
   → 检查 policy rule 和 route result
   → 判断 LOCAL 还是 FORWARD
   → 检查 FORWARD/LOCAL_IN verdict
   → 检查 conntrack/NAT 状态
   → 检查 POST_ROUTING
   → 检查 next-hop neighbor 状态
   → 检查 qdisc 与驱动发送

必须区分
--------

* Routing 与 Neighbor Resolution：Route 选择三层下一跳和设备；邻居表解析下一跳的链路层地址。
* Netfilter Hook 与规则工具：Hook 是内核路径位置；nftables/iptables 是配置规则的机制。
* Conntrack State 与 TCP State：Conntrack 跟踪 packet flow；TCP socket 状态跟踪端点协议生命周期。
* NAT 映射与 Firewall 放行：NAT 改写地址；filter verdict 独立决定 packet 是否继续。
* 抓到 Packet 与成功转发：抓包只证明 packet 到达抓取点，后续 route、Hook、neighbor 或设备仍可失败。

一句话结论
----------

Routing 决定 packet 的三层去向，Neighbor table 把下一跳变成可发送的二层地址，Netfilter/Conntrack/NAT 则在固定路径点决定 packet 是否继续以及它将以什么身份继续。
