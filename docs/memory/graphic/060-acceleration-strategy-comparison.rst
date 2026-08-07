第060章：空间加速策略对比
========================

核心知识点
----------

加速结构选择要从查询问题倒推
   先看对象是否经常移动、空间分布是否均匀、查询是否要求最近命中、执行位置在 CPU 还是 GPU，再决定 BVH、KD-Tree、Grid、Octree、Hierarchical Grid 或混合方案。结构名称本身不能直接给出性能结论。

BVH 以对象边界为组织中心
   Primitive、mesh 或 instance 先按 bounds 分组，父节点包住子节点。它适合形状不规则、尺度差异大、ray query 与 frustum query，以及需要 refit/TLAS/BLAS 的动态实例场景。

KD-Tree 以空间切分为组织中心
   Axis-aligned split 把世界切成二叉区域，适合静态、高空空间比例、频繁 ray/point query。它能精细跳过空区域，但构建成本高，跨 split primitive 复制和动态更新是主要弱点。

Regular / Hash Grid 适合局部均匀、高并行查询
   Cell size 决定每格候选数与遍历 cell 数。粒子邻域、碰撞 broad phase、体素采样、局部动态小物体通常能从连续 cell range、排序键和 prefix-sum 构建中受益。

Octree / Hierarchical Grid 适合稀疏和多尺度空间
   大 cell 负责远处和空区域，小 cell 负责局部密集数据。Sparse voxel、streaming、远近尺度差异大的大世界比单一 dense grid 更适合这类结构。

Scene Graph 不是空间加速结构的替代品
   它管理 node、transform、component 和资源引用，并触发 spatial index 更新。真正的 ray、frustum、collision 或 neighbor query 应进入专门的空间结构。

静态几何可以用更昂贵的高质量构建换长期查询收益
   Static building、terrain、room geometry 可以在加载阶段使用 SAH BVH、KD-Tree 或局部结构。重点指标是 node visits、primitive tests、cache locality 和 memory footprint，而不是每帧 build time。

动态对象优先考虑 update cost
   Vehicle、actor、instance transform 等更适合 TLAS、dynamic BVH、loose/hierarchical grid；粒子适合 hash grid。Skinned mesh 可先 refit，质量退化后再 partial/full rebuild。动态频率决定结构，而不是只看单次查询速度。

Ray Query 与 Collision Broad Phase 的目标不同
   Closest-hit ray 重视 front-to-back 顺序、bounds quality 和 early exit；shadow ray 重视 any-hit；collision broad phase 只需产生少量 false-positive candidate pair。一个结构在 ray tracing 中好，不代表在碰撞候选生成中同样最优。

CPU 与 GPU 偏好的数据布局不同
   CPU 能处理复杂树逻辑，但对 cache miss 敏感；GPU 更偏好连续 buffer、批量 query、规则 build、相干控制流和较少随机访问。CPU-friendly 指针树不应直接原样搬到 GPU。

复杂场景通常需要混合结构
   城市可用 tile index + TLAS/BLAS + dynamic layer；森林可用 region grid + instance TLAS + LOD；室内可用 cell/portal + local BVH；粒子使用 hash grid；体素使用 sparse brick hierarchy/clipmap。不同更新频率的数据应放入不同层级。

验证体系必须覆盖构建、更新、查询、内存与调试成本
   至少记录 build time、update time、node/cell visits、primitive tests、memory footprint、bandwidth/cache、parallelism/divergence 和 debug observability。只看理论复杂度或单个平均时间无法解释真实帧表现。

关键路径
--------

结构选择：

::

   定义主要 query
   → closest-hit / any-hit / overlap / neighbor / streaming
   → 判断 static / dynamic
   → 判断 sparse / dense / multi-scale
   → 判断 CPU / GPU execution
   → 选择 object hierarchy / space partition / grid / hybrid
   → profiler 验证

典型混合城市：

::

   scene graph / streaming tiles
   → static mesh BLAS / local BVH
   → instance TLAS
   → dynamic vehicle layer
   → particle hash grid
   → indoor cell / portal + local BVH
   → sparse volume bricks
   → query-specific candidate list

性能验证：

::

   freeze scene + query counts
   → measure build time
   → measure update/refit/rebuild time
   → measure node/cell visits
   → measure primitive/candidate tests
   → inspect memory + bandwidth + divergence
   → inspect debug overlay / false positive / misses
   → compare full frame time

概念辨析
--------

* **Object Partition 与 Space Partition**：BVH 主要按对象分组；KD-Tree/Grid/Octree 主要按空间区域组织。
* **Static Quality 与 Dynamic Update**：静态结构可以花更长时间构建，动态结构必须优先控制每帧更新预算。
* **Regular Grid 与 Hierarchical Grid**：前者只有一个尺度，后者通过多层 cell 处理密度和对象尺度变化。
* **Scene Graph 与 Acceleration Structure**：前者是逻辑/变换索引，后者是查询加速索引。
* **Ray Query 与 Broad Phase**：前者通常需要精确最近命中，后者只需生成可接受数量的候选。
* **Candidate Count 与 Frame Time**：候选变少不保证整帧更快，结构 build、barrier、bandwidth 和 shader 可能成为新瓶颈。
* **单一结构与混合结构**：复杂大场景中，不同数据频率和查询类型通常应该拆到不同结构，而非追求“一棵树解决所有问题”。

本章结论
--------

空间加速策略应按“数据分布—更新频率—查询类型—执行平台—性能证据”推导。BVH 适合对象边界和 ray query，KD-Tree 适合静态空间切分，Grid 适合局部均匀动态查询，Octree/Hierarchical Grid 适合稀疏多尺度空间，Scene Graph 负责逻辑组织。复杂场景的稳定答案通常是混合结构，并用 build/update/query/memory/bandwidth 指标验证整帧收益，而不是用结构名称或理论复杂度做决定。