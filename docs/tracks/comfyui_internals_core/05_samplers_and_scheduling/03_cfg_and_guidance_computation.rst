========================================================================
无分类器引导（CFG）数学计算、负向提示词对抗与潜空间方差校准
========================================================================

.. note:: 前置背景与上下文承接
   在前两节中，我们建立了 ``KSampler`` 的数值积分调度总控（``01_samplers_and_kdiffusion_wrapper.rst``）以及跨越不同曲率特性的连续/离散噪声时间表（``02_noise_schedules_and_sigmas.rst``）。然而，纯粹依靠无条件的扩散前向得分（Unconditional Score）只能生成随机分布的自然图像，无法精确贴合用户输入的复杂语义提示词。为了使生成过程严格受控于文本条件，**无分类器引导（Classifier-Free Guidance, CFG）**成为了现代生成式扩散模型的通用基石。然而，当引导系数（CFG Scale）较高时，线性外推会导致潜空间数值方差急剧发散，诱发严重的过饱和、色彩灼烧（Color Burning）与塑料感伪影。ComfyUI 在 ``comfy/samplers.py`` 的 ``cfg_function()`` 与挂载插件中构建了包含**向量外推、负向流形对抗、Rescale CFG、动态阈值截断（Dynamic Thresholding）与自注意力引导（SAG/PAG）**的几何校准闭环。本节系统推导其数学机理与工程实现。

------------------------------------------------------------------------

1. 无分类器引导（CFG）数学本质与几何外推
-----------------------------------------

在生成式扩散模型的对数概率密度梯度（Score Function）建模中，条件得分可通过贝叶斯法则分解为无条件得分与分类器梯度的线性组合：

.. math::

   
abla_{x_t} \log P(x_t | c) = 
abla_{x_t} \log P(x_t) + 
abla_{x_t} \log P(c | x_t)

传统分类器引导（Classifier Guidance）需要额外训练一个噪声鲁棒的图像分类器来提供梯度 :math:`
abla_{x_t} \log P(c | x_t)`。Ho 与 Salimans 提出的 **Classifier-Free Guidance（CFG）** 巧妙地通过在训练期以一定概率随机丢弃条件（将 :math:`c` 替换为空条件 :math:`\emptyset`），使单个网络同时学会预测条件得分 :math:`\epsilon_	heta(x_t, c)` 与无条件得分 :math:`\epsilon_	heta(x_t, \emptyset)`。

1.1 预测噪声空间与去噪潜变量空间的线性外推
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在推理阶段，引导向量通过沿从无条件向条件方向进行几何线性外推（Extrapolation）产生：

.. math::

   	ilde{\epsilon}_	heta(x_t, c, \emptyset; s) = \epsilon_	heta(x_t, \emptyset) + s \cdot \left( \epsilon_	heta(x_t, c) - \epsilon_	heta(x_t, \emptyset) \right)

其中 :math:`s \ge 1.0` 为引导缩放因子（CFG Scale）。当 :math:`s = 1.0` 时，引导退化为标准条件生成；当 :math:`s > 1.0` 时，外推向量将潜变量更强烈地推向条件概率密度最高的核心流形区域。

在 ComfyUI 的物理架构中，计算常在预测的纯净图像流形空间（:math:`x_0` Denoised Space）中执行：

.. math::

   	ilde{x}_0(x_t, c, \emptyset; s) = \hat{x}_0(x_t, \emptyset) + s \cdot \left( \hat{x}_0(x_t, c) - \hat{x}_0(x_t, \emptyset) \right)

其几何向量场投影如下图所示：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                                 CFG 几何流形向量外推与负向对抗                                      |
   +----------------------------------------------------------------------------------------------------+
                                                        x_t (当前带噪状态)
                                                           /          \
                                                          /            \
                                                         /              \
                                                        v                v
                                          x0_uncond (负向/无条件流形)   x0_cond (正向条件流形)
                                                        \                /
                                                         \              /
                          外推反向推离负向流形 ───> \            / <─── 正向吸引梯度 (cond - uncond)
                                                           \          /
                                                            \        /
                                                             v      v
                                             x0_final = x0_uncond + s * (x0_cond - x0_uncond)
                                                        (远离负向，高度集中于正向流形高密区)

1.2 负向提示词对抗机制（Negative Prompt Adversarial Projection）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当用户指定负向提示词 :math:`c_{	ext{neg}}`（如 "low quality, blurry, deformed"）时，ComfyUI 将原本的空条件 :math:`\emptyset` 替换为 :math:`c_{	ext{neg}}`：

.. math::

   	ilde{x}_0 = \hat{x}_0(x_t, c_{	ext{neg}}) + s \cdot \left( \hat{x}_0(x_t, c_{	ext{pos}}) - \hat{x}_0(x_t, c_{	ext{neg}}) \right)

通过代数变形可得：

.. math::

   	ilde{x}_0 = s \cdot \hat{x}_0(x_t, c_{	ext{pos}}) - (s - 1) \cdot \hat{x}_0(x_t, c_{	ext{neg}})

