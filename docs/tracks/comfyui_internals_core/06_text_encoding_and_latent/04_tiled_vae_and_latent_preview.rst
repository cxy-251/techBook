========================================================================
大图切块 VAE 编解码（Tiled VAE）边缘重叠羽化融合算法与 Latent 实时流式预览
========================================================================

.. note:: 前置背景与上下文承接
   在前一节（``03_vae_architecture_and_tiling.rst``）中，我们系统剖析了 VAE 的连续卷积金字塔拓扑、潜空间多通道数值重归一化（``scaling_factor``/``shift_factor``）以及基于主成分分析的毫秒级伪彩预览。然而，在超高分辨率生成（如 2K/4K/8K 图像或长视频生成）的落地实践中，VAE 解码器面临着严重的物理显存瓶颈——由于解码器上采样至全分辨率时特征图通道宽、空间尺寸大，全图单次解码的瞬时激活值显存峰值可轻松突破数十吉字节，导致低显存设备直接触发 CUDA OOM 崩溃。此外，在去噪迭代的全过程中，用户需要低延迟、高保真地观测生成过程的演进。ComfyUI 在 ``comfy/sd.py`` 与 ``comfy/taesd/`` 中构建了基于**多维滑动窗口切块（Multidimensional Sliding Window Tiling）**、**余弦/线性边缘羽化重叠融合（Feathering Blending）**与**超轻量级自编码器（TAESD）流式预览**的工业级解决方案。本节系统拆解其算法推导与工程实现。

------------------------------------------------------------------------

1. Tiled VAE 物理切块机制与显存复杂度降阶
-----------------------------------------

设输入潜张量为 :math:`\mathbf{z} \in \mathbb{R}^{B 	imes C_{	ext{latent}} 	imes H_l 	imes W_l}`，其对应的目标重构像素尺寸为 :math:`H_p = H_l 	imes 8, W_p = W_l 	imes 8`。

1.1 全图解码与切块解码显存占用建模
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在全图单次解码模式下，VAE 解码器最后一级特征图（:math:`[B, 128, H_p, W_p]`）的前向激活值显存消耗为：

.. math::

   	ext{Mem}_{	ext{full}} = B 	imes C_{	ext{dec}} 	imes (H_l 	imes 8) 	imes (W_l 	imes 8) 	imes 	ext{dtype\_size} 	imes \kappa_{	ext{overhead}}

当生成一张 $4096 	imes 4096$ 的超高清图像时，单次前向激活值开销将超过 **16 GB**。

Tiled VAE 将大图分解为具有固定最大尺寸 :math:`T_l 	imes T_l`（如 :math:`64 	imes 64` 潜空间块，对应 :math:`512 	imes 512` 像素）的子块网格，使单步解码的显存复杂度与整图分辨率彻底解耦，恒定维持在常数级：

.. math::

   	ext{Mem}_{	ext{tiled}} = \mathcal{O}(T_l^2) \ll \mathcal{O}(H_l 	imes W_l)

1.2 滑动窗口坐标划分与重叠步进算法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了消除切块拼接处的接缝断裂，相邻子块之间必须保持宽度为 :math:`\delta_l` 的重叠边界（Overlap Region，默认对应像素级重叠 64 像素，即 :math:`\delta_l = 8`）。

其空间划分步进定义如下：

.. math::

   	ext{Step}_h = T_l - \delta_l, \quad 	ext{Step}_w = T_l - \delta_l

   N_h = \left\lceil \frac{H_l - \delta_l}{	ext{Step}_h} \right\rceil, \quad N_w = \left\lceil \frac{W_l - \delta_l}{	ext{Step}_w} \right\rceil

其空间几何切片拓扑如下图所示：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                                 Tiled VAE 空间网格滑动窗口划分与重叠区                                |
   +----------------------------------------------------------------------------------------------------+
   
      0                     W_tile                                       W_latent
      +───────────────────────+─────────────────────────────────────────────+
      |       Tile (0, 0)     |                                             |
      |   +---------------+───┼───────────+                                 |
      |   |  有效中心区    |   |           |                                 |
      |   | (Core Region) | 重|           |                                 |
      |   |               | 叠|           |                                 |
      |   +---------------+───+           |                                 |
      |   |    重叠区     | 叠| Tile (0,1)|                                 |
   H_t+───+───────────────+───+───────────+                                 |
      |   |                   |                                             |
      |   |    Tile (1, 0)    |       Tile (1, 1)                           |
      |   +───────────────────+─────────────────────────────────────────────+
      |                                                                     |
   H_l+─────────────────────────────────────────────────────────────────────+

