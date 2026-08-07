第098章：WebGPU Device、Queue 与 Pipeline 模型
===========================================

核心知识点
----------

WebGPU 以显式对象描述浏览器 GPU 工作
   ``GPUAdapter`` 表示浏览器可用的 GPU/驱动组合，``GPUDevice`` 是页面取得的逻辑设备，``GPUQueue`` 接收已编码命令。资源用途、shader 接口、pipeline 和 attachment 都在创建或编码阶段显式声明。

WebGPU 与 WebGL 的关键差异是状态组织方式
   WebGL 依赖 context 持续状态；WebGPU 把 shader、vertex layout、primitive、color target 和绑定布局组合成 pipeline，把资源绑定组合成 bind group，把一帧命令组合成 command buffer。很多错误会更早在 validation 阶段暴露。

Device 是资源与 Pipeline 的创建边界
   Buffer、texture、sampler、shader module、bind group layout、bind group、render/compute pipeline 都属于某个 device。Device lost 后，这些对象整体失效，需要重新 request device 并按依赖重建。

Queue 是数据上传与 GPU 提交入口
   ``queue.writeBuffer`` 等接口负责部分 host→GPU 数据更新，``queue.submit`` 接收完成编码的 command buffer。Submit 返回只说明工作已进入队列，不代表 GPU 已经执行完成。

Render Pipeline 是 Draw 的固定执行合同
   Vertex/fragment shader、vertex buffer layout、primitive state、color target format、depth/stencil 等稳定条件进入 ``GPURenderPipeline``。帧循环应复用 pipeline，不应每帧重新创建。

WGSL 与 Host Descriptor 必须形成一一对应接口
   ``@location`` 对应 vertex attribute，``@builtin(position)`` 对应固定管线位置，``@group/@binding`` 对应 bind group layout，fragment ``@location(0)`` 对应 color target。Shader 能创建不代表 host 侧 layout 已匹配。

Bind Group 把 Shader 逻辑槽连接到真实资源
   WGSL 只定义某个 group/binding 需要何种资源；bind group layout 定义类型和 stage visibility；bind group 再把具体 buffer、texture view、sampler 放入槽位。三者必须一致。

Buffer/Texture Usage 在创建时就是合法性边界
   Vertex buffer、uniform buffer、storage、copy、indirect 等用途通过 usage flags 声明。后续操作未包含对应 usage 会触发 validation error。Usage 既是安全约束，也是浏览器优化底层资源的依据。

Render Pass 决定本帧写入哪个 Attachment
   每帧通过 ``GPUCanvasContext.getCurrentTexture()`` 取得当前画布纹理，创建 view 后放入 color attachment。Pipeline fragment target format 必须与 canvas context format 一致。

Command Encoder 把 CPU 录制与 GPU 执行分开
   ``beginRenderPass``/``beginComputePass`` 只是在 encoder 中记录命令；``finish`` 生成 command buffer；``queue.submit`` 才进入 GPU 执行路径。这个分界是分析 CPU encoding 与 GPU execution 的基础。

WebGPU 的稳定路径是初始化阶段重、帧循环阶段轻
   Device、shader module、pipeline layout、pipeline、静态 buffer 和大多数 bind group 应长期复用；每帧只更新确实变化的 uniform/动态资源并编码 draw/dispatch。

调试应优先使用 Validation 与错误作用域
   Shader、layout、usage、format、attachment、bind group 不匹配应尽量在创建和编码阶段发现。遇到 device lost、uncaptured error 或 validation error 时，先按对象层级定位，不要直接归因于浏览器或 GPU。

关键路径
--------

初始化：

::

   navigator.gpu
   → requestAdapter
   → requestDevice
   → query features / limits
   → configure GPUCanvasContext
   → create buffers / textures / shader modules
   → create bind group layouts / bind groups
   → create render pipeline

一帧渲染：

::

   update uniform / dynamic data
   → getCurrentTexture
   → create view
   → create CommandEncoder
   → beginRenderPass
   → setPipeline
   → setVertexBuffer / setBindGroup
   → draw
   → end pass
   → finish CommandBuffer
   → queue.submit
   → browser presents canvas texture

接口校验：

::

   WGSL @location / @group / @binding
   → vertex layout / bind group layout
   → concrete bind group resources
   → pipeline layout
   → render pass attachment format
   → validation

概念辨析
--------

* **Adapter 与 Device**：adapter 表示候选 GPU 能力，device 是页面实际获得的逻辑执行对象。
* **Device 与 Queue**：device 创建对象，queue 负责上传与提交已编码命令。
* **Pipeline 与 Pass**：pipeline 固化执行状态，pass 指定本帧实际 attachment、资源绑定和 draw/dispatch。
* **Bind Group Layout 与 Bind Group**：前者定义资源接口形状，后者保存具体资源绑定。
* **Command Encoder 与 Command Buffer**：encoder 负责录制，buffer 是可提交的最终命令集合。
* **Submit 与 Complete**：submit 只进入队列，完成状态需要额外 GPU 进度证据。
* **WGSL Valid 与 Pipeline Valid**：WGSL 语法正确并不保证 vertex/binding/target 等 host 合同正确。

本章结论
--------

WebGPU 应按“Adapter—Device—Resource—Pipeline/BindGroup—CommandEncoder—CommandBuffer—Queue—Canvas Texture”理解。初始化失败先查 adapter/device 与 capability；黑屏先查 target format、pipeline、WGSL 接口与 bind group；帧时间抖动先看是否在热路径反复创建 pipeline、buffer 或 bind group。WebGPU 的核心收益，是让资源用途、shader 接口和提交边界都提前结构化，从而把浏览器 GPU 工作变成可验证的数据与命令合同。