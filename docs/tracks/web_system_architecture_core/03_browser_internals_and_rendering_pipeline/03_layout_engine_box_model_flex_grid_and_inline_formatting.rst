========================================================================
Chapter 14: 布局引擎核心、盒模型与排版流水线：从 LayoutTree 到 Flexbox 与 Grid 空间求解
========================================================================

.. note:: 前置背景与认知承接
   前一章解构了 CSS 语法解析、RuleSet 分桶索引、从右向左的选择器匹配引擎、特异度代数计算、Cascade 级联排序算法以及 Blink 内部 `ComputedStyle` 的紧凑内存结构。当样式计算完成后，渲染引擎为 DOM 树中的有效节点绑定了只读的计算样式。然而，`ComputedStyle` 仅定义了视觉属性与相对度量，节点在视口中的几何坐标 $(x, y)$ 与物理宽高 $(w, h)$ 仍属未知。要将样式声明转化为具体的屏幕几何空间占据，浏览器渲染引擎必须启动**布局流水线（Layout Pipeline / Reflow）**。本章将深入 Blink 内核 LayoutNG 架构，系统剖析从 DOM+ComputedStyle 派生 LayoutTree 的映射法则、盒模型物理边界与外边距折叠代数规则、BFC 与 IFC 格式化上下文生成机理、Flexbox 一维弹性伸缩算法的数学解算，以及 CSS Grid 二维网格轨道尺寸计算（Track Sizing Algorithm）的多轮迭代空间求解模型。

------------------------------------------------------------------------
14.1 布局引擎微架构：从 LayoutTree 构建到 LayoutNG 不可变片段
------------------------------------------------------------------------

在渲染流水线中，**布局（Layout）** 的职责是为每一个需要参与视觉呈现的元素计算其几何包围盒（Bounding Box），即确定其在二维（或局部三维）屏幕坐标系中的确切位置与尺寸。

DOM 树到 LayoutTree 的非对称映射拓扑
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

初学者常误以为 LayoutTree 与 DOM 树是 1:1 的直接镜像。在工业级浏览器内核中，两者存在显著的非对称映射关系：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       DOM 树到 LayoutTree 的映射与分化                  |
   +-------------------------------------------------------------------------+

   [ DOM 树节点 ]                            [ LayoutTree 节点 (LayoutObject) ]
   ---------------------------------------------------------------------------
   1. `<div style="display:none">`      --->   [ 无 (不生成任何 LayoutObject) ]
   2. `<head>`, `<script>`, `<style>`   --->   [ 无 (非渲染节点，被直接过滤) ]
   3. `<div style="display:contents">`  --->   [ 无 LayoutObject，但其子节点正常挂载 ]
   4. `<div class="btn">` + `::before`  --->   [ LayoutBlockFlow (div) ]
                                                    |-- [ LayoutInline (::before 伪元素) ]
                                                    +-- [ LayoutText ("Button Text") ]
   5. `<div>Inline 1 <p>Block</p> Inline 2</div>`
        |
        +---> 生成匿名块级盒 (Anonymous Block Box) 修复拓扑断裂:
              [ LayoutBlockFlow (div) ]
                  |-- [ Anonymous LayoutBlockFlow ] -> [ LayoutText ("Inline 1") ]
                  |-- [ LayoutBlockFlow (p) ]       -> [ LayoutText ("Block") ]
                  +-- [ Anonymous LayoutBlockFlow ] -> [ LayoutText ("Inline 2") ]

.. list-table:: DOM 节点与 LayoutObject 映射类型对比
   :widths: 25 35 40
   :header-rows: 1
   :class: tight-table

   * - CSS / DOM 声明
     - LayoutTree 内部表示
     - 内存与几何调度行为
   * - `display: none`
     - 不生成 `LayoutObject`
     - 彻底从渲染管线剔除，不占空间，不触发绘制
   * - `visibility: hidden`
     - 正常生成 `LayoutObject`
     - **完整参与布局计算并占据物理空间**，仅在 Paint 阶段跳过绘制
   * - `display: contents`
     - 自身不生成盒，子元素直连
     - 自身盒模型被抹平，子节点提升为与父级同层的 Layout 节点
   * - 匿名块级盒 (`Anonymous`)
     - `LayoutBlockFlow` (IsAnonymous)
     - 当行内元素与块级元素混合为兄弟节点时，包裹行内节点以维持 BFC 结构

