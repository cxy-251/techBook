第047章：视锥体剔除
==================

核心知识点
----------

视锥体剔除是最前置的保守可见性测试
   它回答“对象是否落在相机可见体积内”，只剔除完全位于六个视锥平面外的对象；与平面相交的对象继续保留。工程上宁可多画，也不能把真实可见对象误剔除。

视锥平面来自 View-Projection 矩阵
   世界点经过 ``p_clip = VP * p_world`` 进入裁剪空间。平面提取公式必须与矩阵乘法方向、row/column-major、深度范围、左右手系、reversed-Z 和无限远投影约定一致。跨 API 时最容易错的是 near plane 与深度 convention。

平面测试建立在有符号距离上
   对归一化平面 ``(n,d)`` 和点 ``p``，距离为 ``dot(n,p)+d``。若法线朝向视锥内部，则非负表示在内侧。包围体只要在任一平面外完全分离，就可直接判定 Outside。

三态结果比单纯 bool 更适合层级剔除
   ``Outside`` 直接停止遍历，``Inside`` 可以整棵子树批量接受，``Intersect`` 才继续下钻。大场景性能主要来自前两类快速结论，而不是让所有对象都落入边界测试。

不同包围体对应不同成本与紧密度
   Sphere 测试最便宜且旋转无关，适合动态对象；AABB 适合静态世界和 chunk；OBB 更贴合旋转长条物体，但测试成本更高；meshlet/cluster bounds 适合 GPU 细粒度剔除。包围体越紧，误保留越少，但更新和测试通常越贵。

层级空间结构用一次测试排除大量对象
   Spatial chunk、BVH、octree 都可以把对象组织成树。根节点 Outside 时整棵子树停止；Inside 时内部对象无需逐个测试；Intersect 时继续访问子节点。场景越大，减少测试对象数量往往比单次平面测试微优化更重要。

动态对象需要维护 bounds 与空间归属
   车辆、门、破坏物、骨骼动画可能让真实几何超出静态 bounds。移动对象应更新自身 bounds，跨 chunk 时更新 membership，并让 dirty 状态向父层级传播。Bounds 过小会误剔除，过大只会降低收益。

CPU 适合 broad phase，GPU 适合 fine phase
   CPU 负责 camera、scene graph、chunk、streaming 等高层数据，先输出候选 chunk/range；GPU compute 再并行测试大量 cluster bounds，写入 visible list 或 indirect draw buffer。这样能避免 CPU 对几十万 cluster 逐个处理。

GPU-driven 剔除必须把结果留在 GPU
   Compute 写 visible IDs 或 indirect args 后，graphics pass 直接消费。若为了得到可见数量又把结果同步 readback 到 CPU，会引入 stall，抵消并行剔除收益。必要统计应延迟读取。

视锥剔除的收益要看后续工作是否真正下降
   Draw count 减少只是入口指标，还应观察 triangle count、vertex invocation、fragment overdraw、CPU submit time、GPU pass time、buffer bandwidth，以及剔除 compute/barrier 本身的成本。

关键路径
--------

CPU 分层剔除：

::

   camera view / projection
   → 生成 VP
   → 提取并归一化六个 frustum planes
   → 测试 root chunk / BVH node
   → Outside: 跳过子树
   → Inside: 批量接受
   → Intersect: 继续子节点 / object bounds
   → 生成 visibility list
   → render pass builder

CPU + GPU 协同：

::

   CPU frustum broad phase
   → candidate chunk / cluster ranges
   → upload candidate buffer + frustum planes
   → GPU compute 测试 cluster bounds
   → compaction / append visible IDs
   → 写 indirect draw args
   → barrier
   → graphics indirect draw

误剔除排查：

::

   显示真实 frustum
   → 检查 VP 与 clip-depth convention
   → 检查 plane normal 方向 / 归一化
   → 显示 object 与 chunk bounds
   → 检查动画/动态位移是否超出 bounds
   → 检查 chunk membership / dirty update
   → 最后检查 GPU visible list 与 indirect args

概念辨析
--------

* **Frustum culling 与 clipping**：culling 在 draw 前按对象/包围体粗排除；clipping 是光栅化管线对已经提交的基元做裁剪。
* **Frustum 与 occlusion**：frustum 判断对象是否落入相机可见体积；occlusion 判断对象虽在视锥内是否被更近几何遮挡。
* **Sphere 与 AABB**：sphere 更新和测试便宜但可能偏松；AABB 对静态世界更紧，但旋转后可能膨胀。
* **Inside 与 Intersect**：Inside 可以接受整个层级；Intersect 只代表不能在当前层级下结论，必须继续测试。
* **Chunk culling 与 cluster culling**：chunk 是粗粒度场景组织，cluster/meshlet 是 GPU 细粒度几何组织，两者常串联而不是互斥。
* **CPU culling 与 GPU culling**：CPU 更适合高层场景决策，GPU 更适合大量同构 bounds 测试；分工取决于数据已经位于哪一侧。
* **Draw count 与 GPU time**：draw 数下降不保证 GPU time 同比例下降，被剔除对象可能原本就很廉价或不是瓶颈。

本章结论
--------

视锥体剔除应按“VP 约定—六平面—包围体三态测试—层级传播—visibility list”理解。正确性优先检查矩阵与深度约定、平面方向和 bounds 覆盖；性能则先靠 chunk/BVH 等层级减少候选，再决定是否把 cluster fine phase 放到 GPU。合格实现既要保证屏幕边缘和动态对象不闪烁，也要能用 draw、vertex、fragment 与 submit 指标证明后续工作真的下降。