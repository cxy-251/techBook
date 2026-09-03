========================================================================
aiohttp 异步 Web 服务端架构、路由注册与 RESTful 提示词提交控制流
========================================================================

.. note:: 前置背景与上下文承接
   在前两节中，我们深入剖析了 ComfyUI 的经典 V1 节点反射协议（``01_custom_node_protocol_and_registration.rst``）与新一代面向对象强类型 V3 API（``02_v3_api_and_typing_architecture.rst``）。然而，节点算子与执行引擎并不能脱离宿主环境孤立运行——无论是 Web 画布图形界面、云端微服务无头（Headless）推理，还是自动化批量作业流水线，均需要一个高并发、低延迟、具备严密安全边界的通信控制中枢。ComfyUI 基于 Python 原生异步框架 ``asyncio`` 与 ``aiohttp`` 构建了单例 HTTP 服务端——``PromptServer``（定义于 ``server.py``）。本节系统解密其异步 Web 服务端架构、多层中间件安全防护、双重路由前缀镜像派发、提示词提交（``/prompt``）全生命周期校验流水线，以及静态多媒体资源的非阻塞 I/O 处理。

------------------------------------------------------------------------

1. aiohttp 异步 Web 服务端架构与中间件流水线
--------------------------------------------

``PromptServer`` 采用单例模式（Singleton）管理整个 ComfyUI 进程的网络生命周期，其底层深度融合了 ``asyncio`` 异步事件循环与 ``aiohttp.web.Application``。

其核心架构拓扑与中间件流水线如下图所示：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                                     PromptServer 核心异步架构                                      |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      v
   +----------------------------------------------------------------------------------------------------+
   |                                aiohttp 中间件流水线 (Middlewares Pipeline)                           |
   |                                                                                                    |
   |   [Request 入口]                                                                                   |
   |         │                                                                                          |
   |         ├──> 1. cache_control: 静态资源与动态 JSON 响应头缓存控制策略                                 |
   |         ├──> 2. deprecation_warning: 捕获 /scripts/ui 与 /extensions/core/ 废弃旧路径访问               |
   |         ├──> 3. compress_body: 对 application/json 与 text/plain 实施 Gzip 动态响应压缩              |
   |         ├──> 4. cors_middleware / origin_only_middleware: 跨域访问控制与回环 Host/Origin 防跨站伪造     |
   |         └──> 5. block_external_middleware: 实施严格的 Content-Security-Policy (CSP) 脚本与框架隔离    |
   |         │                                                                                          |
   |         v                                                                                          |
   |   [Route Handler 业务路由分发]                                                                     |
   +----------------------------------------------------------------------------------------------------+
                                      |
        +─────────────────────────────+─────────────────────────────+
        |                             |                             |
        v                             v                             v
   【RESTful 业务路由表】        【子应用聚合 (Sub-Apps)】     【WebSocket 实时双工总线】
   - /prompt (工作流提交)        - /internal (内部私有路由)     - /ws (JSON 与二进制流式推送)
   - /api/jobs (现代作业管理)    - /assets (资产哈希管理)
   - /object_info (节点反射)     - UserManager / ModelManager
   - /system_stats (硬件负载)    - SubgraphManager
   - /view & /upload (媒体流)    - NodeReplaceManager

1.1 中间件安全防护机制规范
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: PromptServer 核心中间件功能与安全职责
   :widths: 22 28 50
   :header-rows: 1

   * - 中间件名称
     - 拦截阶段与条件
     - 物理安全与性能职责
   * - ``origin_only_middleware``
     - 存在 ``Host`` 与 ``Origin`` 头
     - 校验回环地址（Loopback）下 Host 与 Origin 是否严格一致，封死外部恶意网页对本地 127.0.0.1 发起静默 POST 注入的 CSRF 漏洞。
   * - ``compress_body``
     - 响应体体积 > 阈值且支持 Gzip
     - 对巨型 JSON（如包含数百个节点完整 Schema 的 ``/object_info``）进行实时 Gzip 压缩，网络传输体积缩减 80% 以上。
   * - ``deprecation_warning``
     - 请求匹配废弃前端路径
     - 记录并单次打印旧版 API 访问告警，推动第三方生态平滑迁移。
   * - ``block_external_middleware``
     - ``--disable-api-nodes`` 开启
     - 注入严格的 CSP 响应头（``default-src 'self'``），杜绝 Web 前端加载外部不可信脚本或发起越权外连。

