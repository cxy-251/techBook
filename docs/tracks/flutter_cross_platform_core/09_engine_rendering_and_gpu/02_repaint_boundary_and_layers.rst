========================================================================================
第 2 节：Repaint Boundary 重绘边界、LayerTree 拓扑与保留渲染 (Retained Rendering) 机制
========================================================================================

.. note::
   **源码坐标与本节核心使命**
   * **核心源文件**：``flutter-3.32.0/packages/flutter/lib/src/rendering/layer.dart`` (Layer, ContainerLayer, OffsetLayer, LayerHandle) 与 ``proxy_box.dart`` (RenderRepaintBoundary)
   * **底层依赖源码**：``flutter-3.32.0/packages/flutter/lib/src/rendering/object.dart`` (PaintingContext) 与 ``dart:ui`` (EngineLayer, SceneBuilder.addRetained)
   * **核心使命**：以现代 GPU 增量合成架构与微秒级图层复用算法为基准，深度解构 Flutter 3.32 图层树（LayerTree）的物理拓扑结构——``isRepaintBoundary`` 重绘边界判定法则、``ContainerLayer`` 双向侵入式链表管理、基于 ``LayerHandle`` 引用计数的原生纹理内存安全回收机制、``addRetained`` 图层保留渲染（Retained Rendering）缓存击中原理、以及 ``LeaderLayer`` / ``FollowerLayer`` 跨子树坐标变换矩阵跟随几何学。

----------------------------------------------------------------------------------------

第一幕：重绘边界（`RepaintBoundary`）的判定准则与图层物理切分
--------------------------------------------------------------

在实时图形渲染管线中，光栅化（Rasterization，将矢量指令转化为屏幕像素矩阵）是 CPU 与 GPU 最昂贵的算力开销。若无图层隔离，屏幕上一个 10px 的闪烁光标会导致整个 4K 物理分辨率下的全屏组件被迫全量重绘。

Flutter 通过 **重绘边界（Repaint Boundary）** 实现了像素级的绘制隔离：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ PaintingContext.paintChild 遇到 isRepaintBoundary 时的物理分流           │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 1. 判定 !child.isRepaintBoundary (常规子节点):                            │
   │    • 沿用当前已开启的 PictureLayer 录制器 (ui.PictureRecorder)           │
   │    • 矢量绘制指令 (drawRect, drawText) 连续顺序写入同一个显示列表 (DisplayList)│
   │                                                                          │
   │ 2. 判定 child.isRepaintBoundary == true (重绘边界节点):                   │
   │    • 步骤 A: 立即调用 stopRecordingIfNeeded() 封口当前的 PictureLayer   │
   │    • 步骤 B: 检查子节点 child._needsPaint 脏标记                          │
   │      ├─► 若子节点已脏: 调用 PaintingContext.repaintCompositedChild() 重新录制 │
   │      └─► 若子节点未脏: 直接复用旧 child._layer (零开销图层指针挂载)       │
   │    • 步骤 C: 在图层链表中物理插入独立的 OffsetLayer                       │
   │    • 步骤 D: 重新开启全新的 PictureLayer 接收后续兄弟节点的绘制指令      │
   └──────────────────────────────────────────────────────────────────────────┘

1. `RenderRepaintBoundary` 的内存代价与权衡
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
重绘边界并非免费的银弹：
* **优势**：将子树的绘制与父级完全解耦。父级滚动或变色时，子树直接复用预先录制好的 GPU 纹理；子树动画变动时，重绘范围被死死锁在自身边界内；
* **代价**：每个重绘边界在底层都需要分配一个专有的 ``OffsetLayer``、``ui.EngineLayer`` 以及独立的显存缓冲区。若在长列表的每个小图标上滥用重绘边界，会导致显存占用与图层合成（Compositing）开销急剧飙升。

----------------------------------------------------------------------------------------

第二幕：`ContainerLayer` 双向侵入式链表与图层树拓扑
----------------------------------------------------

不同于 Widget 树和 Element 树，图层树（LayerTree）在内存中采用了极速的**双向侵入式链表（Intrusive Doubly-Linked List）**：

.. code-block:: text

   ContainerLayer (容器节点，如 OffsetLayer, TransformLayer, ClipRRectLayer)
        │
        ├── firstChild ──────────────────────────┐
        │                                        │
        ├── lastChild ─────────────────┐         │
        │                              │         │
        ▼                              ▼         ▼
   ┌─────────────┐ nextSibling  ┌─────────────┐ nextSibling  ┌─────────────┐
   │ Leaf Layer  │ ───────────► │ Container   │ ───────────► │ Leaf Layer  │
   │ (Picture)   │ ◄─────────── │ Layer       │ ◄─────────── │ (Texture)   │
   └─────────────┘ prevSibling  └─────────────┘ prevSibling  └─────────────┘
                                       │
                                拥有自己的子链表...

1. 侵入式链表的硬件物理优势
~~~~~~~~~~~~~~~~~~~~~~~~~~~
* 每个 ``Layer`` 节点内部直接嵌入了 ``_parent``、``_nextSibling`` 与 ``_previousSibling`` 指针；
* 图层插入（``append``）、移除（``remove``）与重排序操作的复杂度严格为 **$O(1)$**，完全不产生动态数组扩容（如 ``List`` 扩容）的内存碎片与垃圾回收（GC）压力。

