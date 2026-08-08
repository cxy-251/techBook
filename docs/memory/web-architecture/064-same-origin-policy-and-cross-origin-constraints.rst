第064章：Same-Origin Policy and Cross-Origin Constraints
========================================================

核心知识点
----------

* Origin 是浏览器最基础的脚本安全边界，普通网络 URL 通常由 ``scheme + host + port`` 决定；path、query、fragment 不参与同源判断。
* Same-Origin Policy（SOP）的核心作用是限制跨 origin 的脚本级读取和操作：DOM、Storage、部分 Window 能力、Fetch 响应内容等都受它约束。
* “能发送请求”“能嵌入资源”“能读取结果”是三种不同能力。跨源 ``img``、``script``、``iframe``、表单提交往往可以发生，响应或 DOM 是否能被脚本读取是另一层判断。
* ``origin`` 与 ``site`` 不是同一个概念：前者更细，后者常参与 SameSite cookie、tracking prevention 等站点级策略。
* 跨源 iframe 的稳定协作方式是显式消息协议：发送方指定 ``targetOrigin``，接收方校验 ``event.origin``，消息只携带必要状态。
* 跨源 Fetch 即使服务器已经返回 ``200``，浏览器仍可能因为 CORS 等策略拒绝把响应暴露给 JavaScript。
* Cookie 可能随跨站请求自动发送，因此 SOP 不能代替 CSRF 防护；危险写操作仍需服务端验证用户意图、Origin/Referer、CSRF token 与权限。
* 第三方脚本属于高信任嵌入：脚本一旦在当前 document 中执行，通常拥有当前页面 origin 下的脚本能力，不能因为资源来自跨源 CDN 就认为权限更低。

关键路径
--------

``用户操作 / 页面代码 → 计算当前 origin → 判断同源或跨源 → 浏览器执行 SOP → 允许嵌入或发送请求 → 对读取能力继续执行 CORS / frame / storage 策略 → 页面获得结果或安全错误``

跨源 iframe 协作路径：

``Parent Document → iframe navigation → Cross-Origin Document → postMessage(message, targetOrigin) → receiver 校验 event.origin → 更新各自本地状态 / 请求服务端确认``

跨源 API 路径：

``Page Script → fetch(cross-origin URL) → Browser → API Server → HTTP Response → Browser Policy Check → expose Response 或抛出跨源错误``

排查时先写完整 URL，并逐项比较 ``scheme``、``host``、``port``；随后区分问题属于“请求未发送”“资源未加载”“响应不可读”“frame DOM 不可读”还是“cookie 仍被发送”。

概念辨析
--------

* SOP ≠ 禁止跨源通信。Web 天生允许大量跨源加载、导航和写入；SOP 主要收紧脚本读取和直接控制能力。
* 跨源 ≠ 跨站。``app.example.com`` 与 ``api.example.com`` 通常跨 origin，但可能 same-site。
* CORS ≠ 身份认证。CORS 决定浏览器是否把跨源响应交给脚本；服务器仍要独立做 authentication 与 authorization。
* ``postMessage`` ≠ 自动安全。消息 API 只是通信通道，``targetOrigin``、``event.origin``、消息 schema 和状态机必须显式校验。
* Cookie 可发送 ≠ 页面可读取响应。跨站请求可以带 cookie 到服务器，浏览器仍可能阻止调用方脚本读取返回内容。
* 第三方 iframe ≠ 第三方 script。iframe 通常拥有独立 document/origin；第三方 script 通常进入当前页面执行环境。

本章结论
--------

Same-Origin Policy 应记成浏览器的“脚本读取与控制边界”。分析任何跨域系统时，先确定 origin，再把 ``发送 / 嵌入 / 读取 / 凭证`` 四件事拆开；跨源协作通过 CORS、``postMessage``、服务端协议等显式放行，状态写入和权限判断始终由可信服务端独立确认。