========================================================================
PromptExecutor 执行状态机、动态 DAG 拓扑排序与调度执行内核
========================================================================

.. note:: 前置背景与上下文承接
   在生成式 AI 工业级系统中，计算任务通常被组织为复杂的高阶数据流网络（Dataflow Graph）。不同于传统推理框架（如 PyTorch 原生序列执行或静态 ONNX 计算图），ComfyUI 将大模型加载、LoRA 权重修补、文本潜变量投影、多步扩散迭代与潜空间解码统一抽象为可动态修改的有向无环图（Directed Acyclic Graph, DAG）。本节作为全书架构内核的首章，深入剖析核心调度器 ``PromptExecutor`` 的执行状态机、``TopologicalSort`` 与 ``ExecutionList`` 的动态解构算法、启发式就绪调度策略以及运行时异常熔断与 OOM 自愈机制。

------------------------------------------------------------------------

1. 计算图执行的物理本质与调度模型
----------------------------------

在现代异构计算（Host CPU + Device GPU）体系下，生成式 AI 推理任务面临三大物理现实约束：

1. **显存容量与模型权重的非对称性**：百亿参数级扩散模型（如 SD3、Flux.1）无法同时完整驻留于消费级甚至企业级 GPU 物理显存中，必须由 CPU 侧精确规划算子生命周期；
2. **算子执行开销的极端悬殊**：加载模型与文本编码耗时数十毫秒，而 KSampler 多步迭代计算耗时数秒至数十秒，动态分支与缓存策略直接决定端到端吞吐率；
3. **图拓扑的运行时可变性**：由于控制流节点（Switch/Condition）、子图展开（Subgraph Expansion）与动态输入的存在，静态编译拓扑图无法满足要求，必须依赖运行时动态消解图（Dynamic Graph Dissolve）。

ComfyUI 的核心调度架构建立在 ``execution.py`` 与 ``comfy_execution/`` 子系统之上，其计算拓扑驱动模式如下图所示：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                                     Prompt JSON (Client Submission)                                |
   +----------------------------------------------------------------------------------------------------+
                                                     |
                                                     v
   +----------------------------------------------------------------------------------------------------+
   |                                    validate_prompt / validate_inputs                               |
   |           (Static Semantic Validation, Recursive Cycle Detection, Type & Range Checking)           |
   +----------------------------------------------------------------------------------------------------+
                                                     |
                                                     v
   +----------------------------------------------------------------------------------------------------+
   |                                     DynamicPrompt & CacheKeySet                                    |
   |              (Hierarchy Isolation, Ancestor Topology Hashing, IS_CHANGED Fingerprinting)          |
   +----------------------------------------------------------------------------------------------------+
                                                     |
                                                     v
   +----------------------------------------------------------------------------------------------------+
   |                                            ExecutionList                                           |
   |                     (Topological In-Degree Tracking, UX-Friendly Node Selection)                   |
   +----------------------------------------------------------------------------------------------------+
                                 |                                           ^
                                 v                                           |
   +-------------------------------------------------------------+           | Unstage / Ephemeral
   |               execute() Node Execution Loop                 |           | Subgraph Expanded /
   |  - Query Node Cache / External Provider                     |-----------+ Lazy Inputs Missing
   |  - Async Function Wrapping (CurrentNodeContext)             |
   |  - Dynamic Subgraph Injection (add_ephemeral_node)          |
   |  - Model Lifetime / GC / RAM Pressure Trigger               |
   +-------------------------------------------------------------+
                                 |
                                 v
   +----------------------------------------------------------------------------------------------------+
   |                        Execution Success / Exception Handling / OOM Circuit Breaking               |
   +----------------------------------------------------------------------------------------------------+

------------------------------------------------------------------------

2. 核心数据结构与状态机字段解剖
--------------------------------

在 ``execution.py`` 与 ``comfy_execution/graph.py`` 中，图执行状态由一组精巧的面向对象数据结构协同维护。

2.1 DynamicPrompt 拓扑抽象
~~~~~~~~~~~~~~~~~~~~~~~~~~

``DynamicPrompt`` 解决了静态用户 Prompt 与运行时动态派生节点之间的命名空间冲突与溯源问题：

.. list-table:: DynamicPrompt 核心字段与系统功能
   :widths: 20 20 60
   :header-rows: 1

   * - 字段名称
     - 类型定义
     - 系统级功能与物理意义
   * - ``original_prompt``
     - ``dict[str, dict]``
     - 客户端原始提交的静态工作流字典，键为静态 ``node_id``，值为包含 ``class_type`` 与 ``inputs`` 的元数据。
   * - ``ephemeral_prompt``
     - ``dict[str, dict]``
     - 运行时由节点内部动态展开（Subgraph Expansion）生成的瞬态节点集合，生命周期仅限于单次 Prompt 执行。
   * - ``ephemeral_parents``
     - ``dict[str, str]``
     - 瞬态节点的父节点映射表。用于调用 ``get_real_node_id()`` 沿层级向上递归追溯根源静态节点。
   * - ``ephemeral_display``
     - ``dict[str, str]``
     - 瞬态节点的 UI 映射表。用于调用 ``get_display_node_id()`` 将执行进度与中间结果定向回前端对应的可视化节点。

