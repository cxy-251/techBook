========================================================================
节点缓存哈希签名树、IS_CHANGED 脏状态探测与系统内存压力回收
========================================================================

.. note:: 前置背景与上下文承接
   在上一节（``01_prompt_executor_and_dag.rst``）中，我们建立了 ComfyUI 计算图拓扑消解（Topological Dissolve）与 ``PromptExecutor`` 状态机的宏观图景。调度器在提取就绪节点执行前，最核心的性能加速机制便是多级张量缓存。本节深入缓存子系统（``comfy_execution/caching.py`` 与 ``execution.py``）的微观物理实现，全面解构全链路因果祖先签名树（``CacheKeySetInputSignature``）、不可变对象的规范化哈希算法、``IS_CHANGED`` 动态指纹探测协议，以及在大规模多任务并发下通过 ``RAMPressureCache`` 与操作系统内核水压协同的张量驱逐算法。

------------------------------------------------------------------------

1. 计算图缓存的物理本质与因果不变性
------------------------------------

在复杂生成式 AI 拓扑中，算子的输入既包含标量字面量（如采样步数 ``steps``、去噪强度 ``denoise``），也包含来自前驱算子的巨大张量（如 4 通道 Latent 特征图、CLIP 文本条件嵌入）。若仅仅对节点自身的入参值进行简单浅层哈希，当上游任何一个祖先节点的参数发生微小变更时（例如微调了上一级 LoRA 的权重），下游所有算子在本地看似入参未变，实际上其输入张量的物理数值已彻底失效。

为了在无须实际执行上游计算的前提下判定下游缓存的有效性，ComfyUI 建立了**因果依赖图同构不变性（Causality Invariant）**：

.. math::

   	ext{CacheKey}(N) = \mathcal{H}\Big(	ext{Op}_N, 	ext{Fingerprint}(N), 	ext{Consts}_N, \big\{ (	ext{Port}_k, 	ext{Idx}(A_k), 	ext{Socket}_k) \big\}_{k=1}^K, \big\{ 	ext{ImmediateKey}(A_i) \big\}_{i \in 	ext{Ancestors}(N)}\Big)

任意节点 $N$ 的缓存 Key 不仅绑定当前节点的算子类型与静态常数，还严格绑定其所有有向祖先集合 $	ext{Ancestors}(N)$ 的拓扑排序与即时签名。

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                                     Node N (e.g. KSampler)                                         |
   |   Inputs: seed=42, cfg=7.5, model=(Link to Node 3, Port 0), latent_image=(Link to Node 2, Port 0)  |
   +----------------------------------------------------------------------------------------------------+
                                      |
         +----------------------------+----------------------------+
         v                                                         v
   +-----------------------------------+             +-----------------------------------+
   | Node 3 (LoraLoader, Ancestor 0)   |             | Node 2 (EmptyLatent, Ancestor 1)  |
   | Inputs: lora_name="style.safetensors" |         | Inputs: width=1024, height=1024   |
   +-----------------------------------+             +-----------------------------------+
         |
         v
   +-----------------------------------+
   | Node 1 (CheckpointLoader, Anc 2)  |
   | Inputs: ckpt_name="sdxl.safetensors" |
   +-----------------------------------+

   Deterministic Signature Stream:
   [ImmediateKey(KSampler), ImmediateKey(LoraLoader), ImmediateKey(EmptyLatent), ImmediateKey(CheckpointLoader)]
   ==> Canonicalized & Hashed ==> Immutable frozenset CacheKey

------------------------------------------------------------------------

2. 拓扑祖先签名树（CacheKeySetInputSignature）实现机制
-------------------------------------------------------

2.1 确定性祖先图拓扑遍历（``get_ordered_ancestry``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了确保跨不同执行批次、不同 Python 进程运行环境下的缓存签名绝对一致，祖先遍历必须具备严格的确定性全序（Total Order）。ComfyUI 在遍历节点输入槽时强制对输入参数键名进行字典序排序：

.. code-block:: python

    def get_ordered_ancestry(self, dynprompt, node_id):
        ancestors = []
        order_mapping = {}
        self.get_ordered_ancestry_internal(dynprompt, node_id, ancestors, order_mapping)
        return ancestors, order_mapping

    def get_ordered_ancestry_internal(self, dynprompt, node_id, ancestors, order_mapping):
        if not dynprompt.has_node(node_id):
            return
        inputs = dynprompt.get_node(node_id)["inputs"]
        # 强制排序键名，消除 Python 字典迭代无序性带来的哈希发散
        input_keys = sorted(inputs.keys())
        for key in input_keys:
            if is_link(inputs[key]):
                ancestor_id = inputs[key][0]
                if ancestor_id not in order_mapping:
                    ancestors.append(ancestor_id)
                    order_mapping[ancestor_id] = len(ancestors) - 1
                    # 深度优先递归遍历祖先的上游
                    self.get_ordered_ancestry_internal(dynprompt, ancestor_id, ancestors, order_mapping)

