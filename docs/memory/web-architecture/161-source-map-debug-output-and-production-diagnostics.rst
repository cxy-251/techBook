第161章：Source Map, Debug Output, and Production Diagnostics
=============================================================

核心知识点
----------

* 线上真正执行的是被 transform、bundle、split、minify 后的 artifact，生产诊断必须把 runtime error 重新映射到原始源码和具体 release。
* Source map 解决“生成代码位置 → 原始源码位置”的映射问题。它不能独自解决“这是哪个 release、哪个 runtime、哪个部署目标”的版本归属问题。
* 稳定诊断至少需要 generation file、line/column、release id、commit SHA、artifact manifest、source map status 与 deployment target。
* Source map 必须与精确 artifact hash 匹配。错误 release 的 map 会产生错误堆栈映射，比没有 map 更危险。
* 多级 transform 形成 source-map chain。TypeScript、Babel/SWC、bundler、minifier 中任一阶段丢失映射，最终只能还原到中间产物。
* Source map 同时是信息暴露边界。公开 map 可能包含源码、``sourcesContent``、目录结构、注释和内部实现，需要按产品风险选择公开、nosources、hidden/private upload 或完全不生成。
* Production 常用 hidden/private source map：构建生成 map，客户端 bundle 不公开引用，由 CI 上传到受控错误平台并绑定 release。
* Build metadata 将错误连接到 release。Release id、commit、build time、runtime、artifact hash、map upload status 应作为发布事实统一保存。
* Minification/mangling 改善传输体积，却降低原始 stack trace/profile 可读性；生产错误平台需要 symbolication/source map 才能恢复可行动上下文。
* Full-stack 项目同时有 client、server、edge 等产物，诊断时必须先定位 runtime；同名 route 在 browser chunk 和 server action 中是不同 artifact。
* Manifest、bundle stats、chunk graph、source map、deploy log 与 runtime error link 共同组成 build observability。
* Debug artifacts 的发布、缓存、访问控制与保留周期应有明确规则，不能由构建目录默认内容决定。

关键路径
--------

生产错误定位：

::

   runtime error
   → generated artifact + line/column
   → release id / runtime target
   → artifact manifest
   → matching source map
   → original source file/line/symbol
   → commit + owner + fix

发布诊断材料：

::

   build
   → emit artifact hashes + manifests + maps + stats
   → assign release/commit metadata
   → upload private maps/diagnostics
   → deploy artifacts
   → runtime errors carry same release id

概念辨析
--------

* **Source Map 与 Source Code**：source map 是位置映射，可选择包含或不包含源码正文。
* **Artifact Hash 与 Commit SHA**：artifact hash 标识具体产物内容，commit SHA 标识源码版本；构建环境变化可能让同一 commit 产生不同 artifact。
* **Minification 与 Obfuscation**：minification 主要减少体积，mangling/obfuscation 改变符号可读性；都可能增加诊断难度。
* **Build Metadata 与 Runtime Logs**：前者说明产物来自哪个发布，后者说明产物运行时发生了什么；二者必须可关联。
* **Public Debug Output 与 Private Diagnostics**：是否生成调试材料和是否公开它们是两个独立决策。

本章结论
--------

生产诊断应按 ``Runtime Error → Artifact → Release → Source Map/Metadata → Original Source`` 建立闭环。Source map 只是其中一环；真正可靠的 build observability 要让每个 client/server/edge 产物都能追溯到精确构建、源码和部署目标，同时控制调试信息暴露。