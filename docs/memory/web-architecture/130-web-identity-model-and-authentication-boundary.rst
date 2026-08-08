第130章：Web Identity Model and Authentication Boundary
=========================================================

核心知识点
----------

* Web identity 不是前端 ``isLoggedIn`` 布尔值，而是系统对“当前请求代表谁”的可验证 claim；常见上下文包括 user、session、tenant、organization、role、认证方式、认证时间与认证强度。
* Authentication 回答“主体是谁”，Authorization 回答“这个主体能否对这个资源执行这个动作”。两者必须分开建模。
* HTTP 请求彼此独立，因此身份边界必须在每次受保护请求中重新建立：读取 cookie/token → 验证 credential → 恢复 session/claims → 检查账号与租户状态 → 建立 identity context → 做资源级授权。
* 浏览器中的头像、菜单、``/me`` query cache 和 local state 只是身份事实的 UI 投影；当前请求是否仍有效必须由可信服务端重新判断。
* Cookie、session、token、OIDC claim 等都是“恢复身份的材料”，不是权限结论本身。服务端仍需检查过期、撤销、issuer/audience、租户、资源归属和操作权限。
* 高风险操作可能要求比普通页面浏览更强或更新的认证，例如 MFA、Passkey 或 recent authentication；“已登录”不等于“可以执行所有敏感动作”。
* 身份 claim 应能回答 ``谁签发 → 谁验证 → 何时过期/撤销``。无法说明来源和撤销路径的 claim 不应进入可信授权决策。
* ``401`` 适合表达当前请求缺少可接受身份或需要重新认证；``403`` 表达身份已识别但权限不足。用户体验可在此基础上扩展 redirect、MFA challenge 或错误页。
* 身份失败本身是用户流程：登录失败、会话过期、MFA 失败、SSO 回调失败和账户冻结都应有可观察、可恢复、可审计的状态转换。
* Web identity 最稳定的模型是跨 browser、auth service、server、session store、database、redirect 和 policy 的状态机，而非单个 token 或组件状态。

关键路径
--------

每次请求重建身份：

::

   browser request + credential
   → server credential parser
   → session/token verification
   → user / tenant / account status
   → identity context
   → resource + action authorization
   → business operation
   → response / redirect / challenge

登录建立会话：

::

   user credential / passkey / provider login
   → authentication service
   → optional MFA / step-up
   → create trusted session or token state
   → Set-Cookie / credential delivery
   → subsequent request rebuilds identity

概念辨析
--------

* **Identity 与 Credential**：identity 是经过验证后的主体上下文；cookie、token、password、Passkey assertion 只是证明或恢复它的材料。
* **Authentication 与 Authorization**：前者确认“是谁”，后者确认“能做什么”。
* **Browser Login State 与 Server Identity**：前者用于界面反馈，后者决定当前请求是否可信。
* **401 与 403**：401 表示需要有效认证或重新认证；403 表示已有身份但当前操作不被允许。
* **Session 与 Permission**：session 保存身份上下文，permission 必须结合目标资源和动作重新求值。

本章结论
--------

Web 身份应按 ``Credential → Verification → Identity Context → Resource Authorization → Failure Recovery`` 阅读。任何受保护请求都要重新建立可信身份；浏览器只展示身份投影，真正的权限与敏感操作判断必须停留在可信运行时。