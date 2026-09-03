========================================================================
自定义节点协议标准（NODE_CLASS_MAPPINGS/INPUT_TYPES）与动态注册机制
========================================================================

.. note:: 前置背景与上下文承接
   在全书的前六个模块中，我们深入剖析了 ComfyUI 的 DAG 调度器（第 1 模块）、异构显存生命周期管理（第 2 模块）、模型权重动态修补（第 3 模块）、扩散与 DiT 骨干架构（第 4 模块）、ODE/SDE 采样数值求解器（第 5 模块）以及文本编码与潜空间 VAE 重构（第 6 模块）。这些精密的底层计算引擎之所以能够组装成千变万化的工作流，完全依赖于 ComfyUI 统一、声明式且高度解耦的**节点抽象契约（Node Protocol Contract）**。ComfyUI 的生态繁荣与数十万第三方插件的无缝集成，根植于 ``nodes.py`` 中建立的 V1 节点类协议与动态扩展加载器。本节系统解密 ``NODE_CLASS_MAPPINGS``、``INPUT_TYPES`` 拓扑签名、缓存脏标记 ``IS_CHANGED``、汇聚端点 ``OUTPUT_NODE`` 以及动态导入机制的底层物理实现。

------------------------------------------------------------------------

1. 声明式节点类契约（Declarative Node Protocol Contract）
---------------------------------------------------------

在 ComfyUI 的经典架构中，任何计算节点本质上都是一个遵循**特定类属性与静态方法签名契约**的 Python 原生类。执行引擎（``PromptExecutor``）与 Web 前端通过反射（Reflection）提取这些元数据以构建 UI 控件与计算图。

其核心协议架构如下图所示：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                                 ComfyUI 声明式节点类协议 (Node Contract)                             |
   +----------------------------------------------------------------------------------------------------+
   |                                                                                                    |
   |   @classmethod INPUT_TYPES(cls) ──> 定义输入槽位与 UI 控件属性 (required, optional, hidden)         |
   |   RETURN_TYPES                  ──> 定义输出槽位类型元组 ("IMAGE", "LATENT", "MODEL"...)            |
   |   RETURN_NAMES                  ──> (可选) 用户可见的输出引脚名称 ("samples", "images"...)          |
   |   FUNCTION                      ──> 节点实例化后前向执行的目标方法名称 ("encode", "sample"...)       |
   |   CATEGORY                      ──> 前端右键菜单与目录树层级 ("model/loaders", "image/transform")   |
   |   OUTPUT_NODE = True / False    ──> 标记是否为 DAG 终点汇聚节点 (Sink Node, 触发主动执行)            |
   |   @classmethod IS_CHANGED(...)  ──> 动态脏状态探测与哈希签名计算 (绕过静态缓存)                     |
   |   @classmethod VALIDATE_INPUTS  ──> 图提交前的前置参数有效性静态校验                                 |
   |                                                                                                    |
   +----------------------------------------------------------------------------------------------------+
                                      |
                                      | 导出至全局符号表
                                      v
   +----------------------------------------------------------------------------------------------------+
   |   NODE_CLASS_MAPPINGS        = { "MyNodeID": MyNodeClass }                                         |
   |   NODE_DISPLAY_NAME_MAPPINGS = { "MyNodeID": "Human Readable Node Title" }                         |
   +----------------------------------------------------------------------------------------------------+

1.1 ``INPUT_TYPES`` 签名规范与类型系统
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``INPUT_TYPES`` 是一个返回嵌套字典的类方法，包含三个标准顶级键：

.. list-table:: ``INPUT_TYPES`` 字典顶级结构规范
   :widths: 18 32 50
   :header-rows: 1

   * - 字典键名
     - 数据类型与语义
     - 引擎调度与 UI 呈现行为
   * - ``"required"``
     - ``dict[str, tuple[Type, dict]]``
     - **必需输入**。所有在工作流中执行该节点必须连接或填写的槽位，缺失将导致 DAG 拓扑校验失败中断。
   * - ``"optional"``
     - ``dict[str, tuple[Type, dict]]``
     - **可选输入**。若未连接连线，引擎执行该方法时传入 ``None`` 或默认值。
   * - ``"hidden"``
     - ``dict[str, str]``
     - **系统隐藏注水上下文**。由引擎在运行时隐式注入的元数据，前端画布不可见连线。

