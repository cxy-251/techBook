Box Model, Normal Flow, Formatting Context, and Overflow
========================================================

核心知识点
----------

* 浏览器布局阶段处理的是 box tree；DOM 元素、文本、伪元素和 computed ``display`` 共同决定实际生成哪些 box。
* Box model 把单个视觉对象拆成 content、padding、border、margin 四层边界；``box-sizing`` 决定声明宽高对应 content box 还是 border box。
* Normal flow 是默认布局基线：block box 沿 block axis 排列，inline 内容在 line box 中排版和换行。复杂布局应先理解 normal flow，再判断 flex、grid、position 等如何改变它。
* Formatting context 是局部布局规则边界。BFC、inline formatting、flex formatting、grid formatting 等决定内部 box 如何相互影响，以及浮动、margin、overflow、尺寸计算如何传播。
* Overflow 描述内容超出 box 几何后的处理策略；``visible``、``hidden``、``clip``、``auto``、``scroll`` 会改变裁剪、滚动容器和 sticky/定位行为。
* Intrinsic size、min-content、max-content、replaced element 固有尺寸、文本换行和图片宽高都是布局输入；未知或迟到尺寸会引起溢出和布局移动。

关键路径
--------

从文档到几何：

``DOM → Computed Style → Box Generation → Formatting Context → Layout Geometry → Overflow/Scroll → Paint/Hit Testing``

单个 box 的局部几何：

``content → padding → border → margin``

布局排查顺序：

``是否生成 box → box 类型/display → formatting context → intrinsic/min/max size → overflow/scroll container → 最终几何``

概念辨析
--------

* **DOM Tree vs Box Tree**：DOM 表达文档对象关系；box tree 表达参与布局的视觉结构，二者不一一对应。
* **Content Box vs Border Box**：前者只含内容区；后者包含 padding 与 border。``box-sizing: border-box`` 让声明尺寸更接近视觉边界。
* **Normal Flow vs Formatting Context**：normal flow 是默认排布原则；formatting context 是某个局部区域采用的具体布局规则。
* **Margin vs Padding**：margin 处理元素外部间距，通常不扩展自身命中区域；padding 属于元素内部边界并扩大可视/可点击盒。
* **Overflow Hidden vs Clip**：二者都能裁剪内容，但滚动容器语义不同；这会影响滚动、sticky 和脚本测量。
* **``display: none`` vs ``visibility: hidden`` vs ``display: contents``**：分别对应移出 box tree、保留几何但不绘制、移除自身 principal box 而保留子内容参与布局。

本章结论
--------

CSS 布局问题应从 box tree 和几何边界开始，而不是从视觉结果倒猜。先确认元素生成什么 box、进入什么 formatting context、在 normal flow 中如何占位，再检查 intrinsic size 与 overflow，才能稳定解释宽高、换行、滚动、裁剪和命中区域问题。