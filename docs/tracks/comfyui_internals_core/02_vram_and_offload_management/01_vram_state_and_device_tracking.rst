========================================================================
GPU 显存物理布局探测、显存预算分级与异构计算设备分配策略
========================================================================

.. note:: 前置背景与上下文承接
   在第 1 模块中，我们完整构建了 ComfyUI 的计算图调度中枢（``PromptExecutor``、``ExecutionList`` 与 ``PromptQueue``）。当调度器将具体算子派发至执行阶段时，底层面临的最严苛物理瓶颈正是**异构硬件的显存容量约束（VRAM Capacity Constraints）**。现代百亿参数级生成式大模型（如 SDXL、SD3、Flux.1）在 FP16/BF16 精度下的权重体积达数 GB 至数十 GB，且前向注意力激活值与潜空间解码需要巨额临时显存。本节作为第 2 模块的开篇，深入 ``comfy/model_management.py`` 与 ``comfy/memory_management.py``，全面剖析异构计算设备探测体系、物理显存与 PyTorch 缓存分配器水位监控、``VRAMState`` 多档位预算状态机，以及 CPU-GPU 跨设备分配路由策略。

------------------------------------------------------------------------

1. 异构计算硬件拓扑与设备抽象层
--------------------------------

现代深度学习推理不仅运行于标准的 NVIDIA CUDA 架构之上，还广泛部署于 AMD ROCm、Apple Silicon (MPS)、Intel XPU、华为昇腾 (Ascend NPU) 以及 DirectML 等多样化异构算力平台。ComfyUI 通过统一的硬件抽象接口屏蔽底层驱动差异：

.. list-table:: ComfyUI 异构算力后端探测与适配矩阵
   :widths: 20 20 25 35
   :header-rows: 1

   * - 硬件架构
     - 驱动/运行时支持
     - 探测判定接口
     - 物理显存管理特性
   * - **NVIDIA CUDA**
     - CUDA Driver / cuDNN
     - ``is_nvidia()`` / ``is_device_cuda()``
     - 支持异步显存池 (cudaMallocAsync)、NVML 动态压感监控与 Direct Pinned 内存。
   * - **AMD ROCm**
     - ROCm / HIP Runtime
     - ``is_amd()`` (检测 ``rocm_version``)
     - 基于 HIP 统一内存与 PCIe 显存流式换入换出，支持 AOTriton 算子加速。
   * - **Apple Silicon**
     - Metal (MPS)
     - ``is_device_mps()``
     - 统一内存架构 (UMA)，CPU 与 GPU 共享物理 DRAM，无 PCIe 传输开销但受系统内存预算严格约束。
   * - **Intel XPU**
     - Intel oneAPI / SYCL
     - ``is_intel_xpu()``
     - 支持 Intel 独立显卡 (Arc) 与数据中心 GPU (Flex/Max) 的异构显存分配。
   * - **Huawei Ascend**
     - CANN / Torch-NPU
     - ``is_ascend_npu()``
     - 专用 NPU 显存池管理，采用私有流同步与权重格式重排。
   * - **DirectML**
     - DirectX 12 / DirectML
     - ``is_directml_enabled()``
     - Windows 平台跨厂商显卡通用后端，通过 D3D12 资源堆管理显存。

1.1 主计算设备与卸载设备解耦（Execution vs Offload Device）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

ComfyUI 架构的一个核心原则是：**明确区分“当前算子执行设备”与“非活跃权重驻留卸载设备”**：

.. code-block:: python

    def get_torch_device():
        global directml_enabled
        if directml_enabled:
            return torch_directml.device()
        if is_device_mps():
            return torch.device("mps")
        if is_intel_xpu():
            return torch.device("xpu")
        if is_ascend_npu():
            return torch.device(f"npu:{torch.npu.current_device()}")
        if torch.cuda.is_available():
            return torch.device(f"cuda:{torch.cuda.current_device()}")
        return torch.device("cpu")

    def get_offload_device():
        # 默认卸载设备为 Host CPU 内存
        return torch.device("cpu")

在多卡并行环境中，``get_all_torch_devices()`` 枚举系统全部可见加速卡，并将主卡置于首位，确保多卡推理与跨卡权重分发时的拓扑一致性。

------------------------------------------------------------------------

2. 物理显存布局与双层水位探测算法
----------------------------------

