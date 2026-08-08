第069章：iframe Sandbox, COOP, COEP, CORP, and Cross-Origin Isolation
=====================================================================

核心知识点
----------

* ``iframe`` 创建独立 browsing context：父页面拥有 iframe 元素和布局位置，子页面拥有自己的 Document、origin、session、脚本、存储和资源生命周期。
* 跨源 iframe 的父子页面不能直接互读 DOM；稳定协作应使用 ``postMessage``、URL/redirect、服务端回调等显式协议。
* ``sandbox`` 是父页面对 iframe 能力的限制集合。空 sandbox 最严格，``allow-scripts``、``allow-forms``、``allow-popups`` 等 token 按需放开能力。
* ``allow-same-origin`` 会让被嵌入文档保留 origin 语义；对不可信同源内容同时放开 ``allow-scripts`` 和 ``allow-same-origin`` 会显著削弱 sandbox 约束，应优先把不可信内容放到独立 origin。
* Sandbox 只限制浏览器中的 document 能力，不能替代服务端 authentication、authorization、签名和业务状态校验。
* COOP（Cross-Origin-Opener-Policy）控制顶层窗口的 opener 关系与 browsing context group；强隔离场景常使用 ``same-origin`` 切断跨源 ``window.opener``。
* COEP（Cross-Origin-Embedder-Policy）从页面侧要求被加载的跨源资源显式满足 CORS/CORP 等可嵌入条件。
* CORP（Cross-Origin-Resource-Policy）从资源提供方声明资源允许 ``same-origin``、``same-site`` 或 ``cross-origin`` 使用。
* Cross-Origin Isolation 是多项策略共同形成的系统状态，不是单个 header。页面、worker、WASM、字体、图片和第三方资源都可能影响最终结果。
* ``window.crossOriginIsolated`` 是运行时验证点；需要 ``SharedArrayBuffer`` 等敏感高性能能力时，应验证它而不是只检查服务器配置文件。
* COOP/COEP 会影响 OAuth popup、支付弹窗、第三方 SDK、CDN、analytics、WASM 等既有集成，启用前必须盘点资源和 opener 通信依赖。
* 嵌入架构的核心问题是：谁能嵌入谁、谁能导航谁、谁能给谁发消息、资源由谁授权、失败后由谁恢复。

关键路径
--------

iframe 路径：

``Parent Document → iframe element(src/sandbox/allow) → Browser navigation → Embedded Document → own origin/storage/scripts → postMessage protocol → Parent state / server state``

Cross-Origin Isolation 路径：

``Top-Level Response → COOP → opener/browsing-context-group isolation``

``Top-Level Response → COEP → cross-origin subresource check → resource CORS or CORP permission``

``所有依赖满足 → crossOriginIsolated=true → SharedArrayBuffer / sensitive high-performance capability``

排查时依次检查 iframe 的 origin 与 sandbox token、popup/opener 关系、主文档 COOP/COEP、失败子资源的 CORS/CORP 响应，以及最终 ``crossOriginIsolated`` 状态。

概念辨析
--------

* iframe ≠ 普通组件。它是完整独立 document，拥有自己的加载、脚本、存储、历史和安全边界。
* Sandbox ≠ same-origin policy。Sandbox 是父页面附加的能力限制；SOP 是浏览器的 origin 访问基础规则。
* COOP ≠ COEP。COOP 主要处理跨窗口 opener 隔离；COEP 主要处理当前文档允许嵌入哪些跨源资源。
* COEP ≠ CORP。COEP 是使用方的要求；CORP 是资源方的声明。
* CORP ≠ CORS。CORP 主要控制跨站嵌入/资源使用边界；CORS 主要控制脚本读取跨源响应的授权协议。
* Cross-Origin Isolation ≠ 只加两个 header。所有相关跨源资源和 worker 都必须符合隔离契约。
* ``z-index`` / DOM 层级 ≠ 信任层级。视觉上嵌入在同一页面的 iframe 仍属于另一个 document 和 origin。

本章结论
--------

嵌入与隔离应按系统合同设计：``iframe 定义 document 边界 → sandbox 收紧子页面能力 → COOP 收紧跨窗口关系 → COEP 要求安全嵌入 → CORP/CORS 由资源方授权 → crossOriginIsolated 验证最终状态``。任何第三方支付、广告、文档预览或高性能 WASM 集成都必须在这条链上逐项验证。