第128章：网络设备注册与 net_device 操作
========================================

核心知识点
----------

网络设备表达 packet 与队列
   ``struct net_device`` 向网络核心发布接口名、MTU、链路地址、feature、队列、统计和操作回调；它不是字符流，也不是块地址空间。

硬件设备与网络接口是不同对象
   PCI、USB 或 platform device 表示承载硬件，``net_device`` 表示网络功能接口。一个硬件实例可以产生多个网络接口或其它功能对象。

注册是可见性边界
   驱动通常分配 netdev 与私有区，设置 ``net_device_ops``、队列、NAPI 和 feature，再调用 ``register_netdev()``。成功后用户态和协议栈可以立即访问。

接口状态分为多个维度
   对象已注册、administratively up、carrier up 和数据面可用不是同一状态。``ndo_open`` 建立运行期资源，``ndo_stop`` 撤销运行能力。

TX 入口转移 SKB 所有权
   ``ndo_start_xmit()`` 接收 ``sk_buff``。返回 ``NETDEV_TX_OK`` 表示驱动已经消费 skb；返回 ``NETDEV_TX_BUSY`` 表示 skb 仍归网络核心，驱动不得保存或释放它。

SKB 不一定线性
   Packet 可由线性 head、page fragments、GSO、checksum 和 VLAN 元数据组成。驱动声明某项 offload 后，必须正确解释并交给硬件或回退软件路径。

TX ring 通过 DMA 与设备协作
   驱动映射 skb 片段、填写 descriptor、建立内存顺序并写 doorbell。只有设备 completion 证明不再访问 buffer 后，才能 unmap DMA 和释放 skb。

队列停止与唤醒构成背压协议
   Ring 空间不足时应停止对应 subqueue；completion 回收空间后再唤醒。空间检查、producer/consumer 更新和 stop/wake 必须避免竞态。

RX 使用预置缓冲区
   驱动先向 RX ring 提供设备可写 buffer。设备 DMA 写入 packet 后产生事件，驱动再同步内存、构造 skb、设置协议元数据并交给网络栈。

NAPI 将逐包中断变为批处理
   IRQ handler 通常确认事件、屏蔽队列中断并调度 NAPI。Poll 在 budget 内批量处理 RX/TX completion，工作耗尽后完成 NAPI 并重新启用中断。

多队列性能取决于完整拓扑
   RSS、RPS/RFS、XPS、IRQ affinity、队列映射和 NUMA 共同决定 packet 在哪个 CPU 处理。队列数、IRQ 数和 CPU 数没有固定一一关系。

注销与释放分离
   ``unregister_netdev()`` 撤销网络核心入口并同步相关使用；ring、DMA、IRQ、NAPI 和 netdev 存储仍需按驱动生命周期继续清理。

关键路径
--------

网络设备注册：

::

   总线 probe 取得硬件资源
   → 分配 net_device 与私有对象
   → 设置 net_device_ops、features、MTU 和队列数
   → 初始化 TX/RX ring、NAPI、锁和统计
   → register_netdev 发布接口
   → 用户设置接口 up
   → ndo_open 启动 IRQ、NAPI、DMA 和硬件队列

发送路径：

::

   协议栈和 qdisc 选择 TX queue
   → ndo_start_xmit 接收 skb
   → 检查 ring 空间并决定 stop subqueue
   → DMA map skb head/frags
   → 填写 descriptor 与 offload 元数据
   → 发布 descriptor 并写 doorbell
   → 设备发送并产生 completion
   → unmap DMA、释放 skb
   → 恢复 ring 空间并 wake subqueue

接收与移除：

::

   设备 DMA 写入 RX buffer
   → IRQ 确认事件并调度 NAPI
   → poll 批量读取 descriptor
   → 同步 DMA、构造 skb、设置元数据
   → GRO/协议栈取得 skb 所有权
   → refill RX ring
   → 移除时阻止新 packet 并 unregister netdev
   → 停止 DMA/IRQ，disable NAPI，回收全部 buffer
   → free_netdev

概念辨析
--------

``net_device`` 与总线设备
   Netdev 表示网络接口；总线 device 表示硬件实例和资源来源。

接口 Up 与 Carrier Up
   Up 表示管理状态已启动；carrier 表示链路可用，二者可独立变化。

``NETDEV_TX_OK`` 与 ``NETDEV_TX_BUSY``
   OK 转移 skb 所有权给驱动；BUSY 保留所有权在网络核心。

IRQ 与 NAPI
   IRQ 快速确认并安排工作；NAPI 在 softirq/poll 语境中批量处理 packet 和 completion。

NAPI Disable 与 DMA Stop
   Disable 只收束 poll；硬件 DMA 和中断源仍需驱动显式停止。

Unregister 与 Free
   Unregister 撤销网络栈入口；free 只有在硬件、队列和全部引用都结束后才能执行。

本章结论
--------

网络驱动用 ``net_device`` 发布 packet 与队列接口，用 TX/RX DMA ring 和 NAPI转移 ``sk_buff`` 所有权，并必须在背压、reset、命名空间变化和热拔插中完整收束每个 packet。
