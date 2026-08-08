第154章：Source to Artifact Transformation Path
================================================

核心知识点
----------

* 现代 Web 的线上行为大量在 build time 被固定：TypeScript 类型被移除、JSX 被转换、CSS 被抽取/内联、资源被 hash、路由进入 manifest、环境变量可能被静态替换、模块被分配到 client/server/edge output。
* Source code 不是孤立文件集合，而是“入口 + 依赖边 + 运行时意图 + 资源引用 + 配置条件”组成的结构化系统。
* Build pipeline 通常经历 ``parse/resolve → transform → module graph → split/optimize → emit artifacts → deploy``。
* Transformation 既改变语法，也改变语义：动态 import 会变成异步 chunk，CSS module 会改变类名，asset import 会变成 URL，env replacement 可能把值直接写进产物。
* Build time 决定 runtime 必须服从的约束，例如某段代码进入 browser 还是 server、某路由静态还是动态、某资源 URL 是什么、某变量是否被公开内联。
* Artifact shape 决定运行时加载、缓存和调试。文件数量、chunk 关系、hash、manifest、source map、CSS split 和 asset path 都会进入用户路径。
* Manifest 是源码与运行时产物之间的重要索引：route、entry、chunk、CSS、asset 和部署 target 关系都可通过 manifest 追踪。
* Build failure 应被视为系统边界失败。类型错误、模块解析、server/client 污染、环境变量缺失、目标 API 不兼容和资源路径错误都说明某个转换边界未成立。
* 调试构建问题应从产物反推：用户实际加载了哪个文件、它来自哪个 entry、经过哪些 transform、被部署到哪个 runtime。

关键路径
--------

源码到产物：

::

   source entry
   → resolve imports/assets/config
   → transform TS/JSX/CSS/MD/assets
   → build module graph
   → split by runtime/lazy boundary
   → optimize/minify/hash
   → emit client/server/edge/assets/manifests/maps
   → deploy to runtime/CDN

故障反查：

::

   runtime error / 404 / wrong asset
   → identify artifact + release
   → inspect manifest/output target
   → map artifact back to source graph
   → inspect transform/config decision

概念辨析
--------

* **Source File 与 Build Input**：源码文件只是输入之一，依赖关系、配置、target 和环境变量同样属于构建输入。
* **Transform 与 Bundle**：transform 改变单个模块语法/语义，bundle 组织多个模块和资源为可部署产物。
* **Build Time 与 Runtime**：build time 决定产物形态，runtime 只能执行已生成产物。
* **Artifact 与 Source**：用户运行的是 artifact，不是编辑器里的源码；source map/manifest 才负责把二者重新连接。
* **Build Error 与 Tool Error**：工具报错只是表现，根因通常是依赖、目标 runtime、边界或配置不一致。

本章结论
--------

现代 Web 构建应按 ``Source Intent → Transformation → Graph → Artifact → Runtime`` 阅读。构建系统不是脚手架附属物，而是决定代码在哪里运行、如何加载、如何缓存、如何诊断与如何回滚的架构层。