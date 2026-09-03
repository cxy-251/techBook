========================================================================
Latent Diffusion UNet 内部拓扑：ResBlock、Spatial Transformer 与跨层跳跃连接
========================================================================

.. note:: 前置背景与上下文承接
   在前一节（``01_base_model_and_unet_dit_taxonomy.rst``）中，我们确立了 ``BaseModel`` 与底层神经网络计算图的解耦机制，建立了跨越四代扩散模型的分类学族谱与自动架构探测工厂。在现代生成式 AI 的发展史与工业级部署中，以 Stable Diffusion 1.5 和 SDXL 为代表的 **Latent Diffusion UNet** 架构承载了极其庞大的生态资产与应用基础。尽管纯 Transformer（DiT）架构已成为前沿主流，UNet 独特的“编码器-瓶颈-解码器”对称多尺度金字塔、残差卷积与空间注意力交织结构，仍然是理解扩散模型空间特征演进、条件注入与 ControlNet 残差引导的最佳范本。本节深入 ``comfy/ldm/modules/diffusionmodules/openaimodel.py`` 与 ``comfy/ldm/modules/attention.py``，系统拆解 UNet 的物理张量演进、模块微观拓扑、Micro-Conditioning 机制以及跨层跳跃连接的显存生命周期。

------------------------------------------------------------------------

1. UNet 多尺度金字塔拓扑与数据流动管线
--------------------------------------

ComfyUI 中的 UNet 骨干（``UNetModel`` / ``OpenAISDXXL``）由三大连续对称阶段构成：

1. **下采样编码路径（``input_blocks``）**：逐级降低空间分辨率，提取高阶语义并压栈缓存跳跃特征；
2. **中间信息瓶颈（``middle_block``）**：在极小分辨率（如 $1/8$ 或 $1/32$ 潜空间尺度）下执行密集的全局自注意力和跨模态交叉注意力计算；
3. **上采样解码路径（``output_blocks``）**：逐级恢复空间分辨率，通过通道拼接（Channel Concatenation）融合编码器缓存的细粒度空间纹理。

其物理拓扑张量流动图如下所示：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                                 Latent Input x: [B, C_in, H, W] (如 [1, 4, 64, 64])                |
   |                                 Timestep t: [B] / Context c: [B, Tokens, D_context]                 |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      v
   +----------------------------------------------------------------------------------------------------+
   |                                 input_blocks (下采样编码路径 - nn.ModuleList)                       |
   |                                                                                                    |
   |   [Layer 0]: Conv2d(3x3) -> [B, 320, 64, 64] ───────────────────────────┐ (压入 hs 栈)           |
   |   [Layer 1-2]: ResBlock + SpatialTransformer(Depth) -> [B, 320, 64, 64] ──┤                        |
   |   [Layer 3]: Downsample / ResBlock(Down) -> [B, 320->640, 32, 32] ────────┤                        |
   |   [Layer 4-5]: ResBlock + SpatialTransformer(Depth) -> [B, 640, 32, 32] ──┤                        |
   |   [Layer 6]: Downsample / ResBlock(Down) -> [B, 640->1280, 16, 16] ───────┤ (共缓存 12-16 个       |
   |   [Layer 7-8]: ResBlock + SpatialTransformer(Depth) -> [B, 1280, 16, 16] ─┤  多尺度中间张量)        |
   |   [Layer 9]: Downsample / ResBlock(Down) -> [B, 1280, 8, 8] ──────────────┤                        |
   |   [Layer 10-11]: ResBlock + (Optional Attn) -> [B, 1280, 8, 8] ──────────┘                        |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      | [B, 1280, 8, 8]
                                      v
   +----------------------------------------------------------------------------------------------------+
   |                                 middle_block (中间语义瓶颈)                                        |
   |                                                                                                    |
   |   ResBlock -> SpatialTransformer(High Depth) -> ResBlock  =>  [B, 1280, 8, 8]                      |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      | [B, 1280, 8, 8]
                                      v
   +----------------------------------------------------------------------------------------------------+
   |                                 output_blocks (上采样解码路径 - nn.ModuleList)                      |
   |                                                                                                    |
   |   [Layer 0]: Pop hs -> Cat([h, hsp], dim=1): [B, 2560, 8, 8] -> ResBlock + Attn                  |
   |   [Layer 1-2]: Pop hs -> Cat -> ResBlock + Attn -> Upsample -> [B, 1280, 16, 16]                  |
   |   [Layer 3-5]: Pop hs -> Cat -> ResBlock + Attn -> Upsample -> [B, 640, 32, 32]                   |
   |   [Layer 6-8]: Pop hs -> Cat -> ResBlock + Attn -> Upsample -> [B, 320, 64, 64]                   |
   |   [Layer 9-11]: Pop hs -> Cat -> ResBlock + Attn -> [B, 320, 64, 64]                              |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      v
   +----------------------------------------------------------------------------------------------------+
   |                 out: GroupNorm(32) -> SiLU() -> Conv2d(3x3) => [B, C_out, H, W] (预测噪声/速度)     |
   +----------------------------------------------------------------------------------------------------+

