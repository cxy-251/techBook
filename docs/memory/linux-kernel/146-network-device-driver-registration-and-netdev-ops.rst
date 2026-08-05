第146章：网络设备驱动注册与 netdev_ops
======================================

本章必须记住
------------

#. ``struct net_device`` 是 Linux 网络核心表示一个网络接口的统一对象。
#. 用户态看到的接口名、ifindex、MTU、MAC、队列、Carrier、统计和 Feature，最终都投影自 ``net_device`` 及其关联对象。
#. PCI、USB、Platform 等总线设备回答“硬件从哪里来”；``net_device`` 回答“硬件怎样成为网络接口”。
#. 驱动私有对象通常保存寄存器、Ring、IRQ、NAPI、PHY、Firmware 与统计；网络核心通过 ``netdev_priv()`` 一类接口关联它。
#. ``alloc_netdev_mqs()``、``alloc_etherdev_mq()`` 等分配接口会同时准备 ``net_device`` 与驱动私有空间，精确 helper 具有版本差异。
#. 分配成功只得到未发布对象；在注册前，驱动必须完成操作表、队列数量、地址、MTU、Feature 和父设备关系初始化。
#. ``net_device_ops`` 是网络核心进入驱动控制面和数据面的主要回调表。
#. ``ndo_open``、``ndo_stop`` 管理接口运行期资源，不等同于总线 ``probe`` 与 ``remove``。
#. 总线 ``probe`` 通常创建并注册接口；用户执行 ``ip link set dev X up`` 时才调用 ``ndo_open``。
#. ``ndo_open`` 常负责启用 Ring、NAPI、IRQ、PHY、DMA 与硬件收发状态。
#. ``ndo_stop`` 必须阻止新发送、停止设备收发、收束 NAPI/IRQ/DMA，并让接口回到可再次打开或安全注销的状态。
#. ``ndo_start_xmit`` 是协议栈把一个 ``skb`` 交给驱动发送的核心入口。
#. ``ndo_start_xmit`` 被调用时，发送队列选择通常已经完成，驱动应处理对应 Subqueue/Ring。
#. 返回 ``NETDEV_TX_OK`` 表示驱动接管了 ``skb``，后续由驱动的完成或错误路径释放。
#. 返回 ``NETDEV_TX_BUSY`` 表示驱动没有接管 ``skb``，不能修改或释放它。
#. 正常背压应在 Ring 即将耗尽前停止 Subqueue，而不是频繁进入 ``ndo_start_xmit`` 后返回 BUSY。
#. ``ndo_set_rx_mode`` 把 Promiscuous、All-multicast 和地址列表变化转换成硬件过滤配置。
#. ``ndo_change_mtu`` 必须验证硬件最大帧、RX Buffer、VLAN、隧道和 Offload 边界。
#. ``ndo_set_mac_address``、``ndo_tx_timeout``、VLAN、TC、BPF/XDP 等回调按驱动能力选择实现，具体成员随版本演进。
#. ``ethtool_ops`` 与 ``net_device_ops`` 角色不同：前者主要提供能力查询、统计和设备参数管理，后者承接网络核心运行操作。
#. ``register_netdev()`` 把已准备好的接口发布到网络核心、Netlink、Sysfs 和 Notifier 视图。
#. ``register_netdev()`` 是取得 RTNL 的便捷接口；已经持有 RTNL 的路径通常使用 ``register_netdevice()``，精确要求以当前源码为准。
#. 注册成功后，用户态和内核其它子系统可能立即访问或打开接口，因此注册是发布屏障，不是普通列表插入。
#. 所有外部可调用操作表、锁、队列数、Feature 和错误回滚状态必须在注册前完成。
#. ``/sys/class/net/<ifname>`` 是 Class 视图，Canonical Device 路径仍可指向对应总线设备。
#. 接口注册状态、Administrative State、Running State 与 Physical Carrier 是不同状态。
#. ``IFF_UP`` 表示用户或管理层要求接口 Up，不证明物理链路可用。
#. Carrier 表示链路层是否具备发送条件，通常由 PHY、Phylink、Firmware 或虚拟后端变化驱动。
#. ``netif_carrier_on()``/``netif_carrier_off()`` 更新网络核心的链路视图并触发相应事件。
#. Carrier On 不表示 IP、路由、邻居或远端连通性正确。
#. Administrative Down 时即使 Carrier 物理存在，数据面也不应正常运行。
#. ``netif_running(dev)`` 通常反映接口是否完成 Open，不等同于 Carrier。
#. TX Queue 的 Stopped/Wake 状态是发送背压，不等同于接口 Administrative Down 或 Carrier Off。
#. 多队列设备需要分别设置分配队列数和实际启用队列数。
#. ``real_num_tx_queues``、``real_num_rx_queues`` 表示网络核心当前使用的队列数量，不能简单等同于硬件最大 Queue 数。
#. 队列数量还受 MSI-X、CPU、Firmware、RSS、SR-IOV 和配置限制影响。
#. 网络核心可根据 Flow Hash、Queue Mapping、XPS、TC 或驱动策略选择 TX Queue。
#. ``netdev_get_tx_queue()`` 一类接口取得某个 Subqueue 的核心状态，驱动 Ring 对象仍由私有结构保存。
#. Feature 是网络栈与驱动之间的能力合同，而不是展示文本。
#. ``hw_features`` 通常表示用户可切换的硬件能力集合；``features`` 表示当前实际启用能力。
#. ``wanted_features`` 表示用户或策略希望启用的集合，最终结果仍需经过依赖修正和驱动设置。
#. ``vlan_features``、``hw_enc_features`` 等集合描述 VLAN 或封装路径可继承的能力，具体字段随版本演进。
#. ``ndo_fix_features`` 可修正互斥或依赖关系；``ndo_set_features`` 把 Feature 变化应用到硬件。
#. ``netdev_update_features()`` 一类路径会重新计算并通知 Feature 变化，不能只改 ``dev->features`` 位图。
#. TSO 通常依赖 Scatter-Gather 与 TX Checksum；关闭底层能力可能连带关闭上层 Feature。
#. 驱动只能声明硬件和路径真实支持的 Feature；错误声明可造成错误校验和、错误分段或数据损坏。
#. ``ethtool -k`` 显示的是当前接口 Feature 视图，不证明某个具体 Packet 一定使用了硬件 Offload。
#. ``ethtool -i``、``ip -d link``、Sysfs 与 Netlink 分别提供驱动、接口和设备层证据，必须放回对象层级解释。
#. 统计信息可以来自核心、驱动、Per-CPU Counter 或硬件寄存器，字段更新方式并不统一。
#. ``ip -s link`` 是聚合网络接口统计；``ethtool -S`` 往往包含驱动和队列私有统计。
#. 计数器名称相似不表示统计位置、丢弃阶段或单位相同。
#. TX Drop 可以发生在 Socket、协议、qdisc、Core、驱动或硬件，不能只看一个接口字段归因。
#. RX Drop 可以发生在硬件 Ring、驱动、XDP、Softnet、协议或 Socket Queue。
#. 注册后的接口由引用、RCU 和 RTNL 等机制保护；不能在外部路径仍可能查找时直接释放 ``net_device``。
#. ``unregister_netdev()`` 撤销接口发布，并在需要时关闭运行接口；它不等于驱动私有异步工作已经自然结束。
#. 注销前后都必须确保新控制操作和新数据提交不再进入即将销毁的硬件状态。
#. 安全退出通常先停止上层 Queue，再停 NAPI/IRQ/DMA 和硬件，再注销接口，最后释放对象。
#. ``free_netdev()`` 只应在接口已经注销且所有相关生命周期条件满足后执行。
#. Device-managed ``net_device`` helper、自动注销和 NAPI 管理接口具有版本差异，不能把某一新版本样例套到旧源码。
#. 驱动 Remove 必须处理接口仍 Up、Carrier 正在变化、Reset Work 在运行、EtHTool 操作并发和 Runtime PM 状态。
#. ``ndo_stop`` 成功后应建立可重复 Open 的初始状态；只支持一次 Up/Down 的驱动生命周期是不完整的。
#. Suspend/Resume 可以保留注册对象，只暂停数据面；Remove 则最终撤销接口对象，两者不能共用不加区分的释放路径。
#. 网络命名空间移动会改变接口所属 ``struct net`` 和用户可见位置，不改变底层硬件父设备。
#. 物理设备通常不能随意跨 Namespace 移动，具体限制由设备类型和驱动决定。
#. 虚拟接口也使用 ``net_device``，因此看到 ``netdev_ops`` 不证明背后一定存在真实 DMA 硬件。
#. Loopback、Veth、Bridge、VLAN、Tunnel 与物理 NIC 共享网络核心对象模型，数据面实现不同。
#. ``rtnl_link_ops`` 用于部分虚拟链路类型的创建和配置，和物理驱动的总线 Probe 路径不同。
#. 排查“接口存在但不能通信”时，应先拆成注册、Admin Up、Carrier、Queue、Route/Neighbor 与设备收发六层。
#. 排查“接口无法 Up”时，应读取 ``ndo_open`` 的第一个失败资源，而不是只看最终 ``ip`` 错误。
#. 排查“修改 MTU/Feature 后断流”时，应确认驱动是否同步重配 Ring、硬件与 Offload 依赖。
#. 排查“注销卡住”时，应检查 RTNL、NAPI、IRQ、Workqueue、Timer、Firmware、Devlink/EtHTool 和未完成 TX。
#. 精确 ``net_device`` 字段、Feature 名称、注册内部函数和锁分工具有内核版本差异。
#. 稳定源码阅读顺序是：总线 Probe → 分配 ``net_device`` → 填回调/能力 → 注册发布 → Open → 收发 Queue → Stop → Unregister → Final Free。

