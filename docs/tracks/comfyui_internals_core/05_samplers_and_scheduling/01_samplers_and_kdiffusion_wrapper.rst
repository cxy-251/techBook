========================================================================
KSampler 采样调度框架、CFGGuider 状态机与 k-diffusion 数值积分器统一封装
========================================================================

.. note:: 前置背景与上下文承接
   在第 4 模块《扩散模型基类与 DiT 架构抽象》中，我们系统剖析了预训练扩散模型骨干网络（UNet 与 DiT）内部的张量前向演进、时间步调制与多模态条件注入。然而，单次前向推理仅仅提供了生成流形上的一个局部梯度或速度场预测（Score / Velocity Estimate）。要将完全随机的高斯白噪声转化为具有丰富空间结构与高频细节的图像/视频，必须依赖**微分方程数值积分器（ODE/SDE Numerical Solvers）**在给定的噪声时间表（Noise Schedule）上执行数十次精密的离散时间步迭代。ComfyUI 在 ``comfy/samplers.py`` 与 ``comfy/k_diffusion/`` 中构建了工业级高吞吐的采样引擎。本节深入拆解 ``KSampler`` 调度总控、``CFGGuider`` 多层状态机、``calc_cond_batch`` 条件自适应批处理装箱算法，以及 ``k-diffusion`` 数值求解器的统一对象封装。

------------------------------------------------------------------------

1. KSampler 调度总控与 CFGGuider 双层状态机
-------------------------------------------

ComfyUI 将采样计算解耦为两层架构：

1. **外观调度层（``KSampler``）**：负责高层参数校验、去噪强度（``denoise``）折算与初始噪声序列（``sigmas``）的数学离散化；
2. **状态机执行中枢（``CFGGuider``）**：负责潜变量打包解包、多设备分配、条件空间掩码解析、条件批量装箱以及前向预测噪声组装。

其调用链路与多层状态流转如下图所示：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                                          KSampler 外观调度层                                        |
   |   - steps, denoise, scheduler, sampler_name                                                        |
   |   - sigmas = calculate_sigmas(model_sampling, scheduler, steps)                                    |
   |   - 依 denoise 裁剪 sigmas 序列: sigmas = sigmas[-(int(steps/denoise) + 1):]                       |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      | 调用 sample(model, noise, positive, negative, cfg, ...)
                                      v
   +----------------------------------------------------------------------------------------------------+
   |                                     CFGGuider 三级状态机执行中枢                                     |
   |                                                                                                    |
   |   【Phase 1: sample() - 潜变量打包与 Hook 策略配置】                                                |
   |      - 嵌套潜变量处理: pack_latents() 压平批次与空间维度                                           |
   |      - 掩码预处理: prepare_mask() 空间重采样并与 latent_shapes 对齐                                |
   |      - Hook 模式优化: 判定 hook 组数 <= 1 则降级为 MinVram 模式                                    |
   |                                                                                                    |
   |   【Phase 2: outer_sample() - 多设备线程池与资源生命周期安全区】                                    |
   |      - prepare_sampling(): 预热模型，锁定 load_device 显存                                         |
   |      - MultiGPU 调度: 构造 MultiGPUThreadPool 并派发多卡模型副本                                   |
   |      - 全生命周期守卫: try ... finally { thread_pool.shutdown(); cleanup(); restore_hooks() }      |
   |                                                                                                    |
   |   【Phase 3: inner_sample() - 空间条件解析与求解器主循环发射】                                     |
   |      - process_conds(): 解析区域提示词 (Area)、软掩码 (Mask) 与时间步区间                           |
   |      - 构建求解器闭包: WrapperExecutor(SAMPLER_SAMPLE) -> sampler.sample()                         |
   |      - process_latent_out(): 逆向重构最终输出潜变量                                                |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      | 驱动数值积分器迭代
                                      v
   +----------------------------------------------------------------------------------------------------+
   |             k-diffusion 求解器 (sample_euler, sample_dpmpp_2m...) 每步回调 CFGGuider.predict_noise |
   +----------------------------------------------------------------------------------------------------+

1.1 嵌套潜变量打包（Nested Latent Packing）机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当工作流需要同时生成多张不同长宽比的图像（例如批量生成 $512 	imes 768$ 与 $768 	imes 512$）时，传统的固定张量批处理会强制补零对齐，造成巨大的无效计算与显存浪费。

ComfyUI 在 ``CFGGuider.sample()`` 中引入了 **嵌套潜变量平铺（Nested Tensor Flat-Packing）**：

.. code-block:: python

    if latent_image.is_nested:
        # 记录各子张量的原始几何形状
        sampler_shapes = [tuple(x.shape) for x in latent_image.unbind()]
        # 将不规则张量沿通道或序列维度平铺压平为单一密集张量
        latent_image, latent_shapes = comfy.utils.pack_latents(latent_image.unbind())
        noise, _ = comfy.utils.pack_latents(noise.unbind())

在采样全流程中，数值求解器在紧凑的压平张量上高速运行；在每一步触发进度回调（``callback``）或最终输出时，再通过 ``unpack_latents()`` 恢复多视图结构，实现了**任意异构分辨率批处理的零显存浪费**。

