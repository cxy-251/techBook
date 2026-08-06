第154章：Zero-copy 路径与 AF_XDP
===============================

核心知识点
----------

AF_XDP 连接 XDP 与用户态 Buffer
   AF_XDP 把早期 Packet Redirect 到用户态可访问的 UMEM，使应用通过 Descriptor 和 Ring 管理 Raw Frame，而不是经过普通 skb、Socket Queue 和 Copy-to-user 主线。

Zero-copy 是 Payload 留址协议
   它尽量让 Packet Payload 保留在同一块可 DMA、可由用户态访问的内存中，只跨边界传递 Descriptor；系统仍有 Ring、同步、Cache、DMA Mapping 和控制成本。

UMEM 是注册后的 Frame 池
   用户态内存被划分为 Chunk/Frame，并通过注册建立内核和设备可使用的 Buffer 集合。Frame Address 是 UMEM 内偏移，不是普通指针或 DMA Address。

四类 Ring 表达所有权
   FILL 提供空 RX Frame，RX 发布已接收 Frame，TX 提交待发送 Frame，COMPLETION 归还已完成 TX Frame。每个 Frame 同一时刻只能属于一个集合。

RX 所有权必须闭环
   标准链是 User Free → FILL → Kernel/Device RX → RX Ring → User Processing → FILL。用户处理后不及时归还会耗尽接收 Buffer。

TX 所有权必须等待 Completion
   标准链是 User Free → TX Ring → Kernel/Device TX → COMPLETION → User Free。提交 TX 后提前复用 Frame 会形成数据损坏。

Ring 是有界 SPSC 队列
   Descriptor 写完后才能发布 Producer；Consumer 观察发布后才能读取。多个线程共享同一 Producer 或 Consumer 需要应用额外同步。

XSK 绑定到设备与 Queue
   AF_XDP Socket 通常绑定 Netdev、RX/TX Queue ID 和模式。RSS 与 Queue 配置决定哪些 Packet 能到达该 XSK。

XSKMAP 完成 Redirect 选择
   XDP Program 常按 ``rx_queue_index`` 查找 XSKMAP 并返回 ``XDP_REDIRECT``。Map Entry、设备、Queue 或 Socket 不匹配会导致 Redirect 失败。

Copy Mode 与 Zero-copy Mode 不同
   Copy Mode 在驱动 Buffer 与 UMEM 间复制，兼容性更高；Zero-copy 要求驱动直接把 UMEM Frame 接入 DMA 路径。应用必须确认实际运行模式。

Backpressure 由 Frame 和 Ring 显式表达
   FILL 空、RX 满、TX 满或 COMPLETION 未消费都会阻塞对应方向或导致 Drop。AF_XDP 不提供无限 Socket Buffer 语义。

性能取决于 Queue、CPU 和 NUMA 对齐
   每 Queue 一个 XSK/Worker 是常见扩展方式。IRQ、NAPI、Worker、UMEM 和 NIC 应尽量保持局部，避免跨 CPU 与跨 NUMA 访问。

关键路径
--------

AF_XDP RX：

::

   用户注册 UMEM
   → 把空 Frame 写入 FILL Ring
   → XSK 绑定 Netdev + Queue
   → XSKMAP 建立 Queue 到 XSK 的映射
   → XDP_REDIRECT
   → 内核/驱动取得 FILL Frame
   → Copy 或 Zero-copy 接收 Packet
   → RX Ring 发布 xdp_desc
   → 用户处理 Frame
   → 重新放回 FILL

AF_XDP TX：

::

   用户取得空闲 Frame
   → 构造合法 Packet
   → TX Ring 发布 Descriptor
   → 必要时 Kick 内核
   → 驱动/NIC 发送
   → COMPLETION Ring 发布 Frame Address
   → 用户回收 Completion
   → Frame 返回空闲池

Frame 守恒：

::

   总 Frame 数
   = User Free
   + FILL Owned
   + RX Published / Processing
   + TX In-flight
   + Completion Pending

   任一 Frame 只能属于一个集合
   → 总数不守恒说明 Leak、Double-submit 或提前复用

安全退出：

::

   停止业务新 TX
   → 从 XSKMAP 删除 Entry 或切换 XDP Program
   → 阻止新的 RX Redirect
   → 消费 RX 并归还 Frame
   → 等待 TX Completion
   → 核对 Frame 总数
   → 关闭 XSK
   → 解除 UMEM 注册并释放内存

概念辨析
--------

* UMEM Address 与 DMA Address：UMEM Address 是用户 Frame 偏移；设备地址由内核和 DMA 层建立。
* Copy Mode 与 Zero-copy Mode：二者共享 AF_XDP API，但 Payload 是否复制及驱动要求不同。
* TX 提交与 TX 完成：Descriptor 发布只转移所有权；COMPLETION 才允许用户复用 Frame。
* XDP Redirect 与 RX Ring 可见：Redirect Action 之后仍受 XSKMAP、FILL、RX Ring 和驱动状态约束。
* 大 Ring 与低延迟：更大 Ring 能吸收 Burst，也会增加驻留内存和最坏排队时间。

本章结论
--------

AF_XDP 的 Zero-copy 是围绕 UMEM Frame 建立的所有权协议：FILL/RX 管理接收，TX/COMPLETION 管理发送，所有性能与正确性都取决于 Frame 守恒和 Queue 闭环。
