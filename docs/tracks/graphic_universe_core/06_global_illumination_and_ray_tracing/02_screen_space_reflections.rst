========================================================================
Chapter 27: 屏幕空间反射 (SSR)：Hi-Z 层次光线步进、厚度边缘衰减与时间性滤波
========================================================================

.. note:: 前置背景与认知承接
   在上一章（Chapter 26）中，我们系统解构了屏幕空间环境光遮蔽（SSAO、HBAO、GTAO），通过对 G-Buffer 深度与法线的局部几何采样，解决了低频漫反射环境光的接触阴影与空间立体感。然而，物理世界中的光线传输不仅包含漫反射，更包含大量遵循微表面折反射定律的高频高光反射（Specular Reflections）。

   在传统光栅化管线中，高光反射通常依赖静态环境立方体贴图（Cubemap）或反射探针（Reflection Probes）。此类方法属于视点无关的静态近似，完全无法反射动态角色、实时特效或近距离物体的局部几何交互。**屏幕空间反射（Screen Space Reflections - SSR）通过直接在屏幕空间已渲染的几何与颜色缓冲区（G-Buffer & Scene Color）中发射物理反射光线，利用光线步进（Raymarching）寻找光线与场景深度的交点，从而以极高性价比实现了全动态场景的局部高光反射。** 本章将深入剖析经典光线步进、层次化分层 Z 缓冲（Hi-Z）几何跳跃加速算法、物理厚度假设、边缘衰减模型、粗糙度 GGX 重要性采样以及基于时空滤波（Temporal Reprojection & SVGF）的降噪体系，并交付工业级 HLSL Compute Shader 实现。

------------------------------------------------------------------------
27.1 屏幕空间反射的物理基础与 2.5D 几何假设
------------------------------------------------------------------------

在基于物理的渲染（PBR）框架中，表面微元沿视线方向 $\mathbf{V}$ 的镜面反射方向 $\mathbf{R}$ 遵循经典反射定律：

.. math::

   \mathbf{R} = 	ext{reflect}(-\mathbf{V}, \mathbf{N}) = 2(\mathbf{N} \cdot \mathbf{V})\mathbf{N} - \mathbf{V}

其中 $\mathbf{N}$ 为表面微观或宏观法线向量，$\mathbf{V} = -	ext{normalize}(\mathbf{P}_{	ext{view}})$ 为由着色点指向摄像机的视线向量。

屏幕空间光线追踪的几何假设与数据源
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

屏幕空间反射（SSR）将原本需要遍历三维场景加速结构（如 BVH）的求交过程，投影并退化为在 **2.5D 屏幕空间高度场（Heightfield）** 上的寻交问题。其核心依赖于延迟渲染管线中的两组核心缓冲区：

1. **G-Buffer 深度图（Depth Buffer）**：表达了摄像机视锥体内所有首个可见表面的世界/观察空间深度分布，相当于一个向摄像机方向展开的连续离散高度场；
2. **场景高动态颜色图（Scene Color Buffer / HDR Target）**：存储了当前帧直射光与漫反射着色完毕后的辐射亮度 $L_o$。

对于屏幕上的任意镜面/高光着色点 $\mathbf{P}$，算法沿反射方向 $\mathbf{R}$ 在三维空间发射一条光线，通过沿光线逐步向前步进（Marching），实时检查光线当前位置是否穿入或落入深度缓冲区所代表的场景几何实体内部。一旦检测到相交，直接读取交点像素位置的 Scene Color 作为反射光强。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                  屏幕空间反射 (SSR) 核心数据流与求交几何拓扑             |
   +-------------------------------------------------------------------------+

                  摄像机视点 (Camera Origin)
                             \
                              \ 视线方向 V
                               \
                                v
      反射光线发射点 P ---------> 表面法线 N
        \                      /
         \                    /
          \ 反射方向 R       /
           \                /
            \              /
             v            v
      +-----------------------------------------+
      |  沿反射光线步进 (Raymarching Steps)     |
      |   P_0 -> P_1 -> P_2 -> P_hit (命中!)    |
      +-------------------+---------------------+
                          |
                          v 投影至屏幕坐标 (u_hit, v_hit)
      +-----------------------------------------+
      | 采样前一阶段着色图 SceneColor(u_hit, v_hit)|
      +-------------------+---------------------+
                          |
                          v 结合 Fresnel-Schlick 项
      +-----------------------------------------+
      | 输出高光反射光强写入当前着色点 P 缓冲区   |
      +-----------------------------------------+

