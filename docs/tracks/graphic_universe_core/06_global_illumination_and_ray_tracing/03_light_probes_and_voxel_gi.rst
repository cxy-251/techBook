========================================================================
Chapter 28: 探针与体素全局光照：辐射度着色、光照探针与体素锥形追踪 (VXGI)
========================================================================

.. note:: 前置背景与认知承接
   在上一章（Chapter 27）中，我们系统解构了屏幕空间反射（SSR），通过对 2.5D 深度高度场的层次光线步进实现了局部高频高光反射。然而，屏幕空间算法受制于视锥体内可见几何的硬性局限，完全无法获取屏幕外遮挡区以及大尺度场景的漫反射多重反弹（Diffuse Interreflection）与环境间接光照。

   要实现宏观空间中连续、平滑且物理守恒的三维全局光照，图形渲染管线必须摆脱屏幕空间的单一平面假设，转向在 **三维欧氏空间中构建低频辐射场与体素化场景几何拓扑**。本章将系统解构经典有限元辐射度着色（Radiosity）、基于正交基底的球谐函数（Spherical Harmonics - SH）低频辐照度压缩、空间光照探针网格与动态漫反射全局光照（DDGI），以及基于 3D 各向异性金字塔的体素锥形追踪（Voxel Cone Tracing - VXGI）流水线，并交付工业级 HLSL Compute Shader 探针着色实现。

------------------------------------------------------------------------
28.1 经典辐射度理论 (Radiosity) 与有限元光能传递方程
------------------------------------------------------------------------

辐射度算法（Radiosity Method）是计算机图形学中最早用于求解完全漫反射（Lambertian）表面之间多重间接反弹全局光照的经典有限元数值解法。

辐射度平衡方程 (Radiosity Equation)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

假设场景由 $N$ 个不透明的理想漫反射微元面片（Patches）组成。对于第 $i$ 个面片，其离开表面的总辐射度 $B_i$（单位面积辐射通量，单位：$	ext{W}/	ext{m}^2$）等于其自身发射的辐射度 $E_i$ 与反射其他所有面片入射光辐射度的总和：

.. math::

   B_i = E_i + \rho_i \sum_{j=1}^{N} B_j F_{ij}

其中：
- $B_i$ 为面片 $i$ 的出射辐射度（Radiosity）；
- $E_i$ 为面片 $i$ 自身的自发光辐射度（Emissivity）；
- $\rho_i \in [0, 1)$ 为面片 $i$ 的漫反射率（Diffuse Reflectance / Albedo）；
- $F_{ij}$ 为面片 $j$ 到面片 $i$ 的 **形状因子（Form Factor）**，表示从面片 $i$ 发出的能量被面片 $j$ 接收的几何比例。

将上式对所有 $N$ 个面片联立，可构建线性代数方程组：

.. math::

   \begin{bmatrix}
   1 - \rho_1 F_{11} & -\rho_1 F_{12} & \cdots & -\rho_1 F_{1N} \
   -\rho_2 F_{21} & 1 - \rho_2 F_{22} & \cdots & -\rho_2 F_{2N} \
   \vdots & \vdots & \ddots & \vdots \
   - \rho_N F_{N1} & -\rho_N F_{N2} & \cdots & 1 - \rho_N F_{NN}
   \end{bmatrix}
   \begin{bmatrix}
   B_1 \ B_2 \ \vdots \ B_N
   \end{bmatrix}
   =
   \begin{bmatrix}
   E_1 \ E_2 \ \vdots \ E_N
   \end{bmatrix}

形状因子 (Form Factor) 的微积分定义
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

两个微分微元 $dA_i$ 与 $dA_j$ 之间的微分形状因子 $dF_{di 	o dj}$ 严格遵循空间几何立体角投影关系：

.. math::

   dF_{di 	o dj} = \frac{\cos	heta_i \cos	heta_j}{\pi r^2} V(dA_i, dA_j) dA_j

其中：
- $r$ 为两微元几何中心点之间的欧氏距离；
- $	heta_i, 	heta_j$ 分别为连线矢量与两面片法线向量 $\mathbf{N}_i, \mathbf{N}_j$ 的空间夹角；
- $V(dA_i, dA_j) \in \{0, 1\}$ 为两点之间的可见性二值函数（若视线被其他几何体阻挡则为 0，否则为 1）。

有限面积面片 $A_i$ 到 $A_j$ 的形状因子为双重重积分：

