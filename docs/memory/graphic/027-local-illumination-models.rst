第027章：局部光照模型
=====================

核心知识点
----------

局部光照模型计算当前表面点的直接光贡献
   它以表面位置 ``P``、法线 ``N``、光照方向 ``L``、视线方向 ``V``、材质参数、灯光参数和可见性为输入，输出当前 fragment 的直接光照颜色。这里的“局部”表示只处理当前表面点附近可直接获得的信息，不包含多次反弹和跨表面全局传输。

所有方向量必须位于同一坐标空间
   ``P``、``N``、``L``、``V`` 可以统一在 world space 或 view space 中计算，但不能混用。高光随物体漂移、明暗方向反转和 normal map 凹凸翻转，优先检查空间和方向定义，而不是先修改公式。

Lambert 漫反射由 ``N·L`` 决定表面受光程度
   基础项为 ``max(dot(N,L),0)``，再乘 albedo、light color、intensity、attenuation 和 shadow visibility。Albedo 应在线性颜色空间参与光照；若 sRGB 数据直接相乘，整体亮度关系会失真。

Phong 与 Blinn-Phong 用经验公式描述镜面高光
   Phong 比较反射向量 ``R`` 与 ``V``，Blinn-Phong 比较半程向量 ``H=normalize(L+V)`` 与 ``N``。Shininess 越高，高光越窄。两种模型的指数不能简单一一对应，切换模型时要重新标定视觉宽度。

点光衰减与光照角度是两条独立路径
   ``N·L`` 表示朝向，attenuation 表示距离。点光常使用常量、一次项和二次项组合的倒数；方向光通常没有距离衰减。Spot light 还需要额外 cone factor。把所有灯光强度问题都归因到 ``N·L`` 会掩盖距离和单位错误。

Normal map 先在切线空间解码，再进入统一光照空间
   纹理值通常从 ``[0,1]`` 映射到 ``[-1,1]``，随后经 TBN 变换并重新归一化。Tangent handedness、bitangent 方向、green channel 约定或纹理被错误标记为 sRGB，都会让局部凹凸方向异常。

Ambient 与 emission 不属于同一类直接光项
   Ambient 是低频补光近似，常与 albedo 相乘；emission 是材质自身输出，通常直接加到最终颜色，不依赖 ``N``、``L``、``V``。Emission 让表面变亮，不等于它自动照亮周围场景。

多灯成本主要来自每 fragment 的遍历与阴影采样
   Forward 路径中灯光越多，ALU、buffer 读取和 shadow fetch 会随像素面积放大。大规模场景应通过 per-object light list、tiled/clustered lighting 或 deferred path 限制每个 fragment 实际评估的灯光集合。

关键路径
--------

单个 fragment 的直接光照：

::

   world/view position P
   → 几何法线或 normal map 得到 N
   → light data 得到 L、颜色、强度、距离
   → camera data 得到 V
   → 计算 NdotL
   → 计算 attenuation
   → 计算 diffuse
   → 计算 Phong/Blinn-Phong specular
   → 乘 shadow visibility
   → 加 ambient 与 emission
   → 写入线性 HDR target
   → 后续 tone mapping / sRGB 输出

局部光照错误排查：

::

   先输出常量色确认 fragment 与 render target
   → 输出 albedo 检查绑定和颜色空间
   → 输出 N、L、V 调试色
   → 检查 NdotL
   → 固定 attenuation=1
   → 固定 shadowVisibility=1
   → 单独输出 diffuse 与 specular
   → 最后恢复 ambient、emission、曝光和多灯

概念辨析
--------

* **Local illumination 与 global illumination**：前者只估计当前点的直接光和局部材质响应；后者还处理跨表面、多次反弹和间接光传输。
* **Diffuse 与 specular**：diffuse 主要描述宽角度散射，specular 描述视角相关镜面高光；二者输入和视觉作用不同。
* **Phong 与 Blinn-Phong**：Phong 使用反射向量，Blinn-Phong 使用半程向量；都属于经验模型，不是完整物理微表面 BRDF。
* **Attenuation 与 shadow**：attenuation 表示光随距离衰减，shadow 表示光路是否被遮挡，两者可以同时让直接光变暗，但物理原因不同。
* **Albedo 与 light color**：albedo 是表面反射颜色，light color 是入射光谱颜色；二者在线性空间相乘后形成直接光颜色。
* **Normal map 与几何法线**：几何法线定义低频表面方向，normal map 只改变着色方向，不改变真实轮廓。
* **Ambient 与 emission**：ambient 是环境补光近似；emission 是表面自发光输出，不能互相替代。

本章结论
--------

局部光照应沿“输入资源—统一空间—角度项—距离项—可见性—颜色合成”理解。画面异常先检查 ``P/N/L/V`` 的空间和方向，再检查 albedo 颜色空间、attenuation 与 shadow，最后检查 diffuse/specular 合成；性能问题则优先看屏幕覆盖、灯光数量、纹理采样和阴影采样，而不是先微调某个数学公式。