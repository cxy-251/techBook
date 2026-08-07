第072章：高质量渲染器
====================

核心知识点
----------

高质量渲染器的目标是生成可复现、可审查、可合成的高位深图像
   它接收 scene、camera、geometry、material、light 和 render settings，通过 sampler、integrator、acceleration structure 与 film 计算 beauty 和 AOV。质量不仅指“更真实”，还包括结果可诊断、可重渲和可进入后期。

Physically Based Material 的核心是稳定 BSDF 语义
   Diffuse、specular、transmission、subsurface、coat 等 lobe 应在能量关系清楚的材质模型中组合。高质量 renderer 需要让 artist 参数能稳定映射到 BSDF，并让不同 DCC、renderer 和资产版本之间尽量保持外观语义一致。

复杂光路决定离线渲染的质量上限
   Primary ray 命中后会继续产生 reflection、refraction、shadow、volume 与 indirect bounce。透明介质、金属高光、焦散、毛发和体积都会延长路径或增加分支，因此相同 samples per pixel 下的真实 ray count 可能完全不同。

Samples per Pixel 只是采样预算的表层指标
   Pixel sampling 解决几何覆盖、景深和时间采样；path sampling 决定灯光、BSDF、介质和后续 bounce 如何选样。真正需要降低的是 estimator variance，而不是机械提高统一 spp。

Importance Sampling 与 MIS 用来把样本放到高贡献区域
   小面积亮光、glossy lobe 和复杂间接光会造成高方差。采样分布越贴近真实贡献，单位 ray 带来的有效信息越多。MIS 的价值是组合多种采样策略，避免单一路径在某类高贡献事件上效率极低。

Adaptive Sampling 应把预算集中到难收敛像素
   大片低频 diffuse 区域可以提前停止，玻璃边缘、金属高光、景深和软阴影继续增加样本。自适应判断必须基于可靠方差或误差估计，否则可能把焦散和高能稀有样本误判为“已经稳定”。

Reconstruction Filter 决定样本如何落到像素
   Box、Gaussian、Mitchell 等 filter 在锐度、噪声纹理和 ringing 之间取舍。更宽的 filter 能压低高频噪声，但可能损失产品边缘和细线细节；filter 选择应与输出分辨率、景深和后期锐化共同考虑。

Denoiser 是采样链末端工具，不应替代正确采样
   去噪可以降低可感知噪声，但不能修复错误材质、错误灯光采样和错误光路。Firefly、caustic 和 glossy noise 应先从 sampler/integrator 查根因，再决定是否由 denoiser 收尾。

Renderer 模块必须保持可诊断边界
   Scene import、acceleration structure、material/BSDF、sampler、integrator、film 和 AOV recorder 应职责清楚。噪声、黑边、透明错误和 AOV 错层都应能定位到具体阶段，而不是全部藏在一个巨大 shading 函数里。

AOV 是生产接口，不是附带调试图
   Beauty、diffuse、specular、normal、depth、Cryptomatte、motion vector 等层要明确空间、过滤规则、数据类型和合成用途。AOV schema 必须在提交前固定，否则合成模板无法稳定消费输出。

OpenEXR 负责承载高动态范围与多层数据
   高质量输出通常需要 half/float、multi-channel、multi-part 或 deep data。EXR 的通道命名、压缩、metadata、color space、frame revision 都属于渲染契约的一部分，不能在每个镜头里临时变化。

性能预算应从 Ray Count、Memory 与 Node Cost 共同估算
   粗略模型可写成 ``pixel count × spp × average rays/sample × average ray cost``，再加 BVH、texture、film、AOV、checkpoint 和 I/O。相同 spp 下，玻璃、体积、景深和高反射会显著提高平均路径成本。

质量优化应定位到具体光路和资源
   噪声先用 diffuse/specular/transmission/volume AOV 归因，再检查灯光大小、roughness、bounce depth、MIS、texture/filter、AOV 与 denoiser。只有问题确实是全局采样不足时，才值得统一提高 spp。

关键路径
--------

高质量渲染：

::

   scene import
   → acceleration structure
   → camera / pixel sample
   → ray intersection
   → material / BSDF evaluation
   → direct-light / BSDF sampling
   → MIS / path continuation
   → Russian roulette termination
   → film accumulation
   → beauty + AOV
   → OpenEXR
   → compositing

噪声定位：

::

   noisy beauty
   → diffuse / specular / transmission / volume AOV
   → identify noisy lobe / path
   → inspect light / BSDF sampling
   → inspect bounce depth / firefly source
   → adaptive sampling / importance sampling / MIS
   → denoise if needed
   → compare fixed-seed crop with reference

预算评估：

::

   resolution
   → spp
   → average rays per sample
   → BVH / shader / texture cost
   → film + AOV memory
   → scene load / build / EXR IO
   → node-hours
   → expected rerender factor
   → delivery budget

概念辨析
--------

* **Pixel Sampling 与 Path Sampling**：前者覆盖像素、镜头和时间维度，后者覆盖光传输方向与事件。
* **SPP 与 Ray Count**：SPP 是 camera sample 数，真实成本更接近总 ray 数和每条 ray 的平均代价。
* **Importance Sampling 与 Adaptive Sampling**：前者改变单条路径如何取样，后者改变哪些像素继续增加样本。
* **Integrator 与 BSDF**：BSDF 描述局部散射，integrator 决定如何沿整条光路组合这些散射事件。
* **Denoising 与 Rendering**：去噪降低方差可见性，不等于恢复错误的光传输模型。
* **Beauty 与 AOV**：Beauty 是主视觉结果，AOV 是同一次渲染中保存的结构化生产数据。
* **Depth AOV 与 Deep Data**：普通 depth 通常只记录一个表面，deep data 可以保存同一像素上的多层深度样本。
* **高质量与无限采样**：生产目标是在有限 node-hours 内达到可接受误差，而不是无条件追求最高 spp。

本章结论
--------

高质量渲染器应按“场景与材质—采样—光路积分—Film/AOV—高位深输出—预算验证”理解。画质问题先归因到具体光路，再决定采样、MIS、材质、filter 或 denoiser；性能问题则用 ray count、memory、scene setup、I/O 和 node-hours 共同解释。真正高质量的 renderer 不只是能算复杂光路，还必须让每个结果可复现、每个 AOV 可解释、每项成本可预算。