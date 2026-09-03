========================================================================
第 1 模块：有向无环图调度与执行引擎 (01_execution_and_scheduler)
========================================================================

.. toctree::
   :maxdepth: 2
   :caption: 模块章节目录

   01_prompt_executor_and_dag
   02_node_caching_and_dirty_tracking
   03_lazy_evaluation_and_subgraph_expansion
   04_prompt_queue_and_async_dispatcher

模块架构概述
============

本模块深入剖析 ComfyUI 的核心大脑——动态有向无环图（DAG）调度与执行引擎。

ComfyUI 的核心计算模型不是固化的序列执行，而是基于数据流驱动的拓扑求解系统。整个调度引擎围绕 ``PromptExecutor``、``ExecutionList``、``DynamicPrompt`` 以及 ``BasicCache`` 等核心数据结构构建：

1. **DAG 拓扑排序与状态机**：解析用户提交的 Prompt JSON，通过入度统计与依赖追踪构建动态拓扑序，依据前端用户体验启发式算法选择就绪节点。
2. **多级哈希缓存与脏状态追踪**：利用 ``CacheKeySetInputSignature`` 生成包含前序祖先节点拓扑、节点输入常数及 ``IS_CHANGED`` 动态指纹的确定性签名，实现跨 Prompt 毫秒级增量执行。
3. **惰性求值与子图展开**：支持条件分支的延迟输入解析（``check_lazy_status``）与节点内部动态展开临时子图（Ephemeral Nodes），实现复杂的动态控制流。
4. **异步任务队列与熔断保护**：基于优先队列 ``PromptQueue`` 与条件变量实现非阻塞的多任务调度，提供原子的中断控制与显存 OOM 自愈熔断。
