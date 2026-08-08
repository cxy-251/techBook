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

Part 4：Browser Engine Process Model, Navigation Ownership, and Page Lifecycle
-----------------------------------------------------------------------------

* `第019章：Browser as a Multi-Process Application Runtime <019-browser-as-a-multi-process-application-runtime.rst>`_；
* `第020章：Browser Process, Renderer Process, GPU Process, and Network Process <020-browser-process-renderer-process-gpu-process-and-network-process.rst>`_；
* `第021章：Frame, Tab, Site Instance, and Isolation Boundary <021-frame-tab-site-instance-and-isolation-boundary.rst>`_；
* `第022章：Navigation Ownership from URL to Document Commit <022-navigation-ownership-from-url-to-document-commit.rst>`_；
* `第023章：Redirect, Response Commit, History Entry, and BFCache <023-redirect-response-commit-history-entry-and-bfcache.rst>`_；
* `第024章：SPA Navigation vs Document Navigation <024-spa-navigation-vs-document-navigation.rst>`_；
* `第025章：Page Lifecycle, Visibility, Freeze, Resume, and Recovery Paths <025-page-lifecycle-visibility-freeze-resume-and-recovery-paths.rst>`_。

Part 5：Browser Loading, Document Construction, Rendering, and Compositing Pipeline
----------------------------------------------------------------------------------

* `第026章：Browser Network Loading and Resource Scheduling <026-browser-network-loading-and-resource-scheduling.rst>`_；
* `第027章：HTML Tokenization, Parsing, and DOM Construction <027-html-tokenization-parsing-and-dom-construction.rst>`_；
* `第028章：Parser Blocking, Script Execution, and Streaming HTML <028-parser-blocking-script-execution-and-streaming-html.rst>`_；
* `第029章：CSS Parsing, CSSOM Construction, and Style Input <029-css-parsing-cssom-construction-and-style-input.rst>`_；
* `第030章：Style Calculation and Render Tree Construction <030-style-calculation-and-render-tree-construction.rst>`_；
* `第031章：Layout, Paint, Rasterization, and Compositing <031-layout-paint-rasterization-and-compositing.rst>`_；
* `第032章：GPU Acceleration, Layer Promotion, and Compositor Pipeline <032-gpu-acceleration-layer-promotion-and-compositor-pipeline.rst>`_；
* `第033章：Browser Cache, Resource Lifetime, and Reload Semantics <033-browser-cache-resource-lifetime-and-reload-semantics.rst>`_；
* `第034章：DevTools as the Browser Observability Surface <034-devtools-as-the-browser-observability-surface.rst>`_。

Part 6：Document Model, HTML Semantics, Accessibility, and Public Web Discovery
-------------------------------------------------------------------------------

* `第035章：HTML as Semantic Document and Runtime Input <035-html-as-semantic-document-and-runtime-input.rst>`_；
* `第036章：DOM Tree, Node, Element, Attribute, and Mutation <036-dom-tree-node-element-attribute-and-mutation.rst>`_；
* `第037章：Head Elements, Resource Hints, Script, Style, and Loading Influence <037-head-elements-resource-hints-script-style-and-loading-influence.rst>`_；
* `第038章：Native Forms, Inputs, Constraint Validation, and Submission Semantics <038-native-forms-inputs-constraint-validation-and-submission-semantics.rst>`_；
* `第039章：Custom Elements, Shadow DOM, Template, and Encapsulation Boundary <039-custom-elements-shadow-dom-template-and-encapsulation-boundary.rst>`_；
* `第040章：Accessibility Tree, Semantic Mapping, Focus, and Keyboard Navigation <040-accessibility-tree-semantic-mapping-focus-and-keyboard-navigation.rst>`_；
* `第041章：Internationalization, Locale, Direction, Unicode, and Semantic Presentation <041-internationalization-locale-direction-unicode-and-semantic-presentation.rst>`_；
* `第042章：Crawling, Sitemap, Open Graph, Structured Data, and Public Web Discovery <042-crawling-sitemap-open-graph-structured-data-and-public-web-discovery.rst>`_。

