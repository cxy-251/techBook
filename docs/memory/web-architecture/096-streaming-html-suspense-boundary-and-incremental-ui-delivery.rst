第096章：Streaming HTML, Suspense Boundary, and Incremental UI Delivery
======================================================================

核心知识点
----------

* Streaming HTML 把页面响应从“完整文档准备好再返回”改成“可显示片段准备好就逐步输出”。
* 首批可用内容通常是 document shell、layout、标题、主图和 fallback；慢数据区域随后继续通过同一响应补齐。
* Streaming 优化的是等待路径和内容可见时机，不会减少数据库查询、模板执行、网络传输和客户端激活的总工作量。
* ``Suspense-like boundary`` 决定等待在哪里变成用户可见状态；边界应对应可命名、可独立等待、可独立失败的页面区域。
* 边界过大，会退化为整页 loading；边界过细，会造成大量闪烁、替换、布局抖动和脚本协调成本。
* Streaming 能否真正到达用户，取决于 server runtime、framework stream、compression、reverse proxy、CDN 与 browser 都允许早期字节向前流动。
* 一旦响应头和部分 body 已提交，后续错误通常无法再改写成新的完整 HTTP 状态；恢复要依赖局部 error boundary、fallback、客户端修复或终止 stream。
* 流式片段还必须和 CSS、script、module graph、hydration data、客户端事件绑定及资源发现顺序协调。

关键路径
--------

::

   Browser Request
     → Server Route / Permission
     → Render Stable Shell
     → Commit Headers + First Bytes
     → Proxy / CDN / Compression
     → Browser Incremental Parse
     → Early DOM / Paint

   Slow Data / Component Work
     → Suspense Boundary Fallback
     → Fragment Ready
     → Stream Remaining HTML / Payload
     → Replace Fallback
     → Client Activation

* 排查“服务端已经 streaming、浏览器仍一次性显示”时，依次观察 server 第一次 write、压缩 flush、代理缓冲、CDN 行为、浏览器收到首批 body 的时间和关键 CSS 是否阻塞绘制。
* 交易相关区域必须把价格、库存、购买按钮放在一致的可信边界里，不能为了更早显示而暴露互相矛盾的中间状态。

概念辨析
--------

* **Streaming ≠ HTTP chunked transfer**：chunk/framing 是传输表现；应用级渐进 UI 还需要可独立的内容边界和替换语义。
* **Suspense ≠ loading spinner**：它定义的是等待边界、恢复位置和内容提交关系，fallback 只是其中一个可见结果。
* **更早 first byte ≠ 更早 useful UI**：无意义的小片段、缺少 CSS 的 shell 或无法交互的占位并不能改善关键任务。
* **响应已开始 ≠ 请求已完成**：stream 生命周期中仍可能发生下游超时、用户取消、数据失败和客户端断开。
* **Streaming ≠ 自动更快**：若代理缓冲、最慢区域属于核心内容或客户端激活很重，用户仍可能没有明显收益。

本章结论
--------

Streaming 的价值在于把页面拆成可先显示、可等待、可失败、可恢复的片段，让最慢依赖不再阻塞全部内容。它要求整个传输链保持流动，并要求边界设计与用户语义一致；一旦开始提交响应，错误恢复与缓存策略也必须按“部分结果已经对用户可见”重新设计。
