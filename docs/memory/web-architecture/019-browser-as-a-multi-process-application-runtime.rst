Browser as a Multi-Process Application Runtime
==============================================

核心知识点
----------

* 现代浏览器是多进程应用运行时，不是单体 HTML/JS 执行器；用户可见页面由 browser、renderer、network、GPU 等边界协作完成。
* Browser process 负责浏览器级控制面：窗口与 tab、地址栏、导航协调、权限提示、下载、进程分配和全局恢复。
* Renderer process 是 document 执行边界，承担 HTML/CSS/JavaScript、DOM、事件、layout 和部分 paint 工作，并处于受限沙箱中。
* Network process 集中处理连接、HTTP、缓存、cookie、证书、代理以及部分安全检查；页面脚本发起请求，但不直接拥有底层连接。
* GPU process 把图形硬件访问、纹理、合成和 WebGL/WebGPU 等高风险共享资源收束到独立边界。
* 多进程模型同时服务于安全、稳定性和资源隔离；代价是 IPC、进程调度、内存占用和跨进程状态同步成本。
* 页面问题应先定位边界：主线程长任务属于 renderer 路径，网络等待属于 network 路径，权限/导航异常属于 browser 控制面，黑屏或 context lost 还要检查 GPU 路径。

关键路径
--------

页面导航与显示的最小路径：

``User Intent → Browser Process → Network Process → Response → Browser Process → Renderer Commit → DOM/CSS/JS → GPU Process → Screen``

页面内请求与更新：

``User Event → Renderer → Fetch Intent → Network Process → Response → Renderer State/DOM → Paint/Composite → GPU → Screen``

跨站嵌入或高权限能力通常还会增加：

``Renderer → IPC → Browser Policy / Other Renderer / GPU / Network → Result → Renderer``

概念辨析
--------

* **Tab vs Process**：tab 是用户界面单元；一个 tab 可包含多个 renderer process，一个 renderer 也可能在策略允许时服务多个相关文档。
* **Browser Process vs Renderer Process**：前者拥有浏览器级控制与高权限协调；后者执行页面 document 和应用代码。
* **页面发起网络请求 vs 页面拥有网络栈**：JavaScript 只表达请求意图，连接、证书、缓存和协议处理在浏览器网络边界执行。
* **Renderer 卡顿 vs 浏览器卡死**：当前页面 renderer 卡顿时，地址栏、其他 tab 和浏览器 UI 仍可能正常响应。
* **GPU 加速 vs 页面主线程性能**：GPU 能加速合成和图形工作，但不能消除 JavaScript、style、layout 等 renderer 主线程瓶颈。

本章结论
--------

浏览器应被理解为一个带多进程隔离、权限控制、网络与图形专用边界的应用运行时。分析 Web 故障时先确定用户动作进入了哪个进程、状态由哪个边界拥有、结果需要跨过哪些 IPC，再检查代码和资源，能显著减少把所有问题都归结为“前端慢”或“浏览器慢”的误判。