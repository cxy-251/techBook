WHATWG, W3C, TC39, IETF, and the Standards Stack
=================================================

核心知识点
----------

* Web 标准不是单一规范，而是文档、DOM、语言、样式、网络、安全、可访问性和国际化等多层契约的组合。
* WHATWG 主要维护 HTML、DOM、Fetch、Streams 等浏览器核心平台行为，采用持续演进的 Living Standard 模式。
* W3C 覆盖 CSS、可访问性、国际化、Web 架构原则以及大量跨平台标准工作。
* TC39 负责 ECMAScript 语言本身，包括语法、对象模型、Promise、module、内建对象和语言执行语义。
* IETF 负责 HTTP、TLS、QUIC 等网络协议层契约，定义浏览器、代理、CDN 和服务器共同理解的传输语义。
* 阅读标准时先定位“当前对象属于哪一层”，再查对应规范；不要用语言规范解释网络失败，也不要用 HTTP 规范解释 Promise 调度。

关键路径
--------

一个典型页面行为可拆成：

``navigation → HTML document → DOM tree/event → ECMAScript execution → Fetch algorithm → HTTP semantics → TLS/QUIC transport → origin server``

标准定位顺序：

``对象/现象 → 所属层级 → 对应标准组织 → 规范对象与状态 → 浏览器实现 → 测试/运行证据``

典型映射：

* document、DOM event、Fetch、Streams → WHATWG；
* CSS、accessibility、internationalization → W3C 生态；
* Promise、module、async/await、语言内建对象 → TC39 / ECMAScript；
* method、status、header、cache semantics、TLS、QUIC → IETF。

概念辨析
--------

* **ECMAScript vs Web API**：``await`` 和 Promise 属于语言语义；``fetch``、DOM、Storage 属于浏览器宿主平台。
* **Fetch vs HTTP**：Fetch 决定浏览器如何构造、检查和暴露请求；HTTP 定义请求响应在网络参与者之间的协议语义。
* **WHATWG vs W3C**：两者不是简单竞争关系，而是覆盖 Web 平台不同对象和协作边界。
* **规范成熟度 vs API 可用性**：规范阶段、浏览器实现和跨浏览器测试是不同证据，不能互相替代。
* **标准组织名称 vs 架构边界**：记住组织名称不是目的，能把故障定位到正确契约层才是目的。

本章结论
--------

现代 Web 是标准栈，不是单规范。工程分析应先判断问题属于 document、DOM、CSS、ECMAScript、Fetch、HTTP 还是更底层协议，再进入对应标准和实现证据。掌握这种分层定位后，框架 API、浏览器行为和线上故障都可以还原到稳定的系统契约。