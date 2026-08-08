第194章：Choosing CSR, SSR, SSG, ISR, Streaming, Islands, or RSC
=================================================================

核心知识点
----------

* 渲染模式的核心问题是：HTML 在哪里产生、数据在哪里读取、JavaScript 在哪里执行、交互从哪里启动、失败由谁恢复。
* CSR 适合高交互、低公开发现压力的应用。浏览器承担主要 UI 生成和状态管理，server 仍拥有权限、价格、库存、订单等最终事实。
* SSR 适合需要早期 HTML 且依赖 request context 的动态页面。它能读取 cookie、session、locale 和实时数据，也把计算、上游延迟和错误更多放到 request-time server。
* SSG 适合稳定公开内容和 CDN 分发。HTML 在 build time 生成，运行期成本低，但高频变化和用户态数据必须拆到其他路径。
* ISR/revalidation 适合半动态公开内容。它允许静态副本在时间窗口内复用，再按 TTL 或事件重新生成；本质是 freshness 与成本交换。
* Streaming 适合页面存在“可先展示”和“需要等待”的分层。它减少整页等待，但要求 server、proxy、CDN、browser 和 error boundary 都正确支持流式传输。
* Islands/partial hydration 适合内容占主、局部交互的页面。大部分 HTML 保持静态，只激活必要组件，降低客户端 JavaScript 和 hydration 范围。
* RSC 适合希望把一部分 UI 组合和数据读取留在 server boundary 的 React 应用；它减少 client bundle，也引入 server/client serialization 与 cache 边界。
* 渲染选择不应整站统一。现代系统应按 route、segment、component、数据新鲜度、SEO 和交互密度组合模式。
* Public content、user-specific content、transaction state 与 local interaction 可以在同一页面使用不同生产路径。
* 任何模式都要配套 cache policy、deployment target、hydration/activation、错误恢复和 rollback；“支持某模式”不等于生产路径正确。
* 最可靠的选择方式是先列初始 HTML 必需内容，再标数据 freshness/personalization，最后决定客户端 JS 最小范围。

关键路径
--------

渲染选择：

::

   route/segment
   → identify initial HTML requirement
   → classify data freshness + personalization
   → choose build/server/browser production boundary
   → choose client activation scope
   → choose cache/revalidation strategy
   → define failure and rollback path

混合商品页：

::

   stable public content → SSG/CDN
   semi-dynamic public data → ISR/revalidation
   request-specific data → SSR/RSC/server read
   local interaction → client component/island
   slow optional region → streaming boundary

概念辨析
--------

* **CSR 与 SPA**：CSR 描述 UI 主要在浏览器生成，SPA 描述导航模型；二者常一起出现但不是同一概念。
* **SSR 与 Server Component**：SSR 描述请求时 HTML 生成，Server Component 描述组件执行位置；可以组合，也不能互相替代。
* **SSG 与 Immutable Data**：SSG 只表示 HTML 在构建时生成，不代表数据永远不变；更新靠重新构建或再验证。
* **ISR 与 Real-Time Data**：ISR 适合允许短暂 stale 的公开内容，不适合必须每次请求确认的交易事实。
* **Streaming 与 Faster Backend**：streaming 不让慢数据本身变快，而是让可用内容更早到达用户。

本章结论
--------

渲染模式应按 ``Initial HTML → Data Freshness → Personalization → Client Interaction → Cache → Failure`` 选择。CSR、SSR、SSG、ISR、streaming、islands 与 RSC 不是竞争答案，而是不同边界分工；正确方案通常是按 route 和 segment 组合。