2.2 即时节点签名构建（``get_immediate_node_signature``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于图中的每一个节点，其即时签名提取了决定其计算结果的最小完备特征集：

.. code-block:: python

    async def get_immediate_node_signature(self, dynprompt, node_id, ancestor_order_mapping):
        if not dynprompt.has_node(node_id):
            return [float("NaN")]
        node = dynprompt.get_node(node_id)
        class_type = node["class_type"]
        class_def = nodes.NODE_CLASS_MAPPINGS[class_type]
        
        # 核心特征 1：算子类型与动态脏状态指纹
        signature = [class_type, await self.is_changed_cache.get(node_id)]
        
        # 核心特征 2：非幂等性隔离（若节点标记为非幂等或消费 UNIQUE_ID，注入真实 node_id 隔离）
        if self.include_node_id_in_input() or (hasattr(class_def, "NOT_IDEMPOTENT") and class_def.NOT_IDEMPOTENT) or include_unique_id_in_input(class_type):
            signature.append(node_id)
            
        inputs = node["inputs"]
        for key in sorted(inputs.keys()):
            if is_link(inputs[key]):
                (ancestor_id, ancestor_socket) = inputs[key]
                ancestor_index = ancestor_order_mapping[ancestor_id]
                # 核心特征 3：拓扑抽象连线（使用相对索引 ancestor_index 替代绝对 node_id）
                signature.append((key, ("ANCESTOR", ancestor_index, ancestor_socket)))
            else:
                # 核心特征 4：字面量输入常数
                signature.append((key, inputs[key]))
        return signature

这里使用 ``("ANCESTOR", ancestor_index, ancestor_socket)`` 的相对拓扑代数，使得子图在不同宿主工作流中被复用或复制节点 ID 改变时，只要拓扑结构相同依然可以完美命中缓存。

------------------------------------------------------------------------

3. 数据规范化、不可变转换与外部提供者哈希
------------------------------------------

3.1 内存对象的不可变映射（``to_hashable``）与 NaN 哨兵
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Python 内置字典与列表属于可变容器（Mutable），不能直接作为哈希表的键。``to_hashable`` 递归地将复杂容器转化为不可变集合（``frozenset``）：

.. code-block:: python

    class Unhashable:
        def __init__(self):
            self.value = float("NaN")

    def to_hashable(obj):
        if isinstance(obj, (int, float, str, bool, bytes, type(None))):
            return obj
        elif isinstance(obj, Mapping):
            return frozenset([(to_hashable(k), to_hashable(v)) for k, v in sorted(obj.items())])
        elif isinstance(obj, Sequence):
            return frozenset(zip(itertools.count(), [to_hashable(i) for i in obj]))
        else:
            # 遇到无法哈希的特殊对象时返回 Unhashable 哨兵
            return Unhashable()

.. note:: NaN 的自反不等性物理原理
   在 IEEE 754 浮点数标准中，``NaN != NaN`` 恒成立。当一个节点包含无法静态哈希的动态对象时，其签名中嵌入 ``float("NaN")``。在 Python 本地字典查询中，由于 ``hash(NaN)`` 虽能计算但对象比较 ``key == cached_key`` 必然判定为 ``False``，从而在底层强制击穿缓存，促使调度器安全执行该节点。

3.2 外部缓存提供者与 SHA-256 规范化序列化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当挂载了外部分布式缓存提供者（如 Redis、远程对象存储或 DiskCache）时，内存态的 ``frozenset`` 无法直接持久化。``comfy_execution/cache_provider.py`` 实现了规范化 JSON 序列化：

