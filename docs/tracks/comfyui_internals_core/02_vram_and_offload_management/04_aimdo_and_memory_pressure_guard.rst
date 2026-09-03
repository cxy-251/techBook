========================================================================
AIMDO 显存压感监控、PyTorch 显存碎片整理、OOM 异常拦截与主动垃圾回收
========================================================================

.. note:: 前置背景与上下文承接
   在前三节中，我们建立了物理显存拓扑感知（``01_vram_state_and_device_tracking.rst``）、模型对象常驻生命周期（``02_model_lifecycle_and_loaded_models.rst``）以及分层流式切片与 CastBuffer 机制（``03_dynamic_weight_streaming_and_cast.rst``）。然而，在极端生成负载下（例如连续高分辨率批处理、复杂 ControlNet 堆叠或多 LoRA 动态融合），即便计算图理论显存预算充足，PyTorch 底层内存分配器的碎片累积（Memory Fragmentation）、瞬时中间激活值（Activation Spike）以及 Python 进程循环引用垃圾仍可能诱发毁灭性的 `CUDA Out of Memory` 异常。ComfyUI 通过 **AIMDO（Anti-OOM & Memory Dynamic Optimizer）** 压感监控、**PyTorch 缓存碎片主动脱扣（Soft Empty Cache）** 与 **前向执行期 OOM 自愈拦截流水线**，构建了工业级的高可用显存防护屏障。本节全面剖析这一显存防御中枢的物理机制与代码实现。

------------------------------------------------------------------------

1. 显存碎片化机理与 PyTorch Caching Allocator 物理剖析
------------------------------------------------------

现代深度学习框架（PyTorch）为了规避频繁调用 OS 内核级 `cudaMalloc` / `cudaFree` 带来的数百微秒同步延迟，设计了分层块式内存缓存分配器（Caching Allocator）。

1.1 显存三态物理模型与碎片率量化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 PyTorch 运行时环境中，物理显存被划分为三个核心指标：

- :math:`M_{	ext{allocated}}`：当前前向张量与常驻权重实际占用的活跃显存。
- :math:`M_{	ext{reserved}}`：Caching Allocator 向 GPU 驱动申请并持有的连续显存池总量（对操作系统与外部进程不可用）。
- :math:`M_{	ext{total}}`：硬件卡上物理安装的显存容量上限。

由此产生系统碎片化度量公式：

.. math::

   \Delta M_{	ext{fragment}} = M_{	ext{reserved}} - M_{	ext{allocated}}

   R_{	ext{fragment}} = \frac{M_{	ext{reserved}} - M_{	ext{allocated}}}{M_{	ext{reserved}}} 	imes 100\%

当模型请求分配大小为 :math:`S_{	ext{req}}` 的连续物理块时，即使 :math:`M_{	ext{total}} - M_{	ext{allocated}} > S_{	ext{req}}`，如果 reserved 内存池中不存在大于等于 :math:`S_{	ext{req}}` 的连续空闲 Block，且操作系统可用显存不足以分配新的 Segment，系统就会立即抛出 `torch.cuda.OutOfMemoryError`。

1.2 常规 empty_cache 与 soft_empty_cache 差异
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: PyTorch 原生 empty_cache 与 ComfyUI soft_empty_cache 特性对比
   :widths: 20 40 40
   :header-rows: 1

   * - 评估维度
     - PyTorch 原生 `torch.cuda.empty_cache()`
     - ComfyUI `soft_empty_cache()`
   * - **执行机制**
     - 强制无条件释放 Allocator 中所有未分配的 Block 归还给 OS
     - 依据当前分配水位与碎片率阈值进行条件判断与分级回收
   * - **性能损耗**
     - 引发全 GPU 硬件流同步（Pipeline Stall），后续分配重新触发 `cudaMalloc`
     - 仅在显存水压触及红色警戒线或模型卸载节点间隙精准执行，保护流水线吞吐
   * - **与 GC 的协同**
     - 纯底层显存释放，不清理 Python 层循环引用
     - 先行触发 `gc.collect()` 销毁不可达张量句柄，再执行显存池碎片释放

------------------------------------------------------------------------

