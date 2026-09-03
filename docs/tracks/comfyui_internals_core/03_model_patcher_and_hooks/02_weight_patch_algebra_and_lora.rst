========================================================================
权重差分注入代数、LoRA/DoRA 矩阵在线融合与动态去补丁机制
========================================================================

.. note:: 前置背景与上下文承接
   在前一节（``01_model_patcher_core_architecture.rst``）中，我们确立了 ``ModelPatcher`` 的轻量代理外壳与浅拷贝克隆树架构，明确了多分支采样工作流如何在共享物理模型的前提下维护独立的修补声明列表。然而，当模型需要加载至 GPU 执行前向推理时，声明式的补丁列表必须转化为物理张量上的数值运算。面对来自 Kohya、Diffusers、OneTrainer、LyCORIS 等多种生态格式的 LoRA、DoRA、Locon、GLoRA 以及全量差分（Diff），ComfyUI 没有采用耗时且破坏原始权重的离线文件合并，而是构建了基于**矩阵差分注入代数（Weight Patch Algebra）**、**动态切片对齐（Narrow Slicing）**与**随机舍入（Stochastic Rounding）**的在线融合计算引擎。本节深入 ``comfy/lora.py``、``comfy/model_patcher.py`` 与 ``comfy/float.py``，系统拆解权重修补与无损复原的数学推导与代码实现。

------------------------------------------------------------------------

1. 权重差分代数数学模型与多格式参数分解
----------------------------------------

在生成式 AI 领域，对预训练基础模型 :math:`W_{	ext{base}} \in \mathbb{R}^{d_{	ext{out}} 	imes d_{	ext{in}}}` 进行下游微调的核心思想是学习一个参数增量矩阵 :math:`\Delta W`。

1.1 经典 LoRA 低秩分解代数
~~~~~~~~~~~~~~~~~~~~~~~~~~

标准 LoRA（Low-Rank Adaptation）假设权重更新具有极低的“内在秩”（Intrinsic Rank :math:`r \ll \min(d_{	ext{in}}, d_{	ext{out}})`），将增量矩阵分解为两个低秩矩阵的乘积：

.. math::

   \Delta W = \alpha_{	ext{patch}} \cdot \frac{\gamma}{r} \left( B \cdot A \right)

其中：

- :math:`A \in \mathbb{R}^{r 	imes d_{	ext{in}}}` 为下投影矩阵（Down-projection，通常初始化为高斯随机分布）。
- :math:`B \in \mathbb{R}^{d_{	ext{out}} 	imes r}` 为上投影矩阵（Up-projection，通常初始化为 0）。
- :math:`r` 为内在秩（Rank），:math:`\gamma` 为 LoRA Alpha 缩放常数，:math:`\alpha_{	ext{patch}}` 为用户在前端指定的注入强度系数（Strength）。

当模型存在基础缩放因子 :math:`\beta_{	ext{model}}` 时，注入后的目标权重为：

.. math::

   W_{	ext{patched}} = W_{	ext{base}} \cdot \beta_{	ext{model}} + \alpha_{	ext{patch}} \cdot \frac{\gamma}{r} \left( B \cdot A \right)

1.2 DoRA 幅度与方向解耦代数
~~~~~~~~~~~~~~~~~~~~~~~~~~~

DoRA（Weight-Decomposed Low-Rank Adaptation）进一步将权重矩阵分解为**幅度向量（Magnitude Vector :math:`m`）**与**方向矩阵（Direction Matrix :math:`V`）**，规避了标准 LoRA 在大幅度权重偏移时方向与尺度耦合的局限：

.. math::

   W_{	ext{base}} = m \odot \frac{V}{\|V\|_c} = \|W_{	ext{base}}\|_c \odot \frac{W_{	ext{base}}}{\|W_{	ext{base}}\|_c}

在注入 LoRA 增量 :math:`\Delta W = B \cdot A` 后，DoRA 通过可学习的幅度缩放系数 :math:`\Delta m` 进行动态归一化加权：

.. math::

   W_{	ext{dora}} = \left( \|W_{	ext{base}}\|_c + \alpha_{	ext{dora}} \cdot \Delta m \right) \odot \frac{W_{	ext{base}} + \alpha_{	ext{patch}} \cdot \Delta W}{\|W_{	ext{base}} + \alpha_{	ext{patch}} \cdot \Delta W\|_c}

