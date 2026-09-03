========================================================================================
第 1 节：adaptive.dart 物理断点系统、DPI 逻辑像素映射与大屏分流执行流
========================================================================================

.. note::
   **源码坐标与本节核心使命**
   * **核心源文件**：``cxyFork-gallery/lib/layout/adaptive.dart``
   * **底层依赖源码**：``flutter-3.32.0/packages/flutter/lib/src/widgets/media_query.dart`` 与 ``packages/flutter/lib/src/widgets/binding.dart``
   * **核心使命**：以跨端物理屏幕与人体工程学规范为基准，深度解构 Gallery 如何将物理硬件像素（Physical Pixels）映射为与设备无关的逻辑像素（Logical Pixels）、Material Design 离散物理断点分级树、折叠屏铰链避让判据，以及 ``maxHomeItemWidth = 1400.0`` 超宽屏防拉伸约束算法。

----------------------------------------------------------------------------------------

第一幕：物理像素与逻辑像素的硬件映射几何学
-------------------------------------------

在跨平台开发中，最底层的物理现实是：不同终端设备的屏幕物理分辨率（Physical Resolution）与屏幕物理尺寸（Physical Dimensions）极其割裂：
* 一台 6.1 英寸的 iPhone 屏幕物理像素高达 $1170 	imes 2532$；
* 一台 27 英寸的 4K 桌面显示器物理像素为 $3840 	imes 2160$；
* 若直接以物理像素为单位进行排版，同一个 300 像素宽度的按钮，在手机上会显得极其微小无法点击，而在低分屏上又会庞大到溢出屏幕。

1. 设备像素比（DPI / Device Pixel Ratio）映射公式
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Flutter 框架通过宿主 C++ Embedder 从操作系统底层获取窗口物理尺寸（``FlutterView.physicalSize``）与设备像素比（``FlutterView.devicePixelRatio``）：

$$	ext{Logical Width} = \frac{	ext{Physical Width}}{	ext{devicePixelRatio}}$$
$$	ext{Logical Height} = \frac{	ext{Physical Height}}{	ext{devicePixelRatio}}$$

* **iPhone Retina 屏**：$1170	ext{px} / 3.0 = 390.0	ext{pt}$ 逻辑宽度；
* **4K 桌面显示器（200% 缩放）**：$3840	ext{px} / 2.0 = 1920.0	ext{pt}$ 逻辑宽度；
* 逻辑像素（Logical Pixels）抹平了不同硬件面板的物理密度差异，使 1.0 个逻辑像素在人眼视觉感知上的物理长度基本恒定（约等于 1/96 英寸）。

2. 窗口拖拽缩放的底层事件循环流水线
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当用户在 macOS 或 Windows 桌面上拖拽窗口边缘调整大小时：

.. code-block:: text

   [操作系统窗口缩放事件: NSWindowDidResize / WM_SIZE]
                               │
                               ▼
   1. 原生 Embedder 捕获物理尺寸变更 ──> 回调 PlatformDispatcher.onMetricsChanged
                               │
                               ▼
   2. WidgetsBinding 观察者触发 ──> didChangeMetrics()
                               │
                               ▼
   3. _MediaQueryFromViewState 执行 _updateData()
      └── 重新计算 MediaQueryData.fromView(window)
                               │
                               ▼
   4. 触发 InheritedModel.inheritFrom<MediaQuery>(aspect: _MediaQueryAspect.size)
                               │
                               ▼
   5. 仅将精确订阅了 size 的布局 Element 标记为 Dirty，并在当前帧重排

----------------------------------------------------------------------------------------

第二幕：Gallery 离散断点模型与自适应分级决策树
----------------------------------------------

在 ``lib/layout/adaptive.dart`` 中，系统并没有针对每种机型做硬编码适配，而是基于 Material Design 响应式网格规范，建立了五级离散断点（Adaptive Breakpoints）：

