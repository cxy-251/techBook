Navigation Ownership from URL to Document Commit
================================================

核心知识点
----------

* Navigation 从用户或脚本产生“导航意图”开始，新 ``Document`` 此时尚不存在；地址栏输入、链接、表单、返回按钮和 ``location`` 都只是不同入口。
* Browser process 拥有导航控制面，负责判断新文档导航、同文档导航、历史遍历、reload、redirect、download、外部协议或取消等路径。
* Navigation request 不只包含 URL，还包含 method/body、cookie/credentials、referrer、frame target、用户激活、缓存条件、策略与 history 信息。
* Redirect、下载响应、204/205、证书或网络错误等都可能在 commit 前改变或终止候选导航。
* Response commit 是关键边界：commit 前响应仍只是候选；commit 后新的 ``Document`` 成为 active document，拥有新的 DOM、JS execution context、CSS、资源加载和页面生命周期。
* 跨站导航可能在 commit 前触发 renderer 重新选择；应用不能要求自己继续留在原 renderer process。
* 同文档导航如 fragment、``pushState`` 或框架 client routing 可以改变 URL/history 而不创建新 ``Document``，此时 route state 和恢复责任更多转移给应用。
* 目标 URL 必须区分“当前同文档状态可达”与“刷新/深链接可独立成立”；后者最终仍要由浏览器、CDN/server routing 正确解释。

关键路径
--------

新文档导航：

``User/Script Intent → Browser Navigation Decision → Navigation Request → Cache/Network/Service Worker/Server → Redirect or Response → Renderer Selection → Commit → New Active Document``

同文档导航：

``Current Document → History/Fragment/Router Update → URL + History Entry Change → Current Document Continues``

commit 前异常分支：

``Candidate Response → redirect / download / 204-205 / network-security failure → no normal new Document commit``

概念辨析
--------

* **URL 变化 vs Document 变化**：URL 可以在同一 document 内变化；判断 navigation 类型必须看是否发生新 document commit。
* **导航发起者 vs 导航所有者**：页面或用户可以发起导航，browser process 仍拥有是否 commit、新建文档和如何处理响应的最终控制。
* **Request URL vs Navigation Request**：URL 只是请求对象的一部分，身份、method、body、referrer、target 和 policy 都会改变真实路径。
* **Server Redirect vs Client Router**：redirect 在 commit 前改变浏览器导航目标；client router 通常复用当前 document 并自行加载数据、更新 UI。
* **Commit vs 首屏完成**：commit 只表示新 document 边界成立，后续 HTML 解析、CSS、JS、图片、hydration 和数据仍可能失败或很慢。

本章结论
--------

Navigation 的稳定分析单位是 ``意图 → 浏览器决策 → 请求上下文 → 候选响应 → commit → Document``。先确认是否跨过 document boundary，再判断 redirect、下载、安全策略、renderer 选择和 history 状态，才能正确区分浏览器导航故障、服务端路由故障和客户端 router 故障。