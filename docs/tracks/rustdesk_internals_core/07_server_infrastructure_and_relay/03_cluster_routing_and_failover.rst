======================================================================
07.03 自建服务集群部署、证书认证与高可用故障转移
======================================================================

.. note:: 前置背景与上下文承接
   在前两章中，我们先后解剖了注册中枢 ``hbbs`` 的 Peer 寻址与在线状态机（《07.01》）以及数据中继 ``hbbr`` 的 UUID 握手配对与令牌桶限速流水线（《07.02》）。对于中大型企业、金融机构或注重数据绝对隐私的用户而言，依赖公网公共中继服务器不仅存在潜在的带宽瓶颈，更可能触犯数据主权合规要求。因此，**构建自主可控、多节点负载均衡且具备自动容灾能力（High Availability & Failover）的私有服务集群**，是生产级远程桌面系统的最终落地形态。本章作为全书的收官终章，将深入解剖 ``src/rendezvous_mediator.rs``、``src/common.rs`` 及 ``libs/hbb_common/src/config.rs``，系统梳理多节点中继集群编排、基于 Ed25519 的自签名私有证书安全背书、GeoDNS 地理亲和性路由与节点宕机自愈机制。

***
自建服务集群拓扑与多中继节点编排
***

在企业私有化部署架构中，信令与数据流应当在物理上解耦：将单点 ``hbbs`` 升级为高可用注册集群，并在全球各主要分支机构数据中心分布式部署多台独立的 ``hbbr`` 中继服务器：

```
                              [ 企业客户端集群 (主控端 / 受控端) ]
                                          │
                  ┌───────────────────────┴───────────────────────┐
                  │ (1. GeoDNS 智能解析 / 延迟探测)               │ (2. 携带 Ed25519 Server Key)
                  ▼                                               ▼
┌───────────────────────────────────┐           ┌───────────────────────────────────┐
│     信令中枢集群: hbbs Cluster    │           │     信令中枢集群: hbbs Cluster    │
│       (主节点: 华北机房)          │<─(心跳同步)─>│       (备节点: 华东机房)          │
└─────────────────┬─────────────────┘           └─────────────────┬─────────────────┘
                  │                                               │
                  ├───────────────────────┬───────────────────────┤
                  │ (根据客户端地理位置与负载动态下发最优中继池)   │
                  ▼                                               ▼
┌───────────────────────────────────┐           ┌───────────────────────────────────┐
│    中继节点 A: hbbr (北京 BGP)    │           │    中继节点 B: hbbr (上海 联通)   │
│   (带宽: 1Gbps, 承载华北并发流量) │           │   (带宽: 1Gbps, 承载华东并发流量) │
└───────────────────────────────────┘           └───────────────────────────────────┘
```

1. 多中继节点配置与动态下发
~~~~~~~~~~~~~~~~~~~~~~~~~~

管理员在启动 ``hbbs`` 时，通过 ``-r`` 参数指定全量候选数据中继服务器列表：

.. code-block:: bash
   :caption: hbbs 多中继集群启动指令

   ./hbbs -r "relay-bj.corp.com:21117,relay-sh.corp.com:21117,relay-sz.corp.com:21117" -k _

当主控端请求中继连接时，``hbbs`` 在返回的 ``RelayResponse`` 中动态注入最优中继节点地址，客户端无缝建立点对点转发隧道。

---
基于 Ed25519 的服务端公钥证书认证与防中间人劫持
---

在公网自建服务器环境中，必须防止恶意攻击者通过 DNS 污染、ARP 欺骗或搭建流氓中继服务器实施中间人攻击（MITM）。

RustDesk 设计了基于 **Ed25519 数字签名的私有证书授权体系**：

```
[自建服务端 hbbs (拥有私钥 id_ed25519)]                     [客户端 Client (预埋公钥 Key)]
                   │                                                        │
   1. 受控端注册 ID 与公钥 (RegisterPk)                                     │
   2. hbbs 使用私钥签发证书:                                                │
      Signature = Sign_Detached(Peer_ID + Peer_PK, id_ed25519)              │
                   │                                                        │
                   ├─ 3. 呼叫时下发被控端元数据与数字证书 ─────────────────>│
                   │     IdPk { id, pk: Peer_PK, sign: Signature }          │
                   │                                                        ├─ 4. 验真逻辑 (decode_id_pk):
                   │                                                        │    Verify(Signature, id + pk, Server_Key)
                   │                                                        │    * 签名有效: 确认来自正规私有集群
                   │                                                        │    * 签名失效: 阻断连接并弹窗告警！
```

1. 客户端证书签名强校验实现（``decode_id_pk``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``src/common.rs::decode_id_pk`` 中，客户端在发起会话前严格执行密码学校验：

.. code-block:: rust
   :caption: 服务端证书签名验证逻辑（src/common.rs）

   pub fn decode_id_pk(bytes: &[u8]) -> ResultType<(String, Vec<u8>)> {
       let msg = IdPk::parse_from_bytes(bytes)?;
       let server_pk = Config::get_key();
       
       if !server_pk.is_empty() {
           let sign_bytes = msg.get_sign();
           let mut content = msg.get_id().as_bytes().to_vec();
           content.extend_from_slice(msg.get_pk());
           
           // 利用客户端本地预埋的 Server 公钥验证被控端公钥的合法性
           if !sign::verify_detached(sign_bytes, &content, &sign::PublicKey::from_slice(&server_pk)?) {
               bail!("Server signature verification failed! Possible MITM attack or forged rendezvous server.");
           }
       }
       
       Ok((msg.get_id().to_string(), msg.get_pk().to_vec()))
   }

