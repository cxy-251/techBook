====================================================================
现代Web系统架构与全栈运行时全景深度剖析
====================================================================

.. toctree::
   :maxdepth: 2
   :caption: 全书 8 大核心系统模块体系目录:
   :numbered:

   ROADMAP
   01_web_system_worldview_and_boundaries/index
   02_standards_protocols_and_networking/index
   03_browser_internals_and_rendering_pipeline/index
   04_js_engine_and_wasm_runtime/index
   05_client_architecture_and_dom_abstraction/index
   06_server_runtimes_ssr_and_modern_stack/index
   07_edge_computing_distributed_delivery_and_observability/index
   08_industrial_case_studies_and_architecture_decisions/index

专著简介与架构全景
==================

本专著是一部以现代 Web 全栈技术体系为研究对象，自底向上穿透浏览器内核（Blink / WebKit）、V8 JavaScript 引擎、网络协议栈、现代底层标准（WebGPU / Streams / Workers）以及服务端全栈运行时（Node.js / Serverless / Edge）的工业级系统架构著作。

现代 Web 绝非孤立的“前端”或“后端”，而是由**浏览器多进程沙箱、网络协议流转、客户端/服务端运行时、CDN 边缘缓存与持久化数据边界**共同构成的分布式复杂异构系统。全书坚持“平台标准与浏览器真实内核机制优先”原则，系统化剖析从 URL 解析导航、HTML/DOM 增量解析、CSSOM 样式计算与 GPU 图层合成，到 V8 JIT 优化、事件循环微任务、同源安全策略、WebGPU 硬件渲染以及 SSR 流式水合（Hydration）的全景工程实现。

核心知识模块拓扑
----------------

.. list-table:: 现代 Web 系统架构与核心知识体系映射
   :widths: 10 25 35 30
   :header-rows: 1

   * - 模块编号
     - 核心系统模块
     - 核心底层机制与系统路径
     - 解决的核心工程问题
   * - 01
     - Web 系统世界观与边界演进
     - Browser/Server/Edge/DB 多执行区划分、请求导航状态流转、站点隔离与跨运行时协同
     - 建立现代 Web 跨运行时协同的全局系统架构心智
   * - 02
     - 标准契约、网络协议与资源交付
     - WHATWG/W3C/IETF 标准栈、HTTP/1.1~HTTP/3 多路复用、QUIC 连接与预加载关键路径
     - 解构网络传输与资源调度底座，降低首字节 (TTFB) 与资源等待时延
   * - 03
     - 浏览器内核与渲染管线微架构
     - HTML/CSS 分词解析、DOM/ComputedStyle 构建、Box 树排版、图层属性树与 GPU OOP-R 光栅化
     - 深入浏览器排版绘制流水线，消除主线程阻塞，实现 60/120fps 丝滑渲染
   * - 04
     - JavaScript 引擎与 WebAssembly 运行时
     - Scanner/Parser 词法语法分析、Ignition 字节码、Feedback Vector / Inline Cache、TurboFan JIT 与 Wasm 执行
     - 深入 JavaScript 宿主执行核心，优化长任务 (Long Tasks) 与执行开销
   * - 05
     - 客户端架构、DOM 抽象与前端运行时
     - DOM C++ 绑定、Virtual DOM 协调、细粒度响应式 Signals、客户端路由与状态存储
     - 掌握前端框架响应式与组件树调和机理，优化内存与交互响应 (INP)
   * - 06
     - 服务端、同构渲染与现代全栈范式
     - Node.js / Deno / Bun 架构、SSR/SSG/ISR 流式渲染、React Server Components (RSC) 与 Hydration
     - 构筑端到端全栈渲染架构，兼顾首屏呈现速度与动态交互能力
   * - 07
     - 边缘计算、分布式交付与可观测性
     - Edge V8 Isolates、边缘状态复制、Core Web Vitals (LCP/INP/CLS) 遥测与跨区域容灾
     - 突破跨洋物理延迟约束，实现全球高可用分布式边缘交付
   * - 08
     - 工业级架构案例演进与技术选型
     - 企业级微前端演进、高并发电商秒杀架构、协同画布 (Wasm/WebRTC) 与工程化工具链
     - 建立系统架构决策矩阵，沉淀严密工程权衡与演进能力

索引与搜索
==========

* :ref:`genindex`
* :ref:`search`
