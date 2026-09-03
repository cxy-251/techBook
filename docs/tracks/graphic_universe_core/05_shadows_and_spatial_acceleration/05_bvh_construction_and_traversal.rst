========================================================================
Chapter 25: 空间加速层次结构：BVH 动态重构、SAH 分割与 GPU 遍历优化
========================================================================

.. note:: 前置背景与认知承接
   在上一章中，我们深入剖析了基于视锥体几何与屏幕空间分层 Z 缓冲（Hi-Z）的可见性剔除流水线。Hi-Z 在光栅化管线的前端过滤与 Overdraw 消除中表现优异，但其本质是依赖单一视口深度图的 2.5D 屏幕空间优化方案。当渲染引擎需要处理任意方向发散的非视口光线——例如光线追踪硬阴影（Ray Traced Shadows）、环境光遮蔽光线（AO Rays）、表面光泽反射（Glossy Reflections）、漫反射间接光反弹（Diffuse GI），以及物理引擎中的连续碰撞检测（CCD）时，屏幕空间结构将彻底失效。

   对于一个包含 $N$ 条光线与 $M$ 个三角形几何图元的复杂工业级场景，若采用暴力求交遍历，其时间复杂度将达到灾难性的 $O(N 	imes M)$。以 $1920 	imes 1080$ 分辨率、每像素发射 4 条光线、场景包含 1000 万个三角形为例，单帧求交计算量将超过 $8.29 	imes 10^{13}$ 次，任何算力集群均无法承受。**空间加速层次结构（Spatial Acceleration Structures）通过将几何图元递归组织为具有空间包含或空间划分性质的树状拓扑，将单条光线的求交时间复杂度从线性阶 $O(M)$ 骤降至对数阶 $O(\log M)$。** 本章将系统解构层次包围盒（Bounding Volume Hierarchy - BVH）的数学拓扑、表面积启发式（SAH）成本模型、现代 GPU 并行线性 BVH（LBVH）构建流水线、两级加速结构（TLAS/BLAS）动态更新，以及面向硬件微架构的 GPU 遍历栈优化技术。

------------------------------------------------------------------------
25.1 空间加速结构的物理必然性与拓扑分类
------------------------------------------------------------------------

空间加速结构的本质是在三维连续空间中建立离散的图元检索索引。在图形学与计算几何数十年的演进中，形成了两大类截然不同的拓扑设计哲学：**空间划分（Spatial Partitioning）** 与 **物体划分（Object Partitioning）**。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                空间划分 (Spatial Partitioning) vs 物体划分 (BVH)        |
   +-------------------------------------------------------------------------+

   [ 空间划分: KD-Tree / Octree / Grid ]       [ 物体划分: BVH (Bounding Volume Hierarchy) ]
   +-----------------------------------+       +-----------------------------------+
   |  空间被互斥切分, 空间无重叠       |       |  图元被严格互斥归类, 图元无重复   |
   |                                   |       |                                   |
   |   +-------------+-------------+   |       |   +---------------------------+   |
   |   |   Cell A    |   Cell B    |   |       |   | Node A (AABB)             |   |
   |   |        /----+---\         |   |       |   |    +---------+            |   |
   |   |       / Prim 1   \        |   |       |   |    | Prim 1  |  Node B (AABB)  |
   |   |      /      |     \       |   |       |   |----+---------+------+     |   |
   |   |     +-------+------+      |   |       |   |    | 重叠空间 |      |     |   |
   |   +-------------+-------------+   |       |   |    +---------+      |     |   |
   |                                   |       |   |        |  Prim 2    |     |   |
   | * 缺陷: 跨边界图元被强制分裂      |       |   +--------+----------------+     |   |
   | * 内存膨胀, 动态场景难以重构      |       | * 优势: 树高确定, 拓扑稳定, 易于内存扁平化|
   +-----------------------------------+       +-----------------------------------+

