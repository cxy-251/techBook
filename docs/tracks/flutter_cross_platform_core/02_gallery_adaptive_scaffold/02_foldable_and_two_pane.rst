========================================================================================
第 2 节：折叠屏物理铰链 (Hinge) 几何边界检测与 TwoPane 双视口避让架构
========================================================================================

.. note::
   **源码坐标与本节核心使命**
   * **核心源文件**：``cxyFork-gallery/lib/layout/adaptive.dart`` 与 ``cxyFork-gallery/lib/pages/splash.dart``
   * **底层依赖源码**：``flutter-3.32.0/packages/flutter/lib/src/widgets/media_query.dart`` 与 ``packages/flutter/lib/src/widgets/display_feature_sub_screen.dart``
   * **核心使命**：以多形态折叠硬件与物理人机工效为基准，深度解构双屏设备（如 Surface Duo、Galaxy Fold）硬件折缝在操作系统底层的特征抽象（``DisplayFeature``）、垂直铰链长宽比数学判据（``aspectRatio < 1``）、以及 ``TwoPane`` 左右双视口排版避让与独立路由分流架构。

----------------------------------------------------------------------------------------

第一幕：折叠屏物理硬件形态与显示特征（`DisplayFeature`）底层感知
------------------------------------------------------------------

在现代移动设备硬件形态演进中，折叠设备主要分为两大物理流派：
1. **柔性屏折叠（Flexible Foldable）**：单块柔性 OLED 屏幕在中间弯折，展开后中间存在微小的物理折痕与触控形变区；
2. **双屏铰链折叠（Dual-Screen Hinge）**：由两块独立的物理玻璃屏幕通过机械铰链（Hinge）连接，屏幕中间存在一道宽度约为 10~30 逻辑像素的**物理黑边盲区（Seam / Dead Zone）**。

1. 物理遮挡危机（The Seam Clipping Bug）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
若应用将折叠设备简单当成一台“大号平板”来排版，使用常规的 ``Row`` 或单列 ``ListView`` 居中排布，屏幕正中间的文字、核心按钮或表单输入框会被物理铰链直接从中间“硬生生裁切吞噬”，导致灾难性的交互不可用。

2. 操作系统硬件抽象与 `DisplayFeature` 管道
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
为了让上层框架感知物理遮挡，操作系统（如 Android Jetpack WindowManager）向 Flutter 底层 C++ 引擎上报屏幕显示特征，并封装为 ``ui.DisplayFeature`` 结构体：

.. code-block:: text

   [底层硬件传感器 / WindowManager]
                  │
                  ▼ 上报物理遮挡边界
   FlutterView.displayFeatures
                  │
                  ▼ 封装至媒体查询
   MediaQueryData.displayFeatures
                  │
                  ├── bounds: Rect (物理遮挡矩形区域的左上角与右下角逻辑坐标)
                  ├── type: DisplayFeatureType.hinge / fold (硬件铰链或柔性折痕)
                  └── state: DisplayFeatureState.postureFlat (展开角度: 平铺/半折叠悬停)

----------------------------------------------------------------------------------------

第二幕：垂直铰链（Vertical Hinge）几何判决数学推导
--------------------------------------------------

在 ``lib/layout/adaptive.dart`` 中，系统通过极简且数学严密的算法检测是否存在有效的垂直折叠铰链：

.. code-block:: text

   bool isDisplayFoldable(BuildContext context) {
     final hinge = MediaQuery.of(context).hinge;
     if (hinge == null) {
       return false;
     } else {
       // Vertical
       return hinge.bounds.size.aspectRatio < 1;
     }
   }

1. 铰链纵横比（Aspect Ratio）数学推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
屏幕铰链的包围盒矩形尺寸为 $	ext{Size}(W_{	ext{hinge}}, H_{	ext{hinge}})$，其纵横比定义为：

$$	ext{aspectRatio} = \frac{W_{	ext{hinge}}}{H_{	ext{hinge}}}$$

* **垂直折叠铰链（Vertical Hinge，左右分屏）**：
  * 铰链横向宽度极窄（$W_{	ext{hinge}} \approx 20	ext{px}$），纵向高度贯穿整个屏幕（$H_{	ext{hinge}} \approx 800	ext{px}$）；
  * 计算得出：
    $$	ext{aspectRatio} = \frac{20}{800} = 0.025 \ll 1.0$$
  * 判定为**有效的左右双屏形态**，激活双视口分流；
