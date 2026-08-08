第137章：Auth Failure, Session Expiry, Reauthentication, and Recovery Experience
================================================================================

核心知识点
----------

* Auth failure 常发生在用户工作流中段：长表单、文件上传、后台刷新、WebSocket、server action、权限变更和支付都可能在页面仍可见时遇到 session/token 失效。
* 浏览器中的表单草稿、modal、scroll、query cache 仍存在，不代表 server 仍接受当前身份。服务端必须以当前请求重新验证 session、权限、MFA 新鲜度和资源状态。
* ``401`` 适合表达当前 credential 已失效或需要重新认证；``403`` 表达身份仍有效但权限不足。应用内部可以再细分 ``SESSION_EXPIRED``、``REAUTH_REQUIRED``、``MFA_REQUIRED`` 等稳定 error code。
* Session expiry 后应区分 Context 与 Intent：Context 是 URL、scroll、tab、modal 等位置；Intent 是用户准备执行的动作。恢复时先保留上下文，再安全恢复动作。
* 低风险草稿可短期保存在 memory、session storage 或 server draft；高风险 mutation 更适合保存一次性 continuation id，并绑定 user、tenant、operation、expiry 与 CSRF 状态。
* Reauthentication 是在已有身份基础上再次证明用户仍控制认证因素，适用于密码修改、支付、删除组织、导出敏感数据、权限提升、MFA 变更等敏感动作。
* “仍登录”与“可执行敏感操作”不是一个状态。系统应分别维护普通 session、MFA level、recent auth、permission 与资源版本。
* Reauth 完成后不能直接重放旧危险 mutation；必须重新读取目标资源、权限、tenant、版本和业务前提，再由用户确认或重新提交。
* Background refresh 失败不应无条件清空整个页面。可以限制新 mutation、标记数据可能过期并提示重新登录，同时保留非敏感本地工作。
* Logout 不只是删除 server session，还应清理相关 cookie、memory/query cache、local/session storage 中的身份投影、Service Worker 用户数据、WebSocket/实时连接和跨标签页状态。
* 身份恢复逻辑必须跨 navigation、API、server component/action、client fetch、WebSocket 和后台任务保持一致；否则同一 session expiry 会表现出相互冲突的 UI。
* 好的 auth UX 是安全架构的可见结果：既不能为“无感”而绕过重新验证，也不能因为 session 过期就无差别丢弃用户工作。

关键路径
--------

Session expiry recovery：

::

   protected request fails auth
   → classify 401 / forbidden / reauth required
   → freeze sensitive mutations
   → preserve URL + draft + safe UI context
   → authenticate / MFA / step-up
   → establish fresh session
   → reload current permission + resource version
   → restore page context
   → user confirms or retries operation

Logout cleanup：

::

   revoke server session / tokens
   → clear auth cookies
   → clear user-scoped client caches and local state
   → close realtime/background channels
   → synchronize other tabs
   → return to anonymous state

概念辨析
--------

* **Session Expiry 与 Permission Loss**：前者通常需要重新认证，后者身份可能仍有效但当前操作应被拒绝。
* **Context 与 Intent**：context 是用户所在位置，intent 是准备执行的动作；高风险 intent 不应在 reauth 后自动重放。
* **Refresh 与 Reauthentication**：refresh 延长或更新 credential，reauthentication 重新证明用户身份控制权。
* **Logout 与 Redirect to Login**：redirect 只是界面导航；logout 需要真正撤销服务端状态并清理客户端身份副本。
* **Cached Data 与 Current Authority**：缓存可保留阅读上下文，但权限变化后不能把旧缓存当作当前授权事实。

本章结论
--------

Auth recovery 应按 ``Failure Classification → Preserve Safe Context → Reauthenticate → Rebuild Authority → Revalidate Resource → Resume Intent`` 设计。会话失效既是安全事件也是状态恢复事件；正确系统能保护可信边界，同时尽量不丢失用户正在进行的工作。