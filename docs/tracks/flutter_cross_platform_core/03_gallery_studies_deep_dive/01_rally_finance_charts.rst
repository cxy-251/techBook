========================================================================================
第 1 节：Rally 金融系统：Canvas 自绘贝塞尔曲线折线图与环形渐变饼图深度算法
========================================================================================

.. note::
   **源码坐标与本节核心使命**
   * **核心源文件**：``cxyFork-gallery/lib/studies/rally/charts/pie_chart.dart``、``line_chart.dart`` 与 ``finance.dart``
   * **底层依赖源码**：``flutter-3.32.0/packages/flutter/lib/src/rendering/custom_paint.dart`` 与 ``packages/flutter/lib/src/painting/text_painter.dart``
   * **核心使命**：以底层自绘图形学与高并发财务状态机为基准，深度解构 Rally 如何在完全不依赖任何第三方重量级图表库的前提下，直接利用 Flutter 底层物理画布（``Canvas`` 与 ``CustomPainter``），手写实现高阶环形带间隙扫掠饼图、二次贝塞尔样条平滑折线图、零 Widget 开销的 ``TextPainter`` 排版、以及无障碍语义树映射（``CustomPainterSemantics``）。

----------------------------------------------------------------------------------------

第一幕：环形甜甜圈饼图（`RallyPieChart`）的物理弧度积分与遮罩几何学
------------------------------------------------------------------

在企业级金融报表开发中，直接引入开源图表库常导致安装包体积激增、动画帧率掉帧以及样式定制受限。Rally 在 ``lib/studies/rally/charts/pie_chart.dart`` 中通过自定义 ``BoxPainter``（``_RallyPieChartOutlineBoxPainter``），直接在 GPU 物理画布上进行微积分级别的弧度计算与几何绘制。

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ RallyPieChart (双同心圆遮罩绘制架构)                                      │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 1. outerRect (外层数据扇区矩形, 半径 R_outer = R - 3 * strokeWidth)       │
   │    • 遍历 segments 数据集，绘制彩色数据扇区                                │
   │    • 扇区之间严格预留 1° 物理间隙 (spaceRadians = 2π / 180)               │
   │    • 剩余预算额度自动补充黑色背景扇区                                     │
   │                                                                          │
   │ 2. innerRect (内层同心圆背景遮罩, 半径 R_inner = R - 4 * strokeWidth)     │
   │    • 以背景色 (RallyColors.primaryBackground) 绘制实心同心圆               │
   │    • 物理上遮挡中心区域，以 0 开销构建出平滑的中空环形甜甜圈图表          │
   └──────────────────────────────────────────────────────────────────────────┘

1. 弧度空间离散化与物理间隙扣除方程
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
一个完整圆周固定为 $2\pi$ 弧度（``wholeRadians = 2 * math.pi``）。为了在各个彩色数据块之间呈现清晰的视觉分割，系统设定每两个扇区之间预留固定的物理角间距（``spaceRadians = 2\pi / 180 \approx 0.0349	ext{ rad} = 1.0^\circ``）：

* **有效可用弧度总额**：
  设数据块总数为 $N$，扣除所有角间隙后，实际可用于分配数据比例的有效弧度总和为：
  $$	ext{EffectiveRadians} = 2\pi - (N 	imes 	ext{spaceRadians})$$
* **单个扇区的扫掠角（Sweep Angle）方程**：
  设当前扇区的数据金额为 $V_i$，账户总金额为 $T_{	ext{total}}$，当前入场动画进度为 $\alpha \in [0, 1]$：
  $$	ext{SweepAngle}_i = \alpha 	imes \left( \frac{V_i}{T_{	ext{total}}} 	imes 	ext{EffectiveRadians} \right)$$
* **起始角（Start Angle）累加积分方程**：
  设前 $i-1$ 个扇区的累加金额为 $C_{i-1} = \sum_{k=0}^{i-1} V_k$。由于起始点在时钟 12 点钟方向（即 $-\pi/2$）：
  $$	ext{StartAngle}_i = \alpha 	imes \left( \frac{C_{i-1}}{T_{	ext{total}}} 	imes 	ext{EffectiveRadians} + i 	imes 	ext{spaceRadians} \right) - \frac{\pi}{2}$$
  每个扇区调用 ``canvas.drawArc(outerRect, startAngle, sweepAngle, true, paint)`` 完成扇形绘制。

