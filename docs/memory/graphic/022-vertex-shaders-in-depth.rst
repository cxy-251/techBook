第022章：Vertex Shader 深入
==========================

核心知识点
----------

Vertex Shader 是 mesh 数据进入可编程图形管线的第一道核心变换
   它读取 vertex/instance attribute 与 uniform/constant/storage 数据，输出裁剪空间位置和供后续插值的 varyings。位置输出决定几何在哪里，varyings 决定 fragment shader 后续能得到哪些材质和几何信息。

输入布局与 shader 语义必须完全对齐
   Attribute location/semantic、format、stride、offset、step mode 与 buffer 实际字节布局共同定义 shader 读到的值。模型被拉伸、实例重叠、UV 乱跳等问题，首先应检查输入合同，而不是直接怀疑矩阵或光照。

坐标变换要沿完整空间链验证
   典型路径是 model → world → view → clip → NDC → viewport。Position 使用齐次坐标 ``w=1``，clip ``w`` 参与透视除法；近裁剪、深度范围、handedness 或矩阵顺序错误，会直接造成几何消失、翻转与深度异常。

法线变换和位置变换规则不同
   Position 接受平移；normal 表示方向。存在非等比缩放时，应使用 model 三阶部分的逆转置矩阵并重新归一化，否则法线会失去与表面的垂直关系，表现为高光和明暗方向错误。

Skinning 是典型顶点级状态变换
   每个顶点通过 joint index 与 joint weight 读取骨骼矩阵，并按权重组合得到当前姿态。稳定性依赖权重归一化、索引范围、inverse bind、矩阵空间和执行顺序一致。局部飞点和整块网格拉走通常都能从这些输入中定位。

Morph target 修改的是基础顶点属性
   Morph 常在 model space 中叠加 position、normal 或 tangent delta，再继续经过对象和相机变换。把 morph delta 错放到 world space 会破坏实例复用和动画语义，也容易让不同对象得到不同错误结果。

Instancing 复用 mesh，但仍会重复顶点执行
   同一 vertex buffer 可通过 instance transform、颜色、材质索引或风参数渲染多个对象。Instancing 主要减少 CPU 提交和资源绑定；GPU 仍按实例数执行顶点工作，所以 instance count、矩阵读取和顶点数量继续影响性能。

Varying 应只输出后续确实需要的数据
   UV、normal、world position、tangent、motion data 等都会跨阶段传递并参与插值。输出过宽会增加接口、寄存器和插值带宽；能由 depth、screen position 或常量重建的数据，应评估是否需要逐顶点传递。

Vertex Shader 优化要区分调用次数、带宽、ALU 与重复工作
   LOD、culling、meshlet 可减少 invocation；属性压缩和 separate stream 可降低 fetch；预计算 MVP、限制 bone influence 可降低 ALU；compute pre-skinning 可减少多个 pass 重复蒙皮。优化方向必须由 profiler 指标决定。

关键路径
--------

一个顶点的执行链：

::

   draw/index/instance 参数
   → vertex input layout 解码 attribute
   → 可选 morph
   → 可选 skinning
   → instance/model transform
   → world/view/projection
   → 输出 clip position
   → 输出 UV、normal、tangent 等 varyings
   → clipping 与 perspective divide
   → rasterization 插值
   → fragment shader 消费

顶点画面错误排查：

::

   检查 draw 与 index/instance 数量
   → 检查 attribute location、format、stride、offset
   → 输出未变换 position 验证资产数据
   → 逐段检查 world、view、clip、NDC
   → 检查 normal matrix
   → 单独关闭 morph/skinning/instancing
   → 再检查 varyings 与后续 shader

性能定位：

::

   记录 vertex count、instance count、VS invocation
   → 检查 vertex stride 与 attribute bandwidth
   → 检查 skinning、矩阵和解包 ALU
   → 检查 post-transform cache 与 index locality
   → 检查 depth/shadow/velocity/color 是否重复执行相同形变
   → 用 LOD、culling、压缩、预计算或 pre-skinning 对症处理

概念辨析
--------

* **Vertex fetch 与 Vertex Shader**：fetch 负责按布局读取和解码字节；shader 负责数学计算和输出，输入错误必须先分清发生在哪一层。
* **Clip space 与 screen space**：Vertex Shader 通常输出 clip space；screen space 要经过裁剪、透视除法和 viewport transform 才得到。
* **Position 与 normal**：position 是点，允许平移；normal 是方向，非等比缩放下需要逆转置变换。
* **Skinning 与 morph**：skinning 用骨骼矩阵变换顶点；morph 用属性 delta 改变基础形状，两者可以组合但顺序和空间必须统一。
* **Per-vertex 与 per-instance**：前者随 mesh 顶点变化；后者随对象实例变化。把实例常量重复写进每个顶点会浪费带宽。
* **Instancing 与减少 GPU 工作**：instancing 主要减少 CPU draw 提交，不自动减少顶点 invocation。
* **Varying 与 uniform**：varying 由顶点输出并在图元内部插值；uniform/constant 在一次 draw 或更大范围内保持统一，不参与光栅插值。
* **压缩与预计算**：压缩减少内存读取并增加解码 ALU；预计算减少 ALU 但可能增加更新和存储成本，应根据瓶颈取舍。

本章结论
--------

Vertex Shader 的稳定理解是“输入布局—局部形变—空间变换—裁剪位置—varying 输出”。正确性先检查 buffer 合同和空间链，再检查 skinning、morph、instancing 与法线；性能则分解为 invocation 数量、attribute 带宽、ALU、缓存和跨 pass 重复计算。只有这五类证据分开观察，顶点阶段的画面错误和性能瓶颈才不会混在一起。