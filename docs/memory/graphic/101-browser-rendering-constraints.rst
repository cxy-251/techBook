第101章：浏览器渲染约束
======================

核心知识点
----------

浏览器图形渲染同时受安全模型和帧调度模型约束
   WebGL/WebGPU 不仅要正确驱动 GPU，还要与跨域策略、事件循环、DOM/CSS、worker、内存限制和 context/device loss 共存。浏览器端卡顿不能只归因于“GPU 慢”。

跨源资源是否可读回由 CORS 决定
   图片、视频或瓦片可以成功显示，但若缺少正确跨域许可，canvas 可能进入 tainted 状态，后续截图、像素读取、导出或部分测试路径会触发安全错误。资源系统应记录“可显示”与“可读回”两种能力。

WebGPU Device/Feature/Limit 属于浏览器安全边界的一部分
   页面得到的是受控 logical device，而非底层 GPU 直接访问。Adapter、device、features、limits、preferred format 应集中形成 renderer profile，后续资源和 pipeline 都从该能力表选择路径。

高精度计时也受安全策略影响
   单帧时间值可能受精度限制和浏览器调度噪声影响。性能判断应使用滑动统计、P50/P95/P99、阶段 marker 与重复实验，不应仅凭单个尖峰下结论。

主线程同时承担 JS、事件、样式布局和部分渲染调度
   大型解析、状态更新、hit test、上传准备、React/Vue 更新或同步读回都会挤占 rAF 之前的时间，最终表现为输入延迟和动画卡顿，即使 GPU 本身还有余量。

requestAnimationFrame 只是帧入口，不是性能保证
   rAF 回调应只放必须在当前帧完成的工作：输入、相机、少量 scene update、draw submit、必要 overlay 更新。大数据解析、空间索引、资源转码、静态合并、预编译等应拆到 worker 或多帧任务队列。

Microtask 可以延迟浏览器进入绘制阶段
   Promise 链、async 续体、框架状态批处理可能在当前任务结束后密集执行。排查主线程卡顿时要区分 rAF、普通 task、microtask、layout、paint 和 GPU submit，而不是只看业务函数。

Worker 适合搬走纯计算和数据准备
   文件解析、过滤、索引构建、几何压缩、资源转码等适合 worker。Worker 不能直接操作 DOM，消息复制和 transferable 成本也需要测量。并行化的目标是缩短主线程 critical work，而不是无条件增加线程。

OffscreenCanvas 可进一步分离 Canvas 渲染与 DOM 主线程
   图形层可以在 worker 中持有 offscreen canvas 并执行 WebGL/WebGPU 工作，主线程保留输入与 DOM。收益取决于浏览器支持、消息协议和资源所有权设计。

GC Pause 是浏览器图形帧尖峰的常见来源
   每帧分配临时数组、对象、闭包、矩阵和遥测 payload 会形成 heap 锯齿并触发回收。图形热路径应复用 typed array、矩阵、command data 和事件对象，避免把高频 pointer event 扩散成大量短生命周期对象。

Canvas 与 DOM Overlay 必须共享同一坐标与尺寸模型
   CSS size、drawing buffer size、DPR、viewport、投影矩阵、canvas bounding rect、滚动偏移和事件坐标必须对齐。命中位置偏移、tooltip 漂移和高 DPI 模糊通常来自这些坐标层级不一致。

DOM/CSS 合成本身也会消耗帧预算
   大面积透明、filter、backdrop blur、阴影、频繁 transform 和整棵组件树更新会增加 style/layout/paint/composite 成本。Canvas GPU pass 很快并不代表页面最终呈现一定快。

内存压力最终会表现为长会话退化或 Context/Device Loss
   大数据集、解码像素、GPU texture/buffer 与 JS heap 共同消耗系统资源。资源层需要预算、LRU/streaming、延迟释放和重建描述，不能只依赖浏览器自动回收。

浏览器瓶颈排查应按层推进
   先看安全/资源失败，再看 rAF 与 long task，再看 worker/上传，再看 GPU pass，再看 DOM/CSS composite，最后看内存曲线和 context/device loss。这样能避免把主线程或 CORS 问题误判成 GPU 问题。

关键路径
--------

浏览器一帧：

::

   input events
   → JS task / microtask
   → scene/UI state update
   → optional worker messages
   → canvas command encoding / submit
   → DOM style / layout / paint
   → GPU execution
   → browser composite
   → present

跨域资源：

::

   asset URL
   → fetch / image decode
   → CORS result
   → display-only or readable resource
   → GPU upload
   → canvas draw
   → optional readback / export

主线程排查：

::

   rAF interval
   → long task / LoAF
   → script + microtask duration
   → layout / paint
   → upload / sync readback
   → GPU submit
   → DOM composite

概念辨析
--------

* **可显示资源 与 可读回资源**：跨域资源可能允许显示，却不允许像素导出或读取。
* **rAF 与 Frame Budget**：rAF 提供刷新前回调机会，真正是否按时完成取决于回调内及前后任务总成本。
* **Worker 与 OffscreenCanvas**：worker 是后台 JS 执行环境，OffscreenCanvas 允许部分 canvas 渲染所有权转移到 worker。
* **Main-Thread Bottleneck 与 GPU Bottleneck**：前者表现为输入/rAF/脚本延迟，后者需要 GPU pass timing 或分辨率/效果对照证明。
* **CSS Size 与 GPU Render Size**：页面布局尺寸和 drawing buffer 像素尺寸不同，DPR 把二者连接起来。
* **Context/Device Loss 与普通 GC**：GC 回收 JS 对象，context/device loss 则让 GPU 资源体系整体失效，需要显式恢复。

本章结论
--------

浏览器图形系统应按“Security—Event Loop—Main Thread/Worker—Canvas GPU Path—DOM/CSS Composite—Memory/Recovery”理解。导出失败先查 CORS，拖动卡顿先查 rAF/long task/microtask，画面快但 UI 慢则查 DOM 合成，长会话退化再查资源预算与 context/device loss。浏览器端稳定渲染的关键，是把 GPU 工作放进 Web 平台真实的安全、线程、坐标和内存边界内设计。