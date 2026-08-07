第106章：Scriptable Render Pipelines
===================================

核心知识点
----------

SRP 把固定渲染黑盒改成可声明的 Pass 系统
   项目可以决定一帧包含哪些 pass、每个 pass 何时注入、读写哪些 texture/buffer、在哪些 camera 和 quality tier 下启用，再由底层渲染架构生成 GPU 命令。

可编程的核心是“Pass 组合与资源路径可控”
   新增 Outline、SSAO、SSR、debug view 等功能时，应拆成明确 pass，并让每个 pass 声明资源。效果异常时就能沿 producer→consumer 找到第一处错误，而不是在一个巨大 renderer 函数中猜状态。

Pipeline Asset 负责长期策略
   它适合保存默认 renderer、阴影配置、质量档位、后处理开关、debug 选项和平台 fallback。它回答“项目允许哪些路径”，不应该承担每帧大量动态工作。

Pipeline Instance 负责当前帧和 Camera 的渲染调度
   每个 camera 的 HDR、MSAA、viewport、stack、scene view/reflection 类型会决定 pass 列表。Camera 条件应在构图阶段决定 pass 是否存在，而不是把不需要的 pass 留着再靠 shader 分支跳过。

Renderer Feature 是功能级扩展入口
   一组自定义 pass 可以作为 feature 被注入某个 renderer/camera。Feature 负责轻量的 enable 判断与 pass 创建，真正的资源读写和 GPU 工作留给 pass。

Render Pass 是帧内最小执行单元
   一个稳定 pass 至少有 name、enable condition、resource declaration、execute/record 命令和 profiling marker。Pass 不应隐式访问图中未声明的资源。

Resource Graph 让资源生命周期成为可推导对象
   Pass 声明 read/write 后，图系统可以计算依赖、pass culling、load/store、barrier、transient lifetime、aliasing 和部分 pass merge。现代 SRP 的核心价值之一，就是把“记住谁还在用资源”交给显式图模型。

自定义 Render Pipeline 应先固定 Frame Context
   Frame context 应包含 camera、platform profile、quality tier、visible lists、shared resources、debug mode 和 profiling sink。所有 pass 都从同一份帧输入做决策，避免各自读取可变全局状态。

Pass Interface 应先声明，再执行
   构图阶段决定 pass 是否存在并声明资源；执行阶段只记录当前 pass 命令。这样 renderer 可以在 GPU 执行前完整知道一帧的资源依赖和开销结构。

Quality Tier 应改变 Pass 与 Resource，而不只是 Shader 参数
   低质量可以直接不创建 normal texture、不注入高成本 outline/SSR pass；高质量才增加额外 attachment、sample 和精细算法。真正关闭 pass 才能减少 CPU 构图、内存和 GPU 成本。

Pass Toggle 应分层
   Feature toggle 决定整组功能是否注入；pass toggle 用于定位链路；shader keyword 只改变 pass 内局部算法。越高层的 toggle 越适合性能控制，越低层越适合视觉调试。

Debug View 应读取真实生产资源
   Normal、depth、shadow、light list、G-buffer 等 debug view 应直接显示管线实际使用的资源，而不是另造一条调试数据路径。这样 debug view 同时验证资源 contract。

工具中的 Pass 名必须稳定
   ``SelectionMask``、``OutlineEdge``、``DeferredLighting`` 等名称应同时出现在源码、Render Graph Viewer/RDG Insights、GPU marker 与 profiler 中。匿名 fullscreen pass 会极大降低工程可观察性。

Unity SRP 与 Unreal RDG 的核心问题一致
   Unity 通过 C# Pipeline Asset、Renderer Feature、ScriptableRenderPass/Render Graph 暴露扩展；Unreal RDG 更靠近 C++ renderer、pass parameter struct、FRDGBuilder 与 RHI。语言和对象不同，核心仍是 pass declaration、resource lifetime、extension point 和 tool integration。

扩展点必须受资源和画质系统约束
   “可插拔”不等于任意时刻读写任意 render target。每个 extension 都必须说明注入点、输入输出、camera 条件、quality tier、fallback 和 profiling cost，否则插件越多，frame graph 越不可推理。

关键路径
--------

SRP Frame Build：

::

   camera data
   → pipeline asset / platform profile
   → quality tier
   → renderer features
   → enabled pass list
   → resource declarations
   → render graph compile
   → GPU command recording
   → execute / present

自定义 Outline：

::

   SelectionMask pass
   → SelectionMask texture
   → OutlineEdge reads mask + depth + optional normal
   → OutlineColor
   → OutlineComposite reads color + outline
   → CameraColor
   → debug/final output

调试与质量控制：

::

   feature toggle
   → pass toggle
   → resource graph view
   → debug resource view
   → GPU marker/timing
   → quality tier adjustment

概念辨析
--------

* **Pipeline Asset 与 Pipeline Instance**：asset 保存长期配置，instance 执行当前帧和 camera 的渲染逻辑。
* **Renderer Feature 与 Render Pass**：feature 是功能扩展入口，pass 是具体帧内 GPU 工作单元。
* **Pass Toggle 与 Shader Keyword**：前者可以真正移除 pass/resource，后者通常仍保留该 pass 的提交成本。
* **Resource Declaration 与 Resource Binding**：声明告诉图系统依赖关系，binding 是执行时把具体资源交给 shader/API。
* **Debug View 与 Debug Shader**：debug view 是整个管线的观察模式，debug shader 只是实现其中某个显示步骤的工具。
* **Unity SRP 与 Unreal RDG**：二者 API/语言不同，但都把现代 renderer 建模为 pass、resource 和图执行关系。

本章结论
--------

SRP 应按“Pipeline Policy—Camera/Quality—Feature—Pass—Resource Graph—Tooling”理解。新增效果先定义注入点和资源 contract，再决定 tier、toggle 和 debug view，最后才写 GPU 命令。真正可维护的可编程管线，不是允许项目随意插代码，而是让每个扩展都能说明它为什么存在、读写什么、在哪些 camera/平台执行、成本是多少以及如何被工具定位。