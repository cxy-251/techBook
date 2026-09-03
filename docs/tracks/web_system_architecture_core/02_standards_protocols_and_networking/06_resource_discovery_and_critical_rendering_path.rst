========================================================================
Chapter 11: 资源发现与关键渲染路径：Preload Scanner、Resource Hints 与优先级调度
========================================================================

.. note:: 前置背景与认知承接
   前一章深入解构了 HTTP 缓存控制平面（强缓存、协商缓存 304 状态机、SWR 异步刷新机制与 Cookie 安全隔离）。在网络传输层面消除了冗余请求之后，Web 系统在页面初次加载（Cold Navigation）时面临的核心挑战，是如何以最短的物理时间建立关键渲染路径（Critical Rendering Path - CRP）。浏览器在解析 HTML 遇到同步脚本时会被强制阻塞主线程，为了打破串行瀑布流，浏览器内核研发了 Preload Scanner（预加载扫描器）异步分词抢跑机制。本章将系统剖析 Preload Scanner 词法快扫架构、Resource Hints（dns-prefetch、preconnect、preload、prefetch）的物理微架构、Fetch Priority 优先级调度器权重树，以及阻塞渲染资源（Render-Blocking Resources）的消除法则。

------------------------------------------------------------------------
11.1 关键渲染路径 (CRP) 物理瓶颈与阻塞级联
------------------------------------------------------------------------

**关键渲染路径（Critical Rendering Path - CRP）** 指的是浏览器自网络接收到首批 HTML 字节流开始，经过解析、样式计算、布局、图层绘制，直到在物理屏幕上渲染出首个有意义像素（FP / FCP / LCP）所必须经历的端到端依赖链路。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       关键渲染路径 (CRP) 严格依赖流水线                 |
   +-------------------------------------------------------------------------+

   [ 接收 HTML 字节流 (Network) ]
        |
        v
   [ 1. HTML 解析与 Tokenization ] --------------------------+
        |                                                    |
        | (遇到同步 <script> 强制挂起!)                       | (构建节点树)
        v                                                    v
   [ 2. CSSOM 构建 (解析所有阻塞 CSS) ]                  [ 3. DOM 树构建 ]
        |                                                    |
        +----------------------------+-----------------------+
                                     |
                                     v
                       [ 4. 渲染树构建 (Render Tree) ]
                                     |
                                     v
                         [ 5. 几何布局 (Layout / Reflow) ]
                                     |
                                     v
                         [ 6. 物理绘制与图层合成 (Paint & Composite) ]
                                     |
                                     v
                          [ 屏幕呈现像素 (Pixels on Screen) ]

级联阻塞的三大物理瓶颈
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **解析器阻塞 (Parser-Blocking - JavaScript)**：
   当 HTML 解析器遇到没有 `async` 或 `defer` 属性的传统 `<script src="app.js">` 标签时，DOM 树的构建过程必须**完全暂停（Block）**。这是因为 JavaScript 拥有直接调用 `document.write()` 修改当前 Token 流的合法权利，浏览器无法推测脚本执行后的 DOM 形态，必须等待该脚本完成物理网络下载并由 V8 引擎执行完毕。
2. **渲染阻塞 (Render-Blocking - CSS)**：
   CSS 被设计为**完全阻塞渲染（Render-Blocking）**。如果浏览器在 CSSOM 尚未构建完成时就绘制页面，用户将会看到没有任何排版与配色的裸露纯文本，并在样式加载完成瞬间发生剧烈的重新排版与颜色突变（无样式内容闪烁 - FOUC）。更致命的是，**CSS 还会间接阻塞 JavaScript 执行**：若 `<script>` 标签出现在 `<link rel="stylesheet">` 之后，由于脚本可能调用 `getComputedStyle()` 查询元素样式，浏览器必须强行挂起脚本执行，直至前面的 CSSOM 解析完成！
3. **字体阻塞 (Font-Blocking - Web Fonts)**：
   外链字体（WOFF2）在未完成下载前，浏览器文字渲染面临**文本不可见闪烁（FOIT - Flash of Invisible Text）**或**未格式化文本闪烁（FOUT - Flash of Unstyled Text）**的抉择。

------------------------------------------------------------------------
11.2 Preload Scanner (预加载扫描器) 词法快扫微架构
------------------------------------------------------------------------

若完全遵循上述串行解析模型，当主线程在 HTML 第 10 行因为一个体积为 500KB 的同步脚本阻塞 300ms 时，页面后续第 50 行的关键 CSS、第 80 行的 Hero 关键大图将一直处于未被发现状态，导致网络带宽在此期间完全空闲闲置。

