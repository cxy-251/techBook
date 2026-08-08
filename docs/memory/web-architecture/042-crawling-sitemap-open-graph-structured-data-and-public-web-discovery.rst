Crawling, Sitemap, Open Graph, Structured Data, and Public Web Discovery
=======================================================================

核心知识点
----------

* Public Web Discovery 描述公开页面如何被 crawler、搜索引擎、社交平台和链接预览系统发现、抓取、解释、缓存和重新访问；它是 URL、HTML、HTTP 与机器可读 metadata 的联合路径。
* Crawlability 先要求 URL 可达、服务器能直接返回可解释响应、链接可被发现。完全依赖客户端内存和点击后 JavaScript 才存在的内容，会提高机器发现和恢复成本。
* ``robots.txt`` 主要表达 crawler 访问策略；页面级 ``meta robots`` 或 HTTP ``X-Robots-Tag`` 表达索引/跟随策略。禁止抓取与禁止索引不是同一个概念。
* Sitemap 是站点主动提供的 URL 发现清单，适合大规模、深层、动态或更新频繁站点；它不能替代正常链接结构、正确 status code 和 canonical。
* Canonical 用于声明内容的首选 URL，避免参数、重复路径和多入口把同一内容拆成多个公开身份；它是提示，不是 redirect。
* Open Graph、Twitter Card 等 metadata 控制社交分享的标题、描述、图片和类型；这些系统常独立缓存，因此修复页面后外部预览不一定立即更新。
* Structured Data 用 JSON-LD 等机器可读格式表达产品、文章、组织、面包屑等实体关系。它必须与用户可见内容一致，不能成为只给 crawler 的另一套事实。
* HTTP status、redirect、cache、locale、authentication 和 deployment 都会改变 discovery path；公开页面应让机器与普通用户看到一致、稳定、可长期寻址的结果。

关键路径
--------

发现与抓取：

``known URL / link / sitemap → crawler → DNS/TLS/HTTP → status/robots decision → HTML response → parse links/metadata/content → index or cache``

页面身份：

``request URL → redirect/canonical/hreflang → preferred public URL → search representation``

社交预览：

``shared URL → social crawler → initial HTML metadata → OG image/title/description → platform cache → preview``

结构化数据：

``server-visible business facts → JSON-LD/schema markup → crawler parse/validation → enriched machine understanding``

诊断公开发现问题时，应先验证 crawler 能否直接获取 URL，再检查 status/robots/canonical，之后才看 metadata、structured data 与外部平台缓存。

概念辨析
--------

* **Crawling vs Indexing**：crawling 是访问和读取；indexing 是搜索系统决定是否把内容加入索引。
* **``robots.txt`` vs ``noindex``**：前者主要控制 crawler 是否抓取路径；后者表达页面不应进入索引。
* **Sitemap vs navigation links**：sitemap 是机器发现辅助入口；正常链接仍定义站点真实可遍历结构。
* **Canonical vs Redirect**：canonical 提示首选身份；redirect 实际改变访问目标。
* **Open Graph vs Structured Data**：Open Graph 主要服务分享预览；structured data 更偏向实体与内容语义表达。
* **Client-rendered metadata vs initial HTML metadata**：很多 crawler 能执行部分 JavaScript，但稳定公开身份应优先存在于直接可获取的初始响应中。

本章结论
--------

公开 Web 发现依赖稳定 URL、正确 HTTP 语义、可解析 HTML 和一致的机器元数据。Sitemap、robots、canonical、Open Graph 与 structured data 都是这条路径的控制信息。它们只有与服务器实际内容、缓存和部署状态保持一致，才能形成可靠的搜索、分享和长期链接入口。