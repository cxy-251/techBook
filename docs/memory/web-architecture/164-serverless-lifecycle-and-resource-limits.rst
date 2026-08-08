第164章：Serverless Lifecycle and Resource Limits
=================================================

核心知识点
----------

* Serverless function 是事件驱动、短生命周期的计算单元。平台拥有 execution environment 的创建、复用、冻结和销毁权，应用只拥有当前 invocation 的处理逻辑。
* 一次 serverless 请求应拆成 ``event → environment selection → init → invoke → external state → response → reuse/shutdown``，不能只看 handler 函数。
* Cold start 把 runtime 启动、代码加载、模块初始化、连接准备等成本放进用户请求延迟，尤其会放大部署后和突发扩容时的尾延迟。
* Module-scope 初始化适合可复用的只读配置、client、模板和轻量缓存，但其成本会在新环境创建时支付。
* Warm state 可以复用连接、已加载模块和不可变对象；user、tenant、request body、trace span、当前权限等必须保持 invocation-local。
* Warm reuse 不是持久状态保证。实例可随时被回收，数据库连接也可能在冻结期间失效，因此复用只能被视为优化机会。
* Serverless 的执行时间、内存、CPU、payload size、临时文件系统、并发、连接数、部署包和后台任务窗口会反向塑造接口边界。
* 长任务、大文件上传、重型 PDF/图像处理和批量任务常应拆成 queue/job/object-storage 流程，而不是强行放在同步 invocation 内。
* Stateless design 不等于没有状态，而是把持久状态外置到 database、object storage、queue、cache、session store 或 workflow。
* 依赖体积和初始化路径会影响 cold start；重型 ORM、SDK、native library 和动态加载应按真实请求路径拆分。
* 安全边界要求跨请求数据隔离。全局 ``currentUser/currentTenant``、共享临时文件和遗留异步回调都可能造成实例复用污染。

关键路径
--------

Serverless invocation：

::

   HTTP/event trigger
   → platform selects warm/new environment
   → cold init if needed
   → invoke handler
   → read/write external state
   → produce response
   → environment frozen/reused or destroyed

长任务拆分：

::

   user request
   → validate + create durable job record
   → enqueue work
   → return job id
   → worker processes task
   → write result to object storage/database
   → client polls/subscribes/downloads

概念辨析
--------

* **Function Code 与 Execution Environment**：前者是部署产物，后者是平台为代码准备的实际运行容器/isolate。
* **Invocation State 与 Warm State**：前者只属于当前请求，后者可能跨 invocation 复用但随时可丢失。
* **Stateless 与 No State**：stateless 指实例不拥有持久业务状态，不代表系统没有外部状态。
* **Cold Start 与 Slow Handler**：cold start 发生在 handler 之前，handler latency 是业务执行时间；观测要分开。
* **Serverless 与 Long-Running Server**：serverless 生命周期受平台控制，长驻 server 更能掌握进程和连接生命周期。

本章结论
--------

Serverless 应按 ``Trigger → Environment Lifecycle → Initialization → Invocation → External State → Resource Limit`` 阅读。它的核心约束不是函数语法，而是实例不由应用拥有、资源预算有限、持久状态必须外置，因此接口形状和失败恢复都要围绕平台生命周期设计。