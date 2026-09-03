========================================================================================
第 1 节：C++ Embedder 宿主工程架构、四大线程并发模型与 TaskRunner 消息分发
========================================================================================

.. note::
   **源码坐标与本节核心使命**
   * **底层 C++ 引擎源码**：``engine/src/flutter/shell/common/engine.cc``、``engine/src/flutter/runtime/dart_vm.cc``、``engine/src/flutter/fml/message_loop.cc`` 与 ``engine/src/flutter/shell/common/rasterizer.cc``
   * **Framework 对应源码**：``flutter-3.32.0/packages/flutter/lib/src/services/binding.dart`` 与 ``packages/flutter/lib/src/scheduler/binding.dart``
   * **核心使命**：跨越 Dart 语言边界向下彻底穿透至 C++ 核心引擎，深度解构 Flutter Embedder 宿主工程的物理隔离机制、C++ 引擎初始化与 Dart VM 实例拉起时序、Platform / UI / Raster / IO 四大多线程拓扑与并发流水线、以及基于 FML（Flutter Message Loop）的 ``TaskRunner`` 跨线程无锁任务调度机制。

----------------------------------------------------------------------------------------

第一幕：Embedder 宿主工程与 C++ 引擎的物理边界
----------------------------------------------

Flutter 与传统 Web 浏览器或混合跨平台框架（如 Electron / React Native）的本质区别在于：**它在操作系统中完全没有依赖任何系统级 UI 控件或 DOM 树**。

在 macOS、Windows、Linux、iOS 和 Android 各大平台上，操作系统眼中的 Flutter 应用仅仅是一个极简的**宿主外壳（Embedder）**：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ 操作系统原生宿主环境 (macOS AppKit / Android NDK / Windows Win32)        │
   │ ┌──────────────────────────────────────────────────────────────────────┐ │
   │ │ 原生宿主外壳 (Embedder: FlutterEngine / FlutterViewController)       │ │
   │ │ • 申请单一物理窗口句柄 (NSWindow / SurfaceView / HWND)               │ │
   │ │ • 捕获操作系统原生事件 (键盘、鼠标、触摸屏硬件中断)                  │ │
   │ └──────────────────────────────────┬───────────────────────────────────┘ │
   └────────────────────────────────────┼─────────────────────────────────────┘
                                        │ (C++ API 接口对接)
   ┌────────────────────────────────────▼─────────────────────────────────────┐
   │ Flutter C++ 核心引擎 (Flutter Engine)                                     │
   │ ├── 1. Dart VM Runtime (Dart 虚拟机与 Isolate 运行时隔离环境)            │
   │ ├── 2. Graphics Backend (Skia / Impeller 现代图形光栅化渲染后端)         │
   │ ├── 3. Text Layout Engine (LibTxt / HarfBuzz / ICU 复杂字形排版引擎)     │
   │ └── 4. FML (Flutter Message Loop - 跨平台高性能多线程事件消息循环)       │
   └──────────────────────────────────────────────────────────────────────────┘

1. 引擎启动生命周期序列（`Engine::Run`）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当原生宿主启动时，物理执行流水线如下：
1. **加载引擎动态库**：宿主加载 ``libflutter.dylib`` (macOS) 或 ``libflutter.so`` (Android)；
2. **初始化 Dart VM**：创建全局单例 ``dart::vm::DartVM``，配置堆内存垃圾回收参数与 JIT/AOT 机器码执行空间；
3. **创建主 Isolate（Root Isolate）**：拉起专门运行应用主程序的沙盒环境，并将编译好的资产文件 ``app.so``（AOT 机器码）或 ``kernel_blob.bin``（字节码）载入内存；
4. **绑定图形渲染上下文（GL / Metal Context）**：向操作系统图形驱动申请与窗口句柄绑定的交换链（Swapchain），为后续 GPU 光栅化做好硬件准备。

----------------------------------------------------------------------------------------

第二幕：四大核心线程模型（Four Dedicated Threads）的物理分工
------------------------------------------------------------

