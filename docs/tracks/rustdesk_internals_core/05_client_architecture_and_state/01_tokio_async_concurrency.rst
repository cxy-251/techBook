======================================================================
05.01 Tokio 异步运行时拓扑与 IO/Worker 线程池协同机制
======================================================================

.. note:: 前置背景与上下文承接
   在前四个模块中，我们先后构建了底层硬件与操作系统原语（模块 01）、音视频流媒体编解码（模块 02）、Protobuf 与 NAT 打洞网络栈（模块 03）以及端到端加密与安全权限控制体系（模块 04）。在整个远程桌面系统的客户端内部，所有这些模块必须同时并发运转：数千个网络 UDP 数据报在毫秒级时间内被异步接收、音视频压缩数据包在专用线程中被硬件或多核 CPU 解码、鼠标高频采样数据被实时发送、剪贴板变化被监听，同时 UI 渲染引擎必须以 60~120 FPS 保持丝滑流畅。如何在单个客户端进程内编排这些**高吞吐异步网络 I/O**与**重度 CPU 密集型编解码任务**？本章正式开启 **模块 05：客户端架构、Tokio 运行时与状态机**，深入剖析 RustDesk 在 ``src/client.rs``、``src/client/io_loop.rs`` 中的 Tokio 多运行时拓扑、无锁环形队列与跨线程协同调度架构。

***
异步 I/O 与 CPU 密集型计算的物理冲突与解耦
***

在基于协程/异步（Async/Await）的现代并发编程中，Tokio 运行时的核心调度单元是轻量级的协作式任务（Green Threads / Tasks）。Tokio 的工作线程（Worker Threads）假定每个任务在其执行轮次（Tick）中仅消耗极少量的 CPU 时间（微秒级）便会主动让出控制权（Yield）。

然而，远程桌面包含两类物理特性完全相反的负载：

1. **高频轻量网络 I/O（I/O-Bound）**：信令轮询、KCP 数据报收发、NAT 心跳维持、输入事件微包发送。要求事件循环具备极高的响应度与极低的时延抖动。
2. **重度 CPU/GPU 计算（Compute-Bound）**：4K 视频帧解码、libyuv 像素格式转换、Opus 音频重采样、NaCl 加解密。单个任务可能持续霸占 CPU 核心 $5 \sim 15\,	ext{ms}$。

.. warning:: 异步协作调度的灾难性陷阱
   若直接在 Tokio 异步任务内部同步调用视频解码器（如 ``decoder.handle_video_frame()``），Tokio 工作线程将被长时间阻塞（Worker Starvation）。这会导致同线程上的网络 I/O 任务无法及时从网卡套接字读取数据，引发 UDP 缓冲区溢出丢包、KCP 确认超时（RTO）以及严重的画面撕裂与控制迟滞。

---
RustDesk 客户端多运行时与线程池分层拓扑
---

为了彻底消除计算饥饿并保证 UI 极致流畅，RustDesk 构建了分工明确的**三层并发拓扑架构**：

```
                    [ Flutter / UI 渲染层 (主线程 / UI 引擎) ]
                                   │
                         (StreamSink / FFI 事件总线)
                                   ▼
[ 异步网络与信令层 (Tokio Multi-Thread Runtime) ]
   ├── Tokio Event Loop 1 ~ N (epoll/kqueue/IOCP 异步驱动)
   ├── Client::start_inner (连接建立、NAT 穿透竞速)
   └── RendezvousMediator (信令心跳保活、配置同步)
                                   │
         ┌─────────────────────────┴─────────────────────────┐
         │ (无锁队列 ArrayQueue)                             │ (MPSC 通道)
         ▼                                                   ▼
[ 专用计算 Worker 线程: 视频解码 ]                 [ 专用计算 Worker 线程: 音频处理 ]
   ├── VideoHandler (std::thread)                      ├── AudioHandler (std::thread)
   ├── 硬件显存解码 / libvpx 软件多线程                ├── Magnum Opus 解码器
   └── 帧率平滑计算与丢帧调度                         └── CPAL 环形缓冲区音频回放
```

1. 全局异步运行时与局部独立运行时
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* **全局多线程运行时（Global Multi-Threaded Runtime）**：
  驱动核心网络客户端、P2P 打洞竞速与信令中继。
* **独立单线程运行时（Current-Thread Runtime Isolation）**：
  针对独立的短生命周期任务（如 NAT 类型探测 ``test_nat_type_``、软件版本检查 ``do_check_software_update``、Windows CPU 使用率同步 ``do_sync_cpu_usage``），使用 ``#[tokio::main(flavor = "current_thread")]`` 创建轻量单线程运行时，杜绝线程过度争用与全局上下文污染。

