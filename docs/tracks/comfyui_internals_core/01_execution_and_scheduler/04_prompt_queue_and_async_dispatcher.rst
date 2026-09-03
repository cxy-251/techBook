========================================================================
PromptQueue 优先队列调度、线程安全条件变量与跨线程中断熔断机制
========================================================================

.. note:: 前置背景与上下文承接
   在前三节中，我们由浅入深剖析了单次工作流执行的计算内核：从有向无环图的动态拓扑消解（``01_prompt_executor_and_dag.rst``）、全链路因果祖先缓存树（``02_node_caching_and_dirty_tracking.rst``），到惰性分支求值与瞬态子图展开（``03_lazy_evaluation_and_subgraph_expansion.rst``）。然而，在工业级部署与多客户端交互场景中，ComfyUI 必须作为一个常驻系统服务，持续处理并发提交、任务插队、实时进度推送、强制中断与显存回收。本节作为第 1 模块的收官之作，深入 ``execution.py``、``server.py`` 与 ``main.py``，解剖由主线程 Asyncio 网络事件循环与后台专用工作者线程（Worker Thread）构成的异构并发底座，详述基于优先堆的 ``PromptQueue`` 调度模型、条件变量同步原语、原子级任务取消与跨线程异常熔断机制。

------------------------------------------------------------------------

1. 异构并发模型：Asyncio 事件循环与工作者线程解耦
-------------------------------------------------

在 Python 全局解释器锁（GIL）与 PyTorch 显存管理的物理现实约束下，如果将网络 I/O、WebSocket 通信与重度深度学习计算混杂在单一线程中，会导致两个致命瓶颈：

1. **网络事件与心跳阻塞**：扩散模型采样（如 KSampler）在 GPU 上执行密集 CUDA 核函数计算时，虽然大部分计算在设备端，但主机 CPU 端的主循环依然会阶段性持有 GIL。若单线程运行，前端 WebSocket 连接将因无法及时响应握手而频繁超时断开；
2. **CUDA 上下文与线程绑定**：PyTorch 的部分底层资源、CUDA 流及内存分配器在跨协程异步切换时极易引发上下文竞争或隐蔽死锁。

ComfyUI 采用了**主从分离的双层异构架构**：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                          Main Thread: Asyncio Event Loop (aiohttp Server)                          |
   |   - REST API Handlers (/prompt, /queue, /interrupt, /history)                                      |
   |   - WebSocket Full-Duplex Stream (/ws: status, executing, progress, executed, preview)            |
   |   - Thread-safe Message Queue (server.messages: asyncio.Queue)                                    |
   +----------------------------------------------------------------------------------------------------+
                                      |                                   ^
                           put() / interrupt()             send_sync() / call_soon_threadsafe
                                      v                                   |
   +----------------------------------------------------------------------------------------------------+
   |                        PromptQueue (Shared Thread-Safe Synchronization Medium)                     |
   |   - Priority Min-Heap (heapq)                                                                      |
   |   - Mutual Exclusion Lock (threading.RLock) & Condition Variable (threading.Condition)            |
   |   - Running Registry (currently_running) & Bounded History (10,000 items)                          |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                  get() / task_done()
                                      v
   +----------------------------------------------------------------------------------------------------+
   |                       Worker Thread (Daemon): prompt_worker Loop                                   |
   |   - Blocking Queue Polling with Dynamic GC Timeout (threading.Condition.wait)                     |
   |   - Dedicated Asyncio Event Loop for Node Execution (asyncio.run(PromptExecutor.execute_async))   |
   |   - Memory Pressure Response & Idle Periodic Garbage Collection (gc.collect + soft_empty_cache)    |
   +----------------------------------------------------------------------------------------------------+

1.1 跨线程无锁化消息泵（``send_sync``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当工作者线程中的算子需要向前端推送进度或执行状态时，不能直接操作主线程的 WebSocket 异步连接。``PromptServer`` 提供了基于事件循环线程安全投递的消息泵：

.. code-block:: python

    def send_sync(self, event, data, sid=None):
        # 利用 asyncio 事件循环的 call_soon_threadsafe 跨线程投递消息至异步队列
        self.loop.call_soon_threadsafe(
            self.messages.put_nowait, (event, data, sid)
        )

主线程中的 ``publish_loop`` 协程则持续从 ``self.messages`` 读取并异步广播给目标 WebSocket 客户端，彻底解耦了算子计算与网络 I/O。

------------------------------------------------------------------------

2. PromptQueue 优先堆拓扑与调度算法
------------------------------------

