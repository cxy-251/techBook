======================================================================
05.03 文件传输子系统：并发分块传输、断点续传与校验
======================================================================

.. note:: 前置背景与上下文承接
   在前一章《05.02 客户端生命周期状态机与多路复用连接管理》中，我们解剖了客户端从未连接到流式传输的八大状态迁移逻辑，并阐述了包括桌面控制、文件管理、端口转发与远程终端在内的多连接类型（``ConnType``）多路复用架构。在企业技术支持与远程运维场景中，**文件传输（File Transfer）** 是使用频率最高且对稳定性要求极苛刻的核心子系统。面对数十吉字节（GB）的超大文件传输、数万个零碎小文件目录树同步、网络中途闪断以及目标路径文件冲突，系统如何保证传输的高吞吐、数据强一致性与断点快速自愈？本章将深入解剖 ``src/client/file_trait.rs``、``libs/hbb_common/src/fs.rs`` 及 ``src/server/service.rs``，系统拆解远程文件系统 RPC 协议、并发分块流控、冲突确认矩阵与断点续传（Resume Job）状态机。

***
远程文件系统 RPC 抽象与目录遍历协议
***

文件管理子系统在逻辑上独立于音视频推流，采用基于 Protobuf 的请求-响应（Request-Response）异步 RPC 模型：

```
[主控端 UI / FileManager]                                  [受控端 Host FS 引擎]
          │                                                          │
          ├─ 1. ReadDir { path: "C:/Projects", include_hidden: true } ─>│
          │                                                          ├─ 2. fs::read_dir() 遍历文件系统
          │                                                          │    获取 Name, Size, ModTime, Type
          │<─ 3. FileDirectory { entries: [FileEntry, ...] } ─────────┤
          │                                                          │
          ├─ 4. ReadEmptyDirs { path: "C:/Projects" } ───────────────>│
          │                                                          ├─ 5. 递归提取空目录拓扑结构
          │<─ 6. ReadEmptyDirsResponse { empty_dirs: [...] } ────────┤
```

.. list-table:: 文件系统核心 RPC 消息与操作指令
   :widths: 22 25 28 25
   :header-rows: 1

   * - 消息 / 操作类型
     - 协议结构体
     - 核心载荷字段
     - 功能描述
   * - **目录项查询**
     - ``ReadDir``
     - ``path``, ``include_hidden``
     - 异步读取目录下的子文件与子目录元数据
   * - **空目录递归**
     - ``ReadEmptyDirs``
     - ``path``, ``empty_dirs``
     - 保证文件夹镜像同步时完整保留空目录结构
   * - **文件增删改**
     - ``CreateDir`` / ``RemoveFile``
     - ``id``, ``path``, ``new_name``
     - 目录创建、单文件删除、全量递归删除与重命名
   * - **传输控制**
     - ``SendFiles`` / ``AddJob``
     - ``id``, ``JobType``, ``file_num``
     - 创建异步文件传输任务作业（Job）

---
文件传输作业（Job）生命周期与并发分块流控
---

为了避免大文件传输占满内存并实现传输进度监控，RustDesk 将文件切分为固定大小的数据分块（Chunks），并通过 **Job 状态机** 进行统筹管理：

.. code-block:: rust
   :caption: FileManager 核心特征接口（src/client/file_trait.rs）

   pub trait FileManager: Interface {
       // 启动文件传输任务
       fn send_files(
           &self,
           id: i32,
           r#type: i32, // Upload 或 Download
           path: String,
           to: String,
           file_num: i32,
           include_hidden: bool,
           is_remote: bool,
       ) {
           self.send(Data::SendFiles((
               id,
               r#type.into(),
               path,
               to,
               file_num,
               include_hidden,
               is_remote,
           )));
       }

       // 取消指定 Job 任务并释放句柄
       fn cancel_job(&self, id: i32) {
           self.send(Data::CancelJob(id));
       }

       // 触发断点续传
       fn resume_job(&self, id: i32, is_remote: bool) {
           self.send(Data::ResumeJob((id, is_remote)));
       }
   }

