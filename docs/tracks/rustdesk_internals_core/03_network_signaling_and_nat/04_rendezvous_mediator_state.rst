======================================================================
03.04 rendezvous_mediator 状态机与连接建立全流程
======================================================================

.. note:: 前置背景与上下文承接
   在前三章中，我们先后解剖了 Protobuf 协议模型（《03.01》）、KCP 可靠 UDP 传输层（《03.02》）以及双向 UDP Hole Punching P2P 打洞机制（《03.03》）。在整个远程桌面生命周期中，无论是设备开机后的公网身份注册、NAT 端口映射保活，还是主控端发起呼叫时的信令中继与设备迁移，都需要一个始终驻留在后台的**信令协调中枢**。在 RustDesk 架构中，这一核心引擎被命名为 **``rendezvous_mediator``**。本章将深入剖析 ``src/rendezvous_mediator.rs``，系统解构受控端后台服务与注册服务器（``hbbs``）之间的心跳保活状态机、网络故障自愈重绑、UUID Mismatch 冲突消解以及端到端连接建立的全局调度流水线。

***
``rendezvous_mediator`` 守护进程拓扑与生命周期
***

在受控端启动时，``RendezvousMediator::start_all()`` 构成了服务端的核心网络入口点。它并发初始化了四大子系统：

1. **直接局域网访问监听（``direct_server``）**：在本地 TCP 端口（默认 21118）监听局域网直连流量，绕过外网信令。
2. **局域网设备广播发现（``lan::start_listening``）**：通过 UDP 组播广播自身存在，实现局域网设备免 ID 发现。
3. **HTTP 同步与配置中心（``hbbs_http::sync``）**：处理地址簿、企业授权与 Web 控制台同步。
4. **信令协调工作线程池（``start_udp / start_tcp``）**：与配置的一个或多个注册服务器（``hbbs``）维持双向长连接。

.. list-table:: 信令传输通道双模架构对比
   :widths: 20 25 30 25
   :header-rows: 1

   * - 通道类型
     - 底层协议
     - 适用网络环境
     - 核心优势
   * - **UDP 信令通道 (默认)**
     - 无连接 UDP + 定时注册包
     - 标准互联网宽带、移动蜂窝网络
     - 零握手延迟，天然支持 NAT 端口反射
   * - **TCP/WS 信令通道 (回退)**
     - 阻塞/非阻塞 TCP / WebSocket
     - 企业 HTTP 代理环境、UDP 彻底被封禁的内网
     - 强穿透防火墙，支持 TLS 加密封装

---
注册与保活状态机 (Registration & Keep-Alive FSM)
---

客户端与 ``hbbs`` 之间通过周期性心跳维持网关 NAT 映射表项的有效性（防止防火墙在 30~60 秒无流量后关闭 UDP 端口）：

```
[未注册状态 / 启动]
         │
         ├─ 1. 发送 RegisterPk (携带 Ed25519 公钥 + 硬件 UUID)
         │
         ▼
[RegisterPkResponse 判定] ──┬─ OK ──────────────> [已认证稳态 (Key Confirmed)]
                            │                           │
                            ├─ UUID_MISMATCH            ├─ 2. 周期性发送 RegisterPeer (心跳)
                            │  (生成新 ID 并重新注册)   │     (带 serial 序列号与 EMA 延迟采样)
                            │                           │
                            └─ NOT_DEPLOYED             ▼
                               (未授权，进入 30s 退避) [检测到超时 / 异常断开]
                                                        │
                                                        └─ 3. 重走 RegisterPk / 重新解析 DNS
```

1. 注册消息双阶模型：``RegisterPk`` 与 ``RegisterPeer``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* **``RegisterPk``（强身份认证）**：
  在连接建立之初或密钥未确认时发送，包含本机的唯一设备 ID、机器全局唯一硬件码（``uuid``）以及 Ed25519 签名公钥（``pk``）。服务端完成签名绑定后返回 ``RegisterPkResponse``。
* **``RegisterPeer``（轻量心跳）**：
  在密钥确认后周期性发送（默认间隔 ``REG_INTERVAL``），仅携带 ID 与配置序列号（``serial``），用于刷新服务端的在线路由表项与维持 NAT 端口保活。

2. 指数移动平均时延估算 (EMA Latency)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了准确获知受控端与服务器之间的通信质量并反馈给 UI，``rendezvous_mediator`` 引入了指数加权移动平均算法：

.. math::

   	ext{Latency}_{	ext{EMA}} = \frac{1}{30} 	imes 	ext{Latency}_{	ext{current}} + \frac{29}{30} 	imes 	ext{Latency}_{	ext{EMA}}

.. code-block:: rust
   :caption: 信令延迟平滑更新与动态上报（src/rendezvous_mediator.rs）

   let mut update_latency = || {
       last_register_resp = Some(Instant::now());
       fails = 0;
       reg_timeout = MIN_REG_TIMEOUT;
       let mut latency = last_register_sent
           .map(|x| x.elapsed().as_micros() as i64)
           .unwrap_or(0);
       last_register_sent = None;
       
       if latency < 0 || latency > 1_000_000 { return; }
       if ema_latency == 0 {
           ema_latency = latency;
       } else {
           // 30 周期加权移动平均，平滑网络突发尖峰
           ema_latency = latency / 30 + (ema_latency * 29 / 30);
           latency = ema_latency;
       }
       if (latency - old_latency).abs() > 3000 || old_latency <= 0 {
           Config::update_latency(&host, latency);
           old_latency = latency;
       }
   };

