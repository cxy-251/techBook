第034章：基础 Ray Tracing 算法
============================

核心知识点
----------

基础 Ray Tracing 围绕 ``trace(ray, depth)`` 展开
   Primary ray 命中表面后，材质阶段计算直接光，并按需要生成 shadow、reflection、refraction 等次级光线。每条次级光线再次查询场景，返回 radiance，再由父调用按材质权重合成。

Primary、shadow、reflection、refraction ray 具有不同查询语义
   Primary ray 要找最近可见表面；shadow ray 只判断命中点到光源之间是否存在遮挡；reflection ray 返回镜面方向看到的场景颜色；refraction ray 返回透过介质后看到的颜色。它们共享 Ray 数据结构，但 ``t`` 区间、终止条件和返回值不同。

Shadow ray 应使用有限 ``tMax``
   点光源可见性查询只需要检查命中点到光源的区间，因此 ``tMax`` 应接近 ``distanceToLight``。光源后方物体不能算作遮挡。Shadow ray 常使用 any-hit 逻辑，找到第一个有效不透明遮挡即可退出。

Reflection ray 使用法线镜像入射方向
   镜面方向由 ``R = I - 2(I·N)N`` 得到。Reflection 子路径返回的 radiance 乘 reflectance 后加入当前命中点。镜面中的对象仍需要完整 shading，因此 reflection 命中漫反射物体后也应继续执行 direct light 和 shadow visibility。

Refraction ray 把透明材质纳入同一递归框架
   基础阶段只需明确进入/离开、IOR、法线方向和透射权重。透明材质的真正方向推导与 Fresnel 分配放到下一章，但算法结构已经是“生成次级 ray → trace → 返回颜色 → 混合”。

Ray origin offset 用来避免自相交
   次级光线若直接从数学命中点出发，浮点误差会导致 ``t≈0`` 再次命中同一表面，产生 acne、黑点或假阴影。稳定实现要结合 ``tMin`` 与法线方向偏移，并让 epsilon 随场景尺度变化。

递归必须有硬边界和能量边界
   ``maxDepth`` 防止无限反射；energy/contribution threshold 根据累计 throughput 终止低贡献路径；材质 flags 可直接阻止不需要的分支。过低 depth 会产生镜面黑块和透明路径截断，过高 depth 会快速放大求交成本。

Russian roulette 是概率终止而非简单截断
   当路径贡献较低时，可以按概率终止，并对存活路径做概率补偿，从而降低平均路径长度并尽量保持期望值。它属于 Monte Carlo 思路，在基础递归模型中应理解其目的，而不是当成固定阈值的替代写法。

Hit record 是 geometry 与 shading 的接口
   Intersection 阶段负责 position、normal、frontFace、material id；shading 阶段读取这些事实，决定 direct light、shadow query 和次级 ray。把几何与材质逻辑分层，才能分别调试求交错误与着色错误。

分项输出比最终 beauty 更适合递归调试
   Depth、normal、shadow mask、direct color、reflection buffer、refraction buffer、ray count 都应能单独观察。这样可以区分“ray 没生成”“ray 方向错误”“命中正确但权重错误”和“最终颜色空间错误”。

关键路径
--------

Whitted-style 基础递归：

::

   camera pixel
   → primary ray
   → closest hit
   → miss: background
   → hit: direct shading
   → shadow ray 做 light visibility
   → material 判断
   → 可选 reflection ray
   → 可选 refraction ray
   → trace 子路径
   → 按 reflectance / transmittance 混合
   → 返回父调用
   → framebuffer

Shadow ray：

::

   hit position
   → 沿 normal 偏移 origin
   → direction = normalize(lightPos - hitPos)
   → tMax = distanceToLight - epsilon
   → any-hit 查询
   → blocked / visible
   → 调制直接光

递归问题排查：

::

   检查 primary hit / depth / normal
   → 单独输出 direct color
   → 单独输出 shadow mask
   → 单独输出 reflection buffer
   → 单独输出 refraction buffer
   → 检查 ray origin offset
   → 检查 maxDepth / contribution
   → 最后检查颜色混合与 display transform

概念辨析
--------

* **Primary ray 与 secondary ray**：primary 从相机出发决定首个可见表面；secondary 从命中点出发查询阴影、反射、折射等间接可见性。
* **Closest-hit 与 shadow any-hit**：前者返回最近完整 hit record；后者只需要遮挡布尔结果，执行目标不同。
* **递归深度与光照物理深度**：实现中的 ``depth`` 是算法预算；实际光路可能因为材质终止、miss 或贡献阈值更早结束。
* **Energy threshold 与 Russian roulette**：前者是确定性裁剪，会引入截断偏差；后者是概率终止并做权重补偿。
* **Reflection weight 与 Fresnel**：固定 reflectance 是基础材质参数；Fresnel 会进一步让反射权重随入射角变化。
* **Ray offset 与 depth bias**：二者都处理数值自交，但 ray offset 发生在新光线起点，shadow-map depth bias 发生在光栅深度比较，两者不是同一机制。
* **Recursive function 与 GPU wavefront**：递归函数是算法表达；GPU 工程实现可改成显式队列或循环，光路语义不变。

本章结论
--------

基础 Ray Tracing 的主干是“命中—局部着色—生成次级 ray—递归查询—贡献回传”。Primary、shadow、reflection、refraction ray 要分别定义查询区间和返回语义；正确性依赖 hit record、offset、方向和颜色权重，性能依赖 ray 数、递归深度与求交次数。先用分项 buffer 验证每类 ray，再讨论更复杂的 Fresnel、Monte Carlo 和 BVH，递归光路才不会失去因果关系。