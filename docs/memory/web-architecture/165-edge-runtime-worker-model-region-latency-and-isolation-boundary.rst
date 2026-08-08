第165章：Edge Runtime, Worker Model, Region, Latency, and Isolation Boundary
===========================================================================

核心知识点
----------

* Edge runtime 把部分请求处理部署到靠近用户的位置，适合 redirect、rewrite、cache decision、geo routing、轻量 auth、A/B test 和 header policy。
* Edge 的低延迟收益只在完整路径上成立。``user → edge`` 变短，但如果 ``edge → database`` 变成跨区域远程访问，总延迟可能反而增加。
* Worker/isolate model 通常比传统 server process 更轻，启动快、资源上限更严格，生命周期和全局状态语义也更弱。
* Edge global state 只适合不可变配置、惰性 client、规则表和可丢失缓存；购物车、session、权限和订单状态不应依赖 isolate 内存持久化。
* Edge runtime 的 host capability surface 通常更小。Node builtin、native addon、文件系统、子进程、长 TCP、动态执行和长期后台任务可能受限。
* 代码能被打包进 edge bundle，不等于 runtime 真能执行；依赖的实际 API、平台 binding、CPU/memory/subrequest 限制都必须核对。
* Edge cache 与 edge compute 应一起设计：request rewrite、cache key、KV/regional cache、static asset 和 fallback-to-origin 是一条路径。
* Region selection 要从 data ownership 出发。强一致 database、余额、库存、权限与交易状态通常不能因为 edge 更近就随意读取陈旧副本。
* 适合 edge 的状态通常来自 request、公共配置、近端 cache 或低风险 eventually consistent read model。
* 多租户 edge 平台依赖严格 isolation boundary；CPU、memory、subrequest、connection 和 secret scope 都属于平台安全模型。
* Edge 最适合轻量、少依赖、低状态、可缓存、可降级逻辑；重事务、重计算、native library 和大文件处理通常更适合 server/worker service。

关键路径
--------

Edge 请求：

::

   browser
   → nearest edge runtime
   → inspect URL/header/cookie/geo
   → compute cache key / route decision
   → edge cache hit: return
   → miss: call origin/regional service
   → optional cache write
   → response

Edge 选型：

::

   user latency goal
   → identify data owner/region
   → list runtime capability needs
   → verify cache/read-model strategy
   → verify isolation/resource limits
   → define origin fallback

概念辨析
--------

* **Edge Runtime 与 Origin Server**：edge 负责早期、近用户的轻量决策；origin 通常承担更完整的业务和数据能力。
* **Edge Compute 与 Edge Cache**：前者执行代码，后者复用响应；两者常协作但不是同一对象。
* **Near User 与 Near Data**：代码靠近用户不代表靠近数据库，关键路径必须把数据位置算进去。
* **Worker Global State 与 Durable State**：全局变量可能被复用但不可依赖持久，durable state 要外置。
* **Edge-Compatible 与 Node-Compatible**：能在 edge 运行的代码通常要求更窄 host capability，并不等于完整 Node 兼容。

本章结论
--------

Edge 架构应按 ``User Location → Edge Decision → Data Location → Runtime Capability → Isolation → Fallback`` 阅读。Edge 的价值来自缩短真正的关键路径，而不是简单把 server 代码搬到边缘；只有数据位置、能力边界和缓存策略都匹配时，低延迟收益才可靠。