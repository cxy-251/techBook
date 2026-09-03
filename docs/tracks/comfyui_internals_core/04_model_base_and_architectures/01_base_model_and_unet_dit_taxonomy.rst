========================================================================
BaseModel 体系架构、DiffusionModel 骨干抽象与多代生成模型族谱分发
========================================================================

.. note:: 前置背景与上下文承接
   在第 3 模块《动态权重修补与 LoRA/Hook 注入体系》中，我们深入剖析了 ``ModelPatcher`` 如何在不改动底层神经网络结构的前提下实现参数增量、对象替换与跨层上下文拦截。然而，生成式 AI 的骨干神经网络本身经历着迅猛的范式迭代——从经典的卷积-注意力混合架构（SD 1.5 / SDXL UNet），到现代纯 Transformer 架构（SD3 MMDiT、Flux.1 双流/单流 DiT、AuraFlow、HunyuanVideo、LTX-Video），以及面向视频时空建模的 3D 卷积扩展。不同模型的输入输出尺度、时间步参数化形式（:math:`\epsilon`-prediction / :math:`v`-prediction / Rectified Flow）、文本表征投影维度与条件注入方式存在巨大差异。ComfyUI 没有为每种模型编写孤立的执行流，而是通过 ``comfy/model_base.py`` 与 ``comfy/supported_models.py`` 建立了高度抽象的 **``BaseModel`` 骨干模型继承体系** 与 **权重签名自动探测分发工厂**。本节系统解剖这一承上启下的模型抽象层。

------------------------------------------------------------------------

1. BaseModel 与 DiffusionModel 的双层解耦架构
---------------------------------------------

在 ComfyUI 的物理架构中，一个完整的扩散模型被严格解耦为两个核心实体：

1. **高层数学与调度适配器（``BaseModel``）**：处理模型采样物理量转换、输入预处理（如给潜变量打补丁、拼接额外通道）、时间步编码以及引导输出格式化；
2. **底层神经网络计算图（``DiffusionModel``）**：纯粹的 PyTorch ``torch.nn.Module``（如 ``UNetModel``、``OpenAISDXXL``、``Flux``、``MMDiT``），仅负责接收标准张量并执行密集矩阵乘法。

其分层架构与调用边界如下图所示：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                                 Sampling Engine (KSampler / CFG Engine)                            |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      | 传入: x (潜变量), sigma (噪声尺度), conditioning (文本条件字典)
                                      v
   +----------------------------------------------------------------------------------------------------+
   |                                     BaseModel (高层数学与调度适配器)                                |
   |                                                                                                    |
   |   - model_sampling: ModelSampling (ContinuousEDM / DiscreteFlow / DiscreteEPS / V-Pred)           |
   |   - model_config: ModelConfig (架构超参数、输入输出通道、上下文维度)                                 |
   |   - memory_required(input_shape): 预估单次前向峰值显存                                             |
   |                                                                                                    |
   |   【apply_model(x, t, c_crossattn, c_concat, control, transformer_options) 调度流水线】             |
   |      1. 潜变量输入变换: x_in = self.model_sampling.calculate_input(sigma, x)                       |
   |      2. 时间步映射: timestep = self.model_sampling.timestep(sigma)                                 |
   |      3. 额外条件打包: adm = self.process_adm_conditions(c_adm, noise_level)                         |
   |      4. 调用底层骨干: out = self.diffusion_model(x_in, timestep, context=c_crossattn, y=adm, ...)    |
   |      5. 物理输出还原: output = self.model_sampling.calculate_denoised(sigma, out, x)               |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      | 传入纯净 Tensor 参数
                                      v
   +----------------------------------------------------------------------------------------------------+
   |                               DiffusionModel (底层 PyTorch 神经网络骨干)                           |
   |                                                                                                    |
   |   - UNetModel / OpenAISDXXL (ResBlock + SpatialTransformer + SkipConnections)                      |
   |   - MMDiT / Flux (DoubleStreamBlock + SingleStreamBlock + RoPE + Modulated RMSNorm)                |
   |   - HunyuanVideo / LTXV (3D Spatio-Temporal Factorized Transformer)                                |
   +----------------------------------------------------------------------------------------------------+

