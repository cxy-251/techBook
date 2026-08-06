第152章：XDP 与早期 Packet 处理
==============================

本章必须记住
------------

#. XDP（eXpress Data Path）把 Packet 的第一轮决策放到 RX 路径的早期，通常发生在普通 ``sk_buff`` 分配之前。
#. XDP 的性能收益来自更早、更窄的对象和语义边界，而不是来自“BPF 指令天然没有成本”。
#. 内核内部常用 ``struct xdp_buff`` 表示早期 RX Buffer；BPF 程序看到的是 UAPI ``struct xdp_md``。
#. ``xdp_buff`` 关联 Packet 数据边界、Metadata、接收设备与 Queue 等上下文，精确字段具有版本与驱动差异。
#. ``xdp_md.data`` 和 ``data_end`` 定义程序可直接访问的 Packet 线性区域。
#. 任何 Header 读取前都必须证明所需字节位于 ``data`` 与 ``data_end`` 之间，否则 Verifier 无法证明安全。
#. XDP 看到的是早期 Frame，不自动拥有 Socket、TCP 重组、Conntrack、Route、qdisc 或应用状态。
#. 只依赖 Ethernet、IP、UDP/TCP Header 的粗粒度判断适合 XDP；依赖完整连接或应用语义的逻辑通常不适合。
#. Native/Driver XDP 通常由驱动在 RX Descriptor 转换为 skb 前执行，最能避免传统网络栈固定成本。
#. Generic/SKB XDP 在普通网络核心路径的 skb 上执行，兼容性更高，无法获得完整的“skb 前”性能收益。
#. Hardware Offload XDP 把支持的程序下沉到 NIC/SmartNIC，能力受硬件指令、Map、Helper 和控制面限制。
#. 同一程序在 Driver、Generic 和 Hardware 模式下的可用 Helper、Metadata、性能和可观测性可能不同。
#. 挂载成功不等于运行在期望模式；必须确认实际 Attach Mode 和驱动能力。
#. XDP 程序的主要返回值是 ``XDP_PASS``、``XDP_DROP``、``XDP_TX``、``XDP_REDIRECT`` 和 ``XDP_ABORTED``。
#. ``XDP_PASS`` 表示当前程序允许 Frame 继续进入普通网络栈，并不表示后续 Route、Netfilter 或 Socket 一定接受。
#. PASS 路径通常继续构造或补全 skb，因此已支付 XDP 检查成本后仍要支付完整协议栈成本。
#. ``XDP_DROP`` 在早期终止 Frame 路径并回收 Buffer，适合明显无效或策略拒绝的流量。
#. DROP 发生在 skb 形成前时，普通 tcpdump、Netfilter Counter 和 Socket 统计通常看不到该 Packet。
#. 生产 XDP_DROP 必须配套低成本 Counter、Reason 或采样，否则早期丢包会成为不可观测黑洞。
#. ``XDP_TX`` 把 Frame 从接收它的同一设备发回，适合简单反射或低层响应。
#. TX 前若修改 MAC、IP、Port、长度或 Checksum，程序必须维护完整 Header 合同。
#. ``XDP_TX`` 不经过普通 qdisc 和 Socket 发送语义，不能自动获得 Pacing、Flow 公平或 TCP 拥塞控制。
#. ``XDP_REDIRECT`` 把 Frame 交给 Redirect 目标，例如 DEVMAP、CPUMAP 或 XSKMAP。
#. DEVMAP 常用于重定向到其它 Netdev；CPUMAP 常用于把后续处理移到其它 CPU；XSKMAP 把 Frame 送往 AF_XDP Socket。
#. Redirect 程序通常先调用 ``bpf_redirect()`` 或 ``bpf_redirect_map()`` 写入目标信息，再返回 Redirect Action。
#. Redirect 的真正提交和 Flush 常在 NAPI Batch 边界完成，精确 Helper 与 Flush 路径具有版本差异。
#. XDP_REDIRECT 成功返回 Action 不保证最终目标一定接收；目标不存在、Queue 不匹配、Ring 满或设备错误仍可导致失败。
#. ``XDP_ABORTED`` 表示异常 Action 或程序错误路径，生产系统应计数并视为错误证据。
#. XDP 程序不应把解析失败的普通畸形 Packet 全部返回 ABORTED；可预期策略拒绝通常使用 DROP。
#. Header 解析必须逐层验证长度，IPv4 IHL、IPv6 Extension Header、VLAN 和 Tunnel 会改变下一层位置。
#. 不能把 ``sizeof(struct iphdr)`` 机械当作所有 IPv4 Header 长度，也不能假设 L4 Header 总是线性可见。
#. XDP 可以通过受支持的 Adjust Helper 改变 ``data``、``data_meta`` 或 Packet 尾部，具体 Helper 依 Program Type 和版本。
#. 调整 Head/Tail 后，先前保存的 Packet 指针可能失效，必须重新读取 ``data``/``data_end`` 并重新验证。
#. ``data_meta`` 可在 XDP 与后续路径之间传递少量 Metadata，但空间、消费方和保留语义必须明确。
#. Metadata 不应被当作跨所有设备和模式稳定存在的通用 ABI。
#. RX Queue Index 可帮助按 Queue 选择策略、Counter 或 XSK，但 Queue 配置变化会改变索引语义。
#. Ingress ifindex 表示当前执行上下文设备，不自动等于最终物理设备或原始外部接口。
#. VLAN、Bond、Bridge、Veth、Tunnel 和虚拟设备会改变 XDP 可挂载层级与看到的 Header 形态。
#. XDP RX Metadata kfunc 可暴露 RX Timestamp、RSS Hash、VLAN 等硬件信息，支持程度依驱动、模式和内核版本。
#. 程序必须对“不支持 Metadata”或字段不可用提供降级路径。
#. Native XDP 的 Buffer 生命周期由驱动 RX Ring、Page Pool 或专用内存模型控制。
#. 返回 PASS、DROP、TX 或 REDIRECT 后，Buffer 所有权由对应核心/驱动路径接管，程序不能在返回后继续引用数据。
#. XDP 程序不能睡眠；它运行在高频 RX 路径中，任何 Map Lookup、循环和 Helper 都会按 Packet/s 放大。
#. Verifier 支持有界循环不表示大型循环适合每 Packet 执行。
#. 高频共享 Hash Map 更新可能造成锁、原子操作或 Cache Line 竞争。
#. Per-CPU Map 常适合 Action Counter，用户态读取时需要聚合所有 CPU 值。
#. LRU Hash 等 Map 可以限制容量，但回收和竞争仍可能影响尾延迟。
#. XDP 程序越长、分支越复杂，I-cache、分支预测和 JIT 代码成本越高。
#. Tail Call 可把程序拆分成多个逻辑阶段，仍受调用深度、Map Lookup 和版本限制。
#. CO-RE/BTF 能提高程序跨内核版本适配性，不改变 Program Type 和 Attach Point 的运行边界。
#. XDP 早期 Drop 会节省 skb、协议、Netfilter 和 Socket 成本，但不会逆转 NIC DMA 已发生的事实。
#. 在 Native XDP 中，设备通常已经把 Frame DMA 到 RX Buffer，程序只是避免后续对象与协议处理。
#. Hardware Offload 可把决策进一步移到设备，但也会减少内核侧 Trace 和 Counter 可见性。
#. Generic XDP 适合先验证业务逻辑、兼容不支持 Native XDP 的设备，不应拿其性能代表 Native 模式。
#. XDP 与 TC ingress 是不同位置：XDP 通常在 skb 前，TC 使用 skb 并能访问更多网络核心语义。
#. XDP 与 Netfilter 不是简单替代关系；Netfilter 提供 Conntrack、NAT 和固定协议 Hook，XDP 提供更早的有限决策点。
#. XDP 与 Socket Filter 也不同：前者绑定设备 RX 路径，后者绑定更靠近 Socket 的 Packet 视图。
#. 选择 Attach Point 时先确定需要的最晚信息，再选择仍能满足功能的最早位置。
#. XDP Program Attach、Replace、Detach 应通过 Link 或受控 Netlink/libbpf 生命周期管理，具体 API 随版本演进。
#. 替换程序时要明确原子替换、期望旧 Program ID 和失败回滚，避免错误地覆盖其它控制面程序。
#. 多程序组合可通过 Dispatcher、Link 或 Tail Call 实现，能力与管理模型具有版本差异。
#. Detach XDP 不会自动销毁仍由 fd、BPF Link、Pin 或其它引用持有的 Program/Map。
#. Map Pinning 能让控制面重启后保留对象，也会让过期策略持续存在，必须设计清理与版本迁移。
#. 驱动 Reset、Queue 重建、MTU 改变和 Feature 更新可能影响 Native XDP、Buffer Size 和 Zero-copy 能力。
#. XDP Program 必须正确处理 MTU、Multi-buffer Frame 和 Fragment 支持差异，不能假设所有 Frame 单 Buffer。
#. XDP Fragments/Multi-buffer 支持依驱动、Program Flag 和内核版本，未声明支持时大 Frame 可能走不同路径。
#. XDP_DROP 增长但 NIC 无错误，可能是策略正常命中；需要与预期 Flow 和 Map 状态对齐。
#. NIC RX 增长而 XDP Counter 不增长，可能是程序未挂在实际入口、流量走其它设备/Queue 或模式不一致。
#. XDP_REDIRECT 增长而目标无流量，应检查 Map Entry、Queue 绑定、Redirect Error、Flush 和目标 Backpressure。
#. ``bpftool net``、``bpftool prog``、Netlink 和驱动统计可确认 Attach 与部分运行状态，具体字段依版本。
#. ``ethtool -S`` 可能提供 XDP Pass/Drop/Tx/Redirect 与错误计数，名称由驱动定义。
#. Perf 可定位 BPF JIT 与驱动 Poll 成本；BPF Map Counter 用于表达业务 Action 分布。
#. 不能在高包率路径逐包 ``bpf_printk``，它会严重扰动性能并产生不可控日志压力。
#. 调试应优先使用 Per-CPU Counter、采样 Ring Buffer 和受控短时间 Trace。
#. 安全退出应先切换或 Detach Program，停止新 Redirect，再排空目标 Queue/Ring，最后释放 Map、Socket 和 Buffer。
#. 稳定源码阅读顺序是：Driver RX Descriptor → ``xdp_buff`` → BPF Program → Action → PASS skb / DROP Recycle / TX / Redirect → Batch Flush → Buffer 回收。

