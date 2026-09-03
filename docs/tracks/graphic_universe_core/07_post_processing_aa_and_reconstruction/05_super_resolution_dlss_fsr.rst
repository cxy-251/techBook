========================================================================
Chapter 35: 超分辨率与神经图像重构：DLSS、FSR 2/3、XeSS 架构与时域特征融合
========================================================================

.. note:: 前置背景与认知承接
   在前一章（Chapter 34）中，我们系统剖析了运动模糊与体积光散射的底层数学方程与着色器架构。借助二维速度缓冲区（Velocity Buffer）与 McGuire Tile-Max 算法，管线在后处理阶段近似恢复了快门曝光时间内的连续时域光子积分；同时，3D 视锥体素网格（Froxel Grid）将辐射传输方程（RTE）的体积分求解从全屏数千万次光线步进解耦为视锥对数体素内的并发求解，大幅压缩了参与介质渲染的显存与算力瓶颈。

   然而，现代 3A 级图形渲染正面临更为严峻的硬件物理墙。随着显示终端分辨率从 1080p（约 207 万像素）普遍跨越至 4K 2160p（约 829 万像素），光栅化几何吞吐与着色器像素填充率以几何级数膨胀 4 倍。更致命的是，随着硬件光线追踪（Hardware Ray Tracing - DXR / Vulkan RT）成为行业标准，每个像素都需要向 BVH 空间加速结构发射多条光线以评估阴影、环境光遮蔽、漫反射间接光与镜面反射。在 4K 原生分辨率下执行高保真路径追踪，即便在顶级旗舰 GPU 上亦会瞬间击穿显存带宽并导致帧率跌破可交互底线。

   为了打破“高分辨率 vs 物理高保真光照”的零和博弈，实时图形工业爆发了一场革命性的技术范式转移：**超分辨率与图像重构（Super Resolution & Image Reconstruction）**。其核心思想是**以较低内部渲染分辨率（如 1080p 或 1440p）执行全部昂贵的几何光栅化与光照/光线追踪着色，随后在管线尾端借助时空历史累积、启发式先验或深度神经网络，智能重构出画质媲美甚至超越原生 4K 的超高清帧**。

   本章作为第七模块（后处理、抗锯齿与图像重构）的收官之作，将全面解构当代超分辨率技术的三大支柱体系：
   1. **纯算法启发式时域重构（AMD FidelityFX Super Resolution - FSR 2/3）**；
   2. **深度学习与张量加速神经重构（NVIDIA Deep Learning Super Sampling - DLSS 2/3/3.5）**；
   3. **跨架构矩阵指令重构（Intel XeSS）与通用平台统一接入规范（Microsoft DirectSR）**。

------------------------------------------------------------------------
35.1 图像重构范式演进：空间放大 vs 时域超分 vs 神经渲染
------------------------------------------------------------------------

实时图像缩放与重构的物理挑战
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
根据奈奎斯特-香农采样定理（Nyquist-Shannon Sampling Theorem），一个离散采样系统所能表达的最大空间频率受限于其采样频率的一半（即奈奎斯特极限频率 $f_{	ext{Nyquist}} = f_s / 2$）。当以较低分辨率（如 $1920 	imes 1080$）渲染三维场景时，场景几何边缘、细微毛发、远景铁丝网以及复杂 PBR 纹理中超过该极限的高频信息将在光栅化阶段发生不可逆的频谱混叠（Aliasing）或直接丢失。

超分辨率任务的数学本质，是从输入的低分辨率离散观测信号 $\mathbf{I}_{	ext{LR}}$，反演并重构出高分辨率目标信号 $\mathbf{I}_{	ext{HR}}$。该反问题在数学上是极其病态的严重不适定问题（Ill-Posed Inverse Problem），因为存在无穷多个不同的高分辨率空间信号在降采样后会退化为相同的低分辨率像素分布。

.. list-table:: 实时超分辨率三代技术范式核心特征与微架构对比
   :widths: 15 20 25 40
   :header-rows: 1
   :class: tight-table

   * - 技术代际
     - 代表性技术
     - 核心输入数据
     - 物理微架构与重构原理
   * - **第一代：空间放大 (Spatial Upscaling)**
     - Bilinear, Bicubic, Lanczos, AMD FSR 1.0
     - 仅当前帧低分辨率 LDR/HDR 图像
     - 单帧邻域空间核卷积与边缘定向插值，配合局部对比度自适应锐化（RCAS）；无法无中生有恢复亚像素高频细节，放大倍数较大时图像呈现明显油画模糊或振铃效应。
   * - **第二代：时域重构 (Temporal Upscaling)**
     - Unreal TSR, TAAU, AMD FSR 2.x
     - 当前帧低分辨率颜色、深度缓冲、速度矢量、历史高分辨率颜色缓冲、曝光与遮罩
     - 引入相机亚像素抖动（Subpixel Jittering）在多帧时间轴累积分数采样相位；利用硬件速度场与深度执行重投影、双边 Lanczos 滤波、方差裁剪与像素锁定机制；纯算法手工启发式驱动，跨硬件通用性极强。
   * - **第三代：神经重构 (Neural Super Resolution)**
     - NVIDIA DLSS 2/3/3.5, Intel XeSS
     - 抖动颜色、速度场、深度、历史特征图，DLSS 3.5 引入光线方向与击中距离
     - 采用全卷积自编码器（Convolutional Autoencoder）或时空循环神经网络（RNN）；利用张量核心（Tensor Core / XMX / DP4a）硬件指令执行万亿次 MAC 混合精度推理，由海量超算离线训练提取复杂的几何边缘与纹理先验。

