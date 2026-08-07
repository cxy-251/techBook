第129章：交互式可视化与 UX 设计
===============================

核心知识点
----------

交互式可视化需要统一 UI、Data、GPU 与 Frame Loop
   一次用户操作可能经过事件系统、状态机、异步数据加载、GPU upload、frame invalidation 和多视图联动。系统必须让这些阶段共享版本和可取消状态，否则容易出现旧数据覆盖、局部资源失配和视觉无反馈。

View State 与 Semantic State 是最重要的边界
   Camera、projection、slice plane、viewport 属于单个视图；timestep、selected region、threshold、focused variable 属于跨视图共享语义。多视图系统应共享后者、独立维护前者。

多视图联动应传递数据语义
   三维主视图、二维切片、曲线图使用不同坐标系，联动时应传 selected bounds、data IDs、time range、filter 等语义，而不是把一个视图的屏幕坐标直接传给另一个视图。

坐标映射必须完整可追踪
   Pointer screen position → viewport → ray/plane → world space → dataset coordinate/index 是 picking 与 selection 的基础。二维切片和三维视图若坐标链不一致，会出现高亮位置错位。

Action 层应高于原始事件
   Pointer down/move/up、wheel、slider input 应被转换成 ``BeginOrbit``、``UpdateBrush``、``CommitSlicePlane``、``PlayTimestep`` 等领域 action。渲染层只消费规约后的状态。

Versioning 能连接用户意图和可见帧
   可维护 inputVersion、semanticVersion、dataVersion、gpuVersion、frameVersion。它们分别说明输入、语义、CPU 数据、GPU 资源和屏幕反馈推进到了哪一版。

版本差可以直接定位同步问题
   UI 已变化但图像未变，先比较 semanticVersion 与 gpuVersion；GPU 已更新但屏幕仍旧，比较 gpuVersion 与 frameVersion；数据持续到达却交互卡顿，则看 upload bytes 与 inputVersion 推进速率。

异步任务必须支持 Cancel/Stale Guard
   用户快速切换时间步或 filter 时，旧任务应取消、降优先级或只进入缓存。任务完成后必须检查 target version，旧结果不能覆盖当前 semantic state。

GPU 资源更新应按 Transaction 发布
   Volume texture、selection mask、legend range、uniform 等若属于同一语义版本，应在准备完成后一起标记为新的 gpuVersion，避免半新半旧资源产生视觉撕裂。

Frame Invalidation 应表达“为什么需要重绘”
   ``dirtyCamera``、``dirtySelection``、``dirtyData``、``dirtyLayout`` 等原因让 scheduler 决定更新哪些 uniform、buffer、texture、label 和 pass，而不是每次状态变化都全量提交。

按需渲染适合分析工具
   静止且数据无变化时可以不提交新帧；camera 操作、动画播放、数据到达、渐进 refine 和 UI 状态变化时再 request frame。这样可降低无效 GPU 工作和功耗。

Preview 与 Commit 要分层
   Drag、brush、slider 拖动中使用低成本 preview；操作结束后再触发高质量统计、数据请求、重采样和精细渲染。用户首先获得控制感，然后获得精度。

多视图更新应基于 Dependency Graph
   Timestep 可能影响 volume、slice、chart 和 legend；camera orbit 只影响主视图；threshold 影响 transfer function、selection 和统计。明确依赖后，才能控制重算范围。

Link Policy 应可配置
   Selection linking、camera linking、time linking、filter linking、annotation linking 是不同关系。某个视图可以锁定 camera 或 slice，同时继续读取共享数据版本和错误状态。

锁定视图必须明确显示状态
   被锁定的切片视图可能不跟随某些联动，但仍属于同一 session。UI 应显示 lock、data version 和 partial/stale 状态，避免用户误以为所有视图完全同步。

多视图实时成本通常来自三类热点
   CPU 每次 pointer move 重算大统计，GPU 频繁上传整块 texture/buffer，UI 每帧重排大量 label。对应策略是 preview/commit 分离、range/tile upload 和 layout cache。

Loading、Error、Partial 与 Stale 都要显式反馈
   系统不能以“画面没变化”表达所有状态。用户需要知道数据正在更新、只有部分结果、当前仍是旧版本，还是任务真正失败。

UX 评价必须同时看任务与系统
   Task completion time、error rate、selection friction、undo/retry 次数属于任务指标；input-to-feedback latency、frame time、upload time、loading duration、stale frame count 属于系统指标。

可读性也是交互成本
   Contrast、label density、occlusion、legend clarity、selection visibility 决定用户是否能理解反馈。一个技术上 60 FPS 的视图若 selection 几乎看不见，仍然是低质量 UX。

关键路径
--------

一次语义更新：

::

   input event
   → domain action
   → semantic state version++
   → cancel obsolete work
   → load/compute new data
   → CPU data version
   → GPU resource transaction
   → gpuVersion++
   → invalidate affected views
   → render frame
   → frameVersion++

多视图联动：

::

   shared semantic state
   → dependency graph
   → main3d derived state
   → slice2d derived state
   → chart derived state
   → local camera/layout preserved
   → render each dirty view

UX 诊断：

::

   user task feels slow or confusing
   → split input / data / upload / frame latency
   → inspect stale/cancel events
   → inspect selection and link state
   → inspect readability/labels/legend
   → compare task time + error rate
   → reduce the dominant interaction cost

概念辨析
--------

* **View State 与 Semantic State**：view state 决定某个视图怎么观察，semantic state 决定整个 session 正在研究什么。
* **Data Version 与 GPU Version**：前者表示 CPU 数据已准备，后者表示 GPU 可供 shader 使用的资源已更新。
* **Dirty Flag 与 State Version**：dirty flag 描述需要重绘什么，version 描述数据/状态更新到了哪一版。
* **Cancel 与 Ignore Stale Result**：cancel 尽量停止旧任务，version guard 确保即使停止失败，旧结果也不能提交。
* **Link Policy 与 Shared State**：shared state 保存共同语义，link policy 决定哪些视图对哪些变化做响应。
* **Rendering Performance 与 UX Performance**：前者关注帧和 GPU 成本，后者还包含输入反馈、加载、可读性和任务完成效率。

本章结论
--------

交互式可视化应按“Action—View/Semantic State—Versioning—Async Data—GPU Transaction—Invalidation—Linked Views—UX Metrics”理解。高质量系统不是让所有视图每次都同步做完全部工作，而是让用户最新意图始终拥有最高优先级，让每一版数据与 GPU 资源可追踪，让 preview、partial、final 和 error 状态都清楚可见，并最终降低完成分析任务所需的时间和错误率。