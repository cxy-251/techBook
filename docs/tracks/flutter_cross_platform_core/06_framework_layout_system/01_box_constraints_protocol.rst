========================================================================================
第 1 节：BoxConstraints 盒约束传递法则：向下传递约束，向上报告尺寸
========================================================================================

.. note::
   **源码坐标与本节核心使命**
   * **核心源文件**：``flutter-3.32.0/packages/flutter/lib/src/rendering/box.dart`` 与 ``packages/flutter/lib/src/rendering/constraints.dart``
   * **底层依赖源码**：``packages/flutter/lib/src/rendering/object.dart`` 与 ``packages/flutter/lib/src/rendering/proxy_box.dart``
   * **核心使命**：以二维笛卡尔坐标系几何学与单遍布局流水线（One-Pass Layout Pipeline）为基准，深度解构 Flutter 3.32 框架核心布局基石 ``BoxConstraints`` 的四维极值边界数学模型（$$[minW, maxW] 	imes [minH, maxH]$$）、享誉计算机图形学的“Flutter 布局三定律”（约束向下传递、尺寸向上报告、父级决定位置）、紧约束（Tight）与松约束（Loose）代数拓扑、Dry Layout 无副作用预演布局引擎、以及黄黑斑马线布局溢出（Overflow）的微观物理成因。

----------------------------------------------------------------------------------------

第一幕：盒约束四维几何代数与物理边界公理
----------------------------------------

在 Web 浏览器（DOM / CSS）布局模型中，元素的尺寸往往受到内边距、外边距、浮动、绝对定位与流式盒模型的互相影响，需要经历多次回溯与复杂的重排计算（Reflow）。

Flutter 在底层渲染树（Render Tree）中彻底摒弃了复杂的 CSS 盒模型，将所有的 2D 矩形布局抽象为一个极简、纯粹且严格线性的数学模型——**``BoxConstraints``（盒约束）**。

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ BoxConstraints 四维极值边界代数定义                                       │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 几何定义: 一个由 4 个浮点数构成的不可变二阶闭区间张量                      │
   │    C = [minWidth, maxWidth] × [minHeight, maxHeight]                     │
   │                                                                          │
   │ 物理不变性公理 (Invariant Axioms):                                       │
   │    0.0 <= minWidth <= maxWidth <= infinity                               │
   │    0.0 <= minHeight <= maxHeight <= infinity                             │
   │                                                                          │
   │ 尺寸合规性充要条件:                                                      │
   │    Size(W, H) 满足约束 C <===> (minW <= W <= maxW) ∧ (minH <= H <= maxH) │
   └──────────────────────────────────────────────────────────────────────────┘

1. 五大约束形态的代数分类
~~~~~~~~~~~~~~~~~~~~~~~~~
依据四个极值边界的数值特征，``BoxConstraints`` 在物理上呈现 5 种互斥的约束状态：

* **紧约束（Tight Constraints，唯一尺寸）**：
  $$	ext{minWidth} = 	ext{maxWidth} \quad \land \quad 	ext{minHeight} = 	ext{maxHeight}$$
  * 特征：``isTight == true``。子节点在此约束下**没有任何尺寸自主选择权**，其最终尺寸被父级强行锁死为唯一可能的值（如 ``BoxConstraints.tight(Size(100, 100))``）。
* **松约束（Loose Constraints，自由膨胀）**：
  $$	ext{minWidth} = 0.0 \quad \land \quad 	ext{minHeight} = 0.0$$
  * 特征：子节点可以在 $[0, 	ext{maxWidth}] 	imes [0, 	ext{maxHeight}]$ 范围内任意挑选自身所需的尺寸（如 ``BoxConstraints.loose(Size(300, 200))``）。
* **有界约束（Bounded Constraints）**：
  $$	ext{maxWidth} < \infty \quad \land \quad 	ext{maxHeight} < \infty$$
  * 特征：存在明确的最大边界上限。
