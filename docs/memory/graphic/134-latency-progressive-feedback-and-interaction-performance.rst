第134章：延迟、渐进反馈与交互性能
================================

核心知识点
----------

交互性能首先看 Input-to-Photon 路径
   Input → Event Queue → UI/State Update → Scene/Data Change → Command Recording → GPU Execution → Present → Display。用户感知的“慢”必须被拆到具体时间段。

输入延迟、处理时长与呈现延迟要分开
   输入排队高先查主线程和事件调度；处理阶段高先查状态更新、数据重建、上传和 command recording；呈现阶段高先查 GPU queue、VSync、swapchain 和显示刷新。

高 FPS 不保证低交互延迟
   平均帧率正常也可能出现长任务、队列堆积或单次 GPU spike。交互评估应同时看 P95/P99 frame、input-to-feedback 和 dropped frame。

第一次反馈不必等待最终画质
   Slider knob、selection outline、camera proxy、preview badge 可以立即变化，证明输入已经生效；昂贵 volume/path tracing/大数据结果随后逐级收敛。

Progressive Refinement 的目标是先保证结构可信
   即时 UI → coarse view → stable intermediate → final quality。粗预览可以低分辨率、低 LOD、粗 ray step、低 sample count，但 camera、selection、transfer function、color scale 等核心语义应保持一致。

预览与最终结果必须同方向
   若粗 LOD 丢失关键结构、颜色范围变化或 selection 对不上，用户会基于错误 preview 做判断。降级只能减少精度，不能改变任务语义。

交互模式与 Refine 模式应分离
   Drag/rotate 时降低阴影、后处理、体渲染步数、路径追踪 sample 或不可见 tile 优先级；输入停止后再恢复高质量 pass。

Quality State 应显式可见
   ``instant``、``coarse``、``refining``、``final`` 或 ``partial`` 应进入 HUD/overlay。用户需要知道当前画面已经能判断什么、哪些内容仍会改变。

Generation/Version 防止旧任务覆盖新输入
   每次交互变化递增 generation；异步 tile、refine、compute 或网络任务完成后必须检查 generation。旧任务可以写缓存，但不能提交到当前可见状态。

Interaction Budget 是资源分配问题
   60Hz 约 16.67 ms，120Hz 约 8.33 ms。输入、UI、scene update、command recording、GPU pass、present 都共享预算。交互阶段优先保障低延迟反馈和最低可读画面。

预算策略应围绕 Critical Feedback
   对用户下一步操作有直接影响的 object transform、gizmo、camera、selection、legend 优先；高质量 shadow、reflection、GI、统计和日志可延后。

Frame Stability 比单帧峰值速度更重要
   连续拖拽时稳定的 12 ms 往往比 6/25/7/30 ms 抖动更易控制。需要记录每帧 CPU/GPU/present、降级状态和输入量，观察尖峰来源。

视觉分析工具的降级边界更严格
   医学、工程和科学可视化必须保留空间位置、阈值、颜色标尺、选区和关键结构；娱乐工具可以更激进地降低阴影和视觉特效。

Async Loading 必须和 Cancellation 一起设计
   旧相机视角的 tile、旧时间步的数据、旧 shader refine 在用户改变意图后应取消、降优先级或只进入缓存。异步但不可取消会持续争夺 IO/CPU/GPU 预算。

取消要发生在安全边界
   磁盘/网络读取后、解压前、GPU upload 前、compute dispatch 前、publish result 前都可检查 token。已经提交到 GPU 的命令通常不能直接撤销，只能限制 in-flight 工作并阻止旧结果发布。

大任务应拆成可调度小块
   Tile、chunk、小 dispatch、小 batch 使 scheduler 能在新输入到来时改变优先级，也能控制每帧 upload/compute budget。

Cancellation 不等于资源立刻消失
   staging buffer、descriptor、texture、fence 等仍需遵守 GPU 生命周期。取消只改变任务是否继续执行/发布，资源释放仍受同步约束。

交互性能必须绑定具体可复现动作
   例如“拖 transfer function 3 秒并旋转相机 90°”，同时固定数据集、分辨率、LOD、刷新率和质量。否则两次性能结果不可比较。

统一 Interaction ID 能连接证据
   Input timestamp、CPU trace、GPU marker、present、quality state、resource request 都应带同一 interaction id，使一次操作形成完整时间线。

关键路径
--------

延迟拆分：

::

   input timestamp
   → event processing start
   → state mutation
   → command submit
   → GPU pass start/end
   → present
   → visible feedback
   → classify delay segment

渐进反馈：

::

   new interaction generation
   → instant UI feedback
   → coarse render
   → schedule refine work
   → cancel stale generation
   → intermediate quality
   → final quality when idle/budget allows

异步资源：

::

   camera/data change
   → request visible resources
   → prioritize current generation
   → IO/decode
   → budgeted upload/compute
   → version check
   → publish current result
   → release stale resources after fences

概念辨析
--------

* **Frame Time 与 Input-to-Photon Latency**：frame time 描述渲染节奏，input-to-photon 描述一次操作到视觉反馈的完整延迟。
* **Coarse Preview 与 Incorrect Preview**：粗预览可以少细节，但不能改变用户需要判断的核心语义。
* **Progressive Refinement 与 Loading Spinner**：前者逐步提供可用图像，后者只说明任务未完成。
* **Async 与 Parallel**：异步让主交互路径不等待，不保证任务一定并行执行。
* **Cancellation 与 GPU Abort**：取消主要阻止后续工作和结果发布，已提交 GPU 的命令通常仍需完成。
* **Average Frame Rate 与 Frame Stability**：平均值无法描述交互期间的长尾和周期性抖动。

本章结论
--------

交互性能应按“Input—CPU State—GPU Work—Present—Feedback—Progressive Quality—Cancellation”理解。优化目标不是让每次输入立即得到最终质量，而是让第一份可信反馈尽早出现，让昂贵工作服从帧预算并可被新输入抢占，同时用 interaction id、generation 和 CPU/GPU/present 时间线证明延迟究竟发生在哪一段。