======================================================================
04.01 基于 NaCl / libsodium 的非对称密钥体系与 Ed25519 身份认证
======================================================================

.. note:: 前置背景与上下文承接
   在前三个模块中，我们先后构建了操作系统底层硬件抽象（模块 01）、音视频编解码与 QoS 流控（模块 02）以及基于 Protobuf 与可靠 UDP/KCP 的 P2P 穿透网络栈（模块 03）。至此，主控端与受控端之间已经能够建立端到端的数据传输通道。然而，公网传输面临着严峻的窃听、篡改与中间人攻击（Man-in-the-Middle, MITM）威胁。远程桌面拥有操作系统的最高控制权，一旦信道被伪造或劫持，将直接导致主机沦陷。现代远程桌面系统如何摆脱笨重且脆弱的 X.509 PKI 证书链体系，以极高的性能与强数学安全性构建身份信任？本章正式开启 **模块 04：端到端加密与安全会话**，深入剖析 RustDesk 在 ``src/common.rs`` 与 ``src/client.rs`` 中基于 **NaCl / libsodium 现代密码学库** 的非对称密钥模型与 Ed25519 身份签名体系。

***
现代密码学选型：为什么选择 Networking and Cryptography library (NaCl)
***

传统远程访问系统（如 RDP、早期 VNC 或老旧 SSH）多采用 RSA 密钥与 X.509 证书体系。但在轻量级、跨平台且要求毫秒级握手的远程桌面场景下，传统 PKI 暴露出严重缺陷：

1. **计算开销与密钥尺寸**：RSA-2048 签名与验签计算极为昂贵，在低功耗 ARM 移动端（Android/iOS）上显著增加 CPU 功耗并拖慢握手；而 Curve25519/Ed25519 仅需 32 字节（256 位）公钥即可提供等同甚至高于 RSA-3072 的安全强度。
2. **侧信道攻击免疫（Constant-Time Operation）**：Daniel J. Bernstein 设计的 NaCl 原语具备全平台常数时间执行特性，天生免疫基于缓存时间（Cache Timing）和分支预测的侧信道攻击。
3. **极简 API 与抗误用设计（Misuse-Resistant API）**：NaCl 抛弃了传统 OpenSSL 繁琐脆弱的密码套件协商，固定绑定经过严格同行评审的最强加密组合。

.. list-table:: RustDesk 采用的核心密码学原语架构
   :widths: 22 24 30 24
   :header-rows: 1

   * - 密码学原语
     - 底层算法与标准
     - 密钥 / 签名尺寸
     - 系统内承载核心职责
   * - **身份签名 (Sign)**
     - Ed25519 (EdDSA on Curve25519)
     - 公钥 32B，私钥 64B，签名 64B
     - 设备数字指纹、中继认证、CA 签名与防篡改
   * - **密钥协商 (Box)**
     - X25519 (ECDH)
     - 临时公钥 32B，私钥 32B
     - 客户端间临时对称密钥的安全派生与信封封装
   * - **会话加密 (SecretBox)**
     - XSalsa20-Poly1305 / ChaCha20
     - 密钥 32B (256-bit)，Nonce 24B/12B
     - 音视频媒体流与键鼠控制帧的实时 AEAD 加密

---
Ed25519 身份密钥生成与设备指纹体系
---

在 RustDesk 中，每台设备在首次安装或初始化时，均会在本地私有配置中生成一组永久的 Ed25519 签名密钥对：

.. code-block:: rust
   :caption: 客户端身份密钥对生成与指纹格式化（src/common.rs）

   // 1. 生成 32 字节 Ed25519 公私钥对
   let (pk, sk) = sodiumoxide::crypto::sign::gen_keypair();

   // 2. 将 32 字节二进制公钥转化为 16 进制 4 字符分组的设备安全指纹
   pub fn pk_to_fingerprint(pk: Vec<u8>) -> String {
       let s: String = pk.iter().map(|u| format!("{:02x}", u)).collect();
       s.chars()
           .enumerate()
           .map(|(i, c)| {
               if i > 0 && i % 4 == 0 {
                   format!(" {}", c)
               } else {
                   format!("{}", c)
               }
           })
           .collect()
   }

此公钥作为受控端的**密码学数字身份证**。即使两台机器在局域网内分配到相同的主机名，其密码学指纹在数学上也具有全局唯一性。

---
注册服务器（``hbbs``）轻量 CA 证书背书与防中间人（MITM）机制
---

若主控端直接通过未经验证的信道获取受控端公钥，公网上的恶意攻击者（或被劫持的中继节点）可以轻易实施中间人替换（将受控端公钥替换为攻击者自己的公钥）。

RustDesk 构建了**基于注册服务器公钥（``rs_pk``）的轻量级单级 CA 签名背书体系**：

