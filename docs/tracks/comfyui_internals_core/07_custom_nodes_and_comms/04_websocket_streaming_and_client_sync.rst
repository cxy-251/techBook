========================================================================
WebSocket 异步二进制/JSON 事件流式广播与前端全双工实时同步
========================================================================

.. note:: 前置背景与上下文承接
   在前三节中，我们系统剖析了 ComfyUI 的经典 V1 节点反射协议（``01_custom_node_protocol_and_registration.rst``）、面向对象强类型 V3 API（``02_v3_api_and_typing_architecture.rst``）以及基于 aiohttp 的 RESTful 服务端架构（``03_server_and_rest_api_layer.rst``）。然而，生成式 AI 的推理过程具有典型的长耗时（秒级至分钟级）、分阶段步进（数十步采样）以及高频中间状态（去噪潜空间预览）等特征。传统的 HTTP 单向请求-响应模型无法支撑细粒度的执行进度反馈、节点动态高亮以及毫秒级潜空间图像流式回传。ComfyUI 在 ``server.py`` 中构建了一套高吞吐、全双工、二进制与 JSON 混合编码的 **WebSocket 异步事件总线（WebSocket Event Bus）**。作为全书正文的最终完结篇，本节全面解剖其线程安全发布-订阅机制、二进制帧封装协议、执行状态机全生命周期广播以及断线重连状态恢复机制。

------------------------------------------------------------------------

1. WebSocket 异步全双工总线架构与线程安全消息队列
--------------------------------------------------

在 ComfyUI 的物理架构中，底层任务执行由独立的后台工作线程（``PromptExecutor`` 线程）驱动，而网络 I/O 则由主线程的 ``asyncio`` 事件循环全权接管。为了在多线程与异步协程之间建立零阻塞、无锁竞争的安全通信通道，``PromptServer`` 构建了双层消息管道。

其架构拓扑与数据流动管线如下图所示：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                          Backend Worker Thread (PromptExecutor 执行线程)                           |
   |                                                                                                    |
   |   - 采样步进更新: k_callback()                                                                      |
   |   - 节点流转跳跃: execute()                                                                        |
   |   - 潜变量预览生成: TAESD.decode()                                                                 |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      | 跨线程安全投递: PromptServer.instance.send_sync(event, data, sid)
                                      | loop.call_soon_threadsafe(self.messages.put_nowait, ...)
                                      v
   +----------------------------------------------------------------------------------------------------+
   |                      Async Event Loop Main Thread (asyncio 事件循环主线程)                          |
   |                                                                                                    |
   |   +--------------------------------------------------------------------------------------------+   |
   |   |                           self.messages: asyncio.Queue (异步缓冲队列)                      |   |
   |   +--------------------------------------------------------------------------------------------+   |
   |                                      |                                                             |
   |                                      | publish_loop() 持续消费                                     |
   |                                      v                                                             |
   |   +--------------------------------------------------------------------------------------------+   |
   |   |                            PromptServer.send(event, data, sid) 分发路由器                   |   |
   |   +--------------------------------------------------------------------------------------------+   |
   |                     |                                              |                               |
   |     isinstance(data, bytes/bytearray)?              isinstance(data, dict/json)?                   |
   |                     |                                              |                               |
   |                     v                                              v                               |
   |   【二进制帧编码 (Binary Frame)】                 【文本 JSON 帧编码 (Text JSON Frame)】          |
   |   - struct.pack(">I", event_type) + Payload       - {"type": event, "data": data}                  |
   +----------------------------------------------------------------------------------------------------+
                                      |                                 |
                                      +────────────────+────────────────+
                                                       |
                                                       v
   +----------------------------------------------------------------------------------------------------+
   |                        Client WebSocket Connections (self.sockets: dict[sid, ws])                   |
   |                                                                                                    |
   |   ──> Client A (WebUI Session 1: sid="a1b2...")  ─── [全双工实时同步 /progress, /executing]         |
   |   ──> Client B (WebUI Session 2: sid="c3d4...")  ─── [接收广播事件 /status]                         |
   |   ──> Client C (API Headless:   sid="e5f6...")  ─── [定向接收二进制图像流 PREVIEW_IMAGE]            |
   +----------------------------------------------------------------------------------------------------+

1.1 跨线程安全投递（``send_sync``）机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了防止工作线程直接操作异步 Socket 导致的事件循环死锁或线程竞争异常，``PromptServer.send_sync()`` 采用事件循环安全调度：

.. code-block:: python

    def send_sync(self, event, data, sid=None):
        # 将消息原子推入 asyncio.Queue，由事件循环自身调度消费
        self.loop.call_soon_threadsafe(
            self.messages.put_nowait, (event, data, sid)
        )

