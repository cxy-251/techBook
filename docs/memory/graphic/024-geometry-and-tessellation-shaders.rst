第024章：Geometry 与 Tessellation Shader
=======================================

核心知识点
----------

Geometry Shader 与 Tessellation 都位于光栅化之前
   Geometry Shader 以已经装配好的 primitive 为输入，能够发射零个或多个新 primitive；Tessellation 以 patch 为输入，通过 tessellation factor 和参数域求值生成更密的几何。两者都能改变进入 rasterizer 的 primitive 数量，但天然粒度和适用问题不同。

Geometry Shader 适合少量 per-primitive 工作
   调试法线、layered rendering、少量 billboard/line 扩增和邻接相关可视化都符合它的输入模型。高倍率扩增会带来可变输出、primitive buffering 和后续 raster/fragment 成本，通常不适合作为大量草叶、毛发或复杂地形的主生成路径。

Geometry Shader 的成本要看输入和输出两端
   一个 GS invocation 对应一个输入 primitive，输出顶点数和 primitive 数可能变化。性能分析应同时观察 GS invocation、generated primitive、输出顶点、rasterized primitive 和 fragment cost，而不能只看 shader 自身指令。

Tessellation 把低面数 patch 转成视距相关的高密度曲面
   Tessellation Control/Hull Shader 负责每个 patch 的控制点与 outer/inner factor；固定功能 tessellator 根据 factor 生成参数域坐标；Tessellation Evaluation/Domain Shader 根据参数坐标求值真实 position、normal、UV 并可采样 height map 做 displacement。

Tessellation factor 是几何密度的主要控制量
   Factor 应由相机距离、屏幕误差、曲率、位移幅度或 pass 需求决定。只按世界距离选择级别会在窄 FOV、大模型和斜视角下产生浪费；相邻 patch 的共享边 factor 还要保持兼容，避免裂缝和跳变。

Displacement 与 normal map 的作用层级不同
   Normal map 只改变着色法线，不改变真实轮廓和遮挡；tessellation displacement 会真正移动生成顶点，影响 silhouette、depth、shadow 与碰撞视觉。Color、depth、shadow 等 pass 必须使用一致或明确降级的位移路径。

启用 Tessellation 首先是 pipeline 输入合同变化
   普通 triangle list 直接进入装配；tessellation path 要使用 patch topology，并绑定 TCS/TES 或 HS/DS，同时让 patch control point count 与 mesh、shader 输入一致。资源还必须绑定到实际读取它们的 stage。

现代几何路径应按任务粒度选择
   Primitive 级少量扩增适合 Geometry Shader；patch 级曲面细分适合 Tessellation；meshlet/workgroup 级 culling 与 primitive 输出适合 Mesh Shader；大规模可见集、LOD 列表和 indirect 参数准备适合 Compute preprocessing。

关键路径
--------

Tessellation 地形路径：

::

   低面数 terrain control points
   → patch topology 输入
   → Vertex Shader 传递控制点
   → TCS/HS 计算 outer/inner tess factor
   → fixed-function tessellator 生成参数域坐标
   → TES/DS 插值控制点
   → 采样 height map 做 displacement
   → 输出 position/normal/UV
   → primitive assembly
   → rasterization

Geometry Shader 调试路径：

::

   vertex/domain 输出
   → primitive assembly
   → GS 一次读取完整 point/line/triangle
   → 计算中心、法线或 layer
   → 发射少量 line/triangle primitive
   → rasterization
   → debug target

路径选择：

::

   明确视觉目标
   → 判断天然输入粒度是 primitive、patch、meshlet 还是 buffer element
   → 估算最大输出规模
   → 查询目标 API feature 与 limit
   → 设计 fallback
   → 用 generated primitive、shader time、raster 与 fragment 指标验证

概念辨析
--------

* **Geometry Shader 与 Vertex Shader**：Vertex Shader 通常按顶点执行；Geometry Shader 按完整 primitive 执行，并能改变 primitive 输出数量。
* **TCS/HS 与 TES/DS**：前者主要决定 patch 常量和细分密度；后者对 tessellator 生成的参数点求值为真实顶点。
* **Patch 与 triangle**：patch 是 tessellation 的控制点集合，不是直接光栅化三角形；经过 tessellator 和 evaluation 后才形成最终 primitive。
* **Tessellation 与 LOD**：tessellation 是几何生成机制；LOD 是决定当前需要多少复杂度的策略，二者可结合但不是同一概念。
* **Displacement 与 normal mapping**：displacement 改真实位置和轮廓；normal map 只改变光照解释。
* **Geometry amplification 与 instancing**：GS 在每个输入 primitive 后生成更多图元；instancing 复用已有 mesh 多次绘制，两者成本和组织方式不同。
* **Mesh Shader 与 Geometry Shader**：Mesh Shader 以 workgroup/meshlet 组织自定义顶点和 primitive 输出，更适合 GPU-driven；GS 是传统 primitive 后处理阶段。
* **Compute preprocessing 与 graphics stage**：compute 先准备 buffer、visible list、LOD 或 indirect args；graphics stage 再按稳定 pipeline 消费这些结果。

本章结论
--------

Geometry Shader 与 Tessellation 的选择应从输入粒度和输出规模推导。Primitive 级少量扩增或调试可使用 GS，patch 级视距细分和真实 displacement 使用 Tessellation；大规模 GPU-driven 组织则更适合 mesh shader 或 compute preprocessing。无论哪条路径，都要同时验证 pipeline topology、stage 资源绑定、pass 一致性以及新增 primitive 对后续 raster/fragment 成本的影响。