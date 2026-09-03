========================================================================
DiT 与 MMDiT 架构深度剖析：双流/单流 Transformer 块、RoPE 旋转位置编码与自适应调制
========================================================================

.. note:: 前置背景与上下文承接
   在前一节（``02_latent_diffusion_unet_internals.rst``）中，我们系统剖析了基于卷积与空间注意力金字塔的 Latent Diffusion UNet 内部拓扑。然而，随着生成式模型参数规模从 10 亿（SDXL 2.6B）跃升至百亿级（SD3 8B、Flux.1 12B、HunyuanVideo 13B），传统的 UNet 架构因其固定的卷积归纳偏置（Inductive Bias）与多尺度跳跃连接显存瓶颈，逐渐让位于以 **Diffusion Transformer（DiT）** 与 **Multimodal Diffusion Transformer（MMDiT）** 为代表的纯序列建模范式。ComfyUI 在 ``comfy/ldm/flux/`` 与 ``comfy/ldm/modules/diffusionmodules/mmdit.py`` 中实现了极其优化的 DiT 执行内核。本节深入拆解 Patchify 潜空间序列化、双流/单流 Transformer 块交织拓扑、多维 RoPE 旋转位置编码数学推导以及 AdaLN-Single 全局自适应调制机制。

------------------------------------------------------------------------

1. 从 UNet 到 DiT：潜空间 Patchify 序列化与架构范式跃迁
------------------------------------------------------

传统 UNet 将潜变量视为 2D 空间特征图（:math:`[B, C, H, W]`），通过步长卷积与最近邻插值进行分辨率升降采样；而 DiT 彻底摒弃了卷积金字塔，将扩散生成统一为**标准序列到序列（Seq2Seq）自回归/流匹配变换**。

1.1 潜空间 Patchify 空间切块与线性投影
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于 VAE 编解码输出的潜张量 :math:`x \in \mathbb{R}^{B 	imes C_{	ext{in}} 	imes H 	imes W}`（以 Flux 为例，:math:`C_{	ext{in}} = 16`），系统首先以步长 :math:`p = 2`（Patch Size）进行无重叠空间平铺切块：

.. math::

   N = \left(\frac{H}{p}\right) 	imes \left(\frac{W}{p}\right), \quad D_{	ext{patch}} = C_{	ext{in}} \cdot p^2 = 16 	imes 4 = 64

通过 ``einops.rearrange`` 实现维度重塑与线性投影：

.. math::

   x_{	ext{seq}} = 	ext{Linear}_{	ext{img\_in}}\left(	ext{Rearrange}\left(x, 	ext{'b c (h ph) (w pw) -> b (h w) (c ph pw)'}\right)\right) \in \mathbb{R}^{B 	imes N 	imes D_{	ext{hidden}}}

1.2 多模态序列拼接拓扑（Flux.1 混合流架构）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Flux.1 的骨干计算图由 **19 个双流块（DoubleStreamBlock）** 与 **38 个单流块（SingleStreamBlock）** 级联构成：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |  Image Latent: [B, 16, H, W] -> Patchify(2x2) -> img_in -> [B, N_img, 3072]                       |
   |  Text Context: [B, L_txt, 4096] (T5-XXL) -> txt_in -> [B, L_txt, 3072]                            |
   |  Vector: Time_in(t) + Guidance_in(g) + Vector_in(y_clip) -> vec: [B, 3072]                        |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      v
   +----------------------------------------------------------------------------------------------------+
   |                          DoubleStreamBlock (双流解耦多模态计算阶段 - 19 层)                          |
   |                                                                                                    |
   |   [Image Stream] ──> Modulated LayerNorm ──> Q, K, V ──┐                                           |
   |                                                        ├──> Unified Joint Attention (含 RoPE)      |
   |   [Text Stream]  ──> Modulated LayerNorm ──> Q, K, V ──┘         |                                 |
   |                                                                  v                                 |
   |   [Image Output] <── Modulated MLP <── Linear Proj <── Img Attn Split                              |
   |   [Text Output]  <── Modulated MLP <── Linear Proj <── Txt Attn Split                              |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      | 序列拼接: x = torch.cat([txt, img], dim=1) -> [B, L_txt + N_img, 3072]
                                      v
   +----------------------------------------------------------------------------------------------------+
   |                          SingleStreamBlock (单流全融合计算阶段 - 38 层)                              |
   |                                                                                                    |
   |   x_norm = Modulated_PreNorm(x)                                                                    |
   |   [QKV, MLP_In] = Linear1(x_norm)  (单宽矩阵并行计算注意力与 MLP 投影)                               |
   |   Attn = Attention(Q, K, V, RoPE)                                                                  |
   |   MLP_Out = Act(MLP_In)                                                                            |
   |   x = x + Gate * Linear2(Concat(Attn, MLP_Out))                                                    |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      | 提取图像部分: out = x[:, L_txt:]
                                      v
   +----------------------------------------------------------------------------------------------------+
   |           FinalLayer: AdaLN_Modulation -> LayerNorm -> Linear -> Unpatchify => [B, 16, H, W]       |
   +----------------------------------------------------------------------------------------------------+

