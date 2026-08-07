第131章：实时交互模式
====================

核心知识点
----------

实时交互是一条闭环
   Input Event → Intent → Interaction State → Dirty Flags → Render Scheduling → Frame Output → Visual Feedback。用户动作只有进入这条链并在后续帧可见，才算完成。

原始事件与用户意图必须分离
   Pointer move、wheel、key down 是设备事件；Translate X、Orbit Camera、Brush Select、Edit Property 才是工具意图。拖拽开始后，即使光标离开原始 handle，当前意图仍应保持稳定。

Pointer Capture 的本质是保持操作所有权
   按下 gizmo、slider、timeline 后，后续 move/up 应继续归属于已建立的交互会话，直到 commit/cancel。不能每帧根据当前命中对象重新决定操作对象。

Preview 与 Commit 应分层
   拖拽期间修改 preview transform，让 viewport、gizmo 和属性面板及时响应；松手时再生成单条语义化 undo command。这样历史记录不会被高频 pointer sample 污染。

共享编辑状态与 View State 应分离
   Object transform、selection、active tool、snap mode 属于共享编辑状态；camera、zoom、grid、overlay 属于单个 viewport；输入框临时文本和 focus 属于 UI local state。

多视图通过共享状态同步，不应互相调用
   透视视口、正交视口、属性面板和预览视图都读取同一 scene/tool state。一个视口发起修改后，其他视图订阅状态结果，而不是形成双向调用链。

状态消息可以分为 PreviewChanged、Committed、ResourceSettled
   PreviewChanged 服务拖拽和即时反馈；Committed 进入 undo、保存和依赖更新；ResourceSettled 表示异步 texture/shader/preview 已完成并可替换占位结果。

事件频率与渲染频率应解耦
   Pointer 事件可能一帧多次到达，render loop 只应消费当前最新状态。输入层可以保留高频采样，但昂贵状态更新、resource rebuild 和 GPU submission 要在帧边界合并。

Dirty Flag 决定最小更新范围
   ``interaction-overlay``、``scene-transform``、``resource-preview``、``camera`` 等标志让 scheduler 只执行相关 pass。Hover 不应触发整套阴影、GI 或材质重建。

交互期与静止期应采用不同质量策略
   Drag/rotate 时优先更新对象代理、gizmo、outline、HUD 和主视图；高成本阴影、SSR、path tracing、体渲染高采样可暂时降级。输入停止后再恢复高质量结果。

响应优化首先缩短关键反馈链
   用户继续操作所依赖的反馈优先级最高，例如 gizmo 位置、当前数值、selection 和 camera。不会影响下一步操作的高质量结果可以延后。

昂贵工作要分帧或异步
   Shader compile、texture load、BVH rebuild、thumbnail、global illumination 等应进入 worker/后台队列，并通过 generation/version 保证旧任务不能覆盖当前状态。

取消是交互协议的一部分
   Esc、selection change 或新一轮拖拽都可能使旧操作失效。Cancel 必须恢复起始 transform、清理 active tool、取消 overlay，并使未完成资源任务失去提交资格。

命中测试需要分层
   框选和 gizmo 可先用屏幕空间 bounds/proxy 粗筛，再对候选集合做精确 mesh/depth test。大型编辑器可维护交互专用 acceleration structure。

多 Viewport 还要处理 DPI 与坐标系统
   OS window、UI logical coordinate、framebuffer pixel、viewport/scissor 和 camera projection 必须有清楚映射。多屏、多 DPI 和 dock 窗口会放大输入错位风险。

高级编辑操作应统一进入 Command 模型
   Box selection、gizmo transform、属性编辑、批量修改、undo/redo 都应最终形成语义 command。Command 保存作用对象、before/after state、selection policy 和依赖更新信息。

实时交互性能应看尾部稳定性
   平均 FPS 合格仍可能出现拖拽尖峰。需要记录 input-to-feedback、CPU update、GPU frame、P95/P99、resource stall 和 dropped frame，定位哪类操作破坏连续性。

关键路径
--------

拖拽操作：

::

   pointer down
   → hit tool handle
   → capture interaction
   → store start state
   → pointer move samples
   → preview transform
   → dirty affected views
   → render feedback
   → pointer up
   → commit command
   → undo stack + refine render

多视图同步：

::

   one view changes shared scene state
   → scene/tool store publishes change
   → each viewport derives local camera/render data
   → property panel derives numeric state
   → dirty scheduler updates affected outputs

取消/异步：

::

   interaction generation N
   → background resource/refine work
   → new interaction generation N+1
   → cancel or invalidate N
   → accept only current generation result

概念辨析
--------

* **Input Event 与 Interaction Intent**：event 是设备采样，intent 是工具解释后的语义操作。
* **Preview State 与 Committed State**：preview 服务连续反馈，committed state 才进入 undo、save 和稳定依赖。
* **Shared State 与 View State**：前者描述场景/选择事实，后者只描述某个视图如何观察。
* **Dirty Flag 与 Immediate Render**：dirty 表示哪些结果失效，不代表事件回调里立即完整渲染。
* **Pointer Capture 与 Picking**：capture 保持已开始操作的输入所有权，picking 用于决定操作开始时命中谁。
* **Average FPS 与 Interaction Stability**：平均吞吐不能替代单次输入延迟和 P95/P99 卡顿观察。

本章结论
--------

实时交互应按“Event—Intent—State Machine—Preview—Dirty Scheduling—Frame Feedback—Commit/Cancel”理解。高质量交互系统不会让每个输入事件直接驱动整套渲染，而是保持操作所有权、合并高频输入、优先输出用户下一步操作所需的反馈，并把昂贵资源与高质量 pass 放到可取消、可版本化的后续路径中。