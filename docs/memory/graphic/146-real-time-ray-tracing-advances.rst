第146章：实时光线追踪进展
========================

核心知识点
----------

实时 Ray Tracing 的工程目标是把有限 Ray Budget 放到最有价值的光传输问题上
   Rasterization 仍适合主可见表面、UI、透明排序和大量常规材质；Ray Tracing 更适合屏幕外反射、软阴影、接触阴影、局部 GI 与复杂可见性查询。一个 RT pass 必须明确回答传统 raster path 难以稳定回答的问题。

实时 RT 已从单一特效变成 Frame Graph 子系统
   Scene update、BLAS/TLAS、G-buffer、ray dispatch、denoiser、history、composite 和 fallback 必须统一管理资源生命周期。只优化 ``TraceRays`` 耗时不足以保证整帧稳定。

Acceleration Structure 是实时 RT 的空间基础
   BLAS 描述底层几何，TLAS 描述实例与变换。静态资产适合预构建和 compaction；刚体运动优先更新 TLAS transform；skinned/deformable geometry 需要 refit、rebuild 或 raster fallback。AS update 策略直接影响 scratch memory、带宽和同步。

硬件 RT 单元主要加速 Traversal 与 Intersection
   RT Core、Ray Accelerator 等负责 BVH traversal、box/triangle intersection。Hit shader 的材质求值、texture fetch、BRDF、denoising、history resolve 和同步仍依赖通用 shader core 与内存系统。

Traversal 快并不代表整个 Ray Path 快
   Any-hit alpha test、复杂材质分支、随机纹理访问、过大的 payload、递归 bounce 和 ray divergence 都会降低 SIMT 效率。真实瓶颈必须拆成 AS build/update、traversal、hit shading、denoise 和 composite。

完整 Ray Pipeline 与 Inline Ray Query 服务不同任务
   独立 raygen/miss/hit pipeline 适合 reflection、GI、可集中 denoise 的 shadow pass；inline ray query 适合在 graphics/compute shader 中做短距离 visibility、contact shadow 或 occlusion 查询。

跨 API 抽象应围绕能力而不是厂商对象名
   DXR、Vulkan RT、MetalRT 虽然 API 不同，但都可以收敛成 acceleration structure、ray effect、shader/material binding、dispatch/query、synchronization 和 fallback 六类职责。

Ray Effect 应声明自己的运行契约
   每类 effect 至少要定义 ray type、resolution scale、max distance、bounce count、mask、payload、hit behavior、denoiser inputs、history policy 和 fallback。Shadow、reflection、AO、GI 不应各自复制一套 AS 与材质绑定逻辑。

Denoiser 是实时 RT 的正式组成部分
   低 spp 输出天然有噪声。Reflection 通常需要 radiance、hit distance、normal、roughness、motion、disocclusion；shadow 需要 visibility、hit distance、light size、normal、history confidence；GI 需要 albedo、normal、depth、radiance moments、variance。

Temporal Stability 与 Raw Sample Quality 同等重要
   一帧噪声较低但快速运动时拖影、漏光或高光滞后，仍然是 RT 失败。Motion vector、depth、normal、roughness、object/material identity 与 history rejection 必须使用同一时空语义。

Ray Budget 应显式分配
   每个 effect 都应限制 resolution、rays per pixel、max distance、roughness cutoff、bounce、update frequency 与 object mask。高贡献近场反射可以分配更多 rays，远景与低贡献材质应使用半分辨率、probe 或其他 fallback。

材质系统会直接影响 RT 成本
   Alpha-tested foliage、透明层、复杂 layered material 和高分歧 hit shader 会增加 traversal 后的 shading 成本。生产管线应允许 simplified hit material、ray visibility mask 与材质级 RT 开关。

跨平台 Fallback 要保持视觉语义一致
   无硬件 RT 时可切 SSR、shadow map、probe GI、SDF shadow、baked lighting；只支持短 ray query 时可保留 contact shadow/occlusion。不同平台可以降低范围和精度，不应改变材质基本语义。

ReSTIR、Path Guiding 与 Neural Cache 的共同目标是提高每条 Ray 的信息价值
   ReSTIR 通过时空 reservoir reuse 提高少量 light sample 的利用率；path guiding 学习更高贡献的采样方向；neural radiance cache 用学习模型缓存/预测间接光。它们都用重用、概率分布或学习表示补偿有限样本。

前沿算法仍依赖正确的几何、运动与时间证据
   Reservoir history、guiding distribution、radiance cache 一旦使用失配的 motion、depth、normal、visibility 或场景版本，就会把错误跨像素或跨帧扩散。高级算法不会绕过基础数据契约。

关键路径
--------

典型 Hybrid RT Frame：

::

   scene update
   → BLAS/TLAS build or update
   → raster G-buffer
   → ray effect dispatch/query
   → noisy radiance / visibility / hit distance
   → temporal validation + denoiser
   → lighting/composite
   → post-process
   → present

RT 性能定位：

::

   RT frame too slow
   → measure AS build/update
   → measure traversal/dispatch
   → inspect any-hit + hit shader divergence
   → inspect memory/payload
   → measure denoiser
   → inspect barriers and queue waits
   → reduce ray/resolution/material cost

跨平台能力选择：

::

   query RT capability
   → full pipeline / inline query / no RT
   → select effect tier
   → select AS update policy
   → select denoiser contract
   → install raster/compute fallback
   → validate visual parity

概念辨析
--------

* **RT Hardware 与 Full RT Pipeline**：专用硬件主要加速 traversal/intersection，完整效果还包含 shader、memory、denoise 与 composite。
* **BLAS 与 TLAS**：BLAS 表达几何结构，TLAS 表达场景实例和变换。
* **Trace Rays 与 Ray Query**：前者组织独立 RT pipeline，后者把短可见性查询嵌入现有 shader。
* **More Rays 与 Better Reuse**：增加 rays 直接提高采样量，ReSTIR/guiding/cache 试图提高有限 rays 的信息利用率。
* **Denoising 与 Correctness**：denoiser 能降低方差，不能修复错误的 geometry、motion、material 或 visibility。
* **Fallback 与 Feature Loss**：fallback 可以降低范围和精度，但应保持同一材质/光照语义。

本章结论
--------

实时光线追踪应按“Scene/AS—Ray Budget—Traversal—Hit Shading—Feature Buffers—Denoise/History—Composite—Fallback”理解。先进性不只来自更快的 RT 单元，而来自渲染器能否把有限 rays、动态 AS、材质复杂度和时间重用组织成稳定数据流，并用 pass timing、history validity 与跨平台视觉一致性证明每个 RT effect 的价值。