========================================================================
Chapter 33: 时间性抗锯齿 (TAA)：历史帧重投影、邻域色彩裁剪 (Color Clamping) 与抖动
========================================================================

.. note:: 前置背景与认知承接
   在前一章（Chapter 32）中，我们系统剖析了后处理管线中两项关键的光学拟真阶段——物理泛光（Bloom）的 Dual-Kawase 滤波金字塔与薄透镜弥散圆（CoC）景深散景架构。通过在 HDR 线性无界空间模拟透镜杂质散射与光圈离焦，渲染流水线有效消除了人工图形生成的冰冷生硬感。

   然而，当代实时渲染架构在几何光栅化、物理光照与材质着色阶段仍面临着另一个根本性的物理限制：**离散空间采样定理（Nyquist-Shannon Sampling Theorem）的下采样混叠（Aliasing）**。当三维场景中的亚像素多边形边缘、微细几何（如树叶、栏杆、头发）、法线贴图高频细节以及粗糙度极低的几何镜面高光在屏幕离散像素网格上光栅化或着色时，信号高频分量超过了像素采样频率的二分之一，不可避免地折叠为严重的锯齿（Spatial Aliasing）。在动态摄像机或物体位移下，这些锯齿在时域上表现为剧烈的高频爬行闪烁（Crawling Edges / Specular Shimmering）。

   传统的超采样（SSAA）开销巨大，而多重采样抗锯齿（MSAA）因与现代延迟着色（Deferred Shading）、计算着色器光照及屏幕空间特效的 G-Buffer 架构存在天然的显存带宽冲突，且完全无法抑制着色器内部高光锯齿，已在 3A 工业级管线中被边缘化。形态学抗锯齿（FXAA / SMAA）作为纯空间后处理边缘模糊算法，由于缺失几何信息与亚像素数据，无法抑制几何运动时的时域闪烁。

   **时间性抗锯齿（Temporal Anti-Aliasing - TAA）** 通过引入时间维度，将空间上的超高密度多重采样分摊到若干个连续的历史帧中（Temporal Amortization），配合低差异亚像素相机抖动序列（Halton / Sobol）、运动矢量速度缓冲区（Velocity Buffer）以及历史帧重投影与邻域色彩裁剪（Color Clamping / Clipping），在几乎不增加几何光栅化开销的前提下实现了接近 $8	imes \sim 16	imes$ SSAA 的平滑边缘与卓越的时域稳定性。本章将系统解构 TAA 的数学机理、投影抖动、速度场重投影、色彩空间方差裁剪、抗鬼影微架构及工业级 Compute Shader 完整工程实现。

------------------------------------------------------------------------
33.1 空间采样定理与时间性超采样的数学本质
------------------------------------------------------------------------

混叠的物理与数学成因
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
根据奈奎斯特-香农采样定理，要无失真地重构连续二维连续图像信号 $f(x, y)$，采样频率 $f_s$ 必须严格大于信号最高空间频率 $f_{\max}$ 的两倍（$f_s > 2 f_{\max}$）。

在光栅化图形流水线中，多边形三角形边缘在空间上呈现为阶跃函数（Heaviside Step Function）：

.. math::

   H(x) = \begin{cases} 1, & x \ge 0 \ 0, & x < 0 \end{cases}

阶跃函数的傅里叶变换具有无限宽广的频域响应（频谱衰减仅为 $1/\omega$）。由于显示器物理像素网格的采样频率 $f_s = 1/\Delta x$ 是严格有限的，三角形边缘的高频无限分量必然发生频谱混叠，高频能量折叠映射到低频区域，形成阶梯状锯齿。

更严重的问题出现在时域维度。当连续函数随时间 $t$ 变化（摄像机移动或物体运动）时，静态空间锯齿在连续帧之间发生周期性相位跳变，人眼视觉暂留系统对这种明暗突变极其敏感，感知为边缘闪烁（Crawling Edges）与高光火花（Specular Fireflies）。

主流抗锯齿技术物理特性全景对比
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
.. list-table:: 现代图形抗锯齿方案微架构与物理特性对比
   :widths: 18 18 20 22 22
   :header-rows: 1
   :class: tight-table

   * - 抗锯齿技术
     - 执行阶段
     - 显存与计算开销
     - 抑制对象
     - 时域稳定性与局限
   * - **SSAA (超采样)**
     - 光栅化 + 着色
     - 极高 ($N 	imes$ 像素着色器运算与显存)
     - 几何边缘 + 着色器高光
     - 极高；现代实时 3A 无法承受其计算负载
   * - **MSAA (多重采样)**
     - 光栅化 ROP
     - 中等 ($N 	imes$ 深度/覆盖率，单次着色)
     - 仅几何三角形边缘
     - 与延迟渲染 G-Buffer 冲突，无法处理高光与 Alpha 贴图锯齿
   * - **FXAA / SMAA**
     - 空间后处理
     - 极低 (单 Pass 全屏后处理)
     - 基于对比度检测的几何边缘
     - 无时域累积，物体运动时高频闪烁严重，画面易整体泛糊
   * - **TAA (时间性抗锯齿)**
     - 时域后处理
     - 低 (1 次历史重投影 + 滤波卷积)
     - 几何边缘 + 材质高光 + 噪点重构
     - 时域极其稳定，但存在鬼影（Ghosting）与动态模糊风险

