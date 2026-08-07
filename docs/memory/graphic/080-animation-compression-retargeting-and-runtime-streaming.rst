第080章：动画压缩、重定向与运行时流式加载
========================================

核心知识点
----------

动画运行时问题不仅是 Pose 求值问题
   一个 clip 能否稳定播放，还取决于压缩格式、误差预算、retarget 语义、stream cache、解码任务、pose buffer、LOD 和 GPU palette 上传。动画库规模上升后，资产管理会直接影响帧时间和视觉连续性。

动画压缩处理的是 Track 时间序列
   Skeletal clip 通常包含 translation、rotation、scale、curve、morph weight、event 和 root motion 等轨道。运行时解码得到 local pose，再经过 retarget/blend、global pose 和 skinning。压缩的目标是减少文件、内存和带宽，同时把视觉误差限制在可接受范围。

压缩目标应拆成多个预算
   文件尺寸影响包体，常驻内存影响可同时保留的 clip，解码带宽影响每帧可更新角色数，随机访问能力影响状态机跳转，误差阈值影响脚底、手部、root motion 与面部质量。单一“压缩率”无法代表运行时价值。

Track 应按用途分级
   Rotation 对身体姿态最敏感，root translation 直接影响移动和脚滑，scale 在普通 humanoid 中少但会向子节点传播，event/gameplay curve 需要保护阈值穿越时机。Hero、cinematic、gameplay、background、crowd 可以使用不同 codec 和误差阈值。

Quantization 必须绑定值域和误差传播
   Translation 可按 track/clip 范围量化；quaternion 需要处理 ``q`` 与 ``-q`` 等价、归一化和分量压缩。局部角度误差会沿骨骼链放大成末端位置偏差，因此不能只看 local rotation error。

Curve Fitting 与 Key Reduction 需要验证插值区间
   删除 key 或拟合曲线可以显著减小数据量，但快速脚步、手臂摆动、root velocity 峰值很容易被抹平。只在原 key 时间检查误差可能漏掉插值中间的峰值。

动画误差应尽量提升到视觉空间评估
   Local transform error 适合快速筛选，global joint position error 更接近真实骨骼结果，skinned vertex error 更接近最终画面，foot/hand/contact error 则直接对应脚滑、持物漂移和交互失败。

Retarget 的本质是迁移动作语义
   Source/target skeleton 可能在命名、骨骼数量、局部轴、A/T pose 和比例上不同。稳定迁移应先建立 retarget pose，再建立 arm/leg/spine/neck/root 等 chain mapping，最后处理比例、root motion 和 IK 接触修正。

Retarget Pose 是迁移基准
   源和目标参考姿态若肩、髋、脚踝角度不同，直接复制旋转会把偏差带到所有动作。Retarget pose 用来把两套骨架对齐到共同语义状态，后续动作增量才有可比性。

比例差异需要分层处理
   Root motion、pelvis、limb end effector、twist bone 不应统一按身高比例缩放。腿长变化会影响步幅，手臂长度会影响持枪/攀爬末端位置，IK 适合修正接触，但不能掩盖错误的 retarget pose 或 chain mapping。

Streaming 解决动作库规模与瞬时可用性的矛盾
   Clip header、duration、event、sync marker、root motion summary 可优先常驻；压缩 track 数据按时间块或 track group 懒加载。Chunk 越大随机跳转更重，越小调度和边界开销越高。

动画内存预算至少包含四层
   Stream cache 中的 compressed chunk、解码临时数据、当前/上一帧及混合 pose buffer、GPU matrix palette/compute skinning buffer 都占内存。压缩率只优化其中一部分。

Streaming 与状态机必须协同预取
   状态切换前应预取目标 clip 的 header 和前几个 chunk；多个角色同帧切换时应避免集中解码峰值。Event、sync marker 与 root motion 等控制数据不能因为普通 track 尚未加载而缺失。

Animation Budget 可以通过 LOD 控制更新频率
   近景主角保持完整轨道、retarget、IK 和高频更新；远景 NPC 可降低手指/面部精度、隔帧更新、共享 pose 或使用简化骨架/预烘焙动画。降频必须配合插值，否则远景角色会明显跳帧。

运行时质量验证应分层 A/B
   先比较 raw clip 与 decoded clip，再比较 retarget 后目标骨架，再放入真实 state machine、streaming 和 LOD，最后检查 GPU skinning。每一步只改变一个变量，才能知道误差属于压缩、迁移、调度还是渲染绑定。

关键路径
--------

压缩到播放：

::

   raw animation tracks
   → classify tracks
   → quantize / fit / reduce keys
   → validate error
   → compressed clip chunks
   → stream cache
   → decode
   → local pose
   → blend / retarget
   → global pose
   → matrix palette
   → skinning

Retarget：

::

   source skeleton + source clip
   → source reference / retarget pose
   → chain mapping
   → target reference alignment
   → root / pelvis scale policy
   → FK transfer
   → IK end-effector correction
   → target pose

Streaming：

::

   state machine predicts next clip
   → prefetch header / metadata
   → request track chunk
   → cache hit / IO
   → decode job
   → pose evaluation
   → LOD update / interpolation
   → GPU palette upload

质量排查：

::

   raw vs decoded on source skeleton
   → global joint / contact error
   → retarget pose / chain mapping
   → root motion / sync marker
   → stream cache / decode timing
   → LOD update frequency
   → CPU pose
   → GPU skinning buffer

概念辨析
--------

* **Compression Ratio 与 Runtime Cost**：更小文件不一定更快，复杂 codec 可能增加解码和随机访问成本。
* **Local Error 与 Visual Error**：局部旋转误差很小，也可能沿长骨骼链放大成明显末端偏差。
* **Retarget Pose 与 IK**：retarget pose 建立基础语义对齐，IK 只负责后续末端修正，不能替代基础映射。
* **Bone Mapping 与 Chain Mapping**：逐 bone 名称映射更脆弱，chain 更能适应骨骼数量和命名差异。
* **Streaming Chunk 与 Pose Buffer**：chunk 是压缩资产数据，pose buffer 是已解码当前运行时状态，两者生命周期不同。
* **Animation LOD 与 Compression Profile**：LOD 控制运行时更新与功能等级，compression profile 控制资产数据精度，可以组合使用。
* **State Transition 卡顿与动画质量错误**：切换首帧卡顿常来自 cache miss/decode 峰值，不一定是 clip 或 blend 本身错误。

本章结论
--------

动画压缩、重定向与流式加载应按“Track—误差预算—压缩—Retarget—Chunk/Cache—Decode—Pose—Skinning”理解。脚滑先在源骨架比较 raw/decoded 的 root 与 foot contact，再查 retarget 比例和 sync marker；手部偏离道具查 arm chain、retarget pose 和 IK；状态切换首帧卡顿查 prefetch、cache miss 和 decode job。稳定运行时不是追求最大压缩率，而是在视觉误差、随机访问、内存、解码和角色 LOD 之间建立可量化的预算。