第174章：Browser DevTools, Network Panel, Performance Panel, and Memory Panel
=============================================================================

核心知识点
----------

* DevTools 的价值是把“架构假设”变成浏览器运行证据：请求怎样发生、脚本执行多久、样式/布局/绘制花多少时间、对象为什么没有释放、真实 DOM/CSS 是什么。
* Network panel 观察 URL、method、status、initiator、priority、protocol、headers、payload、cache、timing、size 和 waterfall，可定位资源发现、请求瀑布、重定向、CORS、缓存和协议问题。
* Waterfall 应先看“请求为什么晚发”，再看“请求本身为什么慢”。``document → main.js → route.js → API`` 这种串行结构常比单个接口耗时更值得修复。
* Response headers 是缓存和安全的重要证据。``Cache-Control``、``Age``、``Vary``、``Set-Cookie``、``ETag``、``Content-Encoding`` 会决定浏览器/CDN 实际行为。
* Performance panel 把 main thread、script、style recalculation、layout、paint、composite、input、frame、GC 和 network 放在同一时间轴上。
* Long task 表示主线程被连续工作占用，会推迟输入、paint 和 animation frame；诊断要继续拆成 JS、framework render、layout、paint 或 GC。
* Rendering cost 应按 ``script → style → layout → paint → composite`` 追踪，避免把所有卡顿都归结为“JavaScript 太多”。
* Memory panel 用 heap snapshot、allocation timeline、retainer path、detached DOM node 追踪对象为何仍被引用；它回答 retention，而 Performance 主要回答时间成本。
* Elements/Computed/Layout/Accessibility 面板显示浏览器最终采用的 DOM、cascade、box model 和 accessibility tree，能验证框架源码之外的实际结果。
* Coverage 用来识别当前场景下未使用的 JS/CSS；source map 把生产 artifact 的 stack/profile 映射回原始源码。
* DevTools 证据只代表当前浏览器、设备、网络和页面状态。机制诊断应结合 RUM/metrics 才能判断真实用户规模。
* 性能和故障分析应先固定场景：production build、缓存状态、浏览器版本、设备/节流、登录态和复现动作，否则不同 trace 很难比较。

关键路径
--------

浏览器故障分析：

::

   user-visible symptom
   → Network: request/resource/cache evidence
   → Performance: main-thread/render timing
   → Elements/Computed: DOM/CSS reality
   → Memory: retained objects/leaks
   → Sources/Coverage/maps: artifact-to-source
   → architecture judgment

请求瀑布：

::

   document
   → resource discovery/initiator
   → connection/cache/protocol
   → server wait/download
   → script execution triggers next request
   → final render

概念辨析
--------

* **Network Timing 与 Main-Thread Timing**：前者解释请求何时到达，后者解释浏览器收到内容后何时能执行和渲染。
* **Performance 与 Memory**：Performance 关注时间线和分配/GC 影响，Memory 关注对象为何长期保留。
* **DOM Source 与 DOM Reality**：框架源码只是输入，Elements 面板展示浏览器当前真实 DOM。
* **Coverage 与 Bundle Analyzer**：Coverage 表示当前运行场景实际用了多少，bundle analyzer 表示构建产物包含什么；二者视角不同。
* **DevTools Evidence 与 RUM Evidence**：DevTools 适合单次复现和机制验证，RUM 适合真实用户分布和规模判断。

本章结论
--------

浏览器调试应按 ``Request → Runtime → Render → Memory → Artifact`` 建立证据链。DevTools 不是最后才打开的排错工具，而是验证预加载、缓存、hydration、代码拆分、渲染成本和对象生命周期等架构假设的基础观察面。