时间性超采样 (Temporal Supersampling) 的数学模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
TAA 的核心思想是将单帧高密度的空间采样点分布于连续的 $N$ 个时间帧中：

设当前帧为 $t$，在第 $t$ 帧的相机投影矩阵中人为注入一个微小的二维亚像素偏移量 $\mathbf{j}_t = (\Delta x_t, \Delta y_t)$，其中 $\Delta x_t, \Delta y_t \in [-0.5, 0.5]$ 像素。

在时间维度上，若物体与摄像机保持相对静止，连续 $N$ 帧在像素 $(x, y)$ 处采样的物理位置等价于一个拥有 $N$ 个样本点的规则/拟随机超采样网格。最终像素颜色由当前帧采样与历史累积帧通过一阶指数移动平均（Exponential Moving Average - EMA）递归合成：

.. math::

   S_t(\mathbf{p}) = \alpha \cdot C_t(\mathbf{p}) + (1 - \alpha) \cdot S_{t-1}(\mathbf{p} - \mathbf{v}_t(\mathbf{p}))

其中：
- $S_t(\mathbf{p})$：第 $t$ 帧像素 $\mathbf{p}$ 的最终抗锯齿输出颜色；
- $C_t(\mathbf{p})$：第 $t$ 帧当前渲染目标经加权滤波重构后的颜色样本；
- $\mathbf{v}_t(\mathbf{p})$：像素 $\mathbf{p}$ 从当前帧 $t$ 回溯至前一帧 $t-1$ 的二维屏幕空间运动矢量（Motion Vector）；
- $S_{t-1}(\dots)$：前一帧历史颜色缓冲区在回溯位置的采样结果；
- $\alpha \in [0.04, 0.12]$：当前帧与历史帧的时域混合系数（Feedback Factor）。当 $\alpha = 0.1$ 时，历史帧等效保留了约 10 帧的时域信息累积。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     TAA 在现代渲染管线中的数据流拓扑架构                |
   +-------------------------------------------------------------------------+

      [ 场景相机参数 ] ---> [ 注入 Halton 亚像素抖动 (Jitter) ]
                                      |
                                      v
      [ G-Buffer Pass / 延迟光照 Pass ] ------> [ 速度缓冲区 (Velocity Buffer) ]
      (渲染带有亚像素抖动的 HDR 场景颜色)                 (生成精确屏幕运动矢量)
                    |                                             |
                    v                                             v
      [ 当前帧 HDR 颜色 (带有 Jitter) ]               [ 历史帧 HDR 颜色缓冲区 ]
                    |                                             |
                    +--------------------+------------------------+
                                         |
                                         v
                         [ TAA 时域重构计算着色器 ]
                         +-----------------------------------+
                         | 1. 速度矢量回溯采样历史帧          |
                         | 2. 3x3 邻域色彩提取与 YCoCg 转换   |
                         | 3. 方差色彩裁剪 (Variance Box)     |
                         | 4. Catmull-Rom 双三次历史重采样    |
                         | 5. EMA 指数时域混合累加           |
                         +-----------------------------------+
                                         |
                                         +---> [ 写回历史缓冲区 (History Buffer) ]
                                         v
                         [ 锐化后处理 Pass (CAS / RCAS) ]
                                         |
                                         v
                         [ 输出最终无锯齿稳定图像 (To Bloom/DoF/Tonemapping) ]

------------------------------------------------------------------------
33.2 亚像素相机抖动序列与投影矩阵调制
------------------------------------------------------------------------

低差异序列 (Low-Discrepancy Sequence) 选择
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
为了在有限的时域累积窗口内以最快速度均匀覆盖像素内部空间，亚像素抖动向量绝对不能使用伪随机数（White Noise，其空间聚集与间隙会导致严重的噪点和采样效率低下）。工业级 TAA 严格采用确定性的 **低差异准随机序列**：

1. **Halton 序列**：基于不同互质基数（Prime Bases）的反向基数映射算法构建。在二维平面上，通常采用基底为 2 和 3 的 $	ext{Halton}(2, 3)$ 序列；
2. **R2 Weyl 序列**：基于黄金分割比与塑性数（Plastic Number）构建的加法重整化序列，分布极其均匀且计算开销极低。

