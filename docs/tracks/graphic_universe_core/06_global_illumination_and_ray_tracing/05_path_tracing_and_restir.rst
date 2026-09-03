========================================================================
Chapter 30: 蒙特卡洛积分与实时路径追踪：重要性采样、多重重要性采样与 ReSTIR 算法
========================================================================

.. note:: 前置背景与认知承接
   在上一章（Chapter 29）中，我们系统剖析了 GPU 硬件加速光线追踪（RT Core）的物理微架构、两级加速结构（TLAS / BLAS）、着色器绑定表（SBT）以及 D3D12 DXR / Vulkan RT 管线与 Ray Query 内联求交机制。硬件 RT Core 解决了光线与宏大多边形场景高速求交的物理硬件瓶颈，使得现代 GPU 具备单帧发射数百万至数千万条求交光线的能力。

   然而，硬件求交仅提供了空间几何可见性（Visibility）与表面命中属性的基础查询。在物理光学中，一个着色点上的出射辐射亮度（Radiance）源自全场景直接光源与多重间接表面反弹的半球积分（Kajiya 渲染方程）。对于包含复杂几何拓扑与高频反射材质的积分，解析求解无法成立。现代物理渲染全面依赖以概率论为基石的蒙特卡洛积分（Monte Carlo Integration）与路径追踪（Path Tracing）。本章将系统推导 **渲染方程的无偏蒙特卡洛估计量、方向与面积测度代数转换、余弦加权与微表面 VNDF 重要性采样（Importance Sampling）、多重重要性采样（MIS）启发式加权、俄罗斯轮盘赌（Russian Roulette）无偏截断、时空储层重要性重采样（ReSTIR DI / GI）微架构，以及工业级实时路径追踪 Compute Shader 完整实现**。

------------------------------------------------------------------------
30.1 渲染方程与无偏蒙特卡洛估计量数学模型
------------------------------------------------------------------------

物理渲染的核心数学基石是卡吉亚（James Kajiya, 1986）提出的 **表面反射渲染方程 (Rendering Equation)**。对于空间中任意非发光或发光表面点 $\mathbf{x}$，沿出射方向 $\omega_o$ 离开表面的光谱辐射亮度 $L_o(\mathbf{x}, \omega_o)$ 定义为自身发光辐射与半球入射光反射积分之和：

.. math::

   L_o(\mathbf{x}, \omega_o) = L_e(\mathbf{x}, \omega_o) + \int_{\Omega^+} L_i(\mathbf{x}, \omega_i) f_r(\mathbf{x}, \omega_i, \omega_o) (\mathbf{n} \cdot \omega_i) \, \mathrm{d}\omega_i

其中各物理量定义如下：
- $L_e(\mathbf{x}, \omega_o)$：表面点 $\mathbf{x}$ 自身向 $\omega_o$ 方向发射的自发光辐射亮度（单位：$\mathrm{W \cdot m^{-2} \cdot sr^{-1}}$）；
- $\Omega^+$：以表面法线 $\mathbf{n}$ 为极轴的单位上半球面方向集合；
- $L_i(\mathbf{x}, \omega_i)$：从半球方向 $\omega_i$ 射入表面点 $\mathbf{x}$ 的入射辐射亮度；
- $f_r(\mathbf{x}, \omega_i, \omega_o)$：双向反射分布函数（BRDF，单位：$\mathrm{sr^{-1}}$）；
- $\mathbf{n} \cdot \omega_i = \cos	heta_i$：朗伯投影余弦衰减因子；
- $\mathrm{d}\omega_i = \sin	heta_i \mathrm{d}	heta_i \mathrm{d}\phi_i$：半球微分立体角测度。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                表面反射渲染方程微分立体角积分几何拓扑                   |
   +-------------------------------------------------------------------------+

                         法线 n
                           ^
                           |    出射方向 \omega_o (朝向相机/上一反弹点)
                           |   /
                           |  /
                           | /
       \omega_i (入射光线) |/ 
              \           +------------------ 表面微元 dA (着色点 x)
               \         / \
                \       /   \  半球积分域 \Omega^+
                 \     /     \
                  v   /       \
                 [ 着色点 x ]---+

蒙特卡洛数值积分 (Monte Carlo Estimator)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于定义在任意高维域 $D$ 上的定积分 $I = \int_D f(x) \, \mathrm{d}x$，若构造一个在 $D$ 上满足 $\int_D p(x) \, \mathrm{d}x = 1$ 且在 $f(x) 
eq 0$ 处恒有 $p(x) > 0$ 的概率密度函数（Probability Density Function - PDF）$p(x)$，从该分布中独立同分布（I.I.D.）抽取 $N$ 个随机样本 $X_1, X_2, \dots, X_N$，则定积分 $I$ 的标准蒙特卡洛估计量 $\langle I \rangle_N$ 定义为：

.. math::

   \langle I \rangle_N = \frac{1}{N} \sum_{k=1}^N \frac{f(X_k)}{p(X_k)}

该估计量具备严格的 **无偏性 (Unbiasedness)**，其数学期望严格等于真实积分值：

.. math::

   \mathbb{E}[\langle I \rangle_N] = \mathbb{E}\left[ \frac{1}{N} \sum_{k=1}^N \frac{f(X_k)}{p(X_k)} \right] = \frac{1}{N} \sum_{k=1}^N \int_D \frac{f(x)}{p(x)} p(x) \, \mathrm{d}x = \int_D f(x) \, \mathrm{d}x = I

