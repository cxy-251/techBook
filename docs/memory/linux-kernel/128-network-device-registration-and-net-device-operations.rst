第128章：网络设备注册与 net_device 操作
========================================

本章必须记住
------------

#. 网络设备向内核暴露的是 packet、队列和链路状态，不是普通字节流或块地址空间。
#. ``struct net_device`` 是网络接口对象，连接接口名、MTU、MAC、feature、队列、NAPI、统计和驱动操作表。
#. ``struct net_device_ops`` 是网络核心调用驱动的主回调表；ethtool、XDP、tc 等能力还有各自接口。
#. 驱动私有对象通常通过 ``netdev_priv()`` 与 ``net_device`` 一同分配和定位。
#. 常见注册路径是 ``alloc_etherdev_mqs()``/``alloc_netdev_mqs()`` → 初始化 → ``register_netdev()``。
#. ``register_netdev()`` 成功后接口立即对用户态和网络栈可见，全部回调、队列和同步状态必须已经可用。
#. ``unregister_netdev()`` 撤销接口并收束网络核心使用；``free_netdev()`` 才释放对象存储。
#. 接口对象存在、接口 administratively up、carrier up 和数据面可用是四个不同状态。
#. 用户执行 ``ip link set dev up`` 通常触发 ``ndo_open``；设置 down 或注销通常触发 ``ndo_stop``。
#. ``ndo_open`` 的稳定职责是建立运行期 ring、IRQ、NAPI、硬件队列和接收 buffer，再启动设备。
#. ``ndo_stop`` 必须停止新发送、关闭硬件中断源、停用 NAPI、排空 TX/RX，并释放运行期资源。
#. ``netif_carrier_on/off`` 表达物理或逻辑链路状态，不替代接口 up/down 和发送队列停启。
#. 多队列网卡常有多个 TX/RX ring；队列数、IRQ 数和 CPU 数不必一一相等。
#. Queue mapping、RSS、RPS/RFS、XPS、IRQ affinity 和 NUMA 共同决定 packet 处理位置，具体机制具有版本差异。
#. 发送路径的驱动入口是 ``ndo_start_xmit(struct sk_buff *skb, struct net_device *dev)``。
#. ``sk_buff`` 保存 packet 数据引用和协议元数据，驱动不能只按 ``skb->data`` 的线性区解释整个包。
#. SKB 可以包含线性 head、page fragments、GSO 分段信息、checksum 状态和 VLAN 元数据。
#. 驱动声明某项 offload feature 后，就必须正确处理对应 skb 元数据，不能把未支持的 packet 交给硬件。
#. 发送前应确认 TX ring 空间；空间不足时先停止对应 subqueue，避免网络核心继续提交。
#. 驱动返回 ``NETDEV_TX_OK`` 表示已经消费并接管 skb，之后必须由 completion 路径释放它。
#. 返回 ``NETDEV_TX_BUSY`` 表示 skb 未被消费，网络核心仍拥有它；驱动不能同时保存或释放该 skb。
#. 正常设计应通过提前停止队列使 ``NETDEV_TX_BUSY`` 很少出现，而不是把它当作常规背压机制。
#. TX DMA mapping 必须覆盖 skb 线性区和 fragments，并保存每个 mapping 供完成时解除。
#. DMA mapping 失败时，驱动应按 packet 丢弃/错误合同处理，并保证 skb 与已映射 segment 不泄漏。
#. 填写 TX descriptor 后，需要在发布 owner/valid 位和 doorbell 前满足设备规定的内存顺序。
#. Doorbell 写入通常是 MMIO；描述符内存可见性与 MMIO posted write 是不同顺序问题。
#. TX completion 由 IRQ、NAPI poll 或其它 poll 路径回收已发送 descriptor、unmap DMA 并释放 skb。
#. 只有设备已不再访问 buffer 后才能解除 DMA mapping 和释放 skb。
#. TX completion 应推进 consumer 指针并在 ring 空间恢复后唤醒已停止的 subqueue。
#. Queue stop/wake 必须防止“检查空间后被 completion 并发修改”的竞态，常用锁或原子顺序协议。
#. ``ndo_tx_timeout`` 表示 watchdog 发现队列长时间无进展，驱动应诊断并进入受控 reset，而不是只增加计数。
#. Reset 路径必须与正常 TX completion 串行化，并防止旧 descriptor completion 命中新 generation。
#. 接收路径通常由驱动预先向 RX ring 提供可供设备 DMA 写入的 buffer。
#. RX buffer 可以来自 page pool、page fragment、skb 或驱动专用池，具体实现随设备和内核版本变化。
#. 设备写入 packet 后触发 IRQ；IRQ handler 通常屏蔽/确认队列中断并调度 NAPI，不在硬中断中处理全部包。
#. NAPI 把高负载接收从每包中断转换成受 budget 限制的批量 poll，降低中断风暴和调度开销。
#. ``napi_schedule*()`` 只调度 poll；驱动必须保证同一 NAPI 实例的所有权和 IRQ 屏蔽顺序正确。
#. NAPI poll 读取 RX descriptor，完成 DMA 同步/解除映射，构造 skb，设置协议和 checksum/offload 元数据。
#. 驱动把 packet 交给 ``napi_gro_receive()``、``netif_receive_skb()`` 等网络核心入口后，通常失去 skb 所有权。
#. GRO 可以在进入协议栈前合并兼容 packet，减少每包固定成本；驱动只应提供准确元数据。
#. Poll 返回处理 packet 数；当工作未完成且达到 budget 时保持 NAPI 调度，不应过早重新启用中断。
#. 当 ring 已处理完且 ``napi_complete_done()`` 成功结束 poll 后，驱动才重新启用对应中断。
#. IRQ 与 NAPI 完成之间必须防止丢失事件：完成检查、重启中断和设备状态读取需按硬件协议设计。
#. 同一 NAPI 实例可以服务一个或多个队列，稳定身份应从驱动队列对象与 IRQ 关系确认。
#. NAPI disable 会等待当前 poll 结束并阻止后续 poll，remove/stop 中仍需先停止设备产生新数据。
#. ``napi_disable()`` 不自动停止 DMA；硬件、ring、IRQ 和 buffer 生命周期仍由驱动收束。
#. RX ring refill 失败会造成 packet drop 或 ring 饥饿，驱动应记录并安排恢复，不能使用已释放 descriptor。
#. Page pool 能优化 RX 页复用和 DMA 生命周期，但必须遵守池、页面和设备 teardown 顺序。
#. XDP 在较早 RX 阶段执行，可 PASS、DROP、TX 或 REDIRECT；支持它会增加 buffer ownership 和 completion 分支。
#. XDP redirect 后 buffer 所有权转交目标路径，驱动不能按普通 RX completion 立即回收。
#. 网络接口可以移动到 network namespace；接口名和 ifindex 的可见性具有 namespace 语义。
#. 驱动硬件对象通常属于全局设备模型，``net_device`` 用户可见接口则受网络命名空间管理。
#. 用户态 close socket 不等于网络设备没有在途 skb；协议栈、qdisc、邻居和驱动队列可能继续持有 packet。
#. ``unregister_netdev()`` 会与网络核心同步并撤销接口，但驱动仍需完成硬件 DMA、IRQ、NAPI 和 worker teardown。
#. 安全 remove 应先阻止上层新 packet，再 unregister，随后停止硬件和排空 descriptor，最后 free netdev。
#. 物理设备突然消失时，应立即设置 disconnected 状态，使 netdev 回调不再访问 MMIO，并失败在途 packet。
#. ``netif_device_detach()`` 等接口可参与停止网络核心提交，精确用法应按目标驱动模型验证。
#. 统计计数可能在多个 CPU/队列更新，应使用 per-CPU 统计和 ``u64_stats_sync`` 等合适协议避免 tearing。
#. ``ndo_get_stats64`` 应提供一致且单调可解释的统计，不能在读取中重置硬件计数而破坏并发。
#. 接口 drop、硬件 error、队列 busy、DMA map 失败和协议栈 drop 是不同层级，统计应尽量准确归类。
#. ``ethtool -S`` 可提供驱动/硬件私有队列统计；字段不是跨驱动稳定 ABI，解释需结合驱动版本。
#. ``ip -s link``、``/proc/interrupts``、sysfs queue、ethtool 和 tracepoint 应按同一接口/队列/CPU 对齐。
#. TX 卡死分析应按 qdisc → subqueue 状态 → ``ndo_start_xmit`` → descriptor → DMA → doorbell → completion 追踪。
#. RX 丢包分析应按硬件计数 → RX ring → refill → IRQ → NAPI budget → GRO/协议栈 → socket queue 追踪。
#. 高 IRQ 不自动表示网卡故障，可能是中断 moderation、NAPI budget、队列映射或流量模式不匹配。
#. 高 softirq CPU 也不自动表示驱动慢，应区分驱动 poll、GRO、协议栈、netfilter 和 socket 处理。
#. 动态 MTU、feature 和 channel 数变更可能要求停止接口并重建 ring，不能只改 ``net_device`` 字段。
#. Runtime PM 必须证明接口和硬件队列空闲；设备对象存在不表示硬件当前处于可访问电源状态。
#. 精确 ``net_device_ops`` 字段、NAPI helper、page_pool 和 XDP API 具有版本差异；稳定模型是 netdev 发布 packet 接口，驱动用 DMA ring 与网络核心转移 skb 所有权。