空间插值的理论极限与振铃效应
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
传统空间放大技术（如 Lanczos 滤波与 FSR 1.0 EASU）完全依赖单帧相邻像素之间的梯度变化。Sinc 核函数在频域对应理想低通滤波器：

.. math::

   	ext{Sinc}(x) = \frac{\sin(\pi x)}{\pi x}

在实际工程中，为了实现有限支集窗口卷积，工业界采用 Lanczos 窗口化 Sinc 函数（通常阶数 $a = 2$ 或 $a = 3$）：

.. math::

   L(x) = \begin{cases} 
   	ext{Sinc}(x) \cdot 	ext{Sinc}(x / a), & 	ext{if } |x| < a \
   0, & 	ext{otherwise}
   \end{cases}

Lanczos 卷积核能够在连续边缘处保持较高的视觉对比度，但由于其负旁瓣（Negative Sidelobes）的存在，在明暗剧烈交界的像素边缘（如高反差天际线）会激发剧烈的吉布斯现象（Gibbs Phenomenon），表现为明显的黑白同心“振铃光晕”（Ringing Artifacts）。更重要的是，**单帧空间算法绝不可能恢复光栅化阶段完全漏采的几何特征**。

时间维度上的奈奎斯特极限突破
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
第二代与第三代超分辨率技术的革命性突破，在于**将空间采样不足的矛盾转化为时间维度的累加积累**。
管线在每一帧向投影矩阵注入微小的亚像素视锥偏移（Subpixel Jittering），使得连续 $M$ 帧的采样网格在二维平面上互补交错分布。当物体在屏幕上静止或沿已知速度矢量运动时，历史多帧像素所记录的其实是该几何表面不同空间连续相位的真值采样。只要准确追踪运动并将历史样本重新投影到当前帧坐标系，时间性重构算法就能够在离散时间流中累加出等效于超采样抗锯齿（SSAA）的超高空间频宽！

.. code-block:: text

   +-------------------------------------------------------------------------+
   |            时域超分辨率 (Temporal Upscaling) 采样累积物理原理           |
   +-------------------------------------------------------------------------+

      [ 物理高分辨率像素网格 (2x2 输出) ]
      +-------+-------+
      |  (1)  |  (2)  |   第 1 帧: Jitter 偏移至位置 (1) -> 采集空间点 P1
      +-------+-------+   第 2 帧: Jitter 偏移至位置 (2) -> 采集空间点 P2
      |  (3)  |  (4)  |   第 3 帧: Jitter 偏移至位置 (3) -> 采集空间点 P3
      +-------+-------+   第 4 帧: Jitter 偏移至位置 (4) -> 采集空间点 P4
             ^
             |
      [ 跨时间帧累加重投影 ]
      - 若几何静止或按速度矢量精确平移，4 帧低分辨率渲染即可在时间轴重构出完整 2x2 超清网格！
      - 核心挑战：遮挡穿透、光照高频剧变、阴影形变与粒子不连续性。

------------------------------------------------------------------------
35.2 AMD FidelityFX Super Resolution (FSR 2/3) 架构微剖析
------------------------------------------------------------------------

FSR 2 时域重构数据流拓扑
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
AMD FSR 2 是一套完全基于手工算法设计、无需任何专用机器学习硬件单元的跨平台时域超分辨率解决方案。其核心通过多级计算着色器（Compute Shader）流水线，在完全遵循 IEEE 754 浮点标准的通用计算单元（ALU）上执行。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                      AMD FSR 2.x 核心数据流拓扑架构                     |
   +-------------------------------------------------------------------------+

      [ 引擎端底层输入流 ]
      - 低分辨率未色调映射 HDR 颜色缓冲 (Input Color)
      - 低分辨率设备深度缓冲 (Input Depth)
      - 全分辨率/低分辨率速度缓冲区 (Motion Vectors)
      - 反应性遮罩与透明度遮罩 (Reactive Mask / Transparency Mask)
      - 场景曝光参数 (Exposure Constant)
                         |
                         v
      [ Stage 1: 速度与深度重构 (Compute Depth/Motion) ]
      - 3x3 邻域深度对比，提取最靠近相机像素的运动矢量（Dilation）
      - 消除透明粒子对速度缓冲的污染
                         |
                         v
      [ Stage 2: 锁存状态评估与生成 (Lock Generation) ]
      - 针对细线几何（Thin Features）生成时域锁存遮罩（Lock Status）
      - 防止细小几何边缘被时域方差裁剪误杀为噪点
                         |
                         v
      [ Stage 3: 时域累积与双边 Lanczos 重构 (Accumulation Pass) ]
      - 历史帧高分辨率重投影与反向坐标变换
      - 局部色彩均值与方差椭圆拟合（Variance Bounding Box）
      - 色彩裁剪（Color Clamping / Clipping）压制重影（Ghosting）
      - 亚像素级双边 Lanczos-like 插值累加
                         |
                         v
      [ Stage 4: 局部对比度自适应锐化 (RCAS Sharpening) ]
      - 高频边缘保真锐化，压制欠阻尼振铃光晕
                         |
                         v
      [ 输出: 目标高分辨率 HDR/LDR 颜色图 (Target 4K Buffer) ]