1.2 输入项元组结构与控件配置
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

每个输入字段的定义为二元组：``(SlotType, ConfigDict)``。

- **基础标量与控件**：
  * ``"INT"`` / ``"FLOAT"``：配置数值范围与步进 ``{"default": 20, "min": 1, "max": 10000, "step": 1}``；
  * ``"STRING"``：配置单行/多行输入 ``{"default": "", "multiline": True, "dynamicPrompts": True}``；
  * ``"BOOLEAN"``：布尔开关 ``{"default": True}``；
  * ``list[str]``（下拉枚举 COMBO）：如 ``(["euler", "heun", "dpmpp_2m"], {"default": "euler"})``。
- **复合引用数据类型**：
  * ``"MODEL"``（``comfy.model_patcher.ModelPatcher``）；
  * ``"CLIP"``（``comfy.sd.CLIP``）；
  * ``"VAE"``（``comfy.sd.VAE``）；
  * ``"IMAGE"``（四维图像张量 :math:`[B, H, W, C] \in [0.0, 1.0]`）；
  * ``"MASK"``（三维掩码张量 :math:`[B, H, W] \in [0.0, 1.0]`）；
  * ``"LATENT"``（字典结构 ``{"samples": Tensor, "noise_mask": Optional[Tensor]}``）；
  * ``"CONDITIONING"``（条件张量与属性字典链表 ``list[list[Tensor, dict]]``）。

1.3 系统隐藏注入槽位（Hidden Injections）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于需要感知全局上下文的特殊节点（如保存图像、动态路由），可通过 ``"hidden"`` 声明以下系统注入项：

- ``"prompt"``（``"PROMPT"``）：当前执行的完整 JSON Prompt 字典；
- ``"extra_pnginfo"``（``"EXTRA_PNGINFO"``）：工作流元数据（Workflow UI 坐标拓扑）；
- ``"unique_id"``（``"UNIQUE_ID"``）：当前节点在图中的唯一字符串 Node ID（如 ``"12"``）；
- ``"dynprompt"``（``"DYNPROMPT"``）：动态子图变异后的最新 Prompt 状态机。

------------------------------------------------------------------------

2. 关键协议标志与生命周期方法
-----------------------------

除了输入输出类型声明外，ComfyUI 协议定义了一系列控制节点计算行为的核心协议标志与类方法。

2.1 ``OUTPUT_NODE`` 汇聚触发器
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在第 1 模块中我们讨论过，ComfyUI 采用逆向广度优先搜索（BFS）从终端节点反向构建执行序列：

.. math::

   \mathcal{V}_{	ext{active}} = \bigcup_{v \in \mathcal{V}, \, 	ext{is\_output}(v)} 	ext{Ancestors}(v)

只有类属性声明了 ``OUTPUT_NODE = True`` 的节点（如 ``SaveImage``、``PreviewImage``、``SaveLatent``），才会被调度器选定为 DAG 遍历的根节点。普通中间节点即使在画布上存在，若其下游未连接至任何 ``OUTPUT_NODE``，将被整图剪枝彻底跳过计算。

2.2 ``IS_CHANGED`` 动态缓存失效探测
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

默认情况下，节点缓存键由其所有输入槽位的值/连线上游输出对象的内存哈希计算得出。但在某些场景下（如从磁盘加载外部文件、随机数发生器、摄像头实时流），节点输入参数未变但输出物理状态已发生改变。

节点可通过声明 ``IS_CHANGED`` 类方法覆盖默认静态哈希计算：

.. code-block:: python

    class LoadImage:
        @classmethod
        def IS_CHANGED(cls, image):
            image_path = folder_paths.get_annotated_filepath(image)
            # 计算目标物理文件的 SHA-256 哈希作为动态指纹
            m = hashlib.sha256()
            with open(image_path, 'rb') as f:
                m.update(f.read())
            return m.digest().hex()

