========================================================================
Chapter 13: CSS 解析、层叠继承与计算样式模型：从样式表到 ComputedStyle 拓扑
========================================================================

.. note:: 前置背景与认知承接
   前一章解构了 HTML 字节流解码、WHATWG 状态机分词、栈驱动树构建算法、领养机构容错机制（AAA）以及 Blink C++/V8 内部双向 DOM 内存拓扑。当 DOM 树在内存中构建就绪后，它仅表达了文档的拓扑结构与文本内容，并不包含任何视觉属性（如几何尺寸、绝对颜色、字体粗细与渲染图层）。要将抽象的 DOM 节点转化为屏幕上的像素网格，浏览器渲染引擎必须执行样式计算流水线（Style Calculation）。本章将深入 Blink 与 WebKit 内核微架构，系统剖析 CSS 词法解析、规则分桶（RuleSet）、从右向左的选择器匹配引擎、特异度（Specificity）代数计算、Cascade 层叠排序算法、六阶段值解析流程以及 C++ 只读 `ComputedStyle` 结构体的内存拓扑与共享缓存机制。

------------------------------------------------------------------------
13.1 CSS 词法分析、语法树与 CSSOM 内部数据结构
------------------------------------------------------------------------

与 HTML 极其复杂的容错树构建不同，CSS 的语法结构严密得多，其解析遵循 CSS Syntax Module Level 3 规范。当网络进程下载完 `<link rel="stylesheet">` 或解析器遇到 `<style>` 标签时，CSS 解析器会经历两级标准化流水线：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       CSS 样式表解析与对象模型构建流水线                |
   +-------------------------------------------------------------------------+

   [ 原始 CSS 文本流 (Raw CSS Text) ]
        |
        v
   [ 1. CSS 词法分词器 (CSSTokenizer) ]
        |  * 扫描并生成基础 Tokens: Ident, Function, At-Keyword, Hash, String,
        |    Dimension, Percentage, Number, Delim, Whitespace, Colon, Semicolon
        v
   [ 2. CSS 语法解析器 (CSSParserImpl / CSSPropertyParser) ]
        |  * 解析 @-rules (如 @media, @keyframes, @layer, @font-face)
        |  * 解析 Qualified Rules: 将选择器字符串编译为 CSSSelectorList
        |  * 解析 Declaration Block: 将属性键值对编译为 ImmutablePropertyValueSet
        v
   [ 3. 样式表内部对象模型 (blink::StyleSheetContents / CSSStyleSheet) ]
        |  * 挂载至 Document 树作用域
        v
   [ 4. 规则集索引与分桶 (RuleSet Indexing) ] ---> 送入样式匹配引擎

Blink 内核核心 CSS 数据结构解构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 Chromium Blink 源码（`third_party/blink/renderer/core/css/`）中，解析后的样式表被转化为高度优化的内存数据结构：

.. code-block:: cpp

   // Blink 内核 CSS 核心对象模型骨干设计
   namespace blink {
   class StyleSheetContents : public GarbageCollected<StyleSheetContents> {
    private:
       HeapVector<Member<StyleRuleBase>> rules_; // 包含 @-rules 与普通样式规则列表
   };

   class StyleRule : public StyleRuleBase {
    private:
       CSSSelectorList selector_list_;           // 解析后的选择器列表
       Member<const CSSPropertyValueSet> properties_; // 不可变的属性键值对集合
   };

   class CSSSelector {
    public:
       enum MatchType { kId, kClass, kTag, kPseudoClass, kPseudoElement, ... };
       enum RelationType { kSubSelector, kDescendant, kChild, kDirectAdjacent, kIndirectAdjacent };
    private:
       AtomicString value_;                      // 属性值 (如 class 名称、ID 字符串)
       uint32_t match_type_ : 8;
       uint32_t relation_ : 8;
       uint32_t bits_ : 16;                      // 缓存 Specificity 与伪类枚举
   };
   }

.. list-table:: Blink CSS 对象模型关键组件职责与内存特征
   :widths: 25 35 40
   :header-rows: 1
   :class: tight-table

   * - 核心数据结构
     - 所属命名空间与生命周期
     - 职责与性能优化机制
   * - **`StyleSheetContents`**
     - `blink::StyleSheetContents`（全局共享）
     - 纯净的 CSSOM 内部数据表示，多 Document / iframe 共享同一份不可变内存
   * - **`StyleRule`**
     - `blink::StyleRule`
     - 封装单一选择器组及其对应的样式声明集合（Property Set）
   * - **`CSSSelector`**
     - `blink::CSSSelector`（链表节点）
     - 表达原子选择器，通过 `relation_` 指针连接为复合选择器链条
   * - **`CSSPropertyValueSet`**
     - `blink::ImmutablePropertyValueSet`
     - 扁平压缩的只读属性数组，消除了动态哈希表的指针开销