在 GPU 架构中，显存分配存在物理硬件层与 PyTorch 运行时缓存分配器（Caching Allocator）的双层结构。简单读取 ``torch.cuda.memory_allocated()`` 只能获取 PyTorch 已分配张量的体积，无法反映操作系统窗口合成器（Desktop Window Manager）、驱动常驻内存及其他外部进程对物理显存的挤占。

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                                 Physical GPU VRAM (e.g. 16,384 MB)                                 |
   +----------------------------------------------------------------------------------------------------+
   |   OS / Display Server (e.g. 800 MB)  |  PyTorch Reserved Pool (12,000 MB)  | Free VRAM (3,584 MB)   |
   |                                      +-------------------------------------+                        |
   |                                      | Active Tensors  | Cached Free Blocks|                        |
   |                                      |   (8,500 MB)    |    (3,500 MB)     |                        |
   +----------------------------------------------------------------------------------------------------+

2.1 双层显存探测算法（``get_total_memory`` 与 ``get_free_memory``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

ComfyUI 通过底层驱动 API 获取真实的全局物理可用容量：

.. code-block:: python

    def get_total_memory(device=None, torch_total_too=False):
        if device is None:
            device = get_torch_device()
        if is_device_cuda(device):
            stats = torch.cuda.get_device_properties(device)
            total_memory = stats.total_memory
            if torch_total_too:
                # 返回 (物理总显存, PyTorch当前已保留的显存池总量)
                return total_memory, torch.cuda.memory_reserved(device)
            return total_memory
        elif is_device_mps(device):
            # Apple Silicon 统一内存：读取 host 物理内存总量
            return psutil.virtual_memory().total
        # ... 适配 XPU / NPU / CPU
        return psutil.virtual_memory().total

    def get_free_memory(device=None, torch_free_too=False):
        if device is None:
            device = get_torch_device()
        if is_device_cuda(device):
            # 关键：调用 cudaMemGetInfo 读取驱动层报告的真实物理空闲显存
            free_memory, total_memory = torch.cuda.mem_get_info(device)
            if torch_free_too:
                # 真实可用显存 = 物理未分配空闲显存 + PyTorch显存池中已释放但未归还驱动的闲置缓存块
                torch_free = torch.cuda.memory_reserved(device) - torch.cuda.memory_allocated(device)
                return free_memory, free_memory + torch_free
            return free_memory
        elif is_device_mps(device):
            # MPS 采用虚拟内存可用量估计
            return psutil.virtual_memory().available
        return psutil.virtual_memory().available

------------------------------------------------------------------------

3. VRAMState：四档位显存预算状态机
-----------------------------------

为了在不同显存规格的硬件上自适应选择最优调度路径，ComfyUI 在系统初始化时根据总物理显存、可用余量及用户 CLI 参数（``--highvram``、``--lowvram``、``--novram``、``--gpu-only``），构建了 ``VRAMState`` 状态机：

.. math::

   	ext{VRAMState} \in \{ 	ext{DISABLED}, 	ext{NO\_VRAM}, 	ext{LOW\_VRAM}, 	ext{NORMAL\_VRAM}, 	ext{HIGH\_VRAM}, 	ext{SHARED} \}

.. list-table:: VRAMState 档位划分与行为准则
   :widths: 20 20 25 35
   :header-rows: 1

   * - 档位枚举
     - 典型硬件配置
     - 显存阈值判定
     - 核心调度与模型卸载行为
   * - **HIGH_VRAM**
     - RTX 3090/4090, A100, H100 (24GB+)
     - 显存充裕，足以同时常驻多个模型
     - CLIP、UNet/DiT 与 VAE 全量常驻 GPU 显存。跨节点执行零 PCIe 换入换出开销，吞吐率最高。
   * - **NORMAL_VRAM**
     - RTX 3060/4060/4070 (8GB ~ 16GB)
     - 单个大模型可驻留，但多模型无法共存
     - 互斥换入换出：执行 UNet 采样前将 CLIP 卸载至 CPU；执行 VAE 解码前将 UNet 卸载至 CPU。
   * - **LOW_VRAM**
     - GTX 1060, RTX 3050, 移动端 GPU (4GB ~ 6GB)
     - 无法完整容纳单个大型 UNet/DiT
     - 细粒度分层卸载：模型以 Block/Layer 级别进行即时流式换入，计算完毕即刻释放，配合权重即时类型转换（CastBuffer）。
   * - **NO_VRAM / DISABLED**
     - 纯 CPU 环境或显式禁用 GPU 显存
     - 显存空间归零
     - 所有模型参数常驻 Host 系统内存，计算强制回退至 CPU，或通过 Direct-Host 零拷贝执行。
   * - **SHARED**
     - Apple M 系列 (M1/M2/M3/M4) UMA 架构
     - 统一内存池
     - 规避任何物理复制，采用零拷贝内存视图（Zero-Copy Views），依赖系统虚拟内存水压动态调节。