方差与大数定律收敛速度 (Variance & Convergence Rate)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

单个样本估计量 $Y_k = \frac{f(X_k)}{p(X_k)}$ 的方差为：

.. math::

   \mathbb{V}[Y_k] = \int_D \left( \frac{f(x)}{p(x)} - I \right)^2 p(x) \, \mathrm{d}x = \int_D \frac{f^2(x)}{p(x)} \, \mathrm{d}x - I^2

由于各样本统计独立，$N$ 样本平均估计量的总体方差为：

.. math::

   \mathbb{V}[\langle I \rangle_N] = \frac{1}{N} \mathbb{V}[Y_k] \implies \sigma(\langle I \rangle_N) = \frac{\sigma(Y_k)}{\sqrt{N}}

根据中心极限定理，蒙特卡洛估计的标准差（即画面均方根视觉噪声）以 $O(1/\sqrt{N})$ 的速度衰减。若要将画面图像噪声降低至原来的 $1/2$，必须将采样数 $N$ 增加至原来的 $4$ 倍（例如从 64 SPP 增至 256 SPP）。这一数学事实决定了：单纯依赖增加每像素样本数（SPP）来消除路径追踪噪声在硬件算力上不可持续，必须通过 **优化概率密度函数 $p(x)$（重要性采样）** 或 **多帧空间复用（ReSTIR）** 降低单样本方差 $\sigma(Y_k)$。

.. list-table:: 蒙特卡洛积分核心数学要素与渲染物理映射
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 数学概念
     - 抽象统计定义
     - 路径追踪物理实现
   * - **被积函数 $f(x)$**
     - 待求空间曲面积分原函数
     - 入射光 $L_i$、材质 BRDF $f_r$ 与几何余弦项 $\cos	heta$ 的乘积
   * - **积分域 $D$**
     - 参数空间几何流形
     - 着色点上半球空间（立体角测度 $\mathrm{d}\omega$）或光源表面（面积测度 $\mathrm{d}A$）
   * - **样本 $X_k$**
     - 从分布 $p(x)$ 中抽取的随机变量
     - 半球出射光线方向向量 $\omega_i$ 或光源表面物理坐标点 $\mathbf{y}$
   * - **概率密度 $p(x)$**
     - 样本在积分域上的微分概率分布
     - 描述向特定方向投射光线的单位立体角概率（$\mathrm{sr^{-1}}$）
   * - **估计量权重 $\frac{f(X_k)}{p(X_k)}$**
     - 单次试验对整体积分的归一化加权
     - 路径在当前反弹点上的局部能量衰减贡献（Throughput Contribution）

------------------------------------------------------------------------
30.2 概率密度函数 (PDF) 与重要性采样 (Importance Sampling)
------------------------------------------------------------------------

当且仅当概率密度函数 $p(x)$ 与被积函数 $f(x)$ 成正比（即 $p(x) = \frac{f(x)}{I}$）时，单个样本的估计量 $\frac{f(X_k)}{p(X_k)} = I$ 恒为常数，此时方差 $\mathbb{V}[\langle I \rangle] = 0$。在实际渲染中，虽然真实积分值 $I$ 未知，但通过构建形状高度契合被积函数局部项（如余弦分布或材质高光瓣）的 PDF，能够大幅压制估计方差。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                逆变换采样法 (Inverse Transform Sampling) 流水线          |
   +-------------------------------------------------------------------------+

      [ 均匀伪随机数 \xi_1, \xi_2 \in [0, 1) ]
                        |
                        v
      [ 累积分布函数 CDF: P(x) = \int_0^x p(t) dt ]
                        |
                        v
      [ 求取 CDF 逆函数: x = P^{-1}(\xi) ]
                        |
                        v
      [ 生成符合目标 PDF p(x) 分布的三维方向向量 \omega_i ]

半球均匀采样 (Uniform Hemisphere Sampling)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在单位半球 $\Omega^+$（总立体角为 $2\pi$）上均匀采样时，PDF 为常数：

.. math::

   p(\omega) = \frac{1}{2\pi}

通过均匀随机数对 $(\xi_1, \xi_2) \in [0, 1)^2$ 映射至球坐标系 $(	heta, \phi)$：

.. math::

   \phi = 2\pi \xi_1, \quad \cos	heta = \xi_2 \implies 	heta = \arccos(\xi_2)

转换为局部切线空间（TBN）笛卡尔坐标：

.. math::

   x = \cos\phi \sin	heta = \cos(2\pi \xi_1) \sqrt{1 - \xi_2^2}, \quad y = \sin\phi \sin	heta = \sin(2\pi \xi_1) \sqrt{1 - \xi_2^2}, \quad z = \cos	heta = \xi_2

余弦加权半球采样 (Cosine-Weighted Hemisphere Sampling)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于理想朗伯漫反射表面（Lambertian Diffuse），BRDF 为常数 $f_r = \frac{\rho}{\pi}$。被积函数主要由余弦投影项 $\cos	heta$ 主导。令 PDF 匹配余弦分布：

.. math::

   p(\omega) = \frac{\cos	heta}{\pi}

使用马利方法（Malley's Method - 将单位圆盘均匀采样垂直投影至半球表面），生成公式为：

.. math::

   r = \sqrt{\xi_1}, \quad \phi = 2\pi \xi_2

.. math::

   x = r \cos\phi = \sqrt{\xi_1} \cos(2\pi \xi_2), \quad y = r \sin\phi = \sqrt{\xi_1} \sin(2\pi \xi_2), \quad z = \sqrt{1 - r^2} = \sqrt{1 - \xi_1}