1.1 SD 1.5 与 SDXL UNet 物理拓扑规格对比
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: SD 1.5 与 SDXL 骨干网络物理参数详尽对照
   :widths: 22 38 40
   :header-rows: 1

   * - 架构维度
     - SD 1.5 UNet
     - SDXL UNet (OpenAISDXXL)
   * - **基础通道数 (model_channels)**
     - 320
     - 320
   * - **通道倍率 (channel_mult)**
     - ``(1, 2, 4, 4)`` (4 级分辨率: 64, 32, 16, 8)
     - ``(1, 2, 4)`` (3 级分辨率: 128, 64, 32)
   * - **跨注意力维度 (context_dim)**
     - 768 (单个 CLIP ViT-L/14)
     - 2048 (CLIP-L 768 + OpenCLIP-bigG 1280 拼接)
   * - **注意力头分配机制**
     - 固定头数 ``num_heads = 8``
     - 固定头维度 ``num_head_channels = 64``
   * - **Transformer 深度 (Depth)**
     - 全局每层 1 个 SpatialTransformer Block
     - 分辨率级联深度: 输入层 ``[0, 2, 10]``，中间层 ``10``，输出层 ``[0, 2, 10]``
   * - **额外条件输入 (adm_in_channels)**
     - 无 (仅标量类别条件可选)
     - 2816 (Pooled Text 1280 + 6 个微条件坐标 1536)

------------------------------------------------------------------------

2. 残差卷积块（``ResBlock``）微观拓扑与时间步注入
-------------------------------------------------

``ResBlock``（定义于 ``comfy/ldm/modules/diffusionmodules/openaimodel.py``）负责在特征图维度变化时维持梯度的平滑流动，并将标量时间步嵌入向量（Timestep Embedding）与类别/尺寸嵌入向量深度注入空间特征。

2.1 物理计算图与时间步调制
~~~~~~~~~~~~~~~~~~~~~~~~~~

对于输入特征张量 :math:`x \in \mathbb{R}^{B 	imes C_{	ext{in}} 	imes H 	imes W}` 与时间步嵌入向量 :math:`\mathbf{e}_{	ext{emb}} \in \mathbb{R}^{B 	imes C_{	ext{emb}}}`，``ResBlock`` 的前向物理计算流如下：

.. math::

   h_1 = 	ext{Conv2d}_{3 	imes 3}\left(	ext{SiLU}\left(	ext{GroupNorm}_{32}(x)\right)\right)

   \mathbf{e}_{	ext{proj}} = 	ext{Linear}\left(	ext{SiLU}(\mathbf{e}_{	ext{emb}})\right)

根据配置的不同，时间步特征向空间特征注入有两种物理机制：