基于基底 $b$ 的 Halton 逆基数函数 $\Phi_b(i)$ 定义为：将非负整数索引 $i$ 展开为 $b$ 进制数，再将其关于小数点对称翻转至 $[0, 1)$ 区间：

.. math::

   i = \sum_{k=0}^{M} a_k b^k \quad \Longrightarrow \quad \Phi_b(i) = \sum_{k=0}^{M} a_k b^{-(k+1)}

以基底 2 为例：
- $i=1 \Rightarrow 1_2 \Rightarrow 0.1_2 = 1/2 = 0.5$；
- $i=2 \Rightarrow 10_2 \Rightarrow 0.01_2 = 1/4 = 0.25$；
- $i=3 \Rightarrow 11_2 \Rightarrow 0.11_2 = 3/4 = 0.75$；
- $i=4 \Rightarrow 100_2 \Rightarrow 0.001_2 = 1/8 = 0.125$。

.. list-table:: 标准 8 阶段 Halton(2, 3) 像素内偏移坐标表
   :widths: 20 25 25 30
   :header-rows: 1
   :class: tight-table

   * - 帧索引 (Phase $i$)
     - $\Phi_2(i)$ (X 偏移)
     - $\Phi_3(i)$ (Y 偏移)
     - 亚像素中心归一化偏移 $(\Delta x, \Delta y) \in [-0.5, 0.5]$
   * - **0**
     - $1/2 = 0.5000$
     - $1/3 \approx 0.3333$
     - $(0.0000, -0.1667)$
   * - **1**
     - $1/4 = 0.2500$
     - $2/3 \approx 0.6667$
     - $(-0.2500, 0.1667)$
   * - **2**
     - $3/4 = 0.7500$
     - $1/9 \approx 0.1111$
     - $(0.2500, -0.3889)$
   * - **3**
     - $1/8 = 0.1250$
     - $4/9 \approx 0.4444$
     - $(-0.3750, -0.0556)$
   * - **4**
     - $5/8 = 0.6250$
     - $7/9 \approx 0.7778$
     - $(0.1250, 0.2778)$
   * - **5**
     - $3/8 = 0.3750$
     - $2/9 \approx 0.2222$
     - $(-0.1250, -0.2778)$
   * - **6**
     - $7/8 = 0.8750$
     - $5/9 \approx 0.5556$
     - $(0.3750, 0.0556)$
   * - **7**
     - $1/16 = 0.0625$
     - $8/9 \approx 0.8889$
     - $(-0.4375, 0.3889)$

投影矩阵抖动注入机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在渲染管线的几何阶段与 G-Buffer 阶段，将亚像素偏移应用到相机裁剪空间透视投影矩阵中：

设屏幕分辨率为 $W 	imes H$，在标准化设备坐标系（NDC，范围 $[-1, 1]$）中，单个像素的宽度为 $2.0 / W$，高度为 $2.0 / H$。

抖动透视投影矩阵 $\mathbf{M}_{	ext{jittered}}$ 可通过在标准投影矩阵 $\mathbf{M}_{	ext{proj}}$ 的平移列注入偏移直接构建：

.. math::

   \mathbf{M}_{	ext{jittered}} = \begin{bmatrix}
   1 & 0 & 0 & \frac{2 \Delta x}{W} \
   0 & 1 & 0 & \frac{2 \Delta y}{H} \
   0 & 0 & 1 & 0 \
   0 & 0 & 0 & 1
   \end{bmatrix} 	imes \mathbf{M}_{	ext{proj}} = \begin{bmatrix}
   M_{00} & 0 & M_{02} + \frac{2 \Delta x}{W} & 0 \
   0 & M_{11} & M_{12} + \frac{2 \Delta y}{H} & 0 \
   0 & 0 & M_{22} & M_{23} \
   0 & 0 & M_{32} & 0
   \end{bmatrix}

*重要工程准则*：
- 阴影贴图生成（Shadow Pass）**严禁** 注入相机抖动，否则会导致连续帧之间深度图抖动，引发极严重的阴影边缘锯齿跳跃；
- 速度缓冲区（Velocity Buffer）在计算当前帧与前一帧坐标差值时，必须**准确抵消**相机自身的亚像素抖动，保证静态物体导出的运动矢量严格为零。

------------------------------------------------------------------------
33.3 运动矢量 (Velocity Buffer) 与历史帧重投影
------------------------------------------------------------------------

运动矢量的物理定义与编码
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
速度缓冲区（Velocity Buffer / Motion Vector Texture）记录了当前屏幕像素从当前时间戳 $t$ 追溯回前一时间戳 $t-1$ 的屏幕空间位移矢量 $\mathbf{v} = (\Delta u, \Delta v)$。

