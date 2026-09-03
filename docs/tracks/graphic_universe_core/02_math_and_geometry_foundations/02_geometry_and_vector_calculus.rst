========================================================================
Chapter 7: 几何与向量微积分：切线空间构建、法线变换与梯度场
========================================================================

.. note:: 前置背景与认知承接
   前一章推导了从模型局部空间到屏幕像素空间的 4x4 齐次坐标变换链条。然而，当物体表面经历非等比缩放或非刚性形变时，传统的几何变换矩阵将直接破坏表面法线（Normal）与切线（Tangent）的正交几何约束。本章将深入微分几何与向量微积分，系统推导逆转置法线矩阵的代数推导过程、基于三角网格 UV 参数化的切线空间（TBN 矩阵）正交化构建算法，并剖析像素着色器中屏幕空间偏导数（ddx/ddy）与标量场梯度的物理求解实现。

------------------------------------------------------------------------
7.1 非等比缩放下法线向量的几何畸变与逆转置矩阵推导
------------------------------------------------------------------------

在局部坐标系中，网格表面任意一点的切线向量 $\mathbf{T}$（与表面相切的微元方向）与表面法线向量 $\mathbf{N}$（垂直于切平面的方向）满足严格的正交几何约束：

.. math::

   \mathbf{T} \cdot \mathbf{N} = 0 \iff \mathbf{T}^T \mathbf{N} = 0

非等比缩放引发的正交性破坏
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

设模型经过包含非等比缩放的仿射变换矩阵 $\mathbf{M}$（例如沿 X 轴拉伸 2 倍：$\mathbf{M} = 	ext{diag}(2, 1, 1)$）。表面切线向量是由相邻顶点的坐标差值定义的（$\mathbf{T} = \mathbf{P}_1 - \mathbf{P}_0$），其变换规律完全遵循模型变换矩阵：

.. math::

   \mathbf{T}' = \mathbf{M} \mathbf{T}

若错误地直接将 $\mathbf{M}$ 应用于法线向量（即令 $\mathbf{N}_{	ext{err}} = \mathbf{M} \mathbf{N}$），变换后的法线与切线内积为：

.. math::

   \mathbf{T}'^T \mathbf{N}_{	ext{err}} = (\mathbf{M} \mathbf{T})^T (\mathbf{M} \mathbf{N}) = \mathbf{T}^T (\mathbf{M}^T \mathbf{M}) \mathbf{N} 
eq 0

由于非等比缩放下 $\mathbf{M}^T \mathbf{M} 
eq \mathbf{I}$，变换后的法线不再垂直于物体表面，导致光照高光与漫反射方向发生严重畸变。

逆转置矩阵的严格数学推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

设正确的法线变换矩阵为 $\mathbf{G}$，即 $\mathbf{N}' = \mathbf{G} \mathbf{N}$。为了确保变换后切线与法线依然正交，必须满足：

.. math::

   \mathbf{T}'^T \mathbf{N}' = (\mathbf{M} \mathbf{T})^T (\mathbf{G} \mathbf{N}) = \mathbf{T}^T (\mathbf{M}^T \mathbf{G}) \mathbf{N} = 0

为使该式对表面任意方向的切线 $\mathbf{T}$ 和法线 $\mathbf{N}$ 均恒成立，充分必要条件为：

.. math::

   \mathbf{M}^T \mathbf{G} = \mathbf{I} \implies \mathbf{G} = (\mathbf{M}^T)^{-1} = (\mathbf{M}^{-1})^T

结论：**法线向量的正确变换矩阵为模型变换矩阵的逆矩阵的转置（Inverse Transpose）**。

- **特殊情况（纯旋转与等比缩放）**：若变换仅包含旋转（正交矩阵满足 $\mathbf{M}^T = \mathbf{M}^{-1}$）和统一等比缩放 $s$，则 $(\mathbf{M}^{-1})^T = \frac{1}{s} \mathbf{M}$。着色器中可直接使用模型矩阵并执行归一化（`normalize`），无需在 CPU 侧逐帧解算逆矩阵。

------------------------------------------------------------------------
7.2 切线空间 (Tangent Space / TBN 矩阵) 的参数化构建算法
------------------------------------------------------------------------

为了在低多边形网格上表现丰富的微观凹凸细节，现代图形学引入了法线贴图（Normal Mapping）。法线贴图中的凸凹扰动定义在物体表面的局部坐标系——**切线空间（Tangent Space）**中。

切线空间由正交的三维基底构成：
- **法线基底 ($\mathbf{N}$)**：网格顶点的宏观几何表面法线；
- **切线基底 ($\mathbf{T}$)**：沿纹理坐标 U 轴正方向递增的表面切向量；
- **副切线基底 ($\mathbf{B}$ - Bitangent)**：沿纹理坐标 V 轴正方向递增的表面切向量。

