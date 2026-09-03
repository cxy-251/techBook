========================================================================
LoadedModel 生命周期状态机、显存空间预估算法与动态 LRU 驱逐策略
========================================================================

.. note:: 前置背景与上下文承接
   在上一节（``01_vram_state_and_device_tracking.rst``）中，我们建立了 GPU 显存双层水位探测、``VRAMState`` 四档位预算状态机与设备拓扑抽象。当确定了硬件显存预算后，调度系统面临的下一个核心工程挑战是：**如何在运行时动态管理多个相互竞争显存的模型实例（如 CLIP 文本编码器、UNet/DiT 扩散骨干、VAE 编解码器与 ControlNet 辅助网络）**。在有限显存无法同时容纳所有模型时，必须建立一套精细的模型生命周期追踪、体积精确预估与自动换出机制。本节深入 ``comfy/model_management.py``，全面剖析 ``LoadedModel`` 状态机、张量参数空间预估数学模型、基于加权优先级的动态 LRU 驱逐算法以及 ``load_models_gpu`` 协同调度流程。

------------------------------------------------------------------------

1. LoadedModel 对象模型与全局驻留注册表
----------------------------------------

在 ComfyUI 内核中，PyTorch 原始神经网络（``torch.nn.Module``）从不直接裸露与设备交互，而是由 ``ModelPatcher`` 进行包装，并在物理加载阶段被抽象为 ``LoadedModel`` 运行时实体。

全局驻留列表 ``current_loaded_models: list[LoadedModel]`` 维护了当前所有常驻物理显存或系统内存中的模型状态机集合：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                                 current_loaded_models (Global List)                                |
   +----------------------------------------------------------------------------------------------------+
   | [0] LoadedModel(CLIP)       | Device: cuda:0 | Current: cuda:0 | Active: False | Size: 1.2 GB      |
   | [1] LoadedModel(UNet/DiT)   | Device: cuda:0 | Current: cpu    | Active: False | Size: 8.4 GB      |
   | [2] LoadedModel(VAE)        | Device: cuda:0 | Current: cpu    | Active: False | Size: 0.3 GB      |
   | [3] LoadedModel(ControlNet) | Device: cuda:0 | Current: cuda:0 | Active: True  | Size: 1.4 GB      |
   +----------------------------------------------------------------------------------------------------+
                                                     |
                                   Request to Load Model [1] (UNet)
                                                     v
   +----------------------------------------------------------------------------------------------------+
   |                          free_memory() Dynamic LRU Eviction Pipeline                               |
   |   - Scan current_loaded_models from oldest to newest                                               |
   |   - Filter out Active models (Active == True is IMMUNE to eviction)                                |
   |   - Evict [0] LoadedModel(CLIP) ==> Unload to CPU Host RAM                                         |
   |   - Free VRAM increases by 1.2 GB                                                                  |
   |   - Check if Free VRAM >= 8.4 GB + Headroom ==> Load [1] to cuda:0                                 |
   +----------------------------------------------------------------------------------------------------+

1.1 LoadedModel 核心字段与状态定义
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: LoadedModel 核心字段与系统功能
   :widths: 20 20 60
   :header-rows: 1

   * - 字段名称
     - 类型定义
     - 物理意义与调度机制
   * - ``model``
     - ``ModelPatcher``
     - 模型的代理包装对象，维护了权重补丁链与模型结构元数据。
   * - ``device``
     - ``torch.device``
     - 模型的目标计算执行设备（通常为目标 GPU，如 ``cuda:0``）。
   * - ``current_device``
     - ``torch.device``
     - 模型权重当前时刻在物理硬件上的驻留位置（处于 ``cpu`` 卸载态或 ``cuda:0`` 加载态）。
   * - ``model_accelerator``
     - ``torch.device``
     - 针对部分特定硬件加速器设定的专用流执行目标。
   * - ``real_model``
     - ``nn.Module``
     - 底层原生 PyTorch 神经网络引用，用于遍历参数与执行显存换入换出。
   * - ``currently_used``
     - ``bool``
     - 活跃状态标志位。当算子正在执行前向计算时为 ``True``，**在驱逐算法中享有绝对豁免权**。

------------------------------------------------------------------------

2. 模型显存占用空间预估数学模型
--------------------------------

在执行显存驱逐或换入决策前，系统必须精确预知目标模型在 GPU 端所需占据的物理字节数，避免因盲目加载导致二次 CUDA OOM。

