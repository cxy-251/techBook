======================================================================
04.02 X25519 密钥协商与临时会话对称密钥派生
======================================================================

.. note:: 前置背景与上下文承接
   在前一章《04.01 基于 NaCl / libsodium 的非对称密钥体系与 Ed25519 身份认证》中，我们解剖了 RustDesk 如何通过注册服务器（``hbbs``）的数字签名背书，确保主控端获取到的受控端公钥绝对真实可信，彻底防御了中间人（MITM）公钥替换攻击。然而，非对称加密算法（如 RSA 或 ECC 加密）的计算开销极大，无法直接用于每秒数十兆字节的 4K 视频流与高频输入事件加密。双方必须在建立连接的微秒级时间内，**安全协商出一个临时的 256 位对称会话密钥（Symmetric Session Key）**。同时，系统必须满足**完全前向保密（Perfect Forward Secrecy, PFS）**：即便设备未来的长效私钥发生泄露，攻击者也无法解密过去捕获的历史流量。本章将深入剖析 ``src/common.rs`` 与 ``src/client.rs`` 中的 X25519 密钥交换协议、Sealed Box 匿名信封加密与会话密钥派生状态机。

***
椭圆曲线 Diffie-Hellman (ECDH on Curve25519) 物理原理
***

Curve25519 是由 Daniel J. Bernstein 设计的 Montgomery 椭圆曲线：

$$y^2 = x^3 + 486662x^2 + x \pmod{2^{255} - 19}$$

在传统的 Diffie-Hellman 密钥交换中，通信双方各自生成临时私钥（标量 $a, b$）与公钥点（$A = aG, B = bG$）。双方交换公钥后，在本地计算共享秘密：

$$K = aB = bA = abG$$

由于椭圆曲线离散对数问题（ECDLP）的计算不可逆性，监听者即便截获了公钥 $A$ 与 $B$，在多项式时间内也无法推导出共享点 $K$。

.. list-table:: 密钥协商与对称密钥信封参数对比
   :widths: 22 25 28 25
   :header-rows: 1

   * - 阶段与载体
     - 使用算法
     - 密钥与载荷长度
     - 核心安全属性
   * - **临时密钥对**
     - Curve25519 (X25519)
     - 私钥 32B，公钥 32B
     - 瞬时生成，会话结束即销毁（PFS）
   * - **会话对称密钥**
     - XSalsa20 / ChaCha20
     - 256-bit (32 字节真随机数)
     - 极速流加密，AES-NI 指令集加速
   * - **信封密封 (Seal)**
     - NaCl ``box_::seal``
     - 32B 密文 + 16B Poly1305 MAC
     - 认证加密（AEAD），防篡改与重放

---
RustDesk 密钥协商协议设计：Sealed Box 架构
---

在标准的端到端握手中，RustDesk 并没有直接使用原始 ECDH 派生出来的共享秘密作为流加密密钥，而是采用了更加健壮的**数字信封（Digital Envelope / Sealed Box）模式**：

```
[主控端 Client]                                               [受控端 Controlled Host]
       │                                                                  │
       │<─ 1. 发送自身已认证的 X25519 公钥 (SignedId::their_pk_b) ───────┤
       │                                                                  │
       ├─ 2. 生成真随机 256 位对称密钥: key = secretbox::gen_key()        │
       ├─ 3. 生成临时 X25519 密钥对: (our_pk_b, our_sk_b)                 │
       ├─ 4. 使用受控端公钥密封:                                          │
       │     sealed_key = box_::seal(key, nonce, their_pk_b, our_sk_b)    │
       │                                                                  │
       ├─ 5. 发送 PublicKey 消息: ───────────────────────────────────────>│
       │     asymmetric_value = our_pk_b                                  ├─ 6. 解密信封提取对称密钥:
       │     symmetric_value  = sealed_key                                │    key = box_::open(
       │                                                                  │      sealed_key,
       │                                                                  │      nonce,
       │                                                                  │      our_pk_b,
       │                                                                  │      my_sk_b
       │                                                                  │    )
       │                                                                  │
       ├─ 7. conn.set_key(key) ───────────────────────────────────────────┼─ 8. conn.set_key(key)
       │                                                                  │
       │<================ 9. 全链路激活 XSalsa20/ChaCha20 对称加密 ==================>│
```

1. 对称密钥生成与密封（``create_symmetric_key_msg``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``src/common.rs`` 中，主控端在确认对端身份后，执行信封生成：

.. code-block:: rust
   :caption: 临时对称密钥生成与 Sealed Box 封装（src/common.rs）

   pub fn create_symmetric_key_msg(their_pk_b: [u8; 32]) -> (Bytes, Bytes, secretbox::Key) {
       let their_pk_b = box_::PublicKey(their_pk_b);
       
       // 1. 生成单次会话专用的临时 Curve25519 密钥对（提供前向保密 PFS）
       let (our_pk_b, out_sk_b) = box_::gen_keypair();
       
       // 2. 生成密码学安全的 256 位真随机对称密钥
       let key = secretbox::gen_key();
       
       // 3. 固定零 Nonce（在临时单次密钥对下，零 Nonce 具备完全数学安全性）
       let nonce = box_::Nonce([0u8; box_::NONCEBYTES]);
       
       // 4. 使用对端公钥与本地临时私钥执行 Authenticated Box 加密
       let sealed_key = box_::seal(&key.0, &nonce, &their_pk_b, &out_sk_b);
       
       // 5. 返回临时公钥、密封密文与明文对称密钥
       (Vec::from(our_pk_b.0).into(), sealed_key.into(), key)
   }