------------------------------------------------------------------------
13.2 选择器匹配引擎：从右向左算法与规则分桶索引 (RuleSet)
------------------------------------------------------------------------

在大型前端工程中，全局样式表往往包含数万条选择器规则。若对 DOM 树中的每个元素都遍历全量规则进行匹配，整体时间复杂度将高达 $O(	ext{DOM Nodes} 	imes 	ext{CSS Rules})$，彻底引发页面卡死。

规则分桶机制 (RuleSet Bucket Indexing)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了在微秒级完成规则筛选，Blink 的 `RuleSet` 依据选择器的**最右侧关键选择器（Key Selector）**将规则进行哈希分桶：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       Blink RuleSet 核心规则分桶哈希表                  |
   +-------------------------------------------------------------------------+

   [ 待索引选择器示例 ]:
   Rule 1: `#header .nav-item a`       ---> 关键选择器是 'a'       -> 存入 Tag 桶: 'a'
   Rule 2: `.container > .active-btn`  ---> 关键选择器是 '.active-btn' -> 存入 Class 桶: 'active-btn'
   Rule 3: `div#main-content`          ---> 关键选择器是 '#main-content' -> 存入 ID 桶: 'main-content'
   Rule 4: `*`                         ---> 关键选择器是 '*'       -> 存入 Universal 通用桶

   +-------------------+-----------------------------------------------------+
   | 分桶类型          | 内部数据结构与查找策略                              |
   +-------------------+-----------------------------------------------------+
   | **ID 规则表**     | `HashMap<AtomicString, HeapVector<RuleData>>`       |
   | **Class 规则表**  | `HashMap<AtomicString, HeapVector<RuleData>>`       |
   | **Tag 规则表**    | `HashMap<AtomicString, HeapVector<RuleData>>`       |
   | **通用规则表**    | `HeapVector<RuleData>` (匹配所有元素，需严格控制数量)|
   +-------------------+-----------------------------------------------------+

从右向左 (Right-to-Left) 匹配算法的物理必然性
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

考虑选择器 `div.container ul > li.active` 与当前正在执行样式计算的目标 DOM 元素 `el`：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |             从左向右 (L-to-R) vs 从右向左 (R-to-L) 匹配算法对比         |
   +-------------------------------------------------------------------------+

   [ 方案 A: 从左向右匹配 (Top-Down) ]
   1. 从当前目标元素出发，必须递归向上遍历整棵 DOM 树寻找 `div.container`；
   2. 找到后，再向下递归寻找其所有子孙 `ul`，再找子 `li.active` 是否等于当前元素；
   * 缺陷: 遇到不匹配时会产生大量回溯搜索，计算复杂度失控！

   [ 方案 B: 从右向左匹配 (Bottom-Up - 现代引擎标准) ]
   1. 步骤 1 (关键选择器校验): 检查当前目标元素 `el` 是否拥有 class `active` 且标签为 `li`；
      -> 若不匹配，0 纳秒立即退出！直接淘汰 95% 以上无关规则！
   2. 步骤 2 (父级检查): 解引用 `el->parentElement`，单次指针判定其标签是否为 `ul`；
   3. 步骤 3 (祖先追溯): 沿 `parent_` 指针单向向上追溯，寻找包含 class `container` 的 `div`；
   * 收益: 绝大部分规则在第一步即被快速剔除，无需任何复杂树回溯。

选择器特异度 (Specificity) 严格代数计算
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当多个选择器同时匹配同一个 DOM 元素时，引擎依据三元组 $(A, B, C)$ 严格计算特异度权重（比较时按从左到右字典序强优先级比较，**绝对不存在低位累加进位到高位的情况**）：

.. math::

   	ext{Specificity} = (A, B, C)

.. list-table:: CSS 选择器特异度 (Specificity) 权重分配矩阵
   :widths: 15 35 50
   :header-rows: 1
   :class: tight-table

   * - 权重级别
     - 涵盖的选择器类型
     - 经典语法示例
   * - **$A$ 级 (最高权重)**
     - ID 选择器
     - `#main`, `#nav-bar`
   * - **$B$ 级 (次高权重)**
     - 类选择器、属性选择器、伪类
     - `.active`, `[type="text"]`, `:hover`, `:nth-child(2)`
   * - **$C$ 级 (基础权重)**
     - 类型选择器（标签名）、伪元素
     - `div`, `span`, `p`, `::before`, `::after`
   * - **零权重 (0, 0, 0)**
     - 通配符选择器、组合符号、`:where()`
     - `*`, `>`, `+`, `~`, `:where(.class)`（降低特异度为 0）
   * - **动态继承权重**
     - `:is()`, `:not()`, `:has()`
     - 取其参数列表中**特异度最高的选择器权重**