Part 7：CSS Cascade, Layout, Visual Formatting, and Rendering Cost
-----------------------------------------------------------------

* `第043章：Cascade, Specificity, Inheritance, and Computed Value <043-cascade-specificity-inheritance-and-computed-value.rst>`_；
* `第044章：Box Model, Normal Flow, Formatting Context, and Overflow <044-box-model-normal-flow-formatting-context-and-overflow.rst>`_；
* `第045章：Flexbox, Grid, Alignment, and Modern Layout Systems <045-flexbox-grid-alignment-and-modern-layout-systems.rst>`_；
* `第046章：Positioning, Containing Block, Stacking Context, and Layering <046-positioning-containing-block-stacking-context-and-layering.rst>`_；
* `第047章：Responsive Design, Media Query, Container Query, and Adaptive Conditions <047-responsive-design-media-query-container-query-and-adaptive-conditions.rst>`_；
* `第048章：CSS Containment, Layout Invalidation, and Layout Shift <048-css-containment-layout-invalidation-and-layout-shift.rst>`_；
* `第049章：Animation Cost Across Layout, Paint, and Composite <049-animation-cost-across-layout-paint-and-composite.rst>`_。

Part 8：JavaScript Engine, Event Loop, Memory, and Host Runtime Coordination
---------------------------------------------------------------------------

* `第050章：JavaScript Source to Execution <050-javascript-source-to-execution.rst>`_；
* `第051章：Parser, Bytecode, Baseline Compilation, and Optimizing Compilation <051-parser-bytecode-baseline-compilation-and-optimizing-compilation.rst>`_；
* `第052章：Call Stack, Heap, Object Allocation, and Garbage Collection <052-call-stack-heap-object-allocation-and-garbage-collection.rst>`_；
* `第053章：Event Loop, Task Queue, Microtask Queue, and Rendering Coordination <053-event-loop-task-queue-microtask-queue-and-rendering-coordination.rst>`_；
* `第054章：Promise, Timer, Event Callback, and Asynchronous Continuation <054-promise-timer-event-callback-and-asynchronous-continuation.rst>`_；
* `第055章：DOM Binding, Web API Callback, and Host Runtime Integration <055-dom-binding-web-api-callback-and-host-runtime-integration.rst>`_；
* `第056章：Long Task, Main Thread Pressure, Responsiveness, and Input Delay <056-long-task-main-thread-pressure-responsiveness-and-input-delay.rst>`_。

Part 9：Web Platform APIs and Cross-Boundary Capability Paths
-------------------------------------------------------------

* `第057章：Fetch, Request, Response, Body, and Streams <057-fetch-request-response-body-and-streams.rst>`_；
* `第058章：URL, History, Navigation, Location, and Browser State <058-url-history-navigation-location-and-browser-state.rst>`_；
* `第059章：Cookie, Local Storage, Session Storage, IndexedDB, and Storage Lifetime <059-cookie-local-storage-session-storage-indexeddb-and-storage-lifetime.rst>`_；
* `第060章：Service Worker, Cache Storage, Offline Path, and Request Interception <060-service-worker-cache-storage-offline-path-and-request-interception.rst>`_；
* `第061章：Web Worker, Shared Worker, Worklet, and Off-Main-Thread Execution <061-web-worker-shared-worker-worklet-and-off-main-thread-execution.rst>`_；
* `第062章：WebSocket, Server-Sent Events, WebRTC, and WebTransport <062-websocket-server-sent-events-webrtc-and-webtransport.rst>`_；
* `第063章：File, Clipboard, Notification, Permission, and Device-Facing APIs <063-file-clipboard-notification-permission-and-device-facing-apis.rst>`_。

Part 10：Browser-Enforced Security, Permission, Isolation, and Trust Boundaries
-------------------------------------------------------------------------------

