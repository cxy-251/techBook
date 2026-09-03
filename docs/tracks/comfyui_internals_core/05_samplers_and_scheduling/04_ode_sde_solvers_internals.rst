========================================================================
经典 ODE/SDE 求解器内核：Euler、Heun、DPM-Solver++、UniPC 与 Ancestral 随机采样微分方程离散化
========================================================================

.. note:: 前置背景与上下文承接
   在第 5 模块前三节中，我们建立了采样器执行状态机（``01_samplers_and_kdiffusion_wrapper.rst``）、推导了离散/连续噪声时间表（``02_noise_schedules_and_sigmas.rst``）并剖析了 CFG 引导与流形方差校准（``03_cfg_and_guidance_computation.rst``）。然而，所有前置模块输出的去噪潜变量预测 :math:`\hat{x}_0` 与噪声得分 :math:`\epsilon_	heta`，最终都必须由具体的**常微分方程（ODE）与随机微分方程（SDE）数值积分求解器**在时间轴上执行状态步进更新。不同的求解器在截断误差阶数（Order of Accuracy）、计算开销（NFE/step）、收敛稳定性以及随机性注入机制上存在巨大差异。ComfyUI 在 ``comfy/k_diffusion/sampling.py`` 与 ``comfy/extra_samplers/uni_pc.py`` 中深度实现了数十种前沿数值求解器。本节系统推导各经典求解器的数学积分方程、张量更新流与随机布朗树物理机制。

------------------------------------------------------------------------

1. 逆向扩散过程的 ODE 与 SDE 理论统一表征
-----------------------------------------

在生成式扩散模型的连续时间动力学中，数据分布的演化由伊藤随机微分方程（Itô SDE）描述：

.. math::

   \mathrm{d} x = f(x, t) \mathrm{d} t + g(t) \mathrm{d} w

根据 Song 等人的得分匹配理论，存在一个与 SDE 具有完全相同边际概率分布 :math:`p_t(x)` 的**确定性概率流微分方程（Probability Flow ODE, PF-ODE）**：

.. math::

   \mathrm{d} x = \left[ f(x, t) - \frac{1}{2} g(t)^2 
abla_x \log p_t(x) \right] \mathrm{d} t

1.1 Karras ODE 规范化导数映射
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 EDM（Elucidating the Design Space of Diffusion-Based Generative Models）坐标系下，PF-ODE 在标准差空间 :math:`\sigma` 下具有极其优美的无漂移形式：

.. math::

   \mathrm{d} x = \frac{x - D_	heta(x; \sigma)}{\sigma} \mathrm{d} \sigma

在 ``comfy/k_diffusion/sampling.py`` 中，核心函数 ``to_d()`` 建立了这一物理导数映射：

.. code-block:: python

    def to_d(x, sigma, denoised):
        """将神经网络去噪输出 denoised 转换为 Karras ODE 瞬时导数 d"""
        return (x - denoised) / utils.append_dims(sigma, x.ndim)

- **ODE 轨迹的物理意义**：:math:`d = \frac{x - \hat{x}_0}{\sigma}` 描述了从当前带噪状态 :math:`x` 指向纯净流形 :math:`\hat{x}_0` 的单位速度向量；数值求解器的核心任务，就是沿着这一向量场进行数值积分。

------------------------------------------------------------------------

2. 经典一阶与显式二阶单步求解器（Euler & Heun）
-----------------------------------------------

2.1 一阶前向欧拉求解器（``sample_euler``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

前向欧拉法是一阶精度的显式单步数值积分器。在每一步 :math:`i`，求解器直接沿着当前切线方向外推：

.. math::

   \Delta t = \sigma_{i+1} - \sigma_i, \quad x_{i+1} = x_i + d_i \cdot \Delta t

.. code-block:: python

    @torch.no_grad()
    def sample_euler(model, x, sigmas, extra_args=None, callback=None, disable=None):
        for i in trange(len(sigmas) - 1, disable=disable):
            # 1. 前向评估神经网络
            denoised = model(x, sigmas[i] * s_in, **extra_args)
            # 2. 计算瞬时导数
            d = to_d(x, sigmas[i], denoised)
            # 3. 欧拉线性步进更新
            dt = sigmas[i + 1] - sigmas[i]
            x = x + d * dt
        return x

- **物理特征**：每步仅需 1 次模型评估（1 NFE/step），计算速度最快，但在大步长下局部截断误差为 :math:`\mathcal{O}(\Delta t^2)`，容易在曲率较大处偏离真实流形。

2.2 显式二阶龙格库塔-休恩求解器（``sample_heun``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Heun 算法采用**预估-校正（Predictor-Corrector）**机制，通过在终点处重新评估导数并取平均，将局部截断误差降低至 :math:`\mathcal{O}(\Delta t^3)`：