Blink LayoutNG 架构演进：从可变内存树到不可变 PhysicalFragment
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

早期 WebKit/Blink 的布局引擎采用**就地可变（In-Place Mutation）**模式：每个 `LayoutObject` 内部直接持有 `x, y, width, height` 字段，排版算法在树遍历过程中递归修改这些变量。这种设计导致多线程并行布局极难实现、增量缓存容易出现脏数据污染，且处理 CSS 分栏（Multi-column）与分页打印等“一个 DOM 节点对应多个物理碎片”的场景时异常复杂。

Chromium 推出的 **LayoutNG** 从根本上重构了布局引擎的微架构：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     Blink LayoutNG 不可变函数式布局流水线               |
   +-------------------------------------------------------------------------+

   [ 输入 1: NGBlockNode (待排版布局节点) ] + [ 输入 2: NGConstraintSpace (外部几何约束) ]
        |
        v
   [ 布局算法执行 (BlockLayoutAlgorithm / FlexLayoutAlgorithm / GridLayoutAlgorithm) ]
        |  * 纯函数式计算，完全无副作用，不修改输入节点本身！
        v
   [ 输出: NGLayoutResult (不可变布局结果对象) ]
        |
        +---> 包含: NGPhysicalBoxFragment (不可变的物理几何碎片)
                 |-- Offset: 相对父容器的绝对 (x, y) 物理偏移量
                 |-- Size: 确定的 (width, height) 物理像素尺寸
                 |-- Baselines: 文本基线数据
                 +-- Children: 子级 NGPhysicalFragment 列表

- **只读不可变性（Immutability）**：`NGPhysicalBoxFragment` 一旦生成即完全只读，主线程布局完成后可安全传递给合成器与绘制流水线，彻底杜绝了并发读写的数据竞争；
- **自适应缓存（Layout Caching）**：若下一次 Reflow 时，父容器传入的 `NGConstraintSpace`（可用宽度、可用高度、百分比基准）与上次完全一致，节点直接复用已有的 `NGLayoutResult`，排版耗时瞬间归零（0ms）。

------------------------------------------------------------------------
14.2 CSS 盒模型微架构与外边距折叠 (Margin Collapsing)
------------------------------------------------------------------------

布局引擎的基本几何单元是**CSS 盒模型（CSS Box Model）**。每个盒模型由内向外由四层连续矩形区域构成：**Content Box** $	o$ **Padding Box** $	o$ **Border Box** $	o$ **Margin Box**。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       标准盒模型四层矩形几何拓扑                        |
   +-------------------------------------------------------------------------+

   +-------------------------------------------------------------------------+
   | Margin Box (外边距区: 控制与其他元素的几何间隔，透明)                   |
   |   +-----------------------------------------------------------------+   |
   |   | Border Box (边框区: 边框线、背景图与背景色绘制边界)             |   |
   |   |   +---------------------------------------------------------+   |   |
   |   |   | Padding Box (内边距区: 内容与边框的缓冲区)              |   |   |
   |   |   |   +-------------------------------------------------+   |   |   |
   |   |   |   | Content Box (内容区: 文本、图片、子盒排版空间)  |   |   |   |
   |   |   |   +-------------------------------------------------+   |   |   |
   |   |   +---------------------------------------------------------+   |   |
   |   +-----------------------------------------------------------------+   |
   +-------------------------------------------------------------------------+

box-sizing 与物理几何尺寸推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: `box-sizing` 对布局几何尺寸解析的代数映射
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 盒模型模式
     - CSS `width` 属性的物理绑定区域
     - 元素占据的总屏幕物理宽度 ($	ext{Total Width}$)
   * - **`content-box` (标准默认)**
     - 仅绑定 $	ext{Content Box}$ 的宽度
     - $	ext{Total} = 	ext{width} + 	ext{Padding}_{	ext{L+R}} + 	ext{Border}_{	ext{L+R}} + 	ext{Margin}_{	ext{L+R}}$
   * - **`border-box` (现代标准)**
     - 绑定到 $	ext{Border Box}$（包含内容、内边距与边框）
     - $	ext{Total} = 	ext{width} + 	ext{Margin}_{	ext{L+R}}$

