第069章：碰撞检测
================

核心知识点
----------

碰撞检测是一条分阶段过滤管线
   系统要连续回答“可能相交吗、真的相交吗、何时相交、接触在哪里”。稳定流程通常是 collision primitive → layer filter → broad phase → narrow phase → contact manifold → CCD/TOI → solver。最终画面中的穿墙、抖动和卡住，必须沿这条链回查。

渲染 Mesh 与 Collision Primitive 应解耦
   高精度视觉模型不适合直接用于所有碰撞。角色常用 capsule，弹丸用 sphere/swept sphere，箱体用 OBB 或 convex hull，静态关卡用 triangle mesh，粒子和碎片使用更粗代理。碰撞形状的目标是稳定交互，不是复刻所有视觉细节。

不同 Primitive 在精度、稳定性和成本之间取舍
   Sphere 测试便宜且旋转无关；AABB 最适合 broad phase；OBB 更贴合旋转箱体；capsule 提供连续圆滑法线，适合角色控制；convex hull 可用 GJK/EPA 处理不规则凸形；triangle mesh 精确但更适合静态环境。

Broad Phase 的职责是保守缩小候选集
   Sweep-and-Prune 利用轴向排序和 temporal coherence；BVH 适合层次裁剪和静态 mesh；Uniform/Hash Grid 适合大量尺寸接近的局部对象。Broad phase 可以产生 false positive，但不能轻易漏掉真实接触。

World AABB 是多数 Broad Phase 的统一代理
   无论内部 shape 是 capsule、OBB、convex hull 还是 mesh，通常先生成世界 AABB 插入空间结构。动态对象 transform 更新后必须同步更新 proxy；AABB 过大则会造成 pair explosion，过小则会漏候选。

Collision Layer 应尽早过滤无关交互
   角色、装饰粒子、弹丸、触发器、布料和车辆不需要互相全量测试。Layer matrix 越早生效，broad phase、narrow phase、pair cache 和 solver 的成本越低。运行时修改 layer 时还要正确失效旧 pair。

Narrow Phase 才计算真实接触几何
   对候选 shape 组合执行 sphere/capsule/SAT/GJK/EPA/triangle 等精确测试，输出 contact point、normal、penetration/separation 和 feature id。稳定接触依赖连续法线与特征匹配，而不是每帧重新产生完全不同的接触点。

Contact Manifold 是碰撞检测与 Solver 的接口
   多个接触点共同支撑箱体、车辆和角色。Manifold 应保存稳定 feature id，便于跨帧匹配并 warm start。单点接触在堆叠和面接触中更容易造成旋转抖动。

Pair Cache 提升时间连续性
   上一 step 已接近的对象通常下一 step 仍接近。缓存 pair 和 contact feature 可以减少重复创建、帮助 warm starting，并让 resting contact 更稳定。对象分离、销毁、sleep 或 layer 变化时必须正确失效。

CCD 负责高速对象的时间区间查询
   当物体单步位移大于障碍厚度时，离散 overlap 可能完全错过。Sphere sweep、capsule sweep、shape cast、swept AABB 与 Time of Impact 用来寻找 ``[t0,t1]`` 中第一次有效接触。弹丸和快速角色冲刺是典型使用者。

Swept AABB 让高速对象先进入候选集
   即使 narrow phase 使用精确 TOI，broad phase 若只看终点 AABB，也可能根本没有候选。高速物体应把上一 transform 与预测 transform 的包围范围合并成 swept proxy，再进入空间结构。

Debug Draw 应覆盖 Primitive、Pair 与 Contact 三层
   仅画碰撞盒不足以定位问题。应同时显示 broad-phase candidate、confirmed contact、normal、penetration、TOI、velocity 和 swept path。这样才能区分“没进入候选”“精确测试失败”“solver 没消费”三类问题。

性能调试先看数量级
   Active body、proxy update、candidate pair、narrow-phase test、CCD cast、manifold、solver island 等计数器比单个毫秒数更容易解释成本来源。爆炸碎片导致帧时间骤升时，先看 pair 数是否指数式增加。

关键路径
--------

离散碰撞：

::

   body transform
   → collision shape / world AABB
   → layer filter
   → broad phase
   → candidate pairs
   → narrow phase shape test
   → contact manifold
   → solver / event / debug draw
   → corrected render transform

高速对象：

::

   previous transform + predicted transform
   → swept AABB
   → broad-phase candidates
   → shape cast / TOI
   → earliest valid hit
   → clamp motion to hit time
   → manifold / response

问题排查：

::

   collision proxy matches visual object
   → world transform / time point
   → broad-phase pair exists
   → narrow-phase contact exists
   → normal / penetration / feature stable
   → CCD / TOI if high speed
   → solver response
   → render transform sync

概念辨析
--------

* **Visual Mesh 与 Collision Proxy**：前者服务画面，后者服务稳定交互；二者不要求同样复杂。
* **AABB 与 OBB**：AABB 轴对齐、便宜且适合 broad phase；OBB 更贴合旋转物体，通常用于更精确测试。
* **Broad Phase 与 Narrow Phase**：前者生成保守候选，后者才产生真实 contact。
* **Pair Cache 与 Contact Manifold**：pair cache 记录对象接近关系，manifold 记录具体接触点与法线。
* **Discrete Collision 与 CCD**：前者只看离散状态，后者把运动时间区间纳入查询。
* **Trigger 与 Physical Contact**：trigger 只产生事件，不生成阻止穿透的 solver constraint。
* **Pair Explosion 与 Solver 慢**：候选对暴涨会让后续阶段都变慢，不能只看到 solver 时间高就直接增加线程或 iteration。

本章结论
--------

碰撞检测应按“代理几何—层过滤—broad phase—narrow phase—manifold—CCD—solver”理解。高速漏检先查 swept proxy 与 TOI，角色抖动先查 capsule、接触法线和 manifold，碎片掉帧先查 candidate pair 数与 layer。只要每一层都提供可观察证据，穿墙、卡角、误碰和性能尖峰就能定位到第一处失效的阶段，而不是靠最终 transform 猜原因。