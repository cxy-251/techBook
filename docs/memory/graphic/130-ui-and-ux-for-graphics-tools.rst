第130章：图形工具的 UI 与 UX
============================

核心知识点
----------

图形工具 UI 是渲染状态编辑器
   按钮、滑条、对象树、属性面板、viewport、timeline 和 HUD 并非独立界面，它们最终都会修改 tool state、resource、shader input、render target 或分析 pass。UI 设计必须和 frame loop、GPU upload、render graph、selection 与 undo 同时考虑。

主任务应形成最短闭环
   典型图形工具的主路径是“选择对象→修改参数→观察结果→比较/分析→提交或撤销”。对象树、viewport picking、inspector 和预览必须共享同一 selection state，避免用户在多个面板之间重复确认对象身份。

反馈应分成 Interaction、Render 与 Project State
   Hover/pressed/focus 说明输入已被接收；viewport 图像、progressive preview 说明渲染是否使用新状态；dirty/unsaved/undo entry 说明修改是否进入工程状态。三类反馈必须可区分。

连续参数应区分 Preview Value 与 Committed Value
   Roughness、曝光、阈值等滑条拖动时可每帧更新 preview，让 shader 实时响应；松手后再写入正式材质状态并生成一条 undo command。昂贵重建型参数应延迟提交或显式 Apply。

控件必须说明作用域
   ``Show Normals``、``Enable SSAO``、``Freeze TAA`` 可能只影响当前 viewport，也可能修改全局 render setting。UI 需要明确 ``Viewport Only``、``Current Material``、``Global``、``Debug Session`` 等语义。

颜色与曲线控件需要保留数值域
   Linear/sRGB、HDR range、alpha 语义、LUT coordinate、单位和 clamp 范围都应显示。UI 中“看起来相同的颜色”不一定对应相同 shader 输入。

Dock Layout 服务空间记忆
   常见结构是左侧对象/资源，右侧属性，中心 viewport，底部 timeline/log/profiler。布局和可见性可以持久化，但 hover、drag、selection draft 等临时交互状态不应写入长期配置。

图形工具需要更多状态标记
   除 idle/hover/active/disabled/error 外，还需要 loading、stale、dirty、out-of-sync。``stale`` 表示 UI 已变但当前 frame 尚未使用新资源；``out-of-sync`` 表示分析面板显示的是旧 capture 或旧 render target。

Immediate-Mode UI 适合调试工具
   Dear ImGui 一类系统每帧根据当前状态生成 draw data，宿主 renderer 再把 UI 当作普通 vertex/index/texture pass 提交。UI 库负责描述界面，不负责替代资源生命周期和渲染同步。

ImGui 接入应保持稳定数据路径
   Platform input → UI frame → tool state → draw data → UI render pass。Font atlas、texture id、clip rect、DPI、alpha blend、多 viewport 和 dock layout 都必须由宿主渲染器正确映射到 GPU 资源和 pipeline。

Input Routing 要区分 UI 与 Viewport
   当 UI 捕获 pointer/keyboard 时，相机和场景 picking 不应同时响应；当用户拖动 gizmo 时，输入应继续属于当前操作，即使指针已经离开 handle。输入归属是状态机问题，不是每帧重新 hit test。

Debug Control 与资产设置必须分离
   ``Show Albedo``、``Freeze TAA``、``Disable Bloom`` 属于观察或 preview override，不应静默写入最终资产。Debug session、preview override、saved setting 应使用不同状态与标记。

分析面板应暴露隐藏渲染状态
   Texture/G-buffer viewer、histogram、mip/UV density、overdraw、pass timing、shader variant、resource binding 和 action log 共同回答“这个像素为什么这样显示”。分析视图必须绑定当前 selection 和当前 frame/capture。

Readback 与 Capture 必须标记时间版本
   Histogram、纹理采样和 GPU capture 常晚于当前 frame。面板必须显示 frame id、resource version 或 capture id，防止用户把旧数据当作当前画面证据。

错误信息要直接支持修复
   Texture missing、format mismatch、shader compile failed、descriptor invalid、render-target size mismatch 等错误应包含对象、阶段、预期、实际值和可执行下一步，而不是只有内部错误码。

Selection Friction 是核心 UX 成本
   小对象、重叠、透明、gizmo 密集会提高命中成本；selection breadcrumb、hover outline、object id、层级过滤、锁定和 selection history 能降低歧义与确认成本。

编辑摩擦还包括等待和恢复
   一个操作可能触发 shader compile、texture upload 或 render graph rebuild。UI 应展示阶段、允许取消/撤销，并让用户知道当前看到的是 preview、stale 还是 final。

关键路径
--------

参数编辑：

::

   user input
   → UI widget active
   → preview tool state
   → dirty resource/pass
   → uniform/resource update
   → render frame
   → viewport/analysis feedback
   → commit
   → undo entry / save state

UI 渲染集成：

::

   platform events
   → input router
   → build UI frame
   → mutate tool state
   → produce UI draw data
   → scene/debug passes
   → UI pass
   → present

分析路径：

::

   visual anomaly
   → current selection
   → resource/pass viewer
   → shader/pipeline/binding
   → frame/capture version
   → error/action log
   → fix state or asset

概念辨析
--------

* **UI State 与 Render State**：UI state 描述控件和工具行为，render state 描述 GPU 如何产生当前 frame；二者通过明确的 dirty/update 路径连接。
* **Preview 与 Commit**：preview 服务实时观察，commit 才进入正式工程状态和撤销历史。
* **Debug Override 与 Saved Setting**：前者改变观察方式，后者改变最终资产或项目配置。
* **Immediate-Mode UI 与 Immediate GPU Rendering**：即时模式只描述 UI 构建方式，不代表 GPU 资源和命令可以无生命周期管理。
* **Selection State 与 Panel Focus**：selection 是工具语义对象，focus 只是当前输入落在哪个控件。
* **Analysis View 与 Final View**：分析视图暴露中间资源和证据，最终视图表达最终合成结果。

本章结论
--------

图形工具 UI/UX 应按“User Task—Selection/Tool State—Widget Edit—Resource/Pass Update—Visible Feedback—Analysis—Commit/Undo”理解。优秀工具的关键不是控件数量，而是让每次操作都能明确说明它修改了什么、GPU 何时使用新状态、当前画面是否可信、错误如何恢复，并让用户以最少选择和等待成本完成视觉判断。