其中 :math:`\|\cdot\|_c` 表示沿列方向（输出通道维度）计算的 Frobenius 范数。ComfyUI 在 ``comfy/lora.py`` 中通过专门的 ``weight_adapter.py`` 实现了对 DoRA 矩阵在线 L2 范数重缩放的高效支持。

1.3 多格式微调适配器分类
~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: ComfyUI 权重注入代数支持的微调模型类型对照
   :widths: 18 27 30 25
   :header-rows: 1

   * - 适配器类型
     - 物理存储形态
     - 数学计算公式
     - 典型应用场景
   * - **标准 LoRA**
     - ``(lora_down, lora_up, alpha)``
     - :math:`W + \alpha \frac{\gamma}{r} (B \cdot A)`
     - 角色概念微调、风格迁移
   * - **DoRA**
     - ``(lora_down, lora_up, dora_scale)``
     - :math:`(m + \Delta m) \odot \frac{W + \Delta W}{\|W + \Delta W\|}`
     - 高保真画风与精细结构微调
   * - **全量差分 (Diff)**
     - ``diff_weight``（全尺寸密集张量）
     - :math:`W + \alpha \cdot \Delta W_{	ext{dense}}`
     - 基础大模型微调插值、权重混合
   * - **动态模型萃取 (Model-as-LoRA)**
     - 两个完整 Checkpoint 的参数对
     - :math:`W_{	ext{base}} + \alpha \cdot (W_{	ext{target}} - W_{	ext{base}})`
     - 零预计算的模型在线实时差分融合

------------------------------------------------------------------------

2. ``calculate_weight`` 矩阵在线融合核心流水线
-----------------------------------------------

在 ``comfy/lora.py`` 中，核心函数 ``calculate_weight()`` 构成了整个补丁代数计算的心脏。它不仅支持单一补丁的计算，还能处理多补丁串联、通道切片（Slicing/Offset）以及张量形状动态对齐。

其内部数据流动管道如下图所示：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                                     Input: Base Weight Tensor W                                    |
   +----------------------------------------------------------------------------------------------------+
                                                     |
                                                     v
                                     [ 遍历 patches 补丁列表 p in patches ]
                                                     |
        +--------------------------------------------+--------------------------------------------+
        |                                                                                         |
        v                                                                                         v
   [ 存在 offset 切片? ]                                                                [ 模型强度缩放 ]
   weight = weight.narrow(dim, start, len)                                               weight = weight * strength_model
        |                                                                                         |
        +--------------------------------------------+--------------------------------------------+
                                                     |
                                                     v
                            [ 判断补丁载体类型 (Adapter / Diff / Set / Model-as-LoRA) ]
                                                     |
        +-----------------------+--------------------+-----------------------+--------------------+
        |                       |                                            |                    |
        v                       v                                            v                    v
   【WeightAdapterBase】    【"diff" 全量差分】                          【"set" 绝对覆盖】   【"model_as_lora"】
   执行 LoRA / DoRA       检查 pad_weight 动态扩展维度                     直接原位 copy_      动态计算:
   低秩矩阵乘法与范数缩放    weight = pad_tensor_to_shape(weight, target)   覆盖物理权重          diff = W_target - W_orig
   weight = v.calc(...)    weight += func(strength * diff)                                     weight += strength * diff
        |                       |                                            |                    |
        +-----------------------+--------------------+-----------------------+--------------------+
                                                     |
                                                     v
                                       [ 存在 offset 局部切片? ]
                             还原父级张量视图：weight = old_weight (已原位写入)
                                                     |
                                                     v
                                        [ 返回修补后的张量 W_patched ]

2.1 局部通道切片修补（Narrow Slicing & Offset）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 Flux.1、SD3 等先进 DiT 架构中，注意力机制的 Query、Key、Value 投影层常常被融合成单个宽矩阵（如 ``linear1_qkv.weight``，形状为 :math:`[3d_{	ext{hidden}}, d_{	ext{in}}]`）。如果外部 LoRA 仅针对其中的 Query 矩阵进行训练，传统做法需要重新拆分并拼接张量，带来巨大的显存拷贝开销。

ComfyUI 利用 PyTorch 的 ``Tensor.narrow()`` 原位切片机制：

.. code-block:: python

    old_weight = None
    if offset is not None:
        # offset 结构为 (dim, start, length)
        old_weight = weight
        weight = weight.narrow(offset[0], offset[1], offset[2])