* **无界约束（Unbounded Constraints，无穷空间）**：
  $$	ext{maxWidth} = \infty \quad \lor \quad 	ext{maxHeight} = \infty$$
  * 特征：通常出现在可滚动视口（如 ``ListView`` 的主轴方向）或无限弹性空间中。子节点可以向无穷大方向任意延展。
* **扩张约束（Expanding Constraints）**：
  $$	ext{minWidth} = 	ext{maxWidth} = \infty \quad \lor \quad 	ext{minHeight} = 	ext{maxHeight} = \infty$$
  * 特征：指示子节点应当尽可能撑满父级的全部剩余可用空间。

2. 约束投影与钳位代数（`constrain`）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当某个 ``RenderBox`` 依据自身内容计算出一个理论尺寸 $	ext{DesiredSize}(w, h)$ 时，底层必须调用 ``constrain()`` 强制将尺寸投影回父级约束闭区间内：

$$	ext{constrainWidth}(w) = \operatorname{clampDouble}(w, 	ext{minWidth}, 	ext{maxWidth})$$
$$	ext{constrainHeight}(h) = \operatorname{clampDouble}(h, 	ext{minHeight}, 	ext{maxHeight})$$
$$	ext{constrain}(Size(w, h)) = Size(	ext{constrainWidth}(w), 	ext{constrainHeight}(h))$$

----------------------------------------------------------------------------------------

第二幕：Flutter 布局三定律（The Three Laws of Flutter Layout）
--------------------------------------------------------------

Flutter 之所以能够实现 $O(N)$ 时间复杂度的单遍线性布局（One-Pass Layout），全赖于整个渲染管线严格遵循的**三定律**：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ Flutter 布局三定律物理数据流向                                            │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 1. 约束向下传递 (Constraints Go Down):                                    │
   │    父节点调用 child.layout(BoxConstraints, parentUsesSize: ...)           │
   │    • 父级向子级强行施加 BoxConstraints 边界范围                          │
   │                                                                          │
   │ 2. 尺寸向上报告 (Sizes Go Up):                                           │
   │    子节点在 performLayout() 内部确定自身几何 Size                        │
   │    • 子级遵守父级约束并设置自身 size = constraints.constrain(desiredSize) │
   │    • 父级在子级 layout() 结束后通过 child.size 读取子级真实尺寸          │
   │                                                                          │
   │ 3. 父级决定物理坐标 (Parents Set Positions):                              │
   │    父节点依据所有子节点的 Size 计算排版坐标 Offset                       │
   │    • 写入子节点的 child.parentData.offset = Offset(X, Y)                  │
   │    • 子节点完全不知道自身在屏幕上的绝对全局位置！                         │
   └──────────────────────────────────────────────────────────────────────────┘

1. 定律一：约束向下传递的单向不可逆性
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* 没有任何子节点能够自行决定脱离父级的约束。即使子组件写了 ``SizedBox(width: 500, height: 500)``，若父级传递下来的是一个 $100 	imes 100$ 的紧约束，该组件的最终尺寸仍然会被物理锁死为 $100 	imes 100$。
* 若想让子组件尺寸生效，中间必须插入一个能够**放松约束（Loosen）**或**重新对齐（Align/Center）**的代理渲染对象（如 ``UnconstrainedBox`` 或 ``Center``）。

2. 定律二：尺寸向上报告与 `parentUsesSize` 性能开关
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* 当父节点在调用 ``child.layout(constraints, parentUsesSize: true)`` 时，声明了“父节点的尺寸计算依赖子节点的最终尺寸”；
* 若父节点声明 ``parentUsesSize: false``（或传入的是 Tight 紧约束），框架会启动极限性能剪枝：子节点未来发生重新布局时，**更新范围会被严格锁死在子节点自身内部，完全不会触发父节点及上层祖先的重新布局（Relayout Boundary 隔离）**。

