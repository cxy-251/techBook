第143章：网络栈中的接收路径与发送路径
====================================

本章必须记住
------------

#. 网络性能和丢包首先是“Packet 在哪里排队、工作在哪个上下文执行”的问题。
#. RX 主线是：NIC → DMA buffer → RX ring → IRQ/NAPI → skb → 协议分发 → IP/TCP/UDP → socket queue。
#. TX 主线是：用户 send → socket/协议队列 → IP/routing → qdisc → netdev queue → driver TX ring → NIC → completion。
#. RX 和 TX 都以 skb 为核心传递对象，但驱动 ring、协议队列和 socket 队列是不同所有者。
#. 设备通过 DMA 把 RX frame 写入驱动准备的 buffer，CPU 不应在设备拥有期间读取或复用该 buffer。
#. RX completion descriptor 通常携带长度、错误、checksum、VLAN、RSS hash 等硬件结果。
#. IRQ 主要用于通知和调度，实际批量收包通常在 NAPI poll 中完成。
#. NAPI 把高包率下的“每包中断”转换成中断触发加预算轮询，降低中断风暴和上下文切换。
#. NAPI instance 由 ``struct napi_struct`` 表示，通常关联一个或多个 RX/TX queue。
#. 驱动硬中断 handler 常先确认事件、mask/ack 设备中断，再调度 NAPI。
#. NAPI 已被调度时，后续同类中断可保持屏蔽，由 poll 继续处理队列。
#. Poll 收到 ``budget``，RX packet 消耗预算；驱动必须按 API 合同返回已处理工作量。
#. 队列仍有工作且预算耗尽时，NAPI 保持调度，后续 softirq/线程继续处理。
#. 队列已排空时，驱动调用 complete helper，并按正确顺序重新打开设备中断。
#. Poll 与中断重新启用存在竞态；必须防止“刚判空后新包到达却没有再次通知”。
#. NAPI poll 可能同时回收 TX completion，TX completion 通常不消耗 RX budget，具体驱动实现有差异。
#. RX 驱动从 descriptor 取得 buffer 后，需要执行 DMA sync/unmap 或 page-pool 规定的 ownership 转换。
#. 构造 skb 时可复制小 packet 到线性区，也可把 page fragment 附加到 skb 以减少复制。
#. ``build_skb``、page pool、XDP、GRO 等路径会改变 buffer 构造与回收方式，属于驱动/版本敏感实现。
#. 驱动必须设置 ``skb->dev``、``protocol``、长度、checksum、VLAN/hash 等后续路径所需元数据。
#. 错误 frame 应在驱动或协议规定的位置丢弃，并更新对应统计，不能交给上层后再静默损坏。
#. XDP 若启用，会在构造普通 skb 前处理 packet，并可 DROP、PASS、TX、REDIRECT。
#. XDP_PASS 后 packet 才继续转换为 skb；XDP_DROP 不会进入普通协议栈。
#. ``napi_gro_receive()`` 一类入口允许 GRO 检查并聚合兼容流。
#. GRO 把多个收到的 segment 聚合成较大 skb，减少协议层每包固定开销。
#. GRO 不表示网卡收到一个超大 wire frame，也不改变远端按合法 segment 发送的事实。
#. 聚合后的 skb 仍要保留 checksum、长度、分段边界和协议兼容性信息。
#. Packet 进入 core receive path 后，可能经过 packet tap、VLAN、bridge、tc、Netfilter、routing 或本地协议分发。
#. ``skb->protocol``、入口设备、network namespace 和 hook 结果共同决定后续分支。
#. 本机目标 packet 最终进入 TCP/UDP 等协议输入，再按四元组/端口查找目标 socket。
#. 协议将数据排入 socket receive queue 或协议私有结构后，更新内存记账并唤醒读取者。
#. Socket receive queue 满、协议内存压力或应用读取过慢都可能导致 RX drop 或反馈窗口收缩。
#. RX ring 丢包、softnet backlog 丢包、协议丢包和 socket queue 丢包属于不同层级。
#. 网卡统计中的 ``rx_dropped`` 不自动包含所有内核协议层 drop，字段语义依驱动和工具。
#. ``/proc/net/softnet_stat``、设备统计、协议 SNMP 计数和 socket drop 需要按时间窗口交叉判断。
#. RX packet 在某 CPU 上进入，不保证应用最终在同一 CPU 运行。
#. RSS、RPS、RFS、IRQ affinity、NAPI 与应用 CPU 亲和性共同影响 cache locality。
#. RSS 是设备侧多队列/hash 分流；RPS 是软件接收 CPU 分流；二者不是同一种机制。
#. 多队列设备性能依赖 RX queue、IRQ vector、NAPI、CPU 和 NUMA 内存位置是否匹配。
#. 单个队列过载时，增加全局 CPU 不一定有帮助；必须确认 packet 是否真正分散到多个队列。
#. TX 从 socket send 开始，协议首先检查连接状态、发送内存和阻塞/非阻塞语义。
#. TCP send 会把用户字节纳入发送队列，并受 MSS、接收窗口、拥塞窗口、Nagle、pacing 和内存限制影响。
#. UDP send 保留数据报边界，但仍需要 socket memory、路由、IP 头、checksum 和设备发送路径。
#. 用户一次 send 不保证对应一个 skb；一个 skb 也不保证对应一个 wire packet。
#. IP 层选择输出路由、源地址、MTU、下一跳和输出设备，并可能执行 fragmentation/PMTU 处理。
#. Routing 成功不表示邻居解析完成，也不表示 Netfilter 允许 packet 继续。
#. 本地发送通常经过 LOCAL_OUT 与 POST_ROUTING 等 hook；转发 packet 的 hook 顺序不同。
#. qdisc 是 netdev 发送前的软件排队与调度层，可分类、限速、重排和丢弃 skb。
#. ``dev_queue_xmit()`` 一类入口把 skb 交给 qdisc 或直接发送路径，精确函数组织具有版本差异。
#. 无队列或特定快速路径不表示没有任何排队，socket、协议、设备 ring 仍可排队。
#. 多队列 netdev 根据 skb hash、queue mapping、XPS 或驱动策略选择 TX queue。
#. XPS 用于引导发送 CPU 与 TX queue 关系，目标是降低锁竞争和 cache 迁移。
#. Byte Queue Limits 根据 completion 反馈控制驱动层允许排队的字节，减少设备 ring 过度缓冲。
#. qdisc backlog、netdev queue stopped 和驱动 TX ring full 是不同排队状态。
#. 驱动 ``ndo_start_xmit`` 被调用时，skb ownership 由返回合同决定。
#. ``NETDEV_TX_OK`` 表示驱动接管 skb；驱动最终在 completion 或错误路径释放。
#. ``NETDEV_TX_BUSY`` 表示未接管 skb，驱动不应释放或破坏该 skb；频繁 BUSY 通常说明驱动队列管理有问题。
#. 正常驱动应在 ring 空间不足前停止 netdev queue，而不是接收 skb 后再频繁返回 BUSY。
#. 驱动把 skb 线性区和 frags 映射为 DMA segment，填写 descriptor 并写 doorbell。
#. Scatter-gather、checksum offload、TSO、VLAN 和 tunnel offload 决定 descriptor 形态和软件 fallback。
#. 映射失败时必须回滚已成功 segment，不能把部分 descriptor 发布给硬件。
#. Descriptor 全部准备和 DMA mapping 完成后，先通过 barrier 发布内容，再更新 owner/producer，最后敲 doorbell。
#. Doorbell 到达设备不表示 packet 已发出；真正回收要等 TX completion。
#. TX completion 负责确认 descriptor 不再被设备使用、解除 DMA mapping、释放 skb 并归还 ring 空间。
#. 只提交不回收会让 TX ring 最终填满，netdev queue 长期停止并造成应用发送阻塞。
#. TX interrupt moderation 与 NAPI completion 批量回收可以提高吞吐，也会增加完成延迟。
#. TSO 让设备把一个大 TCP skb 分成多个 segment；GSO 是软件通用分段框架。
#. GSO skb 的 ``len`` 可远大于 MTU，进入不支持对应 feature 的设备前必须软件分段。
#. Hardware feature 检查发生在 core/driver 边界，设备 capability 与 skb 请求必须匹配。
#. UFO 等部分旧 offload 已发生演进，精确 feature 应按目标内核与设备确认。
#. GRO 是 RX 聚合，GSO/TSO 是 TX 分段；二者方向和时点不同。
#. Checksum offload 只移动校验工作，不自动验证整个 packet 的协议正确性。
#. TX ``CHECKSUM_PARTIAL`` 表示设备需要从指定位置完成校验；驱动必须正确传递 metadata。
#. RX ``CHECKSUM_UNNECESSARY`` 表示硬件/前层已验证适用校验，不表示 packet 的所有外层与内层校验都已验证。
#. 隧道 packet 可能有 outer/inner checksum 和 segmentation，feature 不匹配会触发软件处理。
#. Offload 降低 per-packet CPU，也会让抓包点看到与 wire 不同的 packet 粒度。
#. 发送侧 tcpdump 看到超大 skb 可能是尚未 TSO/GSO 分段；接收侧看到大 skb 可能是 GRO 结果。
#. 关闭 offload 可用于诊断，但会显著改变 CPU、队列和时序，不能把结果直接外推到原配置。
#. Packet drop 必须先定位层级，再解释原因。
#. RX driver drop 常来自 descriptor error、buffer shortage、ring overflow 或 DMA/length 问题。
#. NAPI/softnet drop 常来自 CPU 无法按时处理 backlog 或预算压力。
#. 协议层 drop 可来自 checksum、长度、路由、socket lookup、内存和状态校验。
#. Netfilter drop 是规则 verdict；qdisc drop 是排队/策略行为；驱动 TX drop 是 ring/DMA/hardware 路径。
#. 同一个 packet 可能被 clone 到 tap 后主路径再 drop，因此抓包看到 packet 不证明最终交付。
#. 抓包点位于协议栈特定位置，可能看不到 XDP drop、硬件早期 drop 或某些 offload 后的实际 wire 形态。
#. ``ethtool -S`` 提供驱动/硬件队列统计，字段名和含义由驱动定义。
#. ``ip -s link`` 给出聚合 netdev 统计，不能替代队列级硬件计数。
#. ``tc -s qdisc`` 用于观察 qdisc backlog、drop、overlimit 和 requeue。
#. ``ss`` 用于观察 socket queue、TCP 状态和拥塞信息，不能说明 packet 在驱动 ring 的位置。
#. Ftrace/eBPF 可连接 NAPI、netif receive、qdisc、xmit 和 kfree/drop 事件，事件名随版本演进。
#. Perf 用于定位 CPU 花在驱动、softirq、GRO、协议、qdisc 或 copy 的位置。
#. 软中断 CPU 高不自动等于网卡过载，也可能来自单队列 affinity、GRO 关闭或规则路径过重。
#. 网络延迟要拆分 socket 排队、协议处理、qdisc 排队、驱动排队和设备/链路时间。
#. 吞吐优化要同时看 packets/s、bytes/s、CPU/packet、batch、queue depth 和 P99 latency。
#. 增大 ring 或 backlog 可能减少短时 drop，也可能增加 bufferbloat 和尾延迟。
#. 调整 interrupt coalescing 可能降低 CPU，也可能增加小流延迟。
#. 调整 NAPI weight、RPS/XPS、RSS queue 数和 affinity 必须逐项实验，避免无法归因。
#. 设备 remove/reset 时，先停止上层 queue 与 NAPI 新调度，再停止 DMA/IRQ，回收所有 skb 和 mapping。
#. ``napi_disable()`` 等待 poll 退出，不自动停止设备继续 DMA 或写 descriptor。
#. ``netif_tx_disable``/queue stop 与硬件 DMA stop 也是不同层级。
#. 稳定源码阅读顺序是：RX/TX ring → NAPI/queue → skb 构造 → core network → protocol/qdisc → driver xmit/completion → drop/释放。