1. **加法注入（Additive Injection，标准 SD 1.5/SDXL）**：
   将 :math:`\mathbf{e}_{	ext{proj}}` 沿空间维度广播：

   .. math::

      h_2 = h_1 + \mathbf{e}_{	ext{proj}}[B, C_{	ext{out}}, 1, 1]

2. **尺度-偏移自适应归一化（Scale-Shift Norm / FiLM 机制）**：
   线性层输出维度为 :math:`2 C_{	ext{out}}`，拆分为尺度系数 :math:`\gamma` 与偏置系数 :math:`\beta`：

   .. math::

      h_{	ext{norm}} = 	ext{GroupNorm}_{32}(h_1)

      h_2 = h_{	ext{norm}} \odot (1 + \gamma) + \beta

最终输出通过残差跳跃路径连接：

.. math::

   	ext{Out}_{	ext{ResBlock}} = 	ext{SkipConnection}(x) + 	ext{Conv2d}_{3 	imes 3}\left(	ext{Dropout}\left(	ext{SiLU}\left(	ext{GroupNorm}_{32}(h_2)\right)\right)\right)

其中，当 :math:`C_{	ext{in}} 
eq C_{	ext{out}}` 或存在步长下采样时，:math:`	ext{SkipConnection}` 采用 :math:`1 	imes 1` 卷积进行通道维度对齐。

------------------------------------------------------------------------

3. 空间变换器（``SpatialTransformer``）与双重注意力机制
-------------------------------------------------------

``SpatialTransformer`` 是 UNet 具备理解复杂文本语义与建立长程空间相关性的核心组件。它将 2D 卷积特征图展平为 1D Token 序列，执行高密度的 Self-Attention 与 Cross-Attention 运算。

3.1 空间-序列维度重塑与跨模态注意力流
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                                 Feature Map: [B, C, H, W] (如 [1, 640, 32, 32])                    |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      | 1. 空间投影与展平 (in_proj: Conv2d 1x1 或 Linear)
                                      v
   +----------------------------------------------------------------------------------------------------+
   |                    Sequence Tokens: [B, N, C] (其中 N = H * W = 1024, C = 640)                     |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      v
   +----------------------------------------------------------------------------------------------------+
   |                                 BasicTransformerBlock (级联 Depth 次)                              |
   |                                                                                                    |
   |   [Sub-Block 1: 自注意力 Self-Attention (attn1)]                                                   |
   |      Q = LayerNorm(x) W_Q,  K = LayerNorm(x) W_K,  V = LayerNorm(x) W_V                            |
   |      x = x + Softmax(Q K^T / sqrt(d)) V                                                            |
   |                                                                                                    |
   |   [Sub-Block 2: 交叉注意力 Cross-Attention (attn2)]                                                 |
   |      Q = LayerNorm(x) W_Q                                                                          |
   |      K = TextContext W_K,  V = TextContext W_V  (Context: [B, 77, 2048])                            |
   |      x = x + Softmax(Q K^T / sqrt(d)) V                                                            |
   |                                                                                                    |
   |   [Sub-Block 3: 前馈神经网络 FeedForward (GEGLU / MLP)]                                            |
   |      x = x + Linear_out( GEGLU( LayerNorm(x) W_gate_up ) )                                         |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      | 2. 反向重塑 (out_proj -> Rearrange)
                                      v
   +----------------------------------------------------------------------------------------------------+
   |                                Output Feature Map: [B, C, H, W]                                    |
   +----------------------------------------------------------------------------------------------------+

3.2 注意力内存优化（Memory Efficient Attention & FlashAttention）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在自注意力计算中，直接生成完整的注意力矩阵 :math:`A \in \mathbb{R}^{B 	imes N 	imes N}`（当 :math:`H=W=64` 时，:math:`N=4096`，:math:`A` 的尺寸为 :math:`4096 	imes 4096 	imes 4 	ext{ Bytes} = 64	ext{MB}` 单头单层显存）会在大分辨率下导致显存开销呈 :math:`\mathcal{O}(N^2)` 爆炸。