.. list-table:: 现代空间加速层次结构核心特性全景对比
   :widths: 16 18 18 20 28
   :header-rows: 1
   :class: tight-table

   * - 加速结构类型
     - 划分策略
     - 构建计算复杂度
     - 遍历求交效率
     - 动态场景更新与硬件适配度
   * - **均匀网格 (Uniform Grid)**
     - 空间均匀体素化
     - $O(M)$ (极快)
     - 空间分布不均时严重退化 (茶壶在体育场)
     - 易于动态插入；光线步进在空旷区域开销大
   * - **八叉树 (Octree)**
     - 空间递归 8 等分
     - $O(M \log M)$
     - 中等 ($O(\log M)$)
     - 内存紧凑；但边界图元跨节点分裂，GPU 栈开销大
   * - **KD-Tree**
     - 空间自适应轴对齐平面
     - $O(M \log^2 M)$ (SAH)
     - 极高 (射线严格按空间前后遍历)
     - **图元多次引用导致内存失控**；动态物体无法快速 Refit
   * - **BVH (AABB 层次树)**
     - **物体集合递归二分**
     - $O(M \log M)$ (CPU/GPU)
     - **极高 (硬件专用 RT Core 加速)**
     - **图元唯一归属，内存确定为 $2M-1$ 节点**；完美适配 TLAS/BLAS 与 GPU 并行

**为何现代实时光线追踪与工业级渲染管线全面收敛于 BVH？**
1. **内存占用绝对确定**：包含 $M$ 个三角形图元的二叉 BVH，其内部节点数严格为 $M-1$，叶子节点数严格为 $M$，总节点数严格为 $2M-1$。这意味着可以在内存中预先分配一块连续紧凑的扁平化数组，彻底消除了动态内存分配与指针悬挂。
2. **图元无冗余存储**：在 KD-Tree 中，一个跨越分割平面的大三角形会被拆分并分别存储于多个叶子节点中，导致光线遍历时必须维护复杂的“已求交图元邮箱（Mailboxing）”机制以避免重复计算；BVH 中每个图元在整棵树中只存在一份引用。
3. **动态更新成本低（Refit 友好）**：当骨骼动画或刚体发生运动时，只需自底向上重新计算每个节点的轴对齐包围盒（AABB），无需改变树的拓扑结构，耗时仅需数百微秒。
4. **硬件微架构硬化支持**：现代 GPU（如 NVIDIA RTX 系列的 RT Core、AMD RDNA2/3 的 Ray Accelerator）在硬件 ASIC 电路中硬化了 AABB 求交与二叉 BVH 遍历流水线，BVH 成为底层图形 API（DirectX Raytracing DXR、Vulkan Ray Tracing、Metal Ray Tracing）的唯一标准底层数据结构。

------------------------------------------------------------------------
25.2 表面积启发式 (Surface Area Heuristic - SAH) 成本模型与数学推导
------------------------------------------------------------------------

构建高质量 BVH 的核心问题是：**对于当前节点包含的图元集合，应当选择哪一个轴、以及在哪一个位置进行空间切分，才能使后续光线遍历的平均计算代价最小？**

表面积启发式（SAH）基于几何概率学中的 **Crofton 定理（凸包几何概率）**，为图元分割提供了严格的统计学代价度量模型。

几何概率基础与条件穿透概率推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

设空间中存在一个凸包包围盒 $P$（父节点），其表面积为 $S(P)$。假设穿过该空间区域的光线是空间各向同性、位置均匀分布的随机无限长线段。

根据积分几何学定理，一条穿透父包围盒 $P$ 的随机光线，同时穿透其内部任意子包围盒 $A$（满足 $A \subset P$）的条件概率，严格正比于子包围盒与父包围盒的表面积之比：

.. math::

   P(	ext{Hit } A \mid 	ext{Hit } P) = \frac{S(A)}{S(P)}

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                SAH 几何概率条件穿透模型 (Crofton 定理)                  |
   +-------------------------------------------------------------------------+

              +---------------------------------------------------+
              | 父包围盒 P (表面积 S_P)                           |
              |                                                   |
              |    光线 1 (穿透 P, 未穿透 L 与 R: 零求交代价)     |
              |    =======================================>       |
              |                                                   |
              |    +--------------------+   +-------------------+ |
              |    | 子包围盒 L (S_L)   |   | 子包围盒 R (S_R)  | |
              |    | 包含 N_L 个图元    |   | 包含 N_R 个图元   | |
              |    |                    |   |                   | |
              |    | 光线 2             |   | 光线 3            | |
              |    | ===> 发生 N_L 次求交|   | ===> 发生 N_R 次求交|
              |    +--------------------+   +-------------------+ |
              +---------------------------------------------------+

SAH 期望代价函数推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于一个包含 $N_P$ 个图元的当前节点，若我们将其分割为包含 $N_L$ 个图元的左子节点 $L$（包围盒表面积 $S_L$）与包含 $N_R$ 个图元的右子节点 $R$（包围盒表面积 $S_R$），则单条穿过父节点的光线在遍历过程中的**期望计算代价函数（Cost Function）**定义为：