在此采样下，蒙特卡洛单样本估计量的分子余弦项与分母 PDF 完全相互抵消：

.. math::

   \frac{f_r L_i \cos	heta}{p(\omega)} = \frac{\frac{\rho}{\pi} L_i \cos	heta}{\frac{\cos	heta}{\pi}} = \rho L_i

漫反射计算中的余弦权重与 $\pi$ 因子被数学解析消除，漫反射表面的直接积分方差大幅降低。

微表面 VNDF 重要性采样 (Visible Normal Distribution Function)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于基于 Cook-Torrance 微表面模型的粗糙金属或高光表面，高光反射由 GGX 法线分布函数 $D(\mathbf{m})$ 主导。传统对整个微表面法线分布 $D(\mathbf{m})$ 采样会生成大量处于几何背面或被自身遮挡的无效微表面法线。

现代工业标准（Heitz 2018）采用 **可见微法线分布采样 (Sampling the GGX VNDF)**，即仅对朝向观察方向 $\omega_o$ 且未被自遮蔽的微表面法线集合 $D_{\omega_o}(\mathbf{m})$ 进行重要性采样：

.. math::

   p_{\mathbf{m}}(\mathbf{m}) = D_{\omega_o}(\mathbf{m}) = \frac{G_1(\omega_o, \mathbf{m}) (\omega_o \cdot \mathbf{m}) D(\mathbf{m})}{\cos	heta_o}

通过对出射方向 $\omega_o$ 沿微法线 $\mathbf{m}$ 进行镜面反射生成入射光线 $\omega_i = 2(\omega_o \cdot \mathbf{m})\mathbf{m} - \omega_o$，对应的出射光线立体角 PDF 转换为：

.. math::

   p(\omega_i) = \frac{p_{\mathbf{m}}(\mathbf{m})}{4 (\omega_o \cdot \mathbf{m})} = \frac{G_1(\omega_o, \mathbf{m}) D(\mathbf{m})}{4 \cos	heta_o}

.. list-table:: 常用半球采样策略数学参数与适用场景对照
   :widths: 25 25 25 25
   :header-rows: 1
   :class: tight-table

   * - 采样策略
     - 概率密度函数 $p(\omega)$
     - 坐标生成核心公式
     - 适用着色模型
   * - **半球均匀采样**
     - $p = \frac{1}{2\pi}$
     - $z = \xi_2, \, r = \sqrt{1 - \xi_2^2}$
     - 调试基线、通用环境光
   * - **余弦加权采样**
     - $p = \frac{\cos	heta}{\pi}$
     - $z = \sqrt{1 - \xi_1}, \, r = \sqrt{\xi_1}$
     - 朗伯漫反射表面 (Diffuse)
   * - **GGX VNDF 采样**
     - $p = \frac{G_1 D}{4 \cos	heta_o}$
     - 拉伸视线至半球椭圆坐标解算
     - 粗糙高光与金属表面 (Specular)

------------------------------------------------------------------------
30.3 直接光采样与多重重要性采样 (Multiple Importance Sampling - MIS)
------------------------------------------------------------------------

在渲染包含微小高亮光源（如吊灯、点光源）与光滑镜面物体的场景时，单一采样策略存在天然缺陷：
- **仅采样材质 (BSDF Sampling)**：对于微小光源，随机发射的光线极难命中光源区域，导致直接光照阴影产生大量高频噪点；
- **仅采样光源 (Light Sampling / NEE)**：直接在光源表面采样，对于极度光滑的镜面表面（如镜子、光滑大理石），光源采样点对应的入射方向 $\omega_i$ 在材质 BRDF 高光瓣处的值几乎为零，引发严重的高光噪点（Fireflies）。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |             直接光 Next Event Estimation (NEE) 几何测度转换             |
   +-------------------------------------------------------------------------+

           光源表面 A (采样点 y, 法线 n_L, 面积测度 dA)
                +---------------------+
                |       y (采样点)    |
                +---------\-----------+
                           \  	heta_L (光线与光源法线夹角)
                            \
                             \  距离 r = ||y - x||
                              \
                               \  	heta_x (光线与着色点法线夹角)
                                v
                        [ 着色点 x (法线 n_x, 立体角测度 d\omega) ]

直接光次级事件估计 (Next Event Estimation - NEE)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

NEE 策略在每个表面命中点 $\mathbf{x}$ 上主动向场景光源表面 $\mathbf{y}$ 发射一条阴影射线（Shadow Ray）。由于采样在光源几何表面（面积测度 $\mathrm{d}A$）上执行，而渲染方程基于着色点半球立体角测度 $\mathrm{d}\omega$，必须引入 **雅可比行列式 (Jacobian Determinant)** 进行测度转换：

.. math::

   \mathrm{d}\omega = \frac{\cos	heta_L}{r^2} \, \mathrm{d}A \implies p_{\omega}(\omega_i) = p_A(\mathbf{y}) \frac{r^2}{\cos	heta_L}

其中 $r = \|\mathbf{y} - \mathbf{x}\|$ 为距离，$	heta_L$ 为光线方向 $-\omega_i$ 与光源法线 $\mathbf{n}_L$ 的夹角。

转换后基于光源采样的直接光蒙特卡洛估计量为：

