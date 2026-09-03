========================================================================
模块级对象替换、Forward 计算图函数拦截与链式 Hook 调度体系
========================================================================

.. note:: 前置背景与上下文承接
   在前两节中，我们探讨了 ``ModelPatcher`` 的对象代理外壳（``01_model_patcher_core_architecture.rst``）以及静态/准静态权重矩阵的在线差分注入（``02_weight_patch_algebra_and_lora.rst``）。然而，现代生成式 AI 的高级控制能力远不止修改静态权重——例如 ControlNet 需要在上采样/下采样块间注入额外的残差特征、IP-Adapter 需要在 Cross-Attention 算子前后劫持 Key/Value 投影、AnimateDiff 需要在空间层之间无缝穿插时间注意力层（Temporal Attention），而各种采样调度优化器更需要在 Denoise 前向传播的最外层包裹多重闭包。如果直接侵入式修改 PyTorch 骨干网络（如 UNet / DiT）的 Python 源码，将彻底破坏框架的模块化与多节点复用能力。ComfyUI 通过**模块级对象替换（``object_patches``）**、**洋葱圈式 Forward 函数包装器（``WrapperExecutor``）**与**时间步关键帧 Hook 调度系统（``comfy.hooks``）**，构建了一套高内聚、零侵入、确定性可逆的计算图动态拦截体系。本节系统拆解这一核心机制。

------------------------------------------------------------------------

1. 模块级对象替换机制（``object_patches``）
-------------------------------------------

在 PyTorch 模型中，除权重参数（Parameter）外，网络各层还包含大量的子模块实体（如 ``torch.nn.Conv2d``、``torch.nn.MultiheadAttention``）以及控制属性（如 ``manual_cast_dtype``）。

1.1 属性路径动态解析与劫持
~~~~~~~~~~~~~~~~~~~~~~~~~~

ComfyUI 允许节点通过声明式的“点分路径语法（Dot-notation Path）”向 ``ModelPatcher`` 注册对象替换：

.. code-block:: python

    # 将 UNet 中间的特定 Attention 算子替换为自定义优化算子
    model_patcher.add_object_patch("diffusion_model.middle_block.1.transformer_blocks.0.attn1", custom_attention_module)

    # 动态覆盖全网计算精度
    model_patcher.set_model_compute_dtype(torch.bfloat16)

在底层执行时，``comfy.utils.resolve_attr`` 与 ``set_attr`` 递归遍历 Python 对象的属性树：

.. code-block:: python

    def resolve_attr(obj, attr):
        attributes = attr.split('.')
        for a in attributes[:-1]:
            obj = getattr(obj, a)
        return obj, attributes[-1]

    def set_attr(obj, attr, val):
        parent, last_attr = resolve_attr(obj, attr)
        old_val = getattr(parent, last_attr, None)
        setattr(parent, last_attr, val)
        return old_val

1.2 对象替换的无损复原状态机
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了确保在模型卸载或切换分支时能够彻底恢复原始属性，``ModelPatcher`` 建立了只读镜像栈 ``object_patches_backup``：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                                    Object Patching Lifecycle                                       |
   +----------------------------------------------------------------------------------------------------+
   |   1. 注册期 (Registration):                                                                        |
   |        patcher.object_patches["diffusion_model.middle_block.1"] = CustomBlock()                     |
   |                                                                                                    |
   |   2. 挂载期 (patch_model()):                                                                        |
   |        for k, v in patcher.object_patches.items():                                                 |
   |            old_module = set_attr(patcher.model, k, v)                                              |
   |            patcher.object_patches_backup[k] = old_module                                           |
   |                                                                                                    |
   |   3. 活跃前向期 (Patched Execution):                                                                |
   |        底层 PyTorch 模型执行 CustomBlock 的前向计算逻辑                                            |
   |                                                                                                    |
   |   4. 还原期 (unpatch_model()):                                                                      |
   |        for k, old_module in patcher.object_patches_backup.items():                                 |
   |            set_attr(patcher.model, k, old_module)                                                 |
   |        patcher.object_patches_backup.clear()                                                       |
   +----------------------------------------------------------------------------------------------------+