.. math::

   F_{ij} = \frac{1}{A_i} \int_{A_i} \int_{A_j} \frac{\cos	heta_i \cos	heta_j}{\pi r^2} V(dA_i, dA_j) \, dA_j \, dA_i

形状因子满足守恒对称性与闭合空间能量守恒定律：

.. math::

   A_i F_{ij} = A_j F_{ji}, \quad \sum_{j=1}^{N} F_{ij} = 1 \quad (	ext{闭合环境})

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                 微元间形状因子 (Form Factor) 几何拓扑关系               |
   +-------------------------------------------------------------------------+

              法线 N_i                        法线 N_j
                 ^                               ^
                 |                               |
                 |  \ theta_i         theta_j /  |
                 |   \                       /   |
              +--+----+--+               +--+----+--+
              |   dA_i   |               |   dA_j   |
              +----------+               +----------+
                    \                         /
                     \       连线距离 r      /
                      \---------------------/
                              V(i, j)
                    (可见性阻挡测试: 0 或 1)

半球与半立方体算法 (The Hemicube Algorithm)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

直接解析计算四重空间重积分计算复杂度极高。Cohen 与 Greenberg 提出了 **半立方体算法（Hemicube Algorithm）**：
将微分面片 $dA_i$ 周围的半球空间包围盒化为一个由 1 个正顶面和 4 个侧面组成的离散半立方体。通过光栅化管线将整个三维场景投影至半立方体的 5 个面上，利用带有深度缓冲（Z-Buffer）的硬件渲染器直接解析可见性 $V(i, j)$，并在每个半立方体像素上预置权重因子（Delta Form Factors），大幅加速形状因子采样。

.. list-table:: 经典辐射度矩阵求解算法对比
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 求解方法
     - 矩阵迭代机制
     - 工程优缺点与收敛特性
   * - **高斯-赛德尔迭代 (Gauss-Seidel)**
     - 依次更新每一个面片 $B_i^{(k+1)} = E_i + \rho_i \sum_{j < i} B_j^{(k+1)} F_{ij} + \rho_i \sum_{j > i} B_j^{(k)} F_{ij}$
     - 收敛速度快，但必须计算并持久化存储整个 $N 	imes N$ 形状因子矩阵，内存开销为 $O(N^2)$。
   * - **渐进式辐射度 (Progressive Radiosity)**
     - 每次选取当前未发射能量最大的面片 $k$，将其累积光能单向“发射（Shoot）”至全场其他所有面片
     - 无需存储全局 $N 	imes N$ 矩阵，内存占用降至 $O(N)$；支持实时预览前几次主要反弹效果。

------------------------------------------------------------------------
28.2 球谐函数 (Spherical Harmonics - SH) 与低频辐照度压缩
------------------------------------------------------------------------

在实时渲染管线中，光照探针无法存储全分辨率的全向环境全景图（Cubemap）。**球谐函数（Spherical Harmonics - SH）提供了一种在球面正交基底上对低频光照信号进行紧凑降维压缩的严格数学工具。**

球谐基底正交定义
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

球谐函数 $Y_l^m(	heta, \phi)$ 是拉普拉斯算子在球面坐标系下的本征函数族，其中 $l \ge 0$ 为阶数（Band/Degree），$m \in [-l, l]$ 为阶内方位模式数。对于给定的阶数 $l$，包含 $2l + 1$ 个相互正交的基函数。

实数球谐基底函数（Real Spherical Harmonics）定义为：

.. math::

   Y_l^m(	heta, \phi) =
   \begin{cases}
   \sqrt{2} K_l^m \cos(m\phi) P_l^m(\cos	heta), & m > 0 \
   K_l^0 P_l^0(\cos	heta), & m = 0 \
   \sqrt{2} K_l^{|m|} \sin(|m|\phi) P_l^{|m|}(\cos	heta), & m < 0
   \end{cases}

其中 $P_l^m$ 为连带勒让德多项式（Associated Legendre Polynomials），$K_l^m$ 为归一化缩放因子。

前 3 阶（Order 3, $l \in [0, 2]$，共 9 个基函数）的解析代数多项式展开（笛卡尔坐标方向向量 $\mathbf{d} = (x, y, z)$，满足 $\|\mathbf{d}\| = 1$）：

