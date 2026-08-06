第154章：Zero-copy 路径与 AF_XDP
===============================

本章必须记住
------------

#. AF_XDP 把 XDP 的早期 Packet 决策与用户态共享 Buffer/Ring 连接起来，适合需要 Raw Frame 和自管 Pipeline 的高包率场景。
#. AF_XDP 的核心不是 Socket API 名称，而是 UMEM Frame、四类 Ring、XSKMAP 和设备 Queue 之间的所有权协议。
#. Zero-copy 的稳定定义是尽量让 Packet Payload 留在同一块可 DMA、可由用户态访问的内存中，跨边界传递 Descriptor。
#. Zero-copy 不表示没有 Descriptor Copy、Cache Miss、系统调用、DMA Mapping、同步或用户态处理成本。
#. 普通 Socket RX 常经历 NIC DMA → skb → 协议栈 → Socket Queue → Copy to User；AF_XDP 尝试绕开 skb/Socket Copy 主线。
#. 绕开普通协议栈也意味着应用不自动获得 TCP、Routing、Netfilter、Socket Buffer 和拥塞控制语义。
#. AF_XDP Socket 常称为 XSK，绑定到一个 Netdev 和 RX/TX Queue ID。
#. UMEM 是用户态分配并注册给内核的 Packet Buffer 区域，通常划分成固定 Chunk/Frame。
#. Frame Address 是 UMEM 内偏移语义，不应与普通虚拟地址、物理地址或 DMA Address 混为一谈。
#. 内核和驱动根据 UMEM 注册、Queue 和 DMA 模型把 Frame 转换成设备可访问的 Buffer。
#. ``struct xdp_desc`` 主要描述 UMEM Address、Packet Length 和 Options；实际 Payload 保留在 UMEM Frame。
#. FILL、RX、TX、COMPLETION 四类 Ring 表达 Frame 所有权转移。
#. FILL Ring 由用户态生产、内核消费，条目是可用于接收 Packet 的空 Frame Address。
#. RX Ring 由内核生产、用户态消费，条目是已接收 Packet 的 ``xdp_desc``。
#. TX Ring 由用户态生产、内核消费，条目是待发送 Packet 的 ``xdp_desc``。
#. COMPLETION Ring 由内核生产、用户态消费，条目表示某个 TX Frame 已完成并可被用户态回收。
#. FILL/COMPLETION 通常属于 UMEM 维度；RX/TX 属于具体 XSK 维度，Shared UMEM 时必须按实际 API 组织。
#. 四个 Ring 按单生产者/单消费者模型设计；多个线程访问同一 Producer 或 Consumer 必须由应用额外同步。
#. Ring 是有界队列，不检查容量就推进 Producer 会覆盖未消费条目并破坏所有权。
#. 用户态读取 Consumer/Producer Index 后应按 AF_XDP API 或 libxdp/libbpf Helper 遵守 Acquire/Release 顺序。
#. 直接实现 Ring 操作时，Descriptor 内容必须先写完再发布 Producer；Consumer 必须先看见发布再读取内容。
#. RX Frame 的标准所有权链是 User Free → FILL → Kernel/Device RX → RX Ring → User Processing → FILL。
#. TX Frame 的标准所有权链是 User Free → User Builds Packet → TX Ring → Kernel/Device TX → COMPLETION → User Free。
#. Frame 写入 FILL 后，用户态不能继续修改或读取为当前业务对象，直到该 Frame 经 RX Ring 返回。
#. Frame 写入 TX 后，用户态不能提前复用，直到 COMPLETION 表明设备路径不再访问它。
#. RX Descriptor 被消费后，应用不能无限持有 Frame 而不补充 FILL，否则内核最终没有可接收 Buffer。
#. COMPLETION 不持续消费会让 TX Frame 无法回收，最终耗尽用户态可用 Frame。
#. 同一个 Frame 在同一时刻不能同时位于 FILL、RX、TX、COMPLETION 或用户空闲池中的多个位置。
#. 应用应为每个 Frame 维护明确状态或借助 Ring 所有权推导状态，避免 Double-submit 和 Double-recycle。
#. UMEM Chunk Size、Headroom、Alignment 和 Unaligned Chunk 模式影响有效 Address 与 Packet 容量，精确 ABI 具有版本差异。
#. Frame 必须容纳目标 MTU、Header、可选 Metadata 和驱动要求的 Headroom。
#. MTU 或 XDP Headroom 改变后，原 UMEM 布局可能不再满足 Native/Zero-copy 路径要求。
#. XSK 绑定需要指定 ifindex、Queue ID 和 Flags；Queue 必须真实存在且由目标设备支持。
#. 一个 XSK 通常接收与它绑定的 Queue 流量，RSS、Flow Steering 和队列配置决定哪些 Packet 到达该 Queue。
#. AF_XDP Socket 创建成功不表示任何 Packet 会进入 RX Ring，还需要正确 XDP Redirect。
#. XSKMAP 是 BPF Map，用索引关联 AF_XDP Socket，XDP Program 通过 ``bpf_redirect_map()`` 选择目标。
#. 典型做法用 ``ctx->rx_queue_index`` 作为 XSKMAP Key，使 Queue n 的 Packet 进入绑定 Queue n 的 XSK。
#. XSKMAP Entry、XSK 绑定设备和 Queue 不一致时，Redirect 可能失败或 Drop。
#. XDP_REDIRECT Counter 增长不表示 RX Ring 一定收到 Descriptor，后续仍受 Map、FILL、RX Ring 和驱动路径约束。
#. Redirect Batch 通常需要在 NAPI 轮询末尾 Flush，具体核心/驱动接口具有版本差异。
#. FILL Ring 没有 Frame 时，内核无法为 AF_XDP RX 提供目标 Buffer，Packet 可能 Drop。
#. RX Ring 满时，内核无法发布新的 Descriptor，Packet 也可能 Drop。
#. 用户态处理慢会同时表现为 RX Ring 积压、FILL Frame 归还减少和硬件/Redirect Drop 增长。
#. Copy Mode 与 Zero-copy Mode 是不同数据路径，AF_XDP API 可用不表示驱动支持真正 Zero-copy。
#. Copy Mode 可由内核在普通驱动 Buffer 与 UMEM 之间复制 Payload，兼容性较高，Copy 成本仍存在。
#. Zero-copy Mode 要求驱动和 Queue 支持 XSK Buffer Pool/UMEM 直接进入 RX/TX DMA 路径。
#. ``XDP_ZEROCOPY`` 可要求绑定必须使用 Zero-copy，不支持时失败；``XDP_COPY`` 可要求 Copy Mode，精确 Flags 以目标 UAPI 为准。
#. 未强制模式时，内核可能根据能力选择模式；应用必须读取 Options/运行状态确认实际模式。
#. Zero-copy 支持往往依赖具体驱动、Queue 配置、MTU、Chunk Size、Headroom 和设备 Feature。
#. 同一网卡不同 Driver Version、PF/VF、Queue 或 Firmware 配置可能有不同 Zero-copy 能力。
#. Zero-copy RX 仍先发生 NIC DMA，区别在于 DMA 目标可以直接是注册的 UMEM Frame。
#. IOMMU 可为 UMEM 页面建立 IOVA，仍不消除 Cache、NUMA 和设备 Descriptor 限制。
#. UMEM 页面长期注册或 Pin 会占用内存并限制迁移、回收和 NUMA 管理。
#. 大 UMEM 能吸收更大 Burst，也会增加驻留内存、TLB、Cache 和初始化成本。
#. UMEM 应尽量分配在处理 Queue 与 NIC 所在 NUMA Node，跨 Node 访问会削弱 Zero-copy 收益。
#. Huge Page 可能减少 TLB 压力，具体收益、对齐和 Pinning 行为需要实测。
#. RX/TX Batch 能摊薄 Ring 同步、系统调用和 Wakeup 成本；Batch 太大会增加等待和尾延迟。
#. AF_XDP 数据面通常通过轮询 Ring 工作，是否调用 ``poll()``、``recvfrom()``、``sendto()`` 或专用 Kick 取决于 Need-wakeup 与驱动模式。
#. ``XDP_USE_NEED_WAKEUP`` 允许 Ring Flags 提示用户何时需要显式唤醒内核，减少无效系统调用。
#. Need-wakeup 为假不表示工作已经完成，只表示当前通常不需额外 Kick。
#. Need-wakeup 语义和最佳实践应以目标内核 AF_XDP 文档和用户库为准。
#. Busy Poll 可以降低调度唤醒延迟，也会持续占用 CPU，必须与 Queue/CPU 隔离和功耗目标结合。
#. 用户态 Worker、NIC IRQ/NAPI 和 UMEM Memory 应尽量在同一 CPU/NUMA 拓扑上形成局部路径。
#. 过多 Worker 共享一个 Ring 不会增加 SPSC Ring 并行，反而需要锁并破坏 Cache Locality。
#. 多 Queue 扩展通常采用每 Queue 一个 XSK、一个 Worker 和独立 UMEM/Frame Pool，具体共享策略需按内存目标设计。
#. Shared UMEM 可减少重复注册和内存，但 FILL/COMPLETION Ring 所有权与多 Socket 协调更复杂。
#. TX Packet 必须由应用自行构造合法 Ethernet/IP/L4 Header、Length 和 Checksum，除非路径明确提供相应 Offload。
#. AF_XDP TX Offload 能力与普通 Netdev TX Feature 不完全相同，应按 XDP/Driver 文档验证。
#. TX Descriptor 发布不等于 Packet 已上线；COMPLETION 才表示 Frame 可回收。
#. COMPLETION 也不表示远端收到，只表示本地发送路径完成约定的 Buffer 使用。
#. Packet 被 Redirect 到 AF_XDP 后不会同时自动进入普通协议栈，除非程序 Clone/多路径设计明确实现。
#. XDP_PASS 与 XSK Redirect 的流量分类错误会造成业务流消失或重复处理，必须按 Action Counter 验证。
#. AF_XDP 没有普通 Socket 的自动 Backpressure 语义；Ring 满和 Frame 耗尽通常直接表现为 Drop 或提交失败。
#. 应用必须主动限制处理管线、下游队列和 TX 在途数，不能依赖无限 Buffer。
#. Ring Reserve 返回空间不足时应停止生产、先消费对端进度或执行明确 Drop 策略。
#. Ring Peek 没有 Descriptor 时应按轮询、睡眠或 Need-wakeup 策略等待，不能把空 Ring 当成连接结束。
#. 用户态退出前必须停止 XDP Redirect，否则内核仍可能向即将销毁的 XSK/UMEM 路径发送 Frame。
#. 安全 teardown 顺序是 Replace/Detach Redirect → 从 XSKMAP 删除 Entry → 排空 RX/TX/Completion → 回收所有 Frame → 关闭 XSK → 解除 UMEM 注册。
#. 关闭 XSK fd 不自动保证用户业务状态中的所有 Frame 已归还，应用仍需核对 Frame 状态总数。
#. UMEM 释放前必须确保内核、驱动和设备不再 DMA 访问对应页。
#. 设备 Reset、Queue Down、MTU 改变或 XDP Detach 可能中断 AF_XDP 数据面，应用需要处理 Poll Error 和重新绑定。
#. XSKMAP 可继续持有对已关闭 Socket 的状态变化，具体更新/删除应由控制面显式完成。
#. 观测至少要分别计数 NIC RX、XDP Redirect、Redirect Error、RX Ring Consumed、FILL Produced、TX Submitted 和 COMPLETION Reaped。
#. 只有 NIC Packet 数和应用 Packet 数两个指标，无法定位中间 Drop。
#. ``bpftool map`` 可确认 XSKMAP Entry，``ip``/``ethtool`` 可确认接口和 Queue，应用内部统计负责 Ring/Frame 状态。
#. ``ethtool -S`` 中 AF_XDP/XDP/Queue 字段由驱动定义，不能跨驱动直接比较名称。
#. Perf 可定位 Driver Poll、BPF Program、Ring 操作和用户态 Worker CPU 成本。
#. 优化 AF_XDP 时应一次只改变 Batch、Busy Poll、UMEM Size、Queue Affinity、Zero-copy Mode 或 Worker 数。
#. 稳定源码阅读顺序是：UMEM 注册 → Ring 创建 → XSK Bind → XSKMAP Entry → XDP Redirect → RX/FILL Ownership → TX/Completion Ownership → Wakeup → Teardown。