------------------------------------------------------------------------

2. 洋葱圈式 Forward 计算图包装器（``WrapperExecutor``）
-------------------------------------------------------

当多个独立的插件节点（例如：节点 A 注入采样步数计时器、节点 B 注入潜空间动态阈值裁剪、节点 C 注入 ControlNet 引导）需要同时作用于扩散模型的 ``apply_model`` 前向函数时，简单的单层函数替换会产生覆盖冲突。

ComfyUI 在 ``comfy/patcher_extension.py`` 中实现了一套类似 Web 中间件的**洋葱圈递归调用栈（Onion Architecture Pipeline）**。

2.1 拦截切面分级（``WrappersMP``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

ComfyUI 规范化了扩散模型采样流水线中的标准拦截点：

.. list-table:: ComfyUI 标准 Forward 拦截切面
   :widths: 25 35 40
   :header-rows: 1

   * - 包装切面常量 (WrappersMP)
     - 拦截目标函数
     - 典型应用场景
   * - ``OUTER_SAMPLE``
     - KSampler 最外层主循环
     - 跨步调度重置、全局显存监控、生成进度条包装
   * - ``PREPARE_SAMPLING``
     - 噪声与条件张量预处理阶段
     - 动态噪声注入、潜空间初始分布重构
   * - ``SAMPLER_SAMPLE``
     - 求解器单步积分迭代器
     - 自定义 ODE/SDE 单步收敛修正、动量加速
   * - ``CALC_COND_BATCH``
     - 正负向条件批处理组合计算
     - 无分类器引导（CFG）动态缩放、负向提示词对抗
   * - ``APPLY_MODEL``
     - 扩散模型骨干网络 ``apply_model``
     - ControlNet 残差累加、模型多分支特征融合
   * - ``DIFFUSION_MODEL``
     - 底层 UNet / DiT 核心前向
     - 块级特征提取、跨层跳跃连接（Skip-Connection）劫持

2.2 ``WrapperExecutor`` 递归执行模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``WrapperExecutor`` 通过索引指针 ``idx`` 在不可变包装器列表上构造轻量执行闭包：

.. code-block:: python

    class WrapperExecutor:
        def __init__(self, original: Callable, class_obj: object, wrappers: list[Callable], idx: int):
            self.original = original
            self.class_obj = class_obj
            self.wrappers = wrappers.copy()
            self.idx = idx
            self.is_last = idx == len(wrappers)

        def __call__(self, *args, **kwargs):
            # 步进至下一层包装器或底层原函数
            new_executor = self._create_next_executor()
            return new_executor.execute(*args, **kwargs)

        def execute(self, *args, **kwargs):
            if self.is_last:
                # 递归基：执行原始 PyTorch 模型函数
                return self.original(*args, **kwargs)
            # 执行当前包装器，并将当前 executor 传递给用户函数，供其决定何时调用下一层
            return self.wrappers[self.idx](self, *args, **kwargs)

其调用链路与控制流如下图所示：

.. code-block:: text

   Caller (KSampler)
      |
      v
   Wrapper 0 (e.g. Logging / Profiler) ──[ 前置预处理 ]──>
      |
      v executor(...)
   Wrapper 1 (e.g. Dynamic CFG Rescale) ──[ 修改输入参数 ]──>
      |
      v executor(...)
   Wrapper 2 (e.g. ControlNet Residual Injector) ──[ 注入外部引导 ]──>
      |
      v executor(...)
   Original apply_model() ──[ 底层 PyTorch 骨干计算 ]
      |
      +<──[ 返回原始预测噪声 ]
      |
   Wrapper 2 ──[ 后置处理 / 残差融合 ]──>
      |
      +<──[ 返回调整后张量 ]
      |
   Wrapper 1 ──[ 动态阈值裁剪 ]──>
      |
      +<──[ 返回最终噪声 ]
      |
   Wrapper 0 ──[ 记录耗时与显存 ]──>
      |
      v
   返回最终输出给 KSampler