.. math::

   \langle L_{	ext{dir}} \rangle = \frac{L_e(\mathbf{y}, -\omega_i) f_r(\mathbf{x}, \omega_i, \omega_o) \cos	heta_x}{p_A(\mathbf{y})} \frac{\cos	heta_L}{r^2} V(\mathbf{x}, \mathbf{y})

其中 $V(\mathbf{x}, \mathbf{y}) \in \{0, 1\}$ 为两点之间的几何可见性测试函数（由 RT Core 硬件阴影射线求交判定）。

多重重要性采样 (MIS) 与平衡/幂次启发式
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了将 BSDF 采样（技术 $a$）与光源采样（技术 $b$）无偏地结合，维奇（Eric Veach, 1995）提出了 **多重重要性采样（Multiple Importance Sampling - MIS）**。

对于从 $M$ 种采样技术中分别抽取的样本，MIS 估计量定义为：

.. math::

   \langle I \rangle_{	ext{MIS}} = \sum_{i=1}^M \frac{1}{N_i} \sum_{j=1}^{N_i} w_i(X_{i,j}) \frac{f(X_{i,j})}{p_i(X_{i,j})}

权重函数 $w_i(x)$ 必须满足配分条件：$\sum_{i=1}^M w_i(x) = 1$。

1. **平衡启发式 (Balance Heuristic)**：

.. math::

   w_i(x) = \frac{N_i p_i(x)}{\sum_{k=1}^M N_k p_k(x)}

2. **幂次启发式 (Power Heuristic - 工业标准 $\beta = 2$)**：
   通过平方放大高概率技术的权重，进一步抑制低概率技术产生的极端噪点：

.. math::

   w_i(x) = \frac{(N_i p_i(x))^2}{\sum_{k=1}^M (N_k p_k(x))^2}

在执行 MIS 时，关键准则是：**评估任意技术的样本在其他所有技术下的 PDF 时，必须统一转换至同一测度空间（通常统一为着色点处的立体角测度 $p_{\omega}$）**。

.. list-table:: 路径追踪中 BSDF 采样与光源采样 MIS 融合机制
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 采样技术
     - 优势场景
     - 劣势场景
     - MIS 权重计算公式 ($\beta=2$)
   * - **光源采样 (Light / NEE)**
     - 巨大漫反射表面上的微小面积光源
     - 光滑金属镜面、粗糙度极低的高光反射
     - $w_{	ext{light}} = \frac{p_{	ext{light}}^2}{p_{	ext{light}}^2 + p_{	ext{bsdf}}^2}$
   * - **材质采样 (BSDF Sampling)**
     - 粗糙度极低镜面反射、全景大面积天空盒
     - 点光源、极小发光体直接阴影
     - $w_{	ext{bsdf}} = \frac{p_{	ext{bsdf}}^2}{p_{	ext{light}}^2 + p_{	ext{bsdf}}^2}$

------------------------------------------------------------------------
30.4 路径追踪状态机与吞吐量累积 (Path Throughput & Russian Roulette)
------------------------------------------------------------------------

单向路径追踪（Unidirectional Path Tracing）将整条光线路径表示为一个离散状态机。光线从相机出发，沿着几何反射序列递归行进：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                单向路径追踪状态机与 Throughput 能量级联模型             |
   +-------------------------------------------------------------------------+

   [ 相机光线 Camera Ray ] (初始 Throughput T_0 = 1.0)
             |
             v
   [ 第 1 次反弹 (Bounce 0) ] ---> [ NEE 直接光采样 ] ---> 累积至 Pixel L_pixel += T_0 * L_dir0
             |
             | (抽取下一条出射光线 \omega_1, 计算 Throughput 衰减)
             v
   [ 能量更新: T_1 = T_0 * (f_r1 * cos	heta_1) / p(\omega_1) ]
             |
             v
   [ 第 2 次反弹 (Bounce 1) ] ---> [ NEE 直接光采样 ] ---> 累积至 Pixel L_pixel += T_1 * L_dir1
             |
             | (递归推进 ...)
             v
   [ 俄罗斯轮盘赌判定 (Russian Roulette) ]
             |
       +-----+-----+
       |           |
       v           v
   [ 存活: T_k / q ]  [ 终止路径: 退出循环 ]

路径吞吐量权重 (Path Throughput Evolution)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

令第 $k$ 次反弹的着色点为 $\mathbf{x}_k$，入射方向为 $\omega_{i,k}$，出射方向为 $\omega_{o,k}$。定义路径吞吐量权重 $\mathbf{T}_k$ 为前 $k$ 次反弹累积的能量传输系数：

.. math::

   \mathbf{T}_0 = \mathbf{1} = (1.0, 1.0, 1.0)

.. math::

   \mathbf{T}_k = \mathbf{T}_{k-1} \cdot \frac{f_r(\mathbf{x}_k, \omega_{i,k}, \omega_{o,k}) (\mathbf{n}_k \cdot \omega_{i,k})}{p(\omega_{i,k})}

像素最终累积的辐射亮度为各反弹点直接光照发射与 NEE 贡献的加权和：

.. math::

   L_{	ext{pixel}} = \sum_{k=0}^{D-1} \mathbf{T}_k \cdot L_{	ext{emission}}(\mathbf{x}_k) + \sum_{k=0}^{D-1} \mathbf{T}_k \cdot L_{	ext{dir,NEE}}(\mathbf{x}_k)