.. code-block:: python

    def _canonicalize(obj: Any) -> Any:
        if isinstance(obj, (frozenset, set)):
            # 显式使用 json.dumps 排序，消除集合在不同解释器会话中的哈希加盐随机性
            return ("__frozenset__", sorted(
                [_canonicalize(item) for item in obj],
                key=lambda x: json.dumps(x, sort_keys=True)
            ))
        elif isinstance(obj, tuple):
            return ("__tuple__", [_canonicalize(item) for item in obj])
        elif isinstance(obj, list):
            return [_canonicalize(item) for item in obj]
        elif isinstance(obj, dict):
            return {"__dict__": sorted(
                [[_canonicalize(k), _canonicalize(v)] for k, v in obj.items()],
                key=lambda x: json.dumps(x, sort_keys=True)
            )}
        elif isinstance(obj, (int, float, str, bool, type(None))):
            return (type(obj).__name__, obj)
        elif isinstance(obj, bytes):
            return ("__bytes__", obj.hex())
        else:
            raise ValueError(f"Cannot canonicalize type: {type(obj).__name__}")

    def _serialize_cache_key(cache_key: Any) -> Optional[str]:
        try:
            # 规避 pickle 跨版本非确定性，输出确定性 SHA-256 摘要
            canonical = _canonicalize(cache_key)
            json_str = json.dumps(canonical, sort_keys=True, separators=(',', ':'))
            return hashlib.sha256(json_str.encode('utf-8')).hexdigest()
        except Exception as e:
            _logger.warning(f"Failed to serialize cache key: {e}")
            return None

------------------------------------------------------------------------

4. IS_CHANGED 脏状态动态探测协议
---------------------------------

许多生成式算子拥有与静态输入无关的动态行为。例如：

1. **随机噪声发生器**：参数虽然相同，但若要求每轮重新生成，需返回新的随机种子；
2. **外部文件读取节点（如 LoadImage）**：磁盘图像文件可能已被外部绘图软件修改；
3. **硬件摄像头/视频流采集节点**：每次拉取最新一帧。

ComfyUI 通过 ``IsChangedCache`` 与节点自定义方法建立了运行时脏状态探测协议：

.. list-table:: IS_CHANGED 探测协议规范
   :widths: 20 25 55
   :header-rows: 1

   * - 协议接口
     - 适用节点规范
     - 探测逻辑与返回值语义
   * - ``IS_CHANGED``
     - V1 经典函数式节点
     - 接收节点常量入参。返回任意可哈希值（如文件修改时间戳 ``mtime``、浮点随机数或帧序号）。
   * - ``fingerprint_inputs``
     - V3 面向对象节点 (``_ComfyNodeInternal``)
     - 接收结构化入参对象。返回确定性输入指纹。
   * - ``float("NaN")``
     - 异常或强制脏状态
     - 当节点探测过程中抛出异常或显式返回 NaN 时，底层直接判定该节点及其下游全部失效。

在 ``execution.py`` 的 ``IsChangedCache.get`` 实现中，有一项极其关键的系统设计原则：**在执行 ``IS_CHANGED`` 时，故意不使用前驱节点的缓存输出，仅传入字面量常量参数**。这是因为在计算缓存 Key 阶段，上游输出张量可能尚未生成；如果允许 ``IS_CHANGED`` 依赖上游输出，会导致先有鸡还是先有蛋的死锁循环。

------------------------------------------------------------------------

5. RAMPressureCache：物理内存水压感知与智能驱逐
------------------------------------------------

在长时间运行或批量图像生成场景下，缓存中间层的大尺寸 Tensor（如 2048x2048 分辨率下多层 UNet 激活值与 VAE 潜变量）会急剧消耗 Host 系统物理内存（RAM），最终引发操作系统级的 OOM-Killer。

ComfyUI 设计了 ``RAMPressureCache``，通过订阅操作系统物理内存水位，构建了基于指数代际衰减与张量物理体积的混合驱逐数学模型。

5.1 驱逐评分公式与代际偏置
~~~~~~~~~~~~~~~~~~~~~~~~~~

当系统可用物理内存（``psutil.virtual_memory().available``）低于目标安全裕量（``ram_headroom``）时，驱逐器对缓存条目计算 ``oom_score``：

.. math::

   	ext{Score}(E) = 1.3^{(	ext{Generation}_{	ext{current}} - 	ext{Generation}_{	ext{used}}(E))} 	imes 	ext{RAM\_Usage}(E)