1.2 异步广播发布循环（``publish_loop``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

服务启动时，主事件循环常驻运行 ``publish_loop()`` 协程：

.. code-block:: python

    async def publish_loop(self):
        while True:
            # 异步非阻塞等待新事件
            msg = await self.messages.get()
            # 触发多客户端广播或定向推送
            await self.send(*msg)

------------------------------------------------------------------------

2. 双协议分发机制：JSON 控制事件与二进制大对象（Binary Blob）
--------------------------------------------------------------

ComfyUI 的 WebSocket 通信在物理传输层严格划分为 **UTF-8 文本 JSON 帧** 与 **大端序紧凑二进制帧（Binary Frames）**。

2.1 结构化 JSON 控制事件规范
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

所有工作流生命周期控制事件均打包为统一的 JSON 格式：``{"type": "<event_name>", "data": { ... }}``。

.. list-table:: ComfyUI 核心 WebSocket JSON 事件全生命周期契约
   :widths: 22 28 50
   :header-rows: 1

   * - 事件名称 (type)
     - 载荷字段结构 (data)
     - 物理触发时机与前端响应语义
   * - ``status``
     - ``{"status": {"exec_info": {"queue_remaining": N}}, "sid": "..."}``
     - 队列状态变动时广播。前端更新右上角剩余任务计数器与当前连接 Session ID。
   * - ``execution_start``
     - ``{"prompt_id": "<uuid>"}``
     - 执行引擎正式从队列提取该 Prompt 并启动 DAG 拓扑执行。前端重置进度条与历史高亮。
   * - ``execution_cached``
     - ``{"nodes": ["3", "4"], "prompt_id": "<uuid>"}``
     - 静态哈希命中缓存。通知前端直接将命中的历史节点标记为完成态，跳过物理执行。
   * - ``executing``
     - ``{"node": "5", "display_node": "5", "prompt_id": "<uuid>"}``
     - 算子计算前夕广播。前端画布使当前正在运行的节点产生动态发光边框（Highlight Animation）。若 ``node: null`` 则表示全图执行完毕。
   * - ``progress``
     - ``{"value": 12, "max": 20, "prompt_id": "<uuid>", "node": "3"}``
     - 采样器单步迭代完成时广播。前端更新进度条百分比与步数指示器。
   * - ``executed``
     - ``{"node": "9", "output": {"images": [...]}, "prompt_id": "<uuid>"}``
     - 节点执行成功并产出输出。前端将生成的图片、文本或潜变量元数据挂载至对应节点的 UI 控件。
   * - ``execution_error``
     - ``{"prompt_id": "...", "node_id": "...", "exception_message": "...", "traceback": [...]}``
     - 发生不可恢复异常（如 CUDA OOM、输入非法）。前端弹出红屏错误对话框并精确定位出错节点。
   * - ``execution_interrupted``
     - ``{"prompt_id": "...", "node_id": "...", "executed": [...]}``
     - 用户点击 Cancel 触发原子中断。前端恢复待机态并保留已执行完成的部分节点成果。
   * - ``b_index``
     - ``{"b_index": 0, "prompt_id": "<uuid>"}``
     - 批处理（Batch）多图生成时广播当前正在处理的图片子索引。

2.2 紧凑二进制协议（Binary Frame Protocol）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

