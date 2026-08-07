第100章：将 Web API 映射到渲染 Pipeline
====================================

核心知识点
----------

Web 图形调用必须先映射到真实成本阶段
   ``fetch`` 属于网络，decode 属于 CPU 数据准备，GPU upload 属于主机→GPU 传输，pipeline creation 属于 shader/状态准备，command encoding 属于 CPU 提交构建，queue submit 属于 GPU 工作入口，canvas composite/present 属于浏览器显示路径。

首帧性能由 Critical Path 决定
   首帧必须等待的网络请求、模型/图片解码、最小 GPU 上传、shader/pipeline 和第一批 draw 构成 critical path。高清贴图、非可见模型、可选 shader variant 应从首帧链移出，异步替换。

WebGL 与 WebGPU API 形态不同，但阶段相同
   WebGL 用 context 状态、``bufferData/texImage2D/useProgram/draw*`` 表达资源与 draw；WebGPU 用 device resource、bind group、pipeline、command encoder 与 queue 表达。两者都可以统一抽象成 Asset→CPUData→GPUResource→Binding→Pipeline→Pass→Present。

Buffer/Texture 生命周期必须记录用途和更新频率
   静态 vertex/index 一次上传后长期驻留；per-frame uniform 使用 ring/分帧切片；storage buffer 可能 compute 写、render 读；texture 可能来自 asset、render target 或 storage output。资源类型本身不足以决定生命周期。

Sampler 与 Binding 也属于可复用资源
   Sampler 可按过滤/寻址 key 共享；WebGPU bind group 应按 layout 和资源版本缓存；WebGL 则需要稳定跟踪 texture unit、buffer binding 和 attribute state。频繁重建绑定对象会把成本推到 CPU。

资源状态应显式表达“未加载→已解码→已上传→可绘制”
   异步任务完成只改变资源状态，render loop 根据状态选择真实资源或 fallback。这样网络、decode、upload 和 draw 不需要在同一个主线程任务中阻塞等待。

Device/Context Lost 是 GPU 资源生命周期的全局边界
   JS 对象引用仍存在，不代表 GPU 资源继续有效。资源管理器应保存 CPU 可重建描述，包括 URL、几何源、shader/pipeline key、texture format、sampler 和 binding schema。

能力查询必须先于资源策略
   WebGPU 先查询 adapter/device feature、limit、canvas format；WebGL 查询版本、extension、texture/uniform/precision limits。Renderer profile 决定纹理格式、资源尺寸、后处理、bindless/compute 等路径和 fallback。

上传策略应和数据频率绑定
   静态资源加载阶段批量上传；中频资源按 dirty range/chunk 更新；高频小参数走 uniform/ring；大纹理分帧、压缩或渐进上传。连续在 render loop 上传大块数据会同时影响 JS、浏览器内部复制和 GPU 带宽。

事件循环会改变资源到达和帧提交的相对时机
   Promise/microtask、图片解码、worker message、pipeline async creation 与 rAF 会交错。资源系统必须用状态机收敛异步结果，不应让任何 Promise 完成回调直接无条件修改当前正在渲染的资源集合。

Fallback 应保持上层渲染语义
   WebGPU 不可用可退 WebGL2；高精度 texture 不可用降格式；资源未完成时用 placeholder；shader/pipeline 失败使用 debug material。Frame loop 只消费已经确定好的可用路径。

性能优化应先定位加载、CPU、上传、GPU 还是合成
   首帧慢看 fetch/decode/upload/pipeline；持续掉帧看 rAF 主线程、对象创建、API 调用、shader/带宽、canvas 分辨率和 DOM 合成。不同阶段需要不同工具和指标。

关键路径
--------

从网络到首帧：

::

   asset URL
   → fetch bytes
   → decode / parse CPU data
   → choose renderer capability path
   → create GPU buffers / textures
   → upload
   → create shader / pipeline / bindings
   → resource state = Ready
   → encode draw
   → submit
   → canvas texture / drawing buffer
   → browser composite

资源状态机：

::

   Unloaded
   → Loading
   → Decoded
   → Uploading
   → Ready
   → InUse / Resident
   → Retired
   → Released

   device/context lost
   → GPU objects invalid
   → rebuild from CPU descriptions

每帧：

::

   requestAnimationFrame
   → process ready async state changes
   → update small frame data
   → choose ready resources / fallbacks
   → encode GL/WebGPU commands
   → submit
   → browser composite

概念辨析
--------

* **Fetch Complete 与 Resource Ready**：网络完成只说明字节到达，后面仍可能有 decode、upload 和 pipeline/binding 准备。
* **CPU Data 与 GPU Resource**：前者可用于恢复和重建，后者属于当前 context/device 生命周期。
* **Asset Lifetime 与 Frame Lifetime**：长期资产跨很多帧存在，per-frame uniform/temporary attachment 只在有限 frame slot 内存在。
* **Upload 与 Draw**：upload 负责数据进入 GPU，draw/dispatch 负责消费资源；将大上传放在 draw 热路径会制造尖峰。
* **Async Completion 与 Render Ownership**：Promise/worker 完成表示材料可推进状态，不应绕过 renderer 的帧边界直接改变 in-flight 资源。
* **WebGL State Tracking 与 WebGPU Compatibility Tracking**：前者重点跟踪当前隐式绑定，后者重点跟踪 pipeline/bind group/usage/format 兼容性。

本章结论
--------

Web 图形程序应按“Network—Decode—GPU Upload—Resource/Binding—Pipeline—Command Encode—Submit—Browser Composite”理解。首帧慢先找 critical path，闪烁先查资源状态和异步替换时机，内存泄漏查资源引用与释放，持续掉帧再区分 JS/上传/GPU/DOM 合成。把 Web API 名称放回这条真实数据路径后，加载、渲染和浏览器调度问题才能用同一套工程模型定位。