为了打破这种串行等待僵局，现代浏览器内核（Chromium Blink、WebKit、Gecko）在主解析器之外引入了独立的辅助流水线——**预加载扫描器（Preload Scanner）**。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |             主线程 HTML 解析器 vs Preload Scanner 并发架构              |
   +-------------------------------------------------------------------------+

   [ 网络进程下发 HTML 数据块 (Chunks) ]
        |
        +---> [ 主线程: HTMLDocumentParser ]
        |        |
        |        v (遇到同步 <script src="bundle.js">)
        |     [ 主线程完全挂起阻塞! 等待 bundle.js 下载并执行完毕... ]
        |
        +---> [ 辅助流水线: HTMLPreloadScanner (轻量级预加载扫描器) ]
                 |
                 v (完全不阻塞！以极速对剩余 HTML 原始字符进行词法 Token 扫描)
              [ 发现 <link rel="stylesheet" href="style.css"> ] -> 立即发射网络请求!
              [ 发现 <img src="hero.webp"> ]                   -> 立即发射网络请求!
              [ 发现 <script src="analytics.js"> ]             -> 立即发射网络请求!
                 |
                 v
   [ 物理效果: 所有静态关键资源与阻塞脚本在网络管道中【完全并发重叠传输】! ]

Preload Scanner 的物理特征与盲区
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **纯词法扫描，不构建 DOM**：Preload Scanner 仅进行极其简化的正则表达式或轻量词法匹配，内存开销几乎为零，吞吐量高达每秒数百兆；
- **盲区 1：CSS 内联 `@import`**：Preload Scanner 无法穿透 CSS 文件内部。`@import` 必须等待父 CSS 下载并由 CSS 解析器执行后才能暴露，带来灾难性的二次网络瀑布流；
- **盲区 2：CSS 背景图与动态注入**：通过 `background-image: url(...)` 引用的图片必须等到渲染树构建、确定元素匹配该规则时才会被发起请求；通过 JavaScript 动态 `document.createElement('script')` 插入的标签对 Preload Scanner 完全不可见。

------------------------------------------------------------------------
11.3 Resource Hints 微架构体系：preconnect、dns-prefetch、preload 与 prefetch
------------------------------------------------------------------------

为了消除 Preload Scanner 的盲区，W3C 与 WHATWG 制定了 **Resource Hints** 规范，允许架构师向浏览器内核注入显式的资源提取指令。

.. list-table:: 现代 Web 四大 Resource Hints 核心行为与微架构对比
   :widths: 18 25 27 30
   :header-rows: 1
   :class: tight-table

   * - 指令声明
     - 触发时机与执行阶段
     - 网络与内存开销
     - 适用工业场景与风险
   * - `<link rel="dns-prefetch">`
     - 立即触发目标跨域域名的 DNS 递归解析
     - 极低（仅产生数十字节的 UDP 报文）
     - 跨域第三方 CDN、统计埋点域名；**零副作用**
   * - `<link rel="preconnect">`
     - 完成 DNS + TCP 三次握手 + TLS 1.3 协商
     - 中（维持 TCP/TLS Socket 链接，占用端口）
     - **关键字体 CDN、关键 API 源站**；若 10s 内未用会被内核自动关闭
   * - `<link rel="preload">`
     - **强制以高优先级立即下载当前页关键资产**
     - 高（占用当前页面宝贵的网络首屏带宽）
     - **当前页 LCP 大图、首屏关键 WOFF2 字体、深度 CSS**；滥用会导致网络拥塞
   * - `<link rel="prefetch">`
     - 浏览器完全空闲时（Idle Time）低优先级下载
     - 低（仅在网络与 CPU 空闲时悄悄执行）
     - **下一跳高概率访问页面、后续交互弹窗的 JS Bundle**

`preload` 的严格契约与关键字体预加载范式
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

使用 `rel="preload"` 时必须严格指定 `as` 属性与跨域标记，否则会导致**同一个文件被重复下载两次**的严重事故：

.. code-block:: html

   <!-- 关键字体预加载标准范式: 必须声明 as="font" 与 crossorigin="anonymous" -->
   <link rel="preload" href="/fonts/inter-bold.woff2" as="font" type="font/woff2" crossorigin="anonymous">

   <!-- 首屏 LCP 关键大图预加载 (结合响应式媒体查询) -->
   <link rel="preload" fetchpriority="high" as="image" href="/img/hero-1080w.webp" imagesrcset="/img/hero-480w.webp 480w, /img/hero-1080w.webp 1080w" imagesizes="100vw">

------------------------------------------------------------------------
11.4 Fetch Priority 优先级调度器与网络请求权重树
------------------------------------------------------------------------

浏览器网络进程内部维护着一个复杂的**多队列资源优先级调度器（Resource Priority Scheduler）**。所有进出网络栈的请求都会被赋予 5 级优先级：`VeryHigh`、`High`、`Medium`、`Low`、`VeryLow`。

