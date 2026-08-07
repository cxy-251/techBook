第049章：Portal 与 Cell 剔除
==========================

核心知识点
----------

Portal culling 把建筑结构变成可见性约束
   Cell 对应房间、走廊、楼梯间等被稳定墙体包围的空间；portal 对应门洞、窗洞、走廊口等可见开口。运行时从 camera cell 出发，只沿可见 portal 扩展到相邻 cell。

Portal graph 的边不仅有拓扑，还带几何
   普通邻接图只说明两个 cell 相连；portal graph 还保存 portal polygon。相机视线必须通过这个多边形才能传播到下一 cell，因此每跨过一个 portal 都能进一步缩窄可见体。

Camera cell 是遍历起点
   每帧先根据 camera position 定位当前 cell，初始可见体是 camera frustum。Camera cell 错误会让整条 traversal 从根上出错，因此点包含、边界位置和 previous-cell fallback 都要稳定。

Child volume 是 portal traversal 的核心
   对可见 portal，用相机位置与 portal 边界生成侧向裁剪平面，再与当前 volume 求交，得到更窄的 child volume。经过多个门洞后，可见体可能收缩成很小的角锥，远处大量对象因此被 bounds test 排除。

Cell 与 portal 的粒度必须贴合真实遮挡边界
   Cell 过粗会让大量无关房间同时进入候选；过细会增加 graph、遍历、编辑与 streaming 管理成本。Portal polygon 过大会过度保守，过小会让门边斜视时出现漏绘。

PVS 是离线潜在可见上界，实时 traversal 是当前精确子集
   Potentially Visible Set 可为每个 cell 预存可能可见的其它 cell，用于限制大型关卡候选；运行时再结合相机方向、portal clipping 和门状态收窄。PVS 不能替代动态门和当前视角判断。

对象归属必须处理跨 cell 情况
   完全位于一个房间内的静态对象可以单 cell 归属；角色、门板、粒子或大型动态物体可能同时覆盖多个 cell/portal 邻域，应加入多个动态集合并在 visible-object 收集时按 object id 去重。

动态门状态直接改变 graph 可遍历性
   门关闭时 portal 可以标为 closed；半开门可以实时收缩 portal polygon，也可以保留较大保守开口，把精确遮挡交给后续 depth/occlusion。前者精确，后者更稳定且维护成本低。

Portal culling 应与 frustum、occlusion、LOD、streaming 串联
   Frustum 过滤视锥外对象；portal 过滤墙体拓扑不可达 cell；occlusion/HZB 过滤当前深度后方对象；LOD 决定细节；streaming 决定资源是否预加载。它们回答不同问题，不能互相替代。

Streaming 可复用 portal 信息，但要比绘制更保守
   当前帧 draw 只需要真实可能可见的 cell；资源系统还应预加载玩家即将到达或即将打开的邻接 cell。否则 portal culling 虽正确，进入新房间时仍可能出现资源来不及加载。

Camera、shadow、reflection visibility 应分开
   Portal graph 可以复用，但阴影和反射不是从主相机视点观察。Shadow pass 应从光源视角重新判断，reflection/probe pass 也要使用自己的视点和裁剪体，不能直接复用 camera visible list。

性能收益来自减少 draw-list 构建和后续 GPU 工作
   评估时既要看 CPU traversal、portal tests、object bounds tests、draw-list build，也要看 GPU vertex invocation、fragment cost、overdraw 和 pass time。小场景中 portal graph 本身可能比节省的工作更贵。

关键路径
--------

Portal traversal：

::

   camera position
   → locate camera cell
   → initial camera frustum
   → visit current cell
   → collect objects intersecting current volume
   → test portal open state
   → portal polygon intersects volume
   → camera + portal edges 生成 child clipping planes
   → child volume
   → visit adjacent cell
   → visible cells / objects
   → render-list builder

动态门与对象：

::

   door / portal state update
   → version / open flag / optional polygon update
   → invalid previous visibility cache
   → dynamic object bounds update
   → multi-cell membership
   → portal traversal
   → object-id deduplication

对象消失排查：

::

   camera cell
   → 当前 cell portal 列表
   → portal open state
   → portal polygon 与真实开口
   → 每层 child volume
   → object bounds
   → dynamic multi-cell membership
   → 最后检查 occlusion / LOD / streaming / shader pass

概念辨析
--------

* **Cell 与 spatial chunk**：cell 主要按室内遮挡拓扑划分；chunk 更多服务世界分块、streaming 或一般空间索引，两者可以重合也可以独立。
* **Portal graph 与普通邻接图**：portal graph 的边带开口多边形和动态状态，能约束视线传播范围。
* **Portal culling 与 frustum culling**：frustum 使用相机六平面；portal 在室内拓扑上继续把可见体裁得更窄。
* **Portal culling 与 occlusion**：portal 使用建筑连接关系；occlusion 使用当前 frame 的 depth 证据。门打开后仍可能被物体遮挡，因此二者可串联。
* **PVS 与实时 traversal**：PVS 是静态潜在集合上界，实时 traversal 负责当前相机和动态 portal 状态。
* **Draw visibility 与 streaming visibility**：绘制集合可以严格，预加载集合应更保守以覆盖即将进入的空间。
* **Closed portal 与 occluded room**：closed portal 是拓扑不可达；occluded room 是当前图像空间被遮挡，语义不同。

本章结论
--------

Portal 与 Cell 剔除应按“camera cell—portal graph—portal polygon—child volume—visible cell/object”理解。它最适合墙体、门洞和走廊提供稳定结构遮挡的大型室内场景。正确性先保证 cell 划分、portal 开口和动态门状态，性能再用 traversal time、visible cell、draw call 与 overdraw 验证。遇到对象闪烁时应先查拓扑和裁剪体，再查后续 occlusion 或 streaming。