必背路径
--------

RX 主路径：

::

   NIC 收到 frame
   → DMA 写入 RX buffer
   → 更新 RX completion descriptor
   → 触发 IRQ
   → 驱动 mask/ack 并调度 NAPI
   → NAPI poll 批量读取 descriptor
   → DMA sync / ownership 转移
   → 构造 skb 并设置 metadata
   → XDP/GRO/core receive
   → L2/IP/TCP/UDP
   → Socket receive queue
   → 唤醒应用 recv/epoll

TX 主路径：

::

   应用 send
   → Socket 与协议发送队列
   → TCP/UDP 构造 skb
   → IP route / Netfilter / neighbor
   → qdisc 排队与调度
   → 选择 netdev TX queue
   → ndo_start_xmit
   → DMA map skb head/frags
   → 填写 TX descriptor 并 doorbell
   → NIC 发送
   → TX completion
   → unmap DMA、释放 skb、唤醒 queue

NAPI 完成：

::

   IRQ 调度 NAPI 并屏蔽队列中断
   → poll 在 budget 内处理 RX
   → 同时回收 TX completion
   → 队列仍有工作且预算耗尽
   → 保持 NAPI scheduled
   → 队列排空
   → napi_complete_done
   → 按设备协议重新启用 IRQ
   → 处理判空与新事件竞态

