========================================================================
ControlNet 残差分支挂载、T2I-Adapter 浅层特征注入与跨架构模型级引导抽象
========================================================================

.. note:: 前置背景与上下文承接
   在前三节中，我们建立了 ``BaseModel`` 骨干模型抽象族谱（``01_base_model_and_unet_dit_taxonomy.rst``）、深入拆解了 Latent Diffusion UNet 的多尺度金字塔与跳跃连接（``02_latent_diffusion_unet_internals.rst``），并剖析了现代 DiT/MMDiT 的双流/单流 Transformer 拓扑与 RoPE 旋转位置编码（``03_dit_architecture_and_mmdit.rst``）。然而，纯文本提示词（Text Prompt）在空间构图、姿态约束与边缘结构控制上存在固有的语义歧义。为了实现像素级精确可控生成，**ControlNet**、**T2I-Adapter** 与 **ControlLoRA** 等外部条件引导网络应运而生。ComfyUI 在 ``comfy/controlnet.py`` 中构建了一套高度抽象的 **跨架构模型级引导体系（Unified Model-Level Guidance）**，不仅统一了 UNet 时代的零卷积（Zero Convolution）残差挂载，更无缝扩展至 DiT 时代（SD3、Flux.1、HunyuanDiT）的单双流特征注入。本节系统解密这一跨代引导架构的物理实现。

------------------------------------------------------------------------

1. ControlNet 核心原理：锁定副本、可训练克隆与零卷积（Zero Convolution）
------------------------------------------------------------------------

标准 ControlNet 的核心设计哲学是：**完全冻结原始基础模型权重（Locked Copy），克隆一套相同的编码器网络（Trainable Copy），并通过零初始化的卷积层实现无损渐进式引导注入**。

1.1 零卷积数学推导与初始状态恒等性
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

零卷积（Zero Convolution）是指权重矩阵 :math:`W` 与偏置向量 :math:`b` 在训练初始时刻严格初始化为零的 :math:`1 	imes 1` 卷积层：

.. math::

   \mathcal{Z}(x; W, b) = W \cdot x + b, \quad 	ext{其中 } W \leftarrow \mathbf{0}, \; b \leftarrow \mathbf{0}

在训练第一步，对于任意输入特征 :math:`x`，零卷积输出恒为零：

.. math::

   \mathcal{Z}(x; \mathbf{0}, \mathbf{0}) \equiv \mathbf{0}

设原始基础网络某层的前向映射为 :math:`\mathcal{F}(x; \Theta)`，ControlNet 克隆分支映射为 :math:`\mathcal{F}(x + \mathcal{Z}_{	ext{in}}(c); \Theta_{	ext{clone}})`，则注入后的总输出为：

.. math::

   y = \mathcal{F}(x; \Theta) + \mathcal{Z}_{	ext{out}}\left(\mathcal{F}\left(x + \mathcal{Z}_{	ext{in}}(c); \Theta_{	ext{clone}}\right)\right)

由于初始状态下 :math:`\mathcal{Z}_{	ext{out}}(\cdot) = \mathbf{0}`，整个复合网络的输出严格恒等于未受污染的原始模型输出 :math:`y \equiv \mathcal{F}(x; \Theta)`。这保证了模型在微调初期绝不会破坏预训练大模型的生成先验（Prior Preservation）。

1.2 零卷积梯度传播推导
~~~~~~~~~~~~~~~~~~~~~~

当误差损失 :math:`\mathcal{L}` 反向传播时，零卷积权重的梯度为：

.. math::

   \frac{\partial \mathcal{L}}{\partial W} = \left(\frac{\partial \mathcal{L}}{\partial y} \cdot \frac{\partial y}{\partial \mathcal{Z}_{	ext{out}}}\right) x_{	ext{clone}}^T = \frac{\partial \mathcal{L}}{\partial y} \cdot x_{	ext{clone}}^T 
eq \mathbf{0}

这意味着虽然初始输出为零，但权重矩阵能够在反向传播的第一拍立即获得非零梯度更新，随着训练步数推进，:math:`W` 逐渐偏离零矩阵，以极其平滑的方式将结构引导特征融入骨干网络。

------------------------------------------------------------------------

2. ComfyUI 统一引导抽象架构（``ControlBase`` 与多重链接栈）
------------------------------------------------------------

在 ComfyUI 的物理架构中，所有空间引导器均继承自基类 ``ControlBase``（定义于 ``comfy/controlnet.py``），并通过**单向链表（Chained Linked List）**实现任意多 ControlNet 的级联组合。

