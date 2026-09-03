========================================================================
惰性计算机制、动态子图展开与条件控制流执行熔断器
========================================================================

.. note:: 前置背景与上下文承接
   在前两节中，我们先后剖析了 ComfyUI 的静态有向无环图（DAG）拓扑消解模型（``01_prompt_executor_and_dag.rst``）与全链路因果祖先缓存树（``02_node_caching_and_dirty_tracking.rst``）。然而，现代生成式 AI 工作流已超越了传统的单向流水线，广泛引入了条件分支（If-Else）、宏节点封装（Macro Nodes）、循环迭代与动态路由等复杂控制流。如果采用完全静态预先物化的图遍历，未选中的分支将被无意义地提前执行，造成严重的显存和计算浪费。本节深入 ``execution.py``、``comfy_execution/graph.py`` 与 ``comfy_execution/graph_utils.py``，全面解剖惰性输入求值协议（``check_lazy_status``）、运行时瞬态子图展开（Ephemeral Subgraphs）与基于执行熔断器（``ExecutionBlocker``）的分支死路径剪枝机制。

------------------------------------------------------------------------

1. 静态 DAG 的局限性与动态控制流架构演进
----------------------------------------

传统静态计算图（如静态 ONNX 或早期 TensorFlow Graph）在面对以下工程场景时存在严重的结构性缺陷：

1. **分支选择与显存空转**：在两路模型切换器（Switch Model）中，用户根据布尔条件选择加载 SDXL 还是 Flux.1。静态图必须把两路模型全部从磁盘加载至显存，即使其中一路永远不会被调用；
2. **复合节点黑盒抽象**：用户希望将“文本编码 + 采样 + VAE解码”打包为一个可复用的单一复合节点（Macro Node）。静态图无法在执行期动态裂变展开为细粒度底层算子；
3. **条件式结果阻断**：若前置质量评估算子（如 NSFW 检测或清晰度评分）未达标，工作流需要阻断后续昂贵的放大修复（Upscale）或磁盘存储（SaveImage），同时不能导致整个调度器进程抛出未捕获异常而崩溃。

ComfyUI 通过**按需动态图重构（On-Demand Dynamic Graph Morphing）**彻底解决了上述矛盾，其核心设计理念是在拓扑消解过程中引入运行时可变连接（Elastic Links）与瞬态节点注入（Ephemeral Node Injection）。

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                                 Static Graph Construction (Add Outputs)                            |
   |           Add output nodes -> Trace upstream -> IGNORE links marked as 'lazy'                     |
   +----------------------------------------------------------------------------------------------------+
                                                     |
                                                     v
   +----------------------------------------------------------------------------------------------------+
   |                                    Staged Node Execution (execute())                               |
   +----------------------------------------------------------------------------------------------------+
                                 |                                           |
                    [Has 'check_lazy_status']                   [Returns 'expand' Subgraph]
                                 v                                           v
   +---------------------------------------------+   +--------------------------------------------------+
   | Query Node: which inputs are actually needed?|   | Generate Ephemeral Nodes with unique prefix      |
   | Promote lazy link -> 'make_input_strong_link'|  | Inject into DynamicPrompt (ephemeral_prompt)     |
   | Add upstream subtree -> blockCount increments|  | Scope nested cache via HierarchicalCache         |
   | State: ExecutionResult.PENDING               |  | State: ExecutionResult.PENDING                   |
   | Action: unstage_node_execution()             |  | Action: unstage_node_execution()                 |
   +---------------------------------------------+   +--------------------------------------------------+
                                 |                                           |
                                 +---------------------+---------------------+
                                                       |
                                                       v
   +----------------------------------------------------------------------------------------------------+
   |                              Resume Parent Node upon Dependency Resolution                         |
   +----------------------------------------------------------------------------------------------------+

------------------------------------------------------------------------

2. 惰性输入计算协议（check_lazy_status）与动态拓扑挂载
-------------------------------------------------------

2.1 惰性输入槽的元数据声明
~~~~~~~~~~~~~~~~~~~~~~~~~~

在节点类的 ``INPUT_TYPES()`` 契约中，输入槽可以通过附加 ``"lazy": True`` 标记为惰性依赖：

.. code-block:: python

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "select_index": ("INT", {"default": 0, "min": 0, "max": 1}),
            },
            "optional": {
                "branch_a": ("IMAGE", {"lazy": True}),
                "branch_b": ("IMAGE", {"lazy": True}),
            }
        }

在 ``TopologicalSort.add_node`` 初始逆向图构建阶段，引擎显式检测输入槽的 ``lazy`` 属性：

