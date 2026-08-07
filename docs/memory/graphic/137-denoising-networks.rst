第137章：去噪网络
================

核心知识点
----------

路径追踪噪声本质上是有限样本导致的 Monte Carlo 方差
   低 spp 下 diffuse indirect、glossy reflection、小光源、深层 bounce 都会产生颗粒、firefly 和时域闪烁。去噪首先要确认 signal 的噪声来源，而不是直接把所有高频都当噪声。

实时去噪是空间与时间的联合重建
   单帧网络负责根据邻域与 guide 抑制空间方差；temporal path 通过 motion vector、history、variance、disocclusion 等把多帧信息对齐。画面稳定性往往比单帧 PSNR 更重要。

Guide Buffer 是网络理解几何与材质的关键证据
   Albedo 帮助保留真实纹理边界，normal 表示几何方向，depth/viewZ 约束遮挡，roughness 提示 specular lobe，motion vector 负责历史重投影。Guide 编码或空间失配会直接制造 overblur、ghosting 和边缘污染。

不同 Ray-Traced Signal 应尽量分开处理
   Diffuse indirect 低频且可强平滑；specular reflection 高频、视角相关且对 roughness 敏感；shadow 关注硬边/半影；AO 关注接触区域。所有 signal 混成一张 color 再处理，会把不同统计特性强塞给同一模型。

U-Net 适合同时捕获大尺度照度和局部边缘
   Encoder 扩大感受野，decoder 恢复分辨率，skip connection 保留高频结构。过度依赖低分辨率 feature 会产生油画感，过度依赖 skip 会保留噪声。

Feature-Guided Denoiser 应让几何特征限制跨边界混合
   Guide 可以作为输入 channel，也可以进入 attention、confidence 或 edge weight。关键不是“多给几个 buffer”，而是这些 feature 是否真的与当前 noisy signal 对齐。

Recurrent Denoiser 用历史状态换取极低 spp 下的稳定性
   上一帧 denoised color、hidden state 或 feature history 能累计信息，但错误历史也会持续传播，因此必须配套 motion、disocclusion、history confidence 和 reset。

Temporal Accumulation 的核心是 History Validity
   静态区域可提高 history 权重；新暴露区域、快速运动边缘、视角敏感反射应降低历史贡献。History rejection 失效会比残余噪声更显眼，因为它产生拖尾和亮度延迟。

训练集必须覆盖运行时的噪声与运动分布
   训练数据至少应覆盖 diffuse/specular、small light、HDR firefly、细纹理、透明、动态物体、运动相机和不同 sample count。只用静态或单一材质数据训练出的模型，在真实镜头中很容易失稳。

Noisy/Clean Pair 必须来自一致的渲染语义
   Noisy input 与 high-spp reference 应使用相同 camera、材质、曝光和颜色空间；guide 也必须来自相同 frame。训练 pair 若本身错位，模型会学习补偿错误而非噪声统计。

Loss 应同时约束亮度、结构和时间
   单纯均方误差容易过度平滑。工程上应结合 HDR normalization、edge/detail、perceptual 或 temporal consistency 等目标，并用真实 render 检查是否保留材质细节和反射结构。

运行时预算决定模型架构
   4K 60 FPS 下去噪只有有限毫秒预算。常见手段包括降低 signal 分辨率、half precision、tiling、减少 channel、复用 history、轻量模型或按平台切换模型档位。

去噪 Pass 应进入明确的 Frame Graph
   Ray trace 先输出 noisy signal 和 guides，随后 history reprojection/validation，再执行 denoiser，最后写入 denoised buffer 与下一帧 history。其后 tone mapping、upscaling、bloom、UI 必须知道输入的颜色空间与分辨率。

History Buffer 是跨帧资源，不是普通临时 RT
   Resize、camera cut、model change、exposure jump、render-scale change 都可能要求 history reset。历史生命周期未处理好，会形成长期污染。

效果评估必须同时看静态图与连续帧
   静态图检查 residual noise、overblur、firefly、边缘保护；动态序列检查 ghosting、boiling、lag、disocclusion；性能 capture 检查 inference、memory 和 sync。

Fallback Filter 应共享同一 Signal Contract
   神经模型不可用时可切回 SVGF、A-trous、bilateral 或其他传统方案。只要 noisy signal、guide 和输出格式一致，后续 post-process 与 history 管理就能保持稳定。

关键路径
--------

实时去噪：

::

   low-spp ray tracing
   → noisy diffuse/specular/shadow signals
   → albedo/normal/depth/roughness/motion guides
   → reproject history
   → validate history / disocclusion
   → neural denoiser
   → denoised signal
   → composite / upscale / tone map
   → update history

训练：

::

   representative scenes
   → low-spp noisy frames
   → high-spp reference
   → aligned guide buffers
   → train spatial/temporal network
   → validate static + motion cases
   → export model + runtime contract

故障定位：

::

   artifact appears
   → classify residual noise / blur / ghost / firefly
   → inspect noisy signal
   → inspect guide encoding
   → inspect motion + history validity
   → inspect network output
   → compare reference/fallback
   → measure inference + memory

概念辨析
--------

* **Noise 与 Detail**：随机采样方差应被抑制，真实纹理、几何边缘和反射结构必须保留。
* **Spatial Denoising 与 Temporal Denoising**：前者依赖当前帧邻域，后者依赖跨帧重投影和历史有效性。
* **Guide Buffer 与 Ground Truth**：guide 是运行时辅助特征，ground truth 是训练/评估参考图。
* **History Reprojection 与 Recurrent State**：前者显式搬运上一帧图像/特征，后者把历史压入网络内部状态。
* **Overblur 与 Low Noise**：噪声少不等于质量高，细节被错误抹掉也是去噪失败。
* **Neural Denoiser 与 Traditional Filter**：二者都解决同一 signal contract，区别在滤波/重建函数是否来自训练。

本章结论
--------

去噪网络应按“Noisy Signal—Guide—History—Network—Output—Temporal Stability—Evidence”理解。正确做法是先把不同光照信号和 guide 对齐，再让网络在明确历史有效性规则下重建；质量评价必须同时检查静态细节和动态稳定性，并把 inference、显存和 fallback 一起放进真实 frame budget。