.. code-block:: text

   逻辑宽度 (Logical Width)
   0px ─────────── 360px ─────────── 600px ─────────── 840px ─────────── 1200px ───────────►
      xsmall              small              medium              large              xlarge
   (手表/迷你屏)        (手机竖屏)        (平板/桌面小窗)     (桌面标准屏)        (超宽显示器)
   └───────────────────────┘ └─────────────────────────────────────────────────────┘
         Mobile 移动分支形态                        Desktop 桌面分支形态

1. 核心判定算法：`isDisplayDesktop(context)`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在 ``lib/layout/adaptive.dart`` 中，统领全屏布局分流的唯一布尔开关实现如下：

.. code-block:: text

   bool isDisplayDesktop(BuildContext context) =>
       !isDisplayFoldable(context) &&
       getWindowType(context) >= AdaptiveWindowType.medium;

该判定函数包含了双重物理约束：
1. **宽度门限约束 (`getWindowType >= medium`)**：当前窗口逻辑宽度必须 $\ge 600	ext{px}$；
2. **折叠双屏排除约束 (`!isDisplayFoldable`)**：
   * **物理痛点**：在微软 Surface Duo 或折叠屏手机完全展开时，整屏逻辑宽度虽然可能达到 720px（超过 600px 门限）；
   * **工程策略**：由于屏幕中间存在物理铰链，单个子视口（Pane）的实际可用宽度仅有 360px，根本无法容纳桌面级多列排版；
   * 因此，算法显式排除折叠屏状态，强制让折叠设备进入专属的双视口避让分支。

----------------------------------------------------------------------------------------

第三幕：超宽屏防拉伸与人体工程学约束 (`maxHomeItemWidth = 1400.0`)
-------------------------------------------------------------------

在超宽带鱼屏（21:9）或 4K/8K 桌面显示器上，如果允许主页内容无限制横向铺满（如占满 3840 逻辑像素），会导致严重的**人体工程学视觉灾难**：
* 用户的视线必须频繁进行大角度的颈部转动；
* 图文卡片被严重横向拉伸失真，失去排版节奏。

在 ``adaptive.dart`` 中，顶层定义了全局物理最大宽度常量：

.. code-block:: text

   const maxHomeItemWidth = 1400.0;

居中排版几何数学求解
~~~~~~~~~~~~~~~~~~~~
在主页布局中，系统通过 ``Align``、``Center`` 与 ``ConstrainedBox`` 构筑了双向弹性约束区：

* **有效内容宽度方程**：
  $$	ext{EffectiveWidth} = \min(	ext{ViewportWidth}, 1400.0)$$
* **外侧弹性留白边距（Marginal Gutter）**：
  $$	ext{HorizontalMargin} = \max\left(0.0, \frac{	ext{ViewportWidth} - 1400.0}{2}\right)$$
无论屏幕如何无限拉宽，核心业务卡片永远被收拢在 1400 逻辑像素的人眼最佳视觉夹角内，两侧自动生成对称的优雅留白。

----------------------------------------------------------------------------------------

小结与给下一个对话的施工建议 (Summary & Next Step Advisory)
------------------------------------------------------------

* **本章核心产出**：
  至此，**模块 02 第 1 节：``02_gallery_adaptive_scaffold/01_adaptive_breakpoints.rst`` 已全量落盘完工**！系统拆解了 DPI 逻辑像素映射方程、MediaQuery 窗口缩放流水线、五级离散断点决策树、以及 1400px 超宽屏人体工学约束。
* **给下一个周期的施工建议**：
  下一个周期将严格聚焦 **模块 02 第 2 节：``02_gallery_adaptive_scaffold/02_foldable_and_two_pane.rst``**。
  我们将深入 ``cxyFork-gallery/lib/layout/adaptive.dart`` 与 ``dual_screen`` 依赖源码，系统剖析折叠屏物理铰链（Hinge）几何边界检测（``DisplayFeature``）、长宽比判断（``aspectRatio < 1``）、以及 ``TwoPane`` 左右双视口动态排版避让机制。
