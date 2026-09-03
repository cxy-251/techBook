========================================================================================
第 3 节：gallery_theme_data.dart 语义化设计系统、色彩对比度算法与字体排版规范
========================================================================================

.. note::
   **源码坐标与本节核心使命**
   * **核心源文件**：``cxyFork-gallery/lib/themes/gallery_theme_data.dart``
   * **底层依赖源码**：``flutter-3.32.0/packages/flutter/lib/src/material/color_scheme.dart`` 与 ``theme_data.dart``
   * **核心使命**：以企业级设计系统与无障碍物理规范为基准，深度解构 Gallery 如何将零散的颜色与字号抽象为高内聚的“设计令牌（Design Tokens）”、Material 3 角色化色彩方案的亮度对比度数学推导、Alpha 图层物理融合（``Color.alphaBlend``）以及基于 Google Fonts 的多字体排版拓扑。

----------------------------------------------------------------------------------------

第一幕：设计令牌（Design Tokens）与角色化色彩模型 (`ColorScheme`)
------------------------------------------------------------------

在现代大型跨平台软件工程中，最常见的反模式（Anti-Pattern）是在各个子组件的 ``build()`` 方法中直接硬编码具体的十六进制颜色值（如 ``Color(0xFFB93C5D)``）。这种硬编码会导致三个灾难性后果：
1. **深浅色模式切换断裂**：无法通过单个全局开关无缝翻转所有组件的前景与背景；
2. **多端设计规范失控**：随着业务扩张，界面中会出现数十种微小差异的灰色和红色，设计一致性荡然无存；
3. **无障碍对比度违规**：随意搭配的前景色与背景色极易导致弱视用户无法辨识文字。

在 ``lib/themes/gallery_theme_data.dart`` 中，UI 样式被完全剥离出组件业务逻辑，统一上升为设计系统规范（Design Tokens）：

.. code-block:: text

   ThemeData 全局容器
        │
        ├── ColorScheme (角色化语义颜色系统)
        │        ├── primary / onPrimary         (核心交互色 / 对比前景字色)
        │        ├── primaryContainer            (高亮容器底色)
        │        ├── secondary / onSecondary     (次级点缀色 / 次级前景字色)
        │        ├── secondaryContainer          (次级卡片容器色)
        │        ├── surface / onSurface         (卡片表面底色 / 表面前景字色)
        │        └── background / onBackground   (全屏脚手架底色 / 全局前景字色)
        │
        └── TextTheme (多层级排版规范)
                 ├── Headline (Medium / Small)   (大标题与副标题)
                 ├── Title (Large / Medium)      (卡片标题与列表项头部)
                 ├── Body (Large / Medium)       (长文正文与详细描述)
                 └── Label (Large / Small)       (紧凑按钮与分类标签)

1. 角色化配色（Color Roles）的物理职责划分
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* **``primary``（核心交互主色）**：
  * **浅色模式**：设定为覆盆子红（``Color(0xFFB93C5D)``）；
  * **深色模式**：动态提升明度，调整为柔和亮珊瑚红（``Color(0xFFFF8383)``），防止高饱和暗红色在深黑背景上发生光学晕影（Halation Effect）；
* **``surface`` 与 ``background``（容器表面与全屏背景）**：
  * **浅色模式**：采用微灰白（``Color(0xFFFAFBFB)`` 与 ``Color(0xFFE6EBEB)``），避免纯白（``#FFFFFF``）在视网膜屏幕上造成刺眼的高对比眩光；
  * **深色模式**：采用深紫灰（``Color(0xFF1F1929)`` 与 ``Color(0xFF241E30)``），通过微量的紫色色相（Hue）赋予暗黑模式更高级的层次质感，而非死板的纯黑（``#000000``）。

2. WCAG 2.1 无障碍对比度（Contrast Ratio）数学计算
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Material 规范要求：所有以 ``on-`` 开头的前景文字/图标颜色（如 ``onPrimary``、``onSurface``），与承载它的背景色之间必须满足严格的物理光学对比度要求（正常文本至少 $\ge 4.5:1$，大号粗体文本至少 $\ge 3.0:1$）。

* **相对亮度（Relative Luminance）物理积分公式**：
  根据 CIE 1931 色彩空间标准，将 RGB 颜色分量归一化到 $[0, 1]$ 并进行伽马校正（Gamma Correction）：
  $$R_{	ext{linear}} = \begin{cases} \frac{R}{12.92}, & R \le 0.04045 \ \left(\frac{R + 0.055}{1.055}\right)^{2.4}, & R > 0.04045 \end{cases}$$
  亮度 $L$ 为人眼三原色视锥细胞加权和：
  $$L = 0.2126 	imes R_{	ext{linear}} + 0.7152 	imes G_{	ext{linear}} + 0.0722 	imes B_{	ext{linear}}$$
* **对比度比值公式**：
  设前景色亮度为 $L_1$，背景色亮度为 $L_2$（且 $L_1 > L_2$）：
  $$	ext{Contrast Ratio} = \frac{L_1 + 0.05}{L_2 + 0.05}$$
  在 Gallery 的深色模式下，``surface = #1F1929``（$L_2 \approx 0.015$），配套的 ``onSurface = #FFFFFF``（$L_1 = 1.0$），计算得出：
  $$	ext{Contrast} = \frac{1.0 + 0.05}{0.015 + 0.05} = \frac{1.05}{0.065} \approx 16.15:1$$
  远超 WCAG AAA 级标准的 7.0:1，从数学层面上彻底杜绝了阅读障碍。