```
[受控端 Controlled Host]             [注册服务器 hbbs (拥有私钥 rs_sk)]             [主控端 Client]
          │                                         │                                    │
          ├─ 1. RegisterPk (ID + pk) ──────────────>│                                    │
          │                                         ├─ 2. 生成签名:                      │
          │                                         │     signed_id_pk =                 │
          │                                         │       Sign(ID + pk, rs_sk)         │
          │                                         │                                    │
          │                                         │<─ 3. PunchHoleRequest (发起呼叫) ──┤
          │                                         │                                    │
          │                                         ├─ 4. PunchHoleResponse ────────────>│
          │                                         │     (下发 signed_id_pk)            │
          │                                         │                                    ├─ 5. 校验签名:
          │                                         │                                    │    Verify(signed_id_pk,
          │                                         │                                    │           rs_pub_key)
          │<=================== 6. 确认对端公钥绝对真实 / 启动端到端加密握手 =====================>│
```

1. 签名载体：``IdPk`` 结构解析
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在服务端内部，设备 ID 与公钥被序列化为 Protobuf 结构体 ``IdPk``，并使用 ``hbbs`` 的私钥完成签名。

2. 主控端签名验证流水线（``decode_id_pk``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在主控端发起连接时，严格验证 ``signed_id_pk`` 的签名有效性：

.. code-block:: rust
   :caption: 服务端背书签名校验与 ID 绑定验证（src/common.rs::decode_id_pk）

   pub fn decode_id_pk(signed: &[u8], key: &sign::PublicKey) -> ResultType<(String, [u8; 32])> {
       // 使用预置或配置的注册服务器公钥验证数字签名
       let verified_bytes = sign::verify(signed, key)
           .map_err(|_| anyhow!("Signature mismatch: MITM attack detected or untrusted server"))?;
       
       // 反序列化 IdPk 载体
       let res = IdPk::parse_from_bytes(&verified_bytes)?;
       
       if let Some(pk) = get_pk(&res.pk) {
           Ok((res.id, pk))
       } else {
           bail!("Wrong their public length");
       }
   }

通过该机制，即使通信流经过不受信任的第三方中继节点（``hbbr``），中继节点也无法伪造或篡改受控端的公钥，因为任何篡改都会直接导致 ``sign::verify`` 失败并中断握手。

---
信令通道握手安全：``secure_tcp`` 状态机
---

在客户端与注册服务器（``hbbs``）建立 TCP 传输通道时，为了防止信令被局域网嗅探，RustDesk 同样执行基于 Ed25519 的密钥交换（``KeyExchange``）：

.. code-block:: rust
   :caption: TCP 信令通道密钥交换与加密激活（src/common.rs::secure_tcp_impl）

   async fn secure_tcp_impl(conn: &mut Stream, key: &str, log_on_success: bool) -> ResultType<()> {
       if use_ws() { return Ok(()); } // WSS 原生提供 TLS 传输加密
       let rs_pk = get_rs_pk(key).context("Invalid public key from rendezvous server")?;
       
       // 1. 接收服务端下发的第一阶段协商报文
       if let Some(Ok(bytes)) = timeout(READ_TIMEOUT, conn.next()).await? {
           let msg_in = RendezvousMessage::parse_from_bytes(&bytes)?;
           if let Some(rendezvous_message::Union::KeyExchange(ex)) = msg_in.union {
               // 2. 校验服务端的签名真实性
               let their_pk_b = sign::verify(&ex.keys[0], &rs_pk)
                   .map_err(|_| anyhow!("Signature mismatch in key exchange"))?;
               
               // 3. 派生临时对称会话密钥
               let (asymmetric_value, symmetric_value, key) = create_symmetric_key_msg(
                   get_pk(&their_pk_b).context("Wrong public key length")?,
               );
               
               // 4. 回传密封对称密钥
               let mut msg_out = RendezvousMessage::new();
               msg_out.set_key_exchange(KeyExchange {
                   keys: vec![asymmetric_value, symmetric_value],
                   ..Default::default()
               });
               timeout(CONNECT_TIMEOUT, conn.send(&msg_out)).await??;
               
               // 5. 将对称密钥注入底层 Stream，后续所有流数据自动执行透明 AEAD 加密
               conn.set_key(key);
           }
       }
       Ok(())
   }

***
小结与下章导读
***

本章深入剖析了 RustDesk 基于 NaCl / libsodium 的安全信任底座：
* 阐明了 Ed25519 在性能、密钥尺寸及常数时间抗侧信道攻击上的物理优势。
* 剖析了设备本地 Ed25519 签名密钥对的生成机制与 16 进制分组指纹算法（``pk_to_fingerprint``）。
* 揭示了基于注册服务器私钥签名的 ``IdPk`` 轻量 CA 信任链，杜绝公网中间人（MITM）篡改。
* 解构了信令通道通过 ``secure_tcp`` 执行身份验证与对称密钥派生的完整状态机。

在下一节中，我们将深入端到端会话建立的核心协商算法：
* **《04.02 X25519 密钥协商与临时会话对称密钥派生》**：深入解析基于 Diffie-Hellman（ECDH）的临时密钥对生成、Curve25519 椭圆曲线标量乘法、Sealed Box 匿名公钥加密以及前向保密（PFS）机制。