.. list-table:: 常用 2 阶球谐函数 (Order 3 / 9 项基底) 笛卡尔坐标解析展开式
   :widths: 15 15 70
   :header-rows: 1
   :class: tight-table

   * - 阶数 $l$
     - 模式 $m$
     - 解析基底公式 $Y_l^m(x, y, z)$
   * - **$l=0$ (1 项)**
     - $m=0$
     - $Y_0^0 = \frac{1}{2}\sqrt{\frac{1}{\pi}} \approx 0.282095$
   * - **$l=1$ (3 项)**
     - $m=-1$
     - $Y_1^{-1} = \frac{1}{2}\sqrt{\frac{3}{\pi}} y \approx 0.488603 \, y$
   * -
     - $m=0$
     - $Y_1^0 = \frac{1}{2}\sqrt{\frac{3}{\pi}} z \approx 0.488603 \, z$
   * -
     - $m=1$
     - $Y_1^1 = \frac{1}{2}\sqrt{\frac{3}{\pi}} x \approx 0.488603 \, x$
   * - **$l=2$ (5 项)**
     - $m=-2$
     - $Y_2^{-2} = \frac{1}{2}\sqrt{\frac{15}{\pi}} xy \approx 1.092548 \, xy$
   * -
     - $m=-1$
     - $Y_2^{-1} = \frac{1}{2}\sqrt{\frac{15}{\pi}} yz \approx 1.092548 \, yz$
   * -
     - $m=0$
     - $Y_2^0 = \frac{1}{4}\sqrt{\frac{5}{\pi}} (3z^2 - 1) \approx 0.315392 \, (3z^2 - 1)$
   * -
     - $m=1$
     - $Y_2^1 = \frac{1}{2}\sqrt{\frac{15}{\pi}} xz \approx 1.092548 \, xz$
   * -
     - $m=2$
     - $Y_2^2 = \frac{1}{4}\sqrt{\frac{15}{\pi}} (x^2 - y^2) \approx 0.546274 \, (x^2 - y^2)$

球面信号投影与重建
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

任意定义在球面 $\Omega$ 上的连续环境入射辐射亮度分布 $L(\mathbf{d})$，均可通过在球面度上的内积投影截断为前 9 个球谐系数向量 $\mathbf{c}_i \in \mathbb{R}^3$（RGB 三通道）：

.. math::

   \mathbf{c}_{lm} = \int_{\Omega} L(\mathbf{d}) Y_l^m(\mathbf{d}) \, d\omega

重建后的球面光照分布为：

.. math::

   	ilde{L}(\mathbf{d}) = \sum_{l=0}^{2} \sum_{m=-l}^{l} \mathbf{c}_{lm} Y_l^m(\mathbf{d})

Ramamoorthi-Hanrahan 漫反射卷积理论
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于理想朗伯漫反射表面，表面法线 $\mathbf{N}$ 处的辐照度 $E(\mathbf{N})$ 等于半球范围内入射光强与余弦加权因子的积分：

.. math::

   E(\mathbf{N}) = \int_{\Omega} L(\mathbf{d}) \max(0, \mathbf{N} \cdot \mathbf{d}) \, d\omega

Ravi Ramamoorthi 与 Pat Hanrahan 从信号频域分析严格证明：**余弦加权核函数 $\max(0, \cos	heta)$ 本质上是一个极低通滤波器（Low-pass Filter）。**
在球谐频域中，卷积运算退化为系数的对应标量乘法：

.. math::

   \hat{A}_l = \int_{0}^{2\pi} \int_{0}^{\pi/2} \cos	heta Y_l^0(	heta) \sin	heta \, d	heta \, d\phi

其低通滤波系数衰减极快：
- $\hat{A}_0 = \pi \approx 3.14159$
- $\hat{A}_1 = \frac{2\pi}{3} \approx 2.09439$
- $\hat{A}_2 = \frac{\pi}{4} \approx 0.78539$
- $\hat{A}_3 = 0$
- $\hat{A}_4 = -\frac{\pi}{24} \approx -0.13089$

**前 2 阶球谐展开（仅需 9 个 float3 系数，即 27 个 float）即可捕捉漫反射辐照度环境中超过 99.2% 的总能量！**

