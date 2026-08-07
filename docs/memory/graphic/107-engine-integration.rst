第107章：引擎集成
================

核心知识点
----------

引擎集成解决的是“持续变化的世界如何变成稳定的一帧”
   脚本、动画、物理、资源流式、场景、相机和平台后端都在更新；renderer 需要把这些变化收敛成一个只读、可提交、可调试的 frame snapshot，再生成 visibility、render queue、frame graph 和 GPU commands。

Frame Boundary 是模块协调的第一条规则
   必须明确哪些 simulation/script/animation/physics 结果进入当前 render frame，哪些变化延迟到下一帧。没有固定边界，render queue 会读到半更新对象，工具也无法复现当时世界状态。

Render Snapshot 是游戏状态与渲染状态之间的隔离层
   Snapshot 应包含 transform、bounds、mesh/material handle、light、camera、visibility flags、animation/skinning data、debug tag 等渲染事实。渲染线程读取快照，而不是直接追逐可变 gameplay object。

Simulation Frame、Render Frame 与 GPU Frame 要可追踪
   三个时间编号可以解释“数据晚一帧”“资源早释放”“GPU 仍读旧 buffer”等跨线程问题。日志和 capture 应能把 object/resource 追溯到对应 simulation/render/GPU timeline。

对象身份必须跨模块稳定
   Scene entity、render object ID、asset GUID、material variant、pass/debug name 应建立可追踪关系。GPU capture 中的一条 draw 应能回到具体引擎对象，而不是停留在匿名 buffer/descriptor。

Asset 生命周期分成离线数据、运行时句柄和 GPU Resident Resource
   Import 生成平台资源与 metadata；runtime handle 表示引用和 streaming state；GPU resource 只有上传完成并经过正确同步后才能被 shader 读取。三个层级不能用同一“加载完成”状态代替。

Resource Ready 与 Resource Target 是两种状态
   Streaming 系统可以目标是高 mip/高 LOD，但 renderer 当前帧必须选择已经 ready 的低 mip、低 LOD 或 fallback material。渲染稳定性优先于等待目标质量资源。

GPU Resource 释放必须经过 Retire Pending
   CPU 不再引用资源不代表 GPU 已经完成。Texture、buffer、descriptor、bind group、pipeline 等只有在所有 in-flight frame/fence 证明不再使用后才能真正销毁。

Render Queue 应保存稳定的提交材料
   Draw item 至少应包含 object ID、pass mask、mesh/submesh、material/pipeline key、resource binding/version、transform、bounds、sort key 和 debug labels。Command building 不应回到可变 asset/world 对象重新查询。

Scene Graph 到 GPU 的主路径应分层
   ``scene graph → visibility → LOD → material system → render queue → frame graph → backend``。每一层都转换数据并留下证据。某对象不投阴影时，可以从 shadow flag、shadow visibility、LOD、pass mask 逐层排查。

Visibility 与 LOD 必须同时考虑 Streaming Readiness
   理论上应切换到高 LOD 不代表对应 mesh/texture 已 resident。LOD 选择应基于屏幕误差、质量档位和可用资源共同决定，避免切到尚未准备好的资源造成闪烁或 stall。

多线程的前提是输入固定、输出独立、依赖可表达
   Animation、streaming、culling、LOD、render queue building、command recording 可以并行，但每个 job 应读取稳定输入并写线程独占区域。共享可变 renderer state 会把并行变成锁和 race。

CPU Job Graph 与 GPU Frame Graph 是两张不同的依赖图
   CPU graph 表示 animation/culling/upload/command building 谁等待谁；GPU graph 表示 graphics/compute/copy pass 之间的资源依赖。二者在 upload、command submit 和 frame fence 处连接，但不能混成一层。

Async Compute 只有真正重叠才有收益
   SSAO、light culling、particle 等 compute pass 如果仍被 depth 或 resource dependency 强制排在 graphics 后面，或者占用了同一硬件资源导致竞争，就不会获得理论并行收益。必须通过 queue timeline 证明 overlap。

Frame-Ring 资源必须跟 GPU Completion 对齐
   Per-frame constant、upload ring、transient descriptor、command allocator 和 snapshot 常按 N 帧轮转。CPU 只有在对应 GPU frame 完成后才能覆盖 slot；ring 太少会等待，太多会增加内存与延迟。

质量评估应同时覆盖图像与工程结果
   除平均 FPS 外，还要检查 P95/P99 frame time、GPU pass、内存峰值、streaming hitch、资源错误、同步安全、透明/阴影/LOD 视觉契约、debug 工具可观察性和不同平台 fallback。

关键路径
--------

引擎到渲染：

::

   script / animation / physics / asset streaming
   → commit simulation state
   → build immutable render snapshot
   → visibility / LOD
   → material + resource readiness
   → render queues
   → frame graph
   → backend command recording
   → GPU submit
   → fence / present

资源 Streaming：

::

   imported asset
   → runtime handle
   → target quality request
   → upload queued
   → staging/copy
   → GPU completion / state transition
   → Resident version published
   → future render queue binds new version
   → old version RetirePending
   → release after GPU fences

多线程 Frame：

::

   stable frame inputs
   → parallel animation / streaming / culling jobs
   → visibility + LOD ready
   → parallel render queue / command building
   → resolve GPU pass dependencies
   → submit copy / compute / graphics
   → frame fence
   → recycle per-frame resources

质量排查：

::

   visual contract failure or frame spike
   → object/resource identity
   → simulation/render frame versions
   → visibility / LOD / resource readiness
   → render queue / pass mask
   → frame graph / resource state
   → CPU job timeline + GPU queue timeline
   → memory / fence / fallback evidence

概念辨析
--------

* **Game Object 与 Render Snapshot**：前者持续变化，后者是某个 render frame 可安全读取的只读渲染事实。
* **Asset Ready 与 GPU Resident**：资产数据可用不代表 GPU 上传、同步和绑定已经完成。
* **CPU Reference 与 GPU Lifetime**：CPU 引用计数只能管理主机对象，GPU 是否仍在使用必须由 frame/fence 等完成证据判断。
* **Scene Graph 与 Render Queue**：scene graph 表达世界组织，render queue 表达当前 camera/pass 真正准备提交的 draw 集合。
* **Job Dependency 与 Resource Barrier**：前者约束 CPU 任务，后者约束 GPU 资源访问；属于不同执行层。
* **Async Compute 与 多线程 CPU**：一个是 GPU queue/硬件执行重叠，一个是 CPU job 并行，二者不能互相替代。
* **Target Quality 与 Available Quality**：目标质量指导 streaming，当前帧只能消费已经 ready 的资源质量。

本章结论
--------

引擎集成应按“World State—Frame Boundary—Render Snapshot—Visibility/LOD—Resource Readiness—Render Queue—Frame Graph—GPU Timeline”理解。随机画面错误先查版本、生命周期和 pass mask，streaming 闪烁查 ready/target 资源切换，帧尖峰同时看 CPU job graph 与 GPU queue timeline。稳定引擎 renderer 的核心，是让每个跨模块数据何时提交、谁拥有、哪个 frame 使用、什么时候 GPU 完成以及失败时使用什么 fallback 都有明确契约。