======================================================================
06.01 flutter_rust_bridge 架构与跨语言内存安全传递
======================================================================

.. note:: 前置背景与上下文承接
   在前五个模块中，我们先后构建了底层硬件抽象（模块 01）、音视频编解码与 QoS 流控（模块 02）、Protobuf 与 NAT 打洞传输（模块 03）、端到端加密与权限模型（模块 04）以及客户端 Tokio 异步并发与状态机（模块 05）。至此，RustDesk 的底层系统核心已具备高度完备的能力。然而，现代远程桌面客户端必须为全平台用户（Windows、macOS、Linux、Android、iOS）提供响应敏捷、动画流畅且现代化的图形用户界面（GUI）。RustDesk 选择使用 **Flutter (Dart)** 构建跨平台前端 UI，使用 **Rust** 承载底层系统核心。如何在这两种内存模型截然不同（Dart 的垃圾回收 GC 与 Rust 的所有权 RAII 模型）的语言之间建立零拷贝、高吞吐且强类型安全的跨语言调用桥梁？本章正式开启 **模块 06：Rust-Flutter FFI 桥接与跨平台渲染**，深入解剖 ``src/flutter_ffi.rs`` 与 ``flutter_rust_bridge`` 代码自动生成与内存安全传递机制。

***
跨语言 FFI 架构选型与 flutter_rust_bridge 物理设计
***

在跨平台桌面与移动端开发中，传统的跨语言桥接（如手写 C-ABI ``extern "C"`` 或基于 JNI / Objective-C 包装）面临着严重瓶颈：

1. **手写样板代码繁重且易错**：每新增一个远程控制配置项或事件，都需要在 C、Rust、Dart 三层分别声明结构体与序列化转换，极易发生字段类型对齐不一致导致内存越界崩溃（Segmentation Fault）。
2. **异步模型割裂**：Rust 的 ``Future`` 与 Dart 的 ``Future`` 无法直接互通，传统方式需要借助繁琐的回调函数指针（Callback Function Pointers）。
3. **内存生命周期管理冲突**：Dart 虚拟机由分代垃圾回收器（Generational GC）管理堆内存，而 Rust 依赖严格的栈展开与所有权销毁（RAII）。跨语言传递结构体所有权极易引发内存泄漏或使用已释放内存（Use-After-Free, UAF）。

.. list-table:: 跨语言调用技术对比
   :widths: 22 25 28 25
   :header-rows: 1

   * - 桥接方案
     - 代码生成与类型系统
     - 异步与流式支持
     - 跨语言内存安全
   * - **原生 Dart FFI**
     - 手写 C 结构体与指针转换
     - 需手动通过 ``ReceivePort`` 封装
     - 极易发生悬垂指针与内存泄漏
   * - **Pigeon (Flutter 官方)**
     - 仅支持 Java/Obj-C/Swift 桥接
     - 基于 Platform Channel 消息拷贝
     - 性能开销大，不支持原生 Rust
   * - **flutter_rust_bridge (FRB)**
     - 解析 Rust AST 自动生成 Dart/C/Rust 双向代码
     - 原生支持 ``Future<T>`` 与 ``StreamSink<T>``
     - 严格受控的内存装箱与零拷贝切片借用

---
代码自动生成器 (Codegen) 与 AST 绑定原理
---

RustDesk 在 ``src/flutter_ffi.rs`` 中定义公开的业务逻辑函数。``flutter_rust_bridge_codegen`` 工具链在编译期静态解析 Rust 源码的抽象语法树（AST），全自动生成三大核心胶水层：

```
[src/flutter_ffi.rs (Rust 业务公开接口)]
                 │
                 ▼ (flutter_rust_bridge_codegen 编译期 AST 静态分析)
 ┌───────────────┼──────────────────────────────┐
 ▼                                              ▼
[src/bridge_generated.rs]      [flutter/lib/generated_bridge.dart]
 (Rust 端 C-ABI 包装与解包)     (Dart 端强类型 API、Future 与 Stream 类)
```

