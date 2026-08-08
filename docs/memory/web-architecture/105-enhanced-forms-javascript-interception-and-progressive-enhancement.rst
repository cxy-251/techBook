Enhanced Forms, JavaScript Interception, and Progressive Enhancement
====================================================================

核心知识点
----------

* 增强表单应先保留原生提交契约：``action``、``method``、``enctype``、控件 ``name``、submitter 和服务器 handler 在无 JavaScript 时也要成立。
* ``preventDefault()`` 会把责任从浏览器迁移到应用。应用随后必须自己处理 pending、局部结果、redirect、history、focus、scroll、abort、retry 和错误映射。
* ``fetch()`` 发送请求不会自动形成页面导航。增强路径要明确成功后是局部更新、软导航还是 ``location.assign()`` 进入稳定结果 URL。
* progressive enhancement 应把基础路径和增强路径分开：基础路径保证任务可完成，增强路径增加实时校验、局部刷新、乐观 UI、自动保存与更细反馈。
* submitter 仍是用户意图的一部分。增强代码需要保留按钮的 ``formAction``、``formMethod`` 与 name/value，避免把多动作表单压成同一 mutation。
* 增强路径天然会遇到重复提交、组件卸载、路由切换和旧请求晚到；需要 ``AbortController``、request id、去重和 stale-result 检查。

关键路径
--------

``Native form contract → submit event → Application decides to intercept → preserve submitter/FormData → pending UI → fetch → trusted server action → data/error/redirect result → application updates UI/history/focus or performs real navigation → recovery/abort``

设计增强时先列出浏览器原本自动完成的动作，再逐项确认应用是否接管并补齐；只写一个 ``fetch`` 调用并不等于完成了表单增强。

概念辨析
--------

* **Interception vs enhancement**：拦截只是技术动作；只有在基础路径仍可用且失败体验不退化时，才算渐进增强。
* **Fetch submission vs navigation**：``fetch`` 是数据请求；navigation 还包含 URL、history、document/route state、scroll 与 focus。
* **requestSubmit() vs submit()**：``requestSubmit()`` 更接近用户真实提交，会经过校验和 submit event；直接 ``submit()`` 会绕开部分原生流程。
* **Optimistic UI vs committed state**：乐观结果属于浏览器临时预测，服务器和数据库仍拥有最终业务事实。
* **Abort vs rollback**：取消客户端等待不代表服务器 mutation 没发生；已发送写入需要幂等或查询结果确认。

本章结论
--------

JavaScript 增强表单的本质是主动接管浏览器原生责任。增强越多，应用越需要显式维护导航、等待、取消、错误和恢复语义；最稳的设计始终保留一条无需增强也能完成任务的 form/server 路径。