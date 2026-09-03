========================================================================
ModelPatcher 对象模型架构、底层 PyTorch 模型代理封装与浅拷贝克隆树机制
========================================================================

.. note:: 前置背景与上下文承接
   在第 2 模块《动态显存管理与模型卸载机制》中，我们完整剖析了 ComfyUI 如何在异构硬件设备上度量显存水压、执行 LRU 驱逐、流式换入换出以及应对运行时 OOM 异常。然而，在现代生成式 AI 的实际生产流水线中，纯净的基础模型（Base Checkpoint）极少单独执行推理——它往往需要动态挂载多个 LoRA/DoRA 权重微调、注入 ControlNet 残差分支、动态重载 Attention 优化核（如 FlashAttention/xFormers/SageAttention），或者在不同采样分支中应用差异化的正负向提示词加权。若为每一个微调分支都复制一份完整的十亿级参数 PyTorch 模型，系统内存与显存将瞬间耗尽。ComfyUI 的灵魂级设计——``ModelPatcher``，通过**轻量级对象模型代理封装**、**浅拷贝克隆树（Shallow Cloning Tree）**与**声明式补丁注册表**，以零额外内存开销实现了模型的多分支动态修补。本节深入 ``comfy/model_patcher.py``，系统拆解其核心架构与生命周期。

------------------------------------------------------------------------

1. ModelPatcher 的定位与轻量代理封装
------------------------------------

在传统的 PyTorch 工作流中，模型对象通常是继承自 ``torch.nn.Module`` 的单一实体。一旦修改了其中的 ``Parameter`` 权重或替换了子模块，这种修改是破坏性且不可逆的（In-place Mutation）。

ComfyUI 将计算图中的模型概念解耦为两层：

1. **物理模型（Physical Model）**：底层的 ``torch.nn.Module``（如 ``DiffusionModel``、``CLIP``、``AutoencoderKL``），持有数十亿参数的真实物理 Storage。
2. **代理修补器（ModelPatcher Proxy）**：包装物理模型的管理外壳，负责拦截参数读取、记录补丁变动、管理加载目标设备，并维护补丁的注入与还原。

其对象结构拓扑如下图所示：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                                      ModelPatcher Proxy Instance                                   |
   |                                                                                                    |
   |   - model: torch.nn.Module (共享物理权重，如 SDXL UNet / Flux Transformer)                          |
   |   - load_device: torch.device ("cuda:0") / offload_device: torch.device ("cpu")                     |
   |   - size: int (物理模型计算字节体积)                                                               |
   |   - patches_uuid: UUID (当前补丁组合的全局唯一因果指纹)                                             |
   |                                                                                                    |
   |   +------------------------------------+   +---------------------------------------------------+   |
   |   | 补丁声明注册表 (Declarative Patches)|   | 状态备份还原容器 (State Backups)                   |   |
   |   | - patches: Dict[str, List[Tuple]]  |   | - backup: Dict[str, Dimension(weight, inplace)]   |   |
   |   | - object_patches: Dict[str, Any]   |   | - object_patches_backup: Dict[str, Any]           |   |
   |   | - weight_wrapper_patches: Dict     |   | - backup_buffers: Dict[str, torch.Tensor]         |   |
   |   | - hook_patches: Dict[HookRef, ...] |   | - hook_backup: Dict[str, Tuple[Tensor, Device]]   |   |
   |   +------------------------------------+   +---------------------------------------------------+   |
   |                                                                                                    |
   |   +------------------------------------+   +---------------------------------------------------+   |
   |   | 动态扩展与运行时上下文              |   | 钩子与回调体系                                     |   |
   |   | - model_options: dict (含 TO 字典) |   | - callbacks: CallbacksMP (ON_LOAD, ON_CLONE...)   |   |
   |   | - attachments: Dict[str, Any]      |   | - wrappers: WrappersMP                            |   |
   |   | - additional_models: Dict          |   | - injections: Dict[str, List[PatcherInjection]]   |   |
   |   +------------------------------------+   +---------------------------------------------------+   |
   +----------------------------------------------------------------------------------------------------+
                                               |
                                     持有引用 (Reference)
                                               v
   +----------------------------------------------------------------------------------------------------+
   |                           Underlying PyTorch Model (DiffusionModel)                                |
   |   - diffusion_model.input_blocks.0.0.weight : torch.Tensor (Storage 物理内存/显存)                 |
   |   - diffusion_model.middle_block.1.transformer_blocks.0.attn1.to_q.weight : torch.Tensor           |
   |   - model_loaded_weight_memory: int / model_lowvram: bool / current_weight_patches_uuid: UUID     |
   +----------------------------------------------------------------------------------------------------+

