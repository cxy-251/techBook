第085章：OpenGL 调试与扩展
========================

核心知识点
----------

OpenGL 调试应建立“错误信号—状态证据—能力边界—修复路径”
   黑屏、错纹理、深度异常和 blend 错误都只是视觉症状。稳定调试流程要先让 driver 产生可记录信号，再把消息绑定到 pass 与对象，随后用 frame capture 展开真实 draw state，最后确认当前平台能力与 fallback 是否一致。

``glGetError`` 适合局部哨兵，不适合作为完整诊断系统
   它能把错误区间缩小到资源创建、FBO 配置或某次 draw 前后，但只返回错误枚举，不携带对象名、pass、调用栈、driver 解释和性能提示。大型工程应以 debug output 为主，``glGetError`` 作为局部补充。

Debug Output 是 OpenGL 的主要运行时错误信号通道
   ``glDebugMessageCallback`` 可以接收 source、type、severity、id 与 driver message；``GL_DEBUG_OUTPUT_SYNCHRONOUS`` 让消息更接近触发 GL 调用，适合开发期断点。Callback 内应保持轻量，把分析工作放到日志或帧尾。

Object Label 与 Debug Group 把数字状态映射回工程语义
   ``glObjectLabel`` 给 texture、buffer、program、VAO、FBO 等对象命名，``glPushDebugGroup``/``glPopDebugGroup`` 标记 pass 或 draw 范围。没有这些标签，driver 报错和 frame debugger 中的数字 object id 很难回到业务对象。

Debug Message 应按严重性和类型分类处理
   High-severity error、undefined behavior 适合断点或测试失败；performance warning 用于优化证据；低价值 notification 应按 id 过滤。调试通道要能被统计、过滤和自动化测试消费。

Extension 是能力边界，不是“有字符串就能用”
   ARB、EXT、KHR、vendor extension 表示不同标准化与平台覆盖路径。稳定 feature profile 同时记录 version、profile、vendor、renderer、extension、function entry、limits 与 format support，再把结果归一化为引擎能力位。

Core Version 与 Extension 可能表达同一能力
   某些功能先以 extension 出现，之后进入核心版本。能力判断应使用“core version 或 extension + function pointer + limit”的组合，而不是只检查扩展名。

Fallback 必须与 Shader、Resource、Binding 同时切换
   平台缺少 texture array 等能力时，不能只把资源从 ``GL_TEXTURE_2D_ARRAY`` 换成 ``GL_TEXTURE_2D``，shader 的 sampler 类型、材质 variant、binding layout 和 UV/layer 数据也必须一起切到 fallback 分支。

RenderDoc 用来观察某个 Draw 的真实状态
   调试顺序通常是定位异常 draw → 检查 framebuffer/viewport/scissor → depth/blend/color mask → VAO/buffer → texture/sampler → shader I/O → render target history。它回答的是“这一帧 GPU 实际看到了什么”。

GLIntercept 更偏 API 调用序列记录
   对旧 Windows OpenGL 项目，它可用来追踪哪个函数按什么顺序修改了状态。现代工程通常优先使用 RenderDoc，GLIntercept 作为特定环境下的补充。

黑屏应先分类而不是直接改 Shader
   典型四类是：根本没有 draw；draw 没有覆盖屏幕；fragment 被 cull/depth/stencil/discard；输出随后被 clear/blend/覆盖。分类后再进入对应状态层。

错误纹理要同时检查 Resource Identity 与 Sample Path
   Resource identity 包括 texture object、target、format、mip、array layer；sample path 包括 sampler type、texture unit、sampler object、uniform、UV。Texture viewer 能看到图像内容，并不能证明 shader 正在按正确 target 和 layer 采样它。

深度问题需要统一检查写入、比较、范围和清理
   Attachment、depth mask、depth func、projection/reversed-Z、depth range、clear value 与 pass 顺序必须处于同一约定。Shadow pass 残留 depth func 或 clear value 是常见状态泄漏。

Blend 问题需要同时检查颜色与 Alpha 语义
   Render target format、linear/sRGB、premultiplied alpha、blend equation、blend func 和 color mask 都会影响结果。UI pass 的 blend 状态污染不透明 pass 时，G-buffer 或主颜色输出也可能被破坏。

关键路径
--------

错误信号：

::

   debug context
   → enable GL_DEBUG_OUTPUT
   → debug callback
   → source / type / severity / id
   → debug group + object labels
   → structured log / breakpoint
   → frame capture

Frame Capture：

::

   locate bad draw
   → framebuffer / viewport / scissor
   → depth / stencil / blend / color mask
   → VAO / vertex / index input
   → texture / sampler / uniform bindings
   → shader input / output
   → render target before/after draw
   → owning pass / API call sequence

Capability 与 Fallback：

::

   query version / profile / vendor
   → enumerate extensions
   → load function entries
   → query limits / formats
   → build normalized feature profile
   → select shader + resource + binding branch
   → validate fallback with debug assertions

复杂错误排查：

::

   record symptom
   → enable debug signals
   → identify exact pass/draw
   → inspect output state
   → inspect input resources
   → compare feature profile
   → build minimal repro
   → fix state contract / capability branch
   → retain assertion / regression test

概念辨析
--------

* **glGetError 与 Debug Callback**：前者只提供错误枚举，后者能提供更丰富的来源、类型、严重性和文本信息。
* **Object Label 与 Debug Group**：label 命名资源，group 命名一段命令范围。
* **Version 与 Extension**：version 表示核心能力基线，extension 提供额外能力；最终都要落到实际 function/limit 支持。
* **ARB/EXT/KHR 与 Vendor Extension**：前者标准化程度通常更高，vendor path 需要更明确的平台和 fallback 风险评估。
* **RenderDoc 与 GLIntercept**：前者偏单帧真实 pipeline state，后者偏 API 调用序列。
* **Texture Content 正确与 Sampling 正确**：资源中有正确像素，不代表 shader 绑定了正确 target、unit、sampler 和 layer。
* **State Leak 与 Resource Bug**：状态泄漏是上一 pass 的 context 状态影响当前 draw；资源 bug 则是资源自身内容或生命周期错误。

本章结论
--------

OpenGL 调试应按“Debug Signal—Pass/Resource Label—Frame Capture—Capability Profile—Minimal Repro”理解。黑屏先分类输出路径，错纹理同时查 resource identity 与 sample path，深度和 blend 则回到对应状态 contract。扩展能力必须在初始化时归一化成 feature profile，并让 shader、resource 和 binding 使用同一分支。真正稳定的 OpenGL renderer，不只是能修复一次错误，而是把同类错误固化为可观察消息、可验证状态契约和明确 fallback。