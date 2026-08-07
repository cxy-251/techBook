第087章：Direct3D Pipeline Mapping
=================================

核心知识点
----------

D3D12 Pipeline Mapping 的目标是把一次 Draw 拆成可检查状态
   一个 indexed draw 的最终结果由 IA 输入、shader、root signature、descriptor、PSO、viewport/scissor、RTV/DSV、resource barrier 和 draw 参数共同决定。``DrawIndexedInstanced`` 只是触发已经记录好的状态组合。

Pipeline 同时存在数据流与状态流
   数据流是 buffer/texture/constant → descriptor/root binding → shader → render target；状态流是 PSO、viewport、scissor、RTV/DSV 与 barrier 决定 GPU 如何解释这些数据。调试必须同时观察两条流。

IA 与 Vertex Shader 之间是内存布局契约
   Vertex buffer stride、index format、input layout semantic/offset 与 VS input signature 必须一致。顶点飞散或属性错位先查 IA state，再查 shader 数学。

VS 与 Rasterizer 之间以 ``SV_Position`` 为核心
   VS 输出裁剪空间位置，后续裁剪、perspective divide 与 viewport transform 由固定功能完成。Viewport、scissor、cull、front face、fill mode 与 sample state 都会改变可见覆盖。

Rasterizer 与 Pixel Shader 之间通过插值接口连接
   VS varying 经 rasterizer 插值进入 PS。UV、normal、color 等异常时，需要同时检查 VS 输出、插值语义、primitive orientation 与 rasterizer state。

Pixel Shader 与 Output Merger 之间仍有固定功能决策
   PS 输出 ``SV_Target`` 后，depth/stencil、blend、write mask、RTV/DSV format 与 sample count 决定最终写入。透明、深度和 MRT 问题必须检查 OM，而不是只看 PS。

D3D12 状态应分成 PSO、Binding 与 Dynamic 三层
   PSO 固化 shader bytecode、input layout、blend、rasterizer、depth/stencil、RTV/DSV format、sample count 与 root signature；binding 层包含 descriptor heap/table、CBV/SRV/UAV/sampler；dynamic 层包含 viewport、scissor、RTV/DSV、VB/IB、stencil ref、blend factor 与 barrier。

Root Signature 定义 Shader 可见资源形状
   Root signature 是 command list 与 shader resource register 之间的接口契约。PSO 与 root signature 必须兼容；descriptor table 与 root parameter 绑定必须在 draw 前完整设置。

PSO 是不可变 Pipeline State 的预组合对象
   创建 PSO 时就固定 shader、input、raster、depth/blend、render target format 等高相关状态。PSO cache key 若漏掉 sample count、RTV format、root signature 或 shader permutation，会造成错误复用。

Command List 记录的是“这一帧实际使用什么”
   初始化创建 root signature、descriptor heap 与 PSO；每帧 command list 选择 back buffer、执行 barrier、绑定 heap/table、设置 viewport/RTV/DSV/VB/IB，再 draw。不可变对象与 frame/draw 动态状态应分开管理。

Resource Lifetime 与 Command Recording 必须同时考虑
   Upload heap、constant ring、back buffer、material texture 与 transient descriptor 生命周期不同。CPU 录制完成不代表 GPU 已经消费，frame resource 复用仍需 fence 证明。

PIX/RenderDoc/Debug Layer 用于建立 Draw 的证据链
   Barrier audit 回答资源状态是否正确；descriptor inspection 回答 shader 实际读到哪一资源；PSO inspection 回答当前 pipeline 是否匹配；GPU timing 回答成本集中在哪个 pass 或状态切换路径。

状态问题可分成创建期、绑定期、动态漂移与缓存污染
   创建期如 input signature/RTV format/root signature 不兼容；绑定期如忘记设置 heap/table；动态漂移如 viewport/stencil ref 残留；缓存污染如错误 PSO key。分类后才能选择正确证据入口。

关键路径
--------

一次 Indexed Draw：

::

   SetPipelineState
   → SetGraphicsRootSignature
   → SetDescriptorHeaps
   → SetGraphicsRootDescriptorTable
   → IASetVertexBuffers / IASetIndexBuffer
   → IASetPrimitiveTopology
   → RSSetViewports / RSSetScissorRects
   → OMSetRenderTargets
   → ResourceBarrier as needed
   → DrawIndexedInstanced

Pipeline 阶段：

::

   vertex / index memory
   → input layout
   → vertex shader
   → rasterizer
   → pixel shader
   → depth / stencil / blend
   → RTV / DSV

PIX 排查：

::

   locate bad draw
   → PSO + root signature
   → IA state
   → descriptor heap / tables
   → shader inputs / outputs
   → viewport / scissor / RTV / DSV
   → resource history / barriers
   → GPU timing / PSO switch evidence

概念辨析
--------

* **PSO 与 Root Signature**：PSO 定义大部分 pipeline state，root signature 定义 shader 资源接口；二者必须兼容。
* **PSO State 与 Dynamic State**：shader/raster/depth/blend 等多为 PSO 状态，viewport、scissor、RTV/DSV、descriptor table 等在 command list 动态设置。
* **Descriptor Heap 与 Descriptor Table**：heap 是 descriptor 存储，table 是 root parameter 指向 heap 某段范围的绑定视图。
* **Barrier 与 Draw Binding**：barrier 证明资源用途顺序，binding 证明 draw 具体使用哪个资源。
* **Shader Output 与 Final Pixel**：PS 输出并非最终像素，OM 仍会执行深度、模板、混合和写掩码。
* **PSO Cache 与 Shader Cache**：shader cache 复用 DXIL blob，PSO cache 复用完整 pipeline 组合，key 空间不同。

本章结论
--------

D3D12 Pipeline Mapping 应按“PSO—Root/Descriptor—IA—Shader—Rasterizer—OM—Barrier—Draw”理解。看到黑屏时先固定具体 draw，再检查 PSO/root signature、IA 与 descriptor，然后看 viewport、RTV/DSV 和 resource state；看到性能问题则用 PIX timing、PSO switch、descriptor pressure 与 barrier 证据定位。稳定 renderer 的关键，是让不可变 pipeline、frame binding、draw binding 与 transient dynamic state 四层彼此独立且可追踪。