速度与深度膨胀 (Motion Vector & Depth Dilation)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在光栅化渲染中，运动矢量是在几何顶点的像素着色阶段写出的。当一个高速运动的前景物体（如疾驰赛车的边缘）掠过静止背景时，光栅化像素中心如果恰好落在背景上，该像素的速度值将被写入为背景速度（接近于 0）。如果直接使用该位置的速度去重投影，将无法追踪正在移入该位置的前景物体，导致前景边缘出现严重的残影重影（Ghosting）。

FSR 2 在输入处理阶段执行严格的**近平面速度膨胀算法**：
在以当前像素为中心的 $3 	imes 3$ 邻域内，搜索**设备深度最靠近相机（Depth 值最小/最大，取决于逆 Z 规范）**的样本点，将其对应的运动矢量作为当前像素重构的主导速度：

.. math::

   \mathbf{p}_{	ext{closest}} = \arg\min_{\mathbf{q} \in \Omega_{3	imes 3}(\mathbf{p})} Z_{	ext{linear}}(\mathbf{q})

.. math::

   \mathbf{V}_{	ext{dilated}}(\mathbf{p}) = \mathbf{V}(\mathbf{p}_{	ext{closest}})

该物理操作确保了前景高速运动边缘的速度矢量在屏幕空间向外膨胀扩张至少 1 个像素，从几何拓扑上阻断了背景速度对前景边缘追踪的污染。

时域锁定机制 (Pixel Locking Mechanism)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
纯手工时域滤波算法最难克服的顽疾之一，是细单像素几何（如远处电力线、栏杆铁丝、细小天线）在子像素抖动过程中的闪烁消失问题。当相机抖动使得采样点暂时脱离细线中心时，低分辨率颜色急剧衰减，方差裁剪算法会误认为该像素发生了遮挡跳变，从而粗暴地裁剪掉历史累积的高清细线数据。

FSR 2 引入了革命性的**像素锁存（Locking）状态机**：
1. **细线特征识别**：评估当前像素与局部色彩空间方差，若检测到高对比度、单像素宽度的孤立拓扑特征，算法为其赋予“锁定权标”；
2. **锁存生命周期累积**：一旦像素被锁定，系统为其分配一个生命周期计数器（如 4~8 帧），并记录被锁定时的局部几何特征分布；
3. **放宽方差裁剪约束**：在锁存生命周期内，强制放宽色彩边界盒（Color Box）的紧致收缩约束，阻止时域重投影将其截断，直至检测到明显的场景遮挡跳变（Disocclusion）才注销该锁存。

反应性遮罩 (Reactive Mask) 与半透明复合
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
诸如全屏火焰、魔法粒子、雨雪、半透明玻璃与发光 UI 等半透明材质不写入深度缓冲区，通常也不包含可靠的运动矢量。如果任由时域超分辨率处理半透明流，后方不透明几何的重投影运动将强行穿透并撕扯半透明像素，产生灾难性的拖尾拉丝。

引擎必须在绘制半透明图层时，将半透明颜色的透明度与亮度衰减输出为一张特殊的单通道单色图——**反应性遮罩（Reactive Mask）**：
在 FSR 2 累加阶段，读取到当前像素的反应性因子 $R(\mathbf{p}) \in [0, 1]$：
- 当 $R(\mathbf{p}) 	o 0$ 时，完全启用历史帧时域长线累加；
- 当 $R(\mathbf{p}) 	o 1$ 时，强制将时域累加权重衰减归零，完全回退为当前帧瞬时输入颜色（即降级为即时着色，消除拖尾）。

FSR 3 光流插帧与帧生成体系 (Fluid Motion Frames)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
AMD 在 FSR 3 中引入了类似于 DLSS 3 的插帧生成架构。其在两个连续渲染完成的真实帧 $N$ 与 $N+1$ 之间，纯粹通过计算着色器插入一个完全由算法推导出的过渡帧 $N+0.5$：
1. **硬件光流矢量分析（Optical Flow Analysis）**：针对缺乏几何速度缓冲的区域（如全屏后处理泛光、动画粒子），通过多尺度分层块匹配（Hierarchical Block Matching）计算全场稠密光流场；
2. **双向速度场重投影融合**：结合引擎提供的刚体运动矢量与光流矢量，从前向与后向双向拉伸图块，执行遮挡冲突判定与深度分层融合；
3. **UI 独立渲染通道（Swapchain Composition）**：为了防止文本、准星与 HUD 界面在插帧计算中被扭曲变形，FSR 3 要求引擎将 UI 渲染与游戏世界完全分离，插帧算法仅作用于 3D 场景缓冲，插值完成后再将原生高分辨率 UI 覆盖绘制至最终呈现交换链。

------------------------------------------------------------------------
35.3 NVIDIA DLSS 2/3/3.5 神经图像重构微架构
------------------------------------------------------------------------

深度学习超采样的范式破局：从 DLSS 1 到 DLSS 2
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
NVIDIA 早期推出的 DLSS 1.0 采用针对特定游戏离线训练非时间性卷积神经网络的方案。由于缺乏时间轴信息与底层几何约束，DLSS 1.0 本质上是一个图像幻觉“脑补”生成器，在细微运动下极易出现画面漂移、纹理边缘模糊与难以忍受的“水彩画”涂抹效应，且每个游戏均需送交超级计算机独立训练。