------------------------------------------------------------------------

2. 边缘重叠羽化融合算法（Feathering Blending Mathematics）
----------------------------------------------------------

若直接将各切块解码后的像素块简单拼接，由于卷积算子在边界处的感受野截断（Boundary Receptive Field Truncation）与 GroupNorm 局部统计量差异，边缘拼接处会出现极其刺眼的“网格接缝伪影（Grid Artifacts）”。

ComfyUI 在 ``comfy/sd.py`` 的 ``tiled_scale_multidim()`` 中实现了**多维边缘羽化加权累加与能量归一化算法**。

2.1 一维渐变权重核函数推导
~~~~~~~~~~~~~~~~~~~~~~~~~~

对于当前切块在指定轴向上的局部坐标 :math:`u \in [0, L_{	ext{tile}}]`，其边缘权重函数 :math:`w(u)` 定义为梯形连续函数：

.. math::

   w_{	ext{left}}(u) = \begin{cases}
   \frac{u}{\delta}, & 0 \le u < \delta \
   1.0, & \delta \le u \le L_{	ext{tile}}
   \end{cases}, \quad
   w_{	ext{right}}(u) = \begin{cases}
   1.0, & 0 \le u \le L_{	ext{tile}} - \delta \
   \frac{L_{	ext{tile}} - u}{\delta}, & L_{	ext{tile}} - \delta < u \le L_{	ext{tile}}
   \end{cases}

对于非图像物理边缘的内部切块，综合一维权重核为左右边缘的交集：

.. math::

   W_{	ext{1D}}(u) = \min\left( w_{	ext{left}}(u), \, w_{	ext{right}}(u) \right)

2.2 二维/三维张量积权重矩阵与加权累加
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

通过外积将各维度的一维核函数广播为 2D 空间掩码矩阵（或 3D 时空权重体素）：

.. math::

   \mathbf{M}_{	ext{tile}}(y, x) = W_{	ext{1D}}^H(y) \otimes W_{	ext{1D}}^W(x) \in \mathbb{R}^{H_p^{	ext{tile}} 	imes W_p^{	ext{tile}}}

在整图重构画布上，系统维护两个全局累加缓冲区：

1. **加权像素累加器** :math:`\mathbf{P}_{	ext{accum}} \in \mathbb{R}^{B 	imes C 	imes H_p 	imes W_p}`；
2. **权重累加器** :math:`\mathbf{W}_{	ext{accum}} \in \mathbb{R}^{1 	imes 1 	imes H_p 	imes W_p}`。

对于第 :math:`k` 个解码子块 :math:`\mathbf{I}_k`，执行原位加权累加：

.. math::

   \mathbf{P}_{	ext{accum}}[	ext{slice}_k] \mathrel{+}= \mathbf{I}_k \odot \mathbf{M}_{	ext{tile}}^{(k)}

   \mathbf{W}_{	ext{accum}}[	ext{slice}_k] \mathrel{+}= \mathbf{M}_{	ext{tile}}^{(k)}

遍历所有切块后，执行逐元素精准归一化除法：

.. math::

   \mathbf{I}_{	ext{final}} = \frac{\mathbf{P}_{	ext{accum}}}{\mathbf{W}_{	ext{accum}} + \epsilon}

由于相邻两个子块在重叠区域的权重函数满足线性互补性：

.. math::

   W_A(x) + W_B(x) = \left(1 - \frac{x}{\delta}\right) + \frac{x}{\delta} \equiv 1.0

因此在重叠交界处，图像信号实现**完美的平滑过渡与能量守恒，彻底消除了任何可见接缝**。

------------------------------------------------------------------------

3. 3D 时空视频切块扩展（Spatio-Temporal Tiled VAE）
---------------------------------------------------

在视频生成模型（如 Wan 2.1、CogVideoX、Cosmos、LTXV）中，潜变量维度扩展为 5 维张量 :math:`[B, C, T_l, H_l, W_l]`。若仅在空间维度切块，时间帧数较长时依然会引发显存爆炸。

