========================================================================
transformer_options 运行时上下文注入机制、注意力机制劫持与跨节点状态传递
========================================================================

.. note:: 前置背景与上下文承接
   在前三节中，我们建立了 ``ModelPatcher`` 的对象代理外壳（``01_model_patcher_core_architecture.rst``）、权重差分注入代数（``02_weight_patch_algebra_and_lora.rst``）以及模块级对象替换与洋葱圈函数包装（``03_object_patches_and_forward_wrappers.rst``）。然而，在扩散模型（UNet 与 DiT）密集的去噪前向传播过程中，仍有大量极其精细的控制逻辑需要在数百个深层网络块之间动态传递——例如 IP-Adapter 的跨注意力图像特征注入、自注意力引导（SAG）的 Attention Map 提取、区域提示词（Regional Prompting）的空间遮罩广播，以及各种针对特定时间步的自适应注意力核切换。若通过修改网络层的形参接口来传递这些参数，将导致模型结构极其臃肿且无法兼容不同架构。ComfyUI 通过设计统一的字典级通信协议——**``transformer_options`` 运行时上下文注入体系**，实现了跨层状态广播、注意力机制劫持与节点间隐式数据流的高效协同。本节深入剖析这一机制的内部机理与工程实现。

------------------------------------------------------------------------

1. 运行时通信协议：``model_options`` 与 ``transformer_options`` 架构
--------------------------------------------------------------------

在 ComfyUI 的推理管线中，状态传递遵循两级字典协议：

1. **全局模型级选项（``model_options``）**：绑定于 ``ModelPatcher`` 实例或由采样器节点下发，控制采样器行为、CFG 计算函数以及预处理/后处理钩子；
2. **前向层级上下文（``transformer_options``）**：作为 ``model_options["transformer_options"]`` 的子集，随输入潜变量（Latent）和时间步（Timestep）一同渗透进扩散模型的每一个 Block 内部。

其协议结构与字段映射如下图所示：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                                    model_options 全局调度字典                                      |
   |                                                                                                    |
   |   - sampler_cfg_function: Callable (自定义 CFG 求解函数)                                           |
   |   - sampler_pre_cfg_function / sampler_post_cfg_function: List[Callable] (采样前后潜空间校准)       |
   |   - sampler_calc_cond_batch_function: Callable (条件批处理自适应拆分函数)                          |
   |   - disable_cfg1_optimization: bool (是否禁用 CFG=1 时的单分支跳过优化)                           |
   |   - model_function_wrapper: UnetWrapperFunction (骨干网络最外层包装闭包)                            |
   |                                                                                                    |
   |   +--------------------------------------------------------------------------------------------+   |
   |   |                           transformer_options 跨层前向传播上下文                           |   |
   |   |                                                                                            |   |
   |   |   【全局采样状态 (Global Context)】                                                         |   |
   |   |   - current_step: int (当前迭代步数序号 0..N)                                              |   |
   |   |   - sigmas: torch.Tensor (当前采样的全流程噪声时间表)                                       |   |
   |   |   - cond_or_uncond: List[int] (当前批次张量对应的正负条件索引 [0, 1])                      |   |
   |   |                                                                                            |   |
   |   |   【空间与动态几何 (Spatial & Dynamic Geometry)】                                           |   |
   |   |   - original_shape: Tuple[B, C, H, W] (潜空间原始未切块分辨率)                              |   |
   |   |   - rope_options: dict (针对 DiT 架构 RoPE 旋转位置编码的 scale/shift 参数)                |   |
   |   |                                                                                            |   |
   |   |   【注意力劫持与补丁 (Attention Hijacks & Patches)】                                        |   |
   |   |   - patches: Dict[str, List[Callable]] ("attn1_patch", "attn2_patch", "input_block_patch")|   |
   |   |   - patches_replace: Dict[str, Dict[Tuple, Callable]] (按 (block, number) 坐标精确定向替换) |   |
   |   |   - optimized_attention_override: Callable (硬件注意力内核全局覆盖)                         |   |
   |   |                                                                                            |   |
   |   |   【运行时网络坐标 (Dynamic Block Coordinate - 由模型层在遍历时动态填充)】                  |   |
   |   |   - block: Tuple[str, int] (当前网络块坐标，如 ("input", 4) 或 ("double_block", 12))        |   |
   |   |   - block_index: int (当前子模块在父列表中的绝对序号)                                      |   |
   |   |   - transformer_index: int (在多流 DiT 结构中的内部注意力块索引)                           |   |
   |   +--------------------------------------------------------------------------------------------+   |
   +----------------------------------------------------------------------------------------------------+