SSR 技术的优势与固有物理边界
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 屏幕空间反射 (SSR) 技术边界与物理成因
   :widths: 20 35 45
   :header-rows: 1
   :class: tight-table

   * - 边界特性
     - 物理表现现象
     - 底层几何成因
   * - **完全动态交互**
     - 动态角色、流水、爆炸火光均能实时倒影
     - 直接采样当前帧已着色的 Scene Color，无需预烘焙。
   * - **屏幕外信息缺失 (Off-screen Miss)**
     - 镜头俯视或移动时，原本水面上的高楼倒影突兀消失
     - 反射光线射向摄像机视锥体外部区域，超出 G-Buffer 记录范围。
   * - **背面与被遮挡表面缺失 (Backface Occlusion)**
     - 前景物体背后的地面无法在水面正确反射
     - G-Buffer 仅记录最前端单一表面，不包含物体背面与被遮挡几何。
   * - **掠射角采样走样**
     - 平行于视平面的地板在远处产生严重断裂与噪点
     - 光线在屏幕空间跨越巨大像素跨度，步进采样率急剧下降。

------------------------------------------------------------------------
27.2 经典线性与对分光线步进 (Linear & Binary Search)
------------------------------------------------------------------------

最直观的求交算法是在三维观察空间（View Space）或二维屏幕空间（Screen Space）沿光线方向以固定步长逐步前进，并在检测到相交时通过二分法（Binary Search）精确锁定表面交点。

光线参数方程与步进更新
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

设着色点在观察空间的位置为 $\mathbf{P}_0 = (x_0, y_0, z_0)$，单位反射方向为 $\mathbf{R} = (R_x, R_y, R_z)$。
沿光线步进参数为 $t > 0$（步长 $\Delta t$），光线在第 $k$ 步的三维空间坐标为：

.. math::

   \mathbf{P}_k = \mathbf{P}_0 + (k \cdot \Delta t) \mathbf{R}

将 $\mathbf{P}_k$ 乘以摄像机投影矩阵 $\mathbf{M}_{	ext{proj}}$ 并执行透视除法，映射至屏幕 UV 坐标 $(u_k, v_k)$ 与齐次投影深度 $z_{	ext{ray}, k}$：

.. math::

   \mathbf{P}_{	ext{clip}} = \mathbf{M}_{	ext{proj}} \begin{bmatrix} \mathbf{P}_k \ 1.0 \end{bmatrix}, \quad u_k = 0.5 \frac{P_{	ext{clip}, x}}{P_{	ext{clip}, w}} + 0.5, \quad v_k = -0.5 \frac{P_{	ext{clip}, y}}{P_{	ext{clip}, w}} + 0.5

.. math::

   z_{	ext{ray}, k} = \frac{P_{	ext{clip}, z}}{P_{	ext{clip}, w}}

相交判定与二分精细化搜索 (Binary Search Refinement)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于每个步进点 $k$，从 G-Buffer 深度纹理中读取实际场景深度 $z_{	ext{scene}, k} = 	ext{SampleDepth}(u_k, v_k)$。

1. **相交发生条件**：若光线自身深度大于或等于场景表面深度（在标准 Z 轴下，即光线位于物体后方或内部），且二者深度差位于物理厚度容差 $T_{	ext{thick}}$ 之内：

   .. math::

      z_{	ext{scene}, k} \le z_{	ext{ray}, k} \le z_{	ext{scene}, k} + T_{	ext{thick}}

2. **二分精细化搜索（Binary Refinement）**：
   一旦在第 $k-1$ 步（未穿透）与第 $k$ 步（已穿透）之间检测到相交区间 $[t_{	ext{prev}}, t_{	ext{curr}}]$，算法立即切换至二分迭代模式。在固定迭代次数（通常 8~16 次）内：

   .. math::

      t_{	ext{mid}} = \frac{t_{	ext{prev}} + t_{	ext{curr}}}{2}

   - 计算 $t_{	ext{mid}}$ 处的空间坐标与投影屏幕深度 $z_{	ext{ray, mid}}$，采样场景深度 $z_{	ext{scene, mid}}$；
   - 若 $z_{	ext{ray, mid}} < z_{	ext{scene, mid}}$（光线仍在空气中未触碰表面），则更新左边界 $t_{	ext{prev}} = t_{	ext{mid}}$；
   - 若 $z_{	ext{ray, mid}} \ge z_{	ext{scene, mid}}$（光线已深入物体），则更新右边界 $t_{	ext{curr}} = t_{	ext{mid}}$。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                粗步进 (Linear March) 与二分精细搜索 (Binary Search)     |
   +-------------------------------------------------------------------------+

                      未穿透 (z_ray < z_scene)       穿透! (z_ray >= z_scene)
                           Step k-1                     Step k
                              *---------------------------*  <--- 粗线性步长
                             /              |              \
                            /               | Mid           \
                           /                v                \
                          *-----------------*-----------------*
                        t_prev           二分中点            t_curr
                          |                 |                   |
                     (在空气中)      (已深入物体内部)      (已深入物体内部)
                          |                 |
                          +=================+
                            新搜索区间 [t_prev, t_mid] 持续二分迭代 8 次
                            最终锁定亚像素级精确相交点 P_hit