2. 双同心圆物理遮罩（Donut Masking）的性能优势
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* **传统布尔运算路径剪裁的性能灾难**：在 Canvas 上使用 ``Path.combine(PathOperation.difference, outerPath, innerPath)`` 进行多边形布尔差集运算，需要 CPU 在每帧对复杂的贝塞尔曲线求交点，会导致严重掉帧；
* **Rally 的硬件遮罩解法**：
  1. 首先在较大的 ``outerRect`` 上连续绘制实心彩色扇形；
  2. 随后在较小的 ``innerRect`` 上以背景实色直接覆盖绘制一个整圆（``canvas.drawArc(innerRect, 0, 2*math.pi, true, bgPaint)``）；
  3. 利用 GPU 深度缓冲与图层覆盖，在无需任何路径求交计算的前提下，以极限的帧率绘制出空心圆环。

3. `TweenSequence` 两阶段非线性入场动力学
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
为了让金融数据展示更具科技质感，动画控制器被划分为非线性的两段式序列：
* **前 40% 时间窗口（Weight 1.0）**：数值严格锁定在 0，图表保持静止，等待前置页面的转场位移基本就绪；
* **后 60% 时间窗口（Weight 1.5）**：数值从 0 推进到 1.0，配合减速曲线（``Curves.decelerate``），驱动各个彩色扇区从 12 点钟方向爆发式顺时针展开并优雅停靠。

----------------------------------------------------------------------------------------

第二幕：二次贝塞尔样条平滑折线图（`RallyLineChart`）的高阶数学推导
-----------------------------------------------------------------

在 ``lib/studies/rally/charts/line_chart.dart`` 中，系统实现了一套包含时序数据归一化、中点样条插值与无障碍映射的折线图引擎。

1. 52 天时序资产坐标归一化映射
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
系统统计过去 52 天（``numDays = 52``）的资产余额时序数据。设第 $i$ 天的累加资产值为 $A_i$，画布允许绘制的最大资产上限为 $	ext{maxAmount} = 2000.0$：

* **X 轴水平坐标映射**：
  $$X_i = \frac{i}{	ext{numDays}} 	imes W_{	ext{rect}}$$
* **Y 轴垂直物理坐标映射（坐标系原点位于左上角）**：
  $$Y_i = \frac{	ext{maxAmount} - A_i}{	ext{maxAmount}} 	imes H_{	ext{rect}}$$

