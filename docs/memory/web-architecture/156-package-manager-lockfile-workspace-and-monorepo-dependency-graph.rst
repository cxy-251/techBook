第156章：Package Manager, Lockfile, Workspace, and Monorepo Dependency Graph
============================================================================

核心知识点
----------

* Package manager 把 ``package.json`` 中的版本范围、peer、optional、workspace、alias、override 等约束解析成可安装的具体依赖图。
* 依赖相关对象至少有五层：manifest constraints、resolved graph、physical install layout、runtime resolution、artifact graph；“依赖问题”必须先定位在哪一层。
* Lockfile 记录一次解析后的具体依赖世界，包括版本、来源、integrity 和子依赖关系，是 CI、团队协作、部署和回滚可重复性的核心输入。
* Lockfile 不冻结完整机器环境。Node、包管理器版本、OS/CPU、registry 配置、native toolchain、optional dependency 和 install scripts 仍会改变实际结果。
* Transitive dependencies 是应用供应链的一部分，会影响安全、bundle 体积、构建时间、许可证、native binary 与运行时行为。
* ``dependencies``/``devDependencies`` 只是声明意图；真正暴露面要看包是否在 build time 执行、是否进入 client/server/edge artifact、是否处理 secret 或用户输入。
* Workspace 把多个内部 package 连接进同一依赖图，适合 shared types、UI、server library 和工具链；内部包边界仍需匹配真实 runtime。
* Monorepo dependency graph 应与 build/test/deploy boundary 对齐，避免 client package 依赖 server package、循环引用和部署产物污染。
* Hoisting、dedupe、peer resolution、pnpm symlink/store、alias、override 和 patch 会改变最终 runtime 实际加载的版本，不能只看顶层 manifest。
* Install lifecycle script 是供应链执行边界。新增 postinstall/native binary/download 行为应被 review 和 CI policy 控制。
* 依赖升级要同时观察 lockfile diff、产物体积、runtime target、已知漏洞和构建行为，而不是只看直接依赖版本号。

关键路径
--------

依赖解析到运行时：

::

   package.json constraints
   → package manager resolution
   → lockfile concrete graph
   → physical install layout
   → workspace/internal package links
   → bundler/runtime module resolution
   → client/server/edge artifacts

可重复构建：

::

   commit + lockfile
   + pinned package manager/runtime
   + frozen install
   + controlled build env
   → reproducible dependency world
   → reproducible artifacts

概念辨析
--------

* **package.json 与 Lockfile**：前者声明允许范围，后者记录具体解析结果。
* **Resolved Graph 与 Installed Layout**：解析图说明版本关系，磁盘布局决定 loader 实际怎样找到模块。
* **Workspace 与 Monorepo**：workspace 是包管理连接机制，monorepo 是仓库组织方式；两者常组合但不等同。
* **Direct 与 Transitive Dependency**：直接依赖由项目声明，间接依赖由依赖继续拉入；二者都属于供应链。
* **Dev Dependency 与 Production Exposure**：字段位置不决定最终暴露面，build-time 执行与 artifact inclusion 才决定真实风险。

本章结论
--------

依赖系统应按 ``Constraint → Resolution → Lockfile → Install Layout → Runtime Resolution → Artifact`` 阅读。Package graph 既是构建输入，也是供应链、安全和部署边界；可重复安装只是起点，最终还要确认实际进入各 runtime 的依赖世界。