.. math::

   C_{	ext{split}} = C_{	ext{trav}} + P(	ext{Hit } L \mid 	ext{Hit } P) \cdot C(L) + P(	ext{Hit } R \mid 	ext{Hit } P) \cdot C(R)

代入条件穿透概率公式，展开为：

.. math::

   C_{	ext{split}} = C_{	ext{trav}} + \frac{S(L)}{S(P)} \sum_{i \in L} C_{	ext{isect}}(i) + \frac{S(R)}{S(P)} \sum_{j \in R} C_{	ext{isect}}(j)

在实际工程实现中，通常假设所有图元（三角形）的单次光线求交代价为常数 $C_{	ext{isect}}$，光线与单个包围盒（AABB）的求交与节点遍历跳转代价为常数 $C_{	ext{trav}}$。此时 SAH 代价公式简化为：

.. math::

   C_{	ext{split}} = C_{	ext{trav}} + C_{	ext{isect}} \left( \frac{S(L)}{S(P)} N_L + \frac{S(R)}{S(P)} N_R \right)

其中，三维轴对齐包围盒 $	ext{AABB} = [\mathbf{x}_{\min}, \mathbf{x}_{\max}]$ 的表面积计算公式为：

.. math::

   \Delta x = x_{\max} - x_{\min}, \quad \Delta y = y_{\max} - y_{\min}, \quad \Delta z = z_{\max} - z_{\min}

.. math::

   S(	ext{AABB}) = 2 \cdot (\Delta x \cdot \Delta y + \Delta y \cdot \Delta z + \Delta z \cdot \Delta x)

节点终止分裂准则 (Termination Criterion)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在决定是否对当前节点继续进行空间二分时，必须将最优分割方案的最小代价 $\min(C_{	ext{split}})$ 与**不进行分割、直接将当前节点创建为叶子节点（Leaf Node）**的代价进行严格对比：

- **创建叶子节点代价**：$C_{	ext{leaf}} = N_P \cdot C_{	ext{isect}}$；
- **分裂判定法则**：
  
  .. math::

     \begin{cases}
     \min(C_{	ext{split}}) < C_{	ext{leaf}} & \implies 	ext{执行分割，生成左右内部子节点} \
     \min(C_{	ext{split}}) \ge C_{	ext{leaf}} & \implies 	ext{终止分割，当前节点固化为叶节点}
     \end{cases}

典型经验参数设置：在现代 GPU 与 CPU 架构上，通常设定 $C_{	ext{trav}} = 1.0$ 至 $1.5$，$C_{	ext{isect}} = 1.0$ 至 $2.0$（反映出光线测试一个三角形指令周期约为测试一个 AABB 的 1.5 倍）。

------------------------------------------------------------------------
25.3 现代 BVH 构建算法演进：精确 SAH、分桶 SAH 与 GPU 并行 LBVH
------------------------------------------------------------------------

构建 BVH 的核心矛盾在于 **构建速度（Build Performance）** 与 **光线追踪遍历质量（Trace Quality）** 之间的权衡。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                三大主流 BVH 构建算法架构演进路线                         |
   +-------------------------------------------------------------------------+

   [ 1. 全精确 SAH (Exact Sweep SAH) ]
   * 算法: 对所有图元在 3 个轴排序, 遍历所有 N-1 个缝隙求 SAH
   * 特点: 树质量达到理论极限, 但时间复杂度高达 O(N log^2 N), 构建极慢 (秒级)
   * 适用: 离线电影级渲染器静态场景 (如 RenderMan, Arnold)
                             |
                             v
   [ 2. 分桶 SAH (Binned SAH / Fast SAH) ]
   * 算法: 将空间等分 K 个桶 (如 K=32), 线性将图元分桶并快速计算前后缀包围盒
   * 特点: 树质量达到精确 SAH 的 98%+, 构建时间降低 1~2 个数量级 (复杂度 O(K * N))
   * 适用: 生产级 CPU/GPU 光线追踪引擎 (如 Intel Embree, OptiX)
                             |
                             v
   [ 3. 线性 BVH / 分层线性 BVH (LBVH / HLBVH) ]
   * 算法: 计算莫顿码 (Morton Code) -> GPU 基数排序 -> GPU 线程并行构建树分支
   * 特点: 100% 运行于 GPU Compute / 毫秒级构建数百万图元 / 支持每帧动态全量重构
   * 适用: 实时游戏光追、动态毛发、实时破坏形变 (DXR / Vulkan RT)

