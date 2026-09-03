========================================================================================
第 3 节：SceneBuilder 场景打包、UI与光栅化线程交接与 Impeller GPU 提交
========================================================================================

.. note::
   **源码坐标与本节核心使命**
   * **核心源文件**：``flutter-3.32.0/packages/flutter/lib/src/rendering/view.dart`` (RenderView.compositeFrame) 与 ``binding.dart``
   * **底层引擎源码**：``flutter-3.32.0/engine/src/flutter/lib/ui/compositing/scene_builder.cc``、``shell/common/rasterizer.cc`` 与 ``impeller/`` 渲染架构
   * **核心使命**：以现代实时图形渲染管线与 GPU 驱动提交时序为基准，深度解构 Flutter 3.32 从 Dart 框架层向物理 GPU 跨越的终极微观执行流——``RenderView.compositeFrame`` 的场景打包协议、``ui.SceneBuilder`` 通过 Dart FFI 原生边界构建 C++ ``LayerTree``、UI 线程向光栅化线程（Raster Thread）的流水线任务移交、Impeller 新一代渲染引擎（AOT 预编译着色器、``EntityPass`` 树、``HostBuffer`` 瞬时显存池）彻底终结着色器编译卡顿（Shader Jank）的底层物理架构、以及最终向 Metal / Vulkan API 提交 Command Buffer 并触发 ``Present`` 上屏的完整时序。

----------------------------------------------------------------------------------------

第一幕：`RenderView.compositeFrame` 场景打包与跨边界 FFI 调用
--------------------------------------------------------------

当 ``PipelineOwner.flushPaint()`` 完成整棵渲染树的绘制录制后，内存中已经形成了一棵以根节点 ``RenderView.layer``（``TransformLayer``）为顶点的完整图层树（``LayerTree``）。

在 ``RenderView.compositeFrame()`` 中，系统启动了向 C++ 引擎的终极打包协议：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ RenderView.compositeFrame() 场景打包与 FFI 跨边界执行流                   │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 1. 创建原生场景构建器:                                                   │
   │    ui.SceneBuilder builder = RendererBinding.instance.createSceneBuilder();│
   │    • 底层调用 C++ 构造器: flutter::SceneBuilder::create()                 │
   │                                                                          │
   │ 2. 递归遍历 LayerTree 注入绘制指令:                                       │
   │    ui.Scene scene = layer.buildScene(builder);                           │
   │    • 遍历 ContainerLayer 双向链表，执行 pushTransform / pushClip 等操作   │
   │    • 命中未变动子图层: 直接触发 builder.addRetained(engineLayer) 高速复用  │
   │                                                                          │
   │ 3. 封闭生成不可变场景句柄:                                               │
   │    ui.Scene scene = builder.build();                                     │
   │    • 生成不可变的 C++ flutter::Scene 对象，封装整帧独立的 flutter::LayerTree│
   │                                                                          │
   │ 4. 提交给底层平台视口:                                                   │
   │    _view.render(scene, size: configuration.toPhysicalSize(size));        │
   │    • 触发 FFI 本地调用: WindowClient::Render(scene)                       │
   │    • 跨越语言边界，将控制权移交至 C++ 引擎内核！                          │
   │                                                                          │
   │ 5. 即时销毁 Dart 侧场景句柄:                                              │
   │    scene.dispose(); // 释放 Dart 封装壳，底层 C++ LayerTree 由引擎接管生命周期│
   └──────────────────────────────────────────────────────────────────────────┘

1. 物理像素转换矩阵校验
~~~~~~~~~~~~~~~~~~~~~~~
在调用 ``_view.render`` 前，系统执行逻辑像素到物理像素的严密映射：
$$	ext{PhysicalSize} = 	ext{configuration.toPhysicalSize}(	ext{logicalSize}) = 	ext{logicalSize} 	imes 	ext{devicePixelRatio}$$
根节点的 ``TransformLayer`` 预先加载了放大系数为 $	ext{devicePixelRatio}$ 的缩放矩阵，确保后续所有 GPU 坐标直接在原生物理分辨率（如 4K 或 Retina 视网膜屏）下点对点光栅化，杜绝拉伸模糊。

----------------------------------------------------------------------------------------

第二幕：UI 线程到光栅化线程（Raster Thread）的流水线移交
----------------------------------------------------------

为了保证界面的丝滑流畅，Flutter 严格实行**双缓冲多线程流水线架构**：UI 线程负责计算下一帧，光栅化线程（Raster Thread）负责渲染当前帧，两者在物理上完全并行。

.. code-block:: text

   【UI 线程 (UI Thread)】                           【光栅化线程 (Raster Thread)】
   ════════════════════════                          ════════════════════════════
   执行 flushLayout() / flushPaint()
          │
          ▼
   生成 C++ flutter::LayerTree
          │
          ▼
   调用 Shell::OnPlatformViewRender()
          │
          ├── (推入管道队列 Pipeline<LayerTree>) ──►  唤醒光栅化线程事件循环
          │                                                    │
   [UI 线程立即释放！]                                          ▼
   立即可响应后续手势中断与 VSync 脉冲                         Rasterizer::Draw(layer_tree)
                                                               │
                                                               ▼ 执行真正的 GPU 绘制！

