第082章：OpenGL Pipeline 到 Workflow 的映射
===========================================

核心知识点
----------

OpenGL 的 Draw Call 只是 Pipeline 触发器
   一次 ``glDrawElements`` 会消费已经准备好的 VAO、program、texture、sampler、UBO、FBO、viewport、depth/blend/cull 等状态。工程上应把“draw 前状态声明”视为 draw 本身的一部分，而不是分散到不相关模块。

Pipeline 阶段都能映射到具体 OpenGL 状态
   Vertex input 由 VAO/VBO/IBO 和 attribute format 决定；vertex shader 由 program、uniform、UBO 决定；primitive assembly 与 rasterization 受 primitive mode、cull、viewport、scissor 影响；fragment shader 读取 texture/sampler/varying；最终输出由 depth、stencil、blend、color mask、draw buffers 和 FBO 决定。

Pass State、Material State、Geometry State 与 Resource State 应分层
   Pass 负责 FBO、viewport、clear、depth/stencil/blend；material 负责 program、textures、samplers 和材质级状态；geometry 负责 VAO、index buffer 和 primitive；resource binder 负责 UBO/SSBO/texture/image binding。分层后，状态依赖才能从源码调用序列变成可审计数据。

State Machine 的持续性是状态污染根源
   ``glEnable``、``glBind*``、``glViewport`` 等调用会持续生效，直到显式修改。Shadow pass 留下 1024×1024 viewport、UI pass 留下 blend、透明 pass 留下 depth mask，都可能直接污染后续 draw。

Core Profile 更适合建立现代 Workflow
   Compatibility profile 中固定功能矩阵、立即模式、client array 等历史路径会引入额外隐式状态。现代 workflow 应围绕 VAO、buffer、GLSL program、UBO、texture/sampler、FBO 和 debug output 组织。

GLSL 工作流应区分 Compile、Link、Binding、Execution
   Shader source 编译成功只说明单个 stage 合法；program link 还要验证 stage interface；运行时 binding 要确保 attribute location、UBO binding、sampler unit 与 OpenGL 状态一致；最终 execution 再受 FBO、depth/blend 等外部状态影响。

Shader Interface 应尽量显式化
   使用明确 attribute location、uniform block binding、fragment output location 和 sampler binding，可以减少运行时查询与错配。Program introspection 适合验证最终 link 后接口是否与引擎约定一致。

调试 Render State 应从输出端向输入端收缩
   先检查 FBO、viewport、scissor、draw buffer，再看 depth/stencil/blend/color mask；随后用常量 fragment shader 验证 rasterization；再查 VAO、attribute、index；最后恢复 texture/sampler。这样能区分“没画”“画了但被测试丢弃”“画到错误目标”“输入资源错”。

Debug Callback、State Dump、Frame Capture 与 Minimal Repro 各自回答不同问题
   Callback 给 driver 错误信号，state dump 记录应用认为的当前状态，RenderDoc 展开捕获 draw 的真实 pipeline state，minimal repro 用来判断问题是否来自引擎状态复用和资源生命周期。

State Cache 的目标是减少重复提交，同时收束状态入口
   Cache 可以跳过重复的 ``glUseProgram``、``glBindVertexArray``、texture 和 FBO 绑定。前提是所有状态修改都必须经过同一 backend；若 utility code 绕过 cache 直接调用 GL，缓存与真实 context 会分裂。

Draw Sorting 必须先满足视觉约束
   不透明 draw 可以按 pass/FBO、program、depth/blend state、texture set、VAO/material 排序以提高 state locality；透明 draw 仍需优先满足混合顺序。减少状态切换不能破坏透明和资源依赖正确性。

性能判断要区分 CPU Submit 与 GPU Work
   Program/texture/FBO/VAO 切换多主要影响 CPU/driver validation；fragment shader、overdraw、texture bandwidth 和 render target bandwidth 则是 GPU 成本。若 GPU fragment 已是主瓶颈，继续减少状态切换不会显著降低帧时间。

关键路径
--------

一次不透明 Mesh Draw：

::

   pass state: FBO / viewport / depth / blend
   → material: program / textures / samplers
   → resources: UBO / SSBO bindings
   → geometry: VAO / IBO / primitive
   → glDrawElements
   → vertex shader
   → primitive assembly / clipping
   → rasterization
   → fragment shader
   → depth / stencil / blend
   → color + depth attachments

状态污染排查：

::

   FBO / draw buffers
   → viewport / scissor
   → depth / stencil / blend / color mask
   → constant-color fragment shader
   → VAO / vertex / index input
   → texture unit / sampler / format / mip
   → previous pass state owner

性能组织：

::

   collect draw items
   → group by pass / output target
   → preserve transparency constraints
   → sort by program / material / texture / VAO
   → state cache emits minimal changes
   → debug markers
   → CPU submit + GPU timing validation

概念辨析
--------

* **Pipeline Stage 与 OpenGL Object**：一个阶段可能由多个对象和全局状态共同决定，并非一阶段对应一个对象。
* **Pass State 与 Material State**：pass 决定输出与测试规则，material 决定 shader 与材质资源。
* **Compile Error 与 Link Error**：前者属于单个 shader，后者属于多个 stage 接口组合。
* **Shader 合法与 Draw 正确**：program 可成功 link，仍可能因为 VAO、sampler、FBO 或 depth/blend 状态错误而画错。
* **State Cache 与 State Contract**：cache 负责减少重复调用，contract 负责定义每个 pass 必须声明哪些状态。
* **Batching 与 Sorting**：batching 合并工作单元，sorting 只重排 draw；两者都受透明、资源依赖和剔除粒度约束。
* **CPU Submit Cost 与 GPU Shader Cost**：前者由 API/driver 状态与 draw 数决定，后者由真实 GPU 工作量决定。

本章结论
--------

OpenGL workflow 应按“Pass 声明状态—Material/Geometry/Resource 绑定—Draw 触发—Pipeline 执行—状态证据—批次优化”理解。遇到异常先从输出目标和 per-sample state 排查，再逐步回到 shader 与资源输入；遇到 CPU 提交瓶颈则用 draw sorting 和 state cache 收束冗余调用。真正可维护的 OpenGL 渲染器，不依赖调用者记住上一段代码留下了什么，而是让每个 draw 所需状态在 pass、material、geometry 和 resource contract 中明确可追踪。