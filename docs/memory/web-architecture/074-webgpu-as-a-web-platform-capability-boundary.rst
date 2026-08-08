WebGPU as a Web Platform Capability Boundary
============================================

核心知识点
----------

* WebGPU 是浏览器暴露的现代 GPU 能力，强调显式资源管理、命令提交、render/compute pipeline 和更清晰的 CPU/GPU 协作。
* 能力发现从 ``navigator.gpu.requestAdapter()`` 开始，再通过 adapter 请求 device；adapter/device 把浏览器策略、硬件 feature、limit 和可用格式转成受控能力集合。
* 页面不能假设某个 GPU、feature 或 limit 一定存在。设备、驱动、浏览器版本、操作系统和安全上下文都会改变能力结果。
* WebGPU 的核心对象包括 device、queue、buffer、texture、sampler、shader module、pipeline、bind group、command encoder/pass 和 command buffer。
* 浏览器在页面与原生图形 API/驱动之间执行验证、初始化与隔离，防止越界访问、未初始化数据泄漏和驱动级故障扩散。
* 与更隐式的图形接口相比，WebGPU 把更多责任交给应用：资源用途、绑定布局、pipeline、命令记录、提交、同步点和错误恢复都需要明确设计。
* compute pipeline 让图像处理、仿真、粒子、数据并行和部分机器学习工作进入浏览器 GPU 路径，但数据搬运与同步仍然可能成为主要成本。
* WebGPU 必须设计 feature detection 与 fallback：可以降级到 WebGL、Canvas、CPU/Worker 或关闭高性能功能，不能把 API 存在当作产品可用性保证。

关键路径
--------

能力发现：

``Secure Context → navigator.gpu → requestAdapter → inspect features/limits → requestDevice``

执行路径：

``Application State → GPU Resources / Pipelines → Command Encoding → GPUQueue.submit → Browser GPU Process / Native API → GPU → Presentation Surface → Compositor``

降级路径：

``WebGPU unavailable / feature missing / device lost → choose WebGL / Canvas / Worker / server-side alternative → preserve user-visible task``

架构判断依次确认：当前 runtime 与 secure context → adapter/device 能力 → 数据与资源生命周期 → render/compute pipeline → 异步提交与同步点 → device lost / fallback。

概念辨析
--------

* **WebGPU ≠ 直接暴露 Vulkan/Metal/D3D12**：浏览器提供统一 Web API，并在底层映射到平台图形栈。
* **adapter ≠ 可长期持有的物理 GPU 身份**：它是浏览器提供的能力视图，实际选择受实现和策略控制。
* **device 创建成功 ≠ 所有 feature 可用**：必须读取 features、limits，并只请求需要的能力。
* **compute ≠ 免费并行**：上传、读回、布局转换和同步可能比计算本身更贵。
* **高性能 API ≠ 无降级需求**：浏览器能力差异本身就是 Web 架构的一部分。

本章结论
--------

WebGPU 应被理解为“浏览器治理下的现代 GPU 能力边界”。应用显式组织资源、pipeline 和命令，浏览器负责能力发现、安全验证与隔离，GPU 异步执行。正确架构必须同时包含 feature/limit 检测、资源与数据生命周期、CPU/GPU 协作、device loss 和可用降级路径。