第019章：裁剪与剔除
===================

核心知识点
----------

Clipping 与 culling 作用层级不同
   Culling 通常在对象、mesh、cluster、cell 或 draw 层级提前舍弃无效工作；clipping 处理已经进入几何管线、但与裁剪体边界相交的图元。稳定路径应先用低成本粗粒度剔除减少提交，再让固定管线处理边界图元。

视锥剔除建立在同一坐标空间的包围体测试上
   相机视锥可表示为六个平面，AABB、OBB 或 bounding sphere 与这些平面做保守测试。平面、bounds 和 transform 必须处在同一空间；非均匀缩放、动画或世界变换后若 bounds 未更新，会造成视野边缘突然消失。

Clip-space 条件与 API 深度约定必须匹配
   x、y 常按 ``-w <= x,y <= w`` 判断，z 范围取决于 API 和投影约定。OpenGL 传统深度范围与 Vulkan、Direct3D、Metal 常用约定不同，reverse-Z 又会改变深度比较方向。可见性判断与深度精度策略应分别核对。

保守测试优先避免误删可见对象
   Bounds 可以略放大，投影 screen rect 可以向外扩张，Hi-Z 测试可在不确定时选择保留。少画一个实际可见对象会产生明显 popping，多画一个被遮挡对象主要增加性能成本，因此 culling 系统通常宁可保守。

Frustum、backface、portal 与 cluster culling 解决不同粒度问题
   Frustum culling 去掉相机视锥外对象；backface culling 去掉背向三角形；cell/portal 利用空间连通关系缩小室内可见集；cluster/meshlet culling 对大 mesh 或海量实例做细粒度筛选。

Occlusion culling 依赖已有深度信息
   Hi-Z、上一帧 depth、occlusion query 或 occluder proxy 用来判断视锥内对象是否被前景遮住。它可以减少 vertex、raster 与 fragment 工作，但会引入额外 pass、深度读取、结果延迟和同步成本。

GPU culling 的输出通常是可见列表与 indirect 参数
   Compute shader 读取 instance/cluster bounds、相机参数和可选 Hi-Z，写 visibility、compacted list 或 indirect args。Compute 写入结果必须通过正确 barrier 对 graphics draw 可见，不能把 shader 内同步和跨 pass 资源同步混为一谈。

Occlusion query 不应成为同步点
   Query 结果若在同一帧立即读取，容易制造 CPU/GPU stall。更稳定的做法是延迟一帧或多帧使用，并在相机快速移动、门开启或场景结构变化时采用保守失效规则。

剔除收益必须大于自身成本
   Bounds 过大、对象太小、query 粒度太细、compute compaction 太重或 barrier 太多，都可能让 culling 反而变慢。评估时同时看 draw 数、VS invocation、primitive、fragment、overdraw、query wait 和 culling pass 时间。

关键路径
--------

对象进入 draw list：

::

   更新世界空间 bounds
   → 场景分区或 cell/portal 生成候选集
   → frustum culling
   → 可选 LOD 与 cluster 筛选
   → 将 bounds 投影为 screen rect
   → 使用 Hi-Z 或延迟 query 做 occlusion test
   → 不确定对象保守保留
   → compact visible list
   → 生成 draw list 或 indirect args
   → 固定管线继续 clipping、raster 与 depth test

GPU Hi-Z culling：

::

   instance/cluster bounds + viewProjection + Hi-Z
   → frustum test
   → bounds 投影到屏幕矩形
   → 选择匹配 footprint 的 Hi-Z mip
   → 与对象最近深度做保守比较
   → 写 visibility flag
   → prefix sum / compaction
   → 写 indirect arguments
   → compute-to-graphics barrier
   → indirect draw

可见性错误排查：

::

   固定一个错误对象并显示 bounds
   → 确认 bounds 随 transform/animation 更新
   → 检查 frustum plane 与 bounds 空间
   → 分别显示 frustum、portal、Hi-Z、query 的结果颜色
   → 检查 reverse-Z、depth compare 与 Hi-Z 聚合规则
   → 检查上一帧结果是否过期
   → 最后检查 compact list 与 draw args 是否丢失对象

概念辨析
--------

* **Culling 与 clipping**：culling 提前舍弃完整对象或几何组；clipping 对与视锥边界相交的图元进行边界处理，不能简单丢弃整个相交三角形。
* **Frustum culling 与 occlusion culling**：前者只看相机可见体积；后者还要利用前景深度或遮挡结构判断被挡住的对象。
* **AABB、OBB 与 bounding sphere**：sphere 测试最便宜但较松；AABB 简单且适合世界轴；OBB 更贴合旋转对象但测试更贵。
* **Hi-Z 与 depth buffer**：depth buffer 保存全分辨率深度；Hi-Z 是其层级汇总，用较低成本估计一个屏幕区域是否被遮挡。
* **Occlusion query 与 Hi-Z compute**：query 由硬件统计 proxy 的可见 sample，结果常有读取延迟；Hi-Z compute 直接在 GPU buffer 中生成可见列表，更适合 GPU-driven 路径。
* **保守与激进剔除**：保守策略允许少量多余 draw 以保护正确性；激进策略提高剔除率但更容易产生 popping 和边缘错误。
* **空间分区与可见集缓存**：BVH、octree、quadtree、cell/portal 提供候选结构；visible set cache 复用近期判断，两者都需要明确失效条件。

本章结论
--------

裁剪与剔除的价值在于尽早停止不会影响当前图像的工作。实现时先保证 bounds、视锥与深度约定一致，再按 frustum、分区、遮挡和 cluster 分层筛选，并始终保守处理不确定对象；性能上只有减少的提交、顶点、图元和片元成本超过 culling、query、compaction 与同步成本时，这套可见性系统才真正有效。