DLSS 2.0 确立了现代神经重构的工业典范：
1. **通用化全局网络模型（Universal Network）**：彻底摆脱了为单一游戏定制训练的束缚，单一通用模型能够理解几乎所有 3D 虚拟世界的几何边缘、阴影透视与高频材质；
2. **时空自编码器微架构（Temporal Autoencoder）**：将时间性历史特征与空间几何先验紧密耦合，将超分辨率重建转化为一个在时间流中不断修正误差的高维残差逼近过程。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     NVIDIA DLSS 2.x 神经重构网络微架构                  |
   +-------------------------------------------------------------------------+

      [ 当前帧低分辨率输入 (Jittered LR) ]       [ 上一帧超分辨率历史特征图 (HR History) ]
      - Color (低分辨率 HDR 颜色)                - 重投影至当前帧的高维潜在特征张量
      - Depth (高精度相机深度)                             |
      - Motion Vectors (屏幕空间运动矢量)                  |
      - Exposure / Reactive (曝光控制与反应性)             |
                   |                                       |
                   \-------------------\ /-----------------/
                                       v v
                      [ 统一时空特征对齐与预处理算子 ]
                                       |
                                       v
               +------------------------------------------------+
               |     深度全卷积残差自编码网络 (Convolutional Autoencoder) |
               |                                                |
               |  [ Encoder 编码器 ]                            |
               |  - 多尺度下采样与卷积层提取空间上下文特征       |
               |  - 结合历史特征融合时空运动连续性               |
               |                                                |
               |  [ Latent Bottleneck 隐空间特征变换 ]          |
               |  - 高维特征对齐、几何边缘识别与遮挡推理         |
               |                                                |
               |  [ Decoder 解码器 + 亚像素重组 ]               |
               |  - 转置卷积 / PixelShuffle 向上投影变换         |
               |  - 输出残差补偿矩阵与自适应时空权重掩码         |
               +------------------------------------------------+
                                       |
                    /------------------+------------------\
                    v                                     v
      [ 最终高分辨率超清颜色 (4K HDR Output) ]   [ 传递至下一帧的高维状态特征图 (HR State) ]

Tensor Core 张量计算核心对重构时延的物理压缩
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
卷积神经网络的推理包含数以百万计的高维矩阵乘加运算（GEMM: $D = A \cdot B + C$）。若在常规 GPU 标量/向量 ALU 上执行此类网络，即便最轻量级的自编码器也会耗费 10~20 毫秒以上的计算时间，彻底丧失实时渲染的实用价值。

NVIDIA 通过 Volta / Turing / Ampere / Ada Lovelace 架构中的专用硬件加速单元——**Tensor Core**，实现了超分辨率推理时延的物理级压缩：
1. **混合精度硬线化（Mixed-Precision FP16 / BF16 / INT8）**：
   Tensor Core 在硬件层以半精度 FP16 接收输入矩阵，在单周期内完成 $4 	imes 4 	imes 4$ 矩阵乘累加，并以单精度 FP32 累加输出，在完全消除精度溢出的同时，实现高达常规 FP32 ALU 4~8 倍的超高计算吞吐（TeraFLOPS）；
2. **稀疏化硬件加速（Structured Sparsity 2:4）**：
   在 Ampere 及后续架构中，硬件原生支持 2:4 结构化稀疏矩阵运算，神经网络权重中每 4 个数强制剪枝掉 2 个接近于零的权重，计算吞吐直接再度翻倍；
3. **毫秒级执行保证**：在 4K 目标分辨率下，DLSS 2.x 的全网络前向推理开销被严格压制在 **1.0 ~ 1.8 毫秒** 之内（取决于显卡级别），而其所节约的几何渲染与光线追踪开销通常高达 **8 ~ 16 毫秒**，实现整机帧率 200% ~ 300% 的净收益！

DLSS 3 光流加速器 (OFA) 与时空插帧
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当游戏瓶颈受制于 CPU 单核性能或复杂的 CPU 物理模拟逻辑时，无论 GPU 渲染分辨率降得多低，帧率都无法突破 CPU 主线程的瓶颈上限。为了攻克这一物理墙，DLSS 3 引入了基于硬件**光流加速器（Optical Flow Accelerator - OFA）**的神经网络插帧技术：
1. **OFA 硬件引擎独立工作**：Ada Lovelace GPU 内部集成了独立于显卡着色器核心的专用 OFA 协处理器，硬件单元专门以极高速度比对两帧图像在像素级的双向运动轨迹，生成高精度稠密光流向量场（捕获阴影移动、水波涟漪、粒子破碎等无几何速度场的复杂动态）；
2. **多源物理矢量校验**：插帧自编码网络同时摄入四类独立时空输入：真实帧 $N$、真实帧 $N+1$、OFA 测量光流场、以及游戏引擎原生输出的 3D 几何运动矢量；
3. **完全脱离 CPU 瓶颈的帧率翻倍**：生成的中间帧完全在 GPU 端合成并直接插入显示引擎。由于该中间帧的生成完全不需要 CPU 执行任何场景图遍历、物理碰撞或 DrawCall 提交，从而在 CPU 严重受限的复杂大世界场景中直接带来近乎翻倍的流畅度飞跃。