2.2 TopologicalSort 与 ExecutionList 状态机
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``ExecutionList`` 继承自 ``TopologicalSort``，维护图拓扑消除过程中的动态入度与依赖监听：

.. list-table:: ExecutionList 核心控制字段解剖
   :widths: 25 25 50
   :header-rows: 1

   * - 字段名称
     - 类型定义
     - 调度作用机制
   * - ``pendingNodes``
     - ``dict[str, bool]``
     - 当前尚未完成执行的活跃节点集合。
   * - ``blockCount``
     - ``dict[str, int]``
     - 动态入度计数器：当前节点被多少个尚未执行完成的直接前驱节点所阻塞。当计数值降为 0 时即进入就绪就绪池。
   * - ``blocking``
     - ``dict[str, dict]``
     - 反向依赖邻接表：记录当前节点完成后将解锁哪些后继节点及其具体的输出插槽（Socket）。
   * - ``staged_node_id``
     - ``Optional[str]``
     - 当前已被调度器提取并进入执行流水线的节点 ID。若节点需等待异步任务或惰性输入，可被撤回（Unstage）。
   * - ``execution_cache``
     - ``dict[str, dict]``
     - 本地执行张量缓存上下文：以当前节点为键，保存其前驱节点传递的输出对象引用，执行完毕后即刻解引用以释放内存。
   * - ``externalBlocks``
     - ``int``
     - 外部异步事件阻塞计数器。用于协调诸如非阻塞网络拉取或外部硬件同步事件。

------------------------------------------------------------------------

3. 动态 DAG 拓扑排序与启发式调度算法
------------------------------------

3.1 逆向图展开与入度构建（``add_node``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

ComfyUI 的图构建并非从输入源节点向下广播，而是采用**从目标输出节点（``OUTPUT_NODE``）逆向溯源**的惰性拉取模型。算法确保只有真正对最终输出有贡献的算子才会被加入执行池。

其核心逻辑在 ``TopologicalSort.add_node`` 中实现：

.. code-block:: python

    def add_node(self, node_unique_id, include_lazy=False, subgraph_nodes=None):
        node_ids = [node_unique_id]
        links = []

        while len(node_ids) > 0:
            unique_id = node_ids.pop()
            if unique_id in self.pendingNodes:
                continue

            self.pendingNodes[unique_id] = True
            self.blockCount[unique_id] = 0
            self.blocking[unique_id] = {}

            inputs = self.dynprompt.get_node(unique_id)["inputs"]
            for input_name in inputs:
                value = inputs[input_name]
                if is_link(value):
                    from_node_id, from_socket = value
                    if subgraph_nodes is not None and from_node_id not in subgraph_nodes:
                        continue
                    _, _, input_info = self.get_input_info(unique_id, input_name)
                    is_lazy = input_info is not None and "lazy" in input_info and input_info["lazy"]
                    # 默认情况下跳过标记为 lazy 的输入槽，实现惰性分支延迟展开
                    if include_lazy or not is_lazy:
                        if not self.is_cached(from_node_id):
                            node_ids.append(from_node_id)
                        links.append((from_node_id, from_socket, unique_id))

        for link in links:
            self.add_strong_link(*link)

当通过 ``add_strong_link`` 建立前驱与后继连接时，若前驱节点未被缓存命中，则后继节点的 ``blockCount`` 累加 1，并注册至前驱节点的 ``blocking`` 映射中。

3.2 UX 优先的就绪节点启发式选择算法（``ux_friendly_pick_node``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当多个节点的 ``blockCount`` 同时为 0 时，传统的拓扑排序往往随意挑选或按 ID 排序，但这会导致极差的交互体验（例如用户迟迟看不到预览图，或者异步任务未能尽早发射）。ComfyUI 在 ``ux_friendly_pick_node`` 中实现了四级启发式权重仲裁：

