========================================================================
Chapter 44: 动态全局光照与无限反弹：UE5 Lumen 表面缓存 (Surface Cache) 与屏幕/硬件追踪融合
========================================================================

.. note:: 前置背景与认知承接
   在 Chapter 43 中，我们深入解构了以 UE5 Nanite 为代表的几何虚拟化架构革命。Nanite 依靠网格簇有向无环图（Cluster DAG）、两阶段层次化剔除、软硬件混合自适应光栅化以及极简可见性缓冲区（Visibility Buffer），彻底摧毁了传统图形管线在面对数亿微多边形时的辅助线程过着色惩罚与几何前端带宽墙，实现了屏幕空间几何细节的物理无限化。

   然而，纯粹的几何革命立刻将实时渲染推入了另一个前所未有的物理深水区——**全动态全局光照（Dynamic Global Illumination）危机**。在影视级与现代开放世界游戏场景中，Nanite 带来的数十亿动态多边形直接宣告了传统离线光照烘焙技术（Precomputed Lightmaps）的死刑：面对不断破坏变形的几何体、动态时间与天气变换，离线烘焙数小时甚至数天的纹理贴图根本无法使用。同时，传统的屏幕空间光照（如 SSAO、SSGI、SSR）仅能感知屏幕当前视口内可见的几何薄片，一旦物体移出屏幕或被前景遮挡，反射与遮蔽立即发生剧烈断层伪影。而若直接采用纯粹的硬件光线追踪（Hardware Ray Tracing / DXR），对数十亿微多边形实时构建与更新底层加速结构（BLAS / TLAS），并逐像素发射弥散漫反射光线，巨大的光线发散度（Ray Divergence）与随机显存访存将导致现代 GPU 微架构瞬间陷入显存带宽彻底枯竭。

   为了在完全动态的微多边形世界中实现低开销、高保真、支持无限次光照反弹（Infinite Bounces）的全局光照，Epic Games 设计并构建了革命性的**动态全局光照与反射系统——Lumen**。Lumen 的核心精髓在于**多层次几何代理表达与多级光线求交管线的深度融合**：它通过创新的**表面缓存（Surface Cache）**将场景表面着色与相机视口彻底解耦；通过**网格有向距离场（Mesh SDF）**与**全局距离场（Global SDF）**实现宏大场景的超高速软件光线步进；并在硬件光追可用时，无缝回退至简化几何代理的硬件光追加速管线。本章将深入剖析 Lumen 的底层微架构，推导表面缓存空间流送、SDF 空间步进、无限反弹递推积分以及时空降噪滤波的完整工业级实现。

------------------------------------------------------------------------
44.1 动态全局光照的物理挑战与 Lumen 架构全景
------------------------------------------------------------------------

渲染方程与多重反弹的实时困境
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
基于辐射度量学（Radiometry，Chapter 16），点 $\vec{x}$ 沿出射方向 $\omega_o$ 的总出射辐射率满足经典的** Rendering Equation（Kajiya 渲染方程）**：

.. math::

   L_o(\vec{x}, \omega_o) = L_e(\vec{x}, \omega_o) + \int_{\Omega} f_r(\vec{x}, \omega_i, \omega_o) \, L_i(\vec{x}, \omega_i) \, (\vec{n} \cdot \omega_i) \, d\omega_i

在完全封闭或深层室内场景中，入射光 $L_i(\vec{x}, \omega_i)$ 绝大部分来自于其他物体表面的反射光，即：

