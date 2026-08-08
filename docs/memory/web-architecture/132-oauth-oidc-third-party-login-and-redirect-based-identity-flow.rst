第132章：OAuth, OIDC, Third-Party Login, and Redirect-Based Identity Flow
========================================================================

核心知识点
----------

* OAuth 2.0 的核心是 delegated authorization：resource owner 允许 client 在限定 scope 内访问 resource server；它本身不等于用户登录协议。
* OpenID Connect 在 OAuth 之上增加 identity layer，用 ``ID Token``、issuer、subject、audience、nonce、UserInfo 等语义表达“provider 认证了谁”。
* 第三方登录是跨 browser、application server、authorization server、token endpoint 和 application database 的 redirect-based state machine。
* 应用自己的身份主键不应只依赖邮箱。稳定映射通常以 ``(issuer, subject)`` 作为外部身份主键，再关联内部 user id；email/name/picture 更适合作为资料或辅助绑定信号。
* ``state`` 绑定应用发起的登录尝试与回调，防止回调被错误拼接；``nonce`` 绑定 OIDC 身份声明与当前认证请求；PKCE 用 verifier/challenge 绑定授权码交换；redirect URI 限制授权结果回到预期入口。
* Authorization code 只是一次性中间凭证；access token 用于访问 resource server；ID Token 用于身份声明；应用 session cookie 表达用户进入当前应用后的本地会话。四者职责不同。
* 回调处理必须验证 provider、state、code、PKCE、ID Token 签名、issuer、audience、expiration、nonce，再映射本地用户并创建应用 session。
* Third-party login 的失败有大量中间态：用户取消、provider error、state mismatch、code 过期、token exchange 失败、账号未绑定、重复邮箱、组织限制和权限不足。
* ``return_to``、auth attempt、PKCE verifier、nonce 等应由应用服务端持有并设置短生命周期；浏览器主要承担跳转与 cookie 传输。
* 企业 SSO 会把登录扩展成 federation architecture，需要继续处理多 tenant/provider、domain discovery、账号生命周期、组织成员同步和 IdP 策略。
* 设计第三方登录时先区分目标：如果只是访问第三方 API，重点是 scope/token；如果是登录，重点是 OIDC identity、账号映射、本地 session 与恢复路径。

关键路径
--------

OIDC Authorization Code + PKCE：

::

   user requests protected page
   → app creates auth attempt(state, nonce, verifier, return_to)
   → redirect browser to provider /authorize
   → provider authenticates user
   → redirect to app callback(code, state)
   → validate state
   → exchange code + verifier at token endpoint
   → validate ID Token signature / iss / aud / exp / nonce
   → map issuer + subject to local user
   → create app session
   → redirect to return_to

概念辨析
--------

* **OAuth 与 OIDC**：OAuth 解决委托授权，OIDC 在其上增加身份认证语义。
* **Access Token 与 ID Token**：前者给 resource server 使用，后者给 client 验证用户身份；不可互换。
* **Provider Identity 与 App Identity**：外部 provider subject 需要映射成本地 user、tenant、membership 与 permission。
* **State 与 Nonce**：state 绑定 redirect flow，nonce 绑定 OIDC token 与认证请求。
* **PKCE 与 Client Secret**：PKCE 绑定授权码交换，尤其适合无法安全持有 client secret 的公开客户端；两者解决的边界不同。

本章结论
--------

第三方登录应按 ``Auth Attempt → Provider Redirect → Callback Binding → Token Exchange → Identity Verification → Local Account Mapping → App Session`` 阅读。OAuth/OIDC 只提供协议能力，应用仍必须拥有自己的账号映射、session、安全校验和失败恢复状态机。