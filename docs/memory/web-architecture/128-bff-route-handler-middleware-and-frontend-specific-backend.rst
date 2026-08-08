BFF, Route Handler, Middleware, and Frontend-Specific Backend
============================================================

核心知识点
----------

* BFF（Backend for Frontend）是面向特定前端体验的服务端边界，用于把通用领域服务转换成某个页面、设备或客户端需要的稳定 view model。
* BFF 的核心职责是聚合、塑形、保护：聚合多个内部服务，塑形为前端 contract，在可信 runtime 内完成身份、权限和字段裁剪。
* route handler 是 public HTTP boundary。即使文件位于前端框架目录附近，它仍运行在 server/edge/serverless runtime，必须处理输入校验、auth、secret、cache、错误和 response contract。
* middleware 位于最终 handler 之前，适合做 redirect、locale、experiment、header、rate limit、粗粒度 auth gate 等早期决策；它不应承载复杂 domain transaction 或依赖重型持久化状态的核心业务逻辑。
* BFF 应区分必需数据与增强数据。下游服务部分失败时，可以对推荐、优惠、非关键摘要做局部降级；身份、权限和主要业务数据失败时应返回明确整体错误。
* 个性化 BFF response 必须明确 cache scope。``private``、``Vary``、tenant、locale、experiment、credential 等维度必须与实际 response identity 对齐，避免跨用户或跨租户复用。
* BFF 是 public contract 与 internal contract 的隔离层；它能隐藏内部服务拓扑，但也会增加一跳编排、延迟、故障传播和 ownership 成本。

关键路径
--------

``Browser → CDN/Edge → Middleware → Route Handler/BFF → Identity/Tenant → Internal Services/Cache/DB → Shaped Frontend Response → UI``。

先判断 middleware 是否改变 URL、header、locale、auth 或 experiment，再定位 route handler 的真实 runtime，最后沿 BFF 下游依赖区分必需/可降级数据和超时边界。

对聚合请求优先并行独立下游，并给每个依赖定义 timeout、fallback 与 observability；BFF 不应让一个非关键服务无限阻塞整页响应。

概念辨析
--------

* **BFF vs generic API**：generic API 面向领域对象和多个消费者；BFF 面向具体前端流程和展示形状。
* **BFF vs proxy**：proxy 主要转发；BFF 会恢复身份、组合数据、裁剪字段、转换错误和定义前端 contract。
* **route handler vs component**：前者处理 HTTP 与可信资源；后者处理 UI。目录相邻不代表 runtime 相同。
* **middleware vs domain handler**：middleware 适合早期轻量决策；核心业务写入和事务应落在最终 server/domain boundary。

本章结论
--------

BFF 的价值是把前端体验需求与通用后端领域模型隔离开，并把聚合、字段暴露、权限和容错留在可信服务端边界。设计时必须同时控制 runtime、缓存、下游故障和 public contract。