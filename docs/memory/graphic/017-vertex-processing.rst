第017章：顶点处理
=================

核心知识点
----------

顶点阶段由输入装配、Vertex Shader 与固定功能后处理共同组成
   一个 vertex invocation 的真实输入由 vertex buffer、index buffer、instance buffer、uniform/storage buffer、vertex layout 与 draw 参数共同决定。Shader 只看到已经按 format、stride、offset 和 step mode 解码后的值，因此输入错误应先检查 buffer 合同，再检查 shader 数学。

顶点处理输出分为位置与 varyings
   ``clip position`` 决定几何是否能被裁剪、透视除法和 viewport 映射；UV、normal、tangent、world position、motion data 等 varyings 进入后续插值。位置链错误影响几何可见性，varying 错误通常表现为材质、光照或运动向量异常。

坐标链必须逐段验证
   典型路径为 ``model → skinned/morphed local → world → view → clip → NDC → viewport``。Clip space 中的 ``w`` 同时参与裁剪与 perspective divide；``w`` 符号、near/far、NDC z 范围或矩阵约定错误，会导致靠近相机消失、极端拉伸或深度异常。

跨 API 需要重新确认坐标约定
   OpenGL 传统 NDC z 范围与 Vulkan、Direct3D、Metal、WebGPU 常用范围不同，屏幕 y 方向和 viewport 处理也可能不同。Projection matrix、reverse-Z、viewport 和 depth state 必须属于同一套约定。

Vertex Shader 负责属性解包与顶点级形变
   压缩 position、normal、tangent、UV 等属性需要在 shader 中解码；skinning、morph 和 instancing 会修改顶点局部或世界状态。形变顺序错误会造成局部扭曲，normal/tangent 未同步会造成几何正确但光照错误。

实例化减少提交而不会消除顶点执行
   Instancing 让多个对象共享 mesh 和 pipeline，只把 transform、颜色或变体放进 instance data。CPU draw 数可以下降，但每个实例仍会执行相应顶点工作，因此 instance count、vertex count 和实例数据读取仍进入 GPU 成本。

顶点性能由执行次数、属性带宽、ALU 与缓存共同决定
   Attribute stride 越宽，输入带宽越高；skinning 和矩阵计算增加 ALU；索引局部性影响 post-transform cache；未被 culling/LOD 过滤的不可见几何会制造无效 invocation。优化动作必须绑定到对应指标。

重复形变跨多个 pass 会放大成本
   同一角色在 depth、shadow、velocity、color 等 pass 中重复做 skinning，会让相同计算多次执行。可以按瓶颈选择 compute 预处理 skinning、远景降低骨骼复杂度、减少影响数量或为轻量 pass 使用更低成本变体。

关键路径
--------

一个顶点进入屏幕：

::

   draw/index/instance 参数
   → vertex layout 解码属性
   → 可选 morph 与 skinning
   → instance/model transform
   → view transform
   → projection 得到 clip position
   → clipping
   → perspective divide 得到 NDC
   → viewport transform
   → primitive assembly

顶点错误排查：

::

   确认 draw、index count、instance count 与 input layout
   → 检查 position/normal/UV 实际解码值
   → 固定一个顶点记录 world、view、clip 数值
   → 检查 clip w、NDC z、handedness 与 near/far
   → NDC 正常后检查 viewport、scissor 与后续 cull/depth state

顶点性能定位：

::

   记录 index、vertex、instance 与 VS invocation 数量
   → 检查 vertex stride 与 attribute fetch
   → 检查 skinning、矩阵与解包 ALU
   → 对照唯一顶点数与 post-transform cache 复用
   → 检查 frustum culling、LOD 与无效实例
   → 按证据选择压缩、预计算、重排或减少工作量

概念辨析
--------

* **Vertex input 与 Vertex Shader**：前者决定从 buffer 读取什么、如何解码；后者决定读取后的数据如何被计算和输出。
* **Clip space 与 NDC**：clip space 保留四维 ``w`` 并用于裁剪；NDC 是透视除法后的标准化坐标。
* **Position 与 normal**：position 是点并接受平移；normal 是方向，应使用正确的法线变换，非均匀缩放下不能直接套普通 model matrix。
* **Instancing 与 batching**：instancing 复用同一 mesh、通过 instance data 区分对象；batching 是更广义的减少提交或状态切换策略。
* **Attribute bandwidth 与 shader ALU**：压缩属性可降低读取量但增加解码计算，两者需要按瓶颈取舍。
* **唯一顶点与 VS invocation**：一个逻辑顶点可因索引复用只执行一次或少量次数；糟糕的索引顺序会破坏 post-transform cache 并增加重复执行。
* **Culling 与 Vertex Shader 优化**：culling 直接减少进入顶点阶段的数量；shader 优化降低每次 invocation 的成本，二者作用层级不同。

本章结论
--------

顶点处理应沿“输入合同—形变—空间变换—裁剪坐标—固定功能后处理”整条链理解。正确性先看 layout、矩阵与 ``w``，性能再看 invocation、属性带宽、skinning ALU 和缓存复用；只有把每个顶点为什么被执行、读了多少数据、做了多少计算、最终去了哪里解释清楚，顶点阶段的错误与瓶颈才可稳定定位。