------------------------------------------------------------------------

2. 双流与单流 Transformer 块物理微观拓扑
----------------------------------------

2.1 双流多模态块（``DoubleStreamBlock``）计算流
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在双流阶段，图像与文本保留各自专有的表征流与 MLP 映射空间，但在自注意力层共享注意力权重矩阵（Joint Attention）。

其微观计算推导如下：

1. **模态调制（Modulation）**：
   时间步与引导向量通过 ``Modulation`` 模块分解为各模态的缩放（Scale :math:`\gamma`）、偏移（Shift :math:`\beta`）与门控（Gate :math:`\alpha`）：

   .. math::

      \hat{x}_{	ext{img}} = 	ext{LayerNorm}(x_{	ext{img}}) \odot (1 + \gamma_{	ext{img}, 1}) + \beta_{	ext{img}, 1}

      \hat{x}_{	ext{txt}} = 	ext{LayerNorm}(x_{	ext{txt}}) \odot (1 + \gamma_{	ext{txt}, 1}) + \beta_{	ext{txt}, 1}

2. **QK-Norm 归一化**：
   为彻底解决大模型在低精度（FP16/FP8）下的 Attention Logits 溢出与数值爆炸，Flux 在 Q、K 投影后强制执行 **RMSNorm 约束**：

   .. math::

      Q_{	ext{img}} = 	ext{RMSNorm}\left(\hat{x}_{	ext{img}} W_Q^{	ext{img}}\right), \quad K_{	ext{img}} = 	ext{RMSNorm}\left(\hat{x}_{	ext{img}} W_K^{	ext{img}}\right)

3. **跨模态联合注意力（Joint Self-Attention）**：
   将文本与图像的 Q、K、V 在 Token 维度拼接，执行单次大矩阵注意力计算：

   .. math::

      Q_{	ext{joint}} = [Q_{	ext{txt}} \,\|\, Q_{	ext{img}}], \quad K_{	ext{joint}} = [K_{	ext{txt}} \,\|\, K_{	ext{img}}], \quad V_{	ext{joint}} = [V_{	ext{txt}} \,\|\, V_{	ext{img}}]

      A_{	ext{joint}} = 	ext{Softmax}\left(\frac{	ext{RoPE}(Q_{	ext{joint}}) \cdot 	ext{RoPE}(K_{	ext{joint}})^T}{\sqrt{d_{	ext{head}}}}\right) V_{	ext{joint}}

4. **门控残差回填**：
   计算结果拆分回文本分支与图像分支，分别经过独立的 MLP 块并由各自的门控系数累加：

   .. math::

      x_{	ext{img}} \leftarrow x_{	ext{img}} + \alpha_{	ext{img}, 1} \odot 	ext{Linear}_{	ext{proj}}(A_{	ext{joint}}^{	ext{img}})

      x_{	ext{img}} \leftarrow x_{	ext{img}} + \alpha_{	ext{img}, 2} \odot 	ext{MLP}_{	ext{img}}\left(	ext{LayerNorm}(x_{	ext{img}}) \odot (1 + \gamma_{	ext{img}, 2}) + \beta_{	ext{img}, 2}\right)

2.2 单流全融合块（``SingleStreamBlock``）超宽算子并行
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

随着网络深度增加，文本与图像特征已高度对齐。进入单流阶段后，两个模态合并为单一序列，并通过 **并行宽线性层（Parallel Linear Layer）** 实现算力与显存带宽的最大化利用：

