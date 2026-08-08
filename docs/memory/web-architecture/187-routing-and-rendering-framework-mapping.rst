第187章：Routing and Rendering Framework Mapping
================================================

核心知识点
----------

* Full-stack routing framework 把 URL matching 扩展成应用边界：route、layout、data、action、error、cache 与 deployment 常被绑定在同一工作单元附近。
* 比较 Next.js、React Router/Remix、SvelteKit、Nuxt、Astro 时，应先回答 HTML 在哪里生成、数据在哪里读取、JavaScript 在哪里执行、交互在哪里激活、缓存由谁控制。
* Next.js App Router 以 route segment + component tree 为核心，把 Server Components、Client Components、SSR/SSG/ISR/streaming、route handler 与 server action 放进同一路径。
* Next.js 中 server/client boundary 决定哪些代码和数据会进入浏览器；Server Component 能访问 server-only 数据，Client Component 承担事件与浏览器 API。
* React Router / Remix 更接近 ``navigation → loader``、``mutation → action``。Route module 把数据读取、表单写入、pending、redirect 与 error boundary 组织在一起。
* Loader/action 模型能让 action 完成后重新验证 route data，减少手工“提交后再刷新哪个接口”的胶水，但仍需理解 revalidation 粒度和并发。
* SvelteKit/Nuxt 通过文件路由、page/layout、server load、endpoint 与 adapter 把 Svelte/Vue UI 延伸到 full-stack route boundary。
* Astro 以静态 HTML 与 islands 为核心，大部分页面保持无客户端 JS，只有需要交互的局部组件激活；适合内容占比高、交互局部化的产品。
* Routing framework 的关键差异在“工作单元”：route segment、loader/action、page/layout、island 会决定缓存、错误和重新执行的粒度。
* Prefetch 会提前触发资源或数据读取。它能降低导航延迟，也可能改变 credential、cache、rate limit 和 server load，因此必须纳入边界判断。
* Rendering model 与 deployment target 不能分开。Node、serverless、edge、static output 会改变数据库驱动、streaming、region 和运行时 API 可用性。
* 框架升级时，缓存默认值、server/client split、route config 与 adapter 行为可能改变；稳定架构文档应记录当前版本对应的真实路径，而不是只记 API 名称。

关键路径
--------

路由与渲染映射：

::

   URL/navigation
   → route match
   → select page/layout/segment/route module
   → execute data read
   → produce HTML/RSC/data payload
   → deliver client JavaScript
   → hydrate/activate interactive region
   → mutation/action
   → revalidation/cache invalidation

比较框架：

::

   same product route
   → locate HTML production
   → locate data read runtime
   → locate client activation boundary
   → locate mutation entry
   → locate cache/revalidation owner
   → locate deployment artifact/runtime

概念辨析
--------

* **Route 与 Page File**：route 是 URL 到执行责任的边界，page file 只是框架表达该边界的一种组织方式。
* **Server Component 与 SSR**：Server Component 描述组件执行位置，SSR 描述 HTML 在请求阶段生成；二者相关但不是同一概念。
* **Loader 与 Client Fetch**：loader 通常与 navigation 生命周期绑定，client fetch 由组件或客户端数据层独立触发。
* **Island 与 SPA Component**：island 只激活局部交互，SPA component 通常处于更大客户端运行时树中。
* **Pre-render 与 Runtime Render**：前者在 build time 生成结果，后者在请求或浏览器运行时生成，能访问的状态不同。

本章结论
--------

Routing/rendering framework 应按 ``URL → Work Unit → Data Runtime → HTML Production → Client Activation → Mutation/Revalidation → Deployment`` 比较。框架名称不重要，重要的是它把哪一段系统路径变成默认工作单元，并让哪些边界保持可见。