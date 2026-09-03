========================================================================
Chapter 11: 资源发现与关键路径：Preload Scanner、Resource Hints 与调度
========================================================================

.. note:: 前置背景与认知承接
   前一章深入解构了 HTTP 强缓存指令集状态机、条件请求弱缓存协商、基于哈希指纹的不可变静态资源版本化、Cookie 状态机安全隔离与 Vary 多维缓存键解耦。当浏览器通过网络或缓存获取到入口 HTML 文档后，渲染引擎面临的核心矛盾是：HTML 主解析器（HTML Parser）在遭遇同步 JavaScript 脚本或阻塞样式表时必须挂起等待执行，若等到解析恢复时才去发现后续的外部 CSS、JS 和图片资源，整个流水线将陷入灾难性的网络空转（Network Waterfall Bubble）。本章将系统剖析现代浏览器内核中 Preload Scanner（预加载扫描器 / Lookahead Parser）投机扫描微架构、资源加载优先级计算决策树（Resource Priority Matrix）、Resource Hints 提示体系（`dns-prefetch` / `preconnect` / `preload` / `prefetch` / `modulepreload`），以及关键渲染路径（Critical Rendering Path - CRP）的阻塞链路消除与流水线并行化机理。

------------------------------------------------------------------------
11.1 关键渲染路径 (Critical Rendering Path - CRP) 阻塞链路物理本质
------------------------------------------------------------------------

**关键渲染路径（Critical Rendering Path - CRP）** 是指浏览器从接收 HTML 文档的首个网络字节开始，到最终在物理屏幕上完成页面首帧像素绘制（First Contentful Paint - FCP）所必须经历的串行资源处理链条。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                  关键渲染路径 (CRP) 核心执行流水线                      |
   +-------------------------------------------------------------------------+

   [ 接收 HTML 网络字节流 ]
        |
        v (1. 词法解析与 Tokenization)
   [ 构建 DOM 树 (DOM Construction) ] <----+ (被同步 JS 脚本强制中断挂起!)
        |                                  |
        | [ 发现 <link rel="stylesheet"> ] | [ 发现 <script src="..."> ]
        v                                  v
   [ 构建 CSSOM 树 (CSSOM Tree) ] -----> [ 阻塞等待 CSSOM 完成后执行 JS 引擎 ]
        |                                  |
        +-----------------+----------------+
                          |
                          v (2. 遍历合并 DOM 与 CSSOM)
                   [ 生成渲染树 (Render Tree) ]
                          |
                          v (3. 盒模型几何排版计算)
                   [ 布局计算 (Layout / Reflow) ]
                          |
                          v (4. 绘制指令录制与分块光栅化)
                   [ 绘制与合成 (Paint & Compositing) ]
                          |
                          v
                   [ 物理屏幕像素呈现 (Pixels on Screen / FCP) ]

CRP 三大物理约束度量
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **关键资源数量 (Critical Resources)**：任何可能直接阻塞 DOM 解析或 CSSOM 渲染树构建的资源（入口 HTML、同步外部 CSS、同步外部 JS）；
2. **关键路径长度 (Critical Path Length)**：获取所有关键资源所需经历的**传输层往返时延（RTT）总轮次**；
3. **关键字节数 (Critical Bytes)**：所有关键资源压缩后的物理网络传输体积之和。

阻塞机理的深度物理模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **CSS 渲染阻塞 (Render-Blocking CSS)**：
  默认情况下，外部 CSS 不阻塞 HTML DOM 树的继续构建，但**绝对阻止渲染树（RenderTree）的生成与屏幕绘制**。其物理动机是防止页面在样式未加载前将裸露的 HTML 结构直接绘制到屏幕上，产生严重的**无样式内容闪烁（FOUC - Flash of Unstyled Content）**。
- **JS 解析阻塞 (Parser-Blocking JS)**：
  因为 JavaScript 脚本具备通过 `document.write()` 动态修改后续未解析 HTML 标记的合法权力，HTML 解析器在遇到没有 `async` 或 `defer` 属性的普通 `<script>` 标签时，**必须强制暂停 HTML 解析**，直到该脚本网络下载完成并由 V8 引擎执行完毕！
- **CSS 阻断 JS 执行 (CSS Blocking Script Execution)**：
  若同步 `<script>` 标签之前存在尚未下载完成的 `<link rel="stylesheet">`，由于 JS 脚本随时可能调用 `getComputedStyle()` 读取 DOM 节点的实时几何尺寸与颜色，浏览器内核为了保证计算的一致性，**必须暂停 JS 脚本的执行，直到前方所有的 CSSOM 构建完毕**！
  
这构成了 Web 性能中最臭名昭著的死锁链：**CSS 阻塞 JS 执行，JS 阻塞 HTML 解析，HTML 暂停导致后续关键网络资源无法被发现！**

------------------------------------------------------------------------
11.2 Preload Scanner (预加载扫描器) 投机扫描微架构
------------------------------------------------------------------------

