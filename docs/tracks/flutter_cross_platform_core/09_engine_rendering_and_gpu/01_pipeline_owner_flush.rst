========================================================================================
第 1 节：PipelineOwner 刷新五大阶段：flushLayout、flushPaint 与渲染管线微观调度
========================================================================================

.. note::
   **源码坐标与本节核心使命**
   * **核心源文件**：``flutter-3.32.0/packages/flutter/lib/src/rendering/object.dart`` (PipelineOwner, PaintingContext) 与 ``binding.dart`` (RendererBinding.drawFrame)
   * **底层依赖源码**：``flutter-3.32.0/packages/flutter/lib/src/rendering/layer.dart`` 与 ``dart:ui`` (SceneBuilder, PictureRecorder)
   * **核心使命**：以现代实时图形渲染流水线与微秒级帧调度算法为基准，深度解构 Flutter 3.32 渲染管线的中枢神经——``PipelineOwner`` 在每一物理帧（16.6ms / 8.3ms）内严格执行的五大刷新阶段（``flushLayout`` $	o$ ``flushCompositingBits`` $	o$ ``flushPaint`` $	o$ ``compositeFrame`` $	o$ ``flushSemantics``），解析基于树深度的拓扑排序布局算法（``depth`` 升序）与重绘图层逆向排序机制（``depth`` 降序）、以及从 ``PaintingContext`` 画布记录到 GPU 最终呈现的微观执行流。

----------------------------------------------------------------------------------------

第一幕：每一物理帧的心跳中枢：`RendererBinding.drawFrame` 时序全景
-------------------------------------------------------------------

当硬件显示器发出 VSync 垂直同步脉冲时，底层 C++ 引擎通过 ``PlatformDispatcher.onDrawFrame`` 唤醒 Dart 框架层的 ``SchedulerBinding``。随后控制权移交至 ``RendererBinding.drawFrame()``，开启五大阶段的连续物理冲刷（Pipeline Flush）：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ RendererBinding.drawFrame() 渲染管线五大物理阶段                          │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 阶段 1: pipelineOwner.flushLayout()                                      │
   │         • 处理 _nodesNeedingLayout 队列 (按 depth 升序排序: 父到子)       │
   │         • 触发 RenderObject.layout() ──► performLayout() 计算尺寸与偏移   │
   │                                                                          │
   │ 阶段 2: pipelineOwner.flushCompositingBits()                             │
   │         • 处理 _nodesNeedingCompositingBitsUpdate (按 depth 升序)         │
   │         • 递归向上标记 needsCompositing 位，确定子树是否包含独立光栅图层  │
   │                                                                          │
   │ 阶段 3: pipelineOwner.flushPaint()                                       │
   │         • 处理 _nodesNeedingPaint 队列 (按 depth 降序排序: 深度优先)      │
   │         • 触发 PaintingContext.repaintCompositedChild() 生成绘制显示列表  │
   │                                                                          │
   │ 阶段 4: renderView.compositeFrame()                                      │
   │         • 递归遍历 LayerTree 根节点，调用 SceneBuilder.build()            │
   │         • 通过 window.render(scene) 将二进制场景包提交给 C++ 引擎 GPU 端  │
   │                                                                          │
   │ 阶段 5: pipelineOwner.flushSemantics()                                   │
   │         • 编译辅助功能语义树 (SemanticsTree)，推送到操作系统无障碍通道   │
   └──────────────────────────────────────────────────────────────────────────┘

----------------------------------------------------------------------------------------

第二幕：阶段 1——`flushLayout` 深度升序拓扑排序与边界隔离
--------------------------------------------------------

为什么不能随机遍历脏节点进行布局计算？
* 如果子节点先于父节点完成布局，随后父节点重新执行布局时再次修改了传递给子节点的盒约束（``BoxConstraints``），该子节点就必须**被迫重复执行第二次布局**，导致无谓的计算开销。

1. 深度升序（`depth` 升序）拓扑排序数学证明
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``PipelineOwner`` 在提取所有 ``_nodesNeedingLayout`` 脏节点后，首先执行严格的排序：
$$	ext{dirtyNodes.sort}((a, b) \implies a.	ext{depth} - b.	ext{depth})$$
* **父节点深度永小于子节点**（$	ext{depth}_{	ext{parent}} < 	ext{depth}_{	ext{child}}$）；
* 按升序遍历确保：**父节点必定先于所有子孙节点执行 ``_layoutWithoutResize()``**；
* 当父节点在 ``performLayout()`` 内部主动调用 ``child.layout(constraints)`` 时，已经顺带完成了脏子节点的布局计算并清除了子节点的 ``_needsLayout`` 标记；
* 遍历后续脏节点时，只要检测到 ``!node._needsLayout`` 便可直接跳过，实现了全树 **$O(N)$ 复杂度的单次遍历收敛**。

2. `Relayout Boundary`（重布局边界）截断机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当一个叶子节点调用 ``markNeedsLayout()`` 时，脏标记并不会盲目向上回溯到树根：
* 如果满足以下任一条件，当前节点被直接裁决为 **重布局边界（Relayout Boundary）**：
  1. ``!parentUsesSize``（父节点不依赖子节点的实际尺寸）；
  2. ``sizedByParent == true``（当前节点尺寸完全由父约束决定）；
  3. ``constraints.isTight``（父级传递的约束为死宽高，无任何伸缩空间）；
  4. ``parent == null``（根节点 RenderView）。