俄罗斯轮盘赌 (Russian Roulette) 无偏路径截断
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在实际渲染中，若硬性限制最大递归深度 $D_{\max}$，会截断深层多次反弹的高阶间接光（如暗室角落的多重反射），引入能量损失的系统偏差（Bias）。若不加截断，路径可能无限递归导致计算陷入死循环。

**俄罗斯轮盘赌 (Russian Roulette)** 机制通过引入随机终止概率，在有限计算时间内实现严格 **无偏 (Unbiased)** 的路径截断。

在路径反弹达到设定深度（如 $k \ge 3$）后，计算当前吞吐量的最大颜色分量作为存活概率 $q_k$：

.. math::

   q_k = \operatorname{clamp}\left( \max(T_{k,r}, T_{k,g}, T_{k,b}), \, 0.05, \, 0.95 \right)

生成均匀随机数 $\xi \in [0, 1)$：
1. **若 $\xi > q_k$**：立即终止该路径，停止后续反弹；
2. **若 $\xi \le q_k$**：路径继续存活，但必须将吞吐量权重除以存活概率进行能量补偿：

.. math::

   \mathbf{T}_k \leftarrow \frac{\mathbf{T}_k}{q_k}

数学证明其期望值保持不变（无偏性）：

.. math::

   \mathbb{E}[\mathbf{T}_k^*] = q_k \cdot \left( \frac{\mathbf{T}_k}{q_k} \right) + (1 - q_k) \cdot \mathbf{0} = \mathbf{T}_k

波前路径追踪 (Wavefront) vs 巨石内核 (Megakernel) 架构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 GPU 上执行路径追踪存在两种主要的架构形态：

.. list-table:: GPU 路径追踪架构形态对比：Megakernel vs Wavefront
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 架构形态
     - Megakernel 架构 (单着色器全递归)
     - Wavefront 架构 (阶段解耦多队列)
   * - **微架构拓扑**
     - 单个 RayGen/Compute Shader 包含完整反弹 `for` 循环
     - 拆分为 RayGen、RayTrace、MaterialShade、ShadowRay 等独立 Pass
   * - **寄存器压力**
     - 极高：单个线程必须分配容纳所有材质类型的最大 VGPR
     - **极低**：每个阶段着色器按需分配独立 VGPR，占用率高
   * - **SIMT 分支发散**
     - 严重：随反弹加深，同 Warp 内线程路径分化极剧烈
     - **通过硬件/软件队列重排序（Compaction）消除发散线程**
   * - **显存带宽开销**
     - 零显存中间队列开销，状态全在寄存器中
     - 需要在大容量 G-Buffer / RayQueue 中频繁读写路径状态
   * - **工业适用场景**
     - 简单材质场景、实时 1~2 反弹混成管线
     - **影视级离线渲染、复杂全动态多材质路径追踪**

------------------------------------------------------------------------
30.5 时空储层重要性重采样 (ReSTIR DI / GI) 微架构
------------------------------------------------------------------------

在包含成千上万个动态光源（Many-Light Problem）的现代复杂场景中，传统的直接光采样（NEE）无法承受遍历所有光源计算精确 PDF 的代价。2020 年由 Bitterli、Wyman 等人提出的 **ReSTIR（Reservoir-based Spatiotemporal Importance Resampling 时空储层重要性重采样）** 架构，使 GPU 能够以每像素仅发射 1~2 条阴影射线的极低开销，实现数百万动态光源的高质量直接光（ReSTIR DI）与间接光（ReSTIR GI）采样。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                ReSTIR DI 三阶段时空储层重采样微架构流水线               |
   +-------------------------------------------------------------------------+

      [ 阶段 1: 初始候选光源采样 (Initial Candidate RIS) ]
      (从场景 M 个光源中随机抽取 M_0=32 个候选光源, 评估未归一化目标分布 \hat{p})
                               |
                               v
                     [ 初始储层 R_initial ]
                               |
                               v
      [ 阶段 2: 时间维度重采样 (Temporal Reuse) ] <-----+ (读取上一帧历史储层)
      (重投影至历史帧坐标, 验证深度与法线几何一致性)      |
                               |                        |
                               v                        |
                     [ 时间重采样储层 R_temporal ] ------+
                               |
                               v
      [ 阶段 3: 空间邻域重采样 (Spatial Reuse) ]
      (在当前帧屏幕空间随机采集 k 个邻域像素储层并合并)
                               |
                               v
                     [ 最终合并储层 R_final ]
                               |
                               v
      [ 阶段 4: 硬件阴影射线判定 (Visibility Validation) ]
      (向最终胜出的光源 y 发射唯一一条 Shadow Ray, 乘以非受偏权重 W)
                               |
                               v
                     [ 写入直接光渲染缓冲 (UAV) ]

储层数据结构 (Reservoir Data Structure)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

ReSTIR 的核心是在每个像素处维护一个轻量级的固定大小 **储层 (Reservoir)** 结构体：

.. code-block:: cpp

   struct Reservoir {
       uint32_t y;     // 当前选中的胜出样本索引 (如光源 ID 或反弹光线描述符)
       float    w_sum; // 累积权重和 (Weight Sum)
       uint32_t M;     // 参与该储层合并的总样本计数 (Sample Count)
       float    W;     // 最终非受偏蒙特卡洛重采样权重 (Unbiased Weight)
   };

