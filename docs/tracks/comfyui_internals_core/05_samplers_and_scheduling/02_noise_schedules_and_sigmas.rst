========================================================================
连续与离散噪声时间表（Beta/Cosine/Simple/Karras）与 Sigmas 序列生成方程
========================================================================

.. note:: 前置背景与上下文承接
   在前一节（``01_samplers_and_kdiffusion_wrapper.rst``）中，我们系统拆解了 ``KSampler`` 调度架构与 ``CFGGuider`` 状态机，明确了数值积分器如何在离散时间步上逐步逼近目标流形。然而，数值求解器的收敛速度与生成图像的微观质感，在极大程度上取决于**噪声时间表（Noise Schedule / Sigmas 序列）**的离散化轨迹设计。若时间步划分过于均匀，求解器在纯噪声阶段会浪费无谓的计算步数，而在中低噪声的高频细节生成期又会因步长过大产生严重的离散化截断误差（Discretization Error）。ComfyUI 在 ``comfy/samplers.py`` 与 ``comfy/model_sampling.py`` 中统一抽象了从经典 DDPM 离散调度、Karras 幂次曲率对齐、Beta 分布形变到现代 Rectified Flow 流移位（Flow Shift）的数学体系。本节系统推导各调度方程的物理含义与工程实现。

------------------------------------------------------------------------

1. 扩散微分方程物理量：信噪比（SNR）与噪声尺度（$\sigma$）
---------------------------------------------------------

在连续扩散概率模型（Continuous Diffusion Models）与得分匹配（Score Matching）理论中，前向加噪过程被建模为伊藤随机微分方程（SDE）：

.. math::

   x_t = \alpha_t x_0 + \sigma_t \epsilon, \quad \epsilon \sim \mathcal{N}(0, \mathbf{I})

1.1 物理坐标转换公式
~~~~~~~~~~~~~~~~~~~~

ComfyUI 将所有离散与连续扩散模型统一映射至标准噪声尺度空间 :math:`\sigma \in [\sigma_{	ext{min}}, \sigma_{	ext{max}}]`：

.. math::

   	ext{SNR}(t) = \frac{\alpha_t^2}{\sigma_t^2} = \frac{\bar{\alpha}_t}{1 - \bar{\alpha}_t}

由此可得离散方差保持（Variance Preserving, VP）模型与连续标准差 :math:`\sigma` 之间的双向物理映射：

.. math::

   \sigma = \sqrt{\frac{1 - \bar{\alpha}}{\bar{\alpha}}}, \quad \bar{\alpha} = \frac{1}{\sigma^2 + 1}

对于现代流匹配（Flow Matching）连续模型（如 Flux.1、SD3），加噪轨迹采用线性插值形式：

.. math::

   x_t = (1 - t) x_0 + t \epsilon, \quad \sigma \equiv t \in [0, 1]

------------------------------------------------------------------------

2. 主流噪声调度方程（Noise Schedulers）数学推导与物理分析
----------------------------------------------------------

在 ComfyUI 的 ``SCHEDULER_HANDLERS`` 调度分发表中，系统提供了十余种不同的噪声离散化方程：

2.1 Karras 幂次曲率调度（``karras``, $\rho = 7$）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Karras 等人在 EDM 论文中指出，生成模型在不同噪声尺度下的有效特征维度演变是非线性的。为了使数值求解器在每一步产生的几何离散化误差保持均匀，时间步必须沿噪声曲率进行非均匀幂次变形：

.. math::

   \sigma_i = \left( \sigma_{	ext{max}}^{\frac{1}{\rho}} + \frac{i}{N - 1} \left( \sigma_{	ext{min}}^{\frac{1}{\rho}} - \sigma_{	ext{max}}^{\frac{1}{\rho}} \right) \right)^\rho, \quad i \in [0, N-1]

- **超参数设定**：ComfyUI 默认取 :math:`\rho = 7`。
- **物理特性**：当 :math:`\rho = 7` 时，在 :math:`\sigma > 10` 的高噪声区域（纯几何轮廓确定期），步长极快跨越；而在 :math:`\sigma \in [0.1, 2.0]` 的中低噪声区域（面部五官、毛发与材质纹理形成期），采样点高度密集分布，使得 20 步以内的生成画质大幅提升。

2.2 简单离散调度（``simple``）与均匀步长（``normal`` / ``sgm_uniform``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **``simple`` 调度器**：
  直接在底层模型预计算的 1000 步离散 :math:`\sigma` 数组中执行等距索引抽取：

  .. math::

     	ext{idx}_i = \left\lfloor i \cdot \frac{L - 1}{N} \right\rfloor, \quad \sigma_i = \mathbf{\sigma}_{	ext{model}}[L - 1 - 	ext{idx}_i]

