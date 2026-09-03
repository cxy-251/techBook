========================================================================
文本分词器 Tokenizer 管道、多权重加权语法解析与 77-Token 长文本切块机制
========================================================================

.. note:: 前置背景与上下文承接
   在第 5 模块《采样器数值解法与调度方程》中，我们完整剖析了扩散微分方程的数值积分器（Euler, Heun, DPM-Solver++, UniPC）与无分类器引导（CFG）的几何流形修正。然而，采样器与去噪骨干网络的所有条件引导信号，源头均来自用户输入的自然语言提示词（Prompt）。在现代生成式 AI 中，文本编码并非简单的字符串查找——它涉及**嵌套加权语法词法分析（AST Weight Parsing）**、**Textual Inversion（Embedding）动态张量注入**、**CLIP 77-Token 硬件硬限制突破与无缝多块拼接（Chunking & Batching）**，以及**相对于空基线的词向量权重外推代数**。ComfyUI 在 ``comfy/sd1_clip.py`` 与 ``comfy/text_encoders/`` 中构建了工业界最具表达力的高性能分词流水线。本节系统拆解这一机制的词法分析、张量拓扑与数学原理。

------------------------------------------------------------------------

1. 文本分词管道架构与端到端数据流
---------------------------------

ComfyUI 的文本前端处理将用户的原始字符串逐步转化为多通道对齐的高维特征矩阵，其端到端物理流水线如下图所示：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |  Raw Prompt String: "a (cyberpunk cat:1.2), glowing neon eyes, embedding:retro_style, (masterpiece) |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      | 1. 转义保护: escape_important() 保护 "\(" 与 "\)"
                                      v
   +----------------------------------------------------------------------------------------------------+
   |                                token_weights() 递归括号词法分析树 (Lexer AST)                        |
   |   - "(cyberpunk cat:1.2)"  ──> [("cyberpunk cat", 1.2)]                                            |
   |   - "(masterpiece)"        ──> [("masterpiece", 1.1)] (缺省冒号则乘 1.1)                           |
   |   - "glowing neon eyes"    ──> [("glowing neon eyes", 1.0)]                                        |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      | 2. Embedding 识别与外挂张量替换: _try_get_embedding()
                                      v
   +----------------------------------------------------------------------------------------------------+
   |                                BPE / WordPiece 分词与张量交织列表                                  |
   |   - "cyberpunk" ──> [token_1024, token_305] (权重 1.2)                                             |
   |   - "embedding:retro_style" ──> 注入外部预训练 Tensor: [N_vectors, 768] (权重 1.0)                  |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      | 3. 77-Token 边界划分与词边界保护: SDTokenizer.tokenize_with_weights()
                                      v
   +----------------------------------------------------------------------------------------------------+
   |                           Batched Chunks 结构 (每块固定 77 Tokens)                                 |
   |   - Chunk 0: [START_49406, token_a, ..., token_k, END_49407, PAD_49407...]                        |
   |   - Chunk 1: [START_49406, token_l, ..., token_z, END_49407, PAD_49407...]                        |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      | 4. 神经网络前向与空基线差分外推: ClipTokenWeightEncoder
                                      v
   +----------------------------------------------------------------------------------------------------+
   |   Final Text Embedding: torch.cat([Chunk_0, Chunk_1], dim=1) => [1, 154, 768/2048/4096]            |
   |   Pooled Output: first_pooled => [1, 768/1280]                                                     |
   +----------------------------------------------------------------------------------------------------+

------------------------------------------------------------------------

2. 嵌套权重语法解析引擎（Token Weight Parsing）
------------------------------------------------

在生成式图像控制中，用户广泛使用括号语法精细调整特定词汇的生成权重：

- ``(word)``：默认权重乘以 $1.1$；
- ``((word))``：嵌套乘法，权重为 $1.1 	imes 1.1 = 1.21$；
- ``(word:1.35)``：显式指定绝对权重为 $1.35$；
- ``[word]`` / ``(word:0.8)``：降低权重至 $0.8$ 或 $1/1.1 \approx 0.909$。

2.1 递归词法状态机实现
~~~~~~~~~~~~~~~~~~~~~~

ComfyUI 在 ``comfy/sd1_clip.py`` 中通过 ``parse_parentheses()`` 与 ``token_weights()`` 递归构造语法分析树：

.. code-block:: python

    def parse_parentheses(string):
        result = []
        current_item = ""
        nesting_level = 0
        for char in string:
            if char == "(":
                if nesting_level == 0:
                    if current_item:
                        result.append(current_item)
                    current_item = "("
                else:
                    current_item += char
                nesting_level += 1
            elif char == ")":
                nesting_level -= 1
                if nesting_level == 0:
                    result.append(current_item + ")")
                    current_item = ""
                else:
                    current_item += char
            else:
                current_item += char
        if current_item:
            result.append(current_item)
        return result

