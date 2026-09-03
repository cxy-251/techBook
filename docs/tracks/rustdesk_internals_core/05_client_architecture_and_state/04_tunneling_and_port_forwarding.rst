======================================================================
05.04 端口转发、TCP/UDP 隧道与远程打印协议扩展
======================================================================

.. note:: 前置背景与上下文承接
   在前三章中，我们解剖了客户端 Tokio 多运行时拓扑（《05.01》）、全生命周期状态机演进（《05.02》）以及高可靠文件传输子系统（《05.03》）。在现代远程运维与企业协同场景中，用户的诉求往往不仅限于图形屏幕的查看与键鼠控制，还包括**访问受控端局域网内部的私有服务（如内网 Web、SSH、MySQL 数据库）**，或者**在受控端直接将文档发送至主控端本地物理打印机**。如何在无需额外组网（如配置复杂 VPN）的前提下，复用 RustDesk 已建立的安全 P2P/中继通道进行任意 TCP/UDP 流量透传？本章将深入剖析 ``src/port_forward.rs``、``src/server/printer_service.rs`` 及 ``libs/remote_printer/``，系统解构本地/远程端口转发隧道、原生 RDP 隧道无缝桥接以及虚拟打印驱动适配器体系。

***
端口转发与通用网络隧道物理模型
***

RustDesk 端口转发功能允许主控端在本地监听一个 TCP 端口，并将所有发往该端口的原始字节流通过端到端加密通道透明隧道化（Tunneling）至受控端，再由受控端代为主控端向目标主机（``remote_host:remote_port``）发起 TCP 转发：

```
[本地应用 (如 Navicat / SSH)]
           │
           ▼ (本地 TCP 连接: 127.0.0.1:33060)
[RustDesk 主控端 (Listener)]
           │
           ├─ 1. 握手登录受控端 (ConnType::PORT_FORWARD)
           ├─ 2. 切换至原始流模式 (stream.set_raw())
           │
           ▼ (端到端加密通道: ChaCha20-Poly1305 / XSalsa20)
[RustDesk 受控端 (Host Daemon)]
           │
           ├─ 3. 代为主控端发起 Socket 连接: TcpStream::connect("192.168.1.100:3306")
           │
           ▼ (内网物理局域网流量)
[目标内网数据库服务器 (192.168.1.100:3306)]
```

.. list-table:: 隧道扩展协议三大核心应用模式
   :widths: 20 25 28 27
   :header-rows: 1

   * - 隧道类型
     - 连接类型 (``ConnType``)
     - 本地/远程端点拓扑
     - 典型应用场景
   * - **自定义端口转发**
     - ``ConnType::PORT_FORWARD``
     - ``127.0.0.1:local_port`` $	o$ ``remote_host:remote_port``
     - 穿透内网访问受控端局域网的 Web、SSH、数据库服务
   * - **原生 RDP 隧道**
     - ``ConnType::RDP``
     - 随机本地高位端口 $	o$ ``localhost:3389``
     - 调起微软原生 ``mstsc.exe`` 实现原生 RDP 桌面体验
   * - **远程虚拟打印**
     - ``DEFAULT_CONN`` / 专用 RPC
     - 受控端 XPS 驱动 $	o$ 主控端物理打印机
     - 跨公网无感知云打印

---
TCP 端口转发状态机与双向流管道 (``src/port_forward.rs``)
---

在 ``src/port_forward.rs`` 中，端口转发服务以异步 Tokio 任务的形式运行：

1. 本地监听与动态会话拉起（``listen``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: rust
   :caption: 端口转发本地监听与隧道拉起（src/port_forward.rs）

   pub async fn listen(
       id: String,
       password: String,
       port: i32,
       interface: impl Interface,
       ui_receiver: mpsc::UnboundedReceiver<Data>,
       key: &str,
       token: &str,
       lc: Arc<RwLock<LoginConfigHandler>>,
       remote_host: String,
       remote_port: i32,
   ) -> ResultType<()> {
       // 在本地 127.0.0.1 上绑定监听端口
       let listener = tcp::new_listener(format!("127.0.0.1:{}", port), true).await?;
       let addr = listener.local_addr()?;
       log::info!("Port forwarding listening on: {:?}", addr);

       loop {
           tokio::select! {
               Ok((forward, addr)) = listener.accept() => {
                   log::info!("New incoming connection from {:?}", addr);
                   lc.write().unwrap().port_forward = (remote_host.clone(), remote_port);
                   let mut forward = Framed::new(forward, BytesCodec::new());
                   
                   // 为每一个入站 TCP 连接与远端受控端建立一条独立的加密隧道
                   match connect_and_login(&id, &password, &mut ui_receiver, interface.clone(), 
                                           &mut forward, key, token, is_rdp, &mut close_port_forward).await {
                       Ok(Some(stream)) => {
                           tokio::spawn(async move {
                               // 启动双向零拷贝流转发
                               run_forward(forward, stream).await.ok();
                           });
                       }
                       // ...
                   }
               }
               // ...
           }
       }
   }

2. 流模式切换：从 Protobuf 帧到 Raw Stream（``stream.set_raw()``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在握手和鉴权阶段，通信流承载的是结构化 Protobuf 控制报文（``Hash``、``LoginRequest``、``LoginResponse``）。当受控端校验权限通过并成功连接目标内网端口后，双方流对象调用 ``stream.set_raw()``：
* **脱离 Protobuf 4 字节长度分帧**：后续所有数据不再被解析为 Protobuf 结构体；
* **透明 AEAD 流加解密**：底层仍然保留 XSalsa20/ChaCha20 对称加密层，确保隧道内传输的数据包完全加密。

