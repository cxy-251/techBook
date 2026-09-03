========================================================================
权重跨设备流式换入换出、即时精度转换与 CastBuffer 机制
========================================================================

.. note:: 前置背景与上下文承接
   在前两节中，我们建立了 GPU 物理显存的拓扑感知（``01_vram_state_and_device_tracking.rst``）与模型级对象生命周期（``02_model_lifecycle_and_loaded_models.rst``）。然而，当面对如 Flux.1 (12B)、SD3 (8B) 或更大规模的生成模型时，即便在单模型独占模式下，模型权重本身的体积也可能超过物理 GPU 显存的总上限（例如在 6GB/8GB 显存设备上运行 16GB 的大模型）。此时，将模型全量加载至显存的传统模式彻底失效。ComfyUI 通过**分层流式权重换入换出（Layer-wise Weight Streaming）**与**即时精度动态强转（On-the-Fly Casting & CastBuffer）**，在物理显存极限受限的场景下实现了任意大模型的稳健推理。本节深入 ``comfy/model_management.py``、``comfy/memory_management.py`` 与 ``comfy/model_patcher.py``，全面剖析权重跨设备传输管道、DMA 异步双缓冲、张量切片直接读取与 CastBuffer 显存复用技术。

------------------------------------------------------------------------

1. 细粒度流式调度物理模型（LowVRAM 与分层切片）
-----------------------------------------------

在常规模式（NormalVRAM/HighVRAM）下，模型换入的最小粒度是“整网（Whole Network）”。而在极端低显存模式（LowVRAM）或动态分层卸载架构下，模型的物理调度粒度细化为**子模块/网络层（Layer/Block Group）**。

其核心物理流水线如下图所示：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                          Host CPU RAM (Pinned Memory / Storage Dtype: FP8/FP16)                    |
   |   [Layer 0 Weights]   [Layer 1 Weights]   [Layer 2 Weights]  ...  [Layer N Weights]                |
   +----------------------------------------------------------------------------------------------------+
              |                       |                       |                       |
      PCIe DMA Stream         PCIe DMA Stream         PCIe DMA Stream         PCIe DMA Stream
              v                       v                       v                       v
   +----------------------------------------------------------------------------------------------------+
   |                         GPU VRAM (Scratchpad / Compute Dtype: BF16/FP16)                           |
   |                                                                                                    |
   |   1. Stream Layer k Weights ===> CastBuffer (FP8 -> BF16 on-the-fly)                              |
   |   2. Compute Layer k Forward(x_k) ===> Activation x_{k+1}                                         |
   |   3. Deallocate / Overwrite Layer k Weights                                                        |
   |   4. Repeat for Layer k+1                                                                          |
   +----------------------------------------------------------------------------------------------------+

1.1 静态驻留 vs 分层流式执行对比
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 静态全量驻留与分层流式执行的物理特性对比
   :widths: 20 40 40
   :header-rows: 1

   * - 评估维度
     - 静态全量加载 (Normal/HighVRAM)
     - 分层流式执行 (LowVRAM / Streaming)
   * - **峰值显存占用**
     - :math:`S_{	ext{weights}} + S_{	ext{activations}}`（通常 > 16GB ~ 24GB）
     - :math:`\max_{l}(S_{	ext{layer\_}l}) + S_{	ext{activations}}`（仅需 2GB ~ 4GB）
   * - **PCIe 带宽依赖**
     - 仅在节点切换时发生单次传输，采样迭代内零 PCIe 流量
     - 每步采样的每个 Layer 均需实时通过 PCIe 总线拉取，高度依赖 PCIe 4.0/5.0 带宽
   * - **算力吞吐率**
     - 纯 GPU 算力瓶颈，吞吐率最高
     - 受 PCIe 传输延迟与 CUDA 流同步开销制约，吞吐率略有下降，但获得无限模型容纳能力

------------------------------------------------------------------------

2. 锁页内存（Pinned Memory）与异步 DMA 传输管道
------------------------------------------------

