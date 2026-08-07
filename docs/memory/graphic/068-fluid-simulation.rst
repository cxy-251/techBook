第068章：流体模拟
================

核心知识点
----------

流体模拟的基础状态是速度场、压力场与被输运的物质
   速度场 ``u`` 决定烟雾密度、温度、水体标记和粒子如何移动；压力场用于修正不可压缩性；density、temperature、fuel、foam 等是被 advection 搬运或派生出的可见状态。最终画面只是这些 simulation state 的渲染结果。

不可压缩约束的核心是让散度接近零
   ``∇·u`` 描述局部流入与流出是否平衡。典型网格流体会先得到带散度的临时速度，再解压力 Poisson 方程，最后从速度中减去压力梯度完成 projection。烟雾“越算越胖”、液体莫名缩水时，应优先检查 divergence 与 pressure solve。

Advection 负责搬运速度和标量场
   Eulerian 网格通常沿速度反向追踪上一时刻采样位置；粒子方法直接积分粒子位置。数值 advection 容易耗散高频细节，因此涡旋变钝、烟雾变成均匀雾团时，先看 velocity field 是否已经失去细节，再决定是否调 shader。

Viscosity 与数值耗散不是同一件事
   真实粘性描述动量扩散，数值耗散来自离散算法本身。提高 viscosity 会让速度差更快被抹平；低阶 advection 即使 viscosity 很低也可能迅速损失涡旋。Vorticity confinement 常用于补回部分被数值耗散吃掉的小尺度旋转。

Eulerian Grid 适合连续体积
   固定网格或 3D texture 很适合烟雾、火焰、雾和低分辨率水体，因为 velocity、pressure、density 都可以直接作为纹理 pass 计算，并自然接入 volume raymarch。代价是内存和计算量随三维分辨率快速增长。

粒子方法适合自由表面与飞溅
   SPH/PBF 直接在粒子邻域上估计密度和约束，适合水滴、喷泉和局部液体；粒子能自然分裂、飞散和聚集，但邻域搜索会成为主要成本。泡沫和喷溅通常更适合作为粒子派生状态，而不是强行塞进连续网格。

PIC 与 FLIP 把粒子细节和网格压力求解组合起来
   粒子携带物质与速度，网格负责压力 projection。PIC 直接从网格取新速度，稳定但耗散强；FLIP 把网格速度变化量加回粒子，细节更丰富但噪声更大。实际液体常在二者之间混合。

Boundary Condition 是流体正确性的底线
   墙体、地面、开放边界和移动障碍物决定速度法向分量如何处理、流体能否穿出域外以及压力条件如何设置。漏液、穿墙和边界吸附问题应先查 obstacle/SDF、坐标空间和边界更新时序。

CFL 条件约束时间步与空间尺度
   当单步内信息跨越过多 cell 时，advection、碰撞和压力求解都会变得不稳定。高速局部区域更需要 substep 或自适应时间步。继续增加 pressure iteration 不能替代错误的 timestep。

Surface Reconstruction 是粒子液体到渲染表面的桥梁
   粒子可以重建成隐式场/等值面，也可以用 screen-space depth/thickness 生成实时水面。Simulation 粒子位置正确而水面边缘错位时，应优先查重建和过滤，而不是回头改 solver。

Volume Rendering 是网格烟雾的主要可见路径
   Density/temperature volume 经过 raymarch、lighting、transmittance 和 composite 变成最终颜色。Velocity field 中涡旋正确但最终烟雾仍显得糊，问题更可能位于体积采样、低分辨率 upsample 或透明合成。

泡沫是二级视觉状态，不承担主液体守恒
   Foam 常由高速、曲率、碰撞冲量或自由表面扰动触发，再以短生命周期粒子、mask 或 sprite 表达。泡沫与水面漂移时，应检查它们是否消费同一 simulation version 和同一插值时间点。

流体管线需要显式资源同步
   Compute pass 写 velocity、pressure、density 或 particle buffer，后续 simulation/render pass 再读取。Frame graph 必须表达写后读依赖；跨 queue 时还要处理 barrier/fence。画面偶发旧状态或半更新状态时，同步问题和 solver 问题要分开检查。

关键路径
--------

Eulerian 网格流体：

::

   external force / source
   → velocity advection
   → viscosity / diffusion
   → divergence
   → pressure solve
   → projection
   → advect density / temperature
   → boundary enforcement
   → volume texture
   → raymarch / composite

粒子/混合液体：

::

   particle positions + velocity
   → neighbor search / grid transfer
   → density / pressure constraint
   → pressure solve on particles or grid
   → update particle velocity
   → collision / boundary
   → surface reconstruction
   → water material + foam particles

问题排查：

::

   simulation velocity / density / pressure debug
   → divergence / boundary
   → timestep / CFL / substep
   → pressure iteration
   → advection dissipation / vorticity
   → resource synchronization
   → surface / volume reconstruction
   → final transparent composite

概念辨析
--------

* **Velocity Field 与 Density Field**：前者负责运动，后者通常只是被搬运的可见介质。
* **Pressure 与 Density**：网格不可压缩流体中的 pressure 主要是约束变量，不等于烟雾 density 或液体质量密度。
* **Advection 与 Diffusion**：advection 随速度搬运状态，diffusion/viscosity 在邻域间扩散状态。
* **Eulerian 与 Particle**：前者状态固定在空间网格，后者状态跟随移动粒子。
* **PIC 与 FLIP**：PIC 更稳定但耗散，FLIP 保留细节但更容易噪声和粒子分布不均。
* **Simulation State 与 Render Surface**：水面 mesh、泡沫 sprite、烟雾颜色都是派生显示结果，不是 solver 的全部状态。
* **Pressure Iteration 与 Substep**：iteration 改善同一步内 pressure 收敛，substep 缩短时间推进尺度，作用不同。

本章结论
--------

流体模拟应按“速度/物质表示—advection—散度—pressure projection—边界—渲染映射”理解。烟雾和连续体积优先网格，飞溅和泡沫优先粒子，大型液体常用 PIC/FLIP 混合。稳定性先查 CFL、boundary 和 pressure，再查细节耗散；画面问题则先证明 simulation state 是否正确，再进入 surface reconstruction、volume raymarch 和资源同步。这样才能把数值问题和渲染问题真正分开。