第112章：Hybrid Compute 技术
===========================

核心知识点
----------

Hybrid Compute 解决的是一帧内多执行域如何协作
   CPU、graphics queue、compute queue、copy queue、历史重建和 AI/denoise pass 可能共同完成一帧。优化重点不是“尽量异步”，而是明确每个资源谁生产、谁消费、何时可见、是否允许旧版本。

CPU/GPU 分工应从所有权开始
   CPU 适合输入、场景策略、资源调度、命令构建和少量控制逻辑；GPU compute 适合粒子、culling、scan/compaction、light list、denoise、upscale 等同构并行任务。跨 CPU/GPU 边界会引入 upload、readback 和等待。

每个资源都要回答 Producer、Consumer 与 Frame Distance
   可见性/indirect args 通常要求同帧最新结果；TAA history 明确读取上一帧；统计数据常允许延迟 1—2 帧。是否允许旧数据直接决定同步强度和多版本资源设计。

Compute → Graphics 的间接参数是典型同步边界
   Compute 写 indirect argument 后，graphics 的 indirect stage 读取。必须建立精确 producer stage/access → consumer stage/access 关系，不能只依赖“两个 pass 顺序看起来正确”。

同 Queue Barrier 与跨 Queue Fence/Semaphore 是不同问题
   同一 queue 内通常用 resource barrier 表达访问可见性；跨 compute/graphics/copy queue 还需要 signal/wait 连接执行时间线。CPU 等 fence 则会进一步把 GPU 完成时间暴露给主线程。

数据传输成本分成“字节移动”和“等待”
   Upload/readback/copy/resolve 消耗带宽；barrier、queue wait、fence wait、present wait 消耗调度空间或 CPU 时间。一个 0.2 ms kernel 也可能因为同步 readback 造成数毫秒甚至整帧 stall。

Readback 是混合计算里最高风险的同步入口之一
   GPU timer、统计、pick、截图等若要求 CPU 同帧结果，会迫使 CPU 等 GPU。可延迟统计应读取 N-1/N-2 帧结果，主渲染路径继续提交新帧。

统一内存减少显式 Copy，不取消同步
   CPU/GPU 共享物理内存仍然存在 cache、一致性、资源 hazard 和执行顺序。资源仍需记录生产者、消费者、访问类型和 frame version。

Async Compute 只有在“可重叠 + 不严重争带宽”时才有收益
   粒子 simulation、skinning preprocessing、部分 light list/denoise 可能适合异步；全屏带宽重滤波与 graphics 同时争用 texture/memory bandwidth 时，异步反而可能让总帧更慢。

Simulation、Update、Render 可以采用不同帧距离
   粒子可在 frame N 渲染旧状态、同时计算 N+1；主相机 culling 要同帧；统计结果可延迟。将所有数据都强制成同帧最新会制造过多硬同步。

多版本资源把硬等待变成有界流水线
   动态 buffer、indirect args、readback、history、scratch 常使用 2—3 个版本按 frame index 轮转。版本过少会互相等待，过多则增加内存、cache footprint 和调试复杂度。

Barrier 应放在真正的消费点
   多个 compute pass 写互不冲突资源后，可以在首次下游读取前统一建立必要可见性；不同 mip/slice/range 则保留 subresource 级依赖。每个 dispatch 后全局 barrier 会严重压缩调度空间。

TAA/重建是典型的跨帧 Compute 协同
   当前 color、depth、motion、exposure 与上一帧 history 进入 resolve/reconstruction；当前输出又成为下一帧 history。History 的读写版本、jitter、motion convention 和 resource state 必须统一。

Denoising/Upscaling/AI Pass 延续同一资源模型
   Feature buffer、motion、depth、confidence、history、network weights 都只是新的输入资源。无论执行在普通 compute、专用 SDK 还是 AI 单元，仍需定义输入帧号、输出帧号、同步、延迟与 fallback。

性能分析要同时看 CPU Job 与 GPU Queue Timeline
   CPU timeline 查 fence wait、readback、command build；GPU timeline 查 graphics/compute/copy overlap、idle 和带宽竞争。只看单个 pass 时间无法解释多队列互相等待。

关键路径
--------

Hybrid Frame：

::

   CPU input / camera / quality
   → upload small constants
   → compute culling / particles / preparation
   → indirect args + dynamic buffers
   → barrier or queue handoff
   → graphics raster
   → color/depth/motion/history
   → compute denoise / reconstruction / upscale
   → present
   → delayed stats readback

跨 Queue 交接：

::

   producer queue writes resource
   → resource barrier/release
   → signal timeline/fence value
   → consumer queue waits
   → acquire/read resource
   → downstream pass

同步优化：

::

   identify same-frame dependencies
   → mark data that may use previous frame
   → eliminate unnecessary readback
   → version dynamic resources
   → narrow barrier stage/range
   → test async overlap
   → inspect bandwidth contention
   → compare end-to-end frame latency

概念辨析
--------

* **Upload 与 Readback**：upload 把 CPU 数据送给 GPU，readback 把 GPU 结果交给 CPU；后者更容易导致 CPU 等待。
* **Barrier 与 Fence**：barrier描述 GPU 资源访问关系，fence/timeline可连接 queue 或让 CPU观察完成进度。
* **Same-Frame Data 与 Historical Data**：前者要求当前帧 producer 完成，后者可使用上一帧稳定版本，后者更容易形成流水线。
* **Async Compute 与 Parallel CPU Jobs**：一个是 GPU queue overlap，一个是 CPU 线程并行，分析工具和依赖层级不同。
* **Unified Memory 与 Free Synchronization**：共享物理内存减少 copy，并不意味着 CPU/GPU 能无序同时访问同一数据。
* **AI Pass 与 Traditional Compute Pass**：执行单元和模型不同，但进入 frame graph 后仍受资源、同步、历史和延迟合同约束。

本章结论
--------

Hybrid Compute 应按“Ownership—Producer/Consumer—Frame Distance—Queue—Synchronization—Versioning—Latency”理解。优化优先减少跨域交接和同帧 readback，再用多版本资源建立流水线，最后才尝试 async compute。真正高效的混合计算系统，不是拥有最多并行队列，而是让每次等待、每次资源切换和每一帧数据延迟都能说明其必要性并由时间线证明。