- 若 ``IS_CHANGED`` 返回与上次执行相同的字符串/数值，复用已有缓存；
- 若返回不同值，或返回 ``float("nan")``（如非确定性随机发生器），强制标记该节点为脏状态（Dirty State），迫使节点及其所有下游子图重新执行计算。

2.3 ``VALIDATE_INPUTS`` 静态图拓扑拦截
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在提示词提交给执行器之前，服务器会在 API 路由层调用 ``VALIDATE_INPUTS``：

.. code-block:: python

    @classmethod
    def VALIDATE_INPUTS(cls, latent):
        if not folder_paths.exists_annotated_filepath(latent):
            return f"Invalid latent file: {latent}"
        return True

若校验方法返回字符串错误提示，服务器立即返回 HTTP 400 状态码并拒绝排队，避免无效任务进入 GPU 执行队列浪费算力。

------------------------------------------------------------------------

3. 节点协议核心规范全景对照
----------------------------

.. list-table:: ComfyUI 节点类协议全量属性与方法规范
   :widths: 22 25 23 30
   :header-rows: 1

   * - 协议属性 / 方法名
     - 签名与数据类型
     - 是否必需
     - 物理功能与系统影响
   * - ``INPUT_TYPES``
     - ``@classmethod (cls) -> dict``
     - **必需**
     - 定义必需、可选与隐藏输入槽位，生成前端 Widget 控件与后端校验规则。
   * - ``RETURN_TYPES``
     - ``tuple[str, ...]``
     - **必需**
     - 定义输出端点的数据类型契约，供前端连线类型检查与类型推导使用。
   * - ``FUNCTION``
     - ``str``
     - **必需**
     - 指定前向执行的方法名，引擎实例化后通过 ``getattr(instance, FUNCTION)(**kwargs)`` 调用。
   * - ``CATEGORY``
     - ``str``
     - 推荐
     - 斜杠分隔的分类路径，决定节点在 UI 菜单与节点搜索树中的归属。
   * - ``OUTPUT_NODE``
     - ``bool`` (默认 ``False``)
     - 可选
     - 标记为终端汇聚节点，成为 DAG 逆向遍历起点；为 ``True`` 时返回值可包含 ``{"ui": ...}``。
   * - ``IS_CHANGED``
     - ``@classmethod (cls, **kwargs) -> Any``
     - 可选
     - 动态脏状态探测，返回哈希字符串或 ``NaN`` 强制触发缓存失效重算。
   * - ``VALIDATE_INPUTS``
     - ``@classmethod (cls, **kwargs) -> bool | str``
     - 可选
     - 图提交前静态校验，返回错误字符串阻断非法请求排队。
   * - ``OUTPUT_IS_LIST``
     - ``tuple[bool, ...]``
     - 可选
     - 标记指定输出槽位为列表展开模式，支持单次前向输出动态长度批次。
   * - ``INPUT_IS_LIST``
     - ``bool`` (默认 ``False``)
     - 可选
     - 启用后入参自动汇聚为 Python ``list``，用于批量迭代或跨批次合并操作。

------------------------------------------------------------------------

4. 扩展包自动发现与动态导入管道（Extension Discovery & Import Pipeline）
-------------------------------------------------------------------------

ComfyUI 在服务启动期间通过 ``init_extra_nodes()``（位于 ``nodes.py``）执行三级自动扫描与动态加载：

.. code-block:: text

   init_extra_nodes() 启动扫描链路
       |
       ├── 1. init_builtin_extra_nodes()  ──> 扫描并加载 comfy_extras/nodes_*.py (官方内置扩展)
       |
       ├── 2. init_builtin_api_nodes()    ──> 扫描并加载 comfy_api_nodes/nodes_*.py (官方 REST/V3 扩展)
       |
       └── 3. init_external_custom_nodes() ──> 遍历 custom_nodes/ 目录下的第三方插件包

