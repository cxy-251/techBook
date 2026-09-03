========================================================================
第 6 模块：文本编码与潜空间重构 (06_text_encoding_and_latent)
========================================================================

.. toctree::
   :maxdepth: 2
   :caption: 模块章节目录

   01_clip_and_t5_tokenization_pipeline
   02_text_encoder_embeddings_and_pooling
   03_vae_architecture_and_tiling
   04_tiled_vae_and_latent_preview

模块架构概述
============

本模块解剖扩散模型系统输入与输出的两大空间转换枢纽：语义文本编码（Text Encoding）与图像潜空间重构（Latent Reconstruction）。

ComfyUI 在文本与潜空间处理上设计了高度健壮的工程实现：

1. **分词管道与加权语法解析**：深度解析 CLIP/T5 分词机制、嵌套权重语法（如 ``(prompt:1.2)``）的词法分析与 77-Token 长文本动态切块对齐。
2. **文本编码器表征空间映射**：解剖双 CLIP（SDXL）及 CLIP+T5（SD3/Flux）的多通道嵌入提取、跨层特征拼接与 Pooled Output 聚合。
3. **变分自编码器（VAE）编解码**：剖析 ResnetBlock、Self-Attention 在图像像素空间与潜空间压缩比（8x/16x）之间的前向拓扑与数值重归一化。
4. **Tiled VAE 与实时预览**：剖析显存受限场景下超大分辨率切块（Tiling）算法的重叠区加权羽化融合，以及基于 TAESD 的实时流式潜变量预览。