``PromptQueue`` 是所有工作流任务调度的物理中枢。它基于 Python 的 ``heapq`` 实现最小优先堆，确保任务严格按优先级顺序调度。

2.1 任务元组结构与插队机制
~~~~~~~~~~~~~~~~~~~~~~~~~~

每个进入队列的任务都被封装为一个 6 元组：

.. math::

   T = \big(	ext{number}, 	ext{prompt\_id}, 	ext{prompt\_dict}, 	ext{extra\_data}, 	ext{outputs\_to\_execute}, 	ext{sensitive\_data}\big)

.. list-table:: PromptQueue 任务元组字段与物理意义
   :widths: 20 20 60
   :header-rows: 1

   * - 字段名称
     - 类型定义
     - 调度作用机制
   * - ``number``
     - ``float``
     - 堆排序主键。常规任务递增分配（``self.number += 1``，实现 FIFO）；插队任务取负（``number = -self.number``，直接置于堆顶）。
   * - ``prompt_id``
     - ``str`` (UUID4)
     - 全局唯一工作流标识符。
   * - ``prompt_dict``
     - ``dict``
     - 经过语义校验与节点替换后的完整 DAG 结构字典。
   * - ``extra_data``
     - ``dict``
     - 执行附带上下文（客户端 ID、创建时间戳、实时预览配置等）。
   * - ``outputs_to_execute``
     - ``list[str]``
     - 本次需要实际拉取执行的目标输出节点 ID 列表。
   * - ``sensitive_data``
     - ``dict``
     - 敏感认证信息（如 API 密钥、授权 Token），在任务落入历史前被剥离。

2.2 线程安全入队与条件变量唤醒（``put``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    def put(self, item):
        with self.mutex:
            # 维持二叉最小堆不变量
            heapq.heappush(self.queue, item)
            # 通知前端队列状态已更新
            self.server.queue_updated()
            # 唤醒阻塞在 not_empty 条件变量上的工作者线程
            self.not_empty.notify()

2.3 工作者线程阻塞提取与活跃任务登记（``get``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

工作者线程通过条件变量挂起，避免 CPU 空转自旋（Spin-Waiting）：

.. code-block:: python

    def get(self, timeout=None):
        with self.not_empty:
            while len(self.queue) == 0:
                self.not_empty.wait(timeout=timeout)
                if timeout is not None and len(self.queue) == 0:
                    return None
            item = heapq.heappop(self.queue)
            i = self.task_counter
            # 深度拷贝登记至 currently_running，供并发查询与原子取消探测
            self.currently_running[i] = copy.deepcopy(item)
            self.task_counter += 1
            self.server.queue_updated()
            return (item, i)

------------------------------------------------------------------------

3. 原子级任务中断与取消机制
---------------------------

在长时间推理（如 100 步高清迭代或超大视频生成）过程中，用户随时可能点击“Interrupt”取消任务。若中断逻辑存在时序竞争（Race Condition），可能导致用户原本想要取消任务 A，却因为任务 A 恰好在毫秒级间隙结束，而将中断信号错误传递给了刚开始执行的任务 B。

ComfyUI 在 ``PromptQueue`` 中实现了**互斥锁保护下的原子级精准中断**：

3.1 目标中断（``interrupt_if_running``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    def interrupt_if_running(self, prompt_id):
        with self.mutex:
            for item in self.currently_running.values():
                if item[1] == prompt_id:
                    # 仅在目标 prompt_id 确实处于活跃运行态时设置全局中断标志
                    nodes.interrupt_processing()
                    return True
        return False

3.2 算子执行期的中断检查点（Checkpointing）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

设置中断标志后，引擎在两个关键物理切入点进行主动探测，抛出 ``InterruptProcessingException``：

1. **节点调度前置检查（``before_node_execution``）**：在 ``_async_map_node_over_list`` 启动任何节点函数前执行；
2. **采样进度回调钩子（``hijack_progress``）**：在 KSampler 内部每次迭代生成去噪步长后执行：

.. code-block:: python

    def throw_exception_if_processing_interrupted():
        global interrupt_processing_flag
        if interrupt_processing_flag:
            # 抛出专有中断异常，短路终止当前 Python 调用栈
            raise InterruptProcessingException()

3.3 中断状态隔离与熔断闭环
~~~~~~~~~~~~~~~~~~~~~~~~~~

当 ``InterruptProcessingException`` 抛出时：

.. code-block:: python

    except comfy.model_management.InterruptProcessingException as iex:
        logging.info("Processing interrupted")
        error_details = {"node_id": real_node_id}
        return (ExecutionResult.FAILURE, error_details, iex)

