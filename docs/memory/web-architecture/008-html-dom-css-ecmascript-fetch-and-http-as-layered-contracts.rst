HTML, DOM, CSS, ECMAScript, Fetch, and HTTP as Layered Contracts
================================================================

核心知识点
----------

* HTML、DOM、CSS、ECMAScript、Fetch、HTTP 分别负责不同输入、状态和失败语义，真实页面行为来自这些契约连续交付。
* HTML 把响应字节和标记转换为 document，并触发样式、脚本、图片等资源发现与加载。
* DOM 是 document 与脚本之间的对象边界，负责节点关系、属性、mutation、event 和部分取消语义。
* CSS 接收 DOM、选择器、媒体条件和样式规则，产生 computed style，并进一步影响 layout、paint 和 composite。
* ECMAScript 定义语言求值、对象、函数、module、Promise、async/await 和异常传播；DOM、Fetch 等属于宿主能力。
* Fetch 把脚本请求接入浏览器的 credentials、CORS、redirect、Service Worker、安全策略和 stream 管线。
* HTTP 定义 method、status、header、representation、cache 等跨浏览器、代理、CDN 与服务器共享的协议语义。

关键路径
--------

页面从导航到数据更新的典型路径：

``HTTP HTML response → HTML parser → DOM → CSS calculation/rendering → ECMAScript execution → DOM event → Fetch → HTTP → server/CDN → Response → ECMAScript → DOM mutation``

排查时按层查证：

``输入是否正确 → 当前契约产生了什么对象/状态 → 是否成功交给下一层 → 失败由哪层报告``

例如点击后数据不更新：

``节点存在 → event listener 已绑定 → ECMAScript callback 执行 → Fetch 请求成立 → HTTP 响应正确 → body 解析成功 → DOM mutation 成功``

概念辨析
--------

* **HTML vs DOM**：HTML 是文档输入和解析语义；DOM 是解析结果对脚本暴露的对象模型。
* **DOM state vs CSS result**：DOM 保存结构和内容；CSS 决定这些对象如何参与视觉计算。
* **ECMAScript vs Browser Runtime**：语言规范定义代码如何计算；浏览器宿主提供 document、network、storage 等能力。
* **Fetch failure vs HTTP failure**：Fetch Promise reject 常表示网络、策略或请求管线失败；HTTP 404/500 仍然可能得到正常 ``Response``。
* **HTTP cache semantics vs 应用缓存**：HTTP 缓存属于协议层；框架缓存、query cache 属于更高层状态副本。

本章结论
--------

Web 页面不是“一段前端代码”，而是一串层层交付的契约。分析页面结构、显示、脚本、请求或缓存问题时，应明确当前状态由 HTML、DOM、CSS、ECMAScript、Fetch 还是 HTTP 拥有，再沿相邻边界检查输入、输出和失败证据。