========================================================================
CLIP/T5 双编码器表征空间映射、Text Embeddings 提取与 Pooled Output 投影矩阵
========================================================================

.. note:: 前置背景与上下文承接
   在前一节（``01_clip_and_t5_tokenization_pipeline.rst``）中，我们系统剖析了文本前端分词管道、嵌套加权语法词法分析树（Lexer AST）、77-Token 长文本无损切块以及空基线相对差分外推代数。然而，分词器输出的离散 Token 索引序列必须经过深度神经网络（CLIP Text Encoder、T5-XXL 或自回归 LLM 骨干）的非线性映射，才能转化为高维语义流形上的连续嵌入向量。在生成式大模型的发展脉络中，文本表征从单编码器（SD 1.5 单 CLIP-L）演进至双编码器（SDXL 双 CLIP、Flux.1 CLIP+T5）乃至多模态混合大语言模型（SD3.5、HunyuanVideo）。ComfyUI 在 ``comfy/sd1_clip.py``、``comfy/sdxl_clip.py`` 与 ``comfy/text_encoders/`` 中构建了一套高度通用且解耦的 **多文本编码器表征空间映射与池化投影体系（Multi-Text-Encoder Representation & Pooling Architecture）**。本节深入拆解隐藏层特征提取（Layer Selection）、隐层归一化（LayerNorm）、多通道跨模型嵌入对齐以及全局 Pooled Output 投影矩阵的底层物理实现。

------------------------------------------------------------------------

1. 多代模型文本编码器族谱与表征空间拓扑
---------------------------------------

随着扩散模型对复杂指令理解、空间属性绑定（Attribute Binding）与文字排版生成能力的提升，文本编码器经历了从“纯视觉对比学习空间”向“多模态与自回归语义空间混合表征”的深刻演进。

其主流架构族谱与表征空间拓扑如下图所示：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                                 多代模型文本编码器表征空间拓扑                                      |
   +----------------------------------------------------------------------------------------------------+
   
   【Gen 1: SD 1.5 / 2.1 (单编码器时代)】
     Tokens (77) ──> CLIP-L/14 (12 layers, D=768) ──> Sequence Embeddings [B, 77, 768] (Penultimate)
   
   【Gen 2: SDXL (双 CLIP 混合时代)】
     Tokens (77) ──> CLIP-L/14 (12 layers, D=768)  ──> [B, 77, 768]  ──┐ (通道维度拼接)
     Tokens (77) ──> OpenCLIP-G (32 layers, D=1280) ─> [B, 77, 1280] ─┴─> Cross-Attention: [B, 77, 2048]
                                                    └─> Text Projection (D=1280) ──> Pooled Output [B, 1280]
   
   【Gen 4: SD3 / SD3.5 (三编码器融合时代)】
     Tokens (77)  ──> CLIP-L/14   ──> [B, 77, 768]  ──┐ (通道对齐与补齐)
     Tokens (77)  ──> OpenCLIP-G  ──> [B, 77, 1280] ──┼─> Concat/Pad ──> Joint Cross-Attn: [B, L, 4096]
     Tokens (512) ─> T5-XXL-v1.1 ──> [B, 512, 4096] ─┘
                                  └─> CLIP-L+G Pooled [B, 768+1280=2048] ──> Vector Conditioning (AdaLN)
   
   【Gen 4: Flux.1 (解耦双编码器时代)】
     Tokens (77)  ──> CLIP-L/14   ──> Pooled Output Only: [B, 768] ──> AdaLN 全局引导 (y 向量)
     Tokens (512) ─> T5-XXL-v1.1 ──> Sequence Embeddings Only: [B, 512, 4096] ──> 双流 DiT 文本序列输入