1.1 核心字典操作与不可变性隔离
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了防止深层网络前向计算时对全局上下文造成脏数据污染，``transformer_options`` 在跨层传递时采用**分层浅拷贝隔离模式**：

.. code-block:: python

    # 在网络主干遍历各层时，动态派生当前层的上下文快照
    transformer_options_layer = transformer_options.copy()
    transformer_options_layer["block"] = ("input", block_idx)
    transformer_options_layer["block_index"] = block_idx

    # 调用子模块前向计算，传入专有坐标上下文
    out = sub_module(x, context, transformer_options=transformer_options_layer)

这种机制保证了上游节点注入的修补函数可以精准读取自身所处的网络层深度，同时杜绝了跨线程、跨分支计算的状态冲突。

------------------------------------------------------------------------

2. 注意力机制劫持（Attention Hijacking）物理实现
-------------------------------------------------

在扩散模型与 DiT 架构中，注意力机制（Self-Attention 与 Cross-Attention）是决定生成语义、空间结构与图像保真度的核心枢纽。ComfyUI 通过 ``transformer_options`` 提供了多粒度的注意力计算劫持通道。

2.1 自注意力劫持（``attn1_patch``）与自注意力引导（SAG）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

自注意力（Self-Attention, ``attn1``）负责捕捉潜空间内部像素/Patch 之间的空间上下文相关性：

.. math::

   Q = X W_Q, \quad K = X W_K, \quad V = X W_V

   A = 	ext{Softmax}\left(\frac{Q K^T}{\sqrt{d_k}}\right), \quad 	ext{Out} = A \cdot V

当注册了 ``attn1_patch`` 时，ComfyUI 允许自定义函数接管 Attention 矩阵的生成或对中间特征实施扰动。

**自注意力引导（Self-Attention Guidance, SAG）物理实现示例**：

.. code-block:: python

    def sag_attn1_patch(q, k, v, extra_options):
        # 1. 计算原始自注意力权重图
        sim = torch.einsum('b i d, b j d -> b i j', q, k) * (1.0 / math.sqrt(q.shape[-1]))
        attn_map = sim.softmax(dim=-1)

        # 2. 提取注意力热力极值区域（即模型当前最关注的图像主体）
        if extra_options.get("current_step", 0) < extra_options.get("sag_threshold_step", 15):
            # 对高热力注意力区域施加高斯模糊，构造对抗性扰动潜变量
            blurred_v = apply_gaussian_blur(v, attn_map)
            out = torch.einsum('b i j, b j d -> b i d', attn_map, blurred_v)
            return out

        return torch.einsum('b i j, b j d -> b i d', attn_map, v)

2.2 交叉注意力劫持（``attn2_patch``）与 IP-Adapter 多模态注入
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

交叉注意力（Cross-Attention, ``attn2``）负责将外部文本或图像条件特征（:math:`C`）投影至生成特征空间：

.. math::

   Q = X W_Q, \quad K_{	ext{text}} = C_{	ext{text}} W_K, \quad V_{	ext{text}} = C_{	ext{text}} W_V