1. 帧流水线管道队列（`Pipeline<LayerTree>`）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* C++ 引擎内部维护了一个深度为 2 的线程安全队列（``ProducerConsumerQueue``）；
* UI 线程作为生产者（Producer）将打包好的 ``LayerTree`` 压入队列后，**立即返回并结束当前时钟周期**，完全不需要等待 GPU 渲染完成；
* 光栅化线程作为消费者（Consumer）从队列中弹出 ``LayerTree``，开始驱动底层图形 API 执行硬件渲染。

----------------------------------------------------------------------------------------

第三幕：Impeller 新一代渲染引擎微架构 vs 传统 Skia
---------------------------------------------------

在传统的 Skia 渲染引擎中，移动端长期饱受**着色器编译卡顿（Shader Compilation Jank）**的困扰：当界面首次出现某种特定阴影、渐变或滤镜时，Skia 必须在运行时现场调用 GPU 驱动将 GLSL/MSL 源代码即时编译（JIT）为 GPU 机器码，导致单帧耗时突破 50~100 毫秒引发严重掉帧。

Flutter 3 引入的自研现代图形引擎 **Impeller** 在微架构层面彻底重构了这一流程：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ Impeller 现代图形渲染流水线 (零 JIT 编译卡顿)                             │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 1. AOT 离线着色器预编译 (impellerc 编译器):                               │
   │    • 在应用打包编译期，impellerc 预先将所有着色器编译为二进制字节码:      │
   │      - iOS / macOS: 编译为 Metal Shading Language (MSL) 二进制管线状态库  │
   │      - Android / Linux: 编译为 Vulkan SPIR-V 二进制着色器模块             │
   │    • 运行时零着色器编译开销，彻底消灭首帧卡顿！                           │
   │                                                                          │
   │ 2. Aiks 抽象层与 EntityPass 渲染通道树构建:                              │
   │    • 遍历 LayerTree，将绘制指令转化为不可变实体树 (Entity Tree)          │
   │    • 智能合并绘制操作，自动剔除屏幕视口外的不可见实体 (Occlusion Culling) │
   │                                                                          │
   │ 3. HostBuffer 瞬时显存分配池 (零堆内存碎片):                             │
   │    • 单帧内所有顶点数据、变换矩阵、索引数据全部写入预先分配的线性环形缓冲区 │
   │    • 单次内存分配耗时 < 1 微秒，完全无需频繁调用 malloc / free          │
   │                                                                          │
   │ 4. 原生 GPU Command Buffer 录制与提交:                                   │
   │    • Metal 平台:   直接录入 id<MTLRenderCommandEncoder>                   │
   │    • Vulkan 平台:  直接录入 VkCommandBuffer                               │
   │    • 最终调用 GPU 驱动的 QueueSubmit 批量执行硬件光栅化！                │
   └──────────────────────────────────────────────────────────────────────────┘

1. `HostBuffer` 极速显存环形池
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* Impeller 在主存与显存之间维护了单一连续映射的 ``HostBuffer``；
* 当需要绘制圆角矩形或文字时，算法直接通过移动指针（Pointer Bump）在缓冲区中切出所需字节，并将显存物理偏移量填入 Command Buffer，实现了硬件级的零拷贝传输。

----------------------------------------------------------------------------------------

第四幕：双缓冲交换与物理屏幕上屏呈现（Surface Present）
--------------------------------------------------------

当 GPU 执行完 Command Buffer 中的所有光栅化指令后，最终的像素矩阵已经被完整写入后缓冲区（Back Buffer）：

1. **调用平台层提交（`Surface::Present`）**：
   * 在 macOS / iOS 上：调用 Metal 框架的 ``[MTLDrawable present]``；
   * 在 Android / Linux 上：调用 Vulkan API 的 ``vkQueuePresentKHR()``。
2. **等待 VSync 硬件垂直消隐脉冲**：
   * 显卡显示控制器在扫描线回到屏幕左上角的一瞬间，瞬间对调前缓冲区与后缓冲区指针（Page Flip）；
   * 屏幕像素点发光，呈现出最新一帧的绚丽画面！

----------------------------------------------------------------------------------------

小结与给下一个对话的施工建议 (Summary & Next Step Advisory)
------------------------------------------------------------

* **本章核心产出**：
  至此，**模块 09 第 3 节：``09_engine_rendering_and_gpu/03_scene_builder_and_gpu_raster.rst`` 已全量落盘完工**！系统拆解了 RenderView.compositeFrame 场景打包协议、UI/Raster 跨线程流水线移交、Impeller AOT 着色器预编译架构、HostBuffer 瞬时显存池、以及 Metal/Vulkan Command Buffer 提交与 Present 上屏微观物理时序。
* **给下一个周期的施工建议**：
  下一个周期将迎来 **【全书大结局与最终章节】——模块 09 第 4 节：``09_engine_rendering_and_gpu/04_platform_channels_binary_messenger.rst``**！
  我们将深入 ``flutter-3.32.0/engine/src/flutter/shell/platform/common/client_wrapper/binary_messenger_impl.cc`` 与 ``MethodChannel`` 源码，系统剖析跨语言通信底座——``BinaryMessenger`` 共享内存二进制通道、``StandardMessageCodec`` 零拷贝序列化协议、方法通道（MethodChannel）/ 事件流通道（EventChannel）的异步分发、以及与原生平台（macOS / Android）双向高频调用的性能调优铁律。
