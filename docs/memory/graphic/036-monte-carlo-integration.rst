第036章：Monte Carlo 积分
========================

核心知识点
----------

Monte Carlo Integration 用有限随机样本估计高维光照积分
   Path Tracing 无法穷举所有入射方向、光源位置、反弹、时间和镜头变量，只能抽样并求平均。样本数越多，估计越稳定；算法是否最终正确，取决于 estimator、PDF 和采样域是否一致。

Estimator 的基本结构是 ``sample contribution / PDF``
   对从概率密度 ``p(x)`` 抽取的样本，积分估计通过 ``f(x)/p(x)`` 补偿非均匀采样。渲染中 ``f`` 通常包含 incoming radiance、BRDF/BSDF、cosine、visibility 和后续 path contribution。

Sample、PDF、measure 必须绑定到同一采样域
   Direction sampling 的 PDF 常以 solid angle 为单位；面积光采样常以 area 为单位。Area PDF 转换到 solid angle 时需要 geometry term。若 MIS 中不同技术的 PDF 不在同一 measure 下比较，亮度和权重都会系统性错误。

无偏估计的噪声下降速度很慢
   样本数增加时 variance 约按 ``1/n`` 下降，可见误差约按 ``1/sqrt(n)`` 下降。把 64 spp 提升到 256 spp 只会让标准误差约减半，因此优化重点不是无限加样本，而是让采样分布更接近高贡献区域。

Importance sampling 通过匹配 integrand 降低方差
   Cosine-weighted sampling 匹配 diffuse ``cosθ``；BRDF sampling 匹配 glossy/specular lobe；light sampling 匹配直接光源分布。它们都可以是正确 estimator，只是同样 sample count 下方差不同。

MIS 组合多个采样技术以降低极端样本
   小面积光适合 light sampling，光滑材质适合 BRDF sampling，单一策略很难同时覆盖两类高贡献路径。MIS 同时评估各策略 PDF，并用权重降低“低概率却贡献巨大”的 firefly 风险。

Path throughput 是路径累计权重
   每次 bounce 后，throughput 通常乘 ``BSDF × cosθ / pdf``，并继续包含材质反射率和 Russian roulette 存活概率补偿。它表示后续 radiance 对当前像素的乘法系数，也是判断低贡献路径和 firefly 的关键调试量。

Next Event Estimation 主动估计直接光
   每个表面命中直接抽取光源位置或方向，发 shadow ray 检查 visibility，再将 ``Li × BSDF × cos / lightPDF`` 加入 radiance。NEE 对小面积光和硬/软阴影收敛提升明显，但不能单独解决所有 glossy 与 caustic 路径。

偏差和方差必须区分
   有噪声但随着 spp 增长均值稳定接近正确值，是方差问题；高 spp 后仍稳定偏亮、偏暗或偏色，通常是 PDF、权重、颜色空间、法线或可见性错误。Clamping 可以压 firefly，但会改变期望值，属于明确的 biased trade-off。

Radiance 累积必须在线性 HDR 空间完成
   每个 sample 的线性 radiance 先累积和平均，再进行 tone mapping / display encoding。若每 sample 先做 gamma/sRGB，再平均，得到的不是正确光照估计。

随机数相关性会产生结构化噪声
   Pixel coordinate、sample index、bounce index、dimension 应合理混合。分层、低差异序列和 blue noise 主要改善样本分布与时空视觉噪声，不改变 estimator 权重规则。

关键路径
--------

单个 Path Tracing sample：

::

   pixel sample
   → camera ray
   → trace scene
   → miss: throughput * environment
   → hit: 加 emission
   → NEE 抽光源 + shadow ray
   → eval BSDF / light PDF
   → 累加 direct contribution
   → sample BSDF direction
   → throughput *= BSDF * cos / bsdfPDF
   → Russian roulette / depth test
   → 下一 bounce
   → sample radiance
   → linear HDR accumulation
   → 多 sample 求平均

采样策略验证：

::

   固定场景、曝光、spp、随机种子
   → uniform hemisphere 建基线
   → cosine-weighted 检查 diffuse 噪声
   → BRDF sampling 检查 glossy 高光
   → light sampling 检查小光源直接光
   → MIS 组合
   → 比较 mean luminance / variance / max contribution

Firefly 排查：

::

   输出 per-sample contribution
   → 输出 BSDF PDF / light PDF
   → 输出 throughput
   → 检查 PDF measure conversion
   → 检查 BSDF eval 与 sample 是否一致
   → 检查 MIS 权重
   → 检查 near-zero PDF
   → 最后才考虑 clamp

概念辨析
--------

* **Bias 与 variance**：bias 是期望值本身偏离目标；variance 是有限样本围绕正确期望值波动。更多样本只能降低 variance，不能修复 bias。
* **Uniform 与 importance sampling**：两者都可无偏，区别在样本分布是否匹配高贡献区域，从而改变方差。
* **PDF value 与 probability**：连续采样的 PDF 是密度，不是单点概率；它依赖 measure，单位不能忽略。
* **Cosine sampling 与 BRDF sampling**：Lambert 下二者高度相关；复杂 glossy BSDF 下 BRDF sampling 还要匹配材质 lobe。
* **Light sampling 与 shadow ray**：light sampling 决定抽哪个光源事件，shadow ray 只负责验证该事件是否可见。
* **NEE 与 indirect bounce**：NEE 主动估计直接光；BSDF continuation 负责继续探索间接光路，两条贡献可通过 MIS 合并。
* **Throughput 与 radiance**：throughput 是路径权重，radiance 是沿路径获得的实际光能贡献；二者相乘后累加。
* **Firefly 与普通噪声**：firefly 常来自低 PDF 高贡献尾部、错误 MIS 或数值异常，不应只理解为“样本少”。
* **Clamp 与 denoise**：clamp 改变样本值并可能引入偏差；denoiser 根据空间/时间信息估计图像，二者控制问题不同。

本章结论
--------

Monte Carlo 渲染的核心不是“随机发 ray”，而是“明确采样域—记录正确 PDF—用 contribution/PDF 构造 estimator—通过更匹配的分布降低方差”。Path Tracing 中应同时追踪 radiance、throughput、BSDF/light PDF、visibility 和 accumulation。噪声先优化采样策略，亮度偏差先检查 estimator，firefly 先检查 PDF 与 MIS，只有这些数学合同正确后，增加 spp、时域累积和 denoising 才有稳定意义。