第116章：Profiling 工具与技术
=============================

核心知识点
----------

Profiling 的目标是建立可复查证据链
   “感觉卡”必须被转换成具体 frame、pass、draw/dispatch、shader、resource、state 与 counter。任何优化提案都应能指出它准备减少哪类成本，以及用什么指标复测。

Frame Capture 与 Performance Profiling 职责不同
   Capture 记录命令、pipeline state、shader、纹理、buffer 和 render target；Profiler 记录 CPU/GPU 时间线、硬件 counter、带宽、occupancy、queue wait 和 shader 热点。

工具名称变化，问题类型不变
   RenderDoc、Nsight Graphics、PIX、Radeon GPU Profiler、Xcode GPU Tools 等界面不同，但都应被映射到同一套问题：哪一段慢、执行了什么、访问了什么、硬件为何受限。

RenderDoc 类工具更适合“对象级”检查
   Draw list、pipeline state、mesh、descriptor/binding、resource history 和 attachment 内容可以确认某个事件实际使用了哪些资源与状态。

Vendor Profiler 更适合“硬件原因”检查
   NVIDIA 的 SM/warp、AMD 的 CU/wave、Apple 的 encoder/tile、Direct3D PIX 的 timing/resource 等指标需要翻译成 ALU、texture、memory、ROP、occupancy、同步等通用瓶颈类别。

Capture 前必须固定复现场景
   Camera、分辨率、质量、VSync、动态分辨率、streaming、shader/pipeline 预热和特效触发条件必须稳定。正常帧与问题帧应成对捕获比较。

Marker 是跨工具定位锚点
   ``TransparentParticles/HDRColor``、``BloomDownsample/half-res`` 等稳定名称应同时存在于源码、引擎遥测、frame capture 和 GPU profiler 中。

分析应先 Pass，后 Draw/Dispatch
   先找哪个 pass 超预算，再进入该 pass 的具体事件。过早钻进单个 shader 指令，会失去它在整帧中的成本权重。

Pipeline State 用于验证执行合同
   Viewport、blend、depth、cull、render target format、descriptor、sampler、vertex/index buffer 等状态可能同时造成正确性和性能问题，例如错误全分辨率 viewport 或不必要 blend。

Resource View 用于验证数据假设
   Texture 尺寸/mip/format、HDR 高亮覆盖、history 内容、buffer count、attachment 分辨率都能解释为什么后续 pass 的采样或带宽发生变化。

Counter 只能做分类证据
   ALU 高、texture stall 高、color write 高、L2 traffic 高、occupancy 低分别指向不同方向，但不能脱离具体事件和资源直接生成结论。

Shader Profiling 用于局部优化
   进入已确认的热点 shader 后，再检查采样次数、分支、register、normalize/pow、noise、原子操作和指令分布。Shader 微优化应位于证据链末端，而不是第一步。

优化提案应包含五项
   问题范围、证据、瓶颈类型、修改动作、复测指标。比如“Transparent range 4.6 ms + blend/color-write 高 + 全屏 RGBA16F”才能支持 half-res accumulation 等动作。

性能可视化要分层
   Frame 级看 P50/P95/P99 与 spike；pass 级看 GPU time；draw/dispatch 级看事件；resource 级看字节和尺寸；shader 级看局部执行；timeline 级看 CPU/GPU 并行与等待。

引擎内遥测负责长期回归，外部工具负责解释异常
   引擎应持续记录 pass timer、draw/dispatch count、resource peak、pipeline bind、shader variant 等；发现退化后，再用外部 capture 深挖同名 range。

关键路径
--------

证据链：

::

   visual/performance symptom
   → identify exact bad frame
   → pass markers + timings
   → frame capture event
   → pipeline state + resources
   → vendor counters / shader profile
   → bottleneck classification
   → optimization proposal
   → A/B recapture

尖峰分析：

::

   P95/P99 regression
   → normal frame vs spike frame
   → compare event ranges
   → compile / streaming / draw / bandwidth / wait delta
   → isolate first divergent marker
   → fix and repeat

跨平台工具映射：

::

   tool-specific metric
   → generic category
   → pass/resource/shader evidence
   → engine-level action

概念辨析
--------

* **Frame Capture 与 Profiling**：前者保存某帧状态与命令，后者重点测量时间和硬件利用；通常需要组合使用。
* **Marker 与 Event**：marker 是工程语义范围，event 是具体 draw/dispatch/API 命令。
* **Counter 与 Bottleneck**：counter 是支持瓶颈判断的证据，不是单独的瓶颈结论。
* **External Tool 与 Engine Telemetry**：外部工具适合深度诊断，内部遥测适合长期发现回归。
* **Pass Timing 与 Shader Timing**：pass 包含资源状态、draw、带宽和同步，shader 只是其中一部分执行成本。
* **正常帧 与 尖峰帧**：前者用于基线，后者用于差异定位；没有对照就难以归因。

本章结论
--------

Profiling 应按“Frame—Marker—Pass—Event—State/Resource—Counter—Proposal—Retest”理解。工具只是证据入口；真正可靠的性能分析必须让画面症状、引擎事件、GPU 资源和硬件指标落在同一条链上。最终输出不是一张 profiler 截图，而是一项可以被复测证明或推翻的优化决策。