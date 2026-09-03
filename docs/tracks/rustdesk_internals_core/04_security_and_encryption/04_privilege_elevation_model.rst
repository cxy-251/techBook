======================================================================
04.04 权限控制模型、一次性口令与 Windows 服务提权
======================================================================

.. note:: 前置背景与上下文承接
   在前三章中，我们先后解剖了基于 NaCl 的 Ed25519 非对称身份认证（《04.01》）、X25519 临时密钥协商与前向保密（《04.02》）以及基于 XSalsa20-Poly1305 的会话流加密与防重放机制（《04.03》）。至此，网络传输通道已达到极高的密码学安全标准。然而，当一个经过加密认证的远程连接进入受控端操作系统时，最关键的防线转移到了**应用与操作系统层的访问控制与权限管理**：如何防止静态密码在认证过程中泄露？如何精细化限制主控端的操作权限（如仅允许查看画面、禁止文件传输或剪贴板同步）？在 Windows 操作系统遭遇 UAC（用户账户控制）弹窗或处于锁屏界面时，受控端如何突破 Session 0 隔离实现安全提权？本章将系统解构 RustDesk 在 ``src/client.rs``、``src/common.rs`` 及 ``src/platform/windows.rs`` 中的权限控制模型、零知识挑战口令认证与服务提权体系。

***
细粒度会话权限控制模型 (64-bit Permission Bitmap)
***

远程桌面绝非“全有或全无”的粗暴控制。在多用户协作、技术支持或外包运维场景中，受控端需要精确限制主控端的操作范围。

RustDesk 在 ``src/common.rs`` 中设计了紧凑高效的 **64 位权限状态位图模型**：

```
+-------------------------------------------------------------------------------+
| Bit 63 ~ Bit 16 (Reserved) | Bit 15..14 | ... | Bit 3..2 | Bit 1..0           |
+-------------------------------------------------------------------------------+
                             | Audio Perm | ... | File Xfer| Input (Key/Mouse)  |
```

* **双比特编码状态（2-Bit Tri-State）**：每个权限维度占用 2 个 bit：
  * ``0b00`` (0)：未显式设置（默认继承全局配置）；
  * ``0b01`` (1)：强制禁用（Disable）；
  * ``0b10`` (2)：强制允许（Enable）；
  * ``0b11`` (3)：非法状态（忽略）。

.. code-block:: rust
   :caption: 64 位权限位图解码算法（src/common.rs::get_control_permission）

   pub fn get_control_permission(
       permissions: u64,
       permission: hbb_common::rendezvous_proto::control_permissions::Permission,
   ) -> Option<bool> {
       use hbb_common::protobuf::Enum;
       let index = permission.value();
       if index >= 0 && index < 32 {
           let shift = index * 2;
           let value = (permissions >> shift) & 0b11;
           match value {
               1 => Some(false), // 禁用
               2 => Some(true),  // 允许
               _ => None,        // 未配置
           }
       } else {
           None
       }
   }

通过位图编码，主控端与受控端在握手阶段仅需一个 64 位无符号整数即可同步键鼠、剪贴板、音频、文件传输、系统重启、隐私黑屏与远程终端等数十项安全特权的开关。

---
零知识挑战口令认证 (Challenge-Response Authentication)
---

传统系统若直接将用户密码或静态密码哈希发送至网络，一旦通信链路遭遇极端漏洞，静态口令极易被重放盗用。RustDesk 采用了**零知识挑战-应答（Challenge-Response）双重哈希机制**：

```
[主控端 Client]                                               [受控端 Host]
       │                                                             │
       │<─ 1. 下发动态 Hash 盐值报文: ───────────────────────────────┤
       │     Hash { salt: 32B_random, challenge: 32B_random }        │
       │                                                             │
       ├─ 2. 本地计算持久化口令哈希:                                 ├─ 2. 本地持久化口令哈希:
       │     H_stored = SHA256(password + salt)                      │     H_stored = SHA256(password + salt)
       │                                                             │
       ├─ 3. 混入单次挑战随机数:                                     │
       │     H_wire = SHA256(H_stored + challenge)                   │
       │                                                             │
       ├─ 4. 发送 LoginRequest (携带 H_wire) ────────────────────────>│
       │                                                             ├─ 5. 本地校验:
       │                                                             │    assert_eq!(
       │                                                             │      H_wire,
       │                                                             │      SHA256(H_stored + challenge)
       │                                                             │    )
       │<─ 6. 验证成功，放行会话 ────────────────────────────────────┤
```

1. 密码学时序实现
~~~~~~~~~~~~~~~~

在 ``src/client.rs::handle_hash`` 中，主控端接收到盐值与挑战字后计算不可逆特征：

.. code-block:: rust
   :caption: 挑战-应答口令计算时序（src/client.rs）

   // 1. 结合 Salt 计算本地密码特征 H_stored
   let mut hasher = Sha256::new();
   hasher.update(password);
   hasher.update(&hash.salt);
   let h_stored = hasher.finalize();

   // 2. 混入单次会话专用的随机 Challenge 生成在线认证特征 H_wire
   let mut hasher2 = Sha256::new();
   hasher2.update(&h_stored);
   hasher2.update(&hash.challenge);
   let h_wire: Vec<u8> = hasher2.finalize()[..].to_vec();

   // 3. 发送登录认证
   send_login(lc, os_username, os_password, h_wire, peer).await;