.. list-table:: RAMPressureCache 核心参数与权重配置
   :widths: 35 20 45
   :header-rows: 1

   * - 配置常量名称
     - 数值大小
     - 物理调度意义
   * - ``RAM_CACHE_OLD_WORKFLOW_OOM_MULTIPLIER``
     - ``1.3``
     - 旧工作流代际衰减底数。指数级提高旧执行轮次残留条目的驱逐优先级。
   * - ``RAM_CACHE_DEFAULT_RAM_USAGE``
     - ``0.05`` (MB 等效)
     - 无法直接测算 CPU 张量体积的元数据条目的基准保底权重。
   * - ``RAM_CACHE_LARGE_INTERMEDIATE``
     - ``512 MB``
     - 大尺寸中间激活值阈值。优先驱逐单体超过 512MB 的巨型中间结果。
   * - ``Stale ModelPatcher Penalty``
     - :math:`10^{30}`
     - 针对非当前代活跃的旧 ``ModelPatcher`` 对象赋予天文数字评分，确保旧模型浅拷贝包装器第一时间被彻底清除。

5.2 内存释放状态机（``ram_release``）实现剖析
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    def ram_release(self, target, free_active=False, min_entry_size=0):
        if psutil.virtual_memory().available >= target:
            return 0

        clean_list = []
        for key, cache_entry in self.cache.items():
            # 保护当前正在执行的活跃轮次条目（除非显式指定 free_active）
            if not free_active and self.used_generation[key] == self.generation:
                continue

            # 动态输出对象若在当前代使用中，严禁释放
            if all_outputs_dynamic(cache_entry.outputs) and self.used_generation[key] == self.generation:
                continue

            oom_score = RAM_CACHE_OLD_WORKFLOW_OOM_MULTIPLIER ** (self.generation - self.used_generation[key])
            ram_usage = RAM_CACHE_DEFAULT_RAM_USAGE
            oom_ram_usage = ram_usage

            def scan_list_for_ram_usage(outputs):
                nonlocal ram_usage, oom_ram_usage
                if outputs is None:
                    return
                for output in outputs:
                    if isinstance(output, (list, tuple)):
                        scan_list_for_ram_usage(output)
                    elif isinstance(output, torch.Tensor) and output.device.type == 'cpu':
                        # 物理统计 CPU 驻留张量的实际字节数 (numel * element_size)
                        tensor_bytes = output.numel() * output.element_size()
                        ram_usage += tensor_bytes
                        oom_ram_usage += tensor_bytes
                    elif is_model_patcher_output(output) and self.used_generation[key] != self.generation:
                        # 废弃的 ModelPatcher 赋予极高 OOM 惩罚权重，加速回收
                        oom_ram_usage = 1e30

            scan_list_for_ram_usage(cache_entry.outputs)
            if ram_usage < min_entry_size:
                continue

            oom_score *= oom_ram_usage
            # 使用二分插入法按 (oom_score, timestamp, key, ram_usage) 严格排序
            bisect.insort(clean_list, (oom_score, self.timestamps[key], key, ram_usage))

        freed = 0
        while psutil.virtual_memory().available < target and clean_list:
            _, _, key, ram_usage = clean_list.pop()
            del self.cache[key]
            self.used_generation.pop(key, None)
            self.timestamps.pop(key, None)
            self.children.pop(key, None)
            freed += ram_usage
            
        return freed

在每次节点执行完成后，若系统内存水压依然高于阈值，调度器还会协同调用 ``comfy.model_management.free_pins()`` 释放 PyTorch 锁页内存池（Pinned Memory），并在必要时强制休眠 50ms 等待操作系统内核虚拟内存页解提交（Mem Decommit）完成。

------------------------------------------------------------------------

小结与下章导读
==============

本节全面剖析了 ComfyUI 高性能节点缓存与脏状态管理体系：

1. **因果拓扑签名**：通过 ``CacheKeySetInputSignature`` 构建包含上游全链路因果拓扑的全序哈希树，使用相对连接锚点保证子图复用时的缓存命中率；
2. **确定性序列化**：通过 ``to_hashable`` 与 ``_canonicalize`` 将异构数据转换为不可变集合，并利用 IEEE 754 ``NaN != NaN`` 特性实现硬件级强制跳过缓存；
3. **动态指纹感知**：利用 ``IS_CHANGED`` / ``fingerprint_inputs`` 实现文件变动、动态种子与视频流的高效脏状态感知；
4. **系统级内存水压协商**：``RAMPressureCache`` 结合代际指数衰减与张量物理内存体积，实现了兼顾命中率与系统稳定性的自动化内存回收。

在下一节（``03_lazy_evaluation_and_subgraph_expansion.rst``）中，我们将进一步探讨 ComfyUI 调度引擎的高阶控制流：深度剖析基于 ``check_lazy_status`` 的动态惰性求值分支、运行时嵌套子图（Ephemeral Subgraphs）动态注入机制，以及条件控制流中的执行熔断器（``ExecutionBlocker``）。
