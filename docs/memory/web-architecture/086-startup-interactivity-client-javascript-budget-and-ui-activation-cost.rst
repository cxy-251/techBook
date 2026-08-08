第086章：Startup Interactivity, Client JavaScript Budget, and UI Activation Cost
================================================================================

核心知识点
----------

* Startup interactivity 关注页面从“已经显示”到“可以稳定响应用户操作”之间剩余的客户端工作。
* 可见性与可交互性必须分开：HTML/CSS 可以先显示，相关 JavaScript、状态和事件处理器可能尚未就绪。
* Client JavaScript budget 不只是传输体积，还包括 parse、compile、evaluation、hydration、memory、GC、long task 与第三方脚本竞争。
* UI activation 需要四类 readiness：代码就绪、状态就绪、事件就绪、失败恢复就绪。
* SSR/SSG 可以改善 HTML 抵达和首屏绘制，却不能自动消除 hydration、runtime 接管和客户端状态恢复成本。
* Code splitting 只有与首交互优先级匹配时才有效；错误切分会把等待从首屏转移到首次点击之后。
* 第三方脚本必须进入独立预算，因为它们和应用代码竞争网络、主线程和事件循环。

关键路径
--------

启动激活路径：

``Navigation → HTML/CSS Visible → Client Bundle Download → Parse/Compile/Evaluate → Hydration/State Restore → Event Handler Ready → First Interaction → Next Paint``

对每个首屏交互对象建立 activation map：

#. 视觉结构从哪里来；
#. 首次操作需要哪个 bundle；
#. 依赖哪些 URL、cookie、storage、server snapshot 或 cache state；
#. 事件由原生平台还是客户端 runtime 处理；
#. runtime 未就绪或请求失败时有哪些 fallback。

页面可按三层激活：

``立即交互区 → 启动预算``

``可见但可延迟激活区 → 用户意图/可见性触发``

``首屏之外区域 → route/idle/lazy load``

性能验证应同时查看 transfer size、script evaluation、long task、hydration trace、coverage、INP 和真实设备首交互时间线。

概念辨析
--------

* **Visible ≠ interactive**：用户能看到按钮，不代表 handler 和依赖状态已经可执行。
* **SSR/SSG ≠ zero client cost**：服务端 HTML 只解决启动路径前半段。
* **Small bundle ≠ small CPU cost**：压缩后的字节仍需解析、编译、执行并占用内存。
* **Code splitting ≠ always faster**：切分边界若落在首交互必经路径上，会制造点击后等待。
* **Hydration ≠ browser parsing**：浏览器先创建 DOM；hydration 是客户端 runtime 把已有 DOM 接入组件状态和事件系统。
* **Third-party ≠ free background work**：分析、客服、实验、监控等脚本同样消耗用户主线程预算。

本章结论
--------

启动性能应以“首次可能交互何时真正可用”为目标，而不是只看 HTML 出现或 bundle 体积。先列首屏交互，再反推代码、状态、事件和恢复依赖，把真正必需的客户端工作压进启动预算，其余工作延后。