---
无锁环形队列与跨线程高吞吐管道
---

在网络接收端与解码/渲染工作线程之间，RustDesk 避免使用重量级的互斥锁（``Mutex``），而是采用基于内存屏障的高性能通信管道：

1. 视频帧无锁缓冲队列（``ArrayQueue<VideoFrame>``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``src/client.rs::start_video_thread`` 中，网络线程接收到的未解压视频帧被推入固定容量（默认 120 帧）的无锁环形队列：

.. code-block:: rust
   :caption: 视频工作线程与无锁队列调度（src/client.rs）

   pub fn start_video_thread<F, T>(
       session: Session<T>,
       display: usize,
       video_receiver: mpsc::Receiver<MediaData>,
       video_queue: Arc<RwLock<ArrayQueue<VideoFrame>>>,
       fps: Arc<RwLock<Option<usize>>>,
       chroma: Arc<RwLock<Option<Chroma>>>,
       discard_queue: Arc<RwLock<bool>>,
       video_callback: F,
   ) where
       F: 'static + FnMut(usize, &mut scrap::ImageRgb, *mut c_void, bool) + Send,
       T: InvokeUiSession,
   {
       std::thread::spawn(move || {
           let mut video_handler = None;
           loop {
               if let Ok(data) = video_receiver.recv() {
                   match data {
                       MediaData::VideoQueue => {
                           // 从无锁队列中弹出视频帧
                           if let Some(vf) = video_queue.read().unwrap().pop() {
                               // 若触发丢帧标记（如快速追帧模式），直接跳过历史陈旧帧
                               if discard_queue.read().unwrap().clone() {
                                   continue;
                               }
                               // 执行重度解码与像素处理
                               if let Some(handler) = video_handler.as_mut() {
                                   handler.handle_frame(vf, &mut pixelbuffer, &mut tmp_chroma);
                               }
                           }
                       }
                       // ...
                   }
               }
           }
       });
   }

2. 音频解码与环回延迟平滑（``AudioBuffer``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

音频流具有极高的时序敏感性。RustDesk 在 ``src/client.rs::AudioHandler`` 中独立开辟音频线程，配合 ``cpal`` 的音频输出回调与无锁环形缓冲区（``ringbuf::HeapRb<f32>``），实现动态水位收缩（``try_shrink``），在保证音频不发生破音断续的前提下，将音频缓冲时延压制在 $50\,	ext{ms}$ 以内。

---
异步-同步边界安全与死锁防御策略
---

当在同一个进程中混用 Tokio 异步 Future 与操作系统同步原生锁（``std::sync::Mutex`` / ``RwLock``）时，极易引发死锁：

1. **跨 ``.await`` 持有同步锁导致死锁**：
   若一个 Tokio 任务在获取了 ``std::sync::MutexGuard`` 后调用了 ``.await`` 被挂起，该工作线程若转去调度另一个试图获取相同锁的任务，将导致整个 Tokio 工作线程池彻底冻结。
2. **RustDesk 的防御原则**：
   * **临界区极小化**：同步锁仅用于保护纯内存数据结构的读写，在执行任何网络 I/O、通道发送或异步等待前，通过局部代码块（``{ let _guard = lock; ... }``）强制提前 ``drop`` 释放锁；
   * **异步原生同步原语**：在跨异步点需要等待的场景，严格使用 ``tokio::sync::Mutex`` 与 ``tokio::sync::oneshot``；
   * **生命周期优雅终止**：通过 ``oneshot::channel<()>`` 广播停止信号（如 ``stop_udp_tx.send(())``），确保在会话结束时，各后台线程能够被确定性回收，杜绝僵尸线程与内存泄漏。

***
小结与下章导读
***

本章系统解构了 RustDesk 客户端的核心并发架构：
* 阐述了将高频轻量网络 I/O（Tokio 异步运行时）与 CPU 密集型音视频编解码（独立 OS 线程）严格物理隔离的设计原理。
* 剖析了全局多线程 Tokio Runtime 与单线程局部 Runtime（``current_thread``）的多层拓扑结构。
* 揭示了基于 ``crossbeam_queue::ArrayQueue`` 的无锁视频帧缓冲管道与动态跳帧追流机制。
* 总结了异步-同步边界上的死锁防御规范与基于 RAII / Oneshot 的确定性资源清理。

在下一节中，我们将深入客户端的控制中枢：
* **《05.02 客户端生命周期状态机与多路复用连接管理》**：深入剖析主控端从初始化配置加载、呼叫对端、多路径握手竞速、会话鉴权到断线重连与优雅销毁的全局状态机演进。
