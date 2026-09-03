========================================================================
Chapter 18: 次表面散射 (SSS) 与半透明材质：偶极子扩散、屏幕空间与预积分
========================================================================

.. note:: 前置背景与认知承接
   前一章深入推导了 Cook-Torrance 微表面镜面反射模型、GGX 法线分布与基于能量守恒的金属度-粗糙度管线。Cook-Torrance 以及标准 BRDF 的核心假设是：光线入射点与出射点在空间上完全重合（$x_i = x_o$）。然而对于大理石、玉石、蜡烛、果冻，尤其是人体皮肤（Epidermis 与 Dermis 多层组织）等半透明介质，光线会穿透折射进入物体内部，在介质颗粒间经历成千上万次随机碰撞散射后，从空间另一位置溢出表面——这就是次表面散射（Subsurface Scattering - SSS）。本章将从 BSSRDF（双向散射表面反射率分布函数）物理方程出发，系统剖析 Jensen 偶极子扩散剖面（Dipole Diffusion Approximation）、屏幕空间次表面散射（SSSSS）的高斯核可分离卷积、预积分皮肤渲染（Pre-Integrated Skin Shading）的查找表（LUT）生成数学模型，以及移动端与影视级透明/次表面材质着色器的工程实现。

------------------------------------------------------------------------
18.1 从 BRDF 到 BSSRDF：次表面光传输物理模型
------------------------------------------------------------------------

标准 BRDF 假设出射光线与入射光线在宏观上源于同一点 $x$。若介质内部散射平均自由程（Mean Free Path）较大（如人体皮肤可达数毫米），忽视跨点扩散将导致阴影明暗交界线呈现僵硬的死黑（Sharp Terminator 伪影），完全丧失皮肤特有的通透感与血色漫射。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     BRDF 局部同点反射 vs BSSRDF 次表面光扩散            |
   +-------------------------------------------------------------------------+

   [ 标准 BRDF 局部反射模型 ]               [ BSSRDF 次表面散射模型 ]
      入射光 li         出射光 lo               入射光 li                出射光 lo
         \               /                          \                      /
          \             /                            \                    /
   ========+===========+======= 表面          ========+==================+======= 表面
           |  xi == xo |                              | xi            xo |
           +-----------+                              |   \    /\   /    |
           (微观就地散射)                             |    \--/  \_/     |
                                                      (光子在介质内部长距离扩散)

BSSRDF 8 维物理方程定义
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了精确描述光线从位置 $\mathbf{x}_i$ 沿方向 $\vec{\omega}_i$ 入射，并在物体内部经过多次散射后从位置 $\mathbf{x}_o$ 沿方向 $\vec{\omega}_o$ 出射的过程，图形学引入了 **8 维双向散射表面反射率分布函数（BSSRDF）** $S(\mathbf{x}_i, \vec{\omega}_i, \mathbf{x}_o, \vec{\omega}_o)$：

.. math::

   S(\mathbf{x}_i, \vec{\omega}_i, \mathbf{x}_o, \vec{\omega}_o) = \frac{d L_o(\mathbf{x}_o, \vec{\omega}_o)}{d \Phi_i(\mathbf{x}_i, \vec{\omega}_i)}

根据能量守恒与菲涅尔折射定律，BSSRDF 可以解耦为入射菲涅尔透射率、空间漫反射扩散剖面 $R(\|\mathbf{x}_i - \mathbf{x}_o\|)$ 与出射菲涅尔透射率的乘积：

.. math::

   S(\mathbf{x}_i, \vec{\omega}_i, \mathbf{x}_o, \vec{\omega}_o) = \frac{1}{\pi} F_t(\mathbf{x}_i, \vec{\omega}_i) \cdot R(\|\mathbf{x}_i - \mathbf{x}_o\|) \cdot F_t(\mathbf{x}_o, \vec{\omega}_o)

表面出射总辐射率积分方程
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在表面点 $\mathbf{x}_o$ 沿方向 $\vec{\omega}_o$ 出射的总辐射率需要对整个物体表面积 $A$ 以及入射半球 $\Omega$ 进行双重积分：

.. math::

   L_o(\mathbf{x}_o, \vec{\omega}_o) = \int_{A} \int_{2\pi} S(\mathbf{x}_i, \vec{\omega}_i, \mathbf{x}_o, \vec{\omega}_o) L_i(\mathbf{x}_i, \vec{\omega}_i) (\vec{n}_i \cdot \vec{\omega}_i) \, d\omega_i \, dA(\mathbf{x}_i)