- **``normal`` / ``sgm_uniform`` 调度器**：
  在线性时间步索引空间均匀插值后反查物理噪声尺度：

  .. math::

     t_i = t_{	ext{start}} + \frac{i}{N - 1} (t_{	ext{end}} - t_{	ext{start}}), \quad \sigma_i = 	ext{ModelSampling.sigma}(t_i)

2.3 Beta 分布曲线调度（``beta``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

基于论文 *Beta Sampling for Diffusion Models*，利用正则化不完全 Beta 分布的分位数函数（Percent Point Function, PPF）实现时间流形形变：

.. math::

   	au_i = 1 - \frac{i}{N}, \quad t_i = 	ext{round}\left( 	ext{Beta}_{	ext{ppf}}(	au_i; \alpha=0.6, \beta=0.6) \cdot T_{	ext{total}} \right)

当 :math:`\alpha = \beta = 0.6` 时，Beta 分布呈 U 型对称特征，在极高噪声与极低噪声两端分配更多步数以强化全局结构与极端高频微调。

2.4 指数衰减调度（``exponential``）与 KL 最优调度（``kl_optimal``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **``exponential`` 指数调度**：
  噪声在对数空间严格均匀递减：

  .. math::

     \sigma_i = \sigma_{	ext{max}} \cdot \left( \frac{\sigma_{	ext{min}}}{\sigma_{	ext{max}}} \right)^{\frac{i}{N - 1}} = \exp\left( \ln \sigma_{	ext{max}} + \frac{i}{N-1} (\ln \sigma_{	ext{min}} - \ln \sigma_{	ext{max}}) \right)

- **``kl_optimal`` 正切逆投影调度**：
  通过 :math:`\arctan` 空间插值最小化两步分布间的 KL 散度：

  .. math::

     \sigma_i = 	an\left( \left(1 - \frac{i}{N-1}\right) \arctan(\sigma_{	ext{max}}) + \frac{i}{N-1} \arctan(\sigma_{	ext{min}}) \right)

------------------------------------------------------------------------

3. 噪声时间表物理特性与适用场景全景对照
----------------------------------------

.. list-table:: ComfyUI 核心噪声时间表数学特征与适用场景对照
   :widths: 18 27 25 30
   :header-rows: 1

   * - 调度器名称
     - 数学曲率分布方程
     - 步长密度集中区
     - 最佳适配模型与应用场景
   * - **``karras``**
     - :math:`\sigma_i = (\sigma_{	ext{max}}^{1/7} + \Delta)^{7}`
     - 中低噪声区（高频纹理期）
     - SD 1.5 / SDXL 配合 DPM++ 2M / Euler，20 步精细生成标准推荐
   * - **``exponential``**
     - :math:`\sigma_i = \sigma_{	ext{max}} \cdot r^i`
     - 几何指数对数衰减
     - 动漫/二次元模型平滑色块渲染，避免阶梯状色阶断层
   * - **``simple``**
     - 原始模型数组等步长抽取
     - 依赖基础模型内置先验
     - 保持与原生 Diffusers/A1111 离散基准严格数值对齐
   * - **``sgm_uniform``**
     - 时间步线性等距插值
     - 全程均匀分布
     - Stability AI 官方 SGM 标准模型（如 SVD 视频生成）
   * - **``beta``**
     - Beta 逆累积分布 U 型采样
     - 极高噪声 + 极低噪声端
     - 复杂长文本多主体构图与微观毛发去噪
   * - **``kl_optimal``**
     - :math:`	an(	ext{lerp}(\arctan \sigma))`
     - 极端平滑曲率过渡
     - 极低步数（< 12 步）下抑制局部伪影与过饱和

------------------------------------------------------------------------

4. 时间移位（Time Shift）与零终端信噪比（Zero Terminal SNR）
-------------------------------------------------------------

4.1 连续流时间移位（Flow Shift & SNR Shift）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在大分辨率图像（如 $1024 	imes 1024$ 或 4K）生成中，由于图像 Patch 数量激增，初始高斯噪声在空间维度的相关性被稀释，导致默认的线性时间流动过快脱离高噪声阶段。

ComfyUI 在 ``comfy/model_sampling.py`` 中实现了流移位（Flow Shift）机制：

.. math::

   	ilde{t} = 	ext{time\_shift}(t; \alpha) = \frac{\alpha t}{1 + (\alpha - 1) t}

- **Flux 专用时间位移（Flux Shift）**：
  Flux 引入了双参数指数位移方程：

  .. math::

     	ilde{t}_{	ext{flux}} = \frac{e^{\mu}}{e^{\mu} + \left(\frac{1}{t} - 1\right)^\sigma}, \quad \mu = 1.15

  通过将 $\mu > 0$，时间轨迹在中高噪声区域被显著“拉长”，为大模型构建全局主体构图留出充分的迭代步数。