2.1 静态权重参数量计算（``model_size``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

模型的静态物理体积由其全部注册参数（Parameters）与缓冲区（Buffers）的元素数量和数据类型决定：

.. math::

   S_{	ext{weights}}(M) = \sum_{p \in 	ext{Params}(M)} 	ext{numel}(p) 	imes 	ext{sizeof}(	ext{dtype}(p)) + \sum_{b \in 	ext{Buffers}(M)} 	ext{numel}(b) 	imes 	ext{sizeof}(	ext{dtype}(b))

.. list-table:: 常见精度数据类型单元素字节对照
   :widths: 25 25 50
   :header-rows: 1

   * - 浮点精度类型
     - PyTorch Dtype
     - 单元素字节数（$	ext{sizeof}$）
   * - **Float32 (FP32)**
     - ``torch.float32``
     - 4 字节（32 位）
   * - **Float16 (FP16)**
     - ``torch.float16``
     - 2 字节（16 位）
   * - **Bfloat16 (BF16)**
     - ``torch.bfloat16``
     - 2 字节（16 位）
   * - **Float8 (FP8_E4M3 / FP8_E5M2)**
     - ``torch.float8_e4m3fn`` / ``e5m2``
     - 1 字节（8 位）
   * - **4-Bit Quantized (GGUF / NF4)**
     - 自定义量化张量
     - 0.5 字节（4 位）加量化尺度表开销

2.2 跨设备换入净增量计算（``model_memory_required``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

若模型的部分层或权重已经驻留在目标设备上（例如部分层由于 LowVRAM 策略已提前转移），换入所需的实际净增量显存为：

.. math::

   \Delta M_{	ext{required}}(M, D) = \sum_{t \in 	ext{Tensors}(M), \, 	ext{device}(t) 
eq D} 	ext{numel}(t) 	imes 	ext{sizeof}(	ext{dtype}(t))

``LoadedModel.model_memory_required`` 通过遍历模型参数，精准计算出需要从 Host CPU 传输至 GPU VRAM 的真实张量字节总和。

------------------------------------------------------------------------

3. 动态 LRU 驱逐算法（free_memory）实现解剖
--------------------------------------------

当准备加载新模型至计算设备，而目标设备的物理空闲显存（加上安全保留裕量）小于所需空间时，``free_memory`` 算法启动。

3.1 驱逐决策流与核心源码剖析
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    def free_memory(memory_required, device, keep_loaded=[]):
        unloaded_amount = 0
        can_unload = []
        
        # 步骤 1：收集所有当前不在活跃执行中的候选模型
        for cur_m in current_loaded_models:
            if cur_m.currently_used:
                # 处于活跃计算中的模型严禁卸载
                continue
            if cur_m in keep_loaded:
                # 本轮请求中必须保持常驻的模型严禁卸载
                continue
            if cur_m.current_device == device:
                can_unload.append(cur_m)

        # 步骤 2：按 LRU 时间戳（最久未访问优先）进行排序
        # current_loaded_models 原生按加载时间升序排列，列表头部即为最久未使用的模型
        while len(can_unload) > 0:
            free_mem = get_free_memory(device)
            # 检查当前空闲显存是否已满足需求（包含安全保留阈值）
            if free_mem >= memory_required + minimum_inference_memory():
                break
                
            # 提取最久未使用的候选模型
            to_unload = can_unload.pop(0)
            unloaded_amount += to_unload.model_size()
            
            # 执行物理卸载：将权重张量全部移回 CPU Host RAM 或解分配
            to_unload.model_unload()
            
        # 步骤 3：若卸载所有非活跃模型后显存依然紧张，触发 PyTorch 显存池碎片整理
        if get_free_memory(device) < memory_required:
            soft_empty_cache()
            
        return unloaded_amount

3.2 驱逐规则的物理优先级与防振荡设计
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 模型卸载优先级权重阶梯
   :widths: 20 20 60
   :header-rows: 1

   * - 优先级等级
     - 模型分类 / 状态
     - 驱逐仲裁行为
   * - **第 1 级（绝对免疫）**
     - ``currently_used == True``
     - 正在参与当前 CUDA Kernel 前向计算的模型。任何情况下均不得驱逐，否则将引发运行时内存段错误。
   * - **第 2 级（显式保护）**
     - ``keep_loaded`` 列表包含项
     - 本次计算流水线接下来紧接着需要使用的伴生模型（如与 UNet 协同工作的 ControlNet）。
   * - **第 3 级（LRU 候选）**
     - 空闲状态的非当前算子模型
     - 按上次访问时间戳（Last Access Timestamp）排序，最久未使用的模型优先卸载回 CPU。
   * - **第 4 级（彻底清除）**
     - 孤儿模型（无外部强引用）
     - 在 ``cleanup_models_gc()`` 中直接从全局注册表注销并执行 Python 垃圾回收。

