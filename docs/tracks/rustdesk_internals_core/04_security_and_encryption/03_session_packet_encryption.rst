======================================================================
04.03 会话数据流加密 (XSalsa20/ChaCha20-Poly1305) 与防重放攻击
======================================================================

.. note:: 前置背景与上下文承接
   在前一章《04.02 X25519 密钥协商与临时会话对称密钥派生》中，我们解剖了主控端与受控端如何通过 Curve25519 临时密钥对与 Sealed Box 匿名信封，在毫秒级时间内安全派生出 256 位真随机对称会话密钥（``secretbox::Key``），并实现了完全前向保密（PFS）。在握手成功之后，后续的所有业务流量——包括高吞吐的 4K 视频压缩切片、Opus 实时音频帧、密集的键鼠控制指令以及文件分块传输，都必须全量经过对称流加密引擎。如何在维持数百兆带宽吞吐的前提下保证数据的**机密性（Confidentiality）**、**完整性（Integrity）**并彻底免疫**重放攻击（Replay Attack）**？本章将深入剖析 RustDesk 传输层（``hbb_common::Stream``）中基于 **NaCl ``secretbox`` (XSalsa20-Poly1305 / ChaCha20-Poly1305)** 的认证加密（AEAD）流水线、单调递增 Nonce 状态机与防重放滑动窗口。

***
认证加密 (AEAD) 的物理设计与抗篡改模型
***

传统远程桌面协议或自定义 TCP 流若仅使用普通的块密码加密（如未经 MAC 校验的 AES-CBC），攻击者即便无法获知明文，也可以通过比特翻转攻击（Bit-Flipping Attack）或填充预言机攻击（Padding Oracle Attack）篡改键盘控制指令（例如将按键字符修改为恶意 Payload）。

RustDesk 严格采用现代密码学标准中的**认证加密（Authenticated Encryption with Associated Data, AEAD）**：

.. math::

   C, T = 	ext{AEAD-Encrypt}(K, N, P)

.. math::

   P = 	ext{AEAD-Decrypt}(K, N, C, T) \quad (	ext{若 } T 	ext{ 校验失败则直接抛弃并断开连接})

.. list-table:: RustDesk 会话流加密关键物理参数
   :widths: 22 25 28 25
   :header-rows: 1

   * - 密码学组件
     - 算法规范
     - 结构尺寸
     - 安全属性与防护目标
   * - **对称密码核心**
     - XSalsa20 / ChaCha20
     - 256-bit Key (32 字节)
     - 极速流式加密，全平台常数时间执行，免疫 Cache 侧信道
   * - **消息认证码 (MAC)**
     - Poly1305
     - 128-bit Tag (16 字节)
     - 一次一密信息论安全，任何单比特篡改均导致验签失败
   * - **随机数 / 计数器 (Nonce)**
     - 递增计数器 (Monotonic Counter)
     - 192-bit (24 字节) / 96-bit (12 字节)
     - 保证同一密钥下 Nonce 永不复用，免疫重放攻击

---
单向与双向 Nonce 隔离状态机
---

在流式加密中，**绝对禁止使用相同密钥和相同 Nonce 加密两条不同的明文（Two-Time Pad 灾难）**。一旦 Nonce 发生复用：

$$C_1 \oplus C_2 = (P_1 \oplus 	ext{Keystream}) \oplus (P_2 \oplus 	ext{Keystream}) = P_1 \oplus P_2$$

攻击者只需将两段密文异或，即可直接消除密钥流，通过自然语言统计分析还原出两份明文！

1. 双工通信的 Nonce 空间正交隔离
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在全双工 TCP/KCP 连接中，主控端与受控端同时向对方推流。为了彻底消除 Nonce 冲突，RustDesk 在传输层建立了**严格的方向隔离与单调递增计数器模型**：

```
[主控端 Client Stream]                                     [受控端 Server Stream]
        │                                                           │
        │ 发送 Nonce: [ 0x00, 0x00... | Tx Counter: 1 ]             │ 接收 Nonce: [ 0x00, 0x00... | Rx Counter: 1 ]
        ├─ Frame 1 (Encrypted) ────────────────────────────────────>├─ 校验 MAC 成功，解密并递增 Rx Counter
        │                                                           │
        │ 发送 Nonce: [ 0x00, 0x00... | Tx Counter: 2 ]             │
        ├─ Frame 2 (Encrypted) ────────────────────────────────────>│
        │                                                           │
        │ 接收 Nonce: [ 0x80, 0x00... | Rx Counter: 1 ]             │ 发送 Nonce: [ 0x80, 0x00... | Tx Counter: 1 ]
        │<──────────────────────────────────── Frame 1 (Encrypted) ─┤ (最高位 0x80 区分服务端推流方向)
```

2. 传输层 Nonce 计数器状态机实现
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在底层 ``hbb_common::Stream`` 的流式分帧中，发送端与接收端各自维护独立的 64 位无符号整型（``u64``）计数器：