ComfyUI 将切块引擎推广至多维空间抽象（``tiled_scale_multidim``）：

.. list-table:: 2D 图像与 3D 视频 Tiled VAE 切块参数规范对照
   :widths: 20 40 40
   :header-rows: 1

   * - 切块维度参数
     - 2D 图像 VAE (SDXL / Flux)
     - 3D 时空视频 VAE (Wan 2.1 / CogVideoX)
   * - **时间轴切块 (Tile Frames)**
     - 无 (单帧)
     - ``tile_t = 8`` ~ ``16`` 潜帧 (对应 32~64 视频帧)
   * - **时间重叠量 (Overlap Frames)**
     - 无
     - ``overlap_t = 2`` 潜帧 (对应 8 视频帧重叠)
   * - **空间轴切块 (Tile Size)**
     - ``tile_x = tile_y = 64`` 潜像素 (对应 512x512)
     - ``tile_x = tile_y = 32`` ~ ``64`` 潜像素
   * - **时空因果填充保护**
     - 标准 Reflect / Zero Padding
     - 严格遵循时间轴因果卷积约束，首帧执行独立非重叠解码

------------------------------------------------------------------------

4. TAESD 超轻量神经自编码器与实时流式预览
-----------------------------------------

在采样主循环中，尽管主成分投影（PCA）能够提供毫秒级的伪彩预览，但其色彩还原度低、高频纹理模糊。为了在不显著增加采样耗时的前提下提供照片级的实时去噪预览，ComfyUI 内置集成了 **TAESD（Tiny AutoEncoder for Stable Diffusion）** 体系。

4.1 TAESD 极简卷积网络拓扑
~~~~~~~~~~~~~~~~~~~~~~~~~~

TAESD（由 Madebyollin 设计）是一个极度轻量化的卷积神经网络，其参数量仅为约 **2.5 MB**（不到官方 VAE 解码器的 1/60）。

其解码器拓扑舍弃了昂贵的 Self-Attention 算子与深度下采样结构，完全由微型残差卷积与最近邻插值构建：

.. code-block:: text

   Latent: [B, C_latent, H/8, W/8] (例如 SDXL C=4 或 Flux C=16)
       |
       v Conv2d(C_latent -> 64) -> ReLU
       v ResBlock(64 -> 64) x 2
       v Upsample(scale=2) -> Conv2d(64 -> 64) -> ReLU ──> [B, 64, H/4, W/4]
       v ResBlock(64 -> 64) x 2
       v Upsample(scale=2) -> Conv2d(64 -> 64) -> ReLU ──> [B, 64, H/2, W/2]
       v ResBlock(64 -> 64) x 2
       v Upsample(scale=2) -> Conv2d(64 -> 64) -> ReLU ──> [B, 64, H, W]
       v ResBlock(64 -> 64) x 2
       v Conv2d(64 -> 3) -> Clamp(0.0, 1.0)
       |
       v Output RGB Preview: [B, 3, H, W] (解码耗时仅 2~4 ms)

4.2 跨架构 TAESD 衍生变体支持
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

ComfyUI 在 ``comfy/taesd/`` 中维护了适配全系列前沿模型的微型编解码器权重矩阵：

.. list-table:: ComfyUI TAESD 实时预览引擎族谱
   :widths: 18 22 25 35
   :header-rows: 1

   * - 引擎变体
     - 适配基础模型
     - 潜通道与空间缩放
     - 物理特征与部署优势
   * - **``taesd``**
     - SD 1.5 / SD 2.1
     - 4 通道，:math:`8	imes` 空间下采样
     - 毫秒级极速草图预览，内存占用 < 10MB
   * - **``taesdxl``**
     - SDXL / SDXL-Turbo
     - 4 通道，:math:`8	imes` 空间下采样
     - 深度重对齐 SDXL 色彩空间，抑制偏色
   * - **``taesd3``**
     - SD 3 / SD 3.5
     - 16 通道，:math:`8	imes` 空间下采样
     - 完美支持 16 维多通道稠密特征解码
   * - **``taef1``**
     - Flux.1 (Schnell / Dev)
     - 16 通道，:math:`8	imes` 空间下采样
     - 专门针对 Flow Matching 潜空间结构训练
   * - **``taew1``**
     - Wan 2.1 视频生成模型
     - 16 通道，:math:`(4, 8, 8)` 时空下采样
     - 逐帧轻量时空解压，支撑视频流式首帧预览