1.1 核心字段与状态存储语义
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: ModelPatcher 核心字段功能与内存语义
   :widths: 22 28 50
   :header-rows: 1

   * - 字段名称
     - 数据结构与类型
     - 物理语义与工程作用
   * - ``model``
     - ``torch.nn.Module``
     - 指向底层真实的 PyTorch 神经网络实体，全克隆树内全局唯一共享。
   * - ``patches``
     - ``dict[str, list[tuple]]``
     - 权重差分修补表，Key 为参数名（如 ``"diffusion_model.input_blocks.1.1.weight"``），Value 为补丁元组列表。
   * - ``backup``
     - ``dict[str, Dimension]``
     - 原始参数备份字典。在物理修改发生前将原始权重暂存至 Host 内存，支持无损还原。
   * - ``object_patches``
     - ``dict[str, Any]``
     - 模块/属性级对象替换表（如动态替换 ``manual_cast_dtype`` 或自定义卷积算子）。
   * - ``model_options``
     - ``dict``
     - 运行时上下文（包含跨层传递的 ``transformer_options``、采样器控制函数与自注意力劫持）。
   * - ``patches_uuid``
     - ``uuid.UUID``
     - 补丁签名指纹。每次添加或修改补丁时重新生成，用于快速比对两组模型是否具有相同的修补状态。

------------------------------------------------------------------------

2. 浅拷贝克隆树（Shallow Cloning Tree）物理架构
------------------------------------------------

在节点图执行过程中，用户经常在一个主干模型后连接多个并行分支（例如：分支 A 加载赛博朋克风格 LoRA 并生成图片，分支 B 加载水彩风格 LoRA 并生成图片）。若采用深拷贝（Deepcopy），10GB 的大模型将迅速撑爆 64GB 的内存。

2.1 零拷贝派生机制（``ModelPatcher.clone()``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

ComfyUI 的核心创新在于：**克隆操作只复制代理元数据与补丁列表引用，绝不复制底层的 PyTorch 权重张量**。

.. code-block:: python

    def clone(self, disable_dynamic=False, model_override=None, force_deepcopy=False):
        class_ = self.__class__
        if model_override is None:
            # 提取被代理的底层模型实例以及共享的备份容器
            model_override = self.get_clone_model_override()

        # 实例化新的 ModelPatcher，底层 model 实例完全相同
        n = class_(
            model_override[0],
            self.load_device,
            self.offload_device,
            self.model_size(),
            weight_inplace_update=self.weight_inplace_update
        )

        # 浅拷贝补丁列表（仅复制列表外层结构，元组内部张量保持引用）
        n.patches = {}
        for k in self.patches:
            n.patches[k] = self.patches[k][:]
        n.patches_uuid = self.patches_uuid

        # 复制对象补丁与深拷贝轻量上下文字典
        n.object_patches = self.object_patches.copy()
        n.model_options = comfy.utils.deepcopy_list_dict(self.model_options)
        n.parent = self

        # 共享底层的备份状态容器，确保任意分支的卸载均能还原初始权重
        n.backup, n.backup_buffers, n.object_patches_backup, n.pinned = model_override[1]

        # 派生回调通知
        for callback in self.get_all_callbacks(CallbacksMP.ON_CLONE):
            callback(self, n)
        return n

2.2 树状分支衍生拓扑与内存等价性
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                                 Base Checkpoint Loader Node                                        |
   |                                ModelPatcher_0 (UUID: A001)                                         |
   |                                 - patches: {}                                                      |
   |                                 - model: 0x7f9a100 (SDXL Base 6.6GB)                               |
   +----------------------------------------------------------------------------------------------------+
                                      |                                  |
                        .clone()      v                    .clone()      v
   +------------------------------------------+   +-----------------------------------------------------+
   |      LoraLoader Node A (Cyberpunk)       |   |         LoraLoader Node B (Watercolor)              |
   |       ModelPatcher_1 (UUID: B002)        |   |          ModelPatcher_2 (UUID: C003)                |
   | - patches: {"attn1.q": [LoraA_Tensor]}   |   | - patches: {"attn1.q": [LoraB_Tensor]}              |
   | - model: 0x7f9a100 (共享无内存拷贝)      |   | - model: 0x7f9a100 (共享无内存拷贝)                 |
   +------------------------------------------+   +-----------------------------------------------------+
                        |                                                |
                        v                                                v
               KSampler Node 1 (Run A)                          KSampler Node 2 (Run B)