外边距折叠 (Margin Collapsing) 的严格代数判定规则
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在普通文档流（In-Flow Block Layout）中，垂直方向上的两个或多个相邻外边距会合并为单一外边距。**水平方向的外边距绝对不发生折叠！**

外边距折叠触发的三大几何场景：

1. **相邻兄弟元素（Adjacent Siblings）**：上一个块级盒的 `margin-bottom` 与下一个块级盒的 `margin-top` 相遇；
2. **父元素与首/尾子元素（Parent and First/Last Child）**：当父盒与子盒之间没有 `border`、`padding`、行内内容或 BFC 阻断时，子盒的 `margin-top` 会“穿透”溢出并与父盒的 `margin-top` 折叠；
3. **空块级盒自折叠（Empty Blocks）**：当一个块盒没有 `border`、`padding`、高度（`height: 0` / `min-height: 0`）且无子内容时，其自身的 `margin-top` 与 `margin-bottom` 相互折叠。

折叠结果的代数求解公式
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

设参与折叠的外边距集合为 $M = \{m_1, m_2, \dots, m_k\}$：

.. math::

   M_{	ext{collapsed}} = \max(\{m \in M \mid m \ge 0\} \cup \{0\}) - \left| \min(\{m \in M \mid m < 0\} \cup \{0\}) \right|

- **全部为正数**：取其中的最大值；
- **全部为负数**：取绝对值最大的负数（即最小值）；
- **正负混合**：取最大正边距减去绝对值最大的负边距。

------------------------------------------------------------------------
14.3 格式化上下文机制：BFC 隔离沙箱与 IFC 文本排版管线
------------------------------------------------------------------------

格式化上下文（Formatting Context）是 W3C 规范中定义排版规则的独立物理空间。在该空间内部，子盒按照特定的几何规则进行排列，且与外部空间相互隔离。

块格式化上下文 (Block Formatting Context - BFC)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

BFC 是浏览器排版中的**独立布局沙箱**。BFC 内部的元素无论如何排列，绝不会在几何上影响到外部的元素，反之亦然。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       BFC 核心物理特性与经典应用场景                    |
   +-------------------------------------------------------------------------+

   [ 特性 1: 绝对阻断外边距穿透与折叠 ]
   * 属于不同 BFC 的两个相邻盒之间，垂直外边距绝不发生折叠！

   [ 特性 2: 闭合内部浮动元素 (清除浮动 / Clearfix) ]
   * 计算 BFC 高度时，浮动元素 (Float Boxes) 的物理高度必须被全量计入，
     彻底杜绝父容器高度塌陷问题！

   [ 特性 3: 排除外部浮动侵入 (Avoid Overlapping Floats) ]
   * BFC 盒子的 border-box 绝不会与外部同层浮动盒重叠，天然形成两栏自适应布局！

.. list-table:: 触发创建 BFC 的现代条件矩阵
   :widths: 30 70
   :header-rows: 1
   :class: tight-table

   * - 触发属性类别
     - 具体声明组合
   * - **根元素**
     - 文档根节点 `<html>`
   * - **独立流根属性 (现代首选)**
     - **`display: flow-root`**（专为无副作用创建 BFC 设计）
   * - **浮动与绝对定位**
     - `float: left / right`；`position: absolute / fixed`
   * - **溢出隐藏机制**
     - `overflow: hidden / auto / scroll / clip`（非 `visible`）
   * - **弹性与网格容器**
     - `display: flex / inline-flex`；`display: grid / inline-grid`
   * - **表格与多列容器**
     - `display: table-cell / table-caption`；`column-span: all`
   * - **容器隔离属性**
     - `contain: layout / content / paint`

行内格式化上下文 (Inline Formatting Context - IFC) 与文本排版管线
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