定位 TX 停顿：

::

   检查 Socket Send-Q 与 TCP 窗口
   → 检查 qdisc backlog/drop
   → 检查 netdev queue stopped
   → 检查 TX ring free descriptor
   → 检查 DMA mapping 和 doorbell
   → 检查 completion IRQ/NAPI
   → 检查设备错误与链路状态

定位 RX 丢包：

::

   检查硬件/驱动 RX error 与 no-buffer
   → 检查 RX ring fill 和 NAPI budget
   → 检查 softnet backlog/drop
   → 检查 GRO/协议/Netfilter drop
   → 检查 Socket receive queue 与应用读取
   → 按队列、CPU、namespace 对齐时间线

必须区分
--------

* IRQ 通知与 Packet 处理：IRQ 通知有事件；NAPI poll 通常完成批量收发工作。
* GRO 与 GSO/TSO：GRO 在接收侧聚合；GSO/TSO 在发送侧把大 skb 分段。
* qdisc Queue 与 Driver Ring：qdisc 是软件调度队列；TX ring 是驱动与设备共享的执行队列。
* Send 返回与 TX Completion：Send 表示本地接受数据；completion 才允许驱动解除 DMA 并释放 skb。
* 抓包可见与最终交付：抓取点看到 packet 不表示后续未被路由、规则、qdisc 或协议丢弃。

一句话结论
----------

网络收发性能由 packet 在 RX ring、NAPI、协议队列、qdisc、TX ring 和 socket queue 中的排队位置决定；先定位队列和执行上下文，再谈 offload、CPU 或设备优化。
