====================================================================
ComfyUI 节点式流处理引擎内核架构与调度体系深度剖析
====================================================================

.. toctree::
   :maxdepth: 2
   :caption: 全书目录导航
   :numbered:

   ROADMAP
   01_execution_and_scheduler/index
   02_vram_and_offload_management/index
   03_model_patcher_and_hooks/index
   04_model_base_and_architectures/index
   05_samplers_and_scheduling/index
   06_text_encoding_and_latent/index
   07_custom_nodes_and_comms/index

专著简介与架构全景
==================

本书是一本以现代生成式 AI 领域事实标准的节点式流处理引擎 ``ComfyUI`` 核心源码为基础，自底向上、深入硬件资源与计算图调度核心的工业级架构专著。

与传统的命令行工具或固化 Pipeline（如 Diffusers 顶层封装）不同，ComfyUI 的核心本质是一个**异步驱动的动态计算图拓扑调度与异构显存生命周期管理引擎**。它将深度学习模型的层级参数加载、权重切片修补、张量潜空间变换、数值求解微分方程以及前后端流式交互彻底抽象为有向无环图（DAG）的节点与边。

全书严格遵循“底层物理机制与系统源码实现优先”原则，深入 Python 异步事件循环、PyTorch 动态显存池化、模型权重跨设备流式换入换出（Offload）、LoRA/Hook 差分代数注入、扩散模型（UNet/DiT）拓扑骨干抽象、数值积分采样器求解器、CLIP/T5 文本嵌入空间映射以及 WebSocket 二进制事件广播体系，完整还原 ComfyUI 高性能流处理底座的工程全貌。

核心知识模块拓扑
----------------

.. list-table:: ComfyUI 知识拓扑与核心系统架构映射
   :widths: 15 25 35 25
   :header-rows: 1

   * - 模块编号
     - 核心系统模块
     - 内核关键技术与源码路径
     - 解决的核心工程问题
   * - 01
     - 有向无环图调度与执行引擎
     - ``execution.py``, ``comfy_execution/`` (PromptExecutor, ExecutionList, DynamicPrompt)
     - 动态 DAG 拓扑排序、惰性计算、子图展开、缓存哈希命中与异步中断熔断
   * - 02
     - 动态显存管理与模型卸载机制
     - ``comfy/model_management.py``, ``comfy/memory_management.py``
     - GPU VRAM 预算分级、LoadedModel 状态机、动态换入换出与 OOM 自动降级自愈
   * - 03
     - 动态权重修补与 LoRA/Hook 注入体系
     - ``comfy/model_patcher.py``, ``comfy/hooks.py``
     - 权重非破坏性分层注入、LoRA/DoRA 矩阵融合、Forward 拦截 Hook 链
   * - 04
     - 扩散模型基类与 DiT 架构抽象
     - ``comfy/model_base.py``, ``comfy/ldm/``, ``comfy/cldm/``
     - BaseModel 多态派生、SD1.5/SDXL UNet 骨干拓扑与 SD3/Flux MMDiT 双流块架构
   * - 05
     - 采样器数值解法与调度方程
     - ``comfy/samplers.py``, ``comfy/k_diffusion/``
     - KSampler 调度框架、Sigmas 噪声时间表、CFG 引导计算与高阶 ODE/SDE 求解器
   * - 06
     - 文本编码与潜空间重构
     - ``comfy/sd.py``, ``comfy/text_encoders/``, ``comfy/taesd/``
     - CLIP/T5 分词加权与多向量投影、VAE 潜空间编解码、Tiled VAE 与实时预览
   * - 07
     - 自定义节点协议与 WebSocket 通信体系
     - ``nodes.py``, ``server.py``, ``comfy_api/``
     - 动态类型校验协议、V3 面向对象节点规范、aiohttp API 与 WebSocket 流式事件同步
