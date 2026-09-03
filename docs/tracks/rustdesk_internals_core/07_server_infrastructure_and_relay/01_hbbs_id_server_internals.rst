======================================================================
07.01 注册与 ID 寻址服务器 (hbbs) 架构与 Peer 状态存储
======================================================================

.. note:: 前置背景与上下文承接
   在前面的六个模块中，我们自底向上完整剖析了 RustDesk 客户端的全栈体系——从操作系统底层硬件捕获、音视频编解码、网络穿透、端到端流加密、Tokio 客户端状态机直到 Flutter 跨语言 GPU 渲染管线。然而，在去中心化 P2P 远程桌面架构中，两个处于不同 NAT 子网、公网 IP 动态变化的端点无法直接感知对方的物理网络拓扑。整个分布式网络必须依赖一个高性能、低延迟且安全可靠的**信令与注册中枢（Rendezvous Server）**。在开源生态中，这一核心角色由 **``hbbs``（HeartBeat / Bootstrap Server）** 承担。本章正式开启全书收官模块 **模块 07：服务端架构与中继调度**，系统解剖 ``hbbs`` 的异步网络事件循环、Peer 全局在线状态机、设备公钥证书库与内存/磁盘混合存储架构。

***
``hbbs`` 在远程桌面生态中的定位与物理监听拓扑
***

``hbbs`` 是整个 RustDesk 网络的“神经中枢”，承担着身份注册、公钥验真、NAT 打洞协调与中继分派四大核心职责：

```
[受控端 Host (Peer A)]                                         [主控端 Controller (Peer B)]
          │                                                                  │
          │ (心跳注册: RegisterPeer / RegisterPk)                             │ (呼叫查询: PunchHole / RequestRelay)
          ▼                                                                  ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    RustDesk 注册服务器: hbbs (Rendezvous Server)                  │
│                                                                                 │
│  [21115/TCP: NAT 类型探测]   [21116/UDP: 核心心跳与打洞]   [21116/TCP: 保活中继协商] │
│  [21118/TCP: WebSocket 网页端]                             [21114/TCP: Web 控制台]   │
├─────────────────────────────────────────────────────────────────────────────────┤
│  [全局 Peer 内存路由表 (DashMap)]        [持久化身份数据库 (SQLite / Sled)]       │
│  - ID -> (Public IP, Port, Local IP)   - ID -> Ed25519 Public Key (公钥证书)     │
│  - Machine UUID & Lease TTL            - Device Token & Enterprise Policy       │
└─────────────────────────────────────────────────────────────────────────────────┘
```

.. list-table:: ``hbbs`` 服务端物理端口与监听协议规范
   :widths: 18 20 28 34
   :header-rows: 1

   * - 端口编号
     - 传输协议
     - 协议数据载荷
     - 核心物理职责
   * - **21115**
     - TCP
     - ``NatType`` / 探测帧
     - NAT 类型（Full Cone / Symmetric）探测与端口预测
   * - **21116**
     - UDP
     - ``RendezvousMessage`` (Protobuf)
     - 高频心跳保活、P2P Hole Punching 穿透指令下发
   * - **21116**
     - TCP
     - ``RendezvousMessage`` (Framed)
     - UDP 受限网络下的 TCP 信令备用通道与中继分配
   * - **21118**
     - TCP / WebSocket
     - Protobuf over WS
     - 支持浏览器 Web Client（Wasm）免安装远程连接

---
异步高并发网络事件循环与 Protobuf 消息分发
---

``hbbs`` 采用 **Tokio 异步多线程运行时** 驱动。单台服务器需同时维持数十万台活跃设备的 UDP 心跳。

在 ``src/rendezvous_mediator.rs`` 与服务端核心实现中，UDP 套接字循环接收网络原始报文并执行纳秒级 Protobuf 解析：

.. code-block:: rust
   :caption: hbbs UDP 信令分发主循环（架构模型）

   async fn hbbs_udp_event_loop(
       socket: Arc<UdpSocket>,
       peer_map: Arc<DashMap<String, PeerSessionInfo>>,
       db: Arc<DatabaseBackend>,
   ) -> ResultType<()> {
       let mut buf = [0u8; 65535];
       loop {
           let (len, peer_addr) = socket.recv_from(&mut buf).await?;
           let bytes = &buf[..len];
           
           // 1. 快速反序列化 Protobuf 信令报文
           if let Ok(msg) = RendezvousMessage::parse_from_bytes(bytes) {
               let socket = socket.clone();
               let peer_map = peer_map.clone();
               let db = db.clone();
               
               // 2. 协程并发处理，绝不阻塞 UDP 接收事件循环
               tokio::spawn(async move {
                   match msg.union {
                       Some(Union::RegisterPeer(rp)) => {
                           handle_register_peer(rp, peer_addr, &socket, &peer_map, &db).await;
                       }
                       Some(Union::RegisterPk(rpk)) => {
                           handle_register_pk(rpk, peer_addr, &socket, &peer_map, &db).await;
                       }
                       Some(Union::PunchHole(ph)) => {
                           handle_punch_hole(ph, peer_addr, &socket, &peer_map).await;
                       }
                       Some(Union::RequestRelay(rr)) => {
                           handle_request_relay(rr, peer_addr, &socket, &peer_map).await;
                       }
                       _ => {}
                   }
               });
           }
       }
   }