----------------------------------------------------------------------------------------

第二幕：Alpha 混合与物理图层融合 (`Color.alphaBlend`)
------------------------------------------------------

在 ``gallery_theme_data.dart`` 的 ``snackBarTheme`` 配置中，展示了一段精妙的半透明颜色合成算法：

.. code-block:: text

   backgroundColor: Color.alphaBlend(
     _lightFillColor.withOpacity(0.80),
     _darkFillColor,
   )

1. 图层物理混合光学模型（Alpha Compositing）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在图形光栅化管道中，当一个带有不透明度 $\alpha_{	ext{src}}$ 的源颜色（Source Color）覆盖在一个带有不透明度 $\alpha_{	ext{dst}}$ 的目标背景色（Destination Color）之上时，物理合成公式如下：

* **输出 Alpha 通道计算**：
  $$\alpha_{	ext{out}} = \alpha_{	ext{src}} + \alpha_{	ext{dst}} 	imes (1 - \alpha_{	ext{src}})$$
* **RGB 颜色分量线性插值**：
  $$C_{	ext{out}} = \frac{C_{	ext{src}} 	imes \alpha_{	ext{src}} + C_{	ext{dst}} 	imes \alpha_{	ext{dst}} 	imes (1 - \alpha_{	ext{src}})}{\alpha_{	ext{out}}}$$

2. 为什么使用 `Color.alphaBlend` 替代简单的透明度？
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* 若直接给悬浮提示条（SnackBar）设置透明度（如 ``Colors.black87``），当 SnackBar 浮动在不同颜色的复杂图文或图片上方时，其底层透出来的杂乱像素会破坏提示文字的可读性；
* 通过 ``Color.alphaBlend``，系统在**内存中直接将半透明黑色与纯白底色进行预融合，计算生成一个 100% 不透明的、色相精准收敛的暗灰色**；
* 既保留了半透明设计的柔和灰阶质感，又构建了物理上的全遮挡实色背景，保证文本在任何场景下的对比度绝对恒定。

----------------------------------------------------------------------------------------

第三幕：跨平台字体渲染引擎与排版层级 (`TextTheme` & GoogleFonts)
------------------------------------------------------------------

在多平台运行环境下，文字排版面临巨大的物理渲染挑战：
* macOS / iOS 使用苹果专有的 **CoreText** 排版引擎，采用亚像素抗锯齿；
* Android / Linux 使用 **FreeType + HarfBuzz** 开源字形栅格化引擎；
* Windows 使用微软的 **DirectWrite** 渲染器；
* 各个平台系统自带的默认字体（如苹方 PingFang SC、Roboto、微软雅黑）在字符基线（Baseline）、字偶距（Kerning）和行高（Line Height）计算上存在微小差异，极易导致标题在某些系统上单行换行截断。

1. 几何双字体拓扑策略
~~~~~~~~~~~~~~~~~~~~~
Gallery 在 ``_textTheme`` 中采用了互补的“双字体工程架构”：

.. code-block:: text

   TextTheme 排版中枢
        │
        ├── Montserrat 字体家族 (无衬线几何体)
        │        ├── headlineMedium (20pt Bold)   ── 用于顶级卡片与主页大标题
        │        ├── titleLarge     (16pt Bold)   ── 用于列表项与模块头部
        │        ├── bodyMedium     (16pt Regular)── 用于常规正文说明
        │        └── labelSmall     (12pt Medium) ── 用于紧凑数字与次级标签
        │
        └── Oswald 字体家族 (窄体无衬线几何体)
                 ├── headlineSmall  (16pt Medium) ── 用于紧凑卡片分类标题
                 └── bodySmall      (16pt SemiBold)── 用于高密度数据标签

* **Montserrat**：字形偏圆、几何结构开阔、字面率大，作为正文排版具备极高的人眼长时间阅读舒适度；
* **Oswald**：字形高耸紧凑（Condensed Font）、横向宽度窄，用于空间受限的分类标签和卡片头部，能在有限的逻辑像素宽度内完整呈现长标题而不发生截断换行。

2. 离线固化与字形预热物理收益
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
结合我们在第 1 节中剖析的 ``allowRuntimeFetching = false``，所有 GoogleFonts 字体资产在编译阶段直接转化为二进制字形轮廓（Glyph Outlines）嵌入安装包。
当 Flutter 引擎的 Skia / Impeller 在 GPU 光栅化线程中解析文字时，直接从本地内存映射（mmap）快速抽取贝塞尔矢量轮廓进行着色器渲染，彻底杜绝了字体下载网络延迟、字形抖动与首屏重排。

----------------------------------------------------------------------------------------

小结与给下一个对话的施工建议 (Summary & Next Step Advisory)
------------------------------------------------------------

* **本章核心产出**：
  至此，**【模块 01：Gallery 应用启动与全局架构基建】全部 3 节已全量深度完工并落盘**！彻底解构了启动时序、ModelBinding 状态分发、以及设计令牌、CIE 亮度对比度与双字体排版拓扑。
* **给下一个对话的施工建议**：
  下一个对话将正式进入 **【模块 02：多端自适应布局与顶层脚手架架构】** 的第一节：
  ``02_gallery_adaptive_scaffold/01_adaptive_breakpoints.rst``。
  我们将深入 ``cxyFork-gallery/lib/layout/adaptive.dart`` 源码，系统化推导小屏（<600px）、中屏（600~840px）与大屏（>840px）物理断点划分、DPI 逻辑像素映射、以及跨端视图分流执行流。
