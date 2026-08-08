Forms as the Original Web Mutation Boundary
===========================================

核心知识点
----------

* ``form`` 是 Web 原生写入边界：控件承载用户输入，浏览器依据 ``action``、``method``、``enctype``、submitter 和控件 ``name`` 构造请求，服务器在可信边界内决定是否真正改变状态。
* 提交首先是浏览器行为，再可能成为框架事件。按回车、点击 submitter 或 ``requestSubmit()`` 都能进入原生提交流程；JavaScript 调用 ``preventDefault()`` 后，才把网络、等待、错误和导航责任转交给应用。
* mutation 从控件开始。输入值、checkbox、file、hidden field、submitter intent 都只是用户意图，均可被篡改；服务器必须重新验证身份、权限、业务规则和数据一致性。
* 正确的 form 天然支持渐进增强：没有 JavaScript 时仍能提交和得到页面级结果；有 JavaScript 时再增加 pending、局部刷新、乐观反馈和客户端校验。
* server action、route action、form action 只是对这条稳定 Web 路径的重新包装，不改变 ``Browser → HTTP Request → Trusted Server → Durable State`` 的基本边界。

关键路径
--------

``User edits controls → Browser owns control state → Submit intent → Constraint validation → Successful controls/FormData → HTTP request → Server validation/auth → Business mutation/transaction → Error, response, or redirect → Browser-visible result``

排查写入问题时先看控件是否有正确 ``name``、是否属于目标 form、是否被 disabled，再看实际 submitter、``method/action/enctype``，最后检查服务器 action 与数据库写入；不要直接从组件 state 推断服务器收到的请求。

概念辨析
--------

* **Form vs component state**：form 是跨 browser/server 的提交协议边界；component state 只是当前客户端 runtime 中的交互状态。
* **Client validation vs server validation**：前者优化反馈，后者建立信任；客户端通过不代表写入合法。
* **submit event vs submission**：``submit`` 事件可被拦截；默认 submission 是浏览器后续执行的请求与导航行为。
* **Hidden field vs trusted state**：hidden 只表示不可见输入，不具备可信性；tenant、price、role 等关键事实仍需服务器重新解析。
* **Progressive enhancement vs client-only form**：前者保留原生可用路径，后者把完成任务完全绑定到 JavaScript runtime。

本章结论
--------

Form 的核心价值不是“收集几个字段”，而是把用户意图稳定地转换成一次可观察的 HTTP mutation。设计任何现代写入流程时，先保证原生 form/request/server 路径成立，再决定框架在哪些位置增强它。