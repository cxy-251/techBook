第110章：Compute Shader 模式
===========================

核心知识点
----------

Compute Shader 是 Render Graph 中的通用 GPU 工作阶段
   它不依赖固定的顶点装配或光栅化输入，而是由 dispatch 网格启动大量 invocation，显式读写 storage buffer、storage image/UAV、texture、sampler 和常量数据。

Compute 的第一问题是“一个线程负责什么”
   粒子更新可一线程一粒子，图像处理可一线程一像素，体数据可一线程一 voxel。线程映射越贴近数据布局，索引、边界检查和连续访存越简单。

GPU 内部闭环决定 Compute 的工程价值
   Compute 写出的 buffer/image 若直接被 draw、indirect、postprocess 或后续 compute 消费，就能减少 CPU 往返。频繁 readback 会破坏异步流水线并放大 frame latency。

Map 是最基础的数据并行模式
   输入与输出规模近似一致，每个线程独立更新一个元素。粒子、顶点属性、颜色校正和简单仿真都属于此类，重点是边界保护、连续访存和低分支。

Stencil/Filter 模式依赖邻域读取
   Blur、edge、fluid grid 等任务让一个输出读取多个邻居。数据复用高时可将 tile + halo 载入 shared/group memory，减少重复 global/texture 访问。

Reduction 把大量输入收敛为少量结果
   自动曝光、最大值、统计计数等通常先做 workgroup-local reduction，再用第二次 dispatch 合并。一个 dispatch 内工作组之间没有可移植的全局 barrier。

Prefix Sum/Scan 是 Compaction 的基础
   可见性标记、存活粒子、LOD bucket 等稀疏结果可先 scan 得到目标 offset，再写入紧凑列表。它增加中间 buffer 与多阶段 dispatch，但能让后续工作只处理有效元素。

Scatter/Gather 的关键是写冲突和访问离散度
   Gather 固定写自己的输出，从多个位置读取；Scatter 根据数据决定写入位置，常需要 atomic、预计算 offset 或分桶。高竞争 atomic 会把吞吐压到热点位置。

Indirect Preparation 把 Compute 结果变成 Draw/Dispatch 输入
   Compute 可以写 draw arguments、draw count、instance list 或 dispatch arguments。资源必须声明相应 usage/state，后续 indirect consumer 前还要建立写后读同步。

显式 API 的 Compute 路径可以统一成五步
   创建读写资源 → 定义 descriptor/root binding → 创建 compute pipeline → dispatch → barrier/transition 到消费者。Vulkan 与 D3D12 名称不同，资源合同相同。

Barrier 是 Producer/Consumer 合同的一部分
   Compute 写 storage/UAV 后，vertex/fragment/indirect/后续 compute 读取时必须声明正确 stage/access/resource state。Barrier 太宽会压缩并行空间，缺失则产生旧数据或 hazard。

Workgroup Size 同时影响 Occupancy、Register、Shared Memory 与访存
   128/256 线程常是线性任务的起点，不是固定答案。二维图像更适合二维 group；三维体数据适合三维 group。最终应以有效线程比例、memory throughput 和 profiler 数据决定。

Shared Memory 只在存在数据复用时有价值
   把每个元素只访问一次的数据先复制进 shared memory，往往只是增加 copy/barrier；邻域滤波、tile reduction、局部 histogram 等重复访问场景才更容易获益。

Readback 应限制在 Debug/Profiling/低频统计路径
   CPU 检查 GPU buffer 通常需要 copy 到 readback/staging 并等待 fence。每帧同步读取会把 GPU pipeline 串行化，应延迟几帧或只采样少量数据。

Compute 优化先定位责任层级
   先确认慢在 dispatch、memory、barrier、queue wait、readback 还是后续 draw；再调 workgroup、layout、shared memory、分支。直接改 ``numthreads`` 很难解决错误层级的瓶颈。

关键路径
--------

Compute → Graphics：

::

   frame constants + input buffer
   → bind compute pipeline/resources
   → dispatch workgroups
   → storage/UAV output
   → barrier / state transition
   → graphics binds output
   → draw

模式选择：

::

   fixed-size independent output? → Map
   → neighborhood reuse? → Stencil / tiled shared memory
   → many-to-one? → Reduction
   → sparse variable output? → Scan + Compaction
   → indexed/random write? → Scatter / atomic
   → GPU-generated commands? → Indirect Preparation

瓶颈定位：

::

   GPU timestamp around dispatch
   → valid/effective thread count
   → memory bandwidth / cache
   → occupancy / register / shared memory
   → divergence / atomics
   → barrier / queue idle
   → readback wait
   → downstream render cost

概念辨析
--------

* **Compute Shader 与 CUDA/OpenCL**：Compute Shader 属于图形 API/渲染图，CUDA/OpenCL 是独立通用计算 runtime；数据并行模型相似，资源和提交对象不同。
* **Global ID 与 Local ID**：global ID 定位整个 dispatch 中的数据元素，local ID 定位 workgroup 内线程。
* **Workgroup Barrier 与 Global Barrier**：前者只同步同一工作组，跨组依赖通常需要结束 dispatch 后再建立全局资源同步。
* **Storage Buffer 与 Indirect Buffer**：一个表示 shader 可读写用途，一个表示命令参数用途；同一资源可在 API 允许时按阶段切换用途。
* **Atomic Append 与 Scan Compaction**：前者实现简单但可能竞争，后者步骤多但更容易获得稳定连续输出。
* **Occupancy 与 Throughput**：高 occupancy 只是延迟隐藏条件之一，最终吞吐还受访存、指令和同步约束。

本章结论
--------

Compute Shader 应按“Data Mapping—Parallel Pattern—Resource Binding—Dispatch—Barrier—Consumer—Evidence”理解。结果错误先查线程索引、边界和资源状态；GPU 慢则区分带宽、occupancy、atomic、barrier 与下游消费。高质量 compute 代码的核心不是启动最多线程，而是让数据布局、线程映射、同步范围和下一阶段消费保持同一条可推导资源路径。