必背路径
--------

网络接口注册：

::

   PCI / USB / Platform Probe
   → 分配 struct net_device 与私有对象
   → 设置 parent、MAC、MTU 与队列数量
   → 设置 netdev_ops / ethtool_ops
   → 设置 hw_features / features
   → 初始化锁、NAPI 和驱动状态
   → register_netdev
   → Sysfs / Netlink / Notifier 可见

接口打开：

::

   ip link set dev X up
   → 网络核心验证状态
   → ndo_open
   → 分配或启用 RX/TX Ring
   → Request/Enable IRQ
   → napi_enable
   → 启动 PHY / Firmware / DMA
   → 启动 TX Queue
   → 根据真实链路更新 Carrier

发送入口：

::

   协议栈生成 skb
   → 选择 net_device 与 TX Subqueue
   → qdisc 出队
   → ndo_start_xmit
   → 驱动确认 Ring 空间
   → 接管 skb 并映射 DMA
   → 提交 Descriptor
   → TX Completion 后释放 skb

Feature 更新：

::

   用户或核心改变 wanted_features
   → 计算与 hw_features 的交集
   → ndo_fix_features 修正依赖
   → ndo_set_features 配置硬件
   → 更新实际 features
   → Netlink / ethtool 显示新状态

设备移除：