IP-Adapter（Image Prompt Adapter）通过解耦交叉注意力，在文本条件之外额外挂载独立的图像交叉注意力分支。ComfyUI 利用 ``attn2_patch`` 实现了无缝的双分支在线合并：

.. math::

   	ext{Out}_{	ext{combined}} = 	ext{Softmax}\left(\frac{Q K_{	ext{text}}^T}{\sqrt{d_k}}\right) V_{	ext{text}} + \lambda_{	ext{ip}} \cdot 	ext{Softmax}\left(\frac{Q K_{	ext{img}}^T}{\sqrt{d_k}}\right) V_{	ext{img}}

.. code-block:: python

    def ip_adapter_attn2_patch(q, k, v, extra_options):
        # 计算文本分支的标准 Cross-Attention 输出
        text_out = standard_attention(q, k, v)

        # 从 transformer_options 中提取 IP-Adapter 专有的图像条件与权重投影
        ip_k = extra_options["ip_adapter_k"]
        ip_v = extra_options["ip_adapter_v"]
        scale = extra_options.get("ip_adapter_scale", 1.0)

        # 计算图像分支 Cross-Attention 并加权融入
        image_out = standard_attention(q, ip_k, ip_v)
        return text_out + scale * image_out

2.3 定向坐标替换（``patches_replace``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当插件开发者仅希望修改特定某一个 Block（例如仅劫持 SDXL UNet 的 ``middle_block.1`` 中的第 0 个 Transformer）时，使用全局广播的 ``attn1_patch`` 会带来无谓的条件分支判断开销。

``patches_replace`` 支持基于精准坐标元组的常量级查找：

.. code-block:: python

    # 精确注册至 UNet 的 middle_block, index=1
    patcher.set_model_patch_replace(
        patch=custom_block_fn,
        name="attn1",
        block_name="middle",
        number=1,
        transformer_index=0
    )

在前向传播经过目标层时，网络直接通过哈希表命中：

.. code-block:: python

    target_block_key = (block_name, block_number, transformer_index)
    if target_block_key in transformer_options.get("patches_replace", {}).get("attn1", {}):
        custom_fn = transformer_options["patches_replace"]["attn1"][target_block_key]
        return custom_fn(q, k, v, extra_options=transformer_options)

------------------------------------------------------------------------

3. 采样器调度控制闭环与潜空间校准
----------------------------------

除网络内部的注意力劫持外，``model_options`` 还直接接管了 KSampler 采样循环中的核心数学运算。

3.1 无分类器引导重写（``sampler_cfg_function``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

标准无分类器引导（Classifier-Free Guidance, CFG）方程为：

.. math::

   \epsilon_{	ext{pred}} = \epsilon_{	ext{uncond}} + s \cdot (\epsilon_{	ext{cond}} - \epsilon_{	ext{uncond}})

在复杂生成场景中，固定比例 :math:`s` 容易在采样后期导致色彩过饱和或潜空间数值爆炸（Latent Explosion）。通过 ``sampler_cfg_function``，节点可以动态注入先进的 CFG 约束算法（如 Rescale CFG、动态阈值裁剪 Dynamic Thresholding）：

.. code-block:: python

    def rescale_cfg_function(args):
        cond = args["cond"]
        uncond = args["uncond"]
        cond_scale = args["cond_scale"]
        rescale_phi = 0.7  # 潜空间方差校准因子

        # 计算基础引导预测
        cfg_result = uncond + cond_scale * (cond - uncond)

        # 计算条件与引导结果的标准差
        std_cond = cond.std(dim=(-3, -2, -1), keepdim=True)
        std_cfg = cfg_result.std(dim=(-3, -2, -1), keepdim=True)

        # 执行标准差重缩放融合
        rescaled = cfg_result * (std_cond / std_cfg)
        return rescale_phi * rescaled + (1.0 - rescale_phi) * cfg_result

    # 注册至 ModelPatcher
    model_patcher.set_model_sampler_cfg_function(rescale_cfg_function)