基于三角面 UV 参数化的 TBN 解算方程
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

考察空间三角形的三个顶点 $\mathbf{P}_0, \mathbf{P}_1, \mathbf{P}_2$，其对应的 UV 坐标分别为 $(u_0, v_0), (u_1, v_1), (u_2, v_2)$。三角形的两条空间边向量 $\mathbf{E}_1, \mathbf{E}_2$ 可由切线基底线性表示：

.. math::

   \mathbf{E}_1 = \mathbf{P}_1 - \mathbf{P}_0 = (u_1 - u_0)\mathbf{T} + (v_1 - v_0)\mathbf{B} = \Delta u_1 \mathbf{T} + \Delta v_1 \mathbf{B}

.. math::

   \mathbf{E}_2 = \mathbf{P}_2 - \mathbf{P}_0 = (u_2 - u_0)\mathbf{T} + (v_2 - v_0)\mathbf{B} = \Delta u_2 \mathbf{T} + \Delta v_2 \mathbf{B}

将其写为矩阵乘法形式：

.. math::

   \begin{bmatrix} \mathbf{E}_1^T \ \mathbf{E}_2^T \end{bmatrix} = \begin{bmatrix} \Delta u_1 & \Delta v_1 \ \Delta u_2 & \Delta v_2 \end{bmatrix} \begin{bmatrix} \mathbf{T}^T \ \mathbf{B}^T \end{bmatrix}

两边左乘 $2 	imes 2$ 矩阵的逆矩阵，解得切线 $\mathbf{T}$ 与副切线 $\mathbf{B}$：

.. math::

   \begin{bmatrix} \mathbf{T}^T \ \mathbf{B}^T \end{bmatrix} = \frac{1}{\Delta u_1 \Delta v_2 - \Delta u_2 \Delta v_1} \begin{bmatrix} \Delta v_2 & -\Delta v_1 \ -\Delta u_2 & \Delta u_1 \end{bmatrix} \begin{bmatrix} \mathbf{E}_1^T \ \mathbf{E}_2^T \end{bmatrix}

施密特正交化 (Gram-Schmidt Orthogonalization) 与手性判定
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

直接解算出的 $\mathbf{T}$ 与网格平滑法线 $\mathbf{N}$ 通常不严格垂直。顶点着色器中必须执行 Gram-Schmidt 正交化：

.. math::

   \mathbf{T}_{	ext{ortho}} = 	ext{normalize}\left( \mathbf{T} - (\mathbf{N} \cdot \mathbf{T}) \mathbf{N} \right)

考虑到纹理展开时可能存在 UV 镜像翻转（UV Mirroring），副切线方向通过叉乘及手性符号（Handedness Sign: $\sigma = \pm 1$）重构：

.. math::

   \mathbf{B} = 	ext{cross}(\mathbf{N}, \mathbf{T}_{	ext{ortho}}) 	imes \sigma

在顶点属性管线中，**仅需向 GPU 传递 4 分量切线属性 `float4 Tangent = [Tx, Ty, Tz, sign]`**，即可在片段着色器中以极低显存带宽开销重建完整正交 TBN 矩阵：

.. code-block:: glsl

   // 片段着色器中重建 TBN 矩阵
   mat3 TBN = mat3(v_Tangent, v_Bitangent, v_Normal);

------------------------------------------------------------------------
7.3 法线贴图采样与切线空间光照解算
------------------------------------------------------------------------

法线贴图中的纹理颜色值通过无符号字节存储于 $[0, 1]$ 区间。在着色器中读取后，首先解包映射至 $[-1, 1]$ 的切线空间单位向量：

.. math::

   \mathbf{n}_{	ext{tangent}} = 2.0 	imes 	ext{texture}(	ext{normalMap}, 	ext{uv}).	ext{rgb} - 1.0

- 当法线贴图未做扰动时，颜色为 RGB $(0.5, 0.5, 1.0)$（浅蓝色），解包后向量为 $[0, 0, 1]^T$，即完全指向切平面法线方向。

世界空间光照 vs 切线空间光照
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 法线贴图光照解算空间策略对比
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 策略类型
     - 核心计算路径
     - 适用场景与工程优劣
   * - 世界空间光照 (World-Space Shading)
     - 在片段着色器中通过 TBN 矩阵将采样法线变换至世界空间：
