第139章：ML 材质与着色
=====================

核心知识点
----------

ML 进入材质系统后，首先改变的是材质资产的生产方式
   传统材质由扫描、手工贴图、程序节点和 shader graph 定义；ML 可以从照片、文本、草图、参考材质或已有贴图中生成、估计、补全或压缩材质表示。工程目标不是“生成好看的图”，而是生成可 relight、可缩放、可编辑、可导出的材质资产。

材质输出应尽量落到可解释 PBR/SVBRDF 通道
   Base color、normal、roughness、metallic、height、AO、anisotropy、subsurface 等通道能被现有 renderer 稳定消费。若模型只输出单张 shaded image，就已经混入光照、曝光和相机条件，无法作为稳定材质。

ML 在材质中常承担三种角色
   Generator 从低维条件生成材质；Estimator 从观测图像反推 PBR/SVBRDF 参数；Compressor 把高分辨率多通道材质压成 latent feature 与小型解码器。三者的输入证据、可控性与 runtime 成本不同。

模型先验既是能力也是风险
   文本“潮湿红砖”并没有直接给 roughness 或 normal，模型会根据训练数据猜测。工程上必须区分“由输入证据支持的通道”和“由训练先验补出的通道”，并在验证阶段对不确定结果加强检查。

离线资产生成通常比实时 Neural Material 更容易落地
   模型在 DCC/导入阶段生成普通 PBR 贴图，artist 修正后，runtime 仍走传统 shader。这样最容易接入现有 mip、compression、streaming、material cache 和平台路径。

实时 Neural Material 直接进入每帧 Shading
   Latent texture、network weight、feature decode 会增加 fragment/compute 的采样、矩阵计算、寄存器压力和临时资源。它只在显存节省、复杂外观压缩或传统 BRDF 成本足够高时有明确价值。

数据驱动 Shader 生成应优先输出参数、贴图或 Graph
   让模型直接生成任意 shader 源码会引入语义、性能和资源绑定不可控。更稳妥的路径是模型输出标准参数、mask 或材质图节点，再由固定 shader generator 生成目标平台代码。

Shader Graph 应保持 Artist 可读语义
   ``brick_mask``、``moss_blend``、``wetness``、``normal_strength`` 这类命名节点比匿名 latent 更适合生产。模型负责给出初值和结构，artist 可以局部 override，最终 graph 再编译到 renderer。

参数预测的核心困难是材质与光照去耦
   照片暗部可能来自 base color 也可能来自 shadow；亮斑可能来自 low roughness 也可能来自 exposure；纹理细节可能被误判成 normal。多光照观测、flash、已知几何和 loss 约束能减少歧义。

Texture Synthesis 要同时满足 Tileability 与尺度一致性
   可平铺材质不能只在中心区域好看。应做 3×3 tile 展开、mip 检查、斜视远景检查，确认 seam、重复周期、normal 高频和 roughness 统计在不同尺度都稳定。

BRDF Fitting 受目标材质模型的表达能力限制
   Metal/roughness PBR、Standard Surface、OpenPBR、layered BRDF 能表达的外观不同。模型即使拟合到复杂观测，也必须最终落入 renderer 能执行的参数空间。

材质管线应包含六个阶段
   Training/Data → Inference → Validation → Export → Artist Override → Runtime/Fallback。模型输出若缺少验证、导出和人工修正，只能算生成 demo，不能算生产资产。

导出包需要明确版本和通道契约
   Material package 应记录 model/version、channel semantics、color space、normal convention、roughness range、scale、tile mode、mip policy 与目标 shading model。这样 runtime 和不同 DCC 才能得到一致结果。

Artist Override 必须位于正式流程中
   ML 输出应允许修改 roughness、mask、normal strength、颜色、层混合等关键参数。人工修正不是“破坏模型结果”，而是把不稳定生成结果收束成可控资产。

泛化必须分维度评估
   Light stability、scale stability、material-category stability、input-distribution stability 和 platform stability 应分开检查。只在某个光照失败，优先查 reflectance decomposition；只在远景失败，优先查 mip/tile；只在低端平台失败，优先查格式和 shader cost。

Relighting 是判断材质真实性的重要测试
   在不同方向、强度和色温下重新打光，检查 base color 是否残留阴影、normal 是否方向正确、roughness 是否真的控制高光。单张原光照预览无法证明材质参数正确。

性能与画质必须一起比较
   对 neural texture/compression 要同时测显存减少、decode cost、occupancy、cache、mip/anisotropic sampling 和最终 frame time。节省存储但拖慢 shader 不是有效优化。

生成、扫描和手工材质没有绝对优劣
   扫描材质真实感高但采集成本大，手工材质控制力强但制作时间长，ML 生成速度快且可扩展但存在先验和泛化风险。最佳方案取决于 hero asset、开放世界、移动端或风格化项目的具体约束。

关键路径
--------

ML 材质资产：

::

   photos / text / reference material
   → model inference
   → PBR/SVBRDF maps or material graph
   → relight / tile / scale validation
   → artist override
   → export material package
   → runtime shader/material system
   → fallback asset

数据驱动 Shader：

::

   learned parameters / masks / graph
   → standard node schema
   → shader generator
   → target backend shader
   → bind textures/buffers
   → draw / shade
   → profile GPU cost

泛化检查：

::

   generated material
   → neutral light
   → grazing hard light
   → near/mid/far distance
   → different renderer/platform
   → inspect seams, roughness, normal, mip
   → compare artist/fallback version

概念辨析
--------

* **Shaded Image 与 Material Asset**：前者包含当前光照结果，后者保存可在新光照下重用的外观参数。
* **Generator 与 Estimator**：生成器从先验创造材质，估计器从观测证据反推材质参数。
* **Offline ML Material 与 Runtime Neural Material**：前者只改变资产生产，后者直接改变每帧 shader/inference 成本。
* **Shader Graph Generation 与 Shader Source Generation**：graph 保留结构和可控节点，直接源码更难约束语义与性能。
* **Realism 与 Controllability**：真实感高不代表容易编辑，生产资产通常需要同时满足二者。
* **Memory Saving 与 Performance Saving**：神经压缩减少显存不等于减少总 frame cost，解码可能增加计算和寄存器压力。

本章结论
--------

ML 材质系统应按“Evidence—Material Representation—Inference—Validation—Artist Control—Export—Runtime/Fallback”理解。真正可用的模型必须把不稳定输入收束为 renderer 能理解的稳定材质契约，在不同光照、尺度和平台下仍可验证，并允许人工修改和传统路径接管，而不是只在一张预览图上看起来真实。