* `第064章：Same-Origin Policy and Cross-Origin Constraints <064-same-origin-policy-and-cross-origin-constraints.rst>`_；
* `第065章：CORS, Fetch Credentials, Preflight, and Resource Sharing <065-cors-fetch-credentials-preflight-and-resource-sharing.rst>`_；
* `第066章：CSP, Trusted Types, Script Execution, and Injection Defense <066-csp-trusted-types-script-execution-and-injection-defense.rst>`_；
* `第067章：Secure Context, HTTPS, Mixed Content, and Powerful Features <067-secure-context-https-mixed-content-and-powerful-features.rst>`_；
* `第068章：Cookie Security, Storage Partitioning, and Tracking Prevention <068-cookie-security-storage-partitioning-and-tracking-prevention.rst>`_；
* `第069章：iframe Sandbox, COOP, COEP, CORP, and Cross-Origin Isolation <069-iframe-sandbox-coop-coep-corp-and-cross-origin-isolation.rst>`_；
* `第070章：Permission Prompt, User Consent, and Capability Access Boundary <070-permission-prompt-user-consent-and-capability-access-boundary.rst>`_；
* `第071章：Extension, WebView, Embedded Browser, and Trust Boundary Risk <071-extension-webview-embedded-browser-and-trust-boundary-risk.rst>`_。

Part 11：High-Performance Web Capabilities Across GPU, Media, Worker, and Realtime Paths
---------------------------------------------------------------------------------------

* `第072章：Canvas and SVG Drawing Paths in the Document Runtime <072-canvas-and-svg-drawing-paths-in-the-document-runtime.rst>`_；
* `第073章：WebGL Rendering Path Through Browser and GPU <073-webgl-rendering-path-through-browser-and-gpu.rst>`_；
* `第074章：WebGPU as a Web Platform Capability Boundary <074-webgpu-as-a-web-platform-capability-boundary.rst>`_；
* `第075章：WebGPU Resource, Queue, Shader, and Security Execution Path <075-webgpu-resource-queue-shader-and-security-execution-path.rst>`_；
* `第076章：WebCodecs and Media Source as Browser Media Pipeline <076-webcodecs-and-media-source-as-browser-media-pipeline.rst>`_；
* `第077章：Web Audio Graph, Timing, and Real-Time Scheduling <077-web-audio-graph-timing-and-real-time-scheduling.rst>`_；
* `第078章：Capture, WebRTC Media Path, and Privacy Boundary <078-capture-webrtc-media-path-and-privacy-boundary.rst>`_；
* `第079章：Worker, WASM, GPU, and Media Coordination for High-Performance Web Apps <079-worker-wasm-gpu-and-media-coordination-for-high-performance-web-apps.rst>`_。

Part 12：UI Runtime, Component Model, State, and Interaction Feedback
---------------------------------------------------------------------

* `第080章：UI Runtime as the Bridge Between State and DOM <080-ui-runtime-as-the-bridge-between-state-and-dom.rst>`_；
* `第081章：Component Model, Composition, Props, and Local Responsibility <081-component-model-composition-props-and-local-responsibility.rst>`_；
* `第082章：Client State, Server State, URL State, Form State, and Cache State <082-client-state-server-state-url-state-form-state-and-cache-state.rst>`_；
* `第083章：Virtual DOM, Fine-Grained Reactivity, Signals, and Compiler-Driven UI <083-virtual-dom-fine-grained-reactivity-signals-and-compiler-driven-ui.rst>`_；
* `第084章：Scheduling, Priority, Batching, and User-Perceived Responsiveness <084-scheduling-priority-batching-and-user-perceived-responsiveness.rst>`_；
* `第085章：Event Handling, Feedback Loop, and Interaction Recovery <085-event-handling-feedback-loop-and-interaction-recovery.rst>`_；
* `第086章：Startup Interactivity, Client JavaScript Budget, and UI Activation Cost <086-startup-interactivity-client-javascript-budget-and-ui-activation-cost.rst>`_。

