第158章：Bundler Architecture, Code Splitting, Tree Shaking, and Chunk Graph
===========================================================================

核心知识点
----------

* Bundler 从一个或多个 entry point 出发，解析模块、资源与插件生成的依赖关系，构建 module graph，再生成目标 runtime 可加载的产物。
* Entry 可以是 HTML、client entry、server entry、route entry、worker entry 或 library entry；入口类型决定后续 runtime 假设。
* Module graph 描述源码层依赖，chunk graph 描述构建后浏览器或 runtime 实际需要加载的文件关系。
* Code splitting 把一个依赖图切成多个可加载 chunk，常由 dynamic import、route boundary、worker entry、CSS split 或 framework 规则触发。
* Split point 应围绕真实用户路径设计。首屏核心路径应减少 waterfall，低概率功能适合 lazy load，高概率下一步可使用 preload/prefetch。
* Vendor split 可以提高缓存稳定性，但会改变首屏体积和依赖 waterfall；第三方库不应机械统一拆成一个大 vendor chunk。
* Tree shaking 依赖 ESM 静态结构、used exports、side-effect 判断和 minifier；CommonJS、动态属性访问、顶层副作用会降低裁剪能力。
* ``sideEffects`` 配置错误既可能让无用代码无法删除，也可能误删 CSS、polyfill、全局注册等必须执行的模块。
* Chunk graph 直接决定 runtime loading waterfall：一个 lazy feature 可能同时触发 JS、CSS、WASM、image 与 shared chunk 请求。
* Bundler plugin 是 build-time capability extension，可改写 resolution、virtual modules、CSS/assets、env、manifest 和 framework-specific transform，因此插件同样属于构建边界。
* Development server 与 production build 目标不同：开发阶段优先快速启动/HMR，生产构建优先 minify、hash、split、tree shaking 与可缓存输出；两者行为不能简单等同。
* Bundle 优化是请求数量、首包大小、缓存粒度、解析执行成本和交互延迟之间的权衡。

关键路径
--------

从入口到 chunk：

::

   entry point
   → resolve imports/assets/plugins
   → module graph
   → mark dynamic/route/worker split points
   → tree shake unused code
   → form chunk graph
   → emit hashed JS/CSS/assets/manifests
   → browser/runtime loads chunks

首屏分析：

::

   user route
   → required initial chunks
   → shared dependencies
   → preload/modulepreload
   → parse/compile/execute
   → lazy chunk on interaction

概念辨析
--------

* **Module Graph 与 Chunk Graph**：前者是源码依赖关系，后者是产物加载关系。
* **Code Splitting 与 Lazy Loading**：code splitting 生成独立产物，lazy loading 决定运行时何时请求它。
* **Tree Shaking 与 Minification**：tree shaking 删除可证明未使用代码，minification 压缩仍保留的代码。
* **Vendor Split 与 Better Cache**：独立 vendor chunk 可能提高缓存，也可能放大首包；需按用户路径判断。
* **Dev Server 与 Production Build**：开发行为服务迭代速度，生产构建服务部署和性能，产物语义不同。

本章结论
--------

Bundler 应按 ``Entry → Module Graph → Split/Shake → Chunk Graph → Runtime Requests`` 阅读。优化目标不是“文件越少”或“chunk 越小”，而是让真实用户路径以合理的请求、缓存和执行成本获得所需代码。