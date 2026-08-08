第112章：Server-Only Data, Secret Boundary, and Safe Data Exposure
=================================================================

核心知识点
----------

* 浏览器是用户可观察、可调试、可复制的环境；任何进入 HTML、JSON、RSC payload、hydration data、client cache 或错误上报的数据都应视为已暴露。
* Server-only data 包括 secret、数据库连接、内部 token、admin SDK、风控标签、审计备注、内部权限模型、未裁剪实体和第三方私有响应；这些对象可以参与服务端判断，但不应直接跨到浏览器。
* 安全的数据路径应先做身份、tenant、资源与字段级授权，再构造最小 DTO，最后才序列化进入响应。
* UI 隐藏字段不构成安全边界。字段即使没有被组件渲染，只要已经序列化到浏览器，就可被 DevTools、扩展、缓存、内存或日志观察。
* Server-only code 需要由 runtime/import graph 保护；数据库 client、secret 和内部 SDK 不应被 Client Component、浏览器 hook 或共享 bundle 间接导入。
* Serialization 是实际 exposure boundary：``res.json``、HTML 内嵌状态、RSC payload、server action 返回值、GraphQL response、日志和缓存都属于序列化出口。
* Data minimization 同时降低安全、缓存、网络和 schema 耦合风险；跨边界对象应只包含当前 UI 与当前权限确实需要的信息。
* Cache scope 必须和 DTO 可见范围一致。用户私有或 tenant 私有数据进入共享 cache，会把一次字段暴露放大成跨用户泄漏。

关键路径
--------

``Browser Request → Server Route → Auth/Tenant Check → Server-Only DAL → Database/Internal Service → Authorization/Field Filtering → Safe DTO → Serialization → Browser``

在可信层内部可以读取宽对象和 secret；真正跨边界前必须缩成窄 DTO。日志、错误上报和缓存也要使用同样的最小化原则，不可因为“不是响应体”就忽略暴露风险。

概念辨析
--------

* **Server-only data vs private-looking UI data**：是否 server-only 由暴露能力决定，不由字段名或 UI 是否显示决定。
* **Authorization vs hiding**：授权决定数据能否离开可信边界；CSS、条件渲染和折叠只决定展示。
* **DTO vs database entity**：DTO 是面向跨边界 contract 的最小对象；数据库实体是内部持久化模型，二者不应默认等同。
* **Secret vs public configuration**：浏览器 bundle 中出现的配置应按公开数据处理；真正 secret 必须只在可信 runtime 读取。
* **Serialization vs rendering**：数据序列化到客户端时已经暴露，是否最终渲染并不能撤销暴露。

本章结论
--------

安全的数据读取不是“前端少显示几个字段”，而是在可信服务端完成授权、裁剪和最小 DTO 构造，并把序列化点当成不可逆的暴露边界。任何跨入浏览器、共享缓存、日志或第三方上报的数据，都必须先确认它属于当前用户、当前权限和当前页面所需的最小集合。