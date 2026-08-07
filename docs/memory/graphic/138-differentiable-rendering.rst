第138章：可微渲染
================

核心知识点
----------

可微渲染是在渲染管线末端增加“梯度出口”
   Forward 仍由 geometry、camera、material、light 和 renderer 生成图像；Backward 则让 image loss 沿计算图回到 mesh vertex、camera pose、texture、BRDF 或 light parameter。工程目标不是只渲染图像，而是让误差能推动正确参数更新。

核心闭环是 Parameter → Render → Loss → Gradient → Optimizer
   参数张量组成 ``θ``，renderer 产生 ``R(θ)``，目标图像为 ``I``，loss 衡量二者差异。Optimization 是否可靠取决于 forward 是否正确、loss 是否约束目标、gradient 是否稳定以及 validation view 是否改善。

连续阶段容易求导，可见性阶段最困难
   Matrix transform、barycentric interpolation、bilinear texture sampling、Lambert/简化 BRDF 通常连续；triangle coverage、occlusion、depth winner、shadow visibility 等包含离散切换，会让 gradient 稀疏、不连续或需要 surrogate gradient。

属性梯度和位置梯度要分开理解
   顶点颜色、texture、roughness 等属性在已覆盖像素内常通过连续插值获得稳定梯度；vertex position 还会改变 silhouette 与遮挡，因此更容易受 coverage discontinuity 影响。

Soft/Approximate Visibility 的目标是给边界可用梯度
   Soft rasterization、antialiasing gradient 或其他近似会平滑 silhouette/coverage 的离散变化。它们提供的是优化方向，不应自动当成严格物理导数，需要用 validation render 检查是否造成几何畸变。

Raster-Based Differentiable Rendering 适合 Pose、Silhouette 与 Mesh/Texture Fitting
   它使用显式 mesh 和 camera，计算成本相对低，最容易嵌入现有 raster pipeline。主要风险是边界梯度、遮挡和局部最优。

Path-Based Differentiable Rendering 更适合逆材质与光照
   它直接对 light transport、BSDF、visibility 与 Monte Carlo estimator 求导，物理一致性更强，能够优化 roughness、light、GI 等，但梯度噪声、训练时间和显存成本显著更高。

SDF-Based 方法用隐式表面提供连续形状表示
   SDF/ray marching 适合连续表面和拓扑变化，surface normal 与 geometry gradient 可从距离场获得。薄结构、透明、复杂遮挡和高频纹理仍然是困难区域。

Neural Differentiable Renderer 优化的是可学习场或 Primitive
   NeRF、neural SDF、Gaussian 等把 density、color、opacity、feature 或 covariance 作为参数。它们可以很好地拟合多视角图像，但“图像拟合好”不等于导出的几何、法线或材质就可用。

反向重建存在强参数耦合
   图像变亮可以通过增大 albedo、light intensity 或 exposure；物体变大可以通过几何 scale 或 camera depth。若同时开放过多自由度，optimizer 会找到视觉等价但物理错误的解。

多视角约束能显著降低歧义
   单视角只证明一个投影下图像可拟合。多视角、held-out view、depth、normal、silhouette 与 smoothness 等约束可以减少 geometry/material/light 相互替代。

Loss 设计决定优化目标是什么
   RGB loss 约束颜色，silhouette loss 约束轮廓，depth/normal loss 约束几何，regularization 限制平滑度、尺度或参数范围。Loss 下降只能证明目标函数下降，不等价于场景参数真实。

参数应按语义分组并使用独立学习率
   Geometry、camera、texture/material、light 的梯度尺度不同。Geometry 学习率过高会产生尖刺，texture 学习率过高会记忆 target view，light 过快会吸收曝光误差。

Validation Image 是一等输出
   训练过程应保存 target view、predicted view、silhouette/depth/normal difference、held-out view 和 loss curve。Held-out view 能暴露 geometry collapse、billboard texture、camera drift 与 lighting compensation。

Backward 的资源成本往往高于 Forward
   为反向传播保存 raster/interpolation、sample path、feature、visibility 等中间量会增加显存。Checkpoint/recompute、分辨率渐进、view batching 与参数冻结可控制内存峰值。

随机采样会让 Loss 与 Gradient 同时带噪声
   Path tracing、random ray batch 和 stochastic visibility 需要固定 seed 做复现实验，并通过更多样本、batch、gradient clipping、loss smoothing 等降低方差。不要把渲染噪声误判成 optimizer 参数错误。

局部最优要靠初始化、约束与阶段优化处理
   常见策略是先优化 camera/pose，再 geometry，再 material/light；先低分辨率轮廓，再高分辨率 RGB；逐步增加自由度比所有参数同时放开更稳定。

关键路径
--------

优化闭环：

::

   initial parameters
   → differentiable forward render
   → predicted RGB/depth/mask
   → loss against targets
   → backprop through renderer
   → gradients per parameter group
   → optimizer step
   → validation render

梯度路径：

::

   image error
   → covered pixel / light path
   → interpolation / shading / visibility
   → camera / vertex / texture / material / light
   → gradient sanity check

稳定性排查：

::

   loss stalls or result looks wrong
   → verify forward convention
   → verify parameter participates in graph
   → inspect gradient magnitude
   → isolate parameter groups
   → inspect visibility / sampling noise
   → add regularization or views
   → validate on held-out images

概念辨析
--------

* **Forward Rendering 与 Differentiable Rendering**：前者只要求正确输出图像，后者还要求误差能沿渲染步骤返回参数。
* **True Gradient 与 Surrogate Gradient**：前者对应真实连续导数，后者为不可导步骤提供可用于优化的近似方向。
* **Image Fit 与 Scene Reconstruction**：当前视角图像匹配不代表几何、材质、光照被真实恢复。
* **Raster-Based 与 Path-Based**：前者更适合显式几何和低成本优化，后者更适合物理 light transport 参数。
* **Training View 与 Validation View**：训练视图参与 loss，validation view 用于检查跨视角泛化与参数真实性。
* **Gradient Noise 与 Optimization Noise**：梯度本身可能受随机渲染影响，不能全部归因于 learning rate 或 optimizer。

本章结论
--------

可微渲染应按“Parameter—Forward Render—Visibility/Shading—Loss—Gradient—Optimizer—Validation”理解。可靠反向重建的关键不是让 loss 尽快下降，而是让每类图像误差对应到合理参数、控制可见性和采样造成的梯度噪声，并通过多视角与 held-out render 证明优化结果不是只在训练图上成立。