Browser Process, Renderer Process, GPU Process, and Network Process
==================================================================

核心知识点
----------

* Browser process 是浏览器控制面，拥有地址栏、tab、导航提交、权限、下载、历史记录、进程选择和浏览器级安全 UI。
* Renderer process 是页面执行面，拥有当前 document 的 DOM、CSSOM、JavaScript heap、事件循环、样式计算、layout、paint 输入和页面级状态。
* Network process 是资源与连接面，统一处理 DNS、TCP/QUIC、TLS、HTTP、代理、cookie、HTTP cache、请求调度及部分跨源/安全策略。
* GPU process 是图形硬件与合成面，负责受控 GPU 访问、surface/texture、图层合成以及 Canvas、WebGL、WebGPU 等图形工作的一部分。
* 进程之间通过 IPC 协作；跨边界意味着状态不能靠普通内存引用共享，而要经过序列化、消息传递、句柄或受控共享资源。
* Browser process 可以在 renderer 崩溃后保留浏览器外壳并提供刷新/恢复；独立 GPU、network 边界也让专用故障不必直接摧毁整个浏览器。
* 浏览器具体进程拆分是实现细节，稳定架构结论应依赖职责边界，而不是假设“某 API 永远运行在某个固定 OS 进程”。

关键路径
--------

新页面导航：

``Address Bar / Link → Browser Process → Network Process → Redirect/Response → Browser Process → Renderer Selection → Document Commit``

页面内数据请求：

``DOM Event → Renderer JS → Fetch Request → Network Process → HTTP/Cache/Security → Response Stream → Renderer``

画面输出：

``DOM/CSS/JS State → Style/Layout/Paint in Renderer → Layer/Surface Submission → GPU Process → Compositor → Display``

概念辨析
--------

* **控制面 vs 执行面**：browser process 决定导航、权限和浏览器 UI；renderer 执行页面内容。
* **Network process vs Server**：network process 是用户设备上的浏览器网络边界；server 是远端请求处理和业务状态边界。
* **Paint vs Composite**：renderer 生成绘制与图层输入；最终图层组合和硬件显示更靠近 compositor/GPU 路径。
* **IPC 成本 vs 网络成本**：浏览器内部跨进程消息不经过互联网，但仍有调度、复制/共享、同步和序列化成本。
* **进程隔离 vs Origin 隔离**：OS 进程是实现级隔离工具；origin/same-origin policy 是 Web 平台安全语义，两者相关但不能等同。

本章结论
--------

Browser、renderer、network、GPU 四个边界分别拥有控制、页面执行、网络资源和图形硬件职责。一次 Web 行为常常穿过多个边界，排查时应按 ``用户动作 → 控制面 → 专用服务 → 页面执行 → 图形输出`` 复原路径，并用对应进程的证据定位第一处失配。