重采样重要性采样 (Resampled Importance Sampling - RIS)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于未归一化的目标光照分布函数 $\hat{p}(\mathbf{y}) = \|\mathbf{L}_e(\mathbf{y}) f_r(\mathbf{x}, \mathbf{y}) \cos	heta\|$：
1. 从提议分布（Proposal Distribution）$q(\mathbf{y})$ 中抽取 $M$ 个候选样本 $\mathbf{y}_1, \dots, \mathbf{y}_M$；
2. 计算每个候选样本的权重 $w_i = \frac{\hat{p}(\mathbf{y}_i)}{q(\mathbf{y}_i)}$；
3. 以概率 $P(	ext{选择} \, \mathbf{y}_i) = \frac{w_i}{\sum_{j=1}^M w_j}$ 在线流式更新储层；
4. 胜出样本的最终无偏重采样权重 $W$ 为：

.. math::

   W = \frac{1}{\hat{p}(\mathbf{y})} \left( \frac{1}{M} \sum_{i=1}^M w_i \right) = \frac{w_{	ext{sum}}}{M \cdot \hat{p}(\mathbf{y})}

储层流式合并算法 (Streaming Reservoir Update)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

流式合并（Chao 1982 算法）允许在极低寄存器开销下将任意新样本或外部储层合并入当前储层：

.. code-block:: cpp

   // 将样本 y 及其权重 weight 更新入储层 r
   void UpdateReservoir(inout Reservoir r, uint y_candidate, float weight, float rng) {
       r.w_sum += weight;
       r.M += 1;
       if (rng * r.w_sum < weight) {
           r.y = y_candidate; // 依概率抢占胜出样本
       }
   }

   // 将另一个完整储层 r_src 合并入当前储层 r_dst
   void CombineReservoirs(inout Reservoir r_dst, Reservoir r_src, float target_pdf_at_src, float rng) {
       float weight = target_pdf_at_src * r_src.W * r_src.M;
       r_dst.w_sum += weight;
       r_dst.M += r_src.M;
       if (rng * r_dst.w_sum < weight) {
           r_dst.y = r_src.y;
       }
   }

时空复用中的几何与可见性有效性检查
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在执行时间重采样（Temporal Reuse）与空间邻域重采样（Spatial Reuse）时，必须严格实施 **几何边缘判定（Geometry Similarity Test）**：
- **深度差异**：$|	ext{Depth}_{	ext{curr}} - 	ext{Depth}_{	ext{sample}}| < 0.05 \cdot 	ext{Depth}_{	ext{curr}}$；
- **法线夹角**：$\mathbf{n}_{	ext{curr}} \cdot \mathbf{n}_{	ext{sample}} > 0.866$（夹角 $< 30^\circ$）。

对于跨越几何边缘或遮挡边界的无效邻域储层，直接丢弃该样本合并，规避几何边缘产生严重的漏光（Light Bleeding）与重影伪影。同时，为了防止时间累积导致历史样本权重无限放大、抑制新光源的响应灵敏度，时间储层的 $M$ 值必须被硬性钳制（如 $M_{	ext{temporal}} \le 20 \sim 30$）。

.. list-table:: ReSTIR DI / GI 核心阶段与参数选型矩阵
   :widths: 20 25 30 25
   :header-rows: 1
   :class: tight-table

   * - 流水线阶段
     - 样本采样数
     - 核心过滤条件
     - 物理输出产物
   * - **Initial Candidates**
     - $M_0 = 16 \sim 32$
     - 从全场景光源网格中粗筛
     - 局部初始储层 $R_{	ext{init}}$
   * - **Temporal Reuse**
     - 1 个历史储层
     - 运动矢量重投影 + 深度法线双边阈值
     - 时间累积储层 $R_{	ext{temporal}}$ ($M \le 30$)
   * - **Spatial Reuse**
     - $k = 4 \sim 8$ 个邻域像素
     - 屏幕空间随机圆形泊松盘采样
     - 空间平滑储层 $R_{	ext{spatial}}$ ($M \le 200$)
   * - **Visibility Resolve**
     - **仅发射 1 条 Shadow Ray**
     - 硬件 RT Core 遮挡判定
     - 最终像素直接光照 $L_{	ext{dir}}$

------------------------------------------------------------------------
30.6 工业级 DXR / HLSL 实时路径追踪与 ReSTIR 核心着色器实现
------------------------------------------------------------------------

以下是符合 DirectX 12 / DXR 1.1 与 Vulkan 规范的工业级 ReSTIR DI 直接光采样与着色 Compute Shader HLSL 完整源码实现：

