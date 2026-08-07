第011章：网格拓扑与数据结构
===========================

核心知识点
----------

网格数据分为几何拓扑与渲染表示
   几何层描述顶点、边、面及其邻接关系，服务导入、编辑、简化、法线生成和拓扑修复；渲染层把结果压成 vertex buffer、index buffer、submesh 和 instance data，服务 GPU 连续读取与 draw command。两层使用同一资产，但查询目标完全不同。

边引用次数是拓扑审查的第一证据
   三角网格中，普通内部边通常被两个面引用，边界边被一个面引用；一条边被三个或更多面引用属于 non-manifold edge。孔洞可以是设计边界，也可以是缺面，必须结合边界环是否闭合和资产语义判断。

流形条件决定几何算法能否稳定遍历
   法线平滑、边折叠、细分、体积判断和碰撞代理依赖可解释的一环邻域。两个独立表面只在一个顶点相接、边被多面共享或 winding 混乱，都会破坏邻域顺序和内外侧判断。

Render vertex 不是单纯的空间位置
   GPU 顶点是一组同时被 shader 读取的属性。相同 position 若具有不同 normal、tangent、UV、material boundary、joint 或 weight，就必须拆成多个 render vertex。顶点数量高于几何位置数量通常是合法属性拆分，不能按 position 无条件焊接。

Half-edge 适合处理阶段而非最终绘制
   半边结构通过 ``next``、``twin``、``face`` 和 ``vertex`` 表达有向边，可高效遍历面环、顶点一环和边界环，适合编辑、拓扑验证与简化。最终运行时通常只保留连续 buffer 和必要元数据，避免让 GPU 渲染路径背负复杂指针结构。

Buffer 布局应服从访问模式
   Interleaved layout 把一个顶点的大多数属性连续存放，适合普通 geometry pass；separate streams 把 position、normal、UV 等拆开，适合 depth-only pass、动态变形或不同更新频率。16-bit 或 32-bit index 的选择取决于 render vertex 数量和平台支持。

网格优化必须在属性正确之后执行
   顶点去重应比较完整属性键，切线生成应与 UV island 和 normal split 对齐；index reorder 改善 post-transform cache，vertex reorder 改善 fetch 局部性，量化压缩降低存储和带宽。拓扑错误未修复前进行压缩和重排会隐藏问题并扩大诊断成本。

运行时组织由更新频率和渲染状态决定
   Static mesh、skinned mesh、dynamic stream 由顶点是否随帧变化决定；submesh 由材质和 pipeline state 决定；instance buffer 让多个对象共享同一 mesh；LOD、chunk、meshlet 或 cluster 用于规模、streaming 与 GPU-driven rendering。

关键路径
--------

DCC 网格进入运行时：

::

   DCC position、polygon、attribute 与 material
   → 构建边表或 half-edge
   → 检查 boundary、hole、winding、non-manifold 与退化面
   → 按 normal、UV、tangent、material、skin 属性生成 render vertex
   → 生成 vertex/index buffer
   → 执行 cache reorder、量化和压缩
   → 切分 submesh、LOD 与 streaming chunk
   → 上传 GPU 并组织 draw 或 indirect draw

区分属性拆分与拓扑错误：

::

   按几何 position 聚类候选顶点
   → 比较其 polygon 邻接与边引用次数
   → 边被三个以上面引用时标记拓扑错误
   → 比较 normal、UV、tangent、material、joint、weight
   → 属性不同且符合 seam 或硬边语义时保留拆分
   → 属性无差异的重复记录才进入焊接候选

运行时组织决策：

::

   判断顶点是否动态变化
   → 选择 static、skinned 或 dynamic buffer
   → 按材质和 pipeline state 划分 submesh
   → 判断同一 mesh 是否大量重复并配置 instance data
   → 按可见规模配置 LOD、chunk 或 cluster
   → 用 draw count、vertex count、上传字节和 GPU 时间验证

概念辨析
--------

* **几何顶点与渲染顶点**：几何顶点主要表达空间连接；渲染顶点是完整 shader 输入记录，同一位置可对应多个渲染顶点。
* **边界与孔洞**：边界是只被一个面使用的边形成的环或链；孔洞是边界环围出的缺面区域，可属于设计或错误。
* **流形与封闭网格**：流形描述局部邻域可解释；封闭网格还要求不存在开放边界。开放但流形的曲面仍可正常渲染。
* **Half-edge 与 index buffer**：half-edge 显式保存邻接并适合修改；index buffer 隐式表达三角形连接并适合 GPU 顺序读取。
* **AoS 与 SoA**：AoS 强调单个顶点属性邻近；SoA 强调同类属性连续。应按 pass 读取和更新频率选择，而非固定套用。
* **Submesh 与 instance**：submesh 是同一 mesh 内按材质或状态划分的索引范围；instance 是共享 mesh 的多个对象变换和变体数据。
* **拓扑优化与缓存优化**：拓扑操作可能改变连接关系；索引和顶点重排通常不改变几何语义，只改变访问顺序。

本章结论
--------

网格处理必须把可编辑拓扑、完整顶点属性和 GPU 连续数据分层管理。导入时先用邻接、边界和流形条件验证曲面，再按 seam、硬边、材质与动画属性生成 render vertex，最后进行布局、重排、压缩、submesh 和实例化组织；只有这条顺序明确，顶点数量、接缝、draw call 与运行时成本才具有可解释性。