------------------------------------------------------------------------
13.3 级联层叠算法 (Cascade Order) 与 Cascade Layers 拓扑
------------------------------------------------------------------------

当来自不同来源（User Agent、开发者、用户自定义）、不同特异度及携带 `!important` 的样式规则共同作用于某一属性时，Blink 的 `ElementRuleCollector` 启动**级联层叠排序算法（The Cascade）**。

级联决胜的八级绝对优先级阶梯
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

根据 CSS Cascading and Inheritance Level 5 规范，样式属性的仲裁优先级从最高到最低严格排列如下：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     CSS 级联层叠决胜优先级绝对阶梯                      |
   +-------------------------------------------------------------------------+

   [ 优先级 1 ] -> 浏览器底层内置样式重要声明 (User Agent !important)
        |
        v
   [ 优先级 2 ] -> 用户自定义样式重要声明 (User !important)
        |
        v
   [ 优先级 3 ] -> 开发者样式重要声明 (Author !important: @layer 逆序 > 普通 !important)
        |
        v
   [ 优先级 4 ] -> CSS 动画中生成的运行态关键帧样式 (CSS Animations)
        |
        v
   [ 优先级 5 ] -> 开发者常规声明 (Author Normal):
        |          * 普通内联样式 (style="...")
        |          * @layer 声明层级 (根据 @layer 定义顺序正序排列)
        |          * 选择器特异度 Specificity (A, B, C)
        |          * 源码书写顺序 (Order of Appearance - 后声明者胜出)
        v
   [ 优先级 6 ] -> 用户自定义常规声明 (User Normal)
        |
        v
   [ 优先级 7 ] -> 浏览器底层默认样式常规声明 (User Agent Normal: 如 <div> display:block)
        |
        v
   [ 优先级 8 ] -> CSS 平滑过渡生成态属性 (CSS Transitions: 覆盖所有常规属性)

Cascade Layers (@layer) 拓扑分层微架构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

现代 CSS 引入了 `@layer` 显式层叠层，彻底解决了大型前端工程中第三方组件库与业务样式之间的“特异度军备竞赛（Specificity War）”：

.. code-block:: css

   /* 1. 显式声明全局层级拓扑优先级 */
   @layer reset, framework, components, utilities;

   @layer framework {
       /* 即使包含高特异度 ID，也优先让位于后续层级 */
       #app button.btn { background: blue; }
   }

   @layer utilities {
       /* 低特异度类选择器能够天然覆盖 framework 层的样式 */
       .bg-red { background: red; }
   }

- **层叠层决胜法则**：在普通声明中，后定义的层（如 `utilities`）天然战胜先定义的层（如 `framework`），**完全无视选择器内部的具体 Specificity 大小**；而在 `!important` 声明中，这一规则完全倒置（先定义的层中的 `!important` 具有更高优先级）。

------------------------------------------------------------------------
13.4 属性继承与 CSS 值解析的六阶段数据流
------------------------------------------------------------------------

从 CSS 文本中的一个原始字面量（如 `width: calc(100% - 20px)`），到最终 GPU 光栅化所需的绝对物理像素，属性值必须在渲染流水线中经历**严格的六阶段演进数据流**：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     CSS 属性值解析的六阶段演进数据流                    |
   +-------------------------------------------------------------------------+

   [ 1. 声明值 (Declared Value) ]
        |  * 收集全量匹配当前元素的原始 CSS 声明 (如 width: 50%, color: red)
        v
   [ 2. 层叠值 (Cascaded Value) ]
        |  * 经过 Cascade 级联决胜算法后胜出的唯一样式声明
        v
   [ 3. 指定值 (Specified Value) ]
        |  * 处理空缺: 若无层叠值，可继承属性取父节点值，不可继承属性取初始值 (Initial Value)
        v
   [ 4. 计算值 (Computed Value) - [Style 计算阶段产物: ComputedStyle] ]
        |  * 相对单位绝对化 (如 2em -> 32px, currentColor 转换为绝对 RGBA)
        |  * 能够不依赖页面排版布局即可解析的终态值 (绝对 URI、标准化数值)
        v
   [ 5. 使用值 (Used Value) - [Layout 排版计算阶段产物] ]
        |  * 依赖渲染树排版尺寸的最终值 (如 width: 50% 结合父级 800px 解析为 400px)
        v
   [ 6. 实际值 (Actual Value) - [Paint 绘制阶段产物] ]
        |  * 将浮点像素对齐到物理屏幕设备像素点阵 (如 400.33px 取整为 400px)