IFC 负责管理行内级盒子（Inline-level Boxes）与文本节点的水平排版流：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       IFC 文本排版与行盒 (Line Box) 流水线              |
   +-------------------------------------------------------------------------+

   [ 原始文本字符串 + 字体描述符 ]
        |
        v
   [ 1. 文本塑形引擎 (Text Shaping Engine - 如 HarfBuzz) ]
        |  * 依据 OpenType 字形表解析连字 (Ligatures)、字距调整 (Kerning)
        |  * 测量字形度量 (Glyph Metrics): Advance Width, Ascent, Descent
        v
   [ 2. 自动折行断句算法 (Line Breaking - Unicode UAX #14) ]
        |  * 沿行进方向累加宽度，超出包含块宽度时寻找断行点 (Break Opportunity)
        v
   [ 3. 构建行盒 (Line Box Construction) ]
        |  * 单行内部包含多个 InlineBox 与 TextFragment
        |  * 行盒高度由内部最高元素的顶边界与最低元素的底边界决定
        v
   [ 4. 垂直对齐微调 (Vertical Alignment) ]
        |  * 依据 baseline, top, bottom, middle 计算各子片段的垂直偏移

- **幽灵空白节点（Strut / Ghost Node）**：在 IFC 中，每个行盒的起始处都存在一个具有当前字体基线与度量、但宽度为 0 的不可见基准结构（Strut）。这解释了为何在一个包含行内图片 `<img>` 的容器底部，天然存在 $3	ext{px} \sim 5	ext{px}$ 无法消除的间隙（图片底边默认对齐于 Strut 的文字基线 Baseline，基线下方留有字体 Descent 空间；给图片设置 `display: block` 或 `vertical-align: bottom` 可彻底闭合该间隙）。

------------------------------------------------------------------------
14.4 Flexbox 一维弹性伸缩布局算法数学求解
------------------------------------------------------------------------

Flexbox 专为一维空间（沿单一主轴）的尺寸分配与对齐设计。其排版算法可抽象为严密的五阶段数学求解模型：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       Flexbox 一维排版算法五阶段状态机                  |
   +-------------------------------------------------------------------------+

   [ 阶段 1: 确定主轴 (Main Axis) 与交叉轴 (Cross Axis) 映射 ]
        |  * flex-direction: row (主轴=水平) vs column (主轴=垂直)
        v
   [ 阶段 2: 计算各 Flex Item 的假设主轴尺寸 (Hypothetical Main Size) ]
        |  * 依据 flex-basis, width, min-width, max-width 夹紧求得基准尺寸
        v
   [ 阶段 3: 收集 Flex 行并计算剩余可用自由空间 (Free Space) ]
        |  * FreeSpace = ContainerMainSize - Sum(ItemHypotheticalMainSizes)
        v
   [ 阶段 4: 执行弹性分配 (Flex Grow / Flex Shrink 空间求解) ]
        |
        +-- [ 若 FreeSpace > 0 (正剩余空间) ] ---> 执行 flex-grow 扩张分配
        |
        +-- [ 若 FreeSpace < 0 (溢出负空间) ] ---> 执行 flex-shrink 加权收缩
        v
   [ 阶段 5: 交叉轴对齐与多行排布 (Cross Axis Alignment) ]
        |  * 依据 align-items, align-self, align-content 确定交叉轴坐标

弹性扩张 (flex-grow) 线性分配模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当容器存在富余空间 $\Delta S > 0$ 时，各子项依据其 `flex-grow` 权重瓜分富余空间：

.. math::

   	ext{GrowFactor}_i = \frac{	ext{flex-grow}_i}{\sum_{j=1}^{n} 	ext{flex-grow}_j}

.. math::

   	ext{ActualMainSize}_i = 	ext{HypotheticalSize}_i + \Delta S 	imes 	ext{GrowFactor}_i

弹性收缩 (flex-shrink) 加权抗收缩模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当容器空间不足 $\Delta S < 0$ 时，W3C 规范**并未采用简单的权重算术分配，而是引入了包含基础尺寸权重的“加权收缩模型”**。这是为了防止大尺寸元素与小尺寸元素收缩相同的绝对像素导致小元素直接缩为 0：

1. **计算全行总收缩权重标量（Scaled Shrink Factor）**：

   .. math::

      W_{	ext{shrink}} = \sum_{j=1}^{n} \left( 	ext{flex-shrink}_j 	imes 	ext{flex-basis}_j \right)

2. **计算单个子项应承担的负空间收缩量**：

   .. math::

      	ext{ShrinkAmount}_i = |\Delta S| 	imes \frac{	ext{flex-shrink}_i 	imes 	ext{flex-basis}_i}{W_{	ext{shrink}}}

3. **终态尺寸推导**：

   .. math::

      	ext{ActualMainSize}_i = 	ext{flex-basis}_i - 	ext{ShrinkAmount}_i

------------------------------------------------------------------------
14.5 CSS Grid 二维网格系统与轨道尺寸解析算法 (Track Sizing Algorithm)
------------------------------------------------------------------------

CSS Grid 是 Web 平台上唯一真正的**二维显式布局系统**，能够同时控制行（Rows）与列（Columns）的交叉几何流。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       CSS Grid 网格系统核心拓扑概念                     |
   +-------------------------------------------------------------------------+

              Grid Line 1          Grid Line 2          Grid Line 3
                   |                    |                    |
                   v                    v                    v
      Grid Line 1 +--------------------+--------------------+
                  |                    |                    |  <-- Grid Track (Row 1)
                  |    Grid Cell (1,1) |    Grid Cell (1,2) |
      Grid Line 2 +--------------------+--------------------+
                  |                                         |
                  |         Grid Area (跨越 2 列的合并区域)  |  <-- Grid Track (Row 2)
      Grid Line 3 +-----------------------------------------+
                  ^                                         ^
                  |---------- Grid Track (Column 1) --------|

W3C Grid 轨道尺寸计算算法 (Track Sizing Algorithm) 四阶段
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Grid 布局的计算核心是求解每个轨道（Track）的最终物理像素宽度与高度。算法通过四轮严格的约束传播迭代完成求解：

.. list-table:: CSS Grid 轨道尺寸求解四阶段算法
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 求解阶段
     - 算法执行目标
     - 处理的尺寸指令与约束
   * - **阶段 1: 初始化轨道基准**
     - 为每个轨道建立最小基准尺寸（Base Size）与增长上限（Growth Limit）
     - 固定像素（`100px`）、百分比（`30%`）、`minmax(min, max)` 初始化
   * - **阶段 2: 固有尺寸解析 (Intrinsic Tracks)**
     - 遍历所有网格项，基于内容尺寸反向推导自适应轨道的空间需求
     - 解析 `min-content`（最小不折行词宽）、`max-content`（全展开宽度）、`fit-content()`
   * - **阶段 3: 最大化扩展轨道**
     - 若网格容器存在固定总尺寸且存在剩余空间，等比扩大可增长轨道的 Base Size
     - 消除非 `fr` 轨道的空间空隙
   * - **阶段 4: 弹性轨道分配 (Flexible Tracks: `fr`)**
     - 计算剩余可用网格空间，依据 `fr` 比例分配最终宽度
     - 1. $	ext{FreeSpace} = 	ext{ContainerSize} - \sum 	ext{NonFlexBaseSizes}$；2. 单个 `fr` 对应像素值：$P_{	ext{fr}} = \frac{	ext{FreeSpace}}{\sum 	ext{fr}}$

子网格 (Subgrid) 跨层级对齐微架构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

传统 Grid 中，子元素的子元素无法对齐到祖父级网格线。**CSS Subgrid（`grid-template-columns: subgrid`）** 允许嵌套网格直接继承父网格的轨道定义与对齐参数，由浏览器布局引擎将嵌套网格项直接提升至全局单一约束求解器中统一排版，彻底消除了深层嵌套 UI 组件的对齐开销。

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章深入剖析了从 DOM+ComputedStyle 构建 LayoutTree 的非对称映射机制、Blink LayoutNG 不可变 PhysicalFragment 函数式架构、标准与替代盒模型几何计算、外边距折叠严格代数公式、BFC 隔离沙箱与 IFC 文本排版流水线，以及 Flexbox 一维弹性伸缩与 CSS Grid 轨道尺寸算法的数学求解模型。

当布局引擎精确计算出页面中所有元素的绝对几何坐标 $(x, y, w, h)$ 后，渲染流水线将进入将几何边界转化为可视化绘制指令的阶段。下一章我们将深入现代浏览器渲染架构的核心进阶领域——**绘制流水线、属性树构建与硬件加速图层合成：Paint、Property Trees 与 Layer Compositing**，深度解构 DisplayList 绘制记录、四棵属性树（Transform, Clip, Effect, Scroll）如何实现零主线程重排的高性能滚动与动画合成。