4.3 WebSocket 二进制流式广播管道
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在采样器的每一步迭代中，``k_callback`` 捕获当前预测的纯净潜变量 :math:`\hat{x}_0`，并通过异步线程池驱动 TAESD 进行非阻塞解码与网络传输：

.. code-block:: text

   Sampler Step i ──> k_callback(denoised_x0)
                           |
                           v (异步工作线程)
                    TAESD Decoder (GPU/CPU 极速推理, 3ms)
                           |
                           v PIL Image 压缩为 JPEG/WebP (内存 Buffer)
                    server.send_sync(BinaryEvent: PREVIEW_IMAGE)
                           |
                           v (WebSocket 异步二进制通道)
                    前端 Web 客户端 Canvas 实时绘制渲染

这种设计将生成观测的计算开销完全从采样主线程中剥离，确保了实时交互的绝对流畅性。

------------------------------------------------------------------------

5. 第 6 模块技术全景综合对照表
------------------------------

作为第 6 模块《文本编码与潜空间重构》的完结篇，下表系统梳理了从文本分词、嵌入投影到 VAE 编解码与流式观测的完整物理演进矩阵：

.. list-table:: ComfyUI 文本编码与潜空间重构体系全景
   :widths: 18 27 27 28
   :header-rows: 1

   * - 核心系统层级
     - 物理承载对象 / 模块
     - 核心数学算法与数据结构
     - 系统架构贡献
   * - **文本分词与分块**
     - ``SDTokenizer`` / ``SD1Tokenizer``
     - BPE / SentencePiece、77-Token Chunking、权重加权树
     - 突破长文本截断限制，支持精细化词级别注意力加权语法。
   * - **多模态表征投影**
     - ``SDClipModel`` / ``sd.py``
     - CLIP-L (768) + OpenCLIP-G (1280) + T5-XXL (4096) 拼接
     - 实现多编码器表征对齐与 Pooled 向量全局上下文提取。
   * - **VAE 卷积流形**
     - ``AutoencoderKL`` / ``sd.py``
     - 连续下采样金字塔、确定性均值重参数化、数值缩放因子
     - 将像素高维空间压缩 64 倍至紧凑潜空间，杜绝计算维数灾难。
   * - **超大分辨率重构**
     - ``tiled_scale_multidim``
     - 多维滑动窗口切块、梯形外积羽化融合、权重能量归一化
     - 实现 4K/8K 极限分辨率解码，彻底消除 GPU CUDA OOM 风险。
   * - **实时交互观测**
     - ``TAESD`` / ``latent_preview.py``
     - 微型残差无注意力卷积网络、WebSocket 二进制流式广播
     - 提供 3ms 超低延迟高质量去噪进度可视化。

------------------------------------------------------------------------

小结与下章导读
==============

本节系统解密了大图切块 VAE 与实时流式预览的工程物理实现：

1. **切块显存解耦**：推导了基于固定最大切块尺寸的常数级显存复杂度模型；
2. **边缘羽化融合数学**：建立了基于梯形外积核函数与累加除法归一化的无缝拼接公式；
3. **多维时空扩展**：解析了视频 3D 因果时空切块的参数规范与时间重叠策略；
4. **TAESD 预览体系**：解剖了全系列超轻量神经网络拓扑与 WebSocket 二进制流式广播管线。

至此，**第 6 模块《文本编码与潜空间重构》全 4 节已圆满结稿**。全书 28 节累计完工 **24/28 节**。

在接下来的 **第 7 模块《自定义节点协议与 WebSocket 通信体系》（07_custom_nodes_and_comms）** 中，我们将迎来全书的最终压轴模块——全面剖析 ComfyUI 的生态核心基石：从经典 V1/V2 节点注册协议（`NODE_CLASS_MAPPINGS`/`INPUT_TYPES`）、现代面向对象 V3 API 与 Schema 强类型校验，到 aiohttp 异步 Web 服务端架构与 WebSocket 双向流式实时同步协议。
