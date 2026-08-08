HTML as Semantic Document and Runtime Input
===========================================

核心知识点
----------

* HTML 同时是内容结构和浏览器运行时输入：它既描述文档语义，也驱动 DOM 构建、资源发现、默认交互、可访问性映射、表单提交和后续 hydration。
* 语义元素先于 CSS 与 JavaScript 提供行为基础。``a``、``button``、``form``、``input``、``main``、``nav``、``article``、heading 等元素会直接影响导航、键盘操作、辅助技术和机器理解。
* Attribute 不只是样式钩子。``href``、``name``、``alt``、``lang``、``type``、``rel``、``crossorigin``、``sandbox`` 等都会进入浏览器算法，改变请求、提交、安全、可访问性或资源调度。
* ``head`` 主要承载 document metadata、资源关系和机器可读控制信息；``body`` 主要承载用户可见内容与交互结构。
* HTML parser 会进行标准化错误恢复，因此“服务器输出的字符串”和“浏览器最终 DOM”可能不同；运行时判断应以实际 DOM 为准。
* Framework 模板、SSR、SSG 和 Server Component 最终都要落成 HTML/DOM 契约；框架不能替代浏览器对元素和 attribute 的原生语义。

关键路径
--------

基础文档路径：

``HTML bytes → HTML parser → DOM tree → semantic/default behavior → accessibility/resource/form/navigation paths``

资源与交互分支：

``head declarations → resource discovery / metadata``

``body semantics → focus / navigation / form / user interaction``

框架接管路径：

``Server/Build output → semantic HTML → Browser DOM → hydration/enhancement → runtime mutation``

判断 HTML 质量时，先检查它在无 JavaScript 条件下建立了什么结构和默认行为，再检查增强层接管了哪些责任。

概念辨析
--------

* **HTML source vs DOM**：HTML 是输入文本；DOM 是 parser 和运行时 mutation 后的对象树。
* **Semantic element vs styled ``div``**：前者自带角色、默认行为和平台契约；后者通常需要脚本和 ARIA 补齐。
* **Attribute vs CSS class**：class 主要参与选择器和样式；很多 attribute 会直接改变浏览器行为和协议路径。
* **``head`` vs ``body``**：前者主要定义文档身份、资源和控制面；后者主要定义用户内容与交互面。
* **HTML semantics vs framework component semantics**：组件名只存在于框架开发模型中；浏览器真正执行的是最终元素、属性和 DOM。

本章结论
--------

HTML 是现代 Web 的基础系统契约。它把服务器或构建产物转换成浏览器可执行的文档结构，并同时服务资源加载、导航、表单、可访问性和公开 Web 发现。语义越准确，平台承担的责任越多；语义越弱，JavaScript、框架、测试和恢复路径需要补偿的成本越高。