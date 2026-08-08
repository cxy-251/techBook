第131章：Cookie, Session, Token, JWT, and Session Refresh Path
===============================================================

核心知识点
----------

* Cookie 是浏览器附加到请求上的状态机制；domain、path、Secure、HttpOnly、SameSite、Expires/Max-Age 等属性决定它何时发送、是否可被脚本读取以及生命周期。
* Server-side session 把权威会话状态留在服务端，浏览器通常只保存不可预测的 session id。撤销、权限变化、设备管理和审计因此更容易集中控制。
* Token-based auth 把更多身份或授权状态装进可携带 credential，适合 API、移动端、CLI、gateway 和多服务场景，但增加 scope、audience、签名密钥、撤销和重放治理成本。
* JWT 只是 claims 的签名/加密表达格式，不等于“无状态认证方案”。安全性取决于签名验证、issuer、audience、expiration、token type、存储位置、撤销与权限模型。
* Access token 与 refresh token 责任不同：前者用于资源访问且应短生命周期、最小 scope；后者用于换取新 access token，生命周期更长、价值更高，需更严格的存储、轮换和撤销。
* Credential 的存储位置会改变威胁模型。HttpOnly cookie 降低脚本读取风险，但浏览器会自动附带，因此需考虑 CSRF；localStorage/IndexedDB 更容易被 XSS 读取；memory 状态刷新页面后会消失。
* 会话刷新本质是状态机，而不是“token 快过期就自动续一下”。它要处理并发刷新、旧 token 失效、rotation、撤销、网络失败和多标签页竞争。
* Refresh 成功后要明确旧 credential 的失效关系；refresh 失败后要进入重新认证，而不是无限重试或继续使用过期身份。
* Session expiry 发生在用户工作流中间时，应尽量保留 URL、表单草稿和操作上下文，但敏感 mutation 在重新认证后仍需重新做权限和资源状态检查。
* 选择 cookie/session/token/JWT 时，先比较“状态权威在哪里、谁验证、如何撤销、浏览器怎样携带、失败如何恢复”，而不是按流行度选型。

关键路径
--------

Server session：

::

   login
   → server creates session record
   → Set-Cookie(session id)
   → browser auto-attaches cookie
   → server looks up active session
   → rebuild identity + authorization

Token refresh：

::

   access token expires
   → refresh credential sent to auth service
   → validate session / token family
   → rotate or issue new access token
   → invalidate old material as designed
   → retry original operation once
   → reauthenticate if refresh fails

概念辨析
--------

* **Cookie 与 Session**：cookie 是浏览器传输/存储机制；session 是服务端会话状态，两者常组合使用但不是同一概念。
* **Token 与 JWT**：token 是凭据角色，JWT 是一种格式；token 可以是 opaque，JWT 也不必承担登录会话。
* **Access Token 与 Refresh Token**：前者面向资源服务，后者面向认证服务，权限和生命周期应分离。
* **Stateless 与 Revocable**：本地验证 token 减少中心查询，但即时撤销和权限变化传播会更复杂。
* **Refresh 与 Reauthentication**：refresh 延长已有会话，reauthentication 重新证明用户控制认证因素。

本章结论
--------

会话系统应按 ``Credential Storage → Request Attachment → Server Verification → Expiry → Refresh/Rotation → Revocation → Recovery`` 阅读。Cookie、session、token 和 JWT 只是不同位置的状态与凭据工具；真正的设计目标是让身份可验证、可撤销、可轮换，并在失效后能安全恢复用户意图。