在上述拓扑中：

- ``ModelPatcher_1`` 与 ``ModelPatcher_2`` 各自拥有独立的 ``patches`` 字典和不同的 ``patches_uuid``；
- 但它们底层指向同一块 ``0x7f9a100`` 物理模型内存；
- 当 ``KSampler 1`` 启动时，调度器将 ``LoraA`` 动态注入底层物理权重；执行完毕后，恢复备份并应用 ``LoraB`` 供 ``KSampler 2`` 使用。整个过程物理显存开销严格维持在 1 份基础模型 + 增量 LoRA 矩阵。

------------------------------------------------------------------------

3. 动态补丁注册机制与 UUID 状态溯源
------------------------------------

为了支持多层 LoRA 串联、权重缩放与按层加权注入，``ModelPatcher.add_patches()`` 建立了代数化的补丁注册协议。

3.1 补丁元组数据规范
~~~~~~~~~~~~~~~~~~~~

每一个向指定参数注入的补丁，均由一个 5 元组（5-tuple）描述：

.. math::

   P_{	ext{entry}} = (\alpha_{	ext{patch}}, \mathbf{\Delta W}, \beta_{	ext{model}}, 	ext{offset}, 	ext{function})

其中：

- :math:`\alpha_{	ext{patch}}`：补丁强度系数（Patch Strength，如 LoRA 权重比例）。
- :math:`\mathbf{\Delta W}`：补丁张量结构（可为单一张量、LoRA 低秩分解对 ``(A, B)``、或量化权重大字典）。
- :math:`\beta_{	ext{model}}`：基础模型强度缩放因子（Model Strength）。
- :math:`	ext{offset}`：张量切片偏移（支持针对指定 Head 或 Channel 的局部修补）。
- :math:`	ext{function}`：自定义计算函数（用于非线性权重计算或即时解压）。

3.2 补丁注入与 UUID 重新散列
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    def add_patches(self, patches, strength_patch=1.0, strength_model=1.0):
        with self.use_ejected():
            p = set()
            model_sd = self.model.state_dict()
            for k in patches:
                offset, function = None, None
                if isinstance(k, str):
                    key = k
                else:
                    key, offset = k[0], k[1]
                    if len(k) > 2:
                        function = k[2]

                # 严格校验目标参数是否存在于物理模型的 state_dict 中
                if key in model_sd:
                    p.add(k)
                    current_patches = self.patches.get(key, [])
                    # 追加 5 元组补丁描述
                    current_patches.append((strength_patch, patches[k], strength_model, offset, function))
                    self.patches[key] = current_patches

            # 生成全新的 UUID，使得缓存系统与调度器能敏锐感知模型权重的变动
            self.patches_uuid = uuid.uuid4()
            return list(p)

------------------------------------------------------------------------

4. 模型修补与还原生命周期状态机
--------------------------------

``ModelPatcher`` 通过 ``patch_model()`` 与 ``unpatch_model()`` 严格管理底层物理模型在“原始态”与“修补态”之间的确定性跃迁。

