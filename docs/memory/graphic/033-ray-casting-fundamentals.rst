第033章：Ray Casting 基础
========================

核心知识点
----------

Ray Casting 解决 primary visibility
   对每个像素生成一条 camera ray，在场景中寻找最近有效交点，并把最近命中转换为 normal、depth、material 等后续 shading 输入。它只回答“相机沿这个方向首先看到什么”，不包含递归反射、折射和间接光。

Ray 的统一表示是 ``r(t)=o+t*d``
   ``o`` 是 origin，``d`` 是 direction，``t`` 表示沿光线前进的参数。查询必须带 ``tMin/tMax``：``tMin`` 排除原点附近数值噪声，``tMax`` 限制有效搜索距离。Direction 归一化后，``t`` 可近似直接解释为距离。

Closest hit 的核心是最小正向 ``t``
   不同几何求交最终都要产生候选 ``t``。只有位于有效区间内、且小于当前 ``closestT`` 的命中才能覆盖旧结果。Hit record 应统一保存 ``t``、position、normal、primitive/material id 与 front-face 信息。

球、平面、三角形和 AABB 使用不同数学，但输出合同相同
   Sphere 求二次方程根；plane 解一元线性方程；triangle 常用 Möller–Trumbore 同时求 ``t/u/v``；AABB 用 slab interval 收缩。几何算法可以不同，但都必须返回“是否命中、最近 t、命中属性”。

Epsilon 必须和场景尺度绑定
   平行判断、表面自相交和 ``tMin`` 都需要容差。固定 ``1e-6`` 或 ``1e-4`` 只能作为局部经验值；CAD、大世界、厘米级模型的数值尺度不同，应使用相对尺度或统一世界单位策略。

Camera ray generation 连接二维像素与三维世界
   Pinhole camera 由 eye、forward、right、up、FOV 与 aspect 构造 viewport。像素中心先映射到 NDC，再组合 camera basis 生成 world-space direction。上下翻转、左右手系、FOV 异常首先从这一步检查。

Normal 与 depth visualization 是最有效的正确性证据
   Normal 可映射为 ``0.5*N+0.5``；depth 可将最近 ``t`` 归一化为灰度。Normal 图检查法线和 front-face，depth 图检查最近交点连续性。两者比直接进入复杂 shading 更容易暴露求交和相机错误。

朴素 Ray Casting 的复杂度近似为 ``像素数 × 物体数``
   每个像素遍历所有 primitive 时，大场景很快失控。AABB、BVH、KD-tree 等加速结构的核心价值就是减少精确 primitive tests，而不是改变 ray/geometry 求交数学本身。

内存布局与 ray coherence 会改变真实吞吐
   CPU 需要减少指针跳转、虚调用并提高 SIMD/cache locality；GPU 还受 wave divergence、global memory 和寄存器压力影响。相邻 primary ray 通常方向相近，紧凑对象布局和空间层级可利用这种相干性。

关键路径
--------

单像素 primary visibility：

::

   pixel center
   → NDC / viewport coordinate
   → camera basis 生成 world-space ray
   → 设置 tMin / tMax
   → 遍历对象或加速结构
   → AABB / primitive intersection
   → 过滤无效 t
   → 更新 closestT 与 hit record
   → miss 输出背景
   → hit 输出 normal / depth / material

几何求交统一流程：

::

   Ray + geometry
   → 求候选根或区间
   → 排除平行 / 负 t / 区间外结果
   → 选择最近合法 t
   → position = ray.at(t)
   → 计算并定向 normal
   → 写入 primitive/material/frontFace

错误排查：

::

   先检查 camera basis、FOV、图像翻转
   → 输出 ray direction 调试图
   → 单独保留一种 primitive
   → 检查 tMin/tMax 与 closestT 更新
   → 输出 depth
   → 输出 normal/frontFace
   → 最后恢复完整场景与材质

性能定位：

::

   统计 camera ray 数
   → 统计 AABB tests
   → 统计 primitive tests
   → 统计 hit updates
   → 检查对象/BVH 内存布局
   → 检查 CPU SIMD 或 GPU divergence/cache
   → 再选择更高质量加速结构

概念辨析
--------

* **Ray Casting 与 Ray Tracing**：Ray Casting 只做 primary visibility；Ray Tracing 会在命中点继续生成 shadow、reflection、refraction 或随机 bounce。
* **Ray parameter ``t`` 与 Euclidean distance**：direction 归一化时二者可直接对应；未归一化时 ``t`` 只是参数，不能直接当世界距离。
* **Closest hit 与 any hit**：closest hit 必须找到最近表面；any hit 只需知道是否存在遮挡，命中第一个有效对象即可结束。
* **Geometry normal 与 shading normal**：几何法线来自真实面方向，shading normal 可来自插值或 normal map；基础求交先保存几何事实，再由材质阶段决定着色法线。
* **AABB test 与 primitive intersection**：AABB 是低成本粗筛选，不能替代最终几何求交。
* **Backface culling 与 frontFace 记录**：culling 决定是否拒绝背面；frontFace 记录命中方向关系。透明材质常仍需双面命中并保留 frontFace。
* **Normal view 与最终 shading**：normal view 只是几何/法线诊断，不包含灯光、BRDF 和颜色空间。

本章结论
--------

Ray Casting 的稳定模型是“像素生成 ray—几何返回候选 t—主循环保留最近命中—hit record 驱动输出”。正确性先看 camera、t 区间、求交和 normal/depth；性能先看 ray 数、AABB/primitive test 数和内存访问，再引入 BVH 等层级结构。只要每种几何都遵守同一 hit contract，primary visibility 就能从简单场景平滑扩展到后续 Ray Tracing。