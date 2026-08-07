第067章：软体动力学
==================

核心知识点
----------

软体模拟处理的是可变形状态
   与刚体只推进整体 transform 不同，软体需要更新一组节点、边、面、四面体或粒子簇的位置和速度。布料、披风、果冻、软组织虽然视觉不同，但都可以归结为“rest state + 动态节点 + 约束 + 碰撞 + render binding”。

Mass-Spring、FEM、PBD、Shape Matching 服务不同目标
   Mass-Spring 用弹簧连接节点，直观且易实现；FEM 用元素和材料能量表达更真实的连续材料；PBD 先预测位置，再把位置投影回满足约束的可接受状态，适合实时交互；Shape Matching 让节点簇回到整体 rest shape，适合果冻和软组织。模型选择应先看需要表达什么，再看 solver 预算。

Simulation Mesh 与 Render Mesh 必须分离
   求解器需要的是低成本、稳定的 simulation mesh；屏幕需要的是高分辨率 render mesh。两者可通过一一映射、重心坐标、插值权重或 skinning 绑定。Simulation 状态稳定而表面撕裂时，应优先检查 render binding，而不是继续增加 solver iteration。

PBD 的核心是“预测位置—迭代投影—速度回写”
   外力先得到预测位置，距离、弯曲、pin、碰撞、体积等约束再反复修正位置，最后由新旧位置差恢复速度。约束修正会通过速度进入下一帧，因此过强投影、错误碰撞修正和大 timestep 都会造成后续抖动。

布料约束应区分拉伸、剪切和弯曲
   Structural constraint 控制主要边长，shear constraint 控制网格斜向变形，bend constraint 控制折叠与褶皱尺度。只提高一种 stiffness 往往会让另一种形变失控，因此材质感来自多个独立约束维度。

Pin Constraint 是动画系统与软体系统的边界
   披风肩部、裙腰、旗帜固定边等节点由骨骼或场景 transform 提供目标位置。每个 physics step 应先更新 pin target，再让软体约束围绕这些动态边界求解。Pin 目标晚一帧会直接表现为根部漂移和拉扯。

碰撞约束必须有稳定 inside/outside 语义
   Sphere、capsule、plane、SDF 都能提供连续法线和距离，适合实时 cloth/soft-body。角色披风通常用简化 capsule/SDF，而不是直接撞高模三角形。碰撞只在 solver 最后做一次修正，会与距离约束互相打架；更稳定的方式是让碰撞约束进入迭代循环。

Self-Collision 的主要成本来自候选生成与约束冲突
   布料自碰撞需要 spatial hash、grid 或 BVH 先缩小节点/边/三角形候选，再生成局部接触约束。Collision thickness 太小会漏穿，太大又会让折叠显得蓬松。候选过多时，瓶颈往往先出现在 broad phase，而不是投影公式本身。

Stiffness、Iteration、Timestep 必须联合判断
   Stiffness 决定单次修正强度，iteration 决定约束传播次数，timestep 决定预测位置偏离程度。提高 stiffness 后抖动变大，常见根因不是“还不够硬”，而是 timestep 太大或速度回写被强投影放大。

Substep 是稳定实时软体的重要手段
   将一个大步拆成多个小步可以降低碰撞穿透和约束峰值。贴身披风、快速角色、强风和高 stiffness 更需要 substep；远景 cloth 可通过更少 substep、iteration 和 simulation nodes 降级。

Damping 用来压高频能量，不应用来掩盖错误约束
   速度 damping 或相对速度 damping 可以消除细碎颤动，但过高会让整块布料像被粘住。若增加 damping 才能避免爆炸，应回到 timestep、constraint residual 和碰撞修正检查根因。

体积保持决定三维软体是否塌缩
   四面体 volume constraint、pressure constraint 或 shape matching 可以保持果冻、软包和软组织的体积感。Volume 权重过强会变成橡胶块，过弱会像空壳。应先确认接触正确，再调体积恢复。

GPU 求解适合大规模节点，但要处理共享写冲突
   Particle、constraint、contact、deform buffer 可以放在 compute 中更新。约束共享节点会造成并发写冲突，常用 graph coloring、Jacobi 累积、多 pass 分组或原子方式处理。Compute 写出的 deform buffer 在 render pass 前还需要明确 barrier。

关键路径
--------

PBD/约束型软体：

::

   animation / external force
   → update pin targets
   → predict particle positions
   → build collision constraints
   → solve distance / shear / bend / volume / pin
   → solve collision / self-collision
   → repeat iterations
   → update velocities
   → simulation state
   → render binding
   → deformed vertices / normals

引擎集成：

::

   asset simulation mesh + rest state
   → build constraint buffers
   → fixed step / substep
   → solver output
   → compute render binding
   → barrier / vertex read
   → mesh + shadow + motion-vector passes

稳定性排查：

::

   pin target timing
   → timestep / substep
   → constraint residual
   → stiffness / iteration
   → collision candidates / normals
   → self-collision density
   → damping
   → volume preservation
   → render binding

概念辨析
--------

* **Simulation Mesh 与 Render Mesh**：前者服务求解，后者服务视觉；二者分辨率和拓扑可以不同。
* **Mass-Spring 与 PBD**：前者主要从力推进状态，后者主要把预测位置投影到约束空间。
* **FEM 与 Shape Matching**：FEM 更贴近材料连续力学，Shape Matching 更偏整体形状恢复和实时稳定。
* **Stiffness 与 Iteration**：一个控制单次修正，一个控制重复传播；不能用同一个旋钮替代。
* **Pin 与 Collision**：pin 是外部动画目标，collision 是环境不可穿透约束，二者都会修改节点但语义不同。
* **Damping 与 Stability**：damping 只耗散能量，不会修复错误 timestep、错误法线或错误 binding。
* **Render 穿透与 Simulation 穿透**：simulation 节点正确但高分辨率表面仍穿过，优先查绑定与表面插值。

本章结论
--------

软体动力学应按“simulation mesh—预测位置—约束投影—碰撞—速度回写—render binding”理解。稳定性重点在 timestep、substep、stiffness、iteration、pin 与碰撞之间的平衡，视觉问题还必须区分 solver state 与 render mesh 映射。只要约束残差、碰撞修正和绑定关系都可观察，布料拉伸、抖动、穿透与果冻塌缩就能被定位到具体阶段，而不是靠反复试参数。