必背路径
--------

AF_XDP RX：

::

   用户分配并注册 UMEM
   → 把空 Frame Address 写入 FILL Ring
   → XSK 绑定 Netdev + Queue
   → XSKMAP 关联 Queue 与 XSK
   → NIC 收到 Frame
   → XDP Program 返回 REDIRECT
   → 内核取得 FILL Frame
   → Copy 或 Zero-copy 放入 Packet
   → 在 RX Ring 发布 xdp_desc
   → 用户消费并处理 UMEM 数据
   → Frame 重新写回 FILL Ring

AF_XDP TX：

::

   用户从空闲池取得 UMEM Frame
   → 构造合法 Packet
   → 在 TX Ring 发布 xdp_desc
   → 必要时 Kick 内核
   → 驱动/NIC 发送 Frame
   → 内核在 COMPLETION Ring 发布 Address
   → 用户消费 Completion
   → Frame 返回空闲池或 FILL Ring

Frame 所有权检查：

::

   统计总 Frame 数
   = User Free
   + FILL Owned
   + RX Published / User Processing
   + TX In-flight
   + Completion Pending

   任一 Frame 只能属于一个集合
   → 总数不守恒说明 Double-submit、Leak 或状态遗漏

Zero-copy 确认：

::

   查询驱动与 Queue 能力
   → 使用 XDP_ZEROCOPY 要求绑定
   → 检查 Bind 结果与 Options
   → 确认 UMEM/Chunk/MTU 满足要求
   → 对齐 NIC Queue、CPU 和 NUMA
   → 用 CPU/Packet、Copy 热点和吞吐验证

