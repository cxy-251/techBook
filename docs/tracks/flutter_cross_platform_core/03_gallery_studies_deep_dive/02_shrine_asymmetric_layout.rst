========================================================================================
第 2 节：Shrine 电商系统：2+1 非对称交错商品流、切角边框与强调缓动抽屉算法
========================================================================================

.. note::
   **源码坐标与本节核心使命**
   * **核心源文件**：``cxyFork-gallery/lib/studies/shrine/supplemental/asymmetric_view.dart``、``cut_corners_border.dart``、``balanced_layout.dart`` 与 ``expanding_bottom_sheet.dart``
   * **底层依赖源码**：``flutter-3.32.0/packages/flutter/lib/src/animation/tween.dart``、``packages/flutter/lib/src/animation/curves.dart`` 与 ``packages/flutter/lib/src/painting/borders.dart``
   * **核心使命**：以现代高端商业设计与物理动力学为基准，深度解构 Shrine 如何打破死板对称网格、构建 2+1 交错非对称商品流数学模型、45 度倒角几何切角边框（``CutCornersBorder``）的路径方程、以及基于分段高阶贝塞尔（Quintic Emphasized Easing）的可展开购物车抽屉状态机。

----------------------------------------------------------------------------------------

第一幕：2+1 非对称交错流（`MobileAsymmetricView`）的离散数学模型
----------------------------------------------------------------

传统移动电商界面普遍采用千篇一律的双列网格（`GridView`），导致商品排列极其呆板，缺乏视觉节奏与品牌调性。Shrine 实现了具备顶级时尚杂志排版质感的**交错非对称视图（Asymmetric View）**：

.. code-block:: text

   列索引 k:        k = 0 (偶数列)            k = 1 (奇数列)            k = 2 (偶数列)
   布局形态:    [ 2-Product Column ]      [ 1-Product Column ]      [ 2-Product Column ]
                ┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
                │ Top Card (P_1)   │      │                  │      │ Top Card (P_4)   │
                ├──────────────────┤      │ Large Hero Card  │      ├──────────────────┤
                │ Bottom Card (P_0)│      │     (P_2)        │      │ Bottom Card (P_3)│
                └──────────────────┘      └──────────────────┘      └──────────────────┘
   商品索引推进:      消耗 P_0, P_1               消耗 P_2                消耗 P_3, P_4
   ────────────► 每经过 2 列 (偶+奇)，商品数据集稳定向前推进 3 个 (2 + 1 = 3) ────────────►

1. 偶数列与奇数列商品索引映射推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
设总商品列表为数组 $P = [P_0, P_1, \dots, P_{N-1}]$，横向滚动列的序号为 $k \in [0, M-1]$：

* **偶数列起始索引方程 (`_evenCasesIndex`)**：
  偶数列（$k = 0, 2, 4, \dots$）承载 2 个商品，底部为 $P_{	ext{bottom}}$，顶部为 $P_{	ext{top}}$：
  $$	ext{Index}_{	ext{bottom}}(k) = \lfloor k / 2 \rfloor 	imes 3$$
  $$	ext{Index}_{	ext{top}}(k) = 	ext{Index}_{	ext{bottom}}(k) + 1$$
* **奇数列商品索引方程 (`_oddCasesIndex`)**：
  奇数列（$k = 1, 3, 5, \dots$）承载 1 个单品大图：
  $$	ext{Index}_{	ext{hero}}(k) = \lceil k / 2 \rceil 	imes 3 - 1$$
* **总列数离散映射方程 (`_listItemCount`)**：
  给定商品总数 $N$，横向 ListView 所需构建的子列总数 $M$ 为：
  $$M(N) = \begin{cases} \frac{N}{3} 	imes 2, & 	ext{if } N \pmod 3 = 0 \ \lceil \frac{N}{3} \rceil 	imes 2 - 1, & 	ext{if } N \pmod 3 
eq 0 \end{cases}$$

