第003章：Browser, Server, Edge, Database, CDN, and Build-Time Boundaries
=========================================================================

核心知识点
----------

* Web 边界表示一组责任封装：能读取什么状态、信任什么输入、暴露什么输出、缓存什么结果、失败时由谁恢复。
* Browser boundary 接收用户输入、创建 navigation/data request、维护 document、DOM、JS heap、history、storage，并执行同源、CORS、CSP、cookie 与 permission policy。
* Browser 是低信任边界。用户可观察和修改 client-side state，因此 secret、数据库凭据和最终授权不能只存在于浏览器。
* Server boundary 拥有 request context、secret、session validation、business logic 与可信数据访问，可裁剪数据库字段后再暴露给 client。
* Edge boundary 靠近用户，适合 redirect、rewrite、header normalization、locale、A/B routing、bot filter、缓存 key 等早期决策；其能力由具体 edge runtime 限制。
* Database boundary 拥有 durable state、transaction、constraint、index、concurrency control 与 recovery。浏览器和缓存中的状态通常只是数据库事实的副本或派生结果。
* CDN boundary 负责全球分发和共享缓存。它降低 latency 与 origin load，也引入 cache key、TTL、revalidation、purge、personalization 与 stale response 风险。
* Build-time boundary 决定 static output、module graph、client/server/edge bundle、asset hash、manifest 与 environment capture；它会提前决定运行时能够加载什么代码。
* 一次边界穿越会改变信任、序列化、生命周期、缓存和错误语义。现代 Web 的很多复杂问题都发生在“状态跨边界后语义发生变化”的位置。
* 判断一段逻辑放在哪个边界，应综合 capability、trust、latency、consistency、security、cost 与 failure recovery，而不是只看开发体验。

关键路径
--------

/dashboard 的基础路径：

::

   user intent
   → browser request
   → CDN lookup
   → edge decision
   → server request context
   → database durable state
   → HTML / JSON response
   → CDN / network
   → browser render and local state

Build-time 对运行时的影响：

::

   source modules + env + assets
   → build graph
   → client bundle / server bundle / edge bundle / static output
   → deploy
   → each runtime executes only its generated artifact

概念辨析
--------

* **Browser Storage 与 Database**：浏览器存储改善本地体验，database 通常负责权威持久事实、事务和跨用户一致性。
* **Server 与 Edge**：两者都可执行可信代码，但 edge 更强调地域接近和早期判断，通常能力更受限。
* **CDN 与 Database Replica**：CDN 缓存 HTTP/asset response 副本，数据库副本参与数据读取和一致性模型，语义不同。
* **Build-Time Env 与 Runtime Env**：构建时注入的值会固化进 artifact；runtime env 则在实际执行时读取，二者不能混用。
* **Boundary Crossing 与 Function Call**：跨边界通常需要序列化、协议、安全检查和失败处理，成本和语义都比进程内调用更复杂。

本章结论
--------

现代 Web 的基础边界图是 ``Browser ↔ CDN/Edge ↔ Server ↔ Database``，并由 ``Build Time`` 提前生成各 runtime 的执行产物。架构判断必须先定位责任边界，再讨论框架和 API；边界放错，最终会表现为 secret 泄漏、缓存错乱、数据不一致、运行时不兼容或恢复失败。