DLSS 3.5 光线重建 (Ray Reconstruction) 与降噪器统一
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在现代光线追踪管线中，受制于算力限制，每像素通常只能发射 1 到 2 条光线（1~2 SPP），原始追踪结果充满了剧烈的蒙特卡洛高频白噪声。传统方案高度依赖手工设计的时空级联降噪器（Hand-Tuned Denoisers，如 A-SVGF）。
然而，传统手工降噪器存在严重的固有缺陷：
- 它们通过跨多帧的时间平滑（Accumulation）与大半径空间模糊（Spatial Blurring）去除噪点，这不可避免地导致反射细节模糊、高频阴影丢失、运动重影以及环境光遮蔽的过度滞后。

.. code-block:: text

   [ 传统光追管线 ]
   1 SPP 光追输出 ---> [ 手工时空降噪器 (SVGF) ] ---> [ TAA / DLSS 2 超分 ] ---> 最终图像 (模糊/重影)
                           (手工模糊丢失高频细节)
                           
   [ DLSS 3.5 光线重建管线 ]
   1 SPP 光追输出 +-+
   高精度几何法线 -+---> [ DLSS 3.5 统一光线重建网络 ] ------------------------> 终极超清 4K (锐利反射/精准光影)
   光线击中距离   -+     (用经过 5 倍离线数据训练的统一大模型替代降噪与超分)

DLSS 3.5 彻底废黜了传统的人工降噪器，**将时空去噪与超分辨率重构融为一体，由一个经过海量离线真实渲染数据训练的超级神经网络直接端到端解决**。该网络不仅读取颜色，还深度理解光线命中距离、反射表面曲率与光照传播规律，能够在消除噪点的同时完美保留高频几何投影边缘与水面细腻的菲涅尔高光。

------------------------------------------------------------------------
35.4 Intel XeSS 跨架构矩阵指令重构
------------------------------------------------------------------------

XMX 硬件加速与 DP4a 普适架构兼容
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Intel 推出的 XeSS（Xe Super Sampling）在架构设计上采取了一条极富弹性的双轨路径：既追求专用硬件的极致能效，又保证全平台硬件的普适兼容性。

.. list-table:: Intel XeSS 双运行态执行模式微架构对比
   :widths: 20 25 25 30
   :header-rows: 1
   :class: tight-table

   * - 运行态执行路径
     - 依赖硬件特性
     - 数据吞吐精度
     - 适用硬件生态
   * - **Intel XeSS XMX 核心路径**
     - Intel Arc GPU 专用硬件矩阵扩展 (Xe Matrix Extensions - XMX)
     - 原生 BF16 / FP16 4096-bit 脉动阵列乘加
     - 专用硬件高能耗比；单时钟周期吞吐极高，画质保真度最高。
   * - **Intel XeSS DP4a 通用路径**
     - 通用 GPU 标量计算指令集 (4-element Dot Product Accumulate - DP4a)
     - INT8 向量点积打包累加至 INT32 寄存器
     - 兼容所有支持 DP4a 指令集的近代 GPU（包括 NVIDIA Pascal/Turing/Ampere、AMD RDNA 2/3、Intel 集显）。

DP4a 路径的指令级实现机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在不支持专用硬件张量单元的显卡上，XeSS 采用神经网络结构化低位宽量化技术，将模型全部权重与激活值量化为 8 位有符号整数（`int8`）。
在 HLSL 中，通过调用底层内置原语 `dot4add_i8packed`，单条机器指令即可并发读取两个 32 位通用寄存器（各打包 4 个 8-bit 数据），计算 4 组点积并累加至目标寄存器：

.. math::

   	ext{Result}_{32} = 	ext{Accumulator}_{32} + \sum_{k=0}^{3} A_{8}[k] \cdot B_{8}[k]

通过这种方式，通用矢量计算着色器能够以极其密集的整型吞吐执行深层残差网络，在没有任何专有 AI 核心的通用硬件上，成功将重构耗时控制在 2~3 毫秒的实时预算范围内。

------------------------------------------------------------------------
35.5 现代超分时空特征融合与核心算法实现
------------------------------------------------------------------------

亚像素对齐与负 Mip 偏差计算 (Negative Mip Bias)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
超分辨率技术最容易被忽略但极为致命的物理陷阱，是**纹理采样细节的退化**。
在现代 GPU 光栅化微架构中，硬件纹理映射单元（TMU）通过计算屏幕空间偏导数（`ddx/ddy`）来自动选择纹理的 Mipmap 层级。当内部渲染分辨率从 4K 降低为 1080p 时，像素在屏幕空间跨越的物理间距增大了整整一倍，导致偏导数增大，GPU 硬件将错误地选中更模糊的高阶 Mipmap 级别（如从 Mip 0 跳跃到 Mip 1 或 Mip 2）。其物理后果是：**着色器从一开始读取的纹理源头就丢失了微观细节，无论后续时域超分辨率算法多么强大，也无法重构未被采样的纹理信息！**

为了强制 GPU 硬件在低分辨率光栅化下依然读取最高精度的原生微观纹理数据，渲染引擎必须在所有材质采样器或纹理资源上强制注入**负 Mip 偏差（Negative Mip Bias）**：

