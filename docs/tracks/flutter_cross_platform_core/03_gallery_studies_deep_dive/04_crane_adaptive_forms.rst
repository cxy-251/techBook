========================================================================================
第 4 节：Crane 旅游系统：胶囊边框指示器、多维折叠表单与自适应网格
========================================================================================

.. note::
   **源码坐标与本节核心使命**
   * **核心源文件**：``cxyFork-gallery/lib/studies/crane/border_tab_indicator.dart``、``header_form.dart``、``fly_form.dart``、``sleep_form.dart`` 与 ``eat_form.dart``
   * **底层依赖源码**：``flutter-3.32.0/packages/flutter/lib/src/material/tab_indicator.dart`` 与 ``packages/flutter/lib/src/rendering/custom_paint.dart``
   * **核心使命**：以多维出行预订业务与复杂表单人机工程为基准，深度解构 Crane 全球旅游系统如何脱离默认底划线指示器、手写支持字号动态补偿的胶囊边框指示器（``BorderTabIndicator`` / ``BoxPainter``）、基于 ``LayoutBuilder`` 的四级自适应表单网格求解引擎（移动单列 $	o$ 小桌面双列 $	o$ 标准桌面四列）、以及机票/酒店/餐饮（Fly / Sleep / Eat）三态出行状态机的微观执行流。

----------------------------------------------------------------------------------------

第一幕：自定义胶囊边框指示器（`BorderTabIndicator`）的画笔几何学
------------------------------------------------------------------

在 Flutter 原生 ``TabBar`` 中，默认的选项卡指示器是位于 Tab 底部的单条下划线（``UnderlineTabIndicator``）。而在高端旅游出行设计中，激活的 Tab 需要以一个**完整包裹文本的高对比度圆角胶囊白框（Pill Border）**呈现。

在 ``lib/studies/crane/border_tab_indicator.dart`` 中，通过继承 ``Decoration`` 并重写底层 ``BoxPainter`` 实现了极致轻量级的物理画笔：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ BorderTabIndicator 几何画笔 (BoxPainter 物理图层)                          │
   ├──────────────────────────────────────────────────────────────────────────┤
   │ 1. horizontalInset 字号自适应内边距补偿方程:                               │
   │    horizontalInset = 16.0 - 4.0 * textScaleFactor                        │
   │    • 标准字号 (1.0x): 留白 12.0px                                        │
   │    • 辅助大字号 (1.5x): 自动收缩至 10.0px，防止胶囊框溢出挤压相邻 Tab     │
   │                                                                          │
   │ 2. 居中包围盒矩形 (Rect) 物理坐标计算:                                   │
   │    X_origin = offset.dx + horizontalInset                                │
   │    Y_origin = (Height_tab / 2) - (indicatorHeight / 2) - 1.0             │
   │    Width    = Width_tab - 2 * horizontalInset                            │
   │    Height   = indicatorHeight                                            │
   │                                                                          │
   │ 3. 矢量圆角绘制 (canvas.drawRRect):                                      │
   │    RRect.fromRectAndRadius(Rect, Radius.circular(56.0))                   │
   │    style = PaintingStyle.stroke, strokeWidth = 2.0 (白色线框)             │
   └──────────────────────────────────────────────────────────────────────────┘

1. 字号缩放（Text Scale Factor）动态几何补偿
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
若胶囊边框的左右内边距（Horizontal Inset）采用固定硬编码数值（如 16px），当视障用户调大系统字体（1.3x ~ 2.0x）时，文字宽度变大而胶囊框可用宽度变窄，必然导致文字被强行挤出边框。

代码建立了精妙的反比例补偿公式：
$$	ext{HorizontalInset} = 16.0 - (4.0 	imes 	ext{textScaleFactor})$$
* 字号越大，指示器自动压缩左右边距、向外释放更多有效横向空间，确保无论字号如何变化，文字永远完美居中包裹在胶囊圆角之内。

2. `BoxPainter` 零 Widget 开销的物理优势
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* ``BorderTabIndicator`` 自身是一个不可变配置对象（``const Decoration``）；
* 真正的绘制逻辑全部收敛在 ``BorderPainter.paint()`` 中，直接调用底层的 ``canvas.drawRRect()``；
* 在选项卡切换滑动过程中，框架仅需要驱动画笔的 ``offset`` 插值重绘，**完全不需要重复销毁和重建任何底层的 RenderObject 或 Element 节点**。

----------------------------------------------------------------------------------------

第二幕：四级自适应表单网格（`HeaderForm`）的动态约束求解
--------------------------------------------------------

旅游出行预订需要输入大量结构化信息（出行人数、出发地、目的地、去程日期、返程日期）。在不同终端设备上，表单呈现截然不同的网格拓扑：

