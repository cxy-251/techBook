================================================================================
Part 5: 客户端架构、DOM 抽象与前端运行时
================================================================================

.. toctree::
   :maxdepth: 2
   :caption: 本模块章节目录:
   :numbered:

   01_dom_api_c_plus_plus_bindings_and_event_bubbling
   02_virtual_dom_reconciliation_and_fiber_architecture
   03_fine_grained_reactivity_signals_and_compiler_driven_ui
   04_client_routing_history_api_and_micro_frontends
   05_state_management_redux_mobx_zustand_signals
   06_client_storage_indexeddb_localstorage_cache_storage

模块架构全景
============

在现代 Web 体系中，客户端运行时并非直接操作底层硬件，而是建立在浏览器内核暴露的平台对象与抽象接口之上。本模块聚焦于现代 Web 前端核心运行时与架构抽象层，深入解构从 C++ 原生 DOM 树到 JavaScript 语言边界的穿透代价，剖析声明式 UI 框架的调和（Reconciliation）算法与细粒度响应式编译机理，解密现代客户端状态管理、无刷新路由与浏览器持久化存储的系统级工程实现。

核心知识体系映射
----------------

.. list-table:: 客户端架构、DOM 抽象与前端运行时知识拓扑
   :widths: 10 25 35 30
   :header-rows: 1

   * - 章节
     - 核心主题
     - 深入底层机制
     - 解决的核心工程问题
   * - 25
     - DOM API 与 C++ 绑定
     - V8 Wrapper、Oilpan GC 协同、穿透开销、事件捕获/冒泡微架构
     - 揭示跨语言调用代价，避免强制同步重排与内存泄漏
   * - 26
     - Virtual DOM 与 Fiber 协调
     - 双缓存 Fiber 树、增量分片调度、Lanes 优先级模型与调和算法
     - 掌控高频交互下的渲染平滑度，避免长任务阻塞主线程
   * - 27
     - 细粒度响应式与编译驱动 UI
     - 依赖图拓扑排序、Signals 动态图剪枝、Svelte/Solid 编译期代码生成
     - 消除运行时 VDOM 树 Diff 开销，实现原子级直接 DOM 更新
   * - 28
     - 客户端路由与微前端
     - History API 状态机、PopState 拦截、沙箱隔离 (Proxy/Shadow DOM)
     - 掌控大型企业级单页应用与多团队微前端架构隔离治理
   * - 29
     - 客户端状态管理范式
     - 不可变单向数据流、观察者响应式、原子化派生状态与性能权衡
     - 规避全局无序重渲染，保证高并发状态变更下的数据确定性
   * - 30
     - 客户端存储微架构
     - IndexedDB B-Tree 事务模型、LocalStorage 同步 I/O 阻塞与 Cache Storage
     - 构建高性能离线优先应用与海量结构化数据持久化策略
