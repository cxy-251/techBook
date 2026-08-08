Form and Action Models in Full-Stack Frameworks
===============================================

核心知识点
----------

* Full-stack form/action 模型的核心不是框架语法，而是把 ``User Intent → Form → HTTP Request → Trusted Server Action → Durable Mutation → Navigation/Revalidation`` 连成一条路径。
* form 负责字段与提交意图，浏览器负责请求构造，server action/route action 负责可信验证和 mutation，route/page 负责把结果重新映射成用户可见状态。
* Server Action 把权限、secret、数据库访问和最终业务规则留在 server boundary，可减少同一规则在客户端、API 和数据层多份实现造成的 drift。
* Route Action 把写入、字段错误、redirect、revalidation 和当前用户流程放到同一路由上下文，便于明确“从哪里提交、写了什么、成功后去哪里、哪些读取需要刷新”。
* progressive enhancement 让框架能力更稳：基础 HTML form 在 JavaScript 未加载时仍能提交；增强路径再提供 pending、局部错误、乐观反馈、软导航与缓存刷新。
* action 并不会自动解决一致性。提交后仍要明确 server cache、query cache、loader data、RSC/data payload 等副本的失效范围，并处理重复提交、并发与失败恢复。

关键路径
--------

``Route renders form → User edits controls → Browser/form framework submits request → Route/Server Action parses input → Session/auth/business validation → Domain service/database mutation → Return field error | redirect | result → Revalidate/invalidates affected read models → UI shows committed server state``

使用框架时应把 API 名称还原成四个问题：代码在哪个 runtime 执行、请求如何跨边界、权威状态由谁修改、结果如何回到当前 navigation 与 cache state。

概念辨析
--------

* **Server Action vs RPC magic**：表面像函数调用，真实系统仍是 browser 到 server 的网络 mutation，存在认证、序列化、失败与重试边界。
* **Route Action vs domain service**：route action 负责 request/route 适配；可复用业务规则应下沉到独立 service/domain 层，避免和路由目录强耦合。
* **Action result vs durable truth**：返回 ``ok`` 只是请求结果；数据库提交和后续读取才定义持久化事实。
* **Revalidation vs client state patch**：revalidation 重新读取权威副本；局部 patch 只是客户端对当前结果的更新策略。
* **Progressive enhancement vs framework dependency**：前者利用框架提升体验但保留 Web 基础能力；后者让核心任务只能在完整客户端 runtime 存活。

本章结论
--------

现代框架重新采用 form/action，是把用户写入重新对齐到 Web 原生的请求与导航边界。框架应缩短这条路径的代码，而不是隐藏它；只要始终能指出 form、request、server action、database、cache 和最终 URL 的责任，写入模型就具备可迁移性。