======================================================================
03.02 自研可靠 UDP / KCP 传输层与拥塞控制算法
======================================================================

.. note:: 前置背景与上下文承接
   在前一章《03.01 Protobuf 协议模型设计与消息帧编解码》中，我们解剖了 RustDesk 顶层信令（``RendezvousMessage``）与会话多路复用（``Message``）的二进制数据模型及基于长度前缀的分帧定界机制。在理想局域网中，标准 TCP 流足以承载这些序列化报文。然而，在跨公网、移动蜂窝网络（4G/5G）或跨国长距离链路中，标准 TCP 的拥塞控制机制（如丢包即减半、重传超时 RTO 翻倍惩罚）以及**队头阻塞（Head-of-Line Blocking, HoL）**会导致远程桌面画面出现灾难性的周期性顿挫与高延迟。为了在不可靠的 UDP 数据报网络上建立低延迟、保序且具备高抗丢包能力的传输通道，RustDesk 深度集成了基于 **KCP 协议族** 的可靠 UDP 流体系。本章将深入剖析 ``src/kcp_stream.rs``，系统解构其底层 ARQ 重传模型、滑动窗口状态机与异步 I/O 调度。

***
TCP 在实时远程桌面传输中的物理缺陷
***

标准 TCP 协议设计之初以“绝对可靠性与吞吐量公平性”为核心目标，但其机制与交互式远程控制的实时性要求存在天然冲突：

1. **队头阻塞（Head-of-Line Blocking）**：TCP 是严格连续字节流。若第 $N$ 个数据包在公网中丢失，即便第 $N+1$ 到 $N+10$ 个数据包已先期到达接收端操作系统内核缓冲区，应用层也无法读取后续数据，必须等待第 $N$ 个包重传成功。在 60 FPS 视频流中，单个切片丢失会导致后续所有完整帧全部卡死在内核接收队列中。
2. **RTO 退避算法过于保守**：标准 TCP 在发生超时重传时，超时计时器 RTO（Retransmission TimeOut）采用指数退避（$	ext{RTO} 	imes 2$），且通常设置 $200\,	ext{ms}$ 的保底下限。在 $10\%$ 随机丢包的弱网下，TCP 吞吐量将发生雪崩。
3. **延迟确认机制（Delayed ACK）**：TCP 为了节省带宽，通常会等待 $40\,	ext{ms} \sim 200\,	ext{ms}$ 尝试与反向数据包合并发送 ACK，人为放大了端到端控制往返时延。

.. list-table:: TCP 与可靠 UDP (KCP) 传输层物理特性对比
   :widths: 20 25 30 25
   :header-rows: 1

   * - 协议特征
     - 标准 TCP 传输层
     - 可靠 UDP (RustDesk KCP)
     - 远程桌面体验收益
   * - **重传触发机制**
     - 超时重传（RTO 翻倍）+ 3 次重复 ACK
     - 快速重传（Fast Retransmit）+ 选择性重传（Selective ACK）
     - 重传响应时间从数百毫秒压缩至 $10\,	ext{ms} \sim 30\,	ext{ms}$
   * - **确认策略 (ACK)**
     - 延迟确认（Delayed ACK, 约 40ms 延迟）
     - 极速无延迟确认（Immediate / Non-Delayed ACK）
     - 极大压降交互式键鼠操作的往返反馈延迟
   * - **流抽象封装**
     - 原生操作系统 ``TcpStream``
     - 基于 ``KcpStream`` 封装为 ``AsyncRead + AsyncWrite``
     - 上层 Protobuf 与加密逻辑零代码改动平滑复用

---
KCP 报文物理结构与分段封装
---

在 UDP 数据报载荷内部，KCP 协议将上层流切分为带有元数据控制头的分段（Segments）：

