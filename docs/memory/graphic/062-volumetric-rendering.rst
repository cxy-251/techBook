第062章：体积渲染
================

核心知识点
----------

体积渲染处理沿路径分布的介质
   雾、烟、云和体积光没有单一表面交点，颜色来自沿视线持续发生的吸收与散射。实时实现要把连续积分压缩成有限步数、低分辨率体积网格和历史复用。

吸收、散射与消光决定介质的基本响应
   ``sigma_a`` 表示吸收，``sigma_s`` 表示散射，``sigma_t = sigma_a + sigma_s`` 表示消光。均匀短段的透射率可近似为 ``T = exp(-sigma_t * d)``，决定后方场景颜色还能保留多少。

散射负责让光路本身变得可见
   只有吸收时，雾只会压低后方亮度；加入 scattering 后，光源能量会被介质转向相机，形成车灯、舞台灯、太阳光束和云层内部亮度。

Phase function 决定散射方向
   各向同性模型适合调试；Henyey-Greenstein 常用 ``g`` 参数近似前向/后向散射。正 ``g`` 会增强沿光方向观察时的亮度，负值则增强反向散射。

Density field 决定介质在哪里
   密度可来自高度雾、3D noise、局部 volume、天气系统、粒子或流体模拟。Density 同时进入消光与散射，因此同一参数会影响遮挡强度和介质自身亮度。

Ray marching 是最直观的实时积分
   沿 camera ray 逐步采样 density、light visibility、phase 和 scattering，更新 accumulated radiance 与 transmittance。步长过大会产生 banding，步数过多则直接增加 ALU 和 texture fetch。

Froxel grid 用低分辨率三维网格复用体积光照
   Froxel 是视锥体内的体素。X/Y 通常低于屏幕分辨率，Z 使用线性或对数切片。近处需要更细的 z slice，远处空气雾可以更粗，从而把 per-pixel 体积工作转成可复用的体积数据。

Shadowed volume 决定光束是否尊重几何遮挡
   每个体积采样点需要查询 shadow map、ray traced visibility 或其它遮挡缓存。柱子后仍然发亮通常不是 density 问题，而是 light injection、shadow 坐标、bias 或 visibility history 出错。

Single scattering 是实时主力近似
   它只计算一次 ``light → medium → camera`` 路径。厚云、浓烟的多次散射可由 ambient/probe、precomputed term、radiance cache 或专门 multiple-scattering 近似补足。

Temporal accumulation 用时间换空间采样
   Blue-noise/jitter 将条带转成噪声，history 再降低噪声。历史权重大时响应慢且容易 ghosting，权重小时噪声回升；相机、密度、灯光和遮挡变化都必须触发 rejection。

低分辨率计算必须配合 depth-aware upsample
   半分辨率或四分之一分辨率能显著降低成本，但会在薄几何和深度边缘制造亮雾 halo。Upsample 必须依据 camera depth、normal 或边缘权重限制跨物体混合。

体积 RT 应作为可见性或光照输入，而不是重做整条管线
   Ray traced shadow、probe lighting、volumetric cache 可以补强 froxel/ray-marching 的局部证据。完整积分仍由统一体积 pass 完成，才能保持资源和调试边界清楚。

关键路径
--------

基础体积：

::

   density field
   + camera depth
   + light / shadow data
   → froxel light injection
   → view ray marching
   → accumulated radiance + transmittance
   → temporal reprojection
   → depth-aware upsample
   → volumeRadiance + T * sceneColor

Ray marching：

::

   sample position
   → density
   → extinction / scattering
   → light visibility
   → phase function
   → segment transmittance
   → accumulate in-scattering
   → update total transmittance
   → early terminate when nearly opaque

性能排查：

::

   density / lighting / transmittance debug views
   → light injection time
   → march time / average steps
   → shadow query cost
   → history read/write cost
   → upsample/composite cost
   → adjust resolution / steps / z slices / history / shadow quality

概念辨析
--------

* **Absorption 与 Scattering**：前者减少已有光能，后者把其它方向的光贡献到当前视线。
* **Density 与 Extinction**：density 描述介质分布，extinction 是密度与介质系数组合后的光学衰减。
* **Transmittance 与 Alpha**：transmittance 是物理路径剩余光能，不能简单等同普通 UI alpha。
* **Ray Marching 与 Froxel**：前者描述沿视线积分方式；后者是复用体积属性和光照的空间离散结构。
* **Single Scattering 与 Multiple Scattering**：前者只考虑一次方向改变，后者考虑介质内部多次传播。
* **Jitter 与 Temporal Accumulation**：jitter 打散空间结构，temporal accumulation 再让多帧收敛，二者通常配套。
* **低分辨率与漏光**：降分辨率只是成本策略，真正漏光多来自 upsample 跨深度边界或 shadow evidence 不完整。

本章结论
--------

体积渲染应按“density—light injection—shadow visibility—路径积分—transmittance—history—upsample/composite”理解。先用 density、lighting、transmittance 三张中间图确认物理量，再用 profiler 判断瓶颈位于注光、march、shadow、history 还是 upsample。性能优化主要通过 froxel 分辨率、z slice、步长、自适应采样、checkerboard 和 temporal reuse 完成，但每种降级都会交换 banding、noise、ghosting 或 halo，需要在相机运动、灯光运动和遮挡变化中验证稳定性。