.. code-block:: python

    def ux_friendly_pick_node(self, node_list):
        def is_output(node_id):
            class_type = self.dynprompt.get_node(node_id)["class_type"]
            class_def = nodes.NODE_CLASS_MAPPINGS[class_type]
            return hasattr(class_def, 'OUTPUT_NODE') and class_def.OUTPUT_NODE == True

        def is_async(node_id):
            class_type = self.dynprompt.get_node(node_id)["class_type"]
            class_def = nodes.NODE_CLASS_MAPPINGS[class_type]
            return inspect.iscoroutinefunction(getattr(class_def, class_def.FUNCTION))

        # 策略 1：优先执行直接产生可视化输出的节点或异步协程节点（降低端到端延迟）
        for node_id in node_list:
            if is_output(node_id) or is_async(node_id):
                return node_id

        # 策略 2：优先执行 1 跳即可解锁输出节点的算子（如 VAEDecode -> PreviewImage）
        for node_id in node_list:
            for blocked_node_id in self.blocking[node_id]:
                if is_output(blocked_node_id):
                    return node_id

        # 策略 3：优先执行 2 跳解锁输出节点的算子（如 VAELoader -> VAEDecode -> PreviewImage）
        for node_id in node_list:
            for blocked_node_id in self.blocking[node_id]:
                for blocked_node_id1 in self.blocking[blocked_node_id]:
                    if is_output(blocked_node_id1):
                        return node_id

        # 策略 4：退化为默认顺序
        return node_list[0]

3.3 循环依赖动态解构与责任节点判定（``get_nodes_in_cycle``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

若用户在前端连线中构成了非法环路，且该环路包含运行时动态生成的节点（静态环路已在 ``validate_prompt`` 阶段拦截），``ExecutionList`` 会陷入 ``len(available) == 0`` 且 ``externalBlocks == 0`` 的死锁状态。此时调度器启动反向拓扑消除算法：

.. code-block:: python

    def get_nodes_in_cycle(self):
        blocked_by = {node_id: {} for node_id in self.pendingNodes}
        for from_node_id in self.blocking:
            for to_node_id in self.blocking[from_node_id]:
                if True in self.blocking[from_node_id][to_node_id].values():
                    blocked_by[to_node_id][from_node_id] = True
        
        # 迭代剔除入度为 0 的孤立分支，残存节点即构成最小环路
        to_remove = [node_id for node_id in blocked_by if len(blocked_by[node_id]) == 0]
        while len(to_remove) > 0:
            for node_id in to_remove:
                for to_node_id in blocked_by:
                    if node_id in blocked_by[to_node_id]:
                        del blocked_by[to_node_id][node_id]
                del blocked_by[node_id]
            to_remove = [node_id for node_id in blocked_by if len(blocked_by[node_id]) == 0]
        return list(blocked_by.keys())

调度器通过遍历残存环路节点，调用 ``dynprompt.get_display_node_id()`` 精确追责并向前端抛出 ``DependencyCycleError``。

------------------------------------------------------------------------

4. 节点缓存签名树与哈希失效判定
--------------------------------

ComfyUI 的高响应性极大依赖其多级缓存体系。在 ``PromptExecutor.execute_async`` 启动前，引擎必须精确计算每个节点的缓存 Key。

4.1 拓扑祖先签名树（``CacheKeySetInputSignature``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

不同于简单的节点入参哈希，ComfyUI 采用**全量因果依赖树哈希**。一个节点的输出是否有效，不仅取决于自身参数，更取决于其所有上游祖先节点的计算结果与连接拓扑：

.. code-block:: python

    async def get_node_signature(self, dynprompt, node_id):
        signature = []
        # 1. 获取按输入连接顺序严格确定性排列的所有祖先节点列表
        ancestors, order_mapping = self.get_ordered_ancestry(dynprompt, node_id)
        # 2. 生成当前节点的即时签名
        signature.append(await self.get_immediate_node_signature(dynprompt, node_id, order_mapping))
        # 3. 递归追加所有祖先节点的即时签名
        for ancestor_id in ancestors:
            signature.append(await self.get_immediate_node_signature(dynprompt, ancestor_id, order_mapping))
        return to_hashable(signature)

4.2 即时签名因子剖析
~~~~~~~~~~~~~~~~~~~~

``get_immediate_node_signature`` 将以下关键物理特征序列化为不可变元组（``frozenset``）：

1. **算子类类型标识**：``class_type``（例如 ``"KSampler"``）；
2. **动态脏状态指纹**：由 ``IsChangedCache`` 异步执行该节点的 ``IS_CHANGED`` 或 ``fingerprint_inputs`` 方法返回的哈希值（若返回非数 ``NaN`` 则强制跳过缓存）；
3. **节点非幂等性保护**：若类标记为 ``NOT_IDEMPOTENT = True`` 或包含隐式输入 ``UNIQUE_ID``，则将 ``node_id`` 纳入哈希，隔离不同实例；
4. **静态输入字面量**：按参数名排序后的具体参数值（如浮点数 ``cfg``、整数 ``seed``）；
5. **动态链接锚点**：对于来自上游的链接，记录为三元组 ``("ANCESTOR", ancestor_index, ancestor_socket)``，精确刻画上游拓扑位置而非易变的临时节点 ID。

------------------------------------------------------------------------

5. 执行状态机主循环与异常熔断
------------------------------