.. code-block:: python

    _, _, input_info = self.get_input_info(unique_id, input_name)
    is_lazy = input_info is not None and "lazy" in input_info and input_info["lazy"]
    # 若未指定 include_lazy 且当前槽位为 lazy，则不将上游节点纳入 pending 待执行队列
    if include_lazy or not is_lazy:
        if not self.is_cached(from_node_id):
            node_ids.append(from_node_id)
        links.append((from_node_id, from_socket, unique_id))

这意味着，未被激活的惰性分支在初始阶段完全处于“拓扑隐形”状态，其上游繁重的加载与采样算子根本不会进入执行序列。

2.2 运行时状态探测与强依赖提升（``make_input_strong_link``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当该节点的所有非惰性入参（如控制条件 ``select_index``）准备就绪并被调度器提取执行时，``execute()`` 优先调用节点的 ``check_lazy_status`` 方法：

.. code-block:: python

    if lazy_status_present:
        v3_data_lazy = v3_data.copy()
        v3_data_lazy["create_dynamic_tuple"] = True
        # 异步调用节点的 check_lazy_status，传入当前已就绪的常量与非惰性输入
        required_inputs = await _async_map_node_over_list(
            prompt_id, unique_id, obj, input_data_all, "check_lazy_status", 
            allow_interrupt=True, v3_data=v3_data_lazy
        )
        required_inputs = await resolve_map_node_over_list_results(required_inputs)
        required_inputs = set(sum([r for r in required_inputs if isinstance(r, list)], []))
        
        # 筛选出当前尚未计算且确实缺失的输入槽
        required_inputs = [x for x in required_inputs if isinstance(x, str) and (
            x not in input_data_all or x in missing_keys
        )]
        
        if len(required_inputs) > 0:
            for i in required_inputs:
                # 将惰性连线动态提升为强依赖连线（Strong Link）
                execution_list.make_input_strong_link(unique_id, i)
            # 当前节点挂起，返回 PENDING 状态
            return (ExecutionResult.PENDING, None, None)

2.3 状态机回退与入度重平衡
~~~~~~~~~~~~~~~~~~~~~~~~~~

当 ``make_input_strong_link`` 被触发时，底层执行了以下两步原子操作：

1. **子树挂载**：调用 ``self.add_node(from_node_id)``，将对应上游分支的全部祖先算子递归拉入 ``pendingNodes``，建立常规阻塞关系；
2. **入度增量**：将目标节点的 ``blockCount[unique_id]`` 累加对应前驱数量，使其重新变为非就绪态。

主调度循环捕获到 ``ExecutionResult.PENDING`` 后，调用 ``execution_list.unstage_node_execution()`` 清空 ``staged_node_id``，释放 CPU 控制权去优先调度新挂载的上游算子。当上游计算完毕并将其入度递减回 0 时，该节点将再次被提取执行，此时所需分支的张量已全部就绪。

------------------------------------------------------------------------

3. 瞬态子图展开（Ephemeral Subgraph Expansion）
-----------------------------------------------

为了支持复杂节点在执行期动态裂变展开为子图（如 ControlNet 预处理器链、高级迭代细化器），ComfyUI 设计了瞬态子图机制。

3.1 GraphBuilder 与命名空间隔离
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

子图的生成依赖 ``comfy_execution/graph_utils.py`` 中的 ``GraphBuilder``。为了杜绝子图节点 ID 与宿主图产生冲突，ComfyUI 采用了三段式命名空间前缀分配算法：

.. code-block:: python

    @classmethod
    def alloc_prefix(cls, root=None, call_index=None, graph_index=None):
        if root is None:
            root = GraphBuilder._default_prefix_root
        if call_index is None:
            call_index = GraphBuilder._default_prefix_call_index
        if graph_index is None:
            graph_index = GraphBuilder._default_prefix_graph_index
        result = f"{root}.{call_index}.{graph_index}."
        GraphBuilder._default_prefix_graph_index += 1
        return result

例如，ID 为 ``"12"`` 的宏节点在第 0 轮调用展开时，其内部生成的节点 ID 将被自动加冠前缀 ``"12.0.0.1"``、``"12.0.0.2"``。

3.2 DynamicPrompt 瞬态节点注入与双向映射
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当算子返回 ``{"expand": new_graph, "result": node_outputs}`` 时，``execute()`` 将子图注入 ``DynamicPrompt``：

.. code-block:: python

    for node_id, node_info in new_graph.items():
        new_node_ids.append(node_id)
        display_id = node_info.get("override_display_id", unique_id)
        # 注册瞬态节点，并记录其父节点与可视化前端映射
        dynprompt.add_ephemeral_node(node_id, node_info, unique_id, display_id)
        
        class_type = node_info["class_type"]
        class_def = nodes.NODE_CLASS_MAPPINGS[class_type]
        if hasattr(class_def, 'OUTPUT_NODE') and class_def.OUTPUT_NODE == True:
            new_output_ids.append(node_id)

