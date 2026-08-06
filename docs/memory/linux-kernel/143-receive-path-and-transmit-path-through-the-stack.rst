第143章：网络栈中的接收路径与发送路径
====================================

核心知识点
----------

网络路径首先是排队路径
   RX ring、NAPI、协议 backlog、socket queue、qdisc 和 TX ring 都可能保存 packet。性能与丢包必须先定位具体队列和执行上下文。

RX 从设备所有权转入协议栈
   网卡先 DMA 写入驱动提供的 RX buffer，再通过 completion 通知 CPU。驱动完成同步、构造 skb 并设置 metadata 后，才把 packet 交给网络核心。

IRQ 负责通知，NAPI 负责批处理
   Handler 通常确认事件、屏蔽队列中断并调度 NAPI。Poll 在 budget 内批量处理 RX/TX completion，队列排空后才完成 NAPI 并重新启用中断。

NAPI 完成需要防止丢失事件
   “检查队列为空、结束 poll、重新开中断”必须与设备状态形成原子协议；否则新 packet 可能落在无中断、无 poll 的窗口中。

XDP 与 GRO 改变 RX 处理粒度
   XDP 在普通 skb 创建前决定 PASS、DROP、TX 或 REDIRECT；GRO 在 skb 路径聚合兼容 segment。两者都改变观测点和成本模型。

RX Drop 分布在多个层级
   Ring overflow、buffer shortage、softnet backlog、协议校验、路由、Netfilter、socket memory 和应用读取过慢都会丢包，聚合计数不能替代路径定位。

CPU 局部性由多项映射共同决定
   RSS、IRQ affinity、NAPI、RPS/RFS、应用亲和性和 NUMA 决定 packet 在哪些 CPU 与内存节点之间移动。增加 CPU 数不保证单队列流量自动分散。

TX 经过协议、路由与调度
   应用 send 后，数据可能先停留在 socket/TCP 队列，再经过 IP route、Netfilter、neighbor、qdisc、netdev queue，最后进入驱动 ring。

Qdisc、Netdev Queue 与 Ring 是不同背压点
   Qdisc backlog 表示软件调度排队，netdev queue stopped 表示驱动暂不接收，TX ring full 表示硬件描述符资源不足。

驱动接管 skb 后必须最终回收
   ``NETDEV_TX_OK`` 表示驱动拥有 skb，并负责 DMA unmap、completion 和释放；``NETDEV_TX_BUSY`` 表示 skb 仍归网络核心。

Offload 移动工作而不改变协议合同
   GRO 聚合接收，GSO/TSO 分段发送，checksum offload 移动校验工作。设备 feature 与 skb metadata 不匹配时必须软件回退或拒绝。

关键路径
--------

RX 主路径：

::

   NIC 接收 frame
   → DMA 写 RX buffer
   → 更新 completion descriptor
   → IRQ 调度 NAPI
   → Poll 读取 descriptor
   → DMA ownership 转移
   → 构造 skb 与 metadata
   → XDP/GRO/协议分发
   → TCP/UDP
   → Socket receive queue

TX 主路径：

::

   应用 send
   → Socket/TCP/UDP 队列
   → IP route 与 Netfilter
   → Neighbor resolution
   → qdisc
   → 选择 TX queue
   → ndo_start_xmit
   → DMA map 与 descriptor
   → Doorbell
   → TX completion
   → Unmap、释放 skb、唤醒队列

NAPI 循环：

::

   IRQ mask 并 schedule NAPI
   → Poll 处理至 budget
   → 预算耗尽且仍有工作
   → 保持调度并继续 poll
   → 队列确认排空
   → napi_complete_done
   → 重启设备中断

丢包定位：

::

   对齐时间窗口与接口/队列
   → 检查硬件 RX/TX 统计
   → 检查 ring 与 buffer shortage
   → 检查 softnet/NAPI 压力
   → 检查 Netfilter/qdisc drop
   → 检查协议和 socket queue
   → 检查应用读取与发送速度

概念辨析
--------

* IRQ 与 NAPI：IRQ 提供事件通知；NAPI 以预算批量处理队列。
* RSS 与 RPS：RSS 在设备侧选择 RX queue；RPS 在软件中选择后续处理 CPU。
* Qdisc Backlog 与 TX Ring Full：前者是软件调度排队；后者是驱动硬件资源耗尽。
* ``NETDEV_TX_OK`` 与 ``NETDEV_TX_BUSY``：OK 转移 skb 所有权；BUSY 保留网络核心所有权。
* GRO 与 GSO/TSO：GRO 聚合接收 packet；GSO/TSO 拆分发送 packet。
* 抓到 Packet 与最终交付：抓包只证明 packet 到达观察点，后续仍可能被丢弃或排队。

本章结论
--------

网络收发是一组队列和所有权转移组成的流水线。诊断必须先确定 packet 停在哪一层、由哪个上下文处理，再解释 CPU、offload、拥塞或硬件因素。