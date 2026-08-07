第078章：物理驱动动画集成
==========================

核心知识点
----------

物理驱动动画的核心问题是控制权分配
   Keyframed animation 擅长表达动作意图，physics simulation 擅长响应接触、冲击、重力和约束。稳定系统要明确每个骨骼、每个阶段由动画、IK、physical animation 还是 ragdoll 主导。

动画与物理通过骨骼—刚体映射连接
   Skeleton joint 对应 capsule、box 或 convex rigid body，并保存 bone-to-body offset。动画侧提供目标 pose，物理侧保存质量、惯性、碰撞形状、关节限制和 solver state，最终物理结果再回写到骨骼 pose。

帧内顺序决定反馈是否真正可见
   稳定路径通常是“采样动画 → 生成物理目标 → physics fixed step → 读取 contact/body result → 混合最终 pose → skinning”。若 skinning 已提交后才回写物理，视觉会滞后一帧；若物理后又被动画覆盖，反馈会直接消失。

Physical Animation 用驱动器追踪动画目标
   它不等于完全 ragdoll。刚体以动画 pose 为目标，通过 stiffness、damping、angular/position drive 追踪目标。刚度越高越接近 keyframe，阻尼越高越少回弹；受到冲击时身体可以短暂偏离，再连续恢复。

骨骼空间与刚体世界空间必须可逆转换
   Bind pose 的 bone-body offset、当前 global pose、physics body transform 与回写矩阵必须使用统一空间。脚底贴地错位、肩膀扭曲和 ragdoll 恢复跳变，常见根因就是空间或偏移关系不一致。

Ground Contact 是程序化动画的重要输入
   地面查询提供 contact point、normal、penetration、surface/platform state。角色系统据此生成 foot target、ankle rotation、pelvis offset 和 grounded/support 参数，随后由 IK 与状态机消费。

Foot IK 需要步态相位门控
   支撑期 IK 权重大，脚掌要稳定；摆动期权重低，让脚跟随原始动画跨越障碍。过早锁脚会产生空中吸附，支撑期权重过低会穿地或滑动。

Hit Reaction 应按强度分级
   轻微冲击可使用上半身 additive；中等冲击可让胸肩进入 physical animation；强冲击可切到局部或全身 ragdoll。判断不仅看 impulse，还应结合受击部位、角色质量、动作状态和 gameplay 规则。

环境交互本质是状态交换
   环境提供碰撞、法线、移动平台速度、道具约束；角色提供期望 pose、速度和动作状态。Physics 输出 contact、impulse、constraint error，动画系统再将其转成 foot lock、hit direction、blocked、recovery 等下一帧参数。

Secondary Motion 必须绑定最终身体姿态
   Cloth、hair、挂件、武器带等附属模拟应以最终胸背/头部/手腕姿态作为锚点。若锚点读取的是物理修正前的基础 clip，身体发生偏转时附属物根部会与身体分离。

Blend Weight 与 Constraint Stiffness 职责不同
   Blend weight 决定最终 pose 使用多少物理结果；constraint stiffness 决定物理系统内部关节允许偏离多少。两者不能互相替代。

Recovery Pose 是从 Physics 回到 Keyframe 的桥梁
   不能把 ragdoll 当前姿态直接硬切回奔跑 clip。应读取当前 pelvis、root、脚底接触和朝向，选择恢复动作，先对齐身体基准，再逐步提升 keyframe 权重。

动画物理 LOD 应独立于渲染 LOD
   主角可运行 ground contact、physical animation、ragdoll、cloth 和道具约束；中距离角色保留脚 IK 和少量受击；远景角色仅播放 clip 或低成本 secondary motion。角色重要性、屏幕占比、交互强度和预算共同决定等级。

实时成本来自多个系统叠加
   动画采样、IK、刚体、碰撞、solver iteration、substep、cloth/hair、pose writeback 与 skinning 都会累加。性能排查必须分阶段计时，而不是只看“角色动画”总耗时。

关键路径
--------

动画—物理闭环：

::

   clip / blend tree pose
   → build physical targets
   → bone-to-body mapping
   → fixed physics step
   → collision / constraints / impulses
   → body transforms + contacts
   → masked physics writeback
   → procedural / aim corrections
   → final skeleton pose
   → skinning

环境交互：

::

   predicted foot / body position
   → collision query
   → contact classification
   → foot / body target
   → IK / physical animation
   → state feedback
   → next-frame animation parameters

控制权迁移：

::

   Keyframed
   → Assisted
   → Physical
   → Recovery
   → Keyframed

性能排查：

::

   active characters
   → physical joints per character
   → contacts / constraints
   → substeps / solver iterations
   → cloth / hair workload
   → pose writeback
   → thread dependencies
   → skinning submission
   → animation physics LOD

概念辨析
--------

* **Keyframed Animation 与 Ragdoll**：前者主动表达意图，后者主要由动力学和碰撞决定姿态。
* **Physical Animation 与 Ragdoll**：physical animation 仍追踪动画目标，ragdoll 可以完全失去动画目标驱动。
* **Foot IK 与 Ground Contact**：ground contact 提供环境证据，IK 负责把证据转换成腿部骨骼姿态。
* **Blend Weight 与 Stiffness**：weight 控制最终混合，stiffness 控制物理驱动器内部响应。
* **Physics Pose 与 Final Pose**：物理回写通常只是最终 pose 的一层，后面还可能有 aim/look-at 或其它高优先级约束。
* **Secondary Motion 与主身体 Simulation**：附属模拟应消费稳定身体锚点，不应反过来成为主姿态唯一来源。
* **Recovery 与普通 Transition**：recovery 需要从真实物理状态建立对齐，不只是两个 animation state 之间做权重混合。

本章结论
--------

物理驱动动画应按“动画目标—物理目标—固定步求解—接触/刚体结果—受控回写—最终 Pose—Skinning”理解。受击只偏一帧后立即弹回时，应查回写顺序和 blend weight 是否被下一帧基础动画覆盖；披风根部分离则查锚点是否读取最终身体姿态；脚底问题则从 contact、步态相位和 root motion 开始。稳定系统的关键不是让物理接管更多，而是让动画、物理和程序化修正之间的控制权、时间点与空间边界都明确。