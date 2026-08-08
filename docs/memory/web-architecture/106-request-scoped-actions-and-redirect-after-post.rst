Request-Scoped Actions and Redirect-After-Post
==============================================

核心知识点
----------

* Action 是一次请求范围内的 mutation handler：读取 request/form data 与 session，完成输入校验、身份与权限判断、业务规则、事务写入，再返回数据、错误、redirect 或 revalidation 信号。
* action 的边界通常更靠近 route/request，而不是纯 UI component。组件表达提交意图，action 负责可信写入，最终页面负责读取并展示已提交事实。
* 客户端预校验不能替代服务器验证。服务器必须重新校验字段、CSRF、tenant/role、业务约束和数据库一致性，并把不同失败映射成可恢复状态。
* Redirect-After-Post 将 mutation 结果变成稳定 navigation state。成功后使用 ``303 See Other`` 指向结果资源，浏览器再用 ``GET`` 读取，刷新、收藏、分享和返回都围绕结果 URL 工作。
* action 结果不只有 success/failure：字段错误适合留在当前表单，权限问题可能 redirect，成功可能触发 cache invalidation/revalidation，临时故障应提供重试或保持输入。
* request-scoped 只限制 handler 生命周期，不代表 mutation 没有跨请求影响；持久化事实仍由数据库、缓存和后续读取路径承接。

关键路径
--------

``Form submit → POST/action request → Read session + parse FormData → Validate input/auth/CSRF/business rules → Transactional mutation → Commit durable state → Invalidate/revalidate affected reads → 303 Location → GET stable result resource``

写入成功的提交点应位于 redirect 之前；只有数据库/业务事实确认后才能把用户带到结果页。失败则保持在当前 mutation 上下文，返回可定位错误而不是伪造成功页面。

概念辨析
--------

* **Action vs component callback**：callback 属于 UI runtime；action 属于可信 request boundary，能够访问 session、secret、database 与事务。
* **Request-scoped vs client state**：action 每次请求重新建立上下文；客户端 state 可长时间存在并产生 stale drift。
* **303 vs 307**：``303`` 将 POST 结果转成读取；``307`` 保留 method，更适合请求位置迁移，不适合作为常规成功页跳转。
* **Validation error vs transport error**：字段规则失败是可预期业务状态；网络/5xx 是运行失败，恢复策略不同。
* **Revalidation vs mutation**：mutation 改变权威状态；revalidation 只重新读取或刷新其副本。

本章结论
--------

Action 的价值在于把一次用户写入意图收敛到短生命周期、可信、可审计的服务器请求边界。写入完成后再通过 redirect 和 revalidation 回到稳定读路径，可以显著降低客户端长期维护业务事实的复杂度。