若通过 Base64 字符串在 JSON 中传输实时去噪预览图，会带来 **33% 的网络带宽膨胀** 与沉重的 CPU 编解码开销。ComfyUI 定义了基于大端序（Big-Endian）整数头的紧凑二进制协议：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                          Type 1: PREVIEW_IMAGE (标准图像预览二进制帧)                              |
   |                                                                                                    |
   |   0                   4                   8                                                        |
   |   +-------------------+-------------------+----------------------------------------------------+   |
   |   | Event Type (uint32| Image Type(uint32)|            Compressed Image Binary Payload         |   |
   |   |   Value = 1 (>I)  |  1=JPEG / 2=PNG   |               (JPEG / PNG 图像字节流)              |   |
   |   +-------------------+-------------------+----------------------------------------------------+   |
   +----------------------------------------------------------------------------------------------------+
   |                          Type 3: TEXT (关联节点的二进制流式文本)                                    |
   |                                                                                                    |
   |   0                   4                   8                   8 + L                                |
   |   +-------------------+-------------------+-------------------+--------------------------------+   |
   |   | Event Type (uint32| Node ID Len(uint32|  Node ID (UTF-8)  |        Raw Text Payload        |   |
   |   |   Value = 3 (>I)  |    Length = L     |     "node_id"     |     (控制台日志 / LLM 流式输出)   |   |
   |   +-------------------+-------------------+-------------------+--------------------------------+   |
   +----------------------------------------------------------------------------------------------------+
   |                          Type 4: PREVIEW_IMAGE_WITH_METADATA (含元数据预览帧)                      |
   |                                                                                                    |
   |   0                   4                   8                   8 + M                                |
   |   +-------------------+-------------------+-------------------+--------------------------------+   |
   |   | Event Type (uint32| Meta Len (uint32) | Meta JSON (UTF-8) | Image Type (>I) |  Image Bytes |   |
   |   |   Value = 4 (>I)  |    Length = M     |   {"step": 10...} |   1=JPEG/2=PNG  |  (图像字节流)|   |
   |   +-------------------+-------------------+-------------------+--------------------------------+   |
   +----------------------------------------------------------------------------------------------------+

在 ``PromptServer.encode_bytes()`` 中，首部 4 字节被严格固化为事件类型整型头：

.. code-block:: python

    def encode_bytes(self, event, data):
        if not isinstance(event, int):
            raise RuntimeError(f"Binary event types must be integers, got {event}")
        # 打包大端序 32 位无符号整型 (4 字节)
        packed = struct.pack(">I", event)
        message = bytearray(packed)
        message.extend(data)
        return message

前端 JavaScript 接收到 ``ArrayBuffer`` 后，直接通过 ``DataView.getUint32(0)`` 读取前 4 字节确定事件类型，随后使用 ``URL.createObjectURL(new Blob([data.slice(8)], {type: 'image/jpeg'}))`` 实现**零内存拷贝的高速画布渲染**。

------------------------------------------------------------------------

3. 实时潜空间预览（TAESD）与流式推送链路
----------------------------------------

在扩散采样循环中，带噪潜变量 :math:`x_t` 无法直接呈现为人类可理解的图像。若在每一步调用完整的庞大 VAE 解码器（占用数 GB 显存并耗费数十毫秒），将严重拖慢采样速度。

ComfyUI 引入了轻量级专用神经解码器——**TAESD（Tiny AutoEncoder for Stable Diffusion）**：

.. code-block:: text

   Sampler Step (KSampler)
      │
      ├──> 每步产出预测纯净潜变量 x0: [1, 4, 64, 64] (SD1.5) 或 [1, 16, 128, 128] (Flux)
      │
      v
   TAESD 极速解码引擎 (显存开销 < 50MB, 推理耗时 < 3ms)
      │
      ├──> 极速前向: RGB_Tensor = TAESD_Decoder(x0)
      ├──> 降采样与裁剪: ImageOps.contain(PIL_Image, (max_size, max_size))
      ├──> 内存压缩: PIL_Image.save(BytesIO, format="JPEG", quality=95)
      │
      v
   PromptServer.instance.send_image(("JPEG", PIL_Image, max_size))
      │
      ├──> 组装 Type 1 二进制帧: struct.pack(">II", 1, 1) + jpeg_bytes
      └──> WebSocket.send_bytes() ──[ 毫秒级广播 ]──> 前端画布节点实时显示去噪进程

------------------------------------------------------------------------

4. 会话管理、多客户端隔离与容灾重连机制
----------------------------------------

4.1 客户端 Session 隔离（``clientId``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

每个连接到服务端的 Web 前端均携带全局唯一的 ``clientId``（通过 URL 查询参数 ``/ws?clientId=<uuid>``）。

在 ``PromptServer.websocket_handler()`` 中：

.. code-block:: python

    sid = request.rel_url.query.get('clientId', '')
    if sid:
        # 若存在旧连接则无缝踢出并复用 Session
        self.sockets.pop(sid, None)
    else:
        sid = uuid.uuid4().hex

    self.sockets[sid] = ws
    self.sockets_metadata[sid] = {"feature_flags": {}}

当用户在多标签页或多终端提交任务时，服务端既支持全局广播（``sid=None``），也支持精准将图片结果只推回发起提交的特定客户端（``sid=target_sid``），实现了多用户、多会话的严格隔离。

4.2 断线重连与执行状态自愈（Reconnection State Sync）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当网络发生瞬时抖动导致 WebSocket 连接断开重连时，前端若盲目等待下一次执行，会导致 UI 丢失当前正在运行的节点状态。

ComfyUI 实现了精巧的**重连即时同步机制**：

.. code-block:: python

    # 1. 立即同步当前队列剩余任务信息
    await self.send("status", {"status": self.get_queue_info(), "sid": sid}, sid)

    # 2. 若重连客户端正是当前执行作业的所属发起者，立即重发正在执行的节点 ID
    if self.client_id == sid and self.last_node_id is not None:
        await self.send("executing", {"node": self.last_node_id}, sid)

这使得前端在断网重连后能够在 **1 毫秒内瞬间恢复节点动态高亮与进度条显示**，达成完全无缝的用户体验。

4.3 特性标志双向协商（Feature Flags Handshake）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了实现跨版本服务端与前端的向后兼容，WebSocket 连接建立后的第一包协议固定为**特性标志握手协议**：

1. 客户端发送：``{"type": "feature_flags", "data": {"supports_v3_api": true, "subgraphs": true}}``；
2. 服务端在 ``self.sockets_metadata[sid]`` 中持久化该客户端能力集，并回传服务端支持的特性列表；
3. 后续调度器根据客户端协商结果，自动选择降级向后兼容格式或启用最新的二进制流式特性。

------------------------------------------------------------------------

5. 全书架构全景与技术脉络终极总结
----------------------------------

随着本节的落盘，我们完整遍历了《ComfyUI 节点式流处理引擎内核架构与调度体系深度剖析》全书 7 大模块、28 节核心架构体系。下表总结了驱动整个引擎运转的物理层级全景脉络：

.. list-table:: 《ComfyUI 节点式流处理引擎内核架构与调度体系深度剖析》技术全景总览
   :widths: 18 25 27 30
   :header-rows: 1

   * - 核心系统模块
     - 核心代码实体
     - 关键技术突破与物理抽象
     - 系统架构定位
   * - **第 1 模块：DAG 执行引擎**
     - ``PromptExecutor`` / ``PromptQueue``
     - 因果拓扑哈希、RAMPressureCache 内存压力回收、动态子图惰性展开
     - 全局任务调度中枢与图计算执行引擎
   * - **第 2 模块：显存与卸载管理**
     - ``model_management`` / ``AIMDO``
     - 四级 VRAM 状态机、动态 LRU 驱逐、Pinned Memory 流式 DMA、CUDA OOM 熔断自愈
     - 异构计算硬件资源虚拟化与显存安全守卫
   * - **第 3 模块：模型修补与 Hook**
     - ``ModelPatcher`` / ``calculate_weight``
     - 浅拷贝克隆树、LoRA/DoRA 在线差分代数、洋葱圈 Wrapper、时间步关键帧 Hook
     - 零内存开销的多分支模型动态微调与计算图劫持中枢
   * - **第 4 模块：扩散与 DiT 骨干**
     - ``BaseModel`` / ``Flux`` / ``ControlNet``
     - 双层解耦抽象、零配置签名嗅探、双流/单流 MMDiT、多维 RoPE、零卷积残差挂载
     - 统一支持多代生成模型与多模态空间引导的骨干抽象层
   * - **第 5 模块：采样微分方程**
     - ``CFGGuider`` / ``k_diffusion``
     - 自适应条件装箱、Karras 幂次曲率对齐、Rescale CFG 方差校准、高阶 ODE/SDE 求解
     - 数值积分与生成流形收敛核心数学引擎
   * - **第 6 模块：文本与潜空间**
     - ``CLIP`` / ``T5`` / ``AutoencoderKL``
     - 77-Token 长文本 Chunking、双编码器表征空间对齐、Tiled VAE 边缘羽化融合
     - 跨模态语义映射与像素-潜变量高保真编解码转换底座
   * - **第 7 模块：节点与通信生态**
     - ``PromptServer`` / ``_ComfyNodeInternal``
     - V1/V3 强类型反射契约、aiohttp 异步微服务、全双工 WebSocket 二进制流式总线
     - 插件生态扩展规范与现代化前后端实时交互通信底座

------------------------------------------------------------------------

小结与全书结语
==============

本节系统剖析了 ComfyUI 的通信底座——基于 WebSocket 的全双工异步事件流式广播体系：

1. **线程安全消息管道**：解剖了 ``send_sync`` 与 ``asyncio.Queue`` 的跨线程非阻塞投递机制；
2. **双协议帧规范**：推导了 10 种标准 JSON 控制事件与基于大端序整型头的紧凑二进制帧协议；
3. **极速潜空间预览**：解析了 TAESD 毫秒级去噪图像流式推送链路；
4. **会话隔离与状态自愈**：阐明了基于 ``clientId`` 的多用户隔离与断线重连 1ms 状态即时恢复机制。

至此，**《ComfyUI 节点式流处理引擎内核架构与调度体系深度剖析》全书 7 大核心模块、共 28 节深度专著章节全部圆满结稿！**