------------------------------------------------------------------------

2. 多模态条件批处理引擎（``calc_cond_batch``）与空间张量融合
------------------------------------------------------------

在扩散模型前向计算中，正向提示词（Positive）、负向提示词（Negative）、区域提示词（Regional Conditions）以及各类特征遮罩往往具有不同的空间边界与生效区间。若逐个执行模型前向，计算吞吐将急剧下降。

ComfyUI 在 ``comfy/samplers.py`` 中实现了极其复杂的 **条件自适应批处理装箱算法（Adaptive Memory-Fit Batching）**。

2.1 条件对象结构与空间区域解析
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

每个参与采样的条件项均被解析为一个不可变具名元组 ``cond_obj``：

.. code-block:: python

    cond_obj = collections.namedtuple('cond_obj', [
        'input_x',       # 当前条件截取的局部潜空间切片 (Tensor)
        'mult',          # 空间融合权重矩阵 (Mask Tensor * Strength)
        'conditioning',  # 文本/视觉条件特征字典 (c_crossattn, etc.)
        'area',          # 空间几何边界 (H, W, Y, X)
        'control',       # 绑定的 ControlNet 链表
        'patches',       # 专有局部模型补丁
        'uuid',          # 唯一因果标识符
        'hooks'          # 绑定的条件 HookGroup
    ])

2.2 显存自适应批处理装箱算法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

系统根据当前 GPU 的实时空闲显存，动态探索最大可并发执行的条件批次数量（Batch Chunk Size）：

