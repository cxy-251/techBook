========================================================================================
第 5 节：Fortnightly 新闻系统：三栏报纸排版几何、字号阻尼缩放与三字体拓扑
========================================================================================

.. note::
   **源码坐标与本节核心使命**
   * **核心源文件**：``cxyFork-gallery/lib/studies/fortnightly/shared.dart`` 与 ``app.dart``
   * **底层依赖源码**：``flutter-3.32.0/packages/flutter/lib/src/rendering/flex.dart`` 与 ``packages/flutter/lib/src/painting/text_style.dart``
   * **核心使命**：以现代新闻报刊的高级编排美学与宽屏信息密度为基准，深度解构 Fortnightly 现代新闻门户系统在桌面大屏下的三栏非对称报纸排版几何模型（固定导轨 200px + 核心主视口 2/3 + 侧边资讯流 1/3）、字号阶梯式阻尼缩放算法（``reducedTextScale``）、多色相金融股票行情格式化，以及融合了古典衬线体与现代紧凑体（Merriweather + Libre Franklin + Roboto Condensed）的三字体排版拓扑。

----------------------------------------------------------------------------------------

第一幕：桌面三栏报纸排版（Editorial Masonry Layout）的分栏几何学
------------------------------------------------------------------

在桌面宽屏或高分屏设备上浏览新闻门户时，若采用单列长条排版，过长的文字行长（Line Length）会导致眼球横向跳跃距离过大，产生严重的视疲劳。经典报纸排版通过**分栏阅读通道（Reading Columns）**将信息密度与阅读节奏收拢在黄金视野内。

Fortnightly 在 ``lib/studies/fortnightly/app.dart`` 中实现了经典的三栏非对称报纸排版：

.. code-block:: text

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ Fortnightly 桌面端三栏非对称报纸排版架构                                  │
   ├──────────────────┬───┬──────────────────────────┬───┬────────────────────┤
   │ 1. 导航菜单导轨   │间 │ 2. 核心新闻主视口         │间 │ 3. 实时资讯与行情流 │
   │    NavigationMenu│距 │    Main Story Stream     │距 │    Market & Video  │
   │    固定宽度 200px │20 │    Flexible(flex: 2)     │20 │    Flexible(flex:1)│
   │    常驻分类索引   │px │    头条大图+水平预览图文 │px │    股票走势+视频流 │
   └──────────────────┴───┴──────────────────────────┴───┴────────────────────┘

1. 空间分配与弹性因子（Flex Factor）求解
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
设当前窗口宽度为 $W_{	ext{window}}$，外层内边距为 $W_{	ext{padding}} = 16	ext{px}$，固定侧边栏宽度为 $W_{	ext{menu}} = 200	ext{px}$，两道列间距为 $W_{	ext{spacer}} = 20	ext{px}$：

* **有效可用弹性宽度**：
  $$W_{	ext{available}} = W_{	ext{window}} - (2 	imes 16.0) - 200.0 - (2 	imes 20.0) = W_{	ext{window}} - 272.0$$
* **核心新闻主视口宽度（占可用空间的 2/3）**：
  $$W_{	ext{main}} = \frac{2}{3} 	imes W_{	ext{available}}$$
* **侧边行情与视频流宽度（占可用空间的 1/3）**：
  $$W_{	ext{side}} = \frac{1}{3} 	imes W_{	ext{available}}$$
主次两列各包含一个独立的 ``ListView``，既保证了两侧不同高度内容的滚动独立性，又通过 2:1 的黄金比例构建了清晰的视觉焦点层级。

----------------------------------------------------------------------------------------

第二幕：字号阶梯式阻尼缩放算法（`reducedTextScale`）
----------------------------------------------------

在移动端和大屏排版中，无障碍大字号（Text Scale Factor，如 1.5x ~ 2.0x）是一把双刃剑：如果对固定的标题栏、股票代码栏或水平标签条进行 100% 线性放大，会导致高度固定的组件发生严重的像素溢出（``A RenderFlex overflowed by ... pixels``）。

Fortnightly 引入了**阻尼缩放模型（Reduced Text Scale）**：