这表明负向提示词实际上在目标流形上构建了一个“排斥势能场”，以 :math:`-(s - 1)` 的权重抑制负向特征在潜空间中的激活概率。

------------------------------------------------------------------------

2. 潜空间数值爆炸与方差膨胀机理
--------------------------------

虽然提高 CFG 尺度 :math:`s` 能够显著增强图像与提示词的契合度与色彩对比度，但线性外推会导致潜变量的统计方差产生不可逆的非物理膨胀。

2.1 方差爆炸的数学推导
~~~~~~~~~~~~~~~~~~~~~~

设条件预测与无条件预测为具有相关系数 :math:`\rho` 的随机变量：

.. math::

   	ext{Var}(\hat{x}_{0,	ext{pos}}) \approx \sigma_0^2, \quad 	ext{Var}(\hat{x}_{0,	ext{neg}}) \approx \sigma_0^2, \quad 	ext{Cov}(\hat{x}_{0,	ext{pos}}, \hat{x}_{0,	ext{neg}}) = \rho \sigma_0^2

则 CFG 外推后的潜变量方差为：

.. math::

   	ext{Var}(	ilde{x}_0) = 	ext{Var}\left( (1 - s) \hat{x}_{0,	ext{neg}} + s \hat{x}_{0,	ext{pos}} \right) = \sigma_0^2 \cdot \left[ s^2 + (s - 1)^2 + 2s(1 - s)\rho \right]

当 :math:`s = 7.5, \rho = 0.8` 时：

.. math::

   	ext{Var}(	ilde{x}_0) \approx \sigma_0^2 \cdot \left[ 56.25 + 42.25 - 2 	imes 7.5 	imes 6.5 	imes 0.8 \right] \approx 20.5 \sigma_0^2

方差膨胀超过 **20 倍**！这使得原本处于标准正态分布 :math:`\mathcal{N}(0, 1)` 内的潜空间激活值大量溢出至 :math:`[-10, 10]` 以上，导致 VAE 解码器输入饱和，在图像中表现为强烈的**高对比度色斑、线条硬化与局部死黑**。

------------------------------------------------------------------------

3. 潜空间流形校准算法：Rescale CFG 与动态阈值截断
--------------------------------------------------

为了保留高 CFG 的构图对齐优势并彻底消除数值爆炸伪影，ComfyUI 在采样流程中原生集成了多重方差约束算法。

3.1 方差重缩放（Rescale CFG）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 SDXL 论文及 Common Diffusion Noise Schedules 中提出的 Rescale CFG，核心思想是**强制将外推后张量的标准差拉回正向条件预测的标准差水平**。

在 ``comfy/samplers.py`` 的自定义 ``sampler_cfg_function`` 注册中实现如下：

.. math::

   \sigma_{	ext{pos}} = 	ext{std}(\hat{x}_{0,	ext{pos}}), \quad \sigma_{	ext{cfg}} = 	ext{std}(	ilde{x}_0)

   	ilde{x}_{0,	ext{rescaled}} = 	ilde{x}_0 \cdot \left( \frac{\sigma_{	ext{pos}}}{\sigma_{	ext{cfg}}} \right)

   	ilde{x}_{0,	ext{final}} = \phi \cdot 	ilde{x}_{0,	ext{rescaled}} + (1 - \phi) \cdot 	ilde{x}_0

.. code-block:: python

    def rescale_cfg_function(args):
        cond = args["cond"]          # 实际对应 x - cond_pred
        uncond = args["uncond"]      # 实际对应 x - uncond_pred
        cond_scale = args["cond_scale"]
        rescale_phi = 0.7            # 推荐重缩放系数

        # 1. 基础 CFG 线性外推
        cfg_result = uncond + cond_scale * (cond - uncond)

        # 2. 空间多通道标准差统计 (沿 C, H, W 维度)
        std_cond = cond.std(dim=(-3, -2, -1), keepdim=True)
        std_cfg = cfg_result.std(dim=(-3, -2, -1), keepdim=True)

        # 3. 执行能量守恒归一化与凸组合融合
        rescaled = cfg_result * (std_cond / std_cfg)
        return rescale_phi * rescaled + (1.0 - rescale_phi) * cfg_result

3.2 动态阈值截断（Dynamic Thresholding / Mimic CFG）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

源自 Google Imagen 的动态阈值算法通过分位数动态限制潜变量的绝对峰值幅值：

1. **计算绝对值分位数（如 99.5% 分位点）**：

   .. math::

      s_p = 	ext{Percentile}\left( |	ilde{x}_0|, p = 0.995 \right)

2. **动态阈值归一化**：
   若 :math:`s_p > 1.0`，则将数值截断在 :math:`[-s_p, s_p]` 并按 :math:`s_p` 整体等比缩放：

   .. math::

      	ilde{x}_{0,	ext{clamped}} = \frac{	ext{clamp}(	ilde{x}_0, -s_p, s_p)}{s_p}

这既保留了图像的高频梯度分布方向，又严格将潜变量幅值锁定在 VAE 解码的安全动态范围内。

------------------------------------------------------------------------

