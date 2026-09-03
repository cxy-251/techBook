======================================================================
03.03 NAT 类型探测与 UDP Hole Punching P2P 打洞机制
======================================================================

.. note:: 前置背景与上下文承接
   在前面的章节中，我们先后解剖了 Protobuf 二进制信令协议（《03.01》）与基于 KCP 的可靠 UDP 传输层架构（《03.02》）。然而，在现实互联网拓扑中，绝大多数受控端与主控端均隐匿在运营商级 NAT（Carrier-Grade NAT, CGNAT）、家庭宽带路由器或企业防火墙之后，不具备独立的公网 IPv4 地址。如果所有远程流量都强制经由中心服务器中继，不仅会带来高昂的中继带宽成本，还会显著增加网络延迟。如何让位于两个不同私有局域网中的设备绕过网关防火墙，建立点对点（P2P）直接 UDP 通信？本章将深入剖析 RustDesk 在 ``src/client.rs`` 与 ``src/rendezvous_mediator.rs`` 中的 **NAT 类型探测算法、UDP Hole Punching（打洞）状态机与多路并发竞速模型**。

***
NAT 拓扑分类与端到端穿透可行性数学模型
***

网络地址转换（NAT）网关在转发内部主机出站数据报时，会在其状态表中建立映射：$(	ext{IP}_{	ext{internal}}, 	ext{Port}_{	ext{internal}}) \leftrightarrow (	ext{IP}_{	ext{external}}, 	ext{Port}_{	ext{external}})$。根据 RFC 3489 / RFC 4787 标准，NAT 的端口映射与入站过滤行为可分为四大经典物理模型：

.. list-table:: 四类经典 NAT 行为特征与 P2P 穿透矩阵
   :widths: 20 25 30 25
   :header-rows: 1

   * - NAT 类型
     - 端口映射规则 (Mapping)
     - 入站过滤规则 (Filtering)
     - P2P 穿透可行性
   * - **Full Cone (全锥型 NAT-1)**
     - 内部端口映射到固定公网端口
     - 允许任意外部主机向该映射端口发包
     - $100\%$ 可穿透
   * - **Address Restricted (受限锥型 NAT-2)**
     - 内部端口映射到固定公网端口
     - 仅允许内部主机曾发过包的**目标 IP**发包进入
     - 可穿透（需先向对方公网 IP 发送探测包）
   * - **Port Restricted (端口受限锥型 NAT-3)**
     - 内部端口映射到固定公网端口
     - 仅允许内部主机曾发过包的**目标 IP:Port**发包进入
     - 可穿透（双方必须同时向对方公网 IP:Port 发包）
   * - **Symmetric (对称型 NAT-4)**
     - 每次访问不同的目标 IP:Port，分配**全新的公网端口**
     - 仅允许特定目标 IP:Port 发包进入
     - 传统打洞直接失败（需端口预测或回退 Relay 中继）

在 RustDesk 的协议抽象中（``rendezvous_proto::NatType``），系统将 NAT 简化为两大决策大类：
* **``NatType::ASYMMETRIC``（非对称/锥型 NAT）**：公网映射端口与目标端点无关，支持 UDP 打洞。
* **``NatType::SYMMETRIC``（对称型 NAT）**：公网映射端口随目标变动，直接进入中继协商流程。

---
STUN 机制与 NAT 类型探测算法
---

在建立连接前，客户端必须向注册服务器（``hbbs``）发起探测，获知自身的公网映射 IP、映射端口以及 NAT 类型。