``PromptExecutor.execute_async`` 是驱动整个计算图演进的主控状态机。

5.1 状态机执行流转与行级源码对照
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    while not execution_list.is_empty():
        # 阶段 1：拓扑就绪节点提取
        node_id, error, ex = await execution_list.stage_node_execution()
        if error is not None:
            self.handle_execution_error(prompt_id, dynamic_prompt.original_prompt, current_outputs, executed, error, ex)
            break

        # 阶段 2：执行节点算子
        result, error, ex = await execute(
            self.server, dynamic_prompt, self.caches, node_id, extra_data, 
            executed, prompt_id, execution_list, pending_subgraph_results, 
            pending_async_nodes, ui_node_outputs
        )
        self.success = result != ExecutionResult.FAILURE
        
        # 阶段 3：状态流转与分支处理
        if result == ExecutionResult.FAILURE:
            self.handle_execution_error(prompt_id, dynamic_prompt.original_prompt, current_outputs, executed, error, ex)
            break
        elif result == ExecutionResult.PENDING:
            # 节点触发惰性输入拉取、等待异步协程任务或展开子图，退回就绪队列
            execution_list.unstage_node_execution()
        else: # ExecutionResult.SUCCESS
            # 节点执行成功，消除入度并释放前驱临时缓存
            execution_list.complete_node_execution()

        # 阶段 4：系统物理内存水压监控与动态驱逐
        if self.cache_type == CacheType.RAM_PRESSURE:
            ram_release_callback(ram_inactive_headroom)
            ram_shortfall = ram_headroom - psutil.virtual_memory().available
            if ram_shortfall > 0:
                freed = ram_release_callback(ram_headroom, free_active=True, min_entry_size=RAM_CACHE_LARGE_INTERMEDIATE)
                ram_shortfall -= freed
            if comfy.model_management.should_free_pins_for_ram_pressure(ram_shortfall):
                freed = comfy.model_management.free_pins(ram_shortfall + 512 * (1024 ** 2))
                if freed < ram_shortfall:
                    if freed > 64 * (1024 ** 2):
                        time.sleep(0.05)
                    ram_release_callback(ram_headroom, free_active=True)

5.2 显存 OOM 熔断与自愈机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~

在深度学习推理中，显存分配失败（CUDA Out of Memory）通常会导致整个 Python 进程崩溃退出。ComfyUI 在 ``execute`` 异常捕获中实现了优雅的熔断与自愈处理：

.. code-block:: python

    except Exception as ex:
        if comfy.model_management.is_oom(ex):
            tips = "This error means you ran out of memory on your GPU.

TIPS: If the workflow worked before you might have accidentally set the batch_size to a large number."
            logging.info("Memory summary:
{}".format(comfy.model_management.debug_memory_summary()))
            logging.error("Got an OOM, unloading all loaded models.")
            # 核心自愈：主动卸载显存中所有模型实例，释放 PyTorch 显存池，防止宿主服务瘫痪
            comfy.model_management.unload_all_models()
        elif isinstance(ex, RuntimeError) and ("mat1 and mat2 shapes" in str(ex)) and "Sampler" in class_type:
            tips = "

TIPS: If you have any 'Load CLIP' or '*CLIP Loader' nodes in your workflow connected to this sampler node make sure the correct file(s) and type is selected."

        error_details = {
            "node_id": real_node_id,
            "exception_message": "{}
{}".format(ex, tips),
            "exception_type": exception_type,
            "traceback": traceback.format_tb(tb),
            "current_inputs": input_data_formatted
        }
        return (ExecutionResult.FAILURE, error_details, ex)

------------------------------------------------------------------------

小结与下章导读
==============

本节系统剖析了 ComfyUI 计算图调度的底层状态机与算法实现：

1. **DAG 调度模型**：通过 ``DynamicPrompt`` 隔离静态与瞬态节点，利用 ``TopologicalSort`` 与 ``ExecutionList`` 实现动态入度追踪与拓扑消解；
2. **启发式选点**：在多就绪节点并发场景下，``ux_friendly_pick_node`` 采用多跳输出启发式策略，保证前端交互的极致响应；
3. **因果拓扑缓存**：``CacheKeySetInputSignature`` 构建了包含上游全链路依赖图的确定性哈希签名；
4. **运行时韧性**：针对异步任务与子图展开实现了三态状态机（``SUCCESS`` / ``PENDING`` / ``FAILURE``），并提供了自动捕获 OOM 并卸载模型的自愈熔断。

在下一节（``02_node_caching_and_dirty_tracking.rst``）中，我们将进一步深入节点缓存机制的微观世界：剖析 ``CacheKeySetInputSignature`` 的递归序列化算法、``IS_CHANGED`` 动态指纹探测协议，以及 ``RAMPressureCache`` 与操作系统的物理内存压力协商机制。
