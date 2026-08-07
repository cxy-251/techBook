第028章：BRDF 与材质系统
=======================

核心知识点
----------

BRDF 描述同一表面点的入射光如何分布到观察方向
   输入通常是入射方向 ``L``、观察方向 ``V``、法线 ``N`` 和材质参数，输出用于缩放入射辐射亮度。直接光最小结构可理解为 ``Li × BRDF × max(N·L,0) × visibility``，材质外观差异最终都要回到 BRDF 参数和这条能量路径。

能量守恒是 PBR 材质稳定性的基础
   非自发光表面的反射能量不能无限超过入射能量。Lambert 漫反射常使用 ``albedo / π``，微表面镜面通过 D/G/F 项分配能量。实现中不必每像素做完整积分，但 diffuse、specular、metallic、clearcoat 等分量必须有清晰的能量边界。

Lambert、Cook-Torrance、GGX 与 Disney 代表不同层级的材质表达
   Lambert 只描述宽漫反射；Cook-Torrance 用微表面框架描述镜面；GGX 常作为 NDF，决定粗糙表面的高光尾部；Disney 风格参数把 metallic、roughness、clearcoat、sheen、anisotropy 等组织成面向材质制作的编辑语言。

材质系统是资产语义到 GPU 资源的映射层
   Material 不只是纹理列表，它需要组织 baseColor、roughness、metallic、normal、emissive、clearcoat、factor、texture slot、flags、variant key 与 pass 需求。资产格式、导入器、运行时 buffer、descriptor 和 shader 必须共享同一套字段语义。

颜色贴图与数据贴图必须区别处理
   Base color 与 emissive 通常按 sRGB 存储并在线性空间参与光照；normal、roughness、metallic、AO 等属于线性数据。错误的 sRGB 解码会直接改变 roughness、高光形状和法线方向，不能靠 tone mapping 修复。

通道打包减少采样，但把资产约定绑在一起
   Roughness、metallic、AO、mask 可共享一张纹理的不同通道，从而减少 texture fetch 与 descriptor 数量。代价是它们共享分辨率、mip、压缩格式和生命周期，因此通道顺序和颜色空间必须在资产规范中固定。

Shader variant 应只承载真正改变代码或资源路径的条件
   Normal map、alpha mode、clearcoat、skinning、deferred/forward 等可能改变代码结构或绑定布局，适合进入 variant；颜色、roughness factor、normal strength 等普通数值应留在 uniform/texture。把实例数据放进 variant key 会导致 pipeline 数量爆炸。

Metal/Roughness 与 Specular/Glossiness 是两套参数化，不是两套完全不同的物理模型
   Metal/Roughness 使用 ``baseColor + metallic + roughness``，非金属通常使用低灰色 ``F0``，金属把 baseColor 解释为有色镜面反射。Specular/Glossiness 直接提供 diffuse、RGB specular/F0 与 glossiness，表达自由度更高，但转换、校验和资产管理成本也更高。

引擎内部最好使用统一 canonical material representation
   多种外部格式应在导入阶段转换到内部稳定语义，避免每个 shader 同时理解多套资产工作流。转换时要明确 F0、metallic、roughness/glossiness、颜色空间、贴图通道和信息损失。

关键路径
--------

材质从资产进入 shader：

::

   DCC / glTF / 自有材质描述
   → 导入器解析 factor、texture slot、颜色空间
   → 转换到 canonical material
   → 生成 material flags / variant key
   → 上传 constant/storage buffer 与纹理
   → pass 选择实际需要的资源
   → shader 采样 baseColor、normal、roughness、metallic 等
   → 计算 diffuse / specular BRDF
   → direct light + IBL
   → 输出最终材质结果

PBR 材质错误排查：

::

   先固定白光、统一环境和曝光
   → 输出 baseColor
   → 输出 metallic / roughness / F0
   → 检查颜色空间和通道打包
   → 关闭 normal map 验证基础 BRDF
   → 检查 variant 与资源绑定
   → 再检查 IBL、LUT 和最终 tone mapping

概念辨析
--------

* **BRDF 与材质系统**：BRDF 定义参数如何变成反射；材质系统负责这些参数如何从资产稳定地到达 shader。
* **Lambert 与 Cook-Torrance**：前者主要描述漫反射，后者主要提供微表面镜面框架，现代 PBR 常把二者组合使用。
* **GGX 与完整 BRDF**：GGX 通常是微表面法线分布 D 项，不等于完整 Cook-Torrance 模型。
* **Metallic 与 specular F0**：metallic 是材质工作流中的混合参数；F0 是正入射镜面反射率，两者概念不同但在 metallic 工作流中有固定映射关系。
* **Roughness 与 glossiness**：二者通常方向相反，常见近似是 ``glossiness = 1 - roughness``，具体微表面参数映射仍需和 BRDF/IBL 保持一致。
* **Texture packing 与 material semantics**：打包只改变存储和采样组织，不改变通道本身的物理含义。
* **Variant 与 material instance**：variant 描述代码/资源路径，material instance 描述同一路径下的具体数据，不应混为一体。

本章结论
--------

稳定的 PBR 材质系统应先统一 BRDF 语义，再统一资产参数、颜色空间、通道打包和运行时资源布局。材质外观异常时，先判断数据是否按正确语义进入 shader，再判断 BRDF；跨工作流转换时重点检查 F0、metallic 和 roughness/glossiness；工程规模扩大后，则用 canonical material、pass 裁剪和受控 variant 把视觉表达与 GPU 成本同时收束。