可继承属性 vs 不可继承属性
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **可继承属性（Inherited Properties）**：主要涉及排版与文字流（如 `color`, `font-family`, `font-size`, `line-height`, `visibility`, `cursor`）。若子节点未显式声明，`Specified Value` 阶段直接拷贝父节点的 `ComputedStyle` 属性指针；
- **不可继承属性（Non-Inherited Properties）**：涉及盒模型与布局（如 `margin`, `padding`, `border`, `width`, `height`, `display`, `position`, `transform`）。若未声明，强制取规范定义的初始默认值（`Initial Value`）。

------------------------------------------------------------------------
13.5 Blink C++ ComputedStyle 内存微架构与共享缓存
------------------------------------------------------------------------

样式计算流水线的最终输出，是为 DOM 树中每一个需要渲染的节点挂载一个只读的 `blink::ComputedStyle` 对象。

ComputedStyle 紧凑内存布局与写时复制 (Copy-on-Write)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

一个完整的 CSS 规范包含上千个属性。若每个 DOM 节点都以扁平结构体存储全部属性，单个节点将耗费数 KB 内存。Blink 采用了**两级引用压缩与写时复制架构**：

.. code-block:: cpp

   // Blink 内核 ComputedStyle 引用共享拓扑
   namespace blink {
   class ComputedStyle : public GarbageCollected<ComputedStyle> {
    private:
       // 1. 高频基础属性 (内联存储于结构体头部)
       uint32_t bitfields_;              // display, position, visibility, float 等枚举压缩
       Color color_;                     // 前景色
       Font font_;                       // 字体度量与字形描述符

       // 2. 低频罕见属性 (按功能分类为独立的数据子结构体指针)
       Member<StyleBoxData> box_data_;               // margin, padding, border 尺寸
       Member<StyleSurroundData> surround_data_;     // offset, z-index
       Member<StyleTransformData> transform_data_;   // 3D 变换矩阵、透视属性
       Member<StyleRareNonInheritedData> rare_data_; // mask, filter, backdrop-filter 等极罕见属性
   };
   }

- **结构体指针共享（Structural Sharing）**：当子节点继承父节点样式且未修改 `transform` 或 `filter` 时，子节点的 `transform_data_` 指针直接指向父节点的相同内存块，单节点内存开销被严格压制在几十字节以内。

样式共享缓存 (Style Sharing Cache) 与命中准则
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在大型长列表或类似商品卡片中，成百上千个同级 DOM 节点拥有完全相同的 Class、标签名和祖先链。Blink 维护了一个高速**样式共享缓存（Style Sharing Cache）**：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                  Blink Style Sharing Cache 快速命中判定                 |
   +-------------------------------------------------------------------------+

   [ 正在计算元素 Element B 的样式 ]
        |
        v
   [ 快速比对缓存中的前一元素 Element A ]:
        |  1. 标签名与命名空间完全一致? (tag_A == tag_B)
        |  2. class 列表与 ID 属性完全相同? (classList_A == classList_B)
        |  3. 属性键值集合完全相同? (attributes_A == attributes_B)
        |  4. 父节点的 ComputedStyle 指针完全一致? (parentStyle_A == parentStyle_B)
        |  5. 伪类状态一致 (未处于不同的 :hover / :active 状态)?
        v
   [ 判定成功: 100% 命中样式共享缓存! ]
        |
        +---> Element B 直接复用 Element A 的 ComputedStyle 内存指针!
        * 收益: 彻底跳过全量选择器匹配与级联计算，千节点长列表样式计算耗时降低 80%!

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章系统解构了 CSS 语法解析与 `StyleSheetContents` 对象模型、基于最右侧关键选择器的 `RuleSet` 分桶索引拓扑、从右向左的选择器匹配引擎、特异度三元组 $(A, B, C)$ 严格代数计算、Cascade 层叠决胜优先级阶梯与 `@layer` 分层、属性值解析的六阶段演进，以及 Blink `ComputedStyle` 结构体内存拓扑与样式共享缓存机制。

在 DOM 树与 CSSOM 成功结合生成完整的 `ComputedStyle` 树后，浏览器已经知道了每个节点的字体、颜色与外边距等属性，但依然不知道它们在视口中的绝对坐标与几何宽高。下一章我们将深入渲染流水线最核心的数学与几何计算阶段——**布局引擎核心、盒模型、Flex/Grid 算法与排版流水线**，深度剖析 LayoutObject/LayoutBox 树构建、块级/行内格式化上下文、Flexbox 弹性伸缩算法以及 Grid 网格二维空间求解的几何微架构。
