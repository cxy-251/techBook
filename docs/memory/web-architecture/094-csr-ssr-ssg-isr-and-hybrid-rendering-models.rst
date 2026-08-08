第094章：CSR, SSR, SSG, ISR, and Hybrid Rendering Models
=========================================================

核心知识点
----------

* 渲染模型首先回答“HTML 在哪里、何时生成”，再回答数据读取、缓存失效、客户端激活与失败恢复由谁负责。
* ``CSR`` 把主要 UI 构造放在浏览器；初始 HTML 常只是 shell，JavaScript 启动后再读取数据并创建 DOM。
* ``SSR`` 在请求时由 server/edge 读取 URL、header、cookie、session 与实时数据，生成当前请求对应的 HTML。
* ``SSG`` 在 build time 生成 HTML，适合公开、稳定、可长期缓存、可容忍更新延迟的内容。
* ``ISR`` 把静态输出与运行期再生成结合起来：请求优先复用已有静态结果，再依据 TTL、tag、事件或平台规则触发更新。
* Hybrid rendering 是现代 Web 的常态：同一 route 可同时包含静态主体、请求时片段、客户端交互区与短 TTL 数据。
* 渲染模型会同时改变 browser CPU、server 计算、CDN 命中率、数据新鲜度、SEO、JavaScript 预算与故障传播范围。
* 选择模型时不要给整页贴单一标签，应按 route、segment、component、data 与 user state 拆分责任。

关键路径
--------

::

   User Navigation
     → Browser Document Request
     → CDN / Edge / Origin
     → HTML Production Boundary
        ├─ CSR: shell → JS → API → DOM
        ├─ SSR: request context → server render → HTML
        ├─ SSG: build artifact → CDN → HTML
        ├─ ISR: cached static output → revalidation / regeneration
        └─ Hybrid: static + dynamic + client regions
     → Browser Parse / Paint
     → Client Activation
     → User Interaction

* 公开商品描述可走 ``SSG/ISR → CDN``；会员价、权限、地区价格更适合 ``request → trusted server``；购物车交互留在 browser。
* 排查时依次确认：HTML 生产位置、数据快照时间、缓存层、客户端 bundle、当前用户上下文、失败恢复入口。

概念辨析
--------

* **SSR ≠ 已可交互**：SSR 只保证请求时生成 HTML，交互仍可能等待 JavaScript 与 hydration。
* **SSG ≠ 永远不变**：静态页面仍可通过重新部署、revalidation、ISR 或客户端数据更新刷新。
* **ISR ≠ 实时数据**：ISR 管理的是静态结果更新频率，不能替代请求级权限、实时库存和事务判断。
* **CSR ≠ SPA 专属**：某个页面或局部区域可以使用 CSR，而整个站点仍采用 SSR/SSG。
* **Hybrid ≠ 技术堆叠**：它的核心是按状态所有权和用户路径分配生成边界，而非同时使用尽可能多的框架能力。

本章结论
--------

渲染模型本质上是边界分配问题。先确定 HTML、数据、权限、缓存和交互各自应由 browser、server、edge、CDN 或 build time 中谁拥有，再选择 CSR、SSR、SSG、ISR 或它们的组合；正确模型应让用户关键内容尽早可见、关键交互及时可用，同时保持数据新鲜、缓存安全与失败可恢复。