2.2 转义保护与空括号防御
~~~~~~~~~~~~~~~~~~~~~~~~

为了避免提示词中合法的文本标点（如表情符号 ``:)`` 或数学公式 ``\(x + y\)``）破坏词法树，系统采用空字符转义技术：

.. code-block:: python

    def escape_important(text):
        text = text.replace(r"\)", "\0\1")
        text = text.replace(r"\(", "\0\2")
        return text

    def unescape_important(text):
        text = text.replace("\0\1", ")")
        text = text.replace("\0\2", "(")
        return text

------------------------------------------------------------------------

3. 词向量权重外推代数：空基线差分模型
-------------------------------------

在传统实现中，部分推理框架尝试直接在注意力计算时将 Token 的 Attention Logits 乘以权重因子 :math:`w`。这种方式破坏了 Softmax 的概率和为 1 约束，导致注意力权重在深层网络中发生数值偏移。

ComfyUI 采用了极富创新的 **空基线相对差分外推代数（Relative Extrapolation against Empty Baseline）**。

3.1 权重外推数学推导
~~~~~~~~~~~~~~~~~~~~

设纯净的空提示词文本块（仅包含 ``START``、``END`` 与 ``PAD`` 特征）通过 CLIP 编码器后在第 :math:`j` 个 Token 位置输出的嵌入向量为 :math:`\mathbf{z}_{	ext{empty}, j}`；包含完整提示词的文本块在第 :math:`j` 个 Token 位置输出的原始特征向量为 :math:`\mathbf{z}_{j}`。

当用户为该 Token 指定了权重 :math:`w 
eq 1.0` 时，ComfyUI 在 ``ClipTokenWeightEncoder.encode_token_weights()`` 中执行线性几何外推：

.. math::

   \mathbf{z}_{j}^{	ext{weighted}} = (\mathbf{z}_{j} - \mathbf{z}_{	ext{empty}, j}) \cdot w + \mathbf{z}_{	ext{empty}, j} = \mathbf{z}_{	ext{empty}, j} + w \cdot \Delta \mathbf{z}_j

.. list-table:: 空基线差分外推代数物理特性
   :widths: 22 28 50
   :header-rows: 1

   * - 权重因子取值
     - 数学运算形式
     - 物理几何含义
   * - :math:`w = 1.0`
     - :math:`\mathbf{z}_j`
     - 保持原生 CLIP 文本语义特征不变。
   * - :math:`w > 1.0`
     - :math:`\mathbf{z}_{	ext{empty}, j} + w \Delta \mathbf{z}_j`
     - 沿语义偏移方向向外投射，强化该词的特征激活强度与显著性。
   * - :math:`w = 0.0`
     - :math:`\mathbf{z}_{	ext{empty}, j}`
     - 完全退化为空背景向量，该词在潜空间中完全“隐形”。
   * - :math:`0.0 < w < 1.0`
     - :math:`\mathbf{z}_{	ext{empty}, j} + w \Delta \mathbf{z}_j`
     - 在空背景与该词特征之间进行线性插值，淡化语义影响。

这种方法既保留了 Transformer 内部残差流的几何流形曲率，又在无需修改网络底层权重的前提下实现了连续线性的语义强度精确缩放。

------------------------------------------------------------------------

4. CLIP 77-Token 硬件硬限制突破与分块拼接机制
----------------------------------------------

OpenAI 的原始 CLIP ViT-L/14 架构设定了固定的位置编码表长度为 77（包含 1 个起始 Token ``<|startoftext|>``、75 个有效词 Token 与 1 个终止 Token ``<|endoftext|>``）。当用户提示词超过 75 个单词时，标准 CLIP 会直接截断抛弃超出部分。

ComfyUI 在 ``SDTokenizer.tokenize_with_weights()`` 中设计了透明的 **无损长文本分块算法（Long-Prompt Chunking & Concatenation）**。

4.1 词边界保护分块算法
~~~~~~~~~~~~~~~~~~~~~~

为了防止一个被拆分为多个 Sub-word 的复杂专有名词（如医学术语或生僻人名）被生硬地截断在两个 77-Token 分块的交界处，ComfyUI 引入了词边界智能检测（``max_word_length = 8``）：