.. list-table:: 瞬态子图映射路由机制
   :widths: 25 35 40
   :header-rows: 1

   * - 路由方法
     - 输入节点 ID
     - 递归解析物理目标
   * - ``get_real_node_id(node_id)``
     - 瞬态子节点（如 ``"12.0.0.3"``）
     - 沿 ``ephemeral_parents`` 递归追溯至最顶层的宿主真实静态节点 ID（``"12"``）。
   * - ``get_display_node_id(node_id)``
     - 瞬态子节点（如 ``"12.0.0.3"``）
     - 沿 ``ephemeral_display`` 递归映射至前端 UI 上实际高亮渲染的节点 ID。

3.3 层级缓存隔离（HierarchicalCache）与结果缝合
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了防止瞬态子节点的缓存与主图发生污染，``HierarchicalCache`` 自动为父节点构建独立的子缓存域（Subcache）：

.. code-block:: python

    for cache in caches.all:
        subcache = await cache.ensure_subcache_for(unique_id, new_node_ids)
        subcache.clean_unused()

展开完成后，父节点将自身标记为 ``PENDING`` 并将输出依赖注册至 ``pending_subgraph_results``。当所有瞬态子节点执行完毕后，父节点在下一次迭代中通过 ``execution_list.get_cache(source_node, unique_id)`` 提取子图叶子节点的计算张量，并打包为父节点的最终输出返回给下游。

------------------------------------------------------------------------

4. 条件控制流执行熔断器（ExecutionBlocker）
-------------------------------------------

在数据流驱动体系中，若某个分支由于条件判定不满足需要被终止，抛出异常会直接破坏整个工作流执行。ComfyUI 设计了轻量级的 ``ExecutionBlocker`` 哨兵对象。

4.1 ExecutionBlocker 语义定义
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    class ExecutionBlocker:
        def __init__(self, message):
            self.message = message

- **带消息阻断（``message is not None``）**：代表发生了业务逻辑上的显式阻断。调度器通过 WebSocket 广播 ``execution_error`` 事件，向前端展示提示信息；
- **静默剪枝阻断（``message is None``）**：代表正常的条件分支跳过。调度器不报错，静默向下游传播阻断状态。

4.2 算子执行层的 O(1) 剪枝代数
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``_async_map_node_over_list`` 内部，每次调用算子函数前都会进行入参阻断扫描：

.. code-block:: python

    execution_block = None
    for k, v in inputs.items():
        if input_is_list:
            for e in v:
                if isinstance(e, ExecutionBlocker):
                    v = e
                    break
        if isinstance(v, ExecutionBlocker):
            execution_block = execution_block_cb(v) if execution_block_cb else v
            break

    if execution_block is not None:
        # 直接追加阻断对象，短路跳过实际 Python 函数调用与 GPU Tensor 计算！
        results.append(execution_block)
    else:
        # 正常执行算子前向计算
        result = f(**inputs)
        results.append(result)

.. note:: 物理剪枝开销分析
   当上游节点输出了 ``ExecutionBlocker`` 时，下游连接的无论多么复杂的算子（例如消耗 10GB 显存的 KSampler 或耗时的 VAE Decode），其前向逻辑函数均不会被执行。调度器在 Python 层面直接以 :math:`\mathcal{O}(1)` 的极小开销将阻断哨兵传递给下游，直至图的末端，实现了极其高效的死分支短路。

------------------------------------------------------------------------

5. 控制流机制与数据结构全景对照表
----------------------------------

.. list-table:: ComfyUI 动态控制流核心组件物理特性对照
   :widths: 20 20 30 30
   :header-rows: 1

   * - 机制名称
     - 触发阶段
     - 核心数据载体
     - 系统性能与显存收益
   * - 惰性求值 (Lazy Eval)
     - 拓扑构建与节点执行前
     - ``"lazy": True``, ``check_lazy_status``, ``make_input_strong_link``
     - 完全避免未命中分支模型的磁盘读取与 GPU 显存分配，节省数百 MB 至数十 GB 显存。
   * - 瞬态子图展开 (Subgraphs)
     - 节点前向执行期
     - ``GraphBuilder``, ``add_ephemeral_node``, ``HierarchicalCache``
     - 实现复合宏节点、循环迭代展开，提供模块化封装与独立的局部缓存命名空间。
   * - 执行熔断器 (ExecutionBlocker)
     - 节点入参分发期
     - ``ExecutionBlocker``, ``execution_block_cb``
     - :math:`\mathcal{O}(1)` 短路跳过未激活分支的下游深度学习计算，杜绝无效 CUDA 核函数发射。
