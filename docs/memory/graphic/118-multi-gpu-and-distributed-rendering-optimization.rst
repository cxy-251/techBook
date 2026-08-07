第118章：多 GPU 与分布式渲染优化
================================

核心知识点
----------

多 GPU 优化的前提是存在真实可并行工作
   第二块 GPU 不会自动缩短帧时间。只有任务能独立执行，且同步、传输、合成成本低于并行收益时，多 GPU 才成立。

先建立单 GPU Baseline
   CPU/GPU frame time、pass timestamp、present interval、resource size、history 数据量和 memory pressure 都必须先记录。否则双 GPU 后无法判断收益来自哪里、损失又落在哪里。

跨 GPU 资源必须显式描述所有权
   每个共享资源应有 owner、producer queue、consumer queue、可见范围、ready fence/semaphore 和 fallback path。同步信号只表示执行进度，不等于数据已经高效地跨设备可读。

等待应放在真正消费点之前
   GPU1 生成 shadow atlas，GPU0 只有在 lighting 真正读取前才需要等待。过早 wait 会把 GPU0 原本可并行的 pass 一起阻塞。

静态资源更适合各 GPU 本地副本
   Mesh、material texture、environment 等高频只读数据若反复跨 GPU 访问，会受到互连延迟和带宽限制。复制本地版本通常比长期 remote random access 更稳定。

每帧中间结果才适合评估共享/Copy
   Shadow、probe、低分辨率 denoise result 等输出紧凑、消费点明确的资源更适合 pass 级拆分；全分辨率 G-buffer/history 往往传输压力过大。

AFR 按时间拆分帧
   GPU0 渲染 N，GPU1 渲染 N+1，单帧依赖简单，但输入延迟、frame pacing 和 TAA/SSR/denoise 等历史资源管理困难。平均 FPS 提升不代表交互体验改善。

SFR 按屏幕区域拆分同一帧
   延迟比 AFR 更容易控制，但负载均衡和最终 merge 更困难。不同区域内容复杂度差异会让一块 GPU 空闲、另一块 GPU 成为 present 前长尾。

Pass-Level Multi-Adapter 通常更实用
   把 shadow、reflection probe、部分 RT denoise、预处理或低耦合 compute 放到辅助 GPU，再让主 GPU 完成 lighting/post/present。候选任务应输出紧凑、依赖清晰、消费可延迟。

Peer Memory 不是本地内存
   P2P/NVLink/PCIe 或平台互连能减少 CPU staging，但远端访问仍有延迟、带宽和 cache 代价。大块顺序 copy 比高频随机 texture/buffer 读取更容易获得稳定性能。

Multi-GPU Timeline 必须同时显示 Work、Copy、Wait、Merge
   两块 GPU 都 100% busy 也可能没有收益，因为它们可能重复计算、等待互相数据或在 present 前串行合并。总关键路径才是最终指标。

效率评估应优先查四个尾部成本
   辅助 GPU 是否完成太晚、主 GPU 是否等待太早、跨 GPU copy 是否过大、output merge 是否落在 present 前串行尾巴。这四类问题最容易吞掉并行收益。

跨 GPU 结果可以用“下一帧消费”降低同步
   Shadow/probe/统计等允许一帧延迟的数据可通过多版本资源建立流水线，减少同帧硬等待。代价是固定 latency 与版本管理。

分布式渲染比同机多 GPU 多出网络与版本一致性
   Scene version、resource package、task dependency、output contract 必须固定，否则节点使用不同资产、shader 或时间状态时无法正确合成。

分布式任务粒度决定吞吐与尾延迟
   Frame 级依赖少，适合离线序列；tile 级更细但需要边界与合成；pass 级依赖最强，只有网络延迟和中间结果足够小才适合实时。

实时云渲染关注端到端延迟
   Input→server simulation/render→encode→network→decode→display 才是完整路径。节点更多但网络、编码或 compositor 尾延迟更大时，用户体验仍会下降。

离线 Render Farm 更关注吞吐与长尾
   节点数增加后的收益下降要先查场景/资源分发、共享存储、调度粒度、失败重试和输出写入，再进入单节点 shader 优化。

最佳实践是保留少数高收益跨边界任务
   多 GPU/分布式架构不应追求“拆得最多”，而应把跨设备路径限制在低耦合、结果紧凑、同步少、可回退的任务。

关键路径
--------

同机 Multi-GPU：

::

   CPU builds frame graph
   → GPU1 executes low-coupling task
   → GPU1 signals completion
   → peer copy/shared result
   → GPU0 waits at actual consumer
   → lighting/post
   → output merge
   → present

效率诊断：

::

   single-GPU baseline
   → multi-GPU frame timeline
   → work split balance
   → cross-GPU bytes / remote accesses
   → wait positions
   → merge/present tail
   → P95/P99 frame pacing
   → retain or remove split

分布式渲染：

::

   job submission
   → lock scene/resource version
   → build task graph
   → assign frame/tile/pass tasks
   → worker render
   → validate outputs
   → retry stragglers/failures
   → merge/composite
   → deliver result

概念辨析
--------

* **Fence/Signal 与 Data Transfer**：同步只说明生产工作完成；资源是否能被另一 GPU 读取还取决于内存可见性与 copy/share 路径。
* **AFR 与 SFR**：AFR 按帧时间拆分，SFR 按同一帧屏幕区域拆分；一个更受历史/延迟影响，一个更受负载均衡/合成影响。
* **Multi-Adapter 与 Async Compute**：前者使用不同 GPU/device，后者通常是在同一 GPU 上利用不同 queue/engine 重叠工作。
* **Peer Access 与 Local Access**：peer access 避免 CPU 中转，但通常仍弱于本地资源访问。
* **实时分布式 与 离线 Render Farm**：前者优先端到端延迟与 pacing，后者优先总吞吐、失败恢复和资源利用率。
* **平均 FPS 与 Multi-GPU Efficiency**：平均吞吐提升可能掩盖 frame pacing、输入延迟和长尾恶化。

本章结论
--------

多 GPU 与分布式渲染应按“Baseline—Work Split—Ownership—Transfer—Synchronization—Merge—Latency”理解。任何拆分都必须证明节省的计算时间大于跨边界成本。最有效的方案通常不是把整条 renderer 平均拆开，而是挑选少数输出紧凑、依赖低、可延迟、可回退的任务，让并行真正缩短最终关键路径。