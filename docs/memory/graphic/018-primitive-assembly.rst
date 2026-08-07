第018章：基元装配
=================

核心知识点
----------

基元装配决定顶点如何组成可处理图元
   Vertex Shader 输出仍是一组有顺序的顶点结果，primitive topology 决定它们如何被解释成 point、line、triangle 或 patch。Index buffer 决定访问顺序和顶点复用，topology 决定分组方式，winding 决定后续正反面判断。

Triangle list 是通用实时网格的主力表示
   Triangle list 每三个索引形成一个独立三角形，结构清晰，适合材质拆分、缓存优化、LOD 和工具链。Triangle strip 能减少规则连续几何的索引数量，但引入奇偶 winding、restart 和跨段维护问题。

索引同时影响图元数量、朝向与缓存复用
   同一 index buffer 在不同 topology 下会产生不同 primitive；同一组三角形换索引顺序会改变 winding 与 post-transform cache 局部性。缺面问题应先检查 topology、index 分组、front face 与 cull mode，再检查裁剪和深度。

非三角形高层几何最终要映射到可消费图元
   曲线可采样为 line 或带宽三角形，n-gon 通常在导入阶段三角化，sprite/billboard 可由 CPU quad、instancing 或点扩展生成，patch 则进入 tessellation。转换位置决定缓存能力、运行时灵活性与 GPU 成本。

Adjacency 与 patch 是特殊输入合同
   Adjacency topology 为 Geometry Shader 提供邻接顶点，适合轮廓和 shadow volume 等邻域算法，但增加索引和执行成本。Patch list 是 tessellation 的控制点输入，control point count、tess factor 和 domain 输出共同决定最终 primitive 数量。

跨平台应优先统一到稳定 topology
   Triangle fan 等拓扑并非所有 API/profile 都一致支持。跨平台资产管线通常应尽早转换为 indexed triangle list，减少 API 分支，并让后续重排、压缩、meshlet 和 LOD 工具使用统一输入。

Primitive 组织优化必须先判断瓶颈
   CPU submission-bound 更关注 submesh 合并、instancing、multi-draw 和 indirect draw；vertex-bound 更关注索引复用、cache reorder、LOD 与 meshlet culling；fragment-bound 则更需要关注 overdraw、材质和透明路径。

大场景需要从 mesh 升级到 chunk 与 meshlet 组织
   Chunk 提供 streaming、LOD 和粗粒度可见性边界；meshlet 把一个 mesh 拆成带局部 bounds 和小索引集的几何包，便于 GPU culling 与 GPU-driven draw。Primitive assembly 仍按筛选后的 topology 和 index range 消费结果。

关键路径
--------

Indexed triangle draw：

::

   draw command 指定 topology 与 index range
   → index buffer 给出顶点访问顺序
   → vertex fetch 与 Vertex Shader 得到顶点输出
   → 每三个索引按 triangle list 组成一个 primitive
   → 根据 winding 判断 front/back face
   → clipping 与 culling
   → rasterization

缺面排查：

::

   确认当前 topology
   → 检查 index count 与 primitive 分组
   → 检查 index 是否越界或引用错误顶点
   → 检查 winding 与 front-face 约定
   → 检查 cull mode
   → 再检查 clip position、depth 与材质 pass

海量几何组织：

::

   场景按 chunk 或对象组划分
   → mesh 构建 cache-friendly index 与 meshlet
   → CPU/GPU 做 frustum、LOD 或遮挡筛选
   → visible list 生成 multi-draw/indirect 参数
   → graphics pass 读取筛选后的 index range
   → primitive assembly
   → 用 primitive、VS invocation、draw 与 fragment 指标验证收益

概念辨析
--------

* **Index buffer 与 topology**：index buffer 给出访问序列；topology 给出如何把序列分组为 primitive。
* **Triangle list 与 triangle strip**：list 使用独立三元组，维护简单；strip 连续共享边，索引更紧凑但连接和 winding 更复杂。
* **Winding 与 culling**：winding 定义三角形朝向，cull mode 根据 front-face 约定决定是否舍弃；索引重排必须保留目标朝向。
* **Triangulation 与 primitive assembly**：triangulation 把高层面转换为三角形数据；primitive assembly 在 draw 时按 topology 解释这些数据。
* **Submesh 与 meshlet**：submesh 主要按材质或状态划分 draw range；meshlet 主要按小型几何包组织局部剔除和 GPU-driven 工作。
* **Multi-draw 与 indirect draw**：二者减少逐对象提交成本，但不会改变单个 draw 内 topology 的解释规则。
* **Primitive restart 与退化三角形**：二者都可连接多个 strip；restart 用特殊索引显式断开，退化三角形通过零面积图元过渡。

本章结论
--------

基元装配的核心是把“顶点流”变成“图元流”。正确性由 index、topology、winding 与 cull state 共同决定，性能则由索引复用、draw 组织和可见几何规模决定。小网格先用手工索引验证分组，大场景再用 chunk、meshlet、multi-draw 与 GPU culling 控制进入装配阶段的 primitive 数量。