必背路径
--------

Native XDP 接收：

::

   NIC DMA 写入 RX Buffer
   → NAPI Poll 取得 Descriptor
   → 构造 xdp_buff
   → 执行 XDP Program
   → 根据 Action 转移 Buffer Ownership

   PASS
   → 构造 skb
   → 进入普通网络栈

   DROP
   → 直接回收 RX Buffer

XDP Redirect：

::

   Program 解析 Header
   → 选择 DEVMAP / CPUMAP / XSKMAP Entry
   → bpf_redirect_map 写入目标
   → 返回 XDP_REDIRECT
   → 内核验证目标与 Queue
   → Batch Redirect / Flush
   → 目标设备、CPU 或 AF_XDP 接管 Frame

安全 Header 解析：

::

   读取 data / data_end
   → 验证 Ethernet Header
   → 处理可选 VLAN
   → 验证 IP 最小 Header
   → 按 IHL / Extension Header 推进
   → 验证 L4 Header
   → 读取字段并作出 Action
   → 修改后重算长度/Checksum 合同

模式选择：

::

   查询设备和驱动能力
   → 优先尝试 Native Driver Mode
   → 不支持时决定是否允许 Generic Fallback
   → 需要 SmartNIC 执行时验证 Hardware Offload 限制
   → 确认实际 Attach Mode
   → 用相同流量测 Packet/s、CPU、Drop 和功能差异

