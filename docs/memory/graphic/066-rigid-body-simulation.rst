第066章：刚体模拟
================

核心知识点
----------

刚体状态由平移与旋转两部分组成
   动态刚体的最小状态包括位置 ``x``、旋转 ``q``、线速度 ``v``、角速度 ``ω``、质量 ``m``、惯性张量 ``I``、累计力与力矩。刚体假设物体内部距离不变，因此模拟只推进整体 transform，而不求解内部形变。

力与冲量承担不同职责
   重力、风、马达等持续输入以力或力矩进入积分；碰撞响应通常以冲量瞬时修改速度。线性冲量满足 ``Δv = J / m``，接触点偏离质心时还会通过 ``r × J`` 改变角速度。持续力不应直接当成碰撞修正，碰撞冲量也不应按帧重复累积成持续推力。

固定时间步是刚体稳定性的基础
   实时物理通常使用固定 ``dt``，例如 ``1/60s``，再由渲染帧 accumulator 驱动零个、一个或多个 physics step。半隐式 Euler 常先更新速度再更新位置。可变 ``dt`` 会让摩擦、反弹、solver 收敛和 sleeping 阈值随帧率漂移。

碰撞检测要输出 Contact Manifold，而不只是布尔命中
   Broad phase 用 AABB、BVH、Sweep-and-Prune 等生成候选；narrow phase 对真实 collision shape 计算 contact point、normal、penetration、relative velocity。Solver 消费的对象是稳定接触集合，而不是“两个物体碰到了”这一布尔结果。

接触响应由法向、摩擦与恢复约束共同决定
   法向冲量阻止继续穿透，切向冲量模拟摩擦，restitution 决定高速碰撞保留多少反弹。球落到斜坡后既被法向冲量推开，又因切向摩擦改变滑动速度和角速度，因此最终滚动状态是多种约束共同结果。

Trigger 与 Collider 的输出目标不同
   Collider 生成需要 solver 处理的接触约束；Trigger/Sensor 只生成 overlap begin/end 事件，不修改速度。区域触发、拾取与关卡逻辑应走事件路径，不应伪装成零摩擦碰撞体。

物理状态与渲染状态需要显式同步
   Physics step 产生权威 body transform，渲染帧可在前后两个 physics snapshot 之间插值。插值只改善显示连续性，不会修复 tunneling、漏接触或 solver 错误。单位、坐标系、旋转约定也必须在 physics 与 renderer 之间固定。

稳定堆叠依赖 substep、solver iteration 与 warm starting
   大 ``dt`` 会放大穿透和约束残差；substep 降低每次预测位移；iteration 让接触约束在物体链中继续传播；warm starting 复用上一 step 的接触冲量，加快静止接触收敛。箱体堆轻微抖动时，这几项比继续改材质摩擦更值得先查。

Sleeping 是稳定性与性能机制
   长时间低能量刚体可退出主动求解集合，减少 CPU/GPU 成本并压住微小数值噪声。外力、碰撞或显式速度修改应唤醒相关 body。睡眠阈值过高会让物体过早冻结，过低则会让大量静止对象持续参与 solver。

CCD 解决高速物体在离散步长中的穿透
   当单 step 位移大于薄障碍厚度时，离散 overlap 可能完全错过碰撞。Continuous Collision Detection 使用 swept shape、TOI 或 shape cast 在时间区间内寻找首次接触。CCD 应只给高速或关键对象使用，因为它会增加查询与排序成本。

反馈应使用 solver 证据而不是渲染位移猜测
   撞击粒子、声音和震动更适合由 contact normal impulse、relative speed 等求解结果驱动。渲染位置经过插值，直接用相邻渲染帧位置差估算撞击强度会受刷新率和插值污染。

关键路径
--------

一帧刚体模拟：

::

   input force / torque
   → fixed physics step
   → integrate velocity
   → predict transform
   → broad phase candidates
   → narrow phase manifold
   → contact / joint solver
   → corrected velocity + transform
   → contact / trigger events
   → save physics snapshot
   → render interpolation
   → visible transform

接触求解：

::

   contact point + normal
   → relative velocity at contact
   → normal effective mass
   → normal impulse
   → friction tangent impulse
   → restitution when impact is fast enough
   → write linear / angular velocity
   → iterate across all contacts

稳定性排查：

::

   unit scale / body size / mass range
   → fixed dt / substep
   → broad phase pair
   → contact manifold stability
   → solver iteration / warm start
   → friction / restitution / damping
   → sleeping
   → CCD for remaining high-speed cases

概念辨析
--------

* **Force 与 Impulse**：force 在时间内积分，impulse 直接修改速度；碰撞通常属于后者。
* **Broad Phase 与 Narrow Phase**：前者保守缩小候选集，后者才计算真实接触几何。
* **Contact Manifold 与 Contact Event**：manifold 服务 solver，event 服务 gameplay/VFX；二者都可来自同一次碰撞，但消费者不同。
* **Physics Transform 与 Render Transform**：前者是固定步长权威状态，后者可以是插值结果。
* **Interpolation 与 Extrapolation**：插值使用已知前后快照，稳定但略有延迟；外推猜测未来状态，响应快但误差更大。
* **Substep 与 Solver Iteration**：substep 缩小时间步；iteration 在同一子步内反复求解约束，两者解决的误差来源不同。
* **Sleeping 与 Static Body**：sleeping body 仍是动态对象，只是暂时不求解；static body 从设计上就不参与动态积分。
* **Discrete Collision 与 CCD**：前者只检查离散时刻，后者检查运动时间区间，主要用于 tunneling。

本章结论
--------

刚体模拟应按“外力—固定时间步—碰撞候选—接触流形—冲量求解—物理 transform—渲染插值”理解。抖动先查尺度、dt、manifold、iteration 和 warm starting，穿透先查单步位移与 CCD，反馈则直接使用 solver 的 contact impulse。只要物理状态、事件和渲染 transform 保持明确边界，刚体问题就能从画面症状沿数据路径定位到具体阶段。