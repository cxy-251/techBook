========================================================================
ComfyUI 节点式流处理引擎内核架构与调度体系深度剖析：工程图谱
========================================================================

.. note:: 单一事实源说明
   本文件是《ComfyUI 节点式流处理引擎内核架构与调度体系深度剖析》全书各章节编写状态与知识依赖的唯一权威图谱。所有自动化写作任务与调度器均以此文件的完成状态作为推进依据。

总体进度概览
============

- **总规划模块数**：7 个核心模块
- **总规划章节数**：28 节深度专著章节
- **已完成章节**：28 节（全书 7 大模块全部 28 节已 100% 全部完工落盘！）
- **当前写作状态**：**全书全部完结（Completed）**

.. contents::
   :local:
   :depth: 2

------------------------------------------------------------------------

模块详细进度与章节清单
======================

第 1 模块：有向无环图调度与执行引擎 (01_execution_and_scheduler) [已完工]
-------------------------------------------------------------------------

- [x] ``01_prompt_executor_and_dag.rst`` - PromptExecutor 执行状态机、动态 DAG 拓扑排序算法 (TopologicalSort/ExecutionList) 与节点调度执行闭环
- [x] ``02_node_caching_and_dirty_tracking.rst`` - 节点缓存哈希签名树 (CacheKeySetInputSignature)、IS_CHANGED 脏状态探测与 RAMPressureCache 内存压力回收
- [x] ``03_lazy_evaluation_and_subgraph_expansion.rst`` - 惰性计算机制 (check_lazy_status)、动态子图展开 (Subgraphs/Ephemeral Nodes) 与执行熔断器 (ExecutionBlocker)
- [x] ``04_prompt_queue_and_async_dispatcher.rst`` - PromptQueue 优先队列调度、线程安全条件变量、原子中断控制与异常熔断机制

第 2 模块：动态显存管理与模型卸载机制 (02_vram_and_offload_management) [已完工]
--------------------------------------------------------------------------------

- [x] ``01_vram_state_and_device_tracking.rst`` - GPU 显存物理布局探测 (vram_state)、显存预算阈值划分与异构计算设备分配策略
- [x] ``02_model_lifecycle_and_loaded_models.rst`` - LoadedModel 生命周期状态机、显存占用空间预估算法与动态 LRU 驱逐策略
- [x] ``03_dynamic_weight_streaming_and_cast.rst`` - 权重跨设备流式换入换出 (load_models_gpu/free_memory)、权重精度即时转换与 CastBuffer 机制
- [x] ``04_aimdo_and_memory_pressure_guard.rst`` - AIMDO 显存压感监控、PyTorch 显存碎片整理、OOM 异常拦截与主动垃圾回收

第 3 模块：动态权重修补与 LoRA/Hook 注入体系 (03_model_patcher_and_hooks) [已完工]
------------------------------------------------------------------------------------

- [x] ``01_model_patcher_core_architecture.rst`` - ModelPatcher 对象模型架构、底层 PyTorch 模型代理封装与浅拷贝克隆树机制
- [x] ``02_weight_patch_algebra_and_lora.rst`` - 权重差分注入代数 (add_patches/calculate_weight)、LoRA/DoRA 矩阵在线融合与动态去补丁
- [x] ``03_object_patches_and_forward_wrappers.rst`` - 模块级对象替换 (object_patches)、Forward 计算图函数拦截与链式 Hook 调度体系
- [x] ``04_model_options_and_transformer_options.rst`` - transformer_options 运行时上下文注入机制、注意力机制劫持与跨节点状态传递

第 4 模块：扩散模型基类与 DiT 架构抽象 (04_model_base_and_architectures) [已完工]
----------------------------------------------------------------------------------

- [x] ``01_base_model_and_unet_dit_taxonomy.rst`` - BaseModel 体系架构、DiffusionModel 骨干抽象与多代生成模型族谱分发
- [x] ``02_latent_diffusion_unet_internals.rst`` - SD 1.5 / SDXL UNet 拓扑：ResBlock、Spatial Transformer、CrossAttention 与时间步/文本条件注入
- [x] ``03_dit_architecture_and_mmdit.rst`` - MMDiT (SD3 / Flux) 双流/单流 Transformer 块、RoPE 旋转位置编码与自适应调制层 (AdaLN)
- [x] ``04_controlnet_and_guiding_mechanisms.rst`` - ControlNet 残差分支挂载、T2I-Adapter 浅层特征注入与跨架构模型级引导抽象

第 5 模块：采样器数值解法与调度方程 (05_samplers_and_scheduling) [已完工]
--------------------------------------------------------------------------

- [x] ``01_samplers_and_kdiffusion_wrapper.rst`` - KSampler 采样调度框架、KSamplerImpl 状态机与 k-diffusion 数值积分器统一封装
- [x] ``02_noise_schedules_and_sigmas.rst`` - 连续与离散噪声时间表 (Beta/Cosine/Simple/Karras) 与 Sigmas 序列生成方程
- [x] ``03_cfg_and_guidance_computation.rst`` - 无分类器引导 (CFG) 数学计算、负向提示词对抗、动态阈值 (Dynamic Thresholding) 与 Rescale CFG
- [x] ``04_ode_sde_solvers_internals.rst`` - 经典 ODE/SDE 求解器内核：Euler, Heun, DPM-Solver++, UniPC 与 Ancestral 随机采样微分方程离散化

第 6 模块：文本编码与潜空间重构 (06_text_encoding_and_latent) [已完工]
------------------------------------------------------------------------

- [x] ``01_clip_and_t5_tokenization_pipeline.rst`` - 文本分词器 Tokenizer 管道、多权重加权语法解析 (Weight Parsing) 与 77-Token 长文本 Chunking
- [x] ``02_text_encoder_embeddings_and_pooling.rst`` - CLIP/T5 双编码器表征空间映射、Text Embeddings 提取与 Pooled Output 投影矩阵
- [x] ``03_vae_architecture_and_tiling.rst`` - 变分自编码器 (VAE) 卷积编解码拓扑、潜空间缩放因子 (scaling_factor) 与色彩通道对齐
- [x] ``04_tiled_vae_and_latent_preview.rst`` - 大图切块 VAE 编解码 (Tiled VAE) 边缘重叠羽化融合算法与 Latent 实时流式预览 (TAESD)

第 7 模块：自定义节点协议与 WebSocket 通信体系 (07_custom_nodes_and_comms) [已完工]
--------------------------------------------------------------------------

- [x] ``01_custom_node_protocol_and_registration.rst`` - 自定义节点协议标准 (NODE_CLASS_MAPPINGS/INPUT_TYPES/RETURN_TYPES) 与动态注册机制
- [x] ``02_v3_api_and_typing_architecture.rst`` - ComfyUI V3 API 面向对象节点范式 (_ComfyNodeInternal/io.Combo/Schema 类型校验系统)
- [x] ``03_server_and_rest_api_layer.rst`` - aiohttp 异步 Web 服务端架构、路由注册与 RESTful 提示词提交控制流
- [x] ``04_websocket_streaming_and_client_sync.rst`` - WebSocket 异步二进制/JSON 事件流式广播 (executing/progress/executed) 与前端实时状态同步
