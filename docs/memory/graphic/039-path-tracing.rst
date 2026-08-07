第039章：Path Tracing
====================

核心知识点
----------

Path Tracing 用随机完整光路估计全局光照
   每个像素从 camera ray 出发，在表面反弹、采样光源和材质、更新 path throughput，直到 miss、材质终止、Russian roulette 或最大深度。多条 path 的平均值逼近像素 radiance。

最小路径状态是 ``radiance + throughput + ray + depth``
   ``radiance`` 保存已经累积到当前样本的能量，``throughput`` 保存从相机到当前顶点仍保留的权重，``ray`` 决定下一段查询，``depth`` 控制路径长度。调试时这四个量应能单独观察。

Throughput 把每次散射的能量权重连续乘起来
   常见更新形式为 ``throughput *= BSDF * abs(N·wi) / pdf``。之后命中 light 或 environment 时，再把返回 radiance 乘 throughput 加到样本中。错误 PDF、法线或颜色空间会沿整条路径被放大。

Next Event Estimation 主动估计直接光
   在每个可连接表面显式抽取光源样本并发 shadow ray，可以避免仅靠 BSDF 随机反弹去碰小光源。小 area light 场景下，NEE 是降低直接光高方差的关键路径。

Importance sampling 把有限 ray 投向高贡献方向
   Diffuse 表面适合 cosine-weighted sampling，glossy/metal 适合 BSDF sampling，小光源适合 light sampling，高亮环境适合 importance-sampled environment。策略改变噪声，不应改变长期平均亮度。

MIS 用多个策略共同估计同一贡献
   BRDF sampling 与 light sampling 各有强项。MIS 比较所有可生成当前样本的 PDF，再分配权重，降低低概率高贡献样本形成的 firefly。所有 PDF 必须使用可比较的 measure。

路径终止同时需要硬边界和概率边界
   ``maxDepth`` 控制最坏成本；Russian roulette 根据 throughput 随机终止低贡献路径并补偿存活权重。前几次 bounce 通常不宜过早 roulette，因为浅层间接光承担主要可见能量。

实时 Path Tracing 的核心约束是 ray budget
   实时系统通常每帧每像素只有 1 条或极少 path，因此不能只靠同帧 spp 收敛。必须把样本扩展到时间、空间和缓存维度，通过 temporal accumulation、spatial reuse、reservoir、radiance cache 和 denoiser 共同完成重建。

Temporal accumulation 必须严格验证 history
   Motion vector 负责重投影，depth、normal、material/roughness 和 disocclusion 负责确认上一帧样本是否仍属于当前表面。验证过松会 ghosting，过严会在运动时重新变噪。

Denoiser 依赖几何与材质 guide 保留真实边界
   Noisy radiance、normal、albedo、depth、roughness、motion vector、variance/moments 是常见输入。Diffuse 可以更强地滤波，镜面与几何边缘需要更保守的 history 和空间半径。

Reservoir、cache 与 path guiding 改变的是不同环节
   Reservoir 负责从大量候选中保留并复用少数高价值样本；radiance/probe cache 用已有低频结果替代深层查询；path guiding 学习高贡献方向并改变后续采样分布。它们可以组合，但必须明确各自覆盖的光照分量。

性能优化必须按 ray 类型和 pass 拆开
   Primary、shadow、indirect bounce、specular ray、history、denoiser 都有不同成本结构。先统计数量和 GPU 时间，再决定降分辨率、roughness cutoff、缓存、复用或减少 bounce，最后才处理局部 shader ALU。

关键路径
--------

单个 Path Tracing 样本：

::

   pixel sample
   → camera ray
   → closest hit
   → miss: throughput * environment
   → hit: material / normal / emitter
   → NEE 采样光源 + visibility
   → 累加 direct contribution
   → sample BSDF direction
   → throughput *= BSDF * cos / pdf
   → spawn next ray
   → depth / Russian roulette
   → 下一 bounce
   → sample radiance
   → linear HDR accumulation

实时重建：

::

   noisy current radiance
   + motion / depth / normal / material guides
   → temporal reprojection
   → history validation / rejection
   → 可选 reservoir / spatial reuse
   → variance estimation
   → material-aware denoise
   → composite / tone mapping

问题排查：

::

   关闭 denoiser 看 raw radiance
   → 分离 direct / indirect / specular AOV
   → 检查 throughput 与 PDF
   → 检查 MIS / measure conversion
   → 检查 history validity
   → 检查 variance / guide buffer
   → 最后调整 clamp、滤波和 tone mapping

概念辨析
--------

* **Path Tracing 与递归 Whitted Ray Tracing**：前者用随机 BSDF/light 采样估计完整积分；后者主要沿确定 reflection/refraction/shadow 分支递归。
* **Radiance 与 throughput**：radiance 是路径获得的光，throughput 是它返回到像素时的累计乘法权重。
* **BSDF sampling 与 light sampling**：前者匹配材质反射分布，后者匹配光源分布；两者可通过 MIS 组合。
* **NEE 与下一 bounce**：NEE 主动连接光源估计直接光，BSDF continuation 负责继续探索间接路径。
* **Variance 与 bias**：方差表现为有限样本噪声；错误 PDF、clamp 或错误复用可能引入 bias。增加样本只能降低 variance。
* **Temporal accumulation 与 denoising**：temporal accumulation 在时间维度复用样本；denoiser 根据 guide 估计并滤除噪声，两者目标不同。
* **Reservoir 与 radiance cache**：reservoir 复用候选样本，cache 复用已估计光照；前者保存样本代表，后者保存光照场近似。
* **Firefly 与真实 HDR highlight**：firefly 常由小 PDF 大权重造成，不能把所有高亮都直接 clamp。

本章结论
--------

Path Tracing 的稳定理解是“采样光路—记录 PDF—更新 throughput—累积 radiance—用更多或更聪明的样本降低方差”。离线重点是重要性采样、MIS 和足够 spp；实时则要把极低 ray budget 与 temporal/spatial reuse、cache 和 denoiser结合。亮度错误先查 PDF/权重，运动残影先查 history，噪声先查采样覆盖，再考虑增加 ray。