Part 13：Routing, Navigation State, and Application Flow
--------------------------------------------------------

* `第087章：URL as Application State and Public Interface <087-url-as-application-state-and-public-interface.rst>`_；
* `第088章：Route Match, Nested Route, Layout, and Segment Boundary <088-route-match-nested-route-layout-and-segment-boundary.rst>`_；
* `第089章：File-Based Routing, Route Module, and Framework Routing Contracts <089-file-based-routing-route-module-and-framework-routing-contracts.rst>`_；
* `第090章：Client Navigation, History API, and Transition Semantics <090-client-navigation-history-api-and-transition-semantics.rst>`_；
* `第091章：Loading Boundary, Error Boundary, Redirect, and Missing Routes <091-loading-boundary-error-boundary-redirect-and-missing-routes.rst>`_；
* `第092章：Navigation Prefetch, Restoration, and Experience <092-navigation-prefetch-restoration-and-experience.rst>`_；
* `第093章：Route State, Form State, and Data State Coordination <093-route-state-form-state-and-data-state-coordination.rst>`_。

Part 14：Rendering Models, Hydration Architecture, Streaming, and Server-Client Boundaries
-----------------------------------------------------------------------------------------

* `第094章：CSR, SSR, SSG, ISR, and Hybrid Rendering Models <094-csr-ssr-ssg-isr-and-hybrid-rendering-models.rst>`_；
* `第095章：Build-Time and Request-Time Rendering Output <095-build-time-and-request-time-rendering-output.rst>`_；
* `第096章：Streaming HTML, Suspense Boundary, and Incremental UI Delivery <096-streaming-html-suspense-boundary-and-incremental-ui-delivery.rst>`_；
* `第097章：Hydration, Partial Hydration, Islands, and Client Activation <097-hydration-partial-hydration-islands-and-client-activation.rst>`_；
* `第098章：React Server Components and Server-Client Component Boundary <098-react-server-components-and-server-client-component-boundary.rst>`_；
* `第099章：Resumability and Alternative Interactivity Models <099-resumability-and-alternative-interactivity-models.rst>`_；
* `第100章：HTML Payload, Data Payload, JavaScript Payload, and Rendering Tradeoffs <100-html-payload-data-payload-javascript-payload-and-rendering-tradeoffs.rst>`_；
* `第101章：Choosing a Rendering Model from User Experience and System Constraints <101-choosing-a-rendering-model-from-user-experience-and-system-constraints.rst>`_。

Part 15：Forms, Actions, Progressive Enhancement, and Native Web Interaction
----------------------------------------------------------------------------

* `第102章：Forms as the Original Web Mutation Boundary <102-forms-as-the-original-web-mutation-boundary.rst>`_；
* `第103章：Native Submission, Encoding, Redirect, and Browser Behavior <103-native-submission-encoding-redirect-and-browser-behavior.rst>`_；
* `第104章：Constraint Validation, Form State, and User Feedback <104-constraint-validation-form-state-and-user-feedback.rst>`_；
* `第105章：Enhanced Forms, JavaScript Interception, and Progressive Enhancement <105-enhanced-forms-javascript-interception-and-progressive-enhancement.rst>`_；
* `第106章：Request-Scoped Actions and Redirect-After-Post <106-request-scoped-actions-and-redirect-after-post.rst>`_；
* `第107章：Double Submit, Retry, Idempotency, and Native Interaction Safety <107-double-submit-retry-idempotency-and-native-interaction-safety.rst>`_；
* `第108章：Form and Action Models in Full-Stack Frameworks <108-form-and-action-models-in-full-stack-frameworks.rst>`_。

Part 16：Data Read Path, Loading Coordination, and Server-State Boundaries
--------------------------------------------------------------------------