``PromptExecutor`` 捕获该专有异常，压制详细 Traceback 日志打印，并向客户端广播专用的 ``execution_interrupted`` 事件，而非通用的错误崩溃报文。在下一次执行启动时（``execute_async`` 首行），调度器调用 ``nodes.interrupt_processing(False)`` 重置中断标志，确保后续任务不受污染。

------------------------------------------------------------------------

4. 工作者循环的内存自愈与垃圾回收（GC）
---------------------------------------

在 ``main.py`` 的 ``prompt_worker`` 主循环中，除了调度任务，还集成了系统级显存与内存自愈管线：

.. code-block:: python

    while True:
        timeout = 1000.0
        if need_gc:
            timeout = max(gc_collect_interval - (current_time - last_gc_collect), 0.0)

        queue_item = q.get(timeout=timeout)
        if queue_item is not None:
            # 执行 Prompt 工作流...
            need_gc = True

        # 检查是否接收到强制显存清理标志
        flags = q.get_flags()
        free_memory = flags.get("free_memory", False)
        if flags.get("unload_models", free_memory):
            comfy.model_management.unload_all_models()
            need_gc = True
            last_gc_collect = 0

        # 空闲期触发周期性垃圾回收与显存碎片整理
        if need_gc:
            current_time = time.perf_counter()
            if (current_time - last_gc_collect) > gc_collect_interval:
                gc.collect()
                # 释放 PyTorch 未占用的显存池碎片（cudaEmptyCache）
                comfy.model_management.soft_empty_cache()
                last_gc_collect = current_time
                need_gc = False

------------------------------------------------------------------------

5. 调度体系核心类与方法对照表
------------------------------

.. list-table:: ComfyUI 异步调度与队列管理关键接口对照
   :widths: 25 25 50
   :header-rows: 1

   * - 类 / 函数名称
     - 所属模块
     - 核心功能与并发约束
   * - ``PromptQueue``
     - ``execution.py``
     - 线程安全优先堆队列管理器。封装 ``threading.RLock`` 与 ``Condition``，提供任务 FIFO/LIFO 调度与历史持久化。
   * - ``PromptServer.send_sync``
     - ``server.py``
     - 跨线程安全通信桥梁。通过 ``loop.call_soon_threadsafe`` 将工作者线程事件转发至主线程 WebSocket 消息泵。
   * - ``interrupt_if_running``
     - ``execution.py``
     - 原子级中断校验。在互斥锁保护下验证正在执行的任务 ID，消除并发取消的时序竞争。
   * - ``prompt_worker``
     - ``main.py``
     - 独立守护线程工作循环。负责阻塞拉取队列任务、拉起 ``PromptExecutor``、监控空闲期并触发显存碎片整理。
   * - ``soft_empty_cache``
     - ``model_management.py``
     - 显存碎片整理。在任务空闲期安全调用底层硬件 API 释放闲置显存块。

------------------------------------------------------------------------

小结与全模块总结
================

本节完成了第 1 模块“有向无环图调度与执行引擎”的技术闭环：

1. **异构双层架构**：Asyncio 主线程负责高吞吐网络 I/O 与 WebSocket 事件广播，专用工作者线程负责重度模型执行；
2. **优先堆调度**：``PromptQueue`` 基于最小堆与条件变量实现了高效的任务存取与秒级插队；
3. **原子中断与异常安全**：通过运行时断点探测与专用中断异常，杜绝了时序竞争与服务崩溃；
4. **自愈回收机制**：将执行生命周期与显存碎片整理（``soft_empty_cache``）紧密结合，奠定了长时间稳定运行的基础。

**第 1 模块全景回顾**：
至此，我们已经完整掌握了 ComfyUI 的计算图执行全貌——从 Prompt JSON 的逆向拓扑解析（01 节）、因果哈希签名与内存水压缓存（02 节）、动态惰性求值与瞬态子图展开（03 节），到多任务优先队列与异步并发分发（04 节）。

**下章导读（进入第 2 模块）**：
在掌握了计算图的调度逻辑后，下一个核心物理瓶颈是**硬件显存（VRAM）约束**。在第 2 模块《动态显存管理与模型卸载机制 (02_vram_and_offload_management)》的首节（``01_vram_state_and_device_tracking.rst``）中，我们将深入物理硬件底层，剖析 GPU 显存物理布局探测（``vram_state``）、多档位显存预算阈值划分与异构计算设备分配策略。
