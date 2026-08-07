第113章：CPU-GPU 成本分析
==========================

核心知识点
----------

性能分析先确定 Frame Budget
   30/60/90/120 FPS 分别对应约 33.33/16.67/11.11/8.33 ms。优化讨论应直接使用毫秒和关键路径，不要只看平均 FPS。

Frame Time 不等于 CPU Time，也不等于 GPU Time
   CPU 可以提前录制命令，GPU 可以异步执行，present 还受交换链和刷新节奏影响。必须把 CPU update、render preparation、queue submit、GPU execution、present pacing 分开测量。

瓶颈是关键路径上首先耗尽预算的阶段
   CPU 忙可能来自场景遍历、剔除、命令录制、资源更新；GPU 忙可能来自 shader、overdraw、带宽、render target、compute 或同步；等待则可能来自 fence、queue dependency 或 present。

稳定慢帧与尖峰慢帧需要不同方法
   持续 20 ms 左右的慢帧适合按 pass 拆解；偶发 40—80 ms 尖峰优先查 shader/pipeline 编译、streaming、资源创建、同步 readback、GC 或系统调度。

工作耗时与等待耗时必须分开
   Shader、draw、command recording 属于实际工作；CPU ``WaitForFence``、GPU queue idle、present wait 属于等待。前者优化算法和数据路径，后者优化同步、队列和资源生命周期。

CPU Timer 应按可命名阶段布置
   ``UpdateScene``、``BuildRenderItems``、``RecordCommands``、``SubmitFrame`` 等区间应独立记录，并把 fence/present wait 单独标记，避免“大段 CPU 时间”掩盖真正责任。

GPU Timestamp 是设备时间域证据
   Timestamp 应围绕 frame、pass、draw group 或 dispatch 放置。结果必须按 API 的 timestamp period/frequency 转换，并避免把不同 queue 的时间戳直接当作同一连续时间轴。

Marker 是性能数据的语义锚点
   ``ShadowMap``、``GBuffer``、``DeferredLighting``、``Transparent``、``TAA``、``Bloom`` 等名称应长期稳定，使源码、frame graph、capture 与回归报表能指向同一事件。

Frame Capture 负责把时间落到对象
   Pass timing 只说明哪里慢；capture 进一步显示 draw/dispatch、pipeline state、资源格式、绑定、barrier、shader 与 render target，帮助判断成本来自 ALU、纹理、带宽、overdraw 还是同步。

Counter 负责解释硬件压力类型
   ALU/occupancy、texture/cache、memory throughput、color/depth write、stall reason 等指标只能作为证据的一部分。Counter 必须与具体 pass、资源和 shader 同时解释。

优化动作必须与证据一一对应
   Lighting 带宽高可收窄 G-buffer/格式；light loop 长可加强 tiled/clustered culling；透明 overdraw 高可缩减粒子覆盖；CPU submit 高可 batching/instancing。不能用无关优化解决错误层级的问题。

性能实验必须固定条件
   相机、分辨率、质量档位、动态分辨率、粒子数量、streaming 状态、刷新率、VSync、驱动/API backend 都应记录。否则两个 capture 的时间差不能可靠归因。

最终判断看 End-to-End Frame
   单个 pass 变快不等于整帧变快。每次优化后都应重新测 CPU、GPU、present、P95/P99 和画面质量，确认成本没有转移到别处。

关键路径
--------

成本拆分：

::

   frame budget
   → CPU update
   → render preparation / command recording
   → queue submit
   → GPU passes
   → present pacing
   → displayed frame

GPU 瓶颈定位：

::

   GPU frame time over budget
   → pass timestamps
   → hottest pass
   → frame capture
   → pipeline/resources/shader
   → hardware counters
   → bottleneck class
   → targeted optimization
   → repeat measurement

尖峰定位：

::

   P95/P99 spike
   → identify exact frame
   → CPU/GPU timeline
   → compile / streaming / allocation / readback / wait event
   → capture matching marker
   → remove or pipeline the one-time cost

概念辨析
--------

* **Frame Time 与 CPU/GPU Time**：frame time 是最终交付节奏，CPU/GPU 时间可以相互重叠。
* **GPU Busy 与 GPU Bottleneck**：GPU 很忙不一定超预算；只有关键路径上的 GPU 工作限制帧率时才是瓶颈。
* **Work 与 Wait**：work 表示执行有效任务，wait 表示依赖尚未满足；优化方式完全不同。
* **Timestamp 与 Marker**：timestamp 给时间，marker 给语义，两者组合才构成可复查 pass 证据。
* **Frame Capture 与 Hardware Counter**：capture 回答“什么对象在执行”，counter 回答“硬件为何受压”。
* **平均 FPS 与 P95/P99**：平均值适合看总体趋势，percentile 更能暴露实时交互中的长尾卡顿。

本章结论
--------

CPU-GPU 成本分析应按“Frame Budget—CPU/GPU/Present 分界—Timestamp/Marker—Capture—Counter—Optimization—Retest”理解。先确定慢在哪个时间域，再确定哪个 pass 和资源形成成本，最后让优化动作直接作用于证据指向的瓶颈。没有完整证据链的性能优化，本质上只是猜测。