2. 二次贝塞尔样条平滑算法 (`quadraticBezierTo`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
若直接使用直线段（``lineTo``）连接各个数据点 $(X_i, Y_i)$，折线在每个采样点都会产生尖锐的折角（$C^0$ 连续但一阶导数不连续，视觉极其生硬）。

Rally 采用了经典的**相邻点中点控制样条平滑算法**：

.. code-block:: text

   P_k (X_k, Y_k) ─────────────────────────── P_{k+1} (X_{k+1}, Y_{k+1})
         \                                     /
          \       MidPoint (中点目标锚点)      /
           \    ( (X_k+X_{k+1})/2, (Y_k+Y_{k+1})/2 )
            ▼                                 ▼
   以当前点 P_k 作为控制点 (Control Point)，以中点作为终点 (End Point)
   调用 path.quadraticBezierTo(X_k, Y_k, MidX, MidY) 构建 C^1 连续平滑曲线

* **二次贝塞尔曲线物理方程**：
  设参数 $t \in [0, 1]$，曲线在当前线段内的连续轨迹为：
  $$B(t) = (1-t)^2 P_{	ext{start}} + 2t(1-t) P_{	ext{control}} + t^2 P_{	ext{end}}$$
  使得折线在经过每一个数据点时，切线方向平滑过渡，生成一条极具美感的高级资产波动走势图。

3. 零 Widget 开销的文字排版 (`TextPainter`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在绘制 X 轴的 52 天刻度线与 12 个月份文字标签时：
* 系统**完全没有在 UI 树中挂载任何 Text 组件**（若挂载几十个 Text 组件，会造成巨大的 Element 树构建与垃圾回收开销）；
* 而是直接在 ``paint()`` 方法中就地实例化底层的 ``TextPainter``，传入紧凑的 ``TextSpan`` 并调用 ``leftLabel.layout()``，计算出文字尺寸后直接调用 ``leftLabel.paint(canvas, Offset(x, y))`` 将字形光栅化印在画布上，将排版开销压低至纳秒级。

4. 盲人无障碍语义树映射 (`CustomPainterSemantics`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
由于 Canvas 绘制的线条对操作系统的无障碍屏幕朗读器（VoiceOver / TalkBack）是完全不可见的，Rally 在 ``CustomPainter`` 中重写了 ``semanticsBuilder``：
* 将整个图表横向均匀等分为 10 个虚拟数据区间（``numGroups = 10``）；
* 计算每个区间内的资产中位数（Median Amount）；
* 为每个区间生成一个 ``CustomPainterSemantics`` 虚拟边界盒：
  $$	ext{SemanticsRect}_k = \left( \frac{k}{10} W, 0 \right) \quad 	ext{with Size} \left( \frac{W}{10}, H \right)$$
* 赋予格式化后的金额描述文本（如 ``"$1,420"``），使视障用户在手指滑过图表不同区域时，能够清晰听到资产走势的语音播报。

----------------------------------------------------------------------------------------

第三幕：多维财务状态机与资产结算架构 (`finance.dart`)
------------------------------------------------------

在 ``lib/studies/rally/finance.dart`` 中，财务系统构建了高内聚的数据结算中枢：

1. 金融数据模型三元组
~~~~~~~~~~~~~~~~~~~~~
* **``AccountData``（活期/投资账户）**：维护账户名称、账号后四位、主金额与特定资产色标；
* **``BillData``（应付账单）**：维护账单到期日、还款状态、主金额与扣款账户关联；
* **``BudgetData``（预算配额）**：维护类目限额（``primaryAmount``）与已消费金额（``amountUsed``）。

2. 响应式结算与动态格式化
~~~~~~~~~~~~~~~~~~~~~~~~~
* **金额安全累加器 (`sumOf<T>`)**：在数据发生异步变动时，通过泛型高阶函数安全遍历集合累加金额，防止浮点数精度溢出；
* **多币种本地化格式化器 (`formatters.dart`)**：通过 ``intl.NumberFormat.currency`` 动态绑定系统当前 Locale，在数字达到百万时自动切换为简写千分位（如 ``$1.2M`` 或 ``$45.3K``），实现严密的商业级财务计算闭环。

----------------------------------------------------------------------------------------

小结与给下一个对话的施工建议 (Summary & Next Step Advisory)
------------------------------------------------------------

* **本章核心产出**：
  至此，**模块 03 第 1 节：``03_gallery_studies_deep_dive/01_rally_finance_charts.rst`` 已全量落盘完工**！系统拆解了环形饼图的物理弧度积分、双同心圆硬件遮罩、二次贝塞尔样条插值折线图、TextPainter 零开销排版、以及 CustomPainterSemantics 无障碍语义树。
* **给下一个周期的施工建议**：
  下一个周期将严格聚焦 **模块 03 第 2 节：``03_gallery_studies_deep_dive/02_shrine_asymmetric_layout.rst``**。
  我们将深入 ``cxyFork-gallery/lib/studies/shrine/`` 源码，系统剖析 Shrine 现代电商系统的 **2+1 交错非对称商品流数学模型（``_evenCasesIndex`` / ``_oddCasesIndex``）、桌面端多列均衡算法（``balancedLayout``）、手写 45 度倒角 ``CutCornersBorder`` 几何路径、以及基于 ``SpringSimulation`` 弹簧物理模拟的可展开购物车抽屉**。