其对象依赖与数据流拓扑如下图所示：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                                      ControlNet 节点调用链路 (Chained List)                         |
   |                                                                                                    |
   |   [ControlNet_A: Canny] ──(previous_controlnet)──> [ControlNet_B: OpenPose] ──> None               |
   |   - strength: 0.8, range: (0.0, 0.6)              - strength: 1.0, range: (0.0, 1.0)               |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      | get_control(x_noisy, t, cond, batched_number)
                                      v
   +----------------------------------------------------------------------------------------------------+
   |                                    递归前向计算与特征残差合并                                       |
   |                                                                                                    |
   |   1. 递归拉取前驱结果: control_prev = self.previous_controlnet.get_control(...)                   |
   |   2. 时间步区间过滤: 判定 t in (percent_to_timestep(start), percent_to_timestep(end))             |
   |   3. 视觉条件空间对齐: cond_hint 缩放、补边并搬移至目标设备 (x_noisy.device, dtype)                 |
   |   4. 执行控制网络前向: control_curr = self.control_model(x_noisy, hint=cond_hint, ...)            |
   |   5. 多分支残差融合 (control_merge):                                                               |
   |        out['input'][i]  = control_curr['input'][i] * strength + control_prev['input'][i]           |
   |        out['middle'][0] = control_curr['middle'][0] * strength + control_prev['middle'][0]         |
   |        out['output'][i] = control_curr['output'][i] * strength + control_prev['output'][i]         |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      | 注入扩散模型骨干
                                      v
   +----------------------------------------------------------------------------------------------------+
   |                     DiffusionModel (UNet / DiT) 在各层执行 apply_control() 原位累加                 |
   +----------------------------------------------------------------------------------------------------+

2.1 引导控制类层次体系规范
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: ComfyUI 引导体系核心类职责与实现方式
   :widths: 22 28 50
   :header-rows: 1

   * - 核心类名称
     - 物理模型承载
     - 调度机制与显存特性
   * - ``ControlBase``
     - 抽象基类
     - 定义链表结构、时间步百分比过滤（``timestep_percent_range``）与多控制残差合并算法（``control_merge``）。
   * - ``ControlNet``
     - 完整克隆网络模型
     - 包装 ``cldm.ControlNet``，在每次采样迭代步中与骨干网络同步执行前向推理，输出多层残差字典。
   * - ``T2IAdapter``
     - 轻量级浅层卷积网络
     - 仅包含 4 级下采样 ResBlock，单次采样全流程**仅执行 1 次特征提取**，计算结果跨步缓存复用。
   * - ``ControlLora``
     - 共享骨干 + LoRA 矩阵
     - 动态共享基础扩散模型的主干权重，仅将控制特征与零卷积作为低秩矩阵加载，显存占用降低 70%。

------------------------------------------------------------------------

3. 引导特征注入机制：UNet 与 DiT 的跨代架构适配
------------------------------------------------

由于 UNet 与 DiT 的物理骨干拓扑存在根本性差异，ComfyUI 针对两代架构设计了不同的残差拦截点与注入协议。

3.1 UNet 骨干残差注入协议
~~~~~~~~~~~~~~~~~~~~~~~~~

在 UNet（``comfy/ldm/modules/diffusionmodules/openaimodel.py``）中，ControlNet 残差被注入到下采样块、中间瓶颈与上采样跳跃连接中：

.. code-block:: python

    def apply_control(h, control, name):
        if control is not None and name in control and len(control[name]) > 0:
            ctrl = control[name].pop()
            if ctrl is not None:
                # 原位累加，直接修改张量，杜绝冗余内存拷贝
                h += ctrl
        return h

- **输入下采样期**：在每个 ``input_block`` 计算完成后调用 ``apply_control(h, control, 'input')``；
- **中间瓶颈期**：在 ``middle_block`` 计算完成后调用 ``apply_control(h, control, 'middle')``；
- **输出上采样期**：在从跳跃连接栈弹出特征后，先对其施加 ``apply_control(hsp, control, 'output')``，再执行通道拼接 ``th.cat([h, hsp], dim=1)``。

3.2 DiT 骨干残差注入协议（Flux.1 / SD3 / HunyuanDiT）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在纯 Transformer 架构中，不存在特征金字塔与显式跳跃连接。ComfyUI 在 ``comfy/ldm/flux/model.py`` 中开辟了双通道注入流：

.. code-block:: python

    # 1. 双流阶段 (DoubleStreamBlocks) 注入
    if control is not None:
        control_i = control.get("input")
        if i < len(control_i):
            add = control_i[i]
            if add is not None:
                # 仅将控制残差注入图像 Token 切片，保持文本 Token 纯净
                img[:, :add.shape[1]] += add

    # 2. 单流阶段 (SingleStreamBlocks) 注入
    if control is not None:
        control_o = control.get("output")
        if i < len(control_o):
            add = control_o[i]
            if add is not None:
                # 跨越文本序列偏移量，精准注入图像 Token 区域
                img[:, txt.shape[1] : txt.shape[1] + add.shape[1], ...] += add