.. math::

   L_i(\vec{x}, \omega_i) = L_o(\vec{x}', -\omega_i), \quad \vec{x}' = 	ext{RayCast}(\vec{x}, \omega_i)

这构成了一个无限维递归积分。传统离线烘焙通过将间接光计算转化为辐射度线性方程组或长序列离线路径追踪解决，但在动态世界中，场景中光源的移动、门窗的开启、建筑物的倒塌都会瞬间改变全局可见性流（Visibility Function）。

在实时帧率预算（$16.6\,	ext{ms}$ 或 $33.3\,	ext{ms}$）下，全动态 GI 面临三大微架构层面的硬性物理约束：
1. **几何体量与 BVH 构建开销矛盾**：现代 DXR / Vulkan 硬件光追要求为每个三角形建立层次包围盒（BVH）。面对 Nanite 的数千万动态微多边形，每帧在 GPU 上执行 BVH 重建（Rebuild / Refit）的显存带宽开销就超过数百 GB/s；
2. **光线遍历发散与 Cache 命中率断崖**：漫反射间接光遵循半球面均匀分布，随机采样导致光线方向高度各向同性。GPU 线程束（Warp / Wavefront）内的 32 个线程将访问全然不同的空间分支与材质贴图，造成 L1/L2 缓存命中率跌破 15%，引发长达数百周期的 DRAM 延迟停顿；
3. **无限次反弹算力指数膨胀**：单次光线命中后若继续发射次级光线追踪第 2 次、第 3 次反弹，计算复杂度按指数级 $O(k^N)$ 膨胀，实时硬件绝无可能承受。

Lumen 多层次分级混合架构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
针对上述物理约束，Lumen 确立了**“多级空间代理 + 分段光线遍历 + 表面辐射度解耦缓存”**的宏观架构设计：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       UE5 Lumen 混合光照管线宏观拓扑架构                  |
   +-------------------------------------------------------------------------+

   [ 相机屏幕空间 ]                 [ 近场区域 (< 50m) ]           [ 远场区域 (< 200m) ]
   +-----------------------+       +---------------------+        +--------------------+
   | 屏幕空间深度/法线缓冲 |       | Mesh SDF (高精度)   |        | Global SDF (低精度)|
   | (Screen Tracing)      | ----> | & Card Surface Cache| -----> | Clipmap 连续体素   |
   +-----------------------+       +---------------------+        +--------------------+
              |                               |                              |
              v                               v                              v
   +---------------------------------------------------------------------------------+
   | 光线求交仲裁器 (Ray Traversal Arbiter):                                          |
   | 优先 Screen Trace -> 屏幕缺失/穿透转 Mesh SDF -> 超出范围转 Global SDF / DXR HW  |
   +---------------------------------------------------------------------------------+
              |
              v (光线命中空间任意表面)
   +---------------------------------------------------------------------------------+
   | 辐射度拉取 (Radiance Evaluation):                                               |
   | 不在命中断点执行材质与阴影求值！直接采样预构建好的 **Surface Cache (表面缓存)**  |
   +---------------------------------------------------------------------------------+
              |
              v (时空积分与多级反弹)
   +---------------------------------------------------------------------------------+
   | Final Gathering -> 探针网格辐射度缓存 -> 时域累积时间滤波器 -> 最终合成输出       |
   +---------------------------------------------------------------------------------+

.. list-table:: 主流实时光照管线与 Lumen 架构对比矩阵
   :widths: 20 25 25 30
   :header-rows: 1
   :class: tight-table

   * - 技术方案
     - 离线光照烘焙 (Lightmaps)
     - 纯 DXR 硬件路径追踪 (ReSTIR PT)
     - UE5 Lumen 混合动态管线
   * - **几何与场景动态性**
     - 完全静态，不支持动态破坏与位移
     - 完全动态，但极大受限于 BVH 预算
     - **完全动态，原生兼容 Nanite 几何虚拟化**
   * - **光线求交成本**
     - 零运行时求交，预烘焙至纹理
     - 极高，硬件 BVH 遍历吞吐受限
     - **混合：Screen Trace + SDF 步进 + 代理 DXR**
   * - **光照求值方式**
     - 预计算直接读取纹理像素
     - 每次命中现场调用材质着色器与阴影
     - **命中点直接查表采样解耦的 Surface Cache**
   * - **反弹次数限制**
     - 预烘焙支持无限次反弹
     - 实时帧率下通常仅支持 1~2 次反弹
     - **通过上一帧表面缓存反馈，近似达成物理无限反弹**
   * - **显存与硬件门槛**
     - 极高磁盘占用，运行时低显存开销
     - 极高，需要顶级硬件光追单元（RT Core）
     - **中高显存开销，全线兼容软光追与硬光追平台**

------------------------------------------------------------------------
44.2 表面缓存 (Surface Cache) 微架构：参数化解耦与空间流送
------------------------------------------------------------------------

Mesh Cards：表面正交投影剖分
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
如果光线每次击中场景中的物体表面时，都要去加载该物体的顶点属性、采样多套 4K PBR 材质纹理并向所有光源发射阴影测试光线，硬件算力将在数毫秒内枯竭。Lumen 解决这一难题的终极武器是**表面缓存（Surface Cache）**。

Surface Cache 的设计思想是：**将场景中任意物体表面的光照状态与相机的实时视口完全剥离，将其几何朝向、材质属性与受光辐射率预先烘焙在以图集（Atlas）形式驻留显存的参数化低分辨率纹理中**。当海量漫反射与镜面反射光线打到物体表面时，着色器仅需执行一次极快的 2D 纹理双线性采样，便可瞬间获取该点的全部出射辐射度！

为了为任意复杂的静态网格体（Static Mesh）自动生成紧凑的参数化 UV，Lumen 引入了 **Mesh Cards（网格卡片投影）**：
1. **外包盒投影聚类**：对于每个网格体，离线或在加载时算法在其 6 个轴向（$\pm X, \pm Y, \pm Z$）上放置正交虚拟相机；
2. **贪心表面覆盖算法**：寻找一组数量精简（每个网格通常 12 到 24 张）且能够最大化覆盖该模型外表面的矩形卡片（Cards）；
3. **卡片元数据（Card Metadata）**：每张 Card 本质上是一个带厚度的 3D 定向包围盒（OBB），记录其中心点坐标、旋转四元数、长宽半包围盒尺寸，以及在全局物理 Surface Cache Atlas 中的 UV 分配偏移。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                Mesh Cards 空间正交投射与 Surface Cache 纹理图集             |
   +-------------------------------------------------------------------------+

       [ 任意三维几何体 ]                [ 6 轴向正交 Card 虚拟投射 ]
             / \                             Card +Z (顶视)
            /   \                                |
           /     \                               v
          /       \                  +-----------------------+
         +---------+    Card -X ---> |  3D Mesh Surface Area | <--- Card +X
         |  复杂   |    (左视)        |   (表面几何深度与法线)  |      (右视)
         |  模型   |                 +-----------------------+
         +---------+                             ^
                                                 |
                                            Card -Z (底视)
                                                 |
                                                 v
   [ 汇聚装箱打包装配至 GPU 物理驻留显存 Atlas ]
   +-------------------------------------------------------------------------+
   | Global Surface Cache Physical Atlas (动态分页流送图集)                     |
   | +--------------------+--------------------+---------------------------+ |
   | | Card 0: BaseColor  | Card 1: Normal     | Card 2: Emissive          | |
   | | (RGB8_UNORM)       | (RGB10A2_UNORM)    | (R11G11B10_FLOAT)         | |
   | +--------------------+--------------------+---------------------------+ |
   | | Card 0: DirectRad  | Card 1: IndirectRad| Card 2: Final Radiance    | |
   | | (直接光照辐照度)   | (上一帧多弹反馈)   | (全光照复合，供光线直接读)| |
   | +--------------------+--------------------+---------------------------+ |
   +-------------------------------------------------------------------------+

多物理属性 Atlas 布局与分块分配
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Surface Cache Atlas 在 GPU 显存中分配为一组平行的平铺纹理数组（Tiled Texture Arrays），分辨率通常为 $4096 	imes 4096$：
- **物理几何属性层**：存储每个 Card 采样像素的世界法线（World Normal）、深度偏移与材质不透明度；
- **材质属性层**：存储漫反射基色（BaseColor）与表面粗糙度（Roughness）；
- **直接光照层（Direct Radiance）**：以低频步长调度 Shadow Map 或虚拟阴影贴图（VSM）针对 Card 进行直接光评估；
- **间接光照层（Indirect Radiance）**：存储场景在当前 Card 上积累的多重反弹间接辐照度。

动态优先级流送与视锥体自适应分配
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
如果无差别地为整个大世界所有物体生成全精度 Surface Cache，显存将被瞬时撑爆。Lumen 采用严格的**视锥可见性动态分页流送机制（View-Dependent Streaming）**：
1. **可见性反馈驱动**：在每一帧光栅化（G-Buffer / VisBuffer Pass）以及前一帧光线追踪遍历时，GPU Compute Shader 记录哪些 Card 被光线实际命中或位于主视锥体内，生成一个“活跃请求位图（Active Request Bitmask）”；
2. **多级分辨率分级（Card LODs）**：
   - **高精度卡片（Detailed Cards）**：距离相机近且被视线高度关注的物体，分配每米 $64$ 或 $32$ 像素的物理图集空间；
   - **粗糙体素卡片（Coarse Cards）**：处于中景或遮挡深处仅供间接反射采样的表面，降级为每米 $4$ 像素或仅保留单色常数；
   - **未激活（Inactive）**：完全背向相机且未被任何反射光线命中的 Card，直接在物理图集中释放分配（Deallocate），将其显存页复用给新出现的物体。

通过这套机制，Lumen 将一个数平方公里、包含上百万动态实例的宏大场景的可见表面光照，稳定压缩至 **不足 200MB 的固定显存预算** 之中。

------------------------------------------------------------------------
44.3 距离场求交加速：Mesh SDF 与 Global SDF 分层层级
------------------------------------------------------------------------

有向距离场 (SDF) 数学原理与 Sphere Tracing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在光线遍历阶段，为了在不依赖高成本硬件 BVH 的前提下执行高速光线求交，Lumen 大规模引入了**有向距离场（Signed Distance Field - SDF）**。

空间中的有向距离标量场是一个实数连续函数 $\phi(\vec{x}): \mathbb{R}^3 	o \mathbb{R}$，定义为空间中任意点 $\vec{x}$ 到最近几何表面 $\partial \Omega$ 的欧几里得最短距离：

.. math::

   \phi(\vec{x}) = \begin{cases}
   -\min_{\vec{y} \in \partial \Omega} \|\vec{x} - \vec{y}\|, & \vec{x} \in \Omega 	ext{ (几何体内部)} \
   0, & \vec{x} \in \partial \Omega 	ext{ (几何体边界)} \
   +\min_{\vec{y} \in \partial \Omega} \|\vec{x} - \vec{y}\|, & \vec{x} 
otin \Omega 	ext{ (自由外部空间)}
   \end{cases}

利用 SDF 进行光线求交的核心算法是 **球体步进追踪（Sphere Tracing / Ray Marching）**。设光线起点为 $\vec{P}_0$，传播方向为单位向量 $\vec{D}$。传统步进算法必须采用固定的微小步长，计算量巨大；而利用 SDF，由于已知以当前点 $\vec{P}_k$ 为中心、半径为 $\phi(\vec{P}_k)$ 的球形空间内**绝对不存在任何物体表面**，光线可以无风险地直接向前跨越整整 $\phi(\vec{P}_k)$ 的安全距离：

.. math::

   \vec{P}_{k+1} = \vec{P}_k + \phi(\vec{P}_k) \cdot \vec{D}

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                SDF Sphere Tracing (球体安全步进) 空间推进机制             |
   +-------------------------------------------------------------------------+

   光线起点 P0                                           几何障碍表面 (SDF = 0)
        * === 安全跨越 R0 ===> P1                             +---------------+
       / \                   / \                              |               |
      | R0|                 | R1| === 安全跨越 R1 ===> P2      |   Solid       |
       \ /                   \ /                     / \      |   Geometry    |
        *                     *                     | R2| ==> | * (P_hit)     |
                                                     \ /      |               |
                                                      *       +---------------+
   [ 物理特征 ]:
   1. 远离物体表面时 (R 大): 仅需 1~2 次超大步长跨越广阔虚空;
   2. 逼近物体表面时 (R 趋近 0): 步长自然收敛, 极其精确地捕获几何切点!

如果 $\phi(\vec{P}_k) < \epsilon$（$\epsilon$ 通常取 $0.01\,	ext{cm}$），判定为光线命中；如果步进总距离超过设定上限或步进次数耗尽，判定为光线穿透至无穷远。更重要的是，命中断点的表面几何法线 $\vec{N}$ 完全无需读取网格顶点，直接通过 SDF 标量场的**中心差分梯度（Central Difference Gradient）**解析求得：

.. math::

   \vec{N}(\vec{x}) = 	ext{normalize}\left( 
abla \phi(\vec{x}) \right) = 	ext{normalize}\begin{pmatrix}
   \phi(\vec{x} + \delta\hat{i}) - \phi(\vec{x} - \delta\hat{i}) \
   \phi(\vec{x} + \delta\hat{j}) - \phi(\vec{x} - \delta\hat{j}) \
   \phi(\vec{x} + \delta\hat{k}) - \phi(\vec{x} - \delta\hat{k})
   \end{pmatrix}

Mesh SDF：局部精细稀疏体素场
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
为了保留复杂物体的几何细节，Lumen 为每个静态网格预计算**Mesh SDF（网格距离场）**：
- **局部稀疏体素化**：将模型三维 AABB 剖分为 $64 	imes 64 	imes 64$ 或更高分辨率的局部体素网格。为了节约显存，采用类似砖块分层树（Sparse Voxel Bricks）的数据结构，仅对距离表面小于一定阈值的活动外壳存储体素值；
- **定点压缩**：SDF 距离数值被量化为 8 位或 16 位整型有符号数，极大削减显存占用；
- **动态实例变换**：在运行时，场景中存在数万个实例。光线在追踪某个实例时，通过将光线起点与方向乘以该实例的世界逆变换矩阵 $\mathbf{M}_{	ext{world}}^{-1}$，瞬间变换至实例局部模型空间，直接在局部体素块内执行 Sphere Tracing，完美支持静态物体的任意平移、旋转与非等比缩放。

Global SDF：级联连续体素剪裁图 (Clipmaps)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当光线需要传播数十米甚至上百米以解算天空光、群山遮挡或远景反射时，逐一测试成千上万个 Mesh SDF 会导致严重的分支发散。为此，Lumen 构建了与相机协同移动的**全局距离场（Global SDF）**。

Global SDF 采用四级同心嵌套的 **3D 纹理剪裁图（Clipmaps）**：
- **Level 0 (最精细级)**：覆盖相机周围 $10\,	ext{m}$ 范围，体素边长约 $5\,	ext{cm}$；
- **Level 1**：覆盖 $40\,	ext{m}$ 范围，体素边长约 $20\,	ext{cm}$；
- **Level 2**：覆盖 $100\,	ext{m}$ 范围，体素边长约 $50\,	ext{cm}$；
- **Level 3 (最粗糙级)**：覆盖 $200\,	ext{m}$ 以上宏观地貌，体素边长约 $1.5\,	ext{m}$。

在每一帧，GPU Compute Shader 执行一个增量合并管线（Voxel Merging Pass）：将进入视锥范围内的各个 Mesh SDF 按照空间重叠关系，动态将最短距离写入对应的 Global SDF Clipmap 体素中。远场漫反射光线无需关心微观几何，直接在 Global SDF 中以极高的步长飞速向前推进，将远距离环境遮挡开销压制在微秒级别。

------------------------------------------------------------------------
44.4 屏幕追踪与软硬件光线追踪融合流 (Hybrid Ray Tracing Pipeline)
------------------------------------------------------------------------

多级光线求交流水线状态机
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在实际光线求交时，Lumen 绝不押宝于单一的追踪算法，而是构建了一条层层递进、以精度与性能最优匹配的**多级混合求交状态机（Hierarchical Ray Traversal State Machine）**：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |             Lumen 多级分层光线求交判定时序状态机 (Ray Traversal Flow)     |
   +-------------------------------------------------------------------------+

   [ 步骤 1: 屏幕空间微光线步进 (Screen Tracing) ]
          |
          +---> (命中且未穿透?) ===> [ 提取屏幕深度法线 -> 直接采样当前帧全分辨率光照 ]
          |
          v (步进超界 / 背向相机 / 命中深度断层穿透)
   [ 步骤 2: 切换至距离场软件光线追踪 (Mesh SDF / Global SDF) ]
          | (若项目启用了硬件 DXR 光追，此步转为遍历简化代理网格 BLAS)
          |
          +---> (求交命中物体表面?) 
                     |
                     v
   [ 步骤 3: 表面缓存反查 (Surface Cache Resolve) ]
          |
          |-- 3.1: 取得命中实例 ID 与世界坐标
          |-- 3.2: 计算命中点在该实例最佳 Card 投影下的局部 (u, v) 参数坐标
          |-- 3.3: 采样 Surface Cache Atlas，获取该表面的出射总辐射率 (Radiance)
          v
   [ 步骤 4: 辐射度返回，参与当前像素间接光积分 ]

屏幕空间追踪的 Hi-Z 加速与穿透兜底
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
对于近距离反射（如光滑地面倒影）和接触阴影，屏幕空间拥有当前场景最完整、最高精度的 Nanite 细分几何。Lumen 优先利用当前视口的深度金字塔（Hierarchical-Z / Hi-Z）执行屏幕空间光线步进（Screen Traces）：
1. **基于 DDA 的 Hi-Z 空间跳步**：光线在屏幕像素坐标系下行进，遇到深度不匹配时沿 Hi-Z 粗粒度 Mip 级别快速跳过均质平面；
2. **厚度与穿透判定（Thickness Threshold）**：屏幕深度仅记录最外层表面，无法感知物体后方的厚度。若光线穿过深度表面且穿透深度大于设定阈值 $\Delta Z_{	ext{max}}$，算法判定为“发生漏光穿透失败”；
3. **无缝移交 SDF**：屏幕追踪一旦因穿透、视野出界或背面采样而宣告失败，光线立即将当前的行进端点作为新起点，**平滑交由 Mesh SDF 软件追踪或硬件 DXR 接管**，两者的空间边界通过权值插值完全消除跳变接缝。

硬件光追模式下的 Nanite 代理网格 (Proxy Meshes)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当项目开启“Lumen 硬件光追（Hardware Ray Tracing）”时，Lumen 不再调用 SDF Sphere Tracing，而是调用 DXR / Vulkan RT 的 `TraceRay()` 指令。

然而，Nanite 网格在原始状态下包含数千万微多边形，绝不能直接塞入 DXR BLAS。Lumen 的破局之策是：**利用 Nanite Cluster DAG 的根节点附近较粗糙的层级，提取一个由数千至上万个多边形组成的轻量级“代理网格（Nanite Ray Tracing Proxy Mesh）”**。
- **BLAS 极简构建**：仅为低模代理网格构建 DXR BLAS，每帧构建与更新消耗降低两个数量级；
- **材质解耦保持**：硬件光追的光线击中代理三角形后，**严禁触发复杂的 Any-Hit 或 Closest-Hit 材质着色器**！着色器同样仅计算命中点的 Card 投影坐标，直接拉取 Surface Cache 纹理。这使得硬件光追仅发挥其最高效的“纯空间求交加速电路（RT Core Box/Triangle Intersection）”性能，彻底避开了材质发散与着色死循环。

------------------------------------------------------------------------
44.5 辐射度缓存、时域滤波与双边空间重构 (Radiance Cache & Denoising)
------------------------------------------------------------------------

世界空间辐射度缓存 (World-Space Radiance Cache)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
对于漫反射全局光照（Diffuse GI），光线在整个空间呈极其均匀的半球面散射。若逐屏幕像素发射 32 条光线，即使有 Surface Cache 和 SDF，性能依然无法维持 60 FPS。

Lumen 对漫反射分支引入了**辐射度缓存（Radiance Cache）**架构：
1. **视锥空间八叉树探针阵列**：在相机前方的三维空间，根据距离自适应构建多级密度的稀疏探针网格（Probes）。距离相机近处探针间距为数十厘米，远处逐渐扩大至数米；
2. **八面体方向采样（Octahedral Directional Probes）**：每个探针向周围空间发射一组经过低差异序列（Sobol / Halton）抖动分布的光线，每条光线利用前述管线求交并采样 Surface Cache，将全向入射辐射度编码为一个分辨率极低（例如 $8 	imes 8$）的八面体球面映射图；
3. **屏幕插值与接触边缘重构**：全分辨率屏幕着色时，像素只需根据自身世界坐标，在其周围的 8 个邻近探针之间执行**基于距离和法线双边权重的三线性插值（Tricubic/Trilinear Interpolation）**。仅在检测到几何法线或深度突变（如墙角缝隙）时，额外发射数条短距离 Screen Trace 补充精细的高频接触遮蔽（Contact AO）。

时域反弹递归反馈：无限次光照反弹的数学闭环
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Lumen 实现“无限次反弹”的技术机理极其优雅而高效：它完全没有使用开销庞大的递归光线调用，而是将**表面缓存（Surface Cache）本身作为一个动态跨帧反馈蓄水池**：

.. math::

   L_{	ext{SurfaceCache}}^{(t)}(\vec{x}) = L_{	ext{Direct}}^{(t)}(\vec{x}) + \int_{\Omega} f_r(\vec{x}, \omega_i) \cdot L_{	ext{SurfaceCache}}^{(t-1)}(	ext{Hit}(\vec{x}, \omega_i)) \, (\vec{n} \cdot \omega_i) \, d\omega_i

1. **帧 $t-1$**：在上一帧渲染结束时，Surface Cache 中已经存储了当前场景由直接光照激发的第 1 次反弹辐射度；
2. **帧 $t$**：当探针或新发射的光线击中表面并查询 Surface Cache 时，采出来的不再是纯黑色或无光照的原始材质，而是已经包含了上一帧光照历史的 $L_{	ext{SurfaceCache}}^{(t-1)}$；
3. **能量递推**：随着时间步长的推进，$t$ 帧的光照被再次写回 Surface Cache，作为第 2 次反弹；在接下来的 $t+1, t+2$ 帧中，光线自发携带了第 3 次、第 4 次乃至第 $N$ 次反弹的能量！

只要场景不发生全剧烈瞬变，这种**时域递推马尔可夫链**在数帧内便在物理上自发收敛至稳态辐射度平衡，以极其微小的计算代价达成了近乎离线路径追踪的无限次反弹视觉效果。

时域累积与引导双边滤波降噪 (Spatiotemporal Denoising)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
由于每一帧为辐射度探针或全屏反射发射的光线极其稀疏（反射通道平均仅 $0.25 \sim 1$ Ray/Pixel），RAW 追踪输出充斥着强烈的蒙特卡洛高频白噪声。Lumen 必须配备工业级时空降噪器（Denoising Pipeline）：
1. **历史帧双向重投影（Temporal Reprojection）**：结合屏幕速度缓冲区（Velocity Buffer）与上一帧相机反向矩阵，将历史间接光重投影至当前帧；
2. **邻域色彩空间方差裁剪（Variance Box Clamping）**：计算当前帧周围 $3 	imes 3$ 像素的历史色彩均值与标准差，将历史采样的色彩截断在 $[\mu - \sigma, \mu + \sigma]$ 凸包内，从根本上压制鬼影（Ghosting）；
3. **多尺度引导双边十字滤波（Cross-Bilateral Filtering）**：在空间域以深度梯度（Depth Gradient）和表面法线夹角为引导权重执行多级降采样模糊，使漫反射噪声彻底平滑的同时，严格保全建筑物阳角与几何边缘的高频对比度。

------------------------------------------------------------------------
44.4 工业级 Lumen 核心光线步进与表面缓存着色微架构实现
------------------------------------------------------------------------

以下给出基于 **HLSL (Shader Model 6.6+)** 构建的 Lumen 核心计算着色器微架构实现。该源码完整演示了 Global SDF 剪裁图的球体安全步进追踪、法线解析计算、Mesh Card 局部坐标投影，以及从 Surface Cache Atlas 读取出射辐射度并与时域反弹融合的底层工程闭环：

.. code-block:: hlsl

   // =========================================================================
   // File: LumenCoreSDFSurfaceCache.hlsl
   // Architecture: Dynamic Global Illumination SDF Marching & Surface Cache Sampling
   // Standard: HLSL SM 6.6+, Bindless Texturing, Conservative Sphere Tracing
   // =========================================================================

   #define THREADS_PER_GROUP_X 8
   #define THREADS_PER_GROUP_Y 8
   #define MAX_SDF_TRACE_STEPS 64
   #define SDF_SURFACE_THRESHOLD 0.005f // 0.5cm 击中阈值
   #define MAX_TRACE_DISTANCE 150.0f    // 最大步进 150 米

   // -------------------------------------------------------------------------
   // 1. 数据契约定义与常数缓冲
   // -------------------------------------------------------------------------
   struct LumenCardRecord {
       float3 boundsCenter;
       float  padding0;
       float3 boundsExtent;
       float  padding1;
       float4 cardRotationQuat;      // Card 局部坐标系旋转四元数
       float2 atlasUVOffset;         // 在全局物理 Surface Cache Atlas 的基准偏移
       float2 atlasUVScale;          // 在全局物理 Surface Cache Atlas 的尺寸缩放
   };

   cbuffer LumenViewConstants : register(b0) {
       float4x4 g_WorldToClip;
       float4x4 g_ClipToWorld;
       float3   g_CameraWorldPos;
       float    g_GlobalClipmapExtent; // 当前最细级 Global SDF 的空间覆盖尺寸
       float4   g_GlobalSDFCenter;
       float2   g_AtlasDimensions;
       float    g_TemporalConvergenceAlpha; // 帧间反弹融合权重
   };

   // -------------------------------------------------------------------------
   // 2. 资源绑定 (Bindless / Explicit Bindings)
   // -------------------------------------------------------------------------
   Texture3D<float>                  g_GlobalSDFTexture       : register(t0); // 单通道 3D 浮点距离场
   SamplerState                      g_LinearClampSampler     : register(s0);
   StructuredBuffer<LumenCardRecord> g_LumenCardsBuffer       : register(t1);
   Texture2D<float4>                 g_SurfaceCacheRadiance   : register(t2); // 表面缓存历史辐射度
   Texture2D<float3>                 g_SurfaceCacheNormal     : register(t3); // 表面缓存真实法线

   RWTexture2D<float4>               g_RWIndirectDiffuseOutput: register(u0);

   // -------------------------------------------------------------------------
   // 3. 四元数旋转与局部空间坐标投影辅助函数
   // -------------------------------------------------------------------------
   float3 RotateVectorByQuat(float3 v, float4 q) {
       float3 t = 2.0f * cross(q.xyz, v);
       return v + q.w * t + cross(q.xyz, t);
   }

   float3 InvertRotateVectorByQuat(float3 v, float4 q) {
       float4 conjugateQ = float4(-q.xyz, q.w);
       return RotateVectorByQuat(v, conjugateQ);
   }

   // -------------------------------------------------------------------------
   // 4. Global SDF 距离采样与梯度法线推导
   // -------------------------------------------------------------------------
   float SampleGlobalSDF(float3 worldPos) {
       // 将世界坐标映射至当前 Global SDF Clipmap 归一化 [0, 1] 纹理坐标系
       float3 offset = worldPos - g_GlobalSDFCenter.xyz;
       float3 uvw = (offset / g_GlobalClipmapExtent) + 0.5f;

       // 超出最细级体素包围体则返回正无穷，指示转交下级低模
       if (any(uvw < 0.0f) || any(uvw > 1.0f)) {
           return 1000.0f;
       }
       return g_GlobalSDFTexture.SampleLevel(g_LinearClampSampler, uvw, 0);
   }

   float3 CalculateSDFNormal(float3 worldPos, float currentDistance) {
       const float delta = 0.02f; // 2cm 中心差分步长
       float dX = SampleGlobalSDF(worldPos + float3(delta, 0, 0)) - SampleGlobalSDF(worldPos - float3(delta, 0, 0));
       float dY = SampleGlobalSDF(worldPos + float3(0, delta, 0)) - SampleGlobalSDF(worldPos - float3(0, delta, 0));
       float dZ = SampleGlobalSDF(worldPos + float3(0, 0, delta)) - SampleGlobalSDF(worldPos - float3(0, 0, delta));
       return normalize(float3(dX, dY, dZ));
   }

   // -------------------------------------------------------------------------
   // 5. 表面缓存反查 (Surface Cache Resolve)
   // -------------------------------------------------------------------------
   float3 ResolveSurfaceCacheRadiance(float3 hitWorldPos, float3 hitNormal, uint bestCardId) {
       LumenCardRecord card = g_LumenCardsBuffer[bestCardId];

       // 1. 将命中断点变换至 Card 局部 OBB 坐标系
       float3 localPos = InvertRotateVectorByQuat(hitWorldPos - card.boundsCenter, card.cardRotationQuat);

       // 2. 正交投影至二维 Card 参数面 [0, 1]
       float2 localUV = (localPos.xy / card.boundsExtent.xy) * 0.5f + 0.5f;
       localUV = clamp(localUV, 0.0f, 1.0f);

       // 3. 映射到物理全局 Surface Cache Atlas 绝对 UV
       float2 atlasUV = localUV * card.atlasUVScale + card.atlasUVOffset;

       // 4. 双线性采样出射辐射度与材质历史累积
       float4 cachedData = g_SurfaceCacheRadiance.SampleLevel(g_LinearClampSampler, atlasUV, 0);
       return cachedData.rgb;
   }

   // -------------------------------------------------------------------------
   // 6. Lumen 主计算内核：光线步进与无限反弹合成
   // -------------------------------------------------------------------------
   [numthreads(THREADS_PER_GROUP_X, THREADS_PER_GROUP_Y, 1)]
   void CS_LumenGlobalSDFMarchAndShade(
       uint3 dispatchThreadId : SV_DispatchThreadID
   ) {
       uint2 pixelCoord = dispatchThreadId.xy;

       // 从 G-Buffer 解包主视口世界位置与几何法线 (此处简化展示)
       float2 screenUV = (float2(pixelCoord) + 0.5f) / float2(1920.0f, 1080.0f);
       // 假定读取当前像素的世界位置与表面法线
       float3 surfaceWorldPos = float3(0, 0, 0); // 实际为 G-Buffer 读取
       float3 surfaceNormal   = float3(0, 1, 0);

       // 依据余弦加权分布生成一条漫反射半球采样光线 (基于低差异序列抖动)
       // 此处指定一条定向探测向量作为微架构逻辑闭环展示
       float3 rayOrigin    = surfaceWorldPos + surfaceNormal * 0.05f; // 微小偏移防止自相交
       float3 rayDirection = normalize(surfaceNormal + float3(0.2f, 0.8f, 0.1f));

       // ---------------------------------------------------------------------
       // 阶段 A: Sphere Tracing (球体安全步进光线求交)
       // ---------------------------------------------------------------------
       float totalDistTraveled = 0.0f;
       bool  bHitSurface = false;
       float3 currentRayPos = rayOrigin;

       for (int stepIdx = 0; stepIdx < MAX_SDF_TRACE_STEPS; ++stepIdx) {
           float sceneDist = SampleGlobalSDF(currentRayPos);

           // 击中表面判定
           if (sceneDist < SDF_SURFACE_THRESHOLD) {
               bHitSurface = true;
               break;
           }

           // 安全跨越距离并推进光线端点
           totalDistTraveled += sceneDist;
           if (totalDistTraveled >= MAX_TRACE_DISTANCE) {
               break; // 光线飞向开阔天空
           }

           currentRayPos = rayOrigin + rayDirection * totalDistTraveled;
       }

       // ---------------------------------------------------------------------
       // 阶段 B: 辐射度计算与表面缓存求值
       // ---------------------------------------------------------------------
       float3 incomingRadiance = float3(0.0f, 0.0f, 0.0f);

       if (bHitSurface) {
           // 1. 计算击中断点法线
           float3 hitNormal = CalculateSDFNormal(currentRayPos, SDF_SURFACE_THRESHOLD);

           // 2. 空间查找与判定最佳 Mesh Card ID (此处以 0 号示例 Card 为例)
           uint hitCardId = 0;

           // 3. 直接通过 Surface Cache 提取多弹积累辐射度，零材质二次求值开销！
           incomingRadiance = ResolveSurfaceCacheRadiance(currentRayPos, hitNormal, hitCardId);
       } else {
           // 逃逸光线采样天空盒环境光 (Sky Light)
           incomingRadiance = float3(0.05f, 0.08f, 0.15f);
       }

       // ---------------------------------------------------------------------
       // 阶段 C: 朗伯积分与时域无限反弹累加
       // ---------------------------------------------------------------------
       float nDotL = saturate(dot(surfaceNormal, rayDirection));
       float3 evaluatedDiffuse = incomingRadiance * nDotL;

       // 读取上一帧该像素的历史结果执行时域马尔可夫平滑
       float4 prevRadiance = g_RWIndirectDiffuseOutput[pixelCoord];
       float3 accumulatedRadiance = lerp(prevRadiance.rgb, evaluatedDiffuse, g_TemporalConvergenceAlpha);

       // 写入当前帧最终漫反射间接光缓冲
       g_RWIndirectDiffuseOutput[pixelCoord] = float4(accumulatedRadiance, 1.0f);
   }

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章系统剖析了现代工业级渲染技术中代表最高复杂度的动态全局光照架构——**UE5 Lumen**，推导了其如何克服微多边形世界中海量几何与光线发散的物理矛盾：
1. **全动态 GI 的微架构危机**：阐明了在 Nanite 级别数十亿多边形场景中，直接构建与遍历全场景硬件 DXR BVH 会导致显存带宽彻底枯竭与缓存命中率断崖的物理本质；
2. **表面缓存 (Surface Cache) 的解耦革命**：解构了将三维复杂表面剖分为正交 Mesh Cards，并将其几何、材质、直接光与间接光全面烘焙至全局物理图集（Atlas）的机制，使光线命中后的辐射度获取由“昂贵材质递归着色”骤降为“单次 2D 纹理查表采样”；
3. **距离场空间加速 (Mesh SDF & Global SDF)**：深入推导了利用有向距离场进行安全球体步进（Sphere Tracing）的数学原理，证明了其在空旷空间单步跨越大距离、逼近表面平滑收敛的极高求交效率，并阐释了基于连续 3D 剪裁图（Clipmaps）无缝覆盖数百米宏大场景的实现方案；
4. **多级混合光线遍历流水线**：解析了优先执行极低开销的 Hi-Z 屏幕追踪（Screen Tracing）、穿透失效移交 SDF 软件追踪、并以 Nanite 极简代理网格兜底 DXR 硬件光追的无缝状态机；
5. **无限反弹递推与时空降噪**：揭示了将上一帧 Surface Cache 作为下一帧光线命中采样的时域马尔可夫链递推机制，以接近零的额外开销达成物理无限次光照反弹，并依托双向重投影与引导双边滤波彻底消除低采样率蒙特卡洛方差。

至此，我们已经完整遍历了现代工业渲染管线从底层硬件微架构、数学基础、光栅化、着色器编译、物理材质、阴影加速、全局光照、后处理重构、显式 API 到虚拟化几何与动态 GI 的全部技术拓扑。
在全书的最后一章（**Chapter 45: 工业级 GPU 性能分析与调优：RenderDoc 抓帧、NVIDIA Nsight / AMD RGP 瓶颈定位与 Roofline 模型实战**）中，我们将立足于工程实践的终极终点：如何使用工业级分析器（RenderDoc、Nsight Graphics、RGP）对前述所有高复杂度渲染管线进行精确抓帧、指标采集、硬件单元停顿诊断，并结合 Roofline 模型锁定计算受限与显存带宽墙的终极性能优化闭环。
