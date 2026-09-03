======================================================================
03.01 Protobuf 协议模型设计与消息帧编解码
======================================================================

.. note:: 前置背景与上下文承接
   在前两个模块中，我们先后解剖了操作系统的底层交互原语（抓屏、输入注入、音频环回、虚拟显示）与音视频编解码流水线（帧缓冲对齐、零拷贝、VP9/AV1 软件调优与 GPU 硬件加速）。在这些子系统中，音视频帧、键鼠控制指令、剪贴板数据与会话配置最终都必须转化为二进制字节流注入网络传输层。异构跨平台客户端（Windows、macOS、Linux、Android、iOS、Web）如何以极低的空间开销、向前/向后兼容性以及严格的强类型安全进行序列化通信？本章正式开启 **模块 03：信令通道、Protobuf 与 NAT 穿透**，深入解构 RustDesk 基于 Google Protocol Buffers 的协议消息模型、分帧定界（Framing）机制与流式编解码管道。

***
远程桌面通信协议的架构选型与分层拓扑
***

远程桌面控制包含两类性质截然不同的通信流：

1. **信令与协调流（Signaling & Rendezvous Stream）**：与注册服务器（``hbbs``）、中继服务器（``hbbr``）交互，负责设备注册、公网 IP/端口打洞探测（STUN）、NAT 类型判别与中继调度。
2. **数据与控制流（Peer-to-Peer Data & Control Session）**：主控端与受控端直接（或经中继中转）建立的长连接，承载密集的视频帧包、音频包、高频微小输入事件（鼠标移动/按键）与文件传输块。

.. list-table:: RustDesk 二进制协议两大核心顶层消息模型
   :widths: 20 25 30 25
   :header-rows: 1

   * - 协议模型
     - 顶层 Protobuf 消息
     - 通信端点
     - 核心承载职责
   * - **信令协议 (Rendezvous)**
     - ``RendezvousMessage``
     - Client $\leftrightarrow$ ``hbbs`` / ``hbbr``
     - 注册认证、打洞协商、中继请求、NAT 探测、在线状态位图
   * - **会话协议 (Session Data)**
     - ``Message``
     - Client $\leftrightarrow$ Server (Controlled Host)
     - 登录鉴权、音视频流、键鼠控制、剪贴板同步、文件流

---
信令协议模型：``RendezvousMessage`` 与 NAT 发现
---

信令协议定义在 ``rendezvous_proto`` 中，采用 Rust 代数数据类型（``enum Union``）实现多态分发：

.. code-block:: protobuf
   :caption: 信令顶层消息定义（rendezvous_proto.proto 逻辑结构）

   message RendezvousMessage {
       oneof union {
           RegisterPeer register_peer = 1;
           RegisterPeerResponse register_peer_response = 2;
           PunchHoleRequest punch_hole_request = 3;
           PunchHoleResponse punch_hole_response = 4;
           RequestRelay request_relay = 5;
           RelayResponse relay_response = 6;
           TestNatRequest test_nat_request = 7;
           TestNatResponse test_nat_response = 8;
           OnlineRequest online_request = 9;
           OnlineResponse online_response = 10;
           HealthCheck hc = 11;
           // ...
       }
   }

1. 批量在线状态位图压缩（``OnlineResponse``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当客户端打开地址簿或最近连接列表时，需要快速查询数十甚至上百台主机的在线状态。如果逐个发送查询或返回完整字符串列表，网络开销巨大。RustDesk 采用了**密集位图（Bitmap）压缩传输机制**：

.. code-block:: rust
   :caption: 位图解压与对齐（src/client.rs::peer_online）

   // 服务端返回的 states 为紧凑字节切片，每 1 个 bit 代表一台主机的在线状态（1: 在线, 0: 离线）
   let states = online_response.states;
   let mut onlines = Vec::new();
   let mut offlines = Vec::new();

   for i in 0..ids.len() {
       // 从左至右提取第 i 个 bit 掩码
       let bit_value = 0x01 << (7 - i % 8);
       if (states[i / 8] & bit_value) == bit_value {
           onlines.push(ids[i].clone());
       } else {
           offlines.push(ids[i].clone());
       }
   }

通过位图压缩，上千台主机的在线状态仅需约 $128\,	ext{Bytes}$ 即可在单次往返中完整下发。

---
会话协议模型：``Message`` 与多路复用信道
---

在建立端到端连接后，所有控制与多媒体流均通过统一的顶层 ``Message`` 结构体多路复用分发：