必背路径
--------

网络设备注册：

::

   Bus probe 取得硬件资源
   → 分配 net_device 与私有对象
   → 设置 net_device_ops、ethtool_ops、MTU、features
   → 初始化 TX/RX queue、NAPI、锁和统计
   → 设置硬件地址与队列数量
   → register_netdev
   → 接口进入网络命名空间并对用户可见
   → 用户设置 up 时调用 ndo_open

TX：

::

   Socket/协议栈生成 skb
   → qdisc 与队列选择
   → ndo_start_xmit
   → 检查 TX ring 空间
   → DMA map skb head/frags
   → 填写 descriptor 和 offload 元数据
   → 内存屏障后发布 descriptor
   → 写 doorbell
   → 设备发送并产生 completion
   → unmap DMA、释放 skb、唤醒 subqueue

RX 与 NAPI：

::

   驱动向 RX ring 提供 buffer
   → 设备 DMA 写入 packet
   → IRQ 确认事件并屏蔽队列中断
   → 调度 NAPI
   → poll 批量读取 descriptor
   → 同步 DMA 并构造 skb
   → 设置 protocol/checksum/VLAN 元数据
   → napi_gro_receive 交给协议栈
   → refill RX ring
   → 工作耗尽后完成 NAPI 并重启中断

接口停止与移除：

