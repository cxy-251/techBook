Resource Discovery, Preload, Prefetch, Priority, and Critical Path
==================================================================

核心知识点
----------

* 浏览器只有在“发现”资源后才能调度请求；资源发现时间往往和资源大小一样重要。
* 资源可由 HTML、CSS、ES module graph、JavaScript 动态加载、framework manifest、用户交互等不同阶段暴露，发现越晚，越容易形成 waterfall。
* 浏览器的 preload scanner/speculative scanner 可以提前从 HTML 字节中发现资源，但它不能执行 JavaScript、解析未来 CSS 依赖或理解完整应用状态。
* ``preload`` 面向当前 navigation 的已知关键资源；``prefetch`` 面向未来可能使用的资源；``preconnect`` 提前建立目标 origin 的连接准备；``dns-prefetch`` 只提前做名称解析。
* Resource hint 是提示，不是强制命令。浏览器仍会结合 destination、priority、缓存、安全策略和当前网络资源决定实际调度。
* ``as``、``crossorigin``、``type`` 等属性必须与资源后续真实请求匹配，否则 preload 可能无法复用甚至产生重复下载。
* 关键资源由用户可见路径决定，而不是由扩展名决定：首屏 CSS、LCP 图片、必要字体、启动脚本或首屏数据都可能进入 critical path。
* 错误的 preload/prefetch 会抢占带宽、连接和 CPU，把性能优化变成资源竞争。

关键路径
--------

资源发现：

``Navigation → HTML bytes → parser/preload scanner → CSS/JS/image discovery → deeper CSS/module/runtime discovery → browser scheduler → cache/network → parse/execute/render``

晚发现示例：

``HTML → CSS download → CSS parse → font URL discovered → font request → text stabilizes``

提前关键资源：

``server/build knows critical URL → HTML Link/preload/modulepreload → browser discovers early → cache/security check → scheduled fetch → later consumer reuses``

诊断路径：

``resource start time → initiator → discovery dependency → queue/priority → cache/connect/download → render/execute dependency``

概念辨析
--------

* **发现晚 vs 下载慢**：请求开始得晚通常是依赖/initiator 问题；请求开始早但完成慢才更像网络、服务器或体积问题。
* **Preload vs Prefetch**：preload 针对当前页面关键资源；prefetch 是低确定性的未来使用提示。
* **Preconnect vs DNS Prefetch**：preconnect 试图准备 DNS + transport + TLS；dns-prefetch 只做域名解析。
* **Preload scanner vs Application Knowledge**：浏览器只能从静态线索猜测；应用/服务器更清楚哪些资源对当前用户路径关键。
* **Priority hint vs 强制顺序**：优先级只是调度输入，真实顺序仍受浏览器、协议、缓存和连接资源影响。
* **Lazy loading vs 自动优化**：非关键资源延迟加载有价值；把首屏资源懒到 JavaScript 或 viewport 检测之后会增加关键路径。

本章结论
--------

Web 资源优化首先是发现与依赖图问题。先确定当前 navigation 的关键资源，再让浏览器尽早获得正确 URL、类型和跨源语义；preload、prefetch、preconnect 等只应服务明确路径，不能用“全部提前”替代关键路径分析。