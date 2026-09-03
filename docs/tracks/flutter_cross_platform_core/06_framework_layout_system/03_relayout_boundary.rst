========================================================================================
第 3 节：Relayout Boundary (重新布局边界) 性能隔离机制、四大判定法则与深度排序
========================================================================================

.. note::
   **源码坐标与本节核心使命**
   * **核心源文件**：``flutter-3.32.0/packages/flutter/lib/src/rendering/object.dart`` 与 ``packages/flutter/lib/src/rendering/box.dart``
   * **底层依赖源码**：``packages/flutter/lib/src/rendering/pipeline_owner.dart`` 与 ``packages/flutter/lib/src/rendering/view.dart``
   * **核心使命**：以大型复杂 UI 树的局部重排性能优化为基准，深度解构 Flutter 布局架构的“定海神针”——**重新布局边界（Relayout Boundary）**。系统推导渲染对象成为边界节点的**四大充分条件**（``!parentUsesSize``、``constraints.isTight``、``constraints == parentConstraints``、``sizedByParent``）、``markNeedsLayout()`` 脏标记向上冒泡的物理截断机制、``PipelineOwner.flushLayout()`` 基于树深度的拓扑排序执行流、以及 ``sizedByParent`` 与 ``performResize()`` 的两阶段解耦架构。

----------------------------------------------------------------------------------------

第一幕：为什么无边界的渲染树是 $O(N)$ 性能灾难？
-------------------------------------------------

在真实的商业级应用中，UI 渲染树往往包含数千甚至数万个 ``RenderObject`` 节点。设想一个深层叶子节点（如实时跳动的时间文本或呼吸动画组件）每秒变化 60 次：

1. **朴素重排的雪崩效应（Layout Cascading）**：
   * 若每次叶子节点尺寸微变，都盲目通知父节点重新测量；父节点又通知祖父节点，脏标记（``_needsLayout = true``）一路向上蔓延至根节点 ``RenderView``；
   * 导致每一帧都必须自顶向下重新遍历整棵树的每一个节点，单帧布局耗时暴增至数百毫秒，发生毁灭性的掉帧。
2. **重新布局边界（Relayout Boundary）的物理本质**：
   * 它是渲染树上设立的**“几何防火墙”**；
   * 边界节点向外承诺：“无论我内部的子孙节点如何增删变动，我向外部暴露的物理尺寸绝对不会发生变化”；
   * 从而将布局重算的传播范围死死锁死在局部子树内部，使单帧排版开销从 $O(N_{	ext{全树}})$ 陡降至 $O(N_{	ext{局部}} \approx 1)$。

----------------------------------------------------------------------------------------

第二幕：重新布局边界（Relayout Boundary）四大判定准则的数学推导
----------------------------------------------------------------

在 ``packages/flutter/lib/src/rendering/object.dart`` 的 ``RenderObject.layout()`` 方法中，框架通过以下布尔方程动态判定当前节点是否成为独立的重排边界：

$$	ext{isRelayoutBoundary} = 
eg	ext{parentUsesSize} \lor 	ext{constraints.isTight} \lor (	ext{constraints} == 	ext{parentConstraints}) \lor 	ext{sizedByParent}$$

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ Relayout Boundary 四大物理判定准则                                       │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 1. !parentUsesSize (父节点不消费子节点尺寸):                              │
   │    • 父节点在调用 child.layout(..., parentUsesSize: false) 时显式声明     │
   │    • 父节点的尺寸计算完全独立于子节点 (如 Stack 的非 Positioned 子项)     │
   │                                                                          │
   │ 2. constraints.isTight (输入约束为严格紧约束):                           │
   │    • minWidth == maxWidth 且 minHeight == maxHeight                      │
   │    • 宽高已被父级彻底锁死 (如 SizedBox(width: 100, height: 100))         │
   │                                                                          │
   │ 3. constraints == parentConstraints (子节点约束与父节点所受约束完全相同):│
   │    • 子节点透传了父级的全部约束，子节点尺寸即代表父节点自身尺寸          │
   │                                                                          │
   │ 4. sizedByParent == true (节点尺寸完全由父级输入约束唯一决断):            │
   │    • 节点自身通过 performResize() 决断尺寸，与下层 children 彻底无关     │
   └──────────────────────────────────────────────────────────────────────────┘

1. 准则一：`!parentUsesSize`（父级解耦）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* 父节点在排版子节点时传入 ``parentUsesSize: false``，向框架立下契约：“我不会在自身 ``performLayout()`` 中读取 ``child.size``”；
* 子节点的尺寸无论如何突变，父节点都无需重新计算自身位置，脏标记冒泡在此**物理终止**。

