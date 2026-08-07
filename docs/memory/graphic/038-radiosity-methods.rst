第038章：Radiosity 方法
======================

核心知识点
----------

Radiosity 求解静态 diffuse 表面之间的能量交换
   它把连续场景切成 patch，并为每个 patch 求单位面积向外离开的总能量。结果主要依赖 emission、diffuse reflectance、patch 几何关系和遮挡，因此在场景固定时与相机位置无关。

基本能量方程把发光、传输和反射连成一个系统
   对 patch ``i``，可写成 ``Bi = Ei + rhoi * sum(Fij * Bj)``。``Ei`` 是自身发光，``Fij`` 是 form factor，``rhoi`` 是 diffuse 反射率。RGB 通常分别求解，因此红墙的高红通道反射率会形成可见 color bleeding。

Form factor 是几何传输权重
   它由 sender/receiver 的面积、朝向、距离和 visibility 决定。相互正对、距离近、无遮挡的 patch 交换更强；背向、远距离或被遮挡时交换更弱。封闭场景中 form-factor 行和应接近 1，并可用 ``Ai*Fij = Aj*Fji`` 检查互易性。

Radiosity 常用迭代而不是直接矩阵求逆
   初始化为 emission 后，反复传播上一轮 radiosity；每一轮可理解为增加一层 diffuse bounce。残差低于阈值时停止。若能量不收敛，应优先检查反射率是否超界、矩阵方向和 form factor 归一化。

Patch 分辨率决定光照空间分辨率
   大片平整墙面可以使用较大 patch；灯具附近、墙角、箱体接触边和颜色边界需要更细划分。后续 lightmap 分辨率再高，也无法恢复 patch 阶段已经丢失的能量变化。

Hemicube 与 Monte Carlo 都是 form factor 近似手段
   Hemicube 把半球可见性转换成五面 rasterization 和深度测试；Monte Carlo 从 patch 半球采样方向并用 ray hit 估计传输。前者误差主要受分辨率影响，后者主要表现为采样噪声。

离线求解结果通常 bake 到 lightmap
   Patch radiosity 经过插值写入 lightmap texel，再做 chart dilation、mipmap 与压缩。运行时 shader 只需采样 baked indirect，因此非常适合静态室内、建筑和移动端场景。

Lightmap UV 与颜色空间属于 radiosity 正确性的一部分
   Reflectance 必须在线性空间参与能量传播；lightmap chart 需要足够 padding，避免 mipmap 把亮区泄漏到邻近 chart。直接使用 sRGB 数值或 UV 间距不足都会制造系统性偏色和漏光。

Radiosity 的强项是稳定低频 diffuse GI
   它擅长颜色渗透、暗部抬升和室内多次漫反射；对动态几何、动态灯光、镜面、透明和 glossy 路径表达弱。它本质上是“把计算预算前移到 bake，用存储换运行时稳定”。

关键路径
--------

离线 Radiosity：

::

   静态场景几何与材质
   → patch 切分
   → 记录面积 / 法线 / reflectance / emission
   → 计算 form factors
   → 校验行和 / 互易关系 / visibility
   → 迭代求 radiosity
   → 检查残差与总能量
   → 插值到 lightmap texel
   → dilation / mipmap / compression
   → 运行时采样 baked indirect
   → 与 direct lighting 合成

问题排查：

::

   albedo/emission 线性空间
   → patch 法线与几何封闭
   → form factor 可见性
   → 行和与互易关系
   → bounce 数与收敛残差
   → baked-indirect-only 视图
   → lightmap UV / padding / mip
   → 最后检查运行时绑定、曝光和额外 ambient

概念辨析
--------

* **Radiosity 与 radiance**：radiosity 表达单位面积向整个半球离开的总能量，适合 diffuse 表面；radiance 还包含方向信息。
* **Form factor 与 reflectance**：form factor 是几何传输比例；reflectance 是材质收到能量后保留多少并重新散射。
* **Patch 与 lightmap texel**：patch 是求解离散单元，lightmap texel 是运行时存储/采样单元，两者分辨率职责不同。
* **Hemicube 与 shadow map**：二者都可利用 raster depth，但 hemicube 用来估计半球几何传输，不是最终相机阴影。
* **Radiosity 与 Path Tracing**：前者偏静态、diffuse、视角无关、可 bake；后者统一处理更多材质和光路，但运行时或离线采样成本更高。
* **Radiosity 与 Photon Mapping**：前者求表面 diffuse 能量系统，后者从光源发射并存储离散 photon，再做局部密度估计。
* **Baked indirect 与 ambient**：baked indirect 已包含多次 diffuse 能量，额外强 ambient 会重复抬高暗部。

本章结论
--------

Radiosity 应按“patch—form factor—能量迭代—lightmap bake”理解。正确性先检查线性 reflectance、法线、遮挡、form-factor 归一和收敛，再检查 lightmap；效果上重点观察颜色渗透、背光面补光和墙角层次。它最适合静态 diffuse 场景，用较高离线成本和存储换取低且稳定的运行时 GI 成本。