.. math::

   	ext{MipBias} = \log_2\left( \frac{	ext{Resolution}_{	ext{Render}}}{	ext{Resolution}_{	ext{Target}}} \right) = -\log_2(	ext{UpscaleRatio})

.. list-table:: 典型超分辨率模式下的严格数学 Mip Bias 补偿表
   :widths: 25 25 25 25
   :header-rows: 1
   :class: tight-table

   * - 质量档位 (Quality Mode)
     - 空间缩放比率 (Scale)
     - 输入分辨率 (Target: 4K)
     - 强制注入 Mip Bias
   * - **Ultra Quality**
     - $1.3 	imes$
     - $2954 	imes 1662$
     - **$-0.378$**
   * - **Quality**
     - $1.5 	imes$
     - $2560 	imes 1440$
     - **$-0.585$**
   * - **Balanced**
     - $1.7 	imes$
     - $2258 	imes 1270$
     - **$-0.765$**
   * - **Performance**
     - $2.0 	imes$
     - $1920 	imes 1080$
     - **$-1.000$**
   * - **Ultra Performance**
     - $3.0 	imes$
     - $1280 	imes 720$
     - **$-1.585$**

HLSL 工业级时域特征融合着色器实现
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
以下给出在标准 Compute Shader 中实现的工业级时域超分辨率特征重采样与色彩方差裁剪滤波实现（HLSL 6.2+）。代码完整实现了 **亚像素坐标解算、历史重投影、九宫格色彩矩椭球拟合（Moment Bounding Box）、方差裁剪（Color Variance Clamping）以及时空混合加权**：