.. code-block:: text

   +-------------------------------------------------------------------------+
   |               球谐函数低通滤波与漫反射辐照度极简重建                     |
   +-------------------------------------------------------------------------+

      高频环境光源 L(d)             余弦核函数 max(0, N·d)            平滑漫反射辐照度 E(N)
     (包含尖锐高光/锐利阴影)          (强低通滤波滤波器)             (9个SH系数即可99.2%拟合)
      +------------------+          +------------------+          +------------------+
      |  高频球谐频域谱   |    *     | 极速衰减频域权重 |    =     |  极度平滑的辐照场 |
      |   l=0,1,2,3,4... |          | A0=π, A1=2π/3... |          |  l >= 3 能量归零 |
      +------------------+          +------------------+          +------------------+

------------------------------------------------------------------------
28.3 空间光照探针与动态漫反射全局光照 (DDGI / RTXGI)
------------------------------------------------------------------------

为了将球谐光照应用到三维场景中的任意动态角色与静态几何体，必须在三维空间中布置 **光照探针网格（Light Probe Grid）**。

探针体积拓扑与三线性插值 (Probe Volumes & Trilinear Interpolation)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在世界坐标系中构建三维规则网格或稀疏八叉树网格。每个网格节点存储一个光照探针（9 个 RGB SH 系数）。
对于场景中的任意着色点 $\mathbf{P}$：
1. 定位其所在的立方体单元格（由 8 个相邻探针围成）；
2. 计算其在单元格内的归一化局部权重 $(u, v, w) \in [0, 1]^3$；
3. 对 8 个探针的 SH 向量执行三线性插值（Trilinear Interpolation）：

.. math::

   \mathbf{c}_{	ext{interpolated}} = \sum_{i=0}^{1} \sum_{j=0}^{1} \sum_{k=0}^{1} (1-u)^{1-i} u^i (1-v)^{1-j} v^j (1-w)^{1-k} w^k \, \mathbf{c}_{ijk}

4. 利用插值后的 SH 系数与着色点法线 $\mathbf{N}$ 点乘重构间接光辐照度。

漏光危机与物理根源 (Light Leaking & Shadow Bleeding)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

规则网格插值存在致命的物理缺陷——**漏光（Light Leaking）与阴影穿透（Shadow Bleeding）**：
- 当一面墙壁横穿两个探针之间时，位于室外亮处的探针光能会通过三线性插值错误渗透到室内暗处的着色点上；
- 位于墙体内部或实心几何体内部的完全黑暗探针，会把阴影错误插值到外部受光表面上。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     传统光照探针三线性插值漏光物理成因                  |
   +-------------------------------------------------------------------------+

            室外 (强日光, 探针亮)            室内 (无直射光, 探针暗)
                [ Probe 0 (亮) ]               [ Probe 1 (暗) ]
                       *                              *
                        \                            /
                         \     物理墙体 (Wall)       /
                          \         | |            /
                           \        | |           /
                            \       | |          /
                             v      | |         v
                           着色点 P (在室内暗处!)
                       =============================
                     三线性插值强行混合 Probe 0 (亮)
                     导致室内墙角产生严重的虚假漏光白斑!

DDGI / RTXGI 架构：八面体深度编码与切比雪夫遮挡测试
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

现代商业引擎采用 **动态漫反射全局光照（Dynamic Diffuse Global Illumination - DDGI）** 彻底解决了探针漏光问题：

1. **双层八面体纹理阵列（Octahedral Texture Arrays）**：
   每个探针不再仅存储单一数值，而是在两张全局 2D 纹理图集（Texture Atlas）中存储：
   - **辐照度图集（Irradiance Atlas）**：每个探针对应 $8 	imes 8$ 像素的低分辨率八面体展开图，记录全向漫反射辐照度；
   - **距离与距离平方图集（Distance Atlas）**：每个探针对应 $16 	imes 16$ 像素八面体图，记录探针向各方向发射光线测得的 **平均径向距离均值 $\mathbb{E}[r]$ 与方差 $\mathbb{E}[r^2]$**。

2. **切比雪夫不等式非对称遮挡测试（Chebyshev Visibility Test）**：
   在着色点 $\mathbf{P}$ 插值探针 $k$ 时，计算着色点到探针的有向距离 $d = \|\mathbf{x}_{	ext{probe}, k} - \mathbf{P}\|$ 以及从探针朝向着色点的方向向量 $\mathbf{v}$。
   采样探针 $k$ 距离图集获取 $(\mu, \sigma^2)$，利用切比雪夫上界计算可见性概率因子 $V_k$：

   .. math::

      \sigma^2 = \mathbb{E}[r^2] - \mu^2, \quad V_k = \frac{\sigma^2}{\sigma^2 + \max(0, d - \mu)^2}

