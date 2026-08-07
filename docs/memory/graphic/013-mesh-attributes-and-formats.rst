第013章：网格属性与格式
=======================

核心知识点
----------

顶点属性是 buffer 与 shader 的输入合同
   一次 draw 通过 input layout 规定 attribute 的语义、格式、stride、offset 和 binding。``POSITION``、``NORMAL``、``TANGENT``、``TEXCOORD``、``COLOR``、``JOINTS``、``WEIGHTS`` 与自定义数据分别进入位置、光照、采样、蒙皮或变体路径；声明、上传和 shader 解码必须一致。

属性应按用途、空间和变化频率组织
   Position 直接影响轮廓和 bounds，normal/tangent 影响光照，UV 影响采样，joint/weight 影响变形，离散 material id 不应被普通插值。数据属于 per-vertex、per-instance、per-material、per-draw 还是 per-frame，决定它应放在哪类 buffer 中。

文件格式与运行时布局不是同一层
   OBJ 适合简单静态几何交换，FBX 适合 DCC 层级、骨架和动画输入，glTF 适合接近运行时的场景与 buffer 传输，引擎内部格式保存已经校验和平台化的数据。外部格式中的 accessor 或属性语义不等于最终 GPU buffer 必须保持原布局。

作者格式应在离线管线中冻结为运行时数据
   DCC 文件保留创作信息，导入器负责统一单位、轴向、三角化、法线、切线、材质、骨骼和动画，再生成平台 profile 下的压缩 buffer。运行时不应重复承担作者格式的复杂解释和不确定性。

属性压缩必须绑定误差预算
   Position 可相对局部 bounds 量化，normal/tangent 可使用 normalized 或 octahedral encoding，UV/color/weight 可按范围压缩，index 可使用 16-bit、重排和专用编码。每类误差会进入不同画面路径，不能只用文件体积评价压缩结果。

索引顺序同时影响缓存、带宽和 overdraw
   Post-transform cache optimization 减少重复 vertex shader 执行，vertex fetch reorder 改善属性读取局部性，triangle order 可影响 overdraw。传输压缩还要同时记录解码时间、峰值内存、最终 GPU buffer 大小和首帧可见时间。

自定义属性必须成为正式工程契约
   每个 custom attribute 至少要定义语义名、类型、范围、变化频率、插值方式和缺省值。离散 region id 应使用 flat 语义、primitive/material 数据或边界拆点；实例变体不应在每个顶点重复存储。

跨平台管线需要版本、校验和 fallback
   缓存 key 应覆盖源资产、导入器版本、平台 profile、压缩设置和依赖资源。构建阶段应验证缺失属性、NaN、权重归一化、索引越界、UV/normal/tangent 合法性，并为不支持的格式或扩展提供可解释 fallback。

关键路径
--------

资产到 shader：

::

   DCC 原生文件、FBX、OBJ 或 glTF
   → 导入为引擎中间表示
   → 统一单位、坐标系、三角化和材质语义
   → 校验 position、normal、tangent、UV、skin 与 custom data
   → 按平台 profile 量化、压缩、重排
   → 生成 vertex/index/instance/material buffer
   → 配置 input layout 与 shader 语义
   → draw call 读取并在画面中验证

属性错误定位：

::

   轮廓或位置错误
   → 检查 position、index、transform 与 skinning

   光照或 normal map 错误
   → 检查 normal、tangent、handedness、空间与解码

   纹理错位或拉伸
   → 检查 UV channel、插值、sampler 与 mipmap

   动画拉扯
   → 检查 joint index、weight 精度、归一化和矩阵顺序

   实例或材质变体错误
   → 检查 custom attribute 的频率、flat 语义与 buffer binding

压缩验收：

::

   固定未压缩视觉与性能基线
   → 分别压缩 position、direction、UV、weight
   → 对每类属性做画面和动画回归
   → 执行 index/vertex/triangle reorder
   → 加入传输压缩并记录解码与峰值内存
   → 生成各平台最终 profile 与 fallback

概念辨析
--------

* **属性语义与存储格式**：语义说明数据表示什么；格式说明它如何编码。相同 normal 语义可以使用 float、snorm 或压缩编码。
* **资产格式与内部格式**：资产格式强调工具交换或传输；内部格式强调当前引擎和平台的直接加载、校验与渲染效率。
* **OBJ、FBX 与 glTF**：OBJ 表达简单静态几何，FBX 承载宽泛 DCC 数据，glTF 用明确 accessor 和 buffer 结构服务运行时传输；三者不是简单的质量高低关系。
* **Per-vertex 与 per-instance**：前者随网格顶点变化并参与顶点读取；后者随对象实例变化，多个实例共享同一 mesh 时更节省带宽。
* **Quantization 与传输压缩**：quantization 减少属性位宽并改变最终精度；传输压缩主要减少文件或网络体积，解码后可能仍恢复为较宽 buffer。
* **连续属性与离散属性**：UV、normal、color 通常允许插值；material id、region id、对象索引等离散值需要 flat、整数或独立资源路径。
* **缺失属性与可重建属性**：normal、tangent 有时可由几何和 UV 重建；重建规则必须与烘焙和运行时约定一致，否则显式存储反而更稳定。

本章结论
--------

网格格式、属性语义和 GPU 布局应由同一条离线资产管线连接。先确定 shader 真正需要的数据及其变化频率，再统一外部格式的单位和语义，完成属性校验、压缩和缓存优化，最后用运行时绑定与画面证据验收；稳定的 mesh 系统依赖明确合同，而不是依赖某一种文件格式自动解决所有问题。