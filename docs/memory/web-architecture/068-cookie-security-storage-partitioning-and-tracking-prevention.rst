第068章：Cookie Security, Storage Partitioning, and Tracking Prevention
======================================================================

核心知识点
----------

* Cookie 是浏览器与服务器共同维护的 request-bound state。服务器用 ``Set-Cookie`` 定义状态和属性，浏览器决定保存、发送、过期、脚本可见性和分区行为。
* ``Secure`` 限制 cookie 只通过安全通道发送；``HttpOnly`` 切断 ``document.cookie`` 等脚本读取路径；``SameSite`` 控制跨站请求中的自动发送范围。
* ``Domain`` 会扩大 cookie 可发送的 host 范围。省略 ``Domain`` 形成 host-only cookie，通常比共享到所有子域更容易控制风险。
* ``Path`` 主要约束请求发送范围，不应被当成真正的脚本安全边界。
* ``Expires`` / ``Max-Age`` 定义生命周期；认证、临时安全挑战、偏好和实验状态应按敏感度拆成不同 cookie，而不是共享一个长期凭证。
* ``__Host-`` 前缀要求 ``Secure``、``Path=/`` 且不能设置 ``Domain``，适合把高价值 session 收束到设置它的 host。
* ``SameSite=Strict`` 最严格，适合高敏感站内状态；``Lax`` 常用于普通登录 session；``None`` 用于明确的跨站嵌入/集成并要求 ``Secure``。
* ``HttpOnly`` 只能降低 token 被 XSS 直接读取的风险。恶意脚本仍可能借当前浏览器发同源请求，因此仍需要 CSP、CSRF、权限与二次确认。
* Storage Partitioning 把第三方状态按顶层站点进一步分区，限制一个第三方在不同网站之间共享 cookie、storage、cache 或网络状态。
* ``Partitioned`` cookie（CHIPS）把第三方 cookie 与 top-level site 绑定，适合嵌入组件保存局部状态，又不形成全网共享标识。
* Tracking Prevention 是浏览器产品策略，不同浏览器、版本和隐私模式可能对 third-party cookie、storage access、bounce tracking 等采取不同限制。
* 登录、支付、SSO、第三方 iframe、analytics、A/B testing 和 CDN cache 必须在同一套 cookie/storage 策略下设计，不能假设所有浏览器长期保持传统第三方 cookie 行为。

关键路径
--------

登录 cookie 路径：

``Login Request → Server 验证身份 → Set-Cookie(attributes) → Browser 保存 → 后续匹配 Request → Browser 自动附带 Cookie → Server 读取 session → Authorization → Response``

跨站请求路径：

``Top-Level Site → cross-site navigation/embed/fetch → SameSite / Secure / third-party policy / partition key → cookie 发送或不发送 → Server → UI 恢复``

分区第三方状态：

``Embedded Third Party + Top-Level Site A → Partition A state``

``Embedded Third Party + Top-Level Site B → Partition B state``

排查时先看 ``Set-Cookie`` 实际属性，再看 DevTools 中 cookie 是否被保存、为何未发送，随后确认当前 top-level site、SameSite、Secure、Partitioned 与浏览器隐私策略。

概念辨析
--------

* ``HttpOnly`` ≠ 防止 XSS。它主要阻止脚本直接读取 cookie；XSS 仍可能操作当前页面和发起已认证请求。
* ``SameSite`` ≠ CORS。SameSite 决定 cookie 是否随跨站请求发送；CORS 决定浏览器是否把跨源响应交给脚本。
* ``SameSite=Lax`` ≠ 完整 CSRF 防护。危险 mutation 仍应配合 CSRF token、Origin/Referer 校验和服务端权限。
* ``Domain=example.com`` ≠ 同源。共享 cookie 可以跨多个子域发送，但这些子域的 document 仍可能是不同 origin。
* Storage Partitioning ≠ 清除所有第三方能力。它主要改变状态共享范围，iframe、postMessage、服务端账号体系仍然存在。
* Tracking Prevention ≠ 稳定的单一标准行为。它包含浏览器厂商的产品策略，需要按真实目标浏览器验证。

本章结论
--------

Cookie 策略应从状态用途而不是属性清单出发：``谁拥有状态 → 哪些请求需要它 → 脚本是否应读取 → 是否跨站 → 生命周期多长 → 是否需要分区``。现代浏览器正在把跨站共享状态从默认能力改成显式、受限能力，因此认证和嵌入架构必须减少第三方状态依赖，并始终保留服务端恢复路径。