3. 定律三：坐标解耦的局部相对坐标系
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* 在 Flutter 渲染树中，每个 ``RenderBox`` 拥有专属的局部笛卡尔坐标系，其左上角恒为 $(0, 0)$；
* 所有的绘制指令（``paint``）与命中测试（``hitTest``）均在局部坐标系中展开；
* 只有当图层合成或向屏幕输出时，框架才会叠加祖先链上的全部 ``parentData.offset`` 矩阵位移，计算出物理屏幕上的全局光栅化坐标。

----------------------------------------------------------------------------------------

第三幕：Dry Layout 预演布局与黄黑斑马线溢出物理学
--------------------------------------------------

在某些复杂的布局场景中（如弹性盒 ``Flex`` 计算主轴分布或多列高度对齐），父节点需要在真正排版前获知子节点在特定约束下的预期尺寸，但**绝不允许产生任何修改内部状态或触发重绘的副作用**。

1. 预演布局机制（`computeDryLayout`）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* **物理契约（Dry Contract）**：``computeDryLayout(constraints)`` 是一个纯函数式试算过程：
  * 它接收一个 ``BoxConstraints``，返回一个理想的 ``Size``；
  * **严禁修改自身或子节点的 `_size` 属性**，严禁改变子节点的 ``parentData.offset``，严禁调用 ``markNeedsLayout()``；
* **缓存加速（`_LayoutCacheStorage`）**：
  * ``RenderBox`` 在内部开辟了专用的计算缓存池，缓存最近一次针对特定约束计算的 Dry Layout 尺寸，防止多重探测引发 $O(N^2)$ 的几何计算膨胀。

2. 黄黑相间斑马线溢出（Overflow）的物理成因
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   [父级有界约束: maxHeight = 300px]
                 │
                 ▼ 子节点纵向累加占用 420px
   ┌────────────────────────────────────────┐ ─── 0px
   │ 子组件 A (Height = 150px)              │
   ├────────────────────────────────────────┤ ─── 150px
   │ 子组件 B (Height = 150px)              │
   ├────────────────────────────────────────┤ ─── 300px (父级物理视口下边界)
   │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │
   │ █ █ █ █ 溢出警告区域 (Δ = 120px) █ █ █ │ ─── 420px (超出的内容无法被容纳)
   │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │
   └────────────────────────────────────────┘

* **物理本质**：
  * 当一个无滑动能力的容器（如 ``Column``）在有界纵向约束 $[0, H_{\max}]$ 下排版时，其所有子节点的尺寸总和 $\sum h_i > H_{\max}$；
  * ``RenderFlex`` 无法改变硬件物理视口边界，其最终向上传递的尺寸被截断为 $H_{\max}$；
  * 在绘制阶段（``paint``），框架检测到累积偏移量超出包围盒边界（$\Delta = \sum h_i - H_{\max} > 0$），在 Debug 模式下调用 ``paintOverflowIndicator`` 在视口边缘叠加绘制倾斜 $45^\circ$ 的黄黑条纹与红色溢出像素警告标签。

----------------------------------------------------------------------------------------

小结与给下一个对话的施工建议 (Summary & Next Step Advisory)
------------------------------------------------------------

* **本章核心产出**：
  至此，**模块 06 第 1 节：``06_framework_layout_system/01_box_constraints_protocol.rst`` 已全量落盘完工**！
  系统解构了 BoxConstraints 盒约束四维极值几何代数、五大约束形态拓扑、Flutter 布局三定律（约束向下传递、尺寸向上报告、父级决定位置）、以及 Dry Layout 预演计算与溢出物理学。
* **给下一个周期的施工建议**：
  下一个周期将严格聚焦 **模块 06 第 2 节：``06_framework_layout_system/02_render_box_layout_flow.rst``**。
  我们将深入 ``flutter-3.32.0/packages/flutter/lib/src/rendering/box.dart`` 源码中的 ``RenderBox`` 核心方法，系统剖析 ``performLayout()`` 测量与定位标准执行流、``sizedByParent`` 尺寸旁路优化、``parentData`` 内存注入机制、以及固有尺寸（Intrinsics）与基线（Baseline）的微观计算方程。
