第191章：Build and Deployment Toolchain Mapping
===============================================

核心知识点
----------

* 现代 Web 从源码到线上要经过两次映射：build tool 把 source graph 变成 runtime artifact，hosting platform 再把 artifact 分配到 browser、server、edge、CDN、region 和 cache。
* Source graph 是开发者看到的 import/dependency 关系；artifact graph 是浏览器和平台真正执行/加载的 client chunk、server bundle、edge bundle、CSS、asset、manifest 与 source map。
* Manifest 是构建产物与运行时路由之间的桥，记录入口、chunk、CSS、preload、route、asset 和 runtime output 的对应关系。
* Client chunk 进入 browser boundary，server output 进入 server runtime，edge bundle 进入 edge runtime，static asset 进入 CDN/object storage，source map 进入 observability boundary。
* Vite 的稳定特征是把开发反馈路径与生产交付路径分开：dev 偏按需 ESM/HMR，production 偏 bundle、hash、CSS、manifest 与可部署 artifact。
* Webpack 把 entry、module、loader、plugin、chunk、runtime 与 output 统一成高度可配置 dependency graph；能力强，配置顺序与插件交互也更复杂。
* Rollup 更强调 ESM 静态分析、tree shaking 与 library/production bundle；适合输出结构可控、模块边界清晰的场景。
* Turbopack/Rolldown 等新工具主要改变图计算和增量构建效率，不改变最终必须回答的 artifact、runtime target、chunk 与 deployment 问题。
* Build-time env 与 runtime env 必须区分。被编译进 client bundle 或 server artifact 的值不会因为部署平台后来改变量就自动更新。
* Public env prefix 是发布声明；任何进入客户端 artifact 的值都应视为公开数据，不能包含 secret。
* Hosting platform 负责把 static、serverless、edge、region、CDN、preview/prod、secret/config 和 route policy 映射到线上资源。
* Rollback 必须覆盖 artifact、cache、environment、database migration 与 region rollout；只切回代码版本不一定恢复旧系统状态。

关键路径
--------

源码到运行时：

::

   source graph
   → transform/transpile
   → module/chunk graph
   → client/server/edge/static artifacts
   → manifest + source maps
   → hosting platform routing
   → CDN / server / edge runtime
   → browser request

线上资源故障：

::

   browser missing/wrong resource
   → inspect requested URL
   → inspect HTML/manifest reference
   → inspect build output
   → inspect deploy upload/runtime mapping
   → inspect CDN/cache/base path
   → inspect release/environment version

概念辨析
--------

* **Source File 与 Artifact**：source 是构建输入，artifact 才是线上真正被加载或执行的输出。
* **Bundler 与 Hosting Platform**：bundler 决定输出形状，hosting platform 决定输出在哪里运行和如何被路由。
* **Dev Server 与 Production Server**：开发服务器优化编辑反馈，生产运行时服务真实 artifact 和请求，行为不能默认等价。
* **Build-Time Env 与 Runtime Env**：前者在构建阶段固化，后者在请求执行阶段读取；作用域和更新方式不同。
* **Deploy 与 Release**：deploy 是产物上线动作，release 还包含流量切换、cache、config、migration、监控和回滚。

本章结论
--------

构建部署应按 ``Source Graph → Artifact Graph → Runtime Target → Platform Location → Cache/Environment → Release/Rollback`` 阅读。工具选择只有映射到实际输出文件、运行位置和发布恢复路径后，才有架构意义。