4. 自注意力引导（SAG）与扰动注意力引导（PAG）
----------------------------------------------

传统的 CFG 必须为每个采样步执行两次完整的神经网络前向计算（正向与负向批次），导致算力消耗翻倍。近年来出现的自注意力引导（SAG）与扰动注意力引导（PAG）构建了**无需文本编码器的自引导范式**。

4.1 扰动自注意力引导（PAG）数学原理
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

PAG 认为生成过程中的错误先验主要源于自注意力层对空间结构的不当聚合。因此，PAG 将自注意力矩阵替换为恒等映射（Identity Matrix）或高斯模糊核构造“退化模型（Perturbed Model）”作为负向分支：

.. math::

   	ilde{x}_0 = \hat{x}_{0,	ext{original}} + s_{	ext{pag}} \cdot \left( \hat{x}_{0,	ext{original}} - \hat{x}_{0,	ext{perturbed}} \right)

4.2 各种高级引导算法物理特性对照
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 扩散模型引导与方差校准技术全面对比
   :widths: 20 25 25 30
   :header-rows: 1

   * - 引导/校准算法
     - 额外前向开销 (NFE)
     - 核心物理机制
     - 适用场景与工程收益
   * - **标准 CFG**
     - 2x NFE (正向 + 负向)
     - 正负文本嵌入空间线性外推
     - 通用文本条件对齐，最基础引导标准
   * - **Rescale CFG**
     - 0 (纯后处理计算)
     - 正向方差对齐与标准差重缩放
     - 消除 $s \ge 7.0$ 时的过饱和与色彩发焦，推荐用于 SDXL
   * - **Dynamic Thresholding**
     - 极小 (分位数统计)
     - 潜空间 99.5% 绝对峰值动态截断
     - 支持 $s \in [15, 30]$ 的极限提示词强控制
   * - **CFG=1 单分支优化**
     - 1x NFE (跳过负向)
     - 当 $s=1.0$ 时数学上跳过 Uncond 前向
     - 采样速度提升 50%（广泛用于 Flux.1 / Turbo / LCM 模型）
   * - **PAG (扰动引导)**
     - 0 ~ 1x NFE
     - 自注意力矩阵扰动退化差分
     - 无需负向文本提示词，显著修复手部结构与复杂几何畸变

------------------------------------------------------------------------

5. 单卡与多卡并行下的条件批处理调度闭环
----------------------------------------

在实际工程执行中，ComfyUI 通过 ``calc_cond_batch()`` 与 ``CFGGuider.predict_noise()`` 将 CFG 计算转化为高效的批处理矩阵乘法（GEMM）。

5.1 ``CFG=1`` 单分支跳过优化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``sampling_function()`` 中，系统首先检测是否能够跳过负向计算：

.. code-block:: python

    if math.isclose(cond_scale, 1.0) and model_options.get("disable_cfg1_optimization", False) == False:
        # 当 CFG=1.0 且未强制禁用优化时，彻底置空 uncond 分支
        uncond_ = None
    else:
        uncond_ = uncond

    conds = [cond, uncond_]
    # 仅将非空条件打包送入 calc_cond_batch
    out = calc_cond_batch(model, conds, x, timestep, model_options)

5.2 多 GPU 异构并行调度（``_calc_cond_batch_multigpu``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在多卡环境下，正向条件（Cond）与负向条件（Uncond）被分发至独立的 GPU 副本：

.. code-block:: text

   Master Thread (KSampler)
      |
      ├──> GPU 0 Worker: 执行 Positive Condition 前向 ──> 产出 out_cond
      └──> GPU 1 Worker: 执行 Negative Condition 前向 ──> 产出 out_uncond
      |
      v MultiGPUThreadPool.get_result()
   聚合双卡张量 -> 异步搬移至主设备 -> 执行 cfg_function(out_cond, out_uncond, cond_scale)

这一机制消除了单卡批处理在显存不足时被迫切分为串行 Chunk 的等待开销，使双卡工作站的采样吞吐接近理论翻倍。

------------------------------------------------------------------------

小结与下章导读
==============

本节系统剖析了扩散模型的条件引导与几何校准体系：

1. **CFG 几何外推本质**：推导了正向吸引与负向对抗在得分空间与去噪空间中的数学公式；
2. **方差膨胀机理**：论证了高 CFG 导致潜变量方差激增 20 倍以上的数学机理与伪影根源；
3. **流形校准闭环**：解析了 Rescale CFG 方差对齐与动态阈值分位数截断的物理实现；
4. **自注意力引导扩展**：探讨了 PAG/SAG 无提示词自引导范式的优势；
5. **计算加速与多卡调度**：分析了 ``CFG=1`` 单分支跳过优化与多 GPU 条件并发机制。

在下一节（``04_ode_sde_solvers_internals.rst``）中，我们将迎来第 5 模块的完结篇——**经典 ODE/SDE 求解器内核实现**：深度推导 Euler, Heun, DPM-Solver++, UniPC, LCM 等一阶、二阶及高阶预估-校正数值求解器的每步更新张量流与随机扰动注入方程。