1.1 BaseModel 核心抽象方法规范
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: BaseModel 核心接口定义与工程职责
   :widths: 25 30 45
   :header-rows: 1

   * - 核心方法 / 属性
     - 返回值 / 类型
     - 物理语义与工程职责
   * - ``apply_model()``
     - ``torch.Tensor``
     - 扩散模型统一前向入口，负责组装所有条件并协调底层网络与 ControlNet 残差计算。
   * - ``model_sampling``
     - ``ModelSamplingBase`` 实例
     - 封装特定生成范式的微分方程物理参数（如 EDM、Rectified Flow、Discrete EPS）。
   * - ``memory_required()``
     - ``int`` (字节数)
     - 基于当前输入分辨率动态预估前向激活值与中间特征显存，供显存调度器分配预算。
   * - ``process_latent_in()``
     - ``torch.Tensor``
     - 潜空间通道重排、维度扩展或打补丁（Patchify/Unpatchify）预处理。
   * - ``process_latent_out()``
     - ``torch.Tensor``
     - 将网络输出转换为标准潜变量格式（如去通道重排、反归一化）。

------------------------------------------------------------------------

2. 多代生成模型族谱分类学（Taxonomy）
-------------------------------------

ComfyUI 在 ``comfy/model_base.py`` 中通过面向对象继承体系，为数十种主流生成模型建立了严密的分类学树状结构：

.. code-block:: text

   BaseModel (顶级基类)
      |
      +---> SD15 (Stable Diffusion 1.5 - EPS/V-Pred, 77-Token CLIP-L)
      |        |
      |        +---> SD20 / SD21Unclip (SD 2.x - OpenCLIP-ViT/H, 1024 维表征)
      |
      +---> SDXL (SDXL Base - UNet, 双文本编码器 CLIP-L + OpenCLIP-G, Micro-Conditioning)
      |        |
      |        +---> SDXLRefiner (精炼阶段专用模型，无输入文本条件交叉注意力)
      |        +---> SSD1B / Segmind (精简版剪枝 UNet 骨干)
      |
      +---> SVD_img2vid (Stable Video Diffusion - 3D 卷积时空架构, 时间轴注意力)
      |
      +---> StableCascade_C / StableCascade_B (两阶段级联架构, 极高压缩率潜空间)
      |
      +---> SD3 (Stable Diffusion 3 - MMDiT 双流多模态架构, T5-XXL + CLIP)
      |
      +---> Flux (Flux.1 - 双流 DoubleStreamBlock + 单流 SingleStreamBlock 混合架构, RoPE)
      |
      +---> AuraFlow / PixArt / HunyuanDiT (MMDiT / DiT 变体系列)
      |
      +---> HunyuanVideo / LTXV (现代长视频生成 DiT 骨干)

2.1 UNet 与 DiT 模型族的物理差异对比
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 跨代扩散模型核心架构与物理参数对比
   :widths: 16 20 22 22 20
   :header-rows: 1

   * - 模型架构
     - 代表模型
     - 骨干网络拓扑
     - 文本条件注入机制
     - 采样方程类型
   * - **Gen 1 UNet**
     - SD 1.5 / SD 2.1
     - 4 级下采样-中间-上采样 + 残差跳跃连接
     - 单流 Cross-Attention
     - 离散时间步 EPS / V-Pred
   * - **Gen 2 UNet**
     - SDXL / SDXL-Refiner
     - 3 级大通道 UNet + Micro-Conditioning
     - 双 CLIP 拼接 Cross-Attn + Pooled 向量
     - 离散时间步 EPS 预测
   * - **Gen 3 级联/视频**
     - SVD / Stable Cascade
     - 3D 时空 UNet / 级联自编码 UNet
     - 帧间交叉注意力 + FPS/Motion 嵌入
     - EDM 连续尺度方程
   * - **Gen 4 双流 DiT**
     - SD3 / Flux.1
     - 纯 Transformer 块（无卷积与跳跃连接）
     - 双流独立 QK 计算 + 单流融合多模态
     - Rectified Flow (流匹配)

------------------------------------------------------------------------

3. 权重签名自动探测与模型配置工厂（``model_detection.py``）
------------------------------------------------------------

在生产实践中，用户下载的权重文件（`.safetensors` 或 `.ckpt`）往往没有显式的配置文件。ComfyUI 的一大核心工程优势在于**零配置全自动模型探测**。

3.1 基于张量形状与关键 Key 的嗅探算法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

ComfyUI 在 ``comfy/supported_models_base.py`` 中为每种模型架构定义了独一无二的“特征签名（Signature Probe）”：

.. code-block:: python

    class ModelConfigBase:
        @classmethod
        def matches(cls, unet_config, state_dict):
            # 基础匹配判定接口
            return False

在解析模型文件时，探测引擎遍历各支持模型的配置类，执行多维度规则匹配：

