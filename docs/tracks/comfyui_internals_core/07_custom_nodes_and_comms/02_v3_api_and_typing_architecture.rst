========================================================================
ComfyUI V3 API 面向对象节点范式与 Schema 类型校验系统
========================================================================

.. note:: 前置背景与上下文承接
   在前一节（``01_custom_node_protocol_and_registration.rst``）中，我们系统剖析了 ComfyUI 经典的 V1 声明式节点协议（``NODE_CLASS_MAPPINGS`` / ``INPUT_TYPES``）与模块动态导入管线。然而，经典 V1 协议严重依赖松散的嵌套字典、字符串类型标识符以及易受污染的类属性猴子补丁（Monkey Patching），在大规模工程协作与云原生微服务演进中暴露出**缺乏编译期类型安全、动态输入（如动态增行、条件槽位）拓展困难、无法进行严格的 Schema 静态校验**等局限。为此，ComfyUI 推出了新一代面向对象、强类型约束的 **V3 API（``comfy_api``）**。本节系统解密 ``ComfyNode`` 抽象基类、``io`` 强类型装饰器系统、``Schema`` 全生命周期校验、不可变类隔离（``lock_class``）以及动态泛型（``MatchType`` / ``Autogrow``）的底层物理实现。

------------------------------------------------------------------------

1. V3 API 设计哲学与面向对象抽象体系
------------------------------------

V3 API 的核心演进目标是：**将 V1 时代松散的元组与字典协议重构为严格的面向对象继承体系，在提供编译期 IDE 自动补全的同时，通过双向适配器保持对经典执行器与前端的 100% 向后兼容**。

其类继承体系与底层运行时交互如下图所示：

.. code-block:: text

   +----------------------------------------------------------------------------------------------------+
   |                                     ComfyUI V3 API 核心类层次图谱                                   |
   +----------------------------------------------------------------------------------------------------+
                                      _ComfyNodeInternal (execution.py 统一交互锚点)
                                             |
                                  _ComfyNodeBaseInternal (内部属性反射与 V1 兼容层)
                                             |
                                         ComfyNode (开发者自定义节点的基类)
                                             |
                  +──────────────────────────┴──────────────────────────+
                  |                                                     |
         [必选抽象方法]                                         [可选生命周期钩子]
         - define_schema(cls) -> Schema                         - validate_inputs(cls, **kwargs) -> bool|str
         - execute(cls, **kwargs) -> NodeOutput / coroutine     - fingerprint_inputs(cls, **kwargs) -> Any
                                                                - check_lazy_status(cls, **kwargs) -> list[str]

1.1 核心基类方法与生命周期契约
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``comfy_api.latest._io.py`` 中，所有 V3 节点均必须继承自 ``ComfyNode``，并实现以下核心抽象方法：

.. list-table:: V3 节点核心生命周期方法契约
   :widths: 22 25 25 28
   :header-rows: 1

   * - 方法名称
     - 类型签名
     - 是否必需
     - 对应 V1 协议语义与演进
   * - ``define_schema``
     - ``@classmethod (cls) -> Schema``
     - **必需**
     - 替代 ``INPUT_TYPES`` 与 ``RETURN_TYPES``，返回强类型、自校验的结构化 ``Schema`` 对象。
   * - ``execute``
     - ``@classmethod (cls, **kwargs) -> NodeOutput``
     - **必需**
     - 替代 ``FUNCTION`` 指定的动态方法，原生支持同步函数与 ``async def`` 异步协程。
   * - ``validate_inputs``
     - ``@classmethod (cls, **kwargs) -> bool | str``
     - 可选
     - 对应 V1 的 ``VALIDATE_INPUTS``，在图执行前拦截非法参数并返回错误详情。
   * - ``fingerprint_inputs``
     - ``@classmethod (cls, **kwargs) -> Any``
     - 可选
     - 对应 V1 的 ``IS_CHANGED``，计算动态物理指纹以精细控制缓存命中。
   * - ``check_lazy_status``
     - ``@classmethod (cls, **kwargs) -> list[str]``
     - 可选
     - 对应 V1 的惰性求值探测，返回当前步需要上游计算的输入引脚列表。

