第081章：OpenGL 状态机与 Context 生命周期
==========================================

核心知识点
----------

OpenGL 的核心执行模型是 Current Context 中的持续状态
   ``glDraw*`` 并不携带完整 pipeline 描述，而是在执行时读取当前 context 中的 program、VAO、buffer、texture unit、sampler、framebuffer、viewport、depth/blend/cull 等状态。画面错误经常来自某个状态被上一段代码或上一帧留下。

Context 是 OpenGL 状态机的承载边界
   OpenGL 命令只作用于当前线程中已经 ``make current`` 的 context。一个 context 保存当前绑定、enable flag、错误状态、debug 配置和对象命名空间。Context 未 current 时调用 GL，或者在错误线程使用 context，都是生命周期错误而不是 shader 错误。

稳定初始化顺序必须固定
   典型顺序是“窗口/像素格式 → 创建 context → make current → 加载函数入口 → 查询实际版本与扩展 → 注册 debug callback → 创建资源 → draw → swap”。GLAD/GLEW 等 loader 依赖当前 context 暴露的入口，不能放在 make current 之前。

OpenGL 状态可拆成四层
   Context 级状态包括 current context、debug output 和默认 framebuffer；对象状态包括 buffer storage、texture storage、program link、FBO attachment；绑定状态包括当前 VAO、program、texture unit、draw framebuffer；pipeline flag 包括 depth、blend、cull、viewport、scissor、color mask。Draw 正确依赖四层同时匹配。

VAO 是 Core Profile 顶点输入的关键对象
   VAO 保存 attribute 的 enable、format、stride、offset 和 buffer 来源。Core profile 中未创建或绑定 VAO 就设置 attribute，是最典型的“窗口可 clear、shader 可 link、但三角形不出现”问题。

Program 只负责选择已链接 Shader 管线
   ``glUseProgram`` 选择当前 program，program 必须先完成 compile/link。Attribute、uniform、UBO、sampler 等接口仍需要与 VAO、buffer binding、texture unit 对齐。Shader 合法不等于 draw state 完整。

Texture Sampling 存在多层间接关系
   Sampler uniform 保存 texture unit 编号，texture unit 绑定 texture object，sampler object 决定过滤与 wrap。材质串图、全黑或采样旧纹理时，应同时检查 uniform 值、unit、target、texture object 和 sampler，而不是只看纹理内容。

Framebuffer 决定 Draw 的输出位置
   名称 0 通常表示窗口系统提供的默认 framebuffer；FBO 可以把输出写入离屏 texture/renderbuffer。Draw 本身完全正确但屏幕黑色时，应先确认当前 draw framebuffer、viewport、draw buffer 与后续呈现路径。

Core Profile 与 Compatibility Profile 是重要兼容边界
   Core profile 强制现代对象化路径，旧立即模式、固定功能矩阵栈和客户端数组不再属于核心语义；compatibility profile 保留大量历史状态。新工程应优先固定 core profile，旧工程迁移时先识别依赖的 compatibility 行为。

运行时能力必须查询，不能假设
   请求 OpenGL 4.x 不代表一定得到目标能力。启动后应记录实际 version、profile、vendor、renderer、extension 和关键 limits，并生成 renderer capability profile。可选能力缺失时走 fallback，必需能力缺失时应直接拒绝启动目标路径。

Debug Context 应成为开发期默认入口
   ``GL_DEBUG_OUTPUT``、``glDebugMessageCallback``、object label 与 debug group 可以把驱动错误、未定义行为和性能提示绑定到具体 pass 与资源。它们回答“GL 如何解释当前命令”，不能替代应用对高层渲染意图的验证。

关键路径
--------

OpenGL 初始化与提交：

::

   window / pixel format
   → create context
   → make current
   → load GL entry points
   → query version / profile / extensions
   → enable debug output
   → create VAO / VBO / program / textures / FBO
   → declare draw state
   → glDraw*
   → framebuffer
   → swap / present

一次 Draw 的状态读取：

::

   current context
   → current framebuffer + viewport
   → current program
   → current VAO / buffers
   → uniform / texture unit / sampler
   → depth / stencil / cull / blend / masks
   → draw
   → fragment output

黑屏排查：

::

   context current / loader
   → framebuffer / viewport
   → program link / use
   → VAO / attributes / VBO / IBO
   → uniforms / texture units / samplers
   → depth / cull / blend / color mask
   → swap path

概念辨析
--------

* **Context 与 Window**：window/surface 由平台层创建，context 承载 OpenGL 状态；二者相关但不是同一个对象。
* **Object State 与 Binding State**：对象状态描述资源自身，binding state 描述当前 draw 使用哪个资源。
* **Core 与 Compatibility**：core 约束现代对象路径，compatibility 保留旧固定功能与历史接口。
* **VAO 与 VBO**：VBO 保存字节数据，VAO 保存顶点属性如何解释这些数据。
* **Program 与 Shader**：shader object 先编译，program 负责链接多个 stage 并成为 draw 时可选执行单元。
* **Texture 与 Texture Unit**：texture 是资源，texture unit 是当前 context 的采样绑定槽位。
* **Default Framebuffer 与 FBO**：前者连接窗口系统呈现，后者是应用创建的离屏输出对象。
* **Version 与 Capability**：版本只提供能力上界线索，实际可用路径仍需查询 extension、function entry 和 limits。

本章结论
--------

OpenGL 应按“Context 生命周期—持续状态—对象/绑定—Draw 触发—Framebuffer 输出”理解。窗口能打开并不代表 context 路径正确，shader 能 link 也不代表 draw state 完整。遇到黑屏或随机状态问题时，先确认 current context、framebuffer 和 viewport，再检查 program、VAO、资源绑定和 pipeline flag；平台差异则统一收敛到 capability profile 与 fallback。OpenGL 的难点不在某个函数，而在 draw 时是否能重建出一份完整、一致、可验证的当前状态组合。