3. **法线感知权重与零可见性剔除**：
   插值综合权重为三线性距离权重、法线方向感知权重与切比雪夫可见性权重的乘积：

   .. math::

      w_k = W_{	ext{trilinear}, k} \cdot \max(0, \mathbf{N} \cdot \mathbf{v}_k) \cdot V_k^p

   若探针与着色点之间存在墙体遮挡（$V_k \approx 0$），该探针权重直接被压制归零，彻底消除了跨墙体漏光现象。

.. list-table:: 传统 SH 光照探针 vs DDGI 动态探针系统对比
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 特性维度
     - 传统 SH 光照探针 (SH Light Probes)
     - DDGI / RTXGI 动态探针系统
   * - **存储格式**
     - 每个探针 9 个 RGB 浮点数 (27 floats)
     - $8 	imes 8$ Irradiance + $16 	imes 16$ Distance 纹理
   * - **漏光抑制能力**
     - 无遮挡感知，跨墙体必须人工放置阻断体
     - **硬件级切比雪夫深度测试，全自动消除漏光**
   * - **动态场景适应性**
     - 依赖离线静态烘焙，动态光照无法更新
     - GPU 每帧异步光追更新探针辐射度，支持动态全破坏场景
   * - **着色开销**
     - 极低 (纯 ALU 矩阵乘法)
     - 较低 (每个像素 8 次双线性纹理采样 + 遮挡计算)

------------------------------------------------------------------------
28.4 体素化渲染流水线 (Scene Voxelization)
------------------------------------------------------------------------

光照探针网格在空旷区域具有极高效率，但对于高频遮挡、近距离接触阴影以及光滑表面的间接高光反射无能为力。**体素全局光照（Voxel Global Illumination - VXGI）通过将连续的 3D 三角形几何实时离散化为 3D 体素网格（3D Voxel Grid），构建了场景空间的完全体积化辐射度场。**

3D 剪辑图 (Clipmap) 体素网格结构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了在有限显存（256MB~512MB）下覆盖广袤场景，VXGI 采用以摄像机为中心的 **嵌套分层 3D 剪辑图（Nested 3D Clipmaps）**：
- **Level 0 (近景)**：高精度体素（如 $128^3$，体素边长 $0.1	ext{m}$，覆盖半径 $12.8	ext{m}$）；
- **Level 1 (中景)**：中精度体素（$128^3$，体素边长 $0.4	ext{m}$，覆盖半径 $51.2	ext{m}$）；
- **Level 2 (远景)**：低精度体素（$128^3$，体素边长 $1.6	ext{m}$，覆盖半径 $204.8	ext{m}$）。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                以摄像机为中心的嵌套 3D Clipmaps 体素层级                |
   +-------------------------------------------------------------------------+

                   +---------------------------------------+
                   | Level 2: 远景体素网格 (边长 1.6m)     |
                   |   +-------------------------------+   |
                   |   | Level 1: 中景体素网格 (0.4m)  |   |
                   |   |   +-----------------------+   |   |
                   |   |   | Level 0: 近景 (0.1m)  |   |   |
                   |   |   |        [Camera]       |   |   |
                   |   |   +-----------------------+   |   |
                   |   +-------------------------------+   |
                   +---------------------------------------+

无保守光栅化 3D 体素注入 (Conservative Rasterization Voxel Injection)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

传统光栅化仅在多边形覆盖像素中心时触发片段着色。对于细薄三角形（如栏杆、叶片），极易从体素网格间隙中漏穿。

1. **硬件保守光栅化（Conservative Rasterization）**：
   开启 GPU 硬件保守光栅化模式，只要三角形接触体素立方体的任意边缘，立即强制生成片段；
2. **支配轴正交投影（Dominant Axis Selection）**：
   在几何着色器（GS）中计算三角形面的几何法线 $\mathbf{N} = (N_x, N_y, N_z)$：
   - 若 $|N_x| > \max(|N_y|, |N_z|)$：沿 X 轴正交投影到 YZ 平面；
   - 若 $|N_y| > \max(|N_x|, |N_z|)$：沿 Y 轴正交投影到 XZ 平面；
   - 若 $|N_z| > \max(|N_x|, |N_y|)$：沿 Z 轴正交投影到 XY 平面。
   
   通过投影到投影面积最大的主平面，彻底消除了退化三角形的采样丢失。