Binned SAH（分桶 SAH）算法微架构实现
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Binned SAH 避免了对海量图元进行耗时的全局排序。其算法流程如下：

1. **计算质心包围盒**：计算当前节点内所有图元中心点（Centroid）构成的总包围盒 $	ext{CentroidAABB}$；
2. **确定分割主轴**：选取 $	ext{CentroidAABB}$ 中跨度最长的一个轴（$X, Y$ 或 $Z$）；
3. **空间等距分桶**：将该轴划分为 $K$ 个均匀的区间桶（Bucket，工业界通常取 $K=16$ 或 $K=32$）。对于图元 $i$，其中心点坐标 $c$ 落入的桶索引为：

   .. math::

      	ext{bucketIdx} = 	ext{clamp}\left( 	ext{floor}\left( K \cdot \frac{c - 	ext{axis}_{\min}}{	ext{axis}_{\max} - 	ext{axis}_{\min}} \right), 0, K - 1 \right)

4. **线性统计桶元数据**：遍历所有图元，累加每个桶内的图元数量 $N_b$ 以及合并包围盒 $	ext{AABB}_b$；
5. **前后缀扫描（Prefix & Suffix Sweep）**：执行一次自左向右和自右向左的前缀合并，在 $O(K)$ 时间内求出所有 $K-1$ 个候选切分平面的 $S_L, N_L, S_R, N_R$ 与对应的 $C_{	ext{split}}$；
6. **原地重排图元（Partitioning）**：选取代价最小的分割点，使用双指针算法在线性时间内将图元划分为左右两组，递归构建子树。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                Binned SAH 空间分桶与前后缀包围盒合并示意图               |
   +-------------------------------------------------------------------------+

   Centroid 跨度: [=========================================================]
   K=4 分桶:      |  Bucket 0   |  Bucket 1   |  Bucket 2   |  Bucket 3   |
   图元数量:      |    N=3      |    N=1      |    N=5      |    N=2      |
                  +-------------+-------------+-------------+-------------+
   候选平面 0:                  ^ (L: B0, R: B1~B3) -> 计算 SAH_Cost_0
   候选平面 1:                                ^ (L: B0~B1, R: B2~B3) -> 计算 SAH_Cost_1
   候选平面 2:                                              ^ (L: B0~B2, R: B3) -> 计算 SAH_Cost_2

GPU 并行线性 BVH (LBVH) 与莫顿码 (Morton Code) 数学原理
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 GPU 上，递归树构建会引发严重的线程分支发散（Divergence）与锁同步争用。LBVH（Linear BVH）通过**空间填充曲线（Space-Filling Curve）**将高维三维空间拓扑降维为一维有序序列，从而将树的构建转化为高效的并行基数排序。

**1. 30 位莫顿码（Z-Order Curve）生成算法**

将场景包围盒归一化为单位立方体 $[0, 1]^3$。对于图元中心点 $(x, y, z)$，将其坐标定点化为 10 位整数（范围 $[0, 1023]$），然后将 $x, y, z$ 的二进制位交错排列（Bit Interleaving），生成一个 30 位的唯一整数编码：

.. math::

   	ext{MortonCode} = \sum_{k=0}^{9} (x_k \cdot 2^{3k+2} + y_k \cdot 2^{3k+1} + z_k \cdot 2^{3k})

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                莫顿码 (Morton Code) 三维坐标二进制交错编码原理          |
   +-------------------------------------------------------------------------+

   X 分量 (10-bit):   x9  x8  x7  ...  x2  x1  x0
   Y 分量 (10-bit):   y9  y8  y7  ...  y2  y1  y0
   Z 分量 (10-bit):   z9  z8  z7  ...  z2  z1  z0
                       \   \   \        \   \   \
   交错合并 (30-bit): [x9 y9 z9 x8 y8 z8 ... x0 y0 z0]

位交错在硬件微架构上可通过位操作指令（如 x86 `_pdep_u32` 或 GPU 移位掩码）以常数级时钟周期极速完成：