对于场景中任一点，设其当前帧无抖动裁剪空间坐标为 $\mathbf{P}_{	ext{curr}}^{	ext{clip}} = (x_c, y_c, z_c, w_c)$，前一帧无抖动裁剪空间坐标为 $\mathbf{P}_{	ext{prev}}^{	ext{clip}} = (x_p, y_p, z_p, w_p)$。

执行透视除法转换到 NDC 空间（$[-1, 1]$）：

.. math::

   \mathbf{ndc}_{	ext{curr}} = \left( \frac{x_c}{w_c}, \, \frac{y_c}{w_c} \right), \quad \mathbf{ndc}_{	ext{prev}} = \left( \frac{x_p}{w_p}, \, \frac{y_p}{w_p} \right)

转换为屏幕 UV 坐标系（$[0, 1]$，原点在左上角）：

.. math::

   \mathbf{uv}_{	ext{curr}} = \left( \frac{\mathbf{ndc}_{	ext{curr}}.x + 1}{2}, \, \frac{1 - \mathbf{ndc}_{	ext{curr}}.y}{2} \right), \quad \mathbf{uv}_{	ext{prev}} = \left( \frac{\mathbf{ndc}_{	ext{prev}}.x + 1}{2}, \, \frac{1 - \mathbf{ndc}_{	ext{prev}}.y}{2} \right)

二维屏幕空间速度矢量定义为：

.. math::

   \mathbf{v}(\mathbf{uv}_{	ext{curr}}) = \mathbf{uv}_{	ext{curr}} - \mathbf{uv}_{	ext{prev}}

静态几何与动态刚体/骨骼动画的双轨生成机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
1. **静态场景物体（Static Geometry）**：
   无需在 G-Buffer 额外写出速度纹理。在 TAA Pass 中，读取当前帧深度缓冲区 $z_{	ext{depth}}$，利用逆当前视角投影矩阵 $\mathbf{M}_{	ext{curr}}^{-1}$ 重构世界空间坐标 $\mathbf{X}_{	ext{world}}$，再通过前一帧视角投影矩阵 $\mathbf{M}_{	ext{prev}}$ 投影得到前一帧像素位置。该机制可节约巨额 G-Buffer 写出带宽；
2. **动态物体与蒙皮角色（Skinned Meshes）**：
   物体自身发生位移、旋转或骨骼形变。顶点着色器必须同时输入当前帧蒙皮矩阵与前一帧蒙皮矩阵，在着色器中分别计算两个顶点的世界空间位置并投影，在像素着色器中计算差值并写出至 `RG16_FLOAT` 或 `RG16_SNORM` 格式的速度缓冲区。

深度膨胀与速度取样 (Depth Dilate / Neighborhood Best Velocity)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在多边形物体的边界边缘，由于背景深度骤变，当前像素可能刚好落在背景上，导致采样到背景近乎为零的速度矢量，而实际上该像素在前一帧被快速运动的前景边缘所占据。若直接使用背景速度，会导致前景边缘产生极为严重的边缘撕裂与鬼影。

工业标准采用 **$3 	imes 3$ 邻域最近深度膨胀算法（Depth Dilate / 3x3 Closest Velocity）**：
在 $3 	imes 3$ 像素邻域内搜索深度值最小（离相机最近）的像素坐标，并将该像素的速度矢量作为中心像素的有效速度：

.. code-block:: text

   3x3 邻域深度对比提取前景速度:
   [ z0 ] [ z1 ] [ z2 ]
   [ z3 ] [ z_center ] [ z5 ]  ===> 寻找 z_min (离相机最近的几何表面)
   [ z6 ] [ z7 ] [ z8 ]             将 z_min 对应坐标的 Velocity 赋给中心像素

双三次 (Bicubic Catmull-Rom) 历史重采样
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当使用速度矢量 $\mathbf{v}$ 回溯采样历史帧 $S_{t-1}(\mathbf{uv} - \mathbf{v})$ 时，若直接使用硬件双线性插值（Bilinear Filtering），由于每次插值均引入低通模糊，在静止镜头下经过 20~30 帧的连续累积反馈后，整幅图像将严重软化变糊。

TAA 必须使用高阶重构滤波。工业界普遍采用 **5-Tap Catmull-Rom 双三次插值滤波**：
通过巧妙利用 GPU 硬件双线性插值器的轴向权重组合，仅需 5 次硬件纹理采样即可精确逼近 16-Tap Bicubic 滤波，在完全保留高频纹理细节的同时彻底消除插值过模糊。

------------------------------------------------------------------------
33.4 鬼影 (Ghosting) 与暗部闪烁抑制：邻域色彩裁剪
------------------------------------------------------------------------

