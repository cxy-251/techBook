第076章：运动学与 Rig 基础
==========================

核心知识点
----------

骨骼动画的运行时核心对象是 Joint Pose
   Joint 形成父子层级，local pose 表示相对父节点的 TRS，global pose 由父到子累积得到。Bone 更适合表达相邻 joint 的语义段，真正参与求值的是 joint transform 与 parent index。

Bind Pose 是蒙皮的共同参考状态
   Mesh 在绑定时处于 bind/rest pose。每个 joint 的 inverse bind matrix 将 bind-space 顶点带回对应 joint 的绑定空间，当前帧 global joint matrix 再把它送到当前姿态。典型关系是 ``palette[j] = globalPose[j] * inverseBind[j]``。

Skin Weight 决定顶点如何跟随骨骼
   每个顶点保存若干 joint index 与 weight，权重和应接近 1。肩、肘、腕、膝等区域的变形质量主要由权重分布决定；joint index、inverse bind 顺序或 vertex format 任一错位都会直接造成拉裂、飞点和关节塌陷。

Local-to-Global 更新必须遵守拓扑顺序
   父 joint 必须先于子 joint 更新。矩阵主序、乘法顺序、TRS 合成、角色根空间和 world transform 都要使用同一约定。Local pose 正确而 global pose 错，问题通常位于父链、矩阵约定或 root transform。

Rig 是控制层，不是最终渲染数据
   Skeleton asset 保存稳定骨架定义，control rig 提供 FK/IK、空间切换和控制器，constraint 负责目标关系，retarget profile 负责骨架间语义迁移。它们最终都要产出 joint pose，再生成 matrix palette 供 skinning 使用。

运行时 Constraint 是对基础 Pose 的程序化修正
   Parent/orientation/aim/look-at/two-bone IK 等 constraint 接收目标、链、权重和空间约定，修改当前 pose。Constraint weight 为 0 时保留输入动画，为 1 时完全采用求解结果，中间值用于渐入渐出。

IK 从末端目标反推骨骼链
   Two-bone IK 常用于手臂和腿；goal 决定末端位置，pole vector 决定肘或膝的弯曲平面。肘膝突然翻转时先看 goal、pole、chain 与空间，而不是继续提高 solver 精度。

Foot Placement 是场景查询与 IK 的组合
   稳定脚底贴地通常是“地面查询 → 脚踝目标 → 腿部 IK → pelvis/root 高度修正 → 权重平滑”。它改变的是 pose buffer，最终仍通过 global pose 与 palette 进入蒙皮。

Retarget 应按功能链而不是单个 Bone 名称理解
   不同角色可能存在命名、骨骼数量、比例和参考姿态差异。Arm、leg、spine、neck 等 chain 更适合作为迁移单位；retarget pose、root motion 比例和末端保持策略共同决定动作语义是否保留。

DCC 导入的正确性由 Mesh、Skeleton 与 Clip 三者共同决定
   FBX、glTF、USD 或自研格式都要统一单位、轴向、joint mapping、bind pose、inverse bind、权重和 animation channel。只转换 mesh 而没有同步转换 skeleton/clip，会直接造成骨架和网格分离。

角色动画的最终运行时闭环是 Pose 到 Palette
   Clip sampling 生成基础 local pose，runtime rig/IK 修正 pose，层级更新得到 global pose，随后生成 palette 并上传 GPU。渲染系统消费 palette，不直接理解 control rig 或动画师控制器。

关键路径
--------

角色 Rig 到蒙皮：

::

   skeleton asset + bind pose
   → clip sampling
   → local pose buffer
   → runtime constraint / IK
   → parent-first global pose
   → globalPose * inverseBind
   → matrix palette
   → GPU / CPU skinning
   → skinned mesh

Foot IK：

::

   predicted foot position
   → ground query
   → contact point + normal
   → foot goal / ankle rotation
   → pole direction
   → two-bone IK
   → pelvis height correction
   → constraint weight blend
   → final pose

导入排查：

::

   unit / axis convention
   → skeleton parent indices
   → bind pose / inverse bind
   → vertex joint indices / weights
   → clip target mapping
   → local/global pose
   → palette order
   → draw transform

概念辨析
--------

* **Joint 与 Bone**：joint 是运行时 transform 节点，bone 更偏相邻 joint 间的语义段。
* **Bind Pose 与 Current Pose**：bind pose 是绑定参考，current pose 是当前动画状态；inverse bind 连接两者。
* **Local Pose 与 Global Pose**：local 只描述相对父节点关系，global 才是层级累积后的姿态。
* **Control Rig 与 Skeleton**：control rig 是控制接口，skeleton 是稳定运行时骨架；前者最终写回后者。
* **FK 与 IK**：FK 从父到子推末端，IK 从末端目标反推中间关节。
* **Constraint Weight 与 Solver Strength**：weight 决定结果混合比例，solver/constraint 参数决定目标本身如何求得。
* **Retarget 与 Skinning**：retarget 迁移动作语义，skinning 依据当前 palette 变形顶点，二者位于不同阶段。
* **Character Root 与 Root Joint**：角色场景 transform 与骨架根节点应职责清楚，否则 root motion 容易重复累计。

本章结论
--------

运动学与 Rig 应按“Skeleton/Bind Pose—Local Pose—Constraint/IK—Global Pose—Matrix Palette—Skinning”理解。角色异常时先分清目标错、骨架链错、palette 错还是权重错：手脚目标异常查 rig/IK，骨架层级异常查 local-to-global，骨架正确但网格爆开查 inverse bind、joint index 和 palette，世界位置异常再查 character root 与 root motion。稳定 Rig 管线的本质，是让所有编辑控制最终收敛到一份空间、顺序和索引都明确的 joint pose。