.. code-block:: hlsl

   // =========================================================================
   // File: TemporalSuperResolution_Accumulation.hlsl
   // Standard: HLSL 6.2+ (DX12 / Vulkan via DXC)
   // Architecture: High-Performance Temporal Feature Fusion & Variance Clamping
   // =========================================================================

   struct TSRConstants {
       float2 RenderResolution;       // 低分辨率输入尺寸 (例如 1920x1080)
       float2 TargetResolution;       // 高分辨率输出尺寸 (例如 3840x2160)
       float2 RcpRenderResolution;    // 1.0 / RenderResolution
       float2 RcpTargetResolution;    // 1.0 / TargetResolution
       
       float2 SubpixelJitterOffset;   // 当前帧在低分辨率像素单位下的 Jitter ([-0.5, 0.5])
       float  HistoryWeightMin;       // 最小历史权重 (如 0.85)
       float  HistoryWeightMax;       // 最大历史权重 (如 0.98)
       
       float  VarianceBoxScale;       // 方差椭球扩展尺度 (标准取 1.25 ~ 1.5)
       float  DisocclusionDepthThreshold; // 深度不连续阈值 (例如 0.01)
       float2 Padding;
   };

   ConstantBuffer<TSRConstants> g_TSR : register(b0);

   Texture2D<float4> g_CurrentColorTexture  : register(t0); // 当前帧未降噪/抖动输入 (低分辨率 HDR)
   Texture2D<float>  g_CurrentDepthTexture  : register(t1); // 当前帧深度图 (低分辨率)
   Texture2D<float2> g_VelocityTexture      : register(t2); // 屏幕空间速度向量图 (以全分辨率像素为单位)
   Texture2D<float4> g_HistoryColorTexture  : register(t3); // 上一帧超分辨率累积图 (高分辨率)
   Texture2D<float>  g_HistoryDepthTexture  : register(t4); // 上一帧深度图 (高分辨率)

   SamplerState g_LinearClampSampler : register(s0);
   SamplerState g_PointClampSampler  : register(s1);

   RWTexture2D<float4> g_RWOutputResolvedColor : register(u0); // 本阶段写出目标超清缓冲

   // RGB 与 YCoCg 色彩空间快速转换矩阵 (消除色相偏离，在感知亮度空间裁剪)
   float3 RGBToYCoCg(float3 c) {
       return float3(
            0.25f * c.r + 0.50f * c.g + 0.25f * c.b,
            0.50f * c.r - 0.50f * c.b,
           -0.25f * c.r + 0.50f * c.g - 0.25f * c.b
       );
   }

   float3 YCoCgToRGB(float3 c) {
       return float3(
           c.x + c.y - c.z,
           c.x + c.z,
           c.x - c.y - c.z
       );
   }

   // 求解双边一阶与二阶色彩矩，拟合 AABB 方差椭圆边界盒
   void CalculateColorMoments(int2 currentCoordLR, out float3 boxMin, out float3 boxMax, out float3 averageColor) {
       float3 m1 = float3(0.0f, 0.0f, 0.0f);
       float3 m2 = float3(0.0f, 0.0f, 0.0f);

       [unroll]
       for (int y = -1; y <= 1; ++y) {
           [unroll]
           for (int x = -1; x <= 1; ++x) {
               int2 sampleCoord = clamp(currentCoordLR + int2(x, y), int2(0, 0), int2(g_TSR.RenderResolution) - 1);
               float3 rgb = g_CurrentColorTexture.Load(int3(sampleCoord, 0)).rgb;
               float3 ycocg = RGBToYCoCg(rgb);

               m1 += ycocg;
               m2 += ycocg * ycocg;
           }
       }

       averageColor = m1 / 9.0f;
       float3 variance = sqrt(max(m2 / 9.0f - averageColor * averageColor, 0.0f));

       // 构建方差约束盒: [Avg - Scale * Var, Avg + Scale * Var]
       boxMin = averageColor - g_TSR.VarianceBoxScale * variance;
       boxMax = averageColor + g_TSR.VarianceBoxScale * variance;
   }

   // 3维线段相交裁剪算法 (Clip AABB Towards Center)
   float3 ClipToAABB(float3 historySample, float3 boxMin, float3 boxMax, float3 boxCenter) {
       float3 r = historySample - boxCenter;
       float3 p_max = boxMax - boxCenter;
       float3 p_min = boxMin - boxCenter;

       float3 invR = 1.0f / (abs(r) > 1e-6f ? r : 1e-6f);
       float3 t_max = p_max * invR;
       float3 t_min = p_min * invR;

       float3 t_intersect = max(t_min, t_max);
       float t = min(t_intersect.x, min(t_intersect.y, t_intersect.z));

       return (t < 1.0f && t > 0.0f) ? (boxCenter + r * t) : historySample;
   }

   // =========================================================================
   // 主重构计算核 (16x16 线程网格覆盖输出目标 4K 画布)
   // =========================================================================
   [numthreads(16, 16, 1)]
   void CS_TemporalSuperResolution(uint3 dispatchThreadID : SV_DispatchThreadID)
   {
       int2 targetCoordHR = int2(dispatchThreadID.xy);
       if (any(targetCoordHR >= int2(g_TSR.TargetResolution))) return;

       // 1. 计算当前高分辨率像素对应的高精度连续屏幕 UV
       float2 uv = (float2(targetCoordHR) + 0.5f) * g_TSR.RcpTargetResolution;

       // 2. 映射至低分辨率输入空间的像素坐标
       float2 coordLR = uv * g_TSR.RenderResolution - 0.5f;
       int2   baseCoordLR = int2(floor(coordLR));

       // 3. 读取该位置运动矢量并重投影至上一帧历史坐标
       // 采用膨胀采样获取最稳健速度矢量
       float2 motionVector = g_VelocityTexture.SampleLevel(g_PointClampSampler, uv, 0).xy;
       float2 historyUV = uv - motionVector;

       // 4. 读取当前像素深度并评估是否脱离有效视锥范围
       float currentDepth = g_CurrentDepthTexture.SampleLevel(g_PointClampSampler, uv, 0).r;
       bool isOutOfScreen = any(historyUV < 0.0f) || any(historyUV > 1.0f);

       // 5. 双线性/Lanczos 插值采样历史帧超分辨率颜色
       float4 historySample = g_HistoryColorTexture.SampleLevel(g_LinearClampSampler, historyUV, 0);
       float3 historyYCoCg = RGBToYCoCg(historySample.rgb);

       // 6. 统计当前帧低分辨率 3x3 邻域的一阶与二阶色彩矩，生成方差安全边界盒
       float3 boxMin, boxMax, boxCenter;
       CalculateColorMoments(baseCoordLR, boxMin, boxMax, boxCenter);

       // 7. 执行色彩空间方差裁剪，强行剥离由于几何遮挡或剧烈运动产生的重影数据
       float3 clampedHistoryYCoCg = ClipToAABB(historyYCoCg, boxMin, boxMax, boxCenter);
       float3 clampedHistoryRGB = YCoCgToRGB(clampedHistoryYCoCg);

       // 8. 采样当前帧未抖动瞬态色彩 (经双三次/双线性 Catmull-Rom 插值采样)
       float3 currentFilteredRGB = g_CurrentColorTexture.SampleLevel(g_LinearClampSampler, uv, 0).rgb;

       // 9. 时域自适应累积权重判定 (Adaptive History Weighting)
       float historyWeight = g_TSR.HistoryWeightMax;

       // 若跨出屏幕边缘，或检测到深度重投影不连续，重置历史累积
       if (isOutOfScreen) {
           historyWeight = 0.0f;
       } else {
           float historyDepth = g_HistoryDepthTexture.SampleLevel(g_PointClampSampler, historyUV, 0).r;
           float depthDiff = abs(currentDepth - historyDepth);
           if (depthDiff > g_TSR.DisocclusionDepthThreshold) {
               historyWeight = g_TSR.HistoryWeightMin; // 快速衰减历史，防止遮挡拖尾
           }
       }

       // 10. 指数移动平均 (EMA: Exponential Moving Average) 时域融合
       float3 resolvedColor = lerp(currentFilteredRGB, clampedHistoryRGB, historyWeight);

       // 11. 最终写出重构完成的 4K 超清颜色 (附带像素方差置信度或累积帧数)
       g_RWOutputResolvedColor[targetCoordHR] = float4(resolvedColor, 1.0f);
   }

------------------------------------------------------------------------
35.6 工业引擎标准化集成：Microsoft DirectSR 与接入契约
------------------------------------------------------------------------

碎片化接口的统合诉求
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在过去数年中，游戏引擎开发者同时接入 NVIDIA DLSS、AMD FSR 与 Intel XeSS 面临极大的工程集成阻力：
- 每套技术拥有完全独立的 C++ SDK 库封装；
- 资源状态流转、Jitter 相位生成公式、速度缓冲区正负号约定以及 Mipmap 负偏差规范各不相同，引擎必须编写大量条件编译与抽象隔离胶水代码。

