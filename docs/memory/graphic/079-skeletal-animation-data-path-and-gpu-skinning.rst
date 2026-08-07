第079章：骨骼动画数据路径与 GPU Skinning
======================================

核心知识点
----------

骨骼动画的正确性来自三组数据同时对齐
   静态绑定数据包括 skeleton、bind pose、inverse bind matrix、vertex joint index 和 weight；每帧动画数据包括 sampled local pose、global pose 和 joint palette；渲染绑定数据包括 vertex buffer、palette buffer、pipeline layout 与 draw state。任一组空间、顺序或布局错位，都会直接变成可见错误。

Skeleton Hierarchy 决定 Joint 的空间传播
   每个 joint 保存 parent index 和 local transform，global transform 由父到子累积。Bind pose 是 mesh 与 skeleton 的共同参考，inverse bind 将 bind-space 顶点带入 joint bind space。

Matrix Palette 是 CPU 动画与 GPU 蒙皮的接口
   常见关系是 ``jointMatrix[j] = currentGlobal[j] * inverseBind[j]``。Palette 的索引必须与 mesh 顶点中的 joint index、skin joint table 和 inverse bind 顺序完全一致。

Clip Sampling 只生成 Local Pose
   Animation channel 在当前时间采样 translation/rotation/scale，得到每个 joint 的 local transform；之后必须做 hierarchy evaluation 才能得到 global pose。直接把 local pose 当 palette 使用，越靠近叶子 joint 偏差越大。

GPU Skinning 的典型输入是静态顶点 + Joint Palette
   顶点保存 position、normal、joint indices、weights，vertex shader 根据 4 个或更多 joint 影响组合 skin matrix，再输出变形后的 position/normal/tangent。CPU 每帧主要上传 palette，而不是整份动态顶点。

CPU Skinning 与 GPU Skinning 的核心差异是数据移动路径
   CPU skinning 每帧遍历并上传大量变形后顶点，适合 CPU 端必须立即读取最终 mesh 的场景；vertex-shader skinning 上传较小 palette，把 ALU 压力放在 GPU；compute skinning 先写一次变形结果，可供多个 render pass 复用。

Compute Skinning 适合多 Pass 重复变形
   Shadow、depth、G-buffer、forward、motion vector 等 pass 都重复执行 vertex skinning 时，可以先 compute 输出当前帧 skinned buffer，再由多个 pass 读取。收益来自减少重复 ALU，代价是额外 buffer 写入、显存带宽和 barrier。

Buffer Layout 是最常见的隐性故障源
   Joint index 可压为 8/16 bit，weight 可用 normalized integer，palette 可用 3x4 matrix、dual quaternion 等表示。压缩可以减少带宽，但会增加 vertex format、stride、alignment、normalized flag 与 shader 解包的一致性要求。

Normal/Tangent 也必须跟随变形
   只变 position 会让光照错误。非均匀 scale 存在时，normal 不能简单使用 position 的同一矩阵；很多角色管线会限制 bone non-uniform scale，或使用专门 normal transform。

Blend Shape 与 Skinning 属于同一顶点变形链
   Morph target 通常先在 bind/local mesh space 中累加 delta，再对 morphed vertex 做 skinning。反过来在已 skin 的 world/model 结果上直接加 bind-space delta，会导致表情或肌肉形变方向错误。

Hybrid Deformation 需要维护前后帧状态
   TAA、motion blur 和 temporal upscaling 不仅依赖 previous joint palette，morph weight 改变时也需要上一帧 morph 状态。Compute skinning 也可直接缓存 previous/current skinned buffer。

Reference Pose 是排查 Skinning 的第一基准
   把动画固定在 bind/reference pose，此时 ``currentGlobal * inverseBind`` 应让 mesh 回到原始形状。若 reference pose 已经变形，问题在 inverse bind、mesh/root transform、坐标转换或 joint table，而不是 clip interpolation。

多 Pass 不一致通常是绑定问题
   主 pass 正常但 shadow/motion pass 错误，优先检查各 pass 的 palette buffer、offset、descriptor/root binding、current/previous frame 选择和 instance index，而不是重新检查动画 clip。

关键路径
--------

CPU 动画到 GPU Skinning：

::

   animation clip
   → sample local joint transforms
   → hierarchy evaluation
   → current global matrices
   → global * inverseBind
   → joint palette buffer upload
   → vertex shader reads joints + weights
   → weighted skin matrix
   → skinned position / normal / tangent
   → rasterization

Compute Skinning：

::

   palette + bind vertex buffer
   → compute deformation
   → skinned transient vertex buffer
   → barrier
   → shadow / depth / G-buffer / motion passes

Hybrid Deformation：

::

   base vertex
   + active morph deltas / weights
   → morphed local vertex
   → joint indices / weights + palette
   → skinned vertex
   → current / previous deformation for motion

排查：

::

   bind/reference pose
   → joint index range / weight sum
   → hierarchy global axes
   → inverse bind matrices
   → palette order
   → GPU buffer offset / stride
   → single-joint debug
   → normal / tangent
   → compare render passes

概念辨析
--------

* **Bind Pose 与 Inverse Bind**：bind pose 是参考姿态，inverse bind 是把顶点转换到 joint 绑定空间的矩阵。
* **Local Pose 与 Palette**：local pose 还没有父层级累积，palette 必须由 global pose 生成。
* **CPU Skinning 与 GPU Skinning**：两者数学相同，主要区别是变形执行位置和每帧上传数据规模。
* **Vertex Skinning 与 Compute Skinning**：前者每个 pass 可重复计算，后者先写一次结果供多个 pass 复用。
* **Joint Index 与 Node Index**：skin joint table 的索引不一定等于场景 node index，混用会直接绑定错矩阵。
* **Morph Target 与 Skeleton**：morph 改局部形态，skeleton 改层级姿态；混合变形需要明确顺序。
* **Position 正确与 Lighting 正确**：position 变形正确并不保证 normal/tangent、motion vector 与 shadow pass 正确。

本章结论
--------

骨骼动画数据路径应按“Skeleton/Bind—Clip Sampling—Global Pose—Palette—GPU Binding—Vertex Deformation”理解。角色爆开先查 joint index、weight、palette 越界和 buffer stride；reference pose 已变形则查 inverse bind 与 root/mesh 空间；子关节逐级偏移查 hierarchy 与矩阵顺序；主 pass 正常而其它 pass 异常查资源绑定。GPU skinning 的核心不是 shader 公式本身，而是 CPU pose、静态绑定数据和每个 draw pass 是否消费了同一份、同一顺序、同一空间的 palette。