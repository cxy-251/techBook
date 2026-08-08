DevTools as the Browser Observability Surface
============================================

核心知识点
----------

* DevTools 把框架抽象还原成浏览器事实：request、response、cache、script execution、DOM、computed style、layout/paint、heap 与代码覆盖率。
* Network 面板回答“浏览器有没有以预期语义跨过网络边界”：URL、method、status、headers、cookie、payload、initiator、priority、protocol、cache status 和 timing 都属于证据。
* Performance 面板回答“响应到达后浏览器如何使用 CPU 与渲染管线”：main-thread task、long task、style、layout、paint、composite、frame 与 input delay 可以放到同一时间线。
* Elements/Computed Styles 展示当前真实 DOM 与 cascade 结果，适合区分“源码意图”“运行时 DOM”“CSSOM/matched rules”“最终 computed style”。
* Memory 用 heap snapshot、allocation 等证据定位长期运行页面的对象滞留和泄漏；Coverage 用于识别加载/执行了多少未使用 CSS/JS，但不能单独决定删除代码。
* DevTools 只能证明浏览器边界内发生了什么；数据库、origin compute、CDN 回源等根因仍需 server logs、trace、CDN logs 和 RUM 补齐。

关键路径
--------

浏览器排查顺序：

``User-visible symptom → Network → Performance → Elements/Computed → Memory/Coverage → engineering conclusion``

首屏空白：

``Document request → HTML/JS/CSS/chunk status → main-thread startup → DOM/hydration → paint``

旧数据：

``data request exists? → response/cache source → response body correct? → client state/cache → DOM output``

卡顿：

``User input → event handler → long task/style/layout/paint/composite → frame result``

概念辨析
--------

* **Framework DevTools vs Browser DevTools**：前者解释组件、route、store 等框架对象；后者证明实际网络、DOM、CPU、渲染和内存行为。
* **Network Waiting vs Server Root Cause**：长 TTFB 只能证明浏览器在等响应，数据库、源站或 CDN 哪一层慢仍需后端证据。
* **Long Task vs Render Cost**：long task 表示主线程被占用；具体成本可能来自 JavaScript、style、layout 或其它任务。
* **DOM Source vs Elements DOM**：源码/HTML response 是输入，Elements 是 parser、script 和 framework mutation 后的运行时结果。
* **Memory Growth vs Memory Leak**：内存增长可以是有效 cache 或长期状态；泄漏需要证明对象在应释放生命周期后仍被引用。

本章结论
--------

DevTools 是浏览器系统路径的证据面。稳定排查应从用户症状出发，先确认网络与缓存事实，再定位主线程和渲染成本，之后检查真实 DOM/CSS 与长期内存状态；框架结论必须能落到这些浏览器证据上，并在浏览器边界之外继续接入服务端与平台观测。