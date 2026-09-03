======================================================================
06.02 StreamSink 异步事件总线与 UI 状态同步模型
======================================================================

.. note:: 前置背景与上下文承接
   在前一章《06.01 flutter_rust_bridge 架构与跨语言内存安全传递》中，我们解剖了 RustDesk 如何通过 AST 代码生成、``SyncReturn<T>`` 与 ``Future<T>`` 在 Dart 与 Rust 之间搭建起强类型、零开销且具备 Panic 防御屏障的调用通道。然而，远程桌面并非简单的“请求-响应”式单向调用系统，而是典型的**高频事件驱动（Event-Driven）实时系统**：远端被控端的鼠标每发生 1 像素偏移、视频编码器推送出新渲染帧、网络丢包触发 ABR 码率波动、文件传输进度实时更新，都需要在毫秒级时间内从 Rust 后台异步线程无阻塞地推送到 Flutter 的 UI 组件树。传统的轮询机制（Polling）会耗尽 CPU 并带来显著延迟。RustDesk 是如何基于 ``StreamSink<T>`` 构建全双工异步事件总线并实现多窗口/多显示器状态隔离同步的？本章将深入剖析 ``src/flutter.rs``、``src/flutter_ffi.rs`` 及 ``src/ui_session_interface.rs``，系统拆解事件总线拓扑、帧信号传递与多窗口多路复用模型。

***
全局总线与会话流双层事件拓扑架构
***

在跨平台客户端内部，UI 事件分为两类具有完全不同生命周期与吞吐要求的流量：

1. **全局广播事件（Global App Events）**：应用生命周期、配置变更（如深色模式切换、语言更新）、发现局域网对端、软件自动更新与地址簿在线状态同步。由全局主窗口（Main Window）与连接管理器（Connection Manager, CM）共享。
2. **会话高频实时事件（Session-Scoped High-Throughput Events）**：特定远程桌面会话内的光标坐标、输入锁定状态、视频新帧就绪通知、文件分块进度与音频电平。由独立的远程桌面会话窗口独占。

```
[ Rust 后台线程池 (Tokio / Video Worker / Audio Thread) ]
                             │
     ┌───────────────────────┴───────────────────────┐
     ▼                                               ▼
[ 全局事件总线: GLOBAL_EVENT_STREAM ]    [ 会话级事件流: FlutterHandler::session_handlers ]
  ├── Tag: "main" (主界面事件)             ├── SessionID_1 -> StreamSink<EventToUI>
  └── Tag: "cm" (连接管理服务)            └── SessionID_2 -> StreamSink<EventToUI>
     │                                               │
     ▼                                               ▼
[ Flutter Dart VM: 主 Isolate 事件监听 ]    [ Flutter 远程桌面 Window 渲染与交互组件树 ]
```

.. list-table:: RustDesk 跨语言事件流通道对比
   :widths: 22 25 28 25
   :header-rows: 1

   * - 通道类别
     - 底层数据结构
     - 事件载荷类型
     - 路由目标与生命周期
   * - **全局事件流**
     - ``GLOBAL_EVENT_STREAM`` (HashMap)
     - ``String`` (JSON 广播数据)
     - 随主界面/CM 进程常驻，跨窗口全局分发
   * - **会话实时流**
     - ``SessionHandler::event_stream``
     - ``EventToUI`` 枚举
     - 随远程连接会话动态创建与销毁，单会话/多窗口隔离

---
``EventToUI`` 协议设计与三态分发模型
---

在 ``src/flutter_ffi.rs`` 中，会话级事件载荷被抽象为紧凑的枚举类型 ``EventToUI``：

.. code-block:: rust
   :caption: 会话到 UI 的核心事件枚举（src/flutter_ffi.rs）

   pub enum EventToUI {
       Event(String),         // 结构化业务事件（光标、质量、剪贴板、权限等 JSON）
       Rgba(usize),           // 软件渲染新帧就绪信号（携带 display 索引）
       Texture(usize, bool),  // 硬件 GPU 纹理新帧就绪信号 (display, gpu_texture_flag)
   }

1. 业务事件的高吞吐 JSON 封装与组播（``push_event_``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``src/flutter.rs::FlutterHandler`` 中，底层模块通过 ``InvokeUiSession`` 特征触发 UI 更新。事件分发支持**包含（include）**与**排除（exclude）**过滤：

.. code-block:: rust
   :caption: 会话事件过滤与组播逻辑（src/flutter.rs）

   pub fn push_event_<V>(
       &self,
       name: &str,
       event: &[(&str, V)],
       includes: &[&SessionID],
       excludes: &[&SessionID],
   ) where
       V: Sized + Serialize + Clone,
   {
       let mut h: HashMap<&str, serde_json::Value> =
           event.iter().map(|(k, v)| (*k, json!(*v))).collect();
       h.insert("name", json!(name));
       let out = serde_json::ser::to_string(&h).unwrap_or("".to_owned());

       // 遍历挂载在当前 Peer 上的所有 UI 窗口句柄
       for (sid, session) in self.session_handlers.read().unwrap().iter() {
           let mut push = false;
           if includes.is_empty() {
               if !excludes.contains(&sid) { push = true; }
           } else {
               if includes.contains(&sid) { push = true; }
           }
           if push {
               if let Some(stream) = &session.event_stream {
                   // 写入 Dart Isolate 端口，无锁非阻塞
                   stream.add(EventToUI::Event(out.clone()));
               }
           }
       }
   }

