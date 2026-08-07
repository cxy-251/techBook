第108章：CUDA 图形计算执行模型
==============================

核心知识点
----------

CUDA 是 NVIDIA GPU 上的通用计算执行模型
   Host 代码负责设备选择、资源准备、kernel launch、同步和错误处理；Device 代码以大量线程执行同一 kernel。它适合粒子、体素、图像、网格属性、AI 后处理和离线烘焙等高并行任务。

图形工程中 CUDA 的价值在于“计算结果留在 GPU”
   最理想路径是 CUDA kernel 写共享 buffer/image，后续 graphics pass 直接消费。若每帧完整 readback 到 CPU，再重新上传，PCIe/系统互连与同步等待会吞掉计算收益。

Grid、Block、Thread 是逻辑线程层级
   一次 kernel launch 产生一个 Grid，Grid 由多个 Block 组成，Block 内包含多个 Thread。常见线性索引为 ``blockIdx.x * blockDim.x + threadIdx.x``，通常让一个线程对应一个粒子、像素或体素。

Warp 是硬件调度的重要粒度
   NVIDIA GPU 常以 32 线程 warp 调度。Block size 通常从 128/256 等 warp 倍数开始测试，但最终取值受 register、shared memory、occupancy 和访存模式共同约束。

Memory Coalescing 是高优先级优化项
   相邻线程访问相邻 global memory 地址，更容易合并成较少的 memory transaction。粒子/顶点数据应尽量连续排列，避免同一 warp 中大量离散随机访问。

Occupancy 只表示隐藏延迟的能力，不等于性能
   更高 occupancy 可能帮助隐藏 memory latency，但 register spilling、shared memory 占用和额外线程调度都可能抵消收益。必须结合 memory throughput、stall reason 和 kernel time 判断。

Shared Memory 用片上容量换取 Global Memory 流量
   Tile/filter/reduction 等存在局部数据复用的任务适合先把数据搬入 shared memory。它的收益来自减少重复 global load，成本是占用每个 SM 的 shared memory budget，并可能降低可驻留 block 数。

Warp Divergence 会降低同一 Warp 的有效吞吐
   大量线程在同一 warp 内走不同控制分支，会使不同路径分批执行。尾部边界判断通常影响有限；按粒子类型、材质类型产生的大规模分支更需要通过数据分组或 kernel 拆分治理。

Device Query 应形成 Compute Capability Profile
   启动时记录 device ordinal、compute capability、warp size、最大 block、shared memory、global memory、统一寻址和 graphics interop 能力。Render/compute scheduler 根据 profile 选择 CUDA path、graphics compute path 或 CPU fallback。

Kernel Launch 的错误与执行错误要分开检查
   Launch 后先检查参数与配置错误，再在调试路径用同步或 event 捕获异步执行错误。正确性建立后，应把 ``cudaDeviceSynchronize`` 这类全局同步收窄到 stream event 或外部同步对象。

Graphics Interop 的核心是共享资源的所有权和时间顺序
   CUDA 写 shared buffer 时 graphics 不能同时读取；graphics 消费前必须确认 CUDA 写入完成并可见。OpenGL/D3D11 常见 register-map-unmap，Vulkan/D3D12 更适合 external memory + external semaphore。

双缓冲可以用一帧延迟换取更少同步
   当前帧 graphics 读 Buffer A，CUDA 同时更新 Buffer B，下一帧交换角色。它降低当前帧硬等待，但引入固定一帧数据延迟和更多 GPU memory。

Profiling 要同时看 Kernel 和 Frame Timeline
   Nsight Compute 类工具回答 occupancy、memory throughput、stall、branch、register；系统级 timeline 回答 CUDA 是否延迟 graphics、interop wait 是否过长、readback 是否阻塞 CPU。最终优化目标是整帧更快，而非某个 kernel 指标更漂亮。

关键路径
--------

CUDA 粒子更新：

::

   CPU frame data
   → query/select CUDA device
   → shared/device particle buffer
   → launch kernel grid/block/thread
   → kernel updates particle state
   → CUDA completion/event
   → graphics acquire/read buffer
   → draw particles
   → present

优化定位：

::

   verify output correctness
   → frame timeline
   → kernel launch / copy / sync / render consume
   → memory throughput / coalescing
   → occupancy / registers / shared memory
   → divergence / stall reason
   → compare final frame time

互操作：

::

   graphics creates shareable resource
   → CUDA imports/registers resource
   → graphics releases ownership / signals
   → CUDA waits and writes
   → CUDA signals completion
   → graphics waits/acquires
   → render consumes

概念辨析
--------

* **Grid、Block 与 Thread**：Grid 是一次 launch 的全部线程，Block 是局部分组，Thread 是逻辑执行单元。
* **Block Size 与 Warp Size**：block 是程序员配置的工作组，warp 是硬件实际调度粒度；block 通常包含多个 warp。
* **Occupancy 与 Utilization**：occupancy 描述驻留 warp 比例，utilization 描述执行资源是否真正繁忙，二者不同。
* **Shared Memory 与 Global Memory**：前者容量小、延迟低、按 block 共享；后者容量大，是多数 GPU 数据的长期存储。
* **CUDA Compute 与 Graphics Compute Shader**：CUDA 是 NVIDIA 通用计算 runtime，compute shader 更直接属于 Vulkan/D3D/Metal/WebGPU render graph。
* **Interop 与 Readback**：interop 让 GPU 资源跨 API 共享，readback 把 GPU 数据搬回 CPU；实时路径应优先避免后者。

本章结论
--------

CUDA 图形计算应按“Device Profile—Grid/Block/Thread—Memory Access—Kernel—Interop Sync—Graphics Consume”理解。Kernel 慢先查访存、occupancy 和 divergence；整帧慢则优先查 copy、全局同步和 graphics/CUDA 互相等待。CUDA 在实时图形中的核心价值，不是单独把算法搬到 GPU，而是让高并行数据在 GPU 内持续更新并被渲染阶段直接消费。