安全退出：

::

   停止业务新 TX
   → 从 XSKMAP 删除目标或切换 XDP Program
   → 阻止新的 RX Redirect
   → 消费 RX Ring 并归还 Frame
   → 等待 TX Completion
   → 确认所有 Frame 状态守恒
   → 关闭 XSK
   → 解除并释放 UMEM

必须区分
--------

* UMEM Address 与 DMA Address：Descriptor 使用 UMEM Offset 语义；设备实际 DMA Address 由内核、驱动和 IOMMU 建立。
* Copy Mode 与 Zero-copy Mode：两者使用相同 AF_XDP 对象模型，Payload 是否在路径中复制不同。
* TX Ring 提交与 TX Completion：提交转移 Frame 所有权；只有 Completion 后用户才能复用。
* RX Ring 空与连接结束：空 Ring 只表示当前没有 Descriptor，不表示设备或 XSK 生命周期结束。
* Payload Zero-copy 与零开销：Ring 同步、Cache、NUMA、轮询、Descriptor 和应用处理仍然存在。

一句话结论
----------

AF_XDP 的 Zero-copy 是一套 UMEM Frame 所有权协议：FILL/RX 管理接收，TX/COMPLETION 管理发送，任何提前复用、Ring 耗尽或 Queue 不匹配都会直接转化为数据损坏或丢包。
