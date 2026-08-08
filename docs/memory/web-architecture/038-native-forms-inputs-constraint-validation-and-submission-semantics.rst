Native Forms, Inputs, Constraint Validation, and Submission Semantics
=====================================================================

核心知识点
----------

* 原生 ``form`` 是 Web 平台内置的 mutation boundary：浏览器能在没有应用 JavaScript 的情况下完成输入保存、键盘提交、约束校验、数据构造、编码、请求和导航。
* 表单控件先于 JavaScript 持有用户输入状态。``input``、``select``、``textarea``、checkbox、radio、file 和 submitter 的当前状态共同决定提交数据。
* 提交 shape 由 ``name``、``value``、控件状态、submitter、``action``、``method`` 和 ``enctype`` 共同决定；没有 ``name``、被 disabled 或不满足 successful control 条件的字段不会按普通路径提交。
* GET 适合把读取型表单状态写入 URL，便于分享、刷新和缓存；POST 适合产生副作用的提交。文件上传通常需要 ``multipart/form-data``。
* Constraint Validation 是浏览器级用户反馈，不是可信安全边界。``required``、``type``、``min``、``pattern`` 等能阻止普通原生提交，但请求仍可被绕过或伪造。
* 服务端拥有最终验证、鉴权、幂等、文件安全、业务规则和持久化结果。客户端校验只能改善交互效率。
* JavaScript 拦截 ``submit`` 后，会接管 pending、错误展示、重复提交、URL/history、恢复和失败回退中的一部分浏览器责任。

关键路径
--------

原生提交：

``User input → form controls → submitter → constraint validation → entry list/FormData → method + enctype → HTTP request → server validation/auth → durable result → redirect/page response``

GET 表单：

``controls → query encoding → URL → navigation/cache/shareable state``

增强提交：

``submit event → preventDefault → FormData/fetch/action → pending UI → server result → cache/UI update or fallback``

可信边界：

``browser validation → convenience only``

``server validation + authorization → trusted mutation decision``

概念辨析
--------

* **Control state vs application state**：控件已经拥有运行时 value/checked/file 状态；框架 state 是另一层镜像或控制模型。
* **``disabled`` vs ``readonly``**：disabled 通常不参与提交和约束校验；readonly 通常仍会提交当前值。
* **GET vs POST**：GET 更适合读取和 URL 状态；POST 更适合 mutation。method 是请求语义，不只是编码方式。
* **Constraint Validation vs Server Validation**：前者服务用户反馈；后者决定数据是否可信、是否有权限写入。
* **Native submit vs JavaScript interception**：原生路径由浏览器管理导航与恢复；拦截后应用必须补齐相应状态机。
* **FormData vs durable state**：FormData 只是一次请求输入；最终业务事实由服务器和持久化系统拥有。

本章结论
--------

表单是浏览器把用户意图变成 HTTP mutation 的完整原生路径。架构上应优先保留正确的 ``form``、控件、``name``、method 和 validation 语义，再用 JavaScript 增强反馈与局部更新；任何增强都不能替代服务端验证、授权和持久化一致性。