======================================================================
07.02 中继服务器 (hbbr) 高并发数据转发与限速模型
======================================================================

.. note:: 前置背景与上下文承接
   在前一章《07.01 注册与 ID 寻址服务器 (hbbs) 架构与 Peer 状态存储》中，我们解剖了注册服务器 ``hbbs`` 如何通过 UDP/TCP 异步信令监听、全局在线路由表与公钥验证协调整个分布式网络。然而，在真实的复杂公网环境中，当通信双方均处于**对称型 NAT（Symmetric NAT）**之后，或者企业级严格防火墙拦截了所有不可靠 UDP 数据报时，P2P 直连打洞将不可避免地宣告失败。为了保证远程桌面连接的 $100\%$ 可达性，系统必须平滑降级至数据中继模式。在开源生态中，这一高吞吐数据搬运工的角色由 **``hbbr``（HeartBeat / Relay Server）** 承担。本章将系统解剖 ``hbbr`` 的 UUID 会话握手配对状态机、全双工零拷贝数据转发流水线以及基于令牌桶（Token Bucket）的流量整形与限速模型。

***
``hbbr`` 中继拓扑与端到端盲转发（Blind Proxy）架构
***

``hbbr`` 专注于纯粹的高并发字节流转发。在物理拓扑中，``hbbr`` 监听原生 TCP 端口 **21117** 与 WebSocket 端口 **21119**（供 Web Client 使用）：

```
[主控端 Controller (Client A)]                            [受控端 Host (Client B)]
             │                                                          │
             ├─ 1. TCP Connect (21117)                                  ├─ 1. TCP Connect (21117)
             ├─ 2. RequestRelay { uuid: "U-1" }                         ├─ 2. RelayResponse { uuid: "U-1" }
             │                                                          │
             ▼                                                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RustDesk 数据中继服务器: hbbr (Relay Server)              │
│                                                                             │
│  [21117/TCP: 原生 TCP 流量中继]               [21119/TCP: WebSocket 网页端中继] │
├─────────────────────────────────────────────────────────────────────────────┤
│  [UUID 会话配对池 (DashMap<String, WaitingSocket>)]                          │
│  - 查找匹配 UUID -> 取出 Socket A 与 Socket B 形成双向绑定管道               │
├─────────────────────────────────────────────────────────────────────────────┤
│  [全双工异步转发泵 (tokio::io::copy_bidirectional)]                          │
│  - Socket A (Rx) ──[Token Bucket 限速]──> Socket B (Tx)                     │
│  - Socket B (Rx) ──[Token Bucket 限速]──> Socket A (Tx)                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

.. list-table:: P2P 直连与 ``hbbr`` 中继模式核心指标对比
   :widths: 20 25 28 27
   :header-rows: 1

   * - 通信维度
     - P2P 直连模式 (UDP / KCP / TCP)
     - ``hbbr`` 中继模式 (TCP Relay)
     - 安全与性能物理影响
   * - **网络路径**
     - 端到端直接通信，不经过任何第三方
     - 经过中继服务器转发（两段独立的 TCP 连接）
     - 中继模式延迟略增（取决于中继服务器地理位置）
   * - **NAT 穿透要求**
     - 要求至少一方为 Cone NAT 或端口可预测
     - 仅要求双方均能单向发起出站 TCP 连接
     - 穿透成功率 $100\%$，完美绕过企业防火墙
   * - **端到端机密性**
     - 端到端 AEAD 密钥加密（XSalsa20/ChaCha20）
     - 端到端 AEAD 密钥加密（中继服务器仅做盲转发）
     - ``hbbr`` 无法解密音视频与输入控制流，绝无数据泄露风险

---
UUID 会话握手配对状态机
---

主控端与受控端在被 ``hbbs`` 分派到同一台 ``hbbr`` 节点后，双方各自发起独立的 TCP 连接。``hbbr`` 如何以微秒级时延将这两条异构的 TCP 连接精确“缝合”在一起？

``hbbr`` 维护了一个高并发无锁哈希表（如 ``DashMap<String, (TcpStream, Instant)>``），执行**基于单次会话 UUID 的原子配对状态机**：

```
[连接到达: Socket A] ──> 读取握手帧提取 UUID
                             │
                             ├─ 查询 UUID 是否已在等待池中？
                             │
            ┌────────────────┴────────────────┐
            ▼ (否: 成为等待者)                ▼ (是: 成为配对者)
   [存入等待池 (UUID -> Socket A)]      [从等待池原子取出 Socket A]
   [启动 30s 租约超时定时器]            [与当前 Socket B 组装为转发管道]
            │                                 │
   (30s 内无对端连接则断开释放)         [启动 tokio::io::copy_bidirectional]
