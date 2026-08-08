第066章：CSP, Trusted Types, Script Execution, and Injection Defense
===================================================================

核心知识点
----------

* CSP（Content Security Policy）是服务器向浏览器声明的资源加载与执行策略；服务器生成策略，浏览器执行策略，违规可进入 reporting 路径。
* ``default-src`` 提供默认来源约束；``script-src``、``style-src``、``img-src``、``font-src``、``connect-src``、``frame-src``、``worker-src`` 等 directive 分别约束不同资源类型。
* CSP 的关键价值不是替代输入验证，而是在浏览器执行层进一步压缩注入内容的可利用面。
* 脚本策略最敏感。``script-src`` 会影响外部脚本、inline script、event handler、``javascript:`` URL、``eval`` / ``new Function`` 等执行入口。
* Nonce 适合动态 HTML：每个响应生成新的高熵 nonce，只给可信 script/style 元素注入对应值。Nonce 属于响应级状态，不能被攻击者输入继承。
* Hash 适合内容稳定的 inline script/style；内容发生任何变化都需要同步更新 hash。
* ``strict-dynamic`` 可让已被 nonce/hash 信任的脚本继续加载后续脚本，适合 loader 场景，也会放大入口脚本自身的 URL 构造风险。
* ``unsafe-inline``、``unsafe-eval`` 会显著扩大执行面，应视为兼容性债务而不是默认配置。
* Trusted Types 针对 DOM-based XSS，把普通字符串进入危险 injection sink 的路径改成“必须由受控 policy 生成 TrustedHTML / TrustedScriptURL 等可信对象”。
* Trusted Types 的价值在于收紧 ``innerHTML``、``document.write``、script URL 等危险 sink；它仍不能替代 sanitizer、输出编码和服务端数据验证。
* CSP 与构建系统强耦合：SSR、hydration data、inline bootstrap、dynamic import、analytics、style injection、worker、WASM 都可能影响最终策略。
* 安全策略应先 Report-Only 观察，再逐步 enforce；线上必须有 violation report、监控和回滚路径。

关键路径
--------

资源与脚本执行路径：

``Navigation → Server Response → CSP Header → HTML Parser / Resource Discovery → Browser 根据 directive 校验 source/nonce/hash → load/execute 或 block → violation report``

DOM 注入路径：

``Untrusted Data → context-aware validation / escaping / sanitization → Trusted Types policy（若启用）→ TrustedHTML / TrustedScriptURL → dangerous sink → Browser enforcement``

Nonce 路径：

``Request → Server 生成一次性 nonce → CSP: script-src 'nonce-...' → 可信模板 script nonce=... → Browser 匹配后执行``

排查顺序：先检查实际响应 header，再定位被阻止的是资源来源、inline script、动态脚本还是 DOM sink，随后回到模板、构建产物和第三方依赖修复许可模型。

概念辨析
--------

* CSP ≠ sanitizer。CSP 控制浏览器允许加载或执行什么；sanitizer 控制不可信内容进入 HTML 时保留哪些结构。
* CSP ≠ 输入验证。业务输入仍需在服务端和数据边界验证。
* Nonce ≠ 静态密钥。Nonce 必须按响应生成并且不可预测，长期复用会削弱模型。
* Hash ≠ SRI。两者都可能使用内容摘要，但 CSP hash 主要控制当前 document 中脚本执行，SRI 主要验证外部资源内容完整性。
* Trusted Types ≠ “字符串自动安全”。可信对象必须来自经过审查的 policy；错误 policy 仍会把危险字符串包装成可信值。
* ``Report-Only`` ≠ 已阻断攻击。它只记录违规，真正限制加载和执行需要 enforce policy。

本章结论
--------

现代注入防御应分层：``输入/业务验证 → 上下文编码与 sanitizer → CSP 限制可执行资源 → Trusted Types 收紧危险 DOM sink → reporting 验证策略``。CSP 和 Trusted Types 的本质是把脚本执行权与字符串注入权变成浏览器可强制执行的显式合同。