为了保证界面在高负载运算下依然能够维持稳定的 60Hz / 120Hz 刷新率，Flutter C++ 引擎在底层设计了**严格物理隔离的四大专用线程**：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ Flutter 核心四大并发线程拓扑模型                                          │
   ├───────────────────┬──────────────────────────────────────────────────────┤
   │ 1. Platform Thread│ 宿主操作系统原生主线程 (Native Main Thread)           │
   │    (平台主线程)   │ • 职责: 响应 OS 窗口生命周期、处理原生输入事件与插件通信│
   │                   │ • 规则: 严禁执行任何耗时 Dart 运算或阻塞式 I/O        │
   │                                                                          │
   │ 2. UI Thread      │ Dart 虚拟机执行线程 (Root Isolate Thread)            │
   │    (UI 业务线程)  │ • 职责: 执行 Dart 代码、驱动 Widget/Element/RenderObject│
   │                   │ • 产出: 生成高度优化的图层绘制指令树 (LayerTree)     │
   │                                                                          │
   │ 3. Raster Thread  │ 硬件光栅化线程 (原 GPU Thread)                        │
   │    (光栅化渲染线程)│ • 职责: 接收 LayerTree，调用 Skia/Impeller 生成 GPU 指令│
   │                   │ • 产出: 提交 Metal/Vulkan/OpenGL 交换链上屏渲染       │
   │                                                                          │
   │ 4. IO Thread      │ 异步 I/O 与纹理上传线程 (Background IO Thread)        │
   │    (异步资源线程)  │ • 职责: 异步解码大图片、生成 GPU 离屏纹理并上传显存    │
   │                   │ • 特性: 与 Raster 线程共享 GL Context，完全零卡顿     │
   └───────────────────┴──────────────────────────────────────────────────────┘

1. UI 线程与 Raster 线程的双缓冲流水线（Pipeline Pipelining）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
UI 线程与 Raster 线程并不是串行等待的，而是以**帧流水线（Pipelined Frames）**方式并行工作：

.. code-block:: text

   时间轴 t: ──帧 N 开始 (VSync)────────────帧 N+1 开始 (VSync)────────────►
   UI 线程:   │ 绘制指令计算: Frame N+1      │ 绘制指令计算: Frame N+2      │
   Raster线程:│ GPU 硬件光栅化: Frame N      │ GPU 硬件光栅化: Frame N+1    │

* 在第 $N$ 个 VSync 周期内，UI 线程正在内存中全力计算第 $N+1$ 帧的 Widget 树与 `LayerTree`；
* 同一时刻，Raster 线程正在 GPU 中全力将 UI 线程上一周期提交的第 $N$ 帧 `LayerTree` 光栅化为像素并推上屏幕；
* **物理收益**：双线程流水线将单帧的最大可用计算时间从 16.6ms 理论翻倍，极大地平滑了帧率波动。

----------------------------------------------------------------------------------------

第三幕：FML 消息循环与 `TaskRunner` 任务分发调度机制
----------------------------------------------------

四大线程之间不共享堆栈，所有的跨线程调用全部由 **FML（Flutter Message Loop）** 提供的 ``TaskRunner`` 机制进行无锁调度：

1. `fml::TaskRunner` 核心接口
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
每个线程在 C++ 层面都绑定了一个专有的 ``fml::TaskRunner`` 句柄：
* ``PostTask(fml::closure task)``：将一个无参回调函数推入目标线程的无锁先进先出（FIFO）任务队列中，目标线程在下一次事件循环时就地执行；
* ``PostTaskForTime(fml::closure task, fml::TimePoint target_time)``：高精度定时任务调度，在目标物理时间点到来时准时唤醒执行。

2. `LayerTree` 跨线程无缝移交时序
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当 UI 线程完成一帧的绘制记录后，移交控制权的微观时序如下：
1. UI 线程生成不可变的根图层树：``std::unique_ptr<flutter::LayerTree> layer_tree``；
2. UI 线程调用 ``raster_task_runner->PostTask([rasterizer, layer_tree = std::move(layer_tree)]() { rasterizer->Draw(std::move(layer_tree)); })``；
3. 通过 C++11 移动语义（``std::move``），图层树的所有权被零拷贝瞬间转移至 Raster 线程的任务队列中；
4. UI 线程立刻释放控制权并进入休眠，等待下一个硬件 VSync 脉冲唤醒。

----------------------------------------------------------------------------------------

小结与给下一个对话的施工建议 (Summary & Next Step Advisory)
------------------------------------------------------------

* **本章核心产出**：
  至此，**模块 08 第 1 节：``08_engine_frame_pipeline/01_embedder_and_threads.rst`` 已全量落盘完工**！系统拆解了 C++ Embedder 宿主工程物理边界、Platform / UI / Raster / IO 四大线程并发模型、UI 与 Raster 线程双缓冲帧流水线、以及 FML TaskRunner 跨线程无锁任务调度机制。
* **给下一个周期的施工建议**：
  下一个周期将严格聚焦 **模块 08 第 2 节：``08_engine_frame_pipeline/02_platform_dispatcher_pipeline.rst``**。
  我们将深入 ``engine/src/flutter/lib/ui/window/platform_configuration.cc`` 与 ``flutter-3.32.0/packages/flutter/lib/src/services/binding.dart``，系统剖析 ``PlatformDispatcher`` 单例作为 C++ 引擎与 Dart 框架唯一门户的原生事件管道（``onBeginFrame`` / ``onDrawFrame``）、多视口（Multi-View / FlutterView）窗口度量分发、以及系统配置（Locale / Brightness）变动广播机制。
