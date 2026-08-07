第128章：交互模型
================

核心知识点
----------

交互模型的核心产物是 Interaction State
   Pointer、keyboard、wheel、touch 等原始事件只是输入；系统真正需要维护的是 hover、selection、drag、camera、loading、error、undo 等稳定状态。渲染器读取 state，而不是直接处理设备事件。

交互的基本闭环是 Event → State → Query/Camera → Resource Diff → Render → Feedback
   每次操作都应能追踪到状态修改、数据查询、GPU 上传和可见反馈。只有这条因果链完整，交互错误和延迟才能被定位。

Hover 与 Selection 是不同语义
   Hover 是临时命中和轻量反馈，Selection 是可持久保存的数据集合，通常会影响过滤、统计和多视图联动。把二者混用会导致过多重计算或状态不稳定。

Drag 应建模为操作会话
   Pointer down、move、up 对应 begin/update/commit。拖动中使用 draft state 保证跟手，结束后再把最终范围提交为正式语义状态并触发重计算。

View State 与 Semantic State 应分离
   Camera、zoom、viewport 属于某个视图；selected IDs、time range、threshold 等属于跨视图的数据语义。一个视图移动相机不应无意改变其他视图的数据筛选。

反馈延迟需要按交互类型分预算
   Hover 和 drag overlay 需要接近即时反馈；selection 提交、数据查询和 tile/LOD refinement 可以更慢，但必须显示 loading 或 progressive result。所有操作都用同一延迟策略会破坏体验。

即时反馈和最终结果应分阶段
   Brush dragging 时先更新选择框和局部高亮，commit 后再执行过滤、统计和 GPU selection buffer 上传。重型操作可以先返回粗略结果，再逐步细化。

Event Normalization 降低设备差异
   鼠标、触摸、笔和键盘应先被转换成统一意图，例如 pan、zoom、hover、select、cancel。设备特有属性只在确实需要时进入上层语义。

事件频率和渲染频率应解耦
   Pointer move 可能高于显示刷新率。事件处理只修改 state 与 dirty flags，真正绘制由 frame scheduler 合并到下一帧执行，避免每个输入事件都直接提交 GPU 工作。

Dirty Flag 决定最小必要更新
   ``overlay``、``camera``、``selectionBuffer``、``dataQuery``、``layout`` 等标志帮助调度器只更新受影响资源和 pass。全量重绘和全量上传应是最后选择。

Debounce 适合压缩昂贵重计算
   高频拖动只更新 preview，用户停下或 commit 后再执行远程查询、统计、LOD rebuild 等昂贵工作。Debounce 不能用于需要连续跟手的 camera/overlay 反馈。

Incremental Redraw 控制局部变化成本
   Hover 只改 overlay，camera 只改矩阵和可见性，selection 只更新相关 buffer，数据版本变化才重建大资源。交互系统需要明确每类 state 对哪些 GPU 资源有依赖。

异步结果必须有版本或 Token Guard
   用户连续操作时，旧查询可能晚于新查询返回。只有与当前 state token/version 匹配的结果才能更新可见视图；旧结果可以缓存，但不能覆盖用户最新意图。

多视图联动应共享数据语义，不共享屏幕坐标
   时间轴、热力图、三维流线视图使用不同坐标系，但可以共享 selected IDs、time range、spatial bounds 和 filter。联动中心应是 shared selection model。

Highlight 与 Filter 必须分开
   Highlight 只改变颜色、描边或透明度，通常不改变数据集合；Filter 会改变统计、LOD、GPU buffer 和请求范围。Hover 应尽量走 highlight，commit 操作才进入 filter。

联动状态可能暂时不完整
   某个视图的数据尚未加载或当前尺度只支持聚合结果时，应显示 partial/loading/aggregated 状态，同时保留 shared semantic state，避免不同视图看起来互相矛盾。

Undo 应恢复一组一致状态
   撤销不能只改一个控件值；selection、camera、filter、面板和相关资源版本应按 command/snapshot 恢复到同一语义时刻。

UX 评价需要系统指标和任务指标
   Input-to-feedback latency、P50/P95/P99、GPU upload、dirty region、任务完成时间、误选率、撤销次数和恢复成本共同决定交互质量。

关键路径
--------

事件闭环：

::

   pointer / keyboard
   → normalize event
   → classify interaction intent
   → update interaction state
   → set dirty flags
   → query / resource diff if needed
   → frame scheduler
   → render affected views
   → visible feedback

Brush/Selection：

::

   pointer down
   → draft selection
   → drag overlay updates
   → pointer up / commit
   → semantic selection
   → data filter / GPU selection buffer
   → linked views update

多视图联动：

::

   one view changes shared semantic state
   → selected ids / time / bounds / filter
   → each view maps semantic state to local coordinates
   → highlight or recompute
   → show partial/loading status if data missing

概念辨析
--------

* **Event 与 State**：event 是瞬时输入，state 是交互系统可持续读取的事实。
* **Draft State 与 Committed State**：draft 服务拖动预览，committed state 才触发正式数据语义变化。
* **View State 与 Semantic State**：前者属于单个视图，后者描述多个视图共享的数据含义。
* **Highlight 与 Filter**：highlight 改显示，filter 改数据集合和后续计算。
* **Debounce 与 Frame Scheduling**：debounce 压缩昂贵提交，frame scheduling 合并每帧绘制，两者作用层级不同。
* **Latency 与 Throughput**：交互优先关注单次输入到反馈延迟，整体渲染还需要观察持续吞吐。

本章结论
--------

交互模型应按“Event—Interaction State—Dirty/Dependency—Async Work—GPU Resource Diff—Render—Feedback—Metrics”理解。稳定交互不是让每个事件立即做最多工作，而是让轻量反馈立即可见、昂贵计算按阶段提交、旧结果无法覆盖新意图，并让所有视图围绕同一份语义状态保持一致。