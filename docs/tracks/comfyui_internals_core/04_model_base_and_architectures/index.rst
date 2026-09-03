========================================================================
第 4 模块：扩散模型基类与 DiT 架构抽象 (04_model_base_and_architectures)
========================================================================

.. toctree::
   :maxdepth: 2
   :caption: 模块章节目录

   01_base_model_and_unet_dit_taxonomy
   02_latent_diffusion_unet_internals
   03_dit_architecture_and_mmdit
   04_controlnet_and_guiding_mechanisms

模块架构概述
============

本模块系统解剖 ComfyUI 统一支持跨越十余种生成式基础模型（从 SD 1.5、SD 2.1、SDXL 到 SD3、Flux.1、AuraFlow、HunyuanDiT 等）的模型骨干抽象层。

ComfyUI 通过 ``comfy/model_base.py`` 建立了高度灵活且解耦的神经网络骨干抽象：

1. **BaseModel 体系架构**：统一的扩散模型基类抽象，将时间步嵌入、尺度变换、前向计算与输出格式解耦为可插拔组件。
2. **Latent Diffusion UNet 内核**：剖析 ResBlock、Spatial Transformer、Cross Attention 算子在下采样、中间层与上采样路径中的张量演进。
3. **DiT 与 MMDiT 架构演进**：深入多模态双流/单流 Diffusion Transformer 块（MMDiT Block）、旋转位置编码（RoPE）以及调制自注意力（Modulated Self-Attention）。
4. **ControlNet 与跨架构条件引导**：解析零卷积残差分支（Zero Convolution）、T2I-Adapter 特征注入与统一条件引导机制。