------------------------------------------------------------------------

2. 强类型 I/O 体系与 ``comfytype`` 装饰器
------------------------------------------

V3 API 废弃了 V1 时代脆弱的纯字符串类型约定（如 ``"IMAGE"`` / ``"MODEL"``），构建了基于 Python 类型注解与元类包装的 ``io`` 类型体系。

2.1 ``@comfytype`` 装饰器与类型注册
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``comfy_api/latest/_io.py`` 中，所有数据类型均通过 ``@comfytype`` 装饰器与底层执行引擎的 ``io_type`` 字符串绑定：

.. code-block:: python

    class _ComfyType(ABC):
        Type = Any
        io_type: str = None

    def comfytype(io_type: str, **kwargs):
        def decorator(cls: T) -> T:
            # 动态拷贝 Input 与 Output 内部类以隔离类间继承污染
            new_cls = cls
            if hasattr(new_cls, "Input"):
                new_cls.Input = copy_class(new_cls.Input)
            if hasattr(new_cls, "Output"):
                new_cls.Output = copy_class(new_cls.Output)
            new_cls.io_type = io_type
            if hasattr(new_cls, "Input") and new_cls.Input is not None:
                new_cls.Input.Parent = new_cls
            if hasattr(new_cls, "Output") and new_cls.Output is not None:
                new_cls.Output.Parent = new_cls
            return new_cls
        return decorator

2.2 标准内置类型与 Widget 控件映射
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: ComfyUI V3 标准强类型系统与 Python 物理类型映射
   :widths: 18 22 28 32
   :header-rows: 1

   * - V3 类型对象
     - 底层 ``io_type``
     - Python ``Type`` 提示
     - 构造参数与 UI 控件配置
   * - ``io.Int``
     - ``"INT"``
     - ``int``
     - ``default``, ``min``, ``max``, ``step``, ``display_mode`` (Number / Slider)
   * - ``io.Float``
     - ``"FLOAT"``
     - ``float``
     - ``default``, ``min``, ``max``, ``step``, ``round``, ``gradient_stops``
   * - ``io.String``
     - ``"STRING"``
     - ``str``
     - ``multiline``, ``placeholder``, ``default``, ``dynamic_prompts``
   * - ``io.Boolean``
     - ``"BOOLEAN"``
     - ``bool``
     - ``default``, ``label_on``, ``label_off``
   * - ``io.Combo``
     - ``"COMBO"``
     - ``str`` (或 ``Enum``)
     - ``options: list[str] | Enum``, ``upload``, ``image_folder``, ``remote``
   * - ``io.Image``
     - ``"IMAGE"``
     - ``torch.Tensor``
     - 空间张量 :math:`[B, H, W, C]`
   * - ``io.Mask``
     - ``"MASK"``
     - ``torch.Tensor``
     - 空间张量 :math:`[B, H, W]`
   * - ``io.Latent``
     - ``"LATENT"``
     - ``TypedDict(samples, ...)``
     - 潜变量字典封装
   * - ``io.Conditioning``
     - ``"CONDITIONING"``
     - ``list[tuple[Tensor, dict]]``
     - 文本/视觉引导条件列表
   * - ``io.Model``
     - ``"MODEL"``
     - ``ModelPatcher``
     - 动态权重修补代理对象
   * - ``io.Clip`` / ``io.Vae``
     - ``"CLIP"`` / ``"VAE"``
     - ``CLIP`` / ``VAE``
     - 文本分词编码器与变分自编码器对象

------------------------------------------------------------------------

3. 高级动态泛型：``MatchType``、``Autogrow`` 与 ``DynamicCombo``
----------------------------------------------------------------

V1 协议最难解决的工程痛点是**动态槽位变异**（例如：输入图像数量可动态增减、下拉菜单选中 A 方案时展示一组参数而选中 B 方案时展示另一组参数）。V3 API 原生引入了动态泛型原语：

3.1 ``MatchType`` 泛型多态约束
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``MatchType`` 允许节点的输出端点类型在连接建立时，**动态与指定输入端点的实际连线类型保持一致**（如万能类型转换器、通用路由节点）：