.. code-block:: rust
   :caption: 会话层核心消息多路复用架构

   pub enum Union {
       SignedId(SignedId),               // 初始非对称签名身份公钥
       PublicKey(PublicKey),             // 迪菲-赫尔曼密钥协商载体
       LoginRequest(LoginRequest),       // 客户端登录请求（版本、OS凭据、显示参数）
       LoginResponse(LoginResponse),     // 服务端登录响应与权限确认
       VideoFrame(VideoFrame),           // 视频压缩数据包（H.264/H.265/VP9/AV1）
       AudioFrame(AudioFrame),           // Opus 音频压缩采样包
       MouseEvent(MouseEvent),           // 鼠标移动、点击、滚轮与修饰键
       KeyEvent(KeyEvent),               // 物理扫描码、Unicode、模式与锁定键
       CursorData(CursorData),           // 远端鼠标指针图像与形状缓存
       CursorPosition(CursorPosition),   // 远端鼠标绝对物理坐标广播
       FileTransfer(FileTransfer),       // 文件传输控制与分块数据
       Misc(Misc),                       // 杂项控制：画质/FPS切换、黑屏隐私、分辨率变更
       // ...
   }

1. 细粒度输入事件压缩模型
~~~~~~~~~~~~~~~~~~~~~~~~

鼠标移动属于极高频事件（在 1000Hz 电竞鼠标下每秒产生上千个坐标点）。RustDesk 的 ``MouseEvent`` 通过位掩码（Bitmask）与紧凑变长整型（Varint）将按键状态、操作类型与修饰键合为一个 32 位整型：

.. math::

   	ext{Mask} = (	ext{Buttons} \ll 3) \mid 	ext{EventType}

配合 Protobuf 的 ZigZag 变长编码，极小位移增量在网络传输中仅占 $3 \sim 6\,	ext{Bytes}$。

---
传输层分帧定界（Length-Prefixed Framing）与流式编解码
---

在 TCP 或可靠 UDP（KCP）这类面向流（Stream-oriented）的传输通道中，数据包可能在网络栈中发生粘包或拆包。必须在流上建立**基于长度前缀的分帧协议（Length-Prefixed Framing）**。

```
+--------------------------+---------------------------------------------+
| 4-Byte Big-Endian Length | Encrypted Protobuf Payload (Binary Payload) |
+--------------------------+---------------------------------------------+
|<------- Frame Header --->|<------------- Frame Body ------------------>|
```

1. 异步分帧状态机读取时序
~~~~~~~~~~~~~~~~~~~~~~~~

RustDesk 的传输封装层（``hbb_common::Stream``）在底层集成 Tokio 异步读取状态机：

.. code-block:: rust
   :caption: 流式分帧与零拷贝反序列化伪代码实现

   pub struct FramedStream {
       inner: AsyncStream,
       read_buf: BytesMut,
   }

   impl FramedStream {
       pub async fn next_message(&mut self) -> ResultType<Option<Message>> {
           loop {
               // 1. 检查缓冲区是否包含完整的 4 字节长度头
               if self.read_buf.len() >= 4 {
                   let length = u32::from_be_bytes(self.read_buf[0..4].try_into()?) as usize;
                   
                   // 2. 检查缓冲区是否已接收满一个完整帧体
                   if self.read_buf.len() >= 4 + length {
                       self.read_buf.advance(4); // 弹出长度头
                       let frame_bytes = self.read_buf.split_to(length);
                       
                       // 3. 执行对称流解密（ChaCha20-Poly1305 / XSalsa20）
                       let decrypted_bytes = self.decrypt(frame_bytes)?;
                       
                       // 4. Protobuf 反序列化为 Rust 强类型结构体
                       let msg = Message::parse_from_bytes(&decrypted_bytes)?;
                       return Ok(Some(msg));
                   }
               }
               
               // 5. 缓冲区不足一帧，从底层网络套接字继续异步读取填充
               if self.inner.read_buf(&mut self.read_buf).await? == 0 {
                   return Ok(None); // 远端正常关闭流
               }
           }
       }
   }

2. ``bytes::Bytes`` 引用计数与跨线程零拷贝分发
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了避免音视频大包（如 200KB 的 4K 关键帧）在服务端网络线程池向渲染/控制线程分发时发生昂贵的全量深拷贝，RustDesk 深度使用 ``bytes::Bytes`` 与 ``Arc<Message>``：

* 音视频帧数据封装为 ``bytes::Bytes``，其内部基于原子引用计数（Atomic Reference Counting）共享底层连续内存切片。
* 通过跨线程 MPSC 通道传递所有权时，仅复制胖指针（Fat Pointer），实现真正的进程内数据零拷贝路由。

***
小结与下章导读
***

本章系统解构了 RustDesk 跨平台通信的协议基石：
* 阐明了信令协调流（``RendezvousMessage``）与会话数据流（``Message``）的分层架构与职责边界。
* 剖析了在线状态位图（Bitmap）压缩机制与紧凑输入事件掩码编码。
* 揭示了基于 4 字节大端序长度前缀的分帧定界（Framing）状态机，以及结合 ``bytes::Bytes`` 的零拷贝异步反序列化流水线。

在下一节中，我们将深入传输层核心传输引擎：
* **《03.02 自研可靠 UDP / KCP 传输层与拥塞控制算法》**：深入剖析 RustDesk 如何在 UDP 之上构建类似于 KCP 的可靠有序传输通道，结合 ARQ 自动重传、滑动窗口与快速重传算法对抗弱网抖动。