2. 准则二：`constraints.isTight`（严格紧约束）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* 当父级施加严格紧约束（如屏幕视口强制赋予全屏尺寸），子节点被迫采用固定的宽高；
* 子节点内部即便更换了文字或图标，其向外暴露的边界矩形恒定不变，天然成为重排边界。

3. 准则四：`sizedByParent`（两阶段解耦契约）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* 若渲染对象将 ``sizedByParent`` 声明为 ``true``，该节点宣告：“我的宽高纯粹是输入约束的数学函数，与我的子节点长什么样完全无关”；
* 框架将其直接确立为重排边界。

----------------------------------------------------------------------------------------

第三幕：`markNeedsLayout` 向上冒泡的物理截断与 `PipelineOwner` 深度排序
-----------------------------------------------------------------------

当渲染树中的某个节点发生变化调用 ``markNeedsLayout()`` 时，微观执行流如下：

.. code-block:: text

   [叶子节点调用 markNeedsLayout()]
                 │
                 ▼
   1. 将自身的 _needsLayout 置为 true
                 │
                 ▼ 检查自身是否为重排边界 (this == _relayoutBoundary)
   2. 若非边界 ──► 沿着 parent 指针向上攀爬，一路将祖先节点的 _needsLayout 均置为 true
                 │
                 ▼ 撞击到最近的重排边界节点 BoundaryNode
   3. 冒泡物理终止！绝不向 BoundaryNode.parent 继续蔓延
                 │
                 ▼
   4. 将该 BoundaryNode 注册进全局管线宿主:
      owner._nodesNeedingLayout.add(BoundaryNode)

1. `PipelineOwner.flushLayout()` 的深度拓扑排序（Depth Sorting）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在帧渲染阶段，``PipelineOwner`` 遍历所有收集到的脏边界节点列表 ``_nodesNeedingLayout``：

* **深度优先排序原则**：列表按照节点在树中的深度（``depth``）**从小到大（由根向叶）严格升序排列**；
* **单帧无重复排版保证**：
  * 浅层节点（Depth 小）先被调用 ``_layoutWithoutResize()``；
  * 在浅层节点自顶向下排版的过程中，会自动遍历并顺带完成其深层脏子节点的排版；
  * 当遍历到列表中深层的子节点时，发现其 ``_needsLayout`` 已在刚才被父级顺带清除为 ``false``，直接跳过；
  * 确保渲染树上每一个节点**在单帧之内有且仅被排版一次**，杜绝振荡重排。

----------------------------------------------------------------------------------------

第四幕：`sizedByParent` 与 `performResize()` 两阶段流水线
----------------------------------------------------------

对于声明了 ``sizedByParent = true`` 的渲染对象，框架将其生命周期拆分为独立的两个物理阶段：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ sizedByParent 两阶段执行流水线                                            │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 阶段 1: performResize() (仅在输入约束 constraints 发生变动时调用一次)     │
   │   • 纯基于 constraints 计算 this.size (例如根据 aspectRatio 算高)        │
   │                                                                          │
   │ 阶段 2: performLayout() (仅负责测量与布局子节点)                         │
   │   • 严禁在 performLayout() 中修改 this.size                              │
   │   • 仅对 children 调用 child.layout() 并摆放 parentData.offset            │
   └──────────────────────────────────────────────────────────────────────────┘

* **性能极致优化**：当子节点发生重绘或脏标记时，父级只需重新执行轻量的“阶段 2（子节点摆放）”，完全跳过自身尺寸重算的“阶段 1”，将布局开销压缩至微秒级。

----------------------------------------------------------------------------------------

小结与给下一个对话的施工建议 (Summary & Next Step Advisory)
------------------------------------------------------------

* **本章核心产出**：
  至此，**模块 06 第 3 节：``06_framework_layout_system/03_relayout_boundary.rst`` 已全量落盘完工**！系统拆解了 Relayout Boundary 性能隔离机制、四大充分判定法则的数学证明、markNeedsLayout 冒泡截断、PipelineOwner 深度排序防重排、以及 sizedByParent 两阶段解耦。
* **给下一个周期的施工建议**：
  下一个周期将严格聚焦 **模块 06 第 4 节：``06_framework_layout_system/04_sliver_scroll_viewport.rst``**。
  我们将深入 ``flutter-3.32.0/packages/flutter/lib/src/rendering/sliver.dart`` 与 ``viewport.dart`` 源码，系统剖析 Flutter 滚动视口核心——**Sliver 协议与 ``SliverConstraints``（``scrollOffset``、``overlap``、``remainingPaintExtent``）、``SliverGeometry`` 几何流输出、Viewport 视口懒加载裁剪、以及滚动阻尼物理模拟算法**。
