========================================================================================
第 2 节：RenderBox.performLayout 测量排版执行流、干运行预测与 ParentData 坐标系统
========================================================================================

.. note::
   **源码坐标与本节核心使命**
   * **核心源文件**：``flutter-3.32.0/packages/flutter/lib/src/rendering/box.dart`` 与 ``packages/flutter/lib/src/rendering/object.dart``
   * **底层依赖源码**：``packages/flutter/lib/src/rendering/flex.dart`` 与 ``packages/flutter/lib/src/rendering/shifted_box.dart``
   * **核心使命**：以底层渲染对象的二维笛卡尔几何空间计算为基准，深度解构 ``RenderBox.performLayout()`` 测量与排版执行流水线、干运行预测（``computeDryLayout``）的无副作用尺寸推导、四大固有尺寸（``Intrinsic Dimensions``）反向逆推算法、以及 ``ParentData`` 数据载体与 ``parentData.offset`` 二维物理坐标落盘机制。

----------------------------------------------------------------------------------------

第一幕：`RenderBox.performLayout` 核心执行流水线与状态契约
----------------------------------------------------------

在 Flutter 渲染树中，``RenderBox`` 是所有二维笛卡尔坐标系渲染对象的抽象基类。当一个节点被标记为脏（``_needsLayout = true``）并在帧渲染阶段被激活时，引擎调用其 ``performLayout()`` 方法。

该方法必须严格履行三大**物理状态契约（State Contracts）**：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ RenderBox.performLayout() 执行时序与状态契约                              │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 1. 约束消费与子节点测量 (Child Layout Negotiation):                      │
   │    • 根据自身的 this.constraints 派生出子节点的 childConstraints           │
   │    • 调用 child.layout(childConstraints, parentUsesSize: true/false)      │
   │                                                                          │
   │ 2. 自身几何尺寸确立 (Self Size Assignment):                              │
   │    • 计算自身宽高，必须满足 this.size = constraints.constrain(computedSize)│
   │    • 严禁在 performLayout 结束后 size 仍为 null 或超出 constraints 边界   │
   │                                                                          │
   │ 3. 子节点物理位置裁决 (Child Positioning via ParentData):                 │
   │    • 读取子节点上报的 child.size                                         │
   │    • 计算对齐偏移 Offset(dx, dy)，写入 (child.parentData as BoxParentData)│
   │      的 .offset 属性中                                                   │
   └──────────────────────────────────────────────────────────────────────────┘

1. 尺寸赋值的数学约束校验
~~~~~~~~~~~~~~~~~~~~~~~~~
在 ``performLayout()`` 内部，``this.size`` 的确立必须经过 ``constraints.constrain()`` 的闭区间几何裁剪：
$$	ext{this.size} = 	ext{Size}(\operatorname{clamp}(W, 	ext{minW}, 	ext{maxW}), \operatorname{clamp}(H, 	ext{minH}, 	ext{maxH}))$$
若渲染对象计算出的尺寸违背了父级的输入约束，框架层将在 ``debugAssertDoesMeetConstraints()`` 中直接触发硬件断言，终止本帧渲染，保证布局系统的数学确定性。

2. 布局脏标记的原子清除
~~~~~~~~~~~~~~~~~~~~~~~
当 ``performLayout()`` 完成自身及所有子节点的测量后，框架自动将当前节点的 ``_needsLayout`` 私有布尔标志位重置为 ``false``，宣布本节点在当前帧中已恢复几何稳定态。

----------------------------------------------------------------------------------------

第二幕：干运行预测（`computeDryLayout`）与无副作用尺寸推导
----------------------------------------------------------

在复杂的复合排版（如弹性布局 ``RenderFlex`` 计算基准线对齐、或表格网格动态分配列宽）中，父节点经常需要预先探知：“如果在某组假想约束下，子节点会呈现多大尺寸？”，但此时父节点**绝不能触发真正的子节点排版流程**（否则会污染子节点的 ``parentData`` 并错误触发重绘）。

为此，Flutter 3.x 引入了**干运行预测机制（Dry Layout Protocol）**：

.. code-block:: text

   [父节点发起尺寸预判: child.getDryLayout(testConstraints)]
                             │
                             ▼
   1. 检查子节点缓存 (如果 testConstraints == child.constraints 且 !child._needsLayout)
      • 命中缓存 ──► 直接返回 child.size (0 纳秒开销)
                             │
                             ▼ 未命中缓存
   2. 调用子节点的 computeDryLayout(testConstraints)
      • 纯数学几何推导: 严格禁止修改 this.size、禁止写入 parentData.offset
      • 递归调用孙子节点的 getDryLayout(grandChildConstraints)
                             │
                             ▼
   3. 输出预测尺寸 Size(dryWidth, dryHeight) 供父级决策，整棵子树状态完全零污染！