2. 桌面端多列均衡算法 (`balancedLayout`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在宽屏桌面端，系统放弃了单向水平滚动，切换为垂直瀑布流。系统通过 ``balancedLayout`` 算法动态求解最佳列数并平衡各列高度：

$$	ext{ColumnCount}_{	ext{ideal}} = \max\left(1, \left\lfloor \frac{W_{	ext{window}} + W_{	ext{gap}} - 2 \cdot W_{	ext{margin}} - W_{	ext{sidebar}}}{W_{	ext{col}} + W_{	ext{gap}}} \right\rfloor\right)$$

算法遍历商品集合，交替计算每列的累计像素高度，将下一个商品动态推入当前高度最短的列中，杜绝某一列过长导致的底部参差破损。

----------------------------------------------------------------------------------------

第二幕：45 度几何切角边框（`CutCornersBorder`）的路径多边形数学
----------------------------------------------------------------

在 ``lib/studies/shrine/supplemental/cut_corners_border.dart`` 中，系统通过继承 ``OutlineInputBorder`` 实现了经典的 Material 几何倒角设计：

.. code-block:: text

   (X_L, Y_T+C) ────── (X_L+C, Y_T) ──────── Notch 缺口 ──────── (X_R-C, Y_T) ────── (X_R, Y_T+C)
        │                                                                                     │
        │                                                                                     │
   (X_L, Y_B-C) ────── (X_L+C, Y_B) ──────────────────────────── (X_R-C, Y_B) ────── (X_R, Y_B-C)

1. 八顶角闭环多边形方程 (`_notchedSidesAndBottom`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
设边框包围盒为 $	ext{Rect}(X_L, Y_T, X_R, Y_B)$，切角深度为常量 $C = 7.0	ext{px}$：
* 绕过传统圆弧（ArcTo），系统通过纯线段（``lineTo``）在四个顶角处向内倾斜 45 度切角，构建出连续闭合路径：
  $$(X_R - C, Y_T) \longrightarrow (X_R, Y_T + C) \longrightarrow (X_R, Y_B - C) \longrightarrow (X_R - C, Y_B) \longrightarrow (X_L + C, Y_B) \longrightarrow (X_L, Y_B - C) \longrightarrow (X_L, Y_T + C) \longrightarrow (X_L + C, Y_T)$$

2. 浮动标签切口动态插值（`lerpDouble` 与双向文本适配）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当输入框获得焦点时，输入框标签（Label）向上浮动切开顶边：
* 系统在 ``paint()`` 中调用 ``lerpDouble(0.0, gapExtent + gapPadding * 2, gapPercentage)`` 计算缺口宽度；
* **RTL 语言镜像**：在阿拉伯语系下，缺口起点自动从左侧镜像偏移至右侧（``gapStart + gapPadding - extent``），保证文字嵌入缺口的位置严丝合缝。

----------------------------------------------------------------------------------------

第三幕：购物车抽屉动力学——五次强调缓动曲线（Emphasized Easing）与微观形变
--------------------------------------------------------------------------

在 ``lib/studies/shrine/expanding_bottom_sheet.dart`` 中，实现了一个包含**五次强调缓动曲线**与**连续轮廓形变**的高级可展开购物车面板：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ ExpandingBottomSheet (两段式强调缓动动力学)                               │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 1. 加速段 (t: 0.0 -> 0.248) ── Cubic(0.548, 0, 0.757, 0.464)              │
   │    • 以极高的初始加速度爆发启动，迅速完成 37.9% 的位移推进                 │
   │                                                                          │
   │ 2. 减速段 (t: 0.248 -> 1.0) ── Cubic(0.23, 0.94, 0.41, 1)                │
   │    • 切换为极度平缓的减速曲线，优雅平稳停靠在全屏目标位置                 │
   │                                                                          │
   │ 3. 几何轮廓连续形变 (BeveledRectangleBorder)                              │
   │    • 闭合态: 左上角保留 24px 切角 (桌面端 12px)                           │
   │    • 展开态: 切角半径线性收敛至 0px，无缝融为全屏直角视口                 │
   └──────────────────────────────────────────────────────────────────────────┘

1. 五次强调缓动（Emphasized Easing）的分段复合实现
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
标准的三次贝塞尔曲线（如 ``Curves.fastOutSlowIn``）无法表达物理上“前半段超急剧加速、后半段超长尾极慢停靠”的动态张力。

Shrine 创新性地采用 ``TweenSequence`` 拼接了两条独立的三次贝塞尔曲线：
* **拐点时间参数**：设定峰值速度时间点 $	au_{	ext{peak}} = 0.248210$；
* **拐点进度参数**：设定此时对应的空间位移进度 $P_{	ext{peak}} = 0.379146$；
* **正向展开序列**：
  * 前 24.8% 的时间内，由 ``_accelerateCurve`` 驱动从起点到达峰值点；
  * 后 75.2% 的时间内，由 ``_decelerateCurve`` 驱动从峰值点减速到达终点；
* **反向收起序列**：两条曲线及其时间权重互相对称反转（Flipped），实现符合真实重力与阻尼质感的收起体验。

2. 缩略图列表与 `AnimatedListState` 联动
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* 抽屉内部集成 ``_ListModel``，底层持有 ``GlobalKey<AnimatedListState>``；
* 当用户点击购买商品时，商品缩略图通过 ``insertItem`` 伴随缩放与淡入动效滑动插入购物车；
* 当商品超过 3 个时，尾部自动生成由 ``cappedTextScale`` 约束的溢出角标（如 ``+2``），展现出极致的组件状态管理功底。

----------------------------------------------------------------------------------------

小结与给下一个对话的施工建议 (Summary & Next Step Advisory)
------------------------------------------------------------

* **本章核心产出**：
  至此，**模块 03 第 2 节：``03_gallery_studies_deep_dive/02_shrine_asymmetric_layout.rst`` 已全量落盘完工**！系统拆解了 2+1 交错非对称商品流数学模型、桌面端多列均衡算法、45 度倒角 CutCornersBorder 几何路径、以及五次强调缓动曲线（Emphasized Easing）与购物车抽屉状态机。
* **给下一个周期的施工建议**：
  下一个周期将严格聚焦 **模块 03 第 3 节：``03_gallery_studies_deep_dive/03_reply_motion_and_notches.rst``**。
  我们将深入 ``cxyFork-gallery/lib/studies/reply/`` 源码，系统剖析 Reply 邮件客户端的 **Material 3 容器流体变换（OpenContainer / Container Transform）图层形变物理学、以及底部导航栏瀑布流缺口（``WaterfallNotchedRectangle``）圆与切线二次方程判别式几何学**。