.. code-block:: hlsl

   // HLSL 6.5+: 工业级 ReSTIR DI (Reservoir Spatiotemporal Importance Resampling) Compute Shader
   // 架构: 初始候选采样 -> 时空合并 -> 硬件单光线可见性测试 -> 最终着色

   struct LightSource {
       float4 PositionRadius; // xyz: 世界坐标, w: 影响半径
       float4 RadianceColor;  // rgb: 辐射通量/颜色, w: 光源类型 (0: 点光, 1: 面积光)
       float4 NormalArea;     // xyz: 光源表面法线, w: 物理表面积
   };

   struct Reservoir {
       uint  LightIndex; // 胜出光源索引
       float WeightSum;  // 权重累加和 (w_sum)
       uint  M;          // 样本计数值
       float W;          // 无偏重采样权重
   };

   struct GBufferData {
       float3 WorldPos;
       float3 WorldNormal;
       float3 Albedo;
       float  Roughness;
       float  Metallic;
       float  LinearDepth;
   };

   ConstantBuffer<SceneConstants>           g_SceneCB     : register(b0);
   StructuredBuffer<LightSource>            g_LightsBuffer: register(t0);
   RaytracingAccelerationStructure          g_SceneTLAS   : register(t1);
   Texture2D<float4>                        g_GBufferNormRough : register(t2);
   Texture2D<float4>                        g_GBufferAlbedo    : register(t3);
   Texture2D<float>                         g_GBufferDepth     : register(t4);
   Texture2D<float2>                        g_MotionVectors    : register(t5);
   StructuredBuffer<Reservoir>              g_HistoryReservoirs: register(t6);

   RWStructuredBuffer<Reservoir>            g_OutReservoirs    : register(u0);
   RWTexture2D<float4>                      g_OutDirectLighting: register(u1);

   // -------------------------------------------------------------------------
   // 随机数生成与工具函数
   // -------------------------------------------------------------------------
   uint Hash(uint seed) {
       seed = (seed ^ 61) ^ (seed >> 16);
       seed *= 9;
       seed = seed ^ (seed >> 4);
       seed *= 0x27d4eb2d;
       seed = seed ^ (seed >> 15);
       return seed;
   }

   float NextFloat(inout uint seed) {
       seed = Hash(seed);
       return float(seed) / 4294967296.0f;
   }

   // -------------------------------------------------------------------------
   // 目标光照分布函数 Target PDF \hat{p}(y)
   // -------------------------------------------------------------------------
   float EvaluateTargetPDF(GBufferData gbuf, LightSource light) {
       float3 lightVec = light.PositionRadius.xyz - gbuf.WorldPos;
       float  distSq = dot(lightVec, lightVec);
       if (distSq > light.PositionRadius.w * light.PositionRadius.w) {
           return 0.0f;
       }

       float3 L = normalize(lightVec);
       float  cosTheta = max(dot(gbuf.WorldNormal, L), 0.0f);
       if (cosTheta <= 0.0f) {
           return 0.0f;
       }

       // 计算未经可见性测试的无阻挡局部物理辐射亮度 (Unshadowed Target Radiance)
       float3 radiance = light.RadianceColor.rgb / max(distSq, 0.01f);
       float3 brdf = gbuf.Albedo * (1.0f / 3.14159265f); // 简化漫反射 BRDF
       float3 f = radiance * brdf * cosTheta;

       // 转换为标量亮度作为未归一化目标分布 \hat{p}
       return dot(f, float3(0.2126f, 0.7152f, 0.0722f));
   }

   // -------------------------------------------------------------------------
   // 储层流式更新原子函数
   // -------------------------------------------------------------------------
   void UpdateReservoir(inout Reservoir r, uint candidateLight, float weight, float rng) {
       r.WeightSum += weight;
       r.M += 1;
       if (rng * r.WeightSum < weight) {
           r.LightIndex = candidateLight;
       }
   }

   // -------------------------------------------------------------------------
   // 主计算着色器入口: ReSTIR DI 生成
   // -------------------------------------------------------------------------
   [numthreads(8, 8, 1)]
   void CS_ReSTIR_DI(uint3 dispatchThreadID : SV_DispatchThreadID) {
       uint2 pixelCoord = dispatchThreadID.xy;
       if (any(pixelCoord >= uint2(g_SceneCB.RenderTargetSize))) {
           return;
       }

       uint pixelIndex = pixelCoord.y * uint(g_SceneCB.RenderTargetSize.x) + pixelCoord.x;
       uint rngSeed = Hash(pixelIndex ^ g_SceneCB.FrameIndex);

       // 1. 读取 G-Buffer 重构表面属性
       float depth = g_GBufferDepth[pixelCoord];
       if (depth >= 1.0f) {
           g_OutDirectLighting[pixelCoord] = float4(0, 0, 0, 1);
           return;
       }

       GBufferData gbuf = UnpackGBuffer(pixelCoord, depth);

       // 2. 阶段 1: 初始候选光源 RIS 采样 (Initial Candidate Sampling)
       Reservoir r;
       r.LightIndex = 0;
       r.WeightSum  = 0.0f;
       r.M          = 0;
       r.W          = 0.0f;

       const uint M_INITIAL = 32;
       uint totalLights = g_SceneCB.NumActiveLights;

       for (uint i = 0; i < M_INITIAL; ++i) {
           uint  candidateLightID = min(uint(NextFloat(rngSeed) * float(totalLights)), totalLights - 1);
           float sourcePDF = 1.0f / float(totalLights); // 均匀光源抽样提议分布 q(y)
           
           LightSource light = g_LightsBuffer[candidateLightID];
           float targetPDF = EvaluateTargetPDF(gbuf, light);
           float w = targetPDF / sourcePDF;

           UpdateReservoir(r, candidateLightID, w, NextFloat(rngSeed));
       }

       // 3. 阶段 2: 时间维度储层复用 (Temporal Reuse)
       float2 motion = g_MotionVectors[pixelCoord];
       int2 prevPixelCoord = int2(float2(pixelCoord) + motion * g_SceneCB.RenderTargetSize + 0.5f);

       if (all(prevPixelCoord >= 0) && all(prevPixelCoord < int2(g_SceneCB.RenderTargetSize))) {
           uint prevPixelIndex = prevPixelCoord.y * uint(g_SceneCB.RenderTargetSize.x) + prevPixelCoord.x;
           Reservoir historyR = g_HistoryReservoirs[prevPixelIndex];

           // 读取历史深度与法线验证几何一致性
           GBufferData historyGbuf = UnpackHistoryGBuffer(prevPixelCoord);
           bool isGeometrySimilar = (abs(gbuf.LinearDepth - historyGbuf.LinearDepth) < 0.05f * gbuf.LinearDepth) &&
                                    (dot(gbuf.WorldNormal, historyGbuf.WorldNormal) > 0.866f);

           if (isGeometrySimilar && historyR.M > 0) {
               historyR.M = min(historyR.M, 20u); // 强制钳制历史权重，防止过度滞后
               LightSource historyLight = g_LightsBuffer[historyR.LightIndex];
               float currentTargetPDF = EvaluateTargetPDF(gbuf, historyLight);
               
               float weight = currentTargetPDF * historyR.W * float(historyR.M);
               r.WeightSum += weight;
               r.M += historyR.M;
               if (NextFloat(rngSeed) * r.WeightSum < weight) {
                   r.LightIndex = historyR.LightIndex;
               }
           }
       }

       // 4. 计算当前阶段的无偏归一化权重 W
       LightSource winningLight = g_LightsBuffer[r.LightIndex];
       float finalTargetPDF = EvaluateTargetPDF(gbuf, winningLight);

       if (finalTargetPDF > 0.0f && r.M > 0) {
           r.W = r.WeightSum / (float(r.M) * finalTargetPDF);
       } else {
           r.W = 0.0f;
       }

       // 保存储层状态供下一帧时间复用与下阶段空间复用
       g_OutReservoirs[pixelIndex] = r;

       // 5. 阶段 3: 硬件单光线阴影求交 (Visibility Validation via RT Core)
       float visibility = 0.0f;
       if (r.W > 0.0f) {
           float3 lightPos = winningLight.PositionRadius.xyz;
           float3 lightDir = lightPos - gbuf.WorldPos;
           float  lightDist = length(lightDir);
           float3 L = lightDir / lightDist;

           RayDesc ray;
           ray.Origin = gbuf.WorldPos + gbuf.WorldNormal * 0.002f; // 法线偏置消除自相交
           ray.Direction = L;
           ray.TMin = 0.001f;
           ray.TMax = lightDist - 0.005f;

           RayQuery<RAY_FLAG_FORCE_OPAQUE | 
                    RAY_FLAG_ACCEPT_FIRST_HIT_AND_END_SEARCH | 
                    RAY_FLAG_SKIP_CLOSEST_HIT_SHADER> q;

           q.TraceRayInline(g_SceneTLAS, RAY_FLAG_NONE, 0xFF, ray);
           while (q.Proceed()) {}

           if (q.CommittedStatus() == COMMITTED_NOTHING) {
               visibility = 1.0f; // 无遮挡
           }
       }

       // 6. 最终直接光照着色输出
       float3 finalRadiance = float3(0, 0, 0);
       if (visibility > 0.0f && r.W > 0.0f) {
           float3 L = normalize(winningLight.PositionRadius.xyz - gbuf.WorldPos);
           float  cosTheta = max(dot(gbuf.WorldNormal, L), 0.0f);
           float3 brdf = gbuf.Albedo * (1.0f / 3.14159265f);
           float3 Li = winningLight.RadianceColor.rgb / max(dot(winningLight.PositionRadius.xyz - gbuf.WorldPos, 
                                                                winningLight.PositionRadius.xyz - gbuf.WorldPos), 0.01f);

           finalRadiance = Li * brdf * cosTheta * (r.W * visibility);
       }

       g_OutDirectLighting[pixelCoord] = float4(finalRadiance, 1.0f);
   }