ComfyUI 在 ``comfy/ldm/modules/attention.py`` 中集成了多后端算子自适应分发：

.. list-table:: ComfyUI SpatialTransformer 注意力后端算子对比
   :widths: 22 28 50
   :header-rows: 1

   * - 算子实现
     - 显存复杂度
     - 物理加速原理
   * - **PyTorch 2.0 SDPA**
     - :math:`\mathcal{O}(N)`
     - 硬件级融合内核（FlashAttention-2 / Memory-Efficient），切片分块计算无需实例化完整注意力矩阵。
   * - **xFormers Cutlass**
     - :math:`\mathcal{O}(N)`
     - 基于 CUDA 共享内存（Shared Memory）的流水线化分块 Softmax 在线归一化。
   * - **Sub-Quadratic Chunked**
     - :math:`\mathcal{O}(\sqrt{N})`
     - 面向极端低显存环境，沿 Query/Key 维度强制切片（Chunking）分批次串行计算。

------------------------------------------------------------------------

4. SDXL Micro-Conditioning 与尺寸嵌入物理注入
---------------------------------------------

SDXL 引入了突破性的“微条件控制（Micro-Conditioning）”，彻底解决了 SD 1.5 训练中因随机裁剪（Random Cropping）导致的人体头部截断和低分辨率模糊问题。

4.1 6 维几何坐标嵌入编码
~~~~~~~~~~~~~~~~~~~~~~~~

SDXL 将图像的几何元数据打包为 6 维标量向量：

.. math::

   \mathbf{c}_{	ext{size}} = (	ext{orig\_width}, 	ext{orig\_height}, 	ext{crop\_top}, 	ext{crop\_left}, 	ext{target\_width}, 	ext{target\_height})

在 ComfyUI 的 ``SDXL.process_adm_conditions()`` 中，每个标量坐标均通过正弦傅里叶嵌入投影为 256 维向量，6 个坐标拼接为 :math:`6 	imes 256 = 1536` 维向量。

4.2 向量拼接与 ADM 线性投影
~~~~~~~~~~~~~~~~~~~~~~~~~~~

1536 维几何嵌入与 OpenCLIP-G 的池化文本表征（Pooled Text Embedding, 1280 维）拼接，形成 **2816 维度的条件总向量（ADM Tensor）**：

.. math::

   \mathbf{y}_{	ext{adm}} = \left[ \mathbf{y}_{	ext{pooled}}^{[1280]} \,\|\, \mathbf{e}_{	ext{orig\_w}}^{[256]} \,\|\, \mathbf{e}_{	ext{orig\_h}}^{[256]} \,\|\, \mathbf{e}_{	ext{crop\_y}}^{[256]} \,\|\, \mathbf{e}_{	ext{crop\_x}}^{[256]} \,\|\, \mathbf{e}_{	ext{target\_w}}^{[256]} \,\|\, \mathbf{e}_{	ext{target\_h}}^{[256]} \right] \in \mathbb{R}^{2816}

在 UNet 中，``self.label_emb`` 接收 :math:`\mathbf{y}_{	ext{adm}}` 并通过非线性 MLP 投影至 :math:`	ext{time\_embed\_dim} = 1280`，直接与时间步嵌入 :math:`\mathbf{e}_t` 执行逐元素相加：

.. math::

   \mathbf{e}_{	ext{final}} = \mathbf{e}_t + 	ext{Linear}_2\left(	ext{SiLU}\left(	ext{Linear}_1\left(\mathbf{y}_{	ext{adm}}\right)\right)\right)

这使得整个网络的所有 ``ResBlock`` 均能在前向传播的最底层无缝感知全局裁剪位置与画布目标尺度。

------------------------------------------------------------------------

5. 残差跳跃连接（Skip-Connections）的显存生命周期与峰值分析
-----------------------------------------------------------

UNet 的核心特征在于通过 ``hs`` 栈将编码器的浅层特征直连至解码器。这一机制在保障生成细节的同时，构成了推理显存峰值（Peak VRAM）的最大压力源。