时域抗锯齿的最大挑战：遮挡与新露面 (Disocclusion)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当一个快速移动的物体离开某个屏幕区域时，露出的新背景在前一帧实际上是被遮挡的。此时回溯速度矢量采样历史缓冲区，采样到的必然是刚刚移开的运动物体颜色，而非真正的历史背景。

若将这种失效的历史颜色直接按 EMA 混合，画面后方将拖出一条半透明的残影，被称为 **时域鬼影 (Ghosting)**。

RGB 轴对齐包围盒 (AABB) 裁剪的缺陷
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
为了强行使历史帧颜色与当前帧几何保持一致，早期 TAA 在当前像素的 $3 	imes 3$ 空间邻域内搜索 RGB 各通道的最大值与最小值，构建一个轴对齐包围盒（AABB）：

.. math::

   \mathbf{C}_{\min} = \min_{i \in 3 	imes 3} \mathbf{C}_i, \quad \mathbf{C}_{\max} = \max_{i \in 3 	imes 3} \mathbf{C}_i

将采样到的历史颜色 $\mathbf{C}_{	ext{hist}}$ 截断在包围盒范围内：

.. math::

   \mathbf{C}_{	ext{clamped}} = 	ext{clamp}(\mathbf{C}_{	ext{hist}}, \, \mathbf{C}_{\min}, \, \mathbf{C}_{\max})

*RGB AABB 裁剪的核心缺陷*：
在 RGB 色彩空间中，各个通道强高度相关（高亮黄色需要高 R 与高 G）。由 9 个不同像素的离散分量拼凑出的 $[\mathbf{C}_{\min}, \mathbf{C}_{\max}]$ 包围盒体积过于庞大，且包含了大量物理上不存在的虚假色彩。此外，直接截断（Clamping）会将色彩向量拉向立方体外表面，破坏原始色彩的色相与饱和度，导致运动物体边缘产生变色伪影与频闪。

YCoCg 色彩空间方差裁剪 (Variance Clipping)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
现代 3A 引擎（如 Inside / UE5 / Frostbite）将当前帧邻域像素全部转换至 **正交无相关性的 YCoCg 色彩空间**，并使用基于一阶统计矩（均值）与二阶统计矩（方差）构建的紧凑椭球包围盒进行线段求交裁剪（Color Clipping）：

1. **RGB 向 YCoCg 空间正交转译**：

.. math::

   \begin{bmatrix} Y \ Co \ Cg \end{bmatrix} = \begin{bmatrix} 1/4 & 1/2 & 1/4 \ 1/2 & 0 & -1/2 \ -1/4 & 1/2 & -1/4 \end{bmatrix} \begin{bmatrix} R \ G \ B \end{bmatrix}

其中 $Y$ 代表无色差亮度（Luminance），$Co$ 代表橙色差（Chrominance Orange），$Cg$ 代表绿色差（Chrominance Green）。

2. **$3 	imes 3$ 邻域均值 $\mu$ 与标准差 $\sigma$ 统计**：

.. math::

   \mu = \frac{1}{9} \sum_{i=1}^{9} \mathbf{C}_i, \quad \sigma = \sqrt{\frac{1}{9} \sum_{i=1}^{9} \mathbf{C}_i^2 - \mu^2}

3. **紧凑方差盒构建**：

.. math::

   \mathbf{Box}_{\min} = \mu - \gamma \cdot \sigma, \quad \mathbf{Box}_{\max} = \mu + \gamma \cdot \sigma

其中 $\gamma$ 为盒尺寸缩放因子（通常取 $\gamma = 1.0 \sim 1.5$）。相比极值 AABB，方差盒能够有效过滤掉 $3 	imes 3$ 邻域内的孤立噪点极端值。

4. **色彩射线裁剪 (Ray Clipping)**：
   不同于直接 `clamp`，射线裁剪从当前像素经过加权滤波的中心颜色 $\mathbf{C}_{	ext{curr}}$ 向历史颜色 $\mathbf{C}_{	ext{hist}}$ 引出一条参数化线段，求解该线段与方差盒 $\mathbf{Box}$ 的第一个交点：

.. math::

   \mathbf{C}_{	ext{clipped}} = 	ext{IntersectBox}(\mathbf{C}_{	ext{curr}}, \, \mathbf{C}_{	ext{hist}}, \, \mathbf{Box}_{\min}, \, \mathbf{Box}_{\max})

该方法严格保持了历史色彩向量的方向角，彻底杜绝了色相畸变。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |             YCoCg 空间色彩射线裁剪 (Color Clipping) 几何原理            |
   +-------------------------------------------------------------------------+

              Cg (绿色差)
                  ^
                  |                Box_max (mu + gamma * sigma)
                  |          +---------------+
                  |          |               |
                  |          |       x       | <--- 中心均值 mu
                  |          |    C_clipped  |
                  |          +-------*-------+
                  |                 / \   Box_min (mu - gamma * sigma)
                  |                /   \
                  |               /     \
                  |              /       \
                  +-------------*---------*------------> Co (橙色差)
                              C_curr    C_history (由于运动移出包围盒)