3.2 批处理算力优化（``disable_cfg1_optimization``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当用户设置 ``cfg_scale = 1.0`` 时，数学上 :math:`\epsilon_{	ext{pred}} = \epsilon_{	ext{cond}}`，ComfyUI 默认会跳过负向提示词（Uncond）的整个前向传播，从而节省 50% 的计算时间。

然而，若节点注册了依赖正负分支差异的后处理函数（如负向特征对抗 Hook），跳过 Uncond 会导致插件逻辑崩溃。通过标记 ``disable_cfg1_optimization = True``，``ModelPatcher`` 会强制采样器维持双分支完整批处理，确保高级 Hook 的确定性执行。

------------------------------------------------------------------------

4. 第 3 模块技术全景综合对照表
------------------------------

作为第 3 模块《动态权重修补与 LoRA/Hook 注入体系》的收官总结，下表系统梳理了各核心组件的架构定位与协作关系：

.. list-table:: ComfyUI 动态修补与注入体系技术全景
   :widths: 20 25 25 30
   :header-rows: 1

   * - 核心架构组件
     - 物理截获层级
     - 核心通信与数据结构
     - 系统架构贡献
   * - **ModelPatcher 代理**
     - 对象外壳层
     - 浅拷贝克隆树 / ``patches_uuid``
     - 建立多分支零内存开销共享机制，维护模型加载与还原生命周期。
   * - **权重差分代数**
     - 物理参数层
     - 5 元组补丁表 / ``calculate_weight``
     - 在线融合 LoRA/DoRA/Diff，结合无偏随机舍入杜绝浮点漂移。
   * - **模块对象替换**
     - 网络结构属性层
     - ``object_patches`` / 点分路径解析
     - 支持无侵入式硬件注意力内核与算子热插拔，提供只读镜像无损复原。
   * - **洋葱圈 Forward 包装**
     - 计算图调用栈
     - ``WrapperExecutor`` / ``WrappersMP``
     - 规范 7 大标准切面，解决多第三方插件在采样主循环中的串联冲突。
   * - **链式 Hook 调度**
     - 时间步与条件层
     - ``HookGroup`` / ``HookKeyframeGroup``
     - 实现基于噪声尺度 :math:`\sigma` 的关键帧强度调度与局部条件作用域绑定。
   * - **transformer_options**
     - 跨层前向上下文
     - 动态只读子字典 / 网络坐标元组
     - 支撑 IP-Adapter、SAG、区域提示词等前沿控制算法在深层网络中的特征注入。

------------------------------------------------------------------------

小结与下章导读
==============

本节系统剖析了 ComfyUI 在深层网络前向传播过程中的上下文广播与注意力劫持机制：

1. **协议解耦**：确立了 ``model_options`` 全局调度与 ``transformer_options`` 跨层分发的分级通信标准；
2. **多粒度注意力劫持**：剖析了 ``attn1_patch``（Self-Attn）、``attn2_patch``（Cross-Attn）与 ``patches_replace`` 坐标精确替换的底层计算闭环；
3. **采样控制闭环**：推导了自定义 CFG 求解与潜空间动态阈值校准的实现原理；
4. **全景体系收官**：完整梳理了第 3 模块构建的“代理-代数-拦截-上下文”四位一体动态修补中枢。

至此，**第 3 模块《动态权重修补与 LoRA/Hook 注入体系》全 4 节已圆满结稿**。

在接下来的 **第 4 模块《扩散模型基类与 DiT 架构抽象》（04_model_base_and_architectures）** 中，我们将深入生成式 AI 的神经网络物理骨架——从经典的 SD 1.5/SDXL UNet 拓扑（ResBlock、Spatial Transformer、跨时间步注入），跨越至现代多模态双流 DiT（MMDiT / Flux.1 / SD3）以及 ControlNet 残差引导的底层物理抽象。
