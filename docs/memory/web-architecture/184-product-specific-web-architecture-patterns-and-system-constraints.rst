第184章：Product-Specific Web Architecture Patterns and System Constraints
============================================================================

核心知识点
----------

* Web 架构没有脱离产品约束的统一最优解。内容站、dashboard、电商、编辑器、后台工具对 SEO、cache、auth、offline、realtime、transaction 的权重不同。
* 判断顺序应是 ``Product Type → User Entry → State Authority → Failure Cost → Dominant Boundaries → Technical Pattern``，不能先选框架再解释需求。
* 内容/文档站的主路径是公开发现与静态交付，优先稳定 URL、HTML、metadata、sitemap、SSG、CDN、浏览器缓存和低 JS 成本。
* Dashboard 的主路径是登录后的高密度交互，优先 session/tenant/permission、server state、query cache freshness、mutation recovery 与长会话性能。
* 电商同时包含公共发现与强交易路径。商品内容可积极缓存，价格/库存/优惠/订单/支付在交易前必须回到可信 server 重新确认。
* 购物车可以在浏览器做快速交互，但 checkout 必须由 server 重新计算商品、价格、库存、税费、优惠与配送，并用 idempotency 保护订单写入。
* 编辑器和创作工具优先 local state、undo/redo、autosave、Worker、Canvas/WebGL/WebGPU、file boundary、offline 和 collaboration recovery。
* 后台与内部工具优先 correctness、permission、audit、bulk operation、dangerous-action confirmation、import/export 与故障可追踪性。
* PWA/offline-first 只在核心任务确实需要弱网/离线可用时值得承担同步与版本复杂度；不是所有网站都应引入 Service Worker。
* Realtime 同样应按产品需要引入。Presence、通知和协作可以实时，交易与权限事实仍需稳定可信读写协议。
* Rendering model 应由入口和内容决定：公开发现偏 SSR/SSG，密集交互偏 client runtime，混合产品通常采用不同 route/segment 的混合模型。
* Architecture pattern 的价值在于满足约束；CSR、SSR、RSC、GraphQL、RPC、edge、query cache、Service Worker 都只是实现机制。

关键路径
--------

产品约束到架构：

::

   identify product/user task
   → identify entry path
   → identify durable state owner
   → identify freshness/security/latency requirements
   → identify dominant failure cost
   → choose browser/server/edge/build/cache responsibilities
   → choose rendering/data/mutation/runtime tools
   → verify with user-visible evidence

典型产品映射：

::

   content/docs → URL + HTML + SSG/CDN + metadata
   dashboard    → auth + server state + query cache + dense UI
   e-commerce   → discovery cache + trusted checkout + idempotent transaction
   editor       → local model + worker/storage + autosave + sync/recovery
   admin tool   → permission + audit + safe bulk mutation + rollback

概念辨析
--------

* **Product Constraint 与 Technology Preference**：前者决定系统必须满足什么，后者只能在约束内选实现。
* **Public Content 与 Transaction State**：公开内容可广泛共享缓存，交易状态必须按用户和可信事实边界隔离。
* **Dashboard State 与 Editor State**：dashboard 主要观察远端 server state，编辑器往往拥有大量本地未提交工作状态。
* **Realtime Requirement 与 Realtime Everywhere**：只有需要立即共享的状态才进入实时路径，其他事实可使用普通请求和明确刷新。
* **Pattern 与 Architecture**：模式是可复用方案，完整架构还要说明状态、权限、部署、失败和恢复责任。

本章结论
--------

产品架构应按 ``Constraint → Boundary → State → Failure → Pattern`` 推导。技术选择只有在能够解释用户入口、状态真相、缓存新鲜度、安全边界和失败恢复时才成立；产品约束始终比框架标签更接近真正的架构决策。