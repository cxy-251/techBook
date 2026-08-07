第117章：实时性能约束
====================

核心知识点
----------

实时渲染首先是 Deadline 系统
   一帧必须在下一次显示截止时间前完成足够工作。60/90/120 FPS 的理论窗口约为 16.67/11.11/8.33 ms，工程上还必须预留系统、驱动、present 和负载波动余量。

Frame Time 比 FPS 更适合工程判断
   18 ms 在 60 FPS 下已超预算，9 ms 在 120 FPS 下也超预算。毫秒可以直接与 pass、CPU job、上传和等待成本相加比较。

预算应覆盖 CPU、Submit、GPU、Present 与 Margin
   CPU update、render command build、GPU passes、present pacing 和 latency margin 都需要显式预算。任何阶段超限都应对应自己的证据与降级动作。

关键路径决定是否掉帧
   Worker job 很长但不阻塞主线程，可能不影响当前帧；一个只有 1 ms 的任务若处在所有后续工作必须等待的位置，也可能成为关键路径节点。

平均 FPS 不能描述稳定性
   P50/P95/P99、最长帧、连续超预算帧和 present interval 更能描述用户可见卡顿。实时系统必须同时关注吞吐与 frame pacing。

CPU Budget 要看 Job Wait，不只看线程总耗时
   Animation、culling、particle、streaming 可并行，但主线程在哪个同步点等待这些结果，决定它们是否真正进入关键路径。

Render Submit 是独立预算项
   Pipeline/descriptor 选择、constant 更新、barrier 组织、draw/dispatch recording、command buffer submit 都会消耗 CPU。显式 API 只是让这些成本更可见，并不会让它们消失。

GPU Budget 应按 Pass 分配
   Shadow、opaque/lighting、transparent、SSR、TAA、bloom、UI 等 pass 都应有目标范围。一个新效果加入时，应明确从哪里获得预算，而不是只看“还能跑”。

Present 与 Latency 也是实时约束
   Swapchain buffer、VSync/present mode、CPU ahead frame 数、compositor 和显示扫描会影响帧节奏和输入延迟。更深的队列可能提高吞吐，也可能增加交互延迟。

监控系统应记录每帧时间线
   CPU frame、render submit、GPU timestamps、resource upload、memory pressure、present interval 与自动降级动作需要统一按 frame id 记录，才能解释“为什么这一帧超限”。

调整策略需要迟滞与时间窗口
   单帧波动不应立刻触发大幅画质变化。可用短窗口检测连续超限、长窗口判断趋势，并设置升档/降档阈值避免质量反复跳变。

Dynamic Resolution 主要解决像素型 GPU 压力
   Fragment、transparent overdraw、postprocess、render-target bandwidth 超限时降内部渲染分辨率有效；CPU bottleneck、vertex bottleneck 或资源解码问题不会因此根治。

质量降级应有明确优先级
   可按 dynamic resolution → shadow update/quality → SSR/AO/volumetric → particle density → LOD/material tier → effect disable 等顺序设计，优先降低视觉敏感度低、恢复成本小的项目。

多线程优化的目标是缩短关键路径
   把工作扔进 worker 不代表更快。要减少主线程 wait、长尾 job、锁竞争，并让 command building、resource prep 等工作尽可能在真正消费前完成。

Async Compute 必须用 Timeline 证明重叠
   只有 compute 与 graphics 在硬件上真实并行，且没有严重争抢相同 bandwidth/cache 时才有收益。否则多队列只会增加 semaphore/barrier 和调试复杂度。

容错目标是保持连续性，而不是强行保持最高画质
   短时负载峰值应优先维持输入响应、frame pacing 和画面稳定，再逐步恢复质量。运行时降级是峰值兜底，内容生产仍应遵守长期预算。

关键路径
--------

实时帧：

::

   input
   → CPU update / jobs
   → render submit
   → GPU passes
   → present queue
   → display
   → frame-time telemetry
   → optional quality adjustment

预算闭环：

::

   target frame interval
   → allocate CPU/GPU/present budgets
   → measure each frame
   → classify violation
   → apply stage-specific fallback
   → hysteresis / recovery
   → verify P95/P99 and image quality

调度优化：

::

   CPU job graph + GPU queue timeline
   → identify waits / long tail
   → move non-critical work off path
   → version dynamic resources
   → test async overlap
   → compare end-to-end latency

概念辨析
--------

* **FPS 与 Frame Time**：FPS 是频率结果，frame time 是直接预算单位。
* **Throughput 与 Latency**：更高并行和更深队列可提高吞吐，但可能增加输入到显示延迟。
* **平均帧时间 与 Percentile**：平均值描述总体水平，P95/P99 更能反映卡顿长尾。
* **Worker Parallelism 与 Critical Path**：任务并行不代表它退出关键路径，取决于主线程何时必须等待结果。
* **Dynamic Resolution 与 Quality Scaling**：前者主要改变像素数量，后者可以同时调整阴影、LOD、特效等多个成本维度。
* **Async Compute 与 Guaranteed Speedup**：异步只是调度机会，收益必须由真实 overlap 和总帧时间证明。

本章结论
--------

实时性能应按“Frame Deadline—Budget Allocation—Critical Path—Monitoring—Fallback—Recovery”理解。目标不是让所有帧都以最高画质运行，而是在 CPU、GPU、present 和资源压力变化时，始终让最重要的工作按时完成。稳定的实时系统必须把预算、证据、降级优先级和恢复规则都做成长期工程契约。