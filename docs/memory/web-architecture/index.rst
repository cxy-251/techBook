Web Architecture 必背课本
=========================

本目录与 AIBook 的 ``docs/WebArch`` 一一对应。AIBook 保留完整讲解、平台资料、案例和系统路径，这里只保留稳定、必须掌握、可以直接复习的现代 Web 系统架构模型。

Part 1：Web System Worldview and Engineering Mental Model
---------------------------------------------------------

* `第001章：Modern Web Integration Surface <001-modern-web-integration-surface.rst>`_；
* `第002章：Web Architecture Boundary Expansion <002-web-architecture-boundary-expansion.rst>`_；
* `第003章：Browser, Server, Edge, Database, CDN, and Build-Time Boundaries <003-browser-server-edge-database-cdn-and-build-time-boundaries.rst>`_；
* `第004章：Request, Response, Navigation, and Runtime State <004-request-response-navigation-and-runtime-state.rst>`_；
* `第005章：How Frameworks Package System Boundaries <005-how-frameworks-package-system-boundaries.rst>`_。

Part 2：Web Standards, Compatibility, and Platform Contracts
------------------------------------------------------------

* `第006章：The Web as a Standardized, Multi-Vendor Platform <006-the-web-as-a-standardized-multi-vendor-platform.rst>`_；
* `第007章：WHATWG, W3C, TC39, IETF, and the Standards Stack <007-whatwg-w3c-tc39-ietf-and-the-standards-stack.rst>`_；
* `第008章：HTML, DOM, CSS, ECMAScript, Fetch, and HTTP as Layered Contracts <008-html-dom-css-ecmascript-fetch-and-http-as-layered-contracts.rst>`_；
* `第009章：Compatibility, Interoperability, and the Cost of a Living Platform <009-compatibility-interoperability-and-the-cost-of-a-living-platform.rst>`_；
* `第010章：Progressive Enhancement as an Architectural Principle <010-progressive-enhancement-as-an-architectural-principle.rst>`_；
* `第011章：Browser Baseline, Feature Detection, Polyfill, and Transpilation Boundaries <011-browser-baseline-feature-detection-polyfill-and-transpilation-boundaries.rst>`_。

Part 3：URL, HTTP, Network, and Resource Delivery
-------------------------------------------------

* `第012章：URL as Address, State, Capability, and Routing Input <012-url-as-address-state-capability-and-routing-input.rst>`_；
* `第013章：DNS, TCP, TLS, QUIC, and Connection Establishment <013-dns-tcp-tls-quic-and-connection-establishment.rst>`_；
* `第014章：HTTP Request and Response Semantics <014-http-request-and-response-semantics.rst>`_；
* `第015章：HTTP 1.1, HTTP 2, HTTP 3, and Multiplexed Resource Loading <015-http-1-1-http-2-http-3-and-multiplexed-resource-loading.rst>`_；
* `第016章：Header, Cookie, Cache-Control, Content Negotiation, and Cross-Layer Meaning <016-header-cookie-cache-control-content-negotiation-and-cross-layer-meaning.rst>`_；
* `第017章：Resource Discovery, Preload, Prefetch, Priority, and Critical Path <017-resource-discovery-preload-prefetch-priority-and-critical-path.rst>`_；
* `第018章：Compression, Streaming, Incremental Delivery, and Progressive Response <018-compression-streaming-incremental-delivery-and-progressive-response.rst>`_。

阅读方式
--------

每章依次保留“核心知识点”“关键路径”“概念辨析”和“本章结论”。阅读时优先沿 ``User Intent → Browser → Network/CDN/Edge → Server → Database/Storage → Response → Browser State`` 追踪请求路径，并始终标出 runtime、state owner、cache copy、trust boundary 与 failure recovery；遇到框架术语时，先还原成 browser/server/edge/build/database 等真实系统边界。