2. 显存软清空与垃圾回收调度管道（``soft_empty_cache`` & ``cleanup_models_gc``）
--------------------------------------------------------------------------------

在 ``comfy/model_management.py`` 中，ComfyUI 封装了高度精密的显存清理中枢：

.. code-block:: python

    def soft_empty_cache(force=False):
        global total_vram
        if is_device_mps(get_torch_device()):
            # Apple Silicon MPS 统一内存架构专用同步
            torch.mps.empty_cache()
        elif is_intel_xpu():
            torch.xpu.empty_cache()
        elif hasattr(torch, "cuda") and torch.cuda.is_available():
            # 只有在显存分配达到一定阈值或显式强制时才释放
            if force or should_use_fp16():
                torch.cuda.empty_cache()

2.1 Python 对象循环引用与垃圾回收链路
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

PyTorch 的张量底层 Storage 依赖 C++ 底层引用计数（Refcount）。然而，复杂的自定义节点、Hook 闭包以及计算图递归结构常常导致 Python 层对象产生**循环引用（Reference Cycles）**。当变量超出作用域时，Refcount 无法归零，导致底层 CUDA Storage 无法被 Caching Allocator 识别为空闲块。

ComfyUI 在节点执行间隙与模型调度前后部署了主动垃圾回收管道：

.. code-block:: python

    def cleanup_models_gc():
        # 第一阶段：触发 Python 垃圾收集器解除跨代循环引用
        gc.collect()
        # 第二阶段：清空已过期的 Pinned Memory 锁页缓冲
        free_pins()
        # 第三阶段：执行显存池软整理
        soft_empty_cache(force=False)

------------------------------------------------------------------------

3. AIMDO 动态显存优化器与多级压感监控
--------------------------------------

AIMDO（Anti-OOM & Memory Dynamic Optimizer）是 ComfyUI 内部维护的自适应内存安全中枢。它通过直接查询显卡底层遥测（NVML / ROCm SMI / OS VirtualAlloc API），建立动态四级水压模型：

.. code-block:: text

   +-----------------------------------------------------------------------------------------+
   |                             AIMDO 动态水压状态机模型                                    |
   +-----------------------------------------------------------------------------------------+
   |   [水位 0: NORMAL (<70%)]     ==> 允许模型全量常驻，开启并发预取，禁用强制同步          |
   |   [水位 1: CAUTION (70%-85%)] ==> 冻结预取流水线，降低 CastBuffer 预分配尺寸            |
   |   [水位 2: WARNING (85%-95%)] ==> 触发非活跃模型 LRU 换出，调用 soft_empty_cache()      |
   |   [水位 3: CRITICAL (>95%)]   ==> 降级至 LowVRAM 分层流式计算，强制全量垃圾回收         |
   +-----------------------------------------------------------------------------------------+

3.1 动态水压阈值决策算法
~~~~~~~~~~~~~~~~~~~~~~~~

.. math::

   P_{	ext{dynamic}} = \frac{M_{	ext{reserved}} + M_{	ext{driver\_overhead}}}{M_{	ext{total}}}

.. code-block:: python

    class MemoryPressureGuard:
        def __init__(self, warning_threshold=0.85, critical_threshold=0.95):
            self.warning_threshold = warning_threshold
            self.critical_threshold = critical_threshold

        def evaluate_pressure(self, device):
            free, total = get_free_memory(device, make_decision=False), get_total_memory(device)
            usage_ratio = 1.0 - (free / total)

            if usage_ratio >= self.critical_threshold:
                return "CRITICAL"
            elif usage_ratio >= self.warning_threshold:
                return "WARNING"
            return "NORMAL"

------------------------------------------------------------------------

4. 运行时 OOM 异常拦截、动态降级与自愈重试机制
----------------------------------------------

在传统的 WebUI 或推理框架中，一旦算子前向计算抛出 `CUDA out of memory`，整个 Python 进程或异步 Worker 会直接中断，前端报错并丢失已计算的所有临时状态。

ComfyUI 在调度层（``execution.py``）与算子执行层（``comfy/model_management.py``）构建了**双层 OOM 熔断自愈机制**：

