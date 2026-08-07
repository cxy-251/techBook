第058章：Octree 与 Grid 结构
============================

核心知识点
----------

Octree 与 Grid 都按空间组织候选
   Octree 递归八分三维空间，用层级深度表达稀疏性；Uniform Grid 用固定 cell 提供稳定、规则的寻址和遍历。二者共同目标是让查询成本接近“相关空间”的规模，而不是全世界对象数量。

Octree 适合跳过大块空区域
   根节点覆盖世界 bounds，内部节点用 8 个 child 表达 occupancy，叶子保存 triangle、object、voxel brick 或其它 payload。查询先经过高层节点，空 child 可以直接跳过，只有命中非空区域才继续下钻。

Octree 的核心数据是 occupancy 与 payload
   Occupancy 说明空间是否含有后续需要处理的内容，payload 说明命中后实际测试什么。GPU 上通常使用扁平节点数组、child mask、childBase 和 payload range，避免随机指针和过大的节点结构。

Octree 停止细分要控制深度与候选量
   最大深度、最小 cell、payload 阈值、体素误差或屏幕误差都可作为终止条件。过深会增加节点访问和分支发散，叶子过粗会增加 payload test。大对象跨多个 octant 时还会产生复制或 loose bounds 问题。

Uniform Grid 的第一参数是 cell size
   Cell 太大，每个 cell 候选过多；cell 太小，ray/邻域查询会跨越大量 cell。合理尺寸应结合查询半径、对象尺度、平均密度和最大密度决定，而不是固定使用某个世界单位。

Grid 的 ray traversal 通常使用 DDA
   Ray 进入 grid 后维护当前 cell、步进方向、到下一格边界的 ``tMax`` 和每跨一格的 ``tDelta``。每步只进入相邻 cell，控制流简单，适合 GPU；缺点是空旷空间仍需逐 cell 前进。

Hash Grid 用稀疏索引支持动态对象
   对每个对象计算 cell key，再通过排序/计数/prefix sum 生成 ``cell → offset/count``。它适合粒子、碎片和局部碰撞 broad phase，每帧可重建；风险来自热点 bucket、排序成本和密度失衡。

Octree + Local Grid 是常见混合结构
   上层 Octree 负责大尺度稀疏跳过和 streaming，下层 grid/brick 负责局部连续查询。静态山体可由 coarse octree 管理，建筑密集区进入 micro grid，烟雾进入 sparse voxel brick，移动碎片进入 dynamic hash grid。

动态更新要区分结构变化与 payload 变化
   静态 Octree 应长期复用；移动物体优先进入独立 dynamic grid、loose octree 或高层动态列表；体积数据只更新 dirty brick 和 occupancy。每帧重建整个层级结构通常会浪费预算。

Sparse voxel 的核心是“层级索引 + 活跃 brick”
   上层跳过空区域，下层 brick 保持连续采样。Brick pool、free list、active list、mark-scan-scatter compaction 可以让显存与 dispatch 只覆盖活跃数据。Occupancy 阈值还需要滞回，避免反复分配/释放造成时间抖动。

性能评估必须分离遍历、payload 与更新成本
   需要记录 node/cell visits、leaf payload count、热点 cell、active brick、build/update time、memory footprint、bandwidth 和 barrier 等待。结构本身访问很少但 payload 很大时，瓶颈不在 traversal；动态帧尖峰则应优先检查 rebuild/compaction 范围。

关键路径
--------

Octree 查询：

::

   world bounds
   → root node
   → bounds / occupancy test
   → empty child: skip
   → occupied child: descend
   → leaf payload
   → triangle / object / brick query

Uniform / Hash Grid：

::

   world position / object bounds
   → cell coordinate / hash key
   → cell range
   → payload list
   → neighbor query / collision / ray DDA

混合大世界：

::

   coarse octree / streaming pages
   → leaf type + residency
   → triangle leaf / local grid / voxel brick / dynamic bucket
   → local query
   → candidate tests

动态体积更新：

::

   simulation changes density
   → mark dirty region / brick
   → allocate/free sparse brick
   → update occupancy
   → compact active list
   → barrier
   → volume sampling / ray marching

概念辨析
--------

* **Octree 与 Uniform Grid**：Octree 用层级适应稀疏性；Grid 用固定 cell 换取简单寻址和稳定遍历。
* **Dense Grid 与 Hash Grid**：前者地址直接但空 cell 占内存；后者只保存活跃 cell，但引入 hash/sort/range 构建成本。
* **Occupancy 与 Payload**：occupancy 负责证明空间是否值得进入，payload 才是命中空间后实际处理的数据。
* **Loose Octree 与严格 Octree**：loose bounds 提高动态对象稳定性，但会降低空间排除精度。
* **Sparse voxel 与 dense 3D texture**：前者只保留活跃 brick，适合大范围稀疏体积；后者适合连续密集数据。
* **Traversal cost 与 payload cost**：少访问节点不代表总查询便宜，叶子或热点 cell 中的候选数量同样关键。

本章结论
--------

Octree 与 Grid 应按“世界范围—空间索引—局部 payload—候选测试”理解。大范围稀疏和 streaming 优先用层级 Octree，局部高密度、动态粒子和稳定邻域查询优先用 Grid/Hash Grid；复杂场景常用 coarse hierarchy 加 local grid/brick。动态数据不要强行污染静态层级，性能判断也必须同时看访问空间单元数、payload 分布、更新范围和内存带宽。