4.1 插件加载器（``load_custom_node``）物理实现
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``load_custom_node()`` 中，ComfyUI 利用 Python 的 ``importlib.util`` 实现了进程内动态模块加载与命名空间隔离：

.. code-block:: python

    async def load_custom_node(module_path: str, ignore=set(), module_parent="custom_nodes") -> bool:
        module_name = get_module_name(module_path)
        # 为目录型包或单文件脚本构造唯一 sys.modules 键名
        if os.path.isfile(module_path):
            module_spec = importlib.util.spec_from_file_location(module_name, module_path)
            module_dir = os.path.split(module_path)[0]
        else:
            module_spec = importlib.util.spec_from_file_location(
                module_path.replace(".", "_x_"), os.path.join(module_path, "__init__.py")
            )
            module_dir = module_path

        # 动态编译与执行模块代码
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[module_spec.name] = module
        module_spec.loader.exec_module(module)

        # 1. 注册前端 Web 静态资源目录
        if hasattr(module, "WEB_DIRECTORY") and module.WEB_DIRECTORY is not None:
            web_dir = os.path.abspath(os.path.join(module_dir, module.WEB_DIRECTORY))
            if os.path.isdir(web_dir):
                EXTENSION_WEB_DIRS[module_name] = web_dir

        # 2. V1 经典节点注册：合并全局映射表
        if hasattr(module, "NODE_CLASS_MAPPINGS") and module.NODE_CLASS_MAPPINGS is not None:
            for name, node_cls in module.NODE_CLASS_MAPPINGS.items():
                if name not in ignore:
                    NODE_CLASS_MAPPINGS[name] = node_cls
                    # 动态注入模块源路径属性，便于溯源与调试
                    node_cls.RELATIVE_PYTHON_MODULE = f"{module_parent}.{get_module_name(module_path)}"
            if hasattr(module, "NODE_DISPLAY_NAME_MAPPINGS"):
                NODE_DISPLAY_NAME_MAPPINGS.update(module.NODE_DISPLAY_NAME_MAPPINGS)
            return True

4.2 性能监控与异常隔离机制
~~~~~~~~~~~~~~~~~~~~~~~~~~

为了防止劣质第三方插件拖慢启动或引发服务崩溃，加载器实现了**毫秒级耗时监控与沙盒异常捕获**：

1. **导入耗时统计**：通过 ``time.perf_counter()`` 记录每个插件的解析时间，在终端打印耗时排行，方便开发者定位阻塞源；
2. **异常熔断**：用 ``try...except`` 包裹整个导入过程。当某个插件因依赖缺失（如 ``ModuleNotFoundError``）崩溃时，系统记录 Traceback 并打印 ``(IMPORT FAILED)`` 警告，但**绝不终止主进程启动**，确保核心系统的高可用性。

------------------------------------------------------------------------

小结与下章导读
==============

本节系统剖析了 ComfyUI 经典节点协议与动态注册底座：

1. **声明式契约规范**：拆解了 ``INPUT_TYPES``、``RETURN_TYPES``、``FUNCTION`` 与 ``CATEGORY`` 的标准定义；
2. **调度控制原语**：推导了 ``OUTPUT_NODE`` 对 DAG 逆向遍历的触发作用，以及 ``IS_CHANGED`` 动态指纹与 ``VALIDATE_INPUTS`` 预检拦截机制；
3. **动态发现与导入管线**：解剖了基于 ``importlib`` 的模块动态加载、前端静态目录挂载（``WEB_DIRECTORY``）与故障隔离沙盒。

虽然经典 V1 节点协议简洁直观，但其依赖松散的字符串类型映射，缺乏编译期类型安全与模式校验。在接下来的 **第 7 模块第 2 节（``02_v3_api_and_typing_architecture.rst``）** 中，我们将深入剖析 ComfyUI 现代演进的核心——**V3 API 面向对象节点范式与 Schema 类型校验系统**（``_ComfyNodeInternal`` / ``io.Combo`` / ``ComfyExtension``）。