.. code-block:: text

   【移动端形态 (Mobile)】           【小桌面/平板形态 (Small Desktop)】     【标准桌面形态 (Desktop)】
   ┌──────────────────────┐         ┌───────────┬───────────┐         ┌───────┬───────┬───────┬───────┐
   │ 人数选择 (Field 0)   │         │ 人数      │ 出发地    │         │ 人数  │ 出发地│ 目的地│ 出行日│
   ├──────────────────────┤         ├───────────┼───────────┤         └───────┴───────┴───────┴───────┘
   │ 出发地 (Field 1)     │         │ 目的地    │ 出行日    │         4 列横向内联并排 (crossAxis = 4)
   ├──────────────────────┤         └───────────┴───────────┘         横向边距 120px 居中
   │ 目的地 (Field 2)     │         2 列双排并列 (crossAxis = 2)
   └──────────────────────┘         横向边距 24px
   单列纵向线性堆叠 (Column)

1. `LayoutBuilder` 与长宽比（AspectRatio）动态推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在 ``lib/studies/crane/header_form.dart`` 中，系统通过 ``LayoutBuilder`` 动态解算每个输入框的几何长宽比：

* **列数动态判决**：
  $$	ext{crossAxisCount} = \begin{cases} 4, & 	ext{if isDesktop} \land 
eg 	ext{isSmallDesktop} \ 2, & 	ext{if isSmallDesktop} \ 1, & 	ext{otherwise (Mobile)} \end{cases}$$
* **单个输入框可用宽度方程**：
  $$W_{	ext{item}} = \frac{	ext{constraints.maxWidth}}{	ext{crossAxisCount}}$$
* **`GridView.count` 长宽比方程（高度固定为 $	ext{textFieldHeight} = 60.0	ext{px}$）**：
  $$	ext{childAspectRatio} = \frac{W_{	ext{item}}}{	ext{textFieldHeight}} = \frac{	ext{constraints.maxWidth}}{60.0 	imes 	ext{crossAxisCount}}$$

2. 边缘间距消除算法
~~~~~~~~~~~~~~~~~~~
为了防止最右侧一列的输入框外侧出现多余的缝隙，代码采用模运算进行动态边距裁剪：
$$	ext{hasTrailingMargin} = ((field.index + 1) \pmod{	ext{crossAxisCount}} 
e 0)$$
当属于当前行的最后一个元素时，移除右侧内边距（``Padding.zero``），使整个表单与外层安全边框保持严丝合缝的像素级对齐。

----------------------------------------------------------------------------------------

第三幕：三态多维出行表单与日历范围拾取状态机 (`Fly / Sleep / Eat`)
-------------------------------------------------------------------

在 Crane 架构中，整个出行系统由三大业务状态机统一驱动：

1. 统一字段抽象（`HeaderFormField`）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
每个输入框被标准化抽象为独立实体：
* ``int index``：在表单网格中的唯一拓扑序号；
* ``IconData iconData``：语义化前缀图标（飞机、床铺、餐具、日历、用户）；
* ``String title``：占位提示文本（Hint Text）；
* ``TextEditingController textController``：独立的状态控制器。

2. 三大业务维度的表单特化
~~~~~~~~~~~~~~~~~~~~~~~~~
* **机票订购（Fly Form，5 字段）**：出行人数 $	o$ 出发地 $	o$ 目的地 $	o$ 去程时间 $	o$ 返程时间；
* **酒店住宿（Sleep Form，4 字段）**：入住人数 $	o$ 目标城市 $	o$ 入住日期 $	o$ 离店日期；
* **美食探店（Eat Form，4 字段）**：就餐人数 $	o$ 所在位置 $	o$ 用餐时间 $	o$ 用餐日期。

3. 日历范围拾取器与控制器数据单向流
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当用户点击日期字段时，系统唤起 Crane 专属的日历范围弹窗（``CalendarRangePicker``）：
* 用户在日历上选取起始日与结束日后，数据直接通过 ``textController.text = formatDateRange(start, end)`` 回写；
* **性能收益**：利用控制器直接触发输入框局部的文本重绘，**完全不触发父级表单与全屏脚手架的任何 Rebuild**，保持了极高的数据录入流畅度。

----------------------------------------------------------------------------------------

小结与给下一个对话的施工建议 (Summary & Next Step Advisory)
------------------------------------------------------------

* **本章核心产出**：
  至此，**模块 03 第 4 节：``03_gallery_studies_deep_dive/04_crane_adaptive_forms.rst`` 已全量落盘完工**！系统拆解了 BorderTabIndicator 胶囊指示器的字号自适应画笔几何、四级 HeaderForm 网格动态长宽比求解、以及 Fly/Sleep/Eat 三态出行表单联动状态机。
* **给下一个周期的施工建议**：
  下一个周期将严格聚焦 **模块 03 第 5 节：``03_gallery_studies_deep_dive/05_fortnightly_masonry_grid.rst``**。
  我们将深入 ``cxyFork-gallery/lib/studies/fortnightly/`` 源码，系统剖析 Fortnightly 现代新闻门户系统的 **桌面响应式报纸瀑布流（Masonry Grid）、多列动态字号阶梯缩放模型（``TextScale``）、以及主副新闻卡片自适应比例分配**。