------------------------------------------------------------------------
小结与下卷导读
------------------------------------------------------------------------

本章系统解构了现代实时与离线路径追踪的概率数学底座与前沿时空重采样微架构：
1. **蒙特卡洛积分数学模型**：从卡吉亚渲染方程出发，建立了无偏估计量公式与 $O(1/\sqrt{N})$ 方差收敛律，证明了优化采样概率分布是降低实时噪点的核心突破口；
2. **重要性采样算法族**：推导了半球均匀、余弦加权（Malley 法）与现代 GGX 可见法线（VNDF）采样的坐标变换方程与解析 PDF；
3. **多重重要性采样 (MIS)**：剖析了直接光 NEE 与材质 BSDF 采样的互补特性，推导了平衡与幂次启发式（Power Heuristic $\beta=2$）加权机制；
4. **路径追踪状态机**：建立了 Throughput 级联衰减模型，阐明了俄罗斯轮盘赌（Russian Roulette）无偏截断原理，并对比了 Megakernel 与 Wavefront 架构的硬件开销；
5. **ReSTIR 时空重采样微架构**：深度解构了轻量储层（Reservoir）、流式更新算法、时间重投影与空间邻域复用拓扑，实现了百万动态光源下每像素仅发射单条阴影射线的高质量实时渲染；
6. **工业级着色器落地**：交付了基于 Compute Shader 与 DXR 内联光线查询的完整 ReSTIR DI 直接光采样与着色代码。

至此，**第六模块（Part 6: 全局光照与光线追踪体系）全量完工（5/5 节，全书累计完成 30/45 节）**。

在下一卷中，我们将正式开启 **第七模块：后处理、抗锯齿与图像重构 (07_post_processing_aa_and_reconstruction)**。我们将深入剖析 **高动态范围 (HDR) 色调映射、ACES 工业色彩管线、物理泛光 (Bloom)、时间性抗锯齿 (TAA) 历史帧重投影机制，以及 DLSS / FSR 2/3 / XeSS 神经超分辨率重构微架构**，敬请期待！