* `第109章：Data Read Path from User Intent to UI State <109-data-read-path-from-user-intent-to-ui-state.rst>`_；
* `第110章：Loader, Fetch, Server Component Data Access, and Query Function <110-loader-fetch-server-component-data-access-and-query-function.rst>`_；
* `第111章：Request Waterfall, Parallel Loading, and Dependency Ordering <111-request-waterfall-parallel-loading-and-dependency-ordering.rst>`_；
* `第112章：Server-Only Data, Secret Boundary, and Safe Data Exposure <112-server-only-data-secret-boundary-and-safe-data-exposure.rst>`_；
* `第113章：Query Cache, Server State, and Client-Side Data Ownership <113-query-cache-server-state-and-client-side-data-ownership.rst>`_；
* `第114章：Streaming Data, Deferred Data, Placeholder UI, and Progressive Rendering <114-streaming-data-deferred-data-placeholder-ui-and-progressive-rendering.rst>`_；
* `第115章：Read Path Failure Modes: Loading Hole, Overfetch, Underfetch, and Stale Data <115-read-path-failure-modes-loading-hole-overfetch-underfetch-and-stale-data.rst>`_。

Part 17：Mutation Write Path, Consistency, Retry, and Failure Recovery
---------------------------------------------------------------------

* `第116章：Mutation Write Path from User Action to Durable State <116-mutation-write-path-from-user-action-to-durable-state.rst>`_；
* `第117章：REST, RPC, GraphQL, and Server Function Mutation Paths <117-rest-rpc-graphql-and-server-function-mutation-paths.rst>`_；
* `第118章：Client Validation, Server Validation, and Runtime Schema Enforcement <118-client-validation-server-validation-and-runtime-schema-enforcement.rst>`_；
* `第119章：Optimistic UI, Pending State, Rollback, and Conflict Resolution <119-optimistic-ui-pending-state-rollback-and-conflict-resolution.rst>`_；
* `第120章：Idempotency, Retry, Race Condition, and Double Write Prevention <120-idempotency-retry-race-condition-and-double-write-prevention.rst>`_；
* `第121章：Mutation Result, Cache Invalidation, and UI Consistency <121-mutation-result-cache-invalidation-and-ui-consistency.rst>`_；
* `第122章：Write Path Failure Modes and Recovery Design <122-write-path-failure-modes-and-recovery-design.rst>`_。

Part 18：API Contracts, RPC, Schema, and Interoperability Boundaries
-------------------------------------------------------------------

* `第123章：API Boundary as a Contract Between Independent Runtimes <123-api-boundary-as-a-contract-between-independent-runtimes.rst>`_；
* `第124章：REST Resource Semantics and HTTP-Aligned Interface Design <124-rest-resource-semantics-and-http-aligned-interface-design.rst>`_；
* `第125章：GraphQL Query Shape, Schema, Resolver, and Execution Boundary <125-graphql-query-shape-schema-resolver-and-execution-boundary.rst>`_；
* `第126章：RPC, tRPC, Server Function, and Type-Safe Call Boundary <126-rpc-trpc-server-function-and-type-safe-call-boundary.rst>`_；
* `第127章：OpenAPI, Schema-First Contract, Runtime Validation, and Client Generation <127-openapi-schema-first-contract-runtime-validation-and-client-generation.rst>`_；
* `第128章：BFF, Route Handler, Middleware, and Frontend-Specific Backend <128-bff-route-handler-middleware-and-frontend-specific-backend.rst>`_；
* `第129章：Contract Drift, Versioning, Backward Compatibility, and Migration <129-contract-drift-versioning-backward-compatibility-and-migration.rst>`_。

阅读方式
--------

每章依次保留“核心知识点”“关键路径”“概念辨析”和“本章结论”。阅读时优先沿 ``User Intent → Browser → Network/CDN/Edge → Server → Database/Storage → Response → Browser State`` 追踪请求路径，并始终标出 runtime、state owner、cache copy、trust boundary 与 failure recovery；遇到框架术语时，先还原成 browser/server/edge/build/database 等真实系统边界。