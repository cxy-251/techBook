第064章：Hair、Fur 与 Cloth 渲染
===============================

核心知识点
----------

Hair、Fur、Cloth 的难点来自微结构、透明覆盖和动态形变同时存在
   发丝和短毛包含大量子像素细几何，布料又依赖褶皱、纤维方向与轮廓变化。它们会同时放大 visibility、shadow、lighting、composition、simulation 和 temporal stability 成本。

几何表达必须匹配观察距离
   Strand 最适合近景高质量毛发；Ribbon 把曲线展开为窄带；Shell/Fins 适合短皮毛；Cards 用少量 alpha 面片表达一簇发束；Cloth mesh 负责大面积布料形变。距离越远，越应该从真实纤维转向聚簇、card 和 impostor。

Strand 管线的成本不只来自几何数量
   Render strand 数量、segment、width、guide 插值、visibility、shadow density 和 lighting sample 会共同增加预算。远景仍保留近景 strand 数量时，大量子像素片段几乎没有视觉收益。

Hair 光照具有明显各向异性
   高光主要沿发丝切线方向变化，常需要多 lobe、吸收、transmission 和 tangent 信息。简单各向同性 PBR 会让头发像塑料表面，缺少沿发束移动的高光层次。

Cloth 识别依赖 sheen、roughness 与纤维方向
   布料主体仍可走常规 mesh/PBR，但天鹅绒、绒面等材质需要额外 sheen 或各向异性响应。近景还需 normal、thickness、微阴影与褶皱支撑材质层次。

透明与 coverage 是毛发稳定性的核心
   Alpha test 成本低但边缘容易闪烁；alpha blend 保留柔边但顺序依赖；alpha-to-coverage、weighted OIT、PPLL 等方案在质量、内存、带宽和噪声之间取舍。透明方案必须与 TAA/MSAA 和目标平台一起评估。

自遮挡决定发束和皮毛是否有体积感
   Voxel density、deep opacity、低分辨率 shadow/transmittance 等数据用来表达纤维之间的遮挡与透射。缺少自遮挡时，毛发会像一层贴图；分辨率过低时，内部层次会变成大块暗影。

Simulation 与 Render LOD 应解耦
   Hair/cloth 的骨骼、guide、碰撞、风场和约束不一定要与最终渲染细节保持同一等级。可以降低 guide 数量和模拟频率，同时保留更高 render LOD；也可以保持稳定模拟而把远景直接切到 cards/impostor。

Motion Vector 必须使用模拟后的真实位置
   头发和布料的 TAA/temporal upscaling 依赖上一帧与当前帧最终变形后位置。若 velocity 仍使用骨骼前或 simulation 前位置，会出现拖影、边缘漂移和 LOD 切换残影。

Cluster Culling 用于减少不可见纤维和布片工作
   Groom group、hair cluster、fur tile、cloth patch 可以建立 bounds，再按 frustum、occlusion、screen size 过滤。粒度过粗会保留太多无效工作，过细则让 culling metadata 本身变贵。

Compute Skinning 能把动态几何更新留在 GPU
   Skeleton、guide interpolation、cloth vertex update 可以写入 GPU buffer，再由 visibility/lighting 读取。收益是减少 CPU 逐顶点上传，代价是增加 compute pass、barrier 和跨阶段 buffer 生命周期管理。

完整成本应拆成多阶段预算
   可近似看成 ``simulation + buffer update + visibility + shadow/transmittance + lighting + composition``。只有先找出哪一段超预算，LOD 与材质降级才有明确目标。

关键路径
--------

近景角色：

::

   skeleton pose
   → hair/cloth simulation
   → guide / vertex interpolation
   → dynamic geometry buffer
   → visibility / coverage
   → shadow density / transmittance
   → anisotropic lighting / cloth BRDF
   → transparent composition
   → temporal/post processing

LOD：

::

   screen size / distance
   → strand count / segment count
   → simulation LOD
   → shadow quality
   → material lobe count
   → cards / impostor fallback
   → cluster culling

问题排查：

::

   geometry / strand count
   → simulation output buffer
   → visibility / coverage mask
   → shadow density
   → lighting inputs
   → motion vector
   → composition / TAA

概念辨析
--------

* **Guide Strand 与 Render Strand**：guide 主要参与模拟，render strand 用于最终显示，二者通过插值关联。
* **Strand 与 Card**：strand 保留单根纤维方向和体积，card 用一张面片近似一簇纤维，适合更远距离。
* **Alpha Blend 与 OIT**：普通 alpha blend 强依赖顺序，OIT 通过额外存储或近似降低顺序问题，但成本更高。
* **Simulation LOD 与 Render LOD**：一个控制物理状态精度，一个控制几何/材质显示精度，可以独立降级。
* **Hair Shadow 与普通 Mesh Shadow**：hair 更依赖密度与透射表达，单纯三角形硬阴影常无法表现发束内部层次。
* **Compute Skinning 与 CPU Skinning**：前者减少 CPU 上传并提高批量性，后者更容易调试但大规模角色成本更高。
* **远景真实感与真实纤维**：远景只需保留轮廓、暗部和高光趋势，不需要继续维持完整 strand 级物理表达。

本章结论
--------

Hair、Fur、Cloth 应按“表达模型—动态更新—coverage—self-shadow—lighting—composition—LOD”理解。近景可使用 strands、多 lobe 光照与高质量遮挡，中景应减少 strand/segment 并简化 shadow/material，远景切到 cards 或 impostor。性能优化先用 profiler 拆出 simulation、visibility、shadow、lighting、composition 哪一段超预算，再针对对应资源降级；不要把所有成本都归到“头发 shader”或“布料模拟”一个名字下。