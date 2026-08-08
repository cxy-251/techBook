Native Submission, Encoding, Redirect, and Browser Behavior
============================================================

核心知识点
----------

* 原生提交由浏览器根据 form state 构造请求：成功控件、submitter、``method``、``action``、``enctype`` 和 ``target`` 共同决定最终 HTTP message。
* ``GET`` 更适合搜索、筛选、分页等可分享、可刷新、可回放的读取状态；``POST`` 更适合写入意图。方法语义必须和服务器副作用一致，不能让 ``GET`` 暗含删除、扣款等 mutation。
* ``application/x-www-form-urlencoded`` 适合普通字段；``multipart/form-data`` 适合文件与混合字段；编码选择决定请求 body、``Content-Type``、服务器解析器和资源限制。
* Redirect-After-Post 把一次写入转成稳定读取状态。成功后返回 ``303 See Other``，浏览器再 ``GET`` 最终资源，可降低刷新重放 POST 的风险并让 history/URL 更符合用户预期。
* 浏览器 autofill、password manager、输入类型、历史恢复和原生失败页都属于表单体验的一部分；应用接管提交后不能假设这些平台能力不存在。

关键路径
--------

``Control state + submitter → Browser builds entry list → method/action/enctype → GET query or POST body → Server validates and mutates → 303 Location → Browser GETs stable result URL → History/refresh/back operate on result``

文件上传故障应沿 ``control → multipart encoding → request size/proxy limit → server parser → storage`` 检查；普通字段缺失则先检查 ``name``、disabled、submitter 和编码，而不是先怀疑业务 handler。

概念辨析
--------

* **GET query vs POST body**：前者天然进入 URL 公共状态，后者表达提交意图；二者不是“参数放哪里”的纯格式差异。
* **302/303 vs 307/308**：``303`` 明确让 POST 结果进入 retrieval request；``307/308`` 保留原 method，错误用于成功页可能导致 mutation 被再次发送。
* **URL encoding vs multipart**：前者是键值序列化，后者保留分段、文件名和文件字节边界。
* **Browser history vs server state**：history 记录导航位置，不证明 mutation 是否执行；服务器与数据库才拥有写入事实。
* **Autofill vs application state**：浏览器可在应用事件之外恢复字段值，表单逻辑不能只依赖框架内部 state 推断当前控件值。

本章结论
--------

原生表单提交已经定义了从控件到 HTTP、从 POST 到结果页、从失败到恢复的一整套浏览器语义。现代增强路径应建立在这些语义之上，而不是重新发明一套不兼容的导航和重试模型。