------------------------------------------------------------------------

4. 显存安全裕量（Reserve Headroom）与工作内存估算
-------------------------------------------------

在深度学习推理中，最容易诱发 CUDA OOM 的并非模型权重本身，而是**前向传播过程中的即时激活值峰值（Activation Spikes）**（如长序列自注意力矩阵计算、高分辨率潜空间卷积展开）。

4.1 显存安全裕量计算公式
~~~~~~~~~~~~~~~~~~~~~~~~

ComfyUI 设立了严格的保留裕量（``vram_headroom``），在决定是否将某个模型加载进 GPU 时，必须确保加载后的剩余显存大于预估的最小工作内存：

.. math::

   	ext{AvailableForLoading} = 	ext{FreeVRAM} - 	ext{VRAM\_Headroom} - 	ext{MinimumInferenceMemory}

.. list-table:: 显存安全裕量与工作内存参数
   :widths: 30 25 45
   :header-rows: 1

   * - 参数名称
     - 默认数值 / 估算规则
     - 物理系统作用
   * - ``reserve_vram`` (CLI)
     - ``0.5 GB ~ 1.5 GB``
     - 为操作系统 GUI 窗口管理器与后台进程预留的底线物理显存，严禁 PyTorch 侵占。
   * - ``minimum_inference_memory()``
     - :math:`\approx 1024 	imes 1024 	imes 	ext{batch} 	imes 4 	imes 16`
     - 保证单步前向传播（Forward Pass）不发生 OOM 所需的最小激活值工作暂存区。
   * - ``extra_models_gpu``
     - 布尔标志位 (由 VRAMState 决定)
     - 是否允许轻量级辅助模型（如 CLIP 文本编码器）与重度 Diffusion 骨干网络并发驻留 GPU。

------------------------------------------------------------------------

5. 显存状态探测与设备初始化调用流
---------------------------------

在服务启动与每个 Prompt 执行前，``model_management`` 执行如下初始化流程：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                                      ComfyUI Server Startup                                        |
   +----------------------------------------------------------------------------------------------------+
                                                     |
                                                     v
   +----------------------------------------------------------------------------------------------------+
   |                                 Detect Torch Accelerators & Devices                                |
   |               (probe CUDA -> MPS -> XPU -> NPU -> DirectML -> CPU Fallback)                       |
   +----------------------------------------------------------------------------------------------------+
                                                     |
                                                     v
   +----------------------------------------------------------------------------------------------------+
   |                                      Query Physical Memory Limits                                  |
   |              total_vram = get_total_memory(), free_vram = get_free_memory()                        |
   +----------------------------------------------------------------------------------------------------+
                                                     |
                                                     v
   +----------------------------------------------------------------------------------------------------+
   |                                Determine VRAMState & Headroom Bounds                               |
   |   If Total < 4GB  ==> LOW_VRAM                                                                     |
   |   If 4GB <= Total < 18GB ==> NORMAL_VRAM                                                           |
   |   If Total >= 18GB ==> HIGH_VRAM                                                                   |
   |   If CLI flag overrides (--highvram / --lowvram) ==> Apply Priority Override                        |
   +----------------------------------------------------------------------------------------------------+
                                                     |
                                                     v
   +----------------------------------------------------------------------------------------------------+
   |                             Configure Offload Target (CPU / Pinned Host RAM)                       |
   +----------------------------------------------------------------------------------------------------+

------------------------------------------------------------------------

小结与下章导读
==============

本节系统剖析了 ComfyUI 异构显存调度底座的物理感知层：

1. **多后端硬件抽象**：统一支持 CUDA、ROCm、MPS、XPU、NPU 与 DirectML，确立主计算设备与 Host CPU 卸载设备的双层拓扑；
2. **双层显存探测**：通过 ``mem_get_info`` 穿透 PyTorch Caching Allocator，直接感知驱动与 OS 级别的物理空闲显存；
3. **VRAMState 预算分级**：构建了从 ``LOW_VRAM`` 到 ``HIGH_VRAM`` 的四级自适应状态机，决定模型的驻留与卸载粒度；
4. **安全裕量机制**：引入 ``vram_headroom`` 与最小工作内存估算，为高并发张量计算建立物理防 OOM 缓冲带。

在下一节（``02_model_lifecycle_and_loaded_models.rst``）中，我们将深入模型对象管理的核心状态机：解剖 ``LoadedModel`` 结构体、多模型显存占用空间预估算法、动态 LRU 优先级换出队列以及模型权重的软释放机制。
