第086章：Direct3D 设备、管线与资源模型
=====================================

核心知识点
----------

Direct3D 是应用、Runtime、驱动与 GPU 之间的显式对象契约
   DXGI 负责 adapter、swap chain 与显示输出；Direct3D device 创建资源与状态对象；command context/list 描述工作；driver 将命令映射到 GPU。排查问题时应沿对象边界定位，而不是直接从 shader 数学开始猜。

Adapter、Feature Level 与 API Version 是不同维度
   Adapter 表示实际执行图形工作的设备，feature level 表示硬件能力边界，D3D11/D3D12 表示 API 与责任模型。能创建 D3D12 device 不代表所有高级特性都可用，仍需查询 feature、Shader Model、DXR、mesh shader、format 与 WDDM/驱动能力。

Device 负责创建，Resource 负责存储，View 负责解释
   Buffer、texture、back buffer 属于 resource；RTV、DSV、SRV、UAV、CBV 等 view 决定同一资源以何种用途进入管线。资源存在不等于已经按正确语义绑定，黑屏或错资源必须继续检查 view 与 pipeline binding。

Direct3D Pipeline 可按 IA→Shader→Rasterizer→OM 理解
   Input Assembler 读取 vertex/index buffer、input layout 与 topology；Vertex Shader 产生 ``SV_Position`` 和插值数据；Rasterizer 应用 viewport、scissor、cull 与 sample 状态；Pixel Shader 输出颜色；Output Merger 再执行 depth/stencil、blend 与 render target 写入。

Input Layout 是 CPU 顶点内存与 Shader Signature 的契约
   Semantic、format、offset、slot 与 stride 必须和 vertex shader 输入一致。顶点飞散、属性错位、三角形消失时，应优先检查 vertex buffer view、input layout、index format、topology 与 shader input signature。

Output Merger 是“Shader 已输出但画面仍错误”的高频边界
   Pixel shader 输出正常后，depth test、stencil、blend、RTV/DSV、write mask、sample count 与 render target format 仍可改变最终结果。黑屏排查不能停在 shader 输出。

D3D11 与 D3D12 的关键差异是隐式责任与显式责任
   D3D11 使用 device + immediate/deferred context，runtime/driver 处理更多 hazard 与状态管理；D3D12 使用 command allocator/list/queue、descriptor、barrier、fence，将资源状态、提交与同步责任交给应用。

D3D12 的第一帧必须显式管理 Back Buffer State
   Swap-chain back buffer 在呈现与渲染之间需要 ``PRESENT → RENDER_TARGET → PRESENT`` 转换。Barrier 不只是性能提示，而是资源用途变化的执行证据。

初始化应先验证“显示链”，再接入“渲染数据链”
   先完成 factory、adapter、device、swap chain、RTV/DSV、viewport 与 clear frame；clear 成功后，再增加 shader、vertex/index buffer、root signature/PSO 和 draw。这样能把窗口呈现问题与几何/材质问题分开。

D3D11 Immediate/Deferred 与 D3D12 Command List 不是同一抽象
   D3D11 deferred context 录制 command list，最终由 immediate context 执行；D3D12 command list 原生面向显式 queue 提交，并要求应用管理 allocator、descriptor、barrier 与 fence 生命周期。

兼容性应集中收敛到 Device Capability Profile
   启动时记录 adapter、feature level、Shader Model、格式支持、DXR/mesh shader tier、WDDM 与调试层状态。后续 renderer 只读取归一化能力位，避免各 pass 自行猜测平台支持。

关键路径
--------

D3D12 初始化：

::

   DXGI factory
   → enumerate adapter
   → create device
   → create command queue
   → create swap chain
   → acquire back buffers
   → create RTV / DSV
   → command allocator / command list
   → fence
   → clear frame
   → present

一次 Graphics Draw：

::

   vertex / index resources
   → views + input layout
   → IA
   → vertex shader
   → rasterizer + viewport / scissor
   → pixel shader
   → depth / stencil / blend
   → RTV / DSV
   → back buffer
   → present

黑屏排查：

::

   adapter / device / swap chain
   → current back buffer + RTV
   → viewport / scissor
   → resource state barrier
   → PSO / shader
   → vertex / index / input layout
   → descriptor / constants / textures
   → depth / blend / output merger
   → present state

概念辨析
--------

* **Adapter 与 Device**：adapter 是硬件/软件适配器，device 是应用针对该适配器创建的 Direct3D 对象入口。
* **Resource 与 View**：resource 保存数据，view 定义该数据以 RTV/DSV/SRV/UAV/CBV 等何种方式被访问。
* **Feature Level 与 API Version**：feature level 描述硬件能力，D3D11/D3D12 描述 API 与应用责任模型。
* **D3D11 Context 与 D3D12 Command List**：前者更依赖 runtime 状态管理，后者面向显式录制与 queue 提交。
* **Pipeline State 与 Dynamic State**：D3D12 大量状态固化进 PSO，但 viewport、scissor、RTV/DSV、descriptor table 等仍在 command list 中动态设置。
* **Barrier 与 Fence**：barrier 描述资源访问/状态顺序，fence 描述 GPU 执行进度；二者职责不同。

本章结论
--------

Direct3D 应按“Adapter—Device—Resource/View—Pipeline—Command—Queue—Swap Chain”理解。D3D11 与 D3D12 的主要差别不在渲染公式，而在状态、资源 hazard、命令与同步由谁负责。遇到黑屏时先验证显示链与 back buffer，再沿 IA、shader、rasterizer、OM 逐级检查；D3D12 还必须同时验证 descriptor、barrier 与 fence。稳定工程的基础，是把版本能力、对象职责和资源生命周期都收敛成明确契约。