.. list-table:: SingleStreamBlock 与传统 Transformer Block 算子执行对比
   :widths: 22 38 40
   :header-rows: 1

   * - 计算环节
     - 传统串行 Transformer Block
     - SingleStreamBlock 并行宽算子
   * - **QKV 与 MLP 前向投影**
     - 串行执行 1 次 QKV 投影 + 1 次 MLP Up 投影
     - 单次 GEMM 矩阵乘法：``Linear(H, 3H + MLP_Dim)`` 同时产出 QKV 与 MLP 隐层
   * - **中间非线性激活**
     - 空间自注意力与 MLP 激活分步串行计算
     - Attention 算子与 GELU/SiLU 激活在 CUDA 流中并行发射
   * - **输出投影融合**
     - 分别执行 Attention Proj 与 MLP Down 投影
     - 拼接张量 ``[Attn, MLP_Out]``，单次 ``Linear(H + MLP_Dim, H)`` 投影还原
   * - **显存读写往返 (Memory Round-trip)**
     - 4 次 Global VRAM 读写往返
     - 仅 2 次 Global VRAM 读写，显存带宽利用率提升 40%

------------------------------------------------------------------------

3. 多维旋转位置编码（RoPE）数学推导与空间映射
----------------------------------------------

在 DiT 中，传统的 1D 正弦位置编码无法有效捕捉 2D 图像网格与 3D 视频帧之间的相对几何关系。ComfyUI 在 ``comfy/ldm/flux/math.py`` 中实现了多维解耦 **RoPE（Rotary Position Embedding）**。

3.1 2D/3D 空间坐标与解耦频率基
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于空间中任意坐标 :math:`\mathbf{p} = (t, y, x)`（分别对应时间帧索引、垂直行坐标、水平列坐标），每个维度分配独立的特征通道宽度（如 :math:`	ext{axes\_dim} = [16, 56, 56]`，总和等于单个 Attention Head 维度 :math:`d_{	ext{head}} = 128`）。

对于指定轴坐标 :math:`p \in \mathbb{R}` 和第 :math:`k` 组通道分量，频率基向量定义为：

.. math::

   \omega_k = \frac{1}{	heta^{2k / d_{	ext{axis}}}}, \quad 	heta = 10000

3.2 复数旋转矩阵与原位变换
~~~~~~~~~~~~~~~~~~~~~~~~~~

对于查询向量中的相邻分量对 :math:`(q_{2k}, q_{2k+1})`，RoPE 通过 $2 	imes 2$ 正交旋转矩阵施加位置偏置：

.. math::

   \begin{pmatrix} 	ilde{q}_{2k} \ 	ilde{q}_{2k+1} \end{pmatrix} = \begin{pmatrix} \cos(p \cdot \omega_k) & -\sin(p \cdot \omega_k) \ \sin(p \cdot \omega_k) & \cos(p \cdot \omega_k) \end{pmatrix} \begin{pmatrix} q_{2k} \ q_{2k+1} \end{pmatrix}

在注意力内积计算中，两个位置 :math:`p_m` 与 :math:`p_n` 的查询与键向量内积天然内嵌了相对距离 :math:`(p_m - p_n)` 的相对位置关系：

.. math::

   \langle 	ilde{q}(p_m), 	ilde{k}(p_n) \rangle = q^T R(p_m)^T R(p_n) k = q^T R(p_m - p_n) k

在代码实现中，ComfyUI 通过高效的复数张量点乘实现零显存分配的硬件级 RoPE 注入：

.. code-block:: python

    def _apply_rope1(x: Tensor, freqs_cis: Tensor):
        # x_ 形状为 [B, N, D/2, 2]
        x_ = x.reshape(*x.shape[:-1], -1, 1, 2)
        # 利用三角恒等式并行计算旋转: cos*x0 - sin*x1, sin*x0 + cos*x1
        x_out = freqs_cis[..., 0] * x_[..., 0]
        x_out.addcmul_(freqs_cis[..., 1], x_[..., 1])
        return x_out.reshape(*x.shape).type_as(x)

------------------------------------------------------------------------

4. 自适应层归一化（AdaLN-Single）与全局条件调制
------------------------------------------------

