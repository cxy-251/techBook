第070章：模拟驱动渲染
====================

核心知识点
----------

模拟驱动渲染的核心是跨系统数据契约
   Solver 负责内部状态，Renderer 只应消费面向显示整理过的 render payload。刚体 solver 维护速度、接触和约束，渲染侧只需要 transform、material id 和可选 velocity；布料 solver 维护约束节点，渲染侧需要变形后 vertex/normal/tangent；流体 solver 维护 pressure/velocity，volume pass 更关心 density、temperature 与散射参数。

Solver State 与 Render Payload 应明确分层
   Solver state 可以包含邻居表、约束残差、pair cache、pressure、迭代临时量等内部数据；render payload 则应说明字段、坐标空间、生命周期和消费者 pass。Renderer 不理解 solver 内部细节，Simulation 也不应直接控制 draw call。

Render Payload Build 是跨系统边界
   Simulation step 完成后，需要把 SoA/内部缓存整理成 instance buffer、deform vertex buffer、particle attributes、volume texture 或 debug buffer。这个步骤决定哪些状态真正进入 GPU，也决定后续 bandwidth 与资源生命周期。

CPU 模拟主要面对上传与版本管理
   CPU 物理产生 transform 或少量顶点后，需要写入 ring/double-buffered GPU resource。GPU 仍在读取的 buffer 不能被当前帧 CPU 覆盖。Frame index、offset、staging/upload heap 和 fence 是这条路径的主要正确性证据。

GPU 模拟主要面对资源状态与执行顺序
   Compute 写 particle/deform/volume buffer，graphics pass 随后读取。必须显式建立 compute-write → shader/vertex-read 依赖。跨 graphics/compute queue 时还需要 semaphore/fence/queue ownership。偶发闪烁和旧帧内容常来自这里，而不是 shader 数学。

Readback 应留在低频诊断路径
   GPU 侧可先 reduction 得到 alive count、最大速度、约束残差等少量统计，再延迟若干帧回读。逐帧 readback 大型 simulation buffer 会迫使 CPU/GPU 同步，既破坏并行，也让调试工具本身制造性能问题。

Async Compute 是否有效取决于依赖图
   把 simulation dispatch 放到 compute queue 并不会自动变快。只有它能与 shadow、graphics 或其它 pass 真正重叠，并且消费者足够晚，才可能缩短 frame time。最终判断应看 queue timeline、等待点和总帧时间，而不是看 pass 所属队列名称。

固定模拟步长与可变渲染刷新率需要快照插值
   Render frame 可以在 ``previousState`` 与 ``currentState`` 之间用 ``alpha`` 插值。刚体 position 线性插值、rotation 使用 slerp，粒子和布料也可基于稳定 id 插值。插值只解决采样时间差，不会修复 solver 发散。

Temporal Artifact 与 Simulation Error 必须区分
   原始 fixed-step state 已经跳变，问题属于 solver/input；原始 state 稳定但插值后跳变，问题属于 snapshot/id/time alignment；插值稳定而 TAA 后 ghosting，则应查 motion vector、history rejection 与透明排序。

Motion Vector 必须来自真实最终变形
   布料、粒子、碎片和模拟角色的 velocity/motion 应与渲染看到的最终位置一致。如果 motion vector 使用 simulation 前、skinning 前或错误帧的坐标，TAA、motion blur 和 temporal upscaler 会把同步问题放大成拖影。

Debug Overlay 应是正式的数据消费者
   风场箭头、粒子密度、约束残差、碰撞法线、cell id、同步延迟等 debug view 都应读取明确 payload，而不是临时从最终画面猜状态。调试层与正式渲染层使用同一时间点和坐标空间，才能作为证据。

不同模拟对象可以共享同一帧路径
   粒子通常输出 state/alive/indirect args；布料输出 deform vertices 与 velocity；流体输出 density/velocity texture；刚体输出 instance transform。实现细节不同，但都遵循“input → simulation → payload → sync → render → temporal/output”的公共结构。

关键路径
--------

CPU 模拟到渲染：

::

   gameplay / physics input
   → fixed simulation step
   → solver state
   → render payload build
   → ring / double-buffer upload
   → graphics reads payload
   → draw / debug overlay

GPU 模拟到渲染：

::

   input constants / events
   → compute simulation
   → particle / deform / volume resource write
   → barrier / queue dependency
   → graphics or volume pass read
   → motion vector / temporal pass
   → final frame

视觉稳定性排查：

::

   freeze input + timestep
   → inspect raw fixed-step state
   → inspect previous/current snapshot + alpha
   → inspect render payload
   → inspect writer/reader/barrier/frame index
   → inspect motion vector
   → inspect temporal history / rejection
   → final composite

概念辨析
--------

* **Solver State 与 Render Payload**：前者服务求解正确性，后者服务渲染消费和跨系统契约。
* **Upload 与 Readback**：upload 把 CPU 结果送 GPU，readback 把 GPU 结果拉回 CPU；后者更容易造成同步等待。
* **Barrier 与 Fence**：barrier 主要表达 GPU 资源访问顺序，fence/semaphore 常用于更大范围执行或跨队列同步，具体 API 表达不同。
* **Double Buffer 与 History Buffer**：double/ring buffer 主要避免读写覆盖；history buffer 保存上一帧算法结果用于 temporal reuse，目的不同。
* **Simulation Jitter 与 Render Jitter**：前者来自 solver 或输入，后者可能来自插值、快照选择、TAA jitter 或错误 motion vector。
* **Async Compute 与并行收益**：放到异步队列只是调度选择，真正收益取决于是否有可重叠工作和较少等待。
* **Debug Payload 与 Gameplay Event**：debug payload 服务可视化诊断，gameplay event 服务逻辑；两者可以来自同一 simulation，但生命周期不同。

本章结论
--------

模拟驱动渲染应按“输入—solver state—render payload—GPU 资源—同步—render pass—temporal output”理解。闪烁先查 writer/reader、buffer 版本和 barrier，跳动先区分 solver state 与 interpolation，拖影再查 motion vector 和 history。只要 simulation 内部状态与渲染契约保持分层，并让每个 payload 的写者、读者、时间点和坐标空间都可追踪，刚体、布料、粒子和流体就能使用同一种工程方法排查。