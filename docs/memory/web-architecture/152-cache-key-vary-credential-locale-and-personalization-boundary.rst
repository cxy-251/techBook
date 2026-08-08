第152章：Cache Key, Vary, Credential, Locale, and Personalization Boundary
===========================================================================

核心知识点
----------

* Cache key 决定“谁可以共享同一响应”。缓存正确性的第一原则不是提高 hit rate，而是保证不同语义请求不会错误复用同一副本。
* URL 是常见身份核心，但 locale、currency、country、tenant、experiment bucket、权限视角和请求 header 也可能改变内容，因此需要进入 key、URL、Vary 或私有读取路径。
* ``Vary`` 用请求 header 扩展 HTTP cache identity，适合 ``Accept-Encoding``、``Accept-Language``、``Accept`` 等公共内容协商维度。
* 高基数 header 不适合直接放进共享 ``Vary``。``Cookie``、完整 User-Agent、用户 token 会造成严重 fragmentation，并让安全边界难以审计。
* Credential 通常意味着响应带有用户上下文。Cookie、Authorization、session、tenant membership、member price、cart count 等数据一旦进入响应，共享缓存就必须极其谨慎。
* 带 credential 请求不一定返回私有数据；公开静态资源、公共商品描述仍可共享。判断依据是 response semantics，而不是“请求有没有 cookie”。
* 私有响应应优先使用 ``private``、session-scoped server read 或 client query cache，而不是把 user id/token 塞进全局 CDN key 强行共享。
* Locale 不只是语言，还可能包含 region、currency、timezone、number/date format 与 text direction。它应采用稳定、低基数、可审计的表示。
* Locale 放进 URL 通常最清晰；使用 ``Accept-Language`` 时要把任意浏览器 header 归一化成站点支持的有限 locale 集合，避免缓存维度爆炸。
* Personalization 会把 global copy 切成 segmented copy。会员等级、实验组、地区、设备、推荐和权限越多，缓存越难共享。
* 稳定策略是拆分 public shell 与 private context：静态/匿名公共部分在 CDN 共享，用户专属数据通过受控私有请求或 server-side composition 获取。
* Cache fragmentation 是正确性的副作用。优化命中率应在边界正确后进行，不能通过删除必要 key 维度换取性能。

关键路径
--------

共享响应判断：

::

   inspect response body semantics
   → list all dimensions that change content
   → classify dimensions as public or private
   → public dimensions enter URL / Vary / shared key
   → private dimensions stay in session/server/client private layer
   → verify no cross-user or cross-tenant reuse

公共 + 私有页面：

::

   browser requests public shell
   → CDN serves locale/version-scoped copy
   → browser/server requests private context with credential
   → trusted runtime checks identity + permission
   → private response/client cache
   → compose final UI

概念辨析
--------

* **Cache Key 与 Vary**：cache key 是完整缓存身份；``Vary`` 只是声明某些 request header 参与 HTTP 响应选择。
* **Credential 与 Personalization**：credential 证明主体，personalization 是由主体/环境派生的内容差异；二者经常相关但不是同一概念。
* **Public Request 与 Public Response**：请求匿名不代表响应天然可共享；响应只要依赖隐含地区、实验或其他上下文，就需要相应身份维度。
* **Locale 与 Language**：language 只是语言，locale 还包含地区、格式、货币、时区等语义。
* **Correct Key 与 High Hit Rate**：正确 key 优先保证隔离，命中率是在正确性成立后的优化目标。

本章结论
--------

缓存身份应按 ``Response Semantics → Context Dimensions → Public/Private Split → Cache Key/Vary → Sharing Scope`` 设计。最安全且高效的模式通常是让公共内容保持低基数、可共享，让 credential 与个性化事实停留在私有层，而不是让一个 URL 承担所有用户状态。