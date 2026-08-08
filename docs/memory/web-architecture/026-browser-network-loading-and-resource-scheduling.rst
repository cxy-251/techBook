Browser Network Loading and Resource Scheduling
===============================================

核心知识点
----------

* 浏览器在 HTML 尚未完整到达时就开始发现和调度资源；parser、preload scanner、CSS、module graph、JavaScript、worker 都可能成为请求发起者。
* 资源请求携带 URL、destination、mode、credentials、cache mode、priority、initiator 和所属 document/worker，网络层据此决定缓存、安全与调度路径。
* ``preload`` 解决“发现太晚”，``fetchpriority`` 解决“已发现资源的竞争优先级”；二者不能互相替代。
* stylesheet、classic script、module、font、image、data fetch、worker script 的阻塞语义和失败传播不同，不能只按文件大小判断关键性。
* HTTP cache、Service Worker、CDN 与网络连接共同决定实际字节来源；页面看到的“请求”不一定真正到达源站。
* 调度器要在关键资源、连接复用、协议 stream、优先级提示和非关键请求之间做资源竞争。

关键路径
--------

页面加载主路径：

``Navigation → HTML bytes → parser/preload scanner → CSS/JS/Image/Font discovery → HTTP cache/Service Worker → Network/CDN/Origin → Response → parser/runtime/decoder``

晚发现资源：

``HTML → CSS → font/background URL``

或：

``HTML → JS entry → module graph/dynamic import → chunk``

优化顺序：

``发现时间 → 阻塞语义 → 缓存复用 → 优先级 → 连接/协议 → 失败传播``

概念辨析
--------

* **资源发现 vs 下载优先级**：发现决定请求何时进入队列；优先级决定进入队列后与其它请求怎样竞争。
* **Preload vs Prefetch**：preload 面向当前导航中确定要用的资源；prefetch 面向未来可能使用的资源。
* **Parser Request vs Fetch Request**：都进入浏览器网络系统，但拥有者、阻塞关系与错误恢复不同。
* **HTTP Cache vs Service Worker Cache**：前者按 HTTP 语义自动复用；后者由应用脚本显式拦截与管理。
* **资源关键性 vs 文件类型**：CSS、JS、图片是否关键取决于它是否位于当前用户可见关键路径。

本章结论
--------

浏览器资源加载是一条跨 parser、runtime、cache、network 与 rendering 的调度路径。性能判断应先找资源何时被发现，再看它是否阻塞当前页面、能否复用缓存、是否得到合理优先级，最后检查网络和失败传播；只压缩文件或盲目 preload 无法替代这套路径分析。