1. 流式滑动窗口与背压机制（Backpressure）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在高速局域网下，发送端磁盘读取速度可能远大于接收端写入速度。发送端维护一个**在途未确认分块计数器（In-Flight Chunks Window）**：
* 发送端持续异步读取并发送分块；
* 当未确认分块数量达到窗口上限时，挂起本地文件读取 Future；
* 接收端每写入一个分块并校验成功后回传 ACK 确认帧，推动滑动窗口前移并唤醒发送端继续读取。

---
文件覆盖冲突确认矩阵 (Conflict Resolution)
---

当向目标目录写入已存在的同名文件时，直接静默覆盖可能导致严重的数据丢失。RustDesk 实现了人机交互确认状态机：

.. code-block:: rust
   :caption: 文件覆盖冲突决策与记忆机制（src/client/file_trait.rs）

   fn set_confirm_override_file(
       &self,
       id: i32,
       file_num: i32,
       need_override: bool, // 是否覆盖
       remember: bool,      // 是否应用于当前任务后续所有冲突
       is_upload: bool,
   ) {
       self.send(Data::SetConfirmOverrideFile((
           id,
           file_num,
           need_override,
           remember,
           is_upload,
       )));
   }

* **单次决策与批量记忆（Remember Option）**：用户可选择“覆盖”、“跳过”或“重命名”，若勾选 ``remember = true``，后续所有冲突文件均自动执行该策略，避免数千个文件弹出弹窗阻塞传输。

---
断点续传（Resume Job）与分块哈希校验算法
---

在跨国链路或弱网 Wi-Fi 下，传输数 GB 的大文件极易在 $90\%$ 进度时遭遇网络中断。重新从 $0\%$ 传输将造成巨大的带宽与时间浪费。

RustDesk 在版本 $\ge 1.4.2$ 中引入了**物理偏移探测式断点续传机制**：

```
[网络断开前传输中断]
   发送端本地源文件 (Total: 1000MB)
   接收端写入临时文件: target_file.part (已落盘: 650MB)

[网络重连 / 用户点击继续传输 (ResumeJob)]
   1. 接收端调用 fs::metadata("target_file.part") ──> 获取当前已写入尺寸: 650MB
   2. 接收端向发送端发送 ResumeJob { id: 101, offset: 650 * 1024 * 1024 }
   3. 发送端打开本地文件，调用 file.seek(SeekFrom::Start(offset))
   4. 发送端直接从第 650MB 偏移处开始读取剩余 350MB 分块并推流
   5. 接收端以 Append 模式打开 target_file.part 继续追加写入
   6. 传输完成后校验全量 SHA-256，原子重命名: target_file.part -> target_file
```

1. 临时文件原子落盘（``.part`` 保护）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在整个传输生命周期中，目标文件均以 ``.part`` 后缀形式存在，杜绝了半途失败时生成损坏的半截文件并被其他进程误读的隐患。仅在收到终态成功包且完整性校验通过后，调用操作系统底层的 ``fs::rename`` 执行毫秒级原子重命名。

2. 多层完整性校验体系
~~~~~~~~~~~~~~~~~~~~

为了对抗不可靠网络中的位翻转与磁盘坏道：
* **单块校验（Per-Chunk Checksum）**：每个分块附带 Adler-32 或 CRC32 快速校验码，接收端一旦发现校验不符立即请求单块快速重传；
* **全局强哈希（Whole-File SHA-256）**：全文件传输完毕后，在后台异步计算全量 SHA-256 哈希值与发送端元数据比对，确保金融级数据无损一致性。

***
小结与下章导读
***

本章系统解构了 RustDesk 文件传输子系统的工程实现：
* 阐明了基于 Protobuf RPC 的远程目录遍历、元数据查询与空目录树同步协议。
* 剖析了 Job 任务作业生命周期、流式滑动窗口与跨线程背压限速机制。
* 揭示了文件覆盖冲突的三态交互确认与记忆机制。
* 解构了基于文件偏移寻道（``SeekFrom::Start``）、``.part`` 临时文件保护以及全量 SHA-256 校验的断点续传模型。

在下一节中，我们将深入客户端的网络扩展通道：
* **《05.04 端口转发、TCP/UDP 隧道与远程打印协议扩展》**：解析 RustDesk 如何在端到端安全连接之上构建本地/远程端口转发隧道，实现访问远端局域网内网服务（如 Web、SSH、数据库）以及虚拟打印驱动集成。
