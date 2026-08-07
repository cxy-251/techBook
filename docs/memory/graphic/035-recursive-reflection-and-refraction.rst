第035章：递归反射与折射
=======================

核心知识点
----------

透明命中点需要同时处理反射和折射两条路径
   相机 ray 命中玻璃、水或透明塑料后，一部分能量沿镜面方向返回环境，另一部分进入介质并从另一侧离开。当前像素颜色来自两条子路径 radiance 的加权组合，而不是简单 alpha 混合。

反射方向由入射方向和定向法线决定
   对单位入射方向 ``I`` 和单位法线 ``N``，镜面反射为 ``R = I - 2(I·N)N``。这里 ``I`` 指向命中点，法线必须已按当前介质边界正确定向。公式只决定方向，不决定反射能量比例。

折射方向由 Snell law 与折射率比决定
   令 ``eta = etaI / etaT``，入射角与透射角满足 Snell law。向量公式中的判别量 ``k = 1 - eta²(1-cos²θ)`` 若小于 0，说明没有实数折射方向，发生 total internal reflection，此时只保留反射路径。

Inside/outside 判定是透明材质的核心状态
   Geometry normal 通常固定朝物体外部。若 ``dot(I,Ng)<0``，光线从外部进入；否则从内部离开。进入时通常使用 ``etaI=1``、``etaT=materialIOR``，离开时交换二者，并翻转参与公式的定向法线。

几何法线与定向法线必须分开保存
   Geometry normal 用于判断表面哪一侧、决定 ray offset；oriented normal 用于 reflect/refract 数学。把几何法线直接覆盖后，后续进入/离开和偏移方向会失去依据。

Fresnel 决定反射与透射的角度权重
   电介质常用 Schlick approximation：``F = F0 + (1-F0)(1-cosθ)^5``，其中 ``F0`` 可由 ``((etaI-etaT)/(etaI+etaT))²`` 得到。玻璃正视角通常透射占主导，掠射角反射逐渐增强。

全反射不是错误分支
   从高折射率介质向低折射率介质传播时，入射角足够大就会出现 TIR。此时 ``k<0``、refraction ray 不存在，Fresnel 权重应直接视为 1。玻璃内部边缘强反射因此可能完全合理。

Ray offset 要根据 outgoing direction 选择偏移侧
   Reflection 通常从表面外侧发出，refraction 可能进入物体内部。固定使用 ``hit + normal*eps`` 会把内部折射 ray 推回错误一侧，造成重复命中、漏交或黑边。应根据 ``dot(outgoingDir, geometryNormal)`` 决定正负偏移。

递归透明材质最容易产生路径数量爆炸
   每个命中理论上最多生成 reflection 与 refraction 两个分支。多层玻璃、镜面和透明对象叠加时，ray 数会随深度快速增长，因此需要 ``MAX_DEPTH``、累计 contribution threshold、材质 flags 和 acceleration structure 共同控制。

GPU 上可把递归改成队列化执行
   数学仍是 inside/outside、reflect、refract、Fresnel 和 offset；实现可以从函数递归变成 wavefront queue、显式栈或硬件 ray tracing shader。改变执行组织不应改变能量和方向语义。

关键路径
--------

透明表面一次命中：

::

   hit record
   → geometry normal 判断 entering / leaving
   → 选择 etaI / etaT
   → 得到 oriented normal
   → 计算 reflection direction
   → 计算 refraction 判别量 k
   → k<0: total internal reflection
   → 否则计算 refraction direction
   → 计算 Fresnel F
   → 按方向分别 offset ray origin
   → trace reflection
   → trace refraction
   → F*Lr + (1-F)*transmissionColor*Lt
   → 返回父路径

玻璃黑边排查：

::

   检查 frontFace / entering
   → 检查 etaI 与 etaT 是否在离开时交换
   → 检查 oriented normal
   → 输出 k / TIR mask
   → 输出 Fresnel F
   → 检查 reflection/refraction direction
   → 检查 outgoing-direction-aware offset
   → 提高递归深度验证是否被截断
   → 最后检查 transmissionColor 与环境返回值

性能控制：

::

   统计 reflection / refraction ray 数
   → 统计平均 bounce depth
   → 记录 Fresnel 低权重分支
   → contribution threshold 裁剪低影响路径
   → 按材质 flags 避免无效方向计算
   → BVH/TLAS 降低每条 ray traversal
   → GPU 上按 ray type / bounce 分队列

概念辨析
--------

* **Geometry normal 与 oriented normal**：前者描述真实表面外向，后者为了当前入射事件调整方向，用于反射折射公式。
* **Entering/leaving 与 frontFace**：它们描述 ray 当前位于介质边界哪一侧，是 IOR 切换和法线定向的依据。
* **IOR 与 Fresnel F0**：IOR 是介质折射属性，F0 是正入射反射率；对电介质可由 IOR 推导，但不是同一个量。
* **Refraction 与 transmission**：refraction 决定透射方向，transmission 描述有多少能量进入透射路径。
* **Total internal reflection 与普通高 Fresnel**：TIR 意味着不存在折射解；普通掠射角则可能仍有少量透射，两者数学边界不同。
* **Alpha blending 与光学透明**：alpha 是覆盖/混合策略，不能代替反射、折射、Fresnel 和介质内部路径。
* **Ray offset 与法线翻转**：offset 决定新 ray 从哪一侧开始；法线翻转决定当前公式的方向，两者相关但承担不同职责。
* **Depth limit 与 contribution limit**：前者限制最长路径，后者按能量价值裁剪分支；两者应同时使用。

本章结论
--------

递归反射与折射必须围绕“介质边界状态—方向数学—Fresnel 能量—ray offset—路径预算”组织。先用 geometry normal 判断 inside/outside，再切换 IOR 和 oriented normal，之后计算 reflect/refract 与 TIR，最后按 Fresnel 混合两条子路径。玻璃黑边和错误倒影优先检查法线、IOR 与 offset，性能问题则优先检查路径数量与 traversal，而不是先改材质颜色。