* **纯函数式数学原则**：``computeDryLayout`` 必须是一个无副作用的纯函数（Pure Function），它仅根据传入的 ``BoxConstraints`` 计算并返回一个 ``Size``，保证多轮预判计算的安全幂等性。

----------------------------------------------------------------------------------------

第三幕：固有尺寸体系（Intrinsic Dimensions）的反向逆推算法
----------------------------------------------------------

在某些高级 UI 场景中（如将一组按钮的宽度强制统一为“其中最长文字按钮的自然宽度”），父节点需要从子节点的内容反向推导其几何极值。

``RenderBox`` 定义了四大**固有尺寸度量接口**：

.. code-block:: text

   Intrinsic Dimensions 四大几何度量体系
        │
        ├── 1. computeMinIntrinsicWidth(height)  ── 最小固有宽度 (文本不发生软换行的极限压缩宽度)
        ├── 2. computeMaxIntrinsicWidth(height)  ── 最大固有宽度 (内容完全展开、不再减小高度时的宽度)
        ├── 3. computeMinIntrinsicHeight(width) ── 最小固有高度 (给定宽度下的最小内容包裹高度)
        └── 4. computeMaxIntrinsicHeight(width) ── 最大固有高度 (给定宽度下的最大自然展开高度)

1. $O(N^2)$ 递归风险与内置几何缓存
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* **计算代价**：固有尺寸的推导是深度优先递归进行的。若在一个深层树中无节制使用 ``IntrinsicWidth`` / ``IntrinsicHeight``，会导致每一层节点都对下层执行多次全树推导，产生 $O(N^2)$ 的时间复杂度瓶颈；
* **内部记忆化缓存**：``RenderBox`` 内部维护了 ``_cachedIntrinsicDimensions`` 映射表，针对相同的入参缓存计算结果，防止单帧内重复推导。

----------------------------------------------------------------------------------------

第四幕：`ParentData` 数据载体与二维笛卡尔坐标落盘机制
------------------------------------------------------

在 Flutter 架构中，有一个极其精妙的设计哲学：**子节点自身绝不存储自己在屏幕上的绝对坐标或相对父级的偏移量！**

子节点只知道自己有多大（``size``），而它在父容器里的相对二维坐标（``Offset``），是由父节点作为元数据附加在子节点身上的——这就是 **``ParentData`` 模式**。

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ ParentData 内存寄生与解耦架构                                            │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ RenderObject (子节点)                                                    │
   │   ├── size = Size(100.0, 50.0) ── 自身尺寸                               │
   │   └── parentData: BoxParentData ── 寄生在子节点身上的父级元数据载体        │
   │         ├── offset = Offset(24.0, 120.0) ── 父节点写入的相对偏移坐标     │
   │         └── flex / fit / keepAlive ... ── 扩展专用布局参数               │
   └──────────────────────────────────────────────────────────────────────────┘

1. `BoxParentData.offset` 坐标落盘
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当父节点（如 ``RenderFlex``）在 ``performLayout()`` 中完成对所有子节点的排列计算后，直接将计算出的坐标写入子节点的内存中：
$$	ext{final BoxParentData childParentData} = 	ext{child.parentData as BoxParentData};$$
$$	ext{childParentData.offset} = 	ext{Offset}(	ext{currentX}, 	ext{currentY});$$

2. 绘制阶段（`paint`）与局部坐标矩阵平移
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在后续的绘制阶段，父节点遍历子节点，通过其 ``parentData.offset`` 将绘图上下文（``PaintingContext``）的 Canvas 矩阵进行平移：
$$	ext{context.paintChild}(	ext{child}, 	ext{childParentData.offset});$$
底层渲染管线自动将 Canvas 坐标原点移动到 $(	ext{dx}, 	ext{dy})$，子节点在绘制自身时直接以 $(0, 0)$ 为原点绘制，实现了布局定位与自身绘制的绝对物理正交解耦。

----------------------------------------------------------------------------------------

小结与给下一个对话的施工建议 (Summary & Next Step Advisory)
------------------------------------------------------------

* **本章核心产出**：
  至此，**模块 06 第 2 节：``06_framework_layout_system/02_render_box_layout_flow.rst`` 已全量落盘完工**！系统拆解了 RenderBox.performLayout 测量状态契约、computeDryLayout 无副作用干运行预测、四大 Intrinsic 固有尺寸反向推导模型、以及 BoxParentData.offset 二维坐标落盘与 Canvas 平移机制。
* **给下一个周期的施工建议**：
  下一个周期将严格聚焦 **模块 06 第 3 节：``06_framework_layout_system/03_relayout_boundary.rst``**。
  我们将深入 ``flutter-3.32.0/packages/flutter/lib/src/rendering/object.dart`` 源码，系统剖析 Flutter 布局性能的“定海神针”——**Relayout Boundary（重新布局边界）的四大判定法则、脏标记向上冒泡的物理阻断机制、以及如何利用 `sizedByParent` 实现 $O(1)$ 局部极速更新**。