---
网络故障自愈与动态套接字重绑 (Socket Rebinding)
---

在移动办公或拨号宽带环境下，受控主机的物理网络可能在 Wi-Fi/有线网卡切换或 PPPoE 重拨后发生 IP 变更。原先打开的 UDP 套接字可能在操作系统内核中失效，导致后续发包被底层网卡丢弃。

RustDesk 在 ``start_udp`` 事件循环中设计了**双阶故障熔断与 DNS 自动刷新重绑机制**：

.. code-block:: rust
   :caption: 连续丢包熔断与套接字重绑（src/rendezvous_mediator.rs）

   const MAX_FAILS1: i64 = 2;
   const MAX_FAILS2: i64 = 4;
   const DNS_INTERVAL: i64 = 60_000; // 1 分钟强制 DNS 刷新窗口

   if timeout {
       fails += 1;
       if fails >= MAX_FAILS2 {
           Config::update_latency(&host, -1); // 标记当前服务器不可达
           old_latency = 0;
           
           // 当连续 4 次心跳失败且超过 1 分钟时，强制重新解析域名并重绑 UDP 套接字
           if last_dns_check.elapsed().as_millis() as i64 > DNS_INTERVAL {
               if let Some((s, new_addr)) = socket_client::rebind_udp_for(&rz.host).await? {
                   socket = s;
                   rz.addr = new_addr.clone();
                   addr = new_addr;
                   log::info!("UDP Socket successfully rebound to new address: {:?}", addr);
               }
               last_dns_check = Instant::now();
           }
       } else if fails >= MAX_FAILS1 {
           Config::update_latency(&host, 0); // 标记网络不稳定
       }
   }

---
异常冲突处理：UUID Mismatch 与动态配置热更新
---

1. 设备克隆与 ID 冲突消解（``UUID_MISMATCH``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当用户将操作系统整盘克隆镜像部署到新电脑上时，两台机器会持有相同的 RustDesk ID 但具备不同的硬件 UUID。此时新机器向 ``hbbs`` 注册会触发 ``UUID_MISMATCH`` 错误。

RustDesk 的自愈逻辑为：
* 收到 ``UUID_MISMATCH`` 后，强制清除本地密钥确认标记（``Config::set_key_confirmed(false)``）；
* 调用 ``Config::update_id()`` 基于新硬件生成全新随机 ID；
* 立即使用新 ID 与本机公钥重新发送 ``RegisterPk``，完成新设备的自动无感接入。

2. 集群配置广播与热重启（``ConfigureUpdate``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当自建企业服务端的注册服务器集群发生扩容或变更时，``hbbs`` 会下发带有版本序列号的 ``ConfigureUpdate`` 报文。``rendezvous_mediator`` 解析后比对版本号，直接将新服务器列表持久化写入本地配置，并通过原子标志位 ``SHOULD_EXIT.store(true)`` 触发协程热重启，平滑接入新集群。

---
端到端呼叫调度中枢：从信令到数据通道建立
---

当 ``hbbs`` 转发呼叫请求时，``rendezvous_mediator`` 负责拉起数据管道：

1. **收到 ``PunchHole``**：
   解析对端公网映射地址，调用 ``punch_udp_hole`` 向对端发送打洞包，并启动 ``udp_nat_listen`` 监听 KCP 握手；
2. **收到 ``RequestRelay``**：
   提取唯一的会话 ``uuid`` 与中继服务器地址（``relay_server``），异步发起向 ``hbbr`` 的 TCP 连接并完成中继会话绑定；
3. **收到 ``FetchLocalAddr``（局域网直连优化）**：
   探测双方是否处于同一子网内，若处于同网段则通过内网直连（``handle_intranet``），彻底免除公网流量。

***
小结与下章导读
***

至此，**模块 03：信令通道、Protobuf 与 NAT 穿透** 的四大核心基石已全部完工：
* 《03.01 Protobuf 协议模型设计与消息帧编解码》
* 《03.02 自研可靠 UDP / KCP 传输层与拥塞控制算法》
* 《03.03 NAT 类型探测与 UDP Hole Punching P2P 打洞机制》
* 《03.04 rendezvous_mediator 状态机与连接建立全流程》

系统已具备完整的全球公网寻址、打洞穿透、可靠 UDP 传输与后台保活自愈能力。

在接下来的 **模块 04：端到端加密与安全会话** 中，我们将深入远程控制的安全防御体系：
* **《04.01 基于 NaCl / libsodium 的非对称密钥体系与 Ed25519 身份认证》**：深入解析 RustDesk 如何基于现代密码学标准构建受控端/主控端的公私钥体系，防范中间人攻击（MITM）与伪造劫持。