其生命周期流转状态机如下所示：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                                 PRISTINE STATE (纯净初始态)                                         |
   |               - 底层 PyTorch 物理权重驻留在 offload_device (CPU)                                   |
   |               - backup 字典为空，object_patches 未挂载                                             |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      | patch_model(device_to="cuda:0", lowvram_model_memory=...)
                                      v
   +----------------------------------------------------------------------------------------------------+
   |                                 PATCHING TRANSITION (注入过渡态)                                   |
   |   1. 遍历 object_patches：set_attr 替换属性，旧属性存入 object_patches_backup                     |
   |   2. 遍历 target keys：get_key_weight 读取原始参数并存入 backup[k] = Dimension(weight, copy)       |
   |   3. 计算修补后张量：out_weight = calculate_weight(patches[k], temp_weight)                          |
   |   4. 赋值回底层模型：copy_to_param(model, k, out_weight) 或 set_attr_param                       |
   |   5. 搬移至目标计算设备：load_completely.to(device_to) 或 注册 LowVramPatch 函数                    |
   |   6. 触发所有注入拦截器：inject_model()                                                             |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      | 采样执行期 (Inference Execution / Forward Passes)
                                      v
   +----------------------------------------------------------------------------------------------------+
   |                                  PATCHED ACTIVE STATE (修补活跃态)                                 |
   |               - 底层模型携带目标 LoRA / Hook，在目标设备上执行高性能 Forward 计算                  |
   |               - current_weight_patches_uuid == self.patches_uuid                                   |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      | unpatch_model(device_to="cpu", unpatch_weights=True)
                                      v
   +----------------------------------------------------------------------------------------------------+
   |                                UNPATCHING TRANSITION (还原过渡态)                                  |
   |   1. 退出注入拦截器：eject_model()                                                                  |
   |   2. 清理 Hook 链与锁页内存：unpatch_hooks() / unpin_all_weights()                                 |
   |   3. 物理权重回填还原：for k, bk in backup.items(): copy_to_param(model, k, bk.weight)            |
   |   4. 清理低显存分层函数：wipe_lowvram_weight(m)                                                    |
   |   5. 还原 object_patches：set_attr(model, k, object_patches_backup[k])                              |
   |   6. 搬回卸载设备并释放备份：backup.clear() / object_patches_backup.clear()                         |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      v
                             回到 PRISTINE STATE

4.1 核心防护守卫：``AutoPatcherEjector``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在修改模型元数据、计算权重或克隆分支时，若模型正处于外部自定义插件的“注入态（Injected State）”，直接读写属性可能引发不可预测的副作用。

ComfyUI 引入了上下文管理器 ``AutoPatcherEjector``（``use_ejected()``）：

.. code-block:: python

    class AutoPatcherEjector:
        def __init__(self, model: 'ModelPatcher', skip_and_inject_on_exit_only=False):
            self.model = model
            self.was_injected = False

        def __enter__(self):
            # 进入临界区前自动弹出已注入的拦截层，确保底层模型暴露为纯净态
            if self.model.is_injected:
                self.model.eject_model()
                self.was_injected = True

        def __exit__(self, *args):
            # 退出临界区后重新注入拦截层，维持原有执行上下文
            if self.was_injected and not self.model.skip_injection:
                self.model.inject_model()

------------------------------------------------------------------------

5. 代理修补与物理模型交互对照表
--------------------------------

.. list-table:: ModelPatcher 与底层 PyTorch 模型职责边界对照
   :widths: 20 40 40
   :header-rows: 1

   * - 系统维度
     - ModelPatcher 代理层职责
     - 底层 PyTorch Module 物理层职责
   * - **存储生命周期**
     - 负责补丁元数据、备份引用容器、分支拓扑的生命周期管理与垃圾回收
     - 持有真正的张量物理 Storage，受操作系统与 CUDA Allocator 直接分配管理
   * - **多分支衍生**
     - 通过浅拷贝 ``clone()`` 实现瞬时分支创建，跟踪独立的 ``patches_uuid``
     - 保持单一实体，对上层分支无感知，由当前活跃的 Patcher 动态改写与复原
   * - **设备调度集成**
     - 计算各子模块显存开销（``_load_list``），决定分层卸载或整网载入策略
     - 响应 ``.to(device)`` 指令或在算子前向执行时消费即时换入的切片权重
   * - **前向计算劫持**
     - 挂载 ``model_function_wrapper`` 与 ``transformer_options`` 运行时上下文
     - 执行标准的矩阵乘法、卷积与注意力运算算子

------------------------------------------------------------------------

小结与下章导读
==============

本节系统剖析了 ComfyUI 动态修补体系的核心基石——``ModelPatcher``：

1. **轻量代理架构**：解耦了物理模型与修补声明，确立了模型级元数据管理外壳；
2. **浅拷贝克隆树**：通过共享底层 ``torch.nn.Module`` 与备份容器，实现了多分支工作流的零内存额外开销；
3. **补丁代数与状态溯源**：规范了 5 元组补丁描述符，并通过 ``patches_uuid`` 实现了全局因果指纹追踪；
4. **确定性状态机**：基于 ``patch_model`` 与 ``unpatch_model`` 保证了模型修补与物理还原的绝对无损。

在下一节（``02_weight_patch_algebra_and_lora.rst``）中，我们将深入其核心算法层——**权重差分注入代数与 LoRA/DoRA 在线融合**：探究低秩差分矩阵在线计算原理（``calculate_weight``）、通道切片与重塑数学推导，以及动态去补丁反向消除算法。
