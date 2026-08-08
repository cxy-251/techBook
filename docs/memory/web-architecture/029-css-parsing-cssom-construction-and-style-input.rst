CSS Parsing, CSSOM Construction, and Style Input
===============================================

核心知识点
----------

* CSS 输入可以来自外部 stylesheet、``style`` 元素、inline style、constructed stylesheet 和运行时注入；它们最终都成为 style calculation 的输入。
* CSS parser 把文本转换成 selector、declaration、at-rule、value 等规则系统；解析成功并不代表最终视觉结果正确。
* CSSOM 是样式规则的运行时对象边界，JavaScript 可以读取或修改 ``CSSStyleSheet``、rule list 和 style declaration。
* 跨 origin stylesheet 可以参与渲染，但脚本读取其内部规则可能受到同源安全限制。
* 匹配当前媒体条件的关键 stylesheet 会阻塞首次稳定渲染，因为 layout/paint 需要可用的样式输入。
* class、attribute、custom property、stylesheet mutation 等动态变化会触发 style invalidation；影响范围决定后续重算成本。
* ``@import``、font、media/supports 条件会让样式输入继续依赖网络资源和运行时环境。

关键路径
--------

CSS 输入路径：

``HTML → stylesheet/style discovery → fetch/inline text → CSS parser → rule set → CSSOM → style readiness → style calculation``

运行时修改：

``JavaScript mutation → DOM/CSSOM state change → style invalidation → affected elements → recalculation``

首屏排查：

``关键可见元素 → matched rules → stylesheet source → discovery/fetch/parse → CSSOM readiness``

概念辨析
--------

* **CSS Text vs CSSOM**：前者是资源或源码；后者是浏览器当前持有的样式运行时对象状态。
* **解析成功 vs 规则生效**：规则可被 parser 接受，仍可能因 selector、cascade、media condition 或后续覆盖而不生效。
* **Render Blocking vs Parser Blocking**：stylesheet 主要阻塞稳定渲染；同步 script 才直接暂停 HTML parser。
* **CSSOM Mutation vs DOM Mutation**：前者改变规则系统，后者改变元素结构/属性；二者都可能触发样式失效。
* **样式输入 vs Computed Style**：CSSOM 保存候选规则，computed style 是下一阶段把竞争规则作用到具体元素后的结果。

本章结论
--------

CSS 是渲染系统的输入状态，不是最终像素。排查首屏、主题、动态样式与视觉错乱时，应沿“资源是否到达 → CSS 是否被解析 → CSSOM 当前是什么 → 哪些规则匹配 → 失效范围多大”逐层定位，再进入 computed style、layout 和 paint。