* 脏标记在此处被**物理截断**，仅将该边界节点推入 ``_nodesNeedingLayout`` 队列，保护了祖先整棵树免受重排波及。

----------------------------------------------------------------------------------------

第三幕：阶段 2——`flushCompositingBits` 合成位自底向上拓扑修正
--------------------------------------------------------------

在进入绘制阶段之前，每个 ``RenderObject`` 必须明确知晓：“我的所有子孙节点中，是否存在任何一个需要独立 GPU 图层的组件（如视频硬解码、平台原生视图 PlatformView、或者声明了 ``isRepaintBoundary`` 的图层）？”

1. 为什么绘制前必须更新 `needsCompositing`？
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* 如果子树中包含独立图层，父级在执行裁剪（ClipRect）时，**不能简单在当前 Canvas 上调用 ``canvas.clipRect()``**（因为 Canvas 裁切无法穿透隔离的子图层），而必须在 LayerTree 中物理插入一个 ``ClipRectLayer`` 容器图层；
* ``flushCompositingBits()`` 自底向上递归遍历，将子节点的图层需求汇总为父节点的布尔标志位，为下一步的绘制决策提供精准依据。

----------------------------------------------------------------------------------------

第四幕：阶段 3——`flushPaint` 重绘图层逆向排序与 `PaintingContext` 记录
----------------------------------------------------------------------

当进入绘制阶段时，``PipelineOwner`` 的遍历顺序发生惊人反转：

1. 深度降序（`depth` 降序，深层优先）排序
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
$$	ext{dirtyNodes.sort}((a, b) \implies b.	ext{depth} - a.	ext{depth})$$
* **为什么绘制要逆向优先？**
  * 在绘制树中，重绘边界（``RepaintBoundary``）各自持有独立的 ``OffsetLayer``；
  * 如果深层的子重绘边界先执行绘制，它只需将自己的微型图层指令更新；
  * 当顶层重绘边界被触发时，若发现子图层未脏，可以直接通过 ``_compositeChild`` 复用子图层指针（零开销图层挂载），避免重复遍历子树像素。

2. `PaintingContext` 双模态录制机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
每个绘制上下文内部维护着一个 ``ui.PictureRecorder`` 和 ``Canvas``：
* **普通控件**：所有绘制指令（``drawLine``, ``drawRect``, ``drawText``）被连续录制进当前同一个 ``PictureLayer`` 矢量指令列表中；
* **遇到 RepaintBoundary 子节点**：
  * 框架立即调用 ``stopRecordingIfNeeded()`` 封口当前 ``PictureLayer``；
  * 插入子节点的独立 ``OffsetLayer``；
  * 在其后重新开启一个新的 ``PictureLayer`` 接收后续绘制，实现了复杂界面图层的精细切片与增量复用。

----------------------------------------------------------------------------------------

第五幕：阶段 4——`compositeFrame` 场景打包与 GPU 光栅化提交
----------------------------------------------------------

在所有脏节点绘制完毕后，物理内存中已经构建好一棵完整的 **图层树（LayerTree）**：

.. code-block:: text

   [LayerTree 物理拓扑]
   TransformLayer (根变换)
        │
        ├── PictureLayer (背景装饰、导航栏矢量指令)
        └── OffsetLayer (RepaintBoundary 商品列表独立图层)
                 ├── ClipRRectLayer (圆角裁剪)
                 └── PictureLayer (商品卡片图文绘制指令)
                        │
                        ▼ (传递给 ui.SceneBuilder)
   1. 遍历图层树，调用 sceneBuilder.pushTransform() / addPicture()
   2. 调用 ui.Scene scene = sceneBuilder.build() 生成二进制场景包
   3. 调用 window.render(scene) 跨越 FFI 边界提交至 C++ 引擎
   4. C++ 引擎光栅化线程调度 Impeller / Metal 在 GPU 上点亮物理像素！

----------------------------------------------------------------------------------------

小结与给下一个对话的施工建议 (Summary & Next Step Advisory)
------------------------------------------------------------

* **本章核心产出**：
  至此，**模块 09 第 1 节：``09_engine_rendering_and_gpu/01_pipeline_owner_flush.rst`` 已全量落盘完工**！系统拆解了 RendererBinding.drawFrame 五大物理冲刷阶段、flushLayout 深度升序与 Relayout Boundary 边界截断、flushPaint 深度降序逆向图层复用、以及 SceneBuilder 场景打包与 GPU 提交。
* **给下一个周期的施工建议**：
  下一个周期将严格聚焦 **模块 09 第 2 节：``09_engine_rendering_and_gpu/02_repaint_boundary_and_layers.rst``**。
  我们将深入 ``flutter-3.32.0/packages/flutter/lib/src/rendering/layer.dart`` 源码，系统剖析 ``RepaintBoundary`` 重绘边界判定方程、``ContainerLayer`` 与 ``PictureLayer`` 链表拓扑、图层保留渲染（Retained Rendering）缓存击中、以及 ``LayerHandle`` 内存泄漏防御机制。