::

   设置 stopping/disconnected
   → 停止网络核心新发送
   → unregister_netdev / ndo_stop
   → 停止硬件 TX/RX 和 DMA
   → 屏蔽并同步 IRQ
   → napi_disable 等待 poll 结束
   → 失败或回收全部 TX skb 与 RX buffer
   → 释放 ring、DMA、IRQ 和硬件资源
   → free_netdev

诊断 TX 卡死：

::

   确认 carrier、接口状态和 qdisc
   → 检查 subqueue 是否停止
   → 检查 ndo_start_xmit 返回与 ring producer
   → 检查 DMA map 和 descriptor owner
   → 检查 doorbell 与硬件 consumer
   → 检查 IRQ/NAPI completion
   → 检查 timeout/reset 与旧 generation
   → 对齐 ethtool、trace 和硬件统计

必须区分
--------

* ``net_device`` 与硬件总线设备：Netdev 表示网络接口；PCI/USB/platform device 表示承载它的硬件实例。
* 接口 Up 与 Carrier Up：Up 表示管理状态已启动；carrier 表示链路可用，二者独立变化。
* ``NETDEV_TX_OK`` 与 ``NETDEV_TX_BUSY``：OK 表示驱动消费 skb；BUSY 表示 skb 仍归网络核心，驱动不能释放或保存它。
* IRQ 与 NAPI：IRQ 快速确认并调度；NAPI 在 poll 中批量处理 packet 和完成队列。
* NAPI Disable 与 DMA Stop：Disable 收束 poll；硬件仍需单独停止 DMA 和中断源。
* 接口注销与对象释放：Unregister 撤销网络栈入口；ring、硬件资源和 netdev 存储还需按引用与 teardown 顺序释放。

一句话结论
----------

网络驱动用 ``net_device`` 向协议栈发布 packet/queue 接口，用 TX/RX DMA ring 和 NAPI 转移 ``sk_buff`` 所有权，并必须在队列背压、reset 和热拔插中完整收束每个 packet。
