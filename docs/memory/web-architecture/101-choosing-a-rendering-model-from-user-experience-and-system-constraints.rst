第101章：Choosing a Rendering Model from User Experience and System Constraints
===============================================================================

核心知识点
----------

* 渲染模型选择应从页面约束出发：内容新鲜度、交互密度、公开发现、个性化/安全、运行时能力、缓存、成本和失败恢复共同决定方案。
* 内容越稳定、公开、可容忍延迟更新，越适合 SSG/ISR/CDN；越依赖 cookie、role、tenant、region 与实时数据，越需要 trusted server/edge boundary。
* 交互密度越低，越应缩小客户端 JavaScript 边界；内容页、文档页、营销页和商品页常适合 islands/partial activation；在线 IDE、编辑器、复杂控制台更偏长期 client runtime。
* SEO 和公开发现需要稳定 URL、HTML、metadata、canonical、structured data、可发现链接和正确 HTTP status；客户端增强不能破坏这些平台语义。
* 权限、价格规则、secret、敏感字段过滤与最终业务判断应留在可信 server/edge；浏览器只持有完成交互所需的可见副本和意图状态。
* runtime/hosting 约束会筛掉理论方案：edge 的 CPU、内存、连接与 API 能力，serverless 的 cold start，static hosting 的运行时缺失，数据库连接模型都会影响可落地性。
* 失败恢复必须进入决策矩阵：数据失败、客户端脚本失败、缓存过期、权限变化、stream 中断时，用户是否仍能看到核心内容、重试或完成任务。
* 最终决策通常是混合矩阵，而不是全站统一 CSR/SSR/SSG；同一 route 的不同区域可采用不同生成与激活策略。

关键路径
--------

::

   Page / Route Requirement
     → Classify Content Freshness
     → Classify Interaction Density
     → Identify Public Discovery Requirements
     → Identify Trusted Data / Security Boundary
     → Check Hosting / Runtime Constraints
     → Define Cache Scope and Invalidation
     → Define Failure / Fallback Path
     → Choose Boundary Mix
        ├─ SSG / ISR / CDN for stable public content
        ├─ SSR / Server Component / Edge for request context
        ├─ Streaming for independent slow regions
        ├─ Client Component / Island for interaction
        └─ Client fetch for local high-frequency data
     → Measure Real User Waiting

* 商品页可拆成：标题/主图/说明 → SSG/ISR；会员价/权限 → server request boundary；库存 → 短 TTL/stream/client refresh；购物车 → client interaction + server mutation。
* 每次选择都要回答：谁拥有真相、谁拥有缓存副本、谁能访问 secret、谁负责用户失败恢复。

概念辨析
--------

* **SEO 好 ≠ 必须整页 SSR**：公开主体和 metadata 稳定可见即可，个性化和交互区域可采用其它边界。
* **强交互 ≠ 必须纯 CSR**：首屏公开内容仍可 server/static render，交互区域再进入 client runtime。
* **Edge ≠ 更快的 server 通用替代品**：它适合早期轻量决策，重数据库事务、长 CPU 工作和复杂依赖可能更适合区域 server/origin。
* **Static ≠ 不安全**：公开静态内容通常风险低；真正危险的是把用户、权限或 secret 错误固化进共享 artifact/cache。
* **框架默认值 ≠ 架构答案**：默认 rendering mode 只是实现起点，真实选择必须由数据和用户路径约束验证。

本章结论
--------

选择渲染模型要建立决策矩阵，而不是争论 CSR、SSR 或 SSG 谁更先进。稳定公开内容尽量前移并缓存，用户与权限相关逻辑留在可信运行时，客户端只承担必要交互，慢区域可流式或局部补齐；最终用真实网络、设备、缓存命中和失败场景验证用户完成任务的总成本。
