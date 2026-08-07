第050章：硬件遮挡剔除
==================

核心知识点
----------

Hardware Occlusion 把深度证据转成渲染决策
   它利用 GPU depth buffer、occlusion query、HZB、predication 或 compute culling 判断候选对象是否被遮挡。输入是候选 bounds、深度、相机与分组信息，输出是“绘制、跳过、延后验证或保守保留”。

Depth buffer 是所有硬件遮挡方案的基础
   近处大型遮挡体必须先写入可信深度。候选代理随后和已有 depth 比较；若整个代理投影都在更近深度之后，就可以跳过真实对象。透明、细 alpha-tested 几何通常不适合作为主要遮挡证据。

Query-based occlusion 适合传统 draw-call 管线
   它绘制保守代理并统计 passing samples，结果可由 CPU 延迟读取或被 GPU predication 消费。优点是 API 路径直接、验证直观；缺点是额外 proxy draw、query 管理和结果延迟。

HZB 把深度组织成层级金字塔
   深度逐级降采样形成 mip，每级保存 tile 的保守深度。候选 bounds 投影到屏幕后，选择与投影尺寸匹配的 HZB 层级，用少量采样判断整个区域是否被遮挡。它特别适合 GPU-driven 大量实例或 cluster。

Query 与 HZB 的结果消费路径不同
   Query 常用于对象组级异步决策；HZB compute 更适合直接写 visible list、compacted instance list 或 indirect args，让结果留在 GPU。若 GPU-driven 结果又同步回 CPU 再提交 draw，会丢掉主要优势。

Predication / conditional rendering 负责消费查询结果
   Query 负责“测量”，predication 负责“根据结果是否执行 draw”。在显式 API 中，query heap/pool、result buffer、resource state 和 fence/barrier 都属于正确性的一部分。

遮挡粒度决定是否回本
   大型建筑组、room/cell、facade chunk 或 instance batch 一次决策能省掉很多 draw，更适合 query；大量细粒度候选则更适合 HZB/cluster compute。逐个小物体查询通常会让固定成本超过收益。

遮挡测试必须保守
   Proxy 必须覆盖真实对象可能出现的范围。Proxy 偏大只会 false visible；偏小会 false occluded 并直接造成漏绘。相机快速转向、门状态变化、动态遮挡体移动时，应临时回退到 visible。

时间连续性可以隐藏延迟
   当前帧优先沿用最近可见状态并继续验证，查询结果 ready 后更新下一帧。相机大角速度、near plane 明显变化、遮挡物移动或版本号改变时，旧结果应失效。

不同场景适合不同遮挡体
   城市街面可用大楼、桥梁、山体；森林更适合地形、岩石和林区 chunk，而不是逐树 query；室内已有 portal/cell 拓扑时，hardware occlusion 更适合作为门打开后的动态验证层。

完整可见性链应从便宜、确定的判断开始
   常见顺序是 ``chunk/streaming → frustum → distance → LOD → portal/cell → occlusion → visible list → draw``。Occlusion 不应处理本可由更便宜阶段排除的对象。

渲染可见性不能直接替代系统更新可见性
   某角色被墙挡住后可以跳过 mesh draw，但 AI、网络、物理、动画中的一部分是否更新属于其它系统策略。Occlusion 结果只能影响明确绑定到渲染成本的工作。

性能证据必须落到主瓶颈
   仅“剔除了很多对象”没有意义。应同时观察 occlusion/HZB pass 时间、main pass draw、fragment invocation、overdraw、bandwidth、CPU wait、barrier 和 frame time。若主 pass 没下降，剔除对象可能原本就不贵。

关键路径
--------

Query-based：

::

   frustum / portal / distance 缩小候选
   → depth prepass / 主要遮挡物写深度
   → draw conservative proxy
   → depth test + occlusion query
   → resolve result buffer
   → 后续帧检查 ready / fence
   → visible / fallback / occluded 状态
   → predication 或真实 draw decision

HZB GPU-driven：

::

   depth buffer
   → build hierarchical Z mip chain
   → candidate bounds projection
   → 选择匹配屏幕 footprint 的 HZB mip
   → conservative depth compare
   → write visible instance / cluster IDs
   → compaction / indirect args
   → barrier
   → indirect draw

闪烁/漏绘排查：

::

   检查 proxy 是否保守
   → 检查使用哪份 depth / HZB
   → 检查 reversed-Z 与比较方向
   → 检查 result source frame
   → 检查 camera velocity / door / occluder version invalidation
   → 检查 fallback-visible 规则
   → 最后检查 visible list / indirect args

概念辨析
--------

* **Early-Z 与 occlusion culling**：Early-Z 在真实 draw 内提前拒绝片元；occlusion culling 在真实 draw 前决定对象是否值得提交。
* **Occlusion Query 与 HZB**：前者利用固定管线查询统计，后者把 depth pyramid 作为可编程 compute 输入。
* **Query 与 predication**：query 产生结果，predication/conditional rendering 消费结果控制 draw。
* **Depth prepass 与 HZB build**：prepass 生成可信基础深度；HZB build 把它压成层级结构供 coarse 查询。
* **False visible 与 false occluded**：false visible 只是多做工作；false occluded 会破坏图像，因此所有遮挡测试都应偏保守。
* **Portal 与 hardware occlusion**：portal 使用室内拓扑约束；hardware occlusion 使用当前深度证据。前者先缩小候选，后者验证动态遮挡。
* **Object-group occlusion 与 cluster occlusion**：前者粒度粗、查询少，适合传统管线；后者粒度细，依赖 GPU compaction 和 indirect rendering。
* **剔除数量与性能收益**：真正指标是被节省的瓶颈成本，而不是隐藏对象个数。

本章结论
--------

Hardware Occlusion 应按“可信 depth—保守 proxy—query/HZB—异步或 GPU 侧消费—fallback—性能验证”理解。传统管线优先把 query 用在高成本对象组，GPU-driven 管线则更适合 HZB 和 cluster culling。正确性上要防止旧结果、错误深度和过小代理造成漏绘；性能上必须证明 occlusion 本身的 pass、barrier 与管理成本低于被省掉的主渲染工作。