.. code-block:: python

    # 1. 过滤出与基准条件几何兼容 (can_concat_cond) 的候选集合
    to_batch_temp = [x for x in range(len(to_run)) if can_concat_cond(to_run[x][0], first[0])]
    to_batch = to_batch_temp[:1]

    # 2. 探测 GPU 物理空闲显存并执行安全系数评估
    free_memory = model.current_patcher.get_free_memory(x_in.device)
    for i in range(1, len(to_batch_temp) + 1):
        batch_amount = to_batch_temp[:len(to_batch_temp) // i]
        input_shape = [len(batch_amount) * first_shape[0]] + list(first_shape)[1:]

        # 预估前向激活值峰值显存 (乘以 1.5 倍安全水位线)
        if model.memory_required(input_shape, cond_shapes=cond_shapes) * 1.5 < free_memory:
            to_batch = batch_amount
            break

2.3 区域条件空间边缘羽化与加权归一化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当用户指定了局部区域提示词（例如在图像左侧 $[0, 0, 512, 256]$ 生成“猫”，右侧生成“狗”）时，硬边界拼接会导致交界处出现明显的接缝伪影。

ComfyUI 在 ``get_area_and_mult()`` 中实现了**自动边缘模糊羽化（Fuzzy Boundary Blending）**：

.. code-block:: python

    fuzz = 8
    for i in range(len(dims)):
        rr = min(fuzz, mult.shape[2 + i] // 4)
        # 对区域起始边缘施加线性渐变权重: t / rr
        if area[len(dims) + i] != 0:
            for t in range(rr):
                mult.narrow(i + 2, t, 1) *= ((1.0 / rr) * (t + 1))
        # 对区域终止边缘施加线性衰减权重
        if (area[i] + area[len(dims) + i]) < x_in.shape[i + 2]:
            for t in range(rr):
                mult.narrow(i + 2, area[i] - 1 - t, 1) *= ((1.0 / rr) * (t + 1))

在所有批次预测完成后，系统执行加权累加与归一化除法：

.. math::

   	ext{Denoised}_{	ext{final}} = \frac{\sum_{k} 	ext{Output}_k \odot M_k}{\sum_{k} M_k + \epsilon}

这一数学公式保证了无论局部区域如何重叠、交叉，全图的能量分布始终保持严格守恒。

------------------------------------------------------------------------

3. k-diffusion 数值积分器接口统一封装与 Inpainting 动力学
--------------------------------------------------------

ComfyUI 没有重复造轮子，而是通过面向对象适配器模式（Adapter Pattern）将 Katherine Crowson 的经典开源库 ``k-diffusion`` 全量接入自身框架。

3.1 统一求解器包装器（``KSAMPLER``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``comfy/samplers.py`` 中，``KSAMPLER`` 类封装了所有函数式求解器（如 ``sample_euler``, ``sample_dpmpp_2m``, ``sample_heun``）：

.. list-table:: ComfyUI 采样器类型与底层实现映射
   :widths: 20 25 25 30
   :header-rows: 1

   * - 采样器名称
     - 阶数与算法族
     - 物理步进特征
     - 适用生成模型
   * - ``euler`` / ``euler_ancestral``
     - 1 阶一阶前向欧拉 / 随机 SDE
     - 每步仅需 1 次模型前向评估（1 NFE/step）
     - 通用快速草图、SD 1.5/SDXL/Flux
   * - ``dpmpp_2m`` / ``dpmpp_2m_sde``
     - 2 阶多步预测校正（Multistep）
     - 利用前一步的历史导数信息，实现 2 阶精度而无需额外 NFE
     - 高画质精细生成、收敛极快（15-20 步）
   * - ``heun`` / ``dpm_2``
     - 2 阶显式龙格库塔（Runge-Kutta）
     - 每步包含 Predictor 与 Corrector 两次评估（2 NFE/step）
     - 追求极限几何保真度与物理对称性
   * - ``uni_pc`` / ``uni_pc_bh2``
     - 统一预测-校正器（UniPC）
     - 结合任意阶 Adams-Bashforth-Moulton 算法
     - 极低步数（5-10 步）极限加速

3.2 物理坐标变换与噪声缩放（Noise Scaling）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

扩散模型内部的张量数值并不直接等价于数学方程中的 :math:`x_t`。在进入数值积分循环前，系统必须将输入潜变量与随机噪声映射至指定采样范式的尺度空间：

1. **初始噪声缩放（``noise_scaling``）**：

   .. math::

      x_0 = 	ext{model\_sampling.noise\_scaling}(\sigma_{	ext{max}}, \epsilon, x_{	ext{latent}})

   * 对于标准 EDM 连续模型：:math:`x_0 = \epsilon \cdot \sqrt{\sigma_{	ext{max}}^2 + 1}`；
   * 对于 Flow Matching 连续流模型：:math:`x_0 = (1 - \sigma_{	ext{max}}) x_{	ext{latent}} + \sigma_{	ext{max}} \epsilon`。

2. **终止逆缩放（``inverse_noise_scaling``）**：
   在采样终止步（:math:`\sigma_{	ext{min}} 	o 0`），执行物理坐标反向映射，输出标准 VAE 潜空间幅值。

3.3 Inpainting 动力学约束（``KSamplerX0Inpaint``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在局部重绘（Inpainting）任务中，为了防止非重绘区域在数十步迭代中被累积数值噪声腐蚀，``KSamplerX0Inpaint`` 在求解器内部每一步前向计算后施加动力学硬投影：

.. code-block:: python

    class KSamplerX0Inpaint:
        def __call__(self, x, sigma, denoise_mask, model_options={}, seed=None):
            if denoise_mask is not None:
                latent_mask = 1.0 - denoise_mask
                # 将原始纯净图像按当前噪声尺度加噪后，原位替换非掩码区域
                x = x * denoise_mask + self.inner_model.scale_latent_inpaint(
                    x=x, sigma=sigma, noise=self.noise, latent_image=self.latent_image, denoise_mask=denoise_mask
                ) * latent_mask

            # 执行常规神经网络去噪预测
            out = self.inner_model(x, sigma, model_options=model_options, seed=seed)

            if denoise_mask is not None:
                # 强制将预测的 x0 结果在非掩码区域对齐为原始真实潜变量
                out = out * denoise_mask + self.latent_image * latent_mask
            return out

这种在带噪状态空间（:math:`x_t`）与去噪目标空间（:math:`x_0`）实施的双重投影约束，确保了重绘边缘与原始图像在频域与色彩空间上的完美缝合。

------------------------------------------------------------------------

4. 实时反馈总线与生成状态观测
------------------------------

在长时间的采样计算中，ComfyUI 通过闭包回调总线 ``k_callback`` 实现了毫秒级的前端交互响应：

.. code-block:: python

    def k_callback(x):
        # x 字典包含当前 step, 预测去噪结果 x["denoised"], 当前带噪状态 x["x"], 噪声尺度 x["sigma"]
        if callback is not None:
            callback(x["i"], x["denoised"], x["x"], total_steps)

1. **实时潜空间预览（Latent Preview）**：
   回调函数将每一步预测的 :math:`x_0`（``x["denoised"]``）传入 TAESD（Tiny AutoEncoder）极速解码器，通过 WebSocket 将 RGB 缩略图流式推送到前端画布；
2. **原子中断检测（Interrupt Handling）**：
   在回调执行期间，调度器检查 ``PromptExecutor`` 的全局中断标志位，一旦用户触发中止按钮，立即向 CUDA 流抛出异常并快速释放当前占据的计算显存。

------------------------------------------------------------------------

小结与下章导读
==============

本节系统剖析了 ComfyUI 的采样调度框架与数值积分体系：

1. **双层状态机**：解析了 ``KSampler`` 外观调度与 ``CFGGuider`` 嵌套潜变量打包、多卡派发与资源守卫机制；
2. **条件批处理引擎**：推导了基于空闲显存动态装箱的 ``calc_cond_batch`` 算法与空间边缘羽化加权融合公式；
3. **求解器统一封装**：阐明了 ``k-diffusion`` 算法族的高性能对象化适配与坐标空间缩放原理；
4. **Inpainting 动力学与观测总线**：拆解了双重空间硬投影约束与实时 WebSocket 预览流。

在下一节（``02_noise_schedules_and_sigmas.rst``）中，我们将深入采样计算的数学基石——**噪声时间表与 Sigmas 序列生成方程**：推导 Simple、Karras、Exponential、Beta、SGM Uniform 等多种离散/连续噪声时间表的微分几何背景与曲率对齐原理。