.. code-block:: python

    class UniversalSwitch(ComfyNode):
        @classmethod
        def define_schema(cls) -> Schema:
            template = io.MatchType.Template(
                template_id="any_data",
                allowed_types=[io.Image, io.Latent, io.Model, io.String]
            )
            return Schema(
                node_id="UniversalSwitch",
                inputs=[
                    io.Boolean.Input("switch", default=True),
                    io.MatchType.Input("input_a", template=template),
                    io.MatchType.Input("input_b", template=template),
                ],
                outputs=[
                    io.MatchType.Output(template=template, display_name="selected_data"),
                ]
            )

前端根据 ``template_id`` 在连线拖拽时执行实时的多态类型推导，彻底杜绝了非法类型连接。

3.2 ``Autogrow`` 动态自增长输入
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于多图拼接或多条件融合节点，``Autogrow`` 支持槽位随连线实时自增长：

.. code-block:: python

    io.Autogrow.Input(
        "images",
        template=io.Autogrow.TemplatePrefix(
            input=io.Image.Input("image"),
            prefix="image_",
            min=2,
            max=10
        )
    )

当用户在前端连接了 ``image_0`` 与 ``image_1`` 后，画布自动延展生成 ``image_2`` 供后续接入，而在后端执行期，系统通过 ``build_nested_inputs()`` 将所有离散前缀参数打包为整洁的字典或列表。

------------------------------------------------------------------------

4. Schema 静态声明与全生命周期校验
----------------------------------

4.1 ``Schema`` 结构体定义
~~~~~~~~~~~~~~~~~~~~~~~~~

``Schema`` 是 V3 节点的自描述元数据载体（定义于 ``comfy_api/latest/_io.py``）：

.. code-block:: python

    @dataclass
    class Schema:
        node_id: str                      # 全局唯一节点标识符
        display_name: str = None          # 用户可见标题
        category: str = "sd"              # 菜单层级目录
        inputs: list[Input] = field(...)  # 输入槽位列表
        outputs: list[Output] = field(...)# 输出端点列表
        hidden: list[Hidden] = field(...) # 隐藏上下文注入
        description: str = ""             # 节点说明文档 (Tooltip)
        search_aliases: list[str] = ...   # 搜索别名与缩写
        is_input_list: bool = False       # 是否接收列表输入
        is_output_node: bool = False      # 是否为终端汇聚节点
        not_idempotent: bool = False      # 是否禁用跨图缓存 (非幂等)
        enable_expand: bool = False       # 是否允许动态展开子图
        price_badge: PriceBadge = None    # 云端计费与资源徽章

4.2 双阶段校验与隐藏注入（``validate()`` & ``finalize()``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当节点被系统加载时，``_ComfyNodeBaseInternal.GET_SCHEMA()`` 会执行严格的静态断言：

1. **ID 唯一性探测（``Schema.validate()``）**：
   利用 ``collections.Counter`` 检查所有 ``inputs`` 与 ``outputs`` 的 ``id`` 是否在节点内全局唯一，发现重名立即抛出 ``ValueError``；
2. **隐藏上下文自动注水（``Schema.finalize()``）**：
   * 若 ``is_output_node=True``，自动在 ``hidden`` 中追加 ``Hidden.prompt`` 与 ``Hidden.extra_pnginfo``；
   * 若 ``is_api_node=True``，自动注水 ``Hidden.auth_token_comfy_org``、``Hidden.api_key_comfy_org`` 与 ``Hidden.comfy_usage_source``；
   * 为未指定 ID 的输出端点自动分配标准格式 ID ``f"_{i}_{output.io_type}_"``。

4.3 V1 格式双向转译器（``get_v1_info()``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了让现有的 ``PromptExecutor`` 与 Web 前端无需重写即可直接执行 V3 节点，``Schema.get_v1_info()`` 将 V3 对象动态序列化为标准的 ``NodeInfoV1`` 数据类，实现了底层运行时的零缝隙桥接。

------------------------------------------------------------------------

5. 执行规范化、类锁保护与历史迁移（``NodeReplace``）
----------------------------------------------------