3. 全双工异步流量转发泵（``run_forward``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: rust
   :caption: 全双工流量转发泵（src/port_forward.rs）

   async fn run_forward(forward: Framed<TcpStream, BytesCodec>, stream: Stream) -> ResultType<()> {
       let mut forward = forward;
       let mut stream = stream;
       loop {
           tokio::select! {
               // 1. 本地应用发送数据 -> 加密后推入远程 Stream
               res = forward.next() => {
                   if let Some(Ok(bytes)) = res {
                       allow_err!(stream.send_bytes(bytes.into()).await);
                   } else { break; }
               },
               // 2. 远程 Stream 返回响应 -> 解密后注入本地应用 Socket
               res = stream.next() => {
                   if let Some(Ok(bytes)) = res {
                       allow_err!(forward.send(bytes).await);
                   } else { break; }
               },
           }
       }
       Ok(())
   }

---
Windows 原生 RDP 隧道与免密自动凭据注入
---

RustDesk 创新性地将远程隧道与微软 Windows 原生远程桌面客户端（``mstsc.exe``）深度结合：

1. **随机临时高位端口分配**：主控端指定 ``port = 0``，由操作系统内核分配未占用的随机空闲端口；
2. **系统凭据自动化注入（``cmdkey``）**：
   在拉起 ``mstsc`` 之前，主控端调用 Windows 原生凭据管理器 ``cmdkey.exe /generic:localhost /user:... /pass:...``，将受控端 Windows 账户密码注入本地临时凭据库，彻底避免用户手动输入密码；
3. **原生命令行拉起与窗口定制**：
   通过 ``mstsc.exe /v:localhost:{port}`` 启动微软官方 RDP 客户端，并调用 ``SetWindowTextW`` 动态将窗口标题修改为受控端的主机名或别名（``rdp_display_name``）。

---
远程虚拟打印服务架构 (``libs/remote_printer/``)
---

远程办公时，受控端（如公司办公电脑）上的软件需要打印报表至员工家中主控端的物理打印机上。

RustDesk 在受控端构建了基于 Windows 打印驱动适配器的**虚拟打印机拦截子系统**：

```
[受控端 办公应用程序 (Word/Excel)]
                 │ (点击打印 -> 选择 "RustDesk Remote Printer")
                 ▼
[Windows Print Spooler (打印后台处理程序)]
                 │
                 ▼ (渲染输出 XPS/PRN 数据流)
[printer_driver_adapter.dll (动态加载适配器库)]
                 │
                 ▼ (GetPrnData 轮询提取)
[RustDesk PrinterService (src/server/printer_service.rs)]
                 │
                 ▼ (Protobuf 数据封装)
[P2P / Relay 加密网络通道]
                 │
                 ▼ (主控端接收并在本地物理打印机重放 Spool)
[主控端 本地物理打印机驱动]
```

1. 打印机驱动适配器 FFI 绑定（``printer_service.rs``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

受控端通过 ``dlopen`` 动态加载 ``printer_driver_adapter.dll``，并通过宏 ``make_lib_wrapper!`` 绑定导出函数：

.. code-block:: rust
   :caption: 虚拟打印驱动接口封装（src/server/printer_service.rs）

   pub type Init = fn(tag_name: *const i8) -> i32;
   pub type Uninit = fn();
   pub type GetPrnData = fn(dur_mills: u32, data: *mut *mut i8, data_len: *mut u32);
   pub type FreePrnData = fn(data: *mut i8);

   fn run(sp: EmptyExtraFieldService) -> ResultType<()> {
       while sp.ok() {
           // 轮询获取最近 1000ms 内由虚拟打印驱动生成的 XPS 格式原始打印数据流
           let bytes = get_prn_data(1000)?;
           if !bytes.is_empty() {
               log::info!("Captured remote print spool data: {} bytes", bytes.len());
               crate::server::on_printer_data(bytes);
           }
           thread::sleep(Duration::from_millis(300));
       }
       Ok(())
   }

***
小结与下章导读
***

至此，**模块 05：客户端架构、Tokio 运行时与状态机** 的四大核心基石已全部完工：
* 《05.01 Tokio 异步运行时拓扑与 IO/Worker 线程池协同机制》
* 《05.02 客户端生命周期状态机与多路复用连接管理》
* 《05.03 文件传输子系统：并发分块传输、断点续传与校验》
* 《05.04 端口转发、TCP/UDP 隧道与远程打印协议扩展》

客户端已建立起兼顾高性能多媒体、文件管理、通用网络隧道与硬件外设扩展的完整平台架构。

在接下来的 **模块 06：Rust-Flutter FFI 桥接与跨平台渲染** 中，我们将跨入 Rust 与现代前端 UI 渲染引擎的交叉领域：
* **《06.01 flutter_rust_bridge 架构与跨语言内存安全传递》**：深入解析 RustDesk 如何通过代码自动生成器（Codegen）在 Rust 核心与 Dart/Flutter 虚拟机之间实现零拷贝数据传递、异步 Future 映射与内存生命周期协同。