::

   设置 removing 并阻止新控制操作
   → 停止 TX Queue 与新提交
   → ndo_stop / 停止硬件
   → 停止 NAPI、IRQ、DMA、Work、Timer
   → unregister_netdev
   → 释放 Ring 和总线资源
   → free_netdev / 最终释放私有对象

必须区分
--------

总线设备与网络接口
   总线对象描述硬件发现和资源；``net_device`` 描述协议栈可使用的接口。

Administrative Up 与 Carrier On
   Up 是管理状态；Carrier 是链路状态，二者都不证明三层连通。

``NETDEV_TX_OK`` 与 Packet 已发送
   OK 只表示驱动接管 skb；真正发送和资源回收要等硬件 Completion。

Feature 声明与实际 Packet Offload
   Feature 表示路径能力；具体 skb 还要满足协议、Header 和设备限制。

Unregister 与 Final Free
   注销撤销接口可见性；最终释放还要等待异步路径和引用结束。

一句话结论
----------

``net_device`` 是网络接口的发布与调度对象，驱动只有把回调、队列、Carrier、Feature 和可重复生命周期全部接入它，硬件才真正成为 Linux 网络接口。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 30，Network Device Drivers, NAPI, Queues, Offloads, and Packet Scheduling；
* AIBook 章节：Chapter 146，Network Device Driver Registration and netdev_ops；
* 源文件：``docs/LinuxK/Part_30_Network_Device_Drivers_NAPI_Queues_Offloads_and_Packet_Scheduling/Chapter_146_Network_Device_Driver_Registration_and_netdev_ops.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_30_Network_Device_Drivers_NAPI_Queues_Offloads_and_Packet_Scheduling/Chapter_146_Network_Device_Driver_Registration_and_netdev_ops.md>`_。