------------------------------------------------------------------------

4. 多模型协同加载引擎（load_models_gpu）
-----------------------------------------

在一次复杂的图像生成节点（如带多 ControlNet 的 KSampler）中，执行往往需要多个模型在 GPU 端同时就绪。ComfyUI 通过 ``load_models_gpu`` 实现了多模型原子级协同加载：

.. code-block:: python

    def load_models_gpu(models, memory_required=0):
        # 1. 统计当前批次请求中所有模型的总显存需求
        total_memory_required = memory_required
        for m in models:
            total_memory_required += m.model_memory_required(m.load_device)
            
        # 2. 批量释放显存，确保目标设备有足够连续空间容纳所有请求模型
        for m in models:
            free_memory(total_memory_required, m.load_device, keep_loaded=models)
            
        # 3. 依次将模型参数加载至目标 GPU 设备
        for m in models:
            loaded_model = m.model_load()
            # 将新加载的模型移动至 current_loaded_models 尾部，更新 LRU 热度
            if loaded_model in current_loaded_models:
                current_loaded_models.remove(loaded_model)
            current_loaded_models.append(loaded_model)

4.1 LRU 热度刷新机制
~~~~~~~~~~~~~~~~~~~~

在 ``load_models_gpu`` 成功执行后，每个被访问的模型都会被重新 ``append`` 至 ``current_loaded_models`` 的末尾。这种机制确保了最近被使用过的模型具有最高的热度，在下一轮节点的显存争夺中被保留在 GPU 显存内，最大化缓存局部性（Temporal Locality）。

------------------------------------------------------------------------

5. 核心状态转移与生命周期全景表
--------------------------------

.. list-table:: LoadedModel 物理状态机转移矩阵
   :widths: 20 20 25 35
   :header-rows: 1

   * - 初始状态
     - 触发事件
     - 目标状态
     - 底层物理操作
   * - **Unloaded (CPU)**
     - ``model_load()`` 触发
     - **Loaded (GPU)**
     - 权重从 Host Pinned 内存通过 PCIe 总线流式写入 GPU VRAM，注册至 ``current_loaded_models``。
   * - **Loaded (GPU)**
     - 算子前向计算启动
     - **Active (GPU Running)**
     - ``currently_used`` 置为 ``True``，屏蔽所有驱逐请求，锁定显存占用。
   * - **Active (GPU Running)**
     - 算子计算完成
     - **Idle (GPU Resident)**
     - ``currently_used`` 置为 ``False``，进入 LRU 观察期，权重继续保留在 VRAM 中以备复用。
   * - **Idle (GPU Resident)**
     - ``free_memory()`` 驱逐
     - **Unloaded (CPU)**
     - 权重转移回 CPU 内存或释放显存指针，等待下次按需拉取。
   * - **Unloaded / Idle**
     - Python 强引用归零
     - **Destroyed (Garbage Collected)**
     - 在 ``cleanup_models_gc()`` 中彻底销毁实例，归还所有系统资源。

------------------------------------------------------------------------

小结与下章导读
==============

本节系统剖析了 ComfyUI 模型级显存生命周期与驱逐中枢：

1. **统一模型抽象**：通过 ``LoadedModel`` 追踪参数物理驻留设备与活跃状态；
2. **精确体积度量**：基于元素数量与浮点精度建立跨精度张量内存预估方程；
3. **动态 LRU 驱逐**：在保护活跃计算模型的前提下，按访问时间戳逆序卸载闲置权重，并结合 ``soft_empty_cache`` 消除内存碎片；
4. **多模型协同调度**：通过 ``load_models_gpu`` 实现多模型并发加载与热度队列刷新。

在下一节（``03_dynamic_weight_streaming_and_cast.rst``）中，我们将进一步深入模型权重在跨设备流动时的底层传输与即时精度转换机制：剖析权重流式换入换出（Weight Streaming）、基于 Pinned 内存的高速 DMA 传输、权重即时精度动态强转（CastBuffer）以及低显存模式（LowVRAM）下的分层切片执行技术。