在 Host CPU 内存与 GPU 显存之间进行数据搬运时，操作系统常规的分页内存（Pageable Memory）无法直接被 GPU 显卡 DMA（Direct Memory Access）控制器访问。CPU 必须先在内存中分配不可换页的物理锁页内存（Pinned Memory），将数据复制进去，再通过 PCIe 总线直接传输至 GPU 显存。

2.1 Pinned Memory 加速机制
~~~~~~~~~~~~~~~~~~~~~~~~~~

ComfyUI 在 Host 侧预分配并维护 Pinned 内存池：

.. math::

   T_{	ext{transfer}} = \frac{S_{	ext{tensor}}}{	ext{Bandwidth}_{	ext{PCIe}}} + T_{	ext{DMA\_overhead}}

.. code-block:: python

    # 启用锁页内存进行非阻塞异步 DMA 传输
    tensor_pinned = tensor_cpu.pin_memory()
    tensor_gpu = tensor_pinned.to(device, non_blocking=True)

通过指定 ``non_blocking=True``，张量传输命令被异步发射至专用的 CUDA 拷贝流（Copy Stream），使得 CPU 可以继续执行后续算子的拓扑解析，而 GPU 计算引擎与 DMA 控制器实现指令级并发。

2.2 锁页内存系统压力与动态脱扣（``free_pins``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

由于 Pinned 内存无法被操作系统内核交换至磁盘 Swap 分区，若长时间锁定过多 Host 内存，将导致操作系统物理内存严重紧缺，进而挤压文件系统页缓存（Page Cache）。

在 ``comfy/model_management.py`` 中，系统设立了针对 Pinned 内存的监控与自愈接口：

.. code-block:: python

    def free_pins(amount=0):
        # 当检测到系统 RAM 水压过高时，主动释放已缓存的 Pinned 内存块
        freed = comfy_aimdo.host_buffer.free_pinned_memory(amount)
        return freed

------------------------------------------------------------------------

3. 即时精度转换与 CastBuffer 复用架构
--------------------------------------

为了在低显存设备上运行先进大模型，业界广泛采用低精度量化存储（如 FP8_E4M3、FP8_E5M2 或 NF4/GGUF）。然而，现代 GPU 的 Tensor Core 在执行注意力机制与深度前向时，直接使用 FP8 容易出现数值下溢（Underflow）或累加舍入误差，通常需要在计算时将张量恢复至 BF16 或 FP16 精度。

3.1 存储精度与计算精度解耦
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. math::

   W_{	ext{compute}} = 	ext{Cast}(W_{	ext{storage}}, 	ext{dtype}=	ext{torch.bfloat16})

若在每一层前向计算时都临时调用 ``tensor.to(torch.bfloat16)``，PyTorch 显存分配器会在每一步频繁执行 ``cudaMalloc`` 与 ``cudaFree``，产生巨量的显存碎片，并引发严重的 CPU-GPU 同步阻塞。

3.2 CastBuffer 原理与实现
~~~~~~~~~~~~~~~~~~~~~~~~~

ComfyUI 设计了专用的 ``CastBuffer`` 环形暂存区。系统在初始化时预分配一块连续的 GPU 显存缓冲块，专门用于承载精度提升后的临时权重：

.. code-block:: python

    class CastBuffer:
        def __init__(self, device, max_size):
            self.device = device
            self.buffer = torch.empty(max_size, dtype=torch.uint8, device=device)
            self.offset = 0

        def get_cast_view(self, tensor, target_dtype):
            required_bytes = tensor.numel() * torch.finfo(target_dtype).bits // 8
            # 在预分配的连续显存切片上直接构造目标类型张量视图
            view = self.buffer[self.offset : self.offset + required_bytes].view(target_dtype).view(tensor.shape)
            # 执行即时精度转换写入
            view.copy_(tensor, non_blocking=True)
            return view