------------------------------------------------------------------------
27.3 分层 Z 缓冲光线步进 (Hierarchical-Z / Hi-Z Raymarching)
------------------------------------------------------------------------

尽管固定步长线性步进实现直观，但在长光线传播时存在严重的**算力与精度矛盾**：步长设置过大容易穿透细薄几何体（Leaking / Under-sampling），步长设置过小则单根光线需要数百次 Texture Fetch，极易导致 GPU 显存带宽与 ALU 算力饱和。

为了实现工业级 60fps/120fps 实时性能，现代商业引擎广泛采用 **分层 Z 缓冲（Hi-Z）光线步进加速算法**。

Hi-Z 金字塔的构建原理
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Hi-Z 算法利用 GPU 硬件生成深度图的完整 Mipmap 金字塔（Mip 0 到 Mip $N$）。
与常规颜色纹理的下采样平均滤波不同，**Hi-Z 金字塔的每个父级像素存储其对应 $2 	imes 2$ 子像素中的最保守深度值**：

- **传统正向 Z 缓冲（0.0 Near -> 1.0 Far）**：父级像素存储 $2 	imes 2$ 区域内的 **最小深度值（Minimum Depth）**；
- **逆 Z 缓冲（1.0 Near -> 0.0 Far，现代标准）**：父级像素存储 $2 	imes 2$ 区域内的 **最大深度值（Maximum Depth / 离摄像机最近的表面）**。

因此，在给定的 Mip 层级上，单个像素代表了一个轴对齐的屏幕三维包围盒（AABB）。**如果一条光线在该 Mip 像素所代表的三维包围盒上方掠过，则数学上严格证明该光线绝不可能与该包围盒内部任何更精细的几何表面发生碰撞！**

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                    Hi-Z 深度金字塔最保守深度构建模型                     |
   +-------------------------------------------------------------------------+

      Mip 0 (原始分辨率, 4x4)           Mip 1 (半分辨率, 2x2)       Mip 2 (1x1)
      +----+----+----+----+
      | 0.8| 0.7| 0.4| 0.3|             +---------+---------+
      +----+----+----+----+  Max Pooling|         |         |      +---------+
      | 0.9| 0.6| 0.5| 0.2|  =========> |   0.9   |   0.5   | ===> |   0.9   |
      +----+----+----+----+ (逆Z取最大) +---------+---------+      +---------+
      | 0.1| 0.2| 0.3| 0.3|             |         |         |
      +----+----+----+----+             |   0.4   |   0.3   |
      | 0.3| 0.4| 0.1| 0.2|             +---------+---------+
      +----+----+----+----+

Hi-Z 空间跳跃状态机 (Level Traversal Algorithm)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Hi-Z 算法直接在屏幕空间 DDA 坐标系下运行，维护当前光线位置 $(u, v, z)$ 与当前所在的 Mip 层级 $L$（初始 $L=0$）：

1. **边界步进（Step to Cell Boundary）**：
   计算光线沿 2D 屏幕投影方向穿出当前 Mip $L$ 对应单元格边界所需的最小步长 $t_{	ext{advance}}$，将光线推移至该像素的下一边界；