.. code-block:: rust
   :caption: 传输层 Nonce 递增与加密封装伪代码模型

   pub struct SecureFramedStream {
       inner: Stream,
       key: secretbox::Key,
       tx_counter: u64,
       rx_counter: u64,
       is_server: bool,
   }

   impl SecureFramedStream {
       fn create_nonce(counter: u64, is_server: bool) -> secretbox::Nonce {
           let mut nonce_bytes = [0u8; secretbox::NONCEBYTES]; // 24 字节
           // 1. 最高字节设置方向标志位（0x00: Client->Server, 0x80: Server->Client）
           if is_server {
               nonce_bytes[0] = 0x80;
           }
           // 2. 将 64 位单调递增计数器写入 Nonce 尾部（大端序）
           nonce_bytes[16..24].copy_from_slice(&counter.to_be_bytes());
           secretbox::Nonce(nonce_bytes)
       }

       pub async fn send_secure_frame(&mut self, plaintext: &[u8]) -> ResultType<()> {
           self.tx_counter = self.tx_counter.checked_add(1)
               .ok_or_else(|| anyhow!("Nonce counter overflow! Must re-key"))?;
           
           let nonce = Self::create_nonce(self.tx_counter, self.is_server);
           
           // 执行 XSalsa20-Poly1305 AEAD 加密（生成密文与 16 字节 Poly1305 认证标签）
           let ciphertext = secretbox::seal(plaintext, &nonce, &self.key);
           
           // 组装带 4 字节长度前缀的报文发送
           self.inner.send_bytes(ciphertext).await
       }
   }

---
防重放攻击 (Anti-Replay Attack) 与滑动窗口校验
---

重放攻击是指中间攻击者截获主控端之前发送的合法加密数据报文（例如点击确认弹窗或执行文件删除的按键指令），并在数秒甚至数小时后重新向受控端网络端口灌入该报文。

由于密文的 Poly1305 MAC 签名完全合法，若无防护机制，受控端解密后会误认为是主控端再次发送的指令并重复执行，造成灾难性后果。

1. 面向可靠流 (TCP / KCP) 的严格递增判定
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在基于连接的保序流（TCP 与 KCP）上，底层传输层已保证数据包严格保序到达：

.. math::

   	ext{Expected Nonce Counter} = 	ext{Last Nonce Counter} + 1

接收端每次读取到一个新帧：
1. 构造预期 Nonce：$	ext{Nonce}_{	ext{expected}} = 	ext{create\_nonce}(	ext{rx\_counter} + 1)$；
2. 执行 ``secretbox::open(ciphertext, &Nonce_expected, &key)``；
3. **若解密成功**：$	ext{rx\_counter} \leftarrow 	ext{rx\_counter} + 1$；
4. **若发生重放**：攻击者插入的历史数据包其内部密文是用旧 Nonce 加密的，用当前期望的 $	ext{Nonce}_{	ext{expected}}$ 解密会导致 Poly1305 验签彻底失败，立即抛出 ``Signature mismatch`` 并强制切断 TCP/UDP 连接。

2. 面向不可靠无序 UDP 报文的滑动窗口位图 (Anti-Replay Sliding Window)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

针对直连不可靠 UDP 报文，RustDesk 采用类似于 IPsec RFC 4303 标准的**64 位滑动窗口位图机制**：

.. code-block:: rust
   :caption: 防重放滑动窗口算法逻辑

   pub struct ReplayFilter {
       window_base: u64,
       bitmap: u64, // 64 帧容量滑动位图
   }

   impl ReplayFilter {
       pub fn check_and_update(&mut self, seq: u64) -> bool {
           if seq > self.window_base {
               // 收到新序列号：窗口向前滑动
               let diff = seq - self.window_base;
               if diff < 64 {
                   self.bitmap <<= diff;
               } else {
                   self.bitmap = 0;
               }
               self.bitmap |= 1; // 标记当前包已接收
               self.window_base = seq;
               true
           } else {
               // 收到旧序列号（延迟到达包）
               let diff = self.window_base - seq;
               if diff >= 64 {
                   return false; // 超出窗口左边界：直接丢弃（判定为重放包）
               }
               if (self.bitmap & (1 << diff)) != 0 {
                   return false; // 位图中已标记接收过：直接丢弃（判定为重放包）
               }
               self.bitmap |= 1 << diff; // 标记乱序包已接收
               true
           }
       }
   }

---
高性能零拷贝与内存生命周期保护
---

在 $60	ext{FPS}$ 甚至 $120	ext{FPS}$ 的高刷新率推流下，每秒需加密解密数万个数据包。为了避免频繁的堆内存分配与 GC 抖动：

1. **原地就地加解密（In-Place Encryption/Decryption）**：
   直接在 Tokio 的 ``BytesMut`` 环形缓冲区上执行 Poly1305 标签计算与 XOR 掩码流覆盖，消除内存拷贝开销。
2. **敏感内存安全擦除（Zeroize on Drop）**：
   会话密钥结构体 ``secretbox::Key`` 在脱离作用域销毁时，利用 Rust 的 ``Drop`` 特性自动调用 ``sodiumoxide::utils::memzero`` 清理内存页，防止通过进程内存 Dump 或 Core Dump 窃取密钥。

***
小结与下章导读
***

本章全面解构了 RustDesk 传输层数据通道的流式安全架构：
* 阐明了 AEAD 认证加密在抵抗比特翻转篡改与保持机密性上的核心数学模型。
* 剖析了全双工通信下基于方向标志位与单调递增计数器的 Nonce 正交隔离状态机，杜绝 Nonce 复用灾难。
* 揭示了保序流严格自增校验与无序 UDP 报文 64 位滑动窗口防重放攻击算法。
* 展示了原地零拷贝加解密与内存敏感数据自动擦除（Zeroize）的工程实践。

在下一节中，我们将深入受控端操作系统的权限防线：
* **《04.04 权限控制模型、一次性口令与 Windows 服务提权》**：深入剖析受控端的黑白名单权限位图、随机一次性验证码（2FA）以及在 Windows 下从普通用户进程向 SYSTEM 服务的安全提权与 UAC 穿透机制。