为了打破上述串行阻塞死锁，现代浏览器内核（Blink / WebKit）引入了**预加载扫描器（Preload Scanner / Lookahead Parser）**。

Preload Scanner 的工作机理
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当主线程上的 HTMLTokenParser 遭遇同步脚本阻塞而挂起时，浏览器在后台轻量级线程中并行启动 Preload Scanner：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |            主解析器阻塞挂起 vs Preload Scanner 投机并发扫描             |
   +-------------------------------------------------------------------------+

   HTML 文档流:
   <link rel="stylesheet" href="a.css"> -> 正在慢速网络下载 (耗时 500ms)...
   <script src="heavy.js"></script>    -> [ 主解析器暂停在这一行! DOM 停止构建! ]
   <link rel="stylesheet" href="b.css">
   <script src="feature.js"></script>
   <img src="hero.jpg">

   [ 传统无 Scanner 场景 (串行灾难) ]:
   下载 a.css (500ms) -> 下载并执行 heavy.js (800ms) -> 此时才开始发现 b.css!

   [ 现代 Preload Scanner 场景 (投机并发拉取) ]:
   当主解析器停在 heavy.js 时，Scanner 瞬间以高速向前探测整个 HTML 字符流：
   -> 提前捕获 b.css / feature.js / hero.jpg
   -> 直接向网络进程发射高优先级并发下载请求！
   -> 当 heavy.js 执行完毕、主解析器恢复运行时，b.css 与 hero.jpg 早已在内存就绪！

Preload Scanner 的物理盲区与局限
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Preload Scanner 仅进行纯文本轻量级标记扫描，存在以下三大不可逾越的感知盲区：

.. list-table:: Preload Scanner 感知盲区与失效场景
   :widths: 25 35 40
   :header-rows: 1
   :class: tight-table

   * - 失效场景
     - 代码形态特征
     - 无法预加载的物理根因
   * - **1. CSS 内部依赖**
     - `@import url("sub.css");`
`background: url("bg.jpg");`
`@font-face { src: url(...) }`
     - Scanner 仅扫描 HTML 标签，**完全不解析 CSS 语法**；必须等到 CSS 下载并构建 CSSOM 后才能发现字体与背景图
   * - **2. 动态注入脚本**
     - `const s = document.createElement('script');`
`s.src = 'dynamic.js'; document.head.appendChild(s);`
     - 资源完全依赖 JS 运行时计算生成，静态扫描器无法预测其 URL
   * - **3. 响应式图片多源**
     - `<picture><source media="(min-width: 1000px)" srcset="...">`
     - Scanner 在未完成完整 DOM 布局时，对复杂的媒体查询条件判断可能发生歧义，导致投机预测失准

------------------------------------------------------------------------
11.3 Resource Hints 提示体系：preconnect、preload、prefetch 与 modulepreload
------------------------------------------------------------------------

为了显式弥补 Preload Scanner 的盲区，W3C 制定了 **Resource Hints** 与 **Preload 标准**，赋能开发者对网络调度进行精确控制：

.. list-table:: 现代 Web 资源提示（Resource Hints）微架构对比矩阵
   :widths: 20 20 30 30
   :header-rows: 1
   :class: tight-table

   * - 声明指令
     - 语法形态
     - 执行时机与网络行为
     - 最佳实践与踩坑警告
   * - **`dns-prefetch`**
     - `<link rel="dns-prefetch" href="https://cdn.example.com">`
     - 仅提前执行目标 Host 的 **DNS 递归解析**，不建立 TCP 连接
     - 适用于第三方外链域名或用户可能点击的跳转站点（开销极低）
   * - **`preconnect`**
     - `<link rel="preconnect" href="https://api.example.com" crossorigin>`
     - 提前完成 **DNS + TCP + TLS 1.3 握手**，维持热连接管道
     - **仅限当前页面 100% 确定请求的关键第三方 Origin**（保持连接占用套接字资源，建议不超过 3~4 个）
   * - **`preload`**
     - `<link rel="preload" href="/fonts/c.woff2" as="font" type="font/woff2" crossorigin>`
     - **以高优先级强制提前下载当前页面关键资源**，绕过 Scanner 盲区
     - **必须显式声明 `as` 属性与 `crossorigin`**（字体资源规范强制匿名 CORS），否则会导致同资源双重重复请求下载！
   * - **`modulepreload`**
     - `<link rel="modulepreload" href="/esm/app.js">`
     - 针对 ES Module 设计；**提前下载并在后台执行 V8 词法编译与子模块依赖树解析**
     - 彻底消除传统 ESM 深度嵌套 `import` 引发的瀑布流依赖加载延迟
   * - **`prefetch`**
     - `<link rel="prefetch" href="/next-page/bundle.js" as="script">`
     - **以极低优先级在浏览器空闲时预获取未来导航所需的资源**
     - 下载的数据直接存入 HTTP 磁盘缓存，**严禁用于当前页面关键路径**，避免争抢首屏关键带宽

------------------------------------------------------------------------
11.4 浏览器资源加载优先级计算矩阵与调度树
------------------------------------------------------------------------

