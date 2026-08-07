第135章：视觉系统中的可访问性与可读性
====================================

核心知识点
----------

可访问性与可读性都服务稳定理解
   Accessibility 关注不同视觉能力、认知负荷和输入习惯下是否仍能完成任务；Readability 关注当前视口、距离、缩放、亮度和信息密度下读取内容的成本。二者最终都要落到 frame、overlay、label、legend 和交互状态上验证。

视觉编码应从用户任务反推
   先列任务，再列需要读取的数据字段，随后分配颜色、形状、大小、位置、透明度、线型和动画。一个视觉变量同时承担多个主语义会快速增加认知冲突。

视觉变量需要稳定分工
   连续量可用明度/色阶，类别可用形状或离散色相，selection 可用描边，方向可用箭头/运动，紧急状态可用图标与文本。复杂状态应组合编码，而不是反复覆盖同一颜色。

Shader 与 Legend 必须共享同一编码表
   数据 buffer → shader color mapping → overlay → legend/tooltip 必须引用同一 semantic configuration。两套颜色表会让画面和解释层产生语义漂移。

颜色不能成为唯一关键信号
   色弱、显示设备、HDR、透明混合和底图都会降低色相区分。关键状态应同时使用图标、线型、轮廓、文字、位置或数值。

对比度应在最终合成画面中检查
   设计稿里的文本和图标会经过场景背景、透明 overlay、tone mapping、color grading 和显示变换。真正要测的是 final composited frame 上关键前景与实际背景的可分性。

状态组合要分层编码
   一个道路对象可能同时拥堵、被选中、有事故、处于 hover。填充色表达数据值、外描边表达 selection、图标表达事故、tooltip 表达 hover，能避免不同 pass 争夺同一视觉通道。

Label 是渲染对象
   Label pass 需要 camera、screen anchor、depth、priority、minimum size、overlap budget 和 LOD。标签不是简单字符串绘制，而是需要随视图变化调度的屏幕资源。

标签要支持渐进退化
   缩小时从完整文字变成短编号、聚合计数或隐藏；放大后恢复详细字段。隐藏低优先级标签时，应通过 hover、搜索、列表或详情面板保留信息入口。

图例是视觉语义合同
   Legend 应展示字段名、单位、范围、离散级别、阈值、缺失值、时间范围和当前 filter。图例缺失或过期会让正确 shader 输出也失去可解释性。

认知负荷可通过视觉层级控制
   当前任务对象应最高显著，辅助信息降低饱和/透明度，背景保持低干扰。所有道路、标签、摄像头、告警和动画同时高亮会让用户把注意力浪费在筛选上。

动画只应用于真正需要时间信息的场景
   动画适合方向、状态变化和进行中任务，不适合作为永久分类标记。必须提供减少运动或关闭非必要动画的入口。

相机与导航的目标是保持方向感
   Camera position/orientation、FOV/zoom、clip range、north/orientation axis、scale indicator、current layer 与 reset view 共同帮助用户回答“我在哪里、看向哪里、尺度多大”。

无效视角应受约束
   相机进入模型内部、极端近远裁剪、过度旋转或尺度丢失会破坏可读性。编辑器应提供 framing、focus selected、reset view、2D/3D preset 和合理的 camera limits。

导航状态应可序列化
   Camera、layer、filter、time range、selection、encoding version、theme 等状态应能保存和分享。这样截图或问题链接才能真正复现同一视觉语境。

Explainable Feedback 要覆盖完整状态阶段
   可操作、已触发、处理中、已完成、失败、空结果、旧数据都应有明确视觉表达。``No results`` 与 ``Request failed`` 不能使用相同空白画面。

Hover、Selection、Loading、Error 与 Legend 应保持语义一致
   用户在任何位置看到的状态名、颜色、对象身份和数据版本都必须一致，否则系统会让用户重新猜测当前含义。

可读性审查应使用真实任务脚本
   例如“30 秒内找出最拥堵三条道路、确认事故并分享一条”。角色、目标、时间、输入、成功标准和输出动作明确后，才能判断编码、导航、label 和反馈是否有效。

关键路径
--------

视觉语义：

::

   user task
   → data fields
   → shared encoding table
   → GPU buffers / shader mapping
   → labels / legend / overlays
   → final composited frame
   → user judgement

导航与定位：

::

   input navigation
   → camera/view state
   → orientation + scale cues
   → label/LOD update
   → selection context preserved
   → serializable view state

可读性审查：

::

   task script
   → verify encoding redundancy
   → inspect final contrast
   → grayscale/color-vision check
   → test label overlap/LOD
   → test navigation recovery
   → test loading/error/empty states
   → measure task accuracy/time

概念辨析
--------

* **Accessibility 与 Readability**：前者保证不同用户仍能操作和理解，后者关注当前显示条件下读取信息的成本。
* **Color Encoding 与 Semantic Encoding**：颜色只是视觉通道之一，完整语义还需要形状、文字、位置和交互反馈。
* **Legend 与 Label**：legend 解释编码规则，label 标识具体对象或数值。
* **Contrast 与 Brightness**：对比关注前景与背景的可分性，不等同于简单提高整体亮度。
* **Camera Control 与 Orientation Support**：能移动相机不代表用户有方向感，还需要轴、比例尺、重置和上下文提示。
* **Empty State 与 Error State**：空结果说明查询成功但没有数据，错误说明结果不可信或流程失败。

本章结论
--------

视觉系统的可访问性与可读性应按“Task—Encoding—Contrast/Redundancy—Label/Legend—Navigation—Explainable Feedback—Review”理解。工程目标不是让所有元素都更显眼，而是让每个视觉通道承担明确语义，让最终合成画面在不同用户和视图条件下仍能被准确读取，并让用户始终知道当前视角、数据状态和操作结果代表什么。