2. **保守深度测试（Conservative Depth Test）**：
   采样当前 Mip $L$ 单元格的最保守深度 $Z_{	ext{hiz}}$：
   - **未穿透（$z_{	ext{ray}} < Z_{	ext{hiz}}$）**：说明光线完全位于当前空间宏块之外，且前方无遮挡。**执行升层（Level Up, $L = \min(L+1, L_{\max})$）**，在更大的空间步长下高速跳跃跨过空白区域；
   - **穿透可能发生（$z_{	ext{ray}} \ge Z_{	ext{hiz}}$）**：说明光线可能与内部微观几何发生碰撞。
     - 若当前 $L > 0$：**执行降层（Level Down, $L = L - 1$）**，将光线回退并进入更高分辨率子层级进行精细探测；
     - 若当前 $L = 0$：已处于最高精度的原生几何表面，判定为最终命中相交（Hit Found），终止步进。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                   Hi-Z 空间跳跃算法状态机与几何流转                     |
   +-------------------------------------------------------------------------+

                     [ 初始化: L = 0, RayOrigin, RayDir ]
                                      |
                                      v
                             +----------------+
                 +---------> | 步进至当前单元 |
                 |           | 格下一边缘边界 |
                 |           +-------+--------+
                 |                   |
                 |                   v
                 |           +----------------+
                 |           | 采样当前 Mip L |
                 |           | 保守深度 Z_hiz |
                 |           +-------+--------+
                 |                   |
                 |          +--------+--------+
                 |          | 光线是否穿透?   |
                 |          +---+----------+--+
                 |              |          |
                 |    No (未穿透)       Yes (可能相交)
                 |              |          |
                 |              v          v
                 |     +-------------+   +---------------+
                 +--<--|  升层加速   |   | 当前处于 L=0? |
                       |  L = L + 1  |   +---+-------+---+
                       +-------------+       |       |
                                    No (L>0) |       | Yes (L=0)
                                             |       |
                                             v       v
                                       +---------+  +-------------------+
                                       | 降层细化 |  | 命中实际几何表面!|
                                       | L = L-1 |  | Hit & Terminate   |
                                       +----+----+  +-------------------+
                                            |
                                            +---> 回退并进入子级单元格

.. list-table:: 固定步长线性步进 vs Hi-Z 层次光线步进性能与质量对比
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 评价维度
     - 固定步长线性步进 (Linear Step)
     - Hi-Z 层次加速步进 (Hi-Z Marching)
   * - **平均采样次数**
     - 64 ~ 128 次 Texture Fetch / 像素
     - **10 ~ 20 次 Texture Fetch / 像素 (节省 80%)**
   * - **显存带宽开销**
     - 持续读取高分辨率 Mip 0 产生高频 Cache Miss
     - 绝大多数长距离跳跃在低分辨率 Mip 完成，极度契合 L1/L2 Cache
   * - **微小薄体穿透漏算**
     - 步长较大时频繁穿透栏杆、细树枝
     - 顶层未命中严格保证无相交，底层 $L=0$ 严格保证亚像素精确度
   * - **远景大跨度反射**
     - 算力耗尽导致长光线被强制截断
     - 单次大步长可直接跨越半个屏幕空间

------------------------------------------------------------------------
27.4 物理厚度假设与多重边缘衰减模型
------------------------------------------------------------------------

由于屏幕空间 G-Buffer 仅记录单一 2.5D 表面的局限性，SSR 算法必须引入严谨的**物理衰减与边界平滑加权模型**，以消除由于数据缺失引起的视觉撕裂。

物理厚度容差 (Thickness Threshold)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当光线从某一像素前方穿入其记录的深度 $z_{	ext{scene}}$ 后方时，计算机无法直接判断该像素背后究竟是一个薄片（如树叶、纸张），还是一个无限延伸的厚实体（如建筑物、地面）。

若不施加厚度约束，从空中射向地面并在建筑物背后穿过的光线会被错误判定为“命中了建筑物内部”，从而在建筑物后方的地面上产生拉伸的柱状虚假反射。

**算法引入动态物理厚度窗口 $\Delta Z_{	ext{max}}$**：

.. math::

   	ext{HitValid} = (z_{	ext{ray}} - z_{	ext{scene}} \ge 0) \land (z_{	ext{ray}} - z_{	ext{scene}} \le \Delta Z_{	ext{max}}(z_{	ext{scene}}))

厚度容差通常与当前场景深度成正比线性放大（$\Delta Z_{	ext{max}}(z) = \alpha \cdot z + \beta$），以匹配透视投影下的空间膨胀。

屏幕边缘羽化衰减 (Screen Edge Fading / Vignetting)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当反射光线步进至屏幕边界附近时，因屏幕外数据未渲染，反射图像将发生突兀的硬截断。为了平滑过渡，构建二维屏幕边缘衰减加权函数 $W_{	ext{edge}}(u, v)$：

