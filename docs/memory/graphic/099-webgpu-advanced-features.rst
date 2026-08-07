第099章：WebGPU 高级特性
=======================

核心知识点
----------

WebGPU 高级能力的核心是建立 GPU 内部闭环
   数据进入 GPU buffer/texture 后，compute pass 继续生成下一阶段资源，render pass 直接消费这些结果，JavaScript 只更新少量参数并编码命令。减少 GPU→CPU readback 和逐对象 JS 决策，是高级 WebGPU 扩展性的关键。

WebGPU 当前主线并没有标准化硬件 Ray Tracing Pipeline
   可以用 compute shader 实现软件 BVH 遍历、路径追踪、距离场或屏幕空间 ray marching，但这与 Vulkan RT、DXR、MetalRT 的 acceleration structure/ray pipeline 对象不是同一能力。工程上应把它建模为 compute path，而不是假设存在统一硬件 RT API。

Compute Pipeline 是最稳定的高级入口
   Simulation、visibility culling、LOD、compaction、image processing 等工作都可以使用 storage buffer/texture。其资源接口仍遵循 WGSL、bind group layout、usage flags 与 command pass 的显式合同。

Workgroup Size 是 Compute 执行粒度的重要参数
   Dispatch 数量、workgroup size、storage/shared memory、分支和内存访问模式共同决定 GPU 利用率。过小 dispatch 会放大提交成本，过大或访问离散则会放大带宽与 divergence。

Storage Buffer/Texture 用于跨 Pass 中间结果
   Compute 写粒子状态、visible list、光照缓存、体数据或 ray tracing 输出，后续 compute/render pass 直接读取。资源若能保持在 GPU 内部，就能避免每帧回到 JavaScript 再决定下一步。

Indirect Draw 把“画多少”也交给 GPU
   Compute 可以写 visible instance count 和 indirect argument buffer，render pass 再调用 ``drawIndirect/drawIndexedIndirect``。Buffer 必须包含 ``INDIRECT`` 与必要的 ``STORAGE`` usage，字段布局必须和 API 规定一致。

GPU-Driven 路径应按“更新→剔除→压缩→Indirect→Render”组织
   这种路径适合大规模粒子、草地、点云、体素、实例化节点等。CPU 不再逐对象读取可见性并发 draw，而是提交少量固定 pass。

Timestamp Query 是 GPU 性能证据，不是热路径同步点
   Query 随 command buffer 在 GPU 上执行，resolve 后还要经过 readback 才能由 CPU 读取。稳定 profiling 应延迟数帧读取、采样统计，并和 pass label、分辨率、资源规模一起记录。

JS↔GPU 交互次数经常比单行 Shader 算术更贵
   每帧反复创建 pipeline、bind group、buffer，频繁小块上传，或同步 readback 都会增加浏览器验证、对象分配和提交成本。长期对象应缓存，资源更新应按频率分层。

资源更新应分成低频、中频和高频
   大型几何、材质表、体数据和纹理属于低频，加载阶段上传；dirty brick、选择集等属于中频，按 chunk/range 更新；camera、time、mouse、frame index 属于高频，放入小 uniform/ring buffer 顺序写入。

Worker/OffscreenCanvas 可以减轻主线程压力
   数据解码、资源准备、部分命令构建和非 DOM GPU 工作可以迁到 worker。收益必须和消息传递、transferable、浏览器支持及调试复杂度一起评估。

高级 Web 应用仍受像素成本和透明 Overdraw 限制
   粒子 simulation 可能很快，但大量透明粒子会让 fragment/blend 成为主瓶颈；体渲染可能主要受采样次数与纹理带宽限制。优化必须基于实际 GPU pass 时间，而不是只优化 compute 阶段。

高级能力必须提供降级和预算
   软件 ray tracing 可降分辨率/采样或关闭，GPU-driven path 可回到 CPU culling/instancing，timestamp 可只在 profiling 模式启用。浏览器端高级路径首先要维持交互预算和跨设备稳定性。

关键路径
--------

GPU-Driven 粒子：

::

   JS frame parameters
   → uniform buffer
   → compute update particle state
   → compute visibility / compaction
   → visible instance buffer
   → indirect args buffer
   → render pass drawIndirect
   → canvas output

Compute 图像路径：

::

   scene/storage data
   → compute dispatch
   → storage texture
   → next compute/render pass samples result
   → post process / present

性能测量：

::

   timestamp before pass
   → GPU pass
   → timestamp after pass
   → resolve query
   → copy to readback buffer
   → delayed CPU mapping
   → aggregate by pass / frame percentile

JS-GPU 成本控制：

::

   classify resources by update frequency
   → cache pipeline/bind groups/resources
   → merge high-frequency small parameters
   → upload dirty ranges only
   → keep intermediate data on GPU
   → asynchronous/delayed readback only when needed

概念辨析
--------

* **WebGPU Compute Ray Tracing 与 Hardware RT Pipeline**：前者是 WGSL compute 算法，后者依赖专用 AS/ray pipeline API；WebGPU 主线并未统一暴露后者。
* **Storage Buffer 与 Indirect Buffer**：storage 是 shader 读写用途，indirect 是 draw/dispatch 参数用途，同一 buffer 可在声明相应 usage 后承担两者。
* **GPU-Driven 与 CPU-Driven**：前者让可见性、压缩和绘制数量留在 GPU，后者由 JS/CPU 逐对象决定。
* **Timestamp 与 CPU Timer**：timestamp 测 GPU 命令区间，CPU timer 测 JS/编码/提交路径，两者不能互相替代。
* **Worker 与 GPU 并行**：worker 减少主线程 CPU 压力，不代表 GPU pass 自动更快。
* **Upload 优化 与 Shader 优化**：前者解决 JS/浏览器/GPU 数据传输，后者解决 GPU 执行成本，证据入口不同。

本章结论
--------

WebGPU 高级渲染应按“Persistent GPU Data—Compute—Storage Result—Indirect/Render—Timestamp Evidence—Minimal JS Interaction”理解。画不出来先查 usage、WGSL/bind group 和 indirect layout；JS 时间高先查对象创建、碎片化上传和 readback；GPU 时间高再看 dispatch、内存带宽、fragment overdraw 与分辨率。高级 WebGPU 的价值不在堆更多 API，而在让决定、数据和中间结果尽可能留在 GPU 时间线上。