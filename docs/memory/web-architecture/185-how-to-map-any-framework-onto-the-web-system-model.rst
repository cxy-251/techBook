第185章：How to Map Any Framework onto the Web System Model
===========================================================

核心知识点
----------

* 框架映射的第一步不是看 API，而是先画出 ``browser / network / CDN / edge / server / database / cache / build / deployment`` 边界。
* 框架术语必须落回真实路径：route 对应 URL 匹配，loader 对应数据读取，server component 对应服务端 UI 生成，island 对应局部激活，adapter 对应部署产物转换。
* 任何框架都只覆盖部分路径。UI framework 强在组件与状态；full-stack framework 会继续覆盖 routing、rendering、data、action；API framework 主要覆盖 request/response；build tool 主要覆盖 source graph 与 artifact。
* Rendering path 要回答 HTML 在哪里生成、何时生成、交互在哪里开始。CSR、SSR、SSG、ISR、streaming、islands、RSC 只是不同边界分配方式。
* Data path 要回答谁读取、谁缓存、谁失效、谁拥有 source of truth。框架提供缓存 API 不等于自动拥有一致性语义。
* Mutation path 要还原为 ``user intent → validation → auth → transaction → side effect → cache invalidation → UI feedback``。
* Deployment path 决定最终 runtime contract。同一框架部署到 Node、serverless、edge、static hosting 时，文件系统、连接、region、streaming、secret 和生命周期能力可能不同。
* Framework default 本身就是架构决策。默认缓存、预取、静态生成、client/server split 和 error boundary 都会替项目预先选择路径。
* Escape hatch 体现框架成熟度。自定义 handler、raw Request/Response、manual invalidation、adapter、custom server 等能力决定复杂场景能否退出默认抽象。
* 框架比较应比较路径覆盖、边界清晰度、失败模式、可观测性、部署约束与逃生口；语法和模板偏好是次要维度。

关键路径
--------

框架映射：

::

   user/product path
   → draw browser/server/edge/build/cache/database boundaries
   → place route/render/data/mutation concepts
   → identify state owner and cached copies
   → inspect runtime/deployment target
   → inspect failure and observability surface
   → inspect escape hatches

商品详情示例：

::

   /products/42
   → route match
   → product data read
   → HTML/RSC/JSON generation
   → client activation
   → add-to-cart mutation
   → transaction + invalidation
   → refreshed UI

概念辨析
--------

* **Framework Feature 与 System Boundary**：feature 是框架提供的入口，boundary 决定真实运行位置、权限、状态和失败责任。
* **Full-Stack Framework 与 Full System**：框架可以覆盖多条路径，但数据库一致性、业务权限、队列、运维和恢复仍可能属于外部责任。
* **Rendering Model 与 Framework Name**：同一框架可支持多种渲染模型，架构判断应看页面实际走哪条路径。
* **Default 与 Requirement**：默认值只是框架预设，不代表符合当前产品的新鲜度、安全或部署约束。
* **Abstraction 与 Escape Hatch**：抽象减少常规工作，逃生口保证复杂需求仍能回到底层系统边界。

本章结论
--------

分析任意 Web 框架时，应按 ``Boundary → Route/Render/Data/Mutation → State Ownership → Deployment → Failure/Observability`` 还原。框架 API 只有映射到真实 runtime 和状态路径之后，才具备可比较的架构意义。