1. **预估步（Predictor Step）**：

   .. math::

      	ilde{x}_{i+1} = x_i + d_i \cdot (\sigma_{i+1} - \sigma_i)

2. **校正评估（Corrector Evaluation）**：

   .. math::

      d'_{i+1} = 	ext{to\_d}\left(	ilde{x}_{i+1}, \sigma_{i+1}, D_	heta(	ilde{x}_{i+1}; \sigma_{i+1})\right)

3. **梯形校正步（Trapezoidal Update）**：

   .. math::

      x_{i+1} = x_i + \frac{d_i + d'_{i+1}}{2} \cdot (\sigma_{i+1} - \sigma_i)

- **物理特征**：每步需要 2 次模型评估（2 NFE/step）。在相同总步数下虽然计算耗时翻倍，但收敛曲线极其平滑，几何伪影显著低于 Euler。

2.3 对数流形二阶求解器（``sample_dpm_2``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

传统的 Heun 在实数空间中点取样，而 ``dpm_2`` 在几何对数空间中点取样：

.. math::

   \sigma_{	ext{mid}} = \exp\left( \frac{\ln \sigma_i + \ln \sigma_{i+1}}{2} \right) = \sqrt{\sigma_i \cdot \sigma_{i+1}}

在 :math:`\sigma_{	ext{mid}}` 处计算预估导数，更精准地拟合了对数信噪比（log-SNR）流形的非线性曲率。

------------------------------------------------------------------------

3. 高阶多步与指数积分器（DPM-Solver++ & UniPC）
-----------------------------------------------

在生产实践中，2 NFE/step 的显式二阶方法计算成本过高。**多步法（Multistep Methods）**通过复用前几步的历史导数，实现了**不增加额外 NFE 的高阶精度收敛**。

3.1 DPM-Solver++(2M) 多步指数积分器
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

DPM-Solver++ 针对扩散 ODE 的半线性特征，在对数时间空间 :math:`\lambda = \ln(\alpha_t / \sigma_t)` 下将线性项精确解析求解，仅对非线性得分项执行泰勒展开：

.. math::

   h = \lambda_{i+1} - \lambda_i, \quad r = \frac{h_{	ext{last}}}{h}

利用当前步 :math:`D_i` 与历史步 :math:`D_{i-1}` 构造二阶外推插值：

.. math::

   D_i^{	ext{multistep}} = \left(1 + \frac{1}{2r}\right) D_i - \frac{1}{2r} D_{i-1}

   x_{i+1} = \frac{\sigma_{i+1}}{\sigma_i} x_i - (e^{-h} - 1) D_i^{	ext{multistep}}

.. code-block:: python

    @torch.no_grad()
    def sample_dpmpp_2m(model, x, sigmas, extra_args=None, callback=None, disable=None):
        old_denoised = None
        for i in trange(len(sigmas) - 1, disable=disable):
            denoised = model(x, sigmas[i] * s_in, **extra_args)
            t, t_next = t_fn(sigmas[i]), t_fn(sigmas[i + 1])
            h = t_next - t

            if old_denoised is None or sigmas[i + 1] == 0:
                # 第一步退化为 1 阶指数积分
                x = (sigma_fn(t_next) / sigma_fn(t)) * x - (-h).expm1() * denoised
            else:
                # 2 阶多步插值
                h_last = t - t_fn(sigmas[i - 1])
                r = h_last / h
                denoised_d = (1 + 1 / (2 * r)) * denoised - (1 / (2 * r)) * old_denoised
                x = (sigma_fn(t_next) / sigma_fn(t)) * x - (-h).expm1() * denoised_d

            old_denoised = denoised
        return x

3.2 UniPC 统一预测-校正器（Unified Predictor-Corrector）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

UniPC 统一了任意阶 Adams-Bashforth 预估器与 Adams-Moulton 校正器：

.. math::

   x_{t_{i+1}}^{	ext{pred}} = \phi(h) x_{t_i} + \sum_{j=0}^{k-1} B_j D(x_{t_{i-j}})

在极低步数（如 5~10 步）下，UniPC 能以极高保真度重构全局语义与高频轮廓，是目前生成速度最快的无损失求解器之一。

------------------------------------------------------------------------

4. 随机微分方程（SDE）与 Ancestral 采样物理动力学
-------------------------------------------------

纯确定性 ODE 采样在生成大面部、水面波纹与毛发纹理时容易产生过度平滑（Over-smoothing）伪影。**SDE 与 Ancestral 随机采样** 通过在每步积分中主动注入受控的随机布朗运动扰动，动态恢复图像的高频微观熵。

4.1 步长退化与随机噪声注入（``get_ancestral_step``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Ancestral 采样（如 ``euler_ancestral``, ``dpmpp_2s_ancestral``）首先将目标步长 :math:`\sigma_{i+1}` 分解为确定性回退尺度 :math:`\sigma_{	ext{down}}` 与随机注入尺度 :math:`\sigma_{	ext{up}}`：

.. math::

   \sigma_{	ext{up}} = \min\left( \sigma_{i+1}, \, \eta \sqrt{\frac{\sigma_{i+1}^2 (\sigma_i^2 - \sigma_{i+1}^2)}{\sigma_i^2}} \right)

   \sigma_{	ext{down}} = \sqrt{\sigma_{i+1}^2 - \sigma_{	ext{up}}^2}

状态更新公式为：

.. math::

   x_{i+1} = x_i + d_i \cdot (\sigma_{	ext{down}} - \sigma_i) + \epsilon \cdot \sigma_{	ext{up}}, \quad \epsilon \sim \mathcal{N}(0, \mathbf{I})

当 :math:`\eta = 1.0` 时，随机注入量达到最大；当 :math:`\eta = 0` 时，采样器严格退化为确定性 ODE。

4.2 连续布朗运动树（``BrownianTreeNoiseSampler``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``dpmpp_2m_sde`` 与 ``dpmpp_3m_sde`` 中，离散随机数发生器会导致不同步长间的马尔可夫随机积分产生方差漂移。

ComfyUI 通过集成 ``torchsde.BrownianTree`` 构建了**连续时间维纳过程（Wiener Process）布朗树**：

.. code-block:: python

    class BrownianTreeNoiseSampler:
        def __init__(self, x, sigma_min, sigma_max, seed=None):
            self.tree = BatchedBrownianTree(x, t0, t1, seed=seed)

        def __call__(self, sigma, sigma_next):
            # 严格按照维纳过程区间差分计算归一化增量: W(t2) - W(t1) / sqrt(dt)
            return self.tree(sigma, sigma_next) / (sigma_next - sigma).abs().sqrt()

这确保了无论采样步数如何变化，随机扰动在连续时间域上始终满足严格的柯尔莫哥洛夫连续性条件。

------------------------------------------------------------------------

5. 全求解器族谱物理与计算特性对照表
------------------------------------

.. list-table:: ComfyUI 核心数值求解器物理性能与算法特征全景对照
   :widths: 18 16 18 20 28
   :header-rows: 1

   * - 求解器名称
     - 理论阶数
     - 单步开销 (NFE)
     - 随机性类型
     - 核心优势与适用场景
   * - **``euler``**
     - 1 阶
     - 1 NFE/step
     - 确定性 ODE
     - 速度极快，适合快速验证与 Flux/SD3 直线流生成
   * - **``euler_ancestral``**
     - 1 阶
     - 1 NFE/step
     - 随机 SDE
     - 构图生动多变，二次元画风标准推荐
   * - **``heun``**
     - 2 阶
     - 2 NFE/step
     - 确定性 ODE
     - 几何轮廓精准收敛，高步数（30+）极限画质
   * - **``dpmpp_2m``**
     - 2 阶
     - 1 NFE/step
     - 确定性 ODE
     - 20 步以内画质与速度的最佳平衡点（业界黄金标准）
   * - **``dpmpp_2m_sde``**
     - 2 阶
     - 1 NFE/step
     - 布朗树 SDE
     - 极强的高频细节重构能力，彻底消除写实人像塑料感
   * - **``uni_pc``**
     - 任意多阶
     - 1 NFE/step
     - 确定性 ODE
     - 5~10 步极限加速收敛，移动端与实时交互首选
   * - **``lcm``**
     - 1 阶
     - 1 NFE/step
     - 潜在稠密一致性
     - 专用于 LCM / Turbo 蒸馏模型的 2~4 步超极速推理

------------------------------------------------------------------------

小结与下章导读
==============

本节系统剖析了 ComfyUI 的数值积分求解器内核：

1. **微分方程统一建模**：确立了基于 Karras 规范化导数 :math:`d = (x - \hat{x}_0)/\sigma` 的 PF-ODE 积分基准；
2. **显式与多步算法**：推导了一阶 Euler、二阶显式 Heun 以及零额外开销的 DPM-Solver++(2M) 多步法；
3. **随机动力学与布朗树**：解析了 Ancestral 步长分解方程与基于 ``torchsde`` 的连续维纳过程物理实现；
4. **全景求解器族谱**：列表建立了各求解器在精度阶数、计算开销与随机特性上的对应矩阵。

至此，**第 5 模块《采样器数值解法与调度方程》全 4 节已圆满结稿**。

在接下来的 **第 6 模块《文本编码与潜空间重构》（06_text_encoding_and_latent）** 中，我们将转向生成流水线的输入与输出端——深入探究 CLIP/T5 文本分词管道、77-Token 长文本 Chunking 切分、变分自编码器（VAE）卷积重构，以及大图切块（Tiled VAE）边缘羽化融合的底层物理实现。
