第142章：Domain Logic, Service Layer, Repository, and Use Case Boundary
=======================================================================

核心知识点
----------

* Domain logic 定义“系统里的动作在业务上意味着什么”，例如订单能否成立、文章能否发布、库存能否预留、成员能否被邀请；它超出简单 CRUD。
* UI action 只表达用户意图，不能证明权限、价格、库存、tenant、资源状态和业务前提。可信 use case 必须在 server/backend 重新读取事实并重新判断。
* Service layer/use case 负责跨边界协调：request context、authorization、validation、transaction、repository、external service、event、cache invalidation、audit 与 result mapping。
* Domain logic 与 service coordination 应分离。Domain 负责规则与状态转换，service 负责顺序、IO、事务和副作用；混在一起会把业务规则散落成 handler script。
* Repository 负责在 domain 与 persistence 之间建立访问契约，隐藏表名和 ORM 细节，同时应保留 transaction、lock、pagination、freshness、batch 与 query-cost 等重要信号。
* Repository 不应退化为万能 CRUD wrapper。面向具体 use case 的接口更能表达真实读取需求，例如 checkout snapshot、locked inventory 或 tenant-scoped aggregate。
* Use case boundary 应稳定于 framework 之外。同一个 ``submitOrder`` 可以由 REST、GraphQL、server action、background worker 或 admin tool 调用，而业务语义保持一致。
* 涉及 permission、payment、inventory、quota、subscription、tenant、audit 等规则必须运行在 trusted boundary；前端 disable/hidden button 只能改善 UX。
* Cross-cutting concerns 需要显式进入用例：transaction、audit、rate limit、metrics、cache invalidation、event publish 与 error mapping 不能靠隐式 hook 随机拼接。
* Database constraint 仍是最终保护线；domain/service 决定业务语义，repository 映射持久化，database 保护存储不变量。
* 清晰 domain boundary 能降低更换 UI framework、API style、ORM、queue 或 deployment platform 的风险，因为核心规则不依赖入口语法。

关键路径
--------

一次业务用例：

::

   browser intent
   → API / server action
   → request identity + tenant context
   → use case / service
   → authorization + load required facts
   → domain decision
   → repository writes inside transaction
   → commit
   → audit / event / cache invalidation
   → domain result mapped to response

责任分层：

::

   UI          = collect intent + feedback
   handler     = protocol/request boundary
   use case    = orchestration + failure policy
   domain      = business meaning + rules
   repository  = persistence contract
   database    = durable constraints + transaction

概念辨析
--------

* **Domain Logic 与 CRUD**：CRUD 描述数据操作，domain logic 描述为什么该操作成立以及成立后系统承诺什么。
* **Service Layer 与 Domain Model**：service 组织流程与副作用，domain model 负责业务规则和状态转换。
* **Repository 与 ORM**：repository 是领域侧数据访问契约，ORM 只是其可能使用的一种实现工具。
* **Use Case 与 Route Handler**：route handler 处理 HTTP/框架入口，use case 定义可从多个入口复用的可信业务动作。
* **UI Capability 与 Authorization**：UI capability 是可信策略的展示投影，最终授权必须在执行操作时重新求值。

本章结论
--------

业务写路径应按 ``Intent → Trusted Use Case → Domain Decision → Repository/Transaction → Side Effects → Result`` 组织。稳定架构让页面和框架只负责入口，把真正的业务规则、权限和持久化边界留在可测试、可复用、可审计的可信层。