抗闪烁加权与高光抑制 (Anti-Flicker Karis Weighting)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在 PBR 镜面高光渲染中，亚像素微表面法线会导致单个像素的 HDR 辐射亮度飙升至 $100.0 \sim 1000.0$。当该像素在帧间抖动时，如此强烈的单像素能量注入会导致 TAA 输出在时域上剧烈跳动，形成耀眼的高光噪点（Fireflies）。

Epic Games 工程师 Brian Karis 提出了基于亮度倒数的加权压制算子：
在时域混合之前，对当前帧与历史帧的颜色应用局部非线性色调映射权重：

.. math::

   w(\mathbf{C}) = \frac{1}{1 + 	ext{Luma}(\mathbf{C})}

在加权状态下完成时域插值后，再执行逆映射还原：

.. math::

   \mathbf{C}_{	ext{resolved}} = \frac{w_c \cdot \alpha \cdot \mathbf{C}_{	ext{curr}} + w_h \cdot (1 - \alpha) \cdot \mathbf{C}_{	ext{clipped}}}{w_c \cdot \alpha + w_h \cdot (1 - \alpha)}

该机制对超出白点的超亮高光能量进行了优雅的对数级软压缩，彻底阻断了时域高光跳变。

------------------------------------------------------------------------
33.5 工业级 HLSL / Compute Shader TAA 完整实现
------------------------------------------------------------------------

以下是符合 DirectX 12 / Vulkan 工业规范的完整 TAA 核心计算着色器源码（HLSL 6.5+）。包含 **$3 	imes 3$ 邻域深度膨胀速度提取、Catmull-Rom 5-Tap 历史采样、YCoCg 方差射线裁剪与 Karis 抗闪烁权重混合**：