由于 ``narrow()`` 返回的是底层连续 Storage 的共享内存视图（View），后续在子切片上的原位累加（In-place Accumulation）会直接反映到父张量中，计算完成后直接恢复 ``weight = old_weight``，实现了**零张量分配的局部融合**。

2.2 动态张量对齐与扩展（``pad_tensor_to_shape``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当微调模型对网络层的通道数进行了扩展（例如增加额外的控制通道或改变 Hidden Dimension），补丁矩阵的形状可能大于基础模型权重。

``comfy/lora.py`` 实现了维度自适应补零对齐：

.. code-block:: python

    def pad_tensor_to_shape(tensor: torch.Tensor, new_shape: list[int]) -> torch.Tensor:
        # 创建目标维度的零张量
        padded_tensor = torch.zeros(new_shape, dtype=tensor.dtype, device=tensor.device)
        # 构造跨维度连续切片元组
        orig_slices = tuple(slice(0, dim) for dim in tensor.shape)
        # 将原始基础权重精准复制到新张量的左上角区域
        padded_tensor[orig_slices] = tensor[orig_slices]
        return padded_tensor

------------------------------------------------------------------------

3. 精度截断漂移与随机舍入补偿机制（Stochastic Rounding）
---------------------------------------------------------

在显存极限优化的生产环境中，基础模型往往以低精度（FP8_E4M3、FP8_E5M2 或 NVFP4）存储在 Host 内存或显存中。然而，LoRA 矩阵在融合计算时必须在较高精度（FP32 或 BF16）下执行矩阵乘法，随后必须将结果重新量化回低精度。

3.1 确定性舍入（Round-to-Nearest）的系统性偏差
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

若采用常规的“四舍五入”或截断（Truncation），微小的增量信号 :math:`\Delta W_{ij}` 很容易落在量化网格的同一侧。在深层网络的成千上万次累加迭代中，微小的舍入误差会形成单向偏置（Systematic Bias），导致生成图像出现结构畸变或对比度塌陷：

.. math::

   \mathbb{E}[	ext{Round}(x)] 
eq x \quad (	ext{当 } x 	ext{ 不均匀分布时})

3.2 随机舍入数学原理与实现
~~~~~~~~~~~~~~~~~~~~~~~~~~

ComfyUI 在 ``comfy/float.py`` 中引入了**随机舍入（Stochastic Rounding）**算法。随机舍入将一个实数 :math:`x \in [x_k, x_{k+1}]` 按照其与相邻量化网格点的距离概率随机映射至两个端点：

.. math::

   P(	ilde{x} = x_{k+1}) = \frac{x - x_k}{x_{k+1} - x_k}, \quad P(	ilde{x} = x_k) = 1 - P(	ilde{x} = x_{k+1})

其数学期望严格等于原始实数值：

.. math::

   \mathbb{E}[	ilde{x}] = x_{k+1} \cdot \left(\frac{x - x_k}{x_{k+1} - x_k}\right) + x_k \cdot \left(1 - \frac{x - x_k}{x_{k+1} - x_k}\right) = x

在 ``comfy/float.py`` 中，系统结合尾数位缩放与伪随机数发生器实现了 FP8/FP4 的硬件级快速随机舍入：

.. code-block:: python

    def calc_mantissa(abs_x, exponent, normal_mask, MANTISSA_BITS, EXPONENT_BIAS, generator=None):
        # 1. 计算浮点数尾数缩放至整数空间的绝对位置
        mantissa_scaled = torch.where(
            normal_mask,
            (abs_x / (2.0 ** (exponent - EXPONENT_BIAS)) - 1.0) * (2**MANTISSA_BITS),
            (abs_x / (2.0 ** (-EXPONENT_BIAS + 1 - MANTISSA_BITS)))
        )
        # 2. 注入均匀随机噪声 U(0, 1) 实现概率触发
        mantissa_scaled += torch.rand(mantissa_scaled.size(), dtype=mantissa_scaled.dtype,
                                      device=mantissa_scaled.device, generator=generator)
        # 3. 向下取整并还原缩放
        return mantissa_scaled.floor() / (2**MANTISSA_BITS)

通过使用基于参数名哈希生成的确定性种子（``seed = string_to_seed(key)``），ComfyUI 既保证了单次计算的严格无偏性，又实现了跨次调度的**确定性复现（Deterministic Reproducibility）**。

------------------------------------------------------------------------

4. 动态去补丁与无损复原（Unpatching & In-place Restoration）
-------------------------------------------------------------

