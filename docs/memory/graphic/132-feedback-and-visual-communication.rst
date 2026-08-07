第132章：反馈与视觉沟通
======================

核心知识点
----------

反馈系统要解释“系统现在处于什么状态”
   Selection、loading、progressive quality、error、performance HUD 都来自不同数据路径。反馈的目标不是增加提示，而是让用户知道操作是否命中、资源是否完整、当前画面是否可信、错误能否恢复。

第一次可见反馈应尽可能轻
   点击对象后，outline、bounding box、gizmo 或面板标题可以先出现，不必等待材质、阴影和高分辨率纹理全部就绪。用户首先需要确认“操作被接收”。

Progress State 要区分确定进度与不确定等待
   可枚举 texture/shader/mesh 阶段适合百分比和阶段数；网络响应、驱动编译、GPU fence 等不可预测任务适合 busy state、任务名和取消/超时入口。

错误反馈必须绑定工程对象
   Texture missing 应指向 material slot/asset；shader compile failure 应指向 variant/stage/log；device lost 应指向 frame/device recovery。错误信息要同时说明影响范围和 fallback。

可恢复错误应允许继续工作
   Fallback texture、fallback shader、低质量 preview 可以保持工具可用，但 UI 必须显式标出“当前结果已降级”，避免用户把近似结果当最终结果。

反馈状态应形成状态机
   Idle → HitPending → SelectionVisible → AssetLoading → ProgressivePreview → FinalQuality，并允许进入 RecoverableError/Cancel。状态边界比“显示哪个 spinner”更重要。

颜色只应承担有限主语义
   Selection、warning、error、success、loading 不应争用同一颜色。状态还应辅以形状、位置、文字、图标或轮廓，避免只靠颜色区分。

场景内反馈应与材质分离
   Selection highlight、error marker 更适合 ID/stencil/outline/overlay pass，而不是直接修改物体材质，否则会污染用户对真实材质的判断。

Motion 适合表达变化和进行中状态
   Outline fade、吸附动画、progressive denoise 可以帮助理解状态推进；持续闪烁和装饰动画会争夺注意力，还会增加 GPU/UI composite 成本。

减少运动偏好应被支持
   非必要动画应允许关闭或简化。视觉沟通的核心信息必须在无动画情况下仍然成立。

实时提示应对应渲染管线阶段
   Parsing、GPU buffer creation、texture upload、shader compile、preview ready、final material ready 应是不同提示阶段。这样进度 UI 本身就能帮助定位资源瓶颈。

Progressive Quality 要说明可信边界
   ``geometry ready / materials partial / reflection pending`` 比单一“73%”更有解释力。用户需要知道当前可以判断什么、哪些部分还会变化。

Selection Feedback 应共享统一 Selection Model
   Viewport outline、outliner、inspector、gizmo、breadcrumb 必须显示同一对象身份。反馈不一致往往比命中失败更难理解。

Performance HUD 应解释 Frame
   CPU frame、GPU frame、present/wait、draw/dispatch、memory、shader compile、upload queue、pass timing 应组合显示。HUD 需要帮助区分 CPU、GPU、资源和呈现瓶颈。

用户研究应围绕具体任务
   “加载模型并确认材质完整性”“找出最慢 pass”“处理 texture missing 并导出诊断”等任务应有明确起点、结束条件和成功标准。

UX 指标应与渲染证据关联
   Task time、error rate、first feedback latency、first usable preview、final quality time、confusion point、subjective workload 应能回到当时的 frame/pass/resource/selection 状态。

可用性需同时衡量 Effectiveness、Efficiency、Clarity 与 Recoverability
   能否完成任务、完成多快、是否理解当前状态、出错后能否恢复，共同定义渲染工具的实际可用性。

关键路径
--------

反馈链：

::

   user action
   → engine state mutation
   → feedback model
   → selection/loading/error/performance state
   → UI/overlay pass
   → visible frame
   → metrics log

渐进质量：

::

   asset/resource request
   → coarse resource ready
   → usable preview
   → missing/pending status shown
   → additional resources/quality converge
   → final quality

错误恢复：

::

   failure detected
   → bind error to object/stage
   → show impact + fallback
   → retry / disable / reload / export diagnostics
   → keep current session usable when possible

概念辨析
--------

* **Feedback 与 Decoration**：feedback 解释操作或系统状态，decoration 只改善视觉外观。
* **First Feedback 与 Final Quality**：前者确认输入被接收，后者说明完整渲染结果已经收敛。
* **Loading 与 Error**：loading 表示结果尚未准备，error 表示正常路径失败；二者不能共用模糊状态。
* **Fallback 与 Success**：fallback 允许继续工作，但不等于理想路径成功。
* **Selection Highlight 与 Material Change**：highlight 是交互状态表达，material change 是场景内容修改。
* **Performance HUD 与 Profiler**：HUD 提供实时方向性证据，profiler 用于深入定位具体 CPU/GPU 原因。

本章结论
--------

视觉反馈应按“Action—System State—Feedback State—Overlay/UI—Frame—Metric”理解。可靠反馈会尽早确认输入、明确区分 loading/partial/final/error、把错误绑定到可修复对象，并让颜色、运动、文本和 HUD 服务同一状态语义。反馈的价值最终应由任务完成时间、错误率、理解成本和恢复效率证明。