```
+---------------+---------------+---------------+---------------+
|       Conversation ID (conv: 4-Byte Session Unique Token)     |
+---------------+---------------+---------------+---------------+
|  cmd (1-Byte) |  frg (1-Byte) |           wnd (2-Byte)        |
+---------------+---------------+---------------+---------------+
|                       Timestamp (ts: 4-Byte)                  |
+---------------+---------------+---------------+---------------+
|                  Sequence Number (sn: 4-Byte)                 |
+---------------+---------------+---------------+---------------+
|            Unacknowledged Sequence (una: 4-Byte)              |
+---------------+---------------+---------------+---------------+
|                     Data Length (len: 4-Byte)                 |
+---------------+---------------+---------------+---------------+
|                       Payload Data (len Bytes)                |
+---------------+---------------+---------------+---------------+
```

* **``conv`` (Conversation ID)**：通信会话唯一标识符，确保在 UDP 无连接链路上实现多路会话区分。
* **``cmd`` (Command)**：指令类型，包括数据推送（``IKCP_CMD_PUSH``）、确认应答（``IKCP_CMD_ACK``）、窗口探测（``IKCP_CMD_WASK``）与窗口通告（``IKCP_CMD_WINS``）。
* **``sn`` 与 ``una``**：``sn`` 标识当前分段序号；``una`` 标识接收端当前期望接收的下一个未确认序号（所有小于 ``una`` 的分段均已确认收到）。
* **``frg`` (Fragment)**：大报文分片计数器，实现大于 MTU（$1500\,	ext{Bytes}$）数据帧的透明分拆与重组。

---
RustDesk ``KcpStream`` 异步事件调度架构 (``src/kcp_stream.rs``)
---

在 Rust 异步运行时中，RustDesk 将 底层 C 库/绑定抽象为非阻塞的 Tokio 异步 I/O 管道：

```
                           [ 上层业务会话 (FramedStream) ]
                                         │ (Protobuf / 加密流)
                                         ▼
                            [ stream::KcpStream ]
                                         │ (双向 MPSC 管道)
                         ┌───────────────┴───────────────┐
                         ▼                               ▼
                 [ Input Channel ]               [ Output Channel ]
                         │                               │
                         └───────────────┬───────────────┘
                                         ▼
                             [ tokio::spawn 异步 I/O 循环 ]
                                         │
                             [ Arc<tokio::net::UdpSocket> ]
                                         │ (底层 UDP 数据报)
                                         ▼
                                   [ 公网物理链路 ]
```

1. 双向异步 I/O 循环泵（``kcp_io``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``src/kcp_stream.rs`` 中，后台任务通过 ``tokio::select!`` 同时驱动底层物理 UDP 套接字与上层 KCP 状态机：

.. code-block:: rust
   :caption: KCP 异步 I/O 调度循环泵（src/kcp_stream.rs）

   async fn kcp_io(
       udp_socket: Arc<UdpSocket>,
       input: mpsc::Sender<KcpPacket>,
       mut output: mpsc::Receiver<KcpPacket>,
       mut stop_receiver: oneshot::Receiver<()>,
   ) {
       let udp = udp_socket.clone();
       tokio::spawn(async move {
           let mut buf = vec![0u8; 1500]; // 遵循以太网 1500 字节标准 MTU
           loop {
               tokio::select! {
                   // 1. 监听外部会话终止信号
                   _ = &mut stop_receiver => {
                       log::debug!("KCP io loop received stop signal");
                       break;
                   }
                   // 2. 发送队列：从 KCP 状态机提取封装好的可靠分段，通过 UDP 发送至公网
                   Some(data) = output.recv() => {
                       if let Err(e) = udp.send(&data.inner()).await {
                           log::debug!("KCP send error: {:?}", e);
                           break;
                       }
                   }
                   // 3. 接收队列：从底层 UDP 读取原始数据报，送入 KCP 状态机执行重组、校验与解密
                   result = udp.recv_from(&mut buf) => {
                       match result {
                           Ok((size, _)) => {
                               // 过滤长度小于 KCP 头部尺寸（24 字节）的畸形报文
                               if size < std::mem::size_of::<KcpPacketHeader>() {
                                   continue;
                               }
                               input
                                   .send(BytesMut::from(&buf[..size]).into())
                                   .await.ok();
                           }
                           Err(e) => {
                               log::debug!("KCP recv_from error: {:?}", e);
                               break;
                           }
                       }
                   }
                   else => break,
               }
           }
       });
   }