.. code-block:: rust
   :caption: UDP NAT 探测循环与指数退避重试（src/client.rs::test_udp_uat）

   async fn test_udp_uat(
       udp_socket: Arc<UdpSocket>,
       server_addr: SocketAddr,
       udp_port: Arc<Mutex<u16>>,
       mut stop_udp_rx: oneshot::Receiver<()>,
   ) -> ResultType<()> {
       let start = Instant::now();
       let mut msg_out = RendezvousMessage::new();
       msg_out.set_test_nat_request(TestNatRequest::default());

       let mut retry_interval = Duration::from_millis(20); // 初始激进探测（20ms）
       const MAX_INTERVAL: Duration = Duration::from_millis(200);
       
       let data = msg_out.write_to_bytes()?;
       // 双发首包以抗突发丢包
       for _ in 0..2 {
           udp_socket.send_to(&data, server_addr).await.ok();
       }
       let mut buf = [0u8; 1500];
       loop {
           tokio::select! {
               _ = &mut stop_udp_rx => break,
               _ = hbb_common::sleep(retry_interval.as_secs_f32()) => {
                   // 指数退避重试探测包
                   udp_socket.send_to(&data, server_addr).await.ok();
                   retry_interval = std::cmp::min(
                       Duration::from_millis((retry_interval.as_millis() as f64 * 1.5) as u64),
                       MAX_INTERVAL
                   );
               }
               res = udp_socket.recv(&mut buf[..]) => {
                   if let Ok(n) = res {
                       if let Ok(msg_in) = RendezvousMessage::parse_from_bytes(&buf[0..n]) {
                           if let Some(rendezvous_message::Union::TestNatResponse(response)) = msg_in.union {
                               // 记录服务器反射观察到的公网 NAT 映射端口
                               *udp_port.lock().unwrap() = response.port as u16;
                               break;
                           }
                       }
                   }
               }
           }
       }
       Ok(())
   }

通过两次向不同的服务器端口发送探测包，客户端对比反射回来的端口号 $P_1$ 与 $P_2$：
* 若 $P_1 == P_2$，判定为 **ASYMMETRIC（锥型）**；
* 若 $P_1 
e P_2$，判定为 **SYMMETRIC（对称型）**。

---
UDP Hole Punching 完整打洞交互时序
---

当主控端（Peer A）发起对受控端（Peer B）的连接时，双方通过注册服务器（``hbbs``）进行信令交换并执行双向打洞：

```
[Peer A (主控端)]                 [hbbs 注册服务器]                 [Peer B (受控端)]
       │                                  │                                  │
       ├─ 1. PunchHoleRequest ───────────>│                                  │
       │    (携带 A 的 NAT 类型与端口)      ├─ 2. PunchHole 信令下发 ─────────>│
       │                                  │    (携带 A 的公网映射 IP:Port)   │
       │                                  │                                  ├─ 3. 向 A 发送 UDP 探测包
       │                                  │                                  │    (在 B 网关打通 A 出口)
       │                                  │                                  │
       │<─ 4. PunchHoleResponse ──────────┤                                  ├─ 4. udp_nat_listen 开启
       │    (携带 B 的公网映射 IP:Port)   │                                  │
       │                                  │                                  │
       ├─ 5. 向 B 发送 UDP 探测包 ──────────────────────────────────────────>│ (穿透 B 网关！)
       │                                  │                                  │
       │<===================== 6. KCP 握手成功 / 建立直连 P2P 隧道 ============>│
```

1. 受控端主动打洞与监听（``punch_udp_hole``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当受控端收到 ``hbbs`` 下发的 ``PunchHole`` 消息后，在 ``src/rendezvous_mediator.rs`` 中触发打洞：

.. code-block:: rust
   :caption: 受控端 UDP 打洞与握手监听（src/rendezvous_mediator.rs）

   async fn punch_udp_hole(
       &self,
       peer_addr: SocketAddr,
       server: ServerPtr,
       msg_punch: PunchHoleSent,
       meta: ConnectionMeta,
   ) -> ResultType<()> {
       let mut msg_out = Message::new();
       msg_out.set_punch_hole_sent(msg_punch);
       let (socket, addr) = new_direct_udp_for(&self.host).await?;
       let data = msg_out.write_to_bytes()?;
       
       // 1. 向主控端的公网地址发送 UDP 探测数据报（在自身路由器防火墙上开凿通道条目）
       socket.send_to(&data, addr).await?;
       let socket_cloned = socket.clone();
       
       // 2. 异步延时重发 2 次以对抗网络丢包
       tokio::spawn(async move {
           for _ in 0..2 {
               let tm = (hbb_common::time_based_rand() % 20 + 10) as f32 / 1000.;
               hbb_common::sleep(tm).await;
               socket.send_to(&data, addr).await.ok();
           }
       });
       
       // 3. 进入 UDP 监听与 KCP 流接收状态
       udp_nat_listen(socket_cloned, peer_addr, peer_addr, server, meta).await?;
       Ok(())
   }