1.1 核心文本编码器技术规格全景矩阵
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 主流生成式模型文本编码器技术参数与输出空间对照
   :widths: 16 22 22 20 20
   :header-rows: 1

   * - 模型族系
     - 包含的文本编码器组合
     - 序列嵌入维度 (Sequence)
     - 全局池化维度 (Pooled)
     - 语义空间偏向
   * - **SD 1.5**
     - CLIP-L/14 (OpenAI)
     - :math:`[B, 77 \cdot N, 768]`
     - 无显式 Pooled 向量
     - 粗粒度概念关联、图文美学匹配
   * - **SDXL**
     - CLIP-L/14 + OpenCLIP-G/14
     - :math:`[B, 77 \cdot N, 2048]`
     - :math:`[B, 1280]` (来自 OpenCLIP-G)
     - 宏观画风 + 细粒度物体结构
   * - **SD3 / 3.5**
     - CLIP-L + OpenCLIP-G + T5-XXL
     - :math:`[B, 77 \cdot N + 512, 4096]`
     - :math:`[B, 2048]` (双 CLIP 拼接)
     - 细粒度逻辑关系、文本字符拼写
   * - **Flux.1**
     - CLIP-L/14 + T5-XXL-v1.1
     - :math:`[B, 512, 4096]` (仅取 T5)
     - :math:`[B, 768]` (仅取 CLIP-L)
     - 极致长文本遵从度与排版控制
   * - **HunyuanVideo**
     - LLaMA-3-8B / Qwen-2.5-7B
     - :math:`[B, 256, 4096]`
     - 隐式自回归池化
     - 复杂时空动作描述与多语言理解

------------------------------------------------------------------------

2. 隐藏层特征提取（Layer Selection）与隐层归一化机理
----------------------------------------------------

在标准预训练 CLIP 模型中，文本编码器的最后一层隐藏状态直接用于计算与图像编码器的 InfoNCE 对比损失（Contrastive Loss）。这一训练目标强迫所有细粒度词汇信息迅速坍缩为少数具有高度判别力的全局语义特征。

2.1 倒数第二层（Penultimate Layer, ``layer_idx = -2``）物理优势
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

扩散模型的核心诉求与分类模型完全相反：**扩散去噪过程需要保留提示词中每一个形容词、方位词与从句的局部空间拓扑**。

如果在最后一层提取特征，提示词中的细微修饰语（如“条纹纹理”、“在左上角”）会被严重平滑。因此，自 SD 2.0 与 SDXL 开始，行业标准均切换至提取倒数第二层（Penultimate Layer，即 ``layer_idx = -2``）隐藏状态：

.. math::

   \mathbf{H}_{	ext{penultimate}} = 	ext{EncoderBlock}_{L-2}\left( \dots 	ext{EncoderBlock}_0(\mathbf{x}_{	ext{embed}}) \right)

2.2 隐藏层提取与归一化（``CLIPEncoder`` 与 ``SDClipModel``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

ComfyUI 在 ``comfy/clip_model.py`` 的 ``CLIPEncoder.forward()`` 中实现了任意隐藏层索引的精确截断与克隆提取：

.. code-block:: python

    class CLIPEncoder(torch.nn.Module):
        def forward(self, x, mask=None, intermediate_output=None):
            # 将负索引转换为正向层号: -2 转换为 12 - 2 = 10
            if intermediate_output is not None and intermediate_output < 0:
                intermediate_output = len(self.layers) + intermediate_output

            intermediate = None
            for i, l in enumerate(self.layers):
                x = l(x, mask, optimized_attention)
                if i == intermediate_output:
                    # 原位深拷贝指定层的未退化隐藏状态
                    intermediate = x.clone()

            return x, intermediate

在 ``SDClipModel.forward()`` 中，系统根据模型配置决定是否对该中间层施加最终的层归一化（``final_layer_norm``）：

.. code-block:: python

    outputs = self.transformer(..., intermediate_output=self.layer_idx,
                               final_layer_norm_intermediate=self.layer_norm_hidden_state)
    if self.layer == "last":
        z = outputs[0].float()
    else:
        z = outputs[1].float() # 取得倒数第二层隐藏状态