---
Peer 生命周期状态机与安全身份验证机制
---

客户端与 ``hbbs`` 的交互包含严格的身份确权与防碰撞状态机：

```
[客户端 Client]                                              [注册服务器 hbbs]
       │                                                             │
       ├─ 1. 发送 RegisterPeer { id: "123456" } ────────────────────>│
       │                                                             ├─ 2. 检查本地数据库:
       │                                                             │    * 若未绑定 Ed25519 PK:
       │<─ 3. 返回 RegisterPeerResponse { request_pk: true } ────────┤
       │                                                             │
       ├─ 4. 发送 RegisterPk { id, uuid, pk: Ed25519_PK } ──────────>│
       │                                                             ├─ 5. 校验与持久化:
       │                                                             │    * 若 ID 已被其他 UUID 占用:
       │                                                             │      返回 UUID_MISMATCH (触发换号)
       │                                                             │    * 若通过: 写入 DB 绑定关系
       │<─ 6. 返回 RegisterPkResponse { result: OK, keep_alive } ────┤
```

1. UUID 碰撞检测与防劫持（``UUID_MISMATCH``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了防止恶意攻击者伪造他人 ID 强行向服务器覆盖注册，``hbbs`` 在首次注册时将用户的 ``id`` 与硬件唯一标识符 ``uuid`` 深度绑定：
* 若相同 ``id`` 的后续注册请求携带了不同的 ``uuid``，``hbbs`` 判定为 ID 冲突或冒充攻击，直接返回 ``register_pk_response::Result::UUID_MISMATCH``；
* 客户端收到后会自动触发 ``Config::update_id()`` 生成全新随机 ID，彻底杜绝身份篡改。

2. 指数移动加权（EMA）时延滤波与动态心跳
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

客户端在每次心跳往返中计算 RTT 时延，并采用指数加权移动平均算法平滑网络抖动：

.. math::

   	ext{EMA}_{	ext{Latency}} = \frac{1}{30} 	imes 	ext{Latency}_{	ext{Current}} + \frac{29}{30} 	imes 	ext{EMA}_{	ext{Previous}}

``hbbs`` 根据网络负载与客户端网络类型，在响应中动态下发 ``keep_alive`` 周期（默认 $30\,	ext{s}$），兼顾 NAT 映射保活与服务器 CPU 降载。

---
Peer 状态存储：内存路由表与持久化数据库
---

``hbbs`` 采用**两级存储体系**以兼顾极速信令寻址与数据持久化：

1. **第一级：内存高速并发路由表（In-Memory Routing Table）**：
   采用分段锁哈希表（如 ``DashMap<String, PeerSessionInfo>``），缓存所有在线客户端的 ``(Public IP, Public Port, Local IP, Last Heartbeat)``。查询与更新均在微秒（$\mu	ext{s}$）级完成；
2. **第二级：持久化身份数据库（Persistent DB: SQLite / Sled）**：
   记录不可丢失的元数据：
   * ``peers`` 表：``(id, public_key, uuid, created_at, disabled)``；
   * 记录设备授权令牌、自建服务器私有访问密钥（Key）与企业策略规则。

3. 死信回收与租约淘汰机制（Lease Reaper）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``hbbs`` 启动独立的后台 GC 协程，定期扫描内存路由表：
* 若某 Peer 超过 $3 	imes 	ext{keep\_alive}$ 未收到心跳数据报，判定为异常断网或宕机；
* 自动将其从在线路由表中剔除并释放端口绑定，防止向失效对端发送无效打洞信令。

***
小结与下章导读
***

本章系统解构了 RustDesk 注册中枢 ``hbbs`` 的核心架构：
* 梳理了 21115/21116/21118 端口矩阵在 NAT 探测、UDP 信令与 WebSocket 桥接中的职责分工。
* 剖析了 Tokio 高性能异步 UDP 事件循环与 Protobuf 协程分发模型。
* 揭示了基于 ``UUID_MISMATCH`` 的防碰撞 ID 绑定与 EMA 时延平滑算法。
* 阐述了内存高速路由表与持久化数据库的分层存储架构与租约回收机制。

在下一节中，我们将深入流量转发中枢：
* **《07.02 中继服务器 (hbbr) 高并发数据转发与限速模型》**：深入剖析数据中继服务 ``hbbr`` 在 P2P 打洞失败时的零拷贝流量中继、多路复用会话绑定、非阻塞 Token Bucket 流量整形与带宽限速算法。