.. list-table:: 现代 Chromium 内核资源默认优先级映射矩阵
   :widths: 25 25 50
   :header-rows: 1
   :class: tight-table

   * - 资源类型与位置
     - 默认调度优先级
     - 优先级评定底层依据
   * - **HTML 根主文档**
     - `VeryHigh`
     - 一切后续资源的解析依赖根源
   * - **`<head>` 内的同步 CSS**
     - `VeryHigh`
     - 渲染树构建的绝对阻塞项
   * - **Web 字体 (WOFF2)**
     - `High`
     - 文字排版与布局计算前置依赖
   * - **`<head>` 内的同步 `<script>`**
     - `High`
     - DOM 树构建的阻塞项
   * - **视口内图片 (in-viewport)**
     - `Medium` / `High`
     - 视觉首屏呈现
   * - **带有 `defer` / `async` 的脚本**
     - `Low`
     - 不阻塞主解析器，执行时机已延后
   * - **视口外懒加载图片 / `prefetch`**
     - `Lowest` / `Idle`
     - 非当前首屏必需，绝不抢占带宽

`fetchpriority` 显式属性干预
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

浏览器无法提前知道哪张 `<img>` 是触发 LCP（Largest Contentful Paint）的核心大图。通过在 HTML 中标记 `fetchpriority="high"`，可以将普通图片的优先级由 `Low/Medium` 瞬间拔高至 `High`，使其在 HTTP/2 多路复用流分配中抢先占满初始拥塞窗口（`initcwnd`）：

.. code-block:: html

   <img src="product-hero.jpg" fetchpriority="high" alt="Featured Product">

------------------------------------------------------------------------
11.5 关键渲染路径优化工程法则与反模式归纳
------------------------------------------------------------------------

`async` 与 `defer` 脚本加载属性的物理执行时序对比
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                async vs defer vs 普通 Script 执行时序对比               |
   +-------------------------------------------------------------------------+

   [ 普通 <script src="..."> ]:
   HTML 解析: ====[ 遇到 Script 暂停! ]===================>[ 恢复解析 ]====>
   网络下载:       [ ===== 下载 ===== ]
   脚本执行:                           [ === 执行 === ]

   [ <script async src="..."> ]:
   HTML 解析: =======[ 下载期间继续解析 ]==[ 立即暂停! ]====>[ 恢复解析 ]====>
   网络下载:       [ ===== 异步下载 ===== ]
   脚本执行:                               [ === 立即执行 === ]
   * 缺陷: 下载完成瞬间立刻插队打断 HTML 解析！执行顺序完全无序，极易引发依赖丢失！

   [ <script defer src="..."> - 现代工程金标准 ]:
   HTML 解析: =========================================[ 完全不被打断! ]===>
   网络下载:       [ ===== 异步下载 ===== ]
   脚本执行:                                          [ DOM 树构建完按序执行 ]

.. list-table:: 关键渲染路径 (CRP) 优化准则与反模式清单
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 优化维度
     - 推荐工业范式 (Best Practice)
     - 严禁触碰的反模式 (Anti-Pattern)
   * - **CSS 交付**
     - 首屏 Critical CSS（< 14KB）内联至 `<head>`；异步加载其余 CSS
     - 在 CSS 内部使用 `@import`；将非关键大体积 CSS 放在 `<head>` 同步阻塞
   * - **JS 脚本**
     - 业务代码一律使用 `<script defer>` 或 ESM `type="module"`
     - 在 `<head>` 放置大体积无属性同步脚本；滥用 `document.write`
   * - **字体加载**
     - `preload` 关键 WOFF2 + `font-display: swap`
     - 未预加载且使用默认 `font-display: auto`（导致 3 秒文字完全白屏 FOIT）
   * - **LCP 图片**
     - 首图预加载 `preload` + `fetchpriority="high"`，移除懒加载
     - 对首屏第一屏大图添加 `loading="lazy"`（导致首图被迫延迟至布局后触发）

------------------------------------------------------------------------
小结与下卷导读
------------------------------------------------------------------------

本章系统解构了关键渲染路径（CRP）的三大级联阻塞瓶颈、Preload Scanner 预加载扫描器词法快扫与推测性网络抢跑微架构、Resource Hints（`dns-prefetch`、`preconnect`、`preload`、`prefetch`）执行契约、Chromium 网络请求优先级调度树，以及 `async`/`defer` 脚本执行时序的本质差异。

至此，《现代Web系统架构与全栈运行时全景深度剖析》**第二模块：标准契约、网络协议与资源交付 (02_standards_protocols_and_networking) 圆满全量收官（6/6 节，全书累计完成 11/48 节）！**

在完成了 Web 宏观边界模型与物理网络/协议/资源交付栈的严密探索之后，全书将正式深入浏览器内部最精密复杂的核心引擎——**第 3 模块：浏览器内核与渲染管线微架构 (03_browser_internals_and_rendering_pipeline)**。下一章我们将开启第三模块第一章——**HTML 分词算法、容错机制与 DOM 树构建：从字节流到有向对象图**，解构 Blink / WebKit 内核如何通过字符流解码、确定性状态机分词、栈驱动构建与特有的 HTML5 容错机制，将无序的字符流转换为结构严密的 DOM 内存对象树。
