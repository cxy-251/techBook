第192章：Framework Comparison as Boundary Comparison
====================================================

核心知识点
----------

* Framework comparison 应从 boundary behavior 开始，而不是从组件语法、API 数量或 feature list 开始。
* 同样的页面组件可能运行在 browser、Node server、serverless、edge 或 build time；运行位置改变能力、状态、缓存、生命周期和失败形态。
* Feature 名称必须还原成边界行为。SSR、SSG、edge、API route、server action、island、streaming 等词都要继续追问 runtime、输入、输出、缓存、错误和部署限制。
* SSR 的关键问题不是“支持服务器渲染”，而是 HTML 在哪个 runtime 生成、是否带 request context、能否 stream、如何缓存、失败如何返回。
* Edge 的关键问题是 API capability、region、secret、connection、timeout、streaming 与 Node compatibility，而不是“离用户更近”这一条宣传语。
* Form/server action 的关键问题是 native/JS submission、serialization、auth、validation、idempotency、cache invalidation 与 error recovery。
* Framework default 是框架替项目做出的架构选择。默认 cache、prefetch、bundle split、render mode、error boundary、runtime 与 adapter 都需要被显式审查。
* Default 越适合产品，开发成本越低；产品约束偏离 default 越多，override、调试和升级成本越高。
* Escape hatch 揭示框架是否能承受真实复杂度。成熟框架应允许在 data、cache、runtime、API、build、deploy、observability 上退出 happy path。
* Observability 决定 abstraction 是否安全。框架可以隐藏实现细节，但必须让 request、cache、render、artifact、runtime failure 和 release version 可被检查。
* Framework fit 依赖产品约束。内容站、dashboard、电商、协作编辑器、媒体应用、后台系统和离线 PWA 的主边界不同。
* 正确问题不是“哪个框架最好”，而是“哪个框架最清楚地封装我需要的系统路径，同时最少隐藏我必须控制的边界”。

关键路径
--------

框架比较：

::

   define product constraints
   → choose one real user path
   → map HTML/data/mutation/cache/deployment boundaries
   → inspect framework defaults
   → inspect failure + observability
   → inspect escape hatches
   → compare migration/reversibility cost

Feature 还原：

::

   framework feature name
   → execution runtime
   → request/state inputs
   → output artifact/response
   → cache/freshness behavior
   → error semantics
   → platform support

概念辨析
--------

* **Syntax Comparison 与 Boundary Comparison**：前者比较写法，后者比较代码运行位置、状态所有权和失败责任。
* **Feature Support 与 Production Fit**：支持某功能只证明框架有入口，是否适合生产还取决于当前 runtime、cache、安全和恢复约束。
* **Default 与 Architecture**：默认值不是中性设置，而是已经替应用做出的渲染、缓存、预取和部署选择。
* **Escape Hatch 与 Framework Failure**：逃生口不是框架失败，而是复杂系统需要保留对底层边界的控制能力。
* **Abstraction 与 Observability**：安全抽象可以隐藏常规细节，但不能让系统在故障时失去可观察证据。

本章结论
--------

框架选择应按 ``Product Constraint → Boundary Behavior → Default → Observability → Escape Hatch → Reversibility`` 评估。最合适的框架不是 feature 最多或语法最漂亮的框架，而是能清楚封装目标路径、又不隐藏关键控制面的框架。