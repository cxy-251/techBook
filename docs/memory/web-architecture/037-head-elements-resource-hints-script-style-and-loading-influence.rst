Head Elements, Resource Hints, Script, Style, and Loading Influence
===================================================================

核心知识点
----------

* ``head`` 是 document 的机器可读控制区，集中定义字符集、viewport、title、description、canonical、资源关系、脚本调度和样式加载等初始条件。
* Metadata 决定文档身份和机器解释。``title``、``description``、``canonical``、``robots``、Open Graph、语言和 viewport 会影响浏览器 UI、crawler、社交预览和移动端布局。
* ``link`` 的关键语义由 ``rel`` 决定：stylesheet 进入 CSSOM，preload 提前声明当前导航关键资源，preconnect 只做连接准备，prefetch 面向潜在未来使用，canonical 则表达 URL 关系。
* Resource hint 只是 hint，不是保证。错误 preload/preconnect 会浪费连接、带宽和优先级预算；``as``、``crossorigin``、``type`` 与真实请求不匹配还可能导致重复下载。
* Script 的 ``async``、``defer``、module 等属性决定下载与执行顺序；错误的依赖假设会推迟 DOMContentLoaded、破坏 hydration 或制造启动竞争。
* Stylesheet 与 font 位于首屏 render readiness 路径。关键 CSS、字体发现时间和 media 条件会影响 FCP、LCP 和布局稳定性。

关键路径
--------

文档启动控制面：

``Server/Build → initial HTML head → parser → document metadata + resource discovery → network scheduling → style/script readiness → page startup``

资源关系：

``link rel → relationship semantics → request/connection/crawler behavior``

脚本调度：

``script discovery → fetch → async/defer/module ordering → execution → DOM/hydration state``

公开机器解释：

``server-rendered metadata → crawler/social bot/browser UI → external representation``

排查 ``head`` 问题时先看初始 HTML，再看浏览器真实请求与执行顺序，最后检查外部 crawler/cache 是否持有旧副本。

概念辨析
--------

* **Metadata vs visible content**：metadata 主要服务浏览器和机器系统；body 内容主要服务用户，但两者必须表达同一页面身份。
* **Preload vs Prefetch**：preload 面向当前导航已知关键资源；prefetch 面向较低确定性的未来资源。
* **Preconnect vs Preload**：preconnect 只准备 DNS/连接/TLS；preload 会实际获取指定资源。
* **``async`` vs ``defer``**：async 完成后尽快执行且不保证文档顺序；defer 等解析结束并保持 classic script 的文档顺序。
* **Stylesheet link vs preload style**：preload 只获取资源；真正作为 stylesheet 使用还需要 stylesheet 关系或后续代码接入。
* **Canonical vs Redirect**：canonical 是机器可读主 URL 提示；redirect 是浏览器/HTTP 导航控制动作。

本章结论
--------

``head`` 决定页面启动和公开身份的早期控制面。字符解码、viewport、metadata、CSS、脚本和 resource hint 都会在正文可见之前改变浏览器路径。高质量 ``head`` 的目标不是堆叠优化标签，而是让文档身份、关键资源和执行顺序与真实页面路径一致。