------------------------------------------------------------------------

3. 链式 Hook 调度系统（``comfy.hooks``）
-----------------------------------------

传统的模型修补通常在全采样生命周期内保持静态生效。然而在高级控制场景中，用户往往要求：

- **条件绑定作用域（Conditioning-Scoped Hooks）**：某个 LoRA 只对“正向提示词”生效，不对“负向提示词”生效；或者只在图像特定遮罩区域（Mask）生效；
- **时间步调度关键帧（Keyframed Timestep Scheduling）**：某个概念微调只在扩散过程的前 20% 步骤（高频轮廓生成期）生效，后 80% 步骤自动剥离。

为了解决这一问题，ComfyUI 在 ``comfy/hooks.py`` 中抽象出了完整的 **Hook 体系**。

3.1 Hook 类型与作用域分类
~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: ComfyUI Hook 核心枚举定义
   :widths: 22 28 50
   :header-rows: 1

   * - 枚举分类
     - 枚举项
     - 物理行为与调度语义
   * - **``EnumHookType``**
     - ``Weight``
     - 动态追踪权重补丁，在前向计算前按需实时合入物理模型。
   * -
     - ``ObjectPatch``
     - 挂载条件触发的对象属性替换。
   * -
     - ``AdditionalModels``
     - 触发关联辅助模型（如 IP-Adapter ClipVision 模型）的同步换入。
   * -
     - ``TransformerOptions``
     - 动态注入特定时间步的 Attention 替换逻辑与局部参数。
   * - **``EnumHookScope``**
     - ``AllConditioning``
     - 全局生效：无论当前批次计算哪个 Conditioning，Hook 均处于激活状态。
   * -
     - ``HookedOnly``
     - 局部生效：仅当当前采样 Batch 包含显式绑定了该 Hook 的 Conditioning 时才激活。
   * - **``EnumHookMode``**
     - ``MinVram``
     - 极致显存优先：切换 Hook 时不缓存修补权重，即时计算即时释放。
   * -
     - ``MaxSpeed``
     - 极致速度优先：利用富余显存/内存建立已修补权重缓存（``cached_hook_patches``）。

3.2 时间步关键帧调度（``HookKeyframeGroup``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

每一个 Hook 对象均内嵌一个关键帧调度组 ``HookKeyframeGroup``。系统将用户指定的时间步百分比（``start_percent``）转化为扩散模型的物理噪声尺度（:math:`\sigma` / Timestep）：

.. math::

   \sigma_{	ext{start}} = 	ext{percent\_to\_sigma}(	ext{start\_percent})

在采样主循环的每一步 :math:`t`（即当前噪声尺度 :math:`\sigma_{	ext{curr}}`），调度器调用 ``prepare_current_keyframe`` 进行状态更新：

.. code-block:: python

    def prepare_current_keyframe(self, curr_t: float, transformer_options: dict) -> bool:
        if self.is_empty() or curr_t == self._curr_t:
            return False

        max_sigma = torch.max(transformer_options["sample_sigmas"])
        prev_strength = self._current_strength

        # 检查是否满足最小步数保证（guarantee_steps）
        if self._current_used_steps >= self._current_keyframe.get_effective_guarantee_steps(max_sigma):
            for i in range(self._current_index + 1, len(self.keyframes)):
                eval_c = self.keyframes[i]
                # 扩散采样按 sigma 从大到小递减，故 start_t >= curr_t 判定已进入该关键帧区间
                if eval_c.start_t >= curr_t:
                    self._current_index = i
                    self._current_strength = eval_c.strength
                    self._current_keyframe = eval_c
                    self._current_used_steps = 0
                    if self._current_keyframe.get_effective_guarantee_steps(max_sigma) > 0:
                        break
                else:
                    break

        self._current_used_steps += 1
        self._curr_t = curr_t
        # 若强度发生跃迁，触发模型权重重新计算
        return prev_strength != self._current_strength

