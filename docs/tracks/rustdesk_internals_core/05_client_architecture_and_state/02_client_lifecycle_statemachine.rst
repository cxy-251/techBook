======================================================================
05.02 客户端生命周期状态机与多路复用连接管理
======================================================================

.. note:: 前置背景与上下文承接
   在前一章《05.01 Tokio 异步运行时拓扑与 IO/Worker 线程池协同机制》中，我们剖析了客户端内部多 Runtime 隔离、无锁环形队列与音视频专用 Worker 线程的并发拓扑。在多线程与异步运行时就绪后，客户端必须围绕远程会话建立一套**严密、容错且支持多路复用的生命周期状态机（Lifecycle Finite State Machine, FSM）**。从用户在 UI 中输入对端 ID 点击“连接”开始，系统需经历配置装载、信令打洞、多路径并发竞速、密码学握手、多模式鉴权、流媒体分发、网络抖动重连直至优雅销毁。本章将深入解剖 ``src/client.rs``、``src/client/io_loop.rs`` 与 ``src/ui_session_interface.rs``，系统梳理客户端全局状态跃迁、多会话类型（``ConnType``）多路复用与断线重连容灾模型。

***
客户端连接全生命周期状态机拓扑
***

主控端客户端的生命周期可抽象为八大核心状态之间的确定性跃迁：

```
[1. Disconnected (空闲/未连接)]
        │ (用户发起呼叫 / Session.start())
        ▼
[2. Initializing (配置加载 & PeerConfig)]
        │
        ▼
[3. Rendezvous & Punching (信令打洞 & 多路并发竞速)] ──(打洞超时/失败)──> [Fallback to Relay (中继)]
        │                                                                   │
        └───────────────────────────────┬───────────────────────────────────┘
                                        ▼
                         [4. Handshaking (X25519 & AEAD 激活)]
                                        │
                                        ▼
                         [5. Authenticating (挑战应答 / 2FA / OS 登录)]
                                        │
                                        ▼
                         [6. Active Streaming (多路复用流会话)]
                                        │
                 ┌──────────────────────┴──────────────────────┐
                 ▼ (偶发断线 / 重启受控端)                    ▼ (用户主动断开 / 异常不可恢复)
    [7. Reconnecting (自适应指数退避)]               [8. Closed (资源确定性回收)]
```

.. list-table:: 客户端生命周期核心状态与物理行为
   :widths: 20 22 30 28
   :header-rows: 1

   * - 状态阶段
     - 触发条件 / 函数入口
     - 核心处理与物理行为
     - 异常分支与转移目标
   * - **Initializing**
     - ``LoginConfigHandler::initialize``
     - 加载本地持久化配置、读取口令源、生成 SessionID
     - 配置损坏时重置为默认值
   * - **Punching & Racing**
     - ``Client::_start_inner``
     - 向 ``hbbs`` 请求打洞，并发启动 IPv4/IPv6/UDP/TCP 4 路竞速
     - P2P 均失败时平滑降级至 ``hbbr`` 中继
   * - **Handshaking**
     - ``Client::secure_connection``
     - 校验服务端 CA 签名、ECDH 协商、Sealed Box 派生对称密钥
     - 签名不匹配触发 ``confirm_insecure_connection``
   * - **Authenticating**
     - ``handle_hash`` / ``send_login``
     - 混入 Salt 与 Challenge 计算不可逆 $H_{	ext{wire}}$，提交权限配置
     - 密码错误弹窗重试；触发 2FA 阻断
   * - **Active Streaming**
     - ``io_loop`` / ``start_video_thread``
     - 激活视频、音频、键鼠、剪贴板多路复用调度
     - 检测到心跳丢失或 TCP RST 转入重连
   * - **Reconnecting**
     - ``check_if_retry`` / 重启保护
     - 区分网络闪断与远程操作系统重启，执行自适应重连
     - 超过最大重试窗口后宣告失败并关闭

---
多连接类型（``ConnType``）多路复用与特性协商
---

RustDesk 绝非仅用于图形桌面控制，底层框架支持多种独立的业务会话类型（``ConnType``），各连接类型共享相同的信令穿透与加密通道，但在应用层挂载不同的功能管道：

.. code-block:: rust
   :caption: 连接类型多路复用与配置按需加载（src/client.rs）

   pub enum ConnType {
       DEFAULT_CONN,   // 完整图形桌面控制（音视频流 + 输入注入 + 剪贴板）
       FILE_TRANSFER,  // 纯文件管理器（无画面抓取，仅挂载文件 RPC 引擎）
       PORT_FORWARD,   // TCP 端口转发隧道
       RDP,            // 本地原生 RDP 客户端通过加密隧道中继
       TERMINAL,       // 远程 Shell / PTY 终端交互
       VIEW_CAMERA,    // 远端摄像头独立监控模式
   }

1. 登录报文按需构造（``create_login_msg``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

根据 ``conn_type`` 的不同，客户端在 ``LoginRequest`` 中动态打包特定子系统的初始载荷：