DiT 摒弃了 UNet 中每个 ResBlock 各自持有庞大 Linear 时间步投影层的做法，采用了轻量高效的 **AdaLN-Single 全局调制机制**。

4.1 统一条件向量汇聚
~~~~~~~~~~~~~~~~~~~~

所有全局控制信号（扩散时间步 :math:`t`、CFG 引导尺度 :math:`g`、CLIP 图像/文本池化向量 :math:`y`）首先在模型入口处汇聚为单一上下文向量 :math:`\mathbf{v}_{	ext{global}} \in \mathbb{R}^{D_{	ext{hidden}}}`：

.. math::

   \mathbf{v}_{	ext{global}} = 	ext{MLPEmbedder}_{	ext{time}}(t) + 	ext{MLPEmbedder}_{	ext{guidance}}(g) + 	ext{MLPEmbedder}_{	ext{vector}}(y)

4.2 块级轻量调制投影（Modulation Module）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在每个 Transformer 块内部，不再重复计算高维特征投影，仅通过单个微型线性层从 :math:`\mathbf{v}_{	ext{global}}` 中解析出当前块专用的 6 个标量缩放因子（DoubleStreamBlock 为 12 个）：

.. code-block:: python

    class Modulation(nn.Module):
        def __init__(self, dim: int, double: bool):
            super().__init__()
            self.multiplier = 6 if double else 3
            self.lin = operations.Linear(dim, self.multiplier * dim, bias=True)

        def forward(self, vec: Tensor):
            # 单次 SiLU 与线性投影输出 (shift, scale, gate)
            out = self.lin(nn.functional.silu(vec)).chunk(self.multiplier, dim=-1)
            return ModulationOut(*out[:3]), ModulationOut(*out[3:]) if self.is_double else None

这种设计使得百亿参数的 DiT 在切换不同条件时，参数量和计算开销比传统 UNet 下降了整整一个数量级。

------------------------------------------------------------------------

5. UNet 与 DiT 骨干网络物理资源与执行特征对照表
------------------------------------------------

.. list-table:: UNet (SDXL) 与 DiT (Flux.1) 运行时物理特征全面对比
   :widths: 20 40 40
   :header-rows: 1

   * - 性能与资源指标
     - SDXL UNet 骨干
     - Flux.1 DiT 骨干
   * - **参数量级**
     - 2.6 Billion
     - 12.0 Billion
   * - **计算复杂度增长曲线**
     - 空间卷积固定分辨率，注意力受限于特征金字塔
     - 全序列统一注意力，随序列长度 :math:`N` 呈纯二次方关系 :math:`\mathcal{O}(N^2)`
   * - **显存峰值主要瓶颈**
     - 编码器 ``hs`` 跳跃连接激活值堆栈
     - 长序列（1024x1024 对应 4096 图像 Token）的 Attention 矩阵显存
   * - **多模态融合机制**
     - 空间层与跨注意力层物理分离
     - 双流/单流联合注意力（Joint Attention），文本与图像全对称交互
   * - **位置敏感性**
     - 依赖绝对坐标与卷积感受野
     - 严格依赖 2D/3D RoPE 相对旋转位置偏置

------------------------------------------------------------------------

小结与下章导读
==============

本节系统剖析了以 SD3 与 Flux.1 为代表的现代 Diffusion Transformer 骨干实现：

1. **序列化范式跃迁**：推导了 Patchify 空间切块与线性特征投影的数学过程；
2. **双流与单流拓扑**：拆解了 DoubleStreamBlock 跨模态联合注意力和 SingleStreamBlock 宽算子并行的微观数据流；
3. **多维 RoPE 旋转位置编码**：推导了基于复数正交旋转的多轴几何坐标相对位置偏置方程；
4. **AdaLN-Single 全局调制**：阐明了基于统一上下文向量的超轻量条件缩放与门控机制。

在下一节（``04_controlnet_and_guiding_mechanisms.rst``）中，我们将迎来第 4 模块的完结篇——**ControlNet 与跨架构模型级引导抽象**：深入解密零卷积（Zero Convolution）残差分支挂载、T2I-Adapter 浅层特征注入，以及 ComfyUI 如何在统一框架下实现对 UNet 与 DiT 两代截然不同架构的模型级引导控制。