* **水平折叠铰链（Horizontal Hinge，上下折叠/翻盖机）**：
  * 铰链横向宽度占满屏幕（$W_{	ext{hinge}} \approx 400	ext{px}$），纵向高度极小（$H_{	ext{hinge}} \approx 20	ext{px}$）；
  * 计算得出：
    $$	ext{aspectRatio} = \frac{400}{20} = 20.0 \gg 1.0$$
  * Gallery 在当前业务场景下忽略上下分屏，保持单视口纵向滑动。

----------------------------------------------------------------------------------------

第三幕：`TwoPane` 双视口布局引擎架构与视图解耦
----------------------------------------------

当 ``isDisplayFoldable`` 返回 ``true`` 时，Gallery 在顶层脚手架（如 ``SplashPage`` 与主页）中立即重构视图树，挂载微软开源的 ``TwoPane`` 响应式双视口容器：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ TwoPane 双视口容器 (完全避开中间物理盲区)                                  │
   ├────────────────────────────┬──────────────┬──────────────────────────────┤
   │ 1. StartPane (左主视口)     │ 2. 物理铰链  │ 3. EndPane (右副视口)        │
   │    • 独立安全盒约束         │    Hinge     │    • 独立安全盒约束          │
   │    • 承载: 导航树 / 案例索引 │  (物理黑边)  │    • 承载: 案例详情 / 演示画板 │
   │    • 宽度: 0 ~ X_hinge_left│  不渲染内容  │    • 宽度: X_hinge_right ~ W │
   └────────────────────────────┴──────────────┴──────────────────────────────┘

1. 安全约束裁剪与物理隔离
~~~~~~~~~~~~~~~~~~~~~~~~~
* ``TwoPane`` 内部通过 ``MediaQuery.removeDisplayFeatures(subScreen)`` 将左半屏与右半屏分别转化为两个**互不重叠的独立安全渲染视口**；
* 传递给 ``startPane`` 的最大宽度被严格锁死在铰链左边缘（``constraints.maxWidth = hinge.left``）；
* 传递给 ``endPane`` 的起始坐标被严格偏移至铰链右边缘（``Offset(hinge.right, 0)``）；
* 两个子面板在物理上永远不会有任何像素绘制在铰链盲区内，从几何源头上根除了“文字被铰链腰斩”的视觉 Bug。

2. `SplashPage` 在双屏形态下的动画拓扑演变
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在 ``lib/pages/splash.dart`` 源码中，启动动画在单屏与折叠双屏下呈现完全不同的架构分支：
* **单屏形态**：使用 ``Stack`` 层叠布局，前层主内容通过 ``PositionedTransition`` 在垂直方向上下滑动遮盖背景；
* **折叠双屏形态**：直接返回 ``TwoPane``：
  * ``startPane`` 渲染主页内容；
  * ``endPane`` 独立渲染 ``_SplashBackLayer`` 动画背景，并绑定独立的手势监听器，点击右侧副屏可自由收起或展开启动动画，赋予双屏设备极致的生产力体验。

----------------------------------------------------------------------------------------

小结与给下一个对话的施工建议 (Summary & Next Step Advisory)
------------------------------------------------------------

* **本章核心产出**：
  至此，**模块 02 第 2 节：``02_gallery_adaptive_scaffold/02_foldable_and_two_pane.rst`` 已全量落盘完工**！系统拆解了折叠设备物理盲区危机、``DisplayFeature`` 硬件管道、铰链纵横比数学判据（$	ext{aspectRatio} < 1$）、以及 ``TwoPane`` 双视口安全隔离架构。
* **给下一个周期的施工建议**：
  下一个周期将严格聚焦 **模块 02 第 3 节：``02_gallery_adaptive_scaffold/03_desktop_mouse_and_focus.rst``**。
  我们将深入 ``cxyFork-gallery/lib/pages/home.dart`` 与 ``backdrop.dart`` 源码，系统剖析桌面端鼠标悬停光标样式切换（``MouseRegion``）、桌面轮播翻页按钮（``_DesktopPageButton``）、键盘快捷键监听（``KeyboardListener`` 拦截 ``Escape`` 键）、以及 ``FocusScope`` 焦点隔离树。