.. code-block:: cpp

   // 展开 10 位整数至 30 位 (每位之间插入 2 个 0)
   inline uint32_t ExpandBits(uint32_t v) {
       v = (v * 0x00010001u) & 0xFF0000FFu;
       v = (v * 0x00000101u) & 0x0F00F00Fu;
       v = (v * 0x00000011u) & 0xC30C30C3u;
       v = (v * 0x00000005u) & 0x49249249u;
       return v;
   }

   inline uint32_t CalculateMortonCode30(float3 normalizedPos) {
       uint32_t x = clamp((uint32_t)(normalizedPos.x * 1024.0f), 0u, 1023u);
       uint32_t y = clamp((uint32_t)(normalizedPos.y * 1024.0f), 0u, 1023u);
       uint32_t z = clamp((uint32_t)(normalizedPos.z * 1024.0f), 0u, 1023u);
       return (ExpandBits(x) << 2) | (ExpandBits(y) << 1) | ExpandBits(z);
   }

**2. Karras 2012 GPU 并行拓扑构建算法**

1. 对所有图元的 30 位莫顿码执行 GPU 并行双调/基数排序（Radix Sort），此时在数组中相邻的图元在三维物理空间中同样高度局部相邻；
2. 每一个内部节点 $i \in [0, M-2]$ 由一个独立的 GPU 线程并行处理；
3. 每个线程通过二分查找计算当前节点所覆盖的图元区间 $[j, k]$ 中莫顿码的**最长公共前缀（Longest Common Prefix - LCP）**；
4. 根据前缀差异点确定分裂位置 $\gamma$，将区间无锁分割为 $[j, \gamma]$ 与 $[\gamma+1, k]$；
5. 自底向上使用原子计数器合并包围盒。整棵 BVH 在数毫秒内全部在 GPU 端并行生成完毕！

------------------------------------------------------------------------
25.4 动态场景与两级加速结构 (TLAS / BLAS) 体系
------------------------------------------------------------------------

在现代游戏引擎中，场景包含大量静态几何体（如地形、建筑物）与频繁发生位移、旋转、缩放或骨骼动画的动态几何体（如角色、载具、植被）。如果每帧对全场景上千万多边形执行全量 BVH 重构，将造成巨大的算力浪费。

现代底层图形 API（DirectX 12 DXR、Vulkan Ray Tracing）确立了 **两级加速结构（Two-Level Acceleration Structure）** 标准体系：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                两级加速结构 (TLAS / BLAS) 运行时组织拓扑                 |
   +-------------------------------------------------------------------------+

   [ 顶层加速结构: TLAS (Top-Level Acceleration Structure) ]
   * 包含全场景所有物体的实例 (Instances)
   * 每个实例包含: 4x3 变换矩阵 (Transform), 材质/着色标识, 遮罩 (Mask), BLAS 指针
   * 特性: 图元数量少 (数百至数万), 每帧在 GPU 端瞬间完全重构 (Rebuild < 0.5ms)
                               |
               +---------------+---------------+
               |                               |
               v                               v
   [ 实例 1 (汽车 1: 变换矩阵 M_1) ]   [ 实例 2 (汽车 2: 变换矩阵 M_2) ]
               |                               | (共享同一底层几何拓扑)
               +---------------+---------------+
                               |
                               v
   [ 底层加速结构: BLAS (Bottom-Level Acceleration Structure) ]
   * 包含物体局部坐标系下的真实多边形网格 (Triangles / AABBs)
   * 静态物体: 离线/加载时构建最高质量 Binned SAH, 运行期完全只读零开销
   * 动态骨骼/蒙皮网格: 拓扑不变, 每帧仅执行极速包围盒重拟合 (Refit < 0.2ms)

Refit（重拟合）vs Rebuild（完全重构）决策模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Refit 操作**：保持现有的二叉树拓扑结构与指针关系完全不变。GPU Compute Shader 为每个叶子节点更新变换后的顶点 AABB，随后自底向上递归执行 `Parent.AABB = Union(Left.AABB, Right.AABB)`。耗时仅与节点数量呈线性关系，极其高效；
- **SAH 质量退化与 Rebuild 触发**：当物体发生剧烈旋转、断裂或拓扑改变时，原有的包围盒会发生严重膨胀与空洞重叠，导致 SAH 成本显著攀升，光线遍历效率断崖式下跌。
- 工业级引擎通过监控当前树的**总重叠表面积指标（SAH Metric Degradation）**：当 $\sum S(	ext{Nodes}_{	ext{current}}) / \sum S(	ext{Nodes}_{	ext{initial}}) > 1.35$ 时，在后台异步计算线程触发完整的 Rebuild 重构。

------------------------------------------------------------------------
25.5 现代 GPU 硬件与 Compute Shader 遍历栈优化
------------------------------------------------------------------------