.. code-block:: python

    # 1. 嗅探 Flux.1 架构签名
    if "double_blocks.0.img_attn.qkv.weight" in state_dict:
        # 命中 Flux.1 双流结构特征
        in_channels = state_dict["img_in.weight"].shape[1]
        vec_in_dim = state_dict["vector_in.in_layer.weight"].shape[1]
        return comfy.supported_models.Flux(unet_config, state_dict)

    # 2. 嗅探 SD3 架构签名
    elif "joint_blocks.0.context_block.attn.qkv.weight" in state_dict:
        # 命中 SD3 MMDiT 结构特征
        return comfy.supported_models.SD3(unet_config, state_dict)

    # 3. 嗅探 SDXL 架构签名
    elif "diffusion_model.input_blocks.4.1.transformer_blocks.0.attn2.to_k.weight" in state_dict:
        k_dim = state_dict["diffusion_model.input_blocks.4.1.transformer_blocks.0.attn2.to_k.weight"].shape[1]
        if k_dim == 2048:
            # 2048 维度命中 SDXL (CLIP-L 768 + OpenCLIP-G 1280)
            return comfy.supported_models.SDXL(unet_config, state_dict)

3.2 探测流程决策树
~~~~~~~~~~~~~~~~~~

.. code-block:: text

   输入未知的 state_dict
             |
             +---> 检查是否存在 "double_blocks.0..." ──[YES]──> 识别为 Flux.1 (加载 Flux 骨干与 Flow 采样)
             |
             +---> 检查是否存在 "joint_blocks.0..." ──[YES]──> 识别为 SD3 (加载 MMDiT 骨干)
             |
             +---> 检查是否存在 "diffusion_model.input_blocks..." (UNet 家族)
                      |
                      +---> 检查 cross-attention 维度 == 2048 ──[YES]──> 识别为 SDXL Base
                      +---> 检查 cross-attention 维度 == 1280 ──[YES]──> 识别为 SDXL Refiner
                      +---> 检查 cross-attention 维度 == 1024 ──[YES]──> 识别为 SD 2.x
                      +---> 检查 cross-attention 维度 == 768  ──[YES]──> 识别为 SD 1.5

------------------------------------------------------------------------

4. 时间步与条件投影的数学模型
------------------------------

无论模型属于 UNet 还是 DiT，连续的噪声尺度 :math:`\sigma` 必须转化为神经网络能够理解的高维特征向量。

4.1 正弦时间步编码（Sinusoidal Timestep Embedding）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于给定标量时间步 :math:`t`，标准正弦位置编码计算公式为：

.. math::

   	ext{PE}(t, 2i) = \sin\left(\frac{t}{10000^{2i/d_{	ext{model}}}}\right)

   	ext{PE}(t, 2i+1) = \cos\left(\frac{t}{10000^{2i/d_{	ext{model}}}}\right)

随后通过两层含非线性激活（SiLU）的多层感知机进行投影：

.. math::

   \mathbf{e}_t = 	ext{Linear}_2\left(	ext{SiLU}\left(	ext{Linear}_1\left(	ext{PE}(t)\right)\right)\right)

4.2 Rectified Flow 连续流时间步与自适应调制（AdaLN）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在现代 DiT（Flux / SD3）中，模型直接基于线性插值轨迹建模：

.. math::

   x_t = (1 - t) x_0 + t \epsilon, \quad t \in [0, 1]

时间步向量 :math:`\mathbf{e}_t` 与文本池化表征 :math:`\mathbf{y}_{	ext{pooled}}` 相加后，通过调制投影层生成 6 组尺度与偏移参数（Scale & Shift）：

.. math::

   (\gamma_1, \beta_1, \alpha_1, \gamma_2, \beta_2, \alpha_2) = 	ext{MLP}(\mathbf{e}_t + \mathbf{y}_{	ext{pooled}})

这些参数被直接用于自适应调制层归一化（Adaptive LayerNorm, AdaLN），在前向计算中动态缩放 Transformer Block 的输入与残差通路。

------------------------------------------------------------------------

小结与下章导读
==============

本节系统建立了 ComfyUI 的骨干模型抽象体系：

1. **双层解耦设计**：确立了 ``BaseModel``（调度与数学转换）与 ``DiffusionModel``（底层算子网络）的职责边界；
2. **生成模型族谱分类**：梳理了从 2D UNet、3D 视频 UNet 到双流 DiT / Flow Matching 的四代演进拓扑；
3. **架构特征探测工厂**：剖析了基于张量维度与关键 Key 的全自动零配置模型识别算法；
4. **时间步投影数学**：推导了正弦嵌入与 Flow Matching AdaLN 自适应调制方程。

在下一节（``02_latent_diffusion_unet_internals.rst``）中，我们将深入第 1 代与第 2 代扩散模型的物理基石——**Latent Diffusion UNet 核心实现**：全面剖析 ResBlock、Spatial Transformer、Cross-Attention 算子在下采样、中间瓶颈与上采样路径中的物理张量演进，以及残差跳跃连接的物理显存生命周期。