---
音视频帧到达通知与零拷贝双缓冲（Double-Buffering）
---

对于每秒 60 帧以上的视频画面更新，若直接将巨大的像素数组放入事件总线，序列化与跨 Isolate 内存拷贝将瞬间打满 CPU 并造成垃圾回收停顿（GC Pause）。

RustDesk 采用了**带状态标志的内存双缓冲与纯信号唤醒机制**：

```
[视频解码线程 VideoHandler]                              [Flutter 渲染引擎 / Dart Isolate]
           │                                                            │
           ├─ 1. 解码完成，得到 ImageRgb (宽 w, 高 h, 数据 raw)         │
           ├─ 2. 获取 display_rgbas 锁，检查 rgba_data.valid            │
           │     * 若 valid == true (上一帧 UI 尚未消费):               │
           │       放弃本帧渲染通知，避免积压 (Frame Dropping)          │
           │     * 若 valid == false:                                   │
           │       执行原子内存指针交换: swap(raw, rgba_data.data)     │
           │       标记 rgba_data.valid = true                          │
           │                                                            │
           ├─ 3. 向 StreamSink 发送轻量信号: EventToUI::Rgba(display) ─>│
           │                                                            ├─ 4. Dart 监听到 Rgba 事件
           │                                                            ├─ 5. 调用 session_get_rgba 指针
           │                                                            │    直接由 GPU 渲染管线读取
           │                                                            ├─ 6. 消费完成，调用 session_next_rgba
           │                                                            │    重置 valid = false
```

1. 内存零拷贝指针交换（``std::mem::swap``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: rust
   :caption: 软件渲染双缓冲指针交换（src/flutter.rs）

   fn on_rgba_soft_render(&self, display: usize, rgba: &mut scrap::ImageRgb) {
       let mut rgba_write_lock = self.display_rgbas.write().unwrap();
       if let Some(rgba_data) = rgba_write_lock.get_mut(&display) {
           if rgba_data.valid {
               return; // 上一帧尚在渲染中，跳过本帧通知以维持背压平衡
           } else {
               rgba_data.valid = true;
           }
           // 高性能指针交换：重用已分配的堆内存，零分配开销
           std::mem::swap::<Vec<u8>>(&mut rgba.raw, &mut rgba_data.data);
       }
       // ...
   }

---
多窗口独立显示器会话路由模型 (``sessions`` mod)
---

在多显示器远程办公场景中，主控端支持“将远端不同屏幕拆分为独立窗口”（Displays as Individual Windows）。

1. 动态捕获集合交集计算（``check_remove_unused_displays``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当用户关闭其中一个屏幕的独立窗口时，受控端不应继续编码和推流该屏幕的像素，以大幅节省网络带宽与 CPU/GPU 算力：

.. code-block:: rust
   :caption: 动态多窗口显示器引用计数裁剪（src/flutter.rs）

   fn check_remove_unused_displays(
       current: Option<usize>,
       session_id: &SessionID,
       session: &FlutterSession,
       handlers: &HashMap<SessionID, SessionHandler>,
   ) {
       let mut remains_displays = HashSet::new();
       if let Some(current) = current { remains_displays.insert(current); }
       for (k, h) in handlers.iter() {
           if k == session_id { continue; }
           remains_displays.extend(h.renderer.map_display_sessions.read().unwrap().keys().cloned());
       }
       // 仅保留当前仍有窗口打开的屏幕集合，通知远端停用无引用的屏幕抓屏
       if !remains_displays.is_empty() {
           session.capture_displays(vec![], vec![], remains_displays.iter().map(|d| *d as i32).collect());
       }
   }

***
小结与下章导读
***

本章系统解构了 RustDesk 跨语言异步事件总线架构：
* 剖析了面向全局广播的 ``GLOBAL_EVENT_STREAM`` 与面向高频会话的 ``SessionHandler::event_stream`` 双层拓扑。
* 揭示了 ``EventToUI`` 枚举协议在解耦控制信令与像素数据流中的关键作用。
* 拆解了基于 ``std::mem::swap`` 零拷贝双缓冲与 ``valid`` 背压状态机的 60+ FPS 视频帧信号唤醒机制。
* 总结了多窗口/多显示器会话中的引用计数动态裁剪与带宽智能节约算法。

在下一节中，我们将深入图形渲染流水线的终极环节：
* **《06.03 远程桌面画面渲染：GPU Texture 纹理共享与着色器流水线》**：深入剖析基于 DirectX 11 / Metal 的显存共享句柄跨进程/跨插件绑定、Flutter Texture Widget 硬件直通与 YUV/NV12 到 RGB 的 GPU 着色器加速渲染。