光线在 BVH 树中的遍历是一个深层递归回溯过程。在 SIMT 架构的 GPU 上执行递归遍历，面临两大严峻挑战：
1. **寄存器压力与局部栈开销**：GPU 硬件没有像 CPU 一样无限的线程私有调用栈，每个线程若在局部显存中维护大尺寸栈结构，将导致严重的**寄存器溢出（Register Spilling）**与显存访问延迟；
2. **SIMT 分支发散（Warp Divergence）**：同一个 Warp 内的 32 条光线由于方向不同，访问的 BVH 分支路径产生严重分化，导致硬件执行单元空转。

Ray-AABB 光线包围盒快速相交算法 (Slab 法)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Slab 算法将 3D 包围盒视为 3 对平行平面的交集。对于光线 $\mathbf{R}(t) = \mathbf{O} + t\mathbf{D}$ 与包围盒 $[\mathbf{x}_{\min}, \mathbf{x}_{\max}]$：

设光线方向倒数 $\mathbf{D}_{	ext{inv}} = (1/D_x, 1/D_y, 1/D_z)$。在每个轴向上的进出参数为：

.. math::

   t_{x1} = (x_{\min} - O_x) \cdot D_{	ext{inv}.x}, \quad t_{x2} = (x_{\max} - O_x) \cdot D_{	ext{inv}.x}

.. math::

   t_{x,\min} = \min(t_{x1}, t_{x2}), \quad t_{x,\max} = \max(t_{x1}, t_{x2})

计算三轴求交区间的交集：

.. math::

   t_{	ext{enter}} = \max(t_{x,\min}, t_{y,\min}, t_{z,\min}), \quad t_{	ext{exit}} = \min(t_{x,\max}, t_{y,\max}, t_{z,\max})

**判定充要条件**：若且唯若 $t_{	ext{enter}} \le t_{	ext{exit}} \land t_{	ext{exit}} \ge t_{\min} \land t_{	ext{enter}} \le t_{\max}$ 时，光线与包围盒相交。通过使用 IEEE 754 浮点除法规则（$1.0 / 0.0 = +\infty$），该算法完全无需针对平行于坐标轴的光线进行特殊分支判断！

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                Slab 光线-包围盒求交法区间重叠判定几何示意图              |
   +-------------------------------------------------------------------------+

   Y 轴 Slab: y_max ---------------------------------------------------------
                     |       +-----------------------+        |
                     |       |      AABB 内部        |        |
              y_min ---------------------------------------------------------
                             |                       |
                             x_min                   x_max (X 轴 Slab)

   光线 R(t) -------> [t_x_min] ---> [t_y_min] --------> [t_y_max] -> [t_x_max]
                                     |===============|
                              重叠有效区间 [t_enter, t_exit]

GPU 遍历栈优化三大主流架构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **近子节点优先与动态栈压缩 (Closest-Child Push)**：
   在测试当前节点的左右子包围盒时，若两者均与光线相交，计算它们到光线起点的距离 $t_{L}$ 与 $t_{R}$。**将距离较远的子节点压入栈底，优先遍历距离较近的子节点**。这一策略能以最高概率在最前沿击中真实几何体，从而将光线的有效最大范围 $t_{\max}$ 快速收缩，进而剪枝剔除大量原本需要遍历的远端子树。
2. **短栈（Short-Stack）与栈顶溢出丢弃**：
   在 Compute Shader 中仅保留 8~16 个深度的轻量级寄存器数组。当遇到深层树导致栈溢出时，简单丢弃栈底元素，并在遍历回溯到底部时通过父节点索引动态恢复，从而将线程私有寄存器用量严格压制在 32 个以内，保持高达 100% 的 SM 占用率（Occupancy）。
3. **无栈遍历（Stackless BVH / Rope Trees）**：
   在离线构建期，为每个叶子节点的 6 个面预先计算并存储相邻节点的跳转指针（称为 Rope）。当光线离开当前叶子包围盒时，直接通过穿透面对应的 Rope 指针瞬时跳转至下一个相邻空间节点，**运行时内存栈深度完全为 0**，彻底消除了局部内存读写。

------------------------------------------------------------------------
25.6 工业级 32-Byte 紧凑节点布局与 HLSL GPU 遍历完整实现
------------------------------------------------------------------------