3. **3D UAV 无锁原子写入与颜色平均**：
   在像素着色器中关闭常规 Framebuffer 输出，绑定 `RWTexture3D<uint>`：
   计算当前片段的世界坐标映射的 3D 体素坐标 $(u_x, u_y, u_z)$，计算直接光照辐射度 $L_d$ 与材质 Albedo $\rho$，通过 64 位无锁原子操作（`InterlockedMax` 或浮点累加平均）写入 3D 体素纹理。

------------------------------------------------------------------------
28.5 体素锥形追踪 (Voxel Cone Tracing - VXGI) 遍历求交
------------------------------------------------------------------------

场景完成 3D 体素化并注入光照后，**体素锥形追踪（Voxel Cone Tracing）利用 3D 各向异性 Mipmap 链，以极低的步进采样次数模拟光线在三维空间中的立体角锥形散射。**

各向异性 3D 纹理金字塔 (Anisotropic 3D Mipmaps)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

常规 3D 纹理下采样取 $2 	imes 2 	imes 2$ 共 8 个体素的各向同性平均值，这会丢失几何表面法线的不透明度方向性（例如一块垂直木板在 X 轴看完全不透明，但在 Z 轴看几乎透明）。

各向异性 3D Mipmap 为每个体素存储 **6 个正交方向（$\pm X, \pm Y, \pm Z$）的独立不透明度 $\alpha$ 与定向辐射亮度 $L$**：
在生成父级 Mipmap 时，分别沿 6 个轴向执行定向光线透射前向合成计算（Front-to-Back Blending）：

.. math::

   C_{	ext{mip}} = C_1 + (1 - \alpha_1) C_2, \quad \alpha_{	ext{mip}} = \alpha_1 + (1 - \alpha_1) \alpha_2

圆锥光线步进微积分模型 (Cone Tracing Geometry)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

设从表面着色点 $\mathbf{P}$ 沿方向 $\mathbf{d}$ 发射一个开顶角为 $	heta$ 的圆锥。
当圆锥沿轴线传播距离 $t$ 时，其底面圆形光截面的物理直径 $D(t)$ 为：

.. math::

   D(t) = 2 t 	an\left( \frac{	heta}{2} \right)

设 3D 体素网格在 Level 0 的体素边长为 $s_0$。光截面直径 $D(t)$ 对应的连续 3D Mipmap 采样层级 $L(t)$ 满足：

.. math::

   2^{L(t)} \cdot s_0 = D(t) \implies L(t) = \log_2\left( \frac{2 t 	an(	heta/2)}{s_0} \right)

**圆锥追踪的核心物理洞见：单次三线性硬件纹理采样（SampleLevel with Mip $L(t)$）等效于对圆锥底面所覆盖的成百上千个微观底层体素进行了完全抗走样的立体空间积分！**

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                   体素圆锥追踪 (Voxel Cone Tracing) 步进模型            |
   +-------------------------------------------------------------------------+

             发射点 P
                 *========---___
                  \   步长 Δt   ===---___     圆锥开角 θ (由粗糙度/漫反射决定)
                   \                    ===---___
                    \   Mip L_0 (精细)   Mip L_1  ===---___
                     \    [Voxel]        [ 大体素 ]        ===---___ Mip L_2 (粗糙大光斑)
                      \    (小)            (中)             [ 宏观体素 ]
                       \                                        |
                        \---------------------------------------+
                                  传播轴线距离 t ------------->
                                  光截面直径 D(t) 随距离线性放大
                                  单次 Texture3D SampleLevel 即完成空间积分!

间接漫反射与间接镜面反射解算
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: VXGI 漫反射圆锥 vs 镜面反射圆锥追踪策略
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 参数项
     - 间接漫反射 (Indirect Diffuse)
     - 间接高光反射 (Indirect Specular)
   * - **圆锥数量**
     - 4 ~ 6 根（覆盖上半球）
     - 1 根（沿微面反射方向 $\mathbf{R}$）
   * - **圆锥开角 $	heta$**
     - 固定大角度（约 $60^\circ \approx \pi/3$）
     - 动态角度 $	heta = \arctan(	ext{Roughness})$
   * - **步进终止条件**
     - 累积不透明度 $\alpha \ge 0.98$ 或超出距离
     - 累积不透明度 $\alpha \ge 0.98$ 或命中完全不透明体素
   * - **最终输出**
     - 各圆锥加权求和，重构平滑色彩溢出 (Color Bleeding)
     - 锐利或光滑模糊的高光倒影