3.3 条件挂载与多重合并代数（``set_conds_props``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Hook 与特定 Conditioning 绑定的底层物理实现是将 ``HookGroup`` 封装进 Conditioning 字典的高阶元组结构：

.. code-block:: python

    # 将 Hook 关联至正向提示词 Conditioning
    conditioning = [
        [
            text_embeddings,
            {
                "hooks": hook_group,
                "mask": mask_tensor,
                "start_percent": 0.0,
                "end_percent": 0.6
            }
        ]
    ]

当多个节点对同一组 Conditioning 施加不同的 Hook 时，系统通过 ``HookGroup.clone_and_combine()`` 进行无损集合并集操作，并基于内存指纹缓存（``cache: dict[tuple[HookGroup, HookGroup], HookGroup]``）杜绝递归引用导致的内存泄漏。

------------------------------------------------------------------------

4. 生命周期回调与外部扩展注入（``CallbacksMP`` & ``PatcherInjection``）
------------------------------------------------------------------------

为了支持极端复杂的第三方插件生态，ComfyUI 在 ``ModelPatcher`` 的各个生命周期关键节点部署了声明式回调总线（``CallbacksMP``）：

.. list-table:: ModelPatcher 生命周期事件与回调广播机制
   :widths: 25 35 40
   :header-rows: 1

   * - 生命周期事件 (CallbacksMP)
     - 触发时机
     - 典型插件扩展行为
   * - ``ON_CLONE``
     - 执行 ``ModelPatcher.clone()`` 时
     - 同步克隆插件私有状态、复制局部缓存
   * - ``ON_LOAD``
     - 模型载入 GPU（``load()``）完成后
     - 分配插件专用的 CUDA 辅助流、初始化显存监控
   * - ``ON_PREPARE_STATE``
     - 采样器每步前向准备期
     - 同步 Multi-GPU 节点间的分布式张量状态
   * - ``ON_APPLY_HOOKS``
     - 切换并应用新的 ``HookGroup`` 时
     - 动态重构 ``transformer_options`` 扩展字典
   * - ``ON_INJECT_MODEL``
     - 激活 ``PatcherInjection`` 拦截器时
     - 执行底层 PyTorch 算子的深度 Hook 挂载
   * - ``ON_EJECT_MODEL``
     - 退出 ``AutoPatcherEjector`` 保护区时
     - 临时剥离拦截层，暴露裸模型供权重安全操作

------------------------------------------------------------------------

小结与下章导读
==============

本节系统剖析了 ComfyUI 动态修补体系的高阶计算图拦截机制：

1. **对象替换**：基于 ``object_patches`` 与路径动态解析实现了算子与属性的无损热插拔；
2. **洋葱圈包装器**：通过 ``WrapperExecutor`` 构建了支持任意多插件并存的递归 Forward 拦截调用链；
3. **链式 Hook 体系**：推导了基于时间步关键帧（``HookKeyframeGroup``）与条件作用域（``HookScope``）的精细化动态调度模型；
4. **扩展总线**：阐明了 ``CallbacksMP`` 与 ``PatcherInjection`` 如何为复杂下游任务提供标准化生命周期钩子。

在下一节（``04_model_options_and_transformer_options.rst``）中，我们将迎来第 3 模块的完结篇——**``transformer_options`` 运行时上下文注入与跨节点状态传递**：深入剖析在 UNet 与 DiT 跨层前向传播过程中，Attention 矩阵劫持、跨注意力键值注入（Cross-Attention KV Injection）与自注意力引导（SAG）的底层物理实现。