$\mathbf{N}_{	ext{world}} = 	ext{normalize}(\mathbf{TBN} 	imes \mathbf{n}_{	ext{tangent}})$
     - **现代工业级标准**：通用性强，天然支持多光源计算、环境贴图（IBL）采样与延迟渲染 G-Buffer 写入。
   * - 切线空间光照 (Tangent-Space Shading)
     - 在顶点着色器中将光照方向 $\mathbf{L}$ 与视线方向 $\mathbf{V}$ 通过 $\mathbf{TBN}^T$ 变换至切线空间
     - 仅适用于单光源前向渲染；无法高效支持多光源与基于物理的图像级光照。

------------------------------------------------------------------------
7.4 屏幕空间偏导数 (Screen-Space Derivatives) 与梯度标量场
------------------------------------------------------------------------

GPU 在执行片段着色器时，硬件以 **$2 	imes 2$ 像素四方块（Pixel Quad）** 为基本并发调度单元。这一微架构特性使得 GPU 能够通过相邻像素的值差，硬件实时计算任意标量或向量在屏幕空间中的偏导数：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                 GPU Pixel Quad 硬件偏导数差分解算拓扑                   |
   +-------------------------------------------------------------------------+

   像素四方块 (2x2 Quad):
   +--------------------+--------------------+
   |  P0 (x, y)         |  P1 (x+1, y)       |   水平偏导 ddx(F) = F(P1) - F(P0)
   |  值: F0            |  值: F1            |
   +--------------------+--------------------+
   |  P2 (x, y+1)       |  P3 (x+1, y+1)     |   垂直偏导 ddy(F) = F(P2) - F(P0)
   |  值: F2            |  值: F3            |
   +--------------------+--------------------+

偏导数在图形渲染中的三大核心应用
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **Mipmap 纹理层级自动确定**：
   通过计算纹理坐标 $(u, v)$ 相对于屏幕像素坐标 $(x, y)$ 的偏导数矩阵，评估当前纹理在屏幕上的拉伸足迹（Footprint）：
   
   .. math::
      \rho = \max\left( \sqrt{\left(\frac{\partial u}{\partial x}\right)^2 + \left(\frac{\partial v}{\partial x}\right)^2}, \; \sqrt{\left(\frac{\partial u}{\partial y}\right)^2 + \left(\frac{\partial v}{\partial y}\right)^2} \right), \quad 	ext{MipLevel} = \log_2(\rho \cdot 	ext{TextureSize})

2. **无几何法线时的面法线（Flat Normal）即时重构**：
   对于未导出法线的几何网格，通过世界空间位置的屏幕空间偏导数叉乘，可在片段着色器中即时求解精确面法线：
   
   .. code-block:: glsl

      vec3 dPdx = dFdx(v_WorldPos);
      vec3 dPdy = dFdy(v_WorldPos);
      vec3 flatNormal = normalize(cross(dPdx, dPdy));

3. **程序化条纹与网格自适应抗锯齿 (Analytical Anti-Aliasing)**：
   利用 `fwidth(x) = abs(dFdx(x)) + abs(dFdy(x))` 作为滤波核宽度，结合 `smoothstep` 消除高频几何走样。

------------------------------------------------------------------------
7.5 向量微积分与表面积分在渲染方程中的几何意义
------------------------------------------------------------------------

渲染方程（Rendering Equation）的本质是半球流形上的能量微积分：

.. math::

   L_o(\mathbf{p}, \mathbf{\omega}_o) = L_e(\mathbf{p}, \mathbf{\omega}_o) + \int_{\Omega} f_r(\mathbf{p}, \mathbf{\omega}_i, \mathbf{\omega}_o) L_i(\mathbf{p}, \mathbf{\omega}_i) (\mathbf{n} \cdot \mathbf{\omega}_i) \, d\omega_i

- **微分立体角 (Differential Solid Angle)**：$d\omega = \sin	heta \, d	heta \, d\phi$，描述入射光线在球面投影上的无穷小方向张角；
- **投影立体角与朗伯余弦定律 (Lambert's Cosine Factor)**：项 $(\mathbf{n} \cdot \mathbf{\omega}_i) = \cos	heta$ 描述光线由于入射倾角引起的受光面积几何衰减。

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章从微分几何与向量微积分出发，推导了非等比缩放下逆转置法线变换矩阵的代数推论，剖析了三角网格 UV 切线空间（TBN）的正交化解算与手性判定，并解构了 GPU 硬件 2x2 像素四方块偏导数（`ddx/ddy`）与半球微积分的物理实现。

在掌握了单个多边形表面的微观代数几何后，下一章我们将跃升至多边形几何网格的整体拓扑管理——**多边形网格拓扑数据结构：半边结构 (Half-Edge)、邻域遍历算法与 GPU 顶点缓冲布局**，深入解构流形网格（Manifold Mesh）、半边数据结构的常数级邻域查询，以及工业级 GPU 顶点交错/分流缓冲的最佳工程实践。