通过将 ``hbbs`` 生成的公钥字符串（``Key``）写入客户端配置，整个集群形成封闭的可信计算环境，彻底杜绝流氓服务器冒充。

---
GeoDNS 地理亲和性与基于 EMA 的动态延迟路由
---

为了在全球多机房集群中实现超低操作延迟，RustDesk 融合了 DNS 静态地理分流与客户端动态时延探测：

1. **GeoDNS 静态接入**：主控端发起 DNS 解析时，权威 DNS 根据客户端来源 IP 将 ``rendezvous.corp.com`` 自动解析至物理距离最近的 ``hbbs`` 节点；
2. **多节点心跳并发探测与 EMA 滤波**：
   客户端支持配置逗号分隔的多注册服务器列表（``host1,host2,host3``）。在 ``src/rendezvous_mediator.rs`` 中，客户端通过 ``tokio::spawn`` 并发向所有候选服务器发送 UDP 探测包，并计算指数加权移动平均时延（EMA Latency）：

   .. math::

      	ext{EMA}_t = 0.033 	imes 	ext{RTT}_t + 0.967 	imes 	ext{EMA}_{t-1}

   客户端始终优先将主连接绑定至当前 $	ext{EMA}$ 时延最低的优质服务器。

---
高可用故障转移（Failover）与网络自愈
---

生产环境中服务器宕机、光纤抖动或机房断电不可避免。RustDesk 状态机具备极强的韧性与自愈机制：

```
[并发监听候选服务器列表: join_all(futs)]
                 │
                 ▼ (检测到当前节点宕机 / 连续心跳失败 >= MAX_FAILS2)
[触发 Failover 熔断降级]
   ├── 1. 标记当前服务器 Latency = -1 (失效)
   ├── 2. 定时器检查超过 DNS_INTERVAL (60s) -> 触发重新 DNS 解析
   ├── 3. 调用 socket_client::rebind_udp_for 重新绑定 UDP 本地端口
   └── 4. 自动漂移切换至健康备用 rendezvous 节点重连
```

1. 周期性套接字重新绑定（``rebind_udp_for``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当宽带重拨号、网络从 Wi-Fi 漫游至 5G 或物理网卡重置时，旧的 UDP 套接字可能在操作系统内核中失效。``hbbs`` 客户端在连续失败 4 次心跳（``MAX_FAILS2``）后，主动销毁旧套接字并重新向 DNS 解析的新 IP 执行端口重绑定，实现无感知的网络自愈。

***
全书架构全景总结与回顾 (Architectural Panorama)
***

至此，《RustDesk 核心架构与远程桌面底层机制深度剖析》全书 **7 大模块、26 个深度章节** 已全量完工：

.. list-table:: 《RustDesk 核心架构与远程桌面底层机制深度剖析》全书知识图谱
   :widths: 15 25 60
   :header-rows: 1

   * - 模块编号
     - 核心主题
     - 攻坚技术深度与底层原语
   * - **模块 01**
     - 操作系统与硬件交互
     - DXGI Desktop Duplication、X11/Wayland Screencast、SendInput 输入注入、WASAPI/CoreAudio 音频混音、IddCx 虚拟显示驱动
   * - **模块 02**
     - 音视频媒体管线与编解码
     - YUV420/NV12 帧对齐与零拷贝、libvpx/libaom 软解多线程优化、NVENC/QSV/AMF/VideoToolbox 硬加速、ABR 码率自适应
   * - **模块 03**
     - 信令通道与 NAT 穿透
     - Protobuf 消息分帧、自研可靠 UDP / KCP 拥塞控制、STUN / NAT 端口预测打洞算法、rendezvous_mediator 状态机
   * - **模块 04**
     - 端到端加密与安全会话
     - NaCl Ed25519 身份认证、X25519 密钥协商、XSalsa20/ChaCha20-Poly1305 AEAD 流加密、2FA 与 Windows UAC 服务提权
   * - **模块 05**
     - 客户端架构与状态机
     - Tokio 多 Runtime 并发拓扑、客户端 8 阶段生命周期状态机、并发分块断点续传文件系统、TCP 端口转发与远程虚拟打印
   * - **模块 06**
     - Rust-Flutter 跨语言渲染
     - flutter_rust_bridge AST 代码生成、StreamSink 异步双层事件总线、DirectX 11 / Metal GPU Texture 显存直通渲染
   * - **模块 07**
     - 服务端架构与中继调度
     - hbbs 注册寻址服务器与两级状态存储、hbbr 盲转发中继与令牌桶限速、自建高可用集群与 Ed25519 私有证书验证

本专著构建起了一套从裸机硬件捕获、现代密码学通道、极速图形渲染到全球分布式服务编排的完整工业级系统知识体系。