在每个 Prompt 执行完毕后，调度器统一调用 ``comfy.model_management.reset_cast_buffers()`` 重置缓冲指针，彻底杜绝了动态显存申请带来的性能衰减。

------------------------------------------------------------------------

4. 磁盘张量切片直读（TensorFileSlice）
--------------------------------------

在从磁盘 `.safetensors` 文件加载超大模型时，传统方案是将整个权重字典反序列化进 Host 内存，再逐层提取，这会导致两倍于模型体积的 Host 内存瞬时峰值。

ComfyUI 在 ``comfy/memory_management.py`` 中实现了基于文件偏移量（File Offset）的零拷贝直接读取：

.. code-block:: python

    class TensorFileSlice(NamedTuple):
        file_ref: object    # 打开的 safetensors 底层文件句柄
        lock: object        # 线程安全互斥锁
        offset: int         # 该张量在二进制文件中的绝对字节偏移
        size: int           # 张量物理字节长度

    def read_tensor_file_slice_into(tensor, destination, stream=None, destination2=None):
        info = getattr(tensor.untyped_storage(), "_comfy_tensor_file_slice", None)
        if info is None:
            return False

        # 直接通过 OS 级别的 pread / readinto 将磁盘切片载入目标缓冲区
        buf_type = ctypes.c_ubyte * info.size
        view = memoryview(buf_type.from_address(destination.data_ptr()))
        with info.lock:
            info.file_ref.seek(info.offset)
            info.file_ref.readinto(view)
        return True

通过 ``TensorFileSlice``，大模型可以在仅消耗极小句柄元数据的前提下完成惰性流式加载，真正做到“用哪层读哪层”。

------------------------------------------------------------------------

5. 跨设备传输与精度转换技术对照表
----------------------------------

.. list-table:: ComfyUI 权重流动与精度转换关键机制对照
   :widths: 20 25 25 30
   :header-rows: 1

   * - 核心技术机制
     - 物理承载介质
     - 触发时机
     - 系统性能与架构收益
   * - **分层权重流式换入 (Streaming)**
     - PCIe 总线 + Host RAM / GPU VRAM
     - 前向传播子模块执行钩子
     - 将显存需求从“全网规模”骤降至“单层规模”，支持小显存跑百亿大模型。
   * - **锁页内存管道 (Pinned DMA)**
     - OS Pinned Host RAM
     - 异步张量传输期
     - 绕过 CPU 中介拷贝，实现硬件级 DMA 直通与计算/传输双缓冲重叠。
   * - **即时精度强转 (CastBuffer)**
     - GPU 连续预分配显存块
     - Layer 执行前向即时转换
     - 兼顾 FP8/量化低内存存储与 BF16 高动态范围计算，消除显存分配碎片。
   * - **张量切片直读 (TensorFileSlice)**
     - 磁盘 Safetensors 文件
     - 节点首次拉取参数期
     - 消除模型载入时的全量反序列化内存爆炸，实现秒级冷启动。

------------------------------------------------------------------------

小结与下章导读
==============

本节系统剖析了 ComfyUI 权重流动与即时精度转换的核心机制：

1. **分层流式切片**：在低显存环境下打破整网加载约束，以网络层为单位按需换入换出；
2. **锁页 DMA 传输**：利用 Pinned Memory 与非阻塞异步拷贝流，实现 PCIe 带宽最大化与传输计算重叠；
3. **CastBuffer 内存复用**：解耦存储精度与计算精度，以预分配显存视图消除即时类型转换带来的内存碎片；
4. **切片直接读取**：基于 ``TensorFileSlice`` 实现磁盘到内存的零拷贝按需映射。

在下一节（``04_aimdo_and_memory_pressure_guard.rst``）中，我们将探讨第 2 模块的压轴技术——AIMDO（Anti-OOM & Memory Dynamic Optimizer）与全局内存压力守护：剖析基于 NVML 的实时显存压感监控、PyTorch 显存碎片主动整理、运行时 OOM 拦截自愈与主动 GC 回收机制。