1.2 服务端多地址监听与 TLS 加密初始化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

ComfyUI 在 ``PromptServer.start_multi_address()`` 中支持多 IP/端口并发绑定与可选 TLS 传输层加密：

.. code-block:: python

    async def start_multi_address(self, addresses, call_on_start=None, verbose=True):
        runner = web.AppRunner(self.app, access_log=None)
        await runner.setup()
        ssl_ctx = None
        scheme = "http"

        # 配置双向/单向 TLS 证书链
        if args.tls_keyfile and args.tls_certfile:
            ssl_ctx = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS_SERVER, verify_mode=ssl.CERT_NONE)
            ssl_ctx.load_cert_chain(certfile=args.tls_certfile, keyfile=args.tls_keyfile)
            scheme = "https"

        for addr in addresses:
            address, port = addr[0], addr[1]
            site = web.TCPSite(runner, address, port, ssl_context=ssl_ctx)
            await site.start()

------------------------------------------------------------------------

2. 双重路由前缀镜像与核心元数据反射
------------------------------------

为了同时兼容经典前端直连与现代微服务网关代理（Reverse Proxy），ComfyUI 采用了独特的**双重前缀镜像注册技术**。

2.1 路由自动派发与 ``/api`` 前缀镜像
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``PromptServer.add_routes()`` 中，所有注册到主路由表 ``self.routes`` 的接口均会被自动克隆一份并挂载 ``/api`` 前缀：

.. code-block:: python

    api_routes = web.RouteTableDef()
    for route in self.routes:
        if isinstance(route, web.RouteDef):
            # 将例如 /prompt 自动克隆注册为 /api/prompt
            api_routes.route(route.method, "/api" + route.path)(route.handler, **route.kwargs)
    self.app.add_routes(api_routes)
    self.app.add_routes(self.routes)

