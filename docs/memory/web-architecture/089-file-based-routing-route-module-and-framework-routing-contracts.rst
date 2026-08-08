第089章：File-Based Routing, Route Module, and Framework Routing Contracts
=========================================================================

核心知识点
----------

* File-based routing 把源码目录、文件名、动态 segment 与特殊文件约定转换成公开 URL、route graph、运行时入口和构建产物。
* 目录结构一旦决定 URL 行为，就属于公共契约；重命名目录、动态参数或特殊文件可能同时改变外链、sitemap、缓存键、分析统计与权限规则。
* Route module 把某条路径附近的 UI、loader、action、metadata、headers、error boundary 和 revalidation 组织在同一边界。
* Route module 提升“从 URL 追到代码”的局部性，但核心业务规则不应被复制进多个路由文件；route module 更适合作为 request/response 与框架约定的适配层。
* Routing convention 是框架 API：特殊文件名不仅表示目录风格，还可能声明代码运行在 build time、server、edge 或 browser。
* 构建阶段常生成 route manifest、chunk graph、loader map、static path 或 server output，连接源码目录与真实 runtime。

关键路径
--------

``Source Directory → Route Convention → Build Manifest → Runtime Match → Route Module → UI/Data/Mutation/Error``

* 对 ``/shop/products/42?ref=home``，目录约定先把 ``shop/products/[id]`` 变成公开 route，并捕获 ``id=42``。
* 构建系统扫描特殊文件，生成 route manifest 与代码分割关系，决定导航时应加载哪些模块。
* Route module 接收 params、request、form data 等框架输入，再调用独立 domain/service 层完成数据与业务规则。
* loader/action 的 server 边界、组件的 browser/server rendering 边界、metadata 的 build/server 边界应分别标注，不能因为同文件而假设同 runtime。
* 路由目录改动前检查 URL 兼容、redirect、外链、缓存、analytics、权限与测试路径，必要时提供迁移策略。
* 客户端 router 最终仍要服从平台导航语义：deep link、reload、Back/Forward、form submit、scroll、focus 与 history 都不能被目录约定替代。

概念辨析
--------

* **File-based routing vs Web routing**：前者是框架组织方式；后者最终仍由 URL、HTTP、History 与浏览器导航语义约束。
* **Route module vs business module**：route module 适配路径和请求上下文；business module 保存可跨 route 复用的规则。
* **Directory locality vs architectural coupling**：把相关 route 行为放近有利于追踪，过度把 domain 规则绑定目录会增加迁移和复用成本。
* **Special file vs runtime**：文件名是框架契约，必须查清它被哪个构建阶段识别、最终在哪个 runtime 执行。
* **Source route tree vs generated manifest**：源码表达意图，构建产物才是运行时真正消费的路由映射。

本章结论
--------

File-based routing 的价值是把 URL、代码和路由责任靠近，代价是源码结构开始影响公共行为。工程上应把路由目录视作外部接口，把 route module 视作框架边界适配层，并明确 build、server、edge、browser 各自运行哪些代码。只要目录、manifest、runtime 与平台导航语义保持一致，框架约定才是生产力，而不是隐式耦合来源。