- **SD 1.5**：默认提取最后一层（``layer = "last"``），带有 ``final_layer_norm``；
- **SDXL**：CLIP-L 与 CLIP-G 均强制指定 ``layer = "hidden", layer_idx = -2``，且 ``layer_norm_hidden_state = False``，直接向 UNet 传递未经过度缩放的原始激活特征。

------------------------------------------------------------------------

3. 全局池化表征（Pooled Output）与投影矩阵代数
-----------------------------------------------

除了在序列维度上指导 Cross-Attention 注意力机制的局部特征（Sequence Embeddings）外，现代扩散模型还需要一个全局语义向量（Global Vector），用于对整张图像的风格、光影与基础基调进行全局调制。

3.1 EOS Token 定位与池化张量抽取
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在因果语言模型（Causal LM）与 CLIP Transformer 中，序列终止符 ``<|endoftext|>``（EOS）在经过全层自注意力后汇聚了全句的上下文信息。

ComfyUI 在 ``CLIPTextModel_.forward()`` 中实现了基于实际有效 Token 长度的动态 EOS 索引定位：

.. code-block:: python

    if num_tokens is not None:
        # 基于分词器实际统计的有效 Token 数 (扣除 Padding) 定位 EOS
        pooled_output = x[list(range(x.shape[0])), list(map(lambda a: a - 1, num_tokens))]
    else:
        # 基于 argmax 动态搜寻 eos_token_id 所在的最右侧位置
        eos_indices = (torch.round(input_tokens).to(dtype=torch.int, device=x.device) == self.eos_token_id).int().argmax(dim=-1)
        pooled_output = x[torch.arange(x.shape[0], device=x.device), eos_indices]

3.2 文本投影矩阵（``text_projection``）与空间映射
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在原生 OpenAI CLIP 架构中，隐藏层特征维度为 :math:`D_{	ext{hidden}} = 768`（CLIP-L）或 :math:`1280`（CLIP-G），而多模态对比空间的共享维度为 :math:`D_{	ext{proj}} = 768` 或 :math:`1280`。

通过无偏置线性投影矩阵 :math:`\mathbf{W}_{	ext{proj}} \in \mathbb{R}^{D_{	ext{hidden}} 	imes D_{	ext{proj}}}`：

.. math::

   \mathbf{z}_{	ext{pooled}} = \mathbf{h}_{	ext{eos}} \cdot \mathbf{W}_{	ext{proj}}

在 ComfyUI 中，通过 ``return_projected_pooled`` 布尔标志位灵活切换：

- **SDXL**：使用经过投影的 ``g_pooled``（维度 1280），与 Micro-Conditioning 原始图像尺寸/裁剪坐标向量拼接后，形成 2816 维全局条件向量注入 UNet 的 ADM（Adaptive Model）投影层；
- **Flux.1**：直接使用未投影的 CLIP-L 原始 EOS 特征（维度 768），注入 DiT 的 ``AdaLN-Single`` 时间步/条件调制模块。

------------------------------------------------------------------------

4. 多通道跨模型嵌入对齐与拼接引擎
---------------------------------

在双编码器与三编码器协同推理中，不同网络的分词粒度、词表映射与截断长度存在天然差异。ComfyUI 在顶层类（如 ``SDXLClipModel`` 与 ``FluxClipModel``）中构建了零拷贝特征对齐与融合引擎。

4.1 SDXL 双 CLIP 特征对齐与通道拼接
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``comfy/sdxl_clip.py`` 的 ``SDXLClipModel.encode_token_weights()`` 中：