5.1 标准化输出封装（``NodeOutput``）与执行标准化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

V3 节点的 ``execute()`` 方法统一返回 ``NodeOutput`` 对象：

.. code-block:: python

    class NodeOutput(_NodeOutputInternal):
        def __init__(self, *args: Any, ui: dict = None, expand: dict = None, block_execution: str = None):
            self.args = args                      # 传递给下游的主数据元组
            self.ui = ui                          # 发送给前端 UI 的展示字典 (如图片预览)
            self.expand = expand                  # 动态子图展开数据结构
            self.block_execution = block_execution# 执行阻断器消息

在 ``EXECUTE_NORMALIZED`` 包装器中，引擎自动将裸元组、字典或 ``ExecutionBlocker`` 归一化为 ``NodeOutput``，并对异步执行（``EXECUTE_NORMALIZED_ASYNC``）进行完全透明的 await 调度。

5.2 不可变类锁与状态隔离（``lock_class`` & ``shallow_clone_class``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了杜绝第三方插件在运行时通过修改类属性（Monkey-Patching）导致并发请求间的跨线程状态污染，ComfyUI 在执行前通过元类与浅拷贝实施**类级加锁保护**：

.. code-block:: python

    def lock_class(cls):
        def locked_instance_setattr(self, name, value):
            raise AttributeError(f"Cannot set attribute '{name}' on immutable instance")

        class LockedMeta(type(cls)):
            def __setattr__(cls_, name, value):
                raise AttributeError(f"Cannot modify class attribute '{name}' on locked class")

        locked_dict = dict(cls.__dict__)
        locked_dict['__setattr__'] = locked_instance_setattr
        return LockedMeta(cls.__name__, cls.__bases__, locked_dict)

每个执行请求通过 ``shallow_clone_class()`` 获得专有的类副本并注入当次请求的 ``HiddenHolder``，执行结束后立即销毁，确保了高并发下的绝对线程安全。

5.3 声明式节点历史迁移（``NodeReplace``）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当开发者对旧节点进行重构或废弃时，V3 API 提供了声明式的跨版本迁移契约 ``NodeReplace``：

.. code-block:: python

    class MyNewSampler(ComfyNode):
        REPLACEMENTS = [
            NodeReplace(
                new_node_id="MyNewSampler",
                old_node_id="MyOldSampler_v1",
                old_widget_ids=["steps", "cfg", "sampler_name"],
                input_mapping=[
                    {"new_id": "steps", "old_id": "steps"},
                    {"new_id": "guidance_scale", "old_id": "cfg"},
                    {"new_id": "solver", "old_id": "sampler_name"}
                ],
                output_mapping=[{"new_idx": 0, "old_idx": 0}]
            )
        ]

当用户加载包含 ``MyOldSampler_v1`` 的旧 JSON 工作流时，ComfyUI 服务端与前端会自动读取 ``NodeReplace`` 映射表，在内存中静默完成参数迁移与引脚重连，消除了重构对存量工作流的破坏。

------------------------------------------------------------------------

小结与下章导读
==============

本节系统剖析了 ComfyUI V3 API 面向对象节点范式与强类型体系：

1. **面向对象架构演进**：拆解了从 V1 字典反射到 ``ComfyNode`` 抽象继承契约的升级机理；
2. **强类型 I/O 系统**：推导了基于 ``@comfytype`` 的类型元类包装与 Widget 控件属性映射；
3. **高级动态泛型原语**：深入分析了 ``MatchType`` 多态约束、``Autogrow`` 动态自增长输入与 ``DynamicCombo`` 的实现；
4. **全生命周期安全防护**：解析了 ``Schema.validate()`` 静态断言、``lock_class`` 运行时不可变类锁与 ``NodeReplace`` 历史迁移机制。

在下一节（``03_server_and_rest_api_layer.rst``）中，我们将转向 ComfyUI 的网络通信中枢——**aiohttp 异步 Web 服务端架构与 RESTful API 路由层**：剖析 HTTP 服务的异步初始化、提示词提交（``/prompt``）校验流水线、执行队列状态查询以及客户端文件上传/下载的多线程非阻塞处理。