.. math::

   d_u = \min(u, 1.0 - u), \quad d_v = \min(v, 1.0 - v)

.. math::

   W_{	ext{edge}}(u, v) = 	ext{saturate}\left( \frac{d_u}{	ext{Margin}_x} \right) \cdot 	ext{saturate}\left( \frac{d_v}{	ext{Margin}_y} \right)

通常设置边缘安全余量 $	ext{Margin} = 0.1 \sim 0.15$（即屏幕边缘 10%~15% 区域呈光滑平线性渐变归零）。

视线逆向遮挡衰减 (Backward Facing Fading)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当反射光线方向 $\mathbf{R}$ 几乎直指摄像机视点（即 $\mathbf{R} \cdot \mathbf{V} \approx -1.0$）时，反射面反射的是“摄像机背后”的物体，而屏幕空间无法提供任何机后信息。

引入视线朝向衰减权重 $W_{	ext{view}}(\mathbf{R}, \mathbf{V})$：

.. math::

   W_{	ext{view}} = 	ext{saturate}\left( 1.0 - \frac{\max(0, -\mathbf{R} \cdot \mathbf{V})}{\cos(	heta_{	ext{cutoff}})} \right)

综合反射权重与 Fallback 混合
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

最终反射合成权重为各项衰减因子的乘积：

.. math::

   	ext{Weight}_{	ext{final}} = W_{	ext{edge}} \cdot W_{	ext{view}} \cdot W_{	ext{hit}} \cdot (1.0 - 	ext{Roughness})

在最终着色 Pass 中，当 $	ext{Weight}_{	ext{final}} < 1.0$ 时，平滑插值混合局部反射探针（Reflection Probe / Cubemap）或漫反射 IBL，实现屏幕内外视觉的无缝回退（Fallback）。

------------------------------------------------------------------------
27.5 粗糙表面反射与蒙特卡洛 GGX 重要性采样
------------------------------------------------------------------------

理想镜面反射（Roughness $\approx 0$）只需发射单根确定性反射光线 $\mathbf{R}$。但在现实世界中，绝大多数材质具有一定粗糙度（Roughness $\in [0.1, 0.8]$）。粗糙微表面会将入射光散射为一个波瓣（Specular Lobe）。

微面法线采样与波瓣光线发射
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

根据微表面理论，粗糙表面的反射光线方向取决于局部的微观法线（Half-Vector / Microfacet Normal）$\mathbf{H}$。
对于给定的表面粗糙度 $\alpha = 	ext{Roughness}^2$，利用低差异伪随机数对 $(\xi_1, \xi_2) \in [0, 1)^2$ 进行 **GGX / Trowbridge-Reitz 分布可见微面重要性采样（VNDF Sampling）**：

.. math::

   	heta_m = \arccos\left( \sqrt{\frac{1.0 - \xi_1}{\xi_1(\alpha^2 - 1.0) + 1.0}} \right), \quad \phi_m = 2\pi \xi_2

将局部球面坐标 $(	heta_m, \phi_m)$ 变换为切线空间微观法线 $\mathbf{H}$，进而计算散射反射方向：

.. math::

   \mathbf{R}_{	ext{rough}} = 	ext{reflect}(-\mathbf{V}, \mathbf{H})

多粗糙度预滤波 Mipmap 降采样采样策略 (Roughness to Mipmap Mapping)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了在单像素仅发射 1 根光线（1 SPP）的极低算力开销下模拟粗糙高光的空间模糊感，现代管线将光锥足迹（Cone Footprint）映射至颜色缓冲区的 Mipmap 链：

.. math::

   	ext{MipLevel} = 	ext{Roughness} \cdot \log_2(	ext{RayTravelDistance} \cdot 	ext{Scale} + 1.0)

在光线命中点 $(u_{	ext{hit}}, v_{	ext{hit}})$，着色器直接采样经过高斯模糊预处理的 $	ext{SceneColorMipLevel}$，以零额外求交代价近似模拟粗糙反射的漫散射光斑。

------------------------------------------------------------------------
27.6 时间性重投影与空间双边滤波降噪 (Temporal Reprojection & SVGF)
------------------------------------------------------------------------

由于实时性能限制，粗糙 SSR 在单帧通常仅发射 1 SPP 采样，直接输出呈现出极其严重的蒙特卡洛高频白噪声。必须通过 **时空联合降噪流水线（Spatio-Temporal Variance-Guided Filtering - SVGF）** 进行信号重建。