典型半透明材质光学参数矩阵
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 典型半透明材质次表面物理光学参数对照
   :widths: 20 25 25 30
   :header-rows: 1
   :class: tight-table

   * - 材质名称
     - 吸收系数 $\sigma_a \; (	ext{mm}^{-1})$
     - 等效散射系数 $\sigma'_s \; (	ext{mm}^{-1})$
     - 平均自由程 $l = 1 / (\sigma_a + \sigma'_s)$ 与视觉特征
   * - **大理石 (Marble)**
     - `(0.002, 0.004, 0.007)`
     - `(2.19, 2.62, 3.00)`
     - $\approx 0.35	ext{ mm}$；温润半透，微弱冷色扩散
   * - **石蜡 (Wax)**
     - `(0.001, 0.002, 0.004)`
     - `(1.40, 1.60, 2.10)`
     - $\approx 0.60	ext{ mm}$；极强通透感，深层黄色漫晕
   * - **全脂牛奶 (Milk)**
     - `(0.001, 0.001, 0.001)`
     - `(2.55, 3.21, 3.77)`
     - $\approx 0.30	ext{ mm}$；高浓度微粒，各向同性极强纯白散射
   * - **人类皮肤真皮层 (Dermis)**
     - `(0.032, 0.170, 0.480)`
     - `(0.740, 0.840, 1.050)`
     - **红光自由程显著远大于蓝绿光**（红光穿透深达数毫米，呈现血色红晕）

------------------------------------------------------------------------
18.2 Jensen 偶极子扩散剖面 (Dipole Diffusion Approximation)
------------------------------------------------------------------------

对于高散射光学介质（$\sigma'_s \gg \sigma_a$），光子在介质内部经历成千上万次随机碰撞，光场方向完全随机化，可以用**扩散近似理论（Diffusion Approximation）**将复杂的辐射传输方程（RTE）简化为连续标量扩散方程。

偶极子光源物理配置 (Dipole Configuration)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了在介质几何边界处满足物理上的“零内部反射流边界条件”，Henrik Wann Jensen 于 2001 年提出了**偶极子源（Dipole Source）**模型：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                        Jensen 偶极子点光源空间拓扑                      |
   +-------------------------------------------------------------------------+

                负虚点光源 q- (位于表面上方 zv 处, 用于抵消表面通量误差)
                     * (-q)
                     |
                     | zv = zr + 4A * D
                     v
   ==================+========================================== 物理表面 (z = 0)
                     ^
                     | zr = 1 / sigma'_t
                     |
                     * (+q)
                正真实点光源 q+ (位于表面下方 zr 处, 模拟初次折射光通量)

扩散剖面函数 $R(r)$ 解析解公式推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

根据偶极子两个虚拟点光源在表面任意距离 $r = \|\mathbf{x}_i - \mathbf{x}_o\|$ 处的辐射通量叠加，空间扩散剖面 $R(r)$ 的解析表达为：

.. math::

   R(r) = \frac{\alpha'}{4\pi} \left[ z_r \left( \sigma_{	ext{tr}} + \frac{1}{d_r} \right) \frac{e^{-\sigma_{	ext{tr}} d_r}}{d_r^2} + z_v \left( \sigma_{	ext{tr}} + \frac{1}{d_v} \right) \frac{e^{-\sigma_{	ext{tr}} d_v}}{d_v^2} \right]

- **参数定义**：
  - 有效消光传输系数：$\sigma_{	ext{tr}} = \sqrt{3 \sigma_a \sigma'_s}$；
  - 缩减反照率：$\alpha' = \sigma'_s / \sigma'_t$；
  - 正负光源到出射点的空间直线距离：$d_r = \sqrt{r^2 + z_r^2}, \quad d_v = \sqrt{r^2 + z_v^2}$。

------------------------------------------------------------------------
18.3 屏幕空间次表面散射 (SSSSS) 与可分离高斯核滤波
------------------------------------------------------------------------

在实时游戏引擎中，直接在 3D 几何表面执行面积分 $dA$ 会造成不可接受的性能开销。Jorge Jimenez 等人开创了**屏幕空间次表面散射（Separable Subsurface Scattering - SSSSS）**技术。

扩散剖面的高斯函数和拟合
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

真实皮肤的非线性扩散剖面 $R(r)$ 具有极度陡峭的核心与平缓的拖尾。Jimenez 证明 $R(r)$ 可以高精度拟合为 5~6 个加权高斯核（Gaussian Profiles）的线性组合：

.. math::

   R(r) = \sum_{k=1}^{6} w_k \cdot \frac{1}{2\pi \sigma_k^2} \exp\left( -\frac{r^2}{2\sigma_k^2} \right)

可分离核 (Separable Filter) 二维卷积拆解
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

由于高斯核具备二维各向同性且数学可分离，原本复杂度为 $O(M^2)$ 的二维屏幕像素模糊，可被精确拆解为**水平（Horizontal）与垂直（Vertical）两次一维卷积**：

.. math::

   I_{	ext{sss}}(x, y) = 	ext{Blur}_Y \Big( 	ext{Blur}_X \big( I_{	ext{diffuse}}(x, y) \big) \Big)

将采样纹理读取次数从 $25 	imes 25 = 625$ 次暴跌至 $25 + 25 = 50$ 次，使得在 4K 分辨率下实时运行 SSS 成为现实！

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                   屏幕空间次表面散射 (SSSSS) 两 Pass 流水线             |
   +-------------------------------------------------------------------------+

   [ G-Buffer 阶段 ]: 渲染纯漫反射光照图 (Diffuse RT) + 深度图 (Depth Buffer)
        |
        v
   [ Pass 1: 水平可分离模糊 (Horizontal SSS Filter) ]
        |  * 读取相邻水平像素颜色，结合深度差权重执行高斯加权累加
        v
   [ 中间瞬态渲染目标 (Temp SSS Ping-Pong RT) ]
        |
        v
   [ Pass 2: 垂直可分离模糊 (Vertical SSS Filter) ]
        |  * 读取相邻垂直像素颜色，结合深度差权重累加
        v
   [ 最终合成 ]: SSS 漫反射图 + 独立未模糊的 Specular 镜面高光图

深度感知双边权重 (Depth-Aware Bilateral Weight)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了防止前景人物面颊边缘的红光扩散到远处的背景墙面上（造成光晕边缘渗漏出血 Bleeding Artifacts），卷积核必须根据像素间的观察空间深度差 $\Delta z$ 施加双边抑制：

.. math::

   w_{	ext{final}}(i) = w_k(i) \cdot \exp\left( -\frac{|z_{	ext{center}} - z_{	ext{sample}}|^2}{2 \sigma_z^2} \right)

------------------------------------------------------------------------
18.4 预积分皮肤渲染 (Pre-Integrated Skin Shading) 数学模型与 LUT
------------------------------------------------------------------------

在移动端 GPU 或受限功耗设备上，两次屏幕后处理 Pass 依然存在带宽压力。Penner 与 Borshukov 提出了革命性的**预积分皮肤渲染（Pre-Integrated Skin Shading）**技术，将复杂的次表面光传输降维离线烘焙至一张紧凑的 **2D 查找表（Lookup Table - LUT）** 中。

算法物理洞察：曲率与散射解耦
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Penner 发现，皮肤上大面积的柔和血色散射主要受控于两个核心变量：

1. **局部表面法线朝向光照的夹角余弦**：$\vec{n} \cdot \vec{l} = \cos 	heta$；
2. **物体表面局部曲率半径的倒数**：$\kappa = 1 / \rho = 	ext{Curvature}$（曲率越大的区域如鼻尖、耳垂，光线穿透并从阴影区溢出的比例越高）。

预积分积分方程与 2D LUT 生成
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

将高斯次表面扩散剖面 $R(x)$ 在半径为 $\rho$ 的标准圆柱体表面进行环向漫反射积分，计算任意法线角 $	heta$ 下出射光通量的严格积分：

.. math::

   E(\vec{n} \cdot \vec{l}, 1/\rho) = \frac{\int_{-\pi}^{\pi} \max(0, \cos(	heta + \phi)) \cdot R\left( 2\rho \sin(\phi/2) \right) \, d\phi}{\int_{-\pi}^{\pi} R\left( 2\rho \sin(\phi/2) \right) \, d\phi}

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       预积分皮肤 2D LUT 纹理拓扑结构                    |
   +-------------------------------------------------------------------------+

      曲率 1/rho (Curvature)
        ^
        |   [ 高曲率: 鼻尖/耳垂 ] -> 阴影交界线极宽，呈现饱和深红晕影
        |   [ 中曲率: 面颊/颈部 ] -> 阴影交界线柔和，呈现浅红过渡
        |   [ 低曲率: 额头/平面 ] -> 接近标准 Lambert 漫反射
        |
        +----------------------------------------------------> N dot L (-1.0 ~ 1.0)
        (暗面 背光区)              (阴影交界区 Terminator)           (亮面 顺光区)

运行时曲率计算与 HLSL 着色实现
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

运行时无需执行任何卷积积分，仅需利用屏幕像素导数指令 `ddx` / `ddy` 动态提取法线曲率，单次纹理采样即可获得媲美离线渲染的真实皮肤质感：

.. code-block:: hlsl

   // 运行时提取几何曲率
   float CalculateCurvature(float3 worldNormal, float3 worldPos)
   {
       float3 dNdx = ddx(worldNormal);
       float3 dNdy = ddy(worldNormal);
       float3 dPdx = ddx(worldPos);
       float3 dPdy = ddy(worldPos);

       float deltaN = length(cross(dNdx, dNdy));
       float deltaP = length(cross(dPdx, dPdy));

       return saturate((deltaN / max(deltaP, 0.0001f)) * 0.05f);
   }

   // 预积分皮肤漫反射采样
   float3 EvaluatePreIntegratedSkin(float3 N, float3 L, float curvature, Texture2D skinLUT, SamplerState lutSampler)
   {
       float NdotL = dot(N, L);
       // 将 NdotL (-1~1) 映射到 UV 坐标 (0~1)
       float2 lutUV = float2(NdotL * 0.5f + 0.5f, curvature);

       return skinLUT.Sample(lutSampler, lutUV).rgb;
   }

------------------------------------------------------------------------
18.5 背光透射 (Translucency) 与多层皮肤着色器工程实现
------------------------------------------------------------------------

当强光源从人物头部后方照射时，耳朵、鼻翼等薄壁器官会呈现出强烈的半透明泛红发光现象——这就是**背光透射（Forward Scattering Transmission）**。

薄壁厚度近似与透射着色方程
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

利用阴影贴图（Shadow Map）估算物体内部穿透厚度 $\Delta d = d_{	ext{pixel}} - d_{	ext{shadow}}$：

.. math::

   I_{	ext{trans}} = \exp\left( -\sigma_t \Delta d \right) \cdot 	ext{saturate}\left( \vec{v} \cdot (-\vec{l} + \vec{n} \cdot w_{	ext{distortion}}) \right)^{	ext{power}} \cdot C_{	ext{subsurface}}

完整工业级多层皮肤 HLSL 着色器代码
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: hlsl

   float3 EvaluateHumanSkinShader(
       float3 N, float3 V, float3 L, float3 lightColor,
       float3 albedo, float roughness, float curvature, float thickness,
       Texture2D skinLUT, SamplerState lutSampler)
   {
       // 1. 预积分次表面散射漫反射 (Pre-Integrated SSS)
       float3 sssDiffuse = EvaluatePreIntegratedSkin(N, L, curvature, skinLUT, lutSampler) * albedo;

       // 2. 双层表皮镜面高光 (Dual-Lobe GGX Specular: 油质外层 + 潮湿真皮层)
       float3 H = normalize(V + L);
       float NdotH = max(dot(N, H), 0.0f);
       float NdotV = max(dot(N, V), 0.00001f);
       float NdotL = max(dot(N, L), 0.00001f);

       // 外层微弱平滑高光 (Roughness = 0.2, 权重 = 0.15)
       float specLobe1 = DistributionGGX(N, H, 0.2f) * 0.15f;
       // 基层粗糙漫高光 (Roughness = 0.5, 权重 = 0.85)
       float specLobe2 = DistributionGGX(N, H, roughness) * 0.85f;
       float3 specular = (specLobe1 + specLobe2) * FresnelSchlick(max(dot(H, V), 0.0f), float3(0.04f, 0.04f, 0.04f));

       // 3. 背光透射红晕 (Translucency Transmission)
       float3 transL = L + N * 0.3f; // 沿法线轻微扭曲
       float transDot = pow(saturate(dot(-transL, V)), 8.0f);
       float3 transmission = exp(-thickness * float3(0.2f, 1.2f, 2.5f)) * transDot * float3(0.9f, 0.1f, 0.05f);

       return (sssDiffuse + specular + transmission) * lightColor * NdotL;
   }

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章从 BSSRDF 8 维传输方程出发，推导了高散射介质下的 Jensen 偶极子扩散近似解，解构了屏幕空间次表面散射（SSSSS）的可分离高斯双边卷积流水线，以及基于曲率与法线夹角的预积分（Pre-Integrated Skin）2D LUT 极速生成与采样架构。

次表面散射解决了介质内部的光传输与柔化，但在宏观场景中，光照与形体立体感的另一半基石来自光线被不透明遮挡物阻断形成的投影——**阴影生成技术全景：Shadow Mapping 锯齿、级联阴影 (CSM)、PCF 软阴影与 PCSS**。下一章我们将全面深入阴影贴图的透视走样、级联分割（CSM）平滑过渡、百分比接近滤波（PCF）以及基于物理遮挡距离的接触硬化软阴影（PCSS）硬件实现机制。