2. 统一流抽象接入（``create_framed``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了让整个上层架构对底层传输协议（TCP / KCP）无感知，RustDesk 将 ``stream::KcpStream`` 装箱包裹为 ``DynTcpStream``，并挂载 ``tokio_util::codec::Framed``：

.. code-block:: rust
   :caption: KcpStream 适配为标准 Stream 抽象

   fn create_framed(stream: stream::KcpStream, local_addr: Option<SocketAddr>) -> Stream {
       Stream::Tcp(FramedStream(
           tokio_util::codec::Framed::new(DynTcpStream(Box::new(stream)), BytesCodec::new()),
           local_addr.unwrap_or(config::Config::get_any_listen_addr(true)),
           None,
           0,
       ))
   }

---
ARQ 快速重传与滑动窗口拥塞控制算法
---

为了在丢包率高达 $20\% \sim 30\%$ 的极端弱网下维持稳定的音视频流与控制交互，KCP 实现了四大核心 ARQ 加速算法：

1. 跨包跳跃式快速重传（Fast Retransmit）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

传统 TCP 要求连续收到 3 次重复 ACK（Dup-ACK）才触发快速重传。KCP 引入了更加激进的跳跃计数器：当发送端发送了分段 $1, 2, 3, 4, 5$，而接收端先后收到了 $1, 3, 4, 5$ 时，分段 $2$ 被后续包“跨越”了 2 次。KCP 立即认定分段 $2$ 丢失并触发快速重传，无需等待昂贵的超时计时器触发。

2. 选择性确认（Selective ACK, SACK）与 UNA 累积确认结合
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

KCP 同时使用 UNA（累积确认：表示在此序号之前的数据包全收齐）与 ACK 列表（显式通知发送端已收到的乱序分段），发送端仅重传真正丢失的单个分段，杜绝了 TCP 的回退 $N$ 步（Go-Back-N）全局重传所带来的带宽浪费。

3. 极速时钟滴答与 RTO 线性修正
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在极速模式（Turbo Mode）下，KCP 的内部时钟轮询频率提升至 $10\,	ext{ms}$（``interval = 10``），并将 RTO 增长系数从 TCP 的 $	imes 2.0$ 降至 $	imes 1.5$：

.. math::

   	ext{RTO}_{	ext{new}} = 	ext{Clamp}(	ext{SRTT} + 4 	imes 	ext{RTTVAR}, 	ext{RTO}_{\min}, 	ext{RTO}_{\max})

确保在发生偶发丢包时，系统能在数十毫秒内完成重传补偿，杜绝画面肉眼可见的卡顿。

***
小结与下章导读
***

本章系统解剖了 RustDesk 可靠 UDP 传输层的底层设计：
* 阐明了传统 TCP 在实时远程控制场景下的队头阻塞与 RTO 指数退避缺陷。
* 剖析了 KCP 协议的 24 字节分段头部物理结构（``conv``、``cmd``、``sn``、``una``）。
* 拆解了 ``src/kcp_stream.rs`` 中的双向异步 I/O 调度泵，以及将 UDP 流无缝桥接为 Tokio ``AsyncRead + AsyncWrite`` 的适配架构。
* 揭示了选择性重传（SACK）、快速重传与时钟精细化调度的抗弱网加速机制。

在下一节中，我们将深入 NAT 穿透的核心黑盒：
* **《03.03 NAT 类型探测与 UDP Hole Punching P2P 打洞机制》**：深入剖析 Full Cone、Restricted Cone、Port Restricted Cone 与 Symmetric NAT 的物理行为差异，以及 RustDesk 如何在端到端之间建立直连 UDP 隧道。
