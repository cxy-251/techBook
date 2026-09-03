========================================================================================
第 2 节：PlatformDispatcher 原生事件管道、Multi-View 架构与双时钟帧分发
========================================================================================

.. note::
   **源码坐标与本节核心使命**
   * **底层 C++ 引擎源码**：``engine/src/flutter/lib/ui/window/platform_configuration.cc`` 与 ``engine/src/flutter/lib/ui/window/viewport_metrics.h``
   * **Framework 对应源码**：``flutter-3.32.0/packages/flutter/lib/src/services/binding.dart``、``widgets/binding.dart`` 与 ``dart:ui/platform_dispatcher.dart``
   * **核心使命**：跨越 Dart 语言边界向下彻底穿透至 C++ 引擎的系统调用门，深度解构 ``PlatformDispatcher`` 单例作为 C++ 引擎与 Dart 框架唯一门户的物理机制、现代 Multi-View 多视口（``FlutterView``）拓扑与物理度量分发、``onBeginFrame`` 与 ``onDrawFrame`` 双时钟帧触发信号管线、以及系统级环境配置（窗口缩放、深浅色模式、多语言与无障碍）的底层广播链。

----------------------------------------------------------------------------------------

第一幕：`PlatformDispatcher` 物理单例——C++ 引擎与 Dart 框架的唯一通信门户
-------------------------------------------------------------------------

在早期版本的 Flutter 中，所有系统级事件和窗口度量都绑定在一个全局单例 ``ui.window`` 上。这种设计将“操作系统全局服务”与“单一物理屏幕”死死捆绑在一起，无法支撑桌面端多窗口、折叠屏双屏以及车载多联屏场景。

现代 Flutter 体系将底层门户彻底重构为 **``PlatformDispatcher``（平台分发器单例）**：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ 操作系统原生层 (macOS AppKit / Android WindowManager / Windows Win32)    │
   └────────────────────────────────────┬─────────────────────────────────────┘
                                        │ (原生输入、VSync、窗口物理尺寸变动)
   ┌────────────────────────────────────▼─────────────────────────────────────┐
   │ Flutter C++ 核心引擎 (platform_configuration.cc)                          │
   │ • 维护 ViewportMetrics、Locale、PlatformBrightness 等底层结构体          │
   │ • 通过 Dart C++ API 直接向 Root Isolate 触发闭包回调 (DartInvokeField)    │
   └────────────────────────────────────┬─────────────────────────────────────┘
                                        │ (零中间件内存直通)
   ┌────────────────────────────────────▼─────────────────────────────────────┐
   │ Dart Framework: ui.PlatformDispatcher.instance (唯一的底层平台门面)       │
   │ ├── 1. 多视口管理 (views / implicitView)                                 │
   │ ├── 2. 帧调度回调 (onBeginFrame / onDrawFrame)                           │
   │ ├── 3. 指针事件派发 (onPointerDataPacket)                                 │
   │ └── 4. 平台环境广播 (onMetricsChanged / onLocaleChanged / onBrightness)   │
   └──────────────────────────────────────────────────────────────────────────┘

1. C++ 引擎向 Dart 回调的微观执行时序
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在 C++ 引擎源码 ``platform_configuration.cc`` 中，当操作系统产生环境变动或硬件时钟脉冲时：
* 引擎在 C++ 层面打包二进制数据结构；
* 通过 Dart 虚拟机的 C++ API（``tonic::DartInvokeField``）直接在 Root Isolate 内部调用注册在 ``PlatformDispatcher`` 上的静态闭包；
* **物理收益**：该调用在同一线程内部以直接函数指针跳转的方式瞬间完成，中间没有任何额外的 JSON 序列化或异步线程投递开销。

----------------------------------------------------------------------------------------

第二幕：多视口（Multi-View）架构与 `FlutterView` 度量分发拓扑
--------------------------------------------------------------

现代桌面端与多屏设备允许同一个应用拥有多个独立的物理显示窗口。``PlatformDispatcher`` 将全局平台状态与具体的视口渲染解耦为一对多的拓扑结构：

.. code-block:: text

   PlatformDispatcher (全局平台中枢)
        │
        ├── views: Map<int, FlutterView> (活动视口注册表)
        │     ├── View ID 0 (主窗口 FlutterView) ────► 关联主物理窗口与主 RenderView
        │     ├── View ID 1 (副屏幕 FlutterView) ────► 关联副屏幕与独立 RenderView
        │     └── View ID 2 (弹窗外挂窗口)       ────► 关联独立操作系统窗口
        │
        └── implicitView: FlutterView? (向后兼容的默认隐式视口)