时域历史重投影与混合 (Temporal Reprojection)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

利用 G-Buffer 运动矢量图（Velocity Buffer $\mathbf{V}_{	ext{pixel}}$），将当前像素 $(u, v)$ 重投影回历史前一帧屏幕位置 $(u_{	ext{prev}}, v_{	ext{prev}})$：

.. math::

   u_{	ext{prev}} = u - V_{	ext{pixel}, x}, \quad v_{	ext{prev}} = v - V_{	ext{pixel}, y}

1. **历史有效性检验**：对比当前像素深度与历史深度 $z_{	ext{prev}}$、当前法线与历史法线 $\mathbf{N}_{	ext{prev}}$。若深度差或法线夹角超出阈值（发生几何遮挡或视角突变），则废弃历史缓存；
2. **邻域色彩裁剪（Color Clamping / Variance Clipping）**：
   在当前像素周围 $3 	imes 3$ 窗口内计算局部色彩的均值 $\mu$ 与标准差 $\sigma$ 构建色彩包围盒：

   .. math::

      	ext{AABB}_{\min} = \mu - 1.25\sigma, \quad 	ext{AABB}_{\max} = \mu + 1.25\sigma

   将历史采样值 $C_{	ext{history}}$ 强制裁剪（Clamp）在 AABB 范围内，彻底消除摄像机快速转动时的拖尾鬼影（Ghosting Artifacts）；
3. **指数移动平均混合（EMA）**：

   .. math::

      C_{	ext{temporal}} = 	ext{lerp}(C_{	ext{history, clamped}}, C_{	ext{current}}, \alpha_{	ext{blend}}), \quad \alpha_{	ext{blend}} \approx 0.05 \sim 0.1

空间双边方差引导滤波 (Spatio-Temporal Wavelet Filter)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

经过时域累积后，残存的高频噪波通过两遍或三遍 **À-Trous 小波变换双边滤波**（步进跨度分别设置为 1, 2, 4 像素）进行空域平滑。

核函数权重综合考虑空间距离、深度梯度与局部法线一致性：

.. math::

   W(p, q) = \exp\left( -\frac{\|p - q\|^2}{2\sigma_x^2} \right) \cdot \exp\left( -\frac{|z_p - z_q|}{\sigma_z |
abla z_p| + \epsilon} \right) \cdot \max(0, \mathbf{N}_p \cdot \mathbf{N}_q)^{\sigma_n}

经过 SVGF 滤波后，1 SPP 粗糙 SSR 信号完全收敛为平滑、纯净且精准贴合几何边缘的高保真反射光照。

------------------------------------------------------------------------
27.7 工业级 Hi-Z 屏幕空间反射 Compute Shader (HLSL) 完整实现
------------------------------------------------------------------------

以下是符合 DirectX 12 / Vulkan 工业规范的 Hi-Z 层次光线步进 Compute Shader 核心算法实现：