1. 同步即时返回包装器 (``SyncReturn<T>``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于无阻塞的纯内存属性查询（如获取窗口标题、是否处于单会话模式、读取本地配置），若采用异步 Promise 会导致 UI 产生微小闪烁并增加事件循环调度开销。RustDesk 大量采用 ``SyncReturn<T>``：

.. code-block:: rust
   :caption: 同步无等待 FFI 接口定义（src/flutter_ffi.rs）

   // 直接在 Dart UI 调用的当前线程中同步返回结果，零异步调度开销
   pub fn main_get_app_name_sync() -> SyncReturn<String> {
       SyncReturn(get_app_name())
   }

   pub fn session_get_toggle_option_sync(session_id: SessionID, arg: String) -> SyncReturn<bool> {
       let res = session_get_toggle_option(session_id, arg) == Some(true);
       SyncReturn(res)
   }

   pub fn main_has_gpu_texture_render() -> SyncReturn<bool> {
       SyncReturn(cfg!(feature = "vram"))
   }

2. 异步 Future 自动映射
~~~~~~~~~~~~~~~~~~~~~~

对于耗时的网络 I/O 或文件操作，函数直接返回 Rust 的 ``ResultType<T>``。Codegen 会在 Dart 端将其映射为标准的 ``Future<T>``，底层通过 Dart 的 ``SendPort`` 与 Tokio 线程池自动衔接，保证了在等待网络响应期间绝对不阻塞 Flutter 的 60 FPS 渲染主 Isolate。

---
跨语言内存安全传递与数据序列化
---

在 Dart 与 Rust 跨越 FFI 边界交换复杂数据结构时，RustDesk 采用双重序列化策略：

```
[Dart 虚拟机堆内存 (GC)]                           [Rust 堆/栈内存 (RAII)]
          │                                                │
          ├─ 1. 结构化配置/列表: JSON 字符串传递 ──────────>│ (serde_json 强类型校验)
          │                                                │
          ├─ 2. 视频纹理/帧缓冲: 原始内存指针传递 ─────────>│ (注册 DirectX/Metal 句柄)
          │                                                │
          │<─ 3. 异步事件流: StreamSink<EventToUI> ────────┤ (跨 Isolate 零拷贝投递)
```

1. 结构化配置与列表数据的 JSON 屏障
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于地址簿设备列表（``main_load_recent_peers``）、会话权限集与显示器元数据，RustDesk 采用 ``serde_json`` 序列化为 UTF-8 字符串传递。JSON 字符串在 Dart 端能直接被 V8/Dart 引擎原生的快速 JSON 解析器反序列化为模型对象，在保持两端完全解耦的同时，规避了复杂 C 结构体在 32 位/64 位 CPU 架构下的内存内存对齐（Memory Alignment & Padding）歧义。

2. 音视频大内存指针安全映射
~~~~~~~~~~~~~~~~~~~~~~~~~~

对于每秒吞吐达数百兆的未压缩音视频与渲染纹理，绝对无法使用字符串或频繁深拷贝。RustDesk 通过直接传递内存地址（``usize`` 胖指针）实现零拷贝绑定：

.. code-block:: rust
   :caption: 显存纹理与原始像素缓冲区指针注册（src/flutter_ffi.rs）

   pub fn session_register_pixelbuffer_texture(
       session_id: SessionID,
       display: usize,
       ptr: usize, // 传递由 Flutter 渲染后端创建的纹理指针
   ) -> SyncReturn<()> {
       SyncReturn(super::flutter::session_register_pixelbuffer_texture(
           session_id, display, ptr,
       ))
   }

   pub fn session_register_gpu_texture(
       session_id: SessionID,
       display: usize,
       ptr: usize, // 传递 DirectX 11 / Metal 原始 GPU 纹理共享句柄
   ) -> SyncReturn<()> {
       SyncReturn(super::flutter::session_register_gpu_texture(
           session_id, display, ptr,
       ))
   }

---
跨语言异常处理与 Panic 防御屏障
---

在标准 Rust 中，若线程发生 ``panic!`` 且未被捕获，栈展开（Stack Unwinding）跨越 FFI 边界进入 Dart 虚拟机时会直接导致**未定义行为（Undefined Behavior, UB）**并使整个应用瞬间闪退。

``flutter_rust_bridge`` 在自动生成的 C-ABI 包装函数外层强制包裹了 ``std::panic::catch_unwind`` 屏障：
* 当 Rust 端发生不可恢复异常时，Panic 信息被拦截并安全转化为 Dart 端的异常对象（``FfiException``）；
* Flutter UI 层可以通过标准的 ``try/catch`` 捕获错误并弹出友好提示弹窗，彻底避免了客户端因为单次 FFI 异常而异常崩溃。

***
小结与下章导读
***

本章系统解剖了 RustDesk 跨语言 FFI 桥接的核心架构：
* 阐释了采用 ``flutter_rust_bridge`` 替代传统手写 C-ABI 的核心动机与 AST 自动代码生成原理。
* 剖析了同步无等待调用（``SyncReturn<T>``）与异步 ``Future<T>`` 的双轨调度设计。
* 揭示了配置数据 JSON 屏障与高频音视频渲染显存指针（``ptr: usize``）零拷贝传递的内存管理策略。
* 论证了跨语言 ``catch_unwind`` 防御屏障对客户端健壮性的物理保障。

在下一节中，我们将深入 UI 与底层的实时异步事件总线：
* **《06.02 StreamSink 异步事件总线与 UI 状态同步模型》**：深入解析 RustDesk 如何利用 ``StreamSink<EventToUI>`` 构建全双工实时事件通道，将网络状态、远程光标轨迹与音视频帧到达信号无阻塞地广播给前端 UI。
