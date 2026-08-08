第146章：Cache as a Multi-Layer Web System
===========================================

核心知识点
----------

* Cache 本质是分布式副本系统。Browser HTTP cache、CDN/edge cache、server cache、framework cache、service worker cache 与 client query cache 都在保存过去生成的结果。
* 缓存收益来自缩短路径、降低带宽和后端计算、保护源站以及提高故障时可用性；代价是引入 stale、invalidation、版本漂移和权限串用风险。
* 每一层缓存都必须明确五个对象：``location / key / lifetime / owner / invalidation path``。少一个维度，缓存就难以验证正确性。
* Cache location 决定它能知道什么。Browser 贴近单个用户；CDN 擅长公共共享；server 能看到可信业务上下文；client query cache 能看到页面交互和 mutation 状态。
* Cache key 定义“哪些请求属于同一结果”。会改变响应语义的 product id、tenant、locale、filter、permission version、release version 等必须进入身份设计。
* TTL、``max-age``、``stale-while-revalidate``、validator、tag、version 和 mutation event 共同定义副本何时失去可信度。
* Cache owner 决定谁有资格失效副本。Browser、CDN provider、应用服务、framework runtime 与 client cache 的 owner 不同，不能假设一次 purge 会自动刷新所有层。
* 静态 hash 资源适合长缓存，因为 URL 已表达版本；动态业务事实要按可接受 stale 窗口和失败影响选择更严格策略。
* Cache hit 只说明找到了副本，不说明副本仍符合当前请求语义。正确性判断必须同时验证身份、上下文和 freshness。
* 多层缓存事故应从用户可见路径反向追踪，而不是只检查数据库。数据库已经更新，较近缓存仍可能截断请求并返回旧版本。

关键路径
--------

多层读取：

::

   user request
   → browser/private cache
   → CDN / edge shared cache
   → server / framework cache
   → database or upstream authority
   → response
   → client query cache
   → UI

缓存设计检查：

::

   identify cached result
   → define cache location
   → define complete cache key
   → define freshness/lifetime
   → define owner
   → define invalidation/revalidation path
   → define stale/failure behavior

概念辨析
--------

* **Cache 与 Source of Truth**：cache 保存可失效副本，source of truth 决定冲突时以谁为准。
* **Private Cache 与 Shared Cache**：private cache 面向单个用户代理；shared cache 可服务多个用户，安全边界更严格。
* **Fresh 与 Correct**：fresh 表示仍在缓存生命周期内，correct 还要求 cache key 与请求上下文匹配。
* **Cache Key 与 URL**：URL 常是 key 的核心，但 locale、tenant、credential context、query 参数和版本可能也是响应身份。
* **TTL 与 Invalidation**：TTL 用时间让副本自然失效，invalidation 用事件主动宣布副本失信。

本章结论
--------

缓存架构应按 ``Copy Location → Cache Identity → Freshness → Ownership → Invalidation → Failure`` 阅读。缓存不是一个开关，而是跨多层运行时维护副本可信度的协议；性能收益只有在副本身份和失效责任正确时才成立。