2. 图层类型职责矩阵
~~~~~~~~~~~~~~~~~~~
* **容器图层（`ContainerLayer`）**：
  * ``OffsetLayer``：在二维平面上平移子图层（重绘边界的基础底板）；
  * ``TransformLayer``：应用 3D 仿射变换矩阵（``Matrix4``）；
  * ``ClipRectLayer`` / ``ClipRRectLayer`` / ``ClipPathLayer``：向 GPU 提交剪裁掩码；
  * ``OpacityLayer``：对整个子图层应用 Alpha 透明度通道合成；
  * ``BackdropFilterLayer``：对底层已合成的背景内容应用模糊/滤镜着色器。
* **叶子图层（Leaf Layers）**：
  * ``PictureLayer``：承载由 Skia / Impeller 录制的矢量绘图显示列表（``ui.Picture``）；
  * ``TextureLayer``：承载硬解码视频流、原生相机或外部 OpenGL 纹理句柄；
  * ``PlatformViewLayer``：承载原生 iOS `UIView` 或 Android `SurfaceView`。

----------------------------------------------------------------------------------------

第三幕：`LayerHandle` 引用计数与保留渲染（Retained Rendering）
--------------------------------------------------------------

在高性能图形引擎中，图层对象不仅存在于 Dart 堆内存中，更深度持有底层 C++ 引擎的 GPU 显存纹理与原生场景指针（``ui.EngineLayer``）。

1. `LayerHandle<T>` 引用计数内存安全模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
为了杜绝由于 Dart 垃圾回收延迟导致的显存泄露，或过早释放导致的野指针崩溃（Use-After-Free），Flutter 3.32 实现了严密的 ``LayerHandle`` 引用计数系统：

.. code-block:: text

   [RenderObject 持有 LayerHandle] ──(赋值新图层)──► Layer._refCount 递增 (+1)
                                                       │
   [RenderObject.dispose() 释放]  ──(置为 null) ──► Layer._refCount 递减 (-1)
                                                       │
                                                       ▼ 当 _refCount == 0
                                                  调用 Layer.dispose()
                                                  立即销毁底层 ui.EngineLayer 显存！

2. 保留渲染（`addRetained`）的微观缓存击中
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当整棵图层树向 C++ 引擎提交时（``ContainerLayer.buildScene()``）：

.. code-block:: text

   [遍历子图层 child]
          │
          ▼ 检查 child._needsAddToScene 布尔位
   ┌──────┴─────────────────────────────────────────────┐
   │                                                    │
   ▼ 条件成立 (!child._needsAddToScene && engineLayer)  ▼ 条件不成立 (图层已脏或初次渲染)
   直接调用 ui.SceneBuilder.addRetained(engineLayer)    调用 child.addToScene(builder)
   【极速击中】：C++ 引擎 100% 复用上一帧 GPU 渲染纹理！ 重新生成新的 EngineLayer 节点
   完全跳过子树中数十个图层的指令打包！                 更新 child._needsAddToScene = false

----------------------------------------------------------------------------------------

第四幕：`LeaderLayer` 与 `FollowerLayer` 跨子树矩阵跟随几何学
--------------------------------------------------------------

在复杂的现代 UI 中，气泡提示（Tooltip）、下拉浮层（Dropdown）或文字选中文本把手通常位于全局的 ``Overlay`` 顶层，而触发它们的目标按钮却深嵌在滚动的列表项子树中。

``LeaderLayer`` 与 ``FollowerLayer`` 解决了跨越不同组件树分支的**零延迟物理空间吸附**：

.. code-block:: text

   [深层子树中的 LeaderLayer] (具有局部坐标变换 Matrix_leader)
                 │
                 ├── 通过全局共享的 LayerLink 物理锚定
                 │
                 ▼
   [顶层 Overlay 中的 FollowerLayer] (具有完全不同的祖先链路 Matrix_follower)
                 │
                 ▼ 空间矩阵闭环求解:
   1. 调用 _pathsToCommonAncestor 向上回溯找到两者最近的公共祖先节点 Ancestor
   2. 提取 forwardTransform  = 祖先到 Leader 的累积变换矩阵
   3. 提取 inverseTransform  = 祖先到 Follower 的累积变换矩阵 (并求逆)
   4. 最终复合变换矩阵:
      Matrix_final = Inverse(inverseTransform) * (forwardTransform * Translate(linkedOffset))
   5. FollowerLayer 的子图层像素在空间中与 Leader 产生绝对刚体级绑定！

----------------------------------------------------------------------------------------

小结与给下一个对话的施工建议 (Summary & Next Step Advisory)
------------------------------------------------------------

* **本章核心产出**：
  至此，**模块 09 第 2 节：``09_engine_rendering_and_gpu/02_repaint_boundary_and_layers.rst`` 已全量落盘完工**！系统拆解了 RepaintBoundary 重绘边界分流判定、ContainerLayer 侵入式双向链表、LayerHandle 显存引用计数安全模型、addRetained 保留渲染缓存击中、以及 Leader/Follower 跨子树逆矩阵跟随几何学。
* **给下一个周期的施工建议**：
  下一个周期将严格聚焦 **模块 09 第 3 节：``09_engine_rendering_and_gpu/03_scene_builder_and_gpu_raster.rst``**。
  我们将深入 ``flutter-3.32.0/engine/src/flutter/shell/common/`` 与 ``impeller/`` 源码，系统剖析 ``ui.SceneBuilder`` 二进制场景打包、Dart FFI 跨边界调用 ``window.render(scene)``、光栅化线程（Raster Thread）调度架构、以及 Impeller / Skia 现代着色器管线向 Vulkan / Metal API 提交 Draw Call 的微观执行流。
