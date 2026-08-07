第063章：粒子系统
================

核心知识点
----------

粒子系统是一条状态驱动的数据管线
   Event 产生 spawn 请求，emitter 写初始状态，update 推进生命周期，alive list 收集仍有效粒子，sort/binning 处理透明顺序，draw pass 再把状态展开成 billboard、mesh、trail 或其它视觉表达。

Emitter 决定生成规则，Particle State 保存运行时最小状态
   常见 emitter 参数包括 spawn rate、burst、位置、方向锥、速度、lifetime 和随机种子；粒子状态常包含 position、velocity、age、lifetime、color/size 驱动参数、rotation 和 flags。字段越多，state buffer 带宽越高。

生命周期用归一化时间驱动属性变化
   ``t = age / lifetime`` 可以查询 color、size、alpha、rotation、frame index 等 curve/gradient。运行时只保存少量动态状态，美术曲线可压成纹理或常量表在 GPU 上求值。

Spawn rate 必须与时间步一致
   持续发射应按 ``deltaTime`` 积累，而不是每帧固定生成。否则帧率变化会改变粒子密度。Burst 则是离散事件，应通过稳定 event/spawn command 进入粒子系统。

Alive List 是 GPU 粒子系统的关键中间结果
   大粒子池不应全部进入 sort 和 draw。Update/compaction 只把存活粒子的 index 写入紧凑列表，后续排序和绘制都围绕 alive set 工作。

GPU-driven 的核心是让数量变化留在 GPU 闭环
   State buffer、free list、alive list、sort key 和 indirect args 由 compute pass 更新。CPU 不应每帧 readback alive count 再决定 draw 数量，而应由 GPU 直接写 indirect argument buffer，图形 pass 消费该结果。

Barrier 是粒子正确性的一部分
   Compute 写完 state/alive/indirect args 后，draw 前必须建立 storage-write 到 vertex/storage/indirect-read 的可见性。粒子数量正确但没有绘制时，应优先检查 indirect args 内容与资源状态。

透明排序应只服务真正需要顺序的粒子
   Alpha blend 烟雾通常要远到近排序；additive 火花顺序依赖弱，可按 emitter/tile 分桶；opaque mesh debris 可进入普通深度管线。把所有粒子统一全量排序会浪费大量 GPU 时间。

Soft Particle 用场景深度消除 billboard 与几何硬交界
   Fragment 读取 scene depth，与粒子自身线性深度比较，根据距离衰减 alpha。它只修复几何交叉边缘，不解决透明粒子之间的排序，也不等于真实体积碰撞。

碰撞模型要与视觉目标匹配
   平面/高度场适合地面火花，screen-depth collision 适合相机可见表面，SDF 适合需要三维距离和法线的烟雾/能量场，mesh debris 可交给更精确的 physics proxy。精度越高，采样和同步成本越大。

Memory Pool 决定规模稳定性
   固定容量池便于控制显存和 descriptor。池满时需要明确优先级策略：丢弃远处或低优先级 spawn、缩短 lifetime、降低烟雾数量，并记录 requested/accepted/dropped/alive 峰值。

粒子瓶颈要区分 update 与 draw
   Compute 侧主要受 state buffer、原子、compaction、sort 影响；graphics 侧主要受 billboard 展开、texture fetch、透明 overdraw、blend 和 render-target bandwidth 影响。粒子数增加后哪一个 pass 先变慢，决定优化方向。

关键路径
--------

一帧粒子：

::

   gameplay / animation event
   → spawn command
   → emitter initialization
   → particle state pool
   → compute update
   → lifetime / force / collision
   → alive compaction
   → optional sort / binning
   → indirect args
   → transparent / mesh draw

GPU-driven：

::

   event buffer + free list
   → spawn compute
   → barrier
   → update + alive list
   → optional sort keys
   → write indirect args
   → barrier to indirect/vertex read
   → draw indirect

排查：

::

   requested spawn / accepted spawn
   → alive count
   → state position / age debug
   → sort key / bin
   → indirect draw args
   → blend / depth / soft factor
   → overdraw / GPU timing

概念辨析
--------

* **Emitter 与 Particle**：emitter 是生成规则和资产，particle 是运行时实例状态。
* **Alive List 与 State Pool**：state pool 是容量，alive list 是本帧真正参与后续工作的紧凑集合。
* **CPU Particle 与 GPU Particle**：前者逻辑灵活、适合少量复杂对象；后者适合海量同构更新并减少 CPU 提交。
* **Additive 与 Alpha Blend**：additive 对排序不敏感，alpha blend 顺序依赖明显，不能使用同一排序预算。
* **Soft Particle 与 Collision**：soft particle 只改变交界处 alpha；collision 会真正修改粒子位置或速度。
* **Depth Collision 与 SDF Collision**：前者只知道当前可见深度，后者提供场景空间距离信息。
* **高粒子数与高成本**：真正瓶颈可能是透明覆盖面积而不是粒子 count，因此应同时看 alive 数和 overdraw。

本章结论
--------

粒子系统应按“event—spawn—state—update—alive—sort/bin—indirect draw”理解。大规模实时效果的关键不是把所有逻辑都搬到 GPU，而是让数量变化、存活筛选和绘制参数在 GPU 内闭环，并对排序、碰撞和透明 overdraw 按视觉重要性分级。遇到性能或画面问题时先分离 spawn、compute、sort、draw 四段，再检查 buffer、barrier、blend、depth 和 pool 上限，就能把复杂 VFX 还原成可验证的数据路径。