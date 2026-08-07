第092章：Metal 架构
==================

核心知识点
----------

Metal 是 Apple 平台上的显式图形与计算 API
   它用 ``MTLDevice``、``MTLCommandQueue``、``MTLCommandBuffer``、encoder、pipeline state 和资源对象描述 GPU 工作。应用需要明确一帧使用哪些 render target、buffer、texture、pipeline 和提交顺序。

MTLDevice 是能力与对象创建入口
   Device 代表当前可用 GPU，并负责创建 buffer、texture、sampler、pipeline state、heap 与 command queue。平台能力、pixel format、sample count、ray tracing 或 mesh shader 等高级路径都应先通过 device/profile 判断。

Command Queue 与 Command Buffer 分离提交层级
   ``MTLCommandQueue`` 生产 command buffer，``MTLCommandBuffer`` 表示一次 GPU 工作批次。一个 command buffer 中可以按顺序包含 render、compute、blit 等 encoder；``commit`` 只表示提交，不表示 GPU 已执行完成。

Encoder 是具体命令域
   Render encoder 绑定 ``MTLRenderPipelineState``、vertex/index buffer、texture、sampler、depth/stencil state 并编码 draw；compute encoder 编码 dispatch；blit encoder 处理复制和部分同步。Encoder 边界也是资源读写与调试的重要观察点。

Render Pass Descriptor 描述 Attachment 合约
   Color/depth/stencil texture、load action、store action、clear value、resolve target 与 sample count 都通过 pass descriptor 建立。画面黑屏时，必须确认 drawable/attachment 存在、格式与 pipeline 匹配、load/store 行为没有丢失结果。

MTLRenderPipelineState 是不可变的预编译渲染契约
   Vertex/fragment function、vertex descriptor、color/depth/stencil format、sample count 和 blend 条件会形成 pipeline state。它和 Vulkan graphics pipeline、D3D12 PSO 的工程作用一致：把关键状态提前验证和编译。

Pipeline Cache Key 必须包含输出格式条件
   Shader 名称相同但 color format、depth format、MSAA sample count、vertex layout 或 function constant 不同，都可能需要不同 pipeline。只按材质名或 shader 名缓存会产生错误复用。

Metal 的资源绑定接口较直接，但生命周期问题仍然存在
   小型路径可以直接 ``setVertexBuffer``、``setFragmentTexture``、``setFragmentSamplerState``；大型系统仍需按 frame/pass/material/object 组织频率，并使用 argument buffer、heap 或资源表降低重复绑定。

Apple Silicon 的统一内存不等于无同步
   CPU 和 GPU 可以更直接共享某些内存，但 CPU 何时可重写 buffer、GPU 何时完成读取、资源何时安全复用仍需要 frame ring、command buffer completion、event/fence 或 storage mode 规则来证明。

Storage Mode 决定 CPU/GPU 可见性与性能路径
   Shared 适合 CPU/GPU 共同访问的小型动态数据；Private 适合 GPU 高频访问资源，通常经 staging/blit 上传；Managed 等模式在特定平台还需要显式同步。资源用途应和 storage mode 一起设计。

Drawable 把 GPU Render Target 接到显示系统
   ``MTKView`` 或 ``CAMetalLayer`` 提供当前 drawable texture。典型顺序是获取 drawable → 建 render pass → 编码 draw → end encoder → ``present`` drawable → commit command buffer。Drawable 生命周期不能跨帧无约束持有。

Metal 与 Vulkan/D3D12 的差异主要是显式程度和平台抽象边界
   Vulkan 暴露更细的 image layout、access mask 与 queue family ownership；D3D12 强调 descriptor heap/root signature/resource state；Metal 吸收部分底层状态，但依然要求明确 pipeline、resource usage、encoder 顺序与 frame-in-flight 生命周期。

Xcode GPU Capture 是 Metal 的主要证据入口
   Draw、pipeline state、resource table、attachment、encoder 顺序和 GPU timing 都能在 capture 中检查。遇到黑屏或资源错乱，应先定位具体 draw/encoder，再看 pipeline 与资源，而不是先改 shader。

关键路径
--------

Metal 初始化：

::

   select MTLDevice
   → create MTLCommandQueue
   → load/compile shader library
   → create pipeline states
   → create static buffers / textures / samplers
   → configure MTKView / CAMetalLayer

一帧渲染：

::

   acquire drawable
   → allocate/update frame resources
   → create render pass descriptor
   → make command buffer
   → make render encoder
   → bind pipeline + buffers + textures
   → draw
   → end encoder
   → present drawable
   → commit command buffer
   → completion retires frame resources

资源复用：

::

   choose frame slot
   → CPU writes shared/upload data
   → encode GPU use
   → commit
   → GPU executes
   → completion/event signals
   → frame slot becomes reusable

概念辨析
--------

* **Device 与 Command Queue**：device 负责能力与资源创建，queue 负责生产按顺序提交的 command buffer。
* **Command Buffer 与 Encoder**：command buffer 是一批 GPU 工作，encoder 是其中某一类 render/compute/blit 命令的编码域。
* **Pipeline State 与 Render Pass Descriptor**：pipeline 固化 shader 与格式契约，pass descriptor 指定本帧真正使用的 attachment 和 load/store 行为。
* **Drawable 与 Texture**：drawable 包含可呈现 texture，并受显示系统生命周期管理；普通 texture 完全由应用管理。
* **Shared Memory 与 Synchronization-Free**：共享内存减少复制，不会取消 CPU/GPU 并发访问冲突。
* **Argument Buffer 与普通 set* 绑定**：前者适合大资源表和减少绑定调用，后者适合数量较少、结构简单的资源。
* **Commit 与 Complete**：commit 只提交工作，完成状态需要 completion handler、event 或其它 GPU 进度证据。

本章结论
--------

Metal 应按“Device—Command Queue—Command Buffer—Encoder—Pipeline State—Attachment/Drawable—Commit/Complete”理解。黑屏先查 drawable、render pass、pipeline format 与 draw 是否存在；随机资源错乱先查 frame slot 与 CPU/GPU 复用；提交抖动再看 command encoding、pipeline miss 和 GPU timeline。Metal 隐藏了一部分 Vulkan 式低层状态，但没有隐藏一帧渲染最核心的对象契约、资源生命周期和执行顺序。