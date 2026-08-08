第148章：CDN Cache, Edge Cache, Region, and Global Delivery
============================================================

核心知识点
----------

* CDN cache 通过把可共享响应放到更靠近用户的节点，降低 RTT、源站带宽和重复计算；它缓存的是 origin 结果副本，不拥有业务事实。
* Edge cache 同时是 geographic boundary 与 policy boundary。Region、cache rule、TTL、header/cookie 处理和 custom key 都会影响同一请求是否命中。
* CDN 最适合 public、stable、versioned 内容，尤其是带内容 hash 的 JS、CSS、image、font。它们可长期缓存而不依赖频繁 purge。
* HTML 与公开动态 API 可以共享缓存，但需更短 TTL、validator、tag 或 revalidation；用户私有数据通常应绕过共享缓存或明确使用 private 语义。
* Shared cache key 必须覆盖所有会改变响应的公共维度，例如 query、locale、country、currency 或受控 experiment bucket；漏维度会造成错误共享。
* Personalization 会降低共享缓存安全性。Cookie、Authorization、tenant、role、member price 等一旦影响 body，就必须拆到私有层或进入严格隔离的 key。
* 缓存维度越多，正确性越高但 fragmentation 越严重；高基数用户维度通常不适合直接塞进全局共享 key。
* Purge/invalidation 是发布操作的一部分。单 URL、prefix、cache tag、surrogate key 和全量 purge 的影响范围不同，应优先选择最小精确范围。
* Regional cache 会制造短暂不同世界。不同 POP/region 可能拥有不同年龄、版本和 purge 到达时间，因此全球用户可能暂时看到不同响应。
* 版本化静态资源应采用“asset 先发布、HTML 后切换、旧 asset 保留”的顺序，避免新旧 HTML 在区域传播期间引用不存在的 chunk。
* CDN 正确性必须可观察：cache hit/miss/revalidate/bypass、Age、release id、cache tag 和 region 都应能进入诊断链。

关键路径
--------

CDN 命中：

::

   browser request
   → edge applies cache policy
   → build shared cache key
   → hit + fresh: return edge copy
   → miss/stale: fetch or revalidate origin
   → store according to policy
   → return response

全球发布：

::

   upload new versioned assets
   → verify assets globally reachable
   → publish HTML / route output
   → invalidate only mutable entry points
   → keep old hashed assets
   → monitor region/version skew

概念辨析
--------

* **CDN 与 Origin**：CDN 保存副本，origin 生成权威响应。
* **Edge Compute 与 Edge Cache**：前者执行代码，后者复用响应；二者可同处边缘但责任不同。
* **Public Response 与 Anonymous Request**：匿名请求不自动等于可共享；是否共享取决于响应内容与上下文依赖。
* **Purge 与 Versioned URL**：purge 删除/失效旧副本，versioned URL 通过新身份绕开旧副本；静态资源优先后者。
* **Region Difference 与 Data Corruption**：不同 region 的旧响应可能只是缓存传播差异，不代表数据库事实不同。

本章结论
--------

全球缓存应按 ``Shared Eligibility → Cache Key → Region → Freshness → Purge/Versioning → Observability`` 设计。CDN 的优势来自公共副本可安全复用；一旦响应依赖用户私有上下文，就应缩小共享范围，而不是用复杂缓存规则掩盖权限边界。