5.1 ``hs`` 激活值驻留生命周期
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   时间轴 T (前向传播步进) ─────────────────────────────────────────────────────────────────────────>

   [input_blocks 阶段]
   Layer 0 产生 h_0 [64x64, 320] ──> hs.append(h_0) ───────────────────────────────────────┐
   Layer 1 产生 h_1 [64x64, 320] ──> hs.append(h_1) ─────────────────────────────┐         │
   Layer 3 产生 h_3 [32x32, 640] ──> hs.append(h_3) ───────────────────┐         │         │
   ...                                                                 │         │         │
   Layer 11 产生 h_11 [8x8, 1280] ─> hs.append(h_11) ────────┐         │         │         │
                                                             │         │         │         │
   [middle_block 阶段]                                       │         │         │         │
   计算瓶颈特征 (此时 hs 栈达到全满，占用显存最大化)           │         │         │         │
                                                             │         │         │         │
   [output_blocks 阶段]                                      │         │         │         │
   Layer 0: Pop h_11 ──> Cat([h, h_11]) ──> 计算 ──> 释放 h_11 ┘         │         │         │
   Layer 3: Pop h_3  ──> Cat([h, h_3])  ──> 计算 ──> 释放 h_3 ───────────┘         │         │
   Layer 8: Pop h_1  ──> Cat([h, h_1])  ──> 计算 ──> 释放 h_1 ─────────────────────┘         │
   Layer 11: Pop h_0 ──> Cat([h, h_0]) ──> 计算 ──> 释放 h_0 (显存完全释放) ────────────────┘

5.2 显存峰值临界区与优化策略
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

显存压力在进入 ``output_blocks.0`` 时达到理论极值：

.. math::

   	ext{VRAM}_{	ext{peak}} = 	ext{VRAM}_{	ext{weights}} + \sum_{i=0}^{11} 	ext{Size}(h_i) + 	ext{Size}(h_{	ext{middle}}) + 	ext{Size}(	ext{Cat}(h_{	ext{middle}}, h_{11})) + 	ext{Size}(	ext{Attn}_{	ext{workspace}})

ComfyUI 通过以下机制进行峰值平抑：

1. **瞬时释放（Immediate De-allocation）**：在 ``output_blocks`` 中执行 ``hsp = hs.pop()`` 并完成 ``th.cat([h, hsp], dim=1)`` 后，显式执行 ``del hsp``，使 PyTorch Caching Allocator 能够立即复用该显存块；
2. **ControlNet 残差原位累加**：在 ``apply_control(hsp, control, 'output')`` 时直接在现有张量上执行原位相加，避免为控制特征开辟冗余副本。

------------------------------------------------------------------------

小结与下章导读
==============

本节系统拆解了 Latent Diffusion UNet 的内部物理实现：

1. **多尺度金字塔拓扑**：剖析了 ``input_blocks``、``middle_block`` 与 ``output_blocks`` 的多分辨率张量级联与通道演进；
2. **ResBlock 调制机制**：推导了标准加法注入与 FiLM 尺度-偏移调制数学方程；
3. **SpatialTransformer 计算流**：解析了空间展平、自注意力、跨注意力与 SDPA/xFormers 硬件加速原理；
4. **SDXL 微条件注入**：推导了 6 维几何坐标与 Pooled Text Embedding 构成的 2816 维 ADM 向量物理注入流；
5. **跳跃连接显存生命周期**：分析了 ``hs`` 特征栈的驻留周期与 ``output_blocks`` 显存峰值控制机制。

在下一节（``03_dit_architecture_and_mmdit.rst``）中，我们将跨入现代生成式 AI 的最前沿——**DiT 与 MMDiT 架构深度剖析**：全面解密 SD3 MMDiT 双流块、Flux.1 单双流混合架构、旋转位置编码（RoPE）以及调制自注意力（Modulated Self-Attention）的底层物理实现。