.. code-block:: text

   [系统传入原始字号缩放比例 Scale]
                  │
                  ▼
   reducedTextScale(context) 阻尼衰减计算方程:
   Scale_reduced = 1.0 + (Scale_system - 1.0) * 0.5
                  │
                  ├── 当系统放大 1.5x ──► 实际应用 1.25x
                  └── 当系统放大 2.0x ──► 实际应用 1.50x
                  │
                  ▼ 动态调节固定高度组件
   HeaderHeight = 40.0 * Scale_reduced
   HashtagBarHeight = 32.0 * Scale_reduced

通过将超出 1.0 的缩放增量衰减 50%，既保证了视障用户能够清晰感知到字号变大，又保护了高密度报纸排版网格的物理结构稳定性。

----------------------------------------------------------------------------------------

第三幕：多色相排版系统与三字体融合拓扑
--------------------------------------

在 ``lib/studies/fortnightly/shared.dart`` 的 ``buildTheme()`` 中，系统建立了一套融合了古典出版物与现代数字金融的“三字体排版矩阵”：

.. code-block:: text

   TextTheme 核心排版矩阵
        │
        ├── 1. Merriweather (古典衬线体 Serif)
        │        ├── bodyMedium (Weight 300, 16pt) ── 新闻正文摘要 (严谨文学质感)
        │        └── titleLarge (Weight 700 Italic, 14pt) ── 分栏小标题 (Top Highlights)
        │
        ├── 2. Libre Franklin (人文无衬线体 Sans-Serif)
        │        ├── headlineSmall (Weight 500, 16pt) ── 核心新闻大标题 (清晰易读)
        │        ├── titleSmall    (Weight 400, 14pt) ── 趋势标签 (#TrendingTopic)
        │        └── bodyLarge     (Weight 500, 11pt, Opacity 0.5) ── 阅读耗时 (2 min)
        │
        └── 3. Roboto Condensed (紧凑型几何无衬线体)
                 └── titleMedium (Weight 700, 16pt) ── 类别大写标签与股票代码 (DIJA, NASDAQ)

1. 金融行情极性着色器 (`StockItem`)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
对于实时股市行情展示（DIJA、S&P、Nasdaq、Nikkei）：
* **涨跌百分比格式化**：通过 ``NumberFormat.decimalPercentPattern`` 绑定当前语言环境动态格式化；
* **极性二值色彩语义**：
  * 上涨（$	ext{percent} > 0$）：赋予鲜绿色（``Color(0xff20CF63)``）并自动前置加号 ``+``；
  * 下跌（$	ext{percent} < 0$）：赋予高亮紫色（``Color(0xff661FFF)``）并自动前置减号 ``-``；
在有限的股票条目中提供了极高对比度的涨跌感知。

----------------------------------------------------------------------------------------

第四幕：移动端抽屉（Drawer）到桌面常驻导轨（Docked Menu）的拓扑转换
-------------------------------------------------------------------

在跨端响应式切换时，导航系统的结构发生根本性重塑：
* **移动端（Mobile）**：
  * ``Scaffold.drawer`` 承载 ``NavigationMenu(isCloseable: true)``，平时完全移出屏幕，点击顶栏左侧汉堡菜单时滑出，点击关闭按钮或外部蒙层时调用 ``Navigator.pop(context)``；
* **桌面端（Desktop）**：
  * 抽屉被彻底废除，``NavigationMenu(isCloseable: false)`` 直接作为左侧第一列的固定子节点物理内联到横向 ``Row`` 布局中，实现了多端视图树的零冗余复用。

----------------------------------------------------------------------------------------

小结与给下一个对话的施工建议 (Summary & Next Step Advisory)
------------------------------------------------------------

* **本章核心产出**：
  至此，**【模块 03：Gallery 5 大商业级 Study 源码深度剖析】全部 5 节已全量圆满完工并落盘**！彻底解构了 Rally 自绘图表、Shrine 非对称排版、Reply 容器变换、Crane 胶囊表单、以及 Fortnightly 报纸排版。
* **给下一个周期的施工建议**：
  下一个周期将正式开启 **【模块 04：声明式路由与 CodeViewer 语法引擎】** 的第一节：
  ``04_gallery_routes_and_codeviewer/01_regex_routes_and_deferred.rst``。
  我们将深入 ``cxyFork-gallery/lib/routes.dart`` 与 ``deferred_widget.dart`` 源码，系统剖析声明式 URL 路由捕获、正则表达式捕获组动态提取、以及基于 Dart ``deferred as`` 语法的 Web 异步代码分包与运行时状态机。