**安全属性分析**：
* 攻击者在网络上只能捕获到 $H_{	ext{wire}}$，由于 SHA-256 的单向散列物理特性，攻击者既无法反推出明文密码，也无法反推出 $H_{	ext{stored}}$；
* 每次连接时受控端生成的 ``challenge`` 均为密码学真随机数，因此 $H_{	ext{wire}}$ 在下一次连接中直接作废，物理免疫重放嗅探。

2. 双因子认证 (2FA / TOTP) 与可信设备白名单
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当受控端开启 2FA 时，受控端在密码校验成功后会返回 ``REQUIRE_2FA`` 状态，要求主控端输入基于 RFC 6238 标准的 6 位动态验证码。同时，用户可勾选“信任此设备”（``trust-this-device``），系统会采集本机硬件特征生成唯一哈希硬件码（``hwid = SHA256(machine_uuid)``）并写入受控端白名单，在后续连接中免除二次验证。

---
Windows 服务提权与 UAC / Secure Desktop 穿透机制
---

在 Windows 操作系统中，免安装绿色版（Portable Mode）远程桌面面临着严格的操作系统安全隔离壁垒：

1. **用户界面特权隔离（UIPI）**：以标准普通用户权限运行的远程进程，无法通过 ``SendInput`` 向高权限运行的应用程序（如任务管理器、注册表编辑器）注入鼠标键盘事件。
2. **安全桌面隔离（Secure Desktop Isolation）**：当系统弹出 UAC（用户账户控制）提权弹窗、Ctrl+Alt+Del 界面或锁屏时，Windows 会切换至独立的 ``Winlogon`` 安全桌面。普通桌面进程不仅无法捕捉安全桌面的画面（画面显示黑屏或静止），也无法点击“是”按钮确认提权。

```
[系统 Session 0 (服务层)]
   └── RustDesk Service (以 NT AUTHORITY\SYSTEM 运行)
            │ (监听本地 IPC 命名管道)
            │
            ├─ 1. 收到提权请求 (ElevateDirect / ElevateWithLogon)
            ├─ 2. 获取当前活跃控制台会话: SessionID = WTSGetActiveConsoleSessionId()
            ├─ 3. 复制交互式用户安全令牌: WTSQueryUserToken(SessionID, &hToken)
            ├─ 4. 设置令牌特权标志 (TokenElevation / uiAccess)
            │
            ▼
[活跃用户 Session 1 (交互桌面)]
   └── 启动提权 Worker 进程: CreateProcessAsUserW(...)
            │
            └── 拥有 UIAccess 特权，可无缝捕获 Secure Desktop 并注入 UAC 点击！
```

1. 提权路径状态机
~~~~~~~~~~~~~~~~

RustDesk 在 ``src/platform/windows.rs`` 与 ``src/server/service.rs`` 中实现了双轨提权策略：

.. code-block:: rust
   :caption: 服务提权调度逻辑

   // 主控端向受控端发送提权指令
   pub enum Data {
       ElevateDirect,                       // 直接请求受控端服务提权
       ElevateWithLogon(String, String),    // 提供 Windows 管理员凭据提权
       // ...
   }

* **路径 A：已安装系统服务（Installed Service）**：
  若受控端已安装 RustDesk Windows 服务（以最高系统权限 ``NT AUTHORITY\SYSTEM`` 运行在 Session 0），普通界面的主控端发送 ``ElevateDirect`` 后，服务进程通过 IPC 接收指令，直接利用 ``CreateProcessAsUser`` 在用户 Session 中派生具备 ``uiAccess`` 特权的抓屏与输入注入子进程，用户无需再次输入密码即可无缝穿透 UAC。
* **路径 B：未安装服务（Portable 免安装模式）**：
  受控端进程调用 Windows Shell API（``ShellExecuteExW``）并指定 ``lpVerb = L"runas"``，触发本地操作系统的 UAC 提示，由受控端现场操作人员点击“允许”后将 RustDesk 重启为主管理员进程。

***
小结与下章导读
***

至此，**模块 04：端到端加密与安全会话** 的四大核心基石已全部完工：
* 《04.01 基于 NaCl / libsodium 的非对称密钥体系与 Ed25519 身份认证》
* 《04.02 X25519 密钥协商与临时会话对称密钥派生》
* 《04.03 会话数据流加密 (XSalsa20/ChaCha20-Poly1305) 与防重放攻击》
* 《04.04 权限控制模型、一次性口令与 Windows 服务提权》

系统已具备完整的密码学身份背书、端到端信封密钥协商、AEAD 数据流防篡改与操作系统级安全隔离穿透能力。

在接下来的 **模块 05：客户端架构、Tokio 运行时与状态机** 中，我们将深入客户端软件的并发核心：
* **《05.01 Tokio 异步运行时拓扑与 IO/Worker 线程池协同机制》**：解析客户端如何构建多 Runtime 拓扑，实现网络异步 I/O 线程池、音视频重度编解码 CPU 密集型线程池与 UI 渲染线程之间的无锁高效协同。