4.2 零终端信噪比（Zero Terminal SNR / ZSNR）校准
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

标准 SD 1.5 训练中的最后一个时间步满足 :math:`\bar{\alpha}_T \approx 0.0047 
eq 0`，这意味着图像在理论最高噪声下依然残留了 0.47% 的原图信号。在推理阶段若直接从该分布采样，将导致生成暗色/纯黑场景时出现无法消除的“灰色光晕”伪影。

ComfyUI 在 ``rescale_zero_terminal_snr_sigmas()`` 中通过两极重缩放强制使 :math:`\bar{\alpha}_T \equiv 0`：

.. math::

   \sqrt{\bar{\alpha}_t}^{	ext{rescaled}} = \left( \sqrt{\bar{\alpha}_t} - \sqrt{\bar{\alpha}_T} \right) \cdot \frac{\sqrt{\bar{\alpha}_0}}{\sqrt{\bar{\alpha}_0} - \sqrt{\bar{\alpha}_T}}

   \sigma_{	ext{zsnr}} = \sqrt{\frac{1 - \bar{\alpha}_{	ext{rescaled}}}{\bar{\alpha}_{	ext{rescaled}}}}, \quad \sigma_T 	o \infty

------------------------------------------------------------------------

5. 去噪因子（Denoise Factor）与 Sigmas 序列截断切片
---------------------------------------------------

在图生图（Image-to-Image）、局部重绘（Inpaint）与分段精炼（Refiner）工作流中，用户设置的 ``denoise`` 参数（例如 ``denoise = 0.6``）并非简单地按比例缩减循环次数，而是对全局 Sigmas 序列执行精密的**物理截断与重缩放**。

5.1 步数反折算与子序列截取
~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``KSampler.set_steps()`` 中，系统首先计算出等效全去噪步数：

.. code-block:: python

    if denoise < 1.0:
        # 1. 计算覆盖全生命周期所需的理论总步数
        new_steps = int(steps / denoise)
        # 2. 生成全量理论 Sigmas 序列
        sigmas = calculate_sigmas(model_sampling, scheduler, new_steps).to(device)
        # 3. 从末尾截取与当前 steps 对齐的有效去噪子序列
        self.sigmas = sigmas[-(steps + 1):]

其物理几何意义如下图所示：

.. code-block:: text

   全局 50 步 Sigmas 序列 (对应 denoise=1.0 全程去噪):
   [14.61, 10.22, ..., 2.85, 1.62, 0.95, 0.52, 0.28, 0.11, 0.0]
    |                                   |                       |
    | <──────── 丢弃的高噪声阶段 ──────> | <── 有效去噪区间 ───> |
    |                                   | (对应 denoise=0.4, 20步)
                                        v
                                初始加噪点 sigma_0 = 1.62
                                (直接向原始输入潜变量注入 1.62 尺度的噪声)

5.2 倒数第二步丢弃算子（``DISCARD_PENULTIMATE_SIGMA``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于特定的二阶多步求解器（如 ``dpm_2``, ``dpm_2_ancestral``, ``uni_pc``），其最后一步的积分校正步长会导致 :math:`\sigma_{N-1}` 与 :math:`\sigma_N = 0` 发生数值奇异。ComfyUI 在生成 Sigmas 序列时自动检测并将总步数加 1，并在计算后直接剔除倒数第二个元素：

.. code-block:: python

    if self.sampler in self.DISCARD_PENULTIMATE_SIGMA_SAMPLERS:
        steps += 1
        sigmas = calculate_sigmas(model_sampling, scheduler, steps)
        # 剔除倒数第二项: sigmas[:-2] 与 sigmas[-1:] 拼接
        sigmas = torch.cat([sigmas[:-2], sigmas[-1:]])

------------------------------------------------------------------------

小结与下章导读
==============

本节系统推导并剖析了 ComfyUI 的噪声时间表数学体系：

1. **物理尺度统一**：建立了基于连续标准差 :math:`\sigma` 与 SNR 的跨架构通用坐标系；
2. **调度方程分类学**：严格推导了 Karras 幂次曲率对齐（$\rho=7$）、Beta 分布逆分位数、指数对数衰减与 KL 最优调度方程；
3. **流移位与终端校准**：解析了 Flow Shift 在大分辨率下的时间拉伸以及 Zero Terminal SNR 消除灰色偏置的物理机理；
4. **Denoise 序列切片**：阐明了图生图场景下的总步数反折算算法与二阶奇异步剔除机制。

在下一节（``03_cfg_and_guidance_computation.rst``）中，我们将深入采样计算的引导中枢——**无分类器引导（CFG）与几何流形修正**：推导标准 CFG、负向提示词对抗投影、Rescale CFG、动态阈值裁剪（Dynamic Thresholding）以及 PAG（Perturbed-Attention Guidance）的数学本质与代码实现。