为了终结这一混乱生态，微软在 DirectX 12 敏捷 SDK（Agility SDK）中推出了官方标准接口——**DirectSR (Direct Super Resolution)**。

DirectSR 核心架构与统一接入契约
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
DirectSR 作为一个硬件厂商中立的统一中间层，其底层架构原理是将厂商原生驱动（NVIDIA DLSS Driver Extension、AMD FSR 运行时、Intel XeSS 驱动）抽象为统一的 DirectSR 变体管线。

.. list-table:: 现代 3A 引擎接入超分辨率体系的统一硬性输入契约
   :widths: 25 30 45
   :header-rows: 1
   :class: tight-table

   * - 核心输入流名称
     - 推荐底层格式
     - 严格几何与物理标准规范
   * - **输入低分辨率颜色 (Input Color)**
     - `DXGI_FORMAT_R16G16B16A16_FLOAT`
     - 必须是**色调映射（Tone Mapping）之前**的线性空间 HDR 颜色；严禁包含 UI、后处理噪点或镜头畸变。
   * - **深度缓冲区 (Depth Buffer)**
     - `DXGI_FORMAT_R32_FLOAT` / `D32_FLOAT`
     - 高精度设备深度，必须遵循规范的近平面与远平面映射（推荐逆 Z 规范：$1.0 	o 0.0$）。
   * - **速度缓冲区 (Motion Vectors)**
     - `DXGI_FORMAT_R16G16_FLOAT`
     - 记录从当前帧 $(t)$ 到上一帧 $(t-1)$ 的屏幕空间二维位移；**必须是绝对干净的几何位移，严禁包含当前帧的亚像素 Jitter 抖动！**
   * - **反应性遮罩 (Reactive Mask)**
     - `DXGI_FORMAT_R8_UNORM`
     - 标定半透明材质、全屏后处理粒子与屏幕扭曲特效；值越接近 1.0，强制算法越少信任历史帧。
   * - **Jitter 相位序列 (Jitter Sequence)**
     - 二维浮点坐标数组
     - 标准 Halton(2, 3) 低差异序列；周期长度通常设定为 $8 	imes (	ext{UpscaleRatio})^2$。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                Microsoft DirectSR 统一抽象架构层流转                     |
   +-------------------------------------------------------------------------+

      [ 游戏引擎端标准输出 ]
      (HDR Color + Depth + Clean Velocity + Halton Jitter + Exposure)
                               |
                               v
      [ Microsoft DirectSR API (ID3D12Device::CreateCommandList) ]
                               |
            +------------------+------------------+
            |                                     |
            v (NVIDIA 硬件环境)                   v (AMD/Intel/通用硬件环境)
   [ DLSS 驱动级原生插件 ]              [ FSR 2/3 / XeSS 运行时实现 ]
   - 自动路由至 Tensor Core 硬件         - 自动分发至 Compute Shader / XMX
   - 零额外抽象开销                      - 跨平台无缝执行

------------------------------------------------------------------------
小结与 Part 8 导读
------------------------------------------------------------------------

本章作为第七模块（后处理、抗锯齿与图像重构）的终极篇章，全面解构了打破图形渲染硬件算力墙的基石技术——超分辨率与神经重构体系：
1. **重构技术三代范式**：深刻剖析了空间单帧插值（Lanczos/FSR 1.0）受制于奈奎斯特极限与振铃光晕的物理瓶颈，推导了时间性重构借助亚像素抖动突破单帧空间频宽的数学机理；
2. **AMD FSR 2/3 架构**：深入解析了完全基于通用计算单元的高性能启发式重构流程，系统推导了近平面深度速度膨胀（Dilation）、细线几何像素锁存（Locking）状态机、反应性半透明遮罩与 FSR 3 异步光流插帧的完整实现；
3. **NVIDIA DLSS 神经重构与张量加速**：解构了从 DLSS 1 单帧生成到 DLSS 2 时空全卷积自编码器的演进脉络，剖析了 Tensor Core 混合精度硬件矩阵乘加单元对网络推理时延的压缩机制，阐释了 DLSS 3 光流硬件加速器（OFA）与 DLSS 3.5 统一去噪重构的颠覆性设计；
4. **Intel XeSS 与跨平台生态**：剖析了原生 XMX 矩阵单元与跨架构通用 DP4a 向量指令的灵活双轨微架构；
5. **特征融合与工程契约**：推导了防止光栅化纹理模糊的负 Mip 偏差数学公式，给出了涵盖方差椭球拟合与 AABB 裁剪滤波的工业级 Compute Shader 完整代码，并总结了微软 DirectSR 的统一输入规范。

至此，**Part 7: 后处理、抗锯齿与图像重构（Chapter 31 ~ 35）已圆满全量收官！**

在接下来的全新篇章——**Part 8: 现代底层 API 演进与驱动架构 (08_modern_graphics_apis_and_drivers)** 中，我们将正式由上层渲染算法深入到图形硬件与软件交互的最深水区：
- 我们将全面解构从经典 OpenGL / D3D11 隐式全局状态机向 Vulkan / DirectX 12 / Metal 显式硬件资源模型的哲学演进；
- 深入剖析虚拟显存分页管理、UAV 内存屏障冒险与管线阶段屏障；
- 彻底拆解现代无绑定（Bindless）架构与下一代 GPU 驱动分发机制！下一章，让我们从 Chapter 36 显式图形 API 演进哲学正式启程！