.. code-block:: hlsl

   // HLSL: 工业级分层 Z 缓冲屏幕空间反射 (Hi-Z SSR) Compute Shader
   // 特性: 屏幕空间 DDA 步进 + Hi-Z 金字塔空间跳跃 + 动态物理厚度 + 屏幕边缘平滑羽化

   #define MAX_HIZ_MIP_LEVEL 6
   #define MAX_RAY_STEPS     48
   #define HIZ_STOP_LEVEL    0

   struct SSRConstants {
       float4x4 ViewMatrix;
       float4x4 ProjMatrix;
       float4x4 InvProjMatrix;
       float4x4 InvViewMatrix;
       float4   ScreenSize;       // xy: Width/Height, zw: 1/Width, 1/Height
       float4   DepthBufferSize;  // xy: HiZ Mip0 Width/Height, zw: 1/HiZ Size
       float    RoughnessCutoff;  // 粗糙度剔除阈值 (如 0.6)
       float    Thickness;        // 物理厚度因子
       float    EdgeFadeRange;    // 边缘羽化宽度 (如 0.1)
       uint     FrameIndex;
   };

   ConstantBuffer<SSRConstants> g_SSRCB         : register(b0);
   Texture2D<float>             g_HiZDepthMap   : register(t0); // 包含 Mipmap 的最保守深度图
   Texture2D<float3>            g_NormalTexture : register(t1);
   Texture2D<float4>            g_SceneColor    : register(t2);
   Texture2D<float4>            g_MaterialRough : register(t3); // R 通道存储 Roughness
   SamplerState                 g_PointSampler  : register(s0);
   SamplerState                 g_LinearSampler : register(s1);

   RWTexture2D<float4>          g_OutSSRColor   : register(u0);

   // 屏幕 UV 与逆 Z 重建观察空间三维坐标
   float3 ReconstructViewPos(float2 uv, float depth) {
       float4 clipPos = float4(uv.x * 2.0f - 1.0f, (1.0f - uv.y) * 2.0f - 1.0f, depth, 1.0f);
       float4 viewPos = mul(g_SSRCB.InvProjMatrix, clipPos);
       return viewPos.xyz / viewPos.w;
   }

   // 观察空间坐标投影至屏幕空间 UV 与深度 [0, 1]
   float3 ProjectViewToScreen(float3 viewPos) {
       float4 clipPos = mul(g_SSRCB.ProjMatrix, float4(viewPos, 1.0f));
       float3 ndc = clipPos.xyz / clipPos.w;
       return float3(ndc.x * 0.5f + 0.5f, -ndc.y * 0.5f + 0.5f, ndc.z);
   }

   // 计算光线穿出当前 Mip 单元格边界所需的光线步进参数 t
   float2 GetCellBoundary(float2 rayPos, float2 rayDir, float2 cellCount) {
       float2 cellIndex = floor(rayPos * cellCount);
       float2 boundary = (cellIndex + max(sign(rayDir), 0.0f)) / cellCount;
       return (boundary - rayPos) / rayDir;
   }

   [numthreads(8, 8, 1)]
   void CSMain(uint3 dispatchThreadID : SV_DispatchThreadID) {
       uint2 pixelCoord = dispatchThreadID.xy;
       if (pixelCoord.x >= (uint)g_SSRCB.ScreenSize.x || pixelCoord.y >= (uint)g_SSRCB.ScreenSize.y)
           return;

       float2 uv = (float2(pixelCoord) + 0.5f) * g_SSRCB.ScreenSize.zw;
       float  depth = g_HiZDepthMap.SampleLevel(g_PointSampler, uv, 0);

       // 过滤天空盒无效背景 (逆 Z 下深度为 0.0)
       if (depth <= 1e-6f) {
           g_OutSSRColor[pixelCoord] = float4(0.0f, 0.0f, 0.0f, 0.0f);
           return;
       }

       float roughness = g_MaterialRough.SampleLevel(g_PointSampler, uv, 0).r;
       if (roughness > g_SSRCB.RoughnessCutoff) {
           g_OutSSRColor[pixelCoord] = float4(0.0f, 0.0f, 0.0f, 0.0f);
           return;
       }

       float3 viewPos = ReconstructViewPos(uv, depth);
       float3 viewNorm = normalize(g_NormalTexture.SampleLevel(g_PointSampler, uv, 0).xyz);
       float3 viewDir = normalize(-viewPos);
       float3 reflectDir = reflect(-viewDir, viewNorm);

       // 忽略指向屏幕后方的反射光线
       if (reflectDir.z > 0.8f && viewPos.z > 0.0f) {
           g_OutSSRColor[pixelCoord] = float4(0.0f, 0.0f, 0.0f, 0.0f);
           return;
       }

       // 构建屏幕空间光线起点与终点
       float3 rayOriginSS = float3(uv, depth);
       float3 rayEndPosVS = viewPos + reflectDir * 100.0f; // 追踪最大 100 米
       float3 rayEndSS = ProjectViewToScreen(rayEndPosVS);
       float3 rayDirSS = rayEndSS - rayOriginSS;

       // 屏幕空间光线步进初始化
       float3 currentRayPos = rayOriginSS;
       int   currentMip = 0;
       int   stepCount = 0;
       bool  hitFound = false;

       // Hi-Z 空间跳跃主循环
       while (stepCount < MAX_RAY_STEPS && currentMip >= HIZ_STOP_LEVEL) {
           // 检查是否超出屏幕边界
           if (currentRayPos.x < 0.0f || currentRayPos.x > 1.0f ||
               currentRayPos.y < 0.0f || currentRayPos.y > 1.0f)
               break;

           // 获取当前 Mip 层的网格分辨率
           float2 currentMipSize = g_SSRCB.DepthBufferSize.xy / float(1 << currentMip);
           float2 tDist = GetCellBoundary(currentRayPos.xy, rayDirSS.xy, currentMipSize);
           float  tAdvance = min(tDist.x, tDist.y);

           // 步进至单元格边界处
           float3 nextRayPos = currentRayPos + rayDirSS * (tAdvance + 1e-4f);
           float  sampledDepth = g_HiZDepthMap.SampleLevel(g_PointSampler, currentRayPos.xy, currentMip);

           // 逆 Z 深度测试 (当前光线深度 <= 场景深度表面时发生穿透)
           if (nextRayPos.z <= sampledDepth) {
               // 光线穿透包围盒表面: 降层细化
               if (currentMip == HIZ_STOP_LEVEL) {
                   // 达到最低 Mip 0 级别，执行厚度测试
                   float depthDelta = sampledDepth - nextRayPos.z;
                   float dynamicThickness = g_SSRCB.Thickness * max(nextRayPos.z, 0.05f);

                   if (depthDelta >= 0.0f && depthDelta <= dynamicThickness) {
                       hitFound = true;
                       currentRayPos = nextRayPos;
                       break;
                   }
                   // 穿透厚度容差边界，视为在物体背后穿过，前进一步
                   currentRayPos = nextRayPos;
               } else {
                   // 降至更精细 Mip 层级
                   currentMip--;
               }
           } else {
               // 未发生碰撞: 推进光线并尝试升层加速跳跃
               currentRayPos = nextRayPos;
               currentMip = min(currentMip + 1, MAX_HIZ_MIP_LEVEL);
           }
           stepCount++;
       }

       if (!hitFound) {
           g_OutSSRColor[pixelCoord] = float4(0.0f, 0.0f, 0.0f, 0.0f);
           return;
       }

       // 计算屏幕边缘羽化衰减
       float2 edgeDist = min(currentRayPos.xy, 1.0f - currentRayPos.xy);
       float  edgeWeight = saturate(edgeDist.x / g_SSRCB.EdgeFadeRange) * saturate(edgeDist.y / g_SSRCB.EdgeFadeRange);

       // 计算视线逆向衰减
       float  viewWeight = saturate(1.0f - max(0.0f, -dot(reflectDir, viewDir)));

       // 计算粗糙度淡出与菲涅尔加权
       float  roughnessWeight = saturate(1.0f - roughness / g_SSRCB.RoughnessCutoff);
       float  finalAlpha = edgeWeight * viewWeight * roughnessWeight;

       // 采样命中位置场景颜色 (结合粗糙度进行 Mip 模糊)
       float  colorMip = roughness * 4.0f;
       float3 hitColor = g_SceneColor.SampleLevel(g_LinearSampler, currentRayPos.xy, colorMip).rgb;

       g_OutSSRColor[pixelCoord] = float4(hitColor * finalAlpha, finalAlpha);
   }

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章系统解构了工业级屏幕空间反射（SSR）的核心算法与微架构体系：
1. **物理基础与假设**：推导了基于 G-Buffer 深度高度场与场景颜色图的 2.5D 光线反射几何模型，客观厘清了屏幕外数据缺失与遮挡物背后盲区的物理边界；
2. **步进算法演进**：对比了解析粗步进加二分精细搜索的收敛特性，深入剖析了分层 Z 缓冲（Hi-Z）金字塔构建与单元格边界跳跃状态机，实现了 80% 的采样算力与显存带宽节约；
3. **物理衰减模型**：建立了动态物理厚度容差、二维屏幕边缘平滑羽化以及视线逆向衰减机制，消除了虚假反射拉伸与硬切撕裂；
4. **粗糙反射与降噪**：推导了基于 GGX VNDF 的微面法线采样、粗糙度-Mip 颜色模糊映射，以及基于运动矢量重投影与小波双边滤波（SVGF）的时空联合降噪体系；
5. **工程实现**：交付了符合现代 GPU 标准的完整 Hi-Z SSR Compute Shader 实现。

至此，**第六模块第二章（Chapter 27）完工落盘（全书已完成 27/45 节）**。

在下一章中，我们将进一步跨越屏幕空间的视锥体局限，深入剖析大尺度与全场景全局光照的两大核心支柱——**探针与体素全局光照（Light Probes & Voxel GI）**。我们将系统解构 **辐射度着色 (Radiosity)、球谐函数 (Spherical Harmonics) 光照探针、辐射度体积 (Irradiance Volume) 以及基于 3D 剪辑图体素锥形追踪 (Voxel Cone Tracing - VXGI)**，敬请期待！
