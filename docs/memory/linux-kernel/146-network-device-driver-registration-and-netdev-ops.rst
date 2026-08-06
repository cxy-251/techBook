第146章：网络设备驱动注册与 netdev_ops
======================================

核心知识点
----------

``net_device`` 是网络接口对象
   总线设备说明硬件怎样出现；``struct net_device`` 说明硬件怎样被协议栈当作接口使用，并承载接口名、ifindex、MTU、MAC、队列、Carrier、Feature 与统计。

注册前必须完成全部可见状态
   驱动通常分配 ``net_device`` 与私有空间，设置 ``net_device_ops``、``ethtool_ops``、队列数、地址、Feature、锁和 NAPI。``register_netdev()`` 成功后外部访问可立即发生。

总线生命周期与接口生命周期分层
   Bus ``probe/remove`` 管理硬件对象；``ndo_open/ndo_stop`` 管理接口每次 Up/Down 的运行资源。一个已注册接口可以多次打开和关闭。

``ndo_open`` 建立数据面
   Open 通常启用 RX/TX Ring、NAPI、IRQ、PHY、Firmware、DMA 与发送队列。返回成功前，接口必须具备完整收发条件。

``ndo_stop`` 必须可重复收束
   Stop 先阻止新提交，再停止硬件、DMA、IRQ 和 NAPI，并把 Ring 与状态恢复到可再次 Open 或安全注销的边界。

发送入口遵守 skb 所有权合同
   ``ndo_start_xmit`` 返回 ``NETDEV_TX_OK`` 表示驱动已接管 skb；返回 ``NETDEV_TX_BUSY`` 表示 skb 仍归网络核心。正常背压应依靠 Subqueue Stop/Wake，而非频繁返回 BUSY。

接口状态具有多个维度
   Administrative Up、``netif_running()``、Carrier On、TX Subqueue Stopped 和三层可达性相互独立。接口存在或 Carrier On 都不能证明 IP 通信正常。

多队列是运行期拓扑
   分配的最大队列数、``real_num_tx_queues``、``real_num_rx_queues``、MSI-X 数、RSS、CPU 与硬件 Queue 不必一一相等。

Feature 是跨层能力合同
   ``hw_features`` 表示可配置硬件能力，``features`` 表示当前有效能力，``wanted_features`` 表示期望值。依赖需经 Fix/Set 路径修正并同步到硬件。

统计必须按排队层级解释
   ``ip -s link``、``ethtool -S``、qdisc、协议和硬件计数位于不同层。名称相似不表示同一个 Drop 或错误位置。

注销与释放是两个阶段
   ``unregister_netdev()`` 撤销网络核心入口；``free_netdev()`` 释放对象存储。两者之间仍需收束 NAPI、IRQ、DMA、Work、Timer、Reset 和引用。

关键路径
--------

接口注册：

::

   Bus probe
   → 分配 net_device 与私有对象
   → 设置 parent、MAC、MTU、队列与操作表
   → 初始化 Feature、锁、NAPI 和驱动状态
   → register_netdev
   → Netlink、sysfs 与网络核心可见

接口打开：

::

   用户设置接口 Up
   → ndo_open
   → 准备 RX/TX Ring
   → 申请并启用 IRQ
   → napi_enable
   → 启动 PHY、Firmware 与 DMA
   → 启动发送队列
   → 按真实链路更新 Carrier

发送与背压：

::

   qdisc 交付 skb
   → 选择 TX Subqueue
   → ndo_start_xmit
   → 检查 Ring 空间
   → 接管 skb 并提交硬件
   → Ring 接近满时 Stop Subqueue
   → Completion 回收空间
   → Wake Subqueue

设备移除：

::

   标记 removing
   → 阻止新控制与新发送
   → 停止接口和硬件
   → 收束 NAPI、IRQ、DMA、Work 与 Timer
   → unregister_netdev
   → 释放 Ring 和总线资源
   → free_netdev

概念辨析
--------

* Bus Device 与 ``net_device``：前者表达硬件发现和资源，后者表达网络接口与数据面。
* Administrative Up 与 Carrier On：前者是管理意图，后者是链路状态，均不等于三层连通。
* ``NETDEV_TX_OK`` 与 Packet 已发送：OK 只表示驱动接管 skb，真正完成要等硬件 Completion。
* Feature Enabled 与单个 skb 实际 Offload：接口具备能力不表示当前 Packet 满足使用条件。
* Unregister 与 Final Free：注销撤销入口；最终释放还需等待异步路径和引用结束。

本章结论
--------

``net_device`` 是网络接口的发布、状态与调度边界。驱动必须把可重复 Open/Stop、队列背压、Feature 合同和完整注销顺序统一到同一对象生命周期中。
