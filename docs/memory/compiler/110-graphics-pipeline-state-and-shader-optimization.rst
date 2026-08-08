第110章：Graphics Pipeline State and Shader Optimization
=========================================================

核心知识点
----------

* Shader optimization 的真实输入不只是 shader source，还包括 pipeline state、resource layout、render-target format、specialization values、目标 GPU 能力和 driver heuristics。
* Graphics pipeline 把 programmable shader stages 与 rasterization、depth/stencil、blend、multisample、vertex layout 等 fixed-function state 组合成一个可执行上下文。
* 同一 fragment shader 在 opaque、alpha-cutout、transparent-blend 等 pipeline 中可能具有不同可观察行为，因此 driver 能做的删除、调度和 early-test 优化也不同。
* Stage linking 可以利用完整 pipeline 的输入输出关系删除未使用 varyings。Fragment stage 不消费某个输入时，vertex stage 对应输出及其上游计算也可能变成 dead code。
* Compile-time defines、shader variants、specialization constants 和 runtime uniforms 代表不同“已知时间点”。越早固定，编译器越容易 constant-fold 和 DCE；越晚固定，运行时灵活性越高。
* Macro/variant 可以生成最专用代码，但会增加 shader/PSO 数量和构建、缓存、调试成本；specialization constant 在 pipeline creation 时固定，常用于在复用 module 与获得常量优化之间折中。
* Uniform 条件通常必须保留多条运行路径，因此不能像 compile-time constant 一样直接删除整个分支及其资源访问。
* Texture sampling 的成本由采样次数、filter/LOD、cache locality、memory layout、derivative requirement 和 branch distribution 共同决定，不能只数源码中的 texture call。
* Fragment derivatives 依赖相邻 invocation 的值变化。把 implicit-LOD sampling 或 derivative 计算放入非一致分支会带来语义或性能约束；必要时应在分支前计算稳定梯度或使用显式 LOD/gradient 路径。
* Divergence 发生在同一 warp/wave 的 invocations 走不同控制路径时。硬件可能串行执行不同分支并屏蔽 inactive lanes，因此动态分支成本取决于分支一致性而不只是分支数量。
* ``discard/clip``、UAV/storage writes、atomics、depth writes 等副作用会限制 early depth/stencil、代码移动和死代码删除。
* Register pressure 与控制流、unrolling、texture latency 隐藏、临时向量数量共同决定 occupancy 和 spill 风险；优化 shader 不能只追求更少 ALU 指令。
* Offline compilation、runtime compilation、pipeline cache 和 shader variant management 共同决定“卡顿发生在哪里”。把更多工作前移可减轻 draw-time 编译，但会增加 build size 与 pipeline count。
* Pipeline cache 缓存的是与 shader、state、driver、GPU 等条件相关的编译结果；状态变化过多会降低复用率，variant explosion 会反向伤害启动与运行体验。
* Shader performance 最终必须用目标设备上的 GPU counters、timing、pipeline statistics 和 capture 工具验证。源码复杂度不是可靠性能指标。

关键路径
--------

Pipeline 编译：

::

   shader source/IR
   + compile-time defines/specialization
   + stage interfaces
   + descriptor/resource layout
   + raster/depth/blend/MSAA state
   + render-target format
   + target GPU
   → pipeline/driver compilation
   → constant folding + DCE + linking
   → target-specific lowering
   → device executable + metadata
   → cache/reuse

Variant 决策：

::

   feature switch
   → compile-time macro? maximum specialization, more variants
   → specialization constant? pipeline-time specialization
   → runtime uniform? fewer variants, dynamic branch remains
   → measure code size + PSO count + runtime cost

Fragment 性能：

::

   input interpolation
   → texture/ALU/control flow
   → derivative/divergence constraints
   → depth/stencil/discard interactions
   → register pressure + occupancy
   → color/depth export
   → measured GPU time

概念辨析
--------

* **Shader source optimization 与 pipeline optimization**：前者只看单个程序，后者还能利用 stage linking、fixed-function state 和 target context。
* **Macro variant 与 specialization constant**：前者在源码/离线编译前固定，后者通常在 pipeline creation 时固定；二者都比普通 uniform 更利于删除代码。
* **Dynamic branch 与 divergence**：有分支不代表一定昂贵；同一 wave/warp 内不同 lanes 走不同路径才形成典型 divergence 成本。
* **Texture instruction count 与 texture cost**：真实成本还取决于 cache、LOD、filter、memory locality 和 latency hiding。
* **Pipeline cache 与 shader source cache**：pipeline cache 通常关联更完整的目标状态和 driver 编译结果，不只是缓存源码文本。

本章结论
--------

Shader 优化的稳定模型是 ``Shader IR + Pipeline State + Resources + Target GPU → Specialized Device Executable``。真正的优化对象不是孤立 shader 文件，而是它所在的完整 pipeline；variant、texture、derivative、divergence、depth/blend、register pressure 与 cache 都必须放回同一个执行上下文测量。