```

.. code-block:: rust
   :caption: hbbr 会话配对与管道拉起逻辑模型

   async fn handle_relay_connection(
       mut socket: TcpStream,
       waiting_peers: Arc<DashMap<String, (TcpStream, Instant)>>,
   ) -> ResultType<()> {
       // 1. 读取 4 字节长度分帧与 Protobuf 握手消息
       let msg = read_relay_message(&mut socket).await?;
       let uuid = msg.get_uuid().to_string();

       // 2. 在并发等待表中执行原子配对
       let paired_socket = match waiting_peers.remove(&uuid) {
           Some((_, (peer_socket, _))) => {
               log::info!("Successfully paired relay session for UUID: {}", uuid);
               peer_socket
           }
           None => {
               // 作为首个到达的端点进入等待状态，启动 30 秒超时清理
               waiting_peers.insert(uuid.clone(), (socket, Instant::now()));
               return Ok(());
           }
       };

       // 3. 配对成功：拉起全双工流转发泵
       tokio::spawn(async move {
           run_bidirectional_relay(paired_socket, socket).await.ok();
       });

       Ok(())
   }

---
全双工零拷贝数据转发流水线
---

在完成握手配对后，``hbbr`` 进入纯粹的数据转发阶段。远程桌面流量包含 $4	ext{K}$ 视频大包与高频鼠标微包，对转发吞吐与时延极其敏感：

1. ``tokio::io::copy_bidirectional`` 转发泵
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

转发协程直接调用 Tokio 底层异步 I/O 组合原语：

.. code-block:: rust
   :caption: 双向零拷贝数据泵（架构模型）

   async fn run_bidirectional_relay(mut a: TcpStream, mut b: TcpStream) -> ResultType<()> {
       // 开启 TCP_NODELAY，关闭 Nagle 算法，确保高频控制微包立即发送
       a.set_nodelay(true).ok();
       b.set_nodelay(true).ok();

       // 在两个套接字之间执行全双工零拷贝字节流转发
       let (from_a_to_b, from_b_to_a) = tokio::io::copy_bidirectional(&mut a, &mut b).await?;
       
       log::debug!("Relay session ended. A->B: {} bytes, B->A: {} bytes", from_a_to_b, from_b_to_a);
       Ok(())
   }

2. 操作系统内核级零拷贝（Zero-Copy Splice）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 Linux 操作系统环境下，高级中继实现可通过系统调用 ``splice(2)`` 直接在两个 TCP 套接字的文件描述符（File Descriptors）之间通过内核管道（Pipe Buffer）转移数据页（Page Cache），**完全避免将数据包拷贝至用户空间内存**，极大地降低了高吞吐场景下的 CPU 缓存污染与上下文切换开销。

---
基于令牌桶（Token Bucket）的流量整形与限速算法
---

为了防止个别高带宽会话（如超大文件并发下载）挤占整个中继服务器的网络出口带宽，导致其他远程桌面用户的控制流产生严重卡顿，``hbbr`` 引入了**非阻塞令牌桶限速器（Token Bucket Rate Limiter）**：

1. 令牌桶数学模型
~~~~~~~~~~~~~~~~

.. math::

   T(t) = \min\left(C, T(t - \Delta t) + r 	imes \Delta t\right)

* $C$：令牌桶最大容量（Burst Capacity，允许瞬间突发流量）；
* $r$：令牌生成速率（Fill Rate，对应服务器配置的限速阈值，如 $10\,	ext{MB/s}$）；
* $T(t)$：当前可用令牌数（字节数）。

```
        令牌源 (以恒定速率 r 补充令牌)
                 │
                 ▼
        ┌─────────────────┐
        │  令牌桶 (容量 C) │
        └────────┬────────┘
                 │ (消耗与数据包尺寸等额的令牌)
                 ▼
待发送数据 ──[ 检查可用令牌 ]──> 放行发送 / 令牌不足则异步挂起 Future (Backpressure)
```

2. 异步背压与 TCP 零窗口（Zero-Window）自适应阻尼
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当会话消耗带宽超过预设速率时，限速器不会粗暴丢包（避免引发 TCP 重传风暴），而是挂起对应协程的读取 Future：
* 发送端本地缓冲区被填满；
* TCP 协议栈向客户端发送 Window Size = 0 确认报文（Zero-Window Probing）；
* 客户端底层自动降低发送速率，实现优雅的物理端到端背压流控。

---
连接生命周期回收与 DoS 防御策略
---

中继服务器需要保证长期无人值守稳定运行，必须严防连接泄露与恶意资源耗尽：

1. **确定性级联回收**：一旦通信链路中任意一端主动调用 ``close()`` 或因网络异常收到 TCP RST/FIN，双向数据泵立即退出，并同时触发对端 Socket 的 ``shutdown()``，释放操作系统文件描述符；
2. **最大并发连接保护（``--max-clients``）**：当并发活跃连接数达到系统上限时，服务器对新入站握手实施快速拒绝，防止触发操作系统的内存溢出（OOM）。

***
小结与下章导读
***

本章系统解构了 RustDesk 数据中继服务 ``hbbr`` 的核心技术架构：
* 阐明了在对称 NAT 与严格防火墙下作为 $100\%$ 可达保底方案的中继物理拓扑。
* 剖析了基于 UUID 的高速内存配对状态机与 30 秒无锁租约超时回收机制。
* 揭示了端到端盲转发（Blind Proxy）加密机密性与 ``copy_bidirectional`` 零拷贝转发流水线。
* 拆解了基于令牌桶算法的流量整形、TCP 零窗口背压阻尼与高并发连接资源保护。

在下一节中，我们将迎来全书的收官之作：
* **《07.03 自建服务集群部署、证书认证与高可用故障转移》**：深入解析 RustDesk 自建私有化服务器集群的架构规划、DNS 轮询与地理亲和性路由、基于 Ed25519 的自签名证书安全认证，以及多节点中继的高可用故障转移（Failover）实战体系。