.. code-block:: python

    def encode_token_weights(self, token_weight_pairs):
        token_weight_pairs_g = token_weight_pairs["g"]
        token_weight_pairs_l = token_weight_pairs["l"]

        # 分别独立执行空基线加权编码
        g_out, g_pooled = self.clip_g.encode_token_weights(token_weight_pairs_g)
        l_out, l_pooled = self.clip_l.encode_token_weights(token_weight_pairs_l)

        # 1. 序列长度维度硬对齐 (防范多 Chunk 分块边界不一致)
        cut_to = min(l_out.shape[1], g_out.shape[1])

        # 2. 在特征维度 (dim = -1) 执行拼接: [B, 77, 768] + [B, 77, 1280] => [B, 77, 2048]
        concat_features = torch.cat([l_out[:, :cut_to], g_out[:, :cut_to]], dim=-1)

        return concat_features, g_pooled

4.2 Flux.1 双编码器彻底解耦分工
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``comfy/text_encoders/flux.py`` 的 ``FluxClipModel.encode_token_weights()`` 中，ComfyUI 实现了极致的语义职责解耦：

.. code-block:: python

    def encode_token_weights(self, token_weight_pairs):
        token_weight_pairs_l = token_weight_pairs["l"]
        token_weight_pairs_t5 = token_weight_pairs["t5xxl"]

        # T5-XXL 提供超长上下文细粒度序列嵌入 [B, 512, 4096]
        t5_out, t5_pooled = self.t5xxl.encode_token_weights(token_weight_pairs_t5)
        # CLIP-L 仅提供整句视觉美学对齐的全局池化向量 [B, 768]
        l_out, l_pooled = self.clip_l.encode_token_weights(token_weight_pairs_l)

        return t5_out, l_pooled

这种设计不仅完全免除了 CLIP-L 与 T5-XXL 在序列维度上的复杂对齐开销，更让 T5-XXL 专注负责空间 Token 交叉注意力，让 CLIP-L 专注负责全局风格调制，形成了完美的数学互补。

------------------------------------------------------------------------

5. 显存管理与动态精度适配（``CoreModelPatcher`` 与 Mixed Precision）
---------------------------------------------------------------------

T5-XXL 与大语言模型文本编码器的参数量高达 4.7B ~ 8B（以 FP16 存储需 10GB~16GB 显存）。如果全程驻留显存，消费级 GPU 将无法运行后续的扩散去噪循环。

ComfyUI 通过以下机制实现了极致的显存优化：

1. **按需即时换入换出（On-Demand Offloading）**：
   在 ``CLIP.encode_from_tokens()`` 中，调用 ``load_model()`` 仅在文本编码前一拍将文本编码器搬移至 GPU，前向计算完成后立即向 CPU 卸载，为扩散模型释放全部显存空间；
2. **混合精度与量化运算（Mixed Precision Ops）**：
   通过 ``comfy.ops.mixed_precision_ops`` 原生支持 FP8（E4M3 / E5M2）、NF4 与 INT8 量化权重的前向推理，在 8GB 显存设备上即可流畅运行 4.7B 参数的 T5-XXL。

------------------------------------------------------------------------

小结与下章导读
==============

本节系统剖析了 ComfyUI 的文本编码器表征空间映射与池化投影体系：

1. **多代编码器族谱**：梳理了从单 CLIP-L、双 CLIP (SDXL) 到混合 T5 (SD3/Flux) 的表征演进路径；
2. **倒数第二层特征提取**：推导了 ``layer_idx = -2`` 避免对比损失过度平滑、保留细粒度局部属性的物理优势；
3. **Pooled Output 投影代数**：解析了基于动态 EOS Token 定位的全局向量抽取与投影矩阵映射；
4. **跨模型嵌入对齐**：拆解了 SDXL 序列通道拼接（2048 维）与 Flux.1 序列/池化彻底解耦分工的高性能实现；
5. **显存流式调度**：阐明了结合量化算子与按需卸载的端侧大模型推理策略。

在下一节（``03_vae_architecture_and_tiling.rst``）中，我们将转向图像潜空间转换的另一核心枢纽——**变分自编码器（VAE）卷积编解码拓扑与数值重归一化**：深入拆解 ResnetBlock、Self-Attention、空间下采样/上采样金字塔、潜空间缩放因子（``scaling_factor``）以及颜色通道统计对齐的底层机理。
