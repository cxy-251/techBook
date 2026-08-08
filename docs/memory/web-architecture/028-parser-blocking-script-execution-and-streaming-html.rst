Parser Blocking, Script Execution, and Streaming HTML
=====================================================

核心知识点
----------

* 同步 classic script 可以暂停 HTML parser，因为脚本必须在其文档位置观察并修改“解析到当前点”的 DOM。
* parser blocking 描述 parser 等脚本；stylesheet 还可能间接让同步脚本等待样式就绪，因此 CSS、script 与 DOM construction 会形成串行依赖。
* ``async``、``defer`` 与 ``type="module"`` 改变下载和执行时机：async 以完成时间驱动执行，defer 保留文档顺序并等待解析完成，module 还要等待模块图。
* ``DOMContentLoaded`` 不是“HTML 下载完成”的同义词，它还受到 defer/module 执行等启动工作影响。
* Streaming HTML 让 server generation、network transfer 和 browser parsing 重叠；先到达的 shell 可以先建 DOM、发现资源和显示 fallback。
* Streaming 与 hydration 必须共享稳定的 DOM/marker 边界；后续 chunk、脚本和客户端状态顺序错位会造成 hydration mismatch 或局部启动失败。

关键路径
--------

同步脚本路径：

``HTML bytes → parser → script token → pause parser → fetch/execute script → resume parser``

样式间接阻塞：

``stylesheet discovered → CSS load/parse → synchronous script reads style → script executes → parser resumes``

现代启动路径：

``HTML stream → DOM shell → defer/module graph → DOM parse complete → application/hydration execution → DOMContentLoaded``

Streaming：

``Server shell → network chunks → parser → fallback DOM → later chunks → hydration runtime → interactive UI``

概念辨析
--------

* **Parser Blocking vs Render Blocking**：前者阻止后续 HTML tree construction；后者阻止页面形成可稳定绘制的样式结果。
* **async vs defer**：async 不保证文档顺序；defer 保留顺序并在解析完成后执行。
* **Module Script vs Classic Script**：module 默认异步获取依赖图、具备模块作用域，并通常按类似 defer 的时机执行。
* **Streaming HTML vs Hydration**：streaming 负责分段交付 HTML；hydration 负责把已有 DOM 与客户端运行时状态关联。
* **首字节早 vs 首个有用 UI 早**：过早发送无实际内容的 chunk 不等于用户更早得到可见结果。

本章结论
--------

页面启动由 parser、CSS readiness、脚本调度、streaming response 与 hydration 共同决定。优化目标不是消灭所有阻塞，而是让必须同步的工作足够小、可延迟脚本退出关键路径、streaming 边界稳定，并用实际执行顺序解释 DOMContentLoaded 与首屏启动。