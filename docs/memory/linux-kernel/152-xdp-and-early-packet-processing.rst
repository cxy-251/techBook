第152章：XDP 与早期 Packet 处理
==============================

核心知识点
----------

XDP 把决策前移到 skb 之前
   Native XDP 通常在驱动从 RX Descriptor 取得 Buffer 后、构造普通 ``sk_buff`` 前执行，因此可以避免后续对象和协议路径成本。

``xdp_buff`` 与 ``xdp_md`` 分属内核和 UAPI
   驱动内部用 ``struct xdp_buff`` 表示早期 Frame；BPF 程序通过 ``struct xdp_md`` 访问 ``data``、``data_end``、接口和 Queue 等受限上下文。

模式决定实际收益和能力
   Driver/Native 模式最靠近硬件；Generic/SKB 模式已经进入 skb 路径；Hardware Offload 在设备侧执行。挂载成功后仍要确认真实模式。

Verifier 要求逐层证明边界
   读取 Ethernet、VLAN、IP 和传输层 Header 前必须证明所需范围不超过 ``data_end``；调整 Head/Tail 后旧指针失效，需要重新验证。

Action 是 Buffer 所有权合同
   ``XDP_PASS`` 交给普通网络栈，``XDP_DROP`` 回收 Buffer，``XDP_TX`` 从入口设备发回，``XDP_REDIRECT`` 转交目标路径，``XDP_ABORTED`` 表示异常执行结果。

PASS 不等于最终交付
   PASS 只允许 Frame 继续构造 skb；后续路由、Netfilter、协议和 Socket 仍可能拒绝或丢弃它。

DROP 需要独立可观测性
   skb 前的 ``XDP_DROP`` 通常不会出现在 tcpdump、Netfilter 或 Socket 统计中，生产程序必须维护低成本 Action Counter 和错误计数。

Redirect 具有第二阶段
   Program 选择 DEVMAP、CPUMAP 或 XSKMAP 目标后，真正提交常在 NAPI Batch 边界完成；目标 Ring 满、Queue 不匹配或设备异常仍会失败。

XDP 不拥有完整协议语义
   它适合按早期 Header 做过滤、采样、转发和负载均衡，不直接提供 TCP 重组、Conntrack、NAT、qdisc、Socket Queue 或应用状态。

Map 与程序成本按 Packet/s 放大
   高频共享 Map 更新会造成锁和 Cache Line 竞争；Per-CPU Map 适合计数，但用户态需要聚合各 CPU 副本。

挂载对象具有独立生命周期
   Program、Map、Link、fd 和 bpffs Pin 都可延长对象寿命。Detach 不自动删除 Map，关闭 fd 也不保证对象立即释放。

驱动状态会影响可用性
   MTU、Multi-buffer、Page Pool、Queue 重建、Reset 和 Feature 变化都可能改变 Native XDP、Metadata 与 Redirect 能力。

关键路径
--------

Native XDP：

::

   NIC DMA 写 RX Buffer
   → NAPI Poll 取得 Descriptor
   → 驱动构造 xdp_buff
   → 执行 XDP Program
   → PASS / DROP / TX / REDIRECT
   → 对应路径接管 Buffer Ownership

Redirect：

::

   解析 Header 并选择目标
   → bpf_redirect_map 写入 Redirect 信息
   → 返回 XDP_REDIRECT
   → 内核验证 Map Entry 与 Queue
   → NAPI Batch Flush
   → 目标 Netdev / CPU / AF_XDP 接管
   → 失败时记录 Redirect Error

安全解析：

::

   读取 data 与 data_end
   → 验证 Ethernet Header
   → 处理可选 VLAN
   → 验证 IP 最小长度与可变 Header
   → 验证 L4 Header
   → 读取字段并决定 Action
   → 修改 Packet 后维护长度与 Checksum

安全替换：

::

   加载并验证新 Program
   → 准备新 Map 状态
   → 原子 Replace Link / Attach
   → 验证新 Counter 增长
   → 停止旧控制面更新
   → Detach 旧 Program
   → 删除旧 Pin 并等待引用结束

概念辨析
--------

* ``xdp_buff`` 与 ``sk_buff``：前者表示早期 RX Frame；后者承载完整网络栈元数据。
* Native 与 Generic XDP：Native 在 skb 前执行；Generic 已进入 skb 路径，功能兼容性和成本不同。
* ``XDP_DROP`` 与 Netfilter Drop：XDP 更早，后续规则、抓包和 Socket 通常不可见。
* ``XDP_TX`` 与普通 TX：XDP TX 不经过完整 Socket、qdisc 和协议发送路径。
* Redirect Action 与目标完成：返回 Redirect 只是移交意图，目标 Queue 和 Ring 仍可能产生背压或失败。

本章结论
--------

XDP 通过受验证程序把 Packet 决策前移到 skb 之前；性能来自尽早结束无须继续的路径，正确性来自边界检查、Action 所有权和目标背压闭环。