Chromium / Blink 内核在内部维护了一套严格的 **资源优先级状态机（Resource Priority Matrix）**，直接映射至 HTTP/2 与 HTTP/3 的传输调度流权重：

.. list-table:: Chromium 内核资源优先级判定矩阵
   :widths: 18 22 25 35
   :header-rows: 1
   :class: tight-table

   * - 资源类型与加载上下文
     - Blink 内部优先级
     - HTTP/2 / H3 调度权重
     - 物理调度行为与带宽供给
   * - HTML 入口文档
     - **VeryHigh (最高)**
     - 权重 256
     - 绝对优先通道，保证初始 Token 立即流式交付
   * - `<head>` 中的外部 CSS
     - **VeryHigh (最高)**
     - 权重 256
     - 阻塞渲染树，必须以全速抢占网络带宽
   * - `<head>` 中的同步 JS
     - **High (高)**
     - 权重 220
     - 阻塞 DOM 构建，优先分配带宽
   * - `<link rel="preload">`
     - **根据 `as` 类型继承**
     - 对应类型的最高档
     - `as="style"` 为 VeryHigh；`as="script"` 为 High；`as="font"` 为 High
   * - 视口内部可见图片 (LCP)
     - **Medium / High**
     - 权重 100~150
     - 初始为 Medium，一旦布局确定其位于首屏视口内，动态提升为 High
   * - `<script defer / async>`
     - **Low (低)**
     - 权重 50
     - 允许后台加载，不阻塞 DOM 树构建
   * - `<link rel="prefetch">`
     - **VeryLow (最低)**
     - 权重 16 (最低档)
     - 仅在所有关键资源网络流全部静默时，利用带宽空闲气泡传输

动态优先级提升 (Priority Escalation)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当主线程在执行过程中，若一个原先被判定为低优先级的资源突然转变为关键依赖（例如：用户快速滑屏将一张视口外的图片滚动至屏幕正中央，或者主线程执行到某个 `import()` 语句需要立即等待模块），Blink 的 `ResourceFetcher` 会通过 IPC 向网络进程发送 `UpdatePriority` 命令，**实时修改 HTTP/2 Stream 的权重并重新平衡 TCP 发送窗口**！

------------------------------------------------------------------------
11.5 关键渲染路径重构与网络时延优化黄金法则
------------------------------------------------------------------------

结合现代浏览器网络与渲染引擎微架构，现代全栈系统优化关键渲染路径（CRP）的核心工程范式：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                  现代关键渲染路径 (CRP) 极限优化架构模型                |
   +-------------------------------------------------------------------------+

   [ 1. 域名与连接提前热身 ]
   <link rel="preconnect" href="https://api.example.com" crossorigin>

   [ 2. 绕过字体与核心 LCP 图片的 Scanner 盲区 ]
   <link rel="preload" href="/fonts/inter.woff2" as="font" type="font/woff2" crossorigin>
   <link rel="preload" href="/images/banner.webp" as="image" fetchpriority="high">

   [ 3. 首屏关键 CSS 内联 (Critical CSS Inlining) ]
   <style>
     /* 首屏折叠线上方 (Above-the-Fold) 必须样式的原子级内联: 消除 1-RTT 外部 CSS 阻塞! */
     body { margin: 0; font-family: Inter, sans-serif; }
     .hero { display: flex; height: 100vh; }
   </style>

   [ 4. 非关键大体积 CSS 异步解耦 ]
   <link rel="preload" href="/assets/main.css" as="style" onload="this.rel='stylesheet'">

   [ 5. 全量 JavaScript 脚本异步化 ]
   <script type="module" src="/assets/app.js"></script>
   <!-- 或传统脚本: <script src="/assets/app.js" defer></script> -->

- **`fetchpriority` 属性的细粒度控制**：现代标准允许在 HTML 标签上显式指定 `fetchpriority="high"`（如标注在首屏 Hero LCP 图片上）或 `fetchpriority="low"`（标注在轮播图后续图片上），直接重写浏览器的默认优先级决策树。

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章从浏览器内核微架构出发，系统推导了关键渲染路径（CRP）的三大物理要素与 CSS/JS 相互死锁机理、Preload Scanner 投机扫描与感知盲区、Resource Hints 提示体系（`preload` / `preconnect` / `modulepreload`）、Chromium 资源优先级计算矩阵，以及基于 Critical CSS 内联与脚本异步化的现代 CRP 重构范式。

至此，《现代Web系统架构与全栈运行时全景深度剖析》第二卷（标准契约、网络协议与资源交付）圆满收官（6/6 节全量完工）！在彻底掌握了网络传输协议与资源预调度体系后，我们将正式跨入浏览器的核心执行层——**Part 3: HTML/DOM 结构化构建与资源调度**。在下一章中，我们将深入**HTML5 解析算法与容错状态机：标记化 (Tokenization)、树构建 (Tree Construction) 与脚本中断**，解构字符流解码、自动补全标签与不可信 HTML 安全规整的底层微架构。