为了实现与现代 GPU 128-bit 显存总线事务的物理对齐，工业界将每个 BVH 二叉节点精确压缩为 **32 字节（2 个 `float4`）**：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                GPU 32-Byte 紧凑扁平化 BVH 节点内存布局 (Memory Layout)   |
   +-------------------------------------------------------------------------+

   [ 16 字节 / float4 (0~15 字节) ]:
   +-----------------------------+-----------------------------+-----------------------------+------------------------------------+
   | BBoxMin.x (float, 4 Bytes)  | BBoxMin.y (float, 4 Bytes)  | BBoxMin.z (float, 4 Bytes)  | LeftChildOrFirstPrim (uint, 4 Bytes|
   +-----------------------------+-----------------------------+-----------------------------+------------------------------------+

   [ 16 字节 / float4 (16~31 字节) ]:
   +-----------------------------+-----------------------------+-----------------------------+------------------------------------+
   | BBoxMax.x (float, 4 Bytes)  | BBoxMax.y (float, 4 Bytes)  | BBoxMax.z (float, 4 Bytes)  | PrimCountOrRightChild (uint, 4 Byte|
   +-----------------------------+-----------------------------+-----------------------------+------------------------------------+

   * 编码规则:
     - 若 PrimCount == 0: 该节点为内部节点 (Inner Node), 左子节点索引为 LeftChild, 右子节点索引为 RightChild;
     - 若 PrimCount > 0 : 该节点为叶子节点 (Leaf Node), 其包纳的第一项图元索引为 FirstPrim, 连续图元数为 PrimCount。

以下是符合 DirectX 12 / Vulkan 标准的工业级 HLSL 遍历着色器完整实现：

.. code-block:: hlsl

   // HLSL: 高性能 GPU 紧凑 BVH 深度优先遍历与求交 Compute Shader
   // 特性: 32-Byte 节点对齐 + Slab 无分支求交 + 近子节点优先 + 寄存器栈优化

   struct BVHNodeGPU {
       float3 BBoxMin;
       uint   LeftChildOrFirstPrim;
       float3 BBoxMax;
       uint   PrimCountOrRightChild; // 0 表示内部节点, >0 表示叶节点
   };

   struct TriangleGPU {
       float3 V0;
       float  Padding0;
       float3 V1;
       float  Padding1;
       float3 V2;
       float  MaterialID;
   };

   struct RayHit {
       float  T;
       float2 UV;
       uint   PrimIndex;
       uint   InstanceID;
   };

   StructuredBuffer<BVHNodeGPU>  g_BVHNodes   : register(t0);
   StructuredBuffer<TriangleGPU> g_Triangles  : register(t1);
   StructuredBuffer<uint>        g_PrimIndices: register(t2);

   // 高性能 Slab 光线-AABB 相交测试
   bool IntersectAABB(float3 rayOrigin, float3 rayInvDir, float3 boxMin, float3 boxMax, float rayTMin, float rayTMax, out float tEnter) {
       float3 t0 = (boxMin - rayOrigin) * rayInvDir;
       float3 t1 = (boxMax - rayOrigin) * rayInvDir;

       float3 tmin = min(t0, t1);
       float3 tmax = max(t0, t1);

       float enter = max(max(tmin.x, tmin.y), max(tmin.z, rayTMin));
       float exit  = min(min(tmax.x, tmax.y), min(tmax.z, rayTMax));

       tEnter = enter;
       return enter <= exit;
   }

   // Möller-Trumbore 高性能单指令光线-三角形求交算法
   bool IntersectTriangle(float3 rayOrigin, float3 rayDir, float3 v0, float3 v1, float3 v2, inout RayHit hit) {
       float3 e1 = v1 - v0;
       float3 e2 = v2 - v0;
       float3 pvec = cross(rayDir, e2);
       float  det  = dot(e1, pvec);

       if (abs(det) < 1e-8f) return false;
       float invDet = 1.0f / det;

       float3 tvec = rayOrigin - v0;
       float  u = dot(tvec, pvec) * invDet;
       if (u < 0.0f || u > 1.0f) return false;

       float3 qvec = cross(tvec, e1);
       float  v = dot(rayDir, qvec) * invDet;
       if (v < 0.0f || u + v > 1.0f) return false;

       float t = dot(e2, qvec) * invDet;
       if (t > 1e-4f && t < hit.T) {
           hit.T = t;
           hit.UV = float2(u, v);
           return true;
       }
       return false;
   }

   // GPU 线程私有短栈遍历主函数
   RayHit TraceRayBVH(float3 rayOrigin, float3 rayDir, float tMin, float tMax) {
       RayHit hit;
       hit.T = tMax;
       hit.UV = float2(0.0f, 0.0f);
       hit.PrimIndex = 0xFFFFFFFF;
       hit.InstanceID = 0;

       float3 rayInvDir = 1.0f / rayDir;

       // 线程私有遍历栈 (32 深度足以支持百万级多边形二叉树)
       uint stack[32];
       uint stackPtr = 0;

       // 压入根节点 (索引 0)
       stack[stackPtr++] = 0;

       while (stackPtr > 0) {
           // 弹出当前节点
           uint nodeIdx = stack[--stackPtr];
           BVHNodeGPU node = g_BVHNodes[nodeIdx];

           // 1. 判断是否为叶子节点
           if (node.PrimCountOrRightChild > 0) {
               // 遍历叶节点内引用的所有三角形
               uint firstPrim = node.LeftChildOrFirstPrim;
               uint primCount = node.PrimCountOrRightChild;

               for (uint i = 0; i < primCount; ++i) {
                   uint triIdx = g_PrimIndices[firstPrim + i];
                   TriangleGPU tri = g_Triangles[triIdx];

                   if (IntersectTriangle(rayOrigin, rayDir, tri.V0, tri.V1, tri.V2, hit)) {
                       hit.PrimIndex = triIdx;
                       // 关键剪枝: 缩小射线最大传播范围
                       // (注意: 此时光线有效 t 范围被自动收敛)
                   }
               }
           } else {
               // 2. 内部节点: 测试左右子节点 AABB
               uint leftIdx  = node.LeftChildOrFirstPrim;
               uint rightIdx = node.PrimCountOrRightChild;

               BVHNodeGPU leftChild  = g_BVHNodes[leftIdx];
               BVHNodeGPU rightChild = g_BVHNodes[rightIdx];

               float tEnterL, tEnterR;
               bool hitL = IntersectAABB(rayOrigin, rayInvDir, leftChild.BBoxMin, leftChild.BBoxMax, tMin, hit.T, tEnterL);
               bool hitR = IntersectAABB(rayOrigin, rayInvDir, rightChild.BBoxMin, rightChild.BBoxMax, tMin, hit.T, tEnterR);

               // 3. 近子节点优先遍历策略 (Closest-Child Heuristic)
               if (hitL && hitR) {
                   if (tEnterL < tEnterR) {
                       stack[stackPtr++] = rightIdx; // 较远的先入栈 (后遍历)
                       stack[stackPtr++] = leftIdx;  // 较近的后入栈 (先遍历)
                   } else {
                       stack[stackPtr++] = leftIdx;
                       stack[stackPtr++] = rightIdx;
                   }
               } else if (hitL) {
                   stack[stackPtr++] = leftIdx;
               } else if (hitR) {
                   stack[stackPtr++] = rightIdx;
               }
           }
       }

       return hit;
   }

------------------------------------------------------------------------
小结与下卷导读
------------------------------------------------------------------------

本章系统解构了现代空间加速层次结构的核心骨干体系：
1. **架构拓扑**：对比了空间划分与物体划分（BVH）的物理特性，确立了二叉 BVH 在内存扁平化、无冗余存储与硬件 RT Core 硬化支持上的统治地位；
2. **数学推导**：基于 Crofton 凸包几何概率严格推导了表面积启发式（SAH）成本函数与叶节点终止分裂准则；
3. **算法演进**：对比了解析精确 SAH、分桶 Binned SAH 与面向 GPU 极速构建的莫顿码线性 BVH（LBVH）；
4. **引擎分层**：阐述了全场景 TLAS 与网格局部 BLAS 的两级加速架构，以及动态场景下的 Refit 与 Rebuild 权衡；
5. **硬件遍历**：推导了无分支 Slab 光线-AABB 求交算法，建立了 32-Byte 紧凑节点内存对齐模型，并交付了基于 HLSL 的近子节点优先 GPU 遍历实现。

至此，**第五模块（Part 5: 阴影算法与空间加速结构）全量收官完工（5/5 节，全书累计完成 25/45 节）**。全书进度正式跨过 50% 关键里程碑！

下一卷我们将跨入渲染引擎最具视觉冲击力的核心领域——**第六模块（Part 6: 全局光照与光线追踪体系）**。在 Chapter 26 中，我们将首先深入实时环境光遮蔽的经典巅峰之作——**屏幕空间环境光遮蔽 (SSAO)：从原始球体采样、地平线基准 HBAO 到现代真实感微表面 GTAO 与弯曲法线 (Bent Normals) 积分计算**，开启全动态光线与间接照明的宏大篇章。