.. code-block:: hlsl

   // =========================================================================
   // File: PostProcess_TemporalAntiAliasing.hlsl
   // Standard: HLSL 6.5+ (DX12 / Vulkan via DXC)
   // Architecture: High-Performance Compute Shader TAA with YCoCg Variance Clipping
   // =========================================================================

   struct TAAConstants {
       float2 RenderTargetSize;
       float2 RcpRenderTargetSize;
       
       float2 JitterOffset;             // 当前帧亚像素抖动向量 (UV 坐标系)
       float2 PrevJitterOffset;         // 前一帧亚像素抖动向量
       
       float  FeedbackFactor;           // 基础时域累积因子 alpha (如 0.08)
       float  VarianceBoxScale;         // 方差盒缩放系数 gamma (如 1.25)
       float  MotionSharpnessBoost;     // 运动中锐化保持系数
       float  Padding;
   };

   ConstantBuffer<TAAConstants> g_CB : register(b0);

   Texture2D<float4>   g_CurrentColorTexture   : register(t0); // 带有 Jitter 的 HDR 场景图
   Texture2D<float4>   g_HistoryColorTexture   : register(t1); // 前一帧输出的 TAA 历史图
   Texture2D<float>    g_DepthTexture          : register(t2); // 当前帧深度图 (Device Depth)
   Texture2D<float2>   g_VelocityTexture       : register(t3); // 速度缓冲区 (UV Space)
   SamplerState        g_LinearClampSampler    : register(s0);
   SamplerState        g_PointClampSampler     : register(s1);

   RWTexture2D<float4> g_RWOutputColor         : register(u0); // 本帧解析输出，并写回历史

   // =========================================================================
   // 色彩空间转换函数库: RGB <-> YCoCg
   // =========================================================================
   float3 RGBToYCoCg(float3 c) {
       return float3(
            0.25f * c.r + 0.50f * c.g + 0.25f * c.b,
            0.50f * c.r - 0.50f * c.b,
           -0.25f * c.r + 0.50f * c.g - 0.25f * c.b
       );
   }

   float3 YCoCgToRGB(float3 c) {
       float Y  = c.x;
       float Co = c.y;
       float Cg = c.z;
       return float3(
           Y + Co - Cg,
           Y + Cg,
           Y - Co - Cg
       );
   }

   // 亮度感知权重计算 (Karis Weighting)
   float CalculateLumaWeight(float3 colorRGB) {
       float luma = dot(colorRGB, float3(0.2126f, 0.7152f, 0.0722f));
       return 1.0f / (1.0f + luma);
   }

   // =========================================================================
   // 射线与 AABB 方差盒相交算法 (Ray-AABB Intersection)
   // =========================================================================
   float3 IntersectAABB(float3 boxMin, float3 boxMax, float3 origin, float3 target) {
       float3 dir = target - origin;
       float3 invDir = 1.0f / (abs(dir) > 1e-6f ? dir : float3(1e-6f, 1e-6f, 1e-6f));

       float3 t0 = (boxMin - origin) * invDir;
       float3 t1 = (boxMax - origin) * invDir;

       float3 tmax = max(t0, t1);
       float t = min(tmax.x, min(tmax.y, tmax.z));

       return origin + dir * saturate(t);
   }

   // =========================================================================
   // 5-Tap Catmull-Rom 双三次重采样历史帧
   // =========================================================================
   float4 SampleTextureCatmullRom5Tap(Texture2D tex, SamplerState smp, float2 uv, float2 texSize) {
       float2 position = uv * texSize;
       float2 centerPosition = floor(position - 0.5f) + 0.5f;
       float2 f = position - centerPosition;

       float2 w0 = f * (-0.5f + f * (1.0f - 0.5f * f));
       float2 w1 = 1.0f + f * f * (-2.5f + 1.5f * f);
       float2 w2 = f * (0.5f + f * (2.0f - 1.5f * f));
       float2 w3 = f * f * (-0.5f + 0.5f * f);

       float2 w12 = w1 + w2;
       float2 tc12 = (centerPosition + w2 / w12) / texSize;

       float2 tc0 = (centerPosition - 1.0f) / texSize;
       float2 tc3 = (centerPosition + 2.0f) / texSize;

       float4 color = float4(0, 0, 0, 0);
       color += tex.SampleLevel(smp, float2(tc12.x, tc0.y), 0) * (w12.x * w0.y);
       color += tex.SampleLevel(smp, float2(tc0.x, tc12.y), 0) * (w0.x * w12.y);
       color += tex.SampleLevel(smp, float2(tc12.x, tc12.y), 0) * (w12.x * w12.y);
       color += tex.SampleLevel(smp, float2(tc3.x, tc12.y), 0) * (w3.x * w12.y);
       color += tex.SampleLevel(smp, float2(tc12.x, tc3.y), 0) * (w12.x * w3.y);

       return color / (w12.x * w0.y + w0.x * w12.y + w12.x * w12.y + w3.x * w12.y + w12.x * w3.y);
   }

   // =========================================================================
   // 主 TAA Compute Shader
   // =========================================================================
   [numthreads(8, 8, 1)]
   void CS_TemporalAntiAliasing(uint3 dispatchThreadID : SV_DispatchThreadID)
   {
       uint2 pixelCoord = dispatchThreadID.xy;
       if (pixelCoord.x >= (uint)g_CB.RenderTargetSize.x || 
           pixelCoord.y >= (uint)g_CB.RenderTargetSize.y) return;

       float2 texelSize = g_CB.RcpRenderTargetSize;
       float2 currentUV = (float2(pixelCoord) + 0.5f) * texelSize;

       // ---------------------------------------------------------------------
       // 阶段 1: 3x3 邻域深度膨胀，寻找最近几何表面获取主导运动矢量
       // ---------------------------------------------------------------------
       float  closestDepth = 0.0f; // 逆 Z 规范下 0.0 为最远，1.0 为最近
       int2   closestOffset = int2(0, 0);

       [unroll]
       for (int y = -1; y <= 1; ++y) {
           [unroll]
           for (int x = -1; x <= 1; ++x) {
               float d = g_DepthTexture.Load(int3(pixelCoord + int2(x, y), 0));
               if (d > closestDepth) { // 寻找最靠近相机的像素
                   closestDepth = d;
                   closestOffset = int2(x, y);
               }
           }
       }

       // 采样主导运动矢量
       float2 motionVector = g_VelocityTexture.Load(int3(pixelCoord + closestOffset, 0));
       float2 historyUV = currentUV - motionVector;

       // ---------------------------------------------------------------------
       // 阶段 2: 3x3 邻域色彩统计分析 (YCoCg 均值与方差构建)
       // ---------------------------------------------------------------------
       float3 m1 = float3(0, 0, 0);
       float3 m2 = float3(0, 0, 0);
       float3 centerColorYCoCg = float3(0, 0, 0);

       [unroll]
       for (int dy = -1; dy <= 1; ++dy) {
           [unroll]
           for (int dx = -1; dx <= 1; ++dx) {
               float3 c = g_CurrentColorTexture.Load(int3(pixelCoord + int2(dx, dy), 0)).rgb;
               float3 c_ycocg = RGBToYCoCg(c);

               m1 += c_ycocg;
               m2 += c_ycocg * c_ycocg;

               if (dx == 0 && dy == 0) {
                   centerColorYCoCg = c_ycocg;
               }
           }
       }

       // 计算一阶统计矩 (均值) 与二阶统计矩 (标准差)
       float3 mean   = m1 / 9.0f;
       float3 stdDev = sqrt(max(m2 / 9.0f - mean * mean, 0.0f));

       float3 boxMin = mean - g_CB.VarianceBoxScale * stdDev;
       float3 boxMax = mean + g_CB.VarianceBoxScale * stdDev;

       // ---------------------------------------------------------------------
       // 阶段 3: 历史帧回溯采样与色彩裁剪 (Color Clipping)
       // ---------------------------------------------------------------------
       float3 finalColor = float3(0, 0, 0);

       // 边界越界校验 (Disocclusion 外溢检测)
       if (any(historyUV < 0.0f) || any(historyUV > 1.0f)) {
           // 若移出屏幕边界，直接输出当前帧
           g_RWOutputColor[pixelCoord] = float4(YCoCgToRGB(centerColorYCoCg), 1.0f);
           return;
       }

       // 使用 5-Tap Catmull-Rom 采样历史缓冲区
       float4 rawHistory = SampleTextureCatmullRom5Tap(g_HistoryColorTexture, g_LinearClampSampler, 
                                                      historyUV, g_CB.RenderTargetSize);
       float3 historyYCoCg = RGBToYCoCg(rawHistory.rgb);

       // 执行射线与 AABB 方差盒的相交裁剪
       float3 clippedHistoryYCoCg = IntersectAABB(boxMin, boxMax, centerColorYCoCg, historyYCoCg);
       float3 clippedHistoryRGB   = YCoCgToRGB(clippedHistoryYCoCg);
       float3 currentCenterRGB    = YCoCgToRGB(centerColorYCoCg);

       // ---------------------------------------------------------------------
       // 阶段 4: 自适应时域混合 (Karis 权重 + 运动自适应反馈因子)
       // ---------------------------------------------------------------------
       // 基于速度大小动态提高响应度，抑制高动态下的残影
       float speed = length(motionVector * g_CB.RenderTargetSize);
       float adaptiveAlpha = lerp(g_CB.FeedbackFactor, 0.25f, saturate(speed / 10.0f));

       // 计算亮度非线性权重 (抑制 Fireflies 闪烁)
       float wCurr = CalculateLumaWeight(currentCenterRGB);
       float wHist = CalculateLumaWeight(clippedHistoryRGB);

       float weightedAlpha = adaptiveAlpha * wCurr;
       float weightedOneMinusAlpha = (1.0f - adaptiveAlpha) * wHist;

       finalColor = (currentCenterRGB * weightedAlpha + clippedHistoryRGB * weightedOneMinusAlpha) / 
                    max(weightedAlpha + weightedOneMinusAlpha, 1e-5f);

       // 写回渲染目标与历史帧双缓冲
       g_RWOutputColor[pixelCoord] = float4(finalColor, 1.0f);
   }

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章深入解构了现代工业级渲染管线中抗锯齿的核心支柱——时间性抗锯齿（Temporal Anti-Aliasing - TAA）的完整微架构：
1. **时域超采样数学本质**：阐明了离散多边形光栅化阶跃信号与空间香农采样定理的冲突，推导了将空间高密度采样转换为时间轴加权累加的 EMA 指数移动平均模型；
2. **亚像素抖动序列设计**：剖析了反向基数映射算法，建立了基于低差异准随机序列 $	ext{Halton}(2, 3)$ 的 8 阶段无缝空间填充拓扑与透视投影矩阵平移调制方程；
3. **运动矢量与高保真重投影**：推导了静态几何逆投影与动态蒙皮骨骼速度缓冲区的双轨机制，详解了 $3 	imes 3$ 邻域深度膨胀防止背景速度穿透前景的机制，以及 5-Tap Catmull-Rom 双三次重采样消除时域二次模糊的实现；
4. **鬼影抑制与方差射线裁剪**：揭示了遮挡新露面引发鬼影的物理本质，推导了 YCoCg 去相关色彩空间中的一阶均值与二阶方差盒构建算法，并证明了射线裁剪相较于朴素 AABB 截断在保持色彩饱和度与防频闪上的几何优越性；
5. **Karis 逆亮度加权**：建立了非线性权重函数抑制亚像素高光噪波（Fireflies）的时域防噪拓扑。

在下一章（Chapter 34）中，我们将进一步拓展速度缓冲区的系统应用，解构 **运动模糊与体积光散射 (Motion Blur and Volumetric Fog)**。我们将深入推导 **Tile-Max 速度重构滤波算法、离散像素点沿速度矢量线积分着色、Mie / Rayleigh 大气散射物理相位函数以及基于 3D Froxel 体素网格的 Raymarching 体积雾渲染管线**，敬请期待！