1. 物理视口度量（ViewConfiguration / ViewportMetrics）的下发
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
每个 ``FlutterView`` 独立持有一组精准的物理度量数据：
* **``physicalSize`` 与 ``devicePixelRatio``**：窗口的物理像素尺寸与设备像素比；
* **``viewInsets``（系统遮挡区）**：软键盘弹出时占用的物理像素区域；
* **``viewPadding``（硬件避让区）**：手机刘海屏、底部手势横条或圆角物理切口的安全边距；
* **``systemGestureInsets``（手势边缘拦截区）**：操作系统保留的侧滑返回手势边缘范围。
当用户在 Mac 上拖拽调整某一个窗口的大小时，C++ 引擎仅触发该 ``viewId`` 对应的度量更新，驱动对应的 ``View`` 树进行局部重排，其余窗口完全不受影响。

----------------------------------------------------------------------------------------

第三幕：双时钟帧触发信号管线（`onBeginFrame` 与 `onDrawFrame`）
----------------------------------------------------------------

这是整个 Flutter 渲染流水线最核心的**双阶段时钟驱动机制**。当显示器发出 VSync 垂直同步脉冲时，C++ 引擎依次向 Dart 触发两个严格隔离的阶段回调：

.. code-block:: text

   硬件 VSync 脉冲信号到达 ───────────────────────────────────────────────────────►
        │
        ▼ 【阶段一: 瞬态动画时钟 (Transient Phase)】
   1. 触发 PlatformDispatcher.onBeginFrame(Duration timeStamp)
        │ • 驱动所有处于活动状态的 Ticker 与 AnimationController 步进
        │ • 计算所有补间动画的当前数值 (如平移偏移量、透明度、缩放比)
        │ • 这一阶段只在内存中计算动画数值，【严禁执行任何布局或排版】
        │
        ▼ 【阶段二: 持久渲染流水线 (Persistent Phase)】
   2. 紧接着触发 PlatformDispatcher.onDrawFrame()
        │ • 唤醒 PipelineOwner 启动完整渲染五大阶段:
        │   flushLayout (测量布局) ──► flushCompositingBits ──► flushPaint (绘制)
        │ • 生成最终的 LayerTree 场景图并提交给 C++ 光栅化引擎上屏
        │
        ▼
   一帧渲染结束，UI 线程进入休眠，等待下一个 VSync 信号

1. 为什么必须严格拆分为两个阶段？
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* 若将动画计算与布局绘制混在一个函数中：如果某个动画在计算过程中又动态添加了新的子动画，会导致布局测量过程中出现脏数据竞争（Re-entrant Modification）；
* **双阶段流水线** 确保了：**先在内存中将所有动画状态计算至绝对稳定点（`onBeginFrame`），随后统一执行一次性的布局测量与绘制（`onDrawFrame`）**，彻底杜绝了帧内重复排版与卡顿。

----------------------------------------------------------------------------------------

第四幕：系统级环境变动监听与事件广播链
--------------------------------------

``PlatformDispatcher`` 作为底层事件中枢，向外暴露了一组纯响应式的环境变动回调通道：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ 系统环境变动 ──► C++ Engine ──► PlatformDispatcher ──► Framework 广播链  │
   ├────────────────────────────────┬─────────────────────────────────────────┤
   │ onMetricsChanged               │ 窗口缩放/旋转 ──► 触发 didChangeMetrics ──► 更新 MediaQuery │
   │ onPlatformBrightnessChanged    │ 切换暗黑模式 ──► 触发 didChangePlatformBrightness ──► 换肤   │
   │ onLocaleChanged                │ 切换系统语言 ──► 触发 didChangeLocales ──► 切换语言包       │
   │ onAccessibilityFeaturesChanged │ 开启无障碍/粗体 ──► 触发 didChangeAccessibilityFeatures    │
   └────────────────────────────────┴─────────────────────────────────────────┘

在 `WidgetsBinding` 初始化时，框架层通过注册这些回调，将原生操作系统的底层变动无缝转化为 Dart 的响应式数据流，驱动上层的 `MaterialApp` 与所有子组件实现毫秒级的响应式更新。

----------------------------------------------------------------------------------------

小结与给下一个对话的施工建议 (Summary & Next Step Advisory)
------------------------------------------------------------

* **本章核心产出**：
  至此，**模块 08 第 2 节：``08_engine_frame_pipeline/02_platform_dispatcher_pipeline.rst`` 已全量落盘完工**！系统拆解了 PlatformDispatcher 物理单例架构、Multi-View 多视口拓扑与物理度量分发、onBeginFrame/onDrawFrame 双时钟帧调度管线、以及系统环境变动广播链。
* **给下一个周期的施工建议**：
  下一个周期将严格聚焦 **模块 08 第 3 节：``08_engine_frame_pipeline/03_widgets_flutter_binding_mixins.rst``**。
  我们将深入 ``flutter-3.32.0/packages/flutter/lib/src/widgets/binding.dart``，系统剖析 ``WidgetsFlutterBinding`` 七大底层 Mixin（GestureBinding $	o$ ServicesBinding $	o$ SchedulerBinding $	o$ PaintingBinding $	o$ SemanticsBinding $	o$ RendererBinding $	o$ WidgetsBinding）的**继承拓扑结构、初始化调用链执行时序、以及各 Mixin 之间的物理依赖矩阵**。
