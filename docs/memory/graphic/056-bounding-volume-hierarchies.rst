第056章：Bounding Volume Hierarchy
=================================

核心知识点
----------

BVH 用层级包围盒缩小真实相交测试范围
   内部节点保存覆盖子树的 AABB，叶节点只保存少量 primitive。Ray 先测试节点包围盒，miss 时整棵子树直接跳过，hit 时才继续进入 child 或叶子。BVH 的核心收益是用便宜的 bounds test 替代大量 triangle/primitive test。

遍历质量主要由节点访问数和叶子测试数决定
   AABB 本身不判断真实命中，只回答 ray 是否进入某个空间范围。高质量 BVH 应让 ray 尽早 miss 大量子树、尽早访问近处 child，并尽量减少 sibling overlap、树深与叶子 primitive 数。

AABB 测试通常使用 slab 模型
   Ray 在 x/y/z 三轴上分别得到进入和离开区间，三个区间求交后再与 ``[tMin,tMax]`` 相交。Closest-hit 查询一旦获得更近命中，会缩短 ``tMax``，从而让后续较远节点更容易被跳过。

构建策略本质上是在 build time 与 traversal quality 之间取舍
   Median split 构建简单、树高平衡，但不直接优化重叠；SAH 根据子节点表面积与 primitive 数量估计未来 traversal cost，适合静态高质量 BVH；LBVH 使用 Morton code 和排序快速并行构建，适合动态/短生命周期几何；HLBVH 用 LBVH 构建底层 treelet，再用较高质量策略优化上层。

叶子大小与节点宽度会改变遍历成本
   叶子过小会增加节点和栈操作，叶子过大会增加 primitive test。二叉 BVH 构建简单但树更深，宽 BVH 可一次测试多个 child，适合 SIMD/SIMT，但节点读取量、排序和布局更复杂。

节点布局直接影响带宽
   Traversal 往往是 pointer-chasing 与随机读取混合负载。线性节点数组、连续 child、紧凑 metadata、连续叶子 primitive、structure compaction 都能减少 cache line 和 memory transaction。节点质量很好但带宽仍高时，应优先查布局与压缩，而不是继续改 split。

动态场景要区分 refit 与 rebuild
   Refit 保持拓扑，只重新计算叶子和父节点 bounds，更新便宜但长期可能让 sibling overlap 增大；rebuild 重新划分 primitive，成本高但恢复结构质量；partial rebuild 只重建退化或 dirty 子树，在二者之间折中。

TLAS/BLAS 用两层结构隔离更新频率
   BLAS 管理 mesh 内部几何，TLAS 管理实例 transform 与 BLAS 引用。共享静态 mesh 只需一个 BLAS，多个实例只更新 TLAS。蒙皮角色可以先 refit BLAS，bounds 膨胀和 ray steps 持续上升时再 rebuild 或拆局部 BLAS。

性能评估必须同时看构建与遍历
   Build time、node count、ray steps、memory bandwidth、hit/miss ratio 需要联合解释。低 steps miss 是便宜失败，高 steps miss 才说明树无法及时排除空区域。优化目标是总 frame time，而不是单独追求更少节点或更快构建。

关键路径
--------

BVH 查询：

::

   ray
   → root AABB
   → miss: skip subtree
   → hit: test child bounds
   → near child first / far child deferred
   → leaf
   → primitive intersection
   → closest-hit / any-hit / miss

静态构建：

::

   primitive bounds + centroids
   → choose split strategy
   → median / SAH partition
   → recursive node build
   → leaf primitive ranges
   → linearize / compact nodes
   → upload acceleration structure

动态更新：

::

   geometry / transform changed
   → 判断 BLAS 还是 TLAS
   → small deformation: refit
   → accumulated overlap: partial/full rebuild
   → instance-only change: TLAS update
   → barrier / build completion
   → trace pass

性能排查：

::

   先分离 build/update 与 trace 时间
   → 按 ray type 看 average / P95 steps
   → 检查 node count / leaf size
   → 可视化 sibling overlap / huge bounds
   → 检查 bandwidth / cache miss
   → 调整 split / rebuild threshold / BLAS 粒度

概念辨析
--------

* **BVH 与 primitive test**：BVH 只缩小候选范围，真实几何命中仍由叶子中的相交测试决定。
* **SAH 与 Median Split**：前者直接估计未来查询代价，构建更慢；后者更快但不保证低重叠。
* **LBVH 与 HLBVH**：LBVH 强调并行快速构建；HLBVH 在其基础上改善上层 traversal quality。
* **Refit 与 Rebuild**：refit 更新 bounds 不改拓扑；rebuild 重新分组 primitive 并恢复空间质量。
* **TLAS 与 BLAS**：TLAS 管实例，BLAS 管 mesh 几何；二者分离是动态实例化场景的核心更新边界。
* **Node Count 与性能**：节点少不一定快，叶子过大可能让 primitive tests 急剧增加。
* **Hit Ratio 与结构质量**：命中率本身不说明好坏，必须结合访问 steps 与查询类型解释。

本章结论
--------

BVH 应按“primitive bounds—层级节点—AABB traversal—叶子精确测试—动态更新”理解。静态结构优先用高质量 split 降低 sibling overlap，动态结构用 refit、partial rebuild 和 TLAS/BLAS 控制更新范围。性能判断先分离 build 与 trace，再按 ray 类型检查 steps、节点热点和带宽；真正目标是让构建成本、遍历质量和内存访问共同落在整帧预算内。