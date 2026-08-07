第073章：去噪与重建
==================

核心知识点
----------

Denoising 的本质是在降低方差的同时控制偏差
   Monte Carlo 渲染的随机噪声来自有限采样，样本数增加时方差下降，但代价近似线性增长。去噪器尝试从 noisy radiance、辅助特征和历史帧中恢复更稳定的结果，同时可能抹掉真实细节、改变高光形状或制造 temporal ghosting。

首先要区分真实信号与采样误差
   几何边缘、albedo 纹理、normal 变化、roughness、阴影边界和反射结构属于真实信号；随机颗粒、低概率高能样本和帧间独立闪烁更接近采样误差。去噪前必须先判断高频变化是否与 guide buffer 或高采样 reference 对齐。

Firefly 是高能长尾样本问题
   小面积亮光、镜面路径、caustic 和低概率高贡献事件会产生远高于邻域的样本。简单 blur 会把这些错误能量扩散。更稳定的路径是先在采样端改善 light/BSDF strategy、clamp 极端样本或限制异常路径，再让 denoiser 处理剩余噪声。

Classical Filter 依赖局部相似性
   Gaussian、Bilateral、A-trous 等方法通过邻域平均降低噪声。Bilateral/A-trous 可使用 normal、depth、albedo 与方差控制边缘权重，适合 guide 可信的不透明表面。它们行为可解释、成本稳定，但无法自行理解复杂光路。

Guide Buffer 的语义边界决定滤波可信度
   Primary-hit normal/depth 对普通不透明表面很有效；透明、折射、体积、毛发和镜面反射中，最终 radiance 可能来自另一个空间位置。此时 guide 只能解释部分光路，过度依赖会导致噪声残留、跨层污染或错误边缘保护。

ML Denoiser 利用训练先验学习复杂映射
   Noisy beauty 配合 albedo、normal 等特征可以让网络在低频墙面、材质纹理和几何边缘之间做更复杂判断。它的风险来自训练分布偏差：罕见 caustic、窄 specular、高频程序材质可能被抹掉或被重建成不存在的结构。

实时去噪主要依赖时空复用
   1–4 spp 的实时 ray tracing 很难靠单帧 spatial filter 收敛，通常需要 history、motion vector、depth/viewZ、normal、roughness、hit distance 和 disocclusion mask。时间维度提供主要额外样本，也带来 ghosting、lag 和错误历史传播。

Diffuse 与 Specular 应尽量分开处理
   Diffuse 信号通常低频、历史稳定，可以更强 spatial/temporal accumulation；specular 对 roughness、hit distance 和视角更敏感，历史权重必须更谨慎。把两者混在一张 radiance 里统一去噪会增加高光 smear 和反射拖影。

History Validation 决定 temporal denoising 是否稳定
   Motion vector 只负责 reprojection，不足以证明历史可信。当前与历史的 depth、normal、roughness、hit distance、颜色邻域和 disocclusion 都应参与 rejection/clamp。遮挡新出现区域必须快速丢弃旧历史。

去噪通常应工作在 Tone Mapping 前的 Scene-Linear Radiance
   HDR radiance 的能量关系在线性空间中更可解释。先 tone map 再 denoise 会把不同强度范围压缩到非线性显示空间，改变噪声统计并使高光和暗部的误差关系失真。

Denoiser 是高带宽 Compute Pass
   Full-resolution noisy diffuse/specular、albedo、normal、depth、roughness、motion、history 与输出纹理会产生大量读写。正确性依赖资源状态和 history 生命周期，性能则受分辨率、tile overlap、模型推理、texture bandwidth 与 barrier 影响。

Fallback 必须预先定义
   Feature 缺失、显存不足、设备不支持目标模型或透明区域 guide 不可信时，应能切到较小 spatial filter、仅 diffuse 去噪、降低分辨率、减少 specular history 或提高采样。Fallback 的目标是保持可预测，而不是强行让同一算法覆盖所有像素。

质量评估必须同时看静态、动态与艺术目标
   PSNR/MSE 可看整体能量误差，SSIM 更关注结构，difference image 与 reference crop 能暴露 bias；动态播放用于发现 ghosting、boiling 和 lag；artist review 用来判断材质意图、高光宽度和纹理细节是否被改变。

关键路径
--------

空间去噪：

::

   noisy radiance
   + albedo / normal / depth
   → estimate variance
   → build edge-aware weights
   → spatial / A-trous filtering
   → preserve geometry / texture boundaries
   → denoised radiance

实时时空去噪：

::

   current noisy diffuse / specular
   + motion vector
   + depth / normal / roughness / hit distance
   → reproject previous history
   → disocclusion / history validation
   → temporal accumulation / clamp
   → spatial reconstruction
   → current history
   → tone mapping / later post process

质量排查：

::

   noisy beauty
   → identify real edge vs random noise
   → inspect guide buffers
   → compare high-spp reference
   → disable temporal path
   → validate spatial filter
   → inspect motion / disocclusion / history weight
   → check bias / ghosting / detail loss

概念辨析
--------

* **Noise 与 Detail**：噪声是采样误差，detail 是真实信号；频率高低本身不能区分二者。
* **Variance 与 Bias**：去噪常降低 variance，同时可能增加 bias；更平滑不等于更正确。
* **Spatial 与 Temporal Denoising**：前者只利用当前邻域，后者利用跨帧样本但需要可靠重投影和历史验证。
* **Motion Vector 与 History Validity**：motion 只告诉历史位置，depth/normal/disocclusion 等才决定是否值得复用。
* **Diffuse 与 Specular**：二者时空稳定性不同，最好采用不同滤波强度和 history 策略。
* **Guide Buffer 与 Ground Truth**：normal/depth/albedo 是辅助证据，不代表完整间接光或透明反射路径。
* **Denoiser 与 Sampler**：denoiser 不能替代正确 importance sampling、MIS 和异常样本控制。
* **Reference 与 Clean Output**：高采样 reference 用于判断偏差；“看起来很干净”的输出可能已经丢失真实信号。

本章结论
--------

去噪与重建应按“噪声归因—特征可信度—空间滤波—历史验证—误差评估”理解。墙面颗粒、纹理模糊和 specular 残影属于不同问题，必须分别检查 variance、guide、roughness、motion 和 hit history。稳定管线先从采样端控制极端噪声，再保证 feature 对齐和资源同步，最后用 spatial/temporal/ML denoiser 收敛，并用高采样 reference 与动态播放共同约束 bias。