这使得前端开发服务器（如 Vite Dev Server）能够以统一的 ``/api/*`` 规则将所有后端调用一键转发，而静态文件路由仍保持在根路径。

2.2 核心系统状态与节点元数据反射 API
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: ComfyUI 核心系统与元数据查询端点
   :widths: 22 28 50
   :header-rows: 1

   * - HTTP 路由端点
     - 请求方法与响应格式
     - 接口职责与物理数据源
   * - ``/object_info``
     - ``GET`` (JSON)
     - 全量节点反射接口。遍历 ``NODE_CLASS_MAPPINGS``，生成所有节点的输入、输出、参数取值范围与 Tooltip 说明。
   * - ``/object_info/{node_class}``
     - ``GET`` (JSON)
     - 单节点元数据定向查询，用于动态加载或轻量按需渲染。
   * - ``/system_stats``
     - ``GET`` (JSON)
     - 硬件监控端点。探测操作系统平台、CPU/RAM 剩余量、PyTorch 版本以及所有 GPU 设备的物理显存（``vram_total`` / ``vram_free``）。
   * - ``/features``
     - ``GET`` (JSON)
     - 特性标志（Feature Flags）协商端点。返回服务端支持的扩展能力集（如动态子图、自定义资产）。
   * - ``/embeddings`` / ``/models``
     - ``GET`` (JSON)
     - 查询磁盘上已挂载的 Text Inversion 词嵌入与各目录下的物理模型文件列表。

------------------------------------------------------------------------

3. 提示词提交控制流（``POST /prompt`` Pipeline）
------------------------------------------------

``POST /prompt`` 是外部客户端向 ComfyUI 提交执行任务的唯一主入口。一个合法的图执行请求在进入队列前必须经过严格的**六阶段流水线验证**。

其执行阶段流转图如下所示：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                                    POST /prompt 提示词提交流水线                                    |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      | 1. JSON 反序列化与生命周期拦截
                                      v
   +----------------------------------------------------------------------------------------------------+
   |   Stage 1: trigger_on_prompt()                                                                     |
   |   - 广播执行 on_prompt_handlers 钩子列表 (供第三方插件审查或改写 Prompt 数据)                         |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      | 2. 编号分配与任务排队优先级计算
                                      v
   +----------------------------------------------------------------------------------------------------+
   |   Stage 2: Number & Priority Allocation                                                            |
   |   - 提取自增全局任务号 self.number                                                                  |
   |   - 若包含 "front": true 则置为负数 (number = -number)，使其在优先队列中直达队首插队                 |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      | 3. UUID 生成与幂等性校验
                                      v
   +----------------------------------------------------------------------------------------------------+
   |   Stage 3: Prompt ID Validation                                                                    |
   |   - 校验客户端传入的 prompt_id (必须符合规范 UUID 格式)；若未提供则服务端生成 uuid4()                 |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      | 4. 历史版本节点无损迁移
                                      v
   +----------------------------------------------------------------------------------------------------+
   |   Stage 4: node_replace_manager.apply_replacements(prompt)                                         |
   |   - 扫描工作流，基于 NodeReplace 规则表在内存中静默重写过时的废弃节点与参数映射                     |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      | 5. 异步 DAG 拓扑有效性静态校验
                                      v
   +----------------------------------------------------------------------------------------------------+
   |   Stage 5: await execution.validate_prompt(prompt_id, prompt, targets)                             |
   |   - 检查节点类是否存在、必选输入是否连接/有效、类型是否匹配                                         |
   |   - 提取需要执行的最终输出节点集合 outputs_to_execute                                              |
   |   - 若失败: 立即返回 HTTP 400 + node_errors 错误字典                                               |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      | 6. 敏感数据脱敏与原子入队
                                      v
   +----------------------------------------------------------------------------------------------------+
   |   Stage 6: Queue Enqueue & Response                                                                |
   |   - 剥离 SENSITIVE_EXTRA_DATA_KEYS 敏感信息至隔离字典                                              |
   |   - 压入优先队列: prompt_queue.put((number, prompt_id, prompt, extra_data, outputs, sensitive))    |
   |   - 返回 HTTP 200: {"prompt_id": prompt_id, "number": number, "node_errors": {}}                   |
   +----------------------------------------------------------------------------------------------------+

3.1 核心入队代码与敏感数据隔离
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    @routes.post("/prompt")
    async def post_prompt(request):
        json_data = await request.json()
        json_data = self.trigger_on_prompt(json_data)

        # 分配任务优先级序号
        if "number" in json_data:
            number = float(json_data['number'])
        else:
            number = self.number
            if json_data.get('front', False):
                number = -number  # 负数优先级直达队首
            self.number += 1

        prompt = json_data.get("prompt")
        prompt_id = validate_job_id(json_data.get("prompt_id")) if "prompt_id" in json_data else str(uuid.uuid4())

        # 执行旧节点自动迁移与静态拓扑校验
        self.node_replace_manager.apply_replacements(prompt)
        valid = await execution.validate_prompt(prompt_id, prompt, json_data.get("partial_execution_targets"))

        if valid[0]:
            outputs_to_execute = valid[2]
            extra_data = json_data.get("extra_data", {})
            sensitive = {}
            # 隔离敏感字段 (如 API Key)，防止状态广播泄漏
            for k in execution.SENSITIVE_EXTRA_DATA_KEYS:
                if k in extra_data:
                    sensitive[k] = extra_data.pop(k)

            extra_data["create_time"] = int(time.time() * 1000)
            self.prompt_queue.put((number, prompt_id, prompt, extra_data, outputs_to_execute, sensitive))
            return web.json_response({"prompt_id": prompt_id, "number": number, "node_errors": valid[3]})
        else:
            return web.json_response({"error": valid[1], "node_errors": valid[3]}, status=400)

------------------------------------------------------------------------

4. 作业生命周期管理与队列控制接口
----------------------------------

4.1 现代作业分页查询接口（``GET /api/jobs``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了满足企业级调度与前端任务面板的需求，ComfyUI 引入了统一作业层（``comfy_execution.jobs``）：

.. code-block:: python

    @routes.get("/api/jobs")
    async def get_jobs(request):
        # 提取状态过滤 (pending, in_progress, completed, failed)、排序与分页参数
        running, queued = self.prompt_queue.get_current_queue_volatile()
        history = self.prompt_queue.get_history()

        jobs, total = get_all_jobs(
            _remove_sensitive_from_queue(running),
            _remove_sensitive_from_queue(queued),
            history,
            status_filter=status_filter,
            limit=limit,
            offset=offset
        )
        return web.json_response({'jobs': jobs, 'pagination': {'offset': offset, 'limit': limit, 'total': total}})

4.2 幂等中断与队列删除控制
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 队列控制与中断端点行为规范
   :widths: 22 28 50
   :header-rows: 1

   * - HTTP 路由端点
     - 请求方法与入参
     - 执行语义与原子保证
   * - ``/interrupt``
     - ``POST`` (``{"prompt_id": "<uuid>"}``)
     - 中断控制。若指定 ``prompt_id``，仅当中断目标与当前正在执行的 Prompt 完全一致时触发 ``interrupt_processing()``，杜绝竞态误杀后续任务。
   * - ``/api/jobs/{job_id}/cancel``
     - ``POST``
     - 单作业幂等取消。若处于队列中则执行原子出队，若正在运行则触发中断，已完成任务返回 ``{"cancelled": false}`` 而不报错。
   * - ``/queue``
     - ``POST`` (``{"clear": true, "delete": [...]}``)
     - 队列批处理操作。清空等待队列或按 ID 删除指定挂起项。
   * - ``/free``
     - ``POST`` (``{"unload_models": true, "free_memory": true}``)
     - 强制显存释放。通知队列工作线程触发深度垃圾回收与模型卸载。

------------------------------------------------------------------------

5. 静态多媒体资源非阻塞 I/O 与安全流式传输
------------------------------------------

图像的上传与查看是生成式流处理系统的核心高频 I/O 操作。

5.1 图像上传哈希去重与安全路径约束（``/upload/image``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``image_upload()`` 中，系统首先对文件路径施加严格的安全屏障：

.. code-block:: python

    # 1. 杜绝路径穿越漏洞 (Directory Traversal Attack)
    filepath = os.path.abspath(os.path.join(full_output_folder, filename))
    if os.path.commonpath((upload_dir, filepath)) != upload_dir:
        return web.Response(status=400)

    # 2. 哈希比对去重 (BLAKE3/SHA256)
    if os.path.exists(filepath):
        if compare_image_hash(filepath, image):
            image_is_duplicate = True  # 相同内容直接复用，避免磁盘冗余写入

5.2 图像流式查看、通道分离与 XSS 防护（``/view``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``GET /view`` 中，服务端根据查询参数动态完成实时图像处理：

1. **通道分离与合并（Channel Slicing）**：
   * ``channel=rgb``：实时提取 RGB 三通道并丢弃 Alpha 通道；
   * ``channel=a``：实时提取 Alpha 遮罩图并转换为灰度 PNG 返回；
2. **快速动态缩略图生成（Preview Transcoding）**：
   * ``preview=webp;80``：实时利用 PIL 将大图等比压缩为低带宽 WebP 格式回传给前端节点缩略图展示；
3. **存储型 XSS（Stored XSS）主动防御**：
   对于易携带恶意脚本的活跃 MIME 类型（如 SVG、HTML、XML），服务端强制设置响应头 ``X-Content-Type-Options: nosniff`` 并将 ``Content-Disposition`` 设为 ``attachment``，阻断浏览器直接内嵌执行。

------------------------------------------------------------------------

小结与下章导读
==============

本节系统剖析了 ComfyUI 异步 Web 服务端与 RESTful 路由层的核心机理：

1. **异步架构与安全中间件**：解析了基于 ``aiohttp`` 的单例服务、CSP 隔离以及 Host/Origin 防跨站伪造机制；
2. **双重路由镜像系统**：阐明了标准路由与 ``/api`` 前缀镜像派发的设计哲学；
3. **提示词提交全生命周期**：推导了从参数捕获、优先级分配、自动迁移、静态 DAG 校验到脱敏入队的六阶段流水线；
4. **作业控制与安全 I/O**：拆解了幂等中断调度、多媒体哈希去重、动态通道切片与 XSS 安全传输规范。

在下一节（``04_websocket_streaming_and_client_sync.rst``）中，我们将迎来第 7 模块及全书正文的最终完结篇——**WebSocket 流式事件总线与前端全双工实时同步**：全面解剖 JSON 控制事件与二进制大对象（Binary Blob）通信协议规范，深入剖析执行进度广播、TAESD 潜空间图像实时流式推送以及长连接心跳容灾重连机制。