.. code-block:: text

   +-----------------------------------------------------------------------------------------+
   |                        ComfyUI 运行时 OOM 熔断自愈流水线                                |
   +-----------------------------------------------------------------------------------------+
   |   1. 算子前向执行 (Forward Pass)                                                        |
   |             |                                                                           |
   |             v [抛出 torch.cuda.OutOfMemoryError]                                        |
   |   2. 拦截层捕获异常 (Catch OutOfMemoryError)                                            |
   |             |                                                                           |
   |             v                                                                           |
   |   3. 应急显存排空：                                                                     |
   |        - 强制卸载所有非当前计算依赖模型 (unload_all_models())                           |
   |        - 执行全量 Python GC (gc.collect())                                              |
   |        - 强制清空 CUDA 缓存池 (torch.cuda.empty_cache())                                |
   |             |                                                                           |
   |             v                                                                           |
   |   4. 动态降级重试 (Fallback Execution)：                                                |
   |        - 激活分层流式切片执行 (LowVRAM Mode)                                            |
   |        - 切换注意力机制后端 (如从 FlashAttention 降级至 xformers / Split-Attention)     |
   |        - 重新拉起当前节点计算任务                                                       |
   +-----------------------------------------------------------------------------------------+

4.1 核心自愈实现代码
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    def interrupt_processing(exception=None):
        if isinstance(exception, torch.cuda.OutOfMemoryError):
            logging.error("Detected CUDA Out of Memory! Triggering emergency VRAM evacuation...")
            # 1. 紧急清空全部常驻模型
            unload_all_models()
            # 2. 彻底释放显存池与垃圾引用
            soft_empty_cache(force=True)
            gc.collect()
            # 3. 标记系统进入降级执行模式
            set_vram_state(VRAMState.LOW_VRAM)

------------------------------------------------------------------------

5. 显存管理全模块技术全景总结
------------------------------

作为第 2 模块的收官章节，下表汇总了 ComfyUI 在显存管理架构上的完整技术矩阵：

.. list-table:: ComfyUI 动态显存管理与卸载体系技术全景
   :widths: 20 25 25 30
   :header-rows: 1

   * - 核心架构组件
     - 物理调度粒度
     - 关键源代码位置
     - 架构核心贡献
   * - **显存设备探针 (VRAMState)**
     - 节点级 / 全局系统
     - ``comfy/model_management.py``
     - 建立 4 级硬件显存预算状态机，实现异构硬件统一抽象。
   * - **生命周期模型 (LoadedModel)**
     - 模型实例级
     - ``comfy/model_management.py``
     - 基于访问时间戳与引用计数维护动态 LRU 换出队列。
   * - **流式换入换出 (Streaming)**
     - 子模块 / 网络层级
     - ``comfy/model_patcher.py``
     - 突破物理显存上限，支持 6GB/8GB 显卡运行百亿级大模型。
   * - **CastBuffer 环形缓冲**
     - 张量显存切片
     - ``comfy/model_management.py``
     - 解耦存储与计算精度，消除即时精度转换的显存碎片。
   * - **AIMDO & OOM 熔断自愈**
     - 算子前向计算流
     - ``execution.py``
     - 实时水压压感监控，实现 OOM 异常自动捕获、降级与自愈。

------------------------------------------------------------------------

小结与下章导读
==============

本节全面剖析了 ComfyUI 显存管理体系的最后一道防线：

1. **显存碎片机理**：量化了 PyTorch Caching Allocator 的碎片累积模型与 `soft_empty_cache` 的条件清空策略；
2. **多级压感监控**：基于 AIMDO 建立了从 NORMAL 到 CRITICAL 的四级自适应水压调节通道；
3. **OOM 自愈流水线**：实现了算子层 OOM 捕获、紧急显存排空与动态降级重试闭环。

至此，**第 2 模块《动态显存管理与模型卸载机制》全 4 节已全部圆满结稿**。

在接下来的 **第 3 模块《动态权重修补与 LoRA/Hook 注入体系》（03_model_patcher_and_hooks）** 中，我们将深入剖析 ComfyUI 灵魂级别的参数修补核心——``ModelPatcher``：探究底层 PyTorch 模型的轻量代理封装、浅拷贝克隆树、LoRA/DoRA 矩阵在线融合代数以及链式 Forward 劫持机制。