当多分支生成结束或切换不同 LoRA 组合时，模型必须从当前的修补状态无损还原至初始纯净态。

4.1 物理备份恢复机制（``unpatch_model``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在执行 ``patch_model()`` 之前，系统在 ``backup`` 字典中缓存了物理参数的原始状态镜像（``Dimension(weight, inplace_update)``）。

去补丁的物理执行流程如下：

.. code-block:: python

    def unpatch_model(self, device_to=None, unpatch_weights=True):
        self.eject_model()
        if unpatch_weights:
            self.unpatch_hooks()
            self.unpin_all_weights()

            # 清理 LowVRAM 分层修补函数链
            if self.model.model_lowvram:
                for m in self.model.modules():
                    move_weight_functions(m, device_to)
                    wipe_lowvram_weight(m)

            # 逐参数恢复物理张量
            keys = list(self.backup.keys())
            for k in keys:
                bk = self.backup[k]
                if bk.inplace_update:
                    # 原位拷贝，保持原有内存地址与指针不变
                    comfy.utils.copy_to_param(self.model, k, bk.weight)
                else:
                    # 重设 Parameter 属性
                    comfy.utils.set_attr_param(self.model, k, bk.weight)

            self.model.current_weight_patches_uuid = None
            self.backup.clear()

4.2 为什么禁止“减去 LoRA”的反向消除？
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

部分推理框架尝试通过数学反向消除：:math:`W_{	ext{base}} \approx W_{	ext{patched}} - \alpha \Delta W` 来恢复权重。

ComfyUI 严格禁止这种做法，原因在于：

1. **浮点累积误差**：在 FP16/BF16/FP8 低精度下，加法与减法不满足严格的结合律与可逆性，连续几十次叠加与扣除会导致原始模型权重发生不可逆的数值漂移（Weight Degradation）；
2. **非线性算子不可逆**：DoRA、量化权重融合与随机舍入均包含非线性投影，数学上不存在线性的精确逆运算。

通过维护只读原始镜像与 ``copy_to_param`` 原位覆盖，ComfyUI 确保了即使经过 10000 次不同 LoRA 的热切换，基础模型权重的每一个比特仍与磁盘文件保持 100% 绝对一致。

------------------------------------------------------------------------

5. 权重差分代数各阶段性能与精度对照表
--------------------------------------

.. list-table:: ComfyUI 权重修补计算各阶段技术特性
   :widths: 20 25 25 30
   :header-rows: 1

   * - 计算阶段
     - 执行时机
     - 物理资源消耗
     - 核心算法与保障机制
   * - **补丁解析与映射**
     - Checkpoint/Lora 加载节点
     - 极小 CPU 内存（仅字典映射）
     - 统一 Multi-Ecosystem 命名空间（Diffusers/Kohya/OneTrainer/LyCORIS 自动转换）
   * - **矩阵在线融合**
     - 模型载入目标设备（``load()``）
     - 瞬时计算显存/内存
     - GEMM 低秩矩阵乘法、``narrow`` 零拷贝切片、``pad_tensor_to_shape``
   * - **精度量化与舍入**
     - 参数写入物理 Module 前夕
     - 零额外显存（原位变换）
     - 概率密度无偏随机舍入（Stochastic Rounding），确定性哈希伪随机种子
   * - **模型去补丁复原**
     - 节点切换或工作流结束
     - 零计算开销（内存块搬移）
     - 基于 ``backup`` 镜像的原位 ``copy_to_param``，彻底杜绝浮点漂移

------------------------------------------------------------------------

小结与下章导读
==============

本节系统推导并剖析了 ComfyUI 权重差分注入代数与 LoRA 融合机制：

1. **数学代数建模**：推导了标准 LoRA 低秩分解与 DoRA 幅度方向解耦公式；
2. **在线融合流水线**：解析了 ``calculate_weight`` 在通道切片、张量对齐与动态模型差分中的高效实现；
3. **随机舍入精度保护**：论证了无偏随机舍入在低精度量化环境下的必要性与算法实现；
4. **无损物理复原**：阐明了基于备份镜像的确定性状态还原，规避了数值反向消除的漂移陷阱。

在下一节（``03_object_patches_and_forward_wrappers.rst``）中，我们将探讨动态修补体系的高阶控制——**模块级对象替换（Object Patches）与 Forward 计算图拦截**：剖析如何通过 Python 属性代理与装饰器链，无侵入式劫持模型的 Attention 算子、注入中间特征提取器以及构建多重执行 Hook 管道。