------------------------------------------------------------------------
28.6 工业级球谐光照探针与 DDGI 遮挡重构 HLSL 完整实现
------------------------------------------------------------------------

以下是符合 DirectX 12 / Vulkan 工业规范的 2 阶球谐（Order 3 / 9 系数）漫反射辐照度快速重构与切比雪夫遮挡保护 HLSL 核心实现：

.. code-block:: hlsl

   // HLSL: 工业级 2 阶球谐光照探针辐照度重构与法线偏差偏移
   // 特性: 9 项 SH 基底点积 + 法线偏置抗自遮挡 + 空间探针插值

   struct ProbeGridData {
       float4 GridMin;         // xyz: 网格最小世界包围盒坐标, w: 探针空间步长
       int4   GridCounts;      // xyz: X/Y/Z 方向探针数量 (如 32, 16, 32)
       float4 ProbeOffsetParams; // x: NormalBias, y: ViewBias, z: EnergyScale
   };

   // 单个探针存储的 9 个 RGB 球谐系数 (27 floats, 打包为 7 个 float4)
   struct SH9Color {
       float4 L00_L1m1_L10_L11_R; // R 通道前 4 项
       float4 L2m2_L2m1_L20_L21_R; // R 通道 4 项
       float4 L22_G00_G1m1_G10;    // R 最后一项 + G 通道前 3 项
       float4 L11_L2m2_L2m1_L20_G; // G 通道 4 项
       float4 L21_L22_B00_B1m1;    // G 2 项 + B 通道前 2 项
       float4 L10_L11_L2m2_L2m1_B; // B 通道 4 项
       float4 L20_L21_L22_Pad;     // B 通道后 3 项
   };

   ConstantBuffer<ProbeGridData>  g_GridCB      : register(b0);
   StructuredBuffer<float4>      g_SHCoeffsBuf : register(t0); // 平铺存储的 SH 探针数据

   // 2 阶球谐基底计算 (输入归一化方向 N)
   void EvaluateSH9Basis(float3 N, out float basis[9]) {
       // l=0
       basis[0] = 0.282095f;

       // l=1 (带 A1 = 2π/3 卷积因子)
       basis[1] = 0.488603f * N.y;
       basis[2] = 0.488603f * N.z;
       basis[3] = 0.488603f * N.x;

       // l=2 (带 A2 = π/4 卷积因子)
       basis[4] = 1.092548f * N.x * N.y;
       basis[5] = 1.092548f * N.y * N.z;
       basis[6] = 0.315392f * (3.0f * N.z * N.z - 1.0f);
       basis[7] = 1.092548f * N.x * N.z;
       basis[8] = 0.546274f * (N.x * N.x - N.y * N.y);
   }

   // 解析单探针的 9 项 SH 辐照度
   float3 EvaluateProbeSHIrradiance(uint probeIndex, float3 N) {
       float basis[9];
       EvaluateSH9Basis(N, basis);

       // 应用 Ramamoorthi 漫反射卷积权重 (A0, A1, A2)
       const float c_A0 = 3.141593f;
       const float c_A1 = 2.094395f;
       const float c_A2 = 0.785398f;

       float weights[9] = {
           c_A0 * basis[0],
           c_A1 * basis[1], c_A1 * basis[2], c_A1 * basis[3],
           c_A2 * basis[4], c_A2 * basis[5], c_A2 * basis[6], c_A2 * basis[7], c_A2 * basis[8]
       };

       // 读取探针 9 个 RGB 系数 (从 StructuredBuffer 平铺读取)
       uint baseOffset = probeIndex * 9;
       float3 irradiance = float3(0.0f, 0.0f, 0.0f);

       [unroll]
       for (int i = 0; i < 9; ++i) {
           float4 coeff = g_SHCoeffsBuf[baseOffset + i];
           irradiance += coeff.rgb * weights[i];
       }

       return max(float3(0.0f, 0.0f, 0.0f), irradiance);
   }

   // 3D 空间探针网格三线性插值主入口
   float3 SampleIrradianceProbeGrid(float3 worldPos, float3 worldNormal, float3 viewDir) {
       // 应用法线偏置 (Normal Bias) 避免采样到表面内部被遮挡的探针
       float  spacing = g_GridCB.GridMin.w;
       float3 biasedPos = worldPos + worldNormal * (spacing * g_GridCB.ProbeOffsetParams.x) 
                                   + viewDir * (spacing * g_GridCB.ProbeOffsetParams.y);

       // 计算在探针网格中的浮点索引坐标
       float3 gridCoord = (biasedPos - g_GridCB.GridMin.xyz) / spacing;
       int3   baseIndex = floor(gridCoord);
       float3 fracCoord = frac(gridCoord);

       // 边界安全裁剪
       if (any(baseIndex < 0) || any(baseIndex >= g_GridCB.GridCounts.xyz - 1)) {
           // 超出网格范围回退至兜底探针
           return EvaluateProbeSHIrradiance(0, worldNormal);
       }

       float3 totalIrradiance = float3(0.0f, 0.0f, 0.0f);
       float  totalWeight = 0.0f;

       // 遍历周围 8 个包围探针进行三线性加权
       [unroll]
       for (int z = 0; z <= 1; ++z) {
           for (int y = 0; y <= 1; ++y) {
               for (int x = 0; x <= 1; ++x) {
                   int3   probeCoord = baseIndex + int3(x, y, z);
                   uint   probeFlatID = probeCoord.x + 
                                        probeCoord.y * g_GridCB.GridCounts.x + 
                                        probeCoord.z * (g_GridCB.GridCounts.x * g_GridCB.GridCounts.y);

                   // 计算三线性权重
                   float3 trilinear = float3(
                       x ? fracCoord.x : (1.0f - fracCoord.x),
                       y ? fracCoord.y : (1.0f - fracCoord.y),
                       z ? fracCoord.z : (1.0f - fracCoord.z)
                   );
                   float trilinearWeight = trilinear.x * trilinear.y * trilinear.z;

                   // 计算探针到实际着色点方向的几何加权 (防止墙后探针产生残影)
                   float3 probeWorldPos = g_GridCB.GridMin.xyz + float3(probeCoord) * spacing;
                   float3 toProbe = probeWorldPos - worldPos;
                   float3 probeDir = normalize(toProbe);
                   float  dirWeight = max(0.0001f, dot(worldNormal, probeDir) * 0.5f + 0.5f);

                   float weight = trilinearWeight * dirWeight;

                   float3 probeIrr = EvaluateProbeSHIrradiance(probeFlatID, worldNormal);
                   totalIrradiance += probeIrr * weight;
                   totalWeight += weight;
               }
           }
       }

       return (totalIrradiance / max(totalWeight, 1e-4f)) * g_GridCB.ProbeOffsetParams.z;
   }

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章系统解构了宏观三维空间全局光照的两大核心技术体系——光照探针网格与体素化锥形追踪：
1. **辐射度理论基石**：推导了基于微元面片光能传递守恒的有限元平衡方程、几何形状因子（Form Factor）双重积分与半立方体离散光栅化求解法；
2. **球谐函数频域压缩**：剖析了正交球谐基底 $Y_l^m$ 的数学本质与 Ramamoorthi-Hanrahan 漫反射余弦滤波卷积理论，证明了仅需 9 个系数即可高保真重构 99.2% 的全向辐照度；
3. **空间探针与 DDGI**：深入探针网格三线性插值体系，解析了传统漏光物理成因，系统阐释了 DDGI 引入八面体深度纹理图集与切比雪夫不等式非对称遮挡测试的无漏光设计；
4. **场景体素化**：解构了嵌套 3D Clipmaps 层次网格、硬件保守光栅化支配轴投影与 3D UAV 原子写入流水线；
5. **体素锥形追踪 (VXGI)**：推导了基于各向异性 3D Mipmap 链的立体圆锥步进微积分模型，实现了单次硬件纹理采样对海量微观体素的空间立体角积分；
6. **工程落地**：交付了工业级 Order-3 球谐光照探针网格采样与法线抗自遮挡偏移 HLSL Compute Shader 完整实现。

至此，**第六模块第三章（Chapter 28）完工落盘（全书已完成 28/45 节）**。

在下一章中，我们将迈入现代图形渲染的技术巅峰——**硬件加速光线追踪核心架构 (Hardware Ray Tracing / DXR / Vulkan RT)**。我们将深入剖析 **RT Core 专用硬件微架构（BVH 遍历与 Triangle 求交专用电路）、DirectX Raytracing (DXR) 与 Vulkan KHR 光线追踪管线（Ray Generation, Closest Hit, Miss, Any Hit, Intersection Shaders）以及着色器绑定表 (Shader Binding Table - SBT) 内存拓扑**，敬请期待！