.. code-block:: rust
   :caption: 多路复用登录请求构造（src/client.rs）

   let mut lr = LoginRequest {
       username: pure_id,
       password: password.into(),
       my_id,
       my_name: display_name,
       my_platform,
       option: self.get_option_message(true).into(),
       session_id: self.session_id,
       version: crate::VERSION.to_string(),
       os_login,
       hwid,
       avatar,
       ..Default::default()
   };

   // 根据业务类型挂载专用 Protobuf 子载荷
   match self.conn_type {
       ConnType::FILE_TRANSFER => lr.set_file_transfer(FileTransfer {
           dir: self.get_remote_dir(),
           show_hidden: !self.get_option("remote_show_hidden").is_empty(),
           ..Default::default()
       }),
       ConnType::VIEW_CAMERA => lr.set_view_camera(Default::default()),
       ConnType::PORT_FORWARD | ConnType::RDP => lr.set_port_forward(PortForward {
           host: self.port_forward.0.clone(),
           port: self.port_forward.1,
           ..Default::default()
       }),
       ConnType::TERMINAL => {
           let mut terminal = Terminal::new();
           terminal.service_id = self.get_option(self.get_key_terminal_service_id());
           lr.set_terminal(terminal);
       }
       _ => {}
   }

---
网络异常断线重连与远程操作系统重启保护
---

在公网不可靠环境中，连接中断主要分为三类：物理网络瞬时闪断（如 Wi-Fi 漫游）、中继连接异常重置（Windows 10054 / Linux 104 ECONNRESET）、以及受控端**主动触发的操作系统重启**。

1. 智能重试判定（``check_if_retry``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

客户端在接收到底层错误时，执行严格的白名单过滤，防止对不可恢复的逻辑错误进行盲目重试：

.. code-block:: rust
   :caption: 可重试错误智能过滤器（src/client.rs）

   pub fn check_if_retry(msgtype: &str, title: &str, text: &str, retry_for_relay: bool) -> bool {
       msgtype == "error"
           && title == "Connection Error"
           && ((text.contains("10054") || text.contains("104")) && retry_for_relay
               || (!text.to_lowercase().contains("offline")
                   && !text.to_lowercase().contains("not exist")
                   && !text.to_lowercase().contains("handshake")
                   && !text.to_lowercase().contains("failed")
                   && !text.to_lowercase().contains("resolve")
                   && !text.to_lowercase().contains("mismatch")
                   && !text.to_lowercase().contains("incoming only")
                   && !text.to_lowercase().contains("not allowed")))
   }

2. 远程操作系统重启宽限期窗口（``RESTART_REMOTE_DEVICE_GRACE``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当运维人员点击“重启受控端计算机”时，Windows 关机流程会导致网络在重启前短暂断开又短暂重连。若直接判定为“连接异常中断”并弹出错误弹窗，将打断用户的自动重连体验。

RustDesk 引入了 **5 分钟重启保护宽限期（Grace Window）状态机**：

.. code-block:: rust
   :caption: 远程重启宽限期抑制（src/client.rs）

   const RESTART_REMOTE_DEVICE_GRACE: Duration = Duration::from_secs(5 * 60);

   pub fn is_restarting_remote_device(&self) -> bool {
       if !self.restarting_remote_device {
           return false;
       }
       // 在 5 分钟宽限窗口期内，抑制所有网络断开错误弹窗，UI 显示“正在等待远程主机重启...”
       self.restart_remote_device_at
           .map(|started_at| started_at.elapsed() < RESTART_REMOTE_DEVICE_GRACE)
           .unwrap_or(false)
   }

---
优雅退出与全局资源确定性回收
---

当用户主动点击关闭窗口或连接终止时，状态机必须防止资源泄漏（如显存 Texture 未释放、剪贴板监听钩子未注销、音频流占用）：

1. **剪贴板共享单例解绑（``try_stop_clipboard``）**：
   多会话共享单全局剪贴板监听线程。仅当所有活跃的 ``DEFAULT_CONN`` 会话全部退出后，才真正注销系统原生剪贴板钩子并清空临时文件缓存。
2. **解码器重置与显存清理（``VideoHandler::reset``）**：
   销毁 DirectX / Metal 纹理句柄，回收 FFI 跨语言共享内存指针。
3. **RAII 级联终止**：
   通过 ``oneshot::Sender`` 触发各个子系统内部的终止通道，通知后台 Tokio 协程退出事件循环。

***
小结与下章导读
***

本章系统解剖了 RustDesk 客户端连接管理的生命周期架构：
* 梳理了客户端从 Disconnected 到 Active Streaming 八大核心状态的数学演进模型。
* 剖析了桌面控制、文件传输、端口转发、RDP 隧道与远程终端在传输层的多路复用与配置挂载。
* 揭示了基于 ``check_if_retry`` 的断线智能恢复以及 5 分钟远程主机重启保护宽限期。
* 总结了多会话退出时的全局单例剪贴板、显存解码器与异步任务的优雅注销机制。

在下一节中，我们将深入核心子系统的实现：
* **《05.03 文件传输子系统：并发分块传输、断点续传与校验》**：深入解析远程文件浏览、大文件多块并行传输、SHA-256 完整性分块校验以及网络中断后的断点续传（Resume Job）算法。