---
多路并发竞速与中继平滑回退 (``select_ok``)
---

公网环境极其复杂，单纯依赖单一网络路径极易导致连接失败。RustDesk 在 ``src/client.rs`` 中采用了**四路并发竞速模型（Concurrent Multi-Path Racing）**：

.. code-block:: rust
   :caption: 多路并发打洞与自适应抢占（src/client.rs::_start_inner）

   let mut connect_futures = Vec::new();

   // 1. IPv4 TCP 直连尝试（局域网或公网直接暴露端口）
   let fut_tcp = connect_tcp_local(peer_addr, Some(local_addr), connect_timeout);
   connect_futures.push(async move {
       let conn = fut_tcp.await?;
       Ok((conn, None, "TCP"))
   }.boxed());

   // 2. IPv4 UDP 打洞 + KCP
   if let Some(udp_socket_nat) = udp_socket_nat {
       connect_futures.push(udp_nat_connect(udp_socket_nat, "UDP", connect_timeout).boxed());
   }

   // 3. IPv6 UDP 直连 + KCP（利用 IPv6 无 NAT 特性直连）
   if let Some(udp_socket_v6) = udp_socket_v6 {
       connect_futures.push(udp_nat_connect(udp_socket_v6, "IPv6", connect_timeout).boxed());
   }

   // 4. select_ok 并发竞速：优先采用最快建立直连的通道
   let (mut conn, kcp, mut typ) = match select_ok(connect_futures).await {
       Ok(conn) => (Ok(conn.0.0), conn.0.1, conn.0.2),
       Err(e) => (Err(e), None, ""),
   };

   // 5. 若所有 P2P 路径均超时失败（或检测到 Symmetric NAT），平滑回退至 hbbr 中继服务器
   if interface.is_force_relay() || conn.is_err() {
       conn = Self::request_relay(
           peer_id, relay_server, rendezvous_server,
           !signed_id_pk.is_empty(), key, token, conn_type, &switch_code
       ).await;
       typ = "Relay";
   }

自适应超时计算
~~~~~~~~~~~~~~

为了在保证打洞成功率的同时避免用户过长等待，超时时间根据 NAT 类型与历史打洞时延动态伸缩：

.. math::

   T_{	ext{timeout}} = \begin{cases}
   1000\,	ext{ms} & 	ext{局域网直连 或 对称型 NAT (直接转中继)} \
   T_{	ext{punch}} 	imes 6 & 	ext{非对称型 NAT 正常打洞 (给予充足探测窗口)} \
   T_{	ext{punch}} 	imes 3 & 	ext{曾发生直连失败时的快速降级窗口}
   \end{cases}

***
小结与下章导读
***

本章全面解构了 RustDesk 穿透复杂网络网关的 P2P 核心技术：
* 剖析了四类 NAT 行为模型及锥型与对称型 NAT 的物理穿透判定矩阵。
* 拆解了基于 ``TestNatRequest`` / ``TestNatResponse`` 的 STUN 端口反射与探测算法。
* 揭示了受控端与主控端通过 ``hbbs`` 协同的双向 UDP Hole Punching 状态机。
* 剖析了基于 ``select_ok`` 的 IPv4/IPv6/TCP/UDP 四路并发打洞竞速与 ``hbbr`` 中继平滑回退架构。

在下一节中，我们将深入信令调度的全局中枢：
* **《03.04 rendezvous_mediator 状态机与连接建立全流程》**：解析客户端守护进程如何维持与自建/公共注册服务器的长连接心跳、处理设备迁移（UUID Mismatch）、动态配置热更新与会话生命周期调度。