.. code-block:: python

    for i, t_group in enumerate(tokens):
        # 判定当前词被分词后的子 Token 组是否过长
        is_large = len(t_group) >= self.max_word_length

        while len(t_group) > 0:
            # 检查当前 Batch 剩余槽位是否足以容纳当前单词
            if len(t_group) + len(batch) > self.max_length - has_end_token:
                remaining_length = self.max_length - len(batch) - has_end_token
                if is_large:
                    # 超长单词拆分填满当前 Batch，并闭合 END Token
                    batch.extend([(t, w, i + 1) for t, w in t_group[:remaining_length]])
                    if self.end_token is not None:
                        batch.append((self.end_token, 1.0, 0))
                    t_group = t_group[remaining_length:]
                else:
                    # 常规短词不在末尾切碎，直接提前闭合当前 Batch 并补齐 PAD
                    if self.end_token is not None:
                        batch.append((self.end_token, 1.0, 0))
                    if self.pad_to_max_length:
                        self.pad_tokens(batch, remaining_length)

                # 开启全新的 77-Token Chunk 批次
                batch = []
                if self.start_token is not None:
                    batch.append((self.start_token, 1.0, 0))
                batched_tokens.append(batch)
            else:
                batch.extend([(t, w, i + 1) for t, w in t_group])
                t_group = []

4.2 多 Chunk 独立编码与序列拼接
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

每个 77-Token Chunk 作为独立的样本打包成批次送入 CLIP 文本编码器：

.. math::

   \mathbf{Z}_{	ext{batched}} = 	ext{CLIPTextModel}\left( 	ext{Chunks} \in \mathbb{R}^{N_{	ext{chunks}} 	imes 77} \right) \in \mathbb{R}^{N_{	ext{chunks}} 	imes 77 	imes D}

在完成各自的空基线差分加权后，系统在序列长度维度上执行全量拼接：

.. math::

   \mathbf{Z}_{	ext{final}} = 	ext{Concat}\left( [\mathbf{Z}_0, \mathbf{Z}_1, \dots, \mathbf{Z}_{N-1}], \; 	ext{dim} = 1 \right) \in \mathbb{R}^{1 	imes (77 \cdot N) 	imes D}

在 UNet/DiT 的交叉注意力层中，Query 向量（潜空间特征）将对这一展开后的 :math:`77 \cdot N` 长度序列进行全自由度 Cross-Attention 寻址，从而在物理上彻底消除了 77-Token 的长度瓶颈。

------------------------------------------------------------------------

5. CLIP 与 T5-XXL 分词器架构与特性对照表
----------------------------------------

在 SD3 与 Flux.1 等现代混合多模态架构中，系统同时运行 CLIP 分词器与 T5-XXL 分词器。

.. list-table:: CLIP 与 T5-XXL 分词器技术规格与计算特征对照
   :widths: 20 40 40
   :header-rows: 1

   * - 架构维度
     - CLIP Tokenizer (SD 1.5 / SDXL)
     - T5-XXL Tokenizer (SD3 / Flux.1)
   * - **分词算法**
     - Byte-Pair Encoding (BPE)
     - SentencePiece Unigram
   * - **词表规模 (Vocab Size)**
     - 49,408
     - 32,128 (支持极丰富的多语言子词切分)
   * - **单块最大上下文 (Context Window)**
     - 77 Tokens (依赖 ComfyUI Chunking 扩展)
     - 256 / 512 Tokens (原生超长序列，无需频繁分块)
   * - **特殊标记 (Special Tokens)**
     - ``<|startoftext|>`` (49406), ``<|endoftext|>`` (49407)
     - ``</s>`` (1), ``<pad>`` (0)
   * - **表征空间关注点**
     - 图文对比对齐空间（语义概括性高，风格感强）
     - 纯自回归语言建模空间（擅长细粒度逻辑关系与长句排版）

------------------------------------------------------------------------

小结与下章导读
==============

本节系统剖析了 ComfyUI 的文本分词与条件准备管道：

1. **分词管道架构**：建立了从原始字符串、AST 词法加权树到 77-Token 批次结构的完整转换链路；
2. **空基线差分外推代数**：推导了基于 :math:`\mathbf{z}_{	ext{empty}}` 的相对几何外推公式，阐明了非侵入式语义权重缩放的数学本质；
3. **长文本分块算法**：解析了保留词边界完整性的 77-Token 动态断句与序列维度拼接物理机制；
4. **多模型分词器对照**：对比了 CLIP BPE 与 T5-XXL SentencePiece 在词表与上下文长度上的物理差异。

在下一节（``02_text_encoder_embeddings_and_pooling.rst``）中，我们将深入文本特征提取的神经网络核心——**CLIP 与 T5 双编码器表征空间映射与池化投影**：全面解析 CLIP-L、OpenCLIP-G 与 T5-XXL 的隐藏层特征提取（Layer Selection）、隐层归一化（LayerNorm）、多文本嵌入跨通道对齐与 Pooled Output 投影矩阵的底层物理实现。