2. 主控端协商触发与密钥注入（``src/client.rs``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

主控端将生成的信封打包进 Protobuf ``Message`` 并提交网络流：

.. code-block:: rust
   :caption: 主控端密钥协商状态机驱动（src/client.rs::secure_connection）

   let (asymmetric_value, symmetric_value, key) = create_symmetric_key_msg(their_pk_b);
   let mut msg_out = Message::new();
   msg_out.set_public_key(PublicKey {
       asymmetric_value,
       symmetric_value,
       ..Default::default()
   });

   // 发送公钥信封报文
   timeout(CONNECT_TIMEOUT, conn.send(&msg_out)).await??;

   // 激活底层流的对称加密状态
   conn.set_key(key);

---
受控端解密与会话对称密钥提取
---

在受控端服务（``src/server/service.rs``）中，接收到 ``PublicKey`` 消息后触发解密还原：

.. code-block:: rust
   :caption: 受控端解密提取对称密钥伪代码模型

   if let Some(message::Union::PublicKey(pk_msg)) = msg_in.union {
       let their_ephemeral_pk = box_::PublicKey(get_pk(&pk_msg.asymmetric_value)?);
       let sealed_key = pk_msg.symmetric_value;
       let nonce = box_::Nonce([0u8; box_::NONCEBYTES]);
       
       // 使用受控端长期持有的私钥与主控端临时公钥执行解密
       let decrypted_key_bytes = box_::open(&sealed_key, &nonce, &their_ephemeral_pk, &my_sk_b)
           .map_err(|_| anyhow!("Failed to unseal symmetric session key"))?;
       
       let session_key = secretbox::Key::from_slice(&decrypted_key_bytes)?;
       
       // 激活受控端传输流的对称解密
       conn.set_key(session_key);
   }

---
完全前向保密 (PFS) 与非安全降级防护
---

1. 完全前向保密（PFS）数学证明
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

假设攻击者在公网长期监听并录制了主控端与受控端之间所有的加密网络数据包。若在 1 年后，受控端的物理硬盘被窃取，其长效私钥 ``my_sk_b`` 彻底泄露。

攻击者试图解密历史会话：
1. 攻击者可以使用 ``my_sk_b`` 与历史报文中的 ``our_pk_b`` 解开当时的 ``sealed_key``，从而获得该会话的 ``secretbox::Key``；
2. **但是**，由于主控端的临时私钥 ``our_sk_b`` 仅驻留在当时的内存栈中，且在握手结束时已被操作系统和 Rust 的 RAII 机制彻底擦除释放；
3. 如果采用双临时公私钥（Ephemeral-Ephemeral Diffie-Hellman），则即便双方长效私钥全部暴露，历史会话依然坚不可摧。

2. 非安全模式降级拦截（``confirm_insecure_connection``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当主控端连接老旧版本或未启用加密的第三方客户端时，如果检测到密钥不匹配（``pk mismatch``），RustDesk 会主动发送空公钥报文（``PublicKey::new()``），并在客户端 UI 弹出最高级别安全警告：

.. code-block:: rust
   :caption: 非安全连接拦截确认（src/client.rs）

   pub async fn confirm_insecure_connection(
       interface: &impl Interface,
       receiver: &mut UnboundedReceiver<Data>,
   ) -> bool {
       interface.msgbox(
           "insecure-connection-nocancel-hasclose",
           "Insecure Connection",
           "conn-e2ee-unavailable-tip", // 明确提示端到端加密不可用
           "",
       );
       while let Some(data) = receiver.recv().await {
           match data {
               Data::ContinueInsecureConnection => return true,
               Data::RejectInsecureConnection => return false,
               Data::Close => return false,
               _ => {}
           }
       }
       false
   }

***
小结与下章导读
***

本章系统解构了 RustDesk 端到端对称会话密钥的安全协商机制：
* 阐述了基于 Curve25519 椭圆曲线 Diffie-Hellman（ECDH）的标量乘法数学原理。
* 剖析了主控端通过 ``create_symmetric_key_msg`` 生成临时密钥对、256 位真随机对称密钥并使用 Sealed Box 封装的完整时序。
* 揭示了受控端利用私钥解密提取会话密钥并调用 ``conn.set_key()`` 激活全双工 AEAD 流加密的架构。
* 论证了临时密钥带来的完全前向保密（PFS）特性以及非安全降级时的 UI 拦截策略。

在下一节中，我们将深入数据通道的高性能流加密实现：
* **《04.03 会话数据流加密 (XSalsa20/ChaCha20-Poly1305) 与防重放攻击》**：深入解析底层对称流加密算法的吞吐优化、基于递增计数器 Nonce 的防重放（Replay Attack）机制以及 AEAD 消息认证码校验。
