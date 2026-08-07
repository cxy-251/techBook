第048章：Occlusion Query
=======================

核心知识点
----------

Occlusion Query 解决“在视锥内但被遮挡”的对象
   它利用 GPU 深度测试统计代理几何是否有 sample 通过。结果不是当前帧的立即真值，而是一份异步可见性证据，通常服务后续帧的 draw decision。

查询输入应是保守代理而非真实材质几何
   常见输入是 AABB、OBB、room bounds 或 object-group bounds。查询 pass 关闭颜色写入，通常只保留 depth test，并尽量避免复杂 pixel shader、纹理采样与状态切换。代理偏大只会 false visible，偏小则可能造成真实对象漏绘。

查询结果可以是计数或布尔可见性
   计数型结果给出通过深度测试的 sample 数，二值结果只回答是否存在可见 sample。多数剔除只需要布尔或小阈值；精确计数只有在估计屏幕面积、LOD 或优先级时才更有价值。

结果读取时机决定查询是否有收益
   当前帧立即读取当前帧 query，CPU 可能等待 GPU 完成前序命令，形成 stall。稳定做法是延迟一到两帧读取，并先检查 availability / fence。结果尚未准备好时应保守绘制。

时间连续性比单帧查询结果更重要
   ``Unknown``、``RecentlyVisible`` 等状态应偏向继续渲染；``Occluded`` 也要周期性复查。相机快速移动、遮挡体移动、门状态变化或经过固定时间后，应让旧结果失效并重新查询。

查询粒度必须与被节省的渲染成本匹配
   单个廉价小物体不值得一条独立 query；大型商铺、建筑组、房间、BVH node 或高成本 object group 更容易回本。查询成本包含代理绘制、query begin/end、结果存储、读取与同步。

Depth 输入必须包含主要遮挡体
   Query 依赖已有 depth buffer。若 depth prepass 漏掉主要墙体，或查询发生在遮挡体写入之前，结果会偏可见。反之，透明/alpha-tested 几何若不具备稳定深度，也不适合作为主遮挡证据。

OpenGL、Vulkan、D3D12 的对象不同，语义一致
   OpenGL 使用 query object；Vulkan 使用 ``VkQueryPool``；D3D12 使用 query heap 并 resolve 到 buffer。封装层应统一暴露 begin/end、availability、sample count、source frame，同时把 backend 的 reset、resolve、fence 与资源状态留在平台层。

查询 pass 应集中批量执行
   统一 pipeline、depth buffer 与 proxy format，可以减少状态切换并让 query pass 的 GPU 时间更容易测量。大量零散 begin/end 查询会放大 CPU 命令与 GPU 状态管理成本。

Occlusion Query 最适合稳定大遮挡场景
   城市街区、室内走廊、多房间建筑、地下设施等场景有大块遮挡体和高成本被遮挡对象。空旷场景、透明粒子场和大量小动态对象通常收益低。

现代 GPU-driven 管线常用 HZB 替代大量小 query
   Query 适合对象组级、延迟可见性；HZB compute culling 把 depth pyramid 留在 GPU 侧，对大量实例/cluster 并行测试并直接生成 indirect list。两者是不同粒度与消费路径的工具。

关键路径
--------

典型查询：

::

   frustum / portal 得到候选组
   → 主要遮挡物写入 depth
   → begin occlusion query
   → draw conservative proxy bounds
   → depth test 统计 passing samples
   → end query
   → result storage
   → 后续帧检查 availability
   → 更新 visibility state
   → visible / pending: 保守提交真实 draw
   → stable occluded: 跳过真实 draw

状态更新：

::

   Unknown
   → 查询 + 保守可见
   → RecentlyVisible
   → 连续验证
   → Occluded
   → 周期性复查 / 相机或遮挡状态变化
   → QueryIssued
   → 新结果更新状态

性能排查：

::

   query pass GPU time
   → proxy draw count / 覆盖像素
   → CPU availability wait 次数
   → 被减少的真实 draw
   → geometry / fragment pass 时间变化
   → overdraw / bandwidth
   → 若查询成本高于节省，合并粒度或改 HZB

概念辨析
--------

* **Occlusion Query 与 depth test**：depth test 是片元级可见性机制；query 把一段深度测试结果统计成可供后续决策的数据。
* **Query 与 HZB**：query 由固定图形管线产生结果，常延迟消费；HZB 把深度金字塔作为纹理，由 compute shader 主动测试大量 bounds。
* **Passed samples 与 visible object**：代理有 sample 通过只表示对象“可能可见”，并不保证真实几何最终有明显像素贡献。
* **False visible 与 false occluded**：前者只是多画，后者会漏绘。保守系统优先接受 false visible。
* **Result available 与 result value**：先确认结果是否已经完成，再读取值；把“未完成”误当“不可见”会制造闪烁。
* **Occluded 与 permanently hidden**：遮挡状态是时间相关的，需要在相机、门和遮挡体变化后重新验证。
* **逐物体查询与分层查询**：逐物体更精细但 query 数量大；cell/block/node 级查询更容易摊销固定成本。

本章结论
--------

Occlusion Query 应按“可信 depth—保守代理—异步统计—延迟读取—状态缓存—保守 fallback”理解。最大风险不是查询精度，而是同步等待和过期结果。大型场景应先用 frustum/portal 缩小候选，再只查询值得回本的高成本对象组，并用 query pass 时间、CPU wait、真实 draw 与 fragment 成本的下降证明优化有效。