第077章：动画混合与状态机
========================

核心知识点
----------

动画系统最终混合的是 Pose
   Pose 是同一 skeleton 上所有 joint 的 local transform 集合。多个 clip、additive、mask 和 procedural layer 最终都要生成一份确定的 local pose，再进入 global pose 与 skinning。

State Machine 解决离散动作阶段
   Idle、Move、JumpStart、InAir、Land 等 state 表达动作语义，transition、condition、blend time、entry/exit action 与 event 管理阶段切换。状态机不适合承载每个方向、速度档位的所有 clip 组合。

Blend Tree 解决连续参数空间
   1D tree 常根据 speed 在 idle/walk/run 间插值；2D tree 常根据 forward/right speed 或 speed/turn angle 生成多个 locomotion clip 的权重。状态机回答“处在哪个动作阶段”，blend tree 回答“这个阶段内部使用哪些 clip”。

Pose 权重必须稳定且可解释
   多 pose 混合时 translation/scale 通常线性组合，rotation 使用 quaternion nlerp/slerp。权重应归一化；不同 clip 的动作相位还要尽量一致，否则即使权重连续，脚步也会在过渡区打架。

Additive Pose 表达相对变化
   Aim offset、轻微 hit reaction、呼吸和上半身修正常以 reference pose 为基准保存 delta，再叠加到基础 locomotion。Additive 的优势是保留基础动作节奏，只添加局部姿态差。

Mask 控制骨骼影响范围
   Upper-body aim、reload、hit reaction 等层应通过 per-joint mask 限制作用范围。Mask 边界若突变，腰、肩会出现硬折；常用 spine 梯度权重让下身保持 locomotion，上身逐渐接管。

Root Motion 与普通 Pose 必须分流
   普通 pose 进入 skinning；root motion 提取角色整体位移和旋转，写入 character controller、碰撞或 scene transform。一个角色应有清晰的 root motion 主来源，避免 locomotion、additive 和 gameplay 同时修改整体位移。

Transition 要关注滞回、相位和事件
   Idle→Move 与 Move→Idle 常使用不同 speed 阈值，形成 hysteresis，避免阈值附近来回切换。Jump、land、attack 等事件型状态应记录事件是否已消费；transition blend 还要对齐 foot contact、root motion 与 sync marker。

复杂角色动画需要明确 Layer 规划
   常见顺序是 locomotion 基础层 → aim offset → upper-body mask → hit additive → facial layer。具体项目可调整顺序，但每层都要明确输入、影响骨骼、权重来源和是否能修改 root motion。

动画性能主要来自采样、解码、混合和 Pose 写入
   可见角色数、joint 数、active clip 数、active layer 数、压缩解码和 local-to-global 都会消耗 CPU。先分项计时，再决定 cache、job system、pose buffer reuse 与 animation LOD。

Pose Buffer 应复用而不是每个 Node 每帧分配
   动画图会产生大量中间 pose。固定 pose arena、临时 buffer 池或生命周期复用能减少内存分配和带宽；下游读完之前不能覆盖同一 buffer。

Animation LOD 与 Mesh LOD 是不同层次
   远景角色可以降低动画更新频率、关闭 facial、IK、additive 和部分 upper-body layer，甚至复用共享 pose。降级依据应包含屏幕占比、可见性、角色重要性和动画预算，而不只是距离。

Job System 适合按角色并行动画求值
   多角色的 clip sampling、state evaluation、pose blend 和 local-to-global 通常相互独立，可以并行；skinning 提交前必须等待对应最终 pose 完成，避免 GPU 读取上一帧或半写入 palette。

关键路径
--------

一帧动画求值：

::

   gameplay parameters snapshot
   → state machine
   → active states / transitions
   → blend tree weights
   → clip sampling / decompression
   → base local pose
   → masked / additive layers
   → final local pose
   → global pose
   → skinning palette

Root Motion：

::

   locomotion clip
   → sample root transform delta
   → transition / blend policy
   → extract root motion
   → character controller / collision
   → scene transform

性能排查：

::

   visible character count
   → joints per character
   → active clips / layers
   → clip sampling / decode time
   → blending time
   → pose buffer allocations
   → local-to-global time
   → job wait
   → animation LOD / cache strategy

概念辨析
--------

* **State Machine 与 Blend Tree**：前者处理离散阶段，后者处理连续参数插值。
* **Base Pose 与 Additive Pose**：base 提供完整姿态，additive 提供相对参考姿态的增量。
* **Mask 与 Weight**：weight 控制整个 layer 强度，mask 控制每个 joint 的局部影响范围。
* **Pose Blend 与 Root Motion Blend**：pose 解决骨骼形变，root motion 解决角色整体位移，两条路径要独立定义。
* **Transition Blend 与 Clip Phase**：权重平滑不等于动作连续，脚步、步频和根运动仍需要相位对齐。
* **Animation LOD 与 Mesh LOD**：一个减少姿态计算，一个减少几何渲染，二者可独立配置。
* **Cache 与 Pose Reuse**：clip cache 主要减少动画数据查找/解码，pose reuse 主要减少中间 buffer 与重复求值。

本章结论
--------

动画混合应按“参数快照—状态机—Blend Tree—Clip Sampling—Pose Blend—Layer/Mask—Root Motion—最终 Pose”理解。角色动作发飘时先看状态与 transition 是否正确，再看 blend weight 和相位；上半身与腿部互相污染时查 mask 和 layer 顺序；位移异常时单独查 root motion 主路径。性能问题则从角色数、joint 数、active clip/layer、解码和 pose buffer 开销逐层定位，再用 job、cache 和 animation LOD 控制规模。