这种设计保证了 ControlNet 仅对视觉空间 Token 施加强制几何约束，而不会破坏文本表征在深层多模态注意力中的跨模态对齐。

------------------------------------------------------------------------

4. T2I-Adapter 浅层特征注入与跨尺度融合
---------------------------------------

与 ControlNet 复制庞大的主干网络不同，T2I-Adapter（Text-to-Image Adapter）采用极简的卷积特征金字塔结构。

4.1 一次性提取与静态缓存（One-Time Extraction & Caching）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

T2I-Adapter 假设视觉结构先验（如骨骼姿态、边缘轮廓）是静态的，不随扩散时间步 :math:`t` 的噪声分布变化而变化。

在 ``comfy/controlnet.py`` 的 ``T2IAdapter.get_control()`` 中：

.. code-block:: python

    if self.control_input is None:
        self.t2i_model.to(x_noisy.dtype).to(self.device)
        # 全采样 20~50 步仅在此执行 1 次前向推理
        self.control_input = self.t2i_model(self.cond_hint.to(x_noisy.dtype))
        # 执行完毕后立即将模型卸载回 CPU 释放显存
        self.t2i_model.cpu()

4.2 多尺度残差加权融合
~~~~~~~~~~~~~~~~~~~~~~

T2I-Adapter 产出 4 个尺度的特征张量 :math:`F_1, F_2, F_3, F_4`，分别直接累加到 UNet 下采样的第 0、1、2、3 级块中：

.. math::

   x_{	ext{down}, k} \leftarrow x_{	ext{down}, k} + \alpha_{	ext{adapter}} \cdot F_k

这种设计使 T2I-Adapter 的推理计算开销几乎可忽略不计（不到 ControlNet 的 1/10），成为低算力端侧部署的理想选择。

------------------------------------------------------------------------

5. 第 4 模块技术全景综合对照表
------------------------------

作为第 4 模块《扩散模型基类与 DiT 架构抽象》的完结总结，下表梳理了多代骨干模型与引导机制的架构对应矩阵：

.. list-table:: ComfyUI 骨干模型与控制引导体系技术全景
   :widths: 18 27 27 28
   :header-rows: 1

   * - 架构维度
     - Gen 1/2 UNet (SD 1.5 / SDXL)
     - Gen 4 双流 DiT (SD3 / Flux.1)
     - 控制引导适配层 (ControlNet / T2I)
   * - **骨干拓扑**
     - 卷积残差 + 空间注意力金字塔
     - 双流/单流交织 Transformer 块
     - 克隆编码器 + 零卷积 / 极简特征金字塔
   * - **空间几何建模**
     - 步长卷积 + 最近邻上下采样
     - Patchify 序列化 + 2D/3D RoPE
     - Input Hint 卷积对齐 + 空间自适应插值
   * - **条件融合路径**
     - 跨注意力层 (Cross-Attn) + ADM
     - Joint Attention + AdaLN 全局调制
     - 逐层残差相加（``apply_control`` 原位注入）
   * - **时序调度机制**
     - 离散时间步 EPS / V-Prediction
     - 连续流匹配 (Rectified Flow ODE)
     - 步数百分比动态过滤（``timestep_percent_range``）

------------------------------------------------------------------------

小结与下章导读
==============

本节系统剖析了 ComfyUI 跨架构模型级引导体系的物理实现：

1. **零卷积数学本质**：推导了零初始化下的输出恒等性与非零梯度反向传播原理；
2. **统一引导抽象**：拆解了基于单向链表的 ``ControlBase`` 多重控制网络合并流；
3. **跨代架构注入协议**：对比了 UNet 三阶段残差挂载与 DiT 图像 Token 切片注入的差异；
4. **轻量化 T2I-Adapter**：解析了静态单次特征提取与金字塔残差融合的高效实现。

至此，**第 4 模块《扩散模型基类与 DiT 架构抽象》全 4 节已圆满结稿**。

在接下来的 **第 5 模块《采样器数值解法与调度方程》（05_samplers_and_scheduling）** 中，我们将深入生成式 AI 的数学核心——微分方程数值积分器（KSampler / k-diffusion）、连续与离散噪声时间表（Sigmas 方程）、无分类器引导（CFG）的几何流形修正，以及经典 ODE/SDE 求解器（Euler, Heun, DPM-Solver++, UniPC）的离散化实现。