安全卸载：

::

   停止控制面策略更新
   → Replace/Detach XDP Program
   → 阻止新的 Redirect
   → 排空 DEVMAP/CPUMAP/XSKMAP 目标
   → 等待在途 Batch 和 Queue 完成
   → 关闭 Link/fd 并取消 Pin
   → 释放 Map 与用户态 Buffer

必须区分
--------

* ``xdp_buff`` 与 ``sk_buff``：前者表示早期 RX Frame；后者承载完整网络栈元数据和协议路径。
* Native XDP 与 Generic XDP：Native 在驱动 skb 前路径执行；Generic 已进入 skb 路径，兼容性和成本不同。
* ``XDP_DROP`` 与 Netfilter Drop：XDP Drop 发生得更早，后续抓包、规则计数和 Socket 通常看不到。
* ``XDP_TX`` 与普通 TX：XDP TX 从入口设备快速发回，不经过完整 Socket、qdisc 和协议发送语义。
* Redirect Action 与目标完成：返回 Redirect 只是选择路径；目标 Queue、Ring 和设备仍可能拒绝或丢弃。

一句话结论
----------

XDP 用 ``xdp_buff`` 和受验证 BPF 程序把 Packet 决策前移到 